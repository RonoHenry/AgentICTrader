"""Tests for pd_array_engine.unicorn.detector.UnicornDetector."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, strategies as st

from pd_array_engine.models import BiasDirection, PDArray, PDArrayType, Timeframe
from pd_array_engine.unicorn.detector import UnicornDetector

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def make_array(array_type, direction, high, low, n, strength_score=0.6, tf=Timeframe.M5, array_id=None):
    return PDArray(
        array_id=array_id or f"{array_type.value}-{direction.value}-{n}",
        array_type=array_type,
        direction=direction,
        timeframe=tf,
        high=high,
        low=low,
        formed_at=ts(n),
        strength_score=strength_score,
    )


class TestUnicornDetection:
    def test_bullish_unicorn_detected(self):
        breaker = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 1.10, 1.00, 0)
        fvg = make_array(PDArrayType.FVG, BiasDirection.BULLISH, 1.05, 0.98, 1)
        result = UnicornDetector().detect([breaker, fvg])
        assert result is not None
        assert result.direction == BiasDirection.BULLISH
        assert result.breaker_array_id == breaker.array_id
        assert result.fvg_array_id == fvg.array_id

    def test_bearish_unicorn_detected(self):
        breaker = make_array(PDArrayType.BREAKER, BiasDirection.BEARISH, 1.10, 1.00, 0)
        fvg = make_array(PDArrayType.FVG, BiasDirection.BEARISH, 1.05, 0.98, 1)
        result = UnicornDetector().detect([breaker, fvg])
        assert result is not None
        assert result.direction == BiasDirection.BEARISH

    def test_unicorn_overlap_low_lt_overlap_high(self):
        breaker = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 1.10, 1.00, 0)
        fvg = make_array(PDArrayType.FVG, BiasDirection.BULLISH, 1.05, 0.98, 1)
        result = UnicornDetector().detect([breaker, fvg])
        assert result.overlap_low < result.overlap_high

    def test_overlap_high_is_min_of_highs(self):
        breaker = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 1.10, 1.00, 0)
        fvg = make_array(PDArrayType.FVG, BiasDirection.BULLISH, 1.05, 0.98, 1)
        result = UnicornDetector().detect([breaker, fvg])
        assert result.overlap_high == min(breaker.high, fvg.high)

    def test_overlap_low_is_max_of_lows(self):
        breaker = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 1.10, 1.00, 0)
        fvg = make_array(PDArrayType.FVG, BiasDirection.BULLISH, 1.05, 0.98, 1)
        result = UnicornDetector().detect([breaker, fvg])
        assert result.overlap_low == max(breaker.low, fvg.low)

    def test_no_unicorn_when_no_overlap(self):
        breaker = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 1.10, 1.00, 0)
        fvg = make_array(PDArrayType.FVG, BiasDirection.BULLISH, 2.05, 1.98, 1)  # far away
        result = UnicornDetector().detect([breaker, fvg])
        assert result is None

    def test_most_recent_unicorn_returned(self):
        breaker1 = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 1.10, 1.00, 0, array_id="b1")
        fvg1 = make_array(PDArrayType.FVG, BiasDirection.BULLISH, 1.05, 0.98, 1, array_id="f1")
        breaker2 = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 2.10, 2.00, 5, array_id="b2")
        fvg2 = make_array(PDArrayType.FVG, BiasDirection.BULLISH, 2.05, 1.98, 6, array_id="f2")
        result = UnicornDetector().detect([breaker1, fvg1, breaker2, fvg2])
        assert result.breaker_array_id == "b2"
        assert result.fvg_array_id == "f2"

    def test_unicorn_returns_none_on_empty_arrays(self):
        assert UnicornDetector().detect([]) is None

    def test_unicorn_strength_score_is_combined(self):
        breaker = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 1.10, 1.00, 0, strength_score=0.8)
        fvg = make_array(PDArrayType.FVG, BiasDirection.BULLISH, 1.05, 0.98, 1, strength_score=0.4)
        result = UnicornDetector().detect([breaker, fvg])
        assert result.strength_score == pytest.approx((0.8 + 0.4) / 2)

    def test_cross_direction_not_matched(self):
        breaker = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 1.10, 1.00, 0)
        fvg = make_array(PDArrayType.FVG, BiasDirection.BEARISH, 1.05, 0.98, 1)
        result = UnicornDetector().detect([breaker, fvg])
        assert result is None

    def test_near_touch_within_tolerance(self):
        breaker = make_array(PDArrayType.BREAKER, BiasDirection.BULLISH, 1.000, 0.995, 0)
        fvg = make_array(PDArrayType.FVG, BiasDirection.BULLISH, 1.0002, 1.0001, 1)  # just above breaker.high
        result = UnicornDetector().detect([breaker, fvg], overlap_tolerance_pct=0.001)
        assert result is not None
        assert result.overlap_low < result.overlap_high


@st.composite
def _array_pair(draw):
    direction = draw(st.sampled_from([BiasDirection.BULLISH, BiasDirection.BEARISH]))
    low = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    span = draw(st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False))
    high = low + span
    offset = draw(st.floats(min_value=-40.0, max_value=40.0, allow_nan=False, allow_infinity=False))
    low2 = max(low + offset, 0.001)
    span2 = draw(st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False))
    high2 = low2 + span2
    breaker = make_array(PDArrayType.BREAKER, direction, high, low, 0)
    fvg = make_array(PDArrayType.FVG, direction, high2, low2, 1)
    return breaker, fvg


class TestPropertyBasedTests:
    @settings(max_examples=100)
    @given(pair=_array_pair())
    def test_property_unicorn_overlap_well_formed(self, pair):
        """Property 13: any detected UnicornPattern satisfies overlap_low < overlap_high."""
        breaker, fvg = pair
        result = UnicornDetector().detect([breaker, fvg])
        if result is not None:
            assert result.overlap_low < result.overlap_high

    @settings(max_examples=50)
    @given(
        n=st.integers(min_value=2, max_value=5),
        direction=st.sampled_from([BiasDirection.BULLISH, BiasDirection.BEARISH]),
    )
    def test_property_unicorn_returns_most_recent(self, n, direction):
        """Property 14: with multiple qualifying pairs, the most recent formed_at wins."""
        arrays = []
        for i in range(n):
            base = 1.0 + i * 10.0
            breaker = make_array(PDArrayType.BREAKER, direction, base + 0.10, base, i * 2, array_id=f"b{i}")
            fvg = make_array(PDArrayType.FVG, direction, base + 0.05, base - 0.02, i * 2 + 1, array_id=f"f{i}")
            arrays += [breaker, fvg]
        result = UnicornDetector().detect(arrays)
        assert result is not None
        assert result.breaker_array_id == f"b{n - 1}"
        assert result.fvg_array_id == f"f{n - 1}"
