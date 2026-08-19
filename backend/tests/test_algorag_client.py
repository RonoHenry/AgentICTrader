"""
TDD: agent/algorag_client.py — thin synchronous HTTP client.

RED phase: never raises to the caller — connection/timeout failures degrade
to a neutral AlgoRAGResult (empty similar_setups, zero modifier), matching
agent/visual_model_client.py's degraded-mode contract.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from agent.algorag_client import AlgoRAGSyncClient, _MIN_SAMPLE_SIZE, _RAG_MODIFIER_CAP


def _rag_metrics(**overrides) -> dict:
    base = {
        "avg_r_multiple_similar": 3.5,
        "win_rate_similar": 1.0,
        "sample_size": 5,
        "max_similarity_score": 0.94,
        "avg_confluence_count": 4.0,
    }
    base.update(overrides)
    return base


def _similar_setup(**overrides) -> dict:
    base = {
        "trade_id": "TRD-001",
        "timestamp": "2024-03-15T09:15:00Z",
        "instrument": "EURUSD",
        "time_window": "LONDON_KILLZONE",
        "htf_open_bias": "BULLISH",
        "confluence_count": 4,
        "outcome_result": "WIN",
        "outcome_r_multiple": 4.2,
        "narrative": "Price swept Asian low at 03:15",
        "similarity_score": 0.94,
        "final_score": 0.97,
    }
    base.update(overrides)
    return base


class TestAlgoRAGSyncClientDegradesOnFailure:
    def test_connection_error_returns_degraded_result(self) -> None:
        import httpx

        client = AlgoRAGSyncClient(base_url="http://unreachable-host:9999")
        with patch(
            "httpx.Client.post",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            result = client.retrieve(instrument="EURUSD", timestamp=datetime.now(timezone.utc))

        assert result.degraded is True
        assert result.similar_setups == []
        assert result.rag_modifier == 0.0

    def test_never_raises_on_unexpected_exception(self) -> None:
        client = AlgoRAGSyncClient(base_url="http://fake-host:9999")
        with patch("httpx.Client.post", side_effect=RuntimeError("boom")):
            result = client.retrieve(instrument="EURUSD", timestamp=datetime.now(timezone.utc))

        assert result.degraded is True

    def test_malformed_response_degrades(self) -> None:
        client = AlgoRAGSyncClient(base_url="http://fake-host:9999")
        mock_response = MagicMock()
        mock_response.json.return_value = {"unexpected": "shape"}
        mock_response.raise_for_status.return_value = None
        with patch("httpx.Client.post", return_value=mock_response):
            result = client.retrieve(instrument="EURUSD", timestamp=datetime.now(timezone.utc))

        assert result.degraded is True


class TestAlgoRAGSyncClientParsesSuccess:
    def test_successful_response_is_parsed(self) -> None:
        client = AlgoRAGSyncClient(base_url="http://fake-host:9999")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "similar_setups": [_similar_setup()],
            "rag_metrics": _rag_metrics(),
            "query_time_ms": 45.2,
        }
        mock_response.raise_for_status.return_value = None
        with patch("httpx.Client.post", return_value=mock_response):
            result = client.retrieve(instrument="EURUSD", timestamp=datetime.now(timezone.utc))

        assert result.degraded is False
        assert len(result.similar_setups) == 1
        assert result.similar_setups[0].trade_id == "TRD-001"
        assert result.rag_metrics.sample_size == 5


class TestAlgoRAGModifierComputation:
    def test_full_win_rate_yields_positive_cap(self) -> None:
        client = AlgoRAGSyncClient(base_url="http://fake-host:9999")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "similar_setups": [_similar_setup()],
            "rag_metrics": _rag_metrics(win_rate_similar=1.0, sample_size=5),
            "query_time_ms": 10.0,
        }
        mock_response.raise_for_status.return_value = None
        with patch("httpx.Client.post", return_value=mock_response):
            result = client.retrieve(instrument="EURUSD", timestamp=datetime.now(timezone.utc))

        assert result.rag_modifier == _RAG_MODIFIER_CAP

    def test_zero_win_rate_yields_negative_cap(self) -> None:
        client = AlgoRAGSyncClient(base_url="http://fake-host:9999")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "similar_setups": [],
            "rag_metrics": _rag_metrics(win_rate_similar=0.0, sample_size=5),
            "query_time_ms": 10.0,
        }
        mock_response.raise_for_status.return_value = None
        with patch("httpx.Client.post", return_value=mock_response):
            result = client.retrieve(instrument="EURUSD", timestamp=datetime.now(timezone.utc))

        assert result.rag_modifier == -_RAG_MODIFIER_CAP

    def test_neutral_win_rate_yields_zero_modifier(self) -> None:
        client = AlgoRAGSyncClient(base_url="http://fake-host:9999")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "similar_setups": [],
            "rag_metrics": _rag_metrics(win_rate_similar=0.5, sample_size=5),
            "query_time_ms": 10.0,
        }
        mock_response.raise_for_status.return_value = None
        with patch("httpx.Client.post", return_value=mock_response):
            result = client.retrieve(instrument="EURUSD", timestamp=datetime.now(timezone.utc))

        assert result.rag_modifier == 0.0

    def test_below_minimum_sample_size_yields_zero_modifier(self) -> None:
        client = AlgoRAGSyncClient(base_url="http://fake-host:9999")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "similar_setups": [],
            "rag_metrics": _rag_metrics(win_rate_similar=1.0, sample_size=_MIN_SAMPLE_SIZE - 1),
            "query_time_ms": 10.0,
        }
        mock_response.raise_for_status.return_value = None
        with patch("httpx.Client.post", return_value=mock_response):
            result = client.retrieve(instrument="EURUSD", timestamp=datetime.now(timezone.utc))

        assert result.rag_modifier == 0.0
