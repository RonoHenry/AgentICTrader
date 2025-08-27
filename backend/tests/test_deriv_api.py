"""
Tests for the Deriv API client implementation.
"""
import pytest
import websockets
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC
from decimal import Decimal
import pytest_asyncio
from websockets.client import WebSocketClientProtocol

from trader.infrastructure.deriv_api import (
    DerivAPIClient,
    APIError
)
from trader.infrastructure.market_data_types import (
    TickData,
    TickHistoryRequest,
    TickHistoryResponse
)

@pytest_asyncio.fixture
async def mock_websocket():
    """Create a mock websocket connection."""
    ws = AsyncMock(spec=WebSocketClientProtocol)
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    ws.closed = False
    return ws

@pytest_asyncio.fixture
async def mock_ws_connect(mock_websocket):
    """Patch websockets.connect."""
    async def mock_connect(*args, **kwargs):
        return mock_websocket

    connect_mock = AsyncMock(side_effect=mock_connect)
    with patch('websockets.connect', new=connect_mock):
        yield mock_websocket

@pytest.mark.asyncio
async def test_api_connection(mock_ws_connect):
    """Test connecting to Deriv API."""
    client = DerivAPIClient(app_id="1234")
    
    mock_ws_connect.recv.return_value = json.dumps({
        "msg_type": "authorize",
        "authorize": {
            "email": "test@example.com",
            "currency": "USD"
        }
    })
    
    await client.connect()
    assert client.is_connected()
    
    # Should send auth message
    assert mock_ws_connect.send.called
    auth_msg = json.loads(mock_ws_connect.send.call_args[0][0])
    assert auth_msg["authorize"] == "1234"

@pytest.mark.asyncio
async def test_api_authorization(mock_ws_connect):
    """Test API authorization flow."""
    mock_ws_connect.recv.return_value = json.dumps({
        "msg_type": "authorize",
        "authorize": {
            "email": "test@example.com",
            "currency": "USD",
            "balance": 1000.0,
            "landing_company_name": "svg"
        }
    })
    
    client = DerivAPIClient(app_id="1234")
    await client.connect()
    auth_response = await client.authorize()
    
    assert auth_response["email"] == "test@example.com"
    assert auth_response["currency"] == "USD"
    
    assert mock_ws_connect.recv.called

@pytest.mark.asyncio
async def test_tick_history_request(mock_ws_connect):
    """Test requesting tick history data."""
    mock_ws_connect.recv.side_effect = [
        # Auth response
        json.dumps({
            "msg_type": "authorize",
            "authorize": {"email": "test@example.com"}
        }),
        # History response
        json.dumps({
            "msg_type": "ticks_history",
            "ticks_history": "R_100",
            "history": {
                "times": [1598918400, 1598918460],
                "prices": [1.1234, 1.1235],
            },
            "pip_size": 4
        })
    ]
    
    client = DerivAPIClient(app_id="1234")
    await client.connect()
    
    request = TickHistoryRequest(
        symbol="R_100",
        start=datetime(2020, 9, 1, tzinfo=UTC),
        end=datetime(2020, 9, 1, 0, 1, tzinfo=UTC),
        style="ticks"
    )
    
    response = await client.get_tick_history(request)
    assert len(response.ticks) == 2
    assert response.ticks[0].timestamp == datetime.fromtimestamp(1598918400, tz=UTC)
    assert response.ticks[0].price == Decimal("1.1234")
    
    assert mock_ws_connect.send.call_count >= 2  # Auth + history request
    last_call = json.loads(mock_ws_connect.send.call_args[0][0])
    assert last_call["ticks_history"] == "R_100"

@pytest.mark.asyncio
async def test_error_handling(mock_ws_connect):
    """Test error handling in API responses."""
    mock_ws_connect.recv.side_effect = [
        # Auth response
        json.dumps({
            "msg_type": "authorize",
            "authorize": {"email": "test@example.com"}
        }),
        # Error response
        json.dumps({
            "msg_type": "error",
            "error": {
                "code": "InvalidSymbol",
                "message": "Invalid symbol"
            }
        })
    ]
    
    client = DerivAPIClient(app_id="1234")
    await client.connect()
    
    request = TickHistoryRequest(
        symbol="INVALID",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        style="ticks"
    )
    
    with pytest.raises(APIError) as exc_info:
        await client.get_tick_history(request)
    
    assert "Invalid symbol" in str(exc_info.value)
    assert mock_ws_connect.send.call_count >= 2  # Auth + history request

@pytest.mark.asyncio
async def test_rate_limiting(mock_ws_connect):
    """Test API rate limiting functionality."""
    mock_ws_connect.recv.side_effect = [
        # Auth response
        json.dumps({
            "msg_type": "authorize",
            "authorize": {"email": "test@example.com"}
        })
    ] + [
        # History responses
        json.dumps({
            "msg_type": "ticks_history",
            "ticks_history": "R_100",
            "history": {"times": [], "prices": []},
            "pip_size": 4
        })
    ] * 3  # Return empty response 3 times
    
    client = DerivAPIClient(app_id="1234", rate_limit_per_second=2)
    await client.connect()
    
    # Should be able to make 2 requests immediately
    request = TickHistoryRequest(
        symbol="R_100",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        style="ticks"
    )
    
    await client.get_tick_history(request)
    await client.get_tick_history(request)
    
    # Third request should be delayed
    import time
    start = time.time()
    await client.get_tick_history(request)
    duration = time.time() - start
    
    assert duration >= 0.5  # Should wait at least 500ms
    assert mock_ws_connect.send.call_count >= 4  # Auth + 3 history requests
