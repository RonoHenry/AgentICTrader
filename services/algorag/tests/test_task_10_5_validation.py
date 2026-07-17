"""
Task 10.5 Validation: Diversity filtering implementation validation

This test validates that Task 10.5 requirements have been fully implemented:
- RED: Test limiting results to max 3 setups from same day  
- GREEN: Implement date-based deduplication in top-10 results
- REFACTOR: Add configurable diversity threshold
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from services.algorag.main import app
from services.algorag.models import RetrievalRequest
from services.algorag.diversity import apply_diversity_filter
from services.algorag.config import settings


class TestTask10_5Implementation:
    """Validates Task 10.5 has been fully implemented according to TDD requirements."""

    def test_red_requirement_limit_3_setups_same_day(self):
        """RED: Test limiting results to max 3 setups from same day."""
        # Create 6 setups from the same day (March 15, 2024)
        from services.algorag.models import SimilarSetup
        
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        setups = []
        for i in range(6):
            setups.append(
                SimilarSetup(
                    trade_id=f"TRD-SAME-{i:03d}",
                    timestamp=same_day.replace(hour=8 + i),  # Different hours, same day
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.0 + i * 0.2,
                    narrative=f"Same day setup {i}",
                    similarity_score=0.95 - i * 0.05,  # Decreasing similarity 
                    final_score=0.95 - i * 0.05,
                )
            )
        
        # Apply diversity filtering with default max_per_day=3
        filtered = apply_diversity_filter(setups, max_per_day=3)
        
        # Should limit to exactly 3 setups (top 3 by final_score)
        assert len(filtered) == 3
        assert filtered[0].trade_id == "TRD-SAME-000"  # Best score (0.95)
        assert filtered[1].trade_id == "TRD-SAME-001"  # Second best (0.90)  
        assert filtered[2].trade_id == "TRD-SAME-002"  # Third best (0.85)
        
        # Verify all are from the same calendar day
        dates = [s.timestamp.date() for s in filtered]
        assert all(d == same_day.date() for d in dates)

    def test_green_requirement_date_based_deduplication(self):
        """GREEN: Implement date-based deduplication in top-10 results."""
        from services.algorag.models import SimilarSetup
        
        # Create 10 setups: 5 from March 15, 3 from March 16, 2 from March 17
        setups = []
        
        # 5 setups from March 15 (should be reduced to 3)
        march_15 = datetime(2024, 3, 15, tzinfo=timezone.utc)
        for i in range(5):
            setups.append(
                SimilarSetup(
                    trade_id=f"MAR15-{i:03d}",
                    timestamp=march_15.replace(hour=9 + i),
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.5 + i * 0.1,
                    narrative=f"March 15 setup {i}",
                    similarity_score=0.90 - i * 0.02,  # High similarity 
                    final_score=0.90 - i * 0.02,
                )
            )
        
        # 3 setups from March 16 (all should be kept)
        march_16 = datetime(2024, 3, 16, tzinfo=timezone.utc)
        for i in range(3):
            setups.append(
                SimilarSetup(
                    trade_id=f"MAR16-{i:03d}",
                    timestamp=march_16.replace(hour=10 + i),
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE", 
                    htf_open_bias="BULLISH",
                    confluence_count=2,
                    outcome_result="WIN",
                    outcome_r_multiple=1.8 + i * 0.1,
                    narrative=f"March 16 setup {i}",
                    similarity_score=0.75 - i * 0.02,  # Lower similarity
                    final_score=0.75 - i * 0.02,
                )
            )
        
        # 2 setups from March 17 (all should be kept)  
        march_17 = datetime(2024, 3, 17, tzinfo=timezone.utc)
        for i in range(2):
            setups.append(
                SimilarSetup(
                    trade_id=f"MAR17-{i:03d}",
                    timestamp=march_17.replace(hour=11 + i),
                    instrument="EURUSD",
                    time_window="NY_KILLZONE",
                    htf_open_bias="BEARISH",
                    confluence_count=1,
                    outcome_result="WIN",
                    outcome_r_multiple=1.5 + i * 0.1,
                    narrative=f"March 17 setup {i}",
                    similarity_score=0.65 - i * 0.02,  # Lowest similarity
                    final_score=0.65 - i * 0.02,
                )
            )
        
        # Apply diversity filtering
        filtered = apply_diversity_filter(setups, max_per_day=3)
        
        # Should have exactly 8 setups: 3 from Mar 15, 3 from Mar 16, 2 from Mar 17
        assert len(filtered) == 8
        
        # Count setups per day to verify deduplication
        day_counts = {}
        for setup in filtered:
            day_key = setup.timestamp.date().isoformat()
            day_counts[day_key] = day_counts.get(day_key, 0) + 1
        
        assert day_counts["2024-03-15"] == 3  # Limited to 3
        assert day_counts["2024-03-16"] == 3  # All preserved (under limit)
        assert day_counts["2024-03-17"] == 2  # All preserved (under limit)
        
        # Verify the filtered March 15 setups are the top 3 by score
        mar_15_filtered = [s for s in filtered if s.timestamp.date() == march_15.date()]
        mar_15_ids = [s.trade_id for s in mar_15_filtered]
        assert "MAR15-000" in mar_15_ids  # Best score
        assert "MAR15-001" in mar_15_ids  # Second best
        assert "MAR15-002" in mar_15_ids  # Third best

    def test_refactor_requirement_configurable_threshold(self):
        """REFACTOR: Add configurable diversity threshold."""
        from services.algorag.models import SimilarSetup
        
        # Create 5 setups from same day
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        setups = []
        for i in range(5):
            setups.append(
                SimilarSetup(
                    trade_id=f"TRD-{i:03d}",
                    timestamp=same_day.replace(hour=9 + i),
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.0 + i * 0.1,
                    narrative=f"Setup {i}",
                    similarity_score=0.9 - i * 0.05,
                    final_score=0.9 - i * 0.05,
                )
            )
        
        # Test with different configurable thresholds
        
        # Threshold = 1: Only 1 setup per day
        filtered_1 = apply_diversity_filter(setups, max_per_day=1)
        assert len(filtered_1) == 1
        assert filtered_1[0].trade_id == "TRD-000"
        
        # Threshold = 2: Only 2 setups per day
        filtered_2 = apply_diversity_filter(setups, max_per_day=2)
        assert len(filtered_2) == 2
        assert filtered_2[0].trade_id == "TRD-000"
        assert filtered_2[1].trade_id == "TRD-001"
        
        # Threshold = 4: 4 setups per day
        filtered_4 = apply_diversity_filter(setups, max_per_day=4)
        assert len(filtered_4) == 4
        
        # Threshold = 10: All 5 setups (threshold > available)
        filtered_10 = apply_diversity_filter(setups, max_per_day=10)
        assert len(filtered_10) == 5
        
        # Verify configuration via settings
        assert hasattr(settings.service, 'diversity_max_per_day')
        assert isinstance(settings.service.diversity_max_per_day, int)
        assert settings.service.diversity_max_per_day >= 0

    @pytest.mark.asyncio
    async def test_end_to_end_integration_with_retrieval_endpoint(self):
        """Integration test: Diversity filtering works in full retrieval pipeline."""
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime(2024, 3, 20, 10, 0, tzinfo=timezone.utc),
            time_window="LONDON_KILLZONE", 
            htf_open_bias="BULLISH",
            narrative="End-to-end diversity filtering test",
            top_k=10,
            outcome_filter="WIN"
        )

        # Mock 8 search results: 5 from same day, 3 from different days
        mock_hits = []
        
        # 5 setups from March 15 (should be limited to 3)
        for i in range(5):
            hit = MagicMock()
            hit.score = 0.9 - (i * 0.02)  # High similarity scores
            hit.payload = {
                "trade_id": f"SAME-DAY-{i:03d}",
                "timestamp": "2024-03-15T09:15:00Z",  # Same day
                "instrument": "EURUSD",
                "time_window": "LONDON_KILLZONE",
                "htf_open_bias": "BULLISH",
                "confluence_count": 3,
                "outcome_result": "WIN",
                "outcome_r_multiple": 2.5 + i * 0.1,
                "narrative": f"Same day setup {i}",
                "full_setup": {"entry_price": 1.0920}
            }
            mock_hits.append(hit)
        
        # 3 setups from different days
        for i in range(3):
            hit = MagicMock()
            hit.score = 0.75 - (i * 0.02)  # Lower similarity
            hit.payload = {
                "trade_id": f"DIFF-DAY-{i:03d}",
                "timestamp": f"2024-03-{16+i}T09:15:00Z",  # March 16, 17, 18
                "instrument": "EURUSD",
                "time_window": "LONDON_KILLZONE",
                "htf_open_bias": "BULLISH", 
                "confluence_count": 2,
                "outcome_result": "WIN",
                "outcome_r_multiple": 1.8 + i * 0.1,
                "narrative": f"Different day setup {i}",
                "full_setup": {"entry_price": 1.0900}
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
                
                # Should have total of 6 setups:
                # - 3 from March 15 (diversity limit applied)
                # - 3 from March 16,17,18 (all preserved, different days)
                assert len(similar_setups) == 6
                
                # Count setups per day
                day_counts = {}
                for setup in similar_setups:
                    day = setup["timestamp"][:10]  # Extract YYYY-MM-DD
                    day_counts[day] = day_counts.get(day, 0) + 1
                
                # Verify diversity constraints
                assert day_counts["2024-03-15"] <= 3  # Max 3 from same day
                assert day_counts.get("2024-03-16", 0) <= 1  # Different days preserved
                assert day_counts.get("2024-03-17", 0) <= 1
                assert day_counts.get("2024-03-18", 0) <= 1
                
                # Verify RAG metrics computed correctly (from top-5 only)
                rag_metrics = data["rag_metrics"]
                assert rag_metrics["sample_size"] == 5  # RAG metrics computed from top-5
                assert 0.0 <= rag_metrics["win_rate_similar"] <= 1.0
                assert rag_metrics["avg_r_multiple_similar"] > 0.0

    def test_configuration_environment_variable_support(self):
        """REFACTOR: Test that diversity threshold can be configured via environment."""
        # Test default value
        from services.algorag.config import ServiceConfig
        
        # Test with different environment values
        test_cases = [
            ("1", 1),
            ("2", 2), 
            ("5", 5),
            ("10", 10)
        ]
        
        for env_value, expected_value in test_cases:
            with patch.dict(os.environ, {"DIVERSITY_MAX_PER_DAY": env_value}):
                config = ServiceConfig()
                assert config.diversity_max_per_day == expected_value
        
        # Test default when env var not set
        with patch.dict(os.environ, {}, clear=True):
            config = ServiceConfig()
            assert config.diversity_max_per_day == 3  # Default value