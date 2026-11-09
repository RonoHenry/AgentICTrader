"""Bars as the frames AlgoMindDIS reads (algomind-dis Requirement 8.1, DIS-D2, DIS-D3).

MN1, W1 and D1 as ``liquidity_engine.context.frame_state.Candles`` (times UTC ns), built by ``algo_mind.dis`` (Yahoo's
daily bars, or the terminal's H1 as New York days). MN1 is the calendar month of the D1 candles. A week or month
still forming when the bars end is left out, and ``Frames.at(t)`` gives only the candles closed by t, so nothing
read at t can change when later bars arrive.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping

import numpy as np
import pandas as pd

from algo_mind.dis import daily_market
from liquidity_engine.context.frame_state import Candles

__all__ = ["Frames", "TIMEFRAMES", "candles", "from_daily", "from_market", "ny_daily"]

#: Senior first.
TIMEFRAMES = ("MN1", "W1", "D1")


def candles(tf: str, frame: pd.DataFrame) -> Candles:
    """A frame (open, high, low, close, t_open, t_close in ns) as Candles."""
    f = lambda c: frame[c].to_numpy(dtype=float)                       # noqa: E731
    return Candles(tf, frame["t_open"].to_numpy(dtype=np.int64), frame["t_close"].to_numpy(dtype=np.int64),
                   f("open"), f("high"), f("low"), f("close"))


def _monthly(d1: pd.DataFrame) -> pd.DataFrame:
    month = pd.to_datetime(d1["date"]).dt.to_period("M")
    g = d1.groupby(month.to_numpy(), sort=True)
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "t_open": g["t_open"].first(), "t_close": g["t_close"].last(),
                        "date": g["date"].last()})
    return out.reset_index(drop=True)


def _closed_weeks(w1: pd.DataFrame) -> pd.DataFrame:
    """The weeks whose Friday is in the bars: the last one is forming if it ends before Friday."""
    if len(w1) and pd.Timestamp(w1["date"].iloc[-1]).dayofweek < 4:
        return w1.iloc[:-1].reset_index(drop=True)
    return w1


def _closed_months(mn1: pd.DataFrame) -> pd.DataFrame:
    """The months whose last business day is in the bars: the last one is forming otherwise."""
    if len(mn1):
        last = pd.Timestamp(mn1["date"].iloc[-1])
        if last < last + pd.offsets.BMonthEnd(0):
            return mn1.iloc[:-1].reset_index(drop=True)
    return mn1


@dataclass(frozen=True)
class Frames:
    """One market's closed frames, senior first, and the candles closed by any time."""
    market: str
    full: Mapping[str, Candles]

    def at(self, t: int) -> Dict[str, Candles]:
        out = {}
        for tf, c in self.full.items():
            k = int(np.searchsorted(c.end, t, "right"))
            out[tf] = Candles(tf, c.t[:k], c.end[:k], c.o[:k], c.h[:k], c.l[:k], c.c[:k])
        return out

    def closes(self, tf: str = "D1") -> np.ndarray:
        """The close times of ``tf``: the state steps at D1's."""
        return self.full[tf].end


def from_market(market: str, hist: Mapping[str, pd.DataFrame]) -> Frames:
    """``algo_mind.dis``'s D1 and W1 (``DailyMarket.hist``) with MN1 grouped from D1."""
    d1 = hist["D1"]
    return Frames(market, {"MN1": candles("MN1", _closed_months(_monthly(d1))),
                           "W1": candles("W1", _closed_weeks(hist["W1"])),
                           "D1": candles("D1", d1)})


def ny_daily(h1: pd.DataFrame) -> pd.DataFrame:
    """H1 bars (``time`` UTC, the bar's open) as the chart's trading days: a day runs 17:00 to 17:00 New York and
    is named by the date it closes on (Sunday evening opens Monday's), as ``chain_view.trading_days`` names them."""
    t = pd.to_datetime(h1["time"], utc=True)
    date = (t.dt.tz_convert("America/New_York").dt.tz_localize(None) + pd.Timedelta(hours=7)).dt.normalize()
    g = h1.assign(_d=date.to_numpy()).sort_values("time").groupby("_d", sort=True)
    return pd.DataFrame({"date": g["open"].first().index, "open": g["open"].first().to_numpy(float),
                         "high": g["high"].max().to_numpy(float), "low": g["low"].min().to_numpy(float),
                         "close": g["close"].last().to_numpy(float)})


def from_daily(market: str, days: pd.DataFrame) -> Frames:
    """Yahoo's daily bars (date, open, high, low, close), the weekend merged into Monday (H-AE's day)."""
    return from_market(market, daily_market(days).hist)
