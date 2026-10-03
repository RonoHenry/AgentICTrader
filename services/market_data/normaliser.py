"""
Tick normaliser and OHLCV candle builder.

Consumes raw price ticks and aggregates them into OHLCV candles for the
configured timeframes: M1, M5, M15, H1, H4, D1, W1.

Design rules
------------
- Every call to :meth:`TickNormaliser.process_tick` returns a list of
  :class:`Candle` objects — one per configured timeframe — reflecting the
  current (possibly incomplete) state of each candle.
- When a tick crosses a timeframe boundary the *completed* candle for the
  previous period is emitted with ``complete=True``, followed immediately by
  a new incomplete candle for the new period with ``complete=False``.
- All timestamps are UTC-aware.  Naive datetimes raise :exc:`ValueError`.
- Volume is the tick count within the candle period.

Validates: Requirements FR-1 (real-time multi-timeframe OHLCV ingestion).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

__all__ = [
    "Candle",
    "TickNormaliser",
    "SUPPORTED_TIMEFRAMES",
    "TIMEFRAME_SECONDS",
]


# ---------------------------------------------------------------------------
# Timeframe configuration
# ---------------------------------------------------------------------------

#: Supported timeframe labels and their duration in seconds.
TIMEFRAME_SECONDS: Dict[str, int] = {
    "M1":  60,
    "M5":  300,
    "M15": 900,
    "H1":  3_600,
    "H4":  14_400,
    "D1":  86_400,
    "W1":  604_800,
}

SUPPORTED_TIMEFRAMES = list(TIMEFRAME_SECONDS.keys())


# ---------------------------------------------------------------------------
# Candle dataclass
# ---------------------------------------------------------------------------

@dataclass
class Candle:
    """A single OHLCV candle for one instrument and timeframe.

    Attributes:
        instrument: Normalised instrument symbol, e.g. ``"EURUSD"``.
        timeframe:  Timeframe label, e.g. ``"M1"``.
        time:       UTC-aware open time of the candle, aligned to the
                    timeframe boundary.
        open:       Price of the first tick in this period.
        high:       Highest price seen in this period.
        low:        Lowest price seen in this period.
        close:      Price of the most recent tick in this period.
        volume:     Number of ticks received in this period.
        complete:   ``True`` when the candle period has closed (a tick
                    arrived in the *next* period).  ``False`` while the
                    period is still open.
    """

    instrument: str
    timeframe: str
    time: datetime          # UTC-aware boundary open time
    open: float
    high: float
    low: float
    close: float
    volume: float
    complete: bool = False

    def __repr__(self) -> str:  # pragma: no cover
        status = "COMPLETE" if self.complete else "live"
        return (
            f"Candle({self.instrument} {self.timeframe} "
            f"{self.time.isoformat()} "
            f"O={self.open} H={self.high} L={self.low} C={self.close} "
            f"V={self.volume} [{status}])"
        )


# ---------------------------------------------------------------------------
# Internal per-instrument-timeframe state
# ---------------------------------------------------------------------------

@dataclass
class _CandleState:
    """Mutable accumulator for an in-progress candle."""

    boundary: datetime   # UTC-aware open time of the current period
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def to_candle(self, instrument: str, timeframe: str, complete: bool) -> Candle:
        return Candle(
            instrument=instrument,
            timeframe=timeframe,
            time=self.boundary,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            complete=complete,
        )


# ---------------------------------------------------------------------------
# Boundary helpers
# ---------------------------------------------------------------------------

def _floor_to_boundary(ts: datetime, timeframe: str) -> datetime:
    """Return the UTC open-time boundary for *ts* in the given *timeframe*.

    The result is always UTC-aware and has sub-boundary components zeroed.

    Raises:
        ValueError: If *timeframe* is not in TIMEFRAME_SECONDS.
    """
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(
            f"Unknown timeframe '{timeframe}'. "
            f"Supported: {list(TIMEFRAME_SECONDS.keys())}"
        )

    # Work in UTC epoch seconds for arithmetic simplicity.
    epoch = int(ts.timestamp())

    if timeframe == "W1":
        # Align to Monday 00:00:00 UTC.
        # Python's weekday(): Monday=0, Sunday=6.
        # epoch_seconds since Unix epoch (Thursday 1970-01-01).
        # Days since epoch: epoch // 86400
        # Day-of-week offset from Monday: (epoch // 86400 + 3) % 7
        #   (1970-01-01 was a Thursday → +3 to shift so Monday=0)
        days_since_epoch = epoch // 86400
        day_of_week = (days_since_epoch + 3) % 7  # 0=Monday
        monday_epoch = (days_since_epoch - day_of_week) * 86400
        return datetime.fromtimestamp(monday_epoch, tz=timezone.utc)

    if timeframe == "D1":
        # Align to 00:00:00 UTC of the same day.
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)

    # For sub-day timeframes, floor to the nearest multiple of the period.
    period = TIMEFRAME_SECONDS[timeframe]
    floored_epoch = (epoch // period) * period
    return datetime.fromtimestamp(floored_epoch, tz=timezone.utc)


def _next_boundary(boundary: datetime, timeframe: str) -> datetime:
    """Return the *next* boundary after *boundary* for *timeframe*."""
    if timeframe == "W1":
        return boundary + timedelta(weeks=1)
    if timeframe == "D1":
        return boundary + timedelta(days=1)
    return boundary + timedelta(seconds=TIMEFRAME_SECONDS[timeframe])


# ---------------------------------------------------------------------------
# TickNormaliser
# ---------------------------------------------------------------------------

class TickNormaliser:
    """Aggregates raw price ticks into OHLCV candles for multiple timeframes.

    Usage::

        normaliser = TickNormaliser(timeframes=["M1", "M5", "H1"])
        candles = normaliser.process_tick("EURUSD", 1.0850, datetime.now(timezone.utc))
        # candles is a list of Candle objects — one per timeframe.

    Args:
        timeframes: List of timeframe labels to track.  Defaults to all
                    supported timeframes.

    Raises:
        ValueError: If an unsupported timeframe is requested.
    """

    def __init__(self, timeframes: Optional[List[str]] = None) -> None:
        if timeframes is None:
            timeframes = SUPPORTED_TIMEFRAMES

        for tf in timeframes:
            if tf not in TIMEFRAME_SECONDS:
                raise ValueError(
                    f"Unsupported timeframe '{tf}'. "
                    f"Supported: {SUPPORTED_TIMEFRAMES}"
                )

        self._timeframes: List[str] = list(timeframes)

        # State keyed by (instrument, timeframe)
        self._state: Dict[Tuple[str, str], _CandleState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_tick(
        self,
        instrument: str,
        price: float,
        timestamp: datetime,
    ) -> List[Candle]:
        """Process a single price tick and return the current candle state.

        For each configured timeframe this method:
        1. Checks whether the tick belongs to the current candle period.
        2. If the tick crosses into a new period, emits the *completed*
           previous candle (``complete=True``) and starts a new one.
        3. Returns the current (possibly updated) candle for every timeframe
           as an incomplete candle (``complete=False``), except for the
           completed candle which is prepended with ``complete=True``.

        Args:
            instrument: Instrument symbol, e.g. ``"EURUSD"``.
            price:      Mid-price (or bid/ask mid) for this tick.
            timestamp:  UTC-aware datetime of the tick.

        Returns:
            A list of :class:`Candle` objects — one per configured timeframe.
            When a boundary is crossed the list contains *two* entries for
            that timeframe: the completed candle followed by the new
            incomplete candle.

        Raises:
            ValueError: If *timestamp* is not timezone-aware.
            TypeError:  If *timestamp* is not a :class:`datetime`.
        """
        if not isinstance(timestamp, datetime):
            raise TypeError(
                f"timestamp must be a datetime, got {type(timestamp).__name__}"
            )
        if timestamp.tzinfo is None:
            raise ValueError(
                "timestamp must be timezone-aware (UTC).  "
                "Got a naive datetime — wrap it with timezone.utc."
            )

        result: List[Candle] = []

        for tf in self._timeframes:
            key = (instrument, tf)
            boundary = _floor_to_boundary(timestamp, tf)

            if key not in self._state:
                # First tick for this instrument+timeframe — open a new candle.
                self._state[key] = _CandleState(
                    boundary=boundary,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=1.0,
                )
                result.append(self._state[key].to_candle(instrument, tf, complete=False))

            else:
                state = self._state[key]

                if boundary > state.boundary:
                    # Tick crossed into a new period — close the current candle.
                    completed = state.to_candle(instrument, tf, complete=True)
                    result.append(completed)

                    # Open a fresh candle for the new period.
                    self._state[key] = _CandleState(
                        boundary=boundary,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        volume=1.0,
                    )
                    result.append(self._state[key].to_candle(instrument, tf, complete=False))

                else:
                    # Same period — update OHLCV.
                    state.high = max(state.high, price)
                    state.low = min(state.low, price)
                    state.close = price
                    state.volume += 1.0
                    result.append(state.to_candle(instrument, tf, complete=False))

        return result

    def flush(self, instrument: str, timestamp: datetime) -> List[Candle]:
        """Force-close all open candles for *instrument* at *timestamp*.

        Useful for end-of-session cleanup or graceful shutdown.  Each open
        candle is emitted with ``complete=True`` and removed from state.

        Args:
            instrument: Instrument symbol to flush.
            timestamp:  UTC-aware datetime to use as the close time reference.

        Returns:
            List of completed :class:`Candle` objects.
        """
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC).")

        completed: List[Candle] = []
        keys_to_remove = [k for k in self._state if k[0] == instrument]
        for key in keys_to_remove:
            state = self._state.pop(key)
            _, tf = key
            completed.append(state.to_candle(instrument, tf, complete=True))
        return completed
