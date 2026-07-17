"""
TDD - Task 10.5: Integration tests for diversity filtering

Tests the end-to-end integration of diversity filtering within the 
full retrieval pipeline, including configuration and real API behavior.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from services.algorag.main import app
from services.algorag.models import RetrievalRequest


class TestDiversityFilteringIntegration:
    """Integration tests for diversity filtering with full retrieval pipeline."""

    @pytest.mark.asyncio
    async def test_diversity_filtering_applied_in_retrieval_endpoint(self):
        """RED: Test diversity filtering is applied in the full retrieval pipeline."""
        # Setup request
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime(2024, 3, 20, 10, 0, tzinfo=timezone.utc),
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            narrative="Test diversity filtering in full pipeline",
            top_k=10,
            outcome_filter="WIN"
        )

        # Mock 6 search results - 4 from same day, 2 from different days
        mock_hits = []
        
        # 4 setups from March 15 (should be limited to 3)
        same_day_timestamp = "2024-03-15T09:15:00Z"
        for i in range(4):
            hit = MagicMock()
            hit.score = 0.9 - (i * 0.05)  # Decreasing similarity
            hit.payload = {
                "trade_id": f"TRD-SAME-{i:03d}",
                "timestamp": same_day_timestamp,
                "instrument": "EURUSD",
                "time_window": "LONDON_KILLZONE", 
                "htf_open_bias": "BULLISH",
                "confluence_count": 3,
                "outcome_result": "WIN",
                "outcome_r_multiple": 2.0 + i * 0.2,
                "narrative": f"Same day setup {i}",
                "full_setup": {"entry_price": 1.0920 + i * 0.0001}
            }
            mock_hits.append(hit)
        
        # 2 setups from different days
        for i in range(2):
            hit = MagicMock()
            hit.score = 0.75 - (i * 0.05)  # Lower similarity than same-day ones
            hit.payload = {
                "trade_id": f"TRD-DIFF-{i:03d}",
                "timestamp": f"2024-03-{16+i}T09:15:00Z",  # March 16, 17
                "instrument": "EURUSD",
                "time_window": "LONDON_KILLZONE",
                "htf_open_bias": "BULLISH", 
                "confluence_count": 2,
                "outcome_result": "WIN",
                "outcome_r_multiple": 1.5 + i * 0.3,
                "narrative": f"Different day setup {i}",
                "full_setup": {"entry_price": 1.0900 + i * 0.0001}
            }
            mock_hits.append(hit)

        # Mock the dependencies
        with patch("services.algorag.main.get_qdrant") as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search = AsyncMock(return_value=mock_hits)
            mock_get_qdrant.return_value = mock_wrapper
            
            with patch("services.algorag.main.generate_query_embedding") as mock_embed:
                mock_embed.return_value = [0.1] * 528
                
                client = TestClient(app)
                
                # Execute the retrieval request
                response = client.post(
                    "/rag/retrieve",
                    json=request.model_dump(mode="json")
                )
                
                # Verify response
                assert response.status_code == 200
                data = response.json()
                
                similar_setups = data["similar_setups"]
                
                # Should have total of 5 setups:
                # - 3 from March 15 (diversity limit applied)
                # - 2 from March 16,17 (no limit, different days)
                assert len(similar_setups) == 5
                
                # Count setups per day to verify diversity limit
                day_counts = {}
                for setup in similar_setups:
                    day = setup["timestamp"][:10]  # Extract YYYY-MM-DD
                    day_counts[day] = day_counts.get(day, 0) + 1
                
                # Verify diversity constraints
                assert day_counts["2024-03-15"] <= 3  # Max 3 from same day
                assert day_counts["2024-03-16"] == 1   # Different days preserved
                assert day_counts["2024-03-17"] == 1

    def test_diversity_threshold_configurable_via_environment(self):
        """REFACTOR: Test that diversity threshold is configurable via environment variables."""
        # Test that the config system picks up DIVERSITY_MAX_PER_DAY env var
        
        with patch.dict(os.environ, {"DIVERSITY_MAX_PER_DAY": "2"}):
            # Re-import to get fresh config with new env var
            from services.algorag.config import Settings
            
            test_settings = Settings()
            assert test_settings.service.diversity_max_per_day == 2
            
        with patch.dict(os.environ, {"DIVERSITY_MAX_PER_DAY": "5"}):
            test_settings = Settings()
            assert test_settings.service.diversity_max_per_day == 5
            
        # Test default value when env var not set
        with patch.dict(os.environ, {}, clear=True):
            test_settings = Settings()
            assert test_settings.service.diversity_max_per_day == 3  # Default value

    def test_diversity_filtering_uses_configured_threshold(self):
        """REFACTOR: Test that diversity filtering uses the threshold from settings."""
        from services.algorag.diversity import apply_diversity_filter
        from services.algorag.config import settings
        
        # Create 5 setups from same day
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        setups = []
        for i in range(5):
            from services.algorag.models import SimilarSetup
            setups.append(
                SimilarSetup(
                    trade_id=f"TRD-{i:03d}",
                    timestamp=same_day.replace(hour=9 + i),
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.0,
                    narrative=f"Setup {i}",
                    similarity_score=0.9 - i * 0.1,
                    final_score=0.9 - i * 0.1,
                )
            )
        
        # Test that the diversity filter uses the configured threshold
        # (Default is 3, but we'll test with different values)
        filtered_default = apply_diversity_filter(setups, max_per_day=settings.service.diversity_max_per_day)
        assert len(filtered_default) == min(len(setups), settings.service.diversity_max_per_day)
        
        # Test with custom threshold = 2
        filtered_custom = apply_diversity_filter(setups, max_per_day=2)
        assert len(filtered_custom) == 2
        
        # Test with threshold = 1
        filtered_one = apply_diversity_filter(setups, max_per_day=1)
        assert len(filtered_one) == 1

    def test_diversity_filtering_preserves_reranking_order(self):
        """GREEN: Test that diversity filtering preserves the re-ranking order within constraints."""
        # This test verifies that diversity filtering doesn't accidentally change
        # the order established by re-ranking algorithm
        
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime(2024, 3, 20, tzinfo=timezone.utc), 
            narrative="Order preservation test"
        )

        # Mock 4 hits from same day with specific final_scores after re-ranking
        mock_hits = []
        expected_order = ["TRD-BEST", "TRD-SECOND", "TRD-THIRD", "TRD-WORST"]
        final_scores = [0.95, 0.87, 0.79, 0.62]
        
        for i, (trade_id, score) in enumerate(zip(expected_order, final_scores)):
            hit = MagicMock()
            hit.score = 0.8  # Same similarity score
            hit.payload = {
                "trade_id": trade_id,
                "timestamp": "2024-03-15T09:15:00Z",  # Same day
                "instrument": "EURUSD",
                "outcome_result": "WIN", 
                "outcome_r_multiple": 2.0 + (3 - i) * 0.5,  # Higher R for better trades
                "confluence_count": 3,
                "narrative": f"Setup {trade_id}",
            }
            mock_hits.append(hit)

        with patch("services.algorag.main.get_qdrant") as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search = AsyncMock(return_value=mock_hits)
            mock_get_qdrant.return_value = mock_wrapper
            
            with patch("services.algorag.main.generate_query_embedding") as mock_embed:
                mock_embed.return_value = [0.1] * 528
                
                client = TestClient(app)
                
                response = client.post(
                    "/rag/retrieve",
                    json=request.model_dump(mode="json")
                )
                
                assert response.status_code == 200
                data = response.json()
                
                similar_setups = data["similar_setups"]
                
                # Should have max 3 setups (default diversity limit)
                assert len(similar_setups) == 3
                
                # Should be in re-ranked order (best first) within diversity constraints
                # The re-ranking algorithm should boost higher R-multiples
                returned_ids = [s["trade_id"] for s in similar_setups]
                
                # All returned IDs should be from expected order list
                for returned_id in returned_ids:
                    assert returned_id in expected_order
                    
                # Should maintain relative order from re-ranking
                assert returned_ids[0] == "TRD-BEST"   # Highest R-multiple, should be first

    @pytest.mark.asyncio
    async def test_diversity_filtering_error_handling_fallback(self):
        """GREEN: Test that diversity filtering failures don't break retrieval."""
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime(2024, 3, 20, tzinfo=timezone.utc),
            narrative="Error handling test"
        )

        # Mock normal search results
        mock_hit = MagicMock()
        mock_hit.score = 0.8
        mock_hit.payload = {
            "trade_id": "TRD-001",
            "timestamp": "2024-03-15T09:15:00Z", 
            "instrument": "EURUSD",
            "outcome_result": "WIN",
            "outcome_r_multiple": 2.0,
            "narrative": "Test setup",
        }

        with patch("services.algorag.main.get_qdrant") as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search = AsyncMock(return_value=[mock_hit])
            mock_get_qdrant.return_value = mock_wrapper
            
            with patch("services.algorag.main.generate_query_embedding") as mock_embed:
                mock_embed.return_value = [0.1] * 528
                
                # Mock diversity filtering to raise exception
                with patch("services.algorag.main.apply_diversity_filter") as mock_diversity:
                    mock_diversity.side_effect = Exception("Diversity filter error")
                    
                    client = TestClient(app)
                    
                    response = client.post(
                        "/rag/retrieve", 
                        json=request.model_dump(mode="json")
                    )
                    
                    # Should still return 200 with fallback to re-ranked results
                    assert response.status_code == 200
                    data = response.json()
                    
                    # Should have the result (fallback to reranked)
                    assert len(data["similar_setups"]) == 1
                    assert data["similar_setups"][0]["trade_id"] == "TRD-001"