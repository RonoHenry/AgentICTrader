"""
AlgoRAG Service Configuration
Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field


@dataclass
class QdrantConfig:
    host: str = field(default_factory=lambda: os.getenv("QDRANT_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("QDRANT_PORT", "6333")))
    collection: str = field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "trading_setups"))
    timeout: float = field(default_factory=lambda: float(os.getenv("QDRANT_TIMEOUT", "5.0")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("QDRANT_MAX_RETRIES", "3")))
    retry_backoff: float = field(default_factory=lambda: float(os.getenv("QDRANT_RETRY_BACKOFF", "0.5")))


@dataclass
class ServiceConfig:
    port: int = field(default_factory=lambda: int(os.getenv("SERVICE_PORT", "8003")))
    version: str = field(default_factory=lambda: os.getenv("SERVICE_VERSION", "0.1.0"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


@dataclass
class Settings:
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)


# Singleton settings instance
settings = Settings()
