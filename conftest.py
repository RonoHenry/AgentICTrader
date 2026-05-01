"""
Root conftest.py — shared fixtures available across all services and tests.
"""
import pytest
import numpy as np
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


# ── MARKET DATA FIXTURES ──────────────────────────────────────────────────────

@pytest.fixture
def sample_candles() -> np.ndarray:
    """5 OHLCV candles as numpy array [open, high, low, close, volume]."""
    return np.array([
        [1.1000, 1.1050, 1.0980, 1.1020, 1000],
        [1.1020, 1.1080, 1.1010, 1.1060, 1200],
        [1.1060, 1.1100, 1.1040, 1.1045, 900],
        [1.1045, 1.1055, 1.0990, 1.1000, 1100],
        [1.1000, 1.1010, 1.0950, 1.0960, 1300],
    ], dtype=float)


@pytest.fixture
def sample_candle_dict() -> dict:
    """Single OHLCV candle as dict."""
    return {
        "time": datetime(2026, 4, 24, 14, 0, 0, tzinfo=timezone.utc),
        "instrument": "US500",
        "timeframe": "M5",
        "open": 6519.0,
        "high": 6528.0,
        "low": 6510.0,
        "close": 6512.0,
        "volume": 15420,
    }


@pytest.fixture
def bearish_candles() -> np.ndarray:
    """Clearly bearish sequence for pattern testing."""
    return np.array([
        [1.1100, 1.1120, 1.1080, 1.1090, 1000],
        [1.1090, 1.1095, 1.1050, 1.1055, 1200],
        [1.1055, 1.1060, 1.1010, 1.1015, 1400],
        [1.1015, 1.1020, 1.0970, 1.0975, 1600],
        [1.0975, 1.0980, 1.0930, 1.0935, 1800],
    ], dtype=float)


@pytest.fixture
def bullish_candles() -> np.ndarray:
    """Clearly bullish sequence for pattern testing."""
    return np.array([
        [1.0900, 1.0920, 1.0890, 1.0915, 1000],
        [1.0915, 1.0950, 1.0910, 1.0945, 1200],
        [1.0945, 1.0980, 1.0940, 1.0975, 1400],
        [1.0975, 1.1010, 1.0970, 1.1005, 1600],
        [1.1005, 1.1040, 1.1000, 1.1035, 1800],
    ], dtype=float)


# ── RISK ENGINE FIXTURES ──────────────────────────────────────────────────────

@pytest.fixture
def mock_risk_approved():
    """Mock risk engine response — trade approved."""
    mock = MagicMock()
    mock.verdict = "APPROVED"
    mock.rejection_reason = None
    mock.recommended_size = 2.5
    mock.checks = {
        "daily_dd_limit": "OK",
        "weekly_dd_limit": "OK",
        "max_position_size": "OK",
        "correlation_exposure": "OK",
        "news_blackout": "OK",
    }
    return mock


@pytest.fixture
def mock_risk_rejected():
    """Mock risk engine response — trade rejected."""
    mock = MagicMock()
    mock.verdict = "REJECTED"
    mock.rejection_reason = "Daily drawdown limit reached"
    mock.recommended_size = None
    return mock


# ── KAFKA FIXTURES ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer."""
    producer = AsyncMock()
    producer.send_and_wait = AsyncMock(return_value=None)
    return producer


@pytest.fixture
def mock_kafka_consumer():
    """Mock Kafka consumer."""
    consumer = AsyncMock()
    return consumer


# ── SENTIMENT FIXTURES ────────────────────────────────────────────────────────

@pytest.fixture
def bearish_sentiment():
    return {"score": -0.71, "label": "BEARISH", "instrument": "US500"}


@pytest.fixture
def bullish_sentiment():
    return {"score": 0.65, "label": "BULLISH", "instrument": "EURUSD"}


@pytest.fixture
def neutral_sentiment():
    return {"score": 0.05, "label": "NEUTRAL", "instrument": "XAUUSD"}
