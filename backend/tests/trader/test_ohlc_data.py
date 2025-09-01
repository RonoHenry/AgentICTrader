import pytest
import asyncio
import websockets
from unittest.mock import MagicMock, patch, AsyncMock
from trader.infrastructure.deriv_api import DerivAPIClient, APIError

@pytest.fixture
def mock_websocket():
    websocket = AsyncMock()
    websocket.recv = AsyncMock()
    websocket.send = AsyncMock()
    return websocket

@pytest.fixture
async def api_client(mock_websocket):
    client = DerivAPIClient("app_id")
    client.websocket = mock_websocket
    client._authorized = True
    return client

@pytest.mark.asyncio
async def test_get_ohlc_valid_data(api_client, mock_websocket):
    # Setup mock response with valid OHLC data
    mock_websocket.recv.return_value = """
    {
        "candles": [
            {
                "epoch": 1234567890,
                "open": "1.1000",
                "high": "1.1200",
                "low": "1.0800",
                "close": "1.1100"
            }
        ]
    }
    """
    
    # Call get_ohlc
    candles = await api_client.get_ohlc("frxEURUSD", interval=60, count=1)
    
    # Verify request
    mock_websocket.send.assert_called_once()
    sent_request = eval(mock_websocket.send.call_args[0][0])
    assert sent_request["ticks_history"] == "frxEURUSD"
    assert sent_request["granularity"] == 60
    assert sent_request["count"] == 1
    assert sent_request["style"] == "candles"
    
    # Verify response processing
    assert len(candles) == 1
    assert float(candles[0]["open"]) == 1.1000
    assert float(candles[0]["high"]) == 1.1200
    assert float(candles[0]["low"]) == 1.0800
    assert float(candles[0]["close"]) == 1.1100

@pytest.mark.asyncio
async def test_get_ohlc_invalid_data(api_client, mock_websocket):
    # Setup mock response with invalid OHLC data (missing close)
    mock_websocket.recv.return_value = """
    {
        "candles": [
            {
                "epoch": 1234567890,
                "open": "1.1000",
                "high": "1.1200",
                "low": "1.0800"
            }
        ]
    }
    """
    
    # Verify that invalid data raises error
    with pytest.raises(APIError) as excinfo:
        await api_client.get_ohlc("frxEURUSD")
    assert "Incomplete OHLC data" in str(excinfo.value)

@pytest.mark.asyncio
async def test_get_ohlc_inconsistent_values(api_client, mock_websocket):
    # Setup mock response with inconsistent OHLC data (high < low)
    mock_websocket.recv.return_value = """
    {
        "candles": [
            {
                "epoch": 1234567890,
                "open": "1.1000",
                "high": "1.0800",  
                "low": "1.1200",   
                "close": "1.1100"
            }
        ]
    }
    """
    
    # Verify that inconsistent data raises error
    with pytest.raises(APIError) as excinfo:
        await api_client.get_ohlc("frxEURUSD")
    assert "OHLC values are inconsistent" in str(excinfo.value)

@pytest.mark.asyncio
async def test_get_ohlc_connection_retry(api_client, mock_websocket):
    # Setup mock websocket that will be used after reconnect
    new_websocket = AsyncMock()
    new_websocket.recv = AsyncMock(return_value="""
    {
        "candles": [
            {
                "epoch": 1234567890,
                "open": "1.1000",
                "high": "1.1200",
                "low": "1.0800",
                "close": "1.1100"
            }
        ]
    }
    """)
    new_websocket.send = AsyncMock()

    # Make the first websocket fail
    mock_websocket.recv.side_effect = websockets.exceptions.ConnectionClosed(None, None)
    
    # Mock websockets.connect to be awaitable and return our new mock
    async def async_connect(*args, **kwargs):
        return new_websocket
        
    # Mock the connect function
    with patch('trader.infrastructure.deriv_api.websockets.connect', side_effect=async_connect):
        # Call should succeed after retry
        candles = await api_client.get_ohlc("frxEURUSD")
        assert len(candles) == 1

@pytest.mark.asyncio
async def test_get_ohlc_api_error(api_client, mock_websocket):
    # Setup mock response with API error
    mock_websocket.recv.return_value = """
    {
        "error": {
            "code": "InvalidSymbol",
            "message": "Invalid symbol provided"
        }
    }
    """
    
    # Verify that API error is raised
    with pytest.raises(APIError) as excinfo:
        await api_client.get_ohlc("INVALID")
    assert "Invalid symbol" in str(excinfo.value)
