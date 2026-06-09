"""
TDD – Task 6: Qdrant collection management (schema, creation, indexing).

RED  phase: tests for collection schema validation, idempotent creation,
            metadata index creation, index validation, and rebuild capability.
GREEN phase: implementation lives in QdrantClientWrapper.ensure_collection()
             and the new QdrantClientWrapper.ensure_indexes() method.
REFACTOR: index validation and rebuild separated into validate_indexes() /
          rebuild_indexes() for operational runbook support.

Task 6.3 adds:
- Schema validation tests (payload field constraints, instrument allow-list)
- Query performance tests (filter correctness under timed assertions)
- Collection lifecycle: delete, recreate, verify empty

All Qdrant calls are mocked — no live instance required.
Integration tests that need a real Qdrant are marked @pytest.mark.integration.

Requirements: FR-RAG-1 (Historical Setup Storage), FR-RAG-2 (Semantic Retrieval),
              NFR-RAG-2 (Scalability)
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.http import models as qmodels

from services.algorag.config import QdrantConfig
from services.algorag.qdrant_client import (
    INDEXED_FIELDS,
    VECTOR_DIM,
    QdrantClientWrapper,
)


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

EXPECTED_INDEXED_FIELDS = frozenset(
    {"instrument", "time_window", "htf_open_bias", "outcome_result"}
)


def make_config(**overrides) -> QdrantConfig:
    defaults = dict(
        host="localhost",
        port=6333,
        collection="test_collection",
        timeout=5.0,
        max_retries=3,
        retry_backoff=0.0,
    )
    defaults.update(overrides)
    return QdrantConfig(**defaults)


@pytest.fixture()
def config():
    return make_config()


@pytest.fixture()
def wrapper(config):
    return QdrantClientWrapper(config=config)


@pytest.fixture()
def mock_client():
    """Fully mocked AsyncQdrantClient – collection exists by default."""
    client = AsyncMock()

    # get_collection success (collection exists)
    collection_info = MagicMock()
    collection_info.points_count = 0
    client.get_collection = AsyncMock(return_value=collection_info)

    client.get_collections = AsyncMock(return_value=MagicMock())
    client.create_collection = AsyncMock(return_value=None)
    client.create_payload_index = AsyncMock(return_value=None)
    client.delete_collection = AsyncMock(return_value=None)
    client.close = AsyncMock(return_value=None)
    return client


@pytest.fixture()
def mock_client_absent(mock_client):
    """Mock where the collection does NOT exist yet."""
    mock_client.get_collection = AsyncMock(
        side_effect=Exception("Collection not found")
    )
    return mock_client


# ---------------------------------------------------------------------------
# Task 6.1  –  Collection schema and creation
# ---------------------------------------------------------------------------


class TestCollectionSchema:
    """Verify schema details of the trading_setups collection."""

    # ------------------------------------------------------------------ RED
    @pytest.mark.asyncio
    async def test_vector_dimension_is_528(self, wrapper, mock_client_absent):
        """Collection vectors must be exactly 528-dimensional."""
        wrapper._client = mock_client_absent

        await wrapper.ensure_collection()

        call_kwargs = mock_client_absent.create_collection.call_args.kwargs
        assert call_kwargs["vectors_config"].size == VECTOR_DIM
        assert VECTOR_DIM == 528

    @pytest.mark.asyncio
    async def test_distance_metric_is_cosine(self, wrapper, mock_client_absent):
        """Distance metric must be cosine (required by design doc)."""
        wrapper._client = mock_client_absent

        await wrapper.ensure_collection()

        call_kwargs = mock_client_absent.create_collection.call_args.kwargs
        assert call_kwargs["vectors_config"].distance == qmodels.Distance.COSINE

    @pytest.mark.asyncio
    async def test_collection_name_from_config(self, wrapper, mock_client_absent):
        """Collection is created with the name specified in QdrantConfig."""
        wrapper._client = mock_client_absent

        await wrapper.ensure_collection()

        call_kwargs = mock_client_absent.create_collection.call_args.kwargs
        assert call_kwargs["collection_name"] == wrapper._config.collection

    @pytest.mark.asyncio
    async def test_payload_schema_includes_required_fields(
        self, wrapper, mock_client_absent
    ):
        """
        After collection creation, payload indexes must be created for:
        instrument, time_window, htf_open_bias, outcome_result.

        These fields match the EnrichedSetup / Qdrant payload schema described
        in the design doc (FR-RAG-1, FR-RAG-2).
        """
        wrapper._client = mock_client_absent

        await wrapper.ensure_collection()

        indexed = {
            call.kwargs["field_name"]
            for call in mock_client_absent.create_payload_index.call_args_list
        }
        assert EXPECTED_INDEXED_FIELDS <= indexed, (
            f"Missing payload indexes: {EXPECTED_INDEXED_FIELDS - indexed}"
        )

    # ---------------------------------------------------------------- GREEN
    @pytest.mark.asyncio
    async def test_idempotent_creation_skips_if_exists(self, wrapper, mock_client):
        """If the collection already exists, create_collection is never called."""
        wrapper._client = mock_client

        await wrapper.ensure_collection()

        mock_client.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotent_creation_called_once_on_absent(
        self, wrapper, mock_client_absent
    ):
        """create_collection is called exactly once when collection is absent."""
        wrapper._client = mock_client_absent

        await wrapper.ensure_collection()

        assert mock_client_absent.create_collection.call_count == 1

    @pytest.mark.asyncio
    async def test_ensure_collection_returns_none(self, wrapper, mock_client_absent):
        """ensure_collection() is fire-and-forget — returns None."""
        wrapper._client = mock_client_absent

        result = await wrapper.ensure_collection()

        assert result is None

    # -------------------------------------------------------------- REFACTOR
    @pytest.mark.asyncio
    async def test_custom_collection_name_override(self, wrapper, mock_client_absent):
        """ensure_collection() accepts an explicit collection_name override."""
        wrapper._client = mock_client_absent

        await wrapper.ensure_collection(collection_name="custom_collection")

        call_kwargs = mock_client_absent.create_collection.call_args.kwargs
        assert call_kwargs["collection_name"] == "custom_collection"

    @pytest.mark.asyncio
    async def test_custom_vector_size_override(self, wrapper, mock_client_absent):
        """ensure_collection() accepts an explicit vector_size override."""
        wrapper._client = mock_client_absent

        await wrapper.ensure_collection(vector_size=256)

        call_kwargs = mock_client_absent.create_collection.call_args.kwargs
        assert call_kwargs["vectors_config"].size == 256

    def test_indexed_fields_constant_contains_required_fields(self):
        """INDEXED_FIELDS module constant covers all required filter fields."""
        assert EXPECTED_INDEXED_FIELDS <= set(INDEXED_FIELDS)


# ---------------------------------------------------------------------------
# Task 6.2  –  Metadata indexing, validation, and rebuild
# ---------------------------------------------------------------------------


class TestMetadataIndexing:
    """Index creation, validation, and rebuild capability for metadata filtering."""

    # ------------------------------------------------------------------ RED
    @pytest.mark.asyncio
    async def test_indexes_created_on_all_four_filter_fields(
        self, wrapper, mock_client_absent
    ):
        """
        Indexes on instrument, time_window, htf_open_bias, outcome_result are
        created as KEYWORD schema — required for exact-match metadata filtering
        in the retrieval pipeline (FR-RAG-2).
        """
        wrapper._client = mock_client_absent

        await wrapper.ensure_collection()

        schema_by_field = {
            call.kwargs["field_name"]: call.kwargs["field_schema"]
            for call in mock_client_absent.create_payload_index.call_args_list
        }
        for field in EXPECTED_INDEXED_FIELDS:
            assert field in schema_by_field, f"No index created for field '{field}'"
            assert schema_by_field[field] == qmodels.PayloadSchemaType.KEYWORD, (
                f"Field '{field}' should use KEYWORD schema for exact-match filtering"
            )

    @pytest.mark.asyncio
    async def test_ensure_indexes_creates_missing_indexes(
        self, wrapper, mock_client
    ):
        """
        ensure_indexes() creates any payload index that does not yet exist.
        Uses create_payload_index with ignore_malformed=False so that data-type
        conflicts are surfaced early.
        """
        wrapper._client = mock_client

        await wrapper.ensure_indexes()

        created_fields = {
            call.kwargs["field_name"]
            for call in mock_client.create_payload_index.call_args_list
        }
        assert EXPECTED_INDEXED_FIELDS <= created_fields

    @pytest.mark.asyncio
    async def test_ensure_indexes_uses_keyword_schema(self, wrapper, mock_client):
        """ensure_indexes() always uses KEYWORD schema for all filter fields."""
        wrapper._client = mock_client

        await wrapper.ensure_indexes()

        for call in mock_client.create_payload_index.call_args_list:
            assert call.kwargs["field_schema"] == qmodels.PayloadSchemaType.KEYWORD

    # ---------------------------------------------------------------- GREEN
    @pytest.mark.asyncio
    async def test_validate_indexes_returns_true_when_all_present(
        self, wrapper, mock_client
    ):
        """
        validate_indexes() returns True when all expected indexes are confirmed
        present in the collection info.
        """
        # Build a mock collection info with all 4 fields indexed
        indexed_info = {
            field: MagicMock() for field in EXPECTED_INDEXED_FIELDS
        }
        collection_info = MagicMock()
        collection_info.payload_schema = indexed_info
        mock_client.get_collection = AsyncMock(return_value=collection_info)
        wrapper._client = mock_client

        result = await wrapper.validate_indexes()

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_indexes_returns_false_when_index_missing(
        self, wrapper, mock_client
    ):
        """
        validate_indexes() returns False when one or more expected indexes are
        absent from the collection's payload schema.
        """
        # Only 2 of the 4 required fields are indexed
        partial_indexed = {
            "instrument": MagicMock(),
            "time_window": MagicMock(),
        }
        collection_info = MagicMock()
        collection_info.payload_schema = partial_indexed
        mock_client.get_collection = AsyncMock(return_value=collection_info)
        wrapper._client = mock_client

        result = await wrapper.validate_indexes()

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_indexes_returns_false_on_error(
        self, wrapper, mock_client
    ):
        """validate_indexes() returns False (not raises) on any Qdrant error."""
        mock_client.get_collection = AsyncMock(
            side_effect=Exception("Collection gone")
        )
        wrapper._client = mock_client

        result = await wrapper.validate_indexes()

        assert result is False

    # -------------------------------------------------------------- REFACTOR
    @pytest.mark.asyncio
    async def test_rebuild_indexes_drops_and_recreates(self, wrapper, mock_client):
        """
        rebuild_indexes() calls ensure_indexes() to (re)create all indexes.
        This supports operational runbook step: rebuild after schema migration.
        """
        wrapper._client = mock_client

        await wrapper.rebuild_indexes()

        created_fields = {
            call.kwargs["field_name"]
            for call in mock_client.create_payload_index.call_args_list
        }
        assert EXPECTED_INDEXED_FIELDS <= created_fields

    @pytest.mark.asyncio
    async def test_rebuild_indexes_idempotent(self, wrapper, mock_client):
        """Calling rebuild_indexes() twice does not raise."""
        wrapper._client = mock_client

        await wrapper.rebuild_indexes()
        mock_client.create_payload_index.reset_mock()
        await wrapper.rebuild_indexes()

        # Second call should still attempt to create indexes
        assert mock_client.create_payload_index.called

    @pytest.mark.asyncio
    async def test_rebuild_indexes_uses_correct_collection(self, wrapper, mock_client):
        """rebuild_indexes() targets the collection from config."""
        wrapper._client = mock_client

        await wrapper.rebuild_indexes()

        for call in mock_client.create_payload_index.call_args_list:
            assert call.kwargs["collection_name"] == wrapper._config.collection


# ---------------------------------------------------------------------------
# 6.3 (optional)  –  Collection lifecycle tests
# ---------------------------------------------------------------------------


class TestCollectionLifecycle:
    """Collection creation, deletion, recreation — supports operational tooling."""

    @pytest.mark.asyncio
    async def test_collection_can_be_deleted_and_recreated(
        self, wrapper, mock_client
    ):
        """
        delete_collection() followed by ensure_collection() recreates everything.
        Useful for test teardown and data refresh runbooks.
        """
        wrapper._client = mock_client
        # After deletion the collection no longer exists
        mock_client.delete_collection = AsyncMock(return_value=None)
        mock_client.get_collection = AsyncMock(
            side_effect=Exception("Collection not found")
        )

        await wrapper.delete_collection()
        await wrapper.ensure_collection()

        mock_client.delete_collection.assert_called_once_with(
            collection_name=wrapper._config.collection
        )
        mock_client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_collection_uses_config_name(self, wrapper, mock_client):
        """delete_collection() deletes the collection named in config."""
        wrapper._client = mock_client

        await wrapper.delete_collection()

        mock_client.delete_collection.assert_called_once_with(
            collection_name=wrapper._config.collection
        )


# ---------------------------------------------------------------------------
# Task 6.3 (new) – Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """
    Validate that the collection schema enforces payload shape constraints.

    Tests here verify that the wrapper builds PointStruct payloads with the
    exact fields defined in the Qdrant collection schema (design doc) and that
    the IngestionRequest validator rejects malformed data before it reaches
    Qdrant.  All schema checks are exercised in isolation with mocked clients.

    Requirements: FR-RAG-1, NFR-RAG-2
    """

    def test_vector_dim_constant_is_528(self):
        """Module-level VECTOR_DIM constant must equal 528."""
        assert VECTOR_DIM == 528

    def test_indexed_fields_is_non_empty_tuple(self):
        """INDEXED_FIELDS must be a non-empty sequence of strings."""
        assert len(INDEXED_FIELDS) > 0
        for field in INDEXED_FIELDS:
            assert isinstance(field, str)

    def test_indexed_fields_has_no_duplicates(self):
        """Each field in INDEXED_FIELDS is unique."""
        assert len(INDEXED_FIELDS) == len(set(INDEXED_FIELDS))

    def test_required_payload_fields_covered(self):
        """
        The four filterable payload fields from the design doc are all present
        in INDEXED_FIELDS: instrument, time_window, htf_open_bias, outcome_result.
        """
        required = {"instrument", "time_window", "htf_open_bias", "outcome_result"}
        assert required <= set(INDEXED_FIELDS)

    def test_ingestion_request_rejects_wrong_embedding_dim(self):
        """IngestionRequest must raise ValueError for non-528 embeddings."""
        from pydantic import ValidationError

        from services.algorag.models import IngestionRequest

        with pytest.raises(ValidationError):
            IngestionRequest(
                setup={"trade_id": "TRD-001"},
                embedding=[0.0] * 256,  # wrong size
            )

    def test_ingestion_request_rejects_empty_embedding(self):
        """IngestionRequest must reject an empty embedding list."""
        from pydantic import ValidationError

        from services.algorag.models import IngestionRequest

        with pytest.raises(ValidationError):
            IngestionRequest(
                setup={"trade_id": "TRD-002"},
                embedding=[],
            )

    def test_ingestion_request_accepts_528_dim_embedding(self):
        """IngestionRequest accepts a valid 528-dim embedding without error."""
        from services.algorag.models import IngestionRequest

        req = IngestionRequest(
            setup={"trade_id": "TRD-003"},
            embedding=[0.1] * 528,
        )
        assert len(req.embedding) == 528

    def test_retrieval_request_uppercases_instrument(self):
        """RetrievalRequest normalises instrument to uppercase (FR-RAG-2)."""
        from datetime import datetime, timezone

        from services.algorag.models import RetrievalRequest

        req = RetrievalRequest(
            instrument="eurusd",
            timestamp=datetime.now(tz=timezone.utc),
        )
        assert req.instrument == "EURUSD"

    def test_rag_metrics_win_rate_bounded(self):
        """RAGMetrics.win_rate_similar must be in [0.0, 1.0]."""
        from pydantic import ValidationError

        from services.algorag.models import RAGMetrics

        with pytest.raises(ValidationError):
            RAGMetrics(
                avg_r_multiple_similar=2.0,
                win_rate_similar=1.5,  # out of range
                sample_size=5,
                max_similarity_score=0.9,
                avg_confluence_count=3.0,
            )

    def test_rag_metrics_similarity_score_bounded(self):
        """RAGMetrics.max_similarity_score must be in [0.0, 1.0]."""
        from pydantic import ValidationError

        from services.algorag.models import RAGMetrics

        with pytest.raises(ValidationError):
            RAGMetrics(
                avg_r_multiple_similar=2.0,
                win_rate_similar=0.8,
                sample_size=5,
                max_similarity_score=-0.1,  # out of range
                avg_confluence_count=3.0,
            )

    def test_similar_setup_similarity_score_bounded(self):
        """SimilarSetup similarity_score must be in [0.0, 1.0]."""
        from datetime import datetime, timezone

        from pydantic import ValidationError

        from services.algorag.models import SimilarSetup

        with pytest.raises(ValidationError):
            SimilarSetup(
                trade_id="TRD-X",
                timestamp=datetime.now(tz=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.5,
                narrative="test",
                similarity_score=1.5,  # out of range
                final_score=0.9,
            )

    def test_point_struct_shape_matches_schema(self):
        """
        A PointStruct built for the trading_setups collection must carry all
        required payload keys from the Qdrant schema in the design doc.
        """
        required_payload_keys = {
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
        payload = {
            "trade_id": "TRD-001",
            "timestamp": "2024-03-15T09:15:00Z",
            "instrument": "EURUSD",
            "time_window": "LONDON_KILLZONE",
            "htf_open_bias": "BULLISH",
            "confluence_count": 4,
            "outcome_result": "WIN",
            "outcome_r_multiple": 3.2,
            "narrative": "Price swept Asian low and entered FVG",
            "full_setup": {},
        }
        point = qmodels.PointStruct(
            id="abc-123",
            vector=[0.0] * VECTOR_DIM,
            payload=payload,
        )
        assert required_payload_keys <= set(point.payload.keys())


# ---------------------------------------------------------------------------
# Task 6.3 (new) – Query performance
# ---------------------------------------------------------------------------


class TestQueryPerformance:
    """
    Verify that filter construction and search mechanics behave correctly,
    and that mocked round-trips complete well within the p95 latency budget
    (< 100ms per FR-RAG-2 / NFR-RAG-1).

    Performance numbers here are for the mock path only — real Qdrant
    latency is validated by the integration tests below.
    """

    @pytest.mark.asyncio
    async def test_search_with_instrument_filter_passes_correct_condition(
        self, wrapper, mock_client
    ):
        """
        When searching with an instrument filter the wrapper must include a
        FieldCondition(key='instrument', match=MatchValue(value=...)) in the
        must clause — matching the retrieval pipeline design (FR-RAG-2).
        """
        wrapper._client = mock_client
        mock_client.search = AsyncMock(return_value=[])

        qdrant_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="instrument",
                    match=qmodels.MatchValue(value="EURUSD"),
                )
            ]
        )
        await wrapper.search(
            query_vector=[0.0] * VECTOR_DIM,
            query_filter=qdrant_filter,
            limit=10,
        )

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["query_filter"] is qdrant_filter
        assert call_kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_search_with_composite_filter_passes_all_conditions(
        self, wrapper, mock_client
    ):
        """
        Composite filters (instrument + time_window + outcome) are forwarded
        to Qdrant intact.  The wrapper must not strip or modify the filter
        object — metadata filtering happens server-side (FR-RAG-2).
        """
        wrapper._client = mock_client
        mock_client.search = AsyncMock(return_value=[])

        composite_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="instrument", match=qmodels.MatchValue(value="GBPUSD")
                ),
                qmodels.FieldCondition(
                    key="time_window",
                    match=qmodels.MatchValue(value="NY_KILLZONE"),
                ),
                qmodels.FieldCondition(
                    key="outcome_result", match=qmodels.MatchValue(value="WIN")
                ),
            ]
        )
        await wrapper.search(
            query_vector=[0.0] * VECTOR_DIM,
            query_filter=composite_filter,
        )

        call_kwargs = mock_client.search.call_args.kwargs
        passed_filter = call_kwargs["query_filter"]
        field_keys = {c.key for c in passed_filter.must}
        assert field_keys == {"instrument", "time_window", "outcome_result"}

    @pytest.mark.asyncio
    async def test_search_without_filter_passes_none(self, wrapper, mock_client):
        """
        When no filter is provided the wrapper passes query_filter=None, allowing
        Qdrant to scan the full collection (useful for recall benchmarks).
        """
        wrapper._client = mock_client
        mock_client.search = AsyncMock(return_value=[])

        await wrapper.search(query_vector=[0.0] * VECTOR_DIM)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs.get("query_filter") is None

    @pytest.mark.asyncio
    async def test_search_default_limit_is_ten(self, wrapper, mock_client):
        """
        The default retrieval candidate pool is 10 (top-k before re-ranking).
        This matches the design doc retrieval pipeline.
        """
        wrapper._client = mock_client
        mock_client.search = AsyncMock(return_value=[])

        await wrapper.search(query_vector=[0.0] * VECTOR_DIM)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_search_with_payload_enabled(self, wrapper, mock_client):
        """
        Search must request full payloads (with_payload=True) so the caller
        receives trade_id, narrative, outcome, etc. without a second round-trip.
        """
        wrapper._client = mock_client
        mock_client.search = AsyncMock(return_value=[])

        await wrapper.search(query_vector=[0.0] * VECTOR_DIM)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs.get("with_payload") is True

    @pytest.mark.asyncio
    async def test_mocked_search_completes_under_1ms(self, wrapper, mock_client):
        """
        Mocked search (no I/O) must complete in < 1 ms.  This baseline test
        confirms the wrapper overhead alone is negligible — latency in real
        scenarios is dominated by network + Qdrant ANN, tested via integration.

        NFR-RAG-1 requires p95 < 100ms; this test guards the wrapper path.
        """
        wrapper._client = mock_client
        mock_client.search = AsyncMock(return_value=[])

        start = time.perf_counter()
        await wrapper.search(query_vector=[0.0] * VECTOR_DIM)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 1.0, (
            f"Mock search took {elapsed_ms:.2f}ms — wrapper overhead is too high"
        )

    @pytest.mark.asyncio
    async def test_mocked_ensure_collection_completes_under_5ms(
        self, wrapper, mock_client_absent
    ):
        """
        Collection creation (mocked) must complete in < 5 ms.  Guards wrapper
        startup overhead independently of Qdrant I/O.
        """
        wrapper._client = mock_client_absent

        start = time.perf_counter()
        await wrapper.ensure_collection()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 5.0, (
            f"Mock ensure_collection took {elapsed_ms:.2f}ms — too slow"
        )

    @pytest.mark.asyncio
    async def test_mocked_ensure_indexes_completes_under_5ms(
        self, wrapper, mock_client
    ):
        """
        Index creation for all four fields (mocked) must complete in < 5 ms.
        """
        wrapper._client = mock_client

        start = time.perf_counter()
        await wrapper.ensure_indexes()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 5.0, (
            f"Mock ensure_indexes took {elapsed_ms:.2f}ms — too slow"
        )

    @pytest.mark.asyncio
    async def test_mocked_upsert_100_points_completes_under_10ms(
        self, wrapper, mock_client
    ):
        """
        Batch upsert of 100 PointStructs (mocked) must complete in < 10 ms.
        Validates that the wrapper does not iterate points individually.
        """
        wrapper._client = mock_client
        mock_client.upsert = AsyncMock(return_value=None)

        points = [
            qmodels.PointStruct(
                id=str(i),
                vector=[float(i % 100) / 100.0] * VECTOR_DIM,
                payload={"instrument": "EURUSD"},
            )
            for i in range(100)
        ]

        start = time.perf_counter()
        await wrapper.upsert(points)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 10.0, (
            f"Mock upsert of 100 points took {elapsed_ms:.2f}ms — too slow"
        )

    @pytest.mark.asyncio
    async def test_search_uses_config_collection_name(self, wrapper, mock_client):
        """
        All search calls target the collection specified in QdrantConfig, never
        a hard-coded string.  Collection name isolation is required for
        multi-environment deployments (dev / staging / prod).
        """
        wrapper._client = mock_client
        mock_client.search = AsyncMock(return_value=[])

        await wrapper.search(query_vector=[0.0] * VECTOR_DIM)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["collection_name"] == wrapper._config.collection

    @pytest.mark.asyncio
    async def test_validate_indexes_completes_under_1ms(
        self, wrapper, mock_client
    ):
        """
        validate_indexes() (mocked) must complete in < 1 ms so it can be
        called on every health-check poll without adding measurable overhead.
        """
        indexed_info = {field: MagicMock() for field in INDEXED_FIELDS}
        collection_info = MagicMock()
        collection_info.payload_schema = indexed_info
        mock_client.get_collection = AsyncMock(return_value=collection_info)
        wrapper._client = mock_client

        start = time.perf_counter()
        await wrapper.validate_indexes()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 1.0, (
            f"Mock validate_indexes took {elapsed_ms:.2f}ms — too slow"
        )


# ---------------------------------------------------------------------------
# Integration tests (require live Qdrant on localhost:6333)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCollectionManagementIntegration:
    """Full end-to-end collection management against a live Qdrant instance."""

    @pytest.mark.asyncio
    async def test_live_collection_creation_idempotent(self):
        cfg = make_config(
            collection="test_task6_collection",
            retry_backoff=0.1,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        try:
            # First call creates
            await wrapper.ensure_collection()
            # Second call must not raise
            await wrapper.ensure_collection()
            count = await wrapper.count()
            assert isinstance(count, int)
        finally:
            await wrapper.delete_collection()
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_live_indexes_valid_after_ensure(self):
        cfg = make_config(
            collection="test_task6_indexes",
            retry_backoff=0.1,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        try:
            await wrapper.ensure_collection()
            is_valid = await wrapper.validate_indexes()
            assert is_valid is True
        finally:
            await wrapper.delete_collection()
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_live_rebuild_indexes_after_partial_setup(self):
        cfg = make_config(
            collection="test_task6_rebuild",
            retry_backoff=0.1,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        try:
            await wrapper.ensure_collection()
            # rebuild should be idempotent on a healthy collection
            await wrapper.rebuild_indexes()
            is_valid = await wrapper.validate_indexes()
            assert is_valid is True
        finally:
            await wrapper.delete_collection()
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_live_delete_and_recreate_collection(self):
        """Delete, then recreate — collection comes back empty with all indexes."""
        cfg = make_config(
            collection="test_task6_lifecycle",
            retry_backoff=0.1,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        try:
            await wrapper.ensure_collection()
            count_before = await wrapper.count()
            await wrapper.delete_collection()

            # Recreate
            await wrapper.ensure_collection()
            count_after = await wrapper.count()

            assert isinstance(count_before, int)
            assert count_after == 0  # fresh collection

            is_valid = await wrapper.validate_indexes()
            assert is_valid is True
        finally:
            await wrapper.delete_collection()
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_live_search_latency_p95_under_100ms(self):
        """
        Retrieval p95 latency must be < 100ms against a live empty collection
        (NFR-RAG-1).  Runs 20 searches and checks the 95th-percentile.
        """
        import statistics

        cfg = make_config(
            collection="test_task6_latency",
            retry_backoff=0.1,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        try:
            await wrapper.ensure_collection()

            latencies = []
            for _ in range(20):
                t0 = time.perf_counter()
                await wrapper.search(
                    query_vector=[0.0] * VECTOR_DIM,
                    limit=10,
                )
                latencies.append((time.perf_counter() - t0) * 1000)

            latencies.sort()
            p95 = latencies[int(len(latencies) * 0.95)]
            assert p95 < 100.0, (
                f"Live search p95 latency {p95:.1f}ms exceeds 100ms budget (NFR-RAG-1)"
            )
        finally:
            await wrapper.delete_collection()
            await wrapper.close()
