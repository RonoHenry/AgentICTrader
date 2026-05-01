"""
Market-data broker connectors.

All connectors implement :class:`BaseConnector` and emit :class:`TickEvent`
objects via an ``on_tick`` callback.

Available connectors
--------------------
- :class:`OANDAConnector` — OANDA v20 WebSocket streaming API

Adding a new connector
----------------------
1. Create ``services/market-data/connectors/<broker>.py``
2. Subclass :class:`BaseConnector`
3. Implement ``run()`` and ``stop()``
4. Emit :class:`TickEvent` objects (set ``source`` to your broker name)
5. Export from this ``__init__.py``
"""
from .base import BaseConnector, ConnectorError, TickCallback, TickEvent
from .oanda import OANDAConnector, OANDAConnectorError, SUPPORTED_INSTRUMENTS

__all__ = [
    # Base interface
    "BaseConnector",
    "ConnectorError",
    "TickCallback",
    "TickEvent",
    # OANDA connector
    "OANDAConnector",
    "OANDAConnectorError",
    "SUPPORTED_INSTRUMENTS",
]
