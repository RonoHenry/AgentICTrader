"""
TDD – Task 1.4: AlgoRAG /health endpoint tests.

RED  phase: assert endpoint returns the correct structure and status codes.
GREEN phase: implementation in services/algorag/main.py satisfies all assertions.
REFACTOR: setup_count and version info are included in every response.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# We import the app after patching the Qdrant client so no real network call
# is made during tests.
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_qdrant_connected():
    """Simulate a healthy Qdrant connection with 42 setups indexed."""
    client_mock = AsyncMock()

    # get_collections() returns successfully (connection OK)
    client_mock.get_collections = AsyncMock(return_value=MagicMock())

    # get_collection() returns a mock with points_count
    collection_info = MagicMock()
    collection_info.points_count = 42
    client_mock.get_collection = AsyncMock(return_value=collection_info)

    return client_mock


@pytest.fixture()
def mock_qdrant_disconnected():
    """Simulate Qdrant being unreachable."""
    client_mock = AsyncMock()
    client_mock.get_collections = AsyncMock(
        side_effect=ConnectionError("Qdrant not reachable")
    )
    return client_mock


@pytest.fixture()
def app_client_connected(mock_qdrant_connected):
    """TestClient with a healthy Qdrant mock injected."""
    import services.algorag.main as svc_main

    with patch.object(svc_main, "_qdrant_client", mock_qdrant_connected):
        with patch.object(svc_main, "get_qdrant", return_value=mock_qdrant_connected):
            with TestClient(svc_main.app, raise_server_exceptions=True) as c:
                yield c


@pytest.fixture()
def app_client_disconnected(mock_qdrant_disconnected):
    """TestClient with a disconnected Qdrant mock injected."""
    import services.algorag.main as svc_main

    with patch.object(svc_main, "_qdrant_client", mock_qdrant_disconnected):
        with patch.object(svc_main, "get_qdrant", return_value=mock_qdrant_disconnected):
            with TestClient(svc_main.app, raise_server_exceptions=True) as c:
                yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """GET /health – structure and values."""

    def test_returns_200_when_qdrant_connected(self, app_client_connected):
        """Health endpoint must return HTTP 200 when Qdrant is reachable."""
        resp = app_client_connected.get("/health")
        assert resp.status_code == 200

    def test_status_healthy_when_connected(self, app_client_connected):
        resp = app_client_connected.get("/health")
        data = resp.json()
        assert data["status"] == "healthy"

    def test_vector_store_connected_label(self, app_client_connected):
        resp = app_client_connected.get("/health")
        data = resp.json()
        assert data["vector_store"] == "connected"

    def test_setup_count_is_integer(self, app_client_connected):
        """setup_count must be a non-negative integer (REFACTOR requirement)."""
        resp = app_client_connected.get("/health")
        data = resp.json()
        assert isinstance(data["setup_count"], int)
        assert data["setup_count"] >= 0

    def test_setup_count_reflects_qdrant_value(self, app_client_connected):
        """setup_count must match the value returned by Qdrant (42 in mock)."""
        resp = app_client_connected.get("/health")
        data = resp.json()
        assert data["setup_count"] == 42

    def test_version_string_present(self, app_client_connected):
        """version field must be present and non-empty (REFACTOR requirement)."""
        resp = app_client_connected.get("/health")
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_service_name_is_algorag(self, app_client_connected):
        resp = app_client_connected.get("/health")
        data = resp.json()
        assert data["service"] == "algorag"

    def test_response_schema_has_all_required_fields(self, app_client_connected):
        """All HealthResponse fields must be present in the JSON output."""
        required = {"status", "service", "version", "vector_store", "setup_count"}
        resp = app_client_connected.get("/health")
        assert required.issubset(resp.json().keys())

    # ------------------------------------------------------------------
    # Degraded / disconnected behaviour
    # ------------------------------------------------------------------

    def test_returns_200_when_qdrant_disconnected(self, app_client_disconnected):
        """Service must stay alive and return 200 even when Qdrant is down."""
        resp = app_client_disconnected.get("/health")
        assert resp.status_code == 200

    def test_status_degraded_when_disconnected(self, app_client_disconnected):
        resp = app_client_disconnected.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"

    def test_vector_store_disconnected_label(self, app_client_disconnected):
        resp = app_client_disconnected.get("/health")
        data = resp.json()
        assert data["vector_store"] == "disconnected"

    def test_setup_count_zero_when_disconnected(self, app_client_disconnected):
        resp = app_client_disconnected.get("/health")
        data = resp.json()
        assert data["setup_count"] == 0
