"""
AlgoRAG Ingestion Service.

Provides IngestionService — a high-level service for batch-ingesting enriched
trading setups with pre-computed 528-dim embeddings into the Qdrant vector store.

Key responsibilities:
  - Validates embedding dimensions before any network call
  - Builds deterministic PointStruct IDs from trade_id (uuid5) so Qdrant
    upsert semantics guarantee deduplication server-side
  - Supports configurable batch sizes for efficient bulk ingestion
  - Tracks seen trade_ids in-session for optional SKIP duplicate strategy
  - Captures per-batch failures with full error context for progress reporting

Usage example::

    from services.algorag.ingestion_service import IngestionService, DuplicateStrategy
    from services.algorag.qdrant_client import QdrantClientWrapper

    wrapper = QdrantClientWrapper()
    await wrapper.ensure_collection()

    svc = IngestionService(wrapper=wrapper)
    result = await svc.ingest_batch(list_of_setup_embedding_pairs)
    print(f"Ingested {result.successful}/{result.total} setups")
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from qdrant_client.http import models as qmodels

from services.algorag.config import QdrantConfig, settings
from services.algorag.qdrant_client import QdrantClientWrapper, QdrantConnectionError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBEDDING_DIM: int = 528
"""Expected dimensionality of the combined multi-modal embedding vector."""

DEFAULT_BATCH_SIZE: int = 100
"""Default number of setups submitted in a single Qdrant upsert call."""


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class DuplicateStrategy(str, Enum):
    """Strategy for handling duplicate trade_ids during ingestion.

    UPSERT — always forward to Qdrant; Qdrant's upsert semantics overwrite the
             existing point if the ID already exists.  This is the default.
    SKIP   — check the in-session seen_trade_ids set and skip any trade_id that
             has already been ingested in this service session.
    """
    UPSERT = "upsert"
    SKIP = "skip"


@dataclass
class BatchIngestionResult:
    """Summary of a completed ingest_batch() call.

    Attributes:
        total:        Total number of setups submitted (including skipped/failed).
        successful:   Number of setups successfully upserted to Qdrant.
        failed:       Number of setups that could not be upserted due to errors.
        skipped:      Number of setups skipped due to the SKIP duplicate strategy.
        ingested_ids: Qdrant point UUIDs for successfully ingested setups.
        errors:       List of (trade_id, error_message) tuples for failed setups.
    """
    total: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    ingested_ids: List[str] = field(default_factory=list)
    errors: List[Tuple[str, str]] = field(default_factory=list)


class IngestionServiceError(RuntimeError):
    """Raised when a batch ingestion cannot be completed at all.

    Distinguishable from per-item failures (which are recorded in
    BatchIngestionResult.errors) so that callers can choose a different
    error-handling path for catastrophic vs. partial failures.
    """


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------


def build_point_from_setup(
    setup: Dict[str, Any],
    embedding: List[float],
) -> qmodels.PointStruct:
    """Build a Qdrant PointStruct from an enriched setup and its embedding.

    The PointStruct ID is derived deterministically from the setup's trade_id
    using uuid5(NAMESPACE_DNS, trade_id).  This ensures that re-ingesting the
    same trade_id always produces the same point ID, so Qdrant's upsert
    semantics overwrite rather than duplicate the existing record.

    Args:
        setup:     Enriched setup dict (must include at least "trade_id" key,
                   or a UUID will be generated).
        embedding: Pre-computed 528-dim embedding vector.

    Returns:
        A fully-populated qmodels.PointStruct ready for upsert.

    Raises:
        ValueError: If the embedding does not have exactly EMBEDDING_DIM (528)
                    dimensions.
    """
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding must be {EMBEDDING_DIM}-dimensional, got {len(embedding)}"
        )

    trade_id: str = setup.get("trade_id") or str(uuid.uuid4())
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, trade_id))

    payload: Dict[str, Any] = {
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
    }

    return qmodels.PointStruct(
        id=point_id,
        vector=embedding,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Ingestion service
# ---------------------------------------------------------------------------


class IngestionService:
    """Batch-ingestion service for enriched trading setups.

    Accepts a list of (enriched_setup, embedding) pairs, validates embeddings,
    builds PointStructs, and upserts them to Qdrant in configurable batches.

    Supports an optional SKIP duplicate strategy that tracks seen trade_ids
    in-session to avoid redundant network calls for already-ingested setups.

    Attributes:
        duplicate_strategy: Controls how duplicate trade_ids are handled.
        seen_trade_ids:      Set of trade_ids ingested in the current session.
    """

    def __init__(
        self,
        *,
        wrapper: Optional[QdrantClientWrapper] = None,
        config: Optional[QdrantConfig] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        duplicate_strategy: DuplicateStrategy = DuplicateStrategy.UPSERT,
    ) -> None:
        self._wrapper: QdrantClientWrapper = wrapper or QdrantClientWrapper(
            config=config or settings.qdrant
        )
        self._config: QdrantConfig = config or settings.qdrant
        self._batch_size: int = batch_size
        self.duplicate_strategy: DuplicateStrategy = duplicate_strategy
        self.seen_trade_ids: Set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest_batch(
        self,
        items: List[Tuple[Dict[str, Any], List[float]]],
    ) -> BatchIngestionResult:
        """Ingest a batch of (enriched_setup, embedding) pairs into Qdrant.

        Validates embedding dimensions, applies the duplicate strategy, builds
        PointStructs, and submits them to Qdrant in sub-batches of batch_size.

        Args:
            items: List of (setup_dict, embedding) pairs to ingest.

        Returns:
            BatchIngestionResult with counts and ingested point IDs.

        Raises:
            ValueError:             If any embedding has the wrong dimension
                                    (validation is eager — raised before any
                                    network call is made).
            IngestionServiceError:  If the entire batch fails with a single
                                    sub-batch and no partial progress is
                                    possible.
        """
        result = BatchIngestionResult(total=len(items))

        if not items:
            return result

        # --- Validate all embedding dimensions eagerly ---
        for setup, embedding in items:
            if len(embedding) != EMBEDDING_DIM:
                raise ValueError(
                    f"Embedding must be {EMBEDDING_DIM}-dimensional, got {len(embedding)}"
                )

        # --- Apply duplicate strategy ---
        filtered = self._apply_duplicate_strategy(items, result)

        if not filtered:
            return result

        # --- Build PointStructs ---
        points: List[qmodels.PointStruct] = [
            build_point_from_setup(setup, embedding)
            for setup, embedding in filtered
        ]

        # --- Batch-upsert with per-batch error handling ---
        if self._batch_size >= len(points):
            # Single upsert covers everything — raise on failure so the caller
            # knows the batch was not partially committed
            try:
                await self._wrapper.upsert(
                    points=points,
                    collection_name=self._config.collection,
                )
            except QdrantConnectionError as exc:
                raise IngestionServiceError(
                    f"Batch ingestion failed: {exc}"
                ) from exc
            except Exception as exc:
                raise IngestionServiceError(
                    f"Batch ingestion failed: {exc}"
                ) from exc

            result.successful = len(points)
            result.ingested_ids = [str(p.id) for p in points]
            # Track seen trade_ids
            for p in points:
                self.seen_trade_ids.add(p.payload["trade_id"])
        else:
            # Multiple batches — track partial failures individually
            await self._upsert_in_batches(points, filtered, result)

        logger.info(
            "Ingestion complete: %d/%d successful, %d failed, %d skipped",
            result.successful,
            result.total,
            result.failed,
            result.skipped,
        )
        return result

    def clear_seen_ids(self) -> None:
        """Reset the in-session duplicate detection cache."""
        self.seen_trade_ids.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_duplicate_strategy(
        self,
        items: List[Tuple[Dict[str, Any], List[float]]],
        result: BatchIngestionResult,
    ) -> List[Tuple[Dict[str, Any], List[float]]]:
        """Filter items according to duplicate_strategy; update result.skipped."""
        if self.duplicate_strategy == DuplicateStrategy.UPSERT:
            return list(items)

        # SKIP strategy: filter out already-seen trade_ids
        filtered: List[Tuple[Dict[str, Any], List[float]]] = []
        for setup, embedding in items:
            trade_id = setup.get("trade_id") or ""
            if trade_id in self.seen_trade_ids:
                result.skipped += 1
                logger.debug("Skipping duplicate trade_id: %s", trade_id)
            else:
                filtered.append((setup, embedding))
        return filtered

    async def _upsert_in_batches(
        self,
        points: List[qmodels.PointStruct],
        filtered: List[Tuple[Dict[str, Any], List[float]]],
        result: BatchIngestionResult,
    ) -> None:
        """Submit points to Qdrant in sub-batches; capture per-batch failures."""
        for batch_start in range(0, len(points), self._batch_size):
            batch = points[batch_start : batch_start + self._batch_size]
            try:
                await self._wrapper.upsert(
                    points=batch,
                    collection_name=self._config.collection,
                )
                result.successful += len(batch)
                result.ingested_ids.extend(str(p.id) for p in batch)
                for p in batch:
                    self.seen_trade_ids.add(p.payload["trade_id"])
            except Exception as exc:
                result.failed += len(batch)
                for p in batch:
                    result.errors.append((p.payload.get("trade_id", ""), str(exc)))
                logger.warning(
                    "Batch upsert failed for %d points (offset %d): %s",
                    len(batch),
                    batch_start,
                    exc,
                )
