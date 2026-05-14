"""
ML Inference FastAPI Service.

Loads trained models from the MLflow registry and exposes:
  POST /predict  — synchronous inference for a single instrument/timeframe/candles payload
  GET  /health   — liveness check

Also runs a background Kafka consumer that:
  - Consumes completed candles from market.candles
  - Runs the full inference pipeline (feature extraction → regime → patterns → confluence)
  - Publishes detected setups to setups.detected

setups.detected message schema:
  {
    instrument, timeframe, time, regime, patterns, confidence_score,
    htf_open, htf_high, htf_low, open_bias,
    entry_price, sl_price, tp_price
  }

Confidence thresholds (from design.md):
  < 0.65  → DISCARD (not published)
  0.65–0.74 → LOG ONLY (not published)
  ≥ 0.75  → publish to setups.detected

Usage:
    uvicorn ml.inference.main:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import mlflow
import mlflow.sklearn
import numpy as np
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Path setup — allow running from project root
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ml.features.pipeline import FeaturePipeline
from ml.features.htf_selector import get_htf_correlation, TradingStyle

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TOPIC_CANDLES = "market.candles"
TOPIC_SETUPS = "setups.detected"

CONFIDENCE_FLOOR = 0.65    # below this → discard
CONFIDENCE_LOG_ONLY = 0.75  # [0.65, 0.75) → log only, not published

REGIME_CLASSES = [
    "TRENDING_BULLISH",
    "TRENDING_BEARISH",
    "RANGING",
    "BREAKOUT",
    "NEWS_DRIVEN",
]

PATTERN_LABELS = [
    "BOS_CONFIRMED",
    "CHOCH_DETECTED",
    "BEARISH_ARRAY_REJECTION",
    "BULLISH_ARRAY_BOUNCE",
    "FVG_PRESENT",
    "LIQUIDITY_SWEEP",
    "ORDER_BLOCK",
    "INDUCEMENT",
]

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class OHLCVCandle(BaseModel):
    """Single OHLCV candle."""

    time: str = Field(..., description="ISO-8601 UTC timestamp")
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class PredictRequest(BaseModel):
    """Request body for POST /predict."""

    instrument: str = Field(..., description="e.g. EURUSD, XAUUSD, US500")
    timeframe: str = Field(..., description="e.g. M1, M5, M15, H1, H4, D1")
    candles: List[OHLCVCandle] = Field(
        ..., min_length=2, description="Chronological list of OHLCV candles"
    )
    # Optional reference prices for session feature computation
    daily_open: Optional[float] = None
    weekly_open: Optional[float] = None
    true_day_open: Optional[float] = None


class HTFProjections(BaseModel):
    """HTF projection levels returned in the predict response."""

    htf_timeframe: str
    htf_open: float
    htf_high: float
    htf_low: float
    open_bias: str  # BULLISH | BEARISH | NEUTRAL
    htf_high_proximity_pct: float
    htf_low_proximity_pct: float
    htf_body_pct: float
    htf_upper_wick_pct: float
    htf_lower_wick_pct: float
    htf_close_position: float


class PredictResponse(BaseModel):
    """Response body for POST /predict."""

    instrument: str
    timeframe: str
    time: str
    regime: str
    patterns: List[str]
    confidence_score: float
    htf_projections: HTFProjections
    # Derived trade levels (None when confidence < floor)
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
    models_loaded: bool
    kafka_consumer_running: bool


# ---------------------------------------------------------------------------
# Model registry loader
# ---------------------------------------------------------------------------


class ModelRegistry:
    """
    Loads and caches the three trained models from the MLflow registry.

    Falls back to stub predictors when models are not yet registered
    (e.g. during development before training is complete).
    """

    def __init__(self, tracking_uri: Optional[str] = None) -> None:
        self.tracking_uri = tracking_uri or os.getenv(
            "MLFLOW_TRACKING_URI", "http://localhost:5000"
        )
        mlflow.set_tracking_uri(self.tracking_uri)

        self._regime_model: Any = None
        self._pattern_model: Any = None
        self._confluence_model: Any = None
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load all three models from the MLflow registry."""
        self._regime_model = self._load_model("regime-classifier")
        self._pattern_model = self._load_model("pattern-detector")
        self._confluence_model = self._load_model("confluence-scorer")
        self._loaded = True
        logger.info("All models loaded (or stubs installed)")

    @property
    def loaded(self) -> bool:
        return self._loaded

    def predict_regime(self, X: np.ndarray) -> str:
        """Return the predicted regime class label."""
        if self._regime_model is None:
            return "RANGING"  # stub default
        raw = self._regime_model.predict(X)
        idx = int(raw[0])
        if 0 <= idx < len(REGIME_CLASSES):
            return REGIME_CLASSES[idx]
        # Model may return string labels directly
        return str(raw[0])

    def predict_patterns(self, X: np.ndarray, threshold: float = 0.5) -> List[str]:
        """Return list of active pattern labels above threshold."""
        if self._pattern_model is None:
            return []  # stub default
        try:
            proba_list = self._pattern_model.predict_proba(X)
            active = []
            for label_idx, proba in enumerate(proba_list):
                if proba[0, 1] >= threshold:
                    active.append(PATTERN_LABELS[label_idx])
            return active
        except AttributeError:
            # Model doesn't support predict_proba — fall back to predict
            raw = self._pattern_model.predict(X)
            return [
                PATTERN_LABELS[i]
                for i, val in enumerate(raw[0])
                if val == 1 and i < len(PATTERN_LABELS)
            ]

    def predict_confidence(self, X: np.ndarray) -> float:
        """Return calibrated confidence score in [0.0, 1.0]."""
        if self._confluence_model is None:
            return 0.0  # stub default
        proba = self._confluence_model.predict_proba(X)
        return float(proba[0, 1])

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_model(self, model_name: str) -> Optional[Any]:
        """
        Attempt to load the latest Production version of a registered model.

        Returns None (stub) if the model is not yet registered.
        """
        try:
            client = mlflow.tracking.MlflowClient()
            versions = client.get_latest_versions(model_name, stages=["Production"])
            if not versions:
                # Fall back to any registered version
                versions = client.get_latest_versions(model_name)
            if not versions:
                logger.warning(
                    "Model '%s' not found in registry — using stub predictor", model_name
                )
                return None
            model_uri = f"models:/{model_name}/{versions[0].version}"
            model = mlflow.sklearn.load_model(model_uri)
            logger.info("Loaded model '%s' version %s", model_name, versions[0].version)
            return model
        except Exception as exc:
            logger.warning(
                "Could not load model '%s': %s — using stub predictor", model_name, exc
            )
            return None


# ---------------------------------------------------------------------------
# Inference engine
# ---------------------------------------------------------------------------


class InferenceEngine:
    """
    Orchestrates feature extraction and model inference for a single setup.

    Accepts a list of OHLCV candles, extracts features via FeaturePipeline,
    runs the three models, and returns a structured prediction.
    """

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry
        self.pipeline = FeaturePipeline(enable_validation=False)

    def predict(
        self,
        instrument: str,
        timeframe: str,
        candles: List[Dict[str, Any]],
        daily_open: Optional[float] = None,
        weekly_open: Optional[float] = None,
        true_day_open: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run full inference pipeline for a single instrument/timeframe/candles payload.

        Args:
            instrument: Trading instrument (e.g. "EURUSD")
            timeframe: Candle timeframe (e.g. "M5")
            candles: Chronological list of OHLCV dicts
            daily_open: Optional daily open reference price
            weekly_open: Optional weekly open reference price
            true_day_open: Optional true day open reference price

        Returns:
            Dict with keys: regime, patterns, confidence_score, htf_projections,
                            entry_price, sl_price, tp_price, time
        """
        if len(candles) < 2:
            raise ValueError("At least 2 candles are required for inference")

        # Determine HTF timeframe using the 3-tier correlation
        htf_timeframe = self._get_htf_timeframe(timeframe)

        # Use the most recent candle as the HTF candle proxy when no separate
        # HTF feed is available (the pipeline will use it for HTF projections)
        htf_candle = self._build_htf_candle(candles, htf_timeframe)

        # Extract features
        features_df = self.pipeline.transform(
            candles=candles,
            htf_candle=htf_candle,
            instrument=instrument,
            htf_timeframe=htf_timeframe,
            daily_open=daily_open,
            weekly_open=weekly_open,
            true_day_open=true_day_open,
        )

        # Encode for sklearn models
        X = self._encode_features(features_df)

        # Run models
        regime = self.registry.predict_regime(X)
        patterns = self.registry.predict_patterns(X)
        confidence_score = self.registry.predict_confidence(X)

        # Extract HTF projection values from features
        htf_proj = self._extract_htf_projections(features_df, htf_timeframe)

        # Derive trade levels from the last candle and HTF levels
        current_candle = candles[-1]
        entry_price, sl_price, tp_price = self._derive_trade_levels(
            current_candle=current_candle,
            htf_proj=htf_proj,
            confidence_score=confidence_score,
        )

        # Timestamp from the most recent candle
        time_str = str(current_candle.get("time", datetime.now(timezone.utc).isoformat()))

        return {
            "time": time_str,
            "regime": regime,
            "patterns": patterns,
            "confidence_score": confidence_score,
            "htf_projections": htf_proj,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_htf_timeframe(self, timeframe: str) -> str:
        """Derive the HTF timeframe using the INTRADAY_STANDARD 3-tier correlation."""
        try:
            bias_tf, structure_tf, entry_tf = get_htf_correlation(
                timeframe, TradingStyle.INTRADAY_STANDARD
            )
            return bias_tf
        except (ValueError, KeyError):
            # Fallback mapping for timeframes not in the selector
            _fallback = {
                "M1": "M5", "M3": "M15", "M5": "M15",
                "M15": "H1", "M30": "H4", "H1": "H4",
                "H4": "D1", "D1": "W1", "W1": "D1",
            }
            return _fallback.get(timeframe, "H1")

    def _build_htf_candle(
        self, candles: List[Dict[str, Any]], htf_timeframe: str
    ) -> Dict[str, Any]:
        """
        Build a synthetic HTF candle from the provided candle list.

        In production the HTF candle would be fetched from TimescaleDB.
        Here we aggregate the provided candles into a single OHLCV candle
        to represent the HTF period.
        """
        opens = [float(c["open"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        closes = [float(c["close"]) for c in candles]
        volumes = [float(c.get("volume", 0)) for c in candles]

        return {
            "time": candles[0]["time"],
            "open": opens[0],
            "high": max(highs),
            "low": min(lows),
            "close": closes[-1],
            "volume": sum(volumes),
        }

    def _encode_features(self, features_df) -> np.ndarray:
        """Encode the feature DataFrame to a numeric numpy array for sklearn."""
        import pandas as pd

        df = features_df.copy()

        # Encode string/bool columns
        bias_map = {"BULLISH": 1, "NEUTRAL": 0, "BEARISH": -1}
        pos_map = {"ABOVE": 1, "AT": 0, "BELOW": -1}

        for col in df.columns:
            if df[col].dtype == bool:
                df[col] = df[col].astype(int)
            elif col in ("htf_open_bias", "htf_trend_bias"):
                df[col] = df[col].map(bias_map).fillna(0)
            elif col in ("price_vs_daily_open", "price_vs_weekly_open", "price_vs_true_day_open"):
                df[col] = df[col].map(pos_map).fillna(0)
            elif df[col].dtype == object:
                df[col] = pd.Categorical(df[col]).codes

        return df.values.astype(float)

    def _extract_htf_projections(
        self, features_df, htf_timeframe: str
    ) -> Dict[str, Any]:
        """Extract HTF projection values from the feature DataFrame."""
        row = features_df.iloc[0]
        return {
            "htf_timeframe": htf_timeframe,
            "htf_open": float(row.get("htf_open", 0.0)),
            "htf_high": float(row.get("htf_high", 0.0)),
            "htf_low": float(row.get("htf_low", 0.0)),
            "open_bias": str(row.get("htf_open_bias", "NEUTRAL")),
            "htf_high_proximity_pct": float(row.get("htf_high_proximity_pct", 50.0)),
            "htf_low_proximity_pct": float(row.get("htf_low_proximity_pct", 50.0)),
            "htf_body_pct": float(row.get("htf_body_pct", 0.0)),
            "htf_upper_wick_pct": float(row.get("htf_upper_wick_pct", 0.0)),
            "htf_lower_wick_pct": float(row.get("htf_lower_wick_pct", 0.0)),
            "htf_close_position": float(row.get("htf_close_position", 50.0)),
        }

    def _derive_trade_levels(
        self,
        current_candle: Dict[str, Any],
        htf_proj: Dict[str, Any],
        confidence_score: float,
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Derive entry, SL, and TP prices from the current candle and HTF levels.

        Returns (None, None, None) when confidence is below the floor.

        Logic:
          - Bullish: entry = current close, SL = HTF low, TP = HTF high
          - Bearish: entry = current close, SL = HTF high, TP = HTF low
          - Neutral: no trade levels
        """
        if confidence_score < CONFIDENCE_FLOOR:
            return None, None, None

        close = float(current_candle["close"])
        htf_high = htf_proj["htf_high"]
        htf_low = htf_proj["htf_low"]
        open_bias = htf_proj["open_bias"]

        if open_bias == "BULLISH":
            entry_price = close
            sl_price = htf_low
            tp_price = htf_high
        elif open_bias == "BEARISH":
            entry_price = close
            sl_price = htf_high
            tp_price = htf_low
        else:
            return None, None, None

        # Sanity check: SL must differ from entry
        if abs(entry_price - sl_price) < 1e-8:
            return None, None, None

        return entry_price, sl_price, tp_price


# ---------------------------------------------------------------------------
# Kafka consumer
# ---------------------------------------------------------------------------


class SetupPublisher:
    """Publishes detected setups to the setups.detected Kafka topic."""

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer:
            await self._producer.flush()
            await self._producer.stop()

    async def publish(self, setup: Dict[str, Any]) -> None:
        if self._producer is None:
            return
        key = f"{setup['instrument']}:{setup['timeframe']}".encode()
        value = json.dumps(setup, default=str).encode()
        await self._producer.send(TOPIC_SETUPS, key=key, value=value)


class CandleConsumer:
    """
    Kafka consumer that reads from market.candles and runs inference.

    For each completed candle:
      1. Accumulate a rolling window of candles per instrument/timeframe
      2. Run InferenceEngine.predict()
      3. If confidence >= 0.75, publish to setups.detected
    """

    # Rolling window size per instrument:timeframe key
    WINDOW_SIZE = 50

    def __init__(
        self,
        bootstrap_servers: str,
        engine: InferenceEngine,
        publisher: SetupPublisher,
        group_id: str = "ml-inference-service",
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.engine = engine
        self.publisher = publisher
        self.group_id = group_id
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        # Rolling candle windows: key = "instrument:timeframe"
        self._windows: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            TOPIC_CANDLES,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda v: json.loads(v.decode()),
            auto_offset_reset="latest",
        )
        await self._consumer.start()
        self._running = True
        logger.info("Kafka consumer started — listening on %s", TOPIC_CANDLES)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()

    async def run(self) -> None:
        """Main consume loop — runs until stop() is called."""
        if self._consumer is None:
            raise RuntimeError("Consumer not started — call start() first")

        async for msg in self._consumer:
            if not self._running:
                break
            try:
                await self._handle_message(msg.value)
            except Exception as exc:
                logger.error("Error handling candle message: %s", exc, exc_info=True)

    async def _handle_message(self, candle: Dict[str, Any]) -> None:
        """Process a single candle message."""
        # Only process completed candles
        if not candle.get("complete", False):
            return

        instrument = candle.get("instrument", "")
        timeframe = candle.get("timeframe", "")
        if not instrument or not timeframe:
            return

        key = f"{instrument}:{timeframe}"

        # Maintain rolling window
        window = self._windows.setdefault(key, [])
        window.append(candle)
        if len(window) > self.WINDOW_SIZE:
            window.pop(0)

        # Need at least 2 candles for inference
        if len(window) < 2:
            return

        # Run inference
        result = self.engine.predict(
            instrument=instrument,
            timeframe=timeframe,
            candles=window,
        )

        confidence = result["confidence_score"]

        if confidence < CONFIDENCE_FLOOR:
            logger.debug(
                "Setup discarded (confidence=%.3f < %.2f): %s %s",
                confidence, CONFIDENCE_FLOOR, instrument, timeframe,
            )
            return

        if confidence < CONFIDENCE_LOG_ONLY:
            logger.info(
                "Setup logged only (confidence=%.3f): %s %s — regime=%s patterns=%s",
                confidence, instrument, timeframe, result["regime"], result["patterns"],
            )
            return

        # Build setups.detected message
        htf = result["htf_projections"]
        setup_msg: Dict[str, Any] = {
            "instrument": instrument,
            "timeframe": timeframe,
            "time": result["time"],
            "regime": result["regime"],
            "patterns": result["patterns"],
            "confidence_score": confidence,
            "htf_open": htf["htf_open"],
            "htf_high": htf["htf_high"],
            "htf_low": htf["htf_low"],
            "open_bias": htf["open_bias"],
            "entry_price": result["entry_price"],
            "sl_price": result["sl_price"],
            "tp_price": result["tp_price"],
        }

        await self.publisher.publish(setup_msg)
        logger.info(
            "Setup published (confidence=%.3f): %s %s regime=%s patterns=%s",
            confidence, instrument, timeframe, result["regime"], result["patterns"],
        )


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(
    registry: Optional[ModelRegistry] = None,
    consumer: Optional[CandleConsumer] = None,
    skip_kafka: bool = False,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        registry: Pre-built ModelRegistry (injected for testing)
        consumer: Pre-built CandleConsumer (injected for testing)
        skip_kafka: When True, skip Kafka consumer/producer startup entirely.
                    Automatically set to True when a registry is injected (test mode).

    Returns:
        Configured FastAPI application
    """
    _registry = registry or ModelRegistry()
    _consumer_ref: Dict[str, Any] = {"instance": consumer}
    _consumer_task: Dict[str, Any] = {"task": None}
    # Skip Kafka when a registry is injected (test mode) or explicitly requested
    _skip_kafka = skip_kafka or (registry is not None and consumer is None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup — only load models if not already loaded (e.g. injected in tests)
        if not _registry.loaded:
            _registry.load()

        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

        if not _skip_kafka and _consumer_ref["instance"] is None:
            engine = InferenceEngine(_registry)
            publisher = SetupPublisher(bootstrap)
            try:
                await asyncio.wait_for(publisher.start(), timeout=5.0)
            except (Exception, asyncio.TimeoutError) as exc:
                logger.warning("Kafka publisher unavailable: %s", exc)

            _consumer_ref["instance"] = CandleConsumer(
                bootstrap_servers=bootstrap,
                engine=engine,
                publisher=publisher,
            )
            try:
                await asyncio.wait_for(_consumer_ref["instance"].start(), timeout=5.0)
                _consumer_task["task"] = asyncio.create_task(
                    _consumer_ref["instance"].run()
                )
            except (Exception, asyncio.TimeoutError) as exc:
                logger.warning("Kafka consumer unavailable: %s", exc)

        yield

        # Shutdown
        if _consumer_task["task"]:
            _consumer_task["task"].cancel()
            try:
                await _consumer_task["task"]
            except asyncio.CancelledError:
                pass
        if _consumer_ref["instance"]:
            try:
                await _consumer_ref["instance"].stop()
            except Exception:
                pass

    app = FastAPI(
        title="AgentICTrader ML Inference Service",
        description=(
            "Loads regime-classifier, pattern-detector, and confluence-scorer "
            "from MLflow and exposes a /predict endpoint. Also consumes "
            "market.candles and publishes to setups.detected."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Liveness check."""
        consumer_running = (
            _consumer_ref["instance"] is not None
            and _consumer_ref["instance"].running
        )
        return HealthResponse(
            status="ok",
            models_loaded=_registry.loaded,
            kafka_consumer_running=consumer_running,
        )

    @app.post("/predict", response_model=PredictResponse)
    async def predict(request: PredictRequest) -> PredictResponse:
        """
        Run ML inference for a given instrument/timeframe/candles payload.

        Returns regime classification, detected patterns, confidence score,
        HTF projection levels, and derived trade levels.
        """
        if len(request.candles) < 2:
            raise HTTPException(
                status_code=422,
                detail="At least 2 candles are required for inference",
            )

        candles_dicts = [c.model_dump() for c in request.candles]

        engine = InferenceEngine(_registry)
        try:
            result = engine.predict(
                instrument=request.instrument,
                timeframe=request.timeframe,
                candles=candles_dicts,
                daily_open=request.daily_open,
                weekly_open=request.weekly_open,
                true_day_open=request.true_day_open,
            )
        except Exception as exc:
            logger.error("Inference error: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Inference failed: {exc}")

        htf = result["htf_projections"]
        return PredictResponse(
            instrument=request.instrument,
            timeframe=request.timeframe,
            time=result["time"],
            regime=result["regime"],
            patterns=result["patterns"],
            confidence_score=result["confidence_score"],
            htf_projections=HTFProjections(
                htf_timeframe=htf["htf_timeframe"],
                htf_open=htf["htf_open"],
                htf_high=htf["htf_high"],
                htf_low=htf["htf_low"],
                open_bias=htf["open_bias"],
                htf_high_proximity_pct=htf["htf_high_proximity_pct"],
                htf_low_proximity_pct=htf["htf_low_proximity_pct"],
                htf_body_pct=htf["htf_body_pct"],
                htf_upper_wick_pct=htf["htf_upper_wick_pct"],
                htf_lower_wick_pct=htf["htf_lower_wick_pct"],
                htf_close_position=htf["htf_close_position"],
            ),
            entry_price=result["entry_price"],
            sl_price=result["sl_price"],
            tp_price=result["tp_price"],
        )

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ml.inference.main:app",
        host="0.0.0.0",
        port=int(os.getenv("INFERENCE_PORT", "8001")),
        reload=False,
    )
