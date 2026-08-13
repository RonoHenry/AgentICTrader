"""Tests for LiquidityMap.to_agent_context() and HTFBiasClassifier."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, strategies as st

from liquidity_engine.detectors.bias import HTFBiasClassifier
from liquidity_engine.models import (
    BiasDirection,
    Candle,
    CISDCascadeStatus,
    CRTPhase,
    CRTPhaseResult,
    FractalCandleStep,
    FractalModelResult,
    HTFBias,
    LiquidityLevel,
    LiquidityMap,
    LiquiditySource,
    LiquidityType,
    PDArray,
    PDArrayType,
    SetupGrade,
    SetupGradeDetail,
    StructureEvent,
    StructureEventType,
    SwingStructureResult,
    SwingTier,
    Timeframe,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def mk_candle(open_, high, low, close, n, tf=Timeframe.D1) -> Candle:
    return Candle(
        timestamp=ts(n), open=open_, high=high, low=low, close=close, timeframe=tf, instrument="EURUSD"
    )


def make_bias(tf: Timeframe, direction: BiasDirection) -> HTFBias:
    current = 101.0 if direction == BiasDirection.BULLISH else 99.0
    return HTFBias(
        timeframe=tf, direction=direction, reference_open=100.0, reference_open_time=ts(0),
        current_price=current, distance_from_open=current - 100.0, distance_pct=(current - 100.0) / 100.0,
        is_deep_premium=False, is_deep_discount=False,
    )


def minimal_liquidity_map(**overrides) -> LiquidityMap:
    defaults = dict(
        analyzed_at=ts(5),
        instrument="EURUSD",
        htf_bias={
            Timeframe.D1.value: make_bias(Timeframe.D1, BiasDirection.BULLISH),
            Timeframe.W1.value: make_bias(Timeframe.W1, BiasDirection.BULLISH),
        },
        liquidity_levels=[],
        pd_arrays=[],
        crt_phases={},
        cisd_cascade=None,
        draw_on_liquidity=None,
        sweep_detected=False,
        ote_zone=None,
        unicorn=None,
        setup_grade=SetupGradeDetail(
            grade=SetupGrade.A, conditions_met=7, htf_bias_confirmed=True,
            draw_on_liquidity_identified=True, liquidity_sweep_confirmed=True,
            displacement_present=True, cisd_confirmed=True, entry_pd_array_present=True,
            stop_placement_valid=True, time_window_aligned=False, grade_reason="Grade A (7/8).",
        ),
        swing_structure={},
        fractal_model=None,
    )
    defaults.update(overrides)
    return LiquidityMap(**defaults)


class TestToAgentContext:
    def test_to_agent_context_nonempty(self):
        assert minimal_liquidity_map().to_agent_context() != ""

    def test_to_agent_context_contains_all_htf_biases(self):
        text = minimal_liquidity_map().to_agent_context()
        assert "D1 bias: BULLISH" in text
        assert "W1 bias: BULLISH" in text

    def test_to_agent_context_contains_grade(self):
        text = minimal_liquidity_map().to_agent_context()
        assert "A" in text and "Setup grade" in text

    def test_to_agent_context_contains_conditions_met(self):
        text = minimal_liquidity_map().to_agent_context()
        assert "7/8" in text

    def test_to_agent_context_contains_draw_target_when_set(self):
        draw = LiquidityLevel(
            level_id="lvl", liquidity_type=LiquidityType.BSL, source=LiquiditySource.PDH,
            price=110.5, timeframe=Timeframe.D1, formed_at=ts(0), strength_score=0.7, touch_count=2,
        )
        text = minimal_liquidity_map(draw_on_liquidity=draw).to_agent_context()
        assert "Draw on liquidity" in text
        assert "110.5" in text

    def test_to_agent_context_omits_draw_target_when_none(self):
        text = minimal_liquidity_map(draw_on_liquidity=None).to_agent_context()
        assert "Draw on liquidity" not in text

    def test_to_agent_context_answers_three_questions(self):
        text = minimal_liquidity_map().to_agent_context()
        assert "come from" in text
        assert "now" in text
        assert "go" in text

    def test_to_agent_context_mentions_latest_structure_event_when_present(self):
        event = StructureEvent(
            event_type=StructureEventType.BOS, tier=SwingTier.SHORT_TERM, timeframe=Timeframe.M5,
            direction=BiasDirection.BULLISH, broken_swing_id="swing-1", confirmed_at=ts(3),
        )
        swing_structure = {
            Timeframe.M5.value: SwingStructureResult(events=[event], latest_event=event)
        }
        text = minimal_liquidity_map(swing_structure=swing_structure).to_agent_context()
        assert "BOS" in text

    def test_to_agent_context_mentions_equilibrium_when_fractal_model_present(self):
        candle = mk_candle(100, 101, 99, 100.5, 0)
        fractal_model = FractalModelResult(
            key_level=100.0, steps=[FractalCandleStep(step_number=1, candle=candle, closure_type=None)],
            range_high=101.0, range_low=99.0, equilibrium=100.0, price_above_equilibrium=True,
        )
        text = minimal_liquidity_map(fractal_model=fractal_model).to_agent_context()
        assert "equilibrium" in text.lower()

    def test_to_agent_context_omits_structure_and_equilibrium_lines_when_absent(self):
        text = minimal_liquidity_map(swing_structure={}, fractal_model=None).to_agent_context()
        assert "equilibrium" not in text.lower()
        assert "structure event" not in text.lower()

    @settings(max_examples=25)
    @given(conditions_met=st.integers(min_value=0, max_value=8))
    def test_property_to_agent_context_nonempty_and_complete(self, conditions_met):
        lm = minimal_liquidity_map(
            setup_grade=SetupGradeDetail(
                grade=SetupGrade.NO_TRADE, conditions_met=conditions_met, htf_bias_confirmed=False,
                draw_on_liquidity_identified=False, liquidity_sweep_confirmed=False,
                displacement_present=False, cisd_confirmed=False, entry_pd_array_present=False,
                stop_placement_valid=False, time_window_aligned=False,
                grade_reason=f"Grade NO_TRADE ({conditions_met}/8).",
            )
        )
        text = lm.to_agent_context()
        assert text != ""
        assert str(conditions_met) in text


class TestHTFBiasClassifier:
    def _candles(self, opens_highs_lows_closes, tf=Timeframe.D1):
        return [
            mk_candle(o, h, l, c, n, tf) for n, (o, h, l, c) in enumerate(opens_highs_lows_closes)
        ]

    def test_htf_bias_bullish_when_price_above_open(self):
        candles = self._candles([(100, 101, 99, 100.5)])
        bias = HTFBiasClassifier().classify({Timeframe.D1: candles}, current_price=105.0)
        assert bias[Timeframe.D1].direction == BiasDirection.BULLISH

    def test_htf_bias_bearish_when_price_below_open(self):
        candles = self._candles([(100, 101, 99, 100.5)])
        bias = HTFBiasClassifier().classify({Timeframe.D1: candles}, current_price=95.0)
        assert bias[Timeframe.D1].direction == BiasDirection.BEARISH

    def test_htf_bias_neutral_within_tolerance(self):
        candles = self._candles([(100, 101, 99, 100.5)])
        bias = HTFBiasClassifier().classify({Timeframe.D1: candles}, current_price=100.001)
        assert bias[Timeframe.D1].direction == BiasDirection.NEUTRAL

    def test_htf_bias_distance_from_open(self):
        candles = self._candles([(100, 101, 99, 100.5)])
        bias = HTFBiasClassifier().classify({Timeframe.D1: candles}, current_price=103.0)
        assert bias[Timeframe.D1].distance_from_open == pytest.approx(3.0)

    def test_htf_bias_distance_pct(self):
        candles = self._candles([(100, 101, 99, 100.5)])
        bias = HTFBiasClassifier().classify({Timeframe.D1: candles}, current_price=103.0)
        assert bias[Timeframe.D1].distance_pct == pytest.approx(0.03)

    def test_d1_uses_latest_d1_candle_open_as_reference(self):
        candles = self._candles([(100, 101, 99, 100.5), (108, 109, 107, 108.5)], tf=Timeframe.D1)
        bias = HTFBiasClassifier().classify({Timeframe.D1: candles}, current_price=110.0)
        assert bias[Timeframe.D1].reference_open == 108

    def test_w1_uses_latest_w1_candle_open_as_reference(self):
        candles = self._candles([(50, 55, 49, 54), (58, 62, 57, 61)], tf=Timeframe.W1)
        bias = HTFBiasClassifier().classify({Timeframe.W1: candles}, current_price=70.0)
        assert bias[Timeframe.W1].reference_open == 58

    def test_mn1_uses_latest_mn1_candle_open_as_reference(self):
        candles = self._candles([(10, 15, 9, 14), (16, 20, 15, 19)], tf=Timeframe.MN1)
        bias = HTFBiasClassifier().classify({Timeframe.MN1: candles}, current_price=25.0)
        assert bias[Timeframe.MN1].reference_open == 16

    @settings(max_examples=50)
    @given(
        open_=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        offset_pct=st.floats(min_value=0.001, max_value=0.5, allow_nan=False, allow_infinity=False),
        bullish=st.booleans(),
    )
    def test_property_htf_bias_direction_correctness(self, open_, offset_pct, bullish):
        candles = self._candles([(open_, open_ * 1.01, open_ * 0.99, open_)])
        price = open_ * (1 + offset_pct) if bullish else open_ * (1 - offset_pct)
        bias = HTFBiasClassifier().classify({Timeframe.D1: candles}, current_price=price)
        expected = BiasDirection.BULLISH if bullish else BiasDirection.BEARISH
        assert bias[Timeframe.D1].direction == expected

    @settings(max_examples=50)
    @given(open_=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    def test_property_htf_bias_neutral_band(self, open_):
        candles = self._candles([(open_, open_ * 1.01, open_ * 0.99, open_)])
        price = open_ * (1 + 0.00005)
        bias = HTFBiasClassifier().classify({Timeframe.D1: candles}, current_price=price)
        assert bias[Timeframe.D1].direction == BiasDirection.NEUTRAL
