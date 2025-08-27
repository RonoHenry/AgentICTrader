"""
Common data types for market data handling.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

@dataclass
class TickData:
    """Represents a single price tick."""
    symbol: str
    timestamp: datetime
    price: Decimal
    pip_size: int = 4
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "symbol": self.symbol,
            "timestamp": int(self.timestamp.timestamp()),
            "price": str(self.price),
            "pip_size": self.pip_size
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TickData':
        """Create from dictionary format."""
        return cls(
            symbol=data["symbol"],
            timestamp=datetime.fromtimestamp(data["timestamp"], tz=datetime.timezone.utc),
            price=Decimal(data["price"]),
            pip_size=data.get("pip_size", 4)
        )

@dataclass
class TickHistoryRequest:
    """Request parameters for tick history."""
    symbol: str
    start: datetime
    end: datetime
    style: str = "ticks"  # or "candles"
    count: Optional[int] = None
    adjust_start_time: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API request format."""
        return {
            "ticks_history": self.symbol,
            "start": int(self.start.timestamp()),
            "end": int(self.end.timestamp()),
            "style": self.style,
            **({"count": self.count} if self.count else {}),
            "adjust_start_time": int(self.adjust_start_time)
        }

@dataclass
class TickHistoryResponse:
    """Response containing tick history data."""
    symbol: str
    ticks: List[TickData]
    pip_size: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "symbol": self.symbol,
            "ticks": [tick.to_dict() for tick in self.ticks],
            "pip_size": self.pip_size
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TickHistoryResponse':
        """Create from dictionary format."""
        return cls(
            symbol=data["symbol"],
            ticks=[TickData.from_dict(tick) for tick in data["ticks"]],
            pip_size=data["pip_size"]
        )
