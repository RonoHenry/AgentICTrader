"""
Tests for market data provider implementations.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from trader.infrastructure.provider_factory import MarketDataProviderFactory
from trader.infrastructure.provider_config import RateLimitConfig
from trader.infrastructure.deriv_api import DerivConfig

@pytest.fixture
def deriv_config():
    """Create a test Deriv API configuration."""
    return DerivConfig(
        app_id="98843",  # Using correct app ID
        endpoint="wss://test.endpoint.com/websockets/v3",
        rate_limit=RateLimitConfig(requests_per_second=10)
    )

@pytest.mark.parametrize("provider_id,config", [
    ("deriv", "deriv_config"),
])
def test_provider_factory(provider_id, config, request):
    """Test provider factory creates correct instances."""
    config = request.getfixturevalue(config)
    provider = MarketDataProviderFactory.create_provider(config)
    assert provider.config.provider_id == provider_id

def test_register_provider():
    """Test registering a new provider."""
    class TestProvider:
        def __init__(self, config):
            self.config = config
    
    class TestConfig:
        provider_id = "test"
    
    MarketDataProviderFactory.register_provider("test", TestProvider, TestConfig)
    assert "test" in MarketDataProviderFactory._providers
    assert MarketDataProviderFactory._providers["test"] == TestProvider
    
def test_unknown_provider():
    """Test error handling for unknown provider."""
    class UnknownConfig:
        provider_id = "unknown"
    
    with pytest.raises(ValueError, match="Unknown provider: unknown"):
        MarketDataProviderFactory.create_provider(UnknownConfig())
