"""
Tests for services/market_data/strategy_calendar.py — the one candle calendar (D9).

Task 184 (.kiro/specs/algo-backtester/tasks.md).
Validates: Requirements 3.3
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from liquidity_engine.models import Timeframe
from services.market_data.mt5_clock import MT5ServerClock
from services.market_data.strategy_calendar import StrategyCalendar

NY = ZoneInfo("America/New_York")
CAL = StrategyCalendar()
INTRADAY = [Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.M30, Timeframe.H1,
            Timeframe.H3, Timeframe.H4, Timeframe.H6, Timeframe.H8, Timeframe.H12]
ALL = [*INTRADAY, Timeframe.D1, Timeframe.W1]


def ny(*args) -> datetime:
    """A New York wall-clock time as an aware UTC datetime."""
    return datetime(*args, tzinfo=NY).astimezone(timezone.utc)


# ── D1 ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "t, expected",
    [
        # Winter (EST, UTC-5): Wednesday 10:00 New York belongs to the day that opened Tuesday 17:00.
        (ny(2026, 1, 14, 10, 0), datetime(2026, 1, 13, 22, 0, tzinfo=timezone.utc)),
        # Summer (EDT, UTC-4): same rule, one hour earlier in UTC.
        (ny(2026, 7, 15, 11, 0), datetime(2026, 7, 14, 21, 0, tzinfo=timezone.utc)),
        # Exactly 17:00 New York starts a new day.
        (ny(2026, 1, 14, 17, 0), datetime(2026, 1, 14, 22, 0, tzinfo=timezone.utc)),
        (ny(2026, 1, 14, 16, 59), datetime(2026, 1, 13, 22, 0, tzinfo=timezone.utc)),
    ],
)
def test_d1_starts_17_00_new_york_in_winter_and_summer(t, expected):
    assert CAL.period_start(t, Timeframe.D1) == expected


# ── intraday ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hour", [17, 21, 1, 5, 9, 13])
def test_h4_starts_17_21_01_05_09_13_new_york(hour):
    day = 15 if hour < 17 else 14  # the hours after midnight fall on the next calendar day
    t = ny(2026, 1, day, hour, 30)
    start = CAL.period_start(t, Timeframe.H4).astimezone(NY)
    assert (start.hour, start.minute) == (hour, 0)


def test_intraday_bars_nest_inside_d1():
    t = ny(2026, 1, 14, 17, 0)
    end = t + timedelta(days=1)
    while t < end:
        d1_start, d1_end = CAL.period_start(t, Timeframe.D1), CAL.period_end(t, Timeframe.D1)
        for tf in INTRADAY:
            assert d1_start <= CAL.period_start(t, tf) <= t < CAL.period_end(t, tf) <= d1_end, (tf, t)
        t += timedelta(minutes=7)


# ── W1 ─────────────────────────────────────────────────────────────────────

def test_w1_period_matches_mt5_weekly_bar_labels():
    # MT5 labels weekly bars at the server's Sunday 00:00. On the New York-close
    # clock that is Saturday 17:00 New York. The FX week opens Sunday 17:00
    # inside that period and closes Friday 17:00.
    wednesday = ny(2026, 1, 14, 12, 0)
    assert CAL.period_start(wednesday, Timeframe.W1) == ny(2026, 1, 10, 17, 0)   # Saturday
    assert CAL.period_end(wednesday, Timeframe.W1) == ny(2026, 1, 17, 17, 0)     # next Saturday
    sunday_open = ny(2026, 1, 11, 17, 5)
    friday_close = ny(2026, 1, 16, 16, 59)
    assert CAL.period_start(sunday_open, Timeframe.W1) == CAL.period_start(friday_close, Timeframe.W1)


# ── DST and tiling ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "before, after",
    [
        # US spring-forward weekend (2026-03-08): EST before, EDT after.
        (ny(2026, 3, 6, 12, 0), ny(2026, 3, 9, 12, 0)),
        # US fall-back weekend (2026-11-01): EDT before, EST after.
        (ny(2026, 10, 30, 12, 0), ny(2026, 11, 2, 12, 0)),
    ],
)
def test_d1_stays_at_17_00_new_york_across_dst_change(before, after):
    for t in (before, after):
        start = CAL.period_start(t, Timeframe.D1).astimezone(NY)
        assert (start.hour, start.minute) == (17, 0)


@pytest.mark.parametrize("change_day", [datetime(2026, 3, 8, tzinfo=timezone.utc), datetime(2026, 11, 1, tzinfo=timezone.utc)])
@pytest.mark.parametrize("tf", [Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1])
def test_periods_tile_time_without_gaps_or_overlaps_across_dst_change(change_day, tf):
    # Crypto trades through the US DST change, so every instant must belong to exactly one period.
    t = change_day - timedelta(days=1)
    end = change_day + timedelta(days=2)
    previous_end = None
    while t < end:
        start, stop = CAL.period_start(t, tf), CAL.period_end(t, tf)
        assert start <= t < stop, (tf, t, start, stop)
        if previous_end is not None and start != previous_start:
            assert start == previous_end, (tf, t)
        previous_start, previous_end = start, stop
        t += timedelta(minutes=5)


@pytest.mark.parametrize("tf", ALL)
def test_period_end_equals_next_period_start(tf):
    for t in (ny(2026, 1, 14, 9, 31), ny(2026, 7, 15, 23, 59), ny(2026, 1, 16, 16, 59)):
        end = CAL.period_end(t, tf)
        assert CAL.period_start(end, tf) == end


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        CAL.period_start(datetime(2026, 1, 14, 12, 0), Timeframe.H1)


# ── where native bars can be used directly ─────────────────────────────────

def test_matches_native():
    ny_close = MT5ServerClock("ny_close")
    utc = MT5ServerClock("+0")
    for tf in ALL:
        assert CAL.matches_native(ny_close, tf), tf
    for tf in (Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.M30, Timeframe.H1):
        assert CAL.matches_native(utc, tf), tf
        assert CAL.matches_native(None, tf), tf          # Binance: UTC
    for tf in (Timeframe.H3, Timeframe.H4, Timeframe.H6, Timeframe.H8, Timeframe.H12, Timeframe.D1, Timeframe.W1):
        assert not CAL.matches_native(utc, tf), tf
        assert not CAL.matches_native(None, tf), tf
    # A half-hour offset only lines up for sub-hour bars that divide 30 minutes.
    half = MT5ServerClock("+5.5")
    assert CAL.matches_native(half, Timeframe.M15)
    assert not CAL.matches_native(half, Timeframe.H1)
