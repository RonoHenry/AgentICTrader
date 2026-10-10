"""Running a backtest: the hold-out guard, Phase A once, Phase B per window.

    study = load_or_create_study(cfg.run.study, data_end)
    result = run_backtest(cfg, study, final=False, datas=datas, specs=profile.specs,
                          cache=SignalCache.default(), walk_forward="3M")
    result.journal, result.trades     # all windows, concatenated
    result.windows[0].result          # one window's own SimulationResult
    result.manifest                   # the run-mode fields: study, hold-out, final flag, windows
    result.bars                       # the M1 bars Phase B priced fills on (bid, with the spread used)

In order:
1. Before any work, refuse a run that reaches into its study's hold-out
   unless it is the final validation run (Req 7.2). Also refuse an instrument
   the account can't price: a cross, whose quote currency needs a conversion
   rate over time, isn't supported yet.
2. Phase A once over [start, end), per instrument, through the cache.
3. Phase B once per window: the whole range, or consecutive walk-forward
   windows (Req 7.3). Each window is a full run with its own account and
   broker. An order still open at a window's end is reported open, not
   carried over. A signal at t depends only on data up to t, so each window
   makes the same decisions as the whole run: its warm-up is the data before
   its start.

Validates: Requirements 7.2, 7.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import calendar
import re
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Mapping, Optional, Sequence, TypeVar

from agent.brokers.fill_model import Bar
from agent.instruments import InstrumentSpecs
from algo_backtester.cache import SignalCache
from algo_backtester.config import RunConfig, StudyConfig, check_holdout
from algo_backtester.data import InstrumentData, fill_bars
from algo_backtester.signals import SignalRecord, generate_all
from algo_backtester.sim_broker import ClosedTrade, SimTrade
from algo_backtester.simulation import JournalRow, SimulationResult, simulate

__all__ = ["RunResult", "WindowResult", "run_backtest", "walk_forward_windows"]

UTC = timezone.utc
_PERIOD = re.compile(r"^([1-9][0-9]*)([DWM])$")

T = TypeVar("T")


@dataclass
class WindowResult:
    start: datetime
    end: datetime
    result: SimulationResult


@dataclass
class RunResult:
    windows: list[WindowResult]
    signals: dict[str, list[SignalRecord]]   # Phase A, the whole range
    floored_bars: dict[str, int]             # M1 bars priced at the typical spread (Req 5.1)
    manifest: dict
    bars: dict[str, list[Bar]] = field(default_factory=dict)   # what Phase B priced fills on, the whole range

    @property
    def journal(self) -> list[JournalRow]:
        return [row for w in self.windows for row in w.result.journal]

    @property
    def trades(self) -> list[ClosedTrade]:
        return [trade for w in self.windows for trade in w.result.trades]

    @property
    def open_orders(self) -> list[SimTrade]:
        return [order for w in self.windows for order in w.result.open_orders]


def walk_forward_windows(start: datetime, end: datetime, every: str) -> list[tuple[datetime, datetime]]:
    """Consecutive windows of ``every`` (e.g. "3M", "2W", "5D") covering
    [start, end); the last one is cut at ``end``. Month steps count from
    ``start`` and clamp to month ends (Jan 31 + 1M = Feb 28)."""
    match = _PERIOD.match(every)
    if match is None:
        raise ValueError(f"walk-forward period {every!r}: use a count and D, W or M, e.g. 3M")
    n, unit = int(match[1]), match[2]
    windows, k = [], 0
    while (window_start := _step(start, n * k, unit)) < end:
        windows.append((window_start, min(_step(start, n * (k + 1), unit), end)))
        k += 1
    return windows


def run_backtest(
    cfg: RunConfig,
    study: StudyConfig,
    final: bool,
    datas: Mapping[str, InstrumentData],
    specs: InstrumentSpecs,
    cache: Optional[SignalCache] = None,
    walk_forward: Optional[str] = None,
    workers: Optional[int] = None,
) -> RunResult:
    check_holdout(cfg, study, final)
    for instrument in cfg.run.instruments:
        spec = specs[instrument]
        if specs.account_ccy not in (spec.base_ccy, spec.quote_ccy):
            raise ValueError(f"{instrument} is a cross ({spec.base_ccy}/{spec.quote_ccy}): converting its "
                             f"{spec.quote_ccy} results to {specs.account_ccy} isn't supported yet")

    start, end = _midnight(cfg.run.start), _midnight(cfg.run.end)
    windows = walk_forward_windows(start, end, walk_forward) if walk_forward else [(start, end)]
    run_datas = [datas[instrument] for instrument in cfg.run.instruments]
    spreads = {i: specs[i].default_spread for i in cfg.run.instruments}     # for min_stop_spreads
    signals = {i: [r for r in records if r.t < end]
               for i, records in generate_all(run_datas, cfg.strategy, start, end, workers, cache, spreads).items()}

    bars, floored = {}, {}
    for data in run_datas:
        spread = specs[data.instrument].default_spread
        in_run, floored[data.instrument] = fill_bars(_between(data.m1, start, end), spread)
        pricing, _ = fill_bars(_between(data.m1, start - timedelta(minutes=1), start), spread)
        bars[data.instrument] = pricing + in_run   # the bar closing at start prices the first decision

    results = []
    for window_start, window_end in windows:
        window_bars = {i: _between(series, window_start - timedelta(minutes=1), window_end)
                       for i, series in bars.items()}
        window_signals = {i: [r for r in records if window_start <= r.t < window_end]
                          for i, records in signals.items()}
        results.append(WindowResult(window_start, window_end, simulate(
            window_bars, window_signals, specs, cfg.strategy, cfg.account,
            cost_flag_fraction=cfg.report.cost_flag_fraction)))

    manifest = {
        "study": study.name,
        "holdout_start": study.holdout_start.isoformat(),
        "final_validation": final,
        "variant": cfg.variant,
        "windows": [[a.isoformat(), b.isoformat()] for a, b in windows],
    }
    return RunResult(windows=results, signals=signals, floored_bars=floored, manifest=manifest, bars=bars)


def _between(bars: Sequence[T], start: datetime, end: datetime) -> list[T]:
    """Bars opening in [start, end); ``bars`` is sorted by timestamp."""
    lo = bisect_left(bars, start, key=lambda b: b.timestamp)
    hi = bisect_left(bars, end, key=lambda b: b.timestamp)
    return list(bars[lo:hi])


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _step(start: datetime, n: int, unit: str) -> datetime:
    if unit == "D":
        return start + timedelta(days=n)
    if unit == "W":
        return start + timedelta(weeks=n)
    years, month0 = divmod(start.month - 1 + n, 12)
    year, month = start.year + years, month0 + 1
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))
