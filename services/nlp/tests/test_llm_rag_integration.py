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
        """Create LLMService instance for testing."""
        return LLMService(anthropic_api_key="test-key-123")
    
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