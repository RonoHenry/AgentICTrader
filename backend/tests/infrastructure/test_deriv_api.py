"""
Tests for the Deriv API client implementation.
"""
import asyncio
import json
from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from websockets.exceptions import WebSocketException

from trader.infrastructure.deriv_api import (
    DerivAPIClient,
    DerivConfig,
    APIError,
    RateLimitConfig
)
from trader.infrastructure.market_data_types import (
    TickData,
    TickHistoryRequest,
    TickHistoryResponse
)

@pytest.fixture
def config():
    """Create test configuration."""
    return DerivConfig(
        app_id="98843",  # Using correct app ID
        endpoint="wss://test.endpoint.com/websockets/v3",
        rate_limit=RateLimitConfig(requests_per_second=10)
    )

@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    mock = Mock()
    mock.closed = False
    
    async def mock_send(msg):
        return None
        
    async def mock_recv():
        return json.dumps({"authorize": {"loginid": "CR12345"}})
        
    async def mock_close():
        mock.closed = True
        return None
        
    mock.send = AsyncMock(side_effect=mock_send)
    mock.recv = AsyncMock(side_effect=mock_recv)
    mock.close = AsyncMock(side_effect=mock_close)
    
    return mock

@pytest.fixture
def mock_connect(mock_websocket):
    """Mock websockets.connect."""
    async def mock_connect_impl(*args, **kwargs):
        return mock_websocket
        
    connect_mock = AsyncMock(side_effect=mock_connect_impl)
    with patch('websockets.connect', connect_mock):
        yield connect_mock

@pytest.fixture
async def api_client(mock_connect):
    """Create test client instance."""
    return DerivAPIClient(app_id="98843")  # Using correct app ID

@pytest.mark.asyncio
async def test_connect_and_authorize(api_client, mock_websocket, mock_connect):
    """Test connection establishment and authorization."""
    mock_websocket.recv.return_value = json.dumps({"authorize": {"loginid": "CR12345"}})
    
    # Connect to WebSocket
    await api_client.connect()
    
    # Verify connection was established
    assert api_client.is_connected()
    mock_connect.assert_called_once_with(api_client.endpoint, ssl=api_client._ssl_context)
    
    # Verify authorization request was sent
    mock_websocket.send.assert_called_with(json.dumps({"authorize": "98843"}))

@pytest.mark.asyncio
async def test_get_tick_history(api_client, mock_websocket, mock_connect):
    """Test fetching historical tick data."""
    # Setup mock responses for connect() and get_tick_history()
    mock_websocket.recv.side_effect = [
        json.dumps({"authorize": {"loginid": "CR12345"}}),  # Authorization response
        json.dumps({  # Tick history response
            "history": {
                "times": [1735689600, 1735689601],
                "prices": [1.23456, 1.23457]
            },
            "pip_size": 4,
            "msg_type": "history"
        })
    ]
    
    # Create request
    request = TickHistoryRequest(
        symbol="frxEURUSD",
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 2, tzinfo=UTC)
    )
    
    # Get tick history
    response = await api_client.get_tick_history(request)
    
    # Verify response
    assert isinstance(response, TickHistoryResponse)
    assert len(response.ticks) == 2
    assert response.pip_size == 4
    
    # Verify request format
    calls = mock_websocket.send.call_args_list
    assert len(calls) == 2  # Auth request + history request
    history_request = json.loads(calls[1][0][0])
    expected_request = request.to_dict()
    assert all(history_request[k] == v for k, v in expected_request.items())

@pytest.mark.asyncio
async def test_rate_limiting(api_client, mock_websocket, mock_connect):
    """Test API rate limiting."""
    # Setup mock responses
    auth_response = {"authorize": {"loginid": "CR12345"}}
    history_response = {
        "history": {
            "times": [1735689600],
            "prices": [1.23456]
        },
        "pip_size": 4
    }
    mock_websocket.recv.side_effect = [
        json.dumps(auth_response),
        json.dumps(history_response),
        json.dumps(history_response),
        json.dumps(history_response)
    ]
    
    request = TickHistoryRequest(
        symbol="frxEURUSD",
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 2, tzinfo=UTC)
    )
    
    # Make multiple requests
    start_time = asyncio.get_event_loop().time()
    for _ in range(3):
        await api_client.get_tick_history(request)
    elapsed = asyncio.get_event_loop().time() - start_time
    
    # With rate_limit=10/sec, 3 requests should take at least 0.2 seconds
    assert elapsed >= 0.2

@pytest.mark.asyncio
async def test_api_error_handling(api_client, mock_websocket, mock_connect):
    """Test handling of API errors."""
    # Setup mock responses
    mock_websocket.recv.side_effect = [
        json.dumps({"authorize": {"loginid": "CR12345"}}),
        json.dumps({
            "error": {
                "code": "InvalidSymbol",
                "message": "Invalid symbol provided"
            }
        })
    ]
    
    request = TickHistoryRequest(
        symbol="INVALID",
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end=datetime(2025, 1, 2, tzinfo=UTC)
    )
    
    with pytest.raises(APIError) as exc_info:
        await api_client.get_tick_history(request)
        
    assert exc_info.value.code == "InvalidSymbol"
    assert "Invalid symbol provided" in str(exc_info.value)

@pytest.mark.asyncio
async def test_close_connection(api_client, mock_websocket, mock_connect):
    """Test closing WebSocket connection."""
    # Setup connection
    mock_websocket.recv.return_value = json.dumps({"authorize": {"loginid": "CR12345"}})
    await api_client.connect()
    
    # Close connection
    await api_client.close()
    
    # Verify connection was closed
    mock_websocket.close.assert_called_once()
    assert not api_client.is_connected()
