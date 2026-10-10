"""
Tests for services/market_data/as_of_view.py::aggregate — strategy-calendar bars from finer bars.

Task 185 (.kiro/specs/algo-backtester/tasks.md).
Validates: Requirements 3.3
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from liquidity_engine.models import Candle, Timeframe
from services.market_data.as_of_view import aggregate
from services.market_data.strategy_calendar import StrategyCalendar

CAL = StrategyCalendar()
UTC = timezone.utc


def m1(ts: datetime, o: float, h: float, lo: float, c: float, v: int | None = 1) -> Candle:
    return Candle(timestamp=ts, open=o, high=h, low=lo, close=c, volume=v,
                  timeframe=Timeframe.M1, instrument="EURUSD")


def flat_m1_series(start: datetime, minutes: int, price: float = 1.1) -> list[Candle]:
    return [m1(start + timedelta(minutes=i), price, price, price, price) for i in range(minutes)]


def test_aggregate_ohlcv_values():
    # One H1 bar on the strategy calendar: 14:00-15:00 UTC is a whole H1 period (17:00 New York + n hours).
    start = datetime(2026, 1, 14, 14, 0, tzinfo=UTC)
    bars = [
        m1(start, 1.10, 1.12, 1.09, 1.11, v=3),
        *[m1(start + timedelta(minutes=i), 1.11, 1.15, 1.10, 1.12, v=2) for i in range(1, 59)],
        m1(start + timedelta(minutes=59), 1.12, 1.13, 1.05, 1.08, v=5),
    ]
    [h1] = aggregate(bars, Timeframe.H1, CAL)
    assert h1.timestamp == start
    assert (h1.open, h1.high, h1.low, h1.close) == (1.10, 1.15, 1.05, 1.08)
    assert h1.volume == 3 + 58 * 2 + 5
    assert h1.timeframe == Timeframe.H1 and h1.instrument == "EURUSD"


def test_aggregate_skips_empty_periods():
    # Friday 21:00 UTC (FX close) to Sunday 22:00 UTC (FX open) has no bars: no synthetic H1 bars appear.
    friday = flat_m1_series(datetime(2026, 1, 16, 20, 0, tzinfo=UTC), 60)
    sunday = flat_m1_series(datetime(2026, 1, 18, 22, 0, tzinfo=UTC), 60)
    out = aggregate(friday + sunday, Timeframe.H1, CAL)
    assert [b.timestamp for b in out] == [datetime(2026, 1, 16, 20, 0, tzinfo=UTC), datetime(2026, 1, 18, 22, 0, tzinfo=UTC)]


def test_partial_trailing_period_not_emitted():
    # 90 minutes of M1 from 14:00: the 15:00 H1 period is only half covered, so it isn't emitted.
    out = aggregate(flat_m1_series(datetime(2026, 1, 14, 14, 0, tzinfo=UTC), 90), Timeframe.H1, CAL)
    assert [b.timestamp for b in out] == [datetime(2026, 1, 14, 14, 0, tzinfo=UTC)]


def test_as_of_controls_which_periods_count_as_closed():
    bars = flat_m1_series(datetime(2026, 1, 14, 14, 0, tzinfo=UTC), 120)
    assert len(aggregate(bars, Timeframe.H1, CAL)) == 2
    assert len(aggregate(bars, Timeframe.H1, CAL, as_of=datetime(2026, 1, 14, 15, 30, tzinfo=UTC))) == 1


def test_d1_follows_new_york_close_not_utc_midnight():
    # 21:00-23:00 UTC on a winter day spans 16:00-18:00 New York: two different strategy days.
    bars = flat_m1_series(datetime(2026, 1, 14, 21, 0, tzinfo=UTC), 60)
    bars += [m1(datetime(2026, 1, 14, 22, 0, tzinfo=UTC) + timedelta(minutes=i), 1.2, 1.2, 1.2, 1.2) for i in range(60)]
    days = aggregate(bars, Timeframe.D1, CAL, as_of=datetime(2026, 1, 15, 22, 0, tzinfo=UTC))
    assert [d.timestamp for d in days] == [datetime(2026, 1, 13, 22, 0, tzinfo=UTC), datetime(2026, 1, 14, 22, 0, tzinfo=UTC)]
    assert days[0].close == 1.1 and days[1].open == 1.2


def test_volume_none_when_all_inputs_none():
    bars = [m1(datetime(2026, 1, 14, 14, 0, tzinfo=UTC) + timedelta(minutes=i), 1.1, 1.1, 1.1, 1.1, v=None) for i in range(60)]
    assert aggregate(bars, Timeframe.H1, CAL)[0].volume is None


def test_unsorted_input_rejected():
    bars = flat_m1_series(datetime(2026, 1, 14, 14, 0, tzinfo=UTC), 3)
    with pytest.raises(ValueError, match="ascending"):
        aggregate([bars[1], bars[0], bars[2]], Timeframe.H1, CAL)


def test_input_coarser_than_target_rejected():
    h4 = Candle(timestamp=datetime(2026, 1, 14, 14, 0, tzinfo=UTC), open=1, high=1, low=1, close=1, volume=1,
                timeframe=Timeframe.H4, instrument="EURUSD")
    with pytest.raises(ValueError, match="coarser"):
        aggregate([h4], Timeframe.H1, CAL)


def test_empty_input():
    assert aggregate([], Timeframe.H1, CAL) == []


# ── Property 3: Aggregation Consistency ───────────────────────────────────

@st.composite
def random_walk_m1(draw):
    start = draw(st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2026, 12, 20))).replace(
        second=0, microsecond=0, tzinfo=UTC)
    n = draw(st.integers(min_value=1, max_value=3 * 1440))
    steps = draw(st.lists(st.integers(min_value=-5, max_value=5), min_size=n, max_size=n))
    gaps = draw(st.sets(st.integers(min_value=0, max_value=n - 1), max_size=n // 4))  # missing minutes
    bars, price, t = [], 10_000, start
    for i, step in enumerate(steps):
        t = start + timedelta(minutes=i)
        price = max(100, price + step)
        if i in gaps:
            continue
        o, c = price / 10_000, (price + step) / 10_000
        bars.append(m1(t, o, max(o, c) + 0.0001, min(o, c) - 0.0001, c, v=abs(step)))
    return bars


@settings(max_examples=100, deadline=None)
@given(random_walk_m1())
def test_property_aggregation_consistency(bars):
    """Property 3: aggregate(aggregate(m1, H1), D1) == aggregate(m1, D1); OHLC invariants hold."""
    direct = aggregate(bars, Timeframe.D1, CAL)
    via_h1 = aggregate(aggregate(bars, Timeframe.H1, CAL), Timeframe.D1, CAL)
    assert via_h1 == direct
    for tf in (Timeframe.H1, Timeframe.H4, Timeframe.D1):
        for bar in aggregate(bars, tf, CAL):
            assert bar.low <= min(bar.open, bar.close) and max(bar.open, bar.close) <= bar.high
