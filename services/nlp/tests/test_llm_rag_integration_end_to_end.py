"""
End-to-end integration test for RAG-enhanced LLM reasoning.

This test demonstrates the complete flow from setup to RAG-enhanced reasoning,
showing how the feature would work in production with actual services.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from services.nlp.llm_service import LLMService
from ml.algorag.client import AlgoRAGClient


@pytest.mark.asyncio
async def test_rag_enhanced_reasoning_end_to_end():
    """End-to-end test showing RAG-enhanced LLM reasoning workflow."""
    # Arrange - Create LLM service (no API key = template mode)
    llm_service = LLMService()
    
    # Mock RAG client with realistic response
    rag_client = AsyncMock(spec=AlgoRAGClient)
    rag_client.retrieve_with_fallback.return_value = {
        "similar_setups": [
            {
                "setup": {
                    "trade_id": "TRD-20240315-001",
                    "timestamp": "2024-03-15T09:15:00Z",
                    "narrative": "London killzone manipulation phase, HTF bullish bias, BOS detected",
                    "outcome_result": "WIN",
                    "outcome_r_multiple": 3.8
                },
                "similarity_score": 0.92,
                "final_score": 0.95
            },
            {
                "setup": {
                    "trade_id": "TRD-20240310-002", 
                    "timestamp": "2024-03-10T10:30:00Z",
                    "narrative": "Asian range sweep, bullish FVG at discount, expansion higher",
                    "outcome_result": "WIN",
                    "outcome_r_multiple": 2.1
                },
                "similarity_score": 0.87,
                "final_score": 0.89
            }
        ],
        "rag_metrics": {
            "avg_r_multiple_similar": 2.95,
            "win_rate_similar": 1.0,
            "sample_size": 2,
            "max_similarity_score": 0.92,
            "avg_confluence_count": 4.5
        },
        "query_time_ms": 45.2
    }
    
    # Current trading setup
    setup = {
        "instrument": "EURUSD",
        "direction": "BULLISH", 
        "htf_open_bias": "BULLISH",
        "htf_open": 1.0850,
        "htf_high": 1.0890,
        "htf_low": 1.0840,
        "time_window": "LONDON_KILLZONE",
        "narrative_phase": "MANIPULATION",
        "price_vs_daily_open": "BELOW",
        "price_vs_true_day_open": "BELOW", 
        "patterns": ["BOS_DETECTED", "FVG_PRESENT"],
        "confidence_score": 0.78,
        "entry_price": 1.0855,
        "sl_price": 1.0845, 
        "tp_price": 1.0875,
        "swing_high": 1.0888,
        "swing_low": 1.0842,
        "fvg_present": True,
    }
    
    # Act - Generate RAG-enhanced reasoning
    result = await llm_service.generate_trade_reasoning_with_rag(setup, rag_client)
    
    # Assert - Verify RAG integration
    rag_client.retrieve_with_fallback.assert_called_once()
    
    # Verify RAG request was properly formatted
    call_args = rag_client.retrieve_with_fallback.call_args[0][0]
    assert call_args["instrument"] == "EURUSD"
    assert call_args["htf_open_bias"] == "BULLISH"
    assert call_args["time_window"] == "LONDON_KILLZONE"
    assert "london killzone" in call_args["narrative"].lower()
    assert "bullish" in call_args["narrative"].lower()
    
    # Verify reasoning contains setup details and RAG context  
    assert len(result) > 50  # Substantial reasoning
    assert "BULLISH" in result  # Direction should be in reasoning
    
    # Verify historical context is included 
    assert "Historical precedent" in result
    assert "similar setups" in result
    assert "win rate" in result
    assert "average outcome" in result
    
    print(f"Generated reasoning:\n{result}")
    print(f"RAG request narrative: {call_args['narrative']}")


@pytest.mark.asyncio
async def test_graceful_degradation_when_rag_unavailable():
    """Test that reasoning works gracefully when RAG service is completely unavailable."""
    # Arrange
    llm_service = LLMService()
    
    # Mock RAG client that fails
    rag_client = AsyncMock(spec=AlgoRAGClient)
    rag_client.retrieve_with_fallback.side_effect = Exception("RAG service unavailable")
    
    setup = {
        "instrument": "GBPUSD",
        "direction": "BEARISH",
        "htf_open_bias": "BEARISH", 
        "time_window": "NY_AM_KILLZONE",
        "confidence_score": 0.72
    }
    
    # Act - Should not raise exception
    result = await llm_service.generate_trade_reasoning_with_rag(setup, rag_client)
    
    # Assert - Falls back to standard reasoning
    assert len(result) > 0
    assert "GBPUSD" in result or "bearish" in result.lower()
    
    print(f"Fallback reasoning:\n{result}")


if __name__ == "__main__":
    import asyncio
    
    async def main():
        await test_rag_enhanced_reasoning_end_to_end()
        await test_graceful_degradation_when_rag_unavailable()
        print("All end-to-end tests passed!")
    
    asyncio.run(main())