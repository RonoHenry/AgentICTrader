"""Strategy-calendar candles for the engine: aggregation, and (task 191) the as-of view.

``aggregate()`` builds bars of any timeframe from finer bars on the
StrategyCalendar (decision D9), so a UTC-server broker, a New York-close
broker and Binance all yield identical H4/D1/W1 candles from the same
prices. Pure: no I/O, no clock.

Validates: Requirements 3.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from liquidity_engine.models import Candle, Timeframe
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["aggregate"]

# Nominal lengths, used only to check that input bars nest inside the target
# bars. Actual boundaries always come from the calendar.
_NOMINAL_MINUTES = {
    Timeframe.M1: 1, Timeframe.M3: 3, Timeframe.M5: 5, Timeframe.M15: 15, Timeframe.M30: 30,
    Timeframe.H1: 60, Timeframe.H3: 180, Timeframe.H4: 240, Timeframe.H6: 360, Timeframe.H8: 480,
    Timeframe.H12: 720, Timeframe.D1: 1440,
}


def aggregate(
    bars: Sequence[Candle],
    tf: Timeframe,
    calendar: StrategyCalendar,
    as_of: Optional[datetime] = None,
) -> list[Candle]:
    """Closed ``tf`` bars built from finer ``bars`` (oldest first, one instrument).

    A period is emitted only if it has ended by ``as_of``. By default that is
    the close of the last input bar, so a partly covered trailing period is
    never presented as complete. Periods with no input bars produce no output
    (no synthetic weekend bars).
    """
    if not bars:
        return []
    _validate(bars, tf)
    cutoff = as_of or calendar.period_end(bars[-1].timestamp, bars[-1].timeframe)

    out: list[Candle] = []
    group: list[Candle] = []
    start = end = None
    for bar in bars:
        if end is None or bar.timestamp >= end:
            if group and end <= cutoff:
                out.append(_combine(group, start, tf))
            group = []
            start = calendar.period_start(bar.timestamp, tf)
            end = calendar.period_end(bar.timestamp, tf)
        group.append(bar)
    if group and end <= cutoff:
        out.append(_combine(group, start, tf))
    return out


def _combine(group: list[Candle], start: datetime, tf: Timeframe) -> Candle:
    volumes = [b.volume for b in group if b.volume is not None]
    return Candle(
        timestamp=start,
        open=group[0].open,
        high=max(b.high for b in group),
        low=min(b.low for b in group),
        close=group[-1].close,
        volume=sum(volumes) if volumes else None,
        timeframe=tf,
        instrument=group[0].instrument,
    )


def _validate(bars: Sequence[Candle], tf: Timeframe) -> None:
    instrument = bars[0].instrument
    previous = None
    for bar in bars:
        if bar.instrument != instrument:
            raise ValueError(f"aggregate() got bars for {instrument} and {bar.instrument}")
        if previous is not None and bar.timestamp <= previous:
            raise ValueError("aggregate() needs bars in strictly ascending time order")
        previous = bar.timestamp
    for source_tf in {bar.timeframe for bar in bars}:
        if not _nests(source_tf, tf):
            raise ValueError(f"Cannot aggregate {source_tf.value} bars into {tf.value}: input is coarser or doesn't nest")


def _nests(fine: Timeframe, coarse: Timeframe) -> bool:
    if fine == coarse:
        return True
    if coarse in (Timeframe.W1, Timeframe.MN1):
        return fine in _NOMINAL_MINUTES  # anything up to D1 nests in a week or month
    fine_minutes, coarse_minutes = _NOMINAL_MINUTES.get(fine), _NOMINAL_MINUTES.get(coarse)
    if fine_minutes is None or coarse_minutes is None:
        return False
    return fine_minutes <= coarse_minutes and coarse_minutes % fine_minutes == 0
