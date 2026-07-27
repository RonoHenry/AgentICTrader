"""
TDD – Task 12.1: AlgoRAG POST /rag/ingest endpoint tests.

RED phase: Write tests that describe the expected behavior of the ingestion endpoint.
GREEN phase: Implement the endpoint in services/algorag/main.py to satisfy all assertions.
REFACTOR phase: Add rate limiting and authentication.

Requirements: FR-RAG-7 (Real-Time Ingestion)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_qdrant_client():
    """Mock Qdrant client for endpoint tests."""
    client_mock = AsyncMock()
    client_mock.upsert = AsyncMock(return_value=None)
    client_mock.is_healthy = AsyncMock(return_value=True)
    client_mock.get_collections = AsyncMock(return_value=MagicMock())
    return client_mock


@pytest.fixture()
def app_client(mock_qdrant_client):
    """TestClient with mocked Qdrant injected."""
    import services.algorag.main as svc_main

    with patch.object(svc_main, "_qdrant_client", mock_qdrant_client):
        with patch.object(svc_main, "get_qdrant", return_value=mock_qdrant_client):
            with TestClient(svc_main.app, raise_server_exceptions=True) as c:
                yield c


def make_valid_ingestion_request():
    """Create a valid IngestionRequest payload for testing."""
    return {
        "setup": {
            "trade_id": "TRD-TEST-001",
            "timestamp": "2024-03-15T09:15:00Z",
            "instrument": "EURUSD",
            "direction": "LONG",
            "time_window": "LONDON_KILLZONE",
            "htf_open_bias": "BULLISH",
            "confluence_count": 4,
            "outcome_result": "WIN",
            "outcome_r_multiple": 3.2,
            "narrative": "Price swept Asian low and entered FVG at discount.",
        },
        "embedding": [0.023] * 528,  # 528-dim embedding
    }


# ---------------------------------------------------------------------------
# RED Phase Tests
# ---------------------------------------------------------------------------


class TestIngestionEndpointStructure:
    """Test that POST /rag/ingest exists and returns correct structure."""

    def test_ingest_endpoint_exists(self, app_client):
        """POST /rag/ingest endpoint must exist and respond."""
        payload = make_valid_ingestion_request()
        resp = app_client.post("/rag/ingest", json=payload)
        assert resp.status_code in [200, 201, 503], (
            "Endpoint must exist (not 404)"
        )

    def test_ingest_returns_201_created_on_success(self, app_client):
        """Successful ingestion must return HTTP 201 CREATED."""
        payload = make_valid_ingestion_request()
        resp = app_client.post("/rag/ingest", json=payload)
        assert resp.status_code == 201

    def test_ingest_response_has_status_field(self, app_client):
        """Response must contain a 'status' field."""
        payload = make_valid_ingestion_request()
        resp = app_client.post("/rag/ingest", json=payload)
        data = resp.json()
        assert "status" in data

    def test_ingest_response_status_is_success(self, app_client):
        """Status field must be 'success' for successful ingestion."""
        payload = make_valid_ingestion_request()
        resp = app_client.post("/rag/ingest", json=payload)
        data = resp.json()
        assert data["status"] == "success"

    def test_ingest_response_has_setup_id_field(self, app_client):
        """Response must contain a 'setup_id' (Qdrant point UUID)."""
        payload = make_valid_ingestion_request()
        resp = app_client.post("/rag/ingest", json=payload)
        data = resp.json()
        assert "setup_id" in data

    def test_ingest_response_setup_id_is_nonempty_string(self, app_client):
        """setup_id must be a non-empty string."""
        payload = make_valid_ingestion_request()
        resp = app_client.post("/rag/ingest", json=payload)
        data = resp.json()
        assert isinstance(data["setup_id"], str)
        assert len(data["setup_id"]) > 0

    def test_ingest_response_matches_ingestion_response_schema(self, app_client):
        """Response must match IngestionResponse schema exactly."""
        payload = make_valid_ingestion_request()
        resp = app_client.post("/rag/ingest", json=payload)
        data = resp.json()
        required_keys = {"status", "setup_id"}
        assert required_keys == set(data.keys())


class TestIngestionValidation:
    """Test request validation for the ingestion endpoint."""

    def test_missing_setup_field_returns_422(self, app_client):
        """Request without 'setup' field must return 422 Unprocessable Entity."""
        payload = {"embedding": [0.1] * 528}
        resp = app_client.post("/rag/ingest", json=payload)
        assert resp.status_code == 422

    def test_missing_embedding_field_returns_422(self, app_client):
        """Request without 'embedding' field must return 422."""
        payload = {"setup": {"trade_id": "TRD-001"}}
        resp = app_client.post("/rag/ingest", json=payload)
        assert resp.status_code == 422

    def test_wrong_embedding_dimension_returns_422(self, app_client):
        """Embedding with incorrect dimension must return 422."""
        payload = make_valid_ingestion_request()
        payload["embedding"] = [0.1] * 256  # Wrong dimension
        resp = app_client.post("/rag/ingest", json=payload)
        assert resp.status_code == 422

    def test_embedding_too_large_returns_422(self, app_client):
        """Embedding with more than 528 dimensions must return 422."""
        payload = make_valid_ingestion_request()
        payload["embedding"] = [0.1] * 1024
        resp = app_client.post("/rag/ingest", json=payload)
        assert resp.status_code == 422

    def test_empty_embedding_returns_422(self, app_client):
        """Empty embedding list must return 422."""
        payload = make_valid_ingestion_request()
        payload["embedding"] = []
        resp = app_client.post("/rag/ingest", json=payload)
        assert resp.status_code == 422

    def test_embedding_dimension_validation_error_message(self, app_client):
        """Validation error must mention 528-dimensional requirement."""
        payload = make_valid_ingestion_request()
        payload["embedding"] = [0.1] * 384
        resp = app_client.post("/rag/ingest", json=payload)
        assert resp.status_code == 422
        error_text = resp.text.lower()
        assert "528" in error_text


class TestIngestionBehavior:
    """Test the actual ingestion behavior and integration with Qdrant."""

    def test_ingest_stores_setup_in_qdrant(self, app_client, mock_qdrant_client):
        """Endpoint must call Qdrant upsert with the provided setup and embedding."""
        payload = make_valid_ingestion_request()
        
        resp = app_client.post("/rag/ingest", json=payload)
        
        assert resp.status_code == 201
        # Verify upsert was called
        mock_qdrant_client.upsert.assert_called_once()

    def test_ingest_generates_deterministic_point_id(self, app_client, mock_qdrant_client):
        """Same trade_id must always generate the same Qdrant point ID."""
        payload1 = make_valid_ingestion_request()
        payload2 = make_valid_ingestion_request()
        # Same trade_id
        assert payload1["setup"]["trade_id"] == payload2["setup"]["trade_id"]
        
        resp1 = app_client.post("/rag/ingest", json=payload1)
        resp2 = app_client.post("/rag/ingest", json=payload2)
        
        assert resp1.json()["setup_id"] == resp2.json()["setup_id"]

    def test_ingest_stores_all_required_payload_fields(self, app_client, mock_qdrant_client):
        """Stored point must contain all required payload fields."""
        payload = make_valid_ingestion_request()
        
        app_client.post("/rag/ingest", json=payload)
        
        # Get the point that was upserted
        call_args = mock_qdrant_client.upsert.call_args
        points = call_args.kwargs.get("points") or call_args.args[0]
        point = points[0]
        
        required_keys = {
            "trade_id", "timestamp", "instrument", "time_window",
            "htf_open_bias", "confluence_count", "outcome_result",
            "outcome_r_multiple", "narrative", "full_setup",
        }
        assert required_keys.issubset(point.payload.keys())

    def test_ingest_normalizes_instrument_to_uppercase(self, app_client, mock_qdrant_client):
        """Instrument must be stored in uppercase regardless of input."""
        payload = make_valid_ingestion_request()
        payload["setup"]["instrument"] = "eurusd"  # lowercase
        
        app_client.post("/rag/ingest", json=payload)
        
        call_args = mock_qdrant_client.upsert.call_args
        points = call_args.kwargs.get("points") or call_args.args[0]
        point = points[0]
        
        assert point.payload["instrument"] == "EURUSD"

    def test_ingest_stores_full_setup_in_payload(self, app_client, mock_qdrant_client):
        """The full_setup field must contain the complete setup dict."""
        payload = make_valid_ingestion_request()
        
        app_client.post("/rag/ingest", json=payload)
        
        call_args = mock_qdrant_client.upsert.call_args
        points = call_args.kwargs.get("points") or call_args.args[0]
        point = points[0]
        
        assert point.payload["full_setup"] == payload["setup"]

    def test_ingest_uses_528_dim_embedding_vector(self, app_client, mock_qdrant_client):
        """Point vector must be exactly 528-dimensional."""
        payload = make_valid_ingestion_request()
        
        app_client.post("/rag/ingest", json=payload)
        
        call_args = mock_qdrant_client.upsert.call_args
        points = call_args.kwargs.get("points") or call_args.args[0]
        point = points[0]
        
        assert len(point.vector) == 528


class TestIngestionErrorHandling:
    """Test error handling when Qdrant is unavailable or errors occur."""

    def test_qdrant_unavailable_returns_503(self, app_client, mock_qdrant_client):
        """When Qdrant is unavailable, endpoint must return 503 Service Unavailable."""
        mock_qdrant_client.upsert = AsyncMock(
            side_effect=Exception("Qdrant connection failed")
        )
        payload = make_valid_ingestion_request()
        
        resp = app_client.post("/rag/ingest", json=payload)
        
        assert resp.status_code == 503

    def test_qdrant_error_response_contains_detail(self, app_client, mock_qdrant_client):
        """Error response must contain a 'detail' field with error information."""
        mock_qdrant_client.upsert = AsyncMock(
            side_effect=Exception("Vector store unavailable")
        )
        payload = make_valid_ingestion_request()
        
        resp = app_client.post("/rag/ingest", json=payload)
        
        data = resp.json()
        assert "detail" in data

    def test_setup_without_trade_id_gets_uuid_assigned(self, app_client, mock_qdrant_client):
        """Setup without trade_id must still be ingested with auto-generated UUID."""
        payload = make_valid_ingestion_request()
        del payload["setup"]["trade_id"]
        
        resp = app_client.post("/rag/ingest", json=payload)
        
        assert resp.status_code == 201
        # Verify a setup_id was still generated
        assert len(resp.json()["setup_id"]) > 0


class TestIngestionUpsertSemantics:
    """Test that duplicate trade_ids are updated, not duplicated."""

    def test_same_trade_id_twice_performs_upsert(self, app_client, mock_qdrant_client):
        """Ingesting the same trade_id twice must perform upsert (update, not duplicate)."""
        payload1 = make_valid_ingestion_request()
        payload2 = make_valid_ingestion_request()
        # Same trade_id, different narrative
        payload2["setup"]["narrative"] = "Updated narrative text"
        
        resp1 = app_client.post("/rag/ingest", json=payload1)
        resp2 = app_client.post("/rag/ingest", json=payload2)
        
        # Both succeed
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        # Same setup_id (deterministic from trade_id)
        assert resp1.json()["setup_id"] == resp2.json()["setup_id"]

    def test_different_trade_ids_generate_different_point_ids(self, app_client, mock_qdrant_client):
        """Different trade_ids must generate different Qdrant point IDs."""
        payload1 = make_valid_ingestion_request()
        payload2 = make_valid_ingestion_request()
        payload2["setup"]["trade_id"] = "TRD-TEST-002"  # Different ID
        
        resp1 = app_client.post("/rag/ingest", json=payload1)
        resp2 = app_client.post("/rag/ingest", json=payload2)
        
        assert resp1.json()["setup_id"] != resp2.json()["setup_id"]
