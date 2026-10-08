"""Tests for liquidity_engine.engine.LiquidityMappingEngine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pytest
from hypothesis import given, settings, strategies as st

from liquidity_engine.detectors.bias import HTFBiasClassifier
from liquidity_engine.detectors.external import LiquidityLevelDetector
from liquidity_engine.detectors.internal import PDArrayDetector
from liquidity_engine.detectors.structure import SwingStructureClassifier
from liquidity_engine.engine import LiquidityMappingEngine
from liquidity_engine.fractal.candle_model import FractalModelTracker
from liquidity_engine.grader.sequence import SetupSequenceDetector
from liquidity_engine.grader.setup_grader import SetupGrader
from liquidity_engine.ipda.classifier import IPDAClassifier
from liquidity_engine.models import (
    BiasDirection,
    Candle,
    HTFBias,
    LiquidityLevel,
    LiquiditySource,
    LiquidityType,
    Timeframe,
)
from liquidity_engine.ote.calculator import OTECalculator
from liquidity_engine.unicorn.detector import UnicornDetector

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def d1_ts(n: int) -> datetime:
    return _BASE + timedelta(days=n)


def w1_ts(n: int) -> datetime:
    return _BASE + timedelta(weeks=n)


def m5_ts(n: int) -> datetime:
    return _BASE + timedelta(minutes=5 * n)


def mk(open_, high, low, close, timestamp, tf, instrument="EURUSD") -> Candle:
    return Candle(
        timestamp=timestamp, open=open_, high=high, low=low, close=close,
        timeframe=tf, instrument=instrument,
    )


# D1/W1 use a price scale deliberately far below (bullish) or above (bearish)
# the M5 fixtures' ~100/~197 range, so the derived HTF bias direction is
# unambiguous regardless of the exact M5 drift math.
def bullish_d1(n: int = 10) -> List[Candle]:
    return [mk(50 + i, 50 + i + 2, 50 + i - 1, 50 + i + 1.5, d1_ts(i), Timeframe.D1) for i in range(n)]


def bearish_d1(n: int = 10) -> List[Candle]:
    return [mk(300 - i, 300 - i + 1, 300 - i - 2, 300 - i - 1.5, d1_ts(i), Timeframe.D1) for i in range(n)]


def bullish_w1(n: int = 4) -> List[Candle]:
    return [mk(40 + 2 * i, 40 + 2 * i + 3, 40 + 2 * i - 1, 40 + 2 * i + 2.5, w1_ts(i), Timeframe.W1) for i in range(n)]


def bearish_w1(n: int = 4) -> List[Candle]:
    return [mk(310 - 2 * i, 310 - 2 * i + 1, 310 - 2 * i - 3, 310 - 2 * i - 2.5, w1_ts(i), Timeframe.W1) for i in range(n)]


def bullish_m5_with_gap() -> List[Candle]:
    """A guaranteed 3-candle bullish FVG at indices 0-2, then a long, gentle,
    strictly-increasing drift so the series is non-trivial without introducing
    any further ambiguous swing/gap structure."""
    candles = [
        mk(100.0, 100.2, 99.8, 100.1, m5_ts(0), Timeframe.M5),
        mk(101.5, 102.5, 101.2, 102.3, m5_ts(1), Timeframe.M5),
        mk(102.3, 103.0, 102.8, 102.9, m5_ts(2), Timeframe.M5),
    ]
    price = 102.9
    for i in range(3, 25):
        price += 0.05
        candles.append(mk(price - 0.05, price + 0.1, price - 0.15, price, m5_ts(i), Timeframe.M5))
    return candles


def bearish_m5_with_gap() -> List[Candle]:
    candles = [
        mk(200.0, 200.2, 199.8, 199.9, m5_ts(0), Timeframe.M5),
        mk(198.5, 198.8, 197.5, 197.7, m5_ts(1), Timeframe.M5),
        mk(197.0, 197.2, 197.0, 197.1, m5_ts(2), Timeframe.M5),
    ]
    price = 197.1
    for i in range(3, 25):
        price -= 0.05
        candles.append(mk(price + 0.05, price + 0.15, price - 0.1, price, m5_ts(i), Timeframe.M5))
    return candles


def build_candles_by_tf(bullish: bool = True) -> Dict[Timeframe, List[Candle]]:
    if bullish:
        return {
            Timeframe.D1: bullish_d1(),
            Timeframe.W1: bullish_w1(),
            Timeframe.M5: bullish_m5_with_gap(),
        }
    return {
        Timeframe.D1: bearish_d1(),
        Timeframe.W1: bearish_w1(),
        Timeframe.M5: bearish_m5_with_gap(),
    }


class TestAnalyzeBasics:
    def test_analyze_returns_liquidity_map(self):
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        assert result.instrument == "EURUSD"
        assert result.setup_grade is not None

    def test_analyze_requires_d1_timeframe(self):
        candles_by_tf = build_candles_by_tf()
        del candles_by_tf[Timeframe.D1]
        with pytest.raises(ValueError):
            LiquidityMappingEngine().analyze(candles_by_tf, "EURUSD", d1_ts(20))

    def test_analyze_requires_w1_timeframe(self):
        candles_by_tf = build_candles_by_tf()
        del candles_by_tf[Timeframe.W1]
        with pytest.raises(ValueError):
            LiquidityMappingEngine().analyze(candles_by_tf, "EURUSD", d1_ts(20))

    def test_analyzed_at_matches_timestamp_arg(self):
        ts = d1_ts(20)
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", ts)
        assert result.analyzed_at == ts

    def test_analyzed_at_is_timezone_aware(self):
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        assert result.analyzed_at.tzinfo is not None

    def test_htf_bias_contains_d1(self):
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        assert Timeframe.D1.value in result.htf_bias

    def test_htf_bias_contains_w1(self):
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        assert Timeframe.W1.value in result.htf_bias

    def test_does_not_mutate_input(self):
        candles_by_tf = build_candles_by_tf()
        snapshot = {tf: list(candles) for tf, candles in candles_by_tf.items()}
        LiquidityMappingEngine().analyze(candles_by_tf, "EURUSD", d1_ts(20))
        assert candles_by_tf == snapshot

    def test_swing_structure_populated_per_timeframe(self):
        candles_by_tf = build_candles_by_tf()
        result = LiquidityMappingEngine().analyze(candles_by_tf, "EURUSD", d1_ts(20))
        assert set(result.swing_structure.keys()) == {tf.value for tf in candles_by_tf}

    def test_pd_array_detector_receives_swing_structure(self, monkeypatch):
        received = {}
        original = PDArrayDetector.detect

        def spy(self, candles_by_tf, swing_structure):
            received["swing_structure"] = swing_structure
            return original(self, candles_by_tf, swing_structure)

        monkeypatch.setattr(PDArrayDetector, "detect", spy)
        LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        assert received["swing_structure"] != {}

    def test_get_arrays_in_range_excludes_filled(self):
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        in_range = result.get_arrays_in_range(0.0, 10_000.0)
        assert all(not a.is_filled for a in in_range)


class TestSubComponentOrder:
    def test_sub_components_called_in_order(self, monkeypatch):
        order: List[str] = []

        def record(name, original):
            def wrapper(self, *args, **kwargs):
                order.append(name)
                return original(self, *args, **kwargs)
            return wrapper

        monkeypatch.setattr(HTFBiasClassifier, "classify", record("HTFBiasClassifier", HTFBiasClassifier.classify))
        monkeypatch.setattr(LiquidityLevelDetector, "detect", record("LiquidityLevelDetector", LiquidityLevelDetector.detect))
        monkeypatch.setattr(SwingStructureClassifier, "classify", record("SwingStructureClassifier", SwingStructureClassifier.classify))
        monkeypatch.setattr(PDArrayDetector, "detect", record("PDArrayDetector", PDArrayDetector.detect))
        monkeypatch.setattr(FractalModelTracker, "track", record("FractalModelTracker", FractalModelTracker.track))
        monkeypatch.setattr(IPDAClassifier, "classify_crt_phase", record("IPDAClassifier", IPDAClassifier.classify_crt_phase))
        monkeypatch.setattr(IPDAClassifier, "validate_cisd_cascade", record("IPDAClassifier", IPDAClassifier.validate_cisd_cascade))
        monkeypatch.setattr(OTECalculator, "calculate", record("OTECalculator", OTECalculator.calculate))
        monkeypatch.setattr(UnicornDetector, "detect", record("UnicornDetector", UnicornDetector.detect))
        monkeypatch.setattr(SetupSequenceDetector, "detect", record("SetupSequenceDetector", SetupSequenceDetector.detect))
        monkeypatch.setattr(SetupGrader, "grade", record("SetupGrader", SetupGrader.grade))

        LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))

        first_seen: List[str] = []
        for name in order:
            if name not in first_seen:
                first_seen.append(name)

        expected = [
            "HTFBiasClassifier", "LiquidityLevelDetector", "SwingStructureClassifier",
            "PDArrayDetector", "FractalModelTracker", "IPDAClassifier", "OTECalculator",
            "UnicornDetector", "SetupSequenceDetector", "SetupGrader",            # Requirement 1.5, amended 2026-10
        ]
        assert first_seen == expected


class TestSetupSequenceOnMap:
    def test_engine_records_the_setup_sequence(self):
        # Requirement 18.8: the map carries the detector's sequence over the engine's own PD arrays.
        from tests.test_liquidity_sequence import BULLISH_ROWS, series

        candles_by_tf = {Timeframe.D1: bullish_d1(), Timeframe.W1: bullish_w1(), Timeframe.M15: series(BULLISH_ROWS)}
        result = LiquidityMappingEngine().analyze(candles_by_tf, "EURUSD", d1_ts(20))
        assert result.setup_sequence is not None
        assert result.setup_sequence == SetupSequenceDetector().detect(candles_by_tf, result.pd_arrays)
        assert result.setup_sequence.raid.raided_at == datetime(2024, 1, 2, 7, 45, tzinfo=timezone.utc)

    def test_engine_passes_the_analysis_time_to_the_detector(self, monkeypatch):
        # Requirement 20.2: the Asian pools depend on when the analysis runs.
        seen = {}
        original = SetupSequenceDetector.detect

        def spy(self, candles_by_tf, pd_arrays, as_of=None):
            seen["as_of"] = as_of
            return original(self, candles_by_tf, pd_arrays, as_of=as_of)

        monkeypatch.setattr(SetupSequenceDetector, "detect", spy)
        LiquidityMappingEngine().analyze(sequence_window(), "EURUSD", d1_ts(20))
        assert seen["as_of"] == d1_ts(20)

    def test_no_sequence_without_entry_arrays(self):
        result = LiquidityMappingEngine().analyze(
            {Timeframe.D1: bullish_d1(), Timeframe.W1: bullish_w1()}, "EURUSD", d1_ts(20))
        assert result.setup_sequence is None


class TestFractalModelSeeding:
    def test_fractal_model_populated_when_key_level_available(self):
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        assert result.fractal_model is not None

    def test_fractal_model_none_when_insufficient_data(self):
        candles_by_tf = {
            Timeframe.D1: [bullish_d1(1)[0]],
            Timeframe.W1: [bullish_w1(1)[0]],
        }
        result = LiquidityMappingEngine().analyze(candles_by_tf, "EURUSD", d1_ts(20))
        assert result.fractal_model is None


class TestDrawOnLiquidity:
    def _bias(self, direction: BiasDirection) -> Dict[Timeframe, HTFBias]:
        return {
            Timeframe.D1: HTFBias(
                timeframe=Timeframe.D1, direction=direction, reference_open=100.0,
                reference_open_time=d1_ts(0), current_price=101.0 if direction == BiasDirection.BULLISH else 99.0,
                distance_from_open=1.0, distance_pct=0.01, is_deep_premium=False, is_deep_discount=False,
            )
        }

    def _level(self, liquidity_type: LiquidityType, swept: bool = False, strength: float = 0.5) -> LiquidityLevel:
        return LiquidityLevel(
            level_id=f"lvl-{liquidity_type.value}-{strength}",
            liquidity_type=liquidity_type,
            source=LiquiditySource.PDH if liquidity_type == LiquidityType.BSL else LiquiditySource.PDL,
            price=110.0,
            timeframe=Timeframe.D1,
            formed_at=d1_ts(0),
            strength_score=strength,
            touch_count=1,
            swept=swept,
        )

    def test_draw_on_liquidity_bsl_when_bullish_bias(self):
        engine = LiquidityMappingEngine()
        htf_bias = self._bias(BiasDirection.BULLISH)
        levels = [self._level(LiquidityType.BSL), self._level(LiquidityType.SSL)]
        draw = engine._find_draw_on_liquidity(htf_bias, levels)
        assert draw is not None
        assert draw.liquidity_type == LiquidityType.BSL

    def test_draw_on_liquidity_ssl_when_bearish_bias(self):
        engine = LiquidityMappingEngine()
        htf_bias = self._bias(BiasDirection.BEARISH)
        levels = [self._level(LiquidityType.BSL), self._level(LiquidityType.SSL)]
        draw = engine._find_draw_on_liquidity(htf_bias, levels)
        assert draw is not None
        assert draw.liquidity_type == LiquidityType.SSL

    def test_draw_on_liquidity_none_when_no_unswept_levels(self):
        engine = LiquidityMappingEngine()
        htf_bias = self._bias(BiasDirection.BULLISH)
        levels = [self._level(LiquidityType.BSL, swept=True)]
        draw = engine._find_draw_on_liquidity(htf_bias, levels)
        assert draw is None

    def test_draw_on_liquidity_level_id_in_liquidity_levels(self):
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        if result.draw_on_liquidity is not None:
            assert result.draw_on_liquidity.level_id in {lvl.level_id for lvl in result.liquidity_levels}


def sequence_window() -> Dict[Timeframe, List[Candle]]:
    """The hand-checked bullish raid sequence of test_liquidity_sequence on M15, with HTF context."""
    from tests.test_liquidity_sequence import BULLISH_ROWS, series

    return {Timeframe.D1: bullish_d1(), Timeframe.W1: bullish_w1(), Timeframe.M15: series(BULLISH_ROWS)}


class TestSweepAndSetupLeg:
    """Requirement 13.4 (superseded 2026-10): sweep_detected means a raid sequence exists.
    Requirement 18.15: the SD projection is anchored on the setup leg."""

    def test_sweep_detected_means_setup_sequence(self):
        result = LiquidityMappingEngine().analyze(sequence_window(), "EURUSD", d1_ts(20))
        assert result.sweep_detected is True and result.setup_sequence is not None
        assert result.setup_grade.liquidity_sweep_confirmed is True
        assert result.setup_grade.entry_array_id == result.setup_sequence.entry_array_id
        bare = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        assert bare.sweep_detected is (bare.setup_sequence is not None)

    def test_sd_projection_anchored_on_setup_leg(self):
        result = LiquidityMappingEngine().analyze(sequence_window(), "EURUSD", d1_ts(20))
        sd = result.sd_projection
        # Protected wick 99.6 (the raid bar), leg extreme 102.3: a 2.7 leg projected upward.
        assert (sd.anchor_0, sd.anchor_1) == (102.3, 99.6)
        assert sd.targets[2.0] == pytest.approx(102.3 + 2 * 2.7)

    def test_sd_projection_none_without_sequence(self):
        result = LiquidityMappingEngine().analyze(
            {Timeframe.D1: bullish_d1(), Timeframe.W1: bullish_w1()}, "EURUSD", d1_ts(20))
        assert result.setup_sequence is None and result.sd_projection is None


class TestSweptLevels:
    """Requirement 13.5 (amended 2026-10): a level is swept once a bar of any
    timeframe, opening after the level formed, trades beyond it; the draw on
    liquidity is chosen among untouched levels only (13.1)."""

    def _level(self, liquidity_type: LiquidityType, price: float, formed_at: datetime) -> LiquidityLevel:
        return LiquidityLevel(
            level_id=f"lvl-{liquidity_type.value}-{price}", liquidity_type=liquidity_type,
            source=LiquiditySource.PDH if liquidity_type == LiquidityType.BSL else LiquiditySource.PDL,
            price=price, timeframe=Timeframe.D1, formed_at=formed_at, strength_score=0.5, touch_count=1,
        )

    def test_level_marked_swept_when_later_bar_trades_beyond(self):
        bsl = self._level(LiquidityType.BSL, 110.0, m5_ts(0))
        ssl = self._level(LiquidityType.SSL, 100.0, m5_ts(0))
        candles_by_tf = {Timeframe.M5: [mk(105.0, 110.5, 104.0, 106.0, m5_ts(1), Timeframe.M5),
                                         mk(106.0, 107.0, 101.0, 102.0, m5_ts(2), Timeframe.M5)]}
        marked = LiquidityMappingEngine()._mark_swept_levels(candles_by_tf, [bsl, ssl])
        assert (marked[0].swept, marked[0].swept_at) == (True, m5_ts(1))
        assert (marked[1].swept, marked[1].swept_at) == (False, None)          # 101 never went below 100

    def test_level_not_swept_by_bars_of_its_own_period(self):
        # A previous-day high forms at that day's open; its own day's bars reach it but never beyond it,
        # and bars opening at or before formed_at don't count.
        pdh = self._level(LiquidityType.BSL, 110.0, d1_ts(1))
        candles_by_tf = {
            Timeframe.H1: [mk(108.0, 112.0, 107.0, 109.0, d1_ts(1), Timeframe.H1),            # opens at formed_at
                           mk(109.0, 110.0, 108.0, 109.5, d1_ts(1) + timedelta(hours=5), Timeframe.H1)],
            Timeframe.D1: [mk(100.0, 115.0, 99.0, 101.0, d1_ts(0), Timeframe.D1)],             # before it formed
        }
        [marked] = LiquidityMappingEngine()._mark_swept_levels(candles_by_tf, [pdh])
        assert marked.swept is False and marked.swept_at is None

    def test_swept_at_is_earliest_breaching_bar(self):
        ssl = self._level(LiquidityType.SSL, 100.0, d1_ts(0))
        candles_by_tf = {
            Timeframe.M5: [mk(101.0, 102.0, 99.0, 101.5, d1_ts(2), Timeframe.M5)],
            Timeframe.H1: [mk(101.0, 101.5, 100.5, 101.0, d1_ts(1), Timeframe.H1),
                           mk(101.0, 101.2, 99.5, 100.8, d1_ts(1) + timedelta(hours=3), Timeframe.H1)],
        }
        [marked] = LiquidityMappingEngine()._mark_swept_levels(candles_by_tf, [ssl])
        assert marked.swept_at == d1_ts(1) + timedelta(hours=3)

    def test_draw_on_liquidity_never_swept(self):
        # The fixture's last D1 and W1 bars trade above the previous day's and week's highs.
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(), "EURUSD", d1_ts(20))
        by_source = {lvl.source: lvl for lvl in result.liquidity_levels}
        assert (by_source[LiquiditySource.PDH].swept, by_source[LiquiditySource.PDH].swept_at) == (True, d1_ts(9))
        assert (by_source[LiquiditySource.PWH].swept, by_source[LiquiditySource.PWH].swept_at) == (True, w1_ts(3))
        assert result.draw_on_liquidity is None or not result.draw_on_liquidity.swept

    @settings(max_examples=100, deadline=None)
    @given(st.lists(st.tuples(st.floats(90, 120, allow_nan=False), st.floats(0, 5, allow_nan=False),
                              st.floats(0, 5, allow_nan=False)), min_size=1, max_size=30),
           st.floats(90, 120, allow_nan=False), st.integers(0, 30), st.booleans())
    def test_property_swept_iff_breached(self, bars, price, formed_index, is_bsl):
        """Property 34: swept exactly when some bar opening after formed_at traded beyond the price."""
        candles = [mk(mid, mid + up, mid - down, mid, m5_ts(i), Timeframe.M5) for i, (mid, up, down) in enumerate(bars)]
        level = self._level(LiquidityType.BSL if is_bsl else LiquidityType.SSL, price, m5_ts(formed_index))
        [marked] = LiquidityMappingEngine()._mark_swept_levels({Timeframe.M5: candles}, [level])
        breaches = [c.timestamp for c in candles if c.timestamp > level.formed_at
                    and (c.high > price if is_bsl else c.low < price)]
        assert marked.swept == bool(breaches)
        assert marked.swept_at == (min(breaches) if breaches else None)


class TestEngineProperties:
    @settings(max_examples=25)
    @given(offset=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False))
    def test_property_engine_determinism(self, offset):
        base = build_candles_by_tf()
        result_a = LiquidityMappingEngine().analyze(base, "EURUSD", d1_ts(20))
        result_b = LiquidityMappingEngine().analyze(base, "EURUSD", d1_ts(20))
        assert result_a.model_dump() == result_b.model_dump()

    @settings(max_examples=25)
    @given(bullish=st.booleans())
    def test_property_input_immutability(self, bullish):
        candles_by_tf = build_candles_by_tf(bullish=bullish)
        snapshot = {tf: list(candles) for tf, candles in candles_by_tf.items()}
        LiquidityMappingEngine().analyze(candles_by_tf, "EURUSD", d1_ts(20))
        assert candles_by_tf == snapshot

    @settings(max_examples=25)
    @given(bullish=st.booleans())
    def test_property_d1_w1_bias_always_present(self, bullish):
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(bullish=bullish), "EURUSD", d1_ts(20))
        assert Timeframe.D1.value in result.htf_bias
        assert Timeframe.W1.value in result.htf_bias

    @settings(max_examples=25)
    @given(bullish=st.booleans())
    def test_property_draw_on_liquidity_reference_integrity(self, bullish):
        result = LiquidityMappingEngine().analyze(build_candles_by_tf(bullish=bullish), "EURUSD", d1_ts(20))
        if result.draw_on_liquidity is not None:
            assert result.draw_on_liquidity.level_id in {lvl.level_id for lvl in result.liquidity_levels}
