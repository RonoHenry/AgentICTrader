"""
Thin synchronous HTTP client for services/visual_model.

Matches this codebase's convention of dependency-injected, synchronous node
collaborators (redis_client in analyse_node, risk_engine in decide_node)
rather than an async HTTP client - analyse_node itself is a plain `def`, not
`async def`.

Never raises to the caller. A connection error, timeout, or any unexpected
failure degrades to a neutral VisualAnalysisResponse - identical in shape to
what services/visual_model itself returns on its own internal failures
(see services/visual_model/api/router.py). analyse_node treats "client threw"
and "service returned degraded=True" the same way: proceed numerical-only.

**Validates: Requirement 12.1 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

import httpx

from services.visual_model.api.schemas import VisualAnalysisResponse

logger = logging.getLogger(__name__)


def _degraded() -> VisualAnalysisResponse:
    return VisualAnalysisResponse(
        analysis=None, visual_modifier=0.0, hard_block_reason=None, degraded=True
    )


class VisualModelClient:
    def __init__(
        self,
        base_url: str = "http://visual-model:8005",
        timeout: float = 8.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def analyse(
        self,
        candles_by_tf: Dict[Any, List[Any]],
        liquidity_map: Optional[Any],
        instrument: str,
        timestamp: datetime,
        numerical_direction: Optional[Literal["BULLISH", "BEARISH"]] = None,
        session: Optional[str] = None,
        kill_zone: Optional[str] = None,
    ) -> VisualAnalysisResponse:
        try:
            payload = {
                "instrument": instrument,
                "timestamp": timestamp.isoformat(),
                "candles_by_tf": {
                    (tf.value if hasattr(tf, "value") else str(tf)): [
                        c.model_dump(mode="json") for c in candles
                    ]
                    for tf, candles in candles_by_tf.items()
                },
                "liquidity_map": (
                    liquidity_map.model_dump(mode="json") if liquidity_map is not None else None
                ),
                "session": session,
                "kill_zone": kill_zone,
                "numerical_direction": numerical_direction,
            }
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(f"{self._base_url}/visual/analyse", json=payload)
                response.raise_for_status()
                return VisualAnalysisResponse.model_validate(response.json())
        except Exception as exc:
            logger.warning("visual_model_client: call failed, degrading: %s", exc)
            return _degraded()
