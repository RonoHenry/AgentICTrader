"""
OANDA v20 WebSocket streaming connector.

Connects to the OANDA v20 streaming pricing API and emits normalised
:class:`TickEvent` objects for each PRICE message received.

Supported instruments (12):
    XAUUSD, EURUSD, GBPUSD, EURAUD, GBPAUD, USDJPY,
    US100, US30, US500, GER40, BTCUSD, ETHUSD

Reconnection:
    Exponential backoff: 1s, 2s, 4s, 8s, 16s … capped at 30s.
    Default max_retries = 5 (6 total attempts: 1 initial + 5 retries).

Validates: Requirements FR-1, Task 3.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import websockets
import websockets.exceptions

from services.market_data.connectors.base import (
    BaseConnector,
    ConnectorError,
    TickCallback,
    TickEvent,
)

__all__ = [
    "OANDAConnector",
    "OANDAConnectorError",
    "SUPPORTED_INSTRUMENTS",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: The 12 instruments supported by this connector.
SUPPORTED_INSTRUMENTS: list[str] = [
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "EURAUD",
    "GBPAUD",
    "USDJPY",
    "US100",
    "US30",
    "US500",
    "GER40",
    "BTCUSD",
    "ETHUSD",
]

# OANDA uses underscore-separated instrument names (e.g. EUR_USD).
# Map from normalised symbol → OANDA symbol.
_OANDA_SYMBOL_MAP: dict[str, str] = {
    "XAUUSD": "XAU_USD",
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "EURAUD": "EUR_AUD",
    "GBPAUD": "GBP_AUD",
    "USDJPY": "USD_JPY",
    "US100":  "NAS100_USD",
    "US30":   "US30_USD",
    "US500":  "SPX500_USD",
    "GER40":  "DE30_EUR",
    "BTCUSD": "BTC_USD",
    "ETHUSD": "ETH_USD",
}

# Reverse map: OANDA symbol → normalised symbol.
_NORMALISED_SYMBOL_MAP: dict[str, str] = {v: k for k, v in _OANDA_SYMBOL_MAP.items()}

_STREAM_URL = (
    "wss://stream-fxtrade.oanda.com/v3/accounts/{account_id}/pricing/stream"
    "?instruments={instruments}"
)

_BACKOFF_BASE = 2          # seconds
_BACKOFF_CAP  = 30         # seconds
_DEFAULT_MAX_RETRIES = 5


# ---------------------------------------------------------------------------
# OANDAConnectorError
# ---------------------------------------------------------------------------

class OANDAConnectorError(ConnectorError):
    """Raised when the OANDA connector exhausts all reconnection retries."""


# ---------------------------------------------------------------------------
# OANDAConnector
# ---------------------------------------------------------------------------

class OANDAConnector(BaseConnector):
    """OANDA v20 WebSocket streaming connector.

    Args:
        account_id:   OANDA account ID (e.g. ``"001-001-1234567-001"``).
        access_token: OANDA API access token.
        on_tick:      Async callback invoked for every normalised tick.
        instruments:  List of normalised instrument symbols to subscribe to.
                      Defaults to all 12 :data:`SUPPORTED_INSTRUMENTS`.
        max_retries:  Maximum number of reconnection attempts (default 5).
    """

    def __init__(
        self,
        account_id: str,
        access_token: str,
        on_tick: Optional[TickCallback] = None,
        instruments: Optional[list[str]] = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        super().__init__(on_tick=on_tick)
        self._account_id = account_id
        self._access_token = access_token
        self._instruments = instruments or SUPPORTED_INSTRUMENTS
        self._max_retries = max_retries
        self._stop_requested = False

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Connect to the OANDA stream and emit tick events.

        Reconnects with exponential backoff on :exc:`ConnectionClosed` or
        :exc:`OSError`.  Raises :exc:`OANDAConnectorError` after
        ``max_retries`` consecutive failures.

        Raises:
            OANDAConnectorError: When max retries are exhausted.
        """
        self._stop_requested = False
        attempt = 0

        while not self._stop_requested:
            try:
                await self._connect_and_stream()
                # Stream ended cleanly — reset retry counter.
                attempt = 0
            except (websockets.exceptions.ConnectionClosed, OSError) as exc:
                if attempt >= self._max_retries:
                    raise OANDAConnectorError(
                        f"OANDA connector failed after {self._max_retries} retries: {exc}"
                    ) from exc

                delay = min(_BACKOFF_BASE ** attempt, _BACKOFF_CAP)
                logger.warning(
                    "OANDA stream disconnected (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, self._max_retries, exc, delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

    async def stop(self) -> None:
        """Signal the connector to stop after the current message."""
        self._stop_requested = True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_url(self) -> str:
        """Build the OANDA streaming URL for the configured instruments."""
        oanda_instruments = ",".join(
            _OANDA_SYMBOL_MAP.get(sym, sym) for sym in self._instruments
        )
        return _STREAM_URL.format(
            account_id=self._account_id,
            instruments=oanda_instruments,
        )

    def _build_headers(self) -> dict[str, str]:
        """Build the HTTP headers for the WebSocket handshake."""
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _connect_and_stream(self) -> None:
        """Open a WebSocket connection and process messages until the stream ends."""
        url = self._build_url()
        headers = self._build_headers()

        async with websockets.connect(url, extra_headers=headers) as ws:
            async for raw_message in ws:
                if self._stop_requested:
                    break
                await self._handle_message(raw_message)

    async def _handle_message(self, raw: str) -> None:
        """Parse a raw WebSocket message and emit a TickEvent if it is a PRICE."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Received non-JSON message: %s", raw[:200])
            return

        msg_type = msg.get("type")

        if msg_type == "HEARTBEAT":
            # Silently ignore heartbeats.
            return

        if msg_type == "PRICE":
            tick = self._parse_price(msg)
            if tick is not None:
                await self._emit(tick)

    def _parse_price(self, msg: dict) -> Optional[TickEvent]:
        """Parse a PRICE message into a :class:`TickEvent`.

        Returns ``None`` if the message is malformed.
        """
        try:
            oanda_instrument = msg["instrument"]
            instrument = _NORMALISED_SYMBOL_MAP.get(oanda_instrument, oanda_instrument)
            # Normalise EUR_USD → EURUSD if not in map
            if "_" in instrument:
                instrument = instrument.replace("_", "")

            bid = float(msg["bids"][0]["price"])
            ask = float(msg["asks"][0]["price"])

            # Parse OANDA timestamp (nanosecond precision ISO-8601)
            raw_time = msg["time"]
            # Truncate nanoseconds to microseconds for Python datetime
            if "." in raw_time:
                base, frac = raw_time.rstrip("Z").split(".", 1)
                frac = frac[:6].ljust(6, "0")
                raw_time = f"{base}.{frac}+00:00"
            else:
                raw_time = raw_time.rstrip("Z") + "+00:00"

            time_utc = datetime.fromisoformat(raw_time)

            return TickEvent(
                instrument=instrument,
                bid=bid,
                ask=ask,
                time_utc=time_utc,
                source="oanda",
            )
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning("Failed to parse PRICE message: %s — %s", msg, exc)
            return None
