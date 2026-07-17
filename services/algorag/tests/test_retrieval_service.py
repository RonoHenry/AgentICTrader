"""
Test retrieval service functionality including re-ranking algorithm.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from services.algorag.models import SimilarSetup


class TestReRankingAlgorithm:
    """Tests for the re-ranking algorithm (Task 10.4)."""

    def test_rerank_by_outcome_quality(self):
        """RED: Test re-ranking by outcome quality + recency + confluence overlap."""
        # Setup: 3 setups with different R-multiples and times
        now = datetime.now(timezone.utc)
        setups = [
            SimilarSetup(
                trade_id="TRD-001",
                timestamp=now - timedelta(days=30),  # 30 days ago
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=5,
                outcome_result="WIN",
                outcome_r_multiple=4.0,  # High R-multiple
                narrative="Strong setup",
                similarity_score=0.80,  # Lower similarity
                final_score=0.80,  # Will be updated by re-ranking
            ),
            SimilarSetup(
                trade_id="TRD-002",
                timestamp=now - timedelta(days=5),   # 5 days ago (more recent)
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.0,  # Lower R-multiple
                narrative="Medium setup",
                similarity_score=0.90,  # Higher similarity
                final_score=0.90,  # Will be updated by re-ranking
            ),
            SimilarSetup(
                trade_id="TRD-003",
                timestamp=now - timedelta(days=100), # 100 days ago (older)
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=7,
                outcome_result="WIN",
                outcome_r_multiple=3.0,  # Medium R-multiple
                narrative="High confluence setup",
                similarity_score=0.85,
                final_score=0.85,  # Will be updated by re-ranking
            )
        ]

        from services.algorag.reranking import rerank_setups

        # Execute re-ranking
        reranked = rerank_setups(setups, current_confluence_count=5)

        # Verify: setups are sorted by final_score descending
        assert len(reranked) == 3
        assert reranked[0].final_score >= reranked[1].final_score >= reranked[2].final_score

        # Verify: TRD-001 should score high due to high R-multiple (4.0)
        # even though it has lower similarity (0.80)
        trd_001 = next(s for s in reranked if s.trade_id == "TRD-001")
        trd_002 = next(s for s in reranked if s.trade_id == "TRD-002")

        # TRD-002 is more recent but has lower R-multiple (2.0 vs 4.0)
        # The high R-multiple should outweigh recency, so TRD-001 should score higher
        assert trd_001.final_score > trd_002.final_score
        # Both should have different scores than their original similarity scores
        assert trd_001.final_score != 0.80  # Re-ranking changed it
        assert trd_002.final_score != 0.90  # Re-ranking changed it

    def test_exponential_decay_90_day_half_life(self):
        """RED: Test exponential decay with 90-day half-life."""
        from services.algorag.reranking import compute_recency_score

        now = datetime.now(timezone.utc)

        # At 0 days: score should be 1.0
        score_0 = compute_recency_score(now, now)
        assert abs(score_0 - 1.0) < 0.01

        # At 90 days: score should be ~0.5 (half-life)
        score_90 = compute_recency_score(now - timedelta(days=90), now)
        assert abs(score_90 - 0.5) < 0.05  # Allow 5% tolerance

        # At 180 days: score should be ~0.25 (two half-lives)
        score_180 = compute_recency_score(now - timedelta(days=180), now)
        assert abs(score_180 - 0.25) < 0.05

        # At 270 days: score should be ~0.125 (three half-lives)
        score_270 = compute_recency_score(now - timedelta(days=270), now)
        assert abs(score_270 - 0.125) < 0.05

    def test_configurable_weights(self):
        """RED: Test weights are configurable (outcome: 0.5, recency: 0.3, confluence: 0.2)."""
        from services.algorag.reranking import ReRankingConfig, compute_final_score

        # Default weights
        config = ReRankingConfig()
        assert config.outcome_weight == 0.5
        assert config.recency_weight == 0.3
        assert config.confluence_weight == 0.2

        # Test with older setup where recency is low, so outcome weight matters more
        now = datetime.now(timezone.utc)
        old_setup_time = now - timedelta(days=180)  # 180 days ago (low recency score)

        # Config with higher outcome weight
        outcome_heavy_config = ReRankingConfig(
            outcome_weight=0.8,
            recency_weight=0.1,
            confluence_weight=0.1,
        )

        # Test with high R-multiple where outcome should dominate
        score_default = compute_final_score(
            outcome_r_multiple=8.0,  # Very high R-multiple
            setup_timestamp=old_setup_time,
            current_timestamp=now,
            setup_confluence_count=5,
            current_confluence_count=5,
            config=config,
        )

        score_outcome_heavy = compute_final_score(
            outcome_r_multiple=8.0,  # Very high R-multiple
            setup_timestamp=old_setup_time,
            current_timestamp=now,
            setup_confluence_count=5,
            current_confluence_count=5,
            config=outcome_heavy_config,
        )

        # With higher outcome weight and high R-multiple, score should be higher
        # despite lower recency weight (since recency is already low for old setup)
        assert score_outcome_heavy > score_default

    def test_confluence_overlap_scoring(self):
        """RED: Test confluence overlap component in scoring."""
        from services.algorag.reranking import compute_confluence_score

        # Perfect overlap (same confluence count)
        overlap_score = compute_confluence_score(5, 5)
        assert overlap_score == 1.0

        # Partial overlap (setup has more confluence factors)
        overlap_score = compute_confluence_score(7, 5)
        expected = 5 / 7  # min(current, setup) / max(current, setup)
        assert abs(overlap_score - expected) < 0.01

        # Partial overlap (setup has fewer confluence factors)
        overlap_score = compute_confluence_score(3, 5)
        expected = 3 / 5
        assert abs(overlap_score - expected) < 0.01

        # No overlap (one has zero confluence)
        overlap_score = compute_confluence_score(0, 5)
        assert overlap_score == 0.0

        overlap_score = compute_confluence_score(3, 0)
        assert overlap_score == 0.0

    def test_diversity_filtering_max_3_per_day(self):
        """RED: Test limiting results to max 3 setups from same day."""
        # Setup: 5 setups from the same day
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        setups = []
        for i in range(5):
            setups.append(
                SimilarSetup(
                    trade_id=f"TRD-{i:03d}",
                    timestamp=same_day.replace(hour=9 + i),  # Different hours, same day
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.0 + i * 0.5,  # Different R-multiples
                    narrative=f"Setup {i}",
                    similarity_score=0.9 - i * 0.1,  # Decreasing similarity
                    final_score=0.9 - i * 0.1,
                )
            )

        from services.algorag.diversity import apply_diversity_filter

        # Execute diversity filtering
        filtered = apply_diversity_filter(setups, max_per_day=3)

        # Verify: only 3 setups returned (top 3 by final_score)
        assert len(filtered) == 3
        assert filtered[0].trade_id == "TRD-000"  # Highest score (0.9)
        assert filtered[1].trade_id == "TRD-001"  # Second highest (0.8)
        assert filtered[2].trade_id == "TRD-002"  # Third highest (0.7)

    def test_diversity_filtering_different_days(self):
        """Test diversity filtering preserves setups from different days."""
        base_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        setups = []
        for i in range(5):
            setups.append(
                SimilarSetup(
                    trade_id=f"TRD-{i:03d}",
                    timestamp=base_day + timedelta(days=i),  # Different days
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.0,
                    narrative=f"Setup {i}",
                    similarity_score=0.8,
                    final_score=0.8,
                )
            )

        from services.algorag.diversity import apply_diversity_filter

        # Execute diversity filtering
        filtered = apply_diversity_filter(setups, max_per_day=3)

        # Verify: all 5 setups preserved (all from different days)
        assert len(filtered) == 5

    def test_diversity_filtering_configurable_threshold(self):
        """REFACTOR: Test configurable diversity threshold parameter."""
        # Setup: 5 setups from the same day
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        setups = []
        for i in range(5):
            setups.append(
                SimilarSetup(
                    trade_id=f"TRD-{i:03d}",
                    timestamp=same_day.replace(hour=9 + i),  # Different hours, same day
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.0 + i * 0.5,  # Different R-multiples
                    narrative=f"Setup {i}",
                    similarity_score=0.9 - i * 0.1,  # Decreasing similarity
                    final_score=0.9 - i * 0.1,
                )
            )

        from services.algorag.diversity import apply_diversity_filter

        # Test with different thresholds
        # Threshold = 1: Only 1 setup per day
        filtered_1 = apply_diversity_filter(setups, max_per_day=1)
        assert len(filtered_1) == 1
        assert filtered_1[0].trade_id == "TRD-000"  # Highest score

        # Threshold = 2: Only 2 setups per day  
        filtered_2 = apply_diversity_filter(setups, max_per_day=2)
        assert len(filtered_2) == 2
        assert filtered_2[0].trade_id == "TRD-000"
        assert filtered_2[1].trade_id == "TRD-001"

        # Threshold = 5: All 5 setups (threshold >= total)
        filtered_5 = apply_diversity_filter(setups, max_per_day=5)
        assert len(filtered_5) == 5

        # Threshold = 0: No setups (edge case)
        filtered_0 = apply_diversity_filter(setups, max_per_day=0)
        assert len(filtered_0) == 0