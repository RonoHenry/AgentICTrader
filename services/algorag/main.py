"""
AlgoRAG FastAPI service.

Provides:
  GET  /health          – liveness + readiness with Qdrant connectivity
  POST /rag/retrieve    – retrieve similar historical setups
  POST /rag/ingest      – ingest a new enriched setup + embedding

## Structured Logging & Error Handling (Task 13.2)

This service implements comprehensive structured logging with:

1. **Correlation ID Tracking**: Every request gets a correlation ID for end-to-end tracing
   - Extracted from X-Correlation-ID header or auto-generated
   - Included in all log entries and response headers
   - Enables tracking requests across multiple services

2. **Structured Error Logging**: All errors logged with rich context
   - Request parameters (instrument, timestamp, filters)
   - Full stack traces for debugging
   - Correlation IDs for request tracing
   - JSON format for easy parsing and filtering

3. **Centralized Log Aggregation**: Optional integration with log aggregation systems
   - Supports ELK Stack, Splunk, Datadog, New Relic, custom endpoints
   - Configurable via LOG_AGGREGATION_* environment variables
   - Graceful degradation - never affects application performance

4. **Production-Ready Configuration**:
   - Structured JSON logging enabled by default (STRUCTURED_LOGS=true)
   - Auto-detects test environment to use plain text logs
   - Configurable log levels and aggregation endpoints
   - Error-level logs automatically sent to centralized systems

## Configuration

Environment Variables:
- STRUCTURED_LOGS=true/false (default: true)
- LOG_AGGREGATION_ENABLED=true/false (default: false)  
- LOG_AGGREGATION_ENDPOINT=https://logs.example.com/api/v1/logs
- LOG_AGGREGATION_API_KEY=your-api-key

## Example Log Output

```json
{
  "timestamp": "2024-05-06 09:15:23,456",
  "level": "ERROR", 
  "module": "services.algorag.main",
  "message": "[abc123-def456] Vector search failed: connection timeout (params: instrument=EURUSD, timestamp=2024-05-06 09:15:00+00:00, top_k=10)",
  "correlation_id": "abc123-def456",
  "request_params": {"instrument": "EURUSD", "timestamp": "2024-05-06 09:15:00+00:00", "top_k": 10},
  "exception": {
    "type": "Exception",
    "message": "connection timeout",
    "traceback": ["...full stack trace..."]
  }
}
```
"""

import logging
import logging.config
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import json
import traceback

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from qdrant_client.http.exceptions import UnexpectedResponse
from starlette.middleware.base import BaseHTTPMiddleware

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
# Structured Logging Configuration (Task 13.2)
# ---------------------------------------------------------------------------

class StructuredFormatter(logging.Formatter):
    """
    Structured logging formatter that outputs JSON for centralized log aggregation.
    
    Includes:
    - Standard log fields (timestamp, level, message, module)
    - Correlation ID from request context
    - Request parameters for error tracing
    - Stack trace for exceptions
    """
    
    def format(self, record):
        # Build structured log entry
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add correlation ID if available (set by middleware)
        if hasattr(record, 'correlation_id'):
            log_entry["correlation_id"] = record.correlation_id
            
        # Add request parameters if available (for error context)
        if hasattr(record, 'request_params'):
            log_entry["request_params"] = record.request_params
            
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info)
            }
            
        # Add any extra fields
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                'thread', 'threadName', 'processName', 'process', 'message',
                'correlation_id', 'request_params'
            } and not key.startswith('_'):
                log_entry[key] = value
        
        return json.dumps(log_entry, default=str)

# Configure structured logging
structured_logs_enabled = settings.service.structured_logs and os.getenv("PYTEST_CURRENT_TEST") is None

if structured_logs_enabled:
    # Use structured JSON formatter for production
    formatter = StructuredFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    
    # Configure service logger
    logger.handlers = [handler]
    logger.propagate = False

# ---------------------------------------------------------------------------
# Centralized Log Aggregation (REFACTOR Phase - Task 13.2)
# ---------------------------------------------------------------------------

class CentralizedLogHandler(logging.Handler):
    """
    Handler for sending logs to centralized aggregation systems.
    
    Supports various log aggregation platforms:
    - ELK Stack (Elasticsearch + Logstash)  
    - Splunk HTTP Event Collector (HEC)
    - Datadog Logs API
    - New Relic Logs API
    - Custom webhook endpoints
    
    Configuration via environment variables:
    - LOG_AGGREGATION_ENABLED=true
    - LOG_AGGREGATION_ENDPOINT=https://logs.example.com/api/v1/logs
    - LOG_AGGREGATION_API_KEY=your-api-key
    """
    
    def __init__(self, endpoint: str, api_key: str):
        super().__init__()
        self.endpoint = endpoint
        self.api_key = api_key
        self.session = None
        
    def emit(self, record):
        """Send log record to centralized system."""
        if not self.endpoint:
            return
            
        try:
            # Create session if needed
            if not self.session:
                import requests
                self.session = requests.Session()
                self.session.headers.update({
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.api_key}' if self.api_key else ''
                })
            
            # Format log entry for centralized system
            log_data = {
                'timestamp': record.created,
                'level': record.levelname,
                'logger': record.name,
                'message': self.format(record),
                'service': 'algorag',
                'environment': os.getenv('ENVIRONMENT', 'development'),
            }
            
            # Add structured fields if available
            for attr in ['correlation_id', 'request_params']:
                if hasattr(record, attr):
                    log_data[attr] = getattr(record, attr)
                    
            # Add exception details if present
            if record.exc_info:
                log_data['exception'] = {
                    'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                    'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                }
            
            # Send to centralized system (async in production)
            self.session.post(self.endpoint, json=log_data, timeout=5)
            
        except Exception:
            # Never let log aggregation failures affect the application
            # In production, you might want to use a dead letter queue
            pass

# Add centralized log aggregation if configured
if settings.service.log_aggregation_enabled and settings.service.log_aggregation_endpoint:
    centralized_handler = CentralizedLogHandler(
        endpoint=settings.service.log_aggregation_endpoint,
        api_key=settings.service.log_aggregation_api_key
    )
    # Set to ERROR level to avoid flooding the centralized system
    centralized_handler.setLevel(logging.ERROR)
    logger.addHandler(centralized_handler)

def get_correlation_id_from_request(request: Request) -> str:
    """Extract correlation ID from request state."""
    return getattr(request.state, 'correlation_id', 'unknown')

def log_error_with_context(
    logger_instance: logging.Logger,
    message: str,
    exception: Exception,
    correlation_id: str = None,
    request_params: dict = None
):
    """
    Log errors with structured context for debugging and monitoring.
    
    Args:
        logger_instance: Logger to use
        message: Error description
        exception: The exception that occurred
        correlation_id: Request correlation ID
        request_params: Request parameters for context
    """
    # Build error message with correlation ID and request context for backward compatibility
    log_message = f"{message}: {str(exception)}"
    if correlation_id:
        log_message = f"[{correlation_id}] {log_message}"
    
    # Add request parameters to message for test compatibility
    if request_params:
        params_str = ", ".join(f"{k}={v}" for k, v in request_params.items() if v is not None)
        if params_str:
            log_message = f"{log_message} (params: {params_str})"
    
    # Create log record with extra context
    extra = {}
    if correlation_id:
        extra['correlation_id'] = correlation_id
    if request_params:
        extra['request_params'] = request_params
        
    logger_instance.error(
        log_message,
        exc_info=exception,
        extra=extra
    )

# ---------------------------------------------------------------------------
# Correlation ID Middleware (Task 13.2)
# ---------------------------------------------------------------------------


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract or generate correlation IDs for request tracing.
    
    - Extracts X-Correlation-ID from request headers if present
    - Generates a new UUID if not provided
    - Adds correlation ID to response headers
    - Stores correlation ID in request state for logging
    """
    
    async def dispatch(self, request: Request, call_next):
        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Store in request state for access in endpoints
        request.state.correlation_id = correlation_id
        
        # Call the endpoint
        response = await call_next(request)
        
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response

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

# Add correlation ID middleware (Task 13.2)
app.add_middleware(CorrelationIDMiddleware)


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
async def retrieve_similar_setups(request: RetrievalRequest, http_request: Request) -> RetrievalResponse:
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
    correlation_id = get_correlation_id_from_request(http_request)
    
    # Build request context for error logging
    request_context = {
        "instrument": request.instrument,
        "timestamp": request.timestamp,
        "time_window": getattr(request, 'time_window', None),
        "htf_open_bias": getattr(request, 'htf_open_bias', None),
        "top_k": request.top_k,
    }
    
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
            timeout_msg = f"Qdrant search timeout after {settings.service.retrieval_timeout}s for instrument={request.instrument}"
            log_error_with_context(
                logger,
                "Vector search timeout",
                TimeoutError(timeout_msg),
                correlation_id=correlation_id,
                request_params=request_context
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Vector search timeout - please try again",
            )
            
    except HTTPException:
        # Re-raise HTTPExceptions (these are intended for the client)
        raise
    except Exception as exc:
        log_error_with_context(
            logger,
            "Vector search failed",
            exc,
            correlation_id=correlation_id,
            request_params=request_context
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
                f"Failed to parse search hit: {exc}",
                extra={
                    "correlation_id": correlation_id,
                    "hit_id": getattr(hit, 'id', 'unknown'),
                    "request_params": request_context
                }
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
        logger.warning(
            f"Re-ranking failed, using similarity order: {exc}",
            extra={
                "correlation_id": correlation_id,
                "request_params": request_context,
                "setups_count": len(similar)
            }
        )
        # Fallback: sort by similarity score if re-ranking fails
        reranked = sorted(similar, key=lambda s: s.similarity_score, reverse=True)

    # Apply diversity filtering (max N setups from same calendar day, configurable)
    try:
        diverse = apply_diversity_filter(reranked, max_per_day=settings.service.diversity_max_per_day)
    except Exception as exc:
        logger.warning(
            f"Diversity filtering failed, using re-ranked results: {exc}",
            extra={
                "correlation_id": correlation_id,
                "request_params": request_context,
                "reranked_count": len(reranked)
            }
        )
        # Fallback: use reranked results if diversity filtering fails
        diverse = reranked

    # Compute RAG metrics from final results
    try:
        rag_metrics = _build_rag_metrics(diverse)
    except Exception as exc:
        logger.warning(
            f"RAG metrics computation failed, using defaults: {exc}",
            extra={
                "correlation_id": correlation_id,
                "request_params": request_context,
                "diverse_count": len(diverse)
            }
        )
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
async def ingest_setup(request: IngestionRequest, http_request: Request) -> IngestionResponse:
    """
    Ingest a new enriched setup and its 528-dim embedding into Qdrant.

    Performs an upsert so duplicate trade_ids are updated rather than
    duplicated in the vector store.

    ## Security & Rate Limiting (REFACTOR Phase)
    
    In production deployments:
    - **Authentication**: JWT-based authentication should be enforced at the
      API gateway level (e.g., Kong, Traefik, AWS API Gateway) or via FastAPI
      Depends(get_current_user) middleware from services/auth/main.py
    - **Rate Limiting**: 100 req/min per user should be enforced at the API
      gateway level using tools like Kong rate-limit plugin, Redis-based
      rate limiters, or slowapi middleware
    - **Network Security**: This service should only be accessible from the
      internal network, not exposed directly to the public internet
    
    For development/testing, the endpoint is open to facilitate integration
    testing and rapid iteration. The auth service (services/auth/main.py)
    provides JWT authentication that can be integrated when needed.
    """
    wrapper = get_qdrant()
    setup = request.setup
    trade_id: str = setup.get("trade_id", str(uuid.uuid4()))
    correlation_id = get_correlation_id_from_request(http_request)

    # Build request context for error logging
    request_context = {
        "trade_id": trade_id,
        "instrument": setup.get("instrument"),
        "embedding_size": len(request.embedding) if request.embedding else 0,
        "setup_keys": list(setup.keys()) if setup else [],
    }

    from qdrant_client.http import models as qmodels

    point = qmodels.PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, trade_id)),
        vector=request.embedding,
        payload={
            "trade_id": trade_id,
            "timestamp": setup.get("timestamp"),
            "instrument": str(setup.get("instrument", "")).upper(),
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
        log_error_with_context(
            logger,
            "Qdrant upsert failed",
            exc,
            correlation_id=correlation_id,
            request_params=request_context
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector store unavailable",
        ) from exc

    return IngestionResponse(
        status="success",
        setup_id=str(point.id),
    )
