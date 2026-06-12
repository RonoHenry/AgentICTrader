"""
Test suite for OTE (Optimal Trade Entry) Fibonacci extractor.

Validates TTrades OTE specification:
  - Fibonacci levels: 0.5, 0.62, 0.705, 0.79
  - OTE zone: 0.62–0.79 retracement
  - Golden pocket: 0.705 level
  - LONG: retracement from swing_high downward
  - SHORT: retracement from swing_low upward

Tests follow the same pattern as test_zone_features.py and test_htf_projections.py.

**Validates: OTE feature extractor integration with FeaturePipeline**
"""

import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from ml.features.ote_extractor import OTEExtractor, OTEFeatures  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SWING_HIGH = 1.5100
SWING_LOW = 1.4900
SWING_RANGE = SWING_HIGH - SWING_LOW  # 0.0200


class TestOTEFeaturesDataclass:
    """Test OTEFeatures dataclass structure."""

    def test_ote_features_has_all_required_fields(self):
        """OTEFeatures must expose all expected fields."""
        f = OTEFeatures(
            ote_in_zone=True,
            ote_level_705=1.4959,
            ote_level_62=1.4976,
            ote_level_79=1.4942,
            ote_distance_pct=0.0,
            ote_valid=True,
        )
        assert hasattr(f, "ote_in_zone")
        assert hasattr(f, "ote_level_705")
        assert hasattr(f, "ote_level_62")
        assert hasattr(f, "ote_level_79")
        assert hasattr(f, "ote_distance_pct")
        assert hasattr(f, "ote_valid")


# ---------------------------------------------------------------------------
# LONG direction tests
# ---------------------------------------------------------------------------

class TestOTELongDirection:
    """Tests for LONG (bullish) OTE calculations."""

    def setup_method(self):
        self.extractor = OTEExtractor()

    def test_ote_level_705_computed_correctly_for_long(self):
        """0.705 level = swing_high - 0.705 * swing_range."""
        expected = SWING_HIGH - 0.705 * SWING_RANGE  # 1.5100 - 0.0141 = 1.4959
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, 1.4959, "LONG")
        assert features.ote_level_705 == pytest.approx(expected, abs=1e-6)

    def test_ote_level_62_computed_correctly_for_long(self):
        """0.62 level = swing_high - 0.62 * swing_range."""
        expected = SWING_HIGH - 0.62 * SWING_RANGE   # 1.5100 - 0.0124 = 1.4976
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, 1.4976, "LONG")
        assert features.ote_level_62 == pytest.approx(expected, abs=1e-6)

    def test_ote_level_79_computed_correctly_for_long(self):
        """0.79 level = swing_high - 0.79 * swing_range."""
        expected = SWING_HIGH - 0.79 * SWING_RANGE   # 1.5100 - 0.0158 = 1.4942
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, 1.4942, "LONG")
        assert features.ote_level_79 == pytest.approx(expected, abs=1e-6)

    def test_in_zone_true_when_price_between_62_and_79_long(self):
        """ote_in_zone must be True when price is inside the 0.62–0.79 zone."""
        level_62 = SWING_HIGH - 0.62 * SWING_RANGE  # 1.4976
        level_79 = SWING_HIGH - 0.79 * SWING_RANGE  # 1.4942
        midpoint = (level_62 + level_79) / 2         # ~1.4959

        features = self.extractor.extract(SWING_HIGH, SWING_LOW, midpoint, "LONG")
        assert features.ote_in_zone is True

    def test_in_zone_false_when_price_above_62_long(self):
        """ote_in_zone must be False when price has not yet retraced to 0.62."""
        price_above_62 = SWING_HIGH - 0.50 * SWING_RANGE  # only 50% retrace — not in zone
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, price_above_62, "LONG")
        assert features.ote_in_zone is False

    def test_in_zone_false_when_price_below_79_long(self):
        """ote_in_zone must be False when price has overshot past 0.79."""
        price_below_79 = SWING_HIGH - 0.90 * SWING_RANGE  # 90% retrace — beyond zone
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, price_below_79, "LONG")
        assert features.ote_in_zone is False

    def test_at_exact_62_boundary_is_in_zone_long(self):
        """Price exactly at 0.62 level must be considered in zone (inclusive boundary)."""
        level_62 = SWING_HIGH - 0.62 * SWING_RANGE
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, level_62, "LONG")
        assert features.ote_in_zone is True

    def test_at_exact_79_boundary_is_in_zone_long(self):
        """Price exactly at 0.79 level must be considered in zone (inclusive boundary)."""
        level_79 = SWING_HIGH - 0.79 * SWING_RANGE
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, level_79, "LONG")
        assert features.ote_in_zone is True

    def test_ote_valid_true_for_valid_inputs_long(self):
        """ote_valid must be True when swing_high > swing_low."""
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, 1.4959, "LONG")
        assert features.ote_valid is True

    def test_distance_pct_zero_when_at_705_level_long(self):
        """ote_distance_pct should be ~0 when current price equals the 0.705 level."""
        level_705 = SWING_HIGH - 0.705 * SWING_RANGE
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, level_705, "LONG")
        assert features.ote_distance_pct == pytest.approx(0.0, abs=1e-4)

    def test_distance_pct_positive_when_above_705_long(self):
        """ote_distance_pct should be positive when price is above 0.705 (not yet retraced)."""
        above_705 = SWING_HIGH - 0.62 * SWING_RANGE  # 0.62 level > 0.705 level for LONG
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, above_705, "LONG")
        assert features.ote_distance_pct > 0.0


# ---------------------------------------------------------------------------
# SHORT direction tests
# ---------------------------------------------------------------------------

class TestOTEShortDirection:
    """Tests for SHORT (bearish) OTE calculations."""

    def setup_method(self):
        self.extractor = OTEExtractor()

    def test_ote_level_705_computed_correctly_for_short(self):
        """0.705 level = swing_low + 0.705 * swing_range."""
        expected = SWING_LOW + 0.705 * SWING_RANGE   # 1.4900 + 0.0141 = 1.5041
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, 1.5041, "SHORT")
        assert features.ote_level_705 == pytest.approx(expected, abs=1e-6)

    def test_ote_level_62_computed_correctly_for_short(self):
        """0.62 level = swing_low + 0.62 * swing_range."""
        expected = SWING_LOW + 0.62 * SWING_RANGE    # 1.4900 + 0.0124 = 1.5024
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, 1.5024, "SHORT")
        assert features.ote_level_62 == pytest.approx(expected, abs=1e-6)

    def test_in_zone_true_when_price_between_62_and_79_short(self):
        """ote_in_zone must be True when price retraced into 0.62–0.79 zone (SHORT)."""
        level_62 = SWING_LOW + 0.62 * SWING_RANGE   # 1.5024
        level_79 = SWING_LOW + 0.79 * SWING_RANGE   # 1.5058
        midpoint = (level_62 + level_79) / 2          # ~1.5041

        features = self.extractor.extract(SWING_HIGH, SWING_LOW, midpoint, "SHORT")
        assert features.ote_in_zone is True

    def test_in_zone_false_when_price_below_62_short(self):
        """ote_in_zone must be False when price has not yet retraced to 0.62 (SHORT)."""
        price_below_62 = SWING_LOW + 0.50 * SWING_RANGE  # 50% retrace — not in zone
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, price_below_62, "SHORT")
        assert features.ote_in_zone is False

    def test_in_zone_false_when_price_above_79_short(self):
        """ote_in_zone must be False when price overshot past 0.79 (SHORT)."""
        price_above_79 = SWING_LOW + 0.90 * SWING_RANGE  # 90% retrace — beyond zone
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, price_above_79, "SHORT")
        assert features.ote_in_zone is False


# ---------------------------------------------------------------------------
# Edge cases and degenerate inputs
# ---------------------------------------------------------------------------

class TestOTEEdgeCases:
    """Tests for edge cases and degenerate inputs."""

    def setup_method(self):
        self.extractor = OTEExtractor()

    def test_degenerate_swing_high_equals_low_returns_valid_false(self):
        """When swing_high == swing_low, ote_valid must be False."""
        features = self.extractor.extract(1.5000, 1.5000, 1.5000, "LONG")
        assert features.ote_valid is False
        assert features.ote_in_zone is False

    def test_degenerate_swing_range_zero_returns_current_price_as_levels(self):
        """When swing range is zero, all levels should equal current price."""
        price = 1.5000
        features = self.extractor.extract(1.5000, 1.5000, price, "LONG")
        assert features.ote_level_705 == price
        assert features.ote_level_62 == price
        assert features.ote_level_79 == price

    def test_swing_high_below_swing_low_returns_valid_false(self):
        """When swing_high < swing_low (invalid), ote_valid must be False."""
        features = self.extractor.extract(1.4900, 1.5100, 1.5000, "LONG")
        assert features.ote_valid is False

    def test_default_direction_long_works(self):
        """Calling extract without direction should default to LONG."""
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, 1.4959)
        assert features.ote_valid is True
        # LONG 0.705 level
        expected = SWING_HIGH - 0.705 * SWING_RANGE
        assert features.ote_level_705 == pytest.approx(expected, abs=1e-6)

    def test_price_at_swing_high_not_in_zone_long(self):
        """Price at swing high (0% retrace) should not be in OTE zone."""
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, SWING_HIGH, "LONG")
        assert features.ote_in_zone is False

    def test_price_at_swing_low_not_in_zone_long(self):
        """Price at swing low (100% retrace) should not be in OTE zone."""
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, SWING_LOW, "LONG")
        assert features.ote_in_zone is False

    def test_ote_distance_pct_range(self):
        """ote_distance_pct should be a finite float for valid inputs."""
        features = self.extractor.extract(SWING_HIGH, SWING_LOW, 1.4960, "LONG")
        assert isinstance(features.ote_distance_pct, float)
        assert abs(features.ote_distance_pct) < 1000.0  # sanity: not absurdly large
