"""
Test suite for session and time feature extractor.

This module tests the TimeWindowClassifier and narrative context generation:
- Time window classification (ASIAN_RANGE, TRUE_DAY_OPEN, LONDON_KILLZONE, etc.)
- DST transitions for NY timezone
- Narrative phase derivation
- Time window probability weights
- Price position relative to reference opens
- Narrative context generation

**Validates: Requirements FR-3A**
"""

import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, strategies as st, assume

# ---------------------------------------------------------------------------
# Path setup — add workspace root so `ml` package is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from ml.features.session_features import (  # noqa: E402
    TimeFeatures,
    TimeWindowClassifier,
    get_narrative_context,
)


# ---------------------------------------------------------------------------
# Test Data Helpers
# ---------------------------------------------------------------------------

def create_utc_datetime(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Create a UTC datetime object."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Time Window Boundary Tests
# ---------------------------------------------------------------------------

class TestTimeWindowBoundaries:
    """Test all time window boundaries with exact timestamps."""

    def test_asian_range_window(self):
        """ASIAN_RANGE: 20:00-22:00 NY (00:00-02:00 UTC during EST, 01:00-03:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 20:00 NY = 01:00 UTC next day
        timestamp = create_utc_datetime(2024, 1, 2, 1, 0)  # 20:00 NY on Jan 1
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "ASIAN_RANGE"
        
        # July (EDT): 20:00 NY = 00:00 UTC next day
        timestamp = create_utc_datetime(2024, 7, 2, 0, 0)  # 20:00 NY on July 1
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "ASIAN_RANGE"

    def test_true_day_open_window(self):
        """TRUE_DAY_OPEN: 00:00-01:00 NY (04:00-05:00 UTC during EST, 05:00-06:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 00:00 NY = 05:00 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 5, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "TRUE_DAY_OPEN"
        
        # July (EDT): 00:00 NY = 04:00 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 4, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "TRUE_DAY_OPEN"

    def test_london_killzone_window(self):
        """LONDON_KILLZONE: 02:00-05:00 NY (06:00-09:00 UTC during EST, 07:00-10:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 02:00 NY = 07:00 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 7, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "LONDON_KILLZONE"
        
        # July (EDT): 02:00 NY = 06:00 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 6, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "LONDON_KILLZONE"

    def test_london_silver_bullet_window(self):
        """LONDON_SILVER_BULLET: 03:00-04:00 NY (07:00-08:00 UTC during EST, 08:00-09:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 03:00 NY = 08:00 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 8, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "LONDON_SILVER_BULLET"
        
        # July (EDT): 03:00 NY = 07:00 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 7, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "LONDON_SILVER_BULLET"

    def test_ny_am_killzone_window(self):
        """NY_AM_KILLZONE: 07:00-10:00 NY (11:00-14:00 UTC during EST, 12:00-15:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 07:00 NY = 12:00 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NY_AM_KILLZONE"
        
        # July (EDT): 07:00 NY = 11:00 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 11, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NY_AM_KILLZONE"

    def test_ny_am_silver_bullet_window(self):
        """NY_AM_SILVER_BULLET: 10:00-11:00 NY (14:00-15:00 UTC during EST, 15:00-16:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 10:00 NY = 15:00 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 15, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NY_AM_SILVER_BULLET"
        
        # July (EDT): 10:00 NY = 14:00 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 14, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NY_AM_SILVER_BULLET"

    def test_news_window(self):
        """NEWS_WINDOW: 08:00-09:00 NY (12:00-13:00 UTC during EST, 13:00-14:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 08:00-09:00 NY = 13:00-14:00 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 13, 15)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NEWS_WINDOW"
        
        # July (EDT): 08:00-09:00 NY = 12:00-13:00 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 12, 15)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NEWS_WINDOW"

    def test_london_close_window(self):
        """LONDON_CLOSE: 10:00-12:00 NY (14:00-16:00 UTC during EST, 15:00-17:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 11:00 NY = 16:00 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 16, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "LONDON_CLOSE"
        
        # July (EDT): 11:00 NY = 15:00 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 15, 30)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "LONDON_CLOSE"

    def test_ny_pm_killzone_window(self):
        """NY_PM_KILLZONE: 13:30-16:00 NY (17:30-20:00 UTC during EST, 18:30-21:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 13:30 NY = 18:30 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 18, 30)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NY_PM_KILLZONE"
        
        # July (EDT): 13:30 NY = 17:30 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 17, 30)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NY_PM_KILLZONE"

    def test_ny_pm_silver_bullet_window(self):
        """NY_PM_SILVER_BULLET: 14:00-15:00 NY (18:00-19:00 UTC during EST, 19:00-20:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 14:00 NY = 19:00 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 19, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NY_PM_SILVER_BULLET"
        
        # July (EDT): 14:00 NY = 18:00 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 18, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "NY_PM_SILVER_BULLET"

    def test_daily_close_window(self):
        """DAILY_CLOSE: 17:00-18:00 NY (21:00-22:00 UTC during EST, 22:00-23:00 UTC during EDT)."""
        classifier = TimeWindowClassifier()
        
        # January (EST): 17:00 NY = 22:00 UTC
        timestamp = create_utc_datetime(2024, 1, 1, 22, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "DAILY_CLOSE"
        
        # July (EDT): 17:00 NY = 21:00 UTC
        timestamp = create_utc_datetime(2024, 7, 1, 21, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "DAILY_CLOSE"

    def test_off_hours_window(self):
        """OFF_HOURS: all other times."""
        classifier = TimeWindowClassifier()
        
        # 12:00 NY = 17:00 UTC (EST) - between LONDON_CLOSE and DAILY_CLOSE
        timestamp = create_utc_datetime(2024, 1, 1, 17, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window == "OFF_HOURS"


# ---------------------------------------------------------------------------
# DST Transition Tests
# ---------------------------------------------------------------------------

class TestDSTTransitions:
    """Test DST transitions — NY switches between UTC-4 (EDT) and UTC-5 (EST)."""

    def test_est_to_edt_transition_march(self):
        """Test EST to EDT transition (second Sunday in March, 2:00 AM → 3:00 AM)."""
        classifier = TimeWindowClassifier()
        
        # March 10, 2024: DST starts (EST → EDT)
        # Before transition: 01:00 UTC = 20:00 NY (EST, previous day)
        timestamp_before = create_utc_datetime(2024, 3, 10, 6, 0)  # 01:00 NY EST
        features_before = classifier.classify(timestamp_before, "EURUSD")
        
        # After transition: 07:00 UTC = 03:00 NY (EDT)
        timestamp_after = create_utc_datetime(2024, 3, 10, 7, 0)  # 03:00 NY EDT
        features_after = classifier.classify(timestamp_after, "EURUSD")
        
        # Both should correctly identify their time windows
        # 03:00 NY is in LONDON_SILVER_BULLET window (03:00-04:00 NY)
        assert features_after.time_window == "LONDON_SILVER_BULLET"

    def test_edt_to_est_transition_november(self):
        """Test EDT to EST transition (first Sunday in November, 2:00 AM → 1:00 AM)."""
        classifier = TimeWindowClassifier()
        
        # November 3, 2024: DST ends (EDT → EST)
        # After transition: 07:00 UTC = 02:00 NY (EST, DST ended)
        timestamp_after = create_utc_datetime(2024, 11, 3, 7, 0)  # 02:00 NY EST
        features_after = classifier.classify(timestamp_after, "EURUSD")
        
        # 08:00 UTC = 03:00 NY (EST) - should be LONDON_SILVER_BULLET
        timestamp_killzone = create_utc_datetime(2024, 11, 3, 8, 0)  # 03:00 NY EST
        features_killzone = classifier.classify(timestamp_killzone, "EURUSD")
        
        # Both should correctly identify their time windows
        # 02:00 NY is in LONDON_KILLZONE window (02:00-05:00 NY)
        assert features_after.time_window == "LONDON_KILLZONE"
        # 03:00 NY is in LONDON_SILVER_BULLET window (03:00-04:00 NY)
        assert features_killzone.time_window == "LONDON_SILVER_BULLET"


# ---------------------------------------------------------------------------
# Narrative Phase Tests
# ---------------------------------------------------------------------------

class TestNarrativePhase:
    """Test narrative_phase derivation for all time_window values."""

    def test_asian_range_is_accumulation(self):
        """ASIAN_RANGE → ACCUMULATION phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 2, 1, 0)  # ASIAN_RANGE
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "ACCUMULATION"

    def test_london_killzone_is_manipulation(self):
        """LONDON_KILLZONE → MANIPULATION phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 7, 0)  # LONDON_KILLZONE
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "MANIPULATION"

    def test_london_silver_bullet_is_manipulation(self):
        """LONDON_SILVER_BULLET → MANIPULATION phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 8, 0)  # LONDON_SILVER_BULLET
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "MANIPULATION"

    def test_ny_am_killzone_is_expansion(self):
        """NY_AM_KILLZONE → EXPANSION phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)  # NY_AM_KILLZONE
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "EXPANSION"

    def test_ny_am_silver_bullet_is_expansion(self):
        """NY_AM_SILVER_BULLET → EXPANSION phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 15, 0)  # NY_AM_SILVER_BULLET
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "EXPANSION"

    def test_ny_pm_killzone_is_expansion(self):
        """NY_PM_KILLZONE → EXPANSION phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 18, 30)  # NY_PM_KILLZONE
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "EXPANSION"

    def test_london_close_is_distribution(self):
        """LONDON_CLOSE → DISTRIBUTION phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 16, 0)  # LONDON_CLOSE
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "DISTRIBUTION"

    def test_daily_close_is_distribution(self):
        """DAILY_CLOSE → DISTRIBUTION phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 22, 0)  # DAILY_CLOSE
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "DISTRIBUTION"

    def test_true_day_open_is_transition(self):
        """TRUE_DAY_OPEN → TRANSITION phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 5, 0)  # TRUE_DAY_OPEN
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "TRANSITION"

    def test_off_hours_is_off(self):
        """OFF_HOURS → OFF phase."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 17, 0)  # OFF_HOURS (12:00 NY)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.narrative_phase == "OFF"


# ---------------------------------------------------------------------------
# Time Window Weight Tests
# ---------------------------------------------------------------------------

class TestTimeWindowWeights:
    """Test time_window_weight values for all windows match spec."""

    def test_london_silver_bullet_weight(self):
        """LONDON_SILVER_BULLET → 1.0."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 8, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 1.0

    def test_ny_am_silver_bullet_weight(self):
        """NY_AM_SILVER_BULLET → 1.0."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 15, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 1.0

    def test_ny_pm_silver_bullet_weight(self):
        """NY_PM_SILVER_BULLET → 1.0."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 19, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 1.0

    def test_london_killzone_weight(self):
        """LONDON_KILLZONE → 0.9."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 7, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 0.9

    def test_ny_am_killzone_weight(self):
        """NY_AM_KILLZONE → 0.9."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 0.9

    def test_ny_pm_killzone_weight(self):
        """NY_PM_KILLZONE → 0.9."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 18, 30)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 0.9

    def test_news_window_weight(self):
        """NEWS_WINDOW → 0.8."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 13, 15)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 0.8

    def test_true_day_open_weight(self):
        """TRUE_DAY_OPEN → 0.7."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 5, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 0.7

    def test_london_close_weight(self):
        """LONDON_CLOSE → 0.5."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 16, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 0.5

    def test_asian_range_weight(self):
        """ASIAN_RANGE → 0.3."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 2, 1, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 0.3

    def test_daily_close_weight(self):
        """DAILY_CLOSE → 0.2."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 22, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 0.2

    def test_off_hours_weight(self):
        """OFF_HOURS → 0.1."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 17, 0)  # OFF_HOURS (12:00 NY)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.time_window_weight == 0.1


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestTimeWindowWeightProperty:
    """Property: time_window_weight is always in [0.0, 1.0]."""

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    def test_time_window_weight_in_valid_range(self, hour, minute):
        """
        Property: time_window_weight is always in [0.0, 1.0].
        
        **Validates: Requirements FR-3A**
        """
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, hour, minute)
        features = classifier.classify(timestamp, "EURUSD")
        
        assert 0.0 <= features.time_window_weight <= 1.0, (
            f"time_window_weight must be in [0.0, 1.0], got {features.time_window_weight}"
        )


class TestIsKillzoneProperty:
    """Property: is_killzone is True iff time_window is a killzone or silver bullet window."""

    def test_is_killzone_true_for_london_killzone(self):
        """is_killzone should be True for LONDON_KILLZONE."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 7, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_killzone is True

    def test_is_killzone_true_for_london_silver_bullet(self):
        """is_killzone should be True for LONDON_SILVER_BULLET."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 8, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_killzone is True

    def test_is_killzone_true_for_ny_am_killzone(self):
        """is_killzone should be True for NY_AM_KILLZONE."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_killzone is True

    def test_is_killzone_true_for_ny_am_silver_bullet(self):
        """is_killzone should be True for NY_AM_SILVER_BULLET."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 15, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_killzone is True

    def test_is_killzone_true_for_ny_pm_killzone(self):
        """is_killzone should be True for NY_PM_KILLZONE."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 18, 30)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_killzone is True

    def test_is_killzone_true_for_ny_pm_silver_bullet(self):
        """is_killzone should be True for NY_PM_SILVER_BULLET."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 19, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_killzone is True

    def test_is_killzone_false_for_other_windows(self):
        """is_killzone should be False for all other time windows."""
        classifier = TimeWindowClassifier()
        
        # Test ASIAN_RANGE
        timestamp = create_utc_datetime(2024, 1, 2, 1, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_killzone is False
        
        # Test TRUE_DAY_OPEN
        timestamp = create_utc_datetime(2024, 1, 1, 5, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_killzone is False
        
        # Test OFF_HOURS
        timestamp = create_utc_datetime(2024, 1, 1, 17, 0)  # 12:00 NY
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_killzone is False


class TestIsHighProbabilityWindowProperty:
    """Property: is_high_probability_window is True iff time_window_weight >= 0.7."""

    def test_is_high_probability_true_for_silver_bullets(self):
        """is_high_probability_window should be True for silver bullets (weight=1.0)."""
        classifier = TimeWindowClassifier()
        
        # LONDON_SILVER_BULLET
        timestamp = create_utc_datetime(2024, 1, 1, 8, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is True
        
        # NY_AM_SILVER_BULLET
        timestamp = create_utc_datetime(2024, 1, 1, 15, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is True
        
        # NY_PM_SILVER_BULLET
        timestamp = create_utc_datetime(2024, 1, 1, 19, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is True

    def test_is_high_probability_true_for_killzones(self):
        """is_high_probability_window should be True for killzones (weight=0.9)."""
        classifier = TimeWindowClassifier()
        
        # LONDON_KILLZONE
        timestamp = create_utc_datetime(2024, 1, 1, 7, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is True
        
        # NY_AM_KILLZONE
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is True

    def test_is_high_probability_true_for_news_window(self):
        """is_high_probability_window should be True for NEWS_WINDOW (weight=0.8)."""
        classifier = TimeWindowClassifier()
        
        timestamp = create_utc_datetime(2024, 1, 1, 13, 15)  # NEWS_WINDOW
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is True

    def test_is_high_probability_true_for_true_day_open(self):
        """is_high_probability_window should be True for TRUE_DAY_OPEN (weight=0.7)."""
        classifier = TimeWindowClassifier()
        
        timestamp = create_utc_datetime(2024, 1, 1, 5, 0)  # TRUE_DAY_OPEN
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is True

    def test_is_high_probability_false_for_low_weight_windows(self):
        """is_high_probability_window should be False for windows with weight < 0.7."""
        classifier = TimeWindowClassifier()
        
        # LONDON_CLOSE (weight=0.5)
        timestamp = create_utc_datetime(2024, 1, 1, 16, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is False
        
        # ASIAN_RANGE (weight=0.3)
        timestamp = create_utc_datetime(2024, 1, 2, 1, 0)
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is False
        
        # OFF_HOURS (weight=0.1)
        timestamp = create_utc_datetime(2024, 1, 1, 17, 0)  # 12:00 NY
        features = classifier.classify(timestamp, "EURUSD")
        assert features.is_high_probability_window is False


# ---------------------------------------------------------------------------
# Price Position Tests
# ---------------------------------------------------------------------------

class TestPricePosition:
    """Test price_vs_daily_open, price_vs_weekly_open, price_vs_true_day_open."""

    def test_price_above_daily_open(self):
        """price_vs_daily_open should return ABOVE when current_price > daily_open."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        
        features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.5050,
            daily_open=1.5000,
        )
        assert features.price_vs_daily_open == "ABOVE"

    def test_price_below_daily_open(self):
        """price_vs_daily_open should return BELOW when current_price < daily_open."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        
        features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.4950,
            daily_open=1.5000,
        )
        assert features.price_vs_daily_open == "BELOW"

    def test_price_at_daily_open(self):
        """price_vs_daily_open should return AT when current_price == daily_open."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        
        features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.5000,
            daily_open=1.5000,
        )
        assert features.price_vs_daily_open == "AT"

    def test_price_above_weekly_open(self):
        """price_vs_weekly_open should return ABOVE when current_price > weekly_open."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        
        features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.5050,
            weekly_open=1.5000,
        )
        assert features.price_vs_weekly_open == "ABOVE"

    def test_price_below_weekly_open(self):
        """price_vs_weekly_open should return BELOW when current_price < weekly_open."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        
        features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.4950,
            weekly_open=1.5000,
        )
        assert features.price_vs_weekly_open == "BELOW"

    def test_price_at_weekly_open(self):
        """price_vs_weekly_open should return AT when current_price == weekly_open."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        
        features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.5000,
            weekly_open=1.5000,
        )
        assert features.price_vs_weekly_open == "AT"

    def test_price_above_true_day_open(self):
        """price_vs_true_day_open should return ABOVE when current_price > true_day_open."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        
        features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.5050,
            true_day_open=1.5000,
        )
        assert features.price_vs_true_day_open == "ABOVE"

    def test_price_below_true_day_open(self):
        """price_vs_true_day_open should return BELOW when current_price < true_day_open."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        
        features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.4950,
            true_day_open=1.5000,
        )
        assert features.price_vs_true_day_open == "BELOW"

    def test_price_at_true_day_open(self):
        """price_vs_true_day_open should return AT when current_price == true_day_open."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)
        
        features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.5000,
            true_day_open=1.5000,
        )
        assert features.price_vs_true_day_open == "AT"


# ---------------------------------------------------------------------------
# Narrative Context Tests
# ---------------------------------------------------------------------------

class TestNarrativeContext:
    """Test get_narrative_context returns a non-empty string answering all 3 questions."""

    def test_narrative_context_returns_non_empty_string(self):
        """get_narrative_context should return a non-empty string."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)  # NY_KILLZONE
        
        time_features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.5050,
            daily_open=1.5000,
            weekly_open=1.4950,
            true_day_open=1.5020,
        )
        
        # Mock HTF and zone features
        htf_features = {
            "htf_open": 1.5000,
            "htf_high": 1.5100,
            "htf_low": 1.4900,
            "htf_open_bias": "BULLISH",
        }
        
        zone_features = {
            "swing_high": 1.5080,
            "swing_low": 1.4920,
            "fvg_present": True,
        }
        
        context = get_narrative_context(time_features, htf_features, zone_features)
        
        assert isinstance(context, str)
        assert len(context) > 0

    def test_narrative_context_answers_three_questions(self):
        """get_narrative_context should answer all 3 questions."""
        classifier = TimeWindowClassifier()
        timestamp = create_utc_datetime(2024, 1, 1, 12, 0)  # NY_KILLZONE
        
        time_features = classifier.classify(
            timestamp, "EURUSD",
            current_price=1.5050,
            daily_open=1.5000,
            weekly_open=1.4950,
            true_day_open=1.5020,
        )
        
        htf_features = {
            "htf_open": 1.5000,
            "htf_high": 1.5100,
            "htf_low": 1.4900,
            "htf_open_bias": "BULLISH",
        }
        
        zone_features = {
            "swing_high": 1.5080,
            "swing_low": 1.4920,
            "fvg_present": True,
        }
        
        context = get_narrative_context(time_features, htf_features, zone_features)
        
        # Check that context mentions key concepts from each question
        # Question 1: Where has price come from?
        assert any(keyword in context.lower() for keyword in ["htf", "previous", "range", "swept"])
        
        # Question 2: Where is it now?
        assert any(keyword in context.lower() for keyword in ["killzone", "phase", "open", "bias"])
        
        # Question 3: Where is it likely to go?
        assert any(keyword in context.lower() for keyword in ["liquidity", "imbalance", "target", "high", "low"])

