"""
Tests for RAG-enhanced LLM reasoning functionality.

Tests the generate_trade_reasoning_with_rag() function which integrates
historical examples from AlgoRAG into LLM trade reasoning.

Following TDD methodology:
- RED: Test generate_trade_reasoning_with_rag() calls RAG client and includes examples
- GREEN: Implement the function
- REFACTOR: Add fallback behavior
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from services.nlp.llm_service import LLMService
from ml.algorag.client import AlgoRAGClient


class TestLLMRAGIntegration:
    """Test suite for RAG-enhanced LLM reasoning."""
    
    @pytest.fixture
    def llm_service(self):
        """Create LLMService instance for testing.

        The anthropic SDK is optional: when it is installed,
        ``LLMService(anthropic_api_key="test-key-123")`` builds a *live* client
        and any test that doesn't override ``_client`` would send a real
        request to the Anthropic API. Swap in a test double that fails every
        call ("Claude unreachable") so no test can reach the network; tests
        that need a Claude response override ``_client`` themselves.
        """
        service = LLMService(anthropic_api_key="test-key-123")
        service._client = MagicMock()
        service._client.messages.create.side_effect = ConnectionError(
            "Claude unreachable (test double)"
        )
        return service
    
    @pytest.fixture
    def mock_rag_client(self):
        """Create mock AlgoRAG client."""
        client = AsyncMock(spec=AlgoRAGClient)
        return client
    
    @pytest.fixture
    def sample_setup(self):
        """Sample trading setup for testing."""
        return {
            "instrument": "EURUSD",
            "direction": "BULLISH",
            "htf_open_bias": "BULLISH",
            "htf_open": 1.0850,
            "htf_high": 1.0890,
            "htf_low": 1.0840,
            "time_window": "LONDON_KILLZONE",
            "narrative_phase": "MANIPULATION",
            "price_vs_daily_open": "BELOW",
            "patterns": ["BOS_DETECTED", "FVG_PRESENT"],
            "confidence_score": 0.82,
            "entry_price": 1.0855,
            "sl_price": 1.0845,
            "tp_price": 1.0875,
        }
    
    @pytest.fixture
    def sample_rag_response(self):
        """Sample RAG response with similar setups."""
        return {
            "similar_setups": [
                {
                    "setup": {
                        "trade_id": "TRD-001",
                        "timestamp": "2024-03-15T09:15:00Z",
                        "narrative": "Price swept Asian low at 03:15, respected bullish OB at discount",
                        "outcome_result": "WIN",
                        "outcome_r_multiple": 4.2
                    },
                    "similarity_score": 0.94,
                    "final_score": 0.97
                },
                {
                    "setup": {
                        "trade_id": "TRD-002", 
                        "timestamp": "2024-03-10T10:30:00Z",
                        "narrative": "London killzone BOS, FVG fill at premium rejection",
                        "outcome_result": "WIN",
                        "outcome_r_multiple": 2.8
                    },
                    "similarity_score": 0.89,
                    "final_score": 0.91
                }
            ],
            "rag_metrics": {
                "avg_r_multiple_similar": 3.5,
                "win_rate_similar": 1.0,
                "sample_size": 2,
                "max_similarity_score": 0.94
            },
            "query_time_ms": 45.2
        }

    # RED: Test that function calls RAG client and includes examples
    @pytest.mark.asyncio
    async def test_generate_trade_reasoning_with_rag_calls_client_and_includes_examples(
        self, llm_service, mock_rag_client, sample_setup, sample_rag_response
    ):
        """Test that generate_trade_reasoning_with_rag calls RAG client and formats examples in prompt."""
        # Arrange
        mock_rag_client.retrieve_with_fallback.return_value = sample_rag_response
        
        # Mock Claude response
        mock_message = MagicMock()
        mock_message.content = [MagicMock()]
        mock_message.content[0].text = "Test reasoning with historical examples"
        llm_service._client = MagicMock()
        llm_service._client.messages.create.return_value = mock_message
        
        # Act
        result = await llm_service.generate_trade_reasoning_with_rag(sample_setup, mock_rag_client)
        
        # Assert
        # Verify RAG client was called
        mock_rag_client.retrieve_with_fallback.assert_called_once()
        call_args = mock_rag_client.retrieve_with_fallback.call_args[0][0]
        assert call_args["instrument"] == "EURUSD"
        assert call_args["htf_open_bias"] == "BULLISH"
        
        # Verify Claude was called with prompt including similar setups
        llm_service._client.messages.create.assert_called_once()
        prompt = llm_service._client.messages.create.call_args[1]["messages"][0]["content"]
        
        # Check that similar setups are included in the prompt
        assert "SIMILAR HISTORICAL SETUPS" in prompt
        assert "TRD-001" in prompt
        assert "Price swept Asian low at 03:15" in prompt
        assert "4.2R" in prompt
        assert "94% similarity" in prompt
        
        assert result == "Test reasoning with historical examples"

    @pytest.mark.asyncio 
    async def test_generate_trade_reasoning_with_rag_fallback_when_rag_fails(
        self, llm_service, mock_rag_client, sample_setup
    ):
        """Test that function falls back to template reasoning when RAG fails."""
        # Arrange - RAG client returns empty response (failure case)
        mock_rag_client.retrieve_with_fallback.return_value = {
            "similar_setups": [],
            "rag_metrics": {
                "avg_r_multiple_similar": 0.0,
                "win_rate_similar": 0.0,
                "sample_size": 0,
                "max_similarity_score": 0.0
            },
            "query_time_ms": 0.0
        }
        
        # Act
        result = await llm_service.generate_trade_reasoning_with_rag(sample_setup, mock_rag_client)
        
        # Assert
        # Should fallback to template-based reasoning
        assert len(result) > 0
        assert "EURUSD" in result or "bullish" in result.lower()
        
        # RAG client should still be called (graceful degradation)
        mock_rag_client.retrieve_with_fallback.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_trade_reasoning_with_rag_without_claude(
        self, mock_rag_client, sample_setup, sample_rag_response
    ):
        """Test RAG integration works even without Claude API key."""
        # Arrange - LLM service without Claude
        llm_service_no_claude = LLMService(anthropic_api_key="")
        mock_rag_client.retrieve_with_fallback.return_value = sample_rag_response
        
        # Act
        result = await llm_service_no_claude.generate_trade_reasoning_with_rag(sample_setup, mock_rag_client)
        
        # Assert
        # Should still call RAG and include historical context in template
        mock_rag_client.retrieve_with_fallback.assert_called_once()
        assert len(result) > 0
        
        # Template should include historical context
        assert "similar setups" in result.lower() or "historical" in result.lower()

    @pytest.mark.asyncio
    async def test_rag_request_format(self, llm_service, mock_rag_client, sample_setup):
        """Test that RAG request is properly formatted."""
        # Arrange
        mock_rag_client.retrieve_with_fallback.return_value = {
            "similar_setups": [],
            "rag_metrics": {"sample_size": 0},
            "query_time_ms": 0.0
        }
        
        # Act
        await llm_service.generate_trade_reasoning_with_rag(sample_setup, mock_rag_client)
        
        # Assert
        call_args = mock_rag_client.retrieve_with_fallback.call_args[0][0]
        
        # Check required fields for RAG retrieval
        assert "instrument" in call_args
        assert "timestamp" in call_args  # Should be added by function
        assert "time_window" in call_args
        assert "htf_open_bias" in call_args
        assert "narrative" in call_args  # Should be generated


# ---------------------------------------------------------------------------
# Regression: the real AlgoRAG response shape
# ---------------------------------------------------------------------------
#
# POST /rag/retrieve (services/algorag/models.py::RetrievalResponse) returns
# each similar setup FLAT -- trade_id, narrative, outcome_result,
# outcome_r_multiple and similarity_score are top-level keys. The formatters
# used to read only a nested {"setup": {...}} shape, so with real AlgoRAG data
# the Claude prompt degraded to '- ? (): "" -- ?, N/A, 94% similarity': no
# trade id, narrative or outcome to cite (FR-RAG-6). These payloads are built
# from the service's own pydantic models and serialised exactly as the HTTP
# response is, so they track the wire contract rather than a hand-written dict.

_SAMPLE_SETUP = {
    "instrument": "EURUSD",
    "direction": "BULLISH",
    "htf_open_bias": "BULLISH",
    "time_window": "LONDON_KILLZONE",
    "narrative_phase": "MANIPULATION",
    "confidence_score": 0.82,
}


def _algorag_wire_response(setups, rag_metrics):
    """Serialise a RetrievalResponse the way the AlgoRAG HTTP endpoint does."""
    from datetime import datetime, timezone

    from services.algorag.models import RAGMetrics, RetrievalResponse, SimilarSetup

    base = {
        "timestamp": datetime(2024, 3, 15, 9, 15, tzinfo=timezone.utc),
        "instrument": "EURUSD",
        "time_window": "LONDON_KILLZONE",
        "htf_open_bias": "BULLISH",
        "confluence_count": 5,
        "final_score": 0.9,
    }
    return RetrievalResponse(
        similar_setups=[SimilarSetup(**{**base, **s}) for s in setups],
        rag_metrics=RAGMetrics(**rag_metrics),
        query_time_ms=12.5,
    ).model_dump(mode="json")


def _claude_double(text="Claude reasoning"):
    client = MagicMock()
    message = MagicMock()
    message.content = [MagicMock()]
    message.content[0].text = text
    client.messages.create.return_value = message
    return client


class TestRealAlgoRAGResponseShape:

    @pytest.mark.asyncio
    async def test_claude_prompt_cites_flat_algorag_setups(self):
        response = _algorag_wire_response(
            [{
                "trade_id": "TRD-001",
                "outcome_result": "WIN",
                "outcome_r_multiple": 4.2,
                "narrative": "Price swept Asian low before bullish continuation",
                "similarity_score": 0.94,
            }],
            {"avg_r_multiple_similar": 4.2, "win_rate_similar": 1.0, "sample_size": 1,
             "max_similarity_score": 0.94, "avg_confluence_count": 5.0},
        )
        assert "setup" not in response["similar_setups"][0]  # flat wire shape
        rag_client = AsyncMock(spec=AlgoRAGClient)
        rag_client.retrieve_with_fallback.return_value = response
        service = LLMService(anthropic_api_key="")
        service._client = _claude_double()

        result = await service.generate_trade_reasoning_with_rag(_SAMPLE_SETUP, rag_client)

        assert result == "Claude reasoning"
        prompt = service._client.messages.create.call_args[1]["messages"][0]["content"]
        ts = response["similar_setups"][0]["timestamp"]
        expected_line = (
            f'- TRD-001 ({ts}): "Price swept Asian low before bullish continuation"'
            " — WIN, 4.2R, 94% similarity"
        )
        assert expected_line in prompt.splitlines()

    @pytest.mark.asyncio
    async def test_template_precedent_uses_algorag_metrics(self):
        """Without Claude, the precedent sentence carries AlgoRAG's own
        aggregate (the numbers the Confluence Scorer sees), not a recount."""
        response = _algorag_wire_response(
            [
                {"trade_id": "TRD-001", "outcome_result": "WIN", "outcome_r_multiple": 4.2,
                 "narrative": "a", "similarity_score": 0.94},
                {"trade_id": "TRD-002", "outcome_result": "LOSS", "outcome_r_multiple": -1.0,
                 "narrative": "b", "similarity_score": 0.88},
            ],
            {"avg_r_multiple_similar": 3.5, "win_rate_similar": 0.8, "sample_size": 5,
             "max_similarity_score": 0.94, "avg_confluence_count": 5.0},
        )
        rag_client = AsyncMock(spec=AlgoRAGClient)
        rag_client.retrieve_with_fallback.return_value = response
        service = LLMService(anthropic_api_key="")

        result = await service.generate_trade_reasoning_with_rag(_SAMPLE_SETUP, rag_client)

        expected_note = "Historical precedent: 5 similar setups with 80% win rate and 3.5R average outcome."
        assert result == f"{service._reason_template(_SAMPLE_SETUP)} {expected_note}"


class TestFormatSimilarSetupsForTemplate:

    def test_derives_aggregate_from_flat_setups_when_metrics_absent(self):
        from services.nlp.prompts.rag_reasoning import format_similar_setups_for_template

        setups = [
            {"trade_id": "A", "outcome_result": "WIN", "outcome_r_multiple": 4.2},
            {"trade_id": "B", "outcome_result": "LOSS", "outcome_r_multiple": -1.0},
        ]
        # win rate 1/2 = 50%; average R (4.2 + -1.0) / 2 = 1.6
        assert format_similar_setups_for_template(setups) == (
            "Historical precedent: 2 similar setups with 50% win rate and 1.6R average outcome."
        )

    def test_missing_r_multiple_is_not_averaged_as_zero(self):
        from services.nlp.prompts.rag_reasoning import format_similar_setups_for_template

        setups = [
            {"setup": {"outcome_result": "WIN", "outcome_r_multiple": 3.0}},
            {"setup": {"outcome_result": "LOSS"}},  # R unknown
        ]
        # average over the one known R-multiple is 3.0R, not (3.0 + 0) / 2
        assert format_similar_setups_for_template(setups) == (
            "Historical precedent: 2 similar setups with 50% win rate and 3.0R average outcome."
        )

    def test_empty_setups_give_empty_string(self):
        from services.nlp.prompts.rag_reasoning import format_similar_setups_for_template

        assert format_similar_setups_for_template([], {"sample_size": 5}) == ""


class TestRAGRetrievalFailure:

    @pytest.mark.asyncio
    async def test_raising_rag_client_degrades_to_standard_claude_reasoning(self):
        rag_client = AsyncMock(spec=AlgoRAGClient)
        rag_client.retrieve_with_fallback.side_effect = RuntimeError("AlgoRAG down")
        service = LLMService(anthropic_api_key="")
        service._client = _claude_double("plain reasoning")

        result = await service.generate_trade_reasoning_with_rag(_SAMPLE_SETUP, rag_client)

        assert result == "plain reasoning"
        prompt = service._client.messages.create.call_args[1]["messages"][0]["content"]
        # The standard (ungrounded) prompt, not the RAG-grounded one.
        assert "SIMILAR HISTORICAL SETUPS" not in prompt
        assert "grounded in the similar historical setups" not in prompt

    @pytest.mark.asyncio
    async def test_non_dict_rag_response_degrades_to_standard_template(self):
        rag_client = AsyncMock(spec=AlgoRAGClient)
        rag_client.retrieve_with_fallback.return_value = None
        service = LLMService(anthropic_api_key="")

        result = await service.generate_trade_reasoning_with_rag(_SAMPLE_SETUP, rag_client)

        assert result == service._reason_template(_SAMPLE_SETUP)