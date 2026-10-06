"""Summary statistics for a run (Req 8.2-8.4, 5.4).

Only filled trades count: an order that expired or was refused never traded,
and one still open at the end has no result yet. Both are counted separately.

    summary = summarize(result.journal, initial_equity=10_000.0, min_trades=30, resamples=10_000, seed=seed)
    summary.overall.expectancy_r, summary.overall.expectancy_ci
    summary.breakdowns["killzone"]["NY_AM"].evidence      # "sufficient" / "insufficient"

Definitions (in net R, trades in closing order, unless stated):
- win: net R > 0; loss: net R < 0. The losing streak counts consecutive losses.
- expectancy: mean net R, with a 95% percentile-bootstrap interval that
  resamples trades. Seeded, so a rerun gives the same interval.
- profit factor: net R won / net R lost; None without a losing trade.
- max drawdown R: the deepest fall of cumulative net R from a peak, starting at 0.
- max drawdown %: the same on closed-trade equity (initial equity plus P&L),
  as a share of the peak.
- cost share: cost R / gross R over all trades (Req 5.4); None unless gross R
  is positive, since there is then no gross profit to take a share of.
- evidence: "insufficient" below ``min_trades`` (Req 8.4).

Breakdowns (Req 8.3): instrument, grade, killzone (the engine's, as at the
decision: LONDON / NY_AM / NY_PM / NONE), ICT time window (the finer
TimeWindowClassifier label, e.g. LONDON_SILVER_BULLET), direction, and the
month of the fill (UTC).

Validates: Requirements 5.4, 8.2, 8.3, 8.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import fmean
from typing import Callable, Optional, Sequence

import numpy as np

from algo_backtester.sim_broker import ClosedTrade
from algo_backtester.simulation import JournalRow

__all__ = ["BREAKDOWNS", "Stats", "Summary", "bootstrap_ci", "stats", "summarize"]

_SAMPLES_PER_CHUNK = 2_000_000   # bootstrap draws held in memory at once


@dataclass(frozen=True)
class Stats:
    trades: int
    wins: int
    win_rate: Optional[float]
    avg_gross_r: Optional[float]
    avg_net_r: Optional[float]
    total_net_r: float
    expectancy_r: Optional[float]
    expectancy_ci: Optional[tuple[float, float]]
    profit_factor: Optional[float]
    max_drawdown_r: float
    max_drawdown_pct: float
    longest_losing_streak: int
    avg_holding_minutes: Optional[float]
    avg_cost_r: Optional[float]
    avg_cost_r_spread: Optional[float]
    avg_cost_r_slippage: Optional[float]
    avg_cost_r_commission: Optional[float]
    cost_share: Optional[float]
    evidence: str


@dataclass(frozen=True)
class Summary:
    overall: Stats
    breakdowns: dict[str, dict[str, Stats]]   # name -> bucket -> stats, buckets sorted
    counts: dict                              # journal rows, orders, fills, decisions


BREAKDOWNS: dict[str, Callable[[JournalRow], str]] = {
    "instrument": lambda row: row.instrument,
    "grade": lambda row: row.grade or "NONE",
    "killzone": lambda row: (row.context.killzone if row.context else None) or "NONE",
    "time_window": lambda row: row.time_window or "NONE",
    "direction": lambda row: row.trade.direction,
    "month": lambda row: row.trade.filled_at.strftime("%Y-%m"),
}


def summarize(journal: Sequence[JournalRow], initial_equity: float, min_trades: int, resamples: int,
              seed: int) -> Summary:
    filled = [row for row in journal if row.trade is not None and row.trade.filled]

    def stats_of(rows: Sequence[JournalRow]) -> Stats:
        return stats([row.trade for row in rows], initial_equity, min_trades, resamples, seed)

    breakdowns = {}
    for name, key in BREAKDOWNS.items():
        buckets: dict[str, list[JournalRow]] = defaultdict(list)
        for row in filled:
            buckets[key(row)].append(row)
        breakdowns[name] = {bucket: stats_of(rows) for bucket, rows in sorted(buckets.items())}

    orders = [row for row in journal if row.order_id is not None]
    counts = {
        "rows": len(journal),
        "orders": len(orders),
        "filled": len(filled),
        "unfilled": sum(1 for row in orders if row.trade is not None and not row.trade.filled),
        "open_at_end": sum(1 for row in orders if row.trade is None),
        "decisions": dict(sorted(Counter(row.decision for row in journal).items())),
    }
    return Summary(overall=stats_of(filled), breakdowns=breakdowns, counts=counts)


def stats(trades: Sequence[ClosedTrade], initial_equity: float, min_trades: int, resamples: int,
          seed: int) -> Stats:
    done = sorted((t for t in trades if t.filled), key=lambda t: t.closed_at)
    net = [t.net_r for t in done]
    n = len(net)
    won = sum(r for r in net if r > 0)
    lost = -sum(r for r in net if r < 0)
    gross_total = sum(t.gross_r for t in done)
    cost_total = sum(t.cost_r for t in done)

    def mean(values) -> Optional[float]:
        values = list(values)
        return fmean(values) if values else None

    return Stats(
        trades=n,
        wins=sum(1 for r in net if r > 0),
        win_rate=sum(1 for r in net if r > 0) / n if n else None,
        avg_gross_r=mean(t.gross_r for t in done),
        avg_net_r=mean(net),
        total_net_r=sum(net),
        expectancy_r=mean(net),
        expectancy_ci=bootstrap_ci(net, resamples, seed) if n else None,
        profit_factor=won / lost if lost > 0 else None,
        max_drawdown_r=_max_drawdown(net, start=0.0),
        max_drawdown_pct=_max_drawdown([t.pnl for t in done], start=initial_equity, relative=True),
        longest_losing_streak=_longest_streak(r < 0 for r in net),
        avg_holding_minutes=mean(t.holding_time.total_seconds() / 60 for t in done),
        avg_cost_r=mean(t.cost_r for t in done),
        avg_cost_r_spread=mean(t.cost_r_spread for t in done),
        avg_cost_r_slippage=mean(t.cost_r_slippage for t in done),
        avg_cost_r_commission=mean(t.cost_r_commission for t in done),
        cost_share=cost_total / gross_total if gross_total > 0 else None,
        evidence="sufficient" if n >= min_trades else "insufficient",
    )


def bootstrap_ci(values: Sequence[float], resamples: int, seed: int) -> Optional[tuple[float, float]]:
    """95% percentile interval of the mean, over ``resamples`` resamples of
    ``values`` with replacement."""
    if not values:
        return None
    data = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    chunk = max(1, _SAMPLES_PER_CHUNK // len(data))
    for lo in range(0, resamples, chunk):
        hi = min(resamples, lo + chunk)
        means[lo:hi] = data[rng.integers(0, len(data), size=(hi - lo, len(data)))].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def _max_drawdown(changes: Sequence[float], start: float, relative: bool = False) -> float:
    level = peak = start
    deepest = 0.0
    for change in changes:
        level += change
        peak = max(peak, level)
        fall = (peak - level) / peak * 100 if relative else peak - level
        deepest = max(deepest, fall)
    return deepest


def _longest_streak(flags) -> int:
    longest = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    return longest
