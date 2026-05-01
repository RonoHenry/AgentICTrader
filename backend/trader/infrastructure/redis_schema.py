"""
Redis key schema and cache implementation for AgentICTrader market data.

Key patterns:
  candle:{instrument}:{timeframe}   → latest OHLCV          (TTL 65s)
  htf:{instrument}:{timeframe}      → HTF projection levels  (TTL 300s)
  sentiment:{instrument}            → FinBERT score          (TTL 900s)
  agent:state:{user_id}             → agent state snapshot   (TTL 3600s)
  risk:exposure:{user_id}           → risk exposure snapshot (TTL 60s)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL constants (seconds)
# ---------------------------------------------------------------------------

TTL_CANDLE: int = 65        # slightly longer than M1 candle duration
TTL_HTF: int = 300          # 5 minutes — HTF candles change slowly
TTL_SENTIMENT: int = 900    # 15 minutes — FinBERT scores
TTL_AGENT_STATE: int = 3600 # 1 hour — agent state snapshot
TTL_RISK_EXPOSURE: int = 60 # 1 minute — risk exposure snapshot


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------

def candle_key(instrument: str, timeframe: str) -> str:
    """Return the Redis key for the latest OHLCV candle.

    Args:
        instrument: e.g. "EURUSD"
        timeframe:  e.g. "M1"

    Returns:
        "candle:EURUSD:M1"
    """
    return f"candle:{instrument}:{timeframe}"


def htf_key(instrument: str, timeframe: str) -> str:
    """Return the Redis key for the latest HTF projection levels.

    Args:
        instrument: e.g. "EURUSD"
        timeframe:  e.g. "H1"

    Returns:
        "htf:EURUSD:H1"
    """
    return f"htf:{instrument}:{timeframe}"


def sentiment_key(instrument: str) -> str:
    """Return the Redis key for the latest FinBERT sentiment score.

    Args:
        instrument: e.g. "EURUSD"

    Returns:
        "sentiment:EURUSD"
    """
    return f"sentiment:{instrument}"


def agent_state_key(user_id: str) -> str:
    """Return the Redis key for an agent state snapshot.

    Args:
        user_id: e.g. "user_42"

    Returns:
        "agent:state:user_42"
    """
    return f"agent:state:{user_id}"


def risk_exposure_key(user_id: str) -> str:
    """Return the Redis key for a risk exposure snapshot.

    Args:
        user_id: e.g. "user_42"

    Returns:
        "risk:exposure:user_42"
    """
    return f"risk:exposure:{user_id}"


# ---------------------------------------------------------------------------
# RedisCache
# ---------------------------------------------------------------------------

@dataclass
class RedisConfig:
    """Connection configuration for Redis."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    decode_responses: bool = True


class RedisCache:
    """Async Redis cache with typed get/set/delete helpers.

    All values are JSON-serialised so callers work with plain Python dicts
    and primitives rather than raw byte strings.

    Usage::

        cache = RedisCache(RedisConfig(host="redis"))
        await cache.connect()

        await cache.set(candle_key("EURUSD", "M1"), ohlcv_dict, ttl=TTL_CANDLE)
        data = await cache.get(candle_key("EURUSD", "M1"))
        await cache.delete(candle_key("EURUSD", "M1"))

        await cache.close()
    """

    def __init__(self, config: Optional[RedisConfig] = None) -> None:
        self._config = config or RedisConfig()
        self._client: Optional[aioredis.Redis] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create the async Redis connection pool."""
        self._client = aioredis.Redis(
            host=self._config.host,
            port=self._config.port,
            db=self._config.db,
            password=self._config.password,
            decode_responses=self._config.decode_responses,
        )
        # Verify connectivity eagerly so callers get a clear error on startup.
        await self._client.ping()
        logger.info(
            "RedisCache connected to %s:%s db=%s",
            self._config.host,
            self._config.port,
            self._config.db,
        )

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("RedisCache connection closed")

    # ------------------------------------------------------------------
    # Core typed operations
    # ------------------------------------------------------------------

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Serialise *value* to JSON and store it under *key* with *ttl* seconds.

        Args:
            key:   Redis key string.
            value: Any JSON-serialisable Python object.
            ttl:   Expiry in seconds (must be > 0).

        Raises:
            ValueError: if ttl is not a positive integer.
            RuntimeError: if the cache is not connected.
        """
        if ttl <= 0:
            raise ValueError(f"TTL must be a positive integer, got {ttl!r}")
        self._require_connected()
        serialised = json.dumps(value)
        await self._client.set(key, serialised, ex=ttl)
        logger.debug("SET %s (ttl=%ss)", key, ttl)

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve and deserialise the value stored at *key*.

        Args:
            key: Redis key string.

        Returns:
            Deserialised Python object, or ``None`` if the key does not exist
            or has expired.

        Raises:
            RuntimeError: if the cache is not connected.
        """
        self._require_connected()
        raw = await self._client.get(key)
        if raw is None:
            logger.debug("GET %s → miss", key)
            return None
        logger.debug("GET %s → hit", key)
        return json.loads(raw)

    async def delete(self, key: str) -> bool:
        """Delete *key* from Redis.

        Args:
            key: Redis key string.

        Returns:
            ``True`` if the key existed and was deleted, ``False`` otherwise.

        Raises:
            RuntimeError: if the cache is not connected.
        """
        self._require_connected()
        deleted = await self._client.delete(key)
        logger.debug("DEL %s → %s", key, "deleted" if deleted else "not found")
        return bool(deleted)

    async def ttl(self, key: str) -> int:
        """Return the remaining TTL (in seconds) for *key*.

        Returns:
            Remaining seconds, ``-2`` if the key does not exist, or ``-1`` if
            the key exists but has no expiry.

        Raises:
            RuntimeError: if the cache is not connected.
        """
        self._require_connected()
        return await self._client.ttl(key)

    async def exists(self, key: str) -> bool:
        """Return ``True`` if *key* exists in Redis.

        Raises:
            RuntimeError: if the cache is not connected.
        """
        self._require_connected()
        return bool(await self._client.exists(key))

    # ------------------------------------------------------------------
    # Domain-specific convenience helpers
    # ------------------------------------------------------------------

    async def set_candle(self, instrument: str, timeframe: str, ohlcv: dict) -> None:
        """Store the latest OHLCV candle for *instrument*/*timeframe*."""
        await self.set(candle_key(instrument, timeframe), ohlcv, TTL_CANDLE)

    async def get_candle(self, instrument: str, timeframe: str) -> Optional[dict]:
        """Retrieve the latest OHLCV candle for *instrument*/*timeframe*."""
        return await self.get(candle_key(instrument, timeframe))

    async def set_htf(self, instrument: str, timeframe: str, projection: dict) -> None:
        """Store the latest HTF projection levels for *instrument*/*timeframe*."""
        await self.set(htf_key(instrument, timeframe), projection, TTL_HTF)

    async def get_htf(self, instrument: str, timeframe: str) -> Optional[dict]:
        """Retrieve the latest HTF projection levels for *instrument*/*timeframe*."""
        return await self.get(htf_key(instrument, timeframe))

    async def set_sentiment(self, instrument: str, score: dict) -> None:
        """Store the latest FinBERT sentiment score for *instrument*."""
        await self.set(sentiment_key(instrument), score, TTL_SENTIMENT)

    async def get_sentiment(self, instrument: str) -> Optional[dict]:
        """Retrieve the latest FinBERT sentiment score for *instrument*."""
        return await self.get(sentiment_key(instrument))

    async def set_agent_state(self, user_id: str, state: dict) -> None:
        """Store the agent state snapshot for *user_id*."""
        await self.set(agent_state_key(user_id), state, TTL_AGENT_STATE)

    async def get_agent_state(self, user_id: str) -> Optional[dict]:
        """Retrieve the agent state snapshot for *user_id*."""
        return await self.get(agent_state_key(user_id))

    async def set_risk_exposure(self, user_id: str, exposure: dict) -> None:
        """Store the risk exposure snapshot for *user_id*."""
        await self.set(risk_exposure_key(user_id), exposure, TTL_RISK_EXPOSURE)

    async def get_risk_exposure(self, user_id: str) -> Optional[dict]:
        """Retrieve the risk exposure snapshot for *user_id*."""
        return await self.get(risk_exposure_key(user_id))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if self._client is None:
            raise RuntimeError(
                "RedisCache is not connected. Call await cache.connect() first."
            )
