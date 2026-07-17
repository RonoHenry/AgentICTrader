"""
AlgoRAG Pydantic models for request/response validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------


class SimilarSetup(BaseModel):
    """A single historical setup returned by the retrieval endpoint."""

    trade_id: str = Field(..., description="Unique identifier of the historical trade")
    timestamp: datetime = Field(..., description="Entry timestamp of the historical setup")
    instrument: str = Field(..., description="Trading instrument, e.g. EURUSD")
    time_window: str = Field(..., description="Killzone/session label, e.g. LONDON_KILLZONE")
    htf_open_bias: str = Field(..., description="Higher time-frame directional bias")
    confluence_count: int = Field(..., ge=0, description="Number of confluence factors present")
    outcome_result: str = Field(..., description="WIN or LOSS")
    outcome_r_multiple: float = Field(..., description="R-multiple achieved by the trade")
    narrative: str = Field(..., description="Human-readable setup description")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Raw cosine similarity (0-1)")
    final_score: float = Field(..., ge=0.0, le=1.0, description="Re-ranked composite score (0-1)")
    full_setup: Optional[Dict[str, Any]] = Field(None, description="Full enriched setup payload")


class RAGMetrics(BaseModel):
    """Aggregate statistics computed from the top retrieved setups."""

    avg_r_multiple_similar: float = Field(..., description="Mean R-multiple of similar setups")
    win_rate_similar: float = Field(..., ge=0.0, le=1.0, description="Win rate of similar setups")
    sample_size: int = Field(..., ge=0, description="Number of setups used in computation")
    max_similarity_score: float = Field(..., ge=0.0, le=1.0, description="Highest similarity score")
    avg_confluence_count: float = Field(..., ge=0.0, description="Mean confluence count")


# ---------------------------------------------------------------------------
# Retrieval endpoint models
# ---------------------------------------------------------------------------


class RetrievalRequest(BaseModel):
    """Input to POST /rag/retrieve."""

    instrument: str = Field(..., description="Trading instrument, e.g. EURUSD")
    timestamp: datetime = Field(..., description="Current bar / signal timestamp")
    time_window: Optional[str] = Field(None, description="Killzone filter, e.g. LONDON_KILLZONE")
    htf_open_bias: Optional[str] = Field(None, description="HTF bias filter: BULLISH | BEARISH")
    narrative: Optional[str] = Field(None, description="Narrative text of the current setup")
    htf_structure: Optional[Dict[str, Any]] = Field(None, description="HTF structure context")
    pd_arrays: Optional[Dict[str, Any]] = Field(None, description="PD array detections")
    confluence_factors: Optional[List[str]] = Field(None, description="Active confluence labels")
    top_k: int = Field(10, ge=1, le=50, description="Max candidates before re-ranking")
    outcome_filter: Optional[str] = Field(
        "WIN", description="Restrict retrieval to WIN | LOSS | None for all"
    )

    @field_validator("instrument")
    @classmethod
    def instrument_uppercase(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("instrument cannot be empty")
        return v.upper()


class RetrievalResponse(BaseModel):
    """Output from POST /rag/retrieve."""

    similar_setups: List[SimilarSetup] = Field(default_factory=list)
    rag_metrics: RAGMetrics
    query_time_ms: float = Field(..., ge=0.0, description="End-to-end retrieval latency in ms")


# ---------------------------------------------------------------------------
# Ingestion endpoint models
# ---------------------------------------------------------------------------


class IngestionRequest(BaseModel):
    """Input to POST /rag/ingest."""

    setup: Dict[str, Any] = Field(..., description="Enriched setup document")
    embedding: List[float] = Field(..., description="Pre-computed 528-dim embedding vector")

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dim(cls, v: List[float]) -> List[float]:
        if len(v) != 528:
            raise ValueError(f"Embedding must be 528-dimensional, got {len(v)}")
        return v


class IngestionResponse(BaseModel):
    """Output from POST /rag/ingest."""

    status: str = Field(..., description="'success' or 'updated'")
    setup_id: str = Field(..., description="UUID assigned by Qdrant")


# ---------------------------------------------------------------------------
# Health check model
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Output from GET /health."""

    status: str = Field(..., description="'healthy' | 'degraded' | 'unhealthy'")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    vector_store: str = Field(..., description="'connected' | 'disconnected'")
    setup_count: int = Field(..., ge=0, description="Total indexed setups")
