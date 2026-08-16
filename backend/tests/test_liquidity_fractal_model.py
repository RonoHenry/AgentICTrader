"""Tests for pd_array_engine.fractal.candle_model.FractalModelTracker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, strategies as st

from pd_array_engine.fractal.candle_model import FractalModelTracker
from pd_array_engine.models import Candle, ClosureType, Timeframe

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def mk(open_, high, low, close, n, tf=Timeframe.M5):
    return Candle(
        timestamp=ts(n), open=open_, high=high, low=low, close=close, timeframe=tf, instrument="EURUSD"
    )


def sequence():
    return [
        mk(1.00, 1.05, 0.98, 1.03, 0),  # step 1
        mk(1.03, 1.10, 1.02, 1.08, 1),  # close 1.08 > prior high 1.05 -> CONTINUATION
        mk(1.08, 1.09, 1.00, 1.02, 2),  # close 1.02 not > prior high 1.10 -> REVERSAL
    ]


class TestFractalModelTracking:
    def test_step_one_has_no_closure_type(self):
        result = FractalModelTracker().track(sequence(), key_level=1.0)
        assert result.steps[0].step_number == 1
        assert result.steps[0].closure_type is None

    def test_continuation_closure_when_extending_range(self):
        result = FractalModelTracker().track(sequence(), key_level=1.0)
        assert result.steps[1].closure_type == ClosureType.CONTINUATION

    def test_reversal_closure_when_closing_back_within_prior_range(self):
        result = FractalModelTracker().track(sequence(), key_level=1.0)
        assert result.steps[2].closure_type == ClosureType.REVERSAL

    def test_range_high_only_expands(self):
        candles = sequence() + [mk(1.02, 1.20, 0.95, 1.15, 3), mk(1.15, 1.16, 1.10, 1.12, 4)]
        tracker = FractalModelTracker()
        highs = [tracker.track(candles[:n], key_level=1.0).range_high for n in range(2, len(candles) + 1)]
        assert highs == sorted(highs)

    def test_range_low_only_contracts_downward(self):
        candles = sequence() + [mk(1.02, 1.20, 0.95, 1.15, 3), mk(1.15, 1.16, 1.10, 1.12, 4)]
        tracker = FractalModelTracker()
        lows = [tracker.track(candles[:n], key_level=1.0).range_low for n in range(2, len(candles) + 1)]
        assert lows == sorted(lows, reverse=True)

    def test_equilibrium_equals_range_midpoint(self):
        result = FractalModelTracker().track(sequence(), key_level=1.0)
        assert result.equilibrium == pytest.approx((result.range_high + result.range_low) / 2)

    def test_price_above_equilibrium_true(self):
        candles = sequence() + [mk(1.02, 1.30, 1.00, 1.28, 3)]  # closes well above the range
        result = FractalModelTracker().track(candles, key_level=1.0)
        assert result.price_above_equilibrium is True

    def test_price_above_equilibrium_false(self):
        result = FractalModelTracker().track(sequence(), key_level=1.0)
        assert result.price_above_equilibrium is False

    def test_key_level_immutable_across_steps(self):
        for n in range(2, len(sequence()) + 1):
            result = FractalModelTracker().track(sequence()[:n], key_level=42.5)
            assert result.key_level == 42.5

    def test_returns_none_on_insufficient_candles(self):
        assert FractalModelTracker().track([], key_level=1.0) is None
        assert FractalModelTracker().track([sequence()[0]], key_level=1.0) is None

    def test_track_is_deterministic(self):
        tracker = FractalModelTracker()
        result1 = tracker.track(sequence(), key_level=1.0)
        result2 = tracker.track(sequence(), key_level=1.0)
        assert result1.model_dump() == result2.model_dump()


@st.composite
def _valid_candle_seq(draw):
    n = draw(st.integers(min_value=2, max_value=12))
    base_price = draw(st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    candles = []
    price = base_price
    for i in range(n):
        delta = draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False))
        open_ = max(price + delta, 0.01)
        close = max(open_ + draw(st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False)), 0.01)
        high = max(open_, close) + abs(draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)))
        low = max(min(open_, close) - abs(draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))), 0.001)
        candles.append(mk(open_, high, low, close, i))
        price = close
    return candles


class TestPropertyBasedTests:
    @settings(max_examples=100)
    @given(candles=_valid_candle_seq(), key_level=st.floats(min_value=1.0, max_value=2000.0, allow_nan=False, allow_infinity=False))
    def test_property_fractal_model_range_and_equilibrium_correctness(self, candles, key_level):
        """Property 27: range_high non-decreasing, range_low non-increasing, equilibrium correct — as steps accumulate."""
        tracker = FractalModelTracker()
        prev_high, prev_low = None, None
        for n in range(2, len(candles) + 1):
            result = tracker.track(candles[:n], key_level)
            assert result is not None
            if prev_high is not None:
                assert result.range_high >= prev_high
                assert result.range_low <= prev_low
            assert result.equilibrium == pytest.approx((result.range_high + result.range_low) / 2)
            prev_high, prev_low = result.range_high, result.range_low
