import json
import logging
import time
import asyncio
from datetime import datetime, UTC
from decimal import Decimal
from typing import List, Optional, Dict, Any, AsyncGenerator

import websockets
from websockets.client import WebSocketClientProtocol

from .market_data_types import (
    TickData,
    TickHistoryRequest,
    TickHistoryResponse
)

logger = logging.getLogger(__name__)


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
    def __init__(
        self,
        app_id: str,
        api_token: Optional[str] = None,
        endpoint: str = None,
        rate_limit: Optional[RateLimitConfig] = None
    ):
        self.provider_id = "deriv"
        self.app_id = app_id
        self.api_token = api_token
        self.endpoint = endpoint or "wss://ws.binaryws.com/websockets/v3"
        self.rate_limit = rate_limit or RateLimitConfig()


class DerivAPIClient:
    """Client for interacting with the Deriv API via WebSocket."""

    def __init__(
        self,
        app_id: str,
        endpoint: str = None,
        rate_limit_per_second: int = 2
    ):
        self.app_id = app_id
        self._endpoint = endpoint or f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"
        self.rate_limit = rate_limit_per_second
        self.last_request_time = 0.0
        self._ws: Optional[WebSocketClientProtocol] = None
        self._connect_lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        async with self._connect_lock:
            if not self.is_connected():
                logger.debug(f"Connecting to {self._endpoint}")
                self._ws = await websockets.connect(self._endpoint)
                self._connected = True

    def is_connected(self) -> bool:
        """Check if WebSocket connection is active."""
        return self._ws is not None and self._connected

    async def authorize(self, token: str = None) -> Dict[str, Any]:
        """Authorize with the API.

        Args:
            token: API token. Falls back to app_id if not provided.
        """
        if not self._ws:
            await self.connect()

        auth_token = token or self.app_id
        try:
            response = await self._send_request({"authorize": auth_token})
            return response.get("authorize", {})
        except Exception as e:
            logger.error(f"Authorization failed: {str(e)}")
            self._connected = False
            raise

    async def get_symbols(self) -> List[Dict[str, str]]:
        """Get list of available trading symbols."""
        response = await self._send_request({
            "active_symbols": "brief",
            "product_type": "basic"
        })
        return response.get("active_symbols", [])

    async def get_ohlc(self, symbol: str, interval: int = 60, count: int = 100) -> List[Dict]:
        """Get historical OHLC candles.

        Args:
            symbol: Trading symbol (e.g. 'frxEURUSD')
            interval: Candle interval in seconds (default 60 = M1)
            count: Number of candles to return
        """
        if interval <= 0:
            raise ValueError("Interval must be positive")
        if count <= 0:
            raise ValueError("Count must be positive")

        await self._apply_rate_limit()

        response = await self._send_request({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "granularity": interval,
            "style": "candles"
        })

        candles = response.get("candles", [])
        for candle in candles:
            if not all(k in candle for k in ["open", "high", "low", "close"]):
                raise APIError(code="InvalidData", message="Incomplete OHLC data received")
            if not (float(candle["low"]) <= float(candle["open"]) <= float(candle["high"]) and
                    float(candle["low"]) <= float(candle["close"]) <= float(candle["high"])):
                raise APIError(code="InvalidData", message="OHLC values are inconsistent")
        return candles

    async def subscribe_ticks(self, symbol: str) -> AsyncGenerator[Dict, None]:
        """Subscribe to live price ticks for a symbol."""
        if not self._ws:
            await self.connect()

        await self._ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))
        while True:
            response = json.loads(await self._ws.recv())
            if "error" in response:
                raise APIError(
                    code=response["error"].get("code", "UnknownError"),
                    message=response["error"].get("message", "Unknown error")
                )
            if "tick" in response:
                yield {
                    "price": response["tick"]["quote"],
                    "timestamp": response["tick"]["epoch"]
                }

    async def unsubscribe_ticks(self, symbol: str) -> Dict:
        """Unsubscribe from price ticks."""
        return await self._send_request({"ticks": symbol, "subscribe": 0})

    async def get_tick_history(self, request: TickHistoryRequest) -> TickHistoryResponse:
        """Get historical tick data."""
        if not self.is_connected():
            await self.connect()

        await self._apply_rate_limit()

        response = await self._send_request(request.to_dict())

        # Handle various response formats
        history = response.get("history") or (
            response.get("ticks_history", {}).get("history")
            if isinstance(response.get("ticks_history"), dict) else None
        )

        if not history or "times" not in history or "prices" not in history:
            raise APIError("InvalidResponse", "Invalid or missing history data in response")

        pip_size = response.get("pip_size", 4)
        ticks = [
            TickData(
                symbol=request.symbol,
                timestamp=datetime.fromtimestamp(t, tz=UTC),
                price=Decimal(str(p)),
                pip_size=pip_size
            )
            for t, p in zip(history["times"], history["prices"])
        ]

        return TickHistoryResponse(symbol=request.symbol, ticks=ticks, pip_size=pip_size)

    async def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request and return the response."""
        if not self._ws:
            raise RuntimeError("Not connected. Call connect() first.")

        await self._apply_rate_limit()
        logger.debug(f"Sending: {request}")
        await self._ws.send(json.dumps(request))
        response_data = json.loads(await self._ws.recv())
        logger.debug(f"Received: {response_data}")

        if "error" in response_data:
            raise APIError(
                code=response_data["error"]["code"],
                message=response_data["error"]["message"]
            )
        return response_data

    async def _apply_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        if self.rate_limit <= 0:
            return
        min_interval = 1.0 / self.rate_limit
        wait_time = min_interval - (time.time() - self.last_request_time)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self.last_request_time = time.time()

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._ws = None
                self._connected = False

    # Alias
    disconnect = close
