"""StrategyCalendar — the one candle calendar every strategy timeframe follows.

Decision D9 (.kiro/specs/algo-backtester): the engine must see the same
candles whatever the broker or venue. Exness runs its MT5 server on UTC,
other brokers on New York close, and Binance on UTC. Their native H4/D1/W1
bars differ, and so would the signals. So every timeframe is built on one
calendar: the FX market's New York close.

The rule is "floor in New York wall time + 7 h", which is exactly how an
MT5 ``ny_close`` server clock behaves (services/market_data/mt5_clock.py),
so DST is handled the same way such servers handle it:

- D1 starts at 17:00 New York.
- H1..H12 floor from the 17:00 day start, so H4 starts at 17, 21, 01, 05,
  09 and 13 New York. Every intraday length divides 24 h, so all nest in D1.
- W1 periods start at the ny_close server's Sunday 00:00, which is Saturday
  17:00 New York: the label MT5 gives weekly bars. The FX week opens Sunday
  17:00 inside it, so the trades are the same as "Sunday open to Friday close".
- MN1 starts at the first of the month, at the same daily boundary.

On the two US DST-change days, a period can be shorter or longer than its
nominal length (the hour that New York skips or repeats). It's the same
thing a ny_close MT5 server does, and periods still tile time with no gaps
or overlaps. FX is closed at those hours anyway; crypto is not.

Validates: Requirements 3.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from liquidity_engine.models import Timeframe
from services.market_data.mt5_clock import NY_CLOSE, MT5ServerClock

__all__ = ["StrategyCalendar"]

_INTRADAY_MINUTES = {
    Timeframe.M1: 1,
    Timeframe.M3: 3,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.H3: 180,
    Timeframe.H4: 240,
    Timeframe.H6: 360,
    Timeframe.H8: 480,
    Timeframe.H12: 720,
}
_EPOCH = datetime(1970, 1, 1)
_NY_CLOSE_CLOCK = MT5ServerClock(NY_CLOSE)


class StrategyCalendar:
    """Period boundaries for every timeframe on the New York-close calendar."""

    def period_start(self, t: datetime, tf: Timeframe) -> datetime:
        """Start (UTC) of the ``tf`` period containing instant ``t``."""
        return self._bounds(t, tf)[0]

    def period_end(self, t: datetime, tf: Timeframe) -> datetime:
        """End (UTC, exclusive) of the ``tf`` period containing ``t``; the next period's start."""
        return self._bounds(t, tf)[1]

    def matches_native(self, clock: Optional[MT5ServerClock], tf: Timeframe) -> bool:
        """Whether a venue's native ``tf`` bars coincide with this calendar.

        ``clock`` is an MT5 server clock, or None for Binance (UTC). Where this
        is False, the live runner aggregates ``tf`` from finer native bars.
        """
        spec = clock.spec if clock is not None else "0"
        if spec == NY_CLOSE:
            return True
        offset_minutes = round(float(spec) * 60)
        minutes = _INTRADAY_MINUTES.get(tf)
        # A fixed-offset server's intraday bars line up only where the bar length
        # divides both the offset from New York-close midnight and the hour.
        # Whole-hour offsets: H1 and below. Never D1/W1/MN1: DST moves New York
        # close against any fixed offset.
        return minutes is not None and minutes <= 60 and offset_minutes % minutes == 0

    # ── internals ──────────────────────────────────────────────────────────

    def _bounds(self, t: datetime, tf: Timeframe) -> tuple[datetime, datetime]:
        """The [start, end) UTC interval containing ``t``.

        Boundaries are server-wall times mapped to their first real occurrence.
        When New York falls back, the wall clock repeats an hour. Instants in
        the repeat map to boundaries already passed, so the walk below moves
        on to the period that is still open at ``t``: the one running into the
        repeated hour, which absorbs it. Periods therefore tile time with no
        gaps or overlaps.
        """
        start_wall = self._floor(self._wall(t), tf)
        start = self._to_utc(start_wall)
        end_wall = self._next(start_wall, tf)
        end = self._to_utc(end_wall)
        for _ in range(2000):  # at most one repeated hour of M1 bars
            if end > t:
                return start, end
            start_wall, start = end_wall, end
            end_wall = self._next(start_wall, tf)
            end = self._to_utc(end_wall)
        raise RuntimeError(f"Could not place {t} in a {tf.value} period")

    @staticmethod
    def _wall(t: datetime) -> datetime:
        if t.tzinfo is None:
            raise ValueError("StrategyCalendar requires timezone-aware datetimes")
        return _NY_CLOSE_CLOCK.to_server(t).replace(tzinfo=None)

    @staticmethod
    def _to_utc(wall: datetime) -> datetime:
        return _NY_CLOSE_CLOCK.to_utc(int((wall - _EPOCH).total_seconds()))

    @staticmethod
    def _floor(wall: datetime, tf: Timeframe) -> datetime:
        day = wall.replace(hour=0, minute=0, second=0, microsecond=0)
        minutes = _INTRADAY_MINUTES.get(tf)
        if minutes is not None:
            elapsed = int((wall - day).total_seconds() // 60)
            return day + timedelta(minutes=elapsed - elapsed % minutes)
        if tf == Timeframe.D1:
            return day
        if tf == Timeframe.W1:
            return day - timedelta(days=(day.weekday() + 1) % 7)  # back to Sunday (server)
        if tf == Timeframe.MN1:
            return day.replace(day=1)
        raise ValueError(f"Unsupported timeframe {tf}")

    @staticmethod
    def _next(start: datetime, tf: Timeframe) -> datetime:
        minutes = _INTRADAY_MINUTES.get(tf)
        if minutes is not None:
            return start + timedelta(minutes=minutes)
        if tf == Timeframe.D1:
            return start + timedelta(days=1)
        if tf == Timeframe.W1:
            return start + timedelta(days=7)
        if tf == Timeframe.MN1:
            return (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        raise ValueError(f"Unsupported timeframe {tf}")
