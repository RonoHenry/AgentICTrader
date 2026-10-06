"""
Tests for algo_backtester/metrics.py — summary statistics.

Task 205 (.kiro/specs/algo-backtester/tasks.md). Known trade lists with
hand-computed results. Only filled trades count; a bucket with fewer than
min_trades is marked insufficient evidence rather than reported as a finding.
Validates: Requirements 5.4, 8.2, 8.3, 8.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from algo_backtester.metrics import bootstrap_ci, stats, summarize
from algo_backtester.signals import TradeContext
from algo_backtester.sim_broker import ClosedTrade
from algo_backtester.simulation import JournalRow

UTC = timezone.utc
T0 = datetime(2026, 9, 29, 13, 0, tzinfo=UTC)


def trade(net_r: float, gross_r: float, minutes: int = 60, at: datetime = T0, direction: str = "LONG",
          instrument: str = "EURUSD", cost_split=(None, 0.0, 0.0), filled: bool = True) -> ClosedTrade:
    cost = gross_r - net_r
    spread, slippage, commission = cost_split if cost_split[0] is not None else (cost, 0.0, 0.0)
    return ClosedTrade(
        order_id="sim", setup_id="s", instrument=instrument, direction=direction, kind="LIMIT", entry=1.1,
        stop=1.099, target=1.105, lots=1.0, risk_amount=100.0, placed_at=at, expires_at=None,
        filled_at=at if filled else None, closed_at=at + timedelta(minutes=minutes),
        exit_reason=("TP" if net_r > 0 else "SL") if filled else "EXPIRED",
        ideal_fill=1.1 if filled else None, fill=1.1 if filled else None, ideal_exit=1.1 if filled else None,
        exit=1.1 if filled else None, initial_risk=0.001 if filled else None,
        gross_r=gross_r if filled else None, net_r=net_r if filled else None,
        cost_r_spread=spread if filled else None, cost_r_slippage=slippage if filled else None,
        cost_r_commission=commission if filled else None, mae_r=-0.5 if filled else None,
        mfe_r=1.0 if filled else None, pnl=net_r * 100.0 if filled else 0.0, cost_flag=False,
    )


def row(t: ClosedTrade, grade: str = "A", killzone="NY_AM", time_window: str = "NY_AM_KILLZONE") -> JournalRow:
    context = TradeContext(entry_array=None, draw_on_liquidity=None, swept_level=None, killzone=killzone)
    return JournalRow(t=t.placed_at, instrument=t.instrument, decision="EXECUTE", reason="", grade=grade,
                      intent=None, context=context, order_id=t.order_id, trade=t,
                      time_window=time_window)


# net R 2, -1, -1, 3, -1 (gross 0.1 better each); 30..150 minutes held; $100 per R on $10,000
KNOWN = [trade(net, gross, minutes, at=T0 + timedelta(hours=i)) for i, (net, gross, minutes) in enumerate(
    [(2.0, 2.1, 30), (-1.0, -0.9, 60), (-1.0, -0.9, 90), (3.0, 3.1, 120), (-1.0, -0.9, 150)])]


def known_stats(**kwargs):
    return stats(KNOWN, initial_equity=10_000.0, **{"min_trades": 5, "resamples": 2_000, "seed": 7, **kwargs})


def test_win_rate_expectancy_profit_factor():
    s = known_stats()
    assert s.trades == 5 and s.wins == 2
    assert s.win_rate == pytest.approx(0.4)
    assert s.avg_gross_r == pytest.approx(0.5) and s.avg_net_r == pytest.approx(0.4)
    assert s.expectancy_r == pytest.approx(0.4)
    assert s.profit_factor == pytest.approx(5.0 / 3.0)
    assert stats([trade(1.0, 1.1)], initial_equity=10_000.0, min_trades=1, resamples=100, seed=1).profit_factor is None


def test_max_drawdown_r_and_pct_and_losing_streak():
    s = known_stats()
    # cumulative net R 2, 1, 0, 3, 2: the deepest fall is 2R, from the first peak
    assert s.max_drawdown_r == pytest.approx(2.0)
    # closed-trade equity 10,200 -> 10,000: 200 / 10,200
    assert s.max_drawdown_pct == pytest.approx(200 / 10_200 * 100)
    assert s.longest_losing_streak == 2
    # a loss on the first trade is a drawdown from the starting equity
    first_loss = stats([trade(-1.0, -0.9), trade(1.0, 1.1)], initial_equity=10_000.0, min_trades=1,
                       resamples=100, seed=1)
    assert first_loss.max_drawdown_r == pytest.approx(1.0) and first_loss.max_drawdown_pct == pytest.approx(1.0)


def test_holding_time_and_cost_share():
    s = known_stats()
    assert s.avg_holding_minutes == pytest.approx(90.0)
    assert s.avg_cost_r == pytest.approx(0.1)
    assert s.cost_share == pytest.approx(0.5 / 2.5)       # 0.5R of costs out of 2.5R gross
    split = stats([trade(0.5, 1.0, cost_split=(0.3, 0.1, 0.1))], initial_equity=10_000.0, min_trades=1,
                  resamples=100, seed=1)
    assert (split.avg_cost_r_spread, split.avg_cost_r_slippage, split.avg_cost_r_commission) == pytest.approx(
        (0.3, 0.1, 0.1))
    losing_gross = stats([trade(-1.2, -1.0)], initial_equity=10_000.0, min_trades=1, resamples=100, seed=1)
    assert losing_gross.cost_share is None                # no gross profit to take a share of


def test_bootstrap_ci_deterministic_for_seed_and_contains_mean():
    values = [t.net_r for t in KNOWN] * 10
    low, high = bootstrap_ci(values, resamples=5_000, seed=42)
    assert (low, high) == bootstrap_ci(values, resamples=5_000, seed=42)
    assert bootstrap_ci(values, resamples=5_000, seed=43) != (low, high)
    assert low < sum(values) / len(values) < high
    assert known_stats().expectancy_ci == known_stats().expectancy_ci
    assert bootstrap_ci([1.5], resamples=100, seed=1) == (1.5, 1.5)


def test_insufficient_evidence_below_min_trades():
    assert known_stats(min_trades=30).evidence == "insufficient"
    assert known_stats(min_trades=5).evidence == "sufficient"
    empty = stats([], initial_equity=10_000.0, min_trades=30, resamples=100, seed=1)
    assert empty.trades == 0 and empty.evidence == "insufficient"
    assert empty.win_rate is None and empty.expectancy_ci is None and empty.max_drawdown_r == 0.0


def test_unfilled_and_open_orders_are_not_trades():
    rows = [row(t) for t in KNOWN] + [row(trade(0.0, 0.0, filled=False))]
    skipped = JournalRow(t=T0, instrument="EURUSD", decision="SKIP", reason="daily drawdown", grade="A")
    open_at_end = JournalRow(t=T0, instrument="EURUSD", decision="EXECUTE", reason="", grade="A", order_id="sim-9")
    summary = summarize([*rows, skipped, open_at_end], initial_equity=10_000.0, min_trades=5, resamples=500, seed=1)
    assert summary.overall.trades == 5
    assert summary.counts == {"rows": 8, "orders": 7, "filled": 5, "unfilled": 1, "open_at_end": 1,
                              "decisions": {"EXECUTE": 7, "SKIP": 1}}


def test_breakdowns_by_instrument_grade_killzone_direction_month():
    september, october = T0, datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    rows = [
        row(trade(2.0, 2.1, at=september, instrument="EURUSD", direction="LONG"), grade="A", killzone="NY_AM"),
        row(trade(-1.0, -0.9, at=september, instrument="EURUSD", direction="SHORT"), grade="B", killzone="LONDON",
            time_window="LONDON_SILVER_BULLET"),
        row(trade(1.0, 1.1, at=october, instrument="XAUUSD", direction="LONG"), grade="A", killzone=None,
            time_window="LONDON_CLOSE"),
    ]
    summary = summarize(rows, initial_equity=10_000.0, min_trades=2, resamples=500, seed=1)
    by = summary.breakdowns
    assert set(by) == {"instrument", "grade", "killzone", "time_window", "direction", "month"}
    assert {k: v.trades for k, v in by["instrument"].items()} == {"EURUSD": 2, "XAUUSD": 1}
    assert {k: v.trades for k, v in by["grade"].items()} == {"A": 2, "B": 1}
    assert {k: v.trades for k, v in by["killzone"].items()} == {"NY_AM": 1, "LONDON": 1, "NONE": 1}
    assert {k: v.trades for k, v in by["time_window"].items()} == {
        "NY_AM_KILLZONE": 1, "LONDON_SILVER_BULLET": 1, "LONDON_CLOSE": 1}
    assert {k: v.trades for k, v in by["direction"].items()} == {"LONG": 2, "SHORT": 1}
    assert {k: v.trades for k, v in by["month"].items()} == {"2026-09": 2, "2026-10": 1}
    assert by["grade"]["A"].avg_net_r == pytest.approx(1.5) and by["grade"]["A"].evidence == "sufficient"
    assert by["grade"]["B"].evidence == "insufficient"
    assert list(by["month"]) == ["2026-09", "2026-10"]                      # buckets in sorted order
