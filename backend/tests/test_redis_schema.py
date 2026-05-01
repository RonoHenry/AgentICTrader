"""
Unit tests for backend/trader/infrastructure/redis_schema.py.

All tests use fakeredis so no real Redis instance is required.

Coverage:
  - Key pattern builders for every key type
  - TTL constants have the correct values
  - RedisCache.set / get / delete / ttl / exists
  - TTL is enforced (key expires after the configured duration)
  - get returns None for missing / expired keys
  - delete returns True/False correctly
  - Domain-specific helpers (set_candle, get_candle, set_htf, …)
  - RuntimeError raised when cache is not connected
  - ValueError raised for non-positive TTL
"""
from __future__ import annotations

import asyncio
import json
import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from trader.infrastructure.redis_schema import (
    # Key builders
    candle_key,
    htf_key,
    sentiment_key,
    agent_state_key,
    risk_exposure_key,
    # TTL constants
    TTL_CANDLE,
    TTL_HTF,
    TTL_SENTIMENT,
    TTL_AGENT_STATE,
    TTL_RISK_EXPOSURE,
    # Cache class
    RedisCache,
    RedisConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_cache() -> RedisCache:
    """Return a RedisCache backed by an in-process fakeredis server."""
    cache = RedisCache.__new__(RedisCache)
    cache._config = RedisConfig()
    cache._client = fakeredis.FakeRedis(decode_responses=True)
    return cache


# ---------------------------------------------------------------------------
# Key pattern tests
# ---------------------------------------------------------------------------

class TestKeyBuilders:
    def test_candle_key_format(self):
        assert candle_key("EURUSD", "M1") == "candle:EURUSD:M1"

    def test_candle_key_different_timeframes(self):
        for tf in ("M5", "M15", "H1", "H4", "D1", "W1"):
            key = candle_key("GBPUSD", tf)
            assert key.startswith("candle:")
            assert "GBPUSD" in key
            assert tf in key

    def test_htf_key_format(self):
        assert htf_key("EURUSD", "H1") == "htf:EURUSD:H1"

    def test_htf_key_different_instruments(self):
        for inst in ("EURUSD", "GBPUSD", "US500", "US30", "XAUUSD"):
            key = htf_key(inst, "H4")
            assert key.startswith("htf:")
            assert inst in key

    def test_sentiment_key_format(self):
        assert sentiment_key("EURUSD") == "sentiment:EURUSD"

    def test_sentiment_key_all_instruments(self):
        for inst in ("EURUSD", "GBPUSD", "US500", "US30", "XAUUSD"):
            assert sentiment_key(inst) == f"sentiment:{inst}"

    def test_agent_state_key_format(self):
        assert agent_state_key("user_42") == "agent:state:user_42"

    def test_agent_state_key_different_users(self):
        for uid in ("user_1", "user_abc", "42"):
            key = agent_state_key(uid)
            assert key.startswith("agent:state:")
            assert uid in key

    def test_risk_exposure_key_format(self):
        assert risk_exposure_key("user_42") == "risk:exposure:user_42"

    def test_risk_exposure_key_different_users(self):
        for uid in ("user_1", "user_abc", "42"):
            key = risk_exposure_key(uid)
            assert key.startswith("risk:exposure:")
            assert uid in key

    def test_all_key_patterns_are_distinct(self):
        """Different key types for the same instrument must not collide."""
        instrument = "EURUSD"
        timeframe = "M1"
        user_id = "EURUSD"  # deliberately reuse instrument string as user_id

        keys = [
            candle_key(instrument, timeframe),
            htf_key(instrument, timeframe),
            sentiment_key(instrument),
            agent_state_key(user_id),
            risk_exposure_key(user_id),
        ]
        assert len(keys) == len(set(keys)), "Key patterns must be unique"


# ---------------------------------------------------------------------------
# TTL constant tests
# ---------------------------------------------------------------------------

class TestTTLConstants:
    def test_candle_ttl(self):
        assert TTL_CANDLE == 65

    def test_htf_ttl(self):
        assert TTL_HTF == 300

    def test_sentiment_ttl(self):
        assert TTL_SENTIMENT == 900

    def test_agent_state_ttl(self):
        assert TTL_AGENT_STATE == 3600

    def test_risk_exposure_ttl(self):
        assert TTL_RISK_EXPOSURE == 60

    def test_all_ttls_are_positive(self):
        for ttl in (TTL_CANDLE, TTL_HTF, TTL_SENTIMENT, TTL_AGENT_STATE, TTL_RISK_EXPOSURE):
            assert ttl > 0

    def test_ttl_ordering(self):
        """Sanity-check that TTLs reflect the intended freshness hierarchy."""
        assert TTL_RISK_EXPOSURE < TTL_CANDLE < TTL_HTF < TTL_SENTIMENT < TTL_AGENT_STATE


# ---------------------------------------------------------------------------
# RedisCache core operation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRedisCacheCore:
    async def test_set_and_get_dict(self):
        cache = await _make_cache()
        payload = {"open": 1.1000, "high": 1.1050, "low": 1.0980, "close": 1.1020, "volume": 100}
        await cache.set("test:key", payload, ttl=60)
        result = await cache.get("test:key")
        assert result == payload

    async def test_get_missing_key_returns_none(self):
        cache = await _make_cache()
        result = await cache.get("nonexistent:key")
        assert result is None

    async def test_set_overwrites_existing_value(self):
        cache = await _make_cache()
        await cache.set("test:key", {"v": 1}, ttl=60)
        await cache.set("test:key", {"v": 2}, ttl=60)
        result = await cache.get("test:key")
        assert result == {"v": 2}

    async def test_delete_existing_key_returns_true(self):
        cache = await _make_cache()
        await cache.set("test:key", {"v": 1}, ttl=60)
        deleted = await cache.delete("test:key")
        assert deleted is True

    async def test_delete_missing_key_returns_false(self):
        cache = await _make_cache()
        deleted = await cache.delete("nonexistent:key")
        assert deleted is False

    async def test_get_after_delete_returns_none(self):
        cache = await _make_cache()
        await cache.set("test:key", {"v": 1}, ttl=60)
        await cache.delete("test:key")
        result = await cache.get("test:key")
        assert result is None

    async def test_exists_true_for_present_key(self):
        cache = await _make_cache()
        await cache.set("test:key", {"v": 1}, ttl=60)
        assert await cache.exists("test:key") is True

    async def test_exists_false_for_missing_key(self):
        cache = await _make_cache()
        assert await cache.exists("nonexistent:key") is False

    async def test_set_various_json_types(self):
        cache = await _make_cache()
        for value in (42, 3.14, "hello", [1, 2, 3], {"nested": {"a": 1}}, True, None):
            await cache.set("test:type", value, ttl=60)
            assert await cache.get("test:type") == value

    async def test_invalid_ttl_raises_value_error(self):
        cache = await _make_cache()
        with pytest.raises(ValueError):
            await cache.set("test:key", {}, ttl=0)

    async def test_negative_ttl_raises_value_error(self):
        cache = await _make_cache()
        with pytest.raises(ValueError):
            await cache.set("test:key", {}, ttl=-1)

    async def test_not_connected_raises_runtime_error_on_get(self):
        cache = RedisCache()  # _client is None
        with pytest.raises(RuntimeError, match="not connected"):
            await cache.get("any:key")

    async def test_not_connected_raises_runtime_error_on_set(self):
        cache = RedisCache()
        with pytest.raises(RuntimeError, match="not connected"):
            await cache.set("any:key", {}, ttl=60)

    async def test_not_connected_raises_runtime_error_on_delete(self):
        cache = RedisCache()
        with pytest.raises(RuntimeError, match="not connected"):
            await cache.delete("any:key")


# ---------------------------------------------------------------------------
# TTL enforcement tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTTLEnforcement:
    async def test_ttl_is_set_on_key(self):
        """After set(), the remaining TTL should be close to the requested value."""
        cache = await _make_cache()
        await cache.set("test:ttl", {"v": 1}, ttl=120)
        remaining = await cache.ttl("test:ttl")
        # fakeredis returns the exact TTL; allow a 2-second window for slow CI
        assert 118 <= remaining <= 120

    async def test_ttl_for_missing_key_returns_minus_two(self):
        cache = await _make_cache()
        remaining = await cache.ttl("nonexistent:key")
        assert remaining == -2

    async def test_key_expires_after_ttl(self):
        """Key must not be retrievable after its TTL has elapsed.

        Uses a 1-second TTL and a short asyncio.sleep to let fakeredis
        expire the key naturally — no real Redis required.
        """
        cache = await _make_cache()
        await cache.set("test:expire", {"v": 1}, ttl=1)

        # Confirm the key is present before expiry.
        assert await cache.get("test:expire") == {"v": 1}

        # Wait just past the TTL boundary.
        await asyncio.sleep(1.1)

        result = await cache.get("test:expire")
        assert result is None


# ---------------------------------------------------------------------------
# Domain-specific helper tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDomainHelpers:
    # --- Candle helpers ---

    async def test_set_and_get_candle(self):
        cache = await _make_cache()
        ohlcv = {"open": 1.10, "high": 1.11, "low": 1.09, "close": 1.105, "volume": 500}
        await cache.set_candle("EURUSD", "M1", ohlcv)
        result = await cache.get_candle("EURUSD", "M1")
        assert result == ohlcv

    async def test_candle_uses_correct_ttl(self):
        cache = await _make_cache()
        await cache.set_candle("EURUSD", "M1", {"open": 1.10})
        remaining = await cache.ttl(candle_key("EURUSD", "M1"))
        assert TTL_CANDLE - 2 <= remaining <= TTL_CANDLE

    async def test_get_candle_missing_returns_none(self):
        cache = await _make_cache()
        assert await cache.get_candle("EURUSD", "M1") is None

    async def test_candle_keys_are_isolated_by_instrument(self):
        cache = await _make_cache()
        await cache.set_candle("EURUSD", "M1", {"close": 1.10})
        await cache.set_candle("GBPUSD", "M1", {"close": 1.25})
        assert (await cache.get_candle("EURUSD", "M1"))["close"] == 1.10
        assert (await cache.get_candle("GBPUSD", "M1"))["close"] == 1.25

    async def test_candle_keys_are_isolated_by_timeframe(self):
        cache = await _make_cache()
        await cache.set_candle("EURUSD", "M1", {"close": 1.10})
        await cache.set_candle("EURUSD", "H1", {"close": 1.12})
        assert (await cache.get_candle("EURUSD", "M1"))["close"] == 1.10
        assert (await cache.get_candle("EURUSD", "H1"))["close"] == 1.12

    # --- HTF helpers ---

    async def test_set_and_get_htf(self):
        cache = await _make_cache()
        projection = {
            "htf_open": 1.10, "htf_high": 1.12, "htf_low": 1.08,
            "open_bias": "BULLISH", "htf_high_proximity_pct": 33.3,
        }
        await cache.set_htf("EURUSD", "H1", projection)
        result = await cache.get_htf("EURUSD", "H1")
        assert result == projection

    async def test_htf_uses_correct_ttl(self):
        cache = await _make_cache()
        await cache.set_htf("EURUSD", "H1", {"htf_open": 1.10})
        remaining = await cache.ttl(htf_key("EURUSD", "H1"))
        assert TTL_HTF - 2 <= remaining <= TTL_HTF

    async def test_get_htf_missing_returns_none(self):
        cache = await _make_cache()
        assert await cache.get_htf("EURUSD", "H1") is None

    async def test_htf_keys_isolated_by_timeframe(self):
        cache = await _make_cache()
        await cache.set_htf("EURUSD", "H1", {"htf_open": 1.10})
        await cache.set_htf("EURUSD", "H4", {"htf_open": 1.15})
        assert (await cache.get_htf("EURUSD", "H1"))["htf_open"] == 1.10
        assert (await cache.get_htf("EURUSD", "H4"))["htf_open"] == 1.15

    # --- Sentiment helpers ---

    async def test_set_and_get_sentiment(self):
        cache = await _make_cache()
        score = {"score": 0.72, "direction": "bullish", "freshness_seconds": 120}
        await cache.set_sentiment("EURUSD", score)
        result = await cache.get_sentiment("EURUSD")
        assert result == score

    async def test_sentiment_uses_correct_ttl(self):
        cache = await _make_cache()
        await cache.set_sentiment("EURUSD", {"score": 0.5})
        remaining = await cache.ttl(sentiment_key("EURUSD"))
        assert TTL_SENTIMENT - 2 <= remaining <= TTL_SENTIMENT

    async def test_get_sentiment_missing_returns_none(self):
        cache = await _make_cache()
        assert await cache.get_sentiment("EURUSD") is None

    async def test_sentiment_keys_isolated_by_instrument(self):
        cache = await _make_cache()
        await cache.set_sentiment("EURUSD", {"score": 0.8})
        await cache.set_sentiment("XAUUSD", {"score": -0.3})
        assert (await cache.get_sentiment("EURUSD"))["score"] == 0.8
        assert (await cache.get_sentiment("XAUUSD"))["score"] == -0.3

    # --- Agent state helpers ---

    async def test_set_and_get_agent_state(self):
        cache = await _make_cache()
        state = {"instrument": "EURUSD", "confidence_score": 0.82, "mode": "HUMAN_IN_LOOP"}
        await cache.set_agent_state("user_1", state)
        result = await cache.get_agent_state("user_1")
        assert result == state

    async def test_agent_state_uses_correct_ttl(self):
        cache = await _make_cache()
        await cache.set_agent_state("user_1", {"mode": "AUTONOMOUS"})
        remaining = await cache.ttl(agent_state_key("user_1"))
        assert TTL_AGENT_STATE - 2 <= remaining <= TTL_AGENT_STATE

    async def test_get_agent_state_missing_returns_none(self):
        cache = await _make_cache()
        assert await cache.get_agent_state("user_99") is None

    async def test_agent_state_keys_isolated_by_user(self):
        cache = await _make_cache()
        await cache.set_agent_state("user_1", {"mode": "HUMAN_IN_LOOP"})
        await cache.set_agent_state("user_2", {"mode": "AUTONOMOUS"})
        assert (await cache.get_agent_state("user_1"))["mode"] == "HUMAN_IN_LOOP"
        assert (await cache.get_agent_state("user_2"))["mode"] == "AUTONOMOUS"

    # --- Risk exposure helpers ---

    async def test_set_and_get_risk_exposure(self):
        cache = await _make_cache()
        exposure = {"daily_dd_pct": 1.2, "weekly_dd_pct": 2.5, "open_trades": 1, "equity": 10000.0}
        await cache.set_risk_exposure("user_1", exposure)
        result = await cache.get_risk_exposure("user_1")
        assert result == exposure

    async def test_risk_exposure_uses_correct_ttl(self):
        cache = await _make_cache()
        await cache.set_risk_exposure("user_1", {"equity": 10000.0})
        remaining = await cache.ttl(risk_exposure_key("user_1"))
        assert TTL_RISK_EXPOSURE - 2 <= remaining <= TTL_RISK_EXPOSURE

    async def test_get_risk_exposure_missing_returns_none(self):
        cache = await _make_cache()
        assert await cache.get_risk_exposure("user_99") is None

    async def test_risk_exposure_keys_isolated_by_user(self):
        cache = await _make_cache()
        await cache.set_risk_exposure("user_1", {"equity": 10000.0})
        await cache.set_risk_exposure("user_2", {"equity": 5000.0})
        assert (await cache.get_risk_exposure("user_1"))["equity"] == 10000.0
        assert (await cache.get_risk_exposure("user_2"))["equity"] == 5000.0

    # --- Cross-type isolation ---

    async def test_candle_and_htf_keys_do_not_collide(self):
        """candle:EURUSD:M1 and htf:EURUSD:M1 must be independent."""
        cache = await _make_cache()
        await cache.set_candle("EURUSD", "M1", {"close": 1.10})
        await cache.set_htf("EURUSD", "M1", {"htf_open": 1.09})
        assert (await cache.get_candle("EURUSD", "M1"))["close"] == 1.10
        assert (await cache.get_htf("EURUSD", "M1"))["htf_open"] == 1.09

    async def test_all_five_key_types_coexist(self):
        cache = await _make_cache()
        await cache.set_candle("EURUSD", "M1", {"close": 1.10})
        await cache.set_htf("EURUSD", "H1", {"htf_open": 1.09})
        await cache.set_sentiment("EURUSD", {"score": 0.5})
        await cache.set_agent_state("user_1", {"mode": "HUMAN_IN_LOOP"})
        await cache.set_risk_exposure("user_1", {"equity": 10000.0})

        assert await cache.get_candle("EURUSD", "M1") is not None
        assert await cache.get_htf("EURUSD", "H1") is not None
        assert await cache.get_sentiment("EURUSD") is not None
        assert await cache.get_agent_state("user_1") is not None
        assert await cache.get_risk_exposure("user_1") is not None
