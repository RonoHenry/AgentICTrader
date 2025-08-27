"""
Deriv API client implementation for market data access.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, UTC
from decimal import Decimal
from typing import List, Optional, Dict, Any

import websockets
from websockets.client import WebSocketClientProtocol

from .market_data_types import (
    TickData,
    TickHistoryRequest,
    TickHistoryResponse
)

logger = logging.getLogger(__name__)

class APIError(Exception):
    """Raised when the API returns an error response."""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

class DerivAPIClient:
    """Client for interacting with the Deriv API."""
    
    def __init__(
        self,
        app_id: str,
        endpoint: str = "wss://ws.binaryws.com/websockets/v3",
        rate_limit_per_second: int = 2
    ):
        self.app_id = app_id
        self.endpoint = endpoint
        self.rate_limit = rate_limit_per_second
        self.last_request_time = 0
        self._ws: Optional[WebSocketClientProtocol] = None
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        async with self._connect_lock:
            if not self.is_connected():
                self._ws = await websockets.connect(self.endpoint)
                await self._authorize()

    def is_connected(self) -> bool:
        """Check if WebSocket connection is active."""
        return self._ws is not None and not self._ws.closed

    async def _authorize(self) -> None:
        """Send authorization request."""
        await self._send_request({"authorize": self.app_id})

    async def authorize(self) -> Dict[str, Any]:
        """Authorize and get account info."""
        if not self.is_connected():
            await self.connect()
        response = await self._send_request({"authorize": self.app_id})
        return response["authorize"]

    async def get_tick_history(self, request: TickHistoryRequest) -> TickHistoryResponse:
        """Get historical tick data."""
        if not self.is_connected():
            await self.connect()
            
        # Apply rate limiting
        await self._apply_rate_limit()
        
        response = await self._send_request(request.to_dict())
        
        if "error" in response:
            raise APIError(response["error"]["code"], response["error"]["message"])
            
        history = response["history"]
        pip_size = response.get("pip_size", 4)
        
        ticks = []
        for time_val, price in zip(history["times"], history["prices"]):
            tick = TickData(
                symbol=request.symbol,
                timestamp=datetime.fromtimestamp(time_val, tz=UTC),
                price=Decimal(str(price)),
                pip_size=pip_size
            )
            ticks.append(tick)
            
        return TickHistoryResponse(
            symbol=request.symbol,
            ticks=ticks,
            pip_size=pip_size
        )

    async def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send request and get response."""
        if not self._ws:
            raise RuntimeError("Not connected")
            
        await self._ws.send(json.dumps(request))
        response = await self._ws.recv()
        return json.loads(response)
        
    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        if self.rate_limit <= 0:
            return
            
        current_time = time.time()
        min_interval = 1.0 / self.rate_limit
        
        wait_time = min_interval - (current_time - self.last_request_time)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
            
        self.last_request_time = time.time()

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None
