"""Tests for liquidity_engine.ote.calculator.OTECalculator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, strategies as st

from liquidity_engine.models import BiasDirection, Candle, Timeframe
from liquidity_engine.ote.calculator import OTECalculator

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def mk(open_, high, low, close, n, tf=Timeframe.M5):
    return Candle(
        timestamp=ts(n), open=open_, high=high, low=low, close=close, timeframe=tf, instrument="EURUSD"
    )


class TestFibLevels:
    def test_fib_62_computed_correctly(self):
        zone = OTECalculator().calculate(100.0, 0.0, BiasDirection.BULLISH)
        assert zone.fib_62 == pytest.approx(100.0 - 0.62 * 100.0)

    def test_fib_705_computed_correctly(self):
        zone = OTECalculator().calculate(100.0, 0.0, BiasDirection.BULLISH)
        assert zone.fib_705 == pytest.approx(100.0 - 0.705 * 100.0)

    def test_fib_79_computed_correctly(self):
        zone = OTECalculator().calculate(100.0, 0.0, BiasDirection.BULLISH)
        assert zone.fib_79 == pytest.approx(100.0 - 0.79 * 100.0)

    def test_golden_level_equals_fib705(self):
        for direction in (BiasDirection.BULLISH, BiasDirection.BEARISH):
            zone = OTECalculator().calculate(100.0, 50.0, direction)
            assert zone.golden_level == zone.fib_705

    def test_ote_low_lt_ote_high_bullish(self):
        zone = OTECalculator().calculate(120.0, 80.0, BiasDirection.BULLISH)
        assert zone.ote_low < zone.ote_high

    def test_ote_low_lt_ote_high_bearish(self):
        zone = OTECalculator().calculate(120.0, 80.0, BiasDirection.BEARISH)
        assert zone.ote_low < zone.ote_high

    def test_bullish_ote_anchors_from_high_to_low(self):
        zone = OTECalculator().calculate(120.0, 80.0, BiasDirection.BULLISH)
        assert zone.ote_high == zone.fib_62
        assert zone.ote_low == zone.fib_79
        assert zone.fib_79 < zone.fib_62  # deeper retracement (79%) sits closer to the low

    def test_bearish_ote_anchors_from_low_to_high(self):
        zone = OTECalculator().calculate(120.0, 80.0, BiasDirection.BEARISH)
        assert zone.ote_low == zone.fib_62
        assert zone.ote_high == zone.fib_79
        assert zone.fib_62 < zone.fib_79  # deeper retracement (79%) sits closer to the high


class TestPriceInOTE:
    def test_price_in_ote_true(self):
        zone = OTECalculator().calculate(120.0, 80.0, BiasDirection.BULLISH)
        midpoint = (zone.ote_low + zone.ote_high) / 2
        assert OTECalculator().price_in_ote(midpoint, zone) is True

    def test_price_in_ote_false(self):
        zone = OTECalculator().calculate(120.0, 80.0, BiasDirection.BULLISH)
        assert OTECalculator().price_in_ote(zone.ote_high + 10.0, zone) is False

    def test_price_in_ote_at_boundary(self):
        zone = OTECalculator().calculate(120.0, 80.0, BiasDirection.BULLISH)
        assert OTECalculator().price_in_ote(zone.ote_low, zone) is True
        assert OTECalculator().price_in_ote(zone.ote_high, zone) is True


class TestDisplacementLeg:
    def test_find_displacement_leg_identifies_fvg_leg(self):
        candles = [
            mk(0.98, 1.00, 0.97, 0.99, 0),
            mk(0.99, 1.04, 0.99, 1.03, 1),
            mk(1.03, 1.10, 1.05, 1.08, 2),  # low 1.05 > candle0.high 1.00 -> bullish gap
        ]
        leg = OTECalculator().find_displacement_leg(candles, BiasDirection.BULLISH)
        assert leg is not None
        swing_high, swing_low = leg
        assert swing_high == 1.10
        assert swing_low == 0.97


@st.composite
def _valid_swing_pair(draw):
    swing_low = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    extra = draw(st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False))
    return swing_low + extra, swing_low  # swing_high, swing_low


class TestPropertyBasedTests:
    @settings(max_examples=100)
    @given(pair=_valid_swing_pair(), direction=st.sampled_from([BiasDirection.BULLISH, BiasDirection.BEARISH]))
    def test_property_ote_zone_structural_ordering(self, pair, direction):
        """Property 7/9: the three fib levels are strictly ordered, consistent with anchor direction.

        See module docstring in ote/calculator.py: since ote_low<ote_high must hold
        unconditionally (the load-bearing invariant), the fib_X ordering is
        necessarily direction-dependent rather than a single fixed "fib_62 <
        fib_705 < fib_79" for every zone.
        """
        swing_high, swing_low = pair
        zone = OTECalculator().calculate(swing_high, swing_low, direction)
        if direction == BiasDirection.BEARISH:
            assert zone.fib_62 < zone.fib_705 < zone.fib_79
        else:
            assert zone.fib_79 < zone.fib_705 < zone.fib_62

    @settings(max_examples=100)
    @given(pair=_valid_swing_pair(), direction=st.sampled_from([BiasDirection.BULLISH, BiasDirection.BEARISH]))
    def test_property_ote_low_lt_ote_high(self, pair, direction):
        """Property 8/10: ote_low < ote_high always, regardless of direction."""
        swing_high, swing_low = pair
        zone = OTECalculator().calculate(swing_high, swing_low, direction)
        assert zone.ote_low < zone.ote_high

    @settings(max_examples=100)
    @given(pair=_valid_swing_pair(), direction=st.sampled_from([BiasDirection.BULLISH, BiasDirection.BEARISH]))
    def test_property_golden_level_equals_fib705(self, pair, direction):
        """Property 9/11: golden_level always equals fib_705."""
        swing_high, swing_low = pair
        zone = OTECalculator().calculate(swing_high, swing_low, direction)
        assert zone.golden_level == zone.fib_705

    @settings(max_examples=100)
    @given(
        pair=_valid_swing_pair(),
        direction=st.sampled_from([BiasDirection.BULLISH, BiasDirection.BEARISH]),
        offset_pct=st.floats(min_value=-0.5, max_value=1.5, allow_nan=False, allow_infinity=False),
    )
    def test_property_price_in_ote_flag_correctness(self, pair, direction, offset_pct):
        """Property 10/12: price_in_ote is True iff ote_low <= price <= ote_high."""
        swing_high, swing_low = pair
        zone = OTECalculator().calculate(swing_high, swing_low, direction)
        price = zone.ote_low + offset_pct * (zone.ote_high - zone.ote_low)
        expected = zone.ote_low <= price <= zone.ote_high
        assert OTECalculator().price_in_ote(price, zone) == expected
