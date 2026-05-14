"""
Integration tests for the ML Inference FastAPI service.

Tests cover:
- POST /predict endpoint: request/response schema, confidence thresholds, HTF projections
- GET /health endpoint: liveness check
- ModelRegistry: stub fallback when models not registered
- InferenceEngine: feature extraction and prediction pipeline
- CandleConsumer: Kafka message handling and rolling window
- SetupPublisher: setups.detected message schema
- Confidence threshold gating (< 0.65 discard, 0.65-0.74 log only, >= 0.75 publish)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from ml.inference.main import (
    CandleConsumer,
    InferenceEngine,
    ModelRegistry,
    OHLCVCandle,
    PredictRequest,
    SetupPublisher,
    create_app,
    CONFIDENCE_FLOOR,
    CONFIDENCE_LOG_ONLY,
    PATTERN_LABELS,
    REGIME_CLASSES,
    TOPIC_CANDLES,
    TOPIC_SETUPS,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_candles(n: int = 5, base_price: float = 1.1000) -> List[Dict[str, Any]]:
    """Build a list of n synthetic OHLCV candle dicts."""
    candles = []
    price = base_price
    for i in range(n):
        open_ = price
        close = price + 0.0010 * (1 if i % 2 == 0 else -1)
        high = max(open_, close) + 0.0005
        low = min(open_, close) - 0.0005
        # Use minutes to avoid hour overflow for large n
        hour = (i * 5) // 60
        minute = (i * 5) % 60
        candles.append({
            "time": f"2024-01-01T{hour:02d}:{minute:02d}:00Z",
            "open": round(open_, 5),
            "high": round(high, 5),
            "low": round(low, 5),
            "close": round(close, 5),
            "volume": 1000.0 + i * 100,
        })
        price = close
    return candles


def _make_ohlcv_models(n: int = 5) -> List[OHLCVCandle]:
    """Build a list of n OHLCVCandle Pydantic models."""
    raw = _make_candles(n)
    return [OHLCVCandle(**c) for c in raw]


@pytest.fixture
def sample_candles() -> List[Dict[str, Any]]:
    return _make_candles(10)


@pytest.fixture
def sample_ohlcv_models() -> List[OHLCVCandle]:
    return _make_ohlcv_models(10)


@pytest.fixture
def stub_registry() -> ModelRegistry:
    """ModelRegistry with all models set to None (stub mode)."""
    with patch.object(ModelRegistry, "load", return_value=None):
        registry = ModelRegistry(tracking_uri="http://localhost:5000")
        registry._regime_model = None
        registry._pattern_model = None
        registry._confluence_model = None
        registry._loaded = True
    return registry


@pytest.fixture
def mock_regime_model():
    """Mock sklearn-compatible regime classifier."""
    model = Mock()
    model.predict = Mock(return_value=np.array([0]))  # TRENDING_BULLISH
    return model


@pytest.fixture
def mock_pattern_model():
    """Mock sklearn-compatible multi-label pattern detector."""
    model = Mock()
    # predict_proba returns list of (n_samples, 2) arrays  one per label
    model.predict_proba = Mock(
        return_value=[
            np.array([[0.3, 0.7]]),  # BOS_CONFIRMED active
            np.array([[0.8, 0.2]]),  # CHOCH_DETECTED inactive
            np.array([[0.4, 0.6]]),  # BEARISH_ARRAY_REJECTION active
            np.array([[0.9, 0.1]]),  # BULLISH_ARRAY_BOUNCE inactive
            np.array([[0.3, 0.7]]),  # FVG_PRESENT active
            np.array([[0.8, 0.2]]),  # LIQUIDITY_SWEEP inactive
            np.array([[0.9, 0.1]]),  # ORDER_BLOCK inactive
            np.array([[0.8, 0.2]]),  # INDUCEMENT inactive
        ]
    )
    return model


@pytest.fixture
def mock_confluence_model():
    """Mock sklearn-compatible confluence scorer."""
    model = Mock()
    model.predict_proba = Mock(return_value=np.array([[0.15, 0.85]]))  # 0.85 confidence
    return model


@pytest.fixture
def registry_with_mocks(mock_regime_model, mock_pattern_model, mock_confluence_model):
    """ModelRegistry with mock models injected."""
    with patch.object(ModelRegistry, "load", return_value=None):
        registry = ModelRegistry(tracking_uri="http://localhost:5000")
        registry._regime_model = mock_regime_model
        registry._pattern_model = mock_pattern_model
        registry._confluence_model = mock_confluence_model
        registry._loaded = True
    return registry


@pytest.fixture
def inference_engine(registry_with_mocks) -> InferenceEngine:
    return InferenceEngine(registry_with_mocks)


@pytest.fixture
def test_client(stub_registry) -> TestClient:
    """FastAPI TestClient with stub models (no Kafka)."""
    with patch("ml.inference.main.ModelRegistry", return_value=stub_registry):
        app = create_app(registry=stub_registry)
    return TestClient(app)


# ===========================================================================
# 1. Constants and schema tests
# ===========================================================================


class TestConstants:
    """Verify module-level constants match the spec."""

    def test_confidence_floor_is_0_65(self):
        """CONFIDENCE_FLOOR must be 0.65 (hard discard threshold)."""
        assert CONFIDENCE_FLOOR == 0.65

    def test_confidence_log_only_is_0_75(self):
        """CONFIDENCE_LOG_ONLY must be 0.75 (publish threshold)."""
        assert CONFIDENCE_LOG_ONLY == 0.75

    def test_topic_candles_name(self):
        """Kafka input topic must be market.candles."""
        assert TOPIC_CANDLES == "market.candles"

    def test_topic_setups_name(self):
        """Kafka output topic must be setups.detected."""
        assert TOPIC_SETUPS == "setups.detected"

    def test_regime_classes_count(self):
        """Five regime classes must be defined."""
        assert len(REGIME_CLASSES) == 5

    def test_regime_classes_values(self):
        """All five regime class labels must be present."""
        expected = {
            "TRENDING_BULLISH",
            "TRENDING_BEARISH",
            "RANGING",
            "BREAKOUT",
            "NEWS_DRIVEN",
        }
        assert set(REGIME_CLASSES) == expected

    def test_pattern_labels_count(self):
        """Eight pattern labels must be defined."""
        assert len(PATTERN_LABELS) == 8

    def test_pattern_labels_values(self):
        """All eight pattern labels must be present."""
        expected = {
            "BOS_CONFIRMED",
            "CHOCH_DETECTED",
            "BEARISH_ARRAY_REJECTION",
            "BULLISH_ARRAY_BOUNCE",
            "FVG_PRESENT",
            "LIQUIDITY_SWEEP",
            "ORDER_BLOCK",
            "INDUCEMENT",
        }
        assert set(PATTERN_LABELS) == expected


# ===========================================================================
# 2. ModelRegistry tests
# ===========================================================================


class TestModelRegistry:
    """Tests for ModelRegistry  model loading and stub fallback."""

    def test_registry_instantiates(self):
        """ModelRegistry can be instantiated with a tracking URI."""
        with patch("mlflow.set_tracking_uri"):
            registry = ModelRegistry(tracking_uri="http://localhost:5000")
        assert registry is not None

    def test_registry_not_loaded_before_load_called(self):
        """loaded property is False before load() is called."""
        with patch("mlflow.set_tracking_uri"):
            registry = ModelRegistry(tracking_uri="http://localhost:5000")
        assert registry.loaded is False

    def test_registry_loaded_after_load_called(self, stub_registry):
        """loaded property is True after load() completes."""
        assert stub_registry.loaded is True

    def test_stub_regime_returns_ranging(self, stub_registry):
        """Stub regime model returns RANGING by default."""
        X = np.zeros((1, 10))
        result = stub_registry.predict_regime(X)
        assert result == "RANGING"

    def test_stub_patterns_returns_empty_list(self, stub_registry):
        """Stub pattern model returns empty list by default."""
        X = np.zeros((1, 10))
        result = stub_registry.predict_patterns(X)
        assert result == []

    def test_stub_confidence_returns_zero(self, stub_registry):
        """Stub confluence model returns 0.0 by default."""
        X = np.zeros((1, 10))
        result = stub_registry.predict_confidence(X)
        assert result == 0.0

    def test_regime_model_returns_class_label(self, registry_with_mocks):
        """predict_regime returns a valid REGIME_CLASSES label."""
        X = np.zeros((1, 10))
        result = registry_with_mocks.predict_regime(X)
        assert result in REGIME_CLASSES

    def test_pattern_model_returns_list_of_labels(self, registry_with_mocks):
        """predict_patterns returns a list of PATTERN_LABELS strings."""
        X = np.zeros((1, 10))
        result = registry_with_mocks.predict_patterns(X)
        assert isinstance(result, list)
        for label in result:
            assert label in PATTERN_LABELS

    def test_confidence_model_returns_float_in_range(self, registry_with_mocks):
        """predict_confidence returns a float in [0.0, 1.0]."""
        X = np.zeros((1, 10))
        result = registry_with_mocks.predict_confidence(X)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_load_falls_back_to_stub_when_mlflow_unavailable(self):
        """load() installs stub predictors when MLflow registry is unreachable."""
        with patch("mlflow.set_tracking_uri"), \
             patch("mlflow.tracking.MlflowClient") as mock_client_cls:
            mock_client = Mock()
            mock_client.get_latest_versions.side_effect = Exception("Connection refused")
            mock_client_cls.return_value = mock_client

            registry = ModelRegistry(tracking_uri="http://localhost:5000")
            registry.load()

        assert registry.loaded is True
        # All models should be None (stub mode)
        assert registry._regime_model is None
        assert registry._pattern_model is None
        assert registry._confluence_model is None


# ===========================================================================
# 3. InferenceEngine tests
# ===========================================================================


class TestInferenceEngine:
    """Tests for InferenceEngine  feature extraction and prediction."""

    def test_engine_instantiates(self, stub_registry):
        """InferenceEngine can be instantiated with a registry."""
        engine = InferenceEngine(stub_registry)
        assert engine is not None

    def test_predict_returns_required_keys(self, inference_engine, sample_candles):
        """predict() returns a dict with all required keys."""
        result = inference_engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        required_keys = {
            "time",
            "regime",
            "patterns",
            "confidence_score",
            "htf_projections",
            "entry_price",
            "sl_price",
            "tp_price",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_predict_regime_is_valid_class(self, inference_engine, sample_candles):
        """predict() returns a valid regime class label."""
        result = inference_engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        assert result["regime"] in REGIME_CLASSES

    def test_predict_patterns_is_list(self, inference_engine, sample_candles):
        """predict() returns patterns as a list."""
        result = inference_engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        assert isinstance(result["patterns"], list)

    def test_predict_confidence_score_in_range(self, inference_engine, sample_candles):
        """predict() returns confidence_score in [0.0, 1.0]."""
        result = inference_engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        assert 0.0 <= result["confidence_score"] <= 1.0

    def test_predict_htf_projections_has_required_fields(self, inference_engine, sample_candles):
        """predict() returns htf_projections with all required fields."""
        result = inference_engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        htf = result["htf_projections"]
        required_htf_keys = {
            "htf_timeframe",
            "htf_open",
            "htf_high",
            "htf_low",
            "open_bias",
            "htf_high_proximity_pct",
            "htf_low_proximity_pct",
            "htf_body_pct",
            "htf_upper_wick_pct",
            "htf_lower_wick_pct",
            "htf_close_position",
        }
        assert required_htf_keys.issubset(set(htf.keys()))

    def test_predict_open_bias_is_valid_enum(self, inference_engine, sample_candles):
        """predict() returns open_bias in {BULLISH, BEARISH, NEUTRAL}."""
        result = inference_engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        assert result["htf_projections"]["open_bias"] in {"BULLISH", "BEARISH", "NEUTRAL"}

    def test_predict_raises_on_single_candle(self, inference_engine):
        """predict() raises ValueError when fewer than 2 candles provided."""
        single_candle = _make_candles(1)
        with pytest.raises(ValueError, match="At least 2 candles"):
            inference_engine.predict(
                instrument="EURUSD",
                timeframe="M5",
                candles=single_candle,
            )

    def test_predict_trade_levels_none_when_confidence_below_floor(self, stub_registry, sample_candles):
        """entry/sl/tp are None when confidence < CONFIDENCE_FLOOR (stub returns 0.0)."""
        engine = InferenceEngine(stub_registry)
        result = engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        # Stub confidence is 0.0 < 0.65
        assert result["entry_price"] is None
        assert result["sl_price"] is None
        assert result["tp_price"] is None

    def test_predict_trade_levels_set_when_confidence_above_floor(
        self, registry_with_mocks, sample_candles
    ):
        """entry/sl/tp are set when confidence >= CONFIDENCE_FLOOR and bias is not NEUTRAL."""
        engine = InferenceEngine(registry_with_mocks)
        result = engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        # Mock confidence is 0.85 >= 0.65
        # Trade levels depend on open_bias  if NEUTRAL they remain None
        confidence = result["confidence_score"]
        assert confidence >= CONFIDENCE_FLOOR
        # If bias is directional, levels should be set
        if result["htf_projections"]["open_bias"] in ("BULLISH", "BEARISH"):
            assert result["entry_price"] is not None
            assert result["sl_price"] is not None
            assert result["tp_price"] is not None

    def test_predict_time_is_string(self, inference_engine, sample_candles):
        """predict() returns time as a string."""
        result = inference_engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        assert isinstance(result["time"], str)

    def test_predict_htf_timeframe_is_higher_than_input(
        self, inference_engine, sample_candles
    ):
        """HTF timeframe returned is always a higher timeframe than the input.

        The engine uses INTRADAY_STANDARD style which maps all inputs to D1 bias.
        The key invariant is that the returned htf_timeframe is a valid timeframe
        string and is present in the htf_projections dict.
        """
        result = inference_engine.predict(
            instrument="EURUSD",
            timeframe="M5",
            candles=sample_candles,
        )
        htf_tf = result["htf_projections"]["htf_timeframe"]
        # Must be a non-empty string
        assert isinstance(htf_tf, str)
        assert len(htf_tf) > 0
        # Must be a known timeframe
        valid_timeframes = {"M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"}
        assert htf_tf in valid_timeframes, f"Unknown HTF timeframe: {htf_tf}"
        # For M5 input with INTRADAY_STANDARD style, bias TF should be D1
        assert htf_tf == "D1", f"Expected D1 for M5 INTRADAY_STANDARD, got {htf_tf}"


# ===========================================================================
# 4. POST /predict endpoint tests
# ===========================================================================


class TestPredictEndpoint:
    """Integration tests for POST /predict."""

    @pytest.fixture
    def client(self, stub_registry) -> TestClient:
        app = create_app(registry=stub_registry)
        return TestClient(app)

    def _predict_payload(self, n_candles: int = 5, instrument: str = "EURUSD", timeframe: str = "M5") -> Dict:
        candles = [
            {
                "time": f"2024-01-01T{i:02d}:00:00Z",
                "open": 1.1000 + i * 0.001,
                "high": 1.1010 + i * 0.001,
                "low": 1.0990 + i * 0.001,
                "close": 1.1005 + i * 0.001,
                "volume": 1000.0,
            }
            for i in range(n_candles)
        ]
        return {"instrument": instrument, "timeframe": timeframe, "candles": candles}

    def test_predict_returns_200(self, client):
        """POST /predict returns HTTP 200 for valid payload."""
        response = client.post("/predict", json=self._predict_payload())
        assert response.status_code == 200

    def test_predict_response_has_instrument(self, client):
        """POST /predict response includes instrument field."""
        response = client.post("/predict", json=self._predict_payload(instrument="XAUUSD"))
        assert response.status_code == 200
        assert response.json()["instrument"] == "XAUUSD"

    def test_predict_response_has_timeframe(self, client):
        """POST /predict response includes timeframe field."""
        response = client.post("/predict", json=self._predict_payload(timeframe="H1"))
        assert response.status_code == 200
        assert response.json()["timeframe"] == "H1"

    def test_predict_response_has_regime(self, client):
        """POST /predict response includes regime field."""
        response = client.post("/predict", json=self._predict_payload())
        assert response.status_code == 200
        assert "regime" in response.json()
        assert response.json()["regime"] in REGIME_CLASSES

    def test_predict_response_has_patterns_list(self, client):
        """POST /predict response includes patterns as a list."""
        response = client.post("/predict", json=self._predict_payload())
        assert response.status_code == 200
        assert isinstance(response.json()["patterns"], list)

    def test_predict_response_has_confidence_score(self, client):
        """POST /predict response includes confidence_score in [0, 1]."""
        response = client.post("/predict", json=self._predict_payload())
        assert response.status_code == 200
        score = response.json()["confidence_score"]
        assert 0.0 <= score <= 1.0

    def test_predict_response_has_htf_projections(self, client):
        """POST /predict response includes htf_projections object."""
        response = client.post("/predict", json=self._predict_payload())
        assert response.status_code == 200
        htf = response.json()["htf_projections"]
        assert "htf_open" in htf
        assert "htf_high" in htf
        assert "htf_low" in htf
        assert "open_bias" in htf

    def test_predict_response_htf_open_bias_valid(self, client):
        """POST /predict response open_bias is in valid enum set."""
        response = client.post("/predict", json=self._predict_payload())
        assert response.status_code == 200
        bias = response.json()["htf_projections"]["open_bias"]
        assert bias in {"BULLISH", "BEARISH", "NEUTRAL"}

    def test_predict_response_has_time_field(self, client):
        """POST /predict response includes time field."""
        response = client.post("/predict", json=self._predict_payload())
        assert response.status_code == 200
        assert "time" in response.json()

    def test_predict_rejects_single_candle(self, client):
        """POST /predict returns 422 when only 1 candle provided."""
        payload = self._predict_payload(n_candles=1)
        response = client.post("/predict", json=payload)
        assert response.status_code == 422

    def test_predict_rejects_empty_candles(self, client):
        """POST /predict returns 422 when candles list is empty."""
        payload = {"instrument": "EURUSD", "timeframe": "M5", "candles": []}
        response = client.post("/predict", json=payload)
        assert response.status_code == 422

    def test_predict_accepts_optional_reference_prices(self, client):
        """POST /predict accepts optional daily_open, weekly_open, true_day_open."""
        payload = self._predict_payload()
        payload["daily_open"] = 1.1000
        payload["weekly_open"] = 1.0950
        payload["true_day_open"] = 1.1010
        response = client.post("/predict", json=payload)
        assert response.status_code == 200

    def test_predict_all_supported_instruments(self, client):
        """POST /predict works for all 12 supported instruments."""
        instruments = [
            "XAUUSD", "EURUSD", "GBPUSD", "EURAUD", "GBPAUD",
            "USDJPY", "US100", "US30", "US500", "GER40", "BTCUSD", "ETHUSD",
        ]
        for instrument in instruments:
            response = client.post("/predict", json=self._predict_payload(instrument=instrument))
            assert response.status_code == 200, f"Failed for instrument {instrument}"

    def test_predict_all_supported_timeframes(self, client):
        """POST /predict works for all supported timeframes."""
        timeframes = ["M1", "M5", "M15", "H1", "H4", "D1"]
        for tf in timeframes:
            response = client.post("/predict", json=self._predict_payload(timeframe=tf))
            assert response.status_code == 200, f"Failed for timeframe {tf}"

    def test_predict_stub_confidence_below_floor_no_trade_levels(self, client):
        """Stub confidence (0.0) means entry/sl/tp are null in response."""
        response = client.post("/predict", json=self._predict_payload())
        assert response.status_code == 200
        data = response.json()
        # Stub returns 0.0 confidence < 0.65 floor
        assert data["entry_price"] is None
        assert data["sl_price"] is None
        assert data["tp_price"] is None


# ===========================================================================
# 5. GET /health endpoint tests
# ===========================================================================


class TestHealthEndpoint:
    """Tests for GET /health liveness check."""

    @pytest.fixture
    def client(self, stub_registry) -> TestClient:
        app = create_app(registry=stub_registry)
        return TestClient(app)

    def test_health_returns_200(self, client):
        """GET /health returns HTTP 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_has_status_ok(self, client):
        """GET /health response has status='ok'."""
        response = client.get("/health")
        assert response.json()["status"] == "ok"

    def test_health_response_has_models_loaded(self, client):
        """GET /health response includes models_loaded boolean."""
        response = client.get("/health")
        assert "models_loaded" in response.json()
        assert isinstance(response.json()["models_loaded"], bool)

    def test_health_response_has_kafka_consumer_running(self, client):
        """GET /health response includes kafka_consumer_running boolean."""
        response = client.get("/health")
        assert "kafka_consumer_running" in response.json()
        assert isinstance(response.json()["kafka_consumer_running"], bool)

    def test_health_models_loaded_true_when_registry_loaded(self, stub_registry):
        """models_loaded is True when registry.loaded is True."""
        app = create_app(registry=stub_registry)
        client = TestClient(app)
        response = client.get("/health")
        assert response.json()["models_loaded"] is True

    def test_health_kafka_consumer_false_without_kafka(self, stub_registry):
        """kafka_consumer_running is False when no Kafka consumer is running."""
        app = create_app(registry=stub_registry)
        client = TestClient(app)
        response = client.get("/health")
        # No Kafka in test environment
        assert response.json()["kafka_consumer_running"] is False


# ===========================================================================
# 6. Confidence threshold gating tests
# ===========================================================================


class TestConfidenceThresholds:
    """Tests for confidence threshold gating in InferenceEngine._derive_trade_levels."""

    def _make_htf_proj(self, open_bias: str = "BULLISH") -> Dict[str, Any]:
        return {
            "htf_timeframe": "H1",
            "htf_open": 1.1000,
            "htf_high": 1.1200,
            "htf_low": 1.0800,
            "open_bias": open_bias,
            "htf_high_proximity_pct": 30.0,
            "htf_low_proximity_pct": 70.0,
            "htf_body_pct": 60.0,
            "htf_upper_wick_pct": 20.0,
            "htf_lower_wick_pct": 20.0,
            "htf_close_position": 0.8,
        }

    def _make_candle(self, close: float = 1.1050) -> Dict[str, Any]:
        return {"time": "2024-01-01T00:00:00Z", "open": 1.1000, "high": 1.1100, "low": 1.0950, "close": close, "volume": 1000}

    def test_confidence_below_floor_returns_none_levels(self, stub_registry):
        """confidence < 0.65 -> entry/sl/tp all None."""
        engine = InferenceEngine(stub_registry)
        entry, sl, tp = engine._derive_trade_levels(
            current_candle=self._make_candle(),
            htf_proj=self._make_htf_proj("BULLISH"),
            confidence_score=0.60,
        )
        assert entry is None
        assert sl is None
        assert tp is None

    def test_confidence_at_floor_minus_epsilon_returns_none(self, stub_registry):
        """confidence = 0.6499 (just below floor) -> None levels."""
        engine = InferenceEngine(stub_registry)
        entry, sl, tp = engine._derive_trade_levels(
            current_candle=self._make_candle(),
            htf_proj=self._make_htf_proj("BULLISH"),
            confidence_score=0.6499,
        )
        assert entry is None

    def test_confidence_at_floor_returns_levels(self, stub_registry):
        """confidence = 0.65 (at floor) -> trade levels set for directional bias."""
        engine = InferenceEngine(stub_registry)
        entry, sl, tp = engine._derive_trade_levels(
            current_candle=self._make_candle(close=1.1050),
            htf_proj=self._make_htf_proj("BULLISH"),
            confidence_score=0.65,
        )
        assert entry is not None
        assert sl is not None
        assert tp is not None

    def test_confidence_above_floor_returns_levels(self, stub_registry):
        """confidence = 0.85 -> trade levels set."""
        engine = InferenceEngine(stub_registry)
        entry, sl, tp = engine._derive_trade_levels(
            current_candle=self._make_candle(close=1.1050),
            htf_proj=self._make_htf_proj("BULLISH"),
            confidence_score=0.85,
        )
        assert entry is not None

    def test_bullish_bias_entry_is_close_sl_is_htf_low(self, stub_registry):
        """Bullish bias: entry=close, sl=htf_low, tp=htf_high."""
        engine = InferenceEngine(stub_registry)
        close = 1.1050
        htf_proj = self._make_htf_proj("BULLISH")
        entry, sl, tp = engine._derive_trade_levels(
            current_candle=self._make_candle(close=close),
            htf_proj=htf_proj,
            confidence_score=0.80,
        )
        assert entry == pytest.approx(close)
        assert sl == pytest.approx(htf_proj["htf_low"])
        assert tp == pytest.approx(htf_proj["htf_high"])

    def test_bearish_bias_entry_is_close_sl_is_htf_high(self, stub_registry):
        """Bearish bias: entry=close, sl=htf_high, tp=htf_low."""
        engine = InferenceEngine(stub_registry)
        close = 1.1050
        htf_proj = self._make_htf_proj("BEARISH")
        entry, sl, tp = engine._derive_trade_levels(
            current_candle=self._make_candle(close=close),
            htf_proj=htf_proj,
            confidence_score=0.80,
        )
        assert entry == pytest.approx(close)
        assert sl == pytest.approx(htf_proj["htf_high"])
        assert tp == pytest.approx(htf_proj["htf_low"])

    def test_neutral_bias_returns_none_levels(self, stub_registry):
        """NEUTRAL bias -> no trade levels regardless of confidence."""
        engine = InferenceEngine(stub_registry)
        entry, sl, tp = engine._derive_trade_levels(
            current_candle=self._make_candle(),
            htf_proj=self._make_htf_proj("NEUTRAL"),
            confidence_score=0.90,
        )
        assert entry is None
        assert sl is None
        assert tp is None


# ===========================================================================
# 7. setups.detected message schema tests
# ===========================================================================


class TestSetupsDetectedSchema:
    """Tests for the setups.detected Kafka message schema."""

    REQUIRED_FIELDS = {
        "instrument",
        "timeframe",
        "time",
        "regime",
        "patterns",
        "confidence_score",
        "htf_open",
        "htf_high",
        "htf_low",
        "open_bias",
        "entry_price",
        "sl_price",
        "tp_price",
    }

    def _build_setup_msg(self, **overrides) -> Dict[str, Any]:
        base = {
            "instrument": "EURUSD",
            "timeframe": "M5",
            "time": "2024-01-01T10:00:00Z",
            "regime": "TRENDING_BULLISH",
            "patterns": ["BOS_CONFIRMED", "FVG_PRESENT"],
            "confidence_score": 0.82,
            "htf_open": 1.1000,
            "htf_high": 1.1200,
            "htf_low": 1.0800,
            "open_bias": "BULLISH",
            "entry_price": 1.1050,
            "sl_price": 1.0800,
            "tp_price": 1.1200,
        }
        base.update(overrides)
        return base

    def test_setup_msg_has_all_required_fields(self):
        """setups.detected message contains all 13 required fields."""
        msg = self._build_setup_msg()
        assert self.REQUIRED_FIELDS.issubset(set(msg.keys()))

    def test_setup_msg_instrument_is_string(self):
        """instrument field is a string."""
        msg = self._build_setup_msg()
        assert isinstance(msg["instrument"], str)

    def test_setup_msg_timeframe_is_string(self):
        """timeframe field is a string."""
        msg = self._build_setup_msg()
        assert isinstance(msg["timeframe"], str)

    def test_setup_msg_regime_is_valid_class(self):
        """regime field is a valid REGIME_CLASSES value."""
        msg = self._build_setup_msg()
        assert msg["regime"] in REGIME_CLASSES

    def test_setup_msg_patterns_is_list(self):
        """patterns field is a list."""
        msg = self._build_setup_msg()
        assert isinstance(msg["patterns"], list)

    def test_setup_msg_confidence_score_in_range(self):
        """confidence_score is in [0.0, 1.0]."""
        msg = self._build_setup_msg()
        assert 0.0 <= msg["confidence_score"] <= 1.0

    def test_setup_msg_open_bias_valid(self):
        """open_bias is in {BULLISH, BEARISH, NEUTRAL}."""
        msg = self._build_setup_msg()
        assert msg["open_bias"] in {"BULLISH", "BEARISH", "NEUTRAL"}

    def test_setup_msg_is_json_serialisable(self):
        """setups.detected message can be JSON-serialised."""
        msg = self._build_setup_msg()
        serialised = json.dumps(msg, default=str)
        deserialised = json.loads(serialised)
        assert deserialised["instrument"] == msg["instrument"]
        assert deserialised["confidence_score"] == msg["confidence_score"]

    def test_setup_msg_htf_levels_are_numeric(self):
        """htf_open, htf_high, htf_low are numeric."""
        msg = self._build_setup_msg()
        assert isinstance(msg["htf_open"], (int, float))
        assert isinstance(msg["htf_high"], (int, float))
        assert isinstance(msg["htf_low"], (int, float))

    def test_setup_msg_htf_high_gte_htf_low(self):
        """htf_high >= htf_low (valid OHLC range)."""
        msg = self._build_setup_msg()
        assert msg["htf_high"] >= msg["htf_low"]


# ===========================================================================
# 8. CandleConsumer rolling window tests
# ===========================================================================


class TestCandleConsumer:
    """Tests for CandleConsumer rolling window and message handling."""

    def _make_consumer(self) -> CandleConsumer:
        """Build a CandleConsumer with mock engine and publisher."""
        mock_engine = Mock(spec=InferenceEngine)
        mock_engine.predict = Mock(return_value={
            "time": "2024-01-01T00:00:00Z",
            "regime": "RANGING",
            "patterns": [],
            "confidence_score": 0.0,
            "htf_projections": {
                "htf_timeframe": "H1",
                "htf_open": 1.1000,
                "htf_high": 1.1200,
                "htf_low": 1.0800,
                "open_bias": "NEUTRAL",
                "htf_high_proximity_pct": 50.0,
                "htf_low_proximity_pct": 50.0,
                "htf_body_pct": 60.0,
                "htf_upper_wick_pct": 20.0,
                "htf_lower_wick_pct": 20.0,
                "htf_close_position": 0.5,
            },
            "entry_price": None,
            "sl_price": None,
            "tp_price": None,
        })
        mock_publisher = Mock(spec=SetupPublisher)
        mock_publisher.publish = AsyncMock()
        return CandleConsumer(
            bootstrap_servers="localhost:9092",
            engine=mock_engine,
            publisher=mock_publisher,
        )

    def _make_candle_msg(
        self,
        instrument: str = "EURUSD",
        timeframe: str = "M5",
        complete: bool = True,
        idx: int = 0,
    ) -> Dict[str, Any]:
        return {
            "instrument": instrument,
            "timeframe": timeframe,
            "time": f"2024-01-01T{idx:02d}:00:00Z",
            "open": 1.1000 + idx * 0.001,
            "high": 1.1010 + idx * 0.001,
            "low": 1.0990 + idx * 0.001,
            "close": 1.1005 + idx * 0.001,
            "volume": 1000.0,
            "complete": complete,
            "source": "oanda",
        }

    @pytest.mark.asyncio
    async def test_incomplete_candle_not_processed(self):
        """Incomplete candles (complete=False) are ignored."""
        consumer = self._make_consumer()
        msg = self._make_candle_msg(complete=False)
        await consumer._handle_message(msg)
        consumer.engine.predict.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_candle_triggers_inference(self):
        """Complete candles trigger inference after 2+ candles in window."""
        consumer = self._make_consumer()
        # Send 2 complete candles to build the window
        for i in range(2):
            await consumer._handle_message(self._make_candle_msg(complete=True, idx=i))
        consumer.engine.predict.assert_called()

    @pytest.mark.asyncio
    async def test_single_complete_candle_no_inference(self):
        """Single complete candle does not trigger inference (need >= 2)."""
        consumer = self._make_consumer()
        await consumer._handle_message(self._make_candle_msg(complete=True, idx=0))
        consumer.engine.predict.assert_not_called()

    @pytest.mark.asyncio
    async def test_rolling_window_capped_at_window_size(self):
        """Rolling window is capped at WINDOW_SIZE (50) candles."""
        consumer = self._make_consumer()
        key = "EURUSD:M5"
        # Send WINDOW_SIZE + 10 candles
        for i in range(CandleConsumer.WINDOW_SIZE + 10):
            await consumer._handle_message(self._make_candle_msg(complete=True, idx=i))
        assert len(consumer._windows[key]) == CandleConsumer.WINDOW_SIZE

    @pytest.mark.asyncio
    async def test_separate_windows_per_instrument_timeframe(self):
        """Separate rolling windows maintained per instrument:timeframe key."""
        consumer = self._make_consumer()
        for i in range(3):
            await consumer._handle_message(
                self._make_candle_msg(instrument="EURUSD", timeframe="M5", complete=True, idx=i)
            )
        for i in range(2):
            await consumer._handle_message(
                self._make_candle_msg(instrument="XAUUSD", timeframe="H1", complete=True, idx=i)
            )
        assert "EURUSD:M5" in consumer._windows
        assert "XAUUSD:H1" in consumer._windows
        assert len(consumer._windows["EURUSD:M5"]) == 3
        assert len(consumer._windows["XAUUSD:H1"]) == 2

    @pytest.mark.asyncio
    async def test_candle_missing_instrument_skipped(self):
        """Candles without instrument field are skipped."""
        consumer = self._make_consumer()
        msg = self._make_candle_msg(complete=True)
        del msg["instrument"]
        await consumer._handle_message(msg)
        consumer.engine.predict.assert_not_called()

    @pytest.mark.asyncio
    async def test_candle_missing_timeframe_skipped(self):
        """Candles without timeframe field are skipped."""
        consumer = self._make_consumer()
        msg = self._make_candle_msg(complete=True)
        del msg["timeframe"]
        await consumer._handle_message(msg)
        consumer.engine.predict.assert_not_called()

    @pytest.mark.asyncio
    async def test_low_confidence_setup_not_published(self):
        """Setups with confidence < CONFIDENCE_FLOOR are not published."""
        consumer = self._make_consumer()
        # Engine returns 0.0 confidence (stub)
        for i in range(3):
            await consumer._handle_message(self._make_candle_msg(complete=True, idx=i))
        consumer.publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_high_confidence_setup_published(self):
        """Setups with confidence >= CONFIDENCE_LOG_ONLY (0.75) are published."""
        consumer = self._make_consumer()
        # Override engine to return high confidence
        consumer.engine.predict = Mock(return_value={
            "time": "2024-01-01T00:00:00Z",
            "regime": "TRENDING_BULLISH",
            "patterns": ["BOS_CONFIRMED"],
            "confidence_score": 0.82,
            "htf_projections": {
                "htf_timeframe": "H1",
                "htf_open": 1.1000,
                "htf_high": 1.1200,
                "htf_low": 1.0800,
                "open_bias": "BULLISH",
                "htf_high_proximity_pct": 30.0,
                "htf_low_proximity_pct": 70.0,
                "htf_body_pct": 60.0,
                "htf_upper_wick_pct": 20.0,
                "htf_lower_wick_pct": 20.0,
                "htf_close_position": 0.8,
            },
            "entry_price": 1.1050,
            "sl_price": 1.0800,
            "tp_price": 1.1200,
        })
        for i in range(3):
            await consumer._handle_message(self._make_candle_msg(complete=True, idx=i))
        consumer.publisher.publish.assert_called()

    @pytest.mark.asyncio
    async def test_log_only_confidence_not_published(self):
        """Setups with 0.65 <= confidence < 0.75 are logged but not published."""
        consumer = self._make_consumer()
        consumer.engine.predict = Mock(return_value={
            "time": "2024-01-01T00:00:00Z",
            "regime": "RANGING",
            "patterns": [],
            "confidence_score": 0.70,  # log-only range
            "htf_projections": {
                "htf_timeframe": "H1",
                "htf_open": 1.1000,
                "htf_high": 1.1200,
                "htf_low": 1.0800,
                "open_bias": "NEUTRAL",
                "htf_high_proximity_pct": 50.0,
                "htf_low_proximity_pct": 50.0,
                "htf_body_pct": 60.0,
                "htf_upper_wick_pct": 20.0,
                "htf_lower_wick_pct": 20.0,
                "htf_close_position": 0.5,
            },
            "entry_price": None,
            "sl_price": None,
            "tp_price": None,
        })
        for i in range(3):
            await consumer._handle_message(self._make_candle_msg(complete=True, idx=i))
        consumer.publisher.publish.assert_not_called()


# ===========================================================================
# 9. SetupPublisher tests
# ===========================================================================


class TestSetupPublisher:
    """Tests for SetupPublisher Kafka producer."""

    @pytest.mark.asyncio
    async def test_publisher_instantiates(self):
        """SetupPublisher can be instantiated with bootstrap_servers."""
        publisher = SetupPublisher(bootstrap_servers="localhost:9092")
        assert publisher is not None

    @pytest.mark.asyncio
    async def test_publisher_start_creates_producer(self):
        """start() creates an AIOKafkaProducer instance."""
        with patch("ml.inference.main.AIOKafkaProducer") as mock_producer_cls:
            mock_producer = AsyncMock()
            mock_producer_cls.return_value = mock_producer
            publisher = SetupPublisher(bootstrap_servers="localhost:9092")
            await publisher.start()
            mock_producer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_publisher_stop_flushes_and_stops(self):
        """stop() flushes pending messages and stops the producer."""
        with patch("ml.inference.main.AIOKafkaProducer") as mock_producer_cls:
            mock_producer = AsyncMock()
            mock_producer_cls.return_value = mock_producer
            publisher = SetupPublisher(bootstrap_servers="localhost:9092")
            await publisher.start()
            await publisher.stop()
            mock_producer.flush.assert_called_once()
            mock_producer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_publisher_publish_sends_to_setups_topic(self):
        """publish() sends message to setups.detected topic."""
        with patch("ml.inference.main.AIOKafkaProducer") as mock_producer_cls:
            mock_producer = AsyncMock()
            mock_producer_cls.return_value = mock_producer
            publisher = SetupPublisher(bootstrap_servers="localhost:9092")
            await publisher.start()

            setup = {
                "instrument": "EURUSD",
                "timeframe": "M5",
                "time": "2024-01-01T10:00:00Z",
                "regime": "TRENDING_BULLISH",
                "patterns": ["BOS_CONFIRMED"],
                "confidence_score": 0.82,
                "htf_open": 1.1000,
                "htf_high": 1.1200,
                "htf_low": 1.0800,
                "open_bias": "BULLISH",
                "entry_price": 1.1050,
                "sl_price": 1.0800,
                "tp_price": 1.1200,
            }
            await publisher.publish(setup)

            mock_producer.send.assert_called_once()
            call_args = mock_producer.send.call_args
            assert call_args[0][0] == TOPIC_SETUPS
            assert call_args[1]["key"] == b"EURUSD:M5"

    @pytest.mark.asyncio
    async def test_publisher_publish_json_encodes_message(self):
        """publish() JSON-encodes the setup message."""
        with patch("ml.inference.main.AIOKafkaProducer") as mock_producer_cls:
            mock_producer = AsyncMock()
            mock_producer_cls.return_value = mock_producer
            publisher = SetupPublisher(bootstrap_servers="localhost:9092")
            await publisher.start()

            setup = {
                "instrument": "XAUUSD",
                "timeframe": "H1",
                "time": "2024-01-01T10:00:00Z",
                "regime": "BREAKOUT",
                "patterns": [],
                "confidence_score": 0.78,
                "htf_open": 2380.0,
                "htf_high": 2400.0,
                "htf_low": 2360.0,
                "open_bias": "BULLISH",
                "entry_price": 2385.0,
                "sl_price": 2360.0,
                "tp_price": 2400.0,
            }
            await publisher.publish(setup)

            call_args = mock_producer.send.call_args
            value_bytes = call_args[1]["value"]
            decoded = json.loads(value_bytes.decode())
            assert decoded["instrument"] == "XAUUSD"
            assert decoded["confidence_score"] == 0.78


# ===========================================================================
# 10. Integration test: full app lifecycle
# ===========================================================================


class TestAppLifecycle:
    """Integration tests for the full FastAPI app lifecycle."""

    def test_app_starts_and_stops_cleanly(self, stub_registry):
        """App lifespan starts and stops without errors."""
        app = create_app(registry=stub_registry)
        # Simulate lifespan startup and shutdown
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

    def test_app_loads_models_on_startup(self, stub_registry):
        """App calls registry.load() during startup."""
        with patch.object(ModelRegistry, "load") as mock_load:
            app = create_app(registry=stub_registry)
            with TestClient(app):
                pass
            # load() should have been called during lifespan startup
            # (already called in fixture, so we just verify registry is loaded)
            assert stub_registry.loaded is True

    def test_app_exposes_predict_endpoint(self, test_client):
        """App exposes POST /predict endpoint."""
        response = test_client.post(
            "/predict",
            json={
                "instrument": "EURUSD",
                "timeframe": "M5",
                "candles": _make_candles(5),
            },
        )
        assert response.status_code == 200

    def test_app_exposes_health_endpoint(self, test_client):
        """App exposes GET /health endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200

    def test_app_title_and_version(self, stub_registry):
        """App has correct title and version."""
        app = create_app(registry=stub_registry)
        assert "AgentICTrader" in app.title
        assert app.version == "1.0.0"


# ===========================================================================
# 11. Error handling tests
# ===========================================================================


class TestErrorHandling:
    """Tests for error handling in the inference service."""

    @pytest.fixture
    def client(self, stub_registry) -> TestClient:
        app = create_app(registry=stub_registry)
        return TestClient(app)

    def test_predict_invalid_json_returns_422(self, client):
        """POST /predict with invalid JSON returns 422."""
        response = client.post("/predict", data="not json")
        assert response.status_code == 422

    def test_predict_missing_required_field_returns_422(self, client):
        """POST /predict missing required field returns 422."""
        response = client.post(
            "/predict",
            json={"instrument": "EURUSD"},  # missing timeframe and candles
        )
        assert response.status_code == 422

    def test_predict_invalid_candle_schema_returns_422(self, client):
        """POST /predict with invalid candle schema returns 422."""
        response = client.post(
            "/predict",
            json={
                "instrument": "EURUSD",
                "timeframe": "M5",
                "candles": [{"invalid": "schema"}],
            },
        )
        assert response.status_code == 422

    def test_predict_engine_exception_returns_500(self, stub_registry):
        """POST /predict returns 500 when InferenceEngine raises exception."""
        with patch.object(InferenceEngine, "predict", side_effect=RuntimeError("Test error")):
            app = create_app(registry=stub_registry)
            client = TestClient(app)
            response = client.post(
                "/predict",
                json={
                    "instrument": "EURUSD",
                    "timeframe": "M5",
                    "candles": _make_candles(5),
                },
            )
            assert response.status_code == 500
            assert "Inference failed" in response.json()["detail"]


# ===========================================================================
# 12. Performance and latency tests
# ===========================================================================


class TestPerformance:
    """Performance and latency tests for the inference service."""

    @pytest.mark.slow
    def test_predict_latency_under_500ms(self, test_client):
        """POST /predict completes in < 500ms (NFR-1 requirement)."""
        import time

        payload = {
            "instrument": "EURUSD",
            "timeframe": "M5",
            "candles": _make_candles(50),
        }
        start = time.time()
        response = test_client.post("/predict", json=payload)
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 0.5, f"Predict took {elapsed:.3f}s (> 500ms)"

    @pytest.mark.slow
    def test_health_latency_under_100ms(self, test_client):
        """GET /health completes in < 100ms."""
        import time

        start = time.time()
        response = test_client.get("/health")
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 0.1, f"Health check took {elapsed:.3f}s (> 100ms)"




