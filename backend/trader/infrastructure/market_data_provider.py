"""
Abstract base class for market data providers.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, AsyncIterator, Optional

from .market_data_types import (
    TickData,
    TickHistoryRequest,
    TickHistoryResponse
)

class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the provider."""
        pass
        
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the provider."""
        pass
        
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if provider is connected."""
        pass
        
    @abstractmethod
    async def get_tick_history(self, request: TickHistoryRequest) -> TickHistoryResponse:
        """Get historical tick data."""
        pass
        
    @abstractmethod
    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[TickData]:
        """Subscribe to real-time tick data for a symbol."""
        pass
        
    @abstractmethod
    async def unsubscribe_ticks(self, symbol: str) -> None:
        """Unsubscribe from real-time tick data for a symbol."""
        pass
        
    @abstractmethod
    async def get_symbols(self) -> List[Dict[str, Any]]:
        """Get list of available trading symbols."""
        pass
        
    @abstractmethod
    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a symbol."""
        pass
