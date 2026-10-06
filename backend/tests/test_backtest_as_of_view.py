"""
Tests for services/market_data/as_of_view.py::compose_as_of_view — the candle
window the engine sees at an as-of time t, with nothing from t's future.

Task 191 (.kiro/specs/algo-backtester/tasks.md).
Validates: Requirements 2.1, 2.2, 2.3, 2.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.strategy_config import StrategyConfig
from liquidity_engine.models import Candle, Timeframe as TF
from services.market_data.as_of_view import aggregate, compose_as_of_view
from services.market_data.strategy_calendar import StrategyCalendar

CAL = StrategyCalendar()
UTC = timezone.utc
MINUTE = timedelta(minutes=1)
# Winter, so New York is UTC-5: H4 periods start 22, 02, 06, 10, 14, 18 UTC.
T = datetime(2026, 1, 14, 15, 40, tzinfo=UTC)


def bar(tf: TF, ts: datetime, price: float = 1.1, high: float | None = None) -> Candle:
    return Candle(timestamp=ts, open=price, high=high if high is not None else price, low=price, close=price,
                  volume=1, timeframe=tf, instrument="EURUSD")


def aligned(tf: TF, until: datetime, n: int) -> list[Candle]:
    """``n`` consecutive calendar bars of ``tf``, all ended by ``until``."""
    starts, start = [], CAL.period_start(CAL.period_start(until, tf) - MINUTE, tf)
    for _ in range(n):
        starts.append(start)
        start = CAL.period_start(start - MINUTE, tf)
    return [bar(tf, ts) for ts in reversed(starts)]


def m1_series(start: datetime, end: datetime, price: float = 1.1) -> list[Candle]:
    out, ts = [], start
    while ts < end:
        out.append(bar(TF.M1, ts, price))
        ts += MINUTE
    return out


def closed_at(tf: TF, candle: Candle, t: datetime) -> bool:
    return CAL.period_end(candle.timestamp, tf) <= t


def test_entry_tf_and_below_closed_bars_only():
    # The lists run past t: the forming M15 bar (15:30) and future bars must not appear.
    closed = {TF.M5: aligned(TF.M5, T + timedelta(hours=1), 50), TF.M15: aligned(TF.M15, T + timedelta(hours=1), 50)}

    view = compose_as_of_view(closed, [], T, TF.M15, {TF.M5: 10, TF.M15: 10}, CAL)

    assert view[TF.M15][-1].timestamp == datetime(2026, 1, 14, 15, 15, tzinfo=UTC)  # closed 15:30 <= 15:40
    assert view[TF.M5][-1].timestamp == datetime(2026, 1, 14, 15, 35, tzinfo=UTC)   # closed 15:40, exactly t
    assert len(view[TF.M15]) == len(view[TF.M5]) == 10

    # A bar that closes exactly at t counts as closed.
    on_close = compose_as_of_view(closed, [], datetime(2026, 1, 14, 15, 45, tzinfo=UTC), TF.M15, {TF.M5: 10, TF.M15: 10}, CAL)
    assert on_close[TF.M15][-1].timestamp == datetime(2026, 1, 14, 15, 30, tzinfo=UTC)


def test_htf_window_has_one_in_progress_bar_from_m1():
    period = datetime(2026, 1, 14, 14, 0, tzinfo=UTC)  # the H4 period containing T
    m1 = m1_series(period, T + timedelta(hours=2))
    m1[0] = bar(TF.M1, period, 1.0)                                   # the period's open
    m1[30] = bar(TF.M1, m1[30].timestamp, 1.1, high=1.3)              # known by T
    later = [i for i, b in enumerate(m1) if b.timestamp >= T][0]
    m1[later] = bar(TF.M1, m1[later].timestamp, 1.1, high=9.9)        # closes after T: unknown
    closed = {TF.M15: aligned(TF.M15, T, 20), TF.H4: aligned(TF.H4, T + timedelta(days=1), 30)}

    view = compose_as_of_view(closed, m1, T, TF.M15, {TF.M15: 20, TF.H4: 5}, CAL)

    h4 = view[TF.H4]
    assert len(h4) == 5
    assert all(closed_at(TF.H4, b, T) for b in h4[:-1])
    forming = h4[-1]
    assert forming.timestamp == period and not closed_at(TF.H4, forming, T)
    assert (forming.open, forming.high, forming.close) == (1.0, 1.3, 1.1)  # 9.9 is in T's future
    assert forming.volume == 100                                         # M1 14:00..15:39, all closed by 15:40


def test_no_in_progress_bar_before_first_m1_of_period():
    period = datetime(2026, 1, 14, 14, 0, tzinfo=UTC)
    m1 = m1_series(period - timedelta(hours=1), period + timedelta(hours=1))
    closed = {TF.M15: aligned(TF.M15, period, 20), TF.H4: aligned(TF.H4, period + timedelta(days=1), 30)}

    # At 14:00 the first M1 bar of the period hasn't closed yet; at 14:00:30 neither.
    for t in (period, period + timedelta(seconds=30)):
        view = compose_as_of_view(closed, m1, t, TF.M15, {TF.M15: 20, TF.H4: 5}, CAL)
        assert len(view[TF.H4]) == 5
        assert all(closed_at(TF.H4, b, t) for b in view[TF.H4])
        assert view[TF.H4][-1].timestamp == datetime(2026, 1, 14, 10, 0, tzinfo=UTC)


def test_window_sizes_match_strategy_config():
    cfg = StrategyConfig()
    closed = {tf: aligned(tf, T, cfg.candle_counts[tf] + 5) for tf in cfg.timeframes}
    m1 = m1_series(CAL.period_start(T, TF.W1), T + timedelta(hours=1))

    view = compose_as_of_view(closed, m1, T, cfg.entry_tf, cfg.candle_counts, CAL)

    assert list(view) == list(closed)
    assert {tf: len(bars) for tf, bars in view.items()} == {tf: cfg.candle_counts[tf] for tf in cfg.timeframes}


def test_short_history_gives_shorter_windows():
    closed = {TF.M15: aligned(TF.M15, T, 3), TF.H4: aligned(TF.H4, T, 2)}
    m1 = m1_series(datetime(2026, 1, 14, 14, 0, tzinfo=UTC), T)
    view = compose_as_of_view(closed, m1, T, TF.M15, {TF.M15: 20, TF.H4: 5}, CAL)
    assert (len(view[TF.M15]), len(view[TF.H4])) == (3, 3)  # H4: two closed + the forming one


def test_pure_no_clock_no_io():
    closed = {TF.M15: aligned(TF.M15, T + timedelta(hours=1), 30), TF.D1: aligned(TF.D1, T + timedelta(days=2), 10)}
    m1 = m1_series(datetime(2026, 1, 13, 22, 0, tzinfo=UTC), T + timedelta(hours=1))
    before = copy.deepcopy((closed, m1))

    first = compose_as_of_view(closed, m1, T, TF.M15, {TF.M15: 20, TF.D1: 5}, CAL)
    second = compose_as_of_view(closed, m1, T, TF.M15, {TF.M15: 20, TF.D1: 5}, CAL)

    assert first == second
    assert (closed, m1) == before  # inputs untouched


def test_missing_window_size_rejected():
    with pytest.raises(ValueError, match="H4"):
        compose_as_of_view({TF.M15: [], TF.H4: []}, [], T, TF.M15, {TF.M15: 20}, CAL)


def test_closed_bars_off_the_strategy_calendar_rejected():
    # E.g. a UTC server's native H4 bar (00:00 UTC): off the calendar, it could
    # be counted as closed while it is still forming, so it must not be accepted.
    utc_h4 = [bar(TF.H4, datetime(2026, 1, 14, 8, 0, tzinfo=UTC)), bar(TF.H4, datetime(2026, 1, 14, 12, 0, tzinfo=UTC))]
    with pytest.raises(ValueError, match="strategy calendar"):
        compose_as_of_view({TF.M15: aligned(TF.M15, T, 5), TF.H4: utc_h4}, [], T, TF.M15, {TF.M15: 5, TF.H4: 5}, CAL)


# ── Property 2: As-of View Contains Only Known Data ───────────────────────

@st.composite
def market(draw):
    start = draw(st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2026, 12, 1))).replace(
        second=0, microsecond=0, tzinfo=UTC)
    n = draw(st.integers(min_value=60, max_value=3 * 1440))
    steps = draw(st.lists(st.integers(min_value=-5, max_value=5), min_size=n, max_size=n))
    gaps = draw(st.sets(st.integers(min_value=0, max_value=n - 1), max_size=n // 3))
    m1, price = [], 10_000
    for i, step in enumerate(steps):
        price = max(100, price + step)
        if i not in gaps:
            o, c = price / 10_000, (price + step) / 10_000
            m1.append(Candle(timestamp=start + i * MINUTE, open=o, high=max(o, c) + 0.0001, low=min(o, c) - 0.0001,
                             close=c, volume=abs(step), timeframe=TF.M1, instrument="EURUSD"))
    t = start + draw(st.integers(min_value=0, max_value=n + 60)) * MINUTE + timedelta(seconds=draw(st.sampled_from([0, 30])))
    entry_tf = draw(st.sampled_from([TF.M5, TF.M15]))
    return m1, t, entry_tf


TFS = (TF.M5, TF.M15, TF.H1, TF.H4, TF.D1, TF.W1)
WINDOWS = {TF.M5: 40, TF.M15: 30, TF.H1: 20, TF.H4: 10, TF.D1: 5, TF.W1: 3}


def _view(m1: list[Candle], t: datetime, entry_tf: TF):
    # closed bars per TF from all the M1 given, as the backtester builds them
    closed = {tf: aggregate(m1, tf, CAL, as_of=datetime(2027, 1, 1, tzinfo=UTC)) for tf in TFS}
    return compose_as_of_view(closed, m1, t, entry_tf, WINDOWS, CAL)


@settings(max_examples=75, deadline=None)
@given(market())
def test_property_as_of_view_contains_only_known_data(case):
    m1, t, entry_tf = case
    view = _view(m1, t, entry_tf)
    entry_minutes = {TF.M5: 5, TF.M15: 15}[entry_tf]

    for tf, bars in view.items():
        assert len(bars) <= WINDOWS[tf]
        forming = [b for b in bars if not closed_at(tf, b, t)]
        if tf in (TF.M5, TF.M15) and {TF.M5: 5, TF.M15: 15}[tf] <= entry_minutes:
            assert not forming, f"{tf.value} is entry TF or below: closed bars only"
        else:
            assert len(forming) <= 1 and (not forming or bars[-1] is forming[0])

    # The strong form: data after t can't change the view. Drop every M1 bar
    # that closes after t, rebuild everything, and the view is identical.
    known = [b for b in m1 if b.timestamp + MINUTE <= t]
    assert _view(known, t, entry_tf) == view
