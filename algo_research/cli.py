"""The command line: python -m algo_research snapshot | build | explore | run | ledger.

    python -m algo_research snapshot [--name NAME] [--profile NAME]   # export the study's candles (needs Docker, once)
    python -m algo_research build [--no-cache]                        # the feature and label tables (cached)

snapshot reads the research period's candles from the broker profile's
candle store (TIMESCALE_URL, from the environment or .env) and writes
data/research/snapshots/<name>/. It refuses a period reaching the study's
hold-out, and never overwrites an existing snapshot.

build loads the snapshot (refusing data that no longer matches its
manifest) and builds the tables hypotheses read, cached in
data/research/cache/. No Docker needed.

Exit codes: 0 done; 1 data problems; 2 refused.

Validates: Requirements 1.1 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

from agent.broker_profiles import BrokerProfile, load_profile
from algo_backtester.data import CandleSource, TimescaleSource
from algo_backtester.report import git_state, spec_source
from algo_research.config import REPO_ROOT, HoldoutError, ResearchConfig, load_research_config
from algo_research.dataset import build_dataset
from algo_research.features.cache import CACHE_DIR, ParquetCache
from algo_research.snapshot import SNAPSHOTS_DIR, SnapshotError, SnapshotSpec, export_snapshot, load_snapshot

__all__ = ["main", "parse_args"]

SourceFactory = Callable[[BrokerProfile], CandleSource]


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
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None, source_factory: Optional[SourceFactory] = None,
         root: Path = REPO_ROOT, snapshots_dir: Path = SNAPSHOTS_DIR, cache_dir: Path = CACHE_DIR) -> int:
    """``source_factory``, ``root``, ``snapshots_dir`` and ``cache_dir`` exist for
    tests: the candle store, the repository root, and where snapshots and the
    cache live."""
    args = parse_args(argv)
    try:
        cfg = load_research_config(args.config, root=root)
        if args.command == "snapshot":
            return _snapshot(args, cfg, source_factory or _store, root, snapshots_dir)
        if args.command == "build":
            return _build(args, cfg, root, snapshots_dir, cache_dir)
    except (HoldoutError, SnapshotError) as exc:
        print(f"refused: {exc}")
        return 2
    raise AssertionError(f"unhandled command {args.command}")


def _store(profile: BrokerProfile) -> CandleSource:
    from agent.broker_profiles import _default_getenv

    url = _default_getenv()("TIMESCALE_URL")
    if not url:
        raise SystemExit("TIMESCALE_URL is not set (add it to .env)")
    return TimescaleSource(url, source=profile.venue)


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


def _build(args: argparse.Namespace, cfg: ResearchConfig, root: Path, snapshots_dir: Path, cache_dir: Path) -> int:
    started = time.perf_counter()
    print(f"loading snapshot {cfg.snapshot} ({', '.join(cfg.instruments)}), checking fingerprints...")
    snapshot = load_snapshot(snapshots_dir / cfg.snapshot, cfg.instruments)
    loaded = time.perf_counter() - started
    specs = load_profile(cfg.profile).specs()
    data = build_dataset(snapshot, cfg, specs, cfg.strategy(root), None if args.no_cache else ParquetCache(cache_dir),
                         workers=args.workers)
    summary = data.summary
    for instrument, entry in snapshot.manifest["data"].items():
        if instrument in data.frames:
            problems = entry["coverage_problems"]
            print(f"{instrument}: {summary['rows'][instrument]} rows; {len(problems)} coverage problem(s) in the snapshot")
    timings = {"snapshot": loaded, **summary["timings"]}
    print("timings: " + ", ".join(f"{name} {seconds:.1f}s" for name, seconds in timings.items()))
    if summary["cache_hits"]:
        print(f"from the cache: {', '.join(summary['cache_hits'])}")
    errors = summary["engine_errors"]
    print(f"engine: {len(errors)} day(s) without an anticipation (left null)")
    for message in errors[:20]:
        print(f"  - {message}")
    print(f"built in {time.perf_counter() - started:.1f}s")
    return 0
