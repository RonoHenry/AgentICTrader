"""The replay's candles: one instrument's M1 history, served as of a time.

Market-narrative Requirement 10.2 and 10.4, and update 2026-10-14b. The M1 bars
carry the narrative's price basis (ND-D7), so the chart shows the prices the
narrative and the scores read. Any of the chart's timeframes
(``timeframes.TIMEFRAMES``) is aggregated on request from the M1 bars that closed
by ``until``, so the last bar is the forming one, as a live chart shows it, and
nothing after ``until`` can reach the chart.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from algo_research.config import trading_date_open
from algo_research.narrative import PriceBasis, apply_price_basis
from algo_research.replay.timeframes import TIMEFRAMES, aggregate, bucket, seconds_of, wall_seconds

__all__ = ["ReplayBars"]

_M1 = pd.Timedelta(minutes=1)


class ReplayBars:
    """An instrument's M1 bars, served as of any time at any of the chart's timeframes."""

    TIMEFRAMES = TIMEFRAMES
    #: Bars sent per request: enough history to read, few enough to draw quickly.
    LIMIT = 700
    _LIMITS = {"D1": 400, "W1": 160, "MN1": 60}

    def __init__(self, m1: pd.DataFrame, instrument: str, basis: Optional[PriceBasis] = None) -> None:
        self.instrument = instrument.upper()
        m1 = m1[["time", "open", "high", "low", "close"]].sort_values("time", kind="stable").reset_index(drop=True)
        m1["time"] = pd.DatetimeIndex(pd.to_datetime(m1["time"], utc=True)).as_unit("ns")
        self.m1 = apply_price_basis(m1, self.instrument, basis or PriceBasis())
        self.m1["time"] = pd.DatetimeIndex(self.m1["time"]).as_unit("ns")
        self._t = self.m1["time"].to_numpy(dtype="datetime64[ns]").view("int64")
        self._wall = wall_seconds(self.m1["time"])
        self._ohlc = tuple(self.m1[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close"))
        self.digits = 3 if self.instrument.endswith("JPY") or self.instrument.startswith("XAU") else 5

    def _n_closed_by(self, until: pd.Timestamp) -> int:
        """How many M1 bars have closed by ``until``."""
        return int(np.searchsorted(self._t, (pd.Timestamp(until) - _M1).value, side="right"))

    def price_at(self, until: pd.Timestamp) -> float:
        """The close of the last M1 bar closed by ``until``."""
        n = self._n_closed_by(until)
        if n == 0:
            raise ValueError(f"no {self.instrument} M1 bar closes by {until}")
        return float(self._ohlc[3][n - 1])

    def next_open(self, t: pd.Timestamp) -> Optional[pd.Timestamp]:
        """The open of the first M1 bar opening at or after ``t``; None after the data."""
        i = int(np.searchsorted(self._t, pd.Timestamp(t).value, side="left"))
        return pd.Timestamp(int(self._t[i]), tz="UTC") if i < len(self._t) else None

    def m1_between(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """M1 bars opening at or after ``start`` and closing by ``end``."""
        lo = int(np.searchsorted(self._t, pd.Timestamp(start).value, side="left"))
        return self.m1.iloc[lo:max(lo, self._n_closed_by(end))].reset_index(drop=True)

    def as_of(self, tf: str, until: pd.Timestamp, since: Optional[int] = None,
              limit: Optional[int] = None) -> pd.DataFrame:
        """The ``tf`` bars a chart shows at ``until``: columns time (the bar's start, New York wall
        seconds), open, high, low, close. Only M1 bars closed by ``until`` are read, so the last bar is
        the forming one while its period runs. ``since`` (a wall second): only the bars starting at or
        after the bar holding it, for live updates; otherwise the last ``limit`` bars."""
        size = seconds_of(tf)
        limit = limit or self._LIMITS.get(tf, self.LIMIT)
        n = self._n_closed_by(until)
        if n == 0:
            return aggregate(self._wall[:0], *(a[:0] for a in self._ohlc), tf)
        start = since if since is not None else int(self._wall[n - 1]) - (limit + 1) * size
        first = int(bucket(np.array([start], dtype=np.int64), tf)[0])
        lo = int(np.searchsorted(self._wall[:n], first, side="left"))
        bars = aggregate(self._wall[lo:n], *(a[lo:n] for a in self._ohlc), tf)
        return (bars if since is not None else bars.tail(limit)).reset_index(drop=True)

    def trading_dates(self, first: date, end: date) -> list[date]:
        """Trading dates in [first, end) whose D1 candle has M1 bars."""
        out = []
        day = first
        while day < end:
            open_ = pd.Timestamp(trading_date_open(day))
            if not self.m1_between(open_, pd.Timestamp(trading_date_open(day + timedelta(days=1)))).empty:
                out.append(day)
            day += timedelta(days=1)
        return out
