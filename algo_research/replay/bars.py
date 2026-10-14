"""The replay's candles: one instrument's M1 history, served as of a time.

Market-narrative Requirement 10.2 and 10.4. The M1 bars carry the narrative's
price basis (ND-D7), so the chart shows the prices the narrative and the scores
read. Every timeframe is aggregated once on the strategy calendar
(``aggregate_frame``); ``as_of(tf, until)`` then returns the bars closed by
``until`` plus the forming bar, built only from the M1 bars that closed by then,
as a live chart would show it.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from algo_research.config import trading_date_open
from algo_research.frame import aggregate_frame, period_bounds
from algo_research.narrative import PriceBasis, apply_price_basis
from liquidity_engine.models import Timeframe

__all__ = ["ReplayBars"]

_M1 = pd.Timedelta(minutes=1)
_COLUMNS = ["time", "close_time", "open", "high", "low", "close"]


class ReplayBars:
    """An instrument's M1 bars and their timeframes, as of any time."""

    TIMEFRAMES = (Timeframe.W1, Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5, Timeframe.M1)
    #: Bars sent per request: enough history to read, small enough to draw quickly.
    LIMIT = {Timeframe.W1: 104, Timeframe.D1: 260, Timeframe.H4: 600, Timeframe.H1: 800, Timeframe.M15: 800,
             Timeframe.M5: 900, Timeframe.M1: 1000}

    def __init__(self, m1: pd.DataFrame, instrument: str, basis: Optional[PriceBasis] = None) -> None:
        self.instrument = instrument.upper()
        m1 = m1[["time", "open", "high", "low", "close"]].sort_values("time", kind="stable").reset_index(drop=True)
        m1["time"] = pd.DatetimeIndex(pd.to_datetime(m1["time"], utc=True)).as_unit("ns")
        self.m1 = apply_price_basis(m1, self.instrument, basis or PriceBasis())
        self.m1["time"] = pd.DatetimeIndex(self.m1["time"]).as_unit("ns")
        self._t = self.m1["time"].to_numpy(dtype="datetime64[ns]").view("int64")
        self._closed = {}
        for tf in self.TIMEFRAMES:
            if tf == Timeframe.M1:
                continue
            bars = aggregate_frame(self.m1, tf)
            for col in ("time", "close_time"):
                bars[col] = pd.DatetimeIndex(bars[col]).as_unit("ns")
            self._closed[tf] = bars[_COLUMNS]
        self.digits = 3 if self.instrument.endswith("JPY") or self.instrument.startswith("XAU") else 5

    def _n_closed_by(self, until: pd.Timestamp) -> int:
        """How many M1 bars have closed by ``until``."""
        return int(np.searchsorted(self._t, (pd.Timestamp(until) - _M1).value, side="right"))

    def price_at(self, until: pd.Timestamp) -> float:
        """The close of the last M1 bar closed by ``until``."""
        n = self._n_closed_by(until)
        if n == 0:
            raise ValueError(f"no {self.instrument} M1 bar closes by {until}")
        return float(self.m1["close"].iloc[n - 1])

    def m1_between(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """M1 bars opening at or after ``start`` and closing by ``end``."""
        lo = int(np.searchsorted(self._t, pd.Timestamp(start).value, side="left"))
        return self.m1.iloc[lo:max(lo, self._n_closed_by(end))].reset_index(drop=True)

    def as_of(self, tf: Timeframe, until: pd.Timestamp, limit: Optional[int] = None) -> pd.DataFrame:
        """The ``tf`` bars a chart shows at ``until``: closed bars, then the forming one."""
        until = pd.Timestamp(until)
        limit = limit or self.LIMIT[tf]
        n = self._n_closed_by(until)
        if tf == Timeframe.M1:
            rows = self.m1.iloc[max(0, n - limit):n]
            out = rows.assign(close_time=rows["time"] + _M1)[_COLUMNS]
            return out.reset_index(drop=True)
        closed = self._closed[tf]
        k = int(np.searchsorted(closed["close_time"].to_numpy(dtype="datetime64[ns]").view("int64"),
                                until.value, side="right"))
        out = closed.iloc[max(0, k - limit):k]
        if n:
            start, end = period_bounds(pd.DatetimeIndex([self.m1["time"].iloc[n - 1]]), tf)
            if end[0] > until:                      # the last closed M1 bar's period is still forming
                part = self.m1.iloc[int(np.searchsorted(self._t, start[0].value, side="left")):n]
                forming = pd.DataFrame({"time": [start[0]], "close_time": [end[0]], "open": [part["open"].iloc[0]],
                                        "high": [part["high"].max()], "low": [part["low"].min()],
                                        "close": [part["close"].iloc[-1]]})
                for col in ("time", "close_time"):
                    forming[col] = pd.DatetimeIndex(forming[col]).as_unit("ns")
                out = pd.concat([out.iloc[1:] if len(out) >= limit else out, forming], ignore_index=True)
        return out.reset_index(drop=True)

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
