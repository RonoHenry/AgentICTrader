"""Time and volatility (algomind-dis Requirement 8, §8): context, never a direction.

Times are UTC; New York time comes from ``zoneinfo``, so the clocks' changes are the calendar's, never a fixed
offset. Read at a D1 close, about the day that closed: its weekday, the week's and month's opens and price against
them, and whether the week is the month's first or second (the reader's month window). Scheduled news comes from a
calendar the caller passes (live: ``algo_research.calendar``); it explains volatility and carries no side (§8.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from algo_research.phases import label_phases
from algomind_dis.analyzers.objectives import adr
from algomind_dis.settings import V1, Settings
from liquidity_engine.context.frame_state import Candles

__all__ = ["NY", "TimeContext", "VolatilityContext", "ny_hours", "time_context", "volatility_context"]

NY = ZoneInfo("America/New_York")


def ny_hours(t) -> float:
    """``t`` (a UTC time) as hours since midnight in New York."""
    ny = pd.Timestamp(t).tz_convert(NY)
    return ny.hour + ny.minute / 60


@dataclass(frozen=True)
class TimeContext:
    day: str                     # the trading day that closed, ISO
    weekday: str
    week_of_month: int           # by its week's Monday: days 1-7 are week 1
    first_two_weeks: bool
    week_open: float
    month_open: float
    above_week_open: bool
    above_month_open: bool
    scheduled: tuple[str, ...]


@dataclass(frozen=True)
class VolatilityContext:
    adr: float
    last_range: float
    last_ratio: float            # the last candle's range in ADRs
    expanding: bool              # at least ``displacement_body`` ADRs
    phase: str                   # algo_research.phases' label of the last candle ("" before the first box)


def time_context(d1: Candles, calendar: Optional[Callable[[datetime], Iterable[str]]] = None) -> TimeContext:
    day = pd.Timestamp(int(d1.t[-1]), tz="UTC")
    monday = (day - pd.Timedelta(days=day.dayofweek)).normalize()
    month = day.normalize().replace(day=1)
    t = d1.t.astype(np.int64)
    week_open = float(d1.o[int(np.searchsorted(t, monday.value, "left"))])
    month_open = float(d1.o[int(np.searchsorted(t, month.value, "left"))])
    week = (monday.day - 1) // 7 + 1
    close = float(d1.c[-1])
    scheduled = tuple(calendar(day.to_pydatetime())) if calendar is not None else ()
    return TimeContext(day.date().isoformat(), day.day_name(), week, week <= 2, week_open, month_open,
                       close > week_open, close > month_open, scheduled)


def volatility_context(d1: Candles, s: Settings = V1, labels: Optional[np.ndarray] = None) -> VolatilityContext:
    daily = adr(d1, s)
    last = float(d1.h[-1] - d1.l[-1])
    ratio = last / daily if daily and np.isfinite(daily) else float("nan")
    labels = label_phases(d1.o, d1.h, d1.l, d1.c) if labels is None else labels
    return VolatilityContext(float(daily), last, float(ratio), bool(ratio >= s.displacement_body),
                             str(labels[len(d1) - 1]))
