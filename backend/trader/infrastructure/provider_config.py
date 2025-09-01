"""
Base configuration for market data providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass
class MarketDataProviderConfig(ABC):
    """Abstract base class for provider configurations."""
    
    provider_id: str
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary format."""
        return {"provider_id": self.provider_id}
    
    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MarketDataProviderConfig':
        """Create configuration from dictionary format."""
        pass
    
    @classmethod
    @abstractmethod
    def from_env(cls) -> 'MarketDataProviderConfig':
        """Create configuration from environment variables."""
        pass
        
@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_second: int = 2
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "requests_per_second": self.requests_per_second,
            "requests_per_minute": self.requests_per_minute,
            "requests_per_hour": self.requests_per_hour
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RateLimitConfig':
        """Create from dictionary format."""
        return cls(
            requests_per_second=data.get("requests_per_second", 2),
            requests_per_minute=data.get("requests_per_minute"),
            requests_per_hour=data.get("requests_per_hour")
        )
