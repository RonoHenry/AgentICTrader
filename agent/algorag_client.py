"""
Thin synchronous HTTP client for services/algorag.

Matches this codebase's convention of dependency-injected, synchronous node
collaborators (redis_client and visual_model_client in analyse_node) rather
than the async ml/algorag/client.py::AlgoRAGClient — analyse_node itself is
a plain `def`, not `async def`. ml/algorag/client.py remains the right
client for genuinely async callers (e.g. ml/inference); this one exists
only so analyse_node can call AlgoRAG without pulling asyncio into the
sync agent graph.

Never raises to the caller. A connection error, timeout, or any unexpected
failure degrades to a neutral AlgoRAGResult (no similar setups, zero
modifier) — analyse_node treats "client threw" and "AlgoRAG unavailable"
the same way: proceed without the RAG modifier, same as the visual model
integration degrades to numerical-only.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

import httpx
from pydantic import BaseModel

from services.algorag.models import RAGMetrics, SimilarSetup

logger = logging.getLogger(__name__)

# Below this many retrieved examples, win-rate/R-multiple stats are too
# noisy to act on — mirrors the RAG service's own minimum-sample-size
# validation for its aggregate metrics (rag-enhancement spec task 11).
_MIN_SAMPLE_SIZE = 3

# win_rate_similar=1.0 -> +_RAG_MODIFIER_CAP, 0.0 -> -_RAG_MODIFIER_CAP,
# 0.5 (no edge) -> 0.0. Capped lower than the visual model's ±0.15 since
# this is corroborating evidence over an independent read, not a fresh one.
_RAG_MODIFIER_CAP = 0.10


class AlgoRAGResult(BaseModel):
    similar_setups: List[SimilarSetup] = []
    rag_metrics: Optional[RAGMetrics] = None
    rag_modifier: float = 0.0
    degraded: bool = False


def _degraded() -> AlgoRAGResult:
    return AlgoRAGResult(similar_setups=[], rag_metrics=None, rag_modifier=0.0, degraded=True)


def _compute_modifier(metrics: RAGMetrics) -> float:
    if metrics.sample_size < _MIN_SAMPLE_SIZE:
        return 0.0
    edge = metrics.win_rate_similar - 0.5
    modifier = edge * (_RAG_MODIFIER_CAP / 0.5)
    return max(-_RAG_MODIFIER_CAP, min(_RAG_MODIFIER_CAP, modifier))


class AlgoRAGSyncClient:
    def __init__(self, base_url: str = "http://algorag:8003", timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def retrieve(
        self,
        instrument: str,
        timestamp: datetime,
        narrative: Optional[str] = None,
        time_window: Optional[str] = None,
        htf_open_bias: Optional[str] = None,
        top_k: int = 10,
    ) -> AlgoRAGResult:
        try:
            payload = {
                "instrument": instrument,
                "timestamp": timestamp.isoformat(),
                "time_window": time_window,
                "htf_open_bias": htf_open_bias,
                "narrative": narrative,
                "top_k": top_k,
            }
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(f"{self._base_url}/rag/retrieve", json=payload)
                response.raise_for_status()
                data = response.json()

            metrics = RAGMetrics.model_validate(data["rag_metrics"])
            similar_setups = [
                SimilarSetup.model_validate(s) for s in data.get("similar_setups", [])
            ]
            return AlgoRAGResult(
                similar_setups=similar_setups,
                rag_metrics=metrics,
                rag_modifier=_compute_modifier(metrics),
                degraded=False,
            )
        except Exception as exc:
            logger.warning("algorag_client: call failed, degrading: %s", exc)
            return _degraded()
