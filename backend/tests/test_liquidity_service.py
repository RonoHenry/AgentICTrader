"""Tests for services.liquidity (task 162, optional FastAPI + Kafka wrapper)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from pd_array_engine.models import LiquidityMap
from services.liquidity.kafka_consumer import (
    TOPIC_LIQUIDITY_ANALYZED,
    LiquidityKafkaConsumer,
)
from services.liquidity.main import app

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
client = TestClient(app)


def _candle(n: int, open_: float, tf_days: int = 0) -> Dict[str, Any]:
    ts = _BASE + timedelta(days=tf_days * n)
    return {
        "timestamp": ts.isoformat(),
        "open": open_,
        "high": open_ + 2,
        "low": open_ - 1,
        "close": open_ + 1,
    }


def _valid_analyze_body() -> Dict[str, Any]:
    return {
        "instrument": "EURUSD",
        "timestamp": (_BASE + timedelta(days=20)).isoformat(),
        "candles_by_tf": {
            "D1": [_candle(i, 50 + i, tf_days=1) for i in range(10)],
            "W1": [_candle(i, 40 + 2 * i, tf_days=7) for i in range(4)],
        },
    }


class TestLiquidityServiceHTTP:
    def test_health_endpoint_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_analyze_endpoint_accepts_candles_by_tf_and_returns_liquidity_map(self):
        response = client.post("/analyze", json=_valid_analyze_body())
        assert response.status_code == 200
        body = response.json()
        assert body["instrument"] == "EURUSD"
        assert "setup_grade" in body

    def test_analyze_endpoint_validates_required_timeframes(self):
        body = _valid_analyze_body()
        del body["candles_by_tf"]["W1"]
        response = client.post("/analyze", json=body)
        assert response.status_code == 422


class TestLiquidityKafkaConsumer:
    def _candle_payload(self, n: int, open_: float, tf: str, tf_days: int = 0) -> Dict[str, Any]:
        ts = _BASE + timedelta(days=tf_days * n)
        return {
            "instrument": "EURUSD", "timeframe": tf, "time": ts.isoformat(),
            "open": open_, "high": open_ + 2, "low": open_ - 1, "close": open_ + 1, "volume": 100,
        }

    @pytest.mark.asyncio
    async def test_kafka_consumer_calls_engine_on_market_candles_message(self):
        consumer = LiquidityKafkaConsumer("localhost:9092")
        consumer._producer = AsyncMock()

        for i in range(10):
            await consumer.handle_message(self._candle_payload(i, 50 + i, "D1", tf_days=1))
        for i in range(4):
            result = await consumer.handle_message(self._candle_payload(i, 40 + 2 * i, "W1", tf_days=7))

        assert isinstance(result, LiquidityMap)

    @pytest.mark.asyncio
    async def test_kafka_consumer_publishes_liquidity_map_to_liquidity_analyzed_topic(self):
        consumer = LiquidityKafkaConsumer("localhost:9092")
        consumer._producer = AsyncMock()

        for i in range(10):
            await consumer.handle_message(self._candle_payload(i, 50 + i, "D1", tf_days=1))
        for i in range(4):
            await consumer.handle_message(self._candle_payload(i, 40 + 2 * i, "W1", tf_days=7))

        consumer._producer.send.assert_called()
        _, kwargs = consumer._producer.send.call_args
        args = consumer._producer.send.call_args.args
        assert args[0] == TOPIC_LIQUIDITY_ANALYZED
