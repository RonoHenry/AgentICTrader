"""
Comprehensive unit tests for retrieval logic (Task 10.6).

Tests metadata filtering with various combinations, re-ranking algorithm with mock data,
and diversity filtering edge cases per FR-RAG-2, FR-RAG-3, NFR-RAG-4 requirements.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.http import models as qmodels

from services.algorag.models import (
    RetrievalRequest,
    SimilarSetup,
    RAGMetrics,
)
from services.algorag.reranking import ReRankingConfig


class TestMetadataFilteringCombinations:
    """
    **Validates: Requirements FR-RAG-2**
    
    Comprehensive tests for metadata filtering with various parameter combinations
    to ensure all filtering scenarios work correctly.
    """

    def test_filter_instrument_only(self):
        """RED: Test filtering with only required instrument parameter."""
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
        )

        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)

        # Should have instrument + default outcome_filter conditions
        assert len(qdrant_filter.must) == 2
        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "EURUSD"
        assert conditions["outcome_result"] == "WIN"

    def test_filter_instrument_plus_time_window(self):
        """RED: Test filtering with instrument + time_window combination."""
        request = RetrievalRequest(
            instrument="GBPUSD",
            timestamp=datetime.now(timezone.utc),
            time_window="LONDON_KILLZONE",
        )

        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)

        assert len(qdrant_filter.must) == 3
        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "GBPUSD"
        assert conditions["time_window"] == "LONDON_KILLZONE"
        assert conditions["outcome_result"] == "WIN"
    def test_filter_instrument_plus_htf_bias(self):
        """RED: Test filtering with instrument + HTF bias combination."""
        request = RetrievalRequest(
            instrument="XAUUSD",
            timestamp=datetime.now(timezone.utc),
            htf_open_bias="BEARISH",
        )

        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)

        assert len(qdrant_filter.must) == 3
        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "XAUUSD"
        assert conditions["htf_open_bias"] == "BEARISH"
        assert conditions["outcome_result"] == "WIN"

    def test_filter_all_parameters_combination(self):
        """RED: Test filtering with all possible parameter combinations."""
        request = RetrievalRequest(
            instrument="USDJPY",
            timestamp=datetime.now(timezone.utc),
            time_window="NY_KILLZONE",
            htf_open_bias="BULLISH",
            outcome_filter="WIN",
        )

        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)

        assert len(qdrant_filter.must) == 4
        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "USDJPY"
        assert conditions["time_window"] == "NY_KILLZONE"
        assert conditions["htf_open_bias"] == "BULLISH"
        assert conditions["outcome_result"] == "WIN"

    def test_filter_loss_outcomes_only(self):
        """RED: Test filtering to retrieve only LOSS outcomes."""
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            outcome_filter="LOSS",  # Filter for losing trades
        )

        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)

        assert len(qdrant_filter.must) == 2
        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "EURUSD"
        assert conditions["outcome_result"] == "LOSS"

    def test_filter_no_outcome_restriction(self):
        """RED: Test filtering without outcome restriction (all outcomes)."""
        request = RetrievalRequest(
            instrument="GBPUSD",
            timestamp=datetime.now(timezone.utc),
            outcome_filter=None,  # No outcome filtering
        )

        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)

        # Only instrument condition, no outcome_result condition
        assert len(qdrant_filter.must) == 1
        condition = qdrant_filter.must[0]
        assert condition.key == "instrument"
        assert condition.match.value == "GBPUSD"
    def test_filter_empty_strings_ignored(self):
        """RED: Test that empty strings are properly ignored in filtering."""
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            time_window="  ",  # Whitespace only
            htf_open_bias="",  # Empty string
            outcome_filter="  ",  # Whitespace only
        )

        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)

        # Only instrument should be filtered (empty/whitespace strings ignored)
        assert len(qdrant_filter.must) == 1
        condition = qdrant_filter.must[0]
        assert condition.key == "instrument"
        assert condition.match.value == "EURUSD"

    def test_filter_case_sensitivity_preservation(self):
        """RED: Test that case sensitivity is preserved for filter values."""
        request = RetrievalRequest(
            instrument="eurusd",  # Will be uppercased by validator
            timestamp=datetime.now(timezone.utc),
            time_window="London_Killzone",  # Mixed case preserved
            htf_open_bias="Bullish",  # Mixed case preserved
            outcome_filter="Win",  # Mixed case preserved
        )

        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)

        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "EURUSD"  # Uppercased by validator
        assert conditions["time_window"] == "London_Killzone"  # Case preserved
        assert conditions["htf_open_bias"] == "Bullish"  # Case preserved
        assert conditions["outcome_result"] == "Win"  # Case preserved

    def test_filter_special_characters_handling(self):
        """RED: Test filtering with special characters in values."""
        request = RetrievalRequest(
            instrument="US500",  # Number in instrument
            timestamp=datetime.now(timezone.utc),
            time_window="NY_AM_KILLZONE",  # Underscores
            htf_open_bias="NEUTRAL",  # Different from BULLISH/BEARISH
        )

        from services.algorag.filtering import build_qdrant_filter
        qdrant_filter = build_qdrant_filter(request)

        assert len(qdrant_filter.must) == 3
        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "US500"
        assert conditions["time_window"] == "NY_AM_KILLZONE"
        assert conditions["htf_open_bias"] == "NEUTRAL"


class TestReRankingAlgorithmMockData:
    """
    **Validates: Requirements FR-RAG-3**
    
    Comprehensive tests for re-ranking algorithm using mock data to verify
    outcome quality + recency + confluence overlap scoring works correctly.
    """

    def test_reranking_outcome_quality_dominance(self):
        """RED: Test outcome quality component dominates when configured with high weight."""
        now = datetime.now(timezone.utc)
        
        # Setup with different R-multiples but similar other factors
        setups = [
            SimilarSetup(
                trade_id="LOW_R",
                timestamp=now - timedelta(days=30),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=1.5,  # Low R-multiple
                narrative="Low R setup",
                similarity_score=0.9,
                final_score=0.9,
            ),
            SimilarSetup(
                trade_id="HIGH_R",
                timestamp=now - timedelta(days=35),  # Slightly older
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=8.0,  # High R-multiple
                narrative="High R setup",
                similarity_score=0.8,  # Lower similarity
                final_score=0.8,
            ),
        ]

        # Config with outcome weight dominating
        outcome_heavy_config = ReRankingConfig(
            outcome_weight=0.9,  # Very high outcome weight
            recency_weight=0.05,
            confluence_weight=0.05,
        )

        from services.algorag.reranking import rerank_setups
        reranked = rerank_setups(
            setups=setups,
            current_confluence_count=3,
            current_timestamp=now,
            config=outcome_heavy_config,
        )

        # HIGH_R should rank first despite being older and having lower similarity
        assert reranked[0].trade_id == "HIGH_R"
        assert reranked[1].trade_id == "LOW_R"
        assert reranked[0].final_score > reranked[1].final_score

    def test_reranking_recency_component_verification(self):
        """RED: Test recency component calculation with known timestamps."""
        now = datetime.now(timezone.utc)

        setups = [
            SimilarSetup(
                trade_id="OLD_SETUP",
                timestamp=now - timedelta(days=180),  # 180 days ago (2 half-lives)
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.0,  # Same R-multiple
                narrative="Old setup",
                similarity_score=0.8,
                final_score=0.8,
            ),
            SimilarSetup(
                trade_id="RECENT_SETUP", 
                timestamp=now - timedelta(days=7),   # 1 week ago (recent)
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.0,  # Same R-multiple
                narrative="Recent setup",
                similarity_score=0.8,  # Same similarity
                final_score=0.8,
            ),
        ]

        # Config with recency weight dominating
        recency_heavy_config = ReRankingConfig(
            outcome_weight=0.1,
            recency_weight=0.8,  # High recency weight
            confluence_weight=0.1,
        )

        from services.algorag.reranking import rerank_setups
        reranked = rerank_setups(
            setups=setups,
            current_confluence_count=3,
            current_timestamp=now,
            config=recency_heavy_config,
        )

        # RECENT_SETUP should rank first due to higher recency score
        assert reranked[0].trade_id == "RECENT_SETUP"
        assert reranked[1].trade_id == "OLD_SETUP"
        assert reranked[0].final_score > reranked[1].final_score
    def test_confluence_overlap_scoring_edge_cases(self):
        """RED: Test confluence overlap calculation with edge cases."""
        from services.algorag.reranking import compute_confluence_score

        # Perfect match
        assert compute_confluence_score(5, 5) == 1.0

        # Setup has more confluence than current
        score = compute_confluence_score(8, 5)
        assert abs(score - (5 / 8)) < 0.01

        # Setup has less confluence than current
        score = compute_confluence_score(3, 7)
        assert abs(score - (3 / 7)) < 0.01

        # Both have zero confluence (perfect match)
        assert compute_confluence_score(0, 0) == 1.0

        # One has zero, other has confluence (no overlap)
        assert compute_confluence_score(0, 5) == 0.0
        assert compute_confluence_score(7, 0) == 0.0

    def test_reranking_with_mixed_loss_win_outcomes(self):
        """RED: Test re-ranking handles mixed WIN/LOSS outcomes correctly."""
        now = datetime.now(timezone.utc)

        setups = [
            SimilarSetup(
                trade_id="LOSS_SETUP",
                timestamp=now - timedelta(days=10),
                instrument="EURUSD", 
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=5,
                outcome_result="LOSS",
                outcome_r_multiple=-2.0,  # Negative R-multiple for loss
                narrative="Loss setup",
                similarity_score=0.9,
                final_score=0.9,
            ),
            SimilarSetup(
                trade_id="WIN_SETUP",
                timestamp=now - timedelta(days=30),  # Older but profitable
                instrument="EURUSD",
                time_window="LONDON_KILLZONE", 
                htf_open_bias="BULLISH",
                confluence_count=5,
                outcome_result="WIN",
                outcome_r_multiple=3.0,  # Positive R-multiple
                narrative="Win setup",
                similarity_score=0.8,  # Lower similarity
                final_score=0.8,
            ),
        ]

        from services.algorag.reranking import rerank_setups
        reranked = rerank_setups(setups, current_confluence_count=5)

        # WIN setup should rank higher despite being older and less similar
        # because outcome quality (positive R-multiple) outweighs other factors
        assert reranked[0].trade_id == "WIN_SETUP"
        assert reranked[1].trade_id == "LOSS_SETUP"

    def test_reranking_boundary_r_multiple_values(self):
        """RED: Test re-ranking with boundary R-multiple values."""
        now = datetime.now(timezone.utc)
        
        setups = [
            SimilarSetup(
                trade_id="ZERO_R",
                timestamp=now - timedelta(days=5),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="BREAKEVEN",
                outcome_r_multiple=0.0,  # Breakeven
                narrative="Breakeven setup",
                similarity_score=0.9,
                final_score=0.9,
            ),
            SimilarSetup(
                trade_id="MAX_R",
                timestamp=now - timedelta(days=10),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH", 
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=15.0,  # Above max_r_multiple (10.0)
                narrative="Extreme win setup",
                similarity_score=0.7,
                final_score=0.7,
            ),
            SimilarSetup(
                trade_id="NORMAL_R",
                timestamp=now - timedelta(days=8),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN", 
                outcome_r_multiple=5.0,  # Within normal range
                narrative="Normal win setup",
                similarity_score=0.8,
                final_score=0.8,
            ),
        ]

        from services.algorag.reranking import rerank_setups
        reranked = rerank_setups(setups, current_confluence_count=3)

        # MAX_R should rank highest (clamped to max_r_multiple=10.0 but still best outcome)
        # NORMAL_R should be second
        # ZERO_R should be last (zero outcome quality)
        assert reranked[0].trade_id == "MAX_R"
        assert reranked[1].trade_id == "NORMAL_R" 
        assert reranked[2].trade_id == "ZERO_R"

    def test_reranking_with_custom_config_parameters(self):
        """RED: Test re-ranking with custom configuration parameters."""
        now = datetime.now(timezone.utc)

        setup = SimilarSetup(
            trade_id="TEST_SETUP",
            timestamp=now - timedelta(days=45),  # 45 days ago
            instrument="EURUSD",
            time_window="LONDON_KILLZONE", 
            htf_open_bias="BULLISH",
            confluence_count=4,
            outcome_result="WIN",
            outcome_r_multiple=6.0,
            narrative="Test setup",
            similarity_score=0.8,
            final_score=0.8,
        )

        # Test with different half-life settings
        short_half_life_config = ReRankingConfig(
            recency_half_life_days=30.0,  # Shorter half-life
            max_r_multiple=8.0,  # Lower max R-multiple
        )

        long_half_life_config = ReRankingConfig(
            recency_half_life_days=180.0,  # Longer half-life  
            max_r_multiple=12.0,  # Higher max R-multiple
        )

        from services.algorag.reranking import rerank_setups

        short_result = rerank_setups(
            setups=[setup],
            current_confluence_count=4,
            current_timestamp=now,
            config=short_half_life_config,
        )

        long_result = rerank_setups(
            setups=[setup],
            current_confluence_count=4,
            current_timestamp=now,
            config=long_half_life_config,
        )

        # With longer half-life, recency score should be higher for 45-day old setup
        # With higher max_r_multiple, outcome score should be lower for 6.0 R-multiple
        assert short_result[0].final_score != long_result[0].final_score
class TestDiversityFilteringAdvanced:
    """
    **Validates: Requirements NFR-RAG-4**
    
    Advanced edge cases for diversity filtering to ensure robust behavior
    with complex timestamp patterns and edge scenarios.
    """

    def test_diversity_with_leap_year_dates(self):
        """RED: Test diversity filtering handles leap year dates correctly."""
        # February 29, 2024 (leap year) multiple setups
        leap_day = datetime(2024, 2, 29, tzinfo=timezone.utc)
        
        setups = []
        for i in range(4):
            setups.append(
                SimilarSetup(
                    trade_id=f"LEAP_{i}",
                    timestamp=leap_day.replace(hour=6 + i * 4),
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.0 + i * 0.5,
                    narrative=f"Leap year setup {i}",
                    similarity_score=0.9 - i * 0.1,
                    final_score=0.9 - i * 0.1,
                )
            )

        from services.algorag.diversity import apply_diversity_filter
        filtered = apply_diversity_filter(setups, max_per_day=2)

        # Should limit to 2 setups from leap day
        assert len(filtered) == 2
        assert filtered[0].trade_id == "LEAP_0"
        assert filtered[1].trade_id == "LEAP_1"

    def test_diversity_with_dst_transition_dates(self):
        """RED: Test diversity filtering around DST transition dates."""
        # March 10, 2024 (DST begins in US) - test UTC timestamps
        dst_date = datetime(2024, 3, 10, tzinfo=timezone.utc)
        
        setups = [
            SimilarSetup(
                trade_id="PRE_DST",
                timestamp=dst_date.replace(hour=6),  # Before typical DST transition
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.5,
                narrative="Pre-DST setup",
                similarity_score=0.9,
                final_score=0.9,
            ),
            SimilarSetup(
                trade_id="POST_DST",
                timestamp=dst_date.replace(hour=14),  # After typical DST transition
                instrument="EURUSD", 
                time_window="NY_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=2,
                outcome_result="WIN",
                outcome_r_multiple=1.8,
                narrative="Post-DST setup",
                similarity_score=0.8,
                final_score=0.8,
            ),
        ]

        from services.algorag.diversity import apply_diversity_filter
        filtered = apply_diversity_filter(setups, max_per_day=1)

        # Should only keep one setup (highest score) from DST transition date
        assert len(filtered) == 1
        assert filtered[0].trade_id == "PRE_DST"

    def test_diversity_with_microsecond_precision(self):
        """RED: Test diversity filtering with microsecond-precision timestamps."""
        base_time = datetime(2024, 3, 15, 9, 15, 30, tzinfo=timezone.utc)
        
        setups = []
        for i in range(3):
            setups.append(
                SimilarSetup(
                    trade_id=f"MICRO_{i}",
                    timestamp=base_time.replace(microsecond=i * 100000),  # Same second, different microseconds
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.0 + i * 0.3,
                    narrative=f"Microsecond setup {i}",
                    similarity_score=0.9 - i * 0.05,
                    final_score=0.9 - i * 0.05,
                )
            )

        from services.algorag.diversity import apply_diversity_filter
        filtered = apply_diversity_filter(setups, max_per_day=2)

        # All should be same calendar day, so limited to 2
        assert len(filtered) == 2
        assert filtered[0].trade_id == "MICRO_0"
        assert filtered[1].trade_id == "MICRO_1"
    def test_diversity_preserves_score_ordering_within_limit(self):
        """RED: Test diversity preserves descending score order within daily limit."""
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        
        # Create setups with non-monotonic R-multiples but monotonic final_scores
        setups = [
            SimilarSetup(
                trade_id="HIGH_SCORE",
                timestamp=same_day.replace(hour=8),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=5,
                outcome_result="WIN",
                outcome_r_multiple=2.0,  # Lower R-multiple
                narrative="High score setup",
                similarity_score=0.95,
                final_score=0.95,  # Highest final score
            ),
            SimilarSetup(
                trade_id="MID_SCORE",
                timestamp=same_day.replace(hour=14),
                instrument="EURUSD",
                time_window="NY_KILLZONE", 
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=4.0,  # Higher R-multiple
                narrative="Mid score setup",
                similarity_score=0.85,
                final_score=0.85,  # Middle final score
            ),
            SimilarSetup(
                trade_id="LOW_SCORE",
                timestamp=same_day.replace(hour=20),
                instrument="EURUSD",
                time_window="SYDNEY_OPEN",
                htf_open_bias="BULLISH",
                confluence_count=1,
                outcome_result="WIN", 
                outcome_r_multiple=5.0,  # Highest R-multiple
                narrative="Low score setup",
                similarity_score=0.75,
                final_score=0.75,  # Lowest final score
            ),
        ]

        from services.algorag.diversity import apply_diversity_filter
        filtered = apply_diversity_filter(setups, max_per_day=2)

        # Should preserve top 2 by final_score, not by R-multiple
        assert len(filtered) == 2
        assert filtered[0].trade_id == "HIGH_SCORE"  # Highest final_score
        assert filtered[1].trade_id == "MID_SCORE"   # Second highest final_score
        # LOW_SCORE excluded despite highest R-multiple

    def test_diversity_with_extreme_daily_limits(self):
        """RED: Test diversity filtering with extreme daily limit values."""
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        
        setups = []
        for i in range(10):  # 10 setups same day
            setups.append(
                SimilarSetup(
                    trade_id=f"SETUP_{i:02d}",
                    timestamp=same_day.replace(hour=6 + i),
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=3,
                    outcome_result="WIN",
                    outcome_r_multiple=2.0,
                    narrative=f"Setup {i}",
                    similarity_score=0.9 - i * 0.05,
                    final_score=0.9 - i * 0.05,
                )
            )

        from services.algorag.diversity import apply_diversity_filter

        # Test with very high limit (should return all)
        filtered_high = apply_diversity_filter(setups, max_per_day=100)
        assert len(filtered_high) == 10

        # Test with limit of 1 (should return only best)
        filtered_one = apply_diversity_filter(setups, max_per_day=1)
        assert len(filtered_one) == 1
        assert filtered_one[0].trade_id == "SETUP_00"

        # Test with zero limit (should return empty)
        filtered_zero = apply_diversity_filter(setups, max_per_day=0)
        assert len(filtered_zero) == 0
    def test_diversity_multiple_instruments_same_day(self):
        """RED: Test diversity filtering handles multiple instruments on same day."""
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        
        # Multiple instruments, same day, should not interfere with each other's limits
        setups = [
            SimilarSetup(
                trade_id="EUR_1",
                timestamp=same_day.replace(hour=8),
                instrument="EURUSD",  # Different instruments
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.0,
                narrative="EUR setup 1",
                similarity_score=0.9,
                final_score=0.9,
            ),
            SimilarSetup(
                trade_id="GBP_1",
                timestamp=same_day.replace(hour=9),
                instrument="GBPUSD",  # Different instruments
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=2,
                outcome_result="WIN",
                outcome_r_multiple=1.8,
                narrative="GBP setup 1",
                similarity_score=0.85,
                final_score=0.85,
            ),
            SimilarSetup(
                trade_id="EUR_2", 
                timestamp=same_day.replace(hour=14),
                instrument="EURUSD",  # Same as EUR_1
                time_window="NY_KILLZONE",
                htf_open_bias="BEARISH",
                confluence_count=1,
                outcome_result="WIN",
                outcome_r_multiple=1.5,
                narrative="EUR setup 2",
                similarity_score=0.8,
                final_score=0.8,
            ),
        ]

        from services.algorag.diversity import apply_diversity_filter
        
        # Note: Diversity filtering is applied per calendar day, not per instrument
        # With max_per_day=2, should get top 2 setups regardless of instrument
        filtered = apply_diversity_filter(setups, max_per_day=2)
        
        assert len(filtered) == 2
        assert filtered[0].trade_id == "EUR_1"  # Highest score
        assert filtered[1].trade_id == "GBP_1"  # Second highest score
        # EUR_2 should be excluded (3rd highest score)


class TestRAGMetricsComputation:
    """
    **Validates: Requirements FR-RAG-4**
    
    Tests for RAG metrics computation from retrieved setups to ensure
    statistical validity and proper aggregation.
    """

    def test_rag_metrics_with_empty_setups(self):
        """RED: Test RAG metrics computation with empty setup list."""
        from services.algorag.main import _build_rag_metrics
        
        metrics = _build_rag_metrics([])
        
        assert metrics.avg_r_multiple_similar == 0.0
        assert metrics.win_rate_similar == 0.0
        assert metrics.sample_size == 0
        assert metrics.max_similarity_score == 0.0
        assert metrics.avg_confluence_count == 0.0

    def test_rag_metrics_with_single_setup(self):
        """RED: Test RAG metrics computation with single setup."""
        setup = SimilarSetup(
            trade_id="SINGLE",
            timestamp=datetime.now(timezone.utc),
            instrument="EURUSD",
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            confluence_count=4,
            outcome_result="WIN",
            outcome_r_multiple=3.5,
            narrative="Single setup",
            similarity_score=0.87,
            final_score=0.92,
        )

        from services.algorag.main import _build_rag_metrics
        metrics = _build_rag_metrics([setup])

        assert metrics.avg_r_multiple_similar == 3.5
        assert metrics.win_rate_similar == 1.0  # 100% win rate (1 win out of 1)
        assert metrics.sample_size == 1
        assert metrics.max_similarity_score == 0.87
        assert metrics.avg_confluence_count == 4.0
    def test_rag_metrics_mixed_outcomes(self):
        """RED: Test RAG metrics computation with mixed WIN/LOSS outcomes."""
        setups = [
            SimilarSetup(
                trade_id="WIN_1",
                timestamp=datetime.now(timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=5,
                outcome_result="WIN",
                outcome_r_multiple=4.0,
                narrative="Win setup 1",
                similarity_score=0.95,
                final_score=0.95,
            ),
            SimilarSetup(
                trade_id="LOSS_1",
                timestamp=datetime.now(timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="LOSS",
                outcome_r_multiple=-1.0,  # Negative for loss
                narrative="Loss setup 1",
                similarity_score=0.90,
                final_score=0.85,
            ),
            SimilarSetup(
                trade_id="WIN_2",
                timestamp=datetime.now(timezone.utc),
                instrument="EURUSD",
                time_window="NY_KILLZONE",
                htf_open_bias="BEARISH",
                confluence_count=2,
                outcome_result="WIN",
                outcome_r_multiple=2.5,
                narrative="Win setup 2",
                similarity_score=0.85,
                final_score=0.80,
            ),
        ]

        from services.algorag.main import _build_rag_metrics
        metrics = _build_rag_metrics(setups)

        # Average R-multiple: (4.0 + (-1.0) + 2.5) / 3 = 1.833...
        assert abs(metrics.avg_r_multiple_similar - (5.5 / 3)) < 0.01
        
        # Win rate: 2 wins out of 3 = 0.667
        assert abs(metrics.win_rate_similar - (2 / 3)) < 0.01
        
        assert metrics.sample_size == 3
        assert metrics.max_similarity_score == 0.95
        
        # Average confluence: (5 + 3 + 2) / 3 = 3.333...
        assert abs(metrics.avg_confluence_count - (10 / 3)) < 0.01

    def test_rag_metrics_top_5_limitation(self):
        """RED: Test RAG metrics only uses top-5 setups for computation."""
        # Create 7 setups, metrics should only use first 5
        setups = []
        for i in range(7):
            setups.append(
                SimilarSetup(
                    trade_id=f"SETUP_{i}",
                    timestamp=datetime.now(timezone.utc),
                    instrument="EURUSD",
                    time_window="LONDON_KILLZONE",
                    htf_open_bias="BULLISH",
                    confluence_count=i + 1,  # 1, 2, 3, 4, 5, 6, 7
                    outcome_result="WIN",
                    outcome_r_multiple=float(i + 1),  # 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0
                    narrative=f"Setup {i}",
                    similarity_score=0.9 - i * 0.05,
                    final_score=0.9 - i * 0.05,
                )
            )

        from services.algorag.main import _build_rag_metrics
        metrics = _build_rag_metrics(setups)

        # Should only use first 5 setups
        assert metrics.sample_size == 5
        
        # Average R-multiple of first 5: (1.0 + 2.0 + 3.0 + 4.0 + 5.0) / 5 = 3.0
        assert metrics.avg_r_multiple_similar == 3.0
        
        # Average confluence of first 5: (1 + 2 + 3 + 4 + 5) / 5 = 3.0
        assert metrics.avg_confluence_count == 3.0
        
        # Max similarity of first 5: 0.9 (first setup has highest score)
        assert metrics.max_similarity_score == 0.9

    def test_rag_metrics_bounds_validation(self):
        """RED: Test RAG metrics respect expected bounds (win_rate in [0,1], etc)."""
        setups = [
            SimilarSetup(
                trade_id="EXTREME_WIN",
                timestamp=datetime.now(timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=10,  # High confluence
                outcome_result="WIN",
                outcome_r_multiple=50.0,  # Extreme R-multiple
                narrative="Extreme win",
                similarity_score=1.0,  # Max similarity
                final_score=1.0,
            ),
        ]

        from services.algorag.main import _build_rag_metrics
        metrics = _build_rag_metrics(setups)

        # Verify bounds
        assert 0.0 <= metrics.win_rate_similar <= 1.0
        assert 0.0 <= metrics.max_similarity_score <= 1.0
        assert metrics.sample_size >= 0
        assert metrics.avg_confluence_count >= 0.0
        
        # Specific values for this test
        assert metrics.win_rate_similar == 1.0
        assert metrics.max_similarity_score == 1.0
        assert metrics.avg_r_multiple_similar == 50.0