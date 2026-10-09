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
