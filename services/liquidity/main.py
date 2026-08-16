"""
Liquidity Engine FastAPI service.

Provides:
  GET  /health   - liveness
  POST /analyze  - run LiquidityMappingEngine.analyze() over supplied candles
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pd_array_engine import LiquidityMappingEngine
from pd_array_engine.models import Candle, Timeframe

app = FastAPI(title="Liquidity Engine Service")
_engine = LiquidityMappingEngine()


class CandleInput(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int] = None


class AnalyzeRequest(BaseModel):
    instrument: str
    timestamp: datetime
    candles_by_tf: Dict[str, List[CandleInput]]


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> Dict[str, Any]:
    candles_by_tf: Dict[Timeframe, List[Candle]] = {}
    for tf_key, candle_inputs in request.candles_by_tf.items():
        try:
            tf = Timeframe(tf_key)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown timeframe: {tf_key}")
        candles_by_tf[tf] = [
            Candle(
                timestamp=c.timestamp, open=c.open, high=c.high, low=c.low, close=c.close,
                volume=c.volume, timeframe=tf, instrument=request.instrument,
            )
            for c in candle_inputs
        ]

    try:
        liquidity_map = _engine.analyze(candles_by_tf, request.instrument, request.timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return liquidity_map.model_dump(mode="json")
