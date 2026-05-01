"""
Tests for the OANDA v20 WebSocket streaming connector.

TDD Phase: RED → these tests are written BEFORE the implementation.
Run with:  pytest backend/tests/test_oanda_connector.py -v

All tests in this file must FAIL before any implementation is written.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Import targets — these will raise ImportError until 3b is implemented
# ---------------------------------------------------------------------------
from services.market_data.connectors.base import (
    BaseConnector,
    ConnectorError,
    TickCallback,
    TickEvent,
)
from services.market_data.connectors.oanda import (
    SUPPORTED_INSTRUMENTS,
    OANDAConnector,
    OANDAConnectorError,
)


# ===========================================================================
# Fixtures
# ===========================================================================

FAKE_ACCOUNT_ID = "001-001-1234567-001"
FAKE_ACCESS_TOKEN = "test-access-token-abc123"

SAMPLE_PRICE_MSG = {
    "type": "PRICE",
    "instrument": "EUR_USD",
    "bids": [{"price": "1.08500", "liquidity": 10000000}],
    "asks": [{"price": "1.08510", "liquidity": 10000000}],
    "time": "2024-01-15T10:30:00.000000000Z",
    "tradeable": True,
    "status": "tradeable",
}

SAMPLE_HEARTBEAT_MSG = {
    "type": "HEARTBEAT",
    "time": "2024-01-15T10:30:05.000000000Z",
}


def make_connector(**kwargs) -> OANDAConnector:
    """Return an OANDAConnector with test credentials."""
    defaults = dict(
        account_id=FAKE_ACCOUNT_ID,
        access_token=FAKE_ACCESS_TOKEN,
    )
    defaults.update(kwargs)
    return OANDAConnector(**defaults)


# ===========================================================================
# 1. SUPPORTED_INSTRUMENTS constant
# ===========================================================================

class TestSupportedInstruments:
    """The connector must declare exactly 12 supported instruments."""

    EXPECTED = {
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
    }

    def test_all_12_instruments_present(self):
        assert set(SUPPORTED_INSTRUMENTS) == self.EXPECTED

    def test_exactly_12_instruments(self):
        assert len(SUPPORTED_INSTRUMENTS) == 12


# ===========================================================================
# 2. TickEvent schema
# ===========================================================================

class TestTickEventSchema:
    """TickEvent must have the correct fields and defaults."""

    def test_tick_event_has_required_fields(self):
        tick = TickEvent(
            instrument="EURUSD",
            bid=1.0850,
            ask=1.0851,
            time_utc=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        assert hasattr(tick, "instrument")
        assert hasattr(tick, "bid")
        assert hasattr(tick, "ask")
        assert hasattr(tick, "time_utc")
        assert hasattr(tick, "source")

    def test_source_defaults_to_oanda(self):
        tick = TickEvent(
            instrument="EURUSD",
            bid=1.0850,
            ask=1.0851,
            time_utc=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        assert tick.source == "oanda"

    def test_source_can_be_overridden(self):
        tick = TickEvent(
            instrument="EURUSD",
            bid=1.0850,
            ask=1.0851,
            time_utc=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            source="custom",
        )
        assert tick.source == "custom"

    def test_tick_event_field_types(self):
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        tick = TickEvent(instrument="XAUUSD", bid=2000.5, ask=2001.0, time_utc=now)
        assert isinstance(tick.instrument, str)
        assert isinstance(tick.bid, float)
        assert isinstance(tick.ask, float)
        assert isinstance(tick.time_utc, datetime)
        assert isinstance(tick.source, str)


# ===========================================================================
# 3. PRICE message parsing → TickEvent
# ===========================================================================

class TestPriceMessageParsing:
    """A PRICE message must be parsed into a TickEvent with correct values."""

    @pytest.mark.asyncio
    async def test_price_message_emits_tick_event(self):
        received: list[TickEvent] = []

        async def on_tick(tick: TickEvent) -> None:
            received.append(tick)

        connector = make_connector(on_tick=on_tick)

        ws_mock = AsyncMock()
        ws_mock.__aiter__ = MagicMock(
            return_value=aiter_from_list([json.dumps(SAMPLE_PRICE_MSG)])
        )

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            return_value=async_ctx(ws_mock),
        ):
            await connector.run()

        assert len(received) == 1
        tick = received[0]
        assert tick.instrument == "EURUSD"
        assert tick.bid == pytest.approx(1.08500)
        assert tick.ask == pytest.approx(1.08510)
        assert tick.source == "oanda"
        assert tick.time_utc.tzinfo is not None  # must be timezone-aware

    @pytest.mark.asyncio
    async def test_multiple_price_messages_emit_multiple_ticks(self):
        received: list[TickEvent] = []

        async def on_tick(tick: TickEvent) -> None:
            received.append(tick)

        connector = make_connector(on_tick=on_tick)

        msg2 = {**SAMPLE_PRICE_MSG, "instrument": "XAU_USD",
                "bids": [{"price": "2000.50"}], "asks": [{"price": "2001.00"}]}

        ws_mock = AsyncMock()
        ws_mock.__aiter__ = MagicMock(
            return_value=aiter_from_list([
                json.dumps(SAMPLE_PRICE_MSG),
                json.dumps(msg2),
            ])
        )

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            return_value=async_ctx(ws_mock),
        ):
            await connector.run()

        assert len(received) == 2


# ===========================================================================
# 4. Authorization header
# ===========================================================================

class TestAuthorizationHeader:
    """The connector must send a Bearer token in the Authorization header."""

    @pytest.mark.asyncio
    async def test_authorization_header_sent_on_connect(self):
        connector = make_connector()

        ws_mock = AsyncMock()
        ws_mock.__aiter__ = MagicMock(return_value=aiter_from_list([]))

        connect_kwargs: dict = {}

        async def fake_connect(url, **kwargs):
            connect_kwargs.update(kwargs)
            return async_ctx_obj(ws_mock)

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            side_effect=fake_connect,
        ):
            await connector.run()

        extra_headers = connect_kwargs.get("extra_headers", {})
        # Accept both dict and list-of-tuples formats
        if isinstance(extra_headers, dict):
            auth_value = extra_headers.get("Authorization", "")
        else:
            auth_value = dict(extra_headers).get("Authorization", "")

        assert auth_value == f"Bearer {FAKE_ACCESS_TOKEN}"


# ===========================================================================
# 5. HEARTBEAT handling
# ===========================================================================

class TestHeartbeatHandling:
    """HEARTBEAT messages must be silently ignored — no TickEvent emitted."""

    @pytest.mark.asyncio
    async def test_heartbeat_does_not_emit_tick(self):
        received: list[TickEvent] = []

        async def on_tick(tick: TickEvent) -> None:
            received.append(tick)

        connector = make_connector(on_tick=on_tick)

        ws_mock = AsyncMock()
        ws_mock.__aiter__ = MagicMock(
            return_value=aiter_from_list([json.dumps(SAMPLE_HEARTBEAT_MSG)])
        )

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            return_value=async_ctx(ws_mock),
        ):
            await connector.run()

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_heartbeat_between_prices_does_not_affect_tick_count(self):
        received: list[TickEvent] = []

        async def on_tick(tick: TickEvent) -> None:
            received.append(tick)

        connector = make_connector(on_tick=on_tick)

        ws_mock = AsyncMock()
        ws_mock.__aiter__ = MagicMock(
            return_value=aiter_from_list([
                json.dumps(SAMPLE_PRICE_MSG),
                json.dumps(SAMPLE_HEARTBEAT_MSG),
                json.dumps(SAMPLE_PRICE_MSG),
            ])
        )

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            return_value=async_ctx(ws_mock),
        ):
            await connector.run()

        assert len(received) == 2


# ===========================================================================
# 6. Reconnection on errors
# ===========================================================================

class TestReconnection:
    """The connector must reconnect after transient errors."""

    @pytest.mark.asyncio
    async def test_reconnects_after_connection_closed(self):
        """After a ConnectionClosed, the connector should reconnect and continue."""
        import websockets.exceptions

        received: list[TickEvent] = []

        async def on_tick(tick: TickEvent) -> None:
            received.append(tick)

        connector = make_connector(on_tick=on_tick, max_retries=1)

        call_count = 0

        async def fake_connect(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise websockets.exceptions.ConnectionClosed(None, None)
            ws = AsyncMock()
            ws.__aiter__ = MagicMock(
                return_value=aiter_from_list([json.dumps(SAMPLE_PRICE_MSG)])
            )
            return async_ctx_obj(ws)

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            side_effect=fake_connect,
        ), patch("asyncio.sleep", new_callable=AsyncMock):
            await connector.run()

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_reconnects_after_os_error(self):
        """After an OSError, the connector should reconnect and continue."""
        received: list[TickEvent] = []

        async def on_tick(tick: TickEvent) -> None:
            received.append(tick)

        connector = make_connector(on_tick=on_tick, max_retries=1)

        call_count = 0

        async def fake_connect(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("Network unreachable")
            ws = AsyncMock()
            ws.__aiter__ = MagicMock(
                return_value=aiter_from_list([json.dumps(SAMPLE_PRICE_MSG)])
            )
            return async_ctx_obj(ws)

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            side_effect=fake_connect,
        ), patch("asyncio.sleep", new_callable=AsyncMock):
            await connector.run()

        assert len(received) == 1


# ===========================================================================
# 7. Exponential backoff
# ===========================================================================

class TestExponentialBackoff:
    """Backoff delays must follow the sequence 1, 2, 4, 8, 16 and cap at 30s."""

    @pytest.mark.asyncio
    async def test_backoff_delay_sequence_1_2_4_8_16(self):
        """asyncio.sleep must be called with 1, 2, 4, 8, 16 on successive retries."""
        import websockets.exceptions

        connector = make_connector(max_retries=5)

        async def always_fail(url, **kwargs):
            raise websockets.exceptions.ConnectionClosed(None, None)

        sleep_calls: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            side_effect=always_fail,
        ), patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(OANDAConnectorError):
                await connector.run()

        assert sleep_calls == [1, 2, 4, 8, 16]

    @pytest.mark.asyncio
    async def test_backoff_capped_at_30s(self):
        """Backoff delay must never exceed 30 seconds."""
        import websockets.exceptions

        # Use a connector with many retries to force delays past 30s
        connector = make_connector(max_retries=10)

        async def always_fail(url, **kwargs):
            raise websockets.exceptions.ConnectionClosed(None, None)

        sleep_calls: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            side_effect=always_fail,
        ), patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(OANDAConnectorError):
                await connector.run()

        assert all(d <= 30 for d in sleep_calls), (
            f"Some delays exceeded 30s: {sleep_calls}"
        )

    @pytest.mark.asyncio
    async def test_asyncio_sleep_called_with_correct_backoff_delays(self):
        """asyncio.sleep must be called with the exact computed backoff values."""
        import websockets.exceptions

        connector = make_connector(max_retries=3)

        async def always_fail(url, **kwargs):
            raise websockets.exceptions.ConnectionClosed(None, None)

        sleep_mock = AsyncMock()

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            side_effect=always_fail,
        ), patch("asyncio.sleep", sleep_mock):
            with pytest.raises(OANDAConnectorError):
                await connector.run()

        # 3 retries → delays 1, 2, 4
        assert sleep_mock.call_count == 3
        assert sleep_mock.call_args_list == [call(1), call(2), call(4)]


# ===========================================================================
# 8. Max retries exhausted
# ===========================================================================

class TestMaxRetriesExhausted:
    """After max_retries, OANDAConnectorError must be raised."""

    @pytest.mark.asyncio
    async def test_raises_oanda_connector_error_after_max_retries(self):
        import websockets.exceptions

        connector = make_connector(max_retries=5)

        async def always_fail(url, **kwargs):
            raise websockets.exceptions.ConnectionClosed(None, None)

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            side_effect=always_fail,
        ), patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OANDAConnectorError):
                await connector.run()

    @pytest.mark.asyncio
    async def test_exactly_6_connection_attempts_before_error(self):
        """1 initial attempt + 5 retries = 6 total calls to websockets.connect."""
        import websockets.exceptions

        connector = make_connector(max_retries=5)

        connect_call_count = 0

        async def always_fail(url, **kwargs):
            nonlocal connect_call_count
            connect_call_count += 1
            raise websockets.exceptions.ConnectionClosed(None, None)

        with patch(
            "services.market_data.connectors.oanda.websockets.connect",
            side_effect=always_fail,
        ), patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OANDAConnectorError):
                await connector.run()

        assert connect_call_count == 6  # 1 initial + 5 retries


# ===========================================================================
# Async test helpers
# ===========================================================================

def aiter_from_list(items: list[str]):
    """Return an async iterator that yields items then stops."""
    async def _gen():
        for item in items:
            yield item
    return _gen()


def async_ctx(ws_mock):
    """Return an async context manager that yields ws_mock."""
    class _Ctx:
        async def __aenter__(self):
            return ws_mock
        async def __aexit__(self, *args):
            pass
    return _Ctx()


def async_ctx_obj(ws_mock):
    """Return an object that acts as both context manager and the ws itself."""
    class _Ctx:
        async def __aenter__(self):
            return ws_mock
        async def __aexit__(self, *args):
            pass
        def __aiter__(self):
            return ws_mock.__aiter__()
    return _Ctx()
