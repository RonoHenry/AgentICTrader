"""Tests for liquidity_engine.projections.standard_deviation.StandardDeviationCalculator."""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from liquidity_engine.models import BiasDirection
from liquidity_engine.projections.standard_deviation import (
    DEFAULT_LEVELS,
    StandardDeviationCalculator,
)


class TestAnchorAssignment:
    def test_bullish_anchors_high_to_low(self):
        # Same convention as OTECalculator: bullish measures high->low.
        projection = StandardDeviationCalculator().project(120.0, 80.0, BiasDirection.BULLISH)
        assert projection.anchor_0 == 120.0
        assert projection.anchor_1 == 80.0

    def test_bearish_anchors_low_to_high(self):
        projection = StandardDeviationCalculator().project(120.0, 80.0, BiasDirection.BEARISH)
        assert projection.anchor_0 == 80.0
        assert projection.anchor_1 == 120.0


class TestTargetLevels:
    def test_bullish_targets_project_above_anchor_0(self):
        projection = StandardDeviationCalculator().project(120.0, 80.0, BiasDirection.BULLISH)
        leg_range = 120.0 - 80.0
        assert projection.targets[1.0] == pytest.approx(120.0 + leg_range)
        assert projection.targets[2.5] == pytest.approx(120.0 + 2.5 * leg_range)

    def test_bearish_targets_project_below_anchor_0(self):
        projection = StandardDeviationCalculator().project(120.0, 80.0, BiasDirection.BEARISH)
        leg_range = 120.0 - 80.0
        assert projection.targets[1.0] == pytest.approx(80.0 - leg_range)
        assert projection.targets[2.5] == pytest.approx(80.0 - 2.5 * leg_range)

    def test_default_levels_all_present(self):
        projection = StandardDeviationCalculator().project(120.0, 80.0, BiasDirection.BULLISH)
        assert set(projection.targets.keys()) == set(DEFAULT_LEVELS)

    def test_custom_levels_respected(self):
        projection = StandardDeviationCalculator().project(
            120.0, 80.0, BiasDirection.BULLISH, levels=[1.0, 3.0]
        )
        assert set(projection.targets.keys()) == {1.0, 3.0}


@st.composite
def _valid_swing_pair(draw):
    swing_low = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    extra = draw(st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False))
    return swing_low + extra, swing_low  # swing_high, swing_low


class TestPropertyBasedTests:
    @settings(max_examples=100)
    @given(pair=_valid_swing_pair(), direction=st.sampled_from([BiasDirection.BULLISH, BiasDirection.BEARISH]))
    def test_property_targets_monotonically_extend_in_continuation_direction(self, pair, direction):
        """Higher SD levels always project further from anchor_0 than lower ones, in the
        direction away from anchor_1 (up for bullish, down for bearish)."""
        swing_high, swing_low = pair
        projection = StandardDeviationCalculator().project(swing_high, swing_low, direction)
        sorted_levels = sorted(projection.targets)
        distances = [abs(projection.targets[level] - projection.anchor_0) for level in sorted_levels]
        assert distances == sorted(distances)

    @settings(max_examples=100)
    @given(pair=_valid_swing_pair(), direction=st.sampled_from([BiasDirection.BULLISH, BiasDirection.BEARISH]))
    def test_property_targets_extend_away_from_anchor_1(self, pair, direction):
        """Every target sits on the opposite side of anchor_0 from anchor_1."""
        swing_high, swing_low = pair
        projection = StandardDeviationCalculator().project(swing_high, swing_low, direction)
        leg_sign = 1 if projection.anchor_0 > projection.anchor_1 else -1
        for price in projection.targets.values():
            assert (price - projection.anchor_0) * leg_sign > 0
