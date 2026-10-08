"""
Time and killzone utilities for the Liquidity Engine.

All conversions are pure and stateless; no I/O, no shared mutable state.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from liquidity_engine.models import KillzoneWindow

_NY_TZ = ZoneInfo("America/New_York")

# High-probability trading session windows, expressed as EST/EDT wall-clock
# (start, end) pairs. Both bounds are inclusive.
KILLZONE_WINDOWS: dict[KillzoneWindow, tuple[time, time]] = {
    KillzoneWindow.LONDON: (time(2, 0), time(5, 0)),
    KillzoneWindow.NY_AM: (time(7, 0), time(10, 0)),
    KillzoneWindow.NY_PM: (time(13, 30), time(16, 0)),
}


# The D1 candle opens at 17:00 New York: the strategy calendar's day
# (services/market_data/strategy_calendar.py, algo-backtester decision D9).
TRADING_DAY_OPEN = time(17, 0)


def to_est(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to America/New_York local time (EST/EDT)."""
    if dt.tzinfo is None:
        raise ValueError("to_est requires a timezone-aware datetime")
    return dt.astimezone(_NY_TZ)


def to_utc(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to UTC."""
    if dt.tzinfo is None:
        raise ValueError("to_utc requires a timezone-aware datetime")
    return dt.astimezone(timezone.utc)


def get_killzone(dt: datetime) -> KillzoneWindow:
    """Return the killzone window (EST/EDT wall-clock) containing dt, or NONE."""
    est_time = to_est(dt).time()
    for window, (start, end) in KILLZONE_WINDOWS.items():
        if start <= est_time <= end:
            return window
    return KillzoneWindow.NONE


def is_in_killzone(dt: datetime) -> bool:
    """True when dt falls within any defined killzone window."""
    return get_killzone(dt) != KillzoneWindow.NONE


def trading_day_open(dt: datetime) -> datetime:
    """UTC open of the trading day (D1 candle) containing dt: the last 17:00 New York at or before it."""
    local = to_est(dt)
    day = local.date() if local.time() >= TRADING_DAY_OPEN else local.date() - timedelta(days=1)
    return datetime.combine(day, TRADING_DAY_OPEN, tzinfo=_NY_TZ).astimezone(timezone.utc)


def ny_time_in_day(day_open: datetime, at: time) -> datetime:
    """UTC instant of New York wall time ``at`` in the trading day opening at ``day_open``:
    from 17:00 on the opening date, earlier times on the next date (00:00 is the day's midnight)."""
    open_date = to_est(day_open).date()
    day = open_date if at >= TRADING_DAY_OPEN else open_date + timedelta(days=1)
    return datetime.combine(day, at, tzinfo=_NY_TZ).astimezone(timezone.utc)
