"""
Tests for broker execution tools (OANDA v20 REST API).

TDD Phase: RED → these tests are written BEFORE the implementation.
Run with:  pytest backend/tests/test_broker_tools.py -v

All tests in this file must FAIL before any implementation is written.

Validates: Requirements FR-6 (Agentic Execution Loop), Task 37.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import targets — these will raise ImportError until 37b is implemented
# ---------------------------------------------------------------------------
from agent.broker_tools import (
    BrokerError,
    OANDABrokerClient,
    place_order,
    set_sl_tp,
    close_position,
    get_position_status,
)


# ===========================================================================
# Fixtures
# ===========================================================================

FAKE_ACCOUNT_ID = "001-001-1234567-001"
FAKE_ACCESS_TOKEN = "test-access-token-abc123"
FAKE_API_URL = "https://api-fxtrade.oanda.com"


@pytest.fixture
def broker_client():
    """Return an OANDABrokerClient with test credentials."""
    return OANDABrokerClient(
        account_id=FAKE_ACCOUNT_ID,
        access_token=FAKE_ACCESS_TOKEN,
        api_url=FAKE_API_URL,
    )


@pytest.fixture
def sample_order():
    """Return a sample order dict for testing."""
    return {
        "instrument": "EURUSD",
        "direction": "LONG",
        "entry": 1.0850,
        "stop_loss": 1.0800,
        "take_profit": 1.0950,
        "size": 0.01,
        "setup_id": "test-setup-123",
    }


# ===========================================================================
# 1. place_order returns order_id on success
# ===========================================================================

class TestPlaceOrder:
    """place_order must return order_id on successful OANDA API response."""

    @pytest.mark.asyncio
    async def test_place_order_returns_order_id_on_success(
        self, broker_client, sample_order
    ):
        """When OANDA API returns success, place_order returns order_id."""
        mock_response = {
            "orderCreateTransaction": {
                "id": "12345",
                "type": "MARKET_ORDER",
                "instrument": "EUR_USD",
            },
            "orderFillTransaction": {
                "id": "12346",
                "tradeOpened": {
                    "tradeID": "67890",
                },
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            result = await place_order(broker_client, sample_order)

        assert "order_id" in result
        assert result["order_id"] == "12345"

    @pytest.mark.asyncio
    async def test_place_order_returns_trade_id_on_success(
        self, broker_client, sample_order
    ):
        """When OANDA API returns success, place_order returns trade_id."""
        mock_response = {
            "orderCreateTransaction": {
                "id": "12345",
            },
            "orderFillTransaction": {
                "id": "12346",
                "tradeOpened": {
                    "tradeID": "67890",
                },
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            result = await place_order(broker_client, sample_order)

        assert "trade_id" in result
        assert result["trade_id"] == "67890"

    @pytest.mark.asyncio
    async def test_place_order_normalizes_instrument_symbol(
        self, broker_client, sample_order
    ):
        """EURUSD should be sent to OANDA as EUR_USD."""
        mock_response = {
            "orderCreateTransaction": {"id": "12345"},
            "orderFillTransaction": {
                "id": "12346",
                "tradeOpened": {"tradeID": "67890"},
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            await place_order(broker_client, sample_order)

        # Verify the request was made with EUR_USD format
        call_args = mock_request.call_args
        request_data = call_args[1]["json"]
        assert "order" in request_data
        assert request_data["order"]["instrument"] == "EUR_USD"

    @pytest.mark.asyncio
    async def test_place_order_sends_correct_direction(
        self, broker_client, sample_order
    ):
        """Direction LONG/SHORT should map to positive/negative units."""
        mock_response = {
            "orderCreateTransaction": {"id": "12345"},
            "orderFillTransaction": {
                "id": "12346",
                "tradeOpened": {"tradeID": "67890"},
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            # Test LONG
            await place_order(broker_client, sample_order)
            call_args = mock_request.call_args
            units = int(call_args[1]["json"]["order"]["units"])
            assert units > 0

            # Test SHORT
            short_order = {**sample_order, "direction": "SHORT"}
            await place_order(broker_client, short_order)
            call_args = mock_request.call_args
            units = int(call_args[1]["json"]["order"]["units"])
            assert units < 0


# ===========================================================================
# 2. set_sl_tp returns True on success
# ===========================================================================

class TestSetSlTp:
    """set_sl_tp must return True on successful SL/TP update."""

    @pytest.mark.asyncio
    async def test_set_sl_tp_returns_true_on_success(self, broker_client):
        """When OANDA API successfully updates SL/TP, return True."""
        trade_id = "67890"
        sl_price = 1.0800
        tp_price = 1.0950

        mock_response = {
            "orderCreateTransaction": {
                "id": "12347",
                "type": "STOP_LOSS_ORDER",
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            result = await set_sl_tp(broker_client, trade_id, sl_price, tp_price)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_sl_tp_sends_correct_payload(self, broker_client):
        """set_sl_tp should send correct SL and TP prices to OANDA API."""
        trade_id = "67890"
        sl_price = 1.0800
        tp_price = 1.0950

        mock_response = {
            "orderCreateTransaction": {
                "id": "12347",
                "type": "STOP_LOSS_ORDER",
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            await set_sl_tp(broker_client, trade_id, sl_price, tp_price)

        # Verify correct endpoint and payload
        call_args = mock_request.call_args
        assert f"/trades/{trade_id}/orders" in call_args[0][0]


# ===========================================================================
# 3. close_position returns True on success
# ===========================================================================

class TestClosePosition:
    """close_position must return True on successful position close."""

    @pytest.mark.asyncio
    async def test_close_position_returns_true_on_success(self, broker_client):
        """When OANDA API closes the trade, return True."""
        trade_id = "67890"

        mock_response = {
            "orderCreateTransaction": {
                "id": "12348",
                "type": "MARKET_ORDER",
            },
            "orderFillTransaction": {
                "id": "12349",
                "tradesClosed": [{"tradeID": trade_id}],
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            result = await close_position(broker_client, trade_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_close_position_sends_close_request(self, broker_client):
        """close_position should send a PUT request to close the trade."""
        trade_id = "67890"

        mock_response = {
            "orderFillTransaction": {
                "tradesClosed": [{"tradeID": trade_id}],
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            await close_position(broker_client, trade_id)

        # Verify correct endpoint and method
        call_args = mock_request.call_args
        # endpoint is the first positional arg
        assert f"/trades/{trade_id}/close" in call_args[0][0]
        # method may be positional or keyword
        method_value = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("method", "")
        assert method_value == "PUT"


# ===========================================================================
# 4. get_position_status returns correct data
# ===========================================================================

class TestGetPositionStatus:
    """get_position_status must return {status, unrealised_pnl, current_price}."""

    @pytest.mark.asyncio
    async def test_get_position_status_returns_correct_fields(self, broker_client):
        """get_position_status should return status, unrealised_pnl, current_price."""
        trade_id = "67890"

        mock_response = {
            "trade": {
                "id": trade_id,
                "state": "OPEN",
                "unrealizedPL": "15.50",
                "price": "1.0870",
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            result = await get_position_status(broker_client, trade_id)

        assert "status" in result
        assert "unrealised_pnl" in result
        assert "current_price" in result
        assert result["status"] == "OPEN"
        assert result["unrealised_pnl"] == 15.50
        assert result["current_price"] == 1.0870

    @pytest.mark.asyncio
    async def test_get_position_status_sends_get_request(self, broker_client):
        """get_position_status should send a GET request to fetch trade details."""
        trade_id = "67890"

        mock_response = {
            "trade": {
                "id": trade_id,
                "state": "OPEN",
                "unrealizedPL": "0.00",
                "price": "1.0850",
            },
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            await get_position_status(broker_client, trade_id)

        # Verify correct endpoint and method
        call_args = mock_request.call_args
        # endpoint is the first positional arg
        assert f"/trades/{trade_id}" in call_args[0][0]
        # method may be positional or keyword
        method_value = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("method", "")
        assert method_value == "GET"


# ===========================================================================
# 5. place_order raises BrokerError on API failure
# ===========================================================================

class TestBrokerError:
    """place_order must raise BrokerError when OANDA API fails."""

    @pytest.mark.asyncio
    async def test_place_order_raises_broker_error_on_api_failure(
        self, broker_client, sample_order
    ):
        """When OANDA API returns an error, raise BrokerError."""
        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = Exception("API connection failed")

            with pytest.raises(BrokerError) as exc_info:
                await place_order(broker_client, sample_order)

            assert "API connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_place_order_raises_broker_error_on_http_error(
        self, broker_client, sample_order
    ):
        """When OANDA API returns HTTP error, raise BrokerError."""
        mock_response = {
            "errorMessage": "Insufficient margin",
        }

        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(BrokerError) as exc_info:
                await place_order(broker_client, sample_order)

            assert "Insufficient margin" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_sl_tp_raises_broker_error_on_api_failure(self, broker_client):
        """When set_sl_tp API call fails, raise BrokerError."""
        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = Exception("Network timeout")

            with pytest.raises(BrokerError):
                await set_sl_tp(broker_client, "67890", 1.0800, 1.0950)

    @pytest.mark.asyncio
    async def test_close_position_raises_broker_error_on_api_failure(
        self, broker_client
    ):
        """When close_position API call fails, raise BrokerError."""
        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = Exception("Trade not found")

            with pytest.raises(BrokerError):
                await close_position(broker_client, "67890")

    @pytest.mark.asyncio
    async def test_get_position_status_raises_broker_error_on_api_failure(
        self, broker_client
    ):
        """When get_position_status API call fails, raise BrokerError."""
        with patch.object(
            broker_client, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = Exception("Authorization failed")

            with pytest.raises(BrokerError):
                await get_position_status(broker_client, "67890")


# ===========================================================================
# 6. OANDABrokerClient instantiation
# ===========================================================================

class TestOANDABrokerClient:
    """Test the OANDABrokerClient class instantiation."""

    def test_broker_client_accepts_credentials(self):
        """OANDABrokerClient should accept account_id and access_token."""
        client = OANDABrokerClient(
            account_id=FAKE_ACCOUNT_ID,
            access_token=FAKE_ACCESS_TOKEN,
        )
        assert client.account_id == FAKE_ACCOUNT_ID
        assert client.access_token == FAKE_ACCESS_TOKEN

    def test_broker_client_has_default_api_url(self):
        """OANDABrokerClient should have a default production API URL."""
        client = OANDABrokerClient(
            account_id=FAKE_ACCOUNT_ID,
            access_token=FAKE_ACCESS_TOKEN,
        )
        assert client.api_url == "https://api-fxtrade.oanda.com"

    def test_broker_client_accepts_custom_api_url(self):
        """OANDABrokerClient should accept a custom API URL (for practice)."""
        practice_url = "https://api-fxpractice.oanda.com"
        client = OANDABrokerClient(
            account_id=FAKE_ACCOUNT_ID,
            access_token=FAKE_ACCESS_TOKEN,
            api_url=practice_url,
        )
        assert client.api_url == practice_url
