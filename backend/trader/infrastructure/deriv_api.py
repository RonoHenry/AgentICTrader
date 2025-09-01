import json
import asyncio
import websockets
import ssl
import certifi
import time
from typing import Optional, Dict, Any, List

class APIError(Exception):
    """Base class for API related errors"""
    def __init__(self, code: str = None, message: str = None):
        self.code = code
        self.message = message
        super().__init__(message or code)

class RateLimitConfig:
    """Configuration for API rate limiting"""
    def __init__(self, requests_per_second: float = 1.0):
        self.requests_per_second = requests_per_second
        self.interval = 1.0 / requests_per_second if requests_per_second > 0 else 0
        self.last_request_time = 0.0

class DerivConfig:
    def __init__(self, app_id: str, api_token: Optional[str] = None, endpoint: str = None, rate_limit: Optional[RateLimitConfig] = None):
        self.provider_id = "deriv"  # Required by MarketDataProviderFactory
        self.app_id = app_id
        self.api_token = api_token
        self.endpoint = endpoint or "wss://ws.binaryws.com/websockets/v3"
        self.rate_limit = rate_limit or RateLimitConfig()

class DerivAPIClient:
    def __init__(self, app_id: str = None, api_token: str = None, config: DerivConfig = None, rate_limit_per_second: float = None):
        if config is None:
            config = DerivConfig(app_id=app_id, api_token=api_token)
        if rate_limit_per_second is not None:
            config.rate_limit = RateLimitConfig(requests_per_second=rate_limit_per_second)
        self.config = config
        self.websocket = None
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())

    async def connect(self):
        """Connect to Deriv WebSocket API"""
        self.websocket = await websockets.connect(
            self.config.endpoint,
            ssl=self._ssl_context
        )

        # Send authorize request with app_id
        auth_request = {
            "authorize": self.config.app_id
        }
        await self.websocket.send(json.dumps(auth_request))

    async def authenticate(self) -> Dict[str, Any]:
        """Authenticate with the API using app_id and token"""
        auth_request = {
            "authorize": self.config.api_token,
            "app_id": self.config.app_id,
        }
        await self.websocket.send(json.dumps(auth_request))
        return json.loads(await self.websocket.recv())

    async def get_available_symbols(self) -> List[Dict[str, str]]:
        """Get list of available trading symbols"""
        await self.websocket.send(json.dumps({"active_symbols": "brief", "product_type": "basic"}))
        response = json.loads(await self.websocket.recv())
        return response.get("active_symbols", [])

    async def subscribe_ticks(self, symbol: str):
        """Subscribe to price ticks for a symbol"""
        subscribe_request = {
            "ticks": symbol,
            "subscribe": 1
        }
        await self.websocket.send(json.dumps(subscribe_request))
        while True:
            response = json.loads(await self.websocket.recv())
            if "tick" in response:
                yield {
                    "price": response["tick"]["quote"],
                    "timestamp": response["tick"]["epoch"]
                }

    async def unsubscribe_ticks(self, symbol: str):
        """Unsubscribe from price ticks"""
        unsubscribe_request = {
            "ticks": symbol,
            "subscribe": 0
        }
        await self.websocket.send(json.dumps(unsubscribe_request))
        response = json.loads(await self.websocket.recv())
        return response

    async def close(self):
        """Close the WebSocket connection"""
        if self.websocket:
            await self.websocket.close()
            
    def is_connected(self):
        """Check if the websocket connection is established"""
        return self.websocket is not None and not self.websocket.closed

    @property
    def endpoint(self):
        """Get the WebSocket endpoint"""
        return self.config.endpoint

    async def authorize(self):
        """Authorize with the API"""
        if not self.config.api_token:
            return None
        auth_request = {
            "authorize": self.config.api_token,
            "app_id": self.config.app_id
        }
        await self.websocket.send(json.dumps(auth_request))
        response = json.loads(await self.websocket.recv())
        if "error" in response:
            error = response["error"]
            raise APIError(
                code=error.get("code", "UnknownError"),
                message=error.get("message", "An unknown error occurred")
            )
        return response["authorize"]

    async def get_symbols(self):
        """Get list of available trading symbols"""
        request = {
            "active_symbols": "brief",
            "product_type": "basic"
        }
        await self.websocket.send(json.dumps(request))
        response = json.loads(await self.websocket.recv())
        if "error" in response:
            error = response["error"]
            raise APIError(
                code=error.get("code", "UnknownError"),
                message=error.get("message", "An unknown error occurred")
            )
        return response.get("active_symbols", [])

    async def _apply_rate_limiting(self):
        """Apply rate limiting before making a request"""
        if not self.config.rate_limit:
            return

        current_time = time.time()
        if self.config.rate_limit.last_request_time > 0:
            elapsed = current_time - self.config.rate_limit.last_request_time
            delay = self.config.rate_limit.interval - elapsed
            if delay > 0:
                await asyncio.sleep(delay)

        self.config.rate_limit.last_request_time = time.time()

    async def _reconnect(self):
        """Reconnect to the WebSocket and reauthorize"""
        try:
            await self.close()
            await self.connect()
        except Exception as e:
            raise APIError(code="ReconnectFailed", message=f"Failed to reconnect: {str(e)}")

    async def _handle_connection_error(self, func):
        """Handle connection errors with retry"""
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                return await func()
            except websockets.exceptions.ConnectionClosed:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    await self._reconnect()
                else:
                    raise APIError(code="ConnectionFailed", 
                                 message="Failed to maintain connection after retries")

    async def get_ohlc(self, symbol: str, interval: int = 60, count: int = 100):
        """Get historical OHLC candles
        
        Args:
            symbol: The trading symbol (e.g. 'frxEURUSD')
            interval: Candle interval in seconds (default 60 = 1 minute)
            count: Number of candles to return (default 100)
        """
        await self._apply_rate_limiting()

        # Validate inputs
        if interval <= 0:
            raise ValueError("Interval must be positive")
        if count <= 0:
            raise ValueError("Count must be positive")

        request = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "granularity": interval,
            "style": "candles"
        }

        async def fetch_ohlc():
            await self.websocket.send(json.dumps(request))
            while True:
                response = json.loads(await self.websocket.recv())
                if "error" in response:
                    error = response["error"]
                    raise APIError(code=error.get("code", "UnknownError"),
                                message=error.get("message", "An unknown error occurred"))
                if "candles" in response:
                    candles = response["candles"]
                    # Validate OHLC data
                    for candle in candles:
                        if not all(k in candle for k in ["open", "high", "low", "close"]):
                            raise APIError(code="InvalidData", 
                                        message="Incomplete OHLC data received")
                        if not (float(candle["low"]) <= float(candle["open"]) <= float(candle["high"]) and
                               float(candle["low"]) <= float(candle["close"]) <= float(candle["high"])):
                            raise APIError(code="InvalidData",
                                        message="OHLC values are inconsistent")
                    return candles
        
        return await self._handle_connection_error(fetch_ohlc)

    async def get_tick_history(self, request):
        """Get historical tick data"""
        if not self.is_connected():
            await self.connect()

        await self._apply_rate_limiting()
        
        history_request = {
            "ticks_history": request.symbol,
            "start": int(request.start.timestamp()),
            "end": int(request.end.timestamp()),
            "style": request.style,
            "adjust_start_time": 1
        }
        await self.websocket.send(json.dumps(history_request))

        # Keep reading responses until we get a history response
        while True:
            response = json.loads(await self.websocket.recv())
            print("Response:", json.dumps(response, indent=2))
            if response.get("msg_type") == "history" or "history" in response:
                break
            elif "error" in response:
                error = response["error"]
                raise APIError(code=error.get("code", "UnknownError"),
                             message=error.get("message", "An unknown error occurred"))

        # Capture the actual history data
        history = response.get("history", {})
        print("History:", json.dumps(history, indent=2))
            
        if not history:
            raise APIError(code="NoData", message="No history data received")
        
        from datetime import datetime, timezone
        from decimal import Decimal
        
        from trader.infrastructure.market_data_types import TickData, TickHistoryResponse
        
        # Build tick data
        times = history.get("times", [])
        prices = history.get("prices", [])
        print(f"Times: {times}")
        print(f"Prices: {prices}")
        
        ticks = []
        for time, price in zip(times, prices):
            tick = TickData(
                symbol=request.symbol,
                timestamp=datetime.fromtimestamp(time, tz=timezone.utc),
                price=Decimal(str(price))
            )
            ticks.append(tick)
            print(f"Created tick: {tick}")
            
        response_obj = TickHistoryResponse(
            symbol=request.symbol,
            ticks=ticks,
            pip_size=response.get("pip_size", 4)
        )
        print(f"Response object: {response_obj}")
        return response_obj

    disconnect = close  # Alias for compatibility
