"""
Base connector interface for broker WebSocket streaming APIs.

All broker connectors must subclass :class:`BaseConnector` and implement
:meth:`run` and :meth:`stop`.  They emit :class:`TickEvent` objects via
the ``on_tick`` callback.

Validates: Requirements FR-1 (real-time market data ingestion).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Optional

__all__ = [
    "BaseConnector",
    "ConnectorError",
    "TickCallback",
    "TickEvent",
]


# ---------------------------------------------------------------------------
# TickEvent
# ---------------------------------------------------------------------------

@dataclass
class TickEvent:
    """Normalised tick event emitted by every connector.

    Attributes:
        instrument: Normalised instrument symbol, e.g. ``"EURUSD"``.
        bid:        Best bid price.
        ask:        Best ask price.
        time_utc:   UTC-aware timestamp of the tick.
        source:     Originating broker/feed name (default ``"oanda"``).
    """

    instrument: str
    bid: float
    ask: float
    time_utc: datetime
    source: str = "oanda"


# ---------------------------------------------------------------------------
# Type alias for the tick callback
# ---------------------------------------------------------------------------

#: Async callable that receives a :class:`TickEvent`.
TickCallback = Callable[[TickEvent], Awaitable[None]]


# ---------------------------------------------------------------------------
# ConnectorError
# ---------------------------------------------------------------------------

class ConnectorError(Exception):
    """Base exception for all connector errors."""


# ---------------------------------------------------------------------------
# BaseConnector ABC
# ---------------------------------------------------------------------------

class BaseConnector(abc.ABC):
    """Abstract base class for all broker WebSocket connectors.

    Subclasses must implement :meth:`run` and :meth:`stop`.

    Args:
        on_tick: Async callback invoked for every normalised tick.
    """

    def __init__(self, on_tick: Optional[TickCallback] = None) -> None:
        self._on_tick: Optional[TickCallback] = on_tick

    @abc.abstractmethod
    async def run(self) -> None:
        """Connect to the broker stream and emit tick events.

        This method should run until the stream ends or :meth:`stop` is called.
        Implementations must handle reconnection with exponential backoff.

        Raises:
            ConnectorError: When max retries are exhausted.
        """

    @abc.abstractmethod
    async def stop(self) -> None:
        """Signal the connector to stop and clean up resources."""

    async def _emit(self, tick: TickEvent) -> None:
        """Invoke the on_tick callback if one is registered."""
        if self._on_tick is not None:
            await self._on_tick(tick)
