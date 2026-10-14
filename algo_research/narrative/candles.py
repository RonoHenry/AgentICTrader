"""The candle narrative: how each finished candle formed, at any frame.

``narrate(bars, bar_tf, frame)`` reads bars finer than the frame and returns
one row per frame candle on the strategy calendar (Requirement 1):

- ``start``, ``end``, ``open`` (first bar's open), ``high``, ``low``,
  ``close`` (last bar's close), ``range``;
- ``t_high``, ``t_low``: opening times of the first bars at the extremes;
- ``direction``: UP, DOWN or FLAT, the close against the open (ND-D6);
- the **false-move extreme** (the low of an UP candle, the high of a DOWN
  one) and the **expansion extreme** (the other), with their times;
  ``inverted`` when the expansion extreme came first;
- ``false_move`` (open to the false-move extreme) and its share of the range;
- ``high_child``, ``low_child``: the index of the child candle holding each
  extreme, counted on the calendar from the frame's start (D1 by H4: 0 is
  the 17:00 New York slot; W1 by D1: 0 is the server's Sunday, so Monday is 1);
- ``complete``: false for a candle the series starts or ends inside.

It reads only bars and the calendar, never a timeframe constant (Property 1),
and a candle reads only its own bars (Property 2). It is hindsight: nothing
that decides may import it (Requirement 5).

``fill_phase(candle, bar_open)`` places a bar in a candle's formation
(Requirement 3.2): UNKNOWN for a missing, incomplete or FLAT candle, then
INVERTED, then BEFORE_FALSE_EXTREME, AT_FALSE_EXTREME, IN_EXPANSION (up to and
including the expansion extreme's bar) or AFTER_EXPANSION.

Validates: Requirements 1.1-1.4, 3.2 (.kiro/specs/market-narrative/requirements.md)
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping, Optional

import pandas as pd

from liquidity_engine.models import Timeframe
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["CHILD", "NARRATIVE_COLUMNS", "PHASES", "fill_phase", "narrate"]

CHILD = {Timeframe.MN1: Timeframe.W1, Timeframe.W1: Timeframe.D1, Timeframe.D1: Timeframe.H4,
         Timeframe.H4: Timeframe.H1, Timeframe.H1: Timeframe.M15}
NARRATIVE_COLUMNS = ("start", "end", "open", "high", "low", "close", "range", "t_high", "t_low",
                     "direction", "false_price", "t_false", "exp_price", "t_exp", "inverted",
                     "false_move", "false_share", "high_child", "low_child", "complete")
PHASES = ("BEFORE_FALSE_EXTREME", "AT_FALSE_EXTREME", "IN_EXPANSION", "AFTER_EXPANSION", "INVERTED", "UNKNOWN")

#: Nominal lengths, only to order timeframes ("finer than").
_MINUTES = {Timeframe.M1: 1, Timeframe.M3: 3, Timeframe.M5: 5, Timeframe.M15: 15, Timeframe.M30: 30,
            Timeframe.H1: 60, Timeframe.H3: 180, Timeframe.H4: 240, Timeframe.H6: 360, Timeframe.H8: 480,
            Timeframe.H12: 720, Timeframe.D1: 1440, Timeframe.W1: 10080, Timeframe.MN1: 43200}
_CALENDAR = StrategyCalendar()


class _Periods:
    """Calendar period starts, cached per opening hour for frames of an hour and
    up (their boundaries fall on whole UTC hours)."""

    def __init__(self, calendar: StrategyCalendar, tf: Timeframe) -> None:
        self.calendar, self.tf = calendar, tf
        self.hourly = _MINUTES[tf] >= 60
        self.cache: dict[pd.Timestamp, pd.Timestamp] = {}

    def _hour(self, key: pd.Timestamp) -> pd.Timestamp:
        hit = self.cache.get(key)
        if hit is None:
            hit = self.cache[key] = pd.Timestamp(self.calendar.period_start(key.to_pydatetime(), self.tf))
        return hit

    def start(self, t: pd.Timestamp) -> pd.Timestamp:
        if not self.hourly:
            return pd.Timestamp(self.calendar.period_start(t.to_pydatetime(), self.tf))
        return self._hour(t.replace(minute=0, second=0, microsecond=0, nanosecond=0))

    def starts(self, times: pd.DatetimeIndex) -> list[pd.Timestamp]:
        if not self.hourly:
            return [self.start(t) for t in times]
        hours = times.floor("h")
        return [self._hour(key) for key in hours]


class _Children:
    """Child indexes: how many child periods lie between a frame candle's start
    and the child period holding t, counted on the calendar."""

    def __init__(self, calendar: StrategyCalendar, child: Timeframe) -> None:
        self.calendar, self.child = calendar, child
        self.periods = _Periods(calendar, child)
        self.next: dict[datetime, datetime] = {}

    def index(self, start: pd.Timestamp, t: pd.Timestamp) -> int:
        target = self.periods.start(t).to_pydatetime()
        s: datetime = start.to_pydatetime()
        for k in range(64):
            if s >= target:
                return k
            following = self.next.get(s)
            if following is None:
                following = self.next[s] = self.calendar.period_end(s, self.child)
            s = following
        raise RuntimeError(f"{t} is not in a {self.child.value} child of the candle starting {start}")


def narrate(bars: pd.DataFrame, bar_tf: Timeframe, frame: Timeframe,
            calendar: Optional[StrategyCalendar] = None) -> pd.DataFrame:
    """One row per ``frame`` candle of ``bars`` (time in UTC, open, high, low, close)."""
    if _MINUTES[bar_tf] >= _MINUTES[frame]:
        raise ValueError(f"bars of {bar_tf.value} are not finer than the frame {frame.value}")
    calendar = calendar or _CALENDAR
    if bars.empty:
        return pd.DataFrame(columns=list(NARRATIVE_COLUMNS))
    df = bars.reset_index(drop=True)
    times = pd.DatetimeIndex(df["time"])
    periods = _Periods(calendar, frame)
    df = df.assign(start=periods.starts(times))
    g = df.groupby("start", sort=True)
    agg = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "i_high": g["high"].idxmax(), "i_low": g["low"].idxmin()})
    first_t, last_t = times[0], times[-1]
    last_end = pd.Timestamp(calendar.period_end(last_t.to_pydatetime(), bar_tf))
    child = CHILD.get(frame)
    children = _Children(calendar, child) if child else None

    rows = []
    for start, a in agg.iterrows():
        end = pd.Timestamp(calendar.period_end(start.to_pydatetime(), frame))
        t_high, t_low = times[int(a.i_high)], times[int(a.i_low)]
        direction = "UP" if a.close > a.open else "DOWN" if a.close < a.open else "FLAT"
        rng = a.high - a.low
        if direction == "UP":
            false_price, t_false, exp_price, t_exp = a.low, t_low, a.high, t_high
        elif direction == "DOWN":
            false_price, t_false, exp_price, t_exp = a.high, t_high, a.low, t_low
        else:
            false_price, t_false, exp_price, t_exp = math.nan, pd.NaT, math.nan, pd.NaT
        false_move = abs(a.open - false_price) if direction != "FLAT" else math.nan
        complete = not ((start <= first_t < end and first_t != start) or (start <= last_t < end and last_end != end))
        rows.append({
            "start": start, "end": end, "open": a.open, "high": a.high, "low": a.low, "close": a.close,
            "range": rng, "t_high": t_high, "t_low": t_low, "direction": direction,
            "false_price": false_price, "t_false": t_false, "exp_price": exp_price, "t_exp": t_exp,
            "inverted": direction != "FLAT" and t_exp < t_false,
            "false_move": false_move, "false_share": false_move / rng if rng > 0 else math.nan,
            "high_child": children.index(start, t_high) if children else None,
            "low_child": children.index(start, t_low) if children else None,
            "complete": complete,
        })
    out = pd.DataFrame(rows, columns=list(NARRATIVE_COLUMNS))
    for name in ("t_false", "t_exp"):
        out[name] = pd.to_datetime(out[name], utc=True)
    return out


def fill_phase(candle: Optional[Mapping[str, Any]], bar_open: pd.Timestamp) -> str:
    """Where in ``candle``'s formation the bar opening at ``bar_open`` lies."""
    if candle is None or not bool(candle["complete"]) or candle["direction"] == "FLAT":
        return "UNKNOWN"
    if bool(candle["inverted"]):
        return "INVERTED"
    if bar_open < candle["t_false"]:
        return "BEFORE_FALSE_EXTREME"
    if bar_open == candle["t_false"]:
        return "AT_FALSE_EXTREME"
    if bar_open <= candle["t_exp"]:
        return "IN_EXPANSION"
    return "AFTER_EXPANSION"
