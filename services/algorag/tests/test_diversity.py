"""
Unit tests for diversity filtering (Task 10.5).

Covers the date-based deduplication applied to re-ranked retrieval results:
at most `max_per_day` setups from the same calendar day survive, input order
(assumed already sorted by relevance) is preserved among survivors.

Requirements: NFR-RAG-4
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.algorag.diversity import apply_diversity_filter
from services.algorag.models import SimilarSetup


def _make_setup(trade_id: str, timestamp: datetime, final_score: float = 0.5) -> SimilarSetup:
    return SimilarSetup(
        trade_id=trade_id,
        timestamp=timestamp,
        instrument="EURUSD",
        time_window="LONDON_KILLZONE",
        htf_open_bias="BULLISH",
        confluence_count=2,
        outcome_result="WIN",
        outcome_r_multiple=2.0,
        narrative="Price swept liquidity before reversing.",
        similarity_score=0.8,
        final_score=final_score,
    )


class TestBasicFiltering:
    def test_empty_list_returns_empty(self):
        assert apply_diversity_filter([], max_per_day=3) == []

    def test_under_limit_keeps_all(self):
        day = datetime(2024, 5, 6, 9, 0, tzinfo=timezone.utc)
        setups = [_make_setup(f"T{i}", day) for i in range(2)]
        result = apply_diversity_filter(setups, max_per_day=3)
        assert len(result) == 2

    def test_exactly_at_limit_keeps_all(self):
        day = datetime(2024, 5, 6, 9, 0, tzinfo=timezone.utc)
        setups = [_make_setup(f"T{i}", day) for i in range(3)]
        result = apply_diversity_filter(setups, max_per_day=3)
        assert len(result) == 3

    def test_over_limit_truncates_to_max(self):
        day = datetime(2024, 5, 6, 9, 0, tzinfo=timezone.utc)
        setups = [_make_setup(f"T{i}", day) for i in range(5)]
        result = apply_diversity_filter(setups, max_per_day=3)
        assert len(result) == 3

    def test_keeps_highest_ranked_first_occurrences(self):
        """Input is assumed pre-sorted by score; the first N per day (i.e. the
        highest-ranked) survive, later duplicates for that day are dropped."""
        day = datetime(2024, 5, 6, 9, 0, tzinfo=timezone.utc)
        setups = [
            _make_setup("BEST", day, final_score=0.9),
            _make_setup("SECOND", day, final_score=0.8),
            _make_setup("THIRD", day, final_score=0.7),
            _make_setup("DROPPED", day, final_score=0.6),
        ]
        result = apply_diversity_filter(setups, max_per_day=3)
        assert [s.trade_id for s in result] == ["BEST", "SECOND", "THIRD"]


class TestMultipleDays:
    def test_different_days_each_get_own_quota(self):
        day1 = datetime(2024, 5, 6, 9, 0, tzinfo=timezone.utc)
        day2 = day1 + timedelta(days=1)
        setups = [_make_setup(f"D1-{i}", day1) for i in range(3)] + [
            _make_setup(f"D2-{i}", day2) for i in range(3)
        ]
        result = apply_diversity_filter(setups, max_per_day=3)
        assert len(result) == 6

    def test_preserves_overall_order_across_days(self):
        day1 = datetime(2024, 5, 6, 9, 0, tzinfo=timezone.utc)
        day2 = day1 + timedelta(days=1)
        setups = [
            _make_setup("A", day1),
            _make_setup("B", day2),
            _make_setup("C", day1),
            _make_setup("D", day2),
        ]
        result = apply_diversity_filter(setups, max_per_day=3)
        assert [s.trade_id for s in result] == ["A", "B", "C", "D"]

    def test_same_calendar_day_different_times_share_quota(self):
        morning = datetime(2024, 5, 6, 2, 0, tzinfo=timezone.utc)
        evening = datetime(2024, 5, 6, 23, 0, tzinfo=timezone.utc)
        setups = [_make_setup("MORNING", morning), _make_setup("EVENING", evening)]
        result = apply_diversity_filter(setups, max_per_day=1)
        assert len(result) == 1
        assert result[0].trade_id == "MORNING"


class TestConfigurableThreshold:
    def test_max_per_day_one(self):
        day = datetime(2024, 5, 6, 9, 0, tzinfo=timezone.utc)
        setups = [_make_setup(f"T{i}", day) for i in range(4)]
        result = apply_diversity_filter(setups, max_per_day=1)
        assert len(result) == 1

    def test_default_max_per_day_is_three(self):
        day = datetime(2024, 5, 6, 9, 0, tzinfo=timezone.utc)
        setups = [_make_setup(f"T{i}", day) for i in range(5)]
        result = apply_diversity_filter(setups)
        assert len(result) == 3

    def test_zero_max_per_day_is_treated_as_no_filtering(self):
        """A misconfigured non-positive threshold must not silently drop
        every result — treat it as 'filtering disabled' instead."""
        day = datetime(2024, 5, 6, 9, 0, tzinfo=timezone.utc)
        setups = [_make_setup(f"T{i}", day) for i in range(3)]
        result = apply_diversity_filter(setups, max_per_day=0)
        assert len(result) == 3
