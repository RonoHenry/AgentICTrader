"""The command line: python -m algo_backtester check-data | run | compare | report.

    python -m algo_backtester check-data config/backtests/base.toml
    python -m algo_backtester run config/backtests/base.toml [--variant min_rr_5] [--final] [--walk-forward 3M]
    python -m algo_backtester compare data/backtests/<run_id> data/backtests/<run_id> [--by killzone]
    python -m algo_backtester report data/backtests/<run_id>
    python -m algo_backtester report --forward-test data/paper_trades.json --profile binance

check-data loads every instrument's history for the run and reports coverage
problems and warm-up sources (Req 3.6). On first use it also creates the
run's study: the hold-out is the last 3 months of the data in the store (D7),
and it never moves afterwards.

run refuses, before any work:
- a run that reaches into its study's hold-out, unless ``--final`` (Req 7.2);
- data with coverage problems, unless ``[data] allow_gaps``.
It then runs Phase A (cached in data/backtests/cache/ unless ``--no-cache``)
and Phase B, and writes data/backtests/<run_id>/, report.html included.

compare puts finished runs side by side; runs on different data are refused.

report rewrites a run's report.html from its recorded files, or renders a
paper forward test's trades file with candles from the store (Req 11.7).

Candles come from the TimescaleDB store (TIMESCALE_URL, from the environment
or .env): the rows of the profile's venue, mt5 or binance.

Exit codes: 0 done; 1 data problems; 2 refused (the hold-out, or runs that
can't be compared).

Validates: Requirements 7.1 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

from agent.broker_profiles import BrokerProfile, load_profile
from algo_backtester.cache import SignalCache, engine_code_fingerprint
from algo_backtester.compare import ComparisonError, compare
from algo_backtester.config import (
    REPO_ROOT,
    STUDIES_DIR,
    HoldoutOverlapError,
    RunConfig,
    StudyConfig,
    check_holdout,
    load_or_create_study,
    load_run_config,
)
from algo_backtester.data import CandleSource, CoverageError, InstrumentData, TimescaleSource, ensure_coverage, load_instrument
from algo_backtester.report import RUNS_DIR, build_manifest, git_state, spec_source, write_run
from algo_backtester.report_html import build_forward_test, render, write_html_report, write_report_inputs
from algo_backtester.run import run_backtest
from liquidity_engine.models import Timeframe
from services.market_data.as_of_view import aggregate
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["main", "parse_args"]

SourceFactory = Callable[[BrokerProfile], CandleSource]


class _DataProblem(Exception):
    pass


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m algo_backtester",
                                     description="Backtest the live agent's decisions on stored M1 history.")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check-data", help="report data coverage; create the study's hold-out on first use")
    check.add_argument("config", help="run configuration, e.g. config/backtests/base.toml")
    check.add_argument("--variant", help="a [variants.<name>] of the configuration")

    run = commands.add_parser("run", help="run a backtest and write data/backtests/<run_id>/")
    run.add_argument("config", help="run configuration, e.g. config/backtests/base.toml")
    run.add_argument("--variant", help="a [variants.<name>] of the configuration")
    run.add_argument("--final", action="store_true", help="the final validation run: may use the hold-out")
    run.add_argument("--walk-forward", metavar="PERIOD", help="consecutive windows, e.g. 3M, 2W, 10D")
    run.add_argument("--workers", type=int, help="processes for Phase A (default: one per instrument)")
    run.add_argument("--no-cache", action="store_true", help="recompute Phase A instead of using the cache")
    run.add_argument("--runs-dir", type=Path, default=RUNS_DIR, help=f"where runs are written (default {RUNS_DIR})")

    cmp = commands.add_parser("compare", help="put finished runs side by side")
    cmp.add_argument("run_dirs", nargs="+", type=Path, help="run directories, data/backtests/<run_id>")
    cmp.add_argument("--by", help="one breakdown instead of the overall figures, e.g. killzone")

    rep = commands.add_parser("report", help="(re)write a run's report.html, or one for a paper forward test")
    rep.add_argument("run_dir", nargs="?", type=Path, help="a run directory, data/backtests/<run_id>")
    rep.add_argument("--forward-test", type=Path, metavar="TRADES_JSON", help="the paper broker's trades file")
    rep.add_argument("--profile", help="the forward test's broker profile (its candles come from the store)")
    rep.add_argument("--entry-tf", default="M15", help="chart timeframe for a forward test (default M15)")
    rep.add_argument("--out", type=Path, help="where to write a forward test's report (default: beside the trades)")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None, source_factory: Optional[SourceFactory] = None,
         studies_root: Path = REPO_ROOT) -> int:
    """``source_factory`` and ``studies_root`` exist for tests: the candle
    store and where config/backtests/studies/ lives."""
    args = parse_args(argv)
    if args.command == "compare":
        try:
            print(compare(args.run_dirs, by=args.by), end="")
        except ComparisonError as exc:
            print(f"refused: {exc}")
            return 2
        return 0
    if args.command == "report":
        return _report(args, source_factory or _store)

    cfg = load_run_config(args.config, args.variant)
    profile = load_profile(cfg.run.profile)
    source = (source_factory or _store)(profile)
    try:
        study, created = _study(cfg, source, studies_root)
        if args.command == "check-data":
            return _check_data(cfg, profile, source, study, created)
        return _run(args, cfg, profile, source, study)
    except HoldoutOverlapError as exc:
        print(f"refused: {exc}")
        return 2
    except (_DataProblem, CoverageError) as exc:
        print(f"data problem: {exc}")
        return 1


def _store(profile: BrokerProfile) -> CandleSource:
    from agent.broker_profiles import _default_getenv

    url = _default_getenv()("TIMESCALE_URL")
    if not url:
        raise SystemExit("TIMESCALE_URL is not set (add it to .env)")
    return TimescaleSource(url, source=profile.venue)


def _study(cfg: RunConfig, source: CandleSource, root: Path) -> tuple[StudyConfig, bool]:
    """The run's study, created from the latest stored M1 if it doesn't exist yet."""
    if (root / STUDIES_DIR / f"{cfg.run.study}.toml").exists():
        return load_or_create_study(cfg.run.study, date.today(), root), False
    lasts = {i: source.last_time(i, Timeframe.M1) for i in cfg.run.instruments}
    missing = [i for i, last in lasts.items() if last is None]
    if missing:
        raise _DataProblem(f"no M1 history in the store for {', '.join(missing)}")
    # The hold-out must be data every instrument has: count back from the earliest end.
    return load_or_create_study(cfg.run.study, min(lasts.values()).date(), root), True


def _load(cfg: RunConfig, profile: BrokerProfile, source: CandleSource) -> dict[str, InstrumentData]:
    start = datetime(cfg.run.start.year, cfg.run.start.month, cfg.run.start.day, tzinfo=timezone.utc)
    end = datetime(cfg.run.end.year, cfg.run.end.month, cfg.run.end.day, tzinfo=timezone.utc)
    clock = profile.clock() if profile.venue == "mt5" else None
    return {i: load_instrument(source, i, start, end, cfg.strategy, clock, venue=profile.venue,
                               max_gap_minutes=cfg.data.max_gap_minutes)
            for i in cfg.run.instruments}


def _check_data(cfg: RunConfig, profile: BrokerProfile, source: CandleSource, study: StudyConfig,
                created: bool) -> int:
    print(f"{cfg.run.profile} ({profile.venue}), {cfg.run.start} to {cfg.run.end} (end exclusive)")
    datas = _load(cfg, profile, source)
    for instrument, data in datas.items():
        coverage = data.coverage
        span = (f"M1 {coverage.first:%Y-%m-%d %H:%M} .. {coverage.last:%Y-%m-%d %H:%M} UTC"
                if coverage.first else "no M1 in range")
        warmup = ", ".join(f"{tf} {src}" for tf, src in data.warmup_source.items())
        status = "ok" if coverage.ok else f"{len(coverage.problems)} problem(s)"
        print(f"{instrument}: {status}; {span}; {data.fingerprint.rows} rows; warm-up {warmup}")
        for problem in coverage.problems:
            print(f"  - {problem}")
    how = "created now from the latest stored data" if created else "set when the study was created"
    print(f"study {study.name}: hold-out from {study.holdout_start} ({how})")
    problems = any(not d.coverage.ok for d in datas.values())
    if problems and cfg.data.allow_gaps:
        print("coverage problems are allowed by [data] allow_gaps; runs will record them in the manifest")
        return 0
    return 1 if problems else 0


def _run(args: argparse.Namespace, cfg: RunConfig, profile: BrokerProfile, source: CandleSource,
         study: StudyConfig) -> int:
    check_holdout(cfg, study, args.final)
    print(f"loading {', '.join(cfg.run.instruments)} from {cfg.run.start} to {cfg.run.end}...")
    datas = _load(cfg, profile, source)
    ensure_coverage([d.coverage for d in datas.values()], cfg.data.allow_gaps)
    specs = profile.specs()
    cache = None if args.no_cache else SignalCache.default()

    # Refused orders and risk rejections are expected outcomes: the journal records each with its reason.
    logging.getLogger("agent").setLevel(logging.CRITICAL)
    print("Phase A (signals) and Phase B (account)...")
    result = run_backtest(cfg, study, args.final, datas, specs, cache=cache, walk_forward=args.walk_forward,
                          workers=args.workers)
    manifest = build_manifest(
        cfg, result, datas, specs, spec_source=spec_source(profile.spec_file),
        engine_fingerprint=cache.engine_fingerprint if cache else engine_code_fingerprint(),
        git=git_state(), created_at=datetime.now(timezone.utc),
    )
    run_dir = write_run(args.runs_dir, cfg, manifest, result)
    entry_tf = cfg.strategy.entry_tf
    write_report_inputs(run_dir, result.journal, {i: d.closed[entry_tf] for i, d in datas.items()}, entry_tf,
                        cfg.report.chart_bars_before, cfg.report.chart_bars_after, m1=result.bars,
                        account_ccy=specs.account_ccy)
    report = write_html_report(run_dir)
    counts = {"journal rows": len(result.journal), "closed": len(result.trades), "open": len(result.open_orders)}
    print(f"wrote {run_dir}  ({', '.join(f'{k} {v}' for k, v in counts.items())})")
    print(f"summary: {run_dir / 'summary.md'}")
    print(f"report:  {report}")
    return 0


def _report(args: argparse.Namespace, source_factory: SourceFactory) -> int:
    if args.forward_test is None:
        if args.run_dir is None or not (args.run_dir / "candles.json").is_file():
            print(f"refused: {args.run_dir} is not a run directory with report inputs (candles.json)")
            return 2
        print(f"report: {write_html_report(args.run_dir)}")
        return 0

    if args.profile is None:
        print("refused: --forward-test needs --profile (its candles come from the store)")
        return 2
    trades = json.loads(args.forward_test.read_text(encoding="utf-8"))
    entry_tf = Timeframe(args.entry_tf)
    source = source_factory(load_profile(args.profile))
    margin = timedelta(minutes=15) * 100
    candles = {}
    for instrument in sorted({t["instrument"] for t in trades}):
        mine = [t for t in trades if t["instrument"] == instrument]
        start = min(datetime.fromisoformat(t["placed_at"]) for t in mine) - margin
        end = max(datetime.fromisoformat(t.get("closed_at") or t["placed_at"]) for t in mine) + margin
        m1 = source.bars(instrument, Timeframe.M1, start.astimezone(timezone.utc), end.astimezone(timezone.utc))
        candles[instrument] = aggregate(m1, entry_tf, StrategyCalendar()) if m1 else []
    model = build_forward_test(trades, candles, entry_tf, source=args.forward_test.name)
    out = args.out or args.forward_test.with_suffix(".report.html")
    out.write_text(render(model), encoding="utf-8", newline="\n")
    print(f"report: {out}")
    return 0
