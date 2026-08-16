"""
Time and killzone utilities for the PD Array Engine.

All conversions are pure and stateless; no I/O, no shared mutable state.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from pd_array_engine.models import KillzoneWindow

_NY_TZ = ZoneInfo("America/New_York")

# High-probability trading session windows, expressed as EST/EDT wall-clock
# (start, end) pairs. Both bounds are inclusive.
KILLZONE_WINDOWS: dict[KillzoneWindow, tuple[time, time]] = {
    KillzoneWindow.LONDON: (time(2, 0), time(5, 0)),
    KillzoneWindow.NY_AM: (time(7, 0), time(10, 0)),
    KillzoneWindow.NY_PM: (time(13, 30), time(16, 0)),
}


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
