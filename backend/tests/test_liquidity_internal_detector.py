"""Tests for liquidity_engine.detectors.internal.PDArrayDetector."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
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


class TestFVGIsTheGap:
    """``fvg_zone = "gap"``: the FVG is the gap the user marks, with its CE (Requirement 26, LE-D17)."""

    def _bullish(self):
        return [                                     # the gap runs from candle 0's high to candle 2's low
            mk(0.98, 1.00, 0.97, 0.99, 0),
            mk(0.99, 1.04, 0.99, 1.03, 1),
            mk(1.03, 1.10, 1.05, 1.08, 2),
        ]

    def _bearish(self):
        return [                                     # the gap runs from candle 2's high to candle 0's low
            mk(0.97, 1.00, 0.95, 0.96, 0),
            mk(0.96, 0.97, 0.90, 0.91, 1),
            mk(0.91, 0.92, 0.85, 0.87, 2),
        ]

    def _only(self, candles, zone="gap"):
        fvgs = PDArrayDetector(fvg_zone=zone)._detect_fvg(candles, Timeframe.M5)
        assert len(fvgs) == 1
        return fvgs[0]

    def test_a_bullish_gap_is_c1s_high_to_c3s_low_with_its_ce(self):
        fvg = self._only(self._bullish())
        assert (fvg.low, fvg.high) == (1.00, 1.05)                    # not 0.97 to 1.10, the three candles
        assert fvg.ce == pytest.approx(1.025) and fvg.direction == BiasDirection.BULLISH
        assert fvg.formed_at == ts(2)                                 # the third candle's open time

    def test_a_bearish_gap_is_c3s_high_to_c1s_low_with_its_ce(self):
        fvg = self._only(self._bearish())
        assert (fvg.low, fvg.high) == (0.92, 0.95)
        assert fvg.ce == pytest.approx(0.935) and fvg.direction == BiasDirection.BEARISH

    def test_the_default_is_still_the_three_candles(self):
        assert (self._only(self._bullish(), zone="candles").low,
                self._only(self._bullish(), zone="candles").high) == (0.97, 1.10)
        assert PDArrayDetector()._detect_fvg(self._bullish(), Timeframe.M5)[0].high == 1.10

    def test_a_wick_through_the_gap_leaves_it_live_and_a_close_beyond_fills_it(self):
        detector = PDArrayDetector(fvg_zone="gap")
        wick = self._bullish() + [mk(1.08, 1.09, 0.99, 1.06, 3)]      # straight through the gap, closes above it
        fvg = detector._detect_fvg(wick, Timeframe.M5)[0]
        detector._mark_fvg_filled(fvg, wick)
        assert not fvg.is_filled and fvg.filled_at is None
        closed = self._bullish() + [mk(1.08, 1.09, 0.95, 0.99, 3)]    # closes below the gap's far edge
        beyond = detector._detect_fvg(closed, Timeframe.M5)[0]
        detector._mark_fvg_filled(beyond, closed)
        assert beyond.is_filled and beyond.filled_at == ts(3)

    def test_a_bearish_gap_fills_on_a_close_above_it(self):
        detector = PDArrayDetector(fvg_zone="gap")
        candles = self._bearish() + [mk(0.87, 0.99, 0.86, 0.96, 3)]   # closes above the gap's high
        fvg = detector._detect_fvg(candles, Timeframe.M5)[0]
        detector._mark_fvg_filled(fvg, candles)
        assert fvg.is_filled and fvg.filled_at == ts(3)

    def test_the_default_still_fills_on_a_wick(self):
        detector = PDArrayDetector()
        candles = self._bullish() + [mk(1.08, 1.09, 0.96, 1.06, 3)]   # a wick to the bottom of the three candles
        fvg = detector._detect_fvg(candles, Timeframe.M5)[0]
        detector._mark_fvg_filled(fvg, candles)
        assert fvg.is_filled and fvg.filled_at == ts(3)

    def test_the_ifvg_and_the_bpr_follow_the_gap(self):
        detector = PDArrayDetector(fvg_zone="gap")
        candles = self._bullish() + [mk(1.08, 1.09, 0.95, 0.99, 3)]
        fvgs = detector._detect_fvg(candles, Timeframe.M5)
        for fvg in fvgs:
            detector._mark_fvg_filled(fvg, candles)
        ifvgs = detector._detect_ifvg(candles, fvgs)
        assert len(ifvgs) == 1 and (ifvgs[0].low, ifvgs[0].high) == (1.00, 1.05)
        assert ifvgs[0].direction == BiasDirection.BEARISH and ifvgs[0].ce == pytest.approx(1.025)
        # A bearish gap overlapping the bullish one: the BPR is the overlap of the two gaps.
        bull = detector._detect_fvg(self._bullish(), Timeframe.M5)[0]
        down = [mk(1.06, 1.06, 1.02, 1.03, 4), mk(1.03, 1.04, 0.99, 1.00, 5), mk(1.00, 1.01, 0.96, 0.97, 6)]
        bear = detector._detect_fvg(down, Timeframe.M5)[0]            # the gap: 1.01 to 1.02
        bprs = detector._detect_bpr([bull, bear])
        assert len(bprs) == 1 and (bprs[0].low, bprs[0].high) == (1.01, 1.02)

    def test_the_unicorn_overlaps_the_gap(self):
        from liquidity_engine.unicorn.detector import UnicornDetector

        detector = PDArrayDetector(fvg_zone="gap")
        fvg = detector._detect_fvg(self._bullish(), Timeframe.M5)[0]            # the gap: 1.00 to 1.05
        ob = detector._make_pdarray(PDArrayType.BREAKER, BiasDirection.BULLISH, Timeframe.M5, 1.03, 0.90, ts(3))
        unicorn = UnicornDetector().detect([fvg, ob])
        assert unicorn is not None
        assert (unicorn.overlap_low, unicorn.overlap_high) == (1.00, 1.03)       # the gap, not the candles

    def test_every_timeframe_goes_through_detect(self):
        candles = {Timeframe.M5: self._bullish()}
        gap = [a for a in PDArrayDetector(fvg_zone="gap").detect(candles, {}) if a.array_type == PDArrayType.FVG]
        assert (gap[0].low, gap[0].high) == (1.00, 1.05)
        assert not PDArrayDetector(fvg_zone="gap")._detect_fvg([], Timeframe.M5)

    def test_an_unknown_zone_is_refused(self):
        with pytest.raises(ValueError, match="fvg_zone"):
            PDArrayDetector(fvg_zone="the whole candle")


class TestFVGZoneReachesTheEngine:
    """The plumbing (Requirement 26.4): the option travels from the configuration to the detector."""

    def test_the_engine_passes_it_to_the_detector(self):
        from liquidity_engine import LiquidityMappingEngine

        assert LiquidityMappingEngine().fvg_zone == "candles"
        assert LiquidityMappingEngine(fvg_zone="gap").fvg_zone == "gap"
        with pytest.raises(ValueError, match="fvg_zone"):
            LiquidityMappingEngine(fvg_zone="nonsense")

    def test_the_strategy_config_carries_it_and_defaults_to_the_candles(self):
        from agent.strategy_config import FvgZone, StrategyConfig

        assert StrategyConfig().fvg_zone is FvgZone.CANDLES
        assert StrategyConfig(fvg_zone="gap").fvg_zone is FvgZone.GAP
        with pytest.raises(Exception):
            StrategyConfig(fvg_zone="candles and the wick")

    def test_the_phase_a_cache_key_changes_with_it(self):
        from algo_backtester.cache import cache_key
        from algo_backtester.data import DataFingerprint
        from agent.strategy_config import StrategyConfig

        fp = DataFingerprint(rows=10, sha256="abc")
        args = (fp, "engine-fp", )
        rest = ("EURUSD", datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc))
        candles = cache_key(*args, StrategyConfig(), *rest)
        gap = cache_key(*args, StrategyConfig(fvg_zone="gap"), *rest)
        assert candles != gap

    def test_configurations_with_different_zones_cannot_share_one_engine_view(self):
        from agent.strategy_config import StrategyConfig
        from algo_backtester.signals import same_view

        base = StrategyConfig()
        assert same_view([base, StrategyConfig(min_rr=2.0)])          # execution-only: one engine is enough
        assert not same_view([base, StrategyConfig(fvg_zone="gap")])  # the engine itself reads differently

    def test_phase_a_builds_the_engine_from_the_configuration(self):
        import inspect

        from algo_backtester import signals as sig

        for name in ("signals_at", "generate_signals", "_generate_closes"):
            source = inspect.getsource(getattr(sig, name))
            assert "fvg_zone" in source, f"{name} builds the engine without the configuration's fvg_zone"

    def test_the_live_runner_and_the_watch_pass_it(self):
        import inspect

        from algo_backtester import watch
        import scripts.run_live_agent as live

        assert "fvg_zone" in inspect.getsource(watch.WatchSession._prepare)
        assert "fvg_zone" in inspect.getsource(watch._Capturing)
        assert "fvg_zone" in inspect.getsource(live._process_instrument)


class TestTheGapIsTheResearchsFVG:
    """One definition, read twice (Requirement 26, AR-D27).

    The research reads FVGs from a bar table (``algo_research.atlas.arrays.fvgs``) and the engine from a candle
    list. Under ``fvg_zone = "gap"`` they must agree on every gap of the same series, bound for bound, or the
    turn atlas and the engine are measuring different things — and so is Noculus's comparison.
    """

    def _series(self, n: int = 90):
        """A walk with gaps both ways: each candle steps from the last close, some steps jumping clear."""
        import random

        rng = random.Random(26)
        price, candles = 1.1000, []
        for i in range(n):
            step = rng.choice((-0.0030, -0.0012, -0.0004, 0.0004, 0.0012, 0.0030))
            open_ = price
            close = round(open_ + step, 5)
            high = round(max(open_, close) + rng.choice((0.0, 0.0002, 0.0006)), 5)
            low = round(min(open_, close) - rng.choice((0.0, 0.0002, 0.0006)), 5)
            candles.append(mk(open_, high, low, close, i, tf=Timeframe.H1))
            price = close
        return candles

    def test_the_engine_and_the_research_find_the_same_gaps(self):
        import pandas as pd

        from algo_research.atlas.arrays import fvgs as research_fvgs

        candles = self._series()
        mine = PDArrayDetector(fvg_zone="gap")._detect_fvg(candles, Timeframe.H1)
        bars = pd.DataFrame({
            "time": [c.timestamp for c in candles],
            "close_time": [c.timestamp + timedelta(hours=1) for c in candles],
            "open": [c.open for c in candles], "high": [c.high for c in candles],
            "low": [c.low for c in candles], "close": [c.close for c in candles],
        })
        theirs = research_fvgs(bars, Timeframe.H1)
        assert len(mine) > 8, "the series should hold gaps both ways"
        engine = sorted((a.formed_at, 1 if a.direction == BiasDirection.BULLISH else -1,
                         round(a.low, 5), round(a.high, 5), round(a.ce, 5)) for a in mine)
        # The research stamps a gap with C3's close, the engine with C3's open: one candle apart, by design.
        research = sorted((row.formed_at.tz_convert(None).to_pydatetime().replace(tzinfo=timezone.utc)
                           - timedelta(hours=1), int(row.direction), round(row.low, 5), round(row.high, 5),
                           round(row.mid, 5)) for row in theirs.itertuples())
        assert engine == research

    def test_the_default_finds_different_bounds(self):
        import pandas as pd

        from algo_research.atlas.arrays import fvgs as research_fvgs

        candles = self._series()
        bars = pd.DataFrame({
            "time": [c.timestamp for c in candles],
            "close_time": [c.timestamp + timedelta(hours=1) for c in candles],
            "open": [c.open for c in candles], "high": [c.high for c in candles],
            "low": [c.low for c in candles], "close": [c.close for c in candles],
        })
        wide = PDArrayDetector()._detect_fvg(candles, Timeframe.H1)
        theirs = research_fvgs(bars, Timeframe.H1)
        assert len(wide) == len(theirs)                       # the same gaps are found
        assert [(round(a.low, 5), round(a.high, 5)) for a in wide] != \
               [(round(r.low, 5), round(r.high, 5)) for r in theirs.itertuples()]   # but not the same zones
