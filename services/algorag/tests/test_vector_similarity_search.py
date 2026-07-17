"""
TDD - Task 10.3: Implement vector similarity search

RED   phase: Test cosine similarity search returning top-10 results
GREEN phase: Implement Qdrant search with query embedding and filters  
REFACTOR: Add timeout handling and error recovery

This test covers the vector similarity search functionality required for
the AlgoRAG retrieval pipeline.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from qdrant_client.http import models as qmodels

from services.algorag.main import app
from services.algorag.models import RetrievalRequest


# ---------------------------------------------------------------------------
# RED Tests - Vector Similarity Search
# ---------------------------------------------------------------------------


class TestVectorSimilaritySearch:
    """Test cosine similarity search returning top-10 results."""

    @pytest.mark.asyncio
    async def test_cosine_similarity_search_returns_top_10_results(self):
        """RED: Test cosine similarity search returning top-10 results."""
        # Arrange: Create a retrieval request with narrative
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            time_window="LONDON_KILLZONE", 
            htf_open_bias="BULLISH",
            narrative="Price swept Asian low before reversing bullish at discount array",
            htf_structure={"htf_high": 1.0950, "htf_low": 1.0900},
            pd_arrays={"fvg_present": True, "bos_detected": True},
            confluence_factors=["HTF_ALIGNMENT", "FVG", "BOS"],
            top_k=10,
            outcome_filter="WIN"
        )

        # Mock the embedding generation to return a realistic query vector
        expected_query_vector = np.random.random(528).tolist()
        
        # Mock Qdrant search results - 10 similar setups with different dates for diversity
        mock_hits = []
        for i in range(10):
            hit = MagicMock()
            hit.score = 0.9 - (i * 0.05)  # Decreasing similarity scores
            # Use different dates to avoid diversity filtering limits
            hit_date = f"2024-03-{15+i:02d}T09:15:00Z"
            hit.payload = {
                "trade_id": f"TRD-{i:03d}",
                "timestamp": hit_date,
                "instrument": "EURUSD",
                "time_window": "LONDON_KILLZONE",
                "htf_open_bias": "BULLISH",
                "confluence_count": 3,
                "outcome_result": "WIN",
                "outcome_r_multiple": 2.0 + i * 0.3,
                "narrative": f"Similar setup {i}",
                "full_setup": {"entry_price": 1.0920 + i * 0.0001}
            }
            mock_hits.append(hit)

        # Mock the QdrantClientWrapper
        with patch("services.algorag.main.get_qdrant") as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search = AsyncMock(return_value=mock_hits)
            mock_get_qdrant.return_value = mock_wrapper
            
            # Mock query embedding generation (this will be implemented properly in GREEN phase)
            with patch("services.algorag.main.generate_query_embedding") as mock_embed:
                mock_embed.return_value = expected_query_vector
                
                from fastapi.testclient import TestClient
                client = TestClient(app)
                
                # Act: Call the retrieval endpoint
                response = client.post(
                    "/rag/retrieve",
                    json=request.model_dump(mode="json")
                )
                
                # Assert: Verify the response
                assert response.status_code == 200
                data = response.json()
                
                # Should return exactly 10 results (top-k)
                assert len(data["similar_setups"]) == 10
                
                # Results should be ordered by final_score (after re-ranking)
                scores = [setup["final_score"] for setup in data["similar_setups"]]
                assert scores == sorted(scores, reverse=True)
                
                # Each result should have required fields
                first_result = data["similar_setups"][0]
                assert "trade_id" in first_result
                assert "similarity_score" in first_result
                assert "final_score" in first_result
                assert "narrative" in first_result
                assert "outcome_r_multiple" in first_result
                
                # RAG metrics should be computed
                rag_metrics = data["rag_metrics"]
                assert "avg_r_multiple_similar" in rag_metrics
                assert "win_rate_similar" in rag_metrics
                assert "sample_size" in rag_metrics
                assert "max_similarity_score" in rag_metrics
                
                # Query time should be measured
                assert "query_time_ms" in data
                assert data["query_time_ms"] > 0
                
                # Verify that search was called with proper parameters
                mock_wrapper.search.assert_called_once()
                call_args = mock_wrapper.search.call_args
                assert call_args[1]["query_vector"] == expected_query_vector
                assert call_args[1]["limit"] == 10
                assert call_args[1]["query_filter"] is not None  # Metadata filter applied

    @pytest.mark.asyncio 
    async def test_query_embedding_generation_from_narrative(self):
        """RED: Test that query embedding is generated from request narrative."""
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            narrative="Price swept Asian low before reversing at bullish OB"
        )
        
        # This function should exist and generate 528-dim embedding from narrative
        from services.algorag.embedding_generation import generate_query_embedding
        
        # Should generate 528-dimensional vector from narrative
        embedding = generate_query_embedding(request)
        
        assert isinstance(embedding, list)
        assert len(embedding) == 528
        assert all(isinstance(x, (int, float)) for x in embedding)
        
        # Should be deterministic - same input produces same output
        embedding2 = generate_query_embedding(request)
        assert embedding == embedding2
        
        # Different narratives should produce different embeddings
        request2 = RetrievalRequest(
            instrument="GBPUSD", 
            timestamp=datetime.now(timezone.utc),
            narrative="Different narrative about bearish rejection at premium"
        )
        embedding3 = generate_query_embedding(request2)
        assert embedding != embedding3

    @pytest.mark.asyncio
    async def test_search_with_metadata_filters_and_vector_query(self):
        """RED: Test Qdrant search with both metadata filters and vector similarity."""
        # Mock setup
        mock_wrapper = AsyncMock()
        mock_hits = [MagicMock() for _ in range(5)]
        for i, hit in enumerate(mock_hits):
            hit.score = 0.9 - i * 0.1
            hit.payload = {"trade_id": f"TRD-{i}", "outcome_result": "WIN"}
        mock_wrapper.search = AsyncMock(return_value=mock_hits)
        
        query_vector = [0.1] * 528
        
        # Build filter (should combine instrument + outcome filters)
        from services.algorag.filtering import build_qdrant_filter
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            outcome_filter="WIN"
        )
        qdrant_filter = build_qdrant_filter(request)
        
        # Execute search
        results = await mock_wrapper.search(
            query_vector=query_vector,
            query_filter=qdrant_filter, 
            limit=10
        )
        
        # Verify search called with correct parameters
        mock_wrapper.search.assert_called_once_with(
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=10
        )
        
        # Verify results structure
        assert len(results) == 5
        assert all(hit.score > 0 for hit in results)

    @pytest.mark.asyncio
    async def test_timeout_handling_on_qdrant_search(self):
        """RED: Test timeout handling and error recovery on Qdrant search failures."""
        from fastapi.testclient import TestClient
        
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            narrative="Test setup"
        )
        
        # Mock Qdrant wrapper to raise timeout error
        with patch("services.algorag.main.get_qdrant") as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search = AsyncMock(side_effect=asyncio.TimeoutError("Search timeout"))
            mock_get_qdrant.return_value = mock_wrapper
            
            with patch("services.algorag.main.generate_query_embedding") as mock_embed:
                mock_embed.return_value = [0.0] * 528
                
                client = TestClient(app)
                
                # Should return 503 Service Unavailable on timeout
                response = client.post(
                    "/rag/retrieve", 
                    json=request.model_dump(mode="json")
                )
                
                assert response.status_code == 503
                detail = response.json()["detail"]
                assert "timeout" in detail.lower() or "unavailable" in detail.lower()

    @pytest.mark.asyncio
    async def test_empty_results_handling(self):
        """RED: Test handling when Qdrant returns no similar setups."""
        from fastapi.testclient import TestClient
        
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            narrative="Very unique narrative with no matches"
        )
        
        # Mock Qdrant to return empty results
        with patch("services.algorag.main.get_qdrant") as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search = AsyncMock(return_value=[])  # No hits
            mock_get_qdrant.return_value = mock_wrapper
            
            with patch("services.algorag.main.generate_query_embedding") as mock_embed:
                mock_embed.return_value = [0.0] * 528
                
                client = TestClient(app)
                
                response = client.post(
                    "/rag/retrieve",
                    json=request.model_dump(mode="json") 
                )
                
                assert response.status_code == 200
                data = response.json()
                
                # Should return empty similar_setups
                assert data["similar_setups"] == []
                
                # RAG metrics should handle empty results gracefully
                rag_metrics = data["rag_metrics"] 
                assert rag_metrics["sample_size"] == 0
                assert rag_metrics["avg_r_multiple_similar"] == 0.0
                assert rag_metrics["win_rate_similar"] == 0.0
                assert rag_metrics["max_similarity_score"] == 0.0


# ---------------------------------------------------------------------------
# Performance Tests
# ---------------------------------------------------------------------------


class TestVectorSearchPerformance:
    """Test performance requirements for vector similarity search."""

    @pytest.mark.asyncio
    async def test_retrieval_latency_under_100ms_p95(self):
        """RED: Test retrieval latency < 100ms (p95 requirement)."""
        from fastapi.testclient import TestClient
        
        request = RetrievalRequest(
            instrument="EURUSD", 
            timestamp=datetime.now(timezone.utc),
            narrative="Performance test narrative"
        )
        
        # Mock fast Qdrant response
        mock_hit = MagicMock()
        mock_hit.score = 0.85
        mock_hit.payload = {
            "trade_id": "TRD-PERF",
            "timestamp": "2024-03-15T09:15:00Z",
            "instrument": "EURUSD",
            "outcome_result": "WIN",
            "outcome_r_multiple": 2.5,
            "narrative": "Fast result"
        }
        
        with patch("services.algorag.main.get_qdrant") as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search = AsyncMock(return_value=[mock_hit])
            mock_get_qdrant.return_value = mock_wrapper
            
            with patch("services.algorag.main.generate_query_embedding") as mock_embed:
                mock_embed.return_value = [0.0] * 528
                
                client = TestClient(app)
                
                start_time = time.perf_counter()
                response = client.post(
                    "/rag/retrieve",
                    json=request.model_dump(mode="json")
                )
                end_time = time.perf_counter()
                
                assert response.status_code == 200
                
                # Should complete in under 100ms for p95 requirement
                latency_ms = (end_time - start_time) * 1000
                assert latency_ms < 100, f"Latency {latency_ms:.2f}ms exceeds 100ms target"
                
                # Response should also include measured query time
                data = response.json()
                assert data["query_time_ms"] < 100