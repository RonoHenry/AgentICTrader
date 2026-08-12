"""
Integration tests for POST /rag/retrieve (Tasks 10.2, 10.3, 10.5).

Exercises the full retrieval pipeline through the FastAPI app with a mocked
Qdrant wrapper: real query-embedding generation, real metadata-filter
construction, real re-ranking, and real diversity filtering all run — only
the network call to Qdrant itself is mocked. This is the regression guard
for the retrieval path previously being wired to stub functions (constant
zero-vector embedding, no-op filter, no-op diversity filter).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from qdrant_client.http import models as qmodels


def _make_hit(trade_id: str, timestamp: str, score: float = 0.8):
    return MagicMock(
        score=score,
        payload={
            "trade_id": trade_id,
            "timestamp": timestamp,
            "instrument": "EURUSD",
            "time_window": "LONDON_KILLZONE",
            "htf_open_bias": "BULLISH",
            "confluence_count": 3,
            "outcome_result": "WIN",
            "outcome_r_multiple": 2.5,
            "narrative": "Price swept liquidity before reversing bullish.",
            "full_setup": {},
        },
    )


@pytest.fixture()
def mock_wrapper():
    wrapper = AsyncMock()
    wrapper.search = AsyncMock(return_value=[])
    return wrapper


@pytest.fixture()
def client(mock_wrapper):
    import services.algorag.main as svc_main

    with patch.object(svc_main, "_qdrant_client", mock_wrapper):
        with patch.object(svc_main, "get_qdrant", return_value=mock_wrapper):
            with TestClient(svc_main.app, raise_server_exceptions=True) as c:
                yield c


def _base_request(**overrides):
    payload = {
        "instrument": "EURUSD",
        "timestamp": "2024-05-06T09:15:00Z",
        "narrative": "Price swept the Asian low before reversing bullish through the FVG.",
        "confluence_factors": ["BOS", "FVG"],
        "top_k": 10,
    }
    payload.update(overrides)
    return payload


class TestQueryEmbeddingWiring:
    def test_search_called_with_non_zero_528_dim_vector(self, client, mock_wrapper):
        """Regression guard: the endpoint must not query with the old
        constant-zero-vector stub."""
        resp = client.post("/rag/retrieve", json=_base_request())
        assert resp.status_code == 200

        call_kwargs = mock_wrapper.search.call_args.kwargs
        query_vector = call_kwargs["query_vector"]
        assert len(query_vector) == 528
        assert any(v != 0.0 for v in query_vector)


class TestMetadataFilterWiring:
    def test_search_called_with_real_filter(self, client, mock_wrapper):
        resp = client.post("/rag/retrieve", json=_base_request(htf_open_bias="BULLISH"))
        assert resp.status_code == 200

        call_kwargs = mock_wrapper.search.call_args.kwargs
        qfilter = call_kwargs["query_filter"]
        assert isinstance(qfilter, qmodels.Filter)
        keys = {c.key for c in qfilter.must}
        assert "instrument" in keys
        assert "htf_open_bias" in keys
        # default outcome_filter is "WIN"
        assert "outcome_result" in keys

    def test_outcome_filter_none_omits_condition(self, client, mock_wrapper):
        client.post("/rag/retrieve", json=_base_request(outcome_filter=None))
        qfilter = mock_wrapper.search.call_args.kwargs["query_filter"]
        keys = {c.key for c in qfilter.must}
        assert "outcome_result" not in keys


class TestDiversityFilterWiring:
    def test_diversity_limits_same_day_results(self, client, mock_wrapper):
        same_day = "2024-05-06T09:15:00Z"
        mock_wrapper.search.return_value = [
            _make_hit(f"T{i}", same_day, score=0.9 - i * 0.05) for i in range(6)
        ]
        resp = client.post("/rag/retrieve", json=_base_request(top_k=10))
        assert resp.status_code == 200
        data = resp.json()
        # default diversity_max_per_day is 3
        assert len(data["similar_setups"]) == 3


class TestEndToEndResponseShape:
    def test_empty_results_returns_zeroed_metrics(self, client, mock_wrapper):
        mock_wrapper.search.return_value = []
        resp = client.post("/rag/retrieve", json=_base_request())
        assert resp.status_code == 200
        data = resp.json()
        assert data["similar_setups"] == []
        assert data["rag_metrics"]["sample_size"] == 0

    def test_results_are_reranked_and_metrics_computed(self, client, mock_wrapper):
        mock_wrapper.search.return_value = [
            _make_hit("T1", "2024-05-06T09:15:00Z", score=0.7),
            _make_hit("T2", "2024-01-01T09:15:00Z", score=0.95),
        ]
        resp = client.post("/rag/retrieve", json=_base_request())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["similar_setups"]) == 2
        assert data["rag_metrics"]["sample_size"] == 2
        assert data["rag_metrics"]["win_rate_similar"] == 1.0
