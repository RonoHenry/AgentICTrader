"""
AlgoRAG FastAPI service.

Provides:
  GET  /health          – liveness + readiness with Qdrant connectivity
  POST /rag/retrieve    – retrieve similar historical setups
  POST /rag/ingest      – ingest a new enriched setup + embedding
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, status
from qdrant_client.http.exceptions import UnexpectedResponse

from services.algorag.config import settings
from services.algorag.models import (
    HealthResponse,
    IngestionRequest,
    IngestionResponse,
    RetrievalRequest,
    RetrievalResponse,
    RAGMetrics,
    SimilarSetup,
)
from services.algorag.qdrant_client import QdrantClientWrapper
from services.algorag.reranking import ReRankingConfig
from services.algorag.diversity import apply_diversity_filter
from services.algorag.embedding_generation import generate_query_embedding

logging.basicConfig(level=settings.service.log_level)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application state (populated during lifespan)
# ---------------------------------------------------------------------------

_qdrant_client: QdrantClientWrapper | None = None

# Default re-ranking configuration (can be made configurable via env vars)
_reranking_config = ReRankingConfig(
    outcome_weight=0.5,
    recency_weight=0.3,
    confluence_weight=0.2,
    recency_half_life_days=90.0,
    max_r_multiple=10.0,
)


def get_qdrant() -> QdrantClientWrapper:
    if _qdrant_client is None:
        raise RuntimeError("Qdrant client not initialised")
    return _qdrant_client


# ---------------------------------------------------------------------------
# Lifespan – connect / disconnect from Qdrant
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _qdrant_client
    logger.info(
        "Connecting to Qdrant at %s:%s …",
        settings.qdrant.host,
        settings.qdrant.port,
    )
    wrapper = QdrantClientWrapper()
    _qdrant_client = wrapper
    try:
        await wrapper.ensure_collection()
    except Exception as exc:
        logger.warning("Could not ensure Qdrant collection on startup: %s", exc)
    logger.info("Qdrant client ready")
    yield
    logger.info("Closing Qdrant client")
    await wrapper.close()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AlgoRAG",
    description="Retrieval-Augmented Generation service for AgentICTrader",
    version=settings.service.version,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


async def _get_setup_count(wrapper) -> int:
    """Return the number of vectors in the trading_setups collection (0 if absent).

    Supports QdrantClientWrapper (preferred) and raw AsyncQdrantClient / mock objects
    for backward-compatibility with existing test fixtures.
    """
    if isinstance(wrapper, QdrantClientWrapper):
        return await wrapper.count()
    # Fallback: raw AsyncQdrantClient or duck-typed mock (used by test_health.py)
    try:
        info = await wrapper.get_collection(settings.qdrant.collection)
        return info.points_count or 0
    except Exception:
        return 0


async def _check_qdrant_health(wrapper) -> bool:
    """Return True if Qdrant responds to a health probe.

    Supports QdrantClientWrapper (preferred) and raw AsyncQdrantClient / mock objects
    for backward-compatibility with existing test fixtures.
    """
    if isinstance(wrapper, QdrantClientWrapper):
        return await wrapper.is_healthy()
    # Fallback: raw AsyncQdrantClient or duck-typed mock (used by test_health.py)
    try:
        await wrapper.get_collections()
        return True
    except Exception:
        return False


def _build_rag_metrics(setups: list[SimilarSetup]) -> RAGMetrics:
    """Compute aggregate RAG metrics from the top-5 retrieved setups."""
    top = setups[:5]
    if not top:
        return RAGMetrics(
            avg_r_multiple_similar=0.0,
            win_rate_similar=0.0,
            sample_size=0,
            max_similarity_score=0.0,
            avg_confluence_count=0.0,
        )
    wins = sum(1 for s in top if s.outcome_result == "WIN")
    return RAGMetrics(
        avg_r_multiple_similar=sum(s.outcome_r_multiple for s in top) / len(top),
        win_rate_similar=wins / len(top),
        sample_size=len(top),
        max_similarity_score=max(s.similarity_score for s in top),
        avg_confluence_count=sum(s.confluence_count for s in top) / len(top),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["observability"])
async def health_check() -> HealthResponse:
    """
    Liveness + readiness probe.

    Returns the Qdrant connectivity status and the total number of indexed
    setups so that orchestration layers (Docker, K8s) can verify the service
    is ready to serve traffic.
    """
    wrapper = get_qdrant()
    is_connected = await _check_qdrant_health(wrapper)
    setup_count = await _get_setup_count(wrapper) if is_connected else 0

    return HealthResponse(
        status="healthy" if is_connected else "degraded",
        service="algorag",
        version=settings.service.version,
        vector_store="connected" if is_connected else "disconnected",
        setup_count=setup_count,
    )


@app.post(
    "/rag/retrieve",
    response_model=RetrievalResponse,
    status_code=status.HTTP_200_OK,
    tags=["rag"],
)
async def retrieve_similar_setups(request: RetrievalRequest) -> RetrievalResponse:
    """
    Retrieve historically similar trading setups using vector search.

    Steps:
      1. Generate query embedding from the request 
      2. Apply metadata filters (instrument, time window, HTF bias, outcome)
      3. Run cosine similarity search against Qdrant
      4. Re-rank results (outcome quality + recency + confluence overlap)
      5. Apply diversity filtering (max 3 setups per day)
      6. Compute aggregate RAG metrics
    """
    t0 = time.perf_counter()
    wrapper = get_qdrant()
    
    try:
        # Generate query embedding from request (Task 10.3)
        query_vector = generate_query_embedding(request)
        
        # Build Qdrant filter using the new filtering module
        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)
        
        # Execute vector search with timeout
        import asyncio
        
        async def search_with_timeout():
            return await wrapper.search(
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=request.top_k,
            )
        
        # Apply retrieval timeout (REFACTOR: configurable timeout)
        try:
            hits = await asyncio.wait_for(
                search_with_timeout(), 
                timeout=settings.service.retrieval_timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Qdrant search timeout after %.1fs for instrument=%s", 
                settings.service.retrieval_timeout, 
                request.instrument
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Vector search timeout - please try again",
            )
            
    except HTTPException:
        # Re-raise HTTPExceptions (these are intended for the client)
        raise
    except Exception as exc:
        logger.error(
            "Vector search failed for instrument=%s, error=%s", 
            request.instrument, 
            exc, 
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector store unavailable",
        ) from exc

    # Map hits → SimilarSetup objects
    similar: list[SimilarSetup] = []
    for hit in hits:
        try:
            p = hit.payload or {}
            similar.append(
                SimilarSetup(
                    trade_id=p.get("trade_id", ""),
                    timestamp=p.get("timestamp"),
                    instrument=p.get("instrument", request.instrument),
                    time_window=p.get("time_window", ""),
                    htf_open_bias=p.get("htf_open_bias", ""),
                    confluence_count=p.get("confluence_count", 0),
                    outcome_result=p.get("outcome_result", ""),
                    outcome_r_multiple=p.get("outcome_r_multiple", 0.0),
                    narrative=p.get("narrative", ""),
                    similarity_score=hit.score,
                    final_score=hit.score,  # Will be updated by re-ranking
                    full_setup=p.get("full_setup"),
                )
            )
        except Exception as exc:
            logger.warning(
                "Failed to parse search hit %s: %s", 
                getattr(hit, 'id', 'unknown'),
                exc
            )
            # Skip malformed hits but continue processing others
            continue

    # Apply re-ranking algorithm (Task 10.4)
    try:
        from services.algorag.reranking import rerank_setups
        
        current_confluence_count = len(request.confluence_factors or [])
        reranked = rerank_setups(
            setups=similar,
            current_confluence_count=current_confluence_count,
            current_timestamp=request.timestamp,
            config=_reranking_config,  # Use configurable re-ranking weights
        )
    except Exception as exc:
        logger.warning("Re-ranking failed, using similarity order: %s", exc)
        # Fallback: sort by similarity score if re-ranking fails
        reranked = sorted(similar, key=lambda s: s.similarity_score, reverse=True)

    # Apply diversity filtering (max N setups from same calendar day, configurable)
    try:
        diverse = apply_diversity_filter(reranked, max_per_day=settings.service.diversity_max_per_day)
    except Exception as exc:
        logger.warning("Diversity filtering failed, using re-ranked results: %s", exc)
        # Fallback: use reranked results if diversity filtering fails
        diverse = reranked

    # Compute RAG metrics from final results
    try:
        rag_metrics = _build_rag_metrics(diverse)
    except Exception as exc:
        logger.warning("RAG metrics computation failed, using defaults: %s", exc)
        # Fallback: return empty metrics if computation fails
        rag_metrics = RAGMetrics(
            avg_r_multiple_similar=0.0,
            win_rate_similar=0.0,
            sample_size=0,
            max_similarity_score=0.0,
            avg_confluence_count=0.0,
        )
    
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return RetrievalResponse(
        similar_setups=diverse,
        rag_metrics=rag_metrics,
        query_time_ms=round(elapsed_ms, 2),
    )


@app.post(
    "/rag/ingest",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["rag"],
)
async def ingest_setup(request: IngestionRequest) -> IngestionResponse:
    """
    Ingest a new enriched setup and its 528-dim embedding into Qdrant.

    Performs an upsert so duplicate trade_ids are updated rather than
    duplicated in the vector store.
    """
    wrapper = get_qdrant()
    setup = request.setup
    trade_id: str = setup.get("trade_id", str(uuid.uuid4()))

    from qdrant_client.http import models as qmodels

    point = qmodels.PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, trade_id)),
        vector=request.embedding,
        payload={
            "trade_id": trade_id,
            "timestamp": setup.get("timestamp"),
            "instrument": setup.get("instrument", ""),
            "time_window": setup.get("time_window", ""),
            "htf_open_bias": setup.get("htf_open_bias", ""),
            "confluence_count": setup.get("confluence_count", 0),
            "outcome_result": setup.get("outcome_result", ""),
            "outcome_r_multiple": setup.get("outcome_r_multiple", 0.0),
            "narrative": setup.get("narrative", ""),
            "full_setup": setup,
        },
    )

    try:
        await wrapper.upsert([point])
    except Exception as exc:
        logger.error("Qdrant upsert failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector store unavailable",
        ) from exc

    return IngestionResponse(
        status="success",
        setup_id=str(point.id),
    )
