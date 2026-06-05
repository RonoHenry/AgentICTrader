"""
TDD – Task 1.2: Integration tests for QdrantClientWrapper.

RED  phase: tests for connection, collection management, CRUD, reliability, and health.
GREEN phase: implementation in services/algorag/qdrant_client.py.
REFACTOR: config driven by environment variables in services/algorag/config.py.

All external calls are mocked — no live Qdrant instance required.
Tests that would need a real Qdrant are marked @pytest.mark.integration.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.algorag.config import QdrantConfig
from services.algorag.qdrant_client import QdrantClientWrapper, QdrantConnectionError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_config(**overrides) -> QdrantConfig:
    """Return a QdrantConfig with test-friendly defaults."""
    defaults = dict(
        host="localhost",
        port=6333,
        collection="test_collection",
        timeout=5.0,
        max_retries=3,
        retry_backoff=0.0,  # no sleep in tests
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
def mock_async_client():
    """A fully mocked AsyncQdrantClient."""
    client = AsyncMock()
    # get_collections – success
    client.get_collections = AsyncMock(return_value=MagicMock())
    # get_collection – success (collection exists)
    collection_info = MagicMock()
    collection_info.points_count = 10
    client.get_collection = AsyncMock(return_value=collection_info)
    # upsert / search / delete
    client.upsert = AsyncMock(return_value=MagicMock())
    client.search = AsyncMock(return_value=[])
    client.delete = AsyncMock(return_value=MagicMock())
    client.create_collection = AsyncMock(return_value=MagicMock())
    client.create_payload_index = AsyncMock(return_value=MagicMock())
    client.close = AsyncMock(return_value=None)
    return client


# ---------------------------------------------------------------------------
# 1. Connection tests
# ---------------------------------------------------------------------------


class TestConnection:
    """Client initialisation and environment variable handling."""

    def test_connect_success(self, config):
        """Wrapper creates AsyncQdrantClient with the correct host/port from config."""
        wrapper = QdrantClientWrapper(config=config)
        with patch("services.algorag.qdrant_client.AsyncQdrantClient") as MockClient:
            MockClient.return_value = MagicMock()
            client = wrapper.get_client()
            MockClient.assert_called_once_with(
                host=config.host,
                port=config.port,
                timeout=config.timeout,
            )
            assert client is not None

    def test_connect_uses_env_host(self, monkeypatch):
        """QDRANT_HOST env var is respected."""
        monkeypatch.setenv("QDRANT_HOST", "qdrant-server")
        cfg = QdrantConfig()
        assert cfg.host == "qdrant-server"

    def test_connect_uses_env_port(self, monkeypatch):
        """QDRANT_PORT env var is respected."""
        monkeypatch.setenv("QDRANT_PORT", "6400")
        cfg = QdrantConfig()
        assert cfg.port == 6400

    def test_connect_uses_env_collection(self, monkeypatch):
        """QDRANT_COLLECTION env var is respected."""
        monkeypatch.setenv("QDRANT_COLLECTION", "my_collection")
        cfg = QdrantConfig()
        assert cfg.collection == "my_collection"

    def test_connect_uses_env_timeout(self, monkeypatch):
        """QDRANT_TIMEOUT env var is respected."""
        monkeypatch.setenv("QDRANT_TIMEOUT", "12.5")
        cfg = QdrantConfig()
        assert cfg.timeout == 12.5


# ---------------------------------------------------------------------------
# 2. Collection management tests
# ---------------------------------------------------------------------------


class TestCollectionManagement:
    """ensure_collection creates / skips idempotently."""

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_when_absent(self, wrapper, mock_async_client):
        """Creates collection with 528-dim cosine vectors when it doesn't exist."""
        from qdrant_client.http.exceptions import UnexpectedResponse

        # Simulate collection not found
        mock_async_client.get_collection = AsyncMock(
            side_effect=Exception("Collection not found")
        )
        wrapper._client = mock_async_client

        await wrapper.ensure_collection()

        mock_async_client.create_collection.assert_called_once()
        call_kwargs = mock_async_client.create_collection.call_args.kwargs
        assert call_kwargs["collection_name"] == wrapper._config.collection

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_when_exists(self, wrapper, mock_async_client):
        """Does not call create_collection when collection already exists."""
        wrapper._client = mock_async_client

        await wrapper.ensure_collection()

        mock_async_client.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_collection_schema_uses_cosine_distance(self, wrapper, mock_async_client):
        """Collection is created with cosine distance metric."""
        from qdrant_client.http import models as qmodels

        mock_async_client.get_collection = AsyncMock(
            side_effect=Exception("Collection not found")
        )
        wrapper._client = mock_async_client

        await wrapper.ensure_collection()

        call_kwargs = mock_async_client.create_collection.call_args.kwargs
        vectors_config = call_kwargs["vectors_config"]
        assert vectors_config.distance == qmodels.Distance.COSINE

    @pytest.mark.asyncio
    async def test_collection_vector_size_is_528(self, wrapper, mock_async_client):
        """Collection is created with 528-dimensional vectors."""
        mock_async_client.get_collection = AsyncMock(
            side_effect=Exception("Collection not found")
        )
        wrapper._client = mock_async_client

        await wrapper.ensure_collection()

        call_kwargs = mock_async_client.create_collection.call_args.kwargs
        vectors_config = call_kwargs["vectors_config"]
        assert vectors_config.size == 528


# ---------------------------------------------------------------------------
# 3. CRUD operation tests
# ---------------------------------------------------------------------------


class TestCRUDOperations:
    """upsert, search, delete, count."""

    @pytest.mark.asyncio
    async def test_upsert_single_point(self, wrapper, mock_async_client):
        """Inserts a single point with embedding + payload."""
        from qdrant_client.http import models as qmodels

        wrapper._client = mock_async_client
        point = qmodels.PointStruct(
            id="abc123",
            vector=[0.0] * 528,
            payload={"instrument": "EURUSD"},
        )

        await wrapper.upsert([point])

        mock_async_client.upsert.assert_called_once()
        call_kwargs = mock_async_client.upsert.call_args.kwargs
        assert call_kwargs["collection_name"] == wrapper._config.collection
        assert call_kwargs["points"] == [point]

    @pytest.mark.asyncio
    async def test_upsert_batch_points(self, wrapper, mock_async_client):
        """Inserts multiple points in one call."""
        from qdrant_client.http import models as qmodels

        wrapper._client = mock_async_client
        points = [
            qmodels.PointStruct(id=str(i), vector=[float(i)] * 528, payload={})
            for i in range(5)
        ]

        await wrapper.upsert(points)

        mock_async_client.upsert.assert_called_once()
        call_kwargs = mock_async_client.upsert.call_args.kwargs
        assert len(call_kwargs["points"]) == 5

    @pytest.mark.asyncio
    async def test_search_returns_results(self, wrapper, mock_async_client):
        """Vector search returns hits from Qdrant."""
        hit = MagicMock()
        hit.score = 0.95
        hit.payload = {"instrument": "EURUSD"}
        mock_async_client.search = AsyncMock(return_value=[hit])
        wrapper._client = mock_async_client

        results = await wrapper.search(query_vector=[0.0] * 528, limit=5)

        assert len(results) == 1
        assert results[0].score == 0.95

    @pytest.mark.asyncio
    async def test_search_with_filter(self, wrapper, mock_async_client):
        """Metadata filter is passed through to Qdrant search."""
        from qdrant_client.http import models as qmodels

        wrapper._client = mock_async_client
        qdrant_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="instrument",
                    match=qmodels.MatchValue(value="GBPUSD"),
                )
            ]
        )

        await wrapper.search(query_vector=[0.0] * 528, query_filter=qdrant_filter)

        mock_async_client.search.assert_called_once()
        call_kwargs = mock_async_client.search.call_args.kwargs
        assert call_kwargs["query_filter"] is qdrant_filter

    @pytest.mark.asyncio
    async def test_delete_point_by_id(self, wrapper, mock_async_client):
        """Deletes a point by UUID."""
        wrapper._client = mock_async_client
        point_id = "550e8400-e29b-41d4-a716-446655440000"

        await wrapper.delete([point_id])

        mock_async_client.delete.assert_called_once()
        call_kwargs = mock_async_client.delete.call_args.kwargs
        assert call_kwargs["collection_name"] == wrapper._config.collection

    @pytest.mark.asyncio
    async def test_count_returns_integer(self, wrapper, mock_async_client):
        """count() returns a non-negative integer."""
        collection_info = MagicMock()
        collection_info.points_count = 7
        mock_async_client.get_collection = AsyncMock(return_value=collection_info)
        wrapper._client = mock_async_client

        count = await wrapper.count()

        assert isinstance(count, int)
        assert count >= 0
        assert count == 7


# ---------------------------------------------------------------------------
# 4. Connection pooling / reliability tests
# ---------------------------------------------------------------------------


class TestConnectionPoolingAndReliability:
    """Singleton, close, retry, and graceful degradation."""

    def test_client_is_singleton(self, wrapper):
        """Calling get_client() twice returns the same instance."""
        with patch("services.algorag.qdrant_client.AsyncQdrantClient") as MockClient:
            MockClient.return_value = MagicMock()
            c1 = wrapper.get_client()
            c2 = wrapper.get_client()
            assert c1 is c2
            MockClient.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_releases_connection(self, wrapper, mock_async_client):
        """close() calls the underlying client's close method."""
        wrapper._client = mock_async_client

        await wrapper.close()

        mock_async_client.close.assert_called_once()
        assert wrapper._client is None

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self, wrapper, mock_async_client):
        """Retries up to max_retries on connection error, then raises QdrantConnectionError."""
        call_count = 0

        async def failing_upsert(**kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("transient failure")

        mock_async_client.upsert = failing_upsert
        wrapper._client = mock_async_client

        from qdrant_client.http import models as qmodels

        point = qmodels.PointStruct(id="x", vector=[0.0] * 528, payload={})

        with pytest.raises(QdrantConnectionError):
            await wrapper.upsert([point])

        assert call_count == wrapper._config.max_retries

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_failure(self, wrapper, mock_async_client):
        """Operations fail with a well-typed QdrantConnectionError, not a raw crash."""
        mock_async_client.upsert = AsyncMock(side_effect=RuntimeError("unexpected"))
        wrapper._client = mock_async_client

        from qdrant_client.http import models as qmodels

        point = qmodels.PointStruct(id="y", vector=[0.0] * 528, payload={})

        with pytest.raises(QdrantConnectionError) as exc_info:
            await wrapper.upsert([point])

        # Must be our typed error, not the raw RuntimeError
        assert "QdrantConnectionError" in type(exc_info.value).__name__


# ---------------------------------------------------------------------------
# 5. Health check helper tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """is_healthy() returns True/False based on get_collections() outcome."""

    @pytest.mark.asyncio
    async def test_is_healthy_when_connected(self, wrapper, mock_async_client):
        """Returns True when get_collections() succeeds."""
        wrapper._client = mock_async_client

        result = await wrapper.is_healthy()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_healthy_false_when_disconnected(self, wrapper, mock_async_client):
        """Returns False when get_collections() raises an exception."""
        mock_async_client.get_collections = AsyncMock(
            side_effect=ConnectionError("Qdrant not reachable")
        )
        wrapper._client = mock_async_client

        result = await wrapper.is_healthy()

        assert result is False


# ---------------------------------------------------------------------------
# 6. Live integration tests (require running Qdrant)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestQdrantIntegration:
    """
    Integration tests that require a live Qdrant instance on localhost:6333.
    Run with: pytest -m integration services/algorag/tests/test_qdrant_client.py
    """

    @pytest.mark.asyncio
    async def test_live_connection(self):
        """Wrapper connects to a live Qdrant instance."""
        cfg = make_config(host="localhost", port=6333, retry_backoff=0.1)
        wrapper = QdrantClientWrapper(config=cfg)
        try:
            is_up = await wrapper.is_healthy()
            assert is_up is True
        finally:
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_live_ensure_and_count(self):
        """Creates collection idempotently and counts points on a live instance."""
        cfg = make_config(
            host="localhost",
            port=6333,
            collection="test_qdrant_client_integration",
            retry_backoff=0.1,
        )
        wrapper = QdrantClientWrapper(config=cfg)
        try:
            await wrapper.ensure_collection()
            count = await wrapper.count()
            assert isinstance(count, int)
            assert count >= 0
        finally:
            await wrapper.close()
