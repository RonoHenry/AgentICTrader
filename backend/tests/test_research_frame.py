"""
Tests for algo_research/frame.py — candle frames, the trading calendar and the
decision grid.

Task 246 (.kiro/specs/algo-research/tasks.md). Real data: the backtester's task
186 fixture week; synthetic frames for the calendar edge cases.
Validates: Requirements 2.1-2.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from algo_backtester.data import InstrumentData, fill_bars
from algo_research.config import trading_date, trading_date_open
from algo_research.frame import (
    BAR_TIMEFRAMES,
    aggregate_frame,
    build_grid,
    calendar_columns,
    frame_from_arrays,
    frame_from_data,
)
from liquidity_engine.models import Timeframe as TF
from liquidity_engine.utils.time_utils import get_killzone
from services.market_data.as_of_view import aggregate
from services.market_data.mt5_clock import NY_CLOSE, MT5ServerClock
from services.market_data.strategy_calendar import StrategyCalendar
from tests.test_backtest_signals import data_for

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
MIN = timedelta(minutes=1)
CAL = StrategyCalendar()
SERVER = MT5ServerClock(NY_CLOSE)
SLICES = {"explore": (date(2026, 9, 29), date(2026, 10, 1)), "confirm": (date(2026, 10, 1), date(2026, 10, 3))}


def ny(y, mo, d, h=0, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=NY).astimezone(UTC)


def columns_at(*instants: datetime) -> pd.DataFrame:
    return calendar_columns(pd.DatetimeIndex(list(instants)))


@lru_cache(maxsize=None)
def fixture_frame(instrument: str = "EURUSD"):
    return frame_from_data(data_for(instrument), typical_spread=0.00008 if instrument == "EURUSD" else 0.2,
                           stop_slippage=0.00002)


def test_trading_date_17_00_boundary():
    cols = columns_at(ny(2026, 1, 11, 17, 0), ny(2026, 1, 11, 16, 59), ny(2026, 1, 16, 16, 59), ny(2026, 1, 16, 17, 0))
    assert [d.date() for d in cols["trading_date"]] == [date(2026, 1, 12), date(2026, 1, 11), date(2026, 1, 16),
                                                        date(2026, 1, 17)]
    assert list(cols["weekday"]) == [0, 6, 4, 5]                   # Monday, Sunday, Friday, Saturday
    assert list(cols["ny_minute"]) == [17 * 60, 16 * 60 + 59, 16 * 60 + 59, 17 * 60]


def test_h4_index_on_both_sides_of_dst():
    # US DST starts 2025-03-09 and ends 2025-11-02: the H4 candles keep their New York hours.
    for day in (date(2025, 3, 7), date(2025, 3, 10), date(2025, 10, 31), date(2025, 11, 3)):
        times = [ny(day.year, day.month, day.day, h, m) for h, m in
                 ((1, 0), (4, 59), (5, 0), (9, 0), (12, 59), (13, 0), (16, 59), (17, 0), (21, 0), (0, 59))]
        cols = columns_at(*times)
        assert list(cols["h4_index"]) == [2, 2, 3, 4, 4, 5, 5, 0, 1, 1], day
        assert list(cols["in_window"]) == [True, True, True, True, True, False, False, False, False, False], day
    # The same New York hour is a different UTC hour on each side.
    assert ny(2025, 3, 7, 5).hour == 10 and ny(2025, 3, 10, 5).hour == 9


def test_killzone_is_the_engines():
    times = pd.date_range(ny(2026, 1, 13, 0), ny(2026, 1, 14, 0), freq="15min", inclusive="left")
    cols = calendar_columns(times)
    assert list(cols["killzone"]) == [get_killzone(t.to_pydatetime()).value for t in times]


def test_spread_priced_as_fill_bars():
    data = data_for("EURUSD")
    with_spreads = replace(data, m1=[replace(b, spread=None if i % 3 == 0 else (0.00001 if i % 3 == 1 else 0.0002))
                                     for i, b in enumerate(data.m1)])
    frame = frame_from_data(with_spreads, typical_spread=0.00008, stop_slippage=0.00002)
    bars, _ = fill_bars(with_spreads.m1, 0.00008)
    assert frame.m1["spread"].tolist() == [b.spread for b in bars]
    assert frame.m1["open"].tolist() == [b.open for b in bars]


def test_bar_close_times_follow_the_strategy_calendar():
    frame = fixture_frame()
    for tf in BAR_TIMEFRAMES:
        bars = frame.bars[tf]
        assert len(bars) > 0, tf
        for open_time, close_time in zip(bars["time"], bars["close_time"]):
            assert close_time.to_pydatetime() == CAL.period_end(open_time.to_pydatetime(), tf), tf


def test_grid_is_m15_closes_with_m1():
    frame = fixture_frame()
    grid = build_grid(frame, SLICES)
    times = [t.to_pydatetime() for t in grid["t"]]
    m1_times = [b.timestamp for b in data_for("EURUSD").m1]
    # Every M15 close whose bar holds M1 bars and whose trading date is in a slice, oldest first.
    # A row belongs to the candle containing t: the 17:00 New York close opens the next date.
    closes = sorted({CAL.period_end(t, TF.M15) for t in m1_times})
    expected = [t for t in closes if date(2026, 9, 29) <= trading_date(t) < date(2026, 10, 3)]
    assert times == expected
    assert times[0] == trading_date_open(date(2026, 9, 29))           # 17:00 New York on the eve
    assert all(t.astimezone(NY).weekday() != 5 for t in times)        # nothing on Saturday
    assert list(grid["slice"].unique()) == ["explore", "confirm"]
    assert all(trading_date(t) == d.date() for t, d in zip(times, grid["trading_date"]))


def test_grid_skips_data_gaps():
    data = data_for("EURUSD")
    gap = (ny(2026, 9, 30, 3, 0), ny(2026, 9, 30, 5, 0))
    holed = replace(data, m1=[b for b in data.m1 if not gap[0] <= b.timestamp < gap[1]])
    grid = build_grid(frame_from_data(holed, typical_spread=0.00008, stop_slippage=0.00002), SLICES)
    times = [t.to_pydatetime() for t in grid["t"]]
    assert not [t for t in times if gap[0] < t <= gap[1]]
    assert ny(2026, 9, 30, 3, 0) in times and ny(2026, 9, 30, 5, 15) in times


def test_vectorised_bars_equal_aggregate():
    # The synthetic-world path builds calendar bars itself; on real M1 it must equal aggregate().
    m1 = data_for("EURUSD").m1
    frame = frame_from_arrays("EURUSD", pd.DatetimeIndex([b.timestamp for b in m1]),
                              *(np.array([getattr(b, f) for b in m1]) for f in ("open", "high", "low", "close")),
                              spread=np.full(len(m1), 0.00008), typical_spread=0.00008, stop_slippage=0.00002)
    as_of = m1[-1].timestamp + MIN
    for tf in BAR_TIMEFRAMES:
        expected = aggregate(m1, tf, CAL, as_of=as_of)[1:]           # the first period may be partial
        got = frame.bars[tf]
        got = got[got["time"] >= pd.Timestamp(expected[0].timestamp)] if expected else got.iloc[0:0]
        got = got[got["close_time"] <= pd.Timestamp(as_of)]
        assert [t.to_pydatetime() for t in got["time"]] == [c.timestamp for c in expected], tf
        for name in ("open", "high", "low", "close"):
            assert got[name].tolist() == [getattr(c, name) for c in expected], (tf, name)


def test_aggregate_frame_partial_trailing_period_dropped():
    times = pd.date_range(ny(2026, 1, 13, 9, 0), ny(2026, 1, 13, 9, 50), freq="1min")
    m1 = pd.DataFrame({"time": times, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0})
    bars = aggregate_frame(m1, TF.M15, as_of=times[-1] + pd.Timedelta(minutes=1))
    assert [t.to_pydatetime() for t in bars["time"]] == [ny(2026, 1, 13, 9, 0), ny(2026, 1, 13, 9, 15),
                                                          ny(2026, 1, 13, 9, 30)]


# ── Property 3: Calendar Parity ────────────────────────────────────────────

_DST_EDGES = [ny(2025, 3, 9, 3), ny(2025, 11, 2, 1), ny(2026, 3, 8, 3), ny(2026, 11, 1, 1)]
_instants = st.one_of(
    st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2027, 12, 31)).map(lambda d: d.replace(tzinfo=UTC)),
    st.builds(lambda edge, minutes: edge + timedelta(minutes=minutes), st.sampled_from(_DST_EDGES),
              st.integers(-3 * 1440, 3 * 1440)),
    st.builds(lambda day, minutes: ny(2024, 1, 1, 17) + timedelta(days=day, minutes=minutes),
              st.integers(0, 4 * 365), st.integers(-2, 2)),                       # around 17:00 New York
)


@settings(max_examples=100, deadline=None)
@given(st.lists(_instants, min_size=1, max_size=20))
def test_property_3_calendar_parity(instants):
    cols = columns_at(*instants)
    for t, (_, row) in zip(instants, cols.iterrows()):
        d1 = SERVER.to_server(CAL.period_start(t, TF.D1)).date()
        h4 = SERVER.to_server(CAL.period_start(t, TF.H4)).hour // 4
        w1 = SERVER.to_server(CAL.period_start(t, TF.W1)).date()
        assert row["trading_date"].date() == d1, t
        assert row["h4_index"] == h4, t
        assert row["weekday"] == ((d1 - w1).days - 1) % 7 == d1.weekday(), t
