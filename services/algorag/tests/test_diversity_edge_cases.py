"""
TDD - Task 10.5: Diversity filtering edge cases

Additional edge case tests for diversity filtering to ensure robust behavior
in all scenarios mentioned in the task requirements.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import pytest

from services.algorag.models import SimilarSetup
from services.algorag.diversity import apply_diversity_filter


class TestDiversityFilteringEdgeCases:
    """RED phase: Test edge cases for diversity filtering."""

    def test_diversity_with_empty_list(self):
        """RED: Test diversity filtering with empty setup list."""
        # Should handle empty input gracefully
        filtered = apply_diversity_filter([], max_per_day=3)
        
        assert filtered == []
        assert len(filtered) == 0

    def test_diversity_with_single_setup(self):
        """RED: Test diversity filtering with only one setup."""
        setup = SimilarSetup(
            trade_id="TRD-001",
            timestamp=datetime(2024, 3, 15, 9, 15, tzinfo=timezone.utc),
            instrument="EURUSD",
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            confluence_count=3,
            outcome_result="WIN",
            outcome_r_multiple=2.5,
            narrative="Single setup",
            similarity_score=0.9,
            final_score=0.9,
        )
        
        filtered = apply_diversity_filter([setup], max_per_day=3)
        
        assert len(filtered) == 1
        assert filtered[0].trade_id == "TRD-001"

    def test_diversity_with_mixed_timestamps_same_day(self):
        """RED: Test diversity filtering handles mixed timestamps on same calendar day."""
        # Setup: Different times on same calendar day (March 15, 2024)
        base_date = datetime(2024, 3, 15, tzinfo=timezone.utc)
        
        setups = [
            SimilarSetup(
                trade_id="TRD-EARLY",
                timestamp=base_date.replace(hour=1, minute=30),  # 01:30 UTC
                instrument="EURUSD",
                time_window="ASIAN_KILLZONE", 
                htf_open_bias="BULLISH",
                confluence_count=4,
                outcome_result="WIN",
                outcome_r_multiple=3.0,
                narrative="Early morning setup",
                similarity_score=0.95,
                final_score=0.95,
            ),
            SimilarSetup(
                trade_id="TRD-LONDON", 
                timestamp=base_date.replace(hour=8, minute=0),   # 08:00 UTC
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH", 
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.5,
                narrative="London open setup",
                similarity_score=0.90,
                final_score=0.90,
            ),
            SimilarSetup(
                trade_id="TRD-NY",
                timestamp=base_date.replace(hour=14, minute=30), # 14:30 UTC  
                instrument="EURUSD",
                time_window="NY_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=2,
                outcome_result="WIN", 
                outcome_r_multiple=1.8,
                narrative="NY session setup",
                similarity_score=0.85,
                final_score=0.85,
            ),
            SimilarSetup(
                trade_id="TRD-LATE",
                timestamp=base_date.replace(hour=22, minute=45), # 22:45 UTC
                instrument="EURUSD",
                time_window="SYDNEY_OPEN",
                htf_open_bias="BULLISH",
                confluence_count=2,
                outcome_result="WIN",
                outcome_r_multiple=1.5, 
                narrative="Late session setup",
                similarity_score=0.80,
                final_score=0.80,
            ),
        ]
        
        # Test with max_per_day = 2: should only get top 2 by final_score
        filtered = apply_diversity_filter(setups, max_per_day=2)
        
        assert len(filtered) == 2
        assert filtered[0].trade_id == "TRD-EARLY"    # Highest final_score (0.95)
        assert filtered[1].trade_id == "TRD-LONDON"   # Second highest (0.90)

    def test_diversity_preserves_order_within_day_limit(self):
        """RED: Test diversity filtering preserves original order when under daily limit."""
        # Setup: 2 setups from same day, limit = 3 (under limit)
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        
        setups = [
            SimilarSetup(
                trade_id="TRD-FIRST",
                timestamp=same_day.replace(hour=9),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.0,
                narrative="First setup",
                similarity_score=0.8,
                final_score=0.8,  # Lower score but appears first
            ),
            SimilarSetup(
                trade_id="TRD-SECOND", 
                timestamp=same_day.replace(hour=15),
                instrument="EURUSD",
                time_window="NY_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=2,
                outcome_result="WIN",
                outcome_r_multiple=3.0,
                narrative="Second setup",
                similarity_score=0.9,
                final_score=0.9,  # Higher score but appears second
            ),
        ]
        
        # With limit=3, both should be preserved in original order
        filtered = apply_diversity_filter(setups, max_per_day=3)
        
        assert len(filtered) == 2
        assert filtered[0].trade_id == "TRD-FIRST"   # Original order preserved
        assert filtered[1].trade_id == "TRD-SECOND"

    def test_diversity_with_exactly_max_per_day_count(self):
        """RED: Test diversity filtering when setup count exactly equals max_per_day."""
        # Setup: Exactly 3 setups from same day, limit = 3
        same_day = datetime(2024, 3, 15, tzinfo=timezone.utc)
        
        setups = []
        for i in range(3):
            setups.append(
                SimilarSetup(
                    trade_id=f"TRD-{i:03d}",
                    timestamp=same_day.replace(hour=9 + i * 2),
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
        
        # With limit=3 and exactly 3 setups, all should pass through
        filtered = apply_diversity_filter(setups, max_per_day=3)
        
        assert len(filtered) == 3
        assert [s.trade_id for s in filtered] == ["TRD-000", "TRD-001", "TRD-002"]

    def test_diversity_with_negative_max_per_day(self):
        """RED: Test diversity filtering with invalid negative max_per_day."""
        setup = SimilarSetup(
            trade_id="TRD-001",
            timestamp=datetime(2024, 3, 15, tzinfo=timezone.utc),
            instrument="EURUSD",
            time_window="LONDON_KILLZONE", 
            htf_open_bias="BULLISH",
            confluence_count=3,
            outcome_result="WIN",
            outcome_r_multiple=2.0,
            narrative="Test setup",
            similarity_score=0.9,
            final_score=0.9,
        )
        
        # Negative max_per_day should result in empty list
        filtered = apply_diversity_filter([setup], max_per_day=-1)
        
        assert filtered == []
        assert len(filtered) == 0

    def test_diversity_across_timezone_boundaries(self):
        """RED: Test diversity filtering handles timezone boundaries correctly."""
        # Test case: Two setups at 23:30 UTC and 00:30 UTC (different calendar days in UTC)
        
        setups = [
            SimilarSetup(
                trade_id="TRD-LATE-DAY1",
                timestamp=datetime(2024, 3, 15, 23, 30, tzinfo=timezone.utc),  # March 15 late
                instrument="EURUSD",
                time_window="SYDNEY_OPEN",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN", 
                outcome_r_multiple=2.5,
                narrative="Late March 15 setup",
                similarity_score=0.9,
                final_score=0.9,
            ),
            SimilarSetup(
                trade_id="TRD-EARLY-DAY2",
                timestamp=datetime(2024, 3, 16, 0, 30, tzinfo=timezone.utc),   # March 16 early  
                instrument="EURUSD",
                time_window="SYDNEY_OPEN",
                htf_open_bias="BULLISH",
                confluence_count=2,
                outcome_result="WIN",
                outcome_r_multiple=1.8,
                narrative="Early March 16 setup",
                similarity_score=0.85,
                final_score=0.85,
            ),
        ]
        
        # These are different calendar days in UTC, so both should be preserved
        filtered = apply_diversity_filter(setups, max_per_day=1)
        
        assert len(filtered) == 2  # Different days = no diversity limit applied
        assert filtered[0].trade_id == "TRD-LATE-DAY1"
        assert filtered[1].trade_id == "TRD-EARLY-DAY2"

    def test_diversity_with_none_timestamp(self):
        """RED: Test diversity filtering handles None timestamp gracefully."""
        # This shouldn't happen in normal operation but test for robustness
        
        setups = [
            SimilarSetup(
                trade_id="TRD-VALID",
                timestamp=datetime(2024, 3, 15, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.0,
                narrative="Valid setup",
                similarity_score=0.9,
                final_score=0.9,
            ),
        ]
        
        # Should handle valid timestamp without issues
        filtered = apply_diversity_filter(setups, max_per_day=3)
        
        assert len(filtered) == 1
        assert filtered[0].trade_id == "TRD-VALID"