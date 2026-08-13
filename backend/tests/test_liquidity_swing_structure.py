"""Tests for liquidity_engine.detectors.structure.SwingStructureClassifier."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings, strategies as st

from liquidity_engine.detectors.structure import SwingStructureClassifier
from liquidity_engine.models import (
    BiasDirection,
    Candle,
    StructureEventType,
    SwingPoint,
    SwingTier,
    Timeframe,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def mk(open_, high, low, close, n, tf=Timeframe.M5):
    return Candle(
        timestamp=ts(n),
        open=open_,
        high=high,
        low=low,
        close=close,
        timeframe=tf,
        instrument="EURUSD",
    )


def swing(is_high, price, n, tier=SwingTier.SHORT_TERM):
    return SwingPoint(
        swing_id=f"seed-{'h' if is_high else 'l'}-{n}",
        tier=tier,
        is_high=is_high,
        price=price,
        formed_at=ts(n),
    )


class TestSeeding:
    def test_seeds_short_term_highs_from_swing_indices(self):
        candles = [
            mk(1.0, 1.00, 0.99, 1.00, 0),
            mk(1.0, 1.00, 0.99, 1.00, 1),
            mk(1.0, 1.10, 0.99, 1.00, 2),
            mk(1.0, 1.00, 0.99, 1.00, 3),
            mk(1.0, 1.00, 0.99, 1.00, 4),
        ]
        result = SwingStructureClassifier().classify({Timeframe.M5: candles})[Timeframe.M5]
        assert len(result.short_term_highs) == 1
        sth = result.short_term_highs[0]
        assert sth.tier == SwingTier.SHORT_TERM
        assert sth.is_high is True
        assert sth.price == 1.10

    def test_seeds_short_term_lows_from_swing_indices(self):
        candles = [
            mk(1.0, 1.15, 1.10, 1.0, 0),
            mk(1.0, 1.15, 1.05, 1.0, 1),
            mk(1.0, 1.15, 1.00, 1.0, 2),
            mk(1.0, 1.15, 1.05, 1.0, 3),
            mk(1.0, 1.15, 1.10, 1.0, 4),
        ]
        result = SwingStructureClassifier().classify({Timeframe.M5: candles})[Timeframe.M5]
        assert len(result.short_term_lows) == 1
        stl = result.short_term_lows[0]
        assert stl.tier == SwingTier.SHORT_TERM
        assert stl.is_high is False
        assert stl.price == 1.00

    def test_no_swings_on_flat_candles(self):
        candles = [mk(1.0, 1.0, 1.0, 1.0, n) for n in range(6)]
        result = SwingStructureClassifier().classify({Timeframe.M5: candles})[Timeframe.M5]
        assert result.short_term_highs == []
        assert result.short_term_lows == []
        assert result.events == []
        assert result.latest_event is None


class TestPromotion:
    def test_ith_promoted_when_adjacent_stl_broken(self):
        stl = swing(False, 0.95, 1)
        sth = swing(True, 1.10, 3)
        candles = [
            mk(1.0, 1.02, 0.90, 1.0, 0),
            mk(1.0, 1.02, 0.95, 1.0, 1),
            mk(1.0, 1.05, 0.97, 1.0, 2),
            mk(1.0, 1.10, 0.97, 1.0, 3),
            mk(1.0, 1.05, 0.97, 1.0, 4),
            mk(0.94, 0.96, 0.90, 0.90, 5),  # close 0.90 < 0.95 breaks the STL
        ]
        promoted = SwingStructureClassifier()._promote_tier([stl, sth], candles)
        assert len(promoted) == 1
        assert promoted[0].tier == SwingTier.INTERMEDIATE_TERM
        assert promoted[0].is_high is True
        assert promoted[0].price == sth.price
        # originals are never mutated by promotion
        assert sth.tier == SwingTier.SHORT_TERM
        assert stl.tier == SwingTier.SHORT_TERM

    def test_itl_promoted_when_adjacent_sth_broken(self):
        sth = swing(True, 1.10, 1)
        stl = swing(False, 0.90, 3)
        candles = [
            mk(1.0, 1.08, 0.95, 1.0, 0),
            mk(1.0, 1.10, 0.95, 1.0, 1),
            mk(1.0, 1.05, 0.92, 1.0, 2),
            mk(1.0, 1.05, 0.90, 1.0, 3),
            mk(1.0, 1.05, 0.95, 1.0, 4),
            mk(1.12, 1.16, 1.10, 1.15, 5),  # close 1.15 > 1.10 breaks the STH
        ]
        promoted = SwingStructureClassifier()._promote_tier([sth, stl], candles)
        assert len(promoted) == 1
        assert promoted[0].tier == SwingTier.INTERMEDIATE_TERM
        assert promoted[0].is_high is False
        assert promoted[0].price == stl.price
        assert stl.tier == SwingTier.SHORT_TERM
        assert sth.tier == SwingTier.SHORT_TERM

    def test_lth_promoted_when_adjacent_itl_broken(self):
        itl = swing(False, 0.95, 1, tier=SwingTier.INTERMEDIATE_TERM)
        ith = swing(True, 1.10, 3, tier=SwingTier.INTERMEDIATE_TERM)
        candles = [
            mk(1.0, 1.02, 0.90, 1.0, 0),
            mk(1.0, 1.02, 0.95, 1.0, 1),
            mk(1.0, 1.05, 0.97, 1.0, 2),
            mk(1.0, 1.10, 0.97, 1.0, 3),
            mk(1.0, 1.05, 0.97, 1.0, 4),
            mk(0.94, 0.96, 0.90, 0.90, 5),  # close 0.90 < 0.95 breaks the ITL
        ]
        promoted = SwingStructureClassifier()._promote_tier([itl, ith], candles)
        assert len(promoted) == 1
        assert promoted[0].tier == SwingTier.LONG_TERM
        assert promoted[0].is_high is True
        assert promoted[0].price == ith.price
        assert itl.tier == SwingTier.INTERMEDIATE_TERM
        assert ith.tier == SwingTier.INTERMEDIATE_TERM

    def test_ltl_promoted_when_adjacent_ith_broken(self):
        ith = swing(True, 1.10, 1, tier=SwingTier.INTERMEDIATE_TERM)
        itl = swing(False, 0.90, 3, tier=SwingTier.INTERMEDIATE_TERM)
        candles = [
            mk(1.0, 1.08, 0.95, 1.0, 0),
            mk(1.0, 1.10, 0.95, 1.0, 1),
            mk(1.0, 1.05, 0.92, 1.0, 2),
            mk(1.0, 1.05, 0.90, 1.0, 3),
            mk(1.0, 1.05, 0.95, 1.0, 4),
            mk(1.12, 1.16, 1.10, 1.15, 5),  # close 1.15 > 1.10 breaks the ITH
        ]
        promoted = SwingStructureClassifier()._promote_tier([ith, itl], candles)
        assert len(promoted) == 1
        assert promoted[0].tier == SwingTier.LONG_TERM
        assert promoted[0].is_high is False
        assert promoted[0].price == itl.price
        assert itl.tier == SwingTier.INTERMEDIATE_TERM
        assert ith.tier == SwingTier.INTERMEDIATE_TERM

    def test_promoted_swing_has_derived_from_swing_id(self):
        stl = swing(False, 0.95, 1)
        sth = swing(True, 1.10, 3)
        candles = [
            mk(1.0, 1.02, 0.90, 1.0, 0),
            mk(1.0, 1.02, 0.95, 1.0, 1),
            mk(1.0, 1.05, 0.97, 1.0, 2),
            mk(1.0, 1.10, 0.97, 1.0, 3),
            mk(1.0, 1.05, 0.97, 1.0, 4),
            mk(0.94, 0.96, 0.90, 0.90, 5),
        ]
        promoted = SwingStructureClassifier()._promote_tier([stl, sth], candles)
        assert promoted[0].derived_from_swing_id == stl.swing_id

    def test_no_promotion_without_broken_lower_tier(self):
        stl = swing(False, 0.95, 1)
        sth = swing(True, 1.10, 3)
        candles = [
            mk(1.0, 1.02, 0.90, 1.0, 0),
            mk(1.0, 1.02, 0.95, 1.0, 1),
            mk(1.0, 1.05, 0.97, 1.0, 2),
            mk(1.0, 1.10, 0.97, 1.0, 3),
            mk(1.0, 1.05, 0.97, 1.0, 4),
            mk(1.0, 1.02, 0.96, 1.0, 5),  # never closes below 0.95 or above 1.10
        ]
        promoted = SwingStructureClassifier()._promote_tier([stl, sth], candles)
        assert promoted == []
        assert stl.tier == SwingTier.SHORT_TERM
        assert sth.tier == SwingTier.SHORT_TERM


class TestStructureEvents:
    def test_bos_emitted_on_same_direction_break(self):
        sth1 = swing(True, 1.05, 1)
        sth2 = swing(True, 1.15, 3)
        candles = [
            mk(1.0, 1.05, 0.99, 1.0, 0),
            mk(1.0, 1.05, 0.99, 1.0, 1),
            mk(1.0, 1.06, 0.99, 1.06, 2),  # close 1.06 > 1.05 breaks sth1 -> BOS
            mk(1.0, 1.15, 0.99, 1.0, 3),
            mk(1.0, 1.10, 0.99, 1.0, 4),
            mk(1.0, 1.20, 0.99, 1.20, 5),  # close 1.20 > 1.15 breaks sth2 -> BOS (same trend)
        ]
        events = SwingStructureClassifier()._classify_structure_events(
            [sth1, sth2], candles, Timeframe.M5
        )
        assert len(events) == 2
        assert all(e.event_type == StructureEventType.BOS for e in events)
        assert all(e.direction == BiasDirection.BULLISH for e in events)

    def test_choch_emitted_on_opposite_direction_break(self):
        sth1 = swing(True, 1.05, 1)
        stl1 = swing(False, 0.90, 3)
        candles = [
            mk(1.0, 1.05, 0.99, 1.0, 0),
            mk(1.0, 1.05, 0.99, 1.0, 1),
            mk(1.0, 1.06, 0.99, 1.06, 2),  # close 1.06 > 1.05 breaks sth1 -> BOS, trend=BULLISH
            mk(1.0, 1.05, 0.90, 1.0, 3),
            mk(1.0, 1.05, 0.92, 1.0, 4),
            mk(0.95, 0.96, 0.85, 0.85, 5),  # close 0.85 < 0.90 breaks stl1 -> CHOCH (opposite trend)
        ]
        events = SwingStructureClassifier()._classify_structure_events(
            [sth1, stl1], candles, Timeframe.M5
        )
        assert len(events) == 2
        assert events[0].event_type == StructureEventType.BOS
        assert events[1].event_type == StructureEventType.CHOCH
        assert events[1].direction == BiasDirection.BEARISH

    def test_structure_event_never_both_bos_and_choch(self):
        sth1 = swing(True, 1.05, 1)
        stl1 = swing(False, 0.90, 3)
        candles = [
            mk(1.0, 1.05, 0.99, 1.0, 0),
            mk(1.0, 1.05, 0.99, 1.0, 1),
            mk(1.0, 1.06, 0.99, 1.06, 2),
            mk(1.0, 1.05, 0.90, 1.0, 3),
            mk(1.0, 1.05, 0.92, 1.0, 4),
            mk(0.95, 0.96, 0.85, 0.85, 5),
        ]
        events = SwingStructureClassifier()._classify_structure_events(
            [sth1, stl1], candles, Timeframe.M5
        )
        for e in events:
            assert e.event_type in (StructureEventType.BOS, StructureEventType.CHOCH)

    def test_latest_event_reflects_most_recent_break(self):
        candles = [
            mk(1.0, 1.00, 0.99, 1.00, 0),
            mk(1.0, 1.00, 0.99, 1.00, 1),
            mk(1.0, 1.10, 0.99, 1.00, 2),  # STH @ ts2, price 1.10
            mk(1.0, 1.00, 0.99, 1.00, 3),
            mk(1.0, 1.00, 0.99, 1.00, 4),
            mk(1.0, 1.05, 0.90, 1.00, 5),
            mk(1.0, 1.05, 0.90, 1.00, 6),
            mk(1.0, 1.05, 0.80, 1.00, 7),  # STL @ ts7, price 0.80
            mk(1.0, 1.05, 0.90, 1.00, 8),
            mk(1.0, 1.05, 0.90, 1.00, 9),
            mk(1.0, 1.00, 0.85, 1.00, 10),
            mk(1.0, 1.12, 0.99, 1.12, 11),  # close 1.12 > 1.10 -> breaks STH @ ts2
            mk(1.0, 1.05, 0.95, 1.00, 12),
            mk(0.85, 0.90, 0.75, 0.75, 13),  # close 0.75 < 0.80 -> breaks STL @ ts7 (latest)
        ]
        result = SwingStructureClassifier().classify({Timeframe.M5: candles})[Timeframe.M5]
        assert len(result.events) >= 2
        assert result.latest_event is not None
        assert result.latest_event.confirmed_at == max(e.confirmed_at for e in result.events)
        assert result.latest_event.confirmed_at == ts(13)


class TestClassifyIntegration:
    def test_classify_is_deterministic(self):
        candles = [
            mk(1.0, 1.00, 0.99, 1.00, 0),
            mk(1.0, 1.00, 0.99, 1.00, 1),
            mk(1.0, 1.10, 0.99, 1.00, 2),
            mk(1.0, 1.00, 0.99, 1.00, 3),
            mk(1.0, 1.00, 0.99, 1.00, 4),
            mk(1.0, 1.12, 0.99, 1.12, 5),
        ]
        classifier = SwingStructureClassifier()
        result1 = classifier.classify({Timeframe.M5: candles})
        result2 = classifier.classify({Timeframe.M5: candles})
        assert result1[Timeframe.M5].model_dump() == result2[Timeframe.M5].model_dump()

    def test_swing_structure_result_per_timeframe(self):
        candles_m5 = [mk(1.0, 1.0, 1.0, 1.0, n, tf=Timeframe.M5) for n in range(5)]
        candles_h1 = [mk(1.0, 1.0, 1.0, 1.0, n, tf=Timeframe.H1) for n in range(5)]
        result = SwingStructureClassifier().classify(
            {Timeframe.M5: candles_m5, Timeframe.H1: candles_h1}
        )
        assert set(result.keys()) == {Timeframe.M5, Timeframe.H1}


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
    def test_property_swing_tier_promotion_requires_broken_lower_tier(self, candles):
        """Property 24: any promoted SwingPoint's derived_from points at a broken lower-tier swing."""
        result = SwingStructureClassifier().classify({Timeframe.M5: candles})[Timeframe.M5]
        all_points = {
            sp.swing_id: sp
            for sp in (
                result.short_term_highs
                + result.short_term_lows
                + result.intermediate_term_highs
                + result.intermediate_term_lows
                + result.long_term_highs
                + result.long_term_lows
            )
        }
        expected_lower_tier = {
            SwingTier.INTERMEDIATE_TERM: SwingTier.SHORT_TERM,
            SwingTier.LONG_TERM: SwingTier.INTERMEDIATE_TERM,
        }
        for sp in all_points.values():
            if sp.tier in expected_lower_tier:
                assert sp.derived_from_swing_id is not None
                origin = all_points[sp.derived_from_swing_id]
                assert origin.tier == expected_lower_tier[sp.tier]
                assert origin.broken is True

    @settings(max_examples=100)
    @given(candles=_valid_candle_seq())
    def test_property_bos_choch_mutual_exclusivity(self, candles):
        """Property 25: every StructureEvent is exactly one of BOS or CHOCH."""
        result = SwingStructureClassifier().classify({Timeframe.M5: candles})[Timeframe.M5]
        for event in result.events:
            assert event.event_type in (StructureEventType.BOS, StructureEventType.CHOCH)
