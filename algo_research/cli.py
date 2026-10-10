"""The command line: python -m algo_research snapshot | build | explore | run | ledger.

    python -m algo_research snapshot [--name NAME] [--profile NAME]   # export the study's candles (needs Docker, once)
    python -m algo_research build [--no-cache]                        # the feature and label tables (cached)
    python -m algo_research explore H002                              # exploration slice: terminal + drafts only
    python -m algo_research run H002                                  # confirmation slice: report + ledger row
    python -m algo_research ledger                                    # render docs/research/LEDGER.md

snapshot reads the research period's candles from the broker profile's
candle store (TIMESCALE_URL, from the environment or .env) and writes
data/research/snapshots/<name>/. It refuses a period reaching the study's
hold-out, and never overwrites an existing snapshot.

build loads the snapshot (refusing data that no longer matches its
manifest) and builds the tables hypotheses read, cached in
data/research/cache/. No Docker needed.

explore runs a hypothesis on the exploration slice, prints the result and
writes a draft report to data/research/drafts/. It never touches the ledger.

run is an official test, on the confirmation slice. Before reading any data it
refuses (Property 11):
- a hypothesis file that isn't committed, or has uncommitted changes;
- uncommitted changes in algo_research/;
- an id already in the ledger under another hash: a changed question is a
  new hypothesis, with ``supersedes``.
It then writes docs/research/reports/H<nnn>.md and appends one ledger row per
test. When the ledger already holds this hash, it recomputes and compares
instead, and a different result is an error naming the fields (Property 9).

Exit codes: 0 done; 1 data problems or a result that didn't reproduce; 2 refused.

Validates: Requirements 1.1, 8.2-8.4, 12.1-12.4, 13.1 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import argparse
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

from agent.broker_profiles import BrokerProfile, load_profile
from algo_backtester.data import CandleSource, TimescaleSource
from algo_backtester.report import git_state, spec_source
from algo_research.config import REPO_ROOT, HoldoutError, ResearchConfig, load_research_config
from algo_research.dataset import ResearchData, build_dataset, build_frames
from algo_research.features.cache import CACHE_DIR, ParquetCache
from algo_research.frame import slices_of
from algo_research.hypothesis import Hypothesis, HypothesisError, find_hypothesis, load_hypothesis
from algo_research.ledger import append_rows, ledger_row, read_ledger, render_ledger_md, result_differences
from algo_research.profile import instrument_profile, render_profile
from algo_research.races import RaceCosts
from algo_research.report import ReportInputs, render_report
from algo_research.runner import RunSettings, TestResult, run_test
from algo_research.snapshot import SNAPSHOTS_DIR, SnapshotError, SnapshotSpec, export_snapshot, load_snapshot
from algo_research.stats import seed_from

__all__ = ["main", "parse_args", "preregistration_problems"]

SourceFactory = Callable[[BrokerProfile], CandleSource]
DRAFTS_DIR = REPO_ROOT / "data" / "research" / "drafts"
HYPOTHESES = Path("config") / "research" / "hypotheses"
DOCS = Path("docs") / "research"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m algo_research",
                                     description="Ask whether a condition predicts what price does next.")
    parser.add_argument("--config", type=Path, help="research configuration (default config/research/research.toml)")
    commands = parser.add_subparsers(dest="command", required=True)

    snap = commands.add_parser("snapshot", help="export the study's candles to data/research/snapshots/<name>/")
    snap.add_argument("--name", help="snapshot name (default: research.toml's snapshot)")
    snap.add_argument("--profile", help="broker profile (default: research.toml's profile)")

    build = commands.add_parser("build", help="build the feature and label tables from the snapshot (cached)")
    build.add_argument("--no-cache", action="store_true", help="recompute every table instead of using the cache")
    build.add_argument("--workers", type=int, help="processes for the engine passes (default: one per instrument)")

    for name, text in (("explore", "run a hypothesis on the exploration slice (drafts only, no ledger)"),
                       ("run", "the official test on the confirmation slice: report and ledger row")):
        command = commands.add_parser(name, help=text)
        command.add_argument("hypothesis", help="its id, e.g. H002 (config/research/hypotheses/H002-*.toml)")
        command.add_argument("--workers", type=int, help="processes for a build the cache can't serve")

    commands.add_parser("ledger", help="render docs/research/LEDGER.md from docs/research/ledger.csv")
    commands.add_parser("profile", help="write docs/research/VOLATILITY_PROFILE.md: where each instrument makes "
                                        "its range (exploration slice; descriptive, no ledger)")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None, source_factory: Optional[SourceFactory] = None,
         root: Path = REPO_ROOT, snapshots_dir: Path = SNAPSHOTS_DIR, cache_dir: Path = CACHE_DIR,
         drafts_dir: Path = DRAFTS_DIR, now: Optional[Callable[[], datetime]] = None) -> int:
    """The keyword arguments exist for tests: the candle store, the repository
    root (config, hypotheses, docs/research and the git checks), where
    snapshots, the cache and drafts live, and the clock."""
    args = parse_args(argv)
    now = now or (lambda: datetime.now(timezone.utc))
    try:
        if args.command == "ledger":
            return _ledger(root)
        cfg = load_research_config(args.config, root=root)
        if args.command == "snapshot":
            return _snapshot(args, cfg, source_factory or _store, root, snapshots_dir)
        if args.command == "build":
            return _build(args, cfg, root, snapshots_dir, cache_dir)
        if args.command == "explore":
            return _explore(args, cfg, root, snapshots_dir, cache_dir, drafts_dir, now)
        if args.command == "run":
            return _run(args, cfg, root, snapshots_dir, cache_dir, now)
        if args.command == "profile":
            return _profile(cfg, root, snapshots_dir)
    except (HoldoutError, SnapshotError, HypothesisError) as exc:
        print(f"refused: {exc}")
        return 2
    raise AssertionError(f"unhandled command {args.command}")


def _store(profile: BrokerProfile) -> CandleSource:
    from agent.broker_profiles import _default_getenv

    url = _default_getenv()("TIMESCALE_URL")
    if not url:
        raise SystemExit("TIMESCALE_URL is not set (add it to .env)")
    return TimescaleSource(url, source=profile.venue)


# ── snapshot and build ─────────────────────────────────────────────────────

def _snapshot(args: argparse.Namespace, cfg, source_factory: SourceFactory, root: Path,
              snapshots_dir: Path) -> int:
    profile = load_profile(args.profile or cfg.profile)
    run = cfg.run(root)
    spec = SnapshotSpec(
        name=args.name or cfg.snapshot, profile=profile.name, venue=profile.venue, source=profile.venue,
        instruments=cfg.instruments, start=cfg.start, end=cfg.holdout_start, study=cfg.study,
        holdout_start=cfg.holdout_start, strategy=run.strategy,
        clock=profile.clock() if profile.venue == "mt5" else None, max_gap_minutes=run.data.max_gap_minutes,
        spec_source=spec_source(profile.spec_file) if profile.spec_file is not None else None,
    )
    print(f"snapshot {spec.name}: {profile.name} ({profile.venue}), {', '.join(spec.instruments)}, "
          f"trading dates {spec.start} to {spec.end} (end exclusive; hold-out from {spec.holdout_start})")
    manifest = export_snapshot(source_factory(profile), spec, snapshots_dir, git_commit=git_state().commit,
                               created_at=datetime.now(timezone.utc))
    for instrument, entry in manifest["data"].items():
        problems = entry["coverage_problems"]
        print(f"{instrument}: {entry['rows']} rows ({', '.join(f'{tf} {n}' for tf, n in entry['files'].items())}); "
              f"{len(problems)} coverage problem(s)")
        for problem in problems:
            print(f"  - {problem}")
    print(f"wrote {snapshots_dir / spec.name}")
    return 0


def _load(cfg: ResearchConfig, root: Path, snapshots_dir: Path, cache_dir: Optional[Path],
          workers: Optional[int]):
    snapshot = load_snapshot(snapshots_dir / cfg.snapshot, cfg.instruments)
    specs = load_profile(cfg.profile).specs()
    data = build_dataset(snapshot, cfg, specs, cfg.strategy(root), ParquetCache(cache_dir) if cache_dir else None,
                         workers=workers)
    return snapshot, specs, data


def _build(args: argparse.Namespace, cfg: ResearchConfig, root: Path, snapshots_dir: Path, cache_dir: Path) -> int:
    started = time.perf_counter()
    print(f"loading snapshot {cfg.snapshot} ({', '.join(cfg.instruments)}), checking fingerprints...")
    snapshot, _, data = _load(cfg, root, snapshots_dir, None if args.no_cache else cache_dir, args.workers)
    summary = data.summary
    for instrument, entry in snapshot.manifest["data"].items():
        if instrument in data.frames:
            problems = entry["coverage_problems"]
            print(f"{instrument}: {summary['rows'][instrument]} rows; {len(problems)} coverage problem(s) in the snapshot")
    print("timings: " + ", ".join(f"{name} {seconds:.1f}s" for name, seconds in summary["timings"].items()))
    if summary["cache_hits"]:
        print(f"from the cache: {', '.join(summary['cache_hits'])}")
    errors = summary["engine_errors"]
    print(f"engine: {len(errors)} day(s) without an anticipation (left null)")
    for message in errors[:20]:
        print(f"  - {message}")
    print(f"built in {time.perf_counter() - started:.1f}s")
    return 0


# ── explore and run ────────────────────────────────────────────────────────

def _results(h: Hypothesis, cfg: ResearchConfig, data: ResearchData, specs, slice_name: str) -> list[TestResult]:
    costs = {i: RaceCosts.from_spec(specs[i], specs.account_ccy) for i in data.frames}
    settings = RunSettings(resamples=cfg.bootstrap.resamples, random_time_draws=cfg.baselines.random_time_draws,
                           shuffles=cfg.baselines.shuffles)
    return [run_test(test, data, slice_name, costs, seed_from(h.sha256, test.index), settings) for test in h.tests()]


def _inputs(h: Hypothesis, cfg: ResearchConfig, snapshot, specs, commit: str, seqs: dict) -> ReportInputs:
    fingerprints = {i: f"{d['rows']} rows, sha256 {d['sha256']}" for i, d in snapshot.manifest["data"].items()
                    if i in cfg.instruments}
    costs = {i: {"typical spread": specs[i].default_spread, "stop slippage": specs[i].stop_slippage,
                 "commission": f"{specs[i].commission.value:g} {specs[i].commission.kind}"} for i in cfg.instruments}
    return ReportInputs(snapshot=cfg.snapshot, fingerprints=fingerprints, code_commit=commit, specs=costs,
                        hypothesis_text=h.path.read_text(encoding="utf-8"), ledger_rows=seqs)


def _profile(cfg: ResearchConfig, root: Path, snapshots_dir: Path) -> int:
    """Req 21.3: the volatility profile of the exploration slice, descriptive; no ledger."""
    snapshot = load_snapshot(snapshots_dir / cfg.snapshot, cfg.instruments)
    frames = build_frames(snapshot, load_profile(cfg.profile).specs())
    start, end = slices_of(cfg)["explore"]
    profiles = [instrument_profile(frames[i], start, end) for i in cfg.instruments if i in frames]
    text = render_profile(profiles, {"snapshot": cfg.snapshot, "slice": f"exploration slice, {start} to {end} "
                                     f"(end exclusive)", "code_commit": _commit(root)})
    out = root / DOCS / "VOLATILITY_PROFILE.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out} (descriptive: no verdict, no ledger row)")
    return 0


def _explore(args, cfg: ResearchConfig, root: Path, snapshots_dir: Path, cache_dir: Path, drafts_dir: Path,
             now) -> int:
    h = load_hypothesis(find_hypothesis(args.hypothesis, root / HYPOTHESES))
    snapshot, specs, data = _load(cfg, root, snapshots_dir, cache_dir, args.workers)
    results = _results(h, cfg, data, specs, "explore")
    for r in results:
        print(f"{r.label} [explore]: {r.verdict}; {r.n_events} events on {r.n_dates} dates; skipped "
              f"{ {k: v for k, v in r.skipped.items() if v} }")
        for o in r.outcomes:
            versus = f" vs {o.versus}" if o.versus else ""
            print(f"  {o.stat}{versus}: {o.estimate:.4f} [{o.lo:.4f}, {o.hi:.4f}] -> {'pass' if o.passed else 'fail'}")
    drafts_dir.mkdir(parents=True, exist_ok=True)
    draft = drafts_dir / f"{h.id}-{now():%Y%m%d-%H%M%S}.md"
    draft.write_text(render_report(results, _inputs(h, cfg, snapshot, specs, _commit(root), {})),
                     encoding="utf-8", newline="\n")
    print(f"draft: {draft} (not in the ledger)")
    return 0


def _run(args, cfg: ResearchConfig, root: Path, snapshots_dir: Path, cache_dir: Path, now) -> int:
    path = find_hypothesis(args.hypothesis, root / HYPOTHESES)
    h = load_hypothesis(path)
    ledger_path = root / DOCS / "ledger.csv"
    rows = read_ledger(ledger_path)
    problems = preregistration_problems(path, root, rows, h)
    if problems:
        for problem in problems:
            print(f"refused: {problem}")
        return 2

    snapshot, specs, data = _load(cfg, root, snapshots_dir, cache_dir, args.workers)
    results = _results(h, cfg, data, specs, h.slice)
    commit = _commit(root)
    report_rel = (DOCS / "reports" / f"{h.id}.md").as_posix()
    recorded = {r["test"]: r for r in rows if r["hypothesis"] == h.id and r["sha256"] == h.sha256}
    if recorded:
        return _reproduce(results, recorded, cfg, commit, report_rel)

    run_at = now().isoformat(timespec="seconds")
    new_rows = [ledger_row(r, seq=len(rows) + 1 + i, run_at=run_at, snapshot=cfg.snapshot, code_commit=commit,
                           report=report_rel) for i, r in enumerate(results)]
    seqs = {r.label: row["seq"] for r, row in zip(results, new_rows)}
    report = root / report_rel
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(results, _inputs(h, cfg, snapshot, specs, commit, seqs)), encoding="utf-8",
                      newline="\n")
    append_rows(ledger_path, new_rows)
    (root / DOCS / "LEDGER.md").write_text(render_ledger_md(read_ledger(ledger_path)), encoding="utf-8", newline="\n")
    for r, row in zip(results, new_rows):
        print(f"{r.label}: {r.verdict}; {r.n_events} events on {r.n_dates} dates (ledger row {row['seq']})")
    print(f"report: {report}")
    return 0


def _reproduce(results: list[TestResult], recorded: dict, cfg: ResearchConfig, commit: str, report_rel: str) -> int:
    failed = False
    for r in results:
        before = recorded.get(r.test.name)
        if before is None:
            print(f"{r.label}: not in the ledger with this hash; rerun cannot add tests to a recorded hypothesis")
            failed = True
            continue
        now_row = ledger_row(r, seq=int(before["seq"]), run_at=before["run_at"], snapshot=cfg.snapshot,
                             code_commit=commit, report=report_rel)
        different = result_differences(before, now_row)
        if different:
            print(f"{r.label}: the rerun differs from ledger row {before['seq']} in "
                  + ", ".join(f"{name} ({before.get(name)!r} -> {now_row[name]!r})" for name in different))
            failed = True
        else:
            print(f"{r.label}: reproduced ledger row {before['seq']} exactly")
    return 1 if failed else 0


def _ledger(root: Path) -> int:
    rows = read_ledger(root / DOCS / "ledger.csv")
    path = root / DOCS / "LEDGER.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_ledger_md(rows), encoding="utf-8", newline="\n")
    print(f"{len(rows)} official test(s); wrote {path}")
    return 0


# ── pre-registration (Property 11) ─────────────────────────────────────────

def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _commit(root: Path) -> str:
    result = _git(root, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def preregistration_problems(path: Path, root: Path, ledger_rows: Sequence[dict], h: Hypothesis) -> list[str]:
    """Why ``run`` must refuse this hypothesis now; empty when it may run."""
    problems = []
    rel = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    if _git(root, "ls-files", "--error-unmatch", "--", rel).returncode != 0:
        problems.append(f"{rel} is not committed. Commit it first: the commit is the pre-registration.")
    elif _git(root, "diff", "--quiet", "HEAD", "--", rel).returncode != 0:
        problems.append(f"{rel} has uncommitted changes. Commit them, or put a changed question in a new "
                        f"hypothesis with supersedes = \"{h.id}\".")
    if _git(root, "status", "--porcelain", "--", "algo_research").stdout.strip():
        problems.append("algo_research/ has uncommitted changes: commit the code first, so the result names "
                        "the code that produced it.")
    other = {r["sha256"] for r in ledger_rows if r["hypothesis"] == h.id} - {h.sha256}
    if other:
        problems.append(f"{h.id} is already in the ledger with another hash: a changed question is a new "
                        f"hypothesis. Write a new id with supersedes = \"{h.id}\"; both count.")
    return problems
