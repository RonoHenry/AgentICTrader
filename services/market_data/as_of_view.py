"""Strategy-calendar candles for the engine: aggregation and the as-of view.

``aggregate()`` builds bars of any timeframe from finer bars on the
StrategyCalendar (decision D9), so a UTC-server broker, a New York-close
broker and Binance all yield identical H4/D1/W1 candles from the same
prices.

``compose_as_of_view()`` (task 191) is the candle window the engine sees at
an as-of time t, built only from what was known at t. The backtester and the
live runner both use it, so a backtest replays the evaluation live trading
performs.

Both are pure: no I/O, no clock.

Validates: Requirements 2.1-2.4, 3.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Optional, Sequence

from liquidity_engine.models import Candle, Timeframe
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["aggregate", "compose_as_of_view"]

# Nominal lengths, used only to check that input bars nest inside the target
# bars. Actual boundaries always come from the calendar.
_NOMINAL_MINUTES = {
    Timeframe.M1: 1, Timeframe.M3: 3, Timeframe.M5: 5, Timeframe.M15: 15, Timeframe.M30: 30,
    Timeframe.H1: 60, Timeframe.H3: 180, Timeframe.H4: 240, Timeframe.H6: 360, Timeframe.H8: 480,
    Timeframe.H12: 720, Timeframe.D1: 1440,
}
# For ordering only: which timeframes are above the entry timeframe.
_RANK_MINUTES = {**_NOMINAL_MINUTES, Timeframe.W1: 7 * 1440, Timeframe.MN1: 31 * 1440}
_M1 = timedelta(minutes=1)


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


def compose_as_of_view(
    closed: Mapping[Timeframe, Sequence[Candle]],
    recent_m1: Sequence[Candle],
    t: datetime,
    entry_tf: Timeframe,
    windows: Mapping[Timeframe, int],
    calendar: StrategyCalendar,
) -> dict[Timeframe, list[Candle]]:
    """The engine's candle window at ``t``, with nothing from t's future.

    ``closed`` holds strategy-calendar bars per timeframe, oldest first; it
    may run past ``t`` (bars that haven't closed by ``t`` are ignored).
    ``recent_m1`` must cover the in-progress period of every higher timeframe
    (the current W1 period at most), oldest first.

    - The entry timeframe and below: the last ``windows[tf]`` bars closed by ``t``.
    - Higher timeframes: the last ``windows[tf] - 1`` closed bars plus one
      in-progress bar, aggregated from the M1 bars of the current period that
      closed by ``t``. Before the first of them closes there is no
      in-progress bar, and the window holds ``windows[tf]`` closed bars.

    A bar counts as closed when its calendar period has ended by ``t``.
    """
    missing = [tf.value for tf in closed if tf not in windows]
    if missing:
        raise ValueError(f"compose_as_of_view: no window size for {', '.join(missing)}")
    if entry_tf not in closed:
        raise ValueError(f"compose_as_of_view: no {entry_tf.value} bars for the entry timeframe")
    if recent_m1 and recent_m1[0].timeframe != Timeframe.M1:
        raise ValueError(f"compose_as_of_view: recent_m1 holds {recent_m1[0].timeframe.value} bars, not M1")

    view: dict[Timeframe, list[Candle]] = {}
    for tf, bars in closed.items():
        period_start = calendar.period_start(t, tf)
        # Calendar bars that start before the period containing t have ended by t.
        # Only the window is sliced: Phase A calls this at every entry close.
        n_done = bisect_left(bars, period_start, key=_timestamp)
        if n_done and calendar.period_start(bars[n_done - 1].timestamp, tf) != bars[n_done - 1].timestamp:
            # Off-calendar bars (e.g. a UTC server's native H4) could pass the
            # test above while still forming: that would leak t's future.
            raise ValueError(
                f"compose_as_of_view: {tf.value} bar at {bars[n_done - 1].timestamp} is not on the strategy calendar"
            )
        forming = None
        if _RANK_MINUTES[tf] > _RANK_MINUTES[entry_tf]:
            known = recent_m1[
                bisect_left(recent_m1, period_start, key=_timestamp): bisect_right(recent_m1, t - _M1, key=_timestamp)
            ]
            if known:
                forming = _combine(known, period_start, tf)
        keep = windows[tf] - (forming is not None)
        view[tf] = list(bars[max(0, n_done - keep): n_done]) + ([forming] if forming is not None else [])
    return view


def _timestamp(bar: Candle) -> datetime:
    return bar.timestamp


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
