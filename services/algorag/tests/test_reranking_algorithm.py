"""
Unit tests for re-ranking algorithm (Task 10.6).

Tests re-ranking algorithm with mock data, ensuring outcome quality,
recency, and confluence overlap are correctly weighted.

Requirements: FR-RAG-3
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from services.algorag.models import SimilarSetup
from services.algorag.reranking import (
    ReRankingConfig,
    compute_recency_score,
    compute_outcome_score,
    compute_confluence_score,
    compute_final_score,
    rerank_setups,
)


class TestRecencyScore:
    """Tests for recency score computation with exponential decay."""

    def test_recency_score_same_time(self):
        """RED: Test recency score when setup is from current time (score = 1.0)."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        setup_time = current
        
        score = compute_recency_score(setup_time, current)
        
        assert score == 1.0

    def test_recency_score_90_days_ago(self):
        """RED: Test recency score after exactly 90 days (half-life, score = 0.5)."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        setup_time = current - timedelta(days=90)
        
        score = compute_recency_score(setup_time, current)
        
        # Should be approximately 0.5 (half-life)
        assert 0.49 < score < 0.51

    def test_recency_score_180_days_ago(self):
        """RED: Test recency score after 180 days (2 half-lives, score = 0.25)."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        setup_time = current - timedelta(days=180)
        
        score = compute_recency_score(setup_time, current)
        
        # Should be approximately 0.25 (2 half-lives)
        assert 0.24 < score < 0.26

    def test_recency_score_1_day_ago(self):
        """RED: Test recency score for recent setup (1 day ago)."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        setup_time = current - timedelta(days=1)
        
        score = compute_recency_score(setup_time, current)
        
        # Should be close to 1.0 but slightly less
        assert 0.99 < score <= 1.0

    def test_recency_score_future_time_clamped(self):
        """RED: Test recency score handles future timestamps (should clamp to 1.0)."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        setup_time = current + timedelta(days=10)  # Future time
        
        score = compute_recency_score(setup_time, current)
        
        # Should be clamped to 1.0 (no negative days)
        assert score == 1.0

    def test_recency_score_very_old_setup(self):
        """RED: Test recency score for very old setup (1 year ago)."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        setup_time = current - timedelta(days=365)
        
        score = compute_recency_score(setup_time, current)
        
        # Should be very small but > 0
        assert 0.0 < score < 0.1


class TestOutcomeScore:
    """Tests for outcome quality score computation."""

    def test_outcome_score_zero_r_multiple(self):
        """RED: Test outcome score for R = 0 (score = 0.0)."""
        score = compute_outcome_score(0.0)
        
        assert score == 0.0

    def test_outcome_score_negative_r_multiple(self):
        """RED: Test outcome score for negative R (loss, score = 0.0)."""
        score = compute_outcome_score(-2.5)
        
        assert score == 0.0

    def test_outcome_score_1r(self):
        """RED: Test outcome score for R = 1.0 (10% of max)."""
        score = compute_outcome_score(1.0, max_r_multiple=10.0)
        
        assert score == 0.1  # 1.0 / 10.0

    def test_outcome_score_5r(self):
        """RED: Test outcome score for R = 5.0 (50% of max)."""
        score = compute_outcome_score(5.0, max_r_multiple=10.0)
        
        assert score == 0.5  # 5.0 / 10.0

    def test_outcome_score_max_r_multiple(self):
        """RED: Test outcome score at exactly max_r_multiple (score = 1.0)."""
        score = compute_outcome_score(10.0, max_r_multiple=10.0)
        
        assert score == 1.0

    def test_outcome_score_above_max_clamped(self):
        """RED: Test outcome score above max_r_multiple is clamped to 1.0."""
        score = compute_outcome_score(15.0, max_r_multiple=10.0)
        
        assert score == 1.0  # Clamped

    def test_outcome_score_custom_max_r(self):
        """RED: Test outcome score with custom max_r_multiple."""
        score = compute_outcome_score(4.0, max_r_multiple=5.0)
        
        assert score == 0.8  # 4.0 / 5.0


class TestConfluenceScore:
    """Tests for confluence overlap score computation."""

    def test_confluence_score_both_zero(self):
        """RED: Test confluence score when both setups have 0 confluence (score = 1.0)."""
        score = compute_confluence_score(0, 0)
        
        assert score == 1.0  # Perfect match

    def test_confluence_score_one_zero(self):
        """RED: Test confluence score when one setup has 0 confluence (score = 0.0)."""
        score = compute_confluence_score(3, 0)
        
        assert score == 0.0  # No overlap

    def test_confluence_score_perfect_match(self):
        """RED: Test confluence score with identical counts (score = 1.0)."""
        score = compute_confluence_score(5, 5)
        
        assert score == 1.0  # Perfect match

    def test_confluence_score_partial_overlap(self):
        """RED: Test confluence score with partial overlap (Jaccard-like)."""
        # Historical setup: 4 confluence factors
        # Current setup: 6 confluence factors
        # Score = min/max = 4/6 = 0.667
        score = compute_confluence_score(4, 6)
        
        assert 0.66 < score < 0.67

    def test_confluence_score_inverted_partial_overlap(self):
        """RED: Test confluence score is symmetric."""
        score1 = compute_confluence_score(4, 6)
        score2 = compute_confluence_score(6, 4)
        
        assert score1 == score2  # Symmetric

    def test_confluence_score_minimal_overlap(self):
        """RED: Test confluence score with minimal overlap (1 vs 10)."""
        score = compute_confluence_score(1, 10)
        
        assert score == 0.1  # 1/10


class TestFinalScoreComputation:
    """Tests for final score computation with all components."""

    def test_final_score_perfect_setup(self):
        """RED: Test final score for perfect setup (recent, high R, perfect confluence)."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        setup_time = current  # Same time
        
        config = ReRankingConfig(
            outcome_weight=0.5,
            recency_weight=0.3,
            confluence_weight=0.2,
            max_r_multiple=10.0,
        )
        
        score = compute_final_score(
            outcome_r_multiple=10.0,  # Max R
            setup_timestamp=setup_time,
            current_timestamp=current,
            setup_confluence_count=5,
            current_confluence_count=5,  # Perfect match
            config=config,
        )
        
        # All components = 1.0
        # Final = 0.5*1.0 + 0.3*1.0 + 0.2*1.0 = 1.0
        assert score == 1.0

    def test_final_score_poor_setup(self):
        """RED: Test final score for poor setup (old, low R, no confluence)."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        setup_time = current - timedelta(days=365)  # 1 year ago
        
        config = ReRankingConfig(
            outcome_weight=0.5,
            recency_weight=0.3,
            confluence_weight=0.2,
            max_r_multiple=10.0,
        )
        
        score = compute_final_score(
            outcome_r_multiple=0.5,  # Low R
            setup_timestamp=setup_time,
            current_timestamp=current,
            setup_confluence_count=0,
            current_confluence_count=5,  # No overlap
            config=config,
        )
        
        # All components close to 0
        assert score < 0.1

    def test_final_score_outcome_weighted(self):
        """RED: Test final score is heavily influenced by outcome quality."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        
        config = ReRankingConfig(
            outcome_weight=0.5,
            recency_weight=0.3,
            confluence_weight=0.2,
            max_r_multiple=10.0,
        )
        
        # High R but old and poor confluence
        score_high_r = compute_final_score(
            outcome_r_multiple=10.0,
            setup_timestamp=current - timedelta(days=180),  # Old
            current_timestamp=current,
            setup_confluence_count=2,
            current_confluence_count=8,  # Poor match
            config=config,
        )
        
        # Low R but recent and good confluence
        score_low_r = compute_final_score(
            outcome_r_multiple=1.0,
            setup_timestamp=current,  # Recent
            current_timestamp=current,
            setup_confluence_count=8,
            current_confluence_count=8,  # Perfect match
            config=config,
        )
        
        # High R should dominate despite being old
        assert score_high_r > score_low_r

    def test_final_score_clamped_to_range(self):
        """RED: Test final score is always in [0.0, 1.0] range."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        
        config = ReRankingConfig(
            outcome_weight=0.5,
            recency_weight=0.3,
            confluence_weight=0.2,
            max_r_multiple=10.0,
        )
        
        # Test various edge cases
        test_cases = [
            (0.0, current - timedelta(days=1000), 0, 10),  # All poor
            (20.0, current, 10, 10),  # All excellent (R clamped)
            (-5.0, current + timedelta(days=100), 0, 0),  # Negative R, future time
        ]
        
        for r_mult, setup_time, setup_conf, current_conf in test_cases:
            score = compute_final_score(
                outcome_r_multiple=r_mult,
                setup_timestamp=setup_time,
                current_timestamp=current,
                setup_confluence_count=setup_conf,
                current_confluence_count=current_conf,
                config=config,
            )
            
            assert 0.0 <= score <= 1.0

    def test_final_score_custom_weights(self):
        """RED: Test final score respects custom weight configuration."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        
        # Outcome-heavy weighting
        config_outcome = ReRankingConfig(
            outcome_weight=0.8,
            recency_weight=0.1,
            confluence_weight=0.1,
        )
        
        # Recency-heavy weighting
        config_recency = ReRankingConfig(
            outcome_weight=0.1,
            recency_weight=0.8,
            confluence_weight=0.1,
        )
        
        # Test scenario: high R but old setup
        score_outcome = compute_final_score(
            outcome_r_multiple=10.0,  # High R
            setup_timestamp=current - timedelta(days=180),  # Old (low recency)
            current_timestamp=current,
            setup_confluence_count=3,
            current_confluence_count=3,
            config=config_outcome,
        )
        
        # Same scenario with recency-heavy weights
        score_recency = compute_final_score(
            outcome_r_multiple=10.0,  # High R
            setup_timestamp=current - timedelta(days=180),  # Old (low recency)
            current_timestamp=current,
            setup_confluence_count=3,
            current_confluence_count=3,
            config=config_recency,
        )
        
        # With outcome-heavy weights, the score should be higher
        # because it prioritizes the high R-multiple over low recency
        assert score_outcome > score_recency


class TestRerankSetups:
    """Tests for full re-ranking workflow with mock data."""

    def test_rerank_empty_list(self):
        """RED: Test re-ranking with empty list returns empty list."""
        reranked = rerank_setups(
            setups=[],
            current_confluence_count=3,
        )
        
        assert reranked == []

    def test_rerank_single_setup(self):
        """RED: Test re-ranking with single setup preserves it."""
        setup = SimilarSetup(
            trade_id="TRD-001",
            timestamp=datetime(2024, 3, 15, tzinfo=timezone.utc),
            instrument="EURUSD",
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            confluence_count=3,
            outcome_result="WIN",
            outcome_r_multiple=2.5,
            narrative="Test",
            similarity_score=0.9,
            final_score=0.9,
        )
        
        reranked = rerank_setups(
            setups=[setup],
            current_confluence_count=3,
            current_timestamp=datetime(2024, 5, 6, tzinfo=timezone.utc),
        )
        
        assert len(reranked) == 1
        assert reranked[0].trade_id == "TRD-001"
        # final_score should be updated
        assert reranked[0].final_score != setup.similarity_score

    def test_rerank_sorts_by_final_score(self):
        """RED: Test re-ranking sorts setups by final_score descending."""
        current = datetime(2024, 5, 6, tzinfo=timezone.utc)
        
        setups = [
            # Old setup with low R (should rank low)
            SimilarSetup(
                trade_id="TRD-POOR",
                timestamp=current - timedelta(days=365),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=2,
                outcome_result="WIN",
                outcome_r_multiple=0.5,
                narrative="Poor setup",
                similarity_score=0.95,  # High similarity
                final_score=0.95,
            ),
            # Recent setup with high R (should rank high)
            SimilarSetup(
                trade_id="TRD-GOOD",
                timestamp=current - timedelta(days=1),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=5,
                outcome_result="WIN",
                outcome_r_multiple=8.0,
                narrative="Good setup",
                similarity_score=0.80,  # Lower similarity
                final_score=0.80,
            ),
        ]
        
        reranked = rerank_setups(
            setups=setups,
            current_confluence_count=5,
            current_timestamp=current,
        )
        
        # Good setup should rank first despite lower similarity
        assert reranked[0].trade_id == "TRD-GOOD"
        assert reranked[1].trade_id == "TRD-POOR"
        assert reranked[0].final_score > reranked[1].final_score

    def test_rerank_preserves_similarity_score(self):
        """RED: Test re-ranking preserves original similarity_score."""
        current = datetime(2024, 5, 6, tzinfo=timezone.utc)
        
        setup = SimilarSetup(
            trade_id="TRD-001",
            timestamp=current - timedelta(days=30),
            instrument="EURUSD",
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            confluence_count=3,
            outcome_result="WIN",
            outcome_r_multiple=3.0,
            narrative="Test",
            similarity_score=0.87,
            final_score=0.87,
        )
        
        reranked = rerank_setups(
            setups=[setup],
            current_confluence_count=3,
            current_timestamp=current,
        )
        
        # similarity_score should be unchanged
        assert reranked[0].similarity_score == 0.87
        # final_score should be different
        assert reranked[0].final_score != 0.87

    def test_rerank_uses_default_config_if_none(self):
        """RED: Test re-ranking uses default config when none provided."""
        current = datetime(2024, 5, 6, tzinfo=timezone.utc)
        
        setup = SimilarSetup(
            trade_id="TRD-001",
            timestamp=current,
            instrument="EURUSD",
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            confluence_count=5,
            outcome_result="WIN",
            outcome_r_multiple=10.0,
            narrative="Perfect setup",
            similarity_score=0.9,
            final_score=0.9,
        )
        
        reranked = rerank_setups(
            setups=[setup],
            current_confluence_count=5,
            current_timestamp=current,
            config=None,  # Should use default
        )
        
        # Should complete without error
        assert len(reranked) == 1

    def test_rerank_complex_scenario(self):
        """RED: Test re-ranking with complex multi-setup scenario."""
        current = datetime(2024, 5, 6, 12, 0, tzinfo=timezone.utc)
        
        setups = [
            # A: Very old, very high R
            SimilarSetup(
                trade_id="TRD-A",
                timestamp=current - timedelta(days=270),  # 9 months
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=7,
                outcome_result="WIN",
                outcome_r_multiple=12.0,  # Excellent
                narrative="Old but golden",
                similarity_score=0.95,
                final_score=0.95,
            ),
            # B: Recent, moderate R
            SimilarSetup(
                trade_id="TRD-B",
                timestamp=current - timedelta(days=7),  # 1 week
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=4,
                outcome_result="WIN",
                outcome_r_multiple=3.5,  # Good
                narrative="Recent moderate",
                similarity_score=0.88,
                final_score=0.88,
            ),
            # C: Very recent, low R
            SimilarSetup(
                trade_id="TRD-C",
                timestamp=current - timedelta(hours=12),  # Today
                instrument="EURUSD",
                time_window="NY_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=1.2,  # Mediocre
                narrative="Very recent",
                similarity_score=0.82,
                final_score=0.82,
            ),
        ]
        
        reranked = rerank_setups(
            setups=setups,
            current_confluence_count=5,
            current_timestamp=current,
        )
        
        # A should rank first (high R dominates with 0.5 weight)
        # B should rank second (good balance)
        # C should rank third (low R despite recency)
        assert len(reranked) == 3
        assert reranked[0].trade_id == "TRD-A"
        assert reranked[1].trade_id == "TRD-B"
        assert reranked[2].trade_id == "TRD-C"

    def test_rerank_uses_current_timestamp_if_none(self):
        """RED: Test re-ranking uses current time when current_timestamp is None."""
        setup = SimilarSetup(
            trade_id="TRD-001",
            timestamp=datetime.now(timezone.utc) - timedelta(days=30),
            instrument="EURUSD",
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            confluence_count=3,
            outcome_result="WIN",
            outcome_r_multiple=2.5,
            narrative="Test",
            similarity_score=0.9,
            final_score=0.9,
        )
        
        # Should not raise error and use current time
        reranked = rerank_setups(
            setups=[setup],
            current_confluence_count=3,
            current_timestamp=None,  # Should use now()
        )
        
        assert len(reranked) == 1

    def test_rerank_maintains_all_fields(self):
        """RED: Test re-ranking maintains all setup fields except final_score."""
        current = datetime(2024, 5, 6, tzinfo=timezone.utc)
        
        setup = SimilarSetup(
            trade_id="TRD-001",
            timestamp=current - timedelta(days=30),
            instrument="GBPUSD",
            time_window="NY_KILLZONE",
            htf_open_bias="BEARISH",
            confluence_count=4,
            outcome_result="WIN",
            outcome_r_multiple=2.8,
            narrative="Detailed narrative here",
            similarity_score=0.86,
            final_score=0.86,
            full_setup={"extra": "data"},
        )
        
        reranked = rerank_setups(
            setups=[setup],
            current_confluence_count=4,
            current_timestamp=current,
        )
        
        result = reranked[0]
        # All fields should be preserved except final_score
        assert result.trade_id == "TRD-001"
        assert result.timestamp == setup.timestamp
        assert result.instrument == "GBPUSD"
        assert result.time_window == "NY_KILLZONE"
        assert result.htf_open_bias == "BEARISH"
        assert result.confluence_count == 4
        assert result.outcome_result == "WIN"
        assert result.outcome_r_multiple == 2.8
        assert result.narrative == "Detailed narrative here"
        assert result.similarity_score == 0.86
        assert result.full_setup == {"extra": "data"}
        # Only final_score should change
        assert result.final_score != 0.86
