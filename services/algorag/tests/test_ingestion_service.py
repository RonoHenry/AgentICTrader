"""
TDD – Task 7: Setup ingestion to vector store.

Task 7.1 – Create ingestion service
    RED  phase: tests for batch ingestion of enriched setups with embeddings to Qdrant.
    GREEN phase: implement batch upsert with error handling and retry logic.
    REFACTOR: add progress tracking and logging.

Task 7.2 – Implement duplicate detection
    RED  phase: tests for detection and handling of duplicate trade_ids.
    GREEN phase: implement upsert logic (update if exists, insert if new).
    REFACTOR: add conflict resolution strategy.

All Qdrant calls are mocked — no live instance required.
Integration tests that require a real Qdrant instance are marked
@pytest.mark.integration and are skipped by default.

Requirements: FR-RAG-1 (Historical Setup Storage), FR-RAG-7 (Real-Time Ingestion)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, call, patch

import numpy as np
import pytest
from qdrant_client.http import models as qmodels

from services.algorag.config import QdrantConfig
from services.algorag.ingestion_service import (
    EMBEDDING_DIM,
    BatchIngestionResult,
    DuplicateStrategy,
    IngestionService,
    IngestionServiceError,
    build_point_from_setup,
)
from services.algorag.qdrant_client import QdrantClientWrapper


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def make_config(**overrides) -> QdrantConfig:
    defaults = dict(
        host="localhost",
        port=6333,
        collection="test_trading_setups",
        timeout=5.0,
        max_retries=3,
        retry_backoff=0.0,
    )
    defaults.update(overrides)
    return QdrantConfig(**defaults)


def make_enriched_setup(trade_id: str = "TRD-001", **overrides) -> Dict[str, Any]:
    """Minimal valid enriched setup matching the EnrichedSetup schema."""
    base = {
        "trade_id": trade_id,
        "timestamp": "2024-03-15T09:15:00Z",
        "instrument": "EURUSD",
        "direction": "LONG",
        "time_window": "LONDON_KILLZONE",
        "htf_open_bias": "BULLISH",
        "confluence_count": 4,
        "outcome_result": "WIN",
        "outcome_r_multiple": 3.2,
        "narrative": "Price swept Asian low and entered FVG at discount.",
        "bos_detected": True,
        "choch_detected": False,
        "fvg_present": True,
        "liquidity_sweep": True,
        "htf_high_proximity_pct": 0.35,
        "htf_low_proximity_pct": 0.65,
    }
    base.update(overrides)
    return base


def make_embedding(dim: int = 528) -> List[float]:
    """Return a deterministic 528-dim embedding vector."""
    rng = np.random.default_rng(42)
    return rng.standard_normal(dim).tolist()


@pytest.fixture()
def config() -> QdrantConfig:
    return make_config()


@pytest.fixture()
def mock_qdrant_wrapper() -> QdrantClientWrapper:
    """QdrantClientWrapper with all async methods mocked."""
    wrapper = MagicMock(spec=QdrantClientWrapper)
    wrapper.upsert = AsyncMock(return_value=None)
    wrapper.count = AsyncMock(return_value=10)
    wrapper.is_healthy = AsyncMock(return_value=True)
    return wrapper


@pytest.fixture()
def service(config: QdrantConfig, mock_qdrant_wrapper: QdrantClientWrapper) -> IngestionService:
    """IngestionService with a mocked Qdrant client."""
    return IngestionService(wrapper=mock_qdrant_wrapper, config=config)


# ---------------------------------------------------------------------------
# Task 7.1 – Batch ingestion
# ---------------------------------------------------------------------------


class TestBatchIngestionRED:
    """
    RED phase: tests that describe the desired batch ingestion behaviour.
    These tests define the contract for IngestionService.ingest_batch().
    Requirements: FR-RAG-1, FR-RAG-7
    """

    @pytest.mark.asyncio
    async def test_ingest_single_setup_calls_upsert(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """ingest_batch() with a single setup must call upsert exactly once."""
        setup = make_enriched_setup()
        embedding = make_embedding()

        result = await service.ingest_batch([(setup, embedding)])

        mock_qdrant_wrapper.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_batch_passes_correct_collection(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper, config: QdrantConfig
    ) -> None:
        """ingest_batch() must target the collection from config."""
        setup = make_enriched_setup()
        embedding = make_embedding()

        await service.ingest_batch([(setup, embedding)])

        call_kwargs = mock_qdrant_wrapper.upsert.call_args.kwargs
        assert call_kwargs.get("collection_name") == config.collection

    @pytest.mark.asyncio
    async def test_ingest_batch_returns_result_object(
        self, service: IngestionService
    ) -> None:
        """ingest_batch() returns a BatchIngestionResult with counts."""
        setups = [(make_enriched_setup(f"TRD-{i:03d}"), make_embedding()) for i in range(5)]

        result = await service.ingest_batch(setups)

        assert isinstance(result, BatchIngestionResult)

    @pytest.mark.asyncio
    async def test_ingest_batch_reports_success_count(
        self, service: IngestionService
    ) -> None:
        """BatchIngestionResult.successful equals the number of ingested setups."""
        n = 5
        setups = [(make_enriched_setup(f"TRD-{i:03d}"), make_embedding()) for i in range(n)]

        result = await service.ingest_batch(setups)

        assert result.successful == n

    @pytest.mark.asyncio
    async def test_ingest_batch_reports_zero_failures_on_success(
        self, service: IngestionService
    ) -> None:
        """BatchIngestionResult.failed equals 0 when all setups are ingested."""
        setups = [(make_enriched_setup(f"TRD-{i:03d}"), make_embedding()) for i in range(3)]

        result = await service.ingest_batch(setups)

        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_ingest_batch_multiple_setups_single_upsert_call(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Batch ingestion of N setups must dispatch a single upsert call with
        all N PointStructs, not N individual upsert calls.
        This is the key performance requirement for bulk ingestion.
        """
        n = 10
        setups = [(make_enriched_setup(f"TRD-{i:03d}"), make_embedding()) for i in range(n)]

        await service.ingest_batch(setups)

        assert mock_qdrant_wrapper.upsert.call_count == 1
        call_kwargs = mock_qdrant_wrapper.upsert.call_args.kwargs
        assert len(call_kwargs["points"]) == n

    @pytest.mark.asyncio
    async def test_ingest_batch_point_has_correct_embedding(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """Each PointStruct vector must match the provided embedding."""
        embedding = make_embedding()
        await service.ingest_batch([(make_enriched_setup(), embedding)])

        points = mock_qdrant_wrapper.upsert.call_args.kwargs["points"]
        assert points[0].vector == embedding

    @pytest.mark.asyncio
    async def test_ingest_batch_point_has_required_payload_keys(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """Each PointStruct payload must include all schema-required keys."""
        required_keys = {
            "trade_id",
            "timestamp",
            "instrument",
            "time_window",
            "htf_open_bias",
            "confluence_count",
            "outcome_result",
            "outcome_r_multiple",
            "narrative",
        }
        await service.ingest_batch([(make_enriched_setup(), make_embedding())])

        points = mock_qdrant_wrapper.upsert.call_args.kwargs["points"]
        assert required_keys <= set(points[0].payload.keys())

    @pytest.mark.asyncio
    async def test_ingest_batch_instrument_stored_uppercase(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """Instrument must be stored as uppercase in the payload (project convention)."""
        setup = make_enriched_setup(instrument="eurusd")
        await service.ingest_batch([(setup, make_embedding())])

        points = mock_qdrant_wrapper.upsert.call_args.kwargs["points"]
        assert points[0].payload["instrument"] == "EURUSD"

    @pytest.mark.asyncio
    async def test_ingest_empty_batch_returns_zero_counts(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """Ingesting an empty list returns a result with successful=0, failed=0."""
        result = await service.ingest_batch([])

        assert result.successful == 0
        assert result.failed == 0
        mock_qdrant_wrapper.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_batch_full_setup_stored_in_payload(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """The full setup dict must be stored under the 'full_setup' payload key."""
        setup = make_enriched_setup(trade_id="TRD-FULL")
        await service.ingest_batch([(setup, make_embedding())])

        points = mock_qdrant_wrapper.upsert.call_args.kwargs["points"]
        assert "full_setup" in points[0].payload
        assert points[0].payload["full_setup"]["trade_id"] == "TRD-FULL"


class TestBatchIngestionErrorHandlingGREEN:
    """
    GREEN phase: error handling and retry logic.
    Requirements: FR-RAG-1, FR-RAG-7
    """

    @pytest.mark.asyncio
    async def test_ingest_batch_raises_ingestion_service_error_on_upsert_failure(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """When upsert fails after all retries, IngestionServiceError is raised."""
        from services.algorag.qdrant_client import QdrantConnectionError
        mock_qdrant_wrapper.upsert = AsyncMock(side_effect=QdrantConnectionError("timeout"))

        with pytest.raises(IngestionServiceError, match="Batch ingestion failed"):
            await service.ingest_batch([(make_enriched_setup(), make_embedding())])

    @pytest.mark.asyncio
    async def test_ingest_batch_partial_failure_records_failed_count(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """
        When the service is configured with small_batch_size, individual-batch
        failures are counted in result.failed rather than raising immediately.
        Partial failure allows remaining batches to proceed.
        """
        call_count = 0
        async def flaky_upsert(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("transient failure")

        mock_qdrant_wrapper.upsert = flaky_upsert
        # Use small batch size so we get multiple upsert calls
        service_small = IngestionService(
            wrapper=mock_qdrant_wrapper,
            config=make_config(),
            batch_size=3,
        )
        # 7 setups with batch_size=3 → 3 batches, 2nd fails
        setups = [(make_enriched_setup(f"TRD-{i:03d}"), make_embedding()) for i in range(7)]

        result = await service_small.ingest_batch(setups)

        # 2nd batch of 3 failed, other 2 batches succeeded
        assert result.failed == 3
        assert result.successful == 4

    @pytest.mark.asyncio
    async def test_ingest_batch_invalid_embedding_dimension_raises(
        self, service: IngestionService
    ) -> None:
        """Embeddings with wrong dimension are rejected before hitting Qdrant."""
        bad_embedding = [0.0] * 256  # wrong size

        with pytest.raises(ValueError, match="528"):
            await service.ingest_batch([(make_enriched_setup(), bad_embedding)])

    @pytest.mark.asyncio
    async def test_ingest_batch_missing_trade_id_generates_uuid(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """Setup missing trade_id gets a deterministic UUID assigned."""
        setup_no_id: Dict[str, Any] = {k: v for k, v in make_enriched_setup().items() if k != "trade_id"}

        await service.ingest_batch([(setup_no_id, make_embedding())])

        points = mock_qdrant_wrapper.upsert.call_args.kwargs["points"]
        assert "trade_id" in points[0].payload
        assert len(points[0].payload["trade_id"]) > 0


class TestProgressTrackingREFACTOR:
    """
    REFACTOR phase: progress tracking and logging.
    Requirements: FR-RAG-1
    """

    @pytest.mark.asyncio
    async def test_ingest_batch_result_has_ingested_ids(
        self, service: IngestionService
    ) -> None:
        """BatchIngestionResult.ingested_ids contains a UUID for each ingested setup."""
        n = 3
        setups = [(make_enriched_setup(f"TRD-{i:03d}"), make_embedding()) for i in range(n)]

        result = await service.ingest_batch(setups)

        assert len(result.ingested_ids) == n
        for setup_id in result.ingested_ids:
            assert isinstance(setup_id, str)
            assert len(setup_id) > 0

    @pytest.mark.asyncio
    async def test_ingest_batch_result_has_total_count(
        self, service: IngestionService
    ) -> None:
        """BatchIngestionResult.total equals len(input)."""
        n = 4
        setups = [(make_enriched_setup(f"TRD-{i:03d}"), make_embedding()) for i in range(n)]

        result = await service.ingest_batch(setups)

        assert result.total == n


# ---------------------------------------------------------------------------
# Task 7.2 – Duplicate detection
# ---------------------------------------------------------------------------


class TestDuplicateDetectionRED:
    """
    RED phase: tests for duplicate trade_id detection and upsert semantics.
    Requirements: FR-RAG-1
    """

    def test_build_point_from_setup_generates_deterministic_id(self) -> None:
        """
        build_point_from_setup() must produce the same PointStruct UUID for the
        same trade_id, enabling Qdrant upsert deduplication by point ID.
        Determinism is essential: ingesting the same trade_id twice must
        overwrite the existing vector, not create a duplicate.
        """
        setup = make_enriched_setup(trade_id="TRD-DET-001")
        embedding = make_embedding()

        point1 = build_point_from_setup(setup, embedding)
        point2 = build_point_from_setup(setup, embedding)

        assert point1.id == point2.id

    def test_build_point_different_trade_ids_produce_different_point_ids(self) -> None:
        """
        Different trade_ids must produce different PointStruct UUIDs so that
        distinct setups are stored as separate vectors in Qdrant.
        """
        setup_a = make_enriched_setup(trade_id="TRD-001")
        setup_b = make_enriched_setup(trade_id="TRD-002")
        embedding = make_embedding()

        point_a = build_point_from_setup(setup_a, embedding)
        point_b = build_point_from_setup(setup_b, embedding)

        assert point_a.id != point_b.id

    def test_build_point_id_is_uuid5_of_trade_id(self) -> None:
        """
        The PointStruct ID must be uuid5(NAMESPACE_DNS, trade_id) — the same
        deterministic scheme used by the /rag/ingest endpoint (FR-RAG-1).
        """
        trade_id = "TRD-UUID5-TEST"
        expected_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, trade_id))
        setup = make_enriched_setup(trade_id=trade_id)

        point = build_point_from_setup(setup, make_embedding())

        assert str(point.id) == expected_id

    @pytest.mark.asyncio
    async def test_ingest_same_trade_id_twice_calls_upsert_twice(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Ingesting the same trade_id in two separate calls both reach Qdrant upsert.
        Qdrant's upsert semantics handle the actual deduplication server-side —
        the service must not filter out duplicates client-side.
        """
        setup = make_enriched_setup(trade_id="TRD-DUP")
        embedding = make_embedding()

        await service.ingest_batch([(setup, embedding)])
        await service.ingest_batch([(setup, embedding)])

        assert mock_qdrant_wrapper.upsert.call_count == 2

    @pytest.mark.asyncio
    async def test_ingest_same_trade_id_twice_same_point_id(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Both upsert calls for the same trade_id must send the same PointStruct ID.
        Qdrant uses the ID to identify whether to insert or update the record.
        """
        setup = make_enriched_setup(trade_id="TRD-SAME-ID")
        embedding = make_embedding()

        await service.ingest_batch([(setup, embedding)])
        await service.ingest_batch([(setup, embedding)])

        all_calls = mock_qdrant_wrapper.upsert.call_args_list
        id_first = all_calls[0].kwargs["points"][0].id
        id_second = all_calls[1].kwargs["points"][0].id

        assert id_first == id_second

    @pytest.mark.asyncio
    async def test_ingest_updated_setup_overwrites_payload(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """
        When a trade_id is re-ingested with a different outcome, the new payload
        must be forwarded to Qdrant (not silently dropped).
        """
        setup_v1 = make_enriched_setup(trade_id="TRD-UPDATE", outcome_result="LOSS")
        setup_v2 = make_enriched_setup(trade_id="TRD-UPDATE", outcome_result="WIN")
        embedding = make_embedding()

        await service.ingest_batch([(setup_v1, embedding)])
        await service.ingest_batch([(setup_v2, embedding)])

        last_call_points = mock_qdrant_wrapper.upsert.call_args.kwargs["points"]
        assert last_call_points[0].payload["outcome_result"] == "WIN"


class TestDuplicateStrategyGREEN:
    """
    GREEN phase: upsert logic correctness.
    Requirements: FR-RAG-1
    """

    def test_default_strategy_is_upsert(self, config: QdrantConfig, mock_qdrant_wrapper: QdrantClientWrapper) -> None:
        """IngestionService defaults to UPSERT duplicate strategy."""
        svc = IngestionService(wrapper=mock_qdrant_wrapper, config=config)
        assert svc.duplicate_strategy == DuplicateStrategy.UPSERT

    def test_service_accepts_custom_duplicate_strategy(
        self, config: QdrantConfig, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """IngestionService accepts an explicit DuplicateStrategy at construction."""
        svc = IngestionService(
            wrapper=mock_qdrant_wrapper,
            config=config,
            duplicate_strategy=DuplicateStrategy.UPSERT,
        )
        assert svc.duplicate_strategy == DuplicateStrategy.UPSERT

    @pytest.mark.asyncio
    async def test_ingest_batch_duplicate_strategy_skip_does_not_overwrite(
        self, config: QdrantConfig, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """
        SKIP strategy: when a trade_id is already known to the service
        (tracked in-memory per session), it must not be re-sent to Qdrant.
        """
        svc = IngestionService(
            wrapper=mock_qdrant_wrapper,
            config=config,
            duplicate_strategy=DuplicateStrategy.SKIP,
        )
        setup = make_enriched_setup(trade_id="TRD-SKIP-DUP")
        embedding = make_embedding()

        # First ingestion: should go through
        await svc.ingest_batch([(setup, embedding)])
        # Second ingestion of same trade_id: should be skipped
        await svc.ingest_batch([(setup, embedding)])

        # Only one upsert call should have been made
        assert mock_qdrant_wrapper.upsert.call_count == 1

    @pytest.mark.asyncio
    async def test_ingest_batch_skip_strategy_skip_count_in_result(
        self, config: QdrantConfig, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """SKIP strategy: BatchIngestionResult.skipped reflects skipped count."""
        svc = IngestionService(
            wrapper=mock_qdrant_wrapper,
            config=config,
            duplicate_strategy=DuplicateStrategy.SKIP,
        )
        setup = make_enriched_setup(trade_id="TRD-SKIP-COUNT")
        embedding = make_embedding()

        await svc.ingest_batch([(setup, embedding)])
        result = await svc.ingest_batch([(setup, embedding)])

        assert result.skipped == 1
        assert result.successful == 0


class TestConflictResolutionREFACTOR:
    """
    REFACTOR phase: conflict resolution strategy.
    Requirements: FR-RAG-1
    """

    def test_duplicate_strategy_enum_has_upsert_and_skip(self) -> None:
        """DuplicateStrategy enum must expose UPSERT and SKIP values."""
        assert DuplicateStrategy.UPSERT is not None
        assert DuplicateStrategy.SKIP is not None

    def test_ingestion_service_exposes_seen_trade_ids(
        self, config: QdrantConfig, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """IngestionService tracks seen trade_ids for in-session deduplication."""
        svc = IngestionService(wrapper=mock_qdrant_wrapper, config=config)
        assert hasattr(svc, "seen_trade_ids")
        assert isinstance(svc.seen_trade_ids, set)

    @pytest.mark.asyncio
    async def test_seen_trade_ids_populated_after_ingest(
        self, service: IngestionService
    ) -> None:
        """After ingestion, trade_ids are recorded in seen_trade_ids."""
        setup = make_enriched_setup(trade_id="TRD-SEEN")
        await service.ingest_batch([(setup, make_embedding())])

        assert "TRD-SEEN" in service.seen_trade_ids

    @pytest.mark.asyncio
    async def test_clear_seen_trade_ids_resets_deduplication(
        self, service: IngestionService, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """clear_seen_ids() resets the in-session deduplication cache."""
        setup = make_enriched_setup(trade_id="TRD-CLEAR")
        await service.ingest_batch([(setup, make_embedding())])

        service.clear_seen_ids()

        assert len(service.seen_trade_ids) == 0

    @pytest.mark.asyncio
    async def test_ingest_batch_with_mixed_new_and_duplicate_skip_strategy(
        self, config: QdrantConfig, mock_qdrant_wrapper: QdrantClientWrapper
    ) -> None:
        """
        SKIP strategy: a batch containing both new and already-seen trade_ids
        must only forward the new ones to Qdrant.
        """
        svc = IngestionService(
            wrapper=mock_qdrant_wrapper,
            config=config,
            duplicate_strategy=DuplicateStrategy.SKIP,
        )
        embedding = make_embedding()
        # Pre-seed a known trade_id
        await svc.ingest_batch([(make_enriched_setup(trade_id="TRD-OLD"), embedding)])
        mock_qdrant_wrapper.upsert.reset_mock()

        # Batch with 1 duplicate + 2 new
        mixed_batch = [
            (make_enriched_setup(trade_id="TRD-OLD"), embedding),
            (make_enriched_setup(trade_id="TRD-NEW-1"), embedding),
            (make_enriched_setup(trade_id="TRD-NEW-2"), embedding),
        ]
        result = await svc.ingest_batch(mixed_batch)

        # Upsert is called once for the 2 new setups
        assert mock_qdrant_wrapper.upsert.call_count == 1
        points = mock_qdrant_wrapper.upsert.call_args.kwargs["points"]
        assert len(points) == 2
        assert result.successful == 2
        assert result.skipped == 1


# ---------------------------------------------------------------------------
# build_point_from_setup() unit tests
# ---------------------------------------------------------------------------


class TestBuildPointFromSetup:
    """Unit tests for the pure helper function build_point_from_setup()."""

    def test_returns_point_struct(self) -> None:
        """build_point_from_setup() returns a qdrant PointStruct."""
        point = build_point_from_setup(make_enriched_setup(), make_embedding())
        assert isinstance(point, qmodels.PointStruct)

    def test_vector_matches_embedding(self) -> None:
        """The point vector equals the supplied embedding."""
        embedding = make_embedding()
        point = build_point_from_setup(make_enriched_setup(), embedding)
        assert point.vector == embedding

    def test_payload_instrument_is_uppercase(self) -> None:
        """Instrument is normalised to uppercase regardless of input case."""
        setup = make_enriched_setup(instrument="gbpusd")
        point = build_point_from_setup(setup, make_embedding())
        assert point.payload["instrument"] == "GBPUSD"

    def test_payload_trade_id_preserved(self) -> None:
        """trade_id is preserved exactly in the payload."""
        setup = make_enriched_setup(trade_id="TRD-PRESERVE-001")
        point = build_point_from_setup(setup, make_embedding())
        assert point.payload["trade_id"] == "TRD-PRESERVE-001"

    def test_payload_full_setup_equals_input(self) -> None:
        """full_setup payload key contains a copy of the entire setup dict."""
        setup = make_enriched_setup(trade_id="TRD-FULL-COPY")
        point = build_point_from_setup(setup, make_embedding())
        assert point.payload["full_setup"]["trade_id"] == "TRD-FULL-COPY"

    def test_embedding_dimension_validated(self) -> None:
        """build_point_from_setup() raises ValueError for wrong-dimension embeddings."""
        with pytest.raises(ValueError, match="528"):
            build_point_from_setup(make_enriched_setup(), [0.0] * 100)

    def test_embedding_dim_constant_is_528(self) -> None:
        """EMBEDDING_DIM module constant equals 528."""
        assert EMBEDDING_DIM == 528


# ---------------------------------------------------------------------------
# Integration tests (require live Qdrant)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIngestionServiceIntegration:
    """
    Integration tests requiring a live Qdrant instance (localhost:6333).
    Run with: pytest -m integration services/algorag/tests/test_ingestion_service.py
    """

    @pytest.mark.asyncio
    async def test_ingest_and_count_live(self) -> None:
        """Single setup can be ingested and counted in a live Qdrant collection."""
        cfg = make_config(
            host="localhost",
            port=6333,
            collection="test_ingestion_integration",
            retry_backoff=0.1,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        svc = IngestionService(wrapper=wrapper, config=cfg)
        try:
            await wrapper.ensure_collection()
            setup = make_enriched_setup(trade_id="TRD-LIVE-001")
            result = await svc.ingest_batch([(setup, make_embedding())])

            assert result.successful == 1
            count = await wrapper.count()
            assert count >= 1
        finally:
            await wrapper.delete_collection()
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_duplicate_upsert_does_not_increase_count(self) -> None:
        """Upserting the same trade_id twice does not create two records."""
        cfg = make_config(
            host="localhost",
            port=6333,
            collection="test_ingestion_dedup_integration",
            retry_backoff=0.1,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        svc = IngestionService(wrapper=wrapper, config=cfg)
        try:
            await wrapper.ensure_collection()
            setup = make_enriched_setup(trade_id="TRD-DEDUP-LIVE")
            embedding = make_embedding()

            await svc.ingest_batch([(setup, embedding)])
            await svc.ingest_batch([(setup, embedding)])

            count = await wrapper.count()
            assert count == 1, f"Expected 1 point after double upsert, got {count}"
        finally:
            await wrapper.delete_collection()
            await wrapper.close()
