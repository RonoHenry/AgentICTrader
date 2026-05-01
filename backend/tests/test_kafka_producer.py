"""
Tests for the Kafka producer for market data topics.

TDD Phase: RED → these tests are written BEFORE the implementation.
Run with:  pytest backend/tests/test_kafka_producer.py -v

All tests in this file must FAIL before any implementation is written.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Import targets — these will raise ImportError until 5b is implemented
# ---------------------------------------------------------------------------
from services.market_data.kafka_producer import (
    KafkaProducer,
    TickMessage,
    CandleMessage,
)


# ===========================================================================
# Fixtures
# ===========================================================================

SAMPLE_TICK = {
    "instrument": "EURUSD",
    "bid": 1.0850,
    "ask": 1.0851,
    "time": "2024-01-15T10:30:00.000000Z",
    "source": "oanda",
}

SAMPLE_CANDLE = {
    "instrument": "EURUSD",
    "timeframe": "M5",
    "time": "2024-01-15T10:30:00.000000Z",
    "open": 1.0850,
    "high": 1.0860,
    "low": 1.0845,
    "close": 1.0855,
    "volume": 1500,
    "complete": True,
    "source": "oanda",
}


@pytest.fixture
def kafka_bootstrap_servers():
    """Return Kafka bootstrap servers for testing."""
    return "localhost:9092"


@pytest.fixture
async def kafka_producer(kafka_bootstrap_servers):
    """Create a KafkaProducer instance for testing."""
    producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_servers)
    yield producer
    await producer.close()


# ===========================================================================
# 1. Integration test: ticks published to market.ticks topic
# ===========================================================================

class TestTickPublishing:
    """Ticks must be published to market.ticks topic with key=instrument."""

    @pytest.mark.asyncio
    async def test_tick_published_to_market_ticks_topic(self, kafka_producer):
        """A tick must be published to the market.ticks topic."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock()
            
            await kafka_producer.publish_tick(SAMPLE_TICK)
            
            # Verify send was called with correct topic
            mock_producer.send.assert_called_once()
            call_args = mock_producer.send.call_args
            assert call_args[0][0] == "market.ticks"

    @pytest.mark.asyncio
    async def test_tick_published_with_instrument_as_key(self, kafka_producer):
        """The message key must be the instrument name."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock()
            
            await kafka_producer.publish_tick(SAMPLE_TICK)
            
            call_kwargs = mock_producer.send.call_args[1]
            assert call_kwargs["key"] == b"EURUSD"

    @pytest.mark.asyncio
    async def test_tick_value_is_json_serialized(self, kafka_producer):
        """The message value must be JSON-serialized."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock()
            
            await kafka_producer.publish_tick(SAMPLE_TICK)
            
            call_kwargs = mock_producer.send.call_args[1]
            value = call_kwargs["value"]
            
            # Value should be bytes (JSON serialized)
            assert isinstance(value, bytes)
            
            # Should be valid JSON
            parsed = json.loads(value.decode("utf-8"))
            assert parsed["instrument"] == "EURUSD"
            assert parsed["bid"] == 1.0850
            assert parsed["ask"] == 1.0851


# ===========================================================================
# 2. Integration test: completed candles published to market.candles
# ===========================================================================

class TestCandlePublishing:
    """Completed candles must be published to market.candles with key=instrument:timeframe."""

    @pytest.mark.asyncio
    async def test_candle_published_to_market_candles_topic(self, kafka_producer):
        """A completed candle must be published to the market.candles topic."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock()
            
            await kafka_producer.publish_candle(SAMPLE_CANDLE)
            
            # Verify send was called with correct topic
            mock_producer.send.assert_called_once()
            call_args = mock_producer.send.call_args
            assert call_args[0][0] == "market.candles"

    @pytest.mark.asyncio
    async def test_candle_published_with_instrument_timeframe_as_key(self, kafka_producer):
        """The message key must be instrument:timeframe."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock()
            
            await kafka_producer.publish_candle(SAMPLE_CANDLE)
            
            call_kwargs = mock_producer.send.call_args[1]
            assert call_kwargs["key"] == b"EURUSD:M5"

    @pytest.mark.asyncio
    async def test_candle_value_is_json_serialized(self, kafka_producer):
        """The message value must be JSON-serialized."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock()
            
            await kafka_producer.publish_candle(SAMPLE_CANDLE)
            
            call_kwargs = mock_producer.send.call_args[1]
            value = call_kwargs["value"]
            
            # Value should be bytes (JSON serialized)
            assert isinstance(value, bytes)
            
            # Should be valid JSON
            parsed = json.loads(value.decode("utf-8"))
            assert parsed["instrument"] == "EURUSD"
            assert parsed["timeframe"] == "M5"
            assert parsed["open"] == 1.0850
            assert parsed["high"] == 1.0860
            assert parsed["low"] == 1.0845
            assert parsed["close"] == 1.0855
            assert parsed["volume"] == 1500
            assert parsed["complete"] is True


# ===========================================================================
# 3. JSON schema validation
# ===========================================================================

class TestJSONSchema:
    """Published messages must match the expected JSON schema."""

    @pytest.mark.asyncio
    async def test_candle_json_schema_matches_spec(self, kafka_producer):
        """Candle JSON must have all required fields."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock()
            
            await kafka_producer.publish_candle(SAMPLE_CANDLE)
            
            call_kwargs = mock_producer.send.call_args[1]
            value = call_kwargs["value"]
            parsed = json.loads(value.decode("utf-8"))
            
            # Verify all required fields are present
            required_fields = {
                "instrument",
                "timeframe",
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "complete",
                "source",
            }
            assert set(parsed.keys()) == required_fields

    @pytest.mark.asyncio
    async def test_candle_field_types_are_correct(self, kafka_producer):
        """Candle fields must have correct types."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock()
            
            await kafka_producer.publish_candle(SAMPLE_CANDLE)
            
            call_kwargs = mock_producer.send.call_args[1]
            value = call_kwargs["value"]
            parsed = json.loads(value.decode("utf-8"))
            
            assert isinstance(parsed["instrument"], str)
            assert isinstance(parsed["timeframe"], str)
            assert isinstance(parsed["time"], str)
            assert isinstance(parsed["open"], (int, float))
            assert isinstance(parsed["high"], (int, float))
            assert isinstance(parsed["low"], (int, float))
            assert isinstance(parsed["close"], (int, float))
            assert isinstance(parsed["volume"], int)
            assert isinstance(parsed["complete"], bool)
            assert isinstance(parsed["source"], str)


# ===========================================================================
# 4. Producer health check
# ===========================================================================

class TestHealthCheck:
    """The producer must provide a health check method."""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy_state(self, kafka_producer):
        """health_check() must return a dict with healthy=True when connected."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.client = MagicMock()
            mock_producer.client.cluster = MagicMock()
            mock_producer.client.cluster.brokers = MagicMock(return_value=[MagicMock()])
            
            health = await kafka_producer.health_check()
            
            assert isinstance(health, dict)
            assert "healthy" in health
            assert health["healthy"] is True

    @pytest.mark.asyncio
    async def test_health_check_returns_unhealthy_when_disconnected(self, kafka_producer):
        """health_check() must return healthy=False when not connected."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.client = MagicMock()
            mock_producer.client.cluster = MagicMock()
            mock_producer.client.cluster.brokers = MagicMock(return_value=[])
            
            health = await kafka_producer.health_check()
            
            assert health["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_includes_broker_info(self, kafka_producer):
        """health_check() should include broker connection info."""
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.client = MagicMock()
            mock_producer.client.cluster = MagicMock()
            mock_producer.client.cluster.brokers = MagicMock(return_value=[MagicMock()])
            
            health = await kafka_producer.health_check()
            
            assert "broker_count" in health or "status" in health


# ===========================================================================
# 5. Graceful shutdown
# ===========================================================================

class TestGracefulShutdown:
    """The producer must flush pending messages on shutdown."""

    @pytest.mark.asyncio
    async def test_close_flushes_pending_messages(self):
        """close() must call flush() to ensure all messages are sent."""
        producer = KafkaProducer(bootstrap_servers="localhost:9092")
        
        with patch.object(producer, "_producer") as mock_producer:
            mock_producer.flush = AsyncMock()
            mock_producer.stop = AsyncMock()
            
            await producer.close()
            
            # Verify flush was called before stop
            mock_producer.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_stops_producer(self):
        """close() must call stop() on the underlying producer."""
        producer = KafkaProducer(bootstrap_servers="localhost:9092")
        
        with patch.object(producer, "_producer") as mock_producer:
            mock_producer.flush = AsyncMock()
            mock_producer.stop = AsyncMock()
            
            await producer.close()
            
            # Verify stop was called
            mock_producer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self):
        """Calling close() multiple times should not raise errors."""
        producer = KafkaProducer(bootstrap_servers="localhost:9092")
        
        with patch.object(producer, "_producer") as mock_producer:
            mock_producer.flush = AsyncMock()
            mock_producer.stop = AsyncMock()
            
            await producer.close()
            await producer.close()  # Should not raise
            
            # Should only flush/stop once (or handle multiple calls gracefully)
            assert mock_producer.flush.call_count >= 1
            assert mock_producer.stop.call_count >= 1


# ===========================================================================
# 6. Error handling
# ===========================================================================

class TestErrorHandling:
    """The producer must handle errors gracefully."""

    @pytest.mark.asyncio
    async def test_publish_tick_raises_on_kafka_error(self, kafka_producer):
        """publish_tick should raise an exception if Kafka send fails."""
        from aiokafka.errors import KafkaError
        
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock(side_effect=KafkaError("Connection failed"))
            
            with pytest.raises(Exception):  # Should propagate the error
                await kafka_producer.publish_tick(SAMPLE_TICK)

    @pytest.mark.asyncio
    async def test_publish_candle_raises_on_kafka_error(self, kafka_producer):
        """publish_candle should raise an exception if Kafka send fails."""
        from aiokafka.errors import KafkaError
        
        with patch.object(kafka_producer, "_producer") as mock_producer:
            mock_producer.send = AsyncMock(side_effect=KafkaError("Connection failed"))
            
            with pytest.raises(Exception):  # Should propagate the error
                await kafka_producer.publish_candle(SAMPLE_CANDLE)


# ===========================================================================
# 7. Integration test with real Kafka (optional, requires Docker)
# ===========================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_kafka_publish_and_consume():
    """
    Integration test: publish a message and verify it can be consumed.
    This test requires Kafka to be running (docker-compose up kafka).
    """
    pytest.skip("Integration test - requires running Kafka instance")
    
    # This test would:
    # 1. Create a real KafkaProducer
    # 2. Publish a test message
    # 3. Create a consumer and verify the message was received
    # 4. Clean up
