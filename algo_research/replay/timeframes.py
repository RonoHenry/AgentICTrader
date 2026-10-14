"""The replay chart's timeframes, anchored as the trader's charts are (update 2026-10-14b).

Every bar is placed on New York wall-clock time, in seconds since 1970 read as if
it were UTC: the chart draws those numbers as given, so the axis shows New York
time. The trading day opens at 17:00 New York; intraday bars are counted from
that open, so H4 bars start at 17:00, 21:00, 01:00, 05:00, 09:00 and 13:00, and a
frame that doesn't divide the day (H7, 45 minutes) restarts at each open, its
last bar cut short there. W1 opens Sunday 17:00; MN1 holds the trading dates of
a calendar month and is placed at the eve of its first day, 17:00.

The FX and gold markets are closed when New York changes its clocks (Sunday
02:00), so wall-clock time never repeats or skips inside a session.

Aggregation is vectorised: bars must come sorted by time, and bucket starts are
then non-decreasing.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

__all__ = ["DAY", "DAY_OPEN", "TIMEFRAMES", "TF_SECONDS", "aggregate", "bucket", "seconds_of", "wall_seconds"]

NY = "America/New_York"
DAY = 86_400
DAY_OPEN = 17 * 3600

#: The chart's timeframes, finest first, with their nominal length in seconds. M1 is the finest
#: data there is (the MT5 terminal gives no tick history for these dates), so there are no second charts.
TF_SECONDS = {
    "M1": 60, "M2": 120, "M3": 180, "M4": 240, "M5": 300, "M10": 600, "M15": 900, "M20": 1200, "M30": 1800,
    "M45": 2700,
    "H1": 3600, "H3": 3 * 3600, "H4": 4 * 3600, "H6": 6 * 3600, "H7": 7 * 3600, "H8": 8 * 3600, "H12": 12 * 3600,
    "D1": DAY, "W1": 7 * DAY, "MN1": 31 * DAY,
}
TIMEFRAMES = tuple(TF_SECONDS)


def seconds_of(tf: str) -> int:
    if tf not in TF_SECONDS:
        raise ValueError(f"tf: one of {', '.join(TIMEFRAMES)}")
    return TF_SECONDS[tf]


def wall_seconds(times) -> np.ndarray:
    """UTC instants as New York wall-clock seconds since 1970 (int64)."""
    idx = pd.DatetimeIndex(times)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    naive = idx.tz_convert(NY).tz_localize(None)
    return (naive.as_unit("ns").asi8 // 1_000_000_000).astype(np.int64)


def bucket(wall: np.ndarray, tf: str) -> np.ndarray:
    """The start (wall seconds) of the ``tf`` bar holding each wall-clock second."""
    wall = np.asarray(wall, dtype=np.int64)
    size = seconds_of(tf)
    day_index = (wall - DAY_OPEN) // DAY                 # the trading day, by the date of its eve
    day_open = day_index * DAY + DAY_OPEN
    if tf == "D1":
        return day_open
    if tf == "W1":
        eve_weekday = (day_index + 3) % 7                # 1970-01-01 was a Thursday; Monday is 0
        return day_open - ((eve_weekday - 6) % 7) * DAY  # back to Sunday's open
    if tf == "MN1":
        trading_date = (day_open + DAY - DAY_OPEN).astype("datetime64[s]")
        month = trading_date.astype("datetime64[M]").astype("datetime64[s]").astype(np.int64)
        return month - DAY + DAY_OPEN                    # the eve of the month's first day, 17:00
    return day_open + ((wall - day_open) // size) * size


def aggregate(wall: np.ndarray, o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray, tf: str,
              starts: Optional[np.ndarray] = None) -> pd.DataFrame:
    """``tf`` bars (columns time, open, high, low, close; time in wall seconds) from finer bars sorted by time.
    ``starts``: their bucket starts, when already known."""
    if len(wall) == 0:
        return pd.DataFrame({"time": np.array([], dtype=np.int64), "open": [], "high": [], "low": [], "close": []})
    keys = bucket(wall, tf) if starts is None else starts
    first = np.r_[0, np.flatnonzero(np.diff(keys)) + 1]
    last = np.r_[first[1:], len(keys)] - 1
    return pd.DataFrame({"time": keys[first], "open": np.asarray(o)[first],
                         "high": np.maximum.reduceat(np.asarray(h), first),
                         "low": np.minimum.reduceat(np.asarray(lo), first), "close": np.asarray(c)[last]})
