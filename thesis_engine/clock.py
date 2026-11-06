"""The clock (thesis-engine Requirement 2): M1 bars as each frame's candles on the market's New York calendar.

- **The trading day** opens at 17:00 New York for FX, gold and DXY and at 18:00 for the indices (TE-D11), and is named
  by the date it closes on (Sunday evening opens Monday's).
- **H4** opens every four hours from the day's open; **H1** and **M5** on the clock; **W1** runs from Sunday's open to
  Friday's close.
- **A candle exists from its close.** A period with no bars has no candle, and a candle still forming when the bars
  end is left out, so nothing read at t changes when later bars arrive (TE-D3).
- **The feed** (Requirement 2.5, TE-D17): bars are read once, in time order. A bar repeating or older than the last
  one read is dropped and counted. Leading stand-in rows (a bar followed by more than an hour of silence before
  intraday data starts) are dropped too.

Times are UTC nanoseconds throughout, as AlgoMindDIS's frames.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from liquidity_engine.context.frame_state import Candles
from thesis_engine.settings import MINUTES, V1, Settings

__all__ = ["FRAMES", "NS", "NY", "clean", "frames", "limit_expiry", "stale", "trading_day", "in_window"]

NY = "America/New_York"
NS = 1_000_000_000
MINUTE = 60 * NS
#: Highest first: candles closing together are stepped in this order (TE-D2).
FRAMES = ("W1", "D1", "H4", "H1", "M5")


def clean(m1: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """The bars in time order, each read once, and what was dropped."""
    t = m1["time"].to_numpy("datetime64[ns]").astype(np.int64)
    keep = np.ones(len(t), dtype=bool)
    if len(t) > 1:                                 # a repeat or an older bar never moves time back
        keep[1:] = t[1:] > np.maximum.accumulate(t)[:-1]
    repeated = int((~keep).sum())
    out = m1.loc[keep].reset_index(drop=True)
    lead = 0
    times = out["time"].to_numpy("datetime64[ns]").astype(np.int64)
    while lead + 1 < len(times) and times[lead + 1] - times[lead] > 60 * MINUTE:
        lead += 1
    out = out.iloc[lead:].reset_index(drop=True)
    return out, {"repeated_or_older": repeated, "leading_stand_ins": lead}


def _local(t_ns: np.ndarray) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(t_ns, utc=True)).tz_convert(NY).tz_localize(None)


def _utc(local: pd.DatetimeIndex) -> np.ndarray:
    return local.tz_localize(NY, ambiguous="raise", nonexistent="raise").tz_convert("UTC").asi8


def _day_labels(t_ns: np.ndarray, hour: int) -> pd.DatetimeIndex:
    """The trading day each time belongs to, named by the date it closes on (naive, midnight)."""
    return (_local(t_ns) + pd.Timedelta(hours=24 - hour)).normalize()


def trading_day(t_ns, market: str, s: Settings = V1):
    """The trading day of each time (UTC ns), as the label's ns (naive midnight read as UTC)."""
    t = np.atleast_1d(np.asarray(t_ns, dtype=np.int64))
    return _day_labels(t, s.day_open_hour(market)).asi8


def in_window(t_ns, s: Settings = V1):
    """Whether each time is in the window: New York hours ``s.window``, Monday to Friday (TE-D6)."""
    local = _local(np.atleast_1d(np.asarray(t_ns, dtype=np.int64)))
    hour = local.hour + local.minute / 60
    return np.asarray((hour >= s.window[0]) & (hour < s.window[1]) & (local.dayofweek < 5))


def _aggregate(tf: str, key: np.ndarray, end: np.ndarray, o, h, l, c, last_close: int) -> Candles:
    df = pd.DataFrame({"k": key, "end": end, "o": o, "h": h, "l": l, "c": c})
    g = df.groupby("k", sort=True).agg(end=("end", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"),
                                       c=("c", "last"))
    g = g[g["end"] <= last_close]
    f = lambda k: g[k].to_numpy(dtype=float)                       # noqa: E731
    return Candles(tf, g.index.to_numpy(dtype=np.int64), g["end"].to_numpy(dtype=np.int64), f("o"), f("h"), f("l"),
                   f("c"))


def frames(m1: pd.DataFrame, market: str, s: Settings = V1) -> Dict[str, Candles]:
    """W1, D1, H4, H1 and M5 from clean M1 bars (``time`` UTC, the bar's open), and the clock frames the settings
    execute or read swings on (V3: M30, M20, M15, M10, M3 and M1)."""
    t = m1["time"].to_numpy("datetime64[ns]").astype(np.int64)
    o, h, l, c = (m1[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    hour = s.day_open_hour(market)
    label = _day_labels(t, hour)
    weekday = np.asarray(label.dayofweek)
    keep = weekday < 5                                             # no trading day is named by a weekend date
    t, o, h, l, c, label = t[keep], o[keep], h[keep], l[keep], c[keep], label[keep]
    last_close = int(t[-1]) + MINUTE if len(t) else 0
    out: Dict[str, Candles] = {}

    m5 = t - t % (5 * MINUTE)
    out["M5"] = _aggregate("M5", m5, m5 + 5 * MINUTE, o, h, l, c, last_close)
    h1 = t - t % (60 * MINUTE)                                     # New York is a whole number of hours from UTC
    out["H1"] = _aggregate("H1", h1, h1 + 60 * MINUTE, o, h, l, c, last_close)

    day_open_local = label - pd.Timedelta(days=1) + pd.Timedelta(hours=hour)
    since_open = _local(t) - day_open_local
    bucket = np.asarray(since_open // pd.Timedelta(hours=4), dtype=np.int64)
    h4_open_local = day_open_local + pd.to_timedelta(bucket * 4, unit="h")
    h4_open = _utc(h4_open_local)
    h4_end = _utc(h4_open_local + pd.Timedelta(hours=4))
    out["H4"] = _aggregate("H4", h4_open, h4_end, o, h, l, c, last_close)

    d1_open, d1_end = _utc(day_open_local), _utc(label + pd.Timedelta(hours=hour))
    out["D1"] = _aggregate("D1", d1_open, d1_end, o, h, l, c, last_close)

    monday = label - pd.to_timedelta(np.asarray(label.dayofweek), unit="D")
    w1_open = _utc(monday - pd.Timedelta(days=1) + pd.Timedelta(hours=hour))
    w1_end = _utc(monday + pd.Timedelta(days=4) + pd.Timedelta(hours=hour))
    out["W1"] = _aggregate("W1", w1_open, w1_end, o, h, l, c, last_close)
    extra = sorted({s.e_frame, *s.exec_frames, *s.swing_pools, *(r for _, r in s.refine)} - set(FRAMES),
                   key=lambda tf: -MINUTES[tf])
    for tf in extra:                                               # on the clock, like M5 and H1
        start = t - t % (MINUTES[tf] * MINUTE)
        out[tf] = _aggregate(tf, start, start + MINUTES[tf] * MINUTE, o, h, l, c, last_close)
    return {tf: out[tf] for tf in (*FRAMES, *extra)}


def limit_expiry(at: int, until: int, s: Settings = V1) -> int:
    """When an order or a setup placed at ``at`` stops waiting (Requirement 15.4): the window's end (New York), or
    ``limit_minutes`` after ``at``, whichever is later; never after ``until``, the thesis's end."""
    local = pd.Timestamp(at, tz="UTC").tz_convert(NY)
    end = local.normalize() + pd.Timedelta(hours=s.window[1])
    return min(max(int(end.tz_convert("UTC").value), at + s.limit_minutes * MINUTE), until)


def stale(e: Candles, market: str, s: Settings = V1) -> np.ndarray:
    """Per E candle: whether the feed went silent for longer than ``s.stale_minutes`` before it inside the same
    trading day (TE-D17). The first candle after the gap is stale; the next ones aren't (the bars resumed)."""
    out = np.zeros(len(e), dtype=bool)
    if len(e) < 2:
        return out
    day = trading_day(e.t, market, s)
    gap = e.t[1:] - e.end[:-1]
    out[1:] = (gap > s.stale_minutes * MINUTE) & (day[1:] == day[:-1])
    return out
