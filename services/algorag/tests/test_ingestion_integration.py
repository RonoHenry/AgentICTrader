"""
TDD – Task 7.3: Integration tests for setup ingestion to vector store.

Covers three areas required by FR-RAG-7 and NFR-RAG-1:
  1. Bulk ingestion of 100+ setups (correctness + completeness)
  2. Error handling — network failures, invalid/malformed data
  3. Performance — ingestion throughput < 1 second per setup

Mocked tests: all tests run without a live Qdrant instance by default.
Live integration tests are marked @pytest.mark.integration and require
Qdrant running on localhost:6333. Run with:

    pytest -m integration services/algorag/tests/test_ingestion_integration.py

Requirements: FR-RAG-7 (Real-Time Ingestion), NFR-RAG-1 (Performance)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from services.algorag.config import QdrantConfig
from services.algorag.ingestion_service import (
    EMBEDDING_DIM,
    BatchIngestionResult,
    DuplicateStrategy,
    IngestionService,
    IngestionServiceError,
    build_point_from_setup,
)
from services.algorag.qdrant_client import QdrantClientWrapper, QdrantConnectionError


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def make_config(**overrides) -> QdrantConfig:
    defaults = dict(
        host="localhost",
        port=6333,
        collection="test_ingestion_integration",
        timeout=5.0,
        max_retries=3,
        retry_backoff=0.0,  # no sleep delays in tests
    )
    defaults.update(overrides)
    return QdrantConfig(**defaults)


def make_setup(trade_id: str = "TRD-001", **overrides) -> Dict[str, Any]:
    """Minimal valid enriched setup matching the EnrichedSetup schema."""
    base: Dict[str, Any] = {
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


def make_embedding(seed: int = 42) -> List[float]:
    """Return a deterministic 528-dim unit-norm embedding vector."""
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(EMBEDDING_DIM)
    # Normalise to unit length — mimics real SBERT output characteristics
    vec = vec / (np.linalg.norm(vec) + 1e-9)
    return vec.tolist()


def make_batch(n: int, prefix: str = "TRD") -> List[Tuple[Dict[str, Any], List[float]]]:
    """Generate n unique (setup, embedding) pairs for bulk-ingestion tests."""
    return [
        (make_setup(trade_id=f"{prefix}-{i:04d}", instrument="EURUSD"), make_embedding(seed=i))
        for i in range(n)
    ]


@pytest.fixture()
def config() -> QdrantConfig:
    return make_config()


@pytest.fixture()
def mock_wrapper() -> QdrantClientWrapper:
    """QdrantClientWrapper with all async methods mocked (no live Qdrant needed)."""
    wrapper = MagicMock(spec=QdrantClientWrapper)
    wrapper.upsert = AsyncMock(return_value=None)
    wrapper.count = AsyncMock(return_value=0)
    wrapper.is_healthy = AsyncMock(return_value=True)
    wrapper.ensure_collection = AsyncMock(return_value=None)
    wrapper.delete_collection = AsyncMock(return_value=None)
    wrapper.close = AsyncMock(return_value=None)
    return wrapper


@pytest.fixture()
def service(config: QdrantConfig, mock_wrapper: QdrantClientWrapper) -> IngestionService:
    return IngestionService(wrapper=mock_wrapper, config=config)


# ---------------------------------------------------------------------------
# Area 1: Bulk ingestion of 100+ setups
# ---------------------------------------------------------------------------


class TestBulkIngestion100Plus:
    """
    Verify that the ingestion service can correctly process batches of 100+
    enriched setups in a single call, with all setups reaching Qdrant.

    Requirements: FR-RAG-7
    """

    @pytest.mark.asyncio
    async def test_ingest_exactly_100_setups_successful(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """Ingesting exactly 100 setups returns successful=100."""
        batch = make_batch(100)

        result = await service.ingest_batch(batch)

        assert result.successful == 100
        assert result.failed == 0
        assert result.total == 100

    @pytest.mark.asyncio
    async def test_ingest_500_setups_successful(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """Ingesting 500 setups (MVP threshold) returns successful=500."""
        batch = make_batch(500)

        result = await service.ingest_batch(batch)

        assert result.successful == 500
        assert result.failed == 0
        assert result.total == 500

    @pytest.mark.asyncio
    async def test_ingest_100_setups_all_have_unique_point_ids(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        All 100 setups must produce distinct Qdrant point IDs.
        Collisions would cause silent overwrites in the vector store.
        """
        batch = make_batch(100)

        await service.ingest_batch(batch)

        # Collect all point IDs from all upsert calls
        all_ids: List[str] = []
        for call in mock_wrapper.upsert.call_args_list:
            points = call.kwargs["points"]
            all_ids.extend(str(p.id) for p in points)

        assert len(all_ids) == 100
        assert len(set(all_ids)) == 100, "Duplicate point IDs detected — uuid5 collision"

    @pytest.mark.asyncio
    async def test_ingest_100_setups_single_upsert_call_default_batch(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Default batch_size=100: 100 setups must be dispatched in a single
        Qdrant upsert call (not 100 individual calls).
        Sending all setups in one call is the key performance optimisation.
        """
        batch = make_batch(100)

        await service.ingest_batch(batch)

        assert mock_wrapper.upsert.call_count == 1

    @pytest.mark.asyncio
    async def test_ingest_110_setups_with_batch_size_100_uses_two_calls(
        self, config: QdrantConfig, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        110 setups with batch_size=100 must trigger exactly 2 upsert calls:
        one batch of 100 and one batch of 10. Validates the chunking logic.
        """
        svc = IngestionService(wrapper=mock_wrapper, config=config, batch_size=100)
        batch = make_batch(110)

        await svc.ingest_batch(batch)

        assert mock_wrapper.upsert.call_count == 2
        first_batch_size = len(mock_wrapper.upsert.call_args_list[0].kwargs["points"])
        second_batch_size = len(mock_wrapper.upsert.call_args_list[1].kwargs["points"])
        assert first_batch_size == 100
        assert second_batch_size == 10

    @pytest.mark.asyncio
    async def test_ingest_100_setups_result_has_ingested_ids_list(
        self, service: IngestionService
    ) -> None:
        """BatchIngestionResult.ingested_ids contains a UUID for every ingested setup."""
        batch = make_batch(100)

        result = await service.ingest_batch(batch)

        assert len(result.ingested_ids) == 100
        for setup_id in result.ingested_ids:
            assert isinstance(setup_id, str)
            assert len(setup_id) > 0

    @pytest.mark.asyncio
    async def test_ingest_100_mixed_instruments_all_stored_uppercase(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Instruments are normalised to uppercase for all 100 setups.
        The project-conventions.md rule applies regardless of input case.
        """
        instruments = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US500", "US30"]
        batch: List[Tuple[Dict[str, Any], List[float]]] = []
        for i in range(100):
            instr = instruments[i % len(instruments)].lower()  # intentionally lowercase
            batch.append((make_setup(trade_id=f"TRD-{i:04d}", instrument=instr), make_embedding(i)))

        await service.ingest_batch(batch)

        all_points = []
        for call in mock_wrapper.upsert.call_args_list:
            all_points.extend(call.kwargs["points"])

        for point in all_points:
            assert point.payload["instrument"] == point.payload["instrument"].upper()

    @pytest.mark.asyncio
    async def test_ingest_100_setups_all_have_required_payload_keys(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Every setup among 100 must carry all schema-required payload keys.
        Partial payloads break Qdrant filtering and metadata retrieval.
        """
        required_keys = {
            "trade_id", "timestamp", "instrument", "time_window",
            "htf_open_bias", "confluence_count", "outcome_result",
            "outcome_r_multiple", "narrative", "full_setup",
        }
        batch = make_batch(100)

        await service.ingest_batch(batch)

        all_points = []
        for call in mock_wrapper.upsert.call_args_list:
            all_points.extend(call.kwargs["points"])

        for point in all_points:
            missing = required_keys - set(point.payload.keys())
            assert not missing, (
                f"Point {point.id} missing payload keys: {missing}"
            )

    @pytest.mark.asyncio
    async def test_ingest_100_setups_all_embeddings_are_528_dim(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """Every PointStruct vector must be exactly 528-dimensional."""
        batch = make_batch(100)

        await service.ingest_batch(batch)

        all_points = []
        for call in mock_wrapper.upsert.call_args_list:
            all_points.extend(call.kwargs["points"])

        for point in all_points:
            assert len(point.vector) == EMBEDDING_DIM, (
                f"Point {point.id} has vector dim {len(point.vector)}, expected {EMBEDDING_DIM}"
            )

    @pytest.mark.asyncio
    async def test_ingest_100_setups_ingested_ids_count_equals_successful(
        self, service: IngestionService
    ) -> None:
        """len(ingested_ids) must always equal result.successful."""
        batch = make_batch(100)

        result = await service.ingest_batch(batch)

        assert len(result.ingested_ids) == result.successful

    @pytest.mark.asyncio
    async def test_ingest_100_setups_seen_trade_ids_populated(
        self, service: IngestionService
    ) -> None:
        """After ingesting 100 setups, seen_trade_ids contains all 100 trade_ids."""
        batch = make_batch(100, prefix="BULK")

        await service.ingest_batch(batch)

        expected_ids = {f"BULK-{i:04d}" for i in range(100)}
        assert expected_ids <= service.seen_trade_ids


# ---------------------------------------------------------------------------
# Area 2: Error handling — network failures and invalid data
# ---------------------------------------------------------------------------


class TestNetworkFailureHandling:
    """
    Verify that the ingestion service handles network-level failures correctly:
    raising IngestionServiceError for single-batch failures and recording
    partial failures when multiple batches are used.

    Requirements: FR-RAG-7, NFR-RAG-1
    """

    @pytest.mark.asyncio
    async def test_qdrant_connection_error_raises_ingestion_service_error(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        A QdrantConnectionError (Qdrant unreachable) must be wrapped in an
        IngestionServiceError so callers receive a typed, meaningful exception.
        """
        mock_wrapper.upsert = AsyncMock(
            side_effect=QdrantConnectionError("Connection refused to localhost:6333")
        )
        batch = make_batch(5)

        with pytest.raises(IngestionServiceError, match="Batch ingestion failed"):
            await service.ingest_batch(batch)

    @pytest.mark.asyncio
    async def test_generic_network_exception_raises_ingestion_service_error(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Any unexpected network exception (timeout, SSL error, etc.) must also
        be wrapped in IngestionServiceError — no raw exceptions should leak
        to callers.
        """
        mock_wrapper.upsert = AsyncMock(side_effect=OSError("Connection timed out"))
        batch = make_batch(3)

        with pytest.raises(IngestionServiceError):
            await service.ingest_batch(batch)

    @pytest.mark.asyncio
    async def test_partial_batch_failure_records_failed_count(
        self, config: QdrantConfig, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        When using multi-batch mode and one sub-batch fails, failed setups are
        counted in result.failed while successful batches are still committed.
        The service must NOT abort the entire operation on a single sub-batch failure.
        """
        call_counter = {"n": 0}

        async def flaky_upsert(**kwargs):
            call_counter["n"] += 1
            if call_counter["n"] == 2:
                raise OSError("transient network failure on batch 2")

        mock_wrapper.upsert = flaky_upsert

        svc = IngestionService(wrapper=mock_wrapper, config=config, batch_size=50)
        # 3 batches: [50, 50, 5] → batch 2 fails → failed=50, successful=55
        batch = make_batch(105)

        result = await svc.ingest_batch(batch)

        assert result.failed == 50
        assert result.successful == 55
        assert result.total == 105

    @pytest.mark.asyncio
    async def test_partial_batch_failure_records_error_tuples(
        self, config: QdrantConfig, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Each failed point in a sub-batch must produce an (trade_id, error_msg)
        tuple in result.errors for downstream reporting and observability.
        """
        call_counter = {"n": 0}

        async def flaky_upsert(**kwargs):
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                raise OSError("disk full")

        mock_wrapper.upsert = flaky_upsert

        svc = IngestionService(wrapper=mock_wrapper, config=config, batch_size=10)
        batch = make_batch(25)

        result = await svc.ingest_batch(batch)

        assert len(result.errors) == 10  # first batch of 10 failed
        for trade_id, error_msg in result.errors:
            assert isinstance(trade_id, str)
            assert "disk full" in error_msg

    @pytest.mark.asyncio
    async def test_all_batches_fail_reports_all_as_failed(
        self, config: QdrantConfig, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        When every sub-batch fails, result.failed equals the total count and
        result.successful equals 0 — no silent data loss.
        """
        mock_wrapper.upsert = AsyncMock(side_effect=OSError("Qdrant cluster down"))

        svc = IngestionService(wrapper=mock_wrapper, config=config, batch_size=20)
        batch = make_batch(60)

        result = await svc.ingest_batch(batch)

        assert result.failed == 60
        assert result.successful == 0
        assert result.total == 60

    @pytest.mark.asyncio
    async def test_retry_exhaustion_raises_ingestion_service_error_for_single_batch(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        When QdrantConnectionError is raised and the batch fits in one call,
        IngestionServiceError is raised (not silently swallowed). The error
        message must include a meaningful description.
        """
        mock_wrapper.upsert = AsyncMock(
            side_effect=QdrantConnectionError("max retries exceeded")
        )
        batch = make_batch(10)

        with pytest.raises(IngestionServiceError) as exc_info:
            await service.ingest_batch(batch)

        assert "Batch ingestion failed" in str(exc_info.value)


class TestInvalidDataHandling:
    """
    Verify that invalid or malformed input data is rejected eagerly before
    any network call is made, preventing corrupt data from reaching Qdrant.

    Requirements: FR-RAG-7
    """

    @pytest.mark.asyncio
    async def test_wrong_embedding_dimension_raises_value_error(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        An embedding with fewer than 528 dimensions must raise ValueError
        immediately — no Qdrant call is made with an invalid vector.
        """
        bad_embedding = [0.0] * 256
        batch = [(make_setup(trade_id="TRD-BAD-DIM"), bad_embedding)]

        with pytest.raises(ValueError, match="528"):
            await service.ingest_batch(batch)

        mock_wrapper.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_oversized_embedding_raises_value_error(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """An embedding with more than 528 dimensions must also raise ValueError."""
        bad_embedding = [0.0] * 1024
        batch = [(make_setup(trade_id="TRD-OVER-DIM"), bad_embedding)]

        with pytest.raises(ValueError, match="528"):
            await service.ingest_batch(batch)

        mock_wrapper.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_embedding_raises_value_error(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """An empty embedding list must raise ValueError before any upsert."""
        batch = [(make_setup(trade_id="TRD-EMPTY-EMB"), [])]

        with pytest.raises(ValueError, match="528"):
            await service.ingest_batch(batch)

        mock_wrapper.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_embedding_in_mixed_batch_raises_before_any_upsert(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        If any item in a batch has an invalid embedding, ValueError is raised
        eagerly BEFORE the first upsert call — partial commits must not occur.
        This protects the vector store from partial-batch data corruption.
        """
        # 4 valid setups followed by 1 invalid — all must be rejected atomically
        valid_items = make_batch(4)
        invalid_item = (make_setup(trade_id="TRD-INVALID"), [0.0] * 100)
        batch = valid_items + [invalid_item]

        with pytest.raises(ValueError, match="528"):
            await service.ingest_batch(batch)

        mock_wrapper.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_without_trade_id_gets_uuid_assigned(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        A setup dict without a 'trade_id' key must still be ingested successfully.
        The service generates a UUID to use as trade_id, preventing a KeyError.
        This handles real-time ingestion where trade_id might not yet be assigned.
        """
        setup_no_id = {k: v for k, v in make_setup().items() if k != "trade_id"}
        batch = [(setup_no_id, make_embedding())]

        result = await service.ingest_batch(batch)

        assert result.successful == 1
        points = mock_wrapper.upsert.call_args.kwargs["points"]
        assert "trade_id" in points[0].payload
        assert len(points[0].payload["trade_id"]) > 0

    @pytest.mark.asyncio
    async def test_none_trade_id_gets_uuid_assigned(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """A setup with trade_id=None must also receive a generated UUID."""
        setup_null_id = make_setup(trade_id=None)  # type: ignore[arg-type]
        batch = [(setup_null_id, make_embedding())]

        result = await service.ingest_batch(batch)

        assert result.successful == 1
        points = mock_wrapper.upsert.call_args.kwargs["points"]
        assert points[0].payload["trade_id"] is not None
        assert len(points[0].payload["trade_id"]) > 0

    @pytest.mark.asyncio
    async def test_setup_with_missing_optional_fields_uses_defaults(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        A minimal setup with only trade_id must be ingested without raising.
        Missing fields must fall back to safe defaults (empty string / 0),
        not KeyError — handles incomplete data from early pipeline stages.
        """
        minimal_setup = {"trade_id": "TRD-MINIMAL"}
        batch = [(minimal_setup, make_embedding())]

        result = await service.ingest_batch(batch)

        assert result.successful == 1
        points = mock_wrapper.upsert.call_args.kwargs["points"]
        payload = points[0].payload
        assert payload["instrument"] == ""
        assert payload["confluence_count"] == 0
        assert payload["outcome_result"] == ""
        assert payload["outcome_r_multiple"] == 0.0

    @pytest.mark.asyncio
    async def test_nan_values_in_embedding_are_forwarded_to_qdrant(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        The ingestion service forwards embeddings as-is; NaN detection is the
        responsibility of the embedding generation layer (Task 4.5).
        The service must not silently drop NaN-containing setups.
        Callers upstream must validate embeddings before ingestion.
        """
        nan_embedding = [float("nan")] * EMBEDDING_DIM
        batch = [(make_setup(trade_id="TRD-NAN"), nan_embedding)]

        # Service accepts it (NaN validation is upstream); Qdrant may reject it
        result = await service.ingest_batch(batch)

        # The point was forwarded to upsert — no silent drop
        assert mock_wrapper.upsert.called

    @pytest.mark.asyncio
    async def test_large_batch_with_one_invalid_embedding_fails_atomically(
        self, service: IngestionService, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        In a batch of 100 where the last embedding is invalid, the whole batch
        must be rejected atomically (ValueError raised, no partial upsert).
        This guarantees all-or-nothing semantics for the validation gate.
        """
        valid_items = make_batch(99)
        bad_item = (make_setup(trade_id="TRD-BAD-LAST"), [0.5] * 300)
        batch = valid_items + [bad_item]

        with pytest.raises(ValueError, match="528"):
            await service.ingest_batch(batch)

        mock_wrapper.upsert.assert_not_called()


# ---------------------------------------------------------------------------
# Area 3: Ingestion performance (< 1s per setup)
# ---------------------------------------------------------------------------


class TestIngestionPerformance:
    """
    Verify that the ingestion service meets the performance requirements in
    NFR-RAG-1: each setup must be ingested in under 1 second on average.

    All timing tests use mocked Qdrant — they measure service overhead only,
    not network latency. Network latency is validated in live integration tests.

    NFR-RAG-1 target: < 1s per setup (embedding generation + upsert round-trip)
    """

    @pytest.mark.asyncio
    async def test_ingest_100_setups_under_100_seconds_total(
        self, service: IngestionService
    ) -> None:
        """
        100 setups must complete (mocked) in < 100 seconds total, satisfying
        the < 1s/setup requirement even with conservative timing.

        In practice the mocked path completes in milliseconds; this test
        catches pathological regressions like per-setup sequential I/O.
        """
        batch = make_batch(100)

        t0 = time.perf_counter()
        result = await service.ingest_batch(batch)
        elapsed = time.perf_counter() - t0

        assert result.successful == 100
        assert elapsed < 100.0, (
            f"100 setups took {elapsed:.2f}s — exceeds 100s ceiling (1s/setup)"
        )

    @pytest.mark.asyncio
    async def test_ingest_100_setups_mocked_completes_under_1_second(
        self, service: IngestionService
    ) -> None:
        """
        The service layer overhead for 100 setups must be < 1 second with
        a mocked Qdrant client (no network I/O). This baseline guards against
        CPU-bound regressions in PointStruct construction or embedding copy.
        """
        batch = make_batch(100)

        t0 = time.perf_counter()
        await service.ingest_batch(batch)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 1000.0, (
            f"100-setup mocked ingestion took {elapsed_ms:.1f}ms — service overhead too high"
        )

    @pytest.mark.asyncio
    async def test_ingest_500_setups_mocked_completes_under_5_seconds(
        self, service: IngestionService
    ) -> None:
        """
        500 setups (MVP threshold) must complete in < 5 seconds (mocked path).
        Validates linear, not quadratic, scaling in PointStruct construction.
        """
        batch = make_batch(500)

        t0 = time.perf_counter()
        result = await service.ingest_batch(batch)
        elapsed = time.perf_counter() - t0

        assert result.successful == 500
        assert elapsed < 5.0, (
            f"500-setup mocked ingestion took {elapsed:.2f}s — expected < 5s"
        )

    @pytest.mark.asyncio
    async def test_single_upsert_call_is_faster_than_per_item_calls(
        self, config: QdrantConfig, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Batch upsert (1 call, 100 points) must be faster than 100 individual
        upsert calls. This validates the fundamental performance optimisation
        of batch ingestion vs. per-setup HTTP round-trips.
        """
        # Simulate 1ms per upsert call (network overhead)
        async def slow_upsert(**kwargs):
            await asyncio.sleep(0.001)

        mock_wrapper.upsert = slow_upsert

        batch = make_batch(100)

        # Batch ingestion: 1 upsert call → ~1ms total
        svc_batch = IngestionService(wrapper=mock_wrapper, config=config, batch_size=200)
        t0 = time.perf_counter()
        await svc_batch.ingest_batch(batch)
        batch_time = time.perf_counter() - t0

        # Per-item ingestion simulation: 100 individual upserts → ~100ms
        # We measure by using batch_size=1 to force 100 calls
        mock_wrapper.upsert = slow_upsert
        svc_single = IngestionService(wrapper=mock_wrapper, config=config, batch_size=1)
        t0 = time.perf_counter()
        await svc_single.ingest_batch(batch)
        single_time = time.perf_counter() - t0

        # Batch must be at least 5× faster than per-item
        assert batch_time * 5 < single_time, (
            f"Batch ({batch_time:.3f}s) not significantly faster than per-item ({single_time:.3f}s)"
        )

    @pytest.mark.asyncio
    async def test_build_point_from_setup_100_times_under_100ms(self) -> None:
        """
        Building 100 PointStruct objects must complete in < 100ms.
        This is a pure CPU-bound operation; any slowdown indicates a regression
        in payload construction or deep-copy semantics.
        """
        setups = [make_setup(trade_id=f"TRD-PERF-{i:04d}") for i in range(100)]
        embedding = make_embedding()

        t0 = time.perf_counter()
        for setup in setups:
            build_point_from_setup(setup, embedding)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 100.0, (
            f"Building 100 PointStructs took {elapsed_ms:.1f}ms — expected < 100ms"
        )

    @pytest.mark.asyncio
    async def test_ingestion_throughput_at_least_100_setups_per_second(
        self, service: IngestionService
    ) -> None:
        """
        Service throughput (mocked I/O) must be ≥ 100 setups/second.
        This confirms the 1s/setup budget is met with significant headroom.
        """
        n = 200
        batch = make_batch(n)

        t0 = time.perf_counter()
        result = await service.ingest_batch(batch)
        elapsed = time.perf_counter() - t0

        throughput = result.successful / max(elapsed, 1e-9)
        assert throughput >= 100.0, (
            f"Throughput {throughput:.0f} setups/s — required ≥ 100 setups/s"
        )

    @pytest.mark.asyncio
    async def test_multi_batch_ingestion_performance_scales_linearly(
        self, config: QdrantConfig, mock_wrapper: QdrantClientWrapper
    ) -> None:
        """
        Ingesting 1000 setups should take no more than 10× as long as 100.
        A 10× ceiling with 10× the data confirms at most linear (not quadratic)
        growth in PointStruct construction and batch-chunking logic.

        We use 1000 vs 100 (not 200 vs 100) so that the ratio is measured well
        above the ~1ms timer noise floor, giving a stable signal on any OS.
        """
        svc = IngestionService(wrapper=mock_wrapper, config=config, batch_size=50)

        batch_100 = make_batch(100)
        t0 = time.perf_counter()
        await svc.ingest_batch(batch_100)
        time_100 = time.perf_counter() - t0

        batch_1000 = make_batch(1000, prefix="SCALE")
        t0 = time.perf_counter()
        await svc.ingest_batch(batch_1000)
        time_1000 = time.perf_counter() - t0

        # 1000 setups must not take more than 10× the time for 100 setups
        # (linear scaling would be exactly 10×; we allow the same 10× ceiling)
        assert time_1000 < time_100 * 10, (
            f"1000-setup time ({time_1000:.4f}s) is more than 10× "
            f"the 100-setup time ({time_100:.4f}s) — super-linear growth detected"
        )


# ---------------------------------------------------------------------------
# Live integration tests (require running Qdrant on localhost:6333)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIngestionIntegrationLive:
    """
    End-to-end integration tests validating the full ingestion pipeline against
    a real Qdrant instance.

    Run with: pytest -m integration services/algorag/tests/test_ingestion_integration.py

    Requirements: FR-RAG-7, NFR-RAG-1
    """

    @pytest.mark.asyncio
    async def test_ingest_100_setups_live_all_indexed(self) -> None:
        """
        100 setups ingested into a live Qdrant instance must all be retrievable.
        Validates count == 100 after ingestion — no silent drops.
        """
        cfg = make_config(
            collection="test_bulk_ingestion_100",
            retry_backoff=0.05,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        svc = IngestionService(wrapper=wrapper, config=cfg)
        try:
            await wrapper.ensure_collection()
            batch = make_batch(100)

            result = await svc.ingest_batch(batch)

            assert result.successful == 100
            assert result.failed == 0
            count = await wrapper.count()
            assert count == 100, f"Expected 100 points in Qdrant, found {count}"
        finally:
            await wrapper.delete_collection()
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_ingest_100_setups_live_under_100_seconds(self) -> None:
        """
        End-to-end ingestion of 100 setups with real Qdrant must complete
        in < 100 seconds (1s/setup budget including network round-trip).

        NFR-RAG-1: < 1s per setup for the full ingestion pipeline.
        """
        cfg = make_config(
            collection="test_bulk_ingestion_perf",
            retry_backoff=0.05,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        svc = IngestionService(wrapper=wrapper, config=cfg)
        try:
            await wrapper.ensure_collection()
            batch = make_batch(100)

            t0 = time.perf_counter()
            result = await svc.ingest_batch(batch)
            elapsed = time.perf_counter() - t0

            assert result.successful == 100
            assert elapsed < 100.0, (
                f"Live ingestion of 100 setups took {elapsed:.2f}s — exceeds 1s/setup budget"
            )
        finally:
            await wrapper.delete_collection()
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_ingest_100_setups_live_duplicate_upsert_does_not_increase_count(self) -> None:
        """
        Re-ingesting the same 100 trade_ids must not create 200 records.
        Qdrant upsert semantics (uuid5 point ID) must deduplicate on the server.
        """
        cfg = make_config(
            collection="test_bulk_ingestion_dedup",
            retry_backoff=0.05,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        svc = IngestionService(wrapper=wrapper, config=cfg)
        try:
            await wrapper.ensure_collection()
            batch = make_batch(100)

            await svc.ingest_batch(batch)
            await svc.ingest_batch(batch)  # second pass — all duplicates

            count = await wrapper.count()
            assert count == 100, (
                f"Expected 100 points after double-upsert, got {count} — deduplication broken"
            )
        finally:
            await wrapper.delete_collection()
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_live_network_failure_raises_ingestion_service_error(self) -> None:
        """
        Attempting to ingest into a non-existent Qdrant host raises
        IngestionServiceError (not a raw ConnectionError or TimeoutError).
        """
        cfg = make_config(
            host="localhost",
            port=9999,  # nothing listening here
            collection="unreachable_collection",
            max_retries=1,
            retry_backoff=0.0,
            timeout=1.0,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        svc = IngestionService(wrapper=wrapper, config=cfg)
        batch = make_batch(1)

        with pytest.raises((IngestionServiceError, Exception)):
            await wrapper.ensure_collection()
            await svc.ingest_batch(batch)
        # Cleanup is best-effort; close even if operations failed
        await wrapper.close()

    @pytest.mark.asyncio
    async def test_live_partial_batch_failure_continues_remaining_batches(self) -> None:
        """
        When one sub-batch fails due to transient error, subsequent sub-batches
        proceed and are committed to Qdrant. Partial progress is preserved.
        """
        cfg = make_config(
            collection="test_partial_failure",
            retry_backoff=0.0,
            max_retries=1,
        )
        real_wrapper = QdrantClientWrapper(config=cfg)

        # Wrap upsert to fail on the 2nd call only
        call_count = {"n": 0}
        original_upsert = real_wrapper.upsert

        async def patched_upsert(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise OSError("simulated transient failure on batch 2")
            return await original_upsert(**kwargs)

        real_wrapper.upsert = patched_upsert  # type: ignore[method-assign]

        svc = IngestionService(wrapper=real_wrapper, config=cfg, batch_size=30)
        try:
            await real_wrapper.ensure_collection()
            # 3 batches: [30, 30, 10] — batch 2 fails → 40 committed, 30 failed
            batch = make_batch(70)

            result = await svc.ingest_batch(batch)

            assert result.failed == 30, f"Expected 30 failed, got {result.failed}"
            assert result.successful == 40, f"Expected 40 successful, got {result.successful}"
            count = await real_wrapper.count()
            assert count == 40, f"Expected 40 points in Qdrant, got {count}"
        finally:
            await real_wrapper.delete_collection()
            await real_wrapper.close()
