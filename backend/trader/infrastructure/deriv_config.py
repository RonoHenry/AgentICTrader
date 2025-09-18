"""
Configuration settings for Deriv API.
"""
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class DerivConfig:
    """Configuration for Deriv API."""
    app_id: str
    endpoint: str = "wss://ws.binaryws.com/websockets/v3"
    rate_limit_per_second: int = 2
    
    @classmethod
    def from_env(cls) -> 'DerivConfig':
        """Create config from environment variables."""
        app_id = os.getenv("DERIV_APP_ID")
        if not app_id:
            raise ValueError("DERIV_APP_ID environment variable not set")
            
        endpoint = os.getenv("DERIV_API_ENDPOINT", cls.endpoint)
        rate_limit = int(os.getenv("DERIV_RATE_LIMIT", "2"))
        
        return cls(
            app_id=app_id,
            endpoint=endpoint,
            rate_limit_per_second=rate_limit
        )
