"""
Factory for creating market data providers.
"""
from typing import Dict, Type

from .market_data_provider import MarketDataProvider
from .provider_config import MarketDataProviderConfig
from .deriv_api import DerivAPIClient, DerivConfig

class MarketDataProviderFactory:
    """Factory for creating market data providers."""
    
    _providers: Dict[str, Type[MarketDataProvider]] = {}
    _configs: Dict[str, Type[MarketDataProviderConfig]] = {}
    
    @classmethod
    def register_provider(
        cls,
        provider_id: str,
        provider_class: Type[MarketDataProvider],
        config_class: Type[MarketDataProviderConfig]
    ) -> None:
        """Register a new market data provider."""
        cls._providers[provider_id] = provider_class
        cls._configs[provider_id] = config_class
    
    @classmethod
    def create_provider(cls, config: MarketDataProviderConfig) -> MarketDataProvider:
        """Create a market data provider instance."""
        provider_class = cls._providers.get(config.provider_id)
        if not provider_class:
            raise ValueError(f"Unknown provider: {config.provider_id}")
            
        return provider_class(config)
    
    @classmethod
    def create_config(cls, provider_id: str, **kwargs) -> MarketDataProviderConfig:
        """Create a provider configuration."""
        config_class = cls._configs.get(provider_id)
        if not config_class:
            raise ValueError(f"Unknown provider: {provider_id}")
            
        return config_class(**kwargs)

# Register the Deriv provider
MarketDataProviderFactory.register_provider("deriv", DerivAPIClient, DerivConfig)
