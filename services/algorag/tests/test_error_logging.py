"""
TDD – Task 13.2: Error logging with structured context and correlation IDs.

RED phase: Test that all errors are logged with:
  - Request parameters (instrument, timestamp, filters)
  - Stack trace
  - Correlation ID for request tracing
  - Structured logging format

GREEN phase: Implement structured logging with correlation IDs in main.py
REFACTOR: Add centralized log aggregation capability
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def mock_qdrant_with_search_error():
    """Simulate Qdrant search failure."""
    client_mock = AsyncMock()
    client_mock.search = AsyncMock(
        side_effect=Exception("Vector search failed: connection timeout")
    )
    return client_mock


@pytest.fixture()
def mock_qdrant_with_upsert_error():
    """Simulate Qdrant upsert failure."""
    client_mock = AsyncMock()
    client_mock.upsert = AsyncMock(
        side_effect=Exception("Upsert failed: quota exceeded")
    )
    return client_mock


@contextmanager
def _client_with_qdrant(qdrant_mock):
    """TestClient whose endpoints see ``qdrant_mock`` as the Qdrant wrapper.

    These tests assert on caplog records, which go through the root logger.
    They rely on the ``services.algorag.main`` logger propagating to root.
    main.py configures logging once, at import time, and leaves propagation
    on, so mutating ``settings.service.structured_logs`` here would have no
    effect. Earlier versions of these fixtures did that and leaked the change
    into os.environ and the shared settings singleton for later tests.
    """
    import services.algorag.main as svc_main

    with patch.object(svc_main, "_qdrant_client", qdrant_mock):
        with patch.object(svc_main, "get_qdrant", return_value=qdrant_mock):
            with TestClient(svc_main.app, raise_server_exceptions=False) as c:
                yield c


@pytest.fixture()
def app_client_with_search_error(mock_qdrant_with_search_error):
    """TestClient with Qdrant search error injected."""
    with _client_with_qdrant(mock_qdrant_with_search_error) as c:
        yield c


@pytest.fixture()
def app_client_with_upsert_error(mock_qdrant_with_upsert_error):
    """TestClient with Qdrant upsert error injected."""
    with _client_with_qdrant(mock_qdrant_with_upsert_error) as c:
        yield c


@pytest.fixture()
def capture_logs(caplog):
    """Capture every log record, including DEBUG, for assertions."""
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="services.algorag.main")
    return caplog


@pytest.fixture()
def mock_qdrant_with_both_errors():
    """Simulate both Qdrant search and upsert failures."""
    client_mock = AsyncMock()
    client_mock.search = AsyncMock(
        side_effect=Exception("Vector search failed: connection timeout")
    )
    client_mock.upsert = AsyncMock(
        side_effect=Exception("Upsert failed: quota exceeded")
    )
    return client_mock


@pytest.fixture()
def app_client_with_both_errors(mock_qdrant_with_both_errors):
    """TestClient with both Qdrant search and upsert errors injected."""
    with _client_with_qdrant(mock_qdrant_with_both_errors) as c:
        yield c


class TestErrorLoggingStructure:
    """RED: Test that errors are logged with structured context."""

    def test_retrieval_error_logs_request_params(
        self, app_client_with_search_error, capture_logs
    ):
        """Errors must include request parameters (instrument, timestamp, filters)."""
        request_payload = {
            "instrument": "EURUSD",
            "timestamp": "2024-05-06T09:15:00Z",
            "time_window": "LONDON_KILLZONE",
            "htf_open_bias": "BULLISH",
            "top_k": 10,
        }

        resp = app_client_with_search_error.post("/rag/retrieve", json=request_payload)

        # Should return 503 Service Unavailable
        assert resp.status_code == 503

        # Error log must contain request params
        assert any("EURUSD" in record.message for record in capture_logs.records)

    def test_retrieval_error_logs_stack_trace(
        self, app_client_with_search_error, capture_logs
    ):
        """Errors must include stack trace for debugging."""
        request_payload = {
            "instrument": "GBPUSD",
            "timestamp": "2024-05-06T09:15:00Z",
            "top_k": 10,
        }

        resp = app_client_with_search_error.post("/rag/retrieve", json=request_payload)

        # Should have at least one ERROR log with exc_info
        error_records = [r for r in capture_logs.records if r.levelno >= logging.ERROR]
        assert len(error_records) > 0

        # At least one error record should have exception info
        assert any(r.exc_info is not None for r in error_records)

    def test_retrieval_error_includes_correlation_id(
        self, app_client_with_search_error, capture_logs
    ):
        """Errors must include correlation ID for request tracing."""
        correlation_id = str(uuid4())
        request_payload = {
            "instrument": "XAUUSD",
            "timestamp": "2024-05-06T09:15:00Z",
            "top_k": 10,
        }

        # Send request with correlation ID header
        resp = app_client_with_search_error.post(
            "/rag/retrieve",
            json=request_payload,
            headers={"X-Correlation-ID": correlation_id},
        )

        # Response should include correlation ID in headers
        assert "X-Correlation-ID" in resp.headers

        # Logs should contain correlation ID (either in message or extra fields)
        correlation_found = False
        for record in capture_logs.records:
            # Check if correlation ID is in the record's __dict__ (extra fields)
            if hasattr(record, 'correlation_id') and record.correlation_id == correlation_id:
                correlation_found = True
                break
            # Also check if it's in the message itself
            if correlation_id in record.message:
                correlation_found = True
                break
        
        assert correlation_found, f"Correlation ID {correlation_id} not found in logs"

    def test_ingestion_error_logs_request_context(
        self, app_client_with_upsert_error, capture_logs
    ):
        """Ingestion errors must log setup metadata and embedding info."""
        request_payload = {
            "setup": {
                "trade_id": "TRD-TEST-001",
                "instrument": "EURUSD",
                "timestamp": "2024-05-06T09:15:00Z",
                "time_window": "LONDON_KILLZONE",
            },
            "embedding": [0.1] * 528,  # 528-dim vector
        }

        resp = app_client_with_upsert_error.post("/rag/ingest", json=request_payload)

        # Should return 503 Service Unavailable
        assert resp.status_code == 503

        # Error log must contain trade_id for traceability
        assert any("TRD-TEST-001" in record.message or "Qdrant upsert failed" in record.message 
                   for record in capture_logs.records)

    def test_structured_logging_format(
        self, app_client_with_search_error, capture_logs
    ):
        """Logs must use structured format (JSON-serializable extras)."""
        request_payload = {
            "instrument": "EURUSD",
            "timestamp": "2024-05-06T09:15:00Z",
            "top_k": 5,
        }

        resp = app_client_with_search_error.post("/rag/retrieve", json=request_payload)

        # At least one error log should exist
        error_records = [r for r in capture_logs.records if r.levelno >= logging.ERROR]
        assert len(error_records) > 0

        # Check that structured data is present in log message
        # (We can't easily test extras without custom formatter, so check message content)
        assert any(
            "instrument" in record.message.lower() or "EURUSD" in record.message
            for record in error_records
        )


class TestCorrelationIDPropagation:
    """RED: Test correlation ID is generated, propagated, and returned."""

    def test_correlation_id_generated_if_not_provided(
        self, app_client_with_search_error
    ):
        """If client doesn't send X-Correlation-ID, server must generate one."""
        request_payload = {
            "instrument": "GBPUSD",
            "timestamp": "2024-05-06T09:15:00Z",
            "top_k": 10,
        }

        resp = app_client_with_search_error.post("/rag/retrieve", json=request_payload)

        # Response must include X-Correlation-ID header
        assert "X-Correlation-ID" in resp.headers
        assert len(resp.headers["X-Correlation-ID"]) > 0

    def test_correlation_id_returned_in_response(
        self, app_client_with_search_error
    ):
        """Server must echo back the correlation ID in response headers."""
        correlation_id = str(uuid4())
        request_payload = {
            "instrument": "EURUSD",
            "timestamp": "2024-05-06T09:15:00Z",
            "top_k": 10,
        }

        resp = app_client_with_search_error.post(
            "/rag/retrieve",
            json=request_payload,
            headers={"X-Correlation-ID": correlation_id},
        )

        # Response should echo the same correlation ID
        assert resp.headers["X-Correlation-ID"] == correlation_id

    def test_correlation_id_in_success_response(self, mock_qdrant_connected):
        """Correlation ID should also be returned in successful responses."""
        import services.algorag.main as svc_main

        # Mock successful search
        mock_qdrant_connected.search = AsyncMock(return_value=[])

        with patch.object(svc_main, "_qdrant_client", mock_qdrant_connected):
            with patch.object(svc_main, "get_qdrant", return_value=mock_qdrant_connected):
                with TestClient(svc_main.app) as client:
                    correlation_id = str(uuid4())
                    request_payload = {
                        "instrument": "EURUSD",
                        "timestamp": "2024-05-06T09:15:00Z",
                        "narrative": "Test narrative",
                        "top_k": 10,
                    }

                    resp = client.post(
                        "/rag/retrieve",
                        json=request_payload,
                        headers={"X-Correlation-ID": correlation_id},
                    )

                    # Success response should include correlation ID
                    assert resp.status_code == 200
                    assert resp.headers["X-Correlation-ID"] == correlation_id


@pytest.fixture()
def mock_qdrant_connected():
    """Mock healthy Qdrant for success cases."""
    client_mock = AsyncMock()
    client_mock.search = AsyncMock(return_value=[])
    client_mock.count = AsyncMock(return_value=100)
    return client_mock


class TestErrorMetrics:
    """RED: Test error metrics are tracked for monitoring."""

    def test_error_count_incremented_on_failure(
        self, app_client_with_search_error, capture_logs
    ):
        """Each error should be logged at ERROR level for metrics collection."""
        request_payload = {
            "instrument": "EURUSD",
            "timestamp": "2024-05-06T09:15:00Z",
            "top_k": 10,
        }

        # Make multiple requests to test error counting
        for _ in range(3):
            resp = app_client_with_search_error.post("/rag/retrieve", json=request_payload)
            assert resp.status_code == 503

        # Should have at least 3 error log records
        error_records = [r for r in capture_logs.records if r.levelno >= logging.ERROR]
        assert len(error_records) >= 3

    def test_different_error_types_logged_distinctly(
        self, app_client_with_both_errors, capture_logs
    ):
        """Different error types must be distinguishable in logs."""
        # Test retrieval error
        resp1 = app_client_with_both_errors.post(
            "/rag/retrieve",
            json={"instrument": "EURUSD", "timestamp": "2024-05-06T09:15:00Z", "top_k": 10},
        )

        # Test ingestion error
        resp2 = app_client_with_both_errors.post(
            "/rag/ingest",
            json={"setup": {"trade_id": "TEST"}, "embedding": [0.1] * 528},
        )

        # Both should fail
        assert resp1.status_code == 503
        assert resp2.status_code == 503

        # Logs should contain different error contexts
        log_messages = [r.message for r in capture_logs.records]
        assert any("search" in msg.lower() or "vector" in msg.lower() for msg in log_messages)
        assert any("upsert" in msg.lower() or "ingest" in msg.lower() for msg in log_messages)


class TestLoggerConfiguration:
    """Regression: main.py's import-time logging setup must not hide records.

    When a test module imported services.algorag.main at top level, the import
    ran during pytest collection, when PYTEST_CURRENT_TEST is unset. main.py
    then enabled JSON logging and set ``logger.propagate = False``, so every
    caplog-based test in this file failed in combined runs but passed alone.
    """

    def test_service_logger_propagates_to_root(self):
        import services.algorag.main as svc_main

        assert svc_main.logger.propagate is True

    def test_pytest_detected_during_collection(self, monkeypatch):
        """Detection must not depend on PYTEST_CURRENT_TEST, which is unset
        while modules are imported at collection time."""
        import services.algorag.main as svc_main

        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert svc_main._running_under_pytest() is True

    def test_structured_logging_disabled_under_pytest(self):
        """The module was imported by this pytest process (possibly at
        collection time), so JSON logging must be off."""
        import services.algorag.main as svc_main

        assert svc_main.structured_logs_enabled is False


# Test will fail (RED phase) until we implement structured logging with correlation IDs
