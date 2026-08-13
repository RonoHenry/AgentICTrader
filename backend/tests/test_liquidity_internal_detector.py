"""Tests for liquidity_engine.detectors.internal.PDArrayDetector."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings, strategies as st

from liquidity_engine.detectors.internal import PDArrayDetector
from liquidity_engine.models import (
    BiasDirection,
    Candle,
    PDArrayType,
    StructureEvent,
    StructureEventType,
    SwingTier,
    Timeframe,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def mk(open_, high, low, close, n, tf=Timeframe.M5):
    return Candle(
        timestamp=ts(n), open=open_, high=high, low=low, close=close, timeframe=tf, instrument="EURUSD"
    )


def make_event(direction, confirmed_at_n, tf=Timeframe.M5):
    return StructureEvent(
        event_type=StructureEventType.BOS,
        tier=SwingTier.SHORT_TERM,
        timeframe=tf,
        direction=direction,
        broken_swing_id="seed",
        confirmed_at=ts(confirmed_at_n),
    )


class TestFVG:
    def _bullish_gap_candles(self):
        return [
            mk(0.98, 1.00, 0.97, 0.99, 0),
            mk(0.99, 1.04, 0.99, 1.03, 1),
            mk(1.03, 1.10, 1.05, 1.08, 2),  # low 1.05 > candle0.high 1.00
        ]

    def _bearish_gap_candles(self):
        return [
            mk(0.97, 1.00, 0.95, 0.96, 0),
            mk(0.96, 0.97, 0.90, 0.91, 1),
            mk(0.91, 0.92, 0.85, 0.87, 2),  # high 0.92 < candle0.low 0.95
        ]

    def test_bullish_fvg_detected(self):
        arrays = PDArrayDetector()._detect_fvg(self._bullish_gap_candles(), Timeframe.M5)
        fvgs = [a for a in arrays if a.array_type == PDArrayType.FVG]
        assert len(fvgs) == 1
        assert fvgs[0].direction == BiasDirection.BULLISH
        assert fvgs[0].low == 0.97
        assert fvgs[0].high == 1.10

    def test_bearish_fvg_detected(self):
        arrays = PDArrayDetector()._detect_fvg(self._bearish_gap_candles(), Timeframe.M5)
        fvgs = [a for a in arrays if a.array_type == PDArrayType.FVG]
        assert len(fvgs) == 1
        assert fvgs[0].direction == BiasDirection.BEARISH
        assert fvgs[0].high == 1.00
        assert fvgs[0].low == 0.85

    def test_fvg_high_gt_low(self):
        for candles in (self._bullish_gap_candles(), self._bearish_gap_candles()):
            for array in PDArrayDetector()._detect_fvg(candles, Timeframe.M5):
                assert array.high > array.low

    def test_fvg_filled_when_price_fills_gap(self):
        candles = self._bullish_gap_candles() + [mk(1.05, 1.06, 0.95, 0.96, 3)]
        detector = PDArrayDetector()
        fvgs = detector._detect_fvg(candles, Timeframe.M5)
        fvg = fvgs[0]
        assert fvg.is_filled is False
        detector._mark_fvg_filled(fvg, candles)
        assert fvg.is_filled is True
        assert fvg.filled_at == ts(3)


class TestOrderBlocks:
    def _baseline(self):
        return [mk(1.00, 1.01, 0.99, 1.00, n) for n in range(5)]

    def test_bearish_ob_detected(self):
        candles = self._baseline() + [
            mk(1.00, 1.03, 1.00, 1.03, 5),  # up-close candle -> becomes the OB
            mk(1.03, 1.03, 0.90, 0.91, 6),  # large bearish expansion
        ]
        arrays = PDArrayDetector()._detect_order_blocks(candles, Timeframe.M5)
        obs = [a for a in arrays if a.array_type == PDArrayType.OB]
        assert len(obs) == 1
        assert obs[0].direction == BiasDirection.BEARISH
        assert obs[0].high == 1.03
        assert obs[0].low == 1.00

    def test_bullish_ob_detected(self):
        candles = self._baseline() + [
            mk(1.00, 1.00, 0.97, 0.97, 5),  # down-close candle -> becomes the OB
            mk(0.97, 1.15, 0.97, 1.14, 6),  # large bullish expansion
        ]
        arrays = PDArrayDetector()._detect_order_blocks(candles, Timeframe.M5)
        obs = [a for a in arrays if a.array_type == PDArrayType.OB]
        assert len(obs) == 1
        assert obs[0].direction == BiasDirection.BULLISH
        assert obs[0].high == 1.00
        assert obs[0].low == 0.97

    def test_ob_high_gt_low(self):
        candles = self._baseline() + [
            mk(1.00, 1.03, 1.00, 1.03, 5),
            mk(1.03, 1.03, 0.90, 0.91, 6),
        ]
        for array in PDArrayDetector()._detect_order_blocks(candles, Timeframe.M5):
            assert array.high > array.low


class TestBreakerBlocks:
    def _bearish_ob_and_violation(self):
        candles = [mk(1.00, 1.01, 0.99, 1.00, n) for n in range(5)] + [
            mk(1.00, 1.03, 1.00, 1.03, 5),  # up-close OB candle
            mk(1.03, 1.03, 0.90, 0.91, 6),  # bearish expansion
            mk(0.95, 1.10, 0.95, 1.08, 7),  # close 1.08 > 1.03 -> violates the OB
        ]
        return candles

    def test_breaker_block_from_violated_ob(self):
        candles = self._bearish_ob_and_violation()
        detector = PDArrayDetector()
        obs = detector._detect_order_blocks(candles, Timeframe.M5)
        breakers = detector._detect_breaker_blocks(candles, obs, [])
        assert len(breakers) == 1
        breaker = breakers[0]
        assert breaker.array_type == PDArrayType.BREAKER
        assert breaker.direction == BiasDirection.BULLISH
        assert breaker.source_ob_id == obs[0].array_id
        assert breaker.formed_at == ts(7)

    def test_breaker_structure_confirmed_true_after_opposing_structure_event(self):
        candles = self._bearish_ob_and_violation()
        detector = PDArrayDetector()
        obs = detector._detect_order_blocks(candles, Timeframe.M5)
        events = [make_event(BiasDirection.BULLISH, 8)]
        breakers = detector._detect_breaker_blocks(candles, obs, events)
        assert breakers[0].structure_confirmed is True

    def test_breaker_structure_confirmed_false_without_structure_event(self):
        candles = self._bearish_ob_and_violation()
        detector = PDArrayDetector()
        obs = detector._detect_order_blocks(candles, Timeframe.M5)
        breakers = detector._detect_breaker_blocks(candles, obs, [])
        assert breakers[0].structure_confirmed is False

    def test_breaker_classification_unaffected_by_structure_confirmed(self):
        candles = self._bearish_ob_and_violation()
        detector = PDArrayDetector()
        obs = detector._detect_order_blocks(candles, Timeframe.M5)
        confirmed = detector._detect_breaker_blocks(candles, obs, [make_event(BiasDirection.BULLISH, 8)])
        unconfirmed = detector._detect_breaker_blocks(candles, obs, [])
        assert len(confirmed) == len(unconfirmed) == 1
        assert confirmed[0].high == unconfirmed[0].high
        assert confirmed[0].low == unconfirmed[0].low
        assert confirmed[0].source_ob_id == unconfirmed[0].source_ob_id
        assert confirmed[0].direction == unconfirmed[0].direction


class TestIFVGAndBPR:
    def test_ifvg_from_filled_fvg(self):
        candles = [
            mk(0.98, 1.00, 0.97, 0.99, 0),
            mk(0.99, 1.04, 0.99, 1.03, 1),
            mk(1.03, 1.10, 1.05, 1.08, 2),
            mk(1.05, 1.06, 0.95, 0.96, 3),  # fills the bullish FVG
        ]
        detector = PDArrayDetector()
        fvgs = detector._detect_fvg(candles, Timeframe.M5)
        for fvg in fvgs:
            detector._mark_fvg_filled(fvg, candles)
        ifvgs = detector._detect_ifvg(candles, fvgs)
        assert len(ifvgs) == 1
        assert ifvgs[0].array_type == PDArrayType.IFVG
        assert ifvgs[0].direction == BiasDirection.BEARISH

    def test_bpr_from_overlapping_fvgs(self):
        detector = PDArrayDetector()
        bull_fvg = detector._make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, Timeframe.M5, 1.10, 1.00, ts(0))
        bear_fvg = detector._make_pdarray(PDArrayType.FVG, BiasDirection.BEARISH, Timeframe.M5, 1.08, 0.95, ts(1))
        bprs = detector._detect_bpr([bull_fvg, bear_fvg])
        assert len(bprs) == 1
        bpr = bprs[0]
        assert bpr.array_type == PDArrayType.BPR
        assert bpr.high == 1.08
        assert bpr.low == 1.00
        assert bpr.bpr_bullish_fvg_id == bull_fvg.array_id
        assert bpr.bpr_bearish_fvg_id == bear_fvg.array_id


class TestCISDLevel:
    def test_cisd_level_is_first_candle_open(self):
        candles = [
            mk(1.00, 1.02, 0.99, 1.01, 0),
            mk(1.01, 1.04, 1.00, 1.03, 1),
            mk(1.03, 1.06, 1.02, 1.05, 2),
            mk(1.05, 1.05, 0.95, 0.98, 3),  # closes below first candle's open (1.00)
        ]
        arrays = PDArrayDetector()._detect_cisd_levels(candles, Timeframe.M5)
        cisd_levels = [a for a in arrays if a.array_type == PDArrayType.CISD_LEVEL]
        assert len(cisd_levels) == 1
        assert cisd_levels[0].cisd_sequence_open == 1.00
        assert cisd_levels[0].direction == BiasDirection.BEARISH


class TestGeneralInvariants:
    def _rich_candles(self):
        return [mk(1.00, 1.01, 0.99, 1.00, n) for n in range(5)] + [
            mk(1.00, 1.03, 1.00, 1.03, 5),
            mk(1.03, 1.03, 0.90, 0.91, 6),
            mk(0.95, 1.10, 0.95, 1.08, 7),
            mk(1.07, 1.20, 1.06, 1.18, 8),
        ]

    def test_pdarray_timeframe_populated(self):
        candles = self._rich_candles()
        arrays = PDArrayDetector().detect({Timeframe.M5: candles}, {})
        assert arrays
        for array in arrays:
            assert array.timeframe == Timeframe.M5

    def test_strength_score_in_range(self):
        candles = self._rich_candles()
        arrays = PDArrayDetector().detect({Timeframe.M5: candles}, {})
        assert arrays
        for array in arrays:
            assert 0.0 <= array.strength_score <= 1.0


@st.composite
def _valid_candle_seq(draw):
    n = draw(st.integers(min_value=5, max_value=15))
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
    @given(candles=_valid_candle_seq())
    def test_property_all_pdarray_high_gt_low(self, candles):
        """Property 6/7/8: every PDArray of any type satisfies high > low."""
        arrays = PDArrayDetector().detect({Timeframe.M5: candles}, {})
        for array in arrays:
            assert array.high > array.low

    @settings(max_examples=100)
    @given(candles=_valid_candle_seq())
    def test_property_pdarray_strength_scores_in_range(self, candles):
        """Property 19/21: every PDArray has strength_score in [0.0, 1.0]."""
        arrays = PDArrayDetector().detect({Timeframe.M5: candles}, {})
        for array in arrays:
            assert 0.0 <= array.strength_score <= 1.0

    @settings(max_examples=100)
    @given(
        events=st.lists(
            st.builds(
                make_event,
                direction=st.sampled_from([BiasDirection.BULLISH, BiasDirection.BEARISH]),
                confirmed_at_n=st.integers(min_value=-5, max_value=15),
            ),
            max_size=5,
        )
    )
    def test_property_structure_confirmed_breaker_requires_event(self, events):
        """Property 28: structure_confirmed=True implies a qualifying StructureEvent exists."""
        candles = [mk(1.00, 1.01, 0.99, 1.00, n) for n in range(5)] + [
            mk(1.00, 1.03, 1.00, 1.03, 5),
            mk(1.03, 1.03, 0.90, 0.91, 6),
            mk(0.95, 1.10, 0.95, 1.08, 7),  # violation at ts(7)
        ]
        detector = PDArrayDetector()
        obs = detector._detect_order_blocks(candles, Timeframe.M5)
        breakers = detector._detect_breaker_blocks(candles, obs, events)
        for breaker in breakers:
            if breaker.structure_confirmed:
                assert any(
                    e.direction == breaker.direction and e.confirmed_at >= ts(7) for e in events
                )
