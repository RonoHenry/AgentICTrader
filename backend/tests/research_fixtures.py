"""Hand-made M1 paths for the AlgoResearch tests (not a test module).

``Path`` builds M1 bars minute by minute over the FX week (Sunday 17:00 to
Friday 17:00 New York) at a base price, with chosen bars overridden, so a
test states exactly the highs, lows and opens it reasons about.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from algo_research.frame import InstrumentFrame, build_grid, frame_from_arrays

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
MIN = timedelta(minutes=1)


def ny(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=NY).astimezone(UTC)


def fx_open(t: datetime) -> bool:
    """FX trades from Sunday 17:00 to Friday 17:00 New York."""
    local = t.astimezone(NY)
    if local.weekday() == 5:
        return False
    if local.weekday() == 6:
        return local.hour >= 17
    if local.weekday() == 4:
        return local.hour < 17
    return True


class Path:
    """M1 bars from ``start`` to ``end`` at ``base`` (a flat bar: open = close =
    base, high = base + wick, low = base - wick), FX hours only."""

    def __init__(self, start: datetime, end: datetime, base: float = 1.1, wick: float = 0.0001):
        self.times = [t for t in _minutes(start, end) if fx_open(t)]
        n = len(self.times)
        self.index = {t: i for i, t in enumerate(self.times)}
        self.o, self.c = np.full(n, base), np.full(n, base)
        self.h, self.l = np.full(n, base + wick), np.full(n, base - wick)

    def bar(self, t: datetime, o: Optional[float] = None, h: Optional[float] = None, lo: Optional[float] = None,
            c: Optional[float] = None) -> "Path":
        i = self.index[t]
        if o is not None:
            self.o[i] = o
        if c is not None:
            self.c[i] = c
        if h is not None:
            self.h[i] = h
        if lo is not None:
            self.l[i] = lo
        self.h[i] = max(self.h[i], self.o[i], self.c[i])
        self.l[i] = min(self.l[i], self.o[i], self.c[i])
        return self

    def level(self, start: datetime, end: datetime, price: float, wick: float = 0.0001) -> "Path":
        """Every bar in [start, end) flat at ``price``."""
        for t in self.times:
            if start <= t < end:
                i = self.index[t]
                self.o[i] = self.c[i] = price
                self.h[i], self.l[i] = price + wick, price - wick
        return self

    def drop(self, start: datetime, end: datetime) -> "Path":
        keep = [i for i, t in enumerate(self.times) if not start <= t < end]
        self.times = [self.times[i] for i in keep]
        self.o, self.h, self.l, self.c = self.o[keep], self.h[keep], self.l[keep], self.c[keep]
        self.index = {t: i for i, t in enumerate(self.times)}
        return self

    def frame(self, instrument: str = "EURUSD", spread: float = 0.0001) -> InstrumentFrame:
        return frame_from_arrays(instrument, pd.DatetimeIndex(self.times), self.o.copy(), self.h.copy(),
                                 self.l.copy(), self.c.copy(), spread=np.full(len(self.times), spread),
                                 typical_spread=spread, stop_slippage=spread / 4)


def _minutes(start: datetime, end: datetime):
    t = start
    while t < end:
        yield t
        t += MIN


def grid_for(frame: InstrumentFrame, first: date, end: date):
    return build_grid(frame, {"explore": (first, end)})


# ── simulated markets (self-check, task 255) ─────────────────────────────────

#: Volatility by New York hour, relative: quiet at the rollover and in Asia,
#: busiest at the London and New York opens.
SESSION_VOL = {17: 0.5, 18: 0.5, 19: 0.5, 20: 0.6, 21: 0.6, 22: 0.6, 23: 0.6, 0: 0.7, 1: 0.8, 2: 1.5, 3: 1.5,
               4: 1.3, 5: 1.0, 6: 1.0, 7: 1.6, 8: 1.8, 9: 1.8, 10: 1.4, 11: 1.0, 12: 0.9, 13: 0.9, 14: 0.8,
               15: 0.8, 16: 0.6}
_HOUR_VOL = np.array([SESSION_VOL[h] for h in range(24)])


def fx_minutes(first_sunday: date, days: int) -> pd.DatetimeIndex:
    """Every FX minute (Sunday 17:00 to Friday 17:00 New York) of ``days`` trading dates."""
    start = pd.Timestamp(datetime(first_sunday.year, first_sunday.month, first_sunday.day, 17, tzinfo=NY))
    weeks = days // 5 + 2
    every = pd.date_range(start, periods=weeks * 7 * 1440, freq="1min").tz_convert("UTC")
    local = every.tz_convert("America/New_York")
    wd, hour = local.weekday, local.hour
    trading = ~((wd == 5) | ((wd == 6) & (hour < 17)) | ((wd == 4) & (hour >= 17)))
    every = every[trading]
    day = (local[trading].tz_localize(None) + pd.Timedelta(hours=7)).normalize()
    keep = day < sorted(set(day))[days] if len(set(day)) > days else np.ones(len(every), dtype=bool)
    return every[keep]


def simulated_frame(instrument: str, times: pd.DatetimeIndex, normals: np.ndarray, base: float = 1.1,
                    sigma: float = 0.00006, spread: float = 0.0001) -> InstrumentFrame:
    """A driftless random walk on ``times`` with session-shaped volatility, M1 bars
    with wicks, and a constant spread. ``normals`` holds 3 standard normals per bar."""
    n = len(times)
    vol = sigma * _HOUR_VOL[times.tz_convert("America/New_York").hour.to_numpy()]
    close = base + np.cumsum(normals[:n] * vol)
    open_ = np.concatenate([[base], close[:-1]])
    high = np.maximum(open_, close) + np.abs(normals[n:2 * n]) * vol * 0.5
    low = np.minimum(open_, close) - np.abs(normals[2 * n:3 * n]) * vol * 0.5
    return frame_from_arrays(instrument, times, open_, high, low, close, spread=np.full(n, spread),
                             typical_spread=spread, stop_slippage=spread / 4)


def research_data(frames: dict, slices: dict):
    """The research tables for simulated frames: market features and labels (no engine)."""
    from algo_research.dataset import ResearchData
    from algo_research.features.market import market_features
    from algo_research.labels import build_labels

    markets = {i: market_features(f, build_grid(f, slices)) for i, f in frames.items()}
    labels = [build_labels(frames[i], m) for i, m in markets.items()]
    return ResearchData(frames=frames, features=pd.concat(markets.values(), ignore_index=True),
                        labels=pd.concat(labels, ignore_index=True))
