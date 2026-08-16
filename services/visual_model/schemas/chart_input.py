"""
Input validation schemas for chart rendering / analysis requests.

**Validates: Requirements 10.1 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel

from pd_array_engine.models import Candle, LiquidityMap, Timeframe


class ChartAnalysisRequest(BaseModel):
    instrument: str
    timestamp: datetime
    candles_by_tf: Dict[Timeframe, List[Candle]]
    liquidity_map: Optional[LiquidityMap] = None
    session: Optional[str] = None
    kill_zone: Optional[str] = None
    # Plain string, not agent.state.Direction - this service must stay
    # importable and deployable independently of the agent package.
    numerical_direction: Optional[Literal["BULLISH", "BEARISH"]] = None


class ChartRenderRequest(BaseModel):
    instrument: str
    timestamp: datetime
    candles_by_tf: Dict[Timeframe, List[Candle]]
    liquidity_map: Optional[LiquidityMap] = None
