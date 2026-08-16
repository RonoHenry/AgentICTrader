"""Tests for pd_array_engine.grader.setup_grader.SetupGrader."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from hypothesis import given, settings, strategies as st

from pd_array_engine.grader.setup_grader import SetupGrader
from pd_array_engine.models import (
    BiasDirection,
    CISDCascadeStatus,
    FractalModelResult,
    FractalCandleStep,
    Candle,
    HTFBias,
    LiquidityLevel,
    LiquidityMap,
    LiquiditySource,
    LiquidityType,
    OTEZone,
    PDArray,
    PDArrayType,
    SetupGrade,
    Timeframe,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
NY = ZoneInfo("America/New_York")


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def make_bias(tf: Timeframe, direction: BiasDirection) -> HTFBias:
    current = 101.0 if direction == BiasDirection.BULLISH else 99.0
    return HTFBias(
        timeframe=tf,
        direction=direction,
        reference_open=100.0,
        reference_open_time=ts(0),
        current_price=current,
        distance_from_open=current - 100.0,
        distance_pct=(current - 100.0) / 100.0,
        is_deep_premium=False,
        is_deep_discount=False,
    )


def make_level(level_id: str = "lvl1", price: float = 110.0) -> LiquidityLevel:
    return LiquidityLevel(
        level_id=level_id,
        liquidity_type=LiquidityType.BSL,
        source=LiquiditySource.PDH,
        price=price,
        timeframe=Timeframe.D1,
        formed_at=ts(0),
        strength_score=0.7,
        touch_count=1,
    )


def make_pdarray(
    array_type,
    direction,
    high,
    low,
    is_filled=False,
    structure_confirmed=False,
    strength_score=0.6,
    array_id=None,
    tf=Timeframe.M5,
):
    return PDArray(
        array_id=array_id or f"{array_type.value}-{direction.value}-{high}-{low}",
        array_type=array_type,
        direction=direction,
        timeframe=tf,
        high=high,
        low=low,
        formed_at=ts(0),
        is_filled=is_filled,
        strength_score=strength_score,
        structure_confirmed=structure_confirmed,
    )


def full_liquidity_map(**overrides) -> LiquidityMap:
    """All 8 SetupGrader conditions satisfied by default; tests override specific fields."""
    level = make_level()
    defaults = dict(
        analyzed_at=ts(5),
        instrument="EURUSD",
        htf_bias={
            Timeframe.D1.value: make_bias(Timeframe.D1, BiasDirection.BULLISH),
            Timeframe.W1.value: make_bias(Timeframe.W1, BiasDirection.BULLISH),
        },
        liquidity_levels=[level],
        pd_arrays=[
            make_pdarray(PDArrayType.OB, BiasDirection.BULLISH, 100.5, 100.0),
            make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.2, strength_score=0.9),
        ],
        crt_phases={},
        cisd_cascade=CISDCascadeStatus(cascade_valid=True, cascade_chain=[]),
        draw_on_liquidity=level,
        sweep_detected=True,
        ote_zone=None,
        unicorn=None,
        setup_grade=None,
        swing_structure={},
        fractal_model=None,
    )
    defaults.update(overrides)
    return LiquidityMap(**defaults)


LONDON_TS = datetime(2024, 1, 15, 3, 0, tzinfo=NY)
NY_AM_TS = datetime(2024, 1, 15, 8, 0, tzinfo=NY)
NY_PM_TS = datetime(2024, 1, 15, 14, 30, tzinfo=NY)
OFF_HOURS_TS = datetime(2024, 1, 15, 12, 0, tzinfo=NY)


class TestGradeAssignment:
    def test_aplus_grade_all_8_conditions_true(self):
        detail = SetupGrader().grade(full_liquidity_map(), LONDON_TS)
        assert detail.grade == SetupGrade.A_PLUS
        assert detail.conditions_met == 8

    def test_a_grade_7_conditions_true(self):
        lm = full_liquidity_map()  # time_window_aligned will be the only False condition
        detail = SetupGrader().grade(lm, OFF_HOURS_TS)
        assert detail.conditions_met == 7
        assert detail.grade == SetupGrade.A

    def test_b_grade_sweep_cisd_fvg_only(self):
        # sweep + cisd + FVG-only entry array True; displacement (OB) and time window False
        lm = full_liquidity_map(pd_arrays=[make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.2)])
        detail = SetupGrader().grade(lm, OFF_HOURS_TS)
        assert detail.conditions_met == 6
        assert detail.grade == SetupGrade.B

    def test_no_trade_fewer_than_6_conditions(self):
        # htf_bias + draw + sweep + entry + stop = 5 (no OB -> no displacement,
        # invalid cascade -> no cisd, off-hours -> no time window)
        lm = full_liquidity_map(
            pd_arrays=[make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0)],
            cisd_cascade=CISDCascadeStatus(cascade_valid=False, cascade_chain=[]),
        )
        detail = SetupGrader().grade(lm, OFF_HOURS_TS)
        assert detail.conditions_met == 5
        assert detail.grade == SetupGrade.NO_TRADE

    def test_no_trade_when_htf_bias_false(self):
        lm = full_liquidity_map(
            htf_bias={
                Timeframe.D1.value: make_bias(Timeframe.D1, BiasDirection.NEUTRAL),
                Timeframe.W1.value: make_bias(Timeframe.W1, BiasDirection.BULLISH),
            }
        )
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert detail.grade == SetupGrade.NO_TRADE

    def test_no_trade_when_no_draw_on_liquidity(self):
        lm = full_liquidity_map(draw_on_liquidity=None)
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert detail.grade == SetupGrade.NO_TRADE

    def test_conditions_met_count_correct(self):
        lm = full_liquidity_map()
        detail = SetupGrader().grade(lm, LONDON_TS)
        booleans = [
            detail.htf_bias_confirmed,
            detail.draw_on_liquidity_identified,
            detail.liquidity_sweep_confirmed,
            detail.displacement_present,
            detail.cisd_confirmed,
            detail.entry_pd_array_present,
            detail.stop_placement_valid,
            detail.time_window_aligned,
        ]
        assert detail.conditions_met == sum(booleans)

    def test_grade_reason_nonempty(self):
        for lm, timestamp in (
            (full_liquidity_map(), LONDON_TS),
            (full_liquidity_map(draw_on_liquidity=None), OFF_HOURS_TS),
            (full_liquidity_map(pd_arrays=[]), OFF_HOURS_TS),
        ):
            detail = SetupGrader().grade(lm, timestamp)
            assert detail.grade_reason != ""


class TestConditionChecks:
    def test_check_htf_bias_true(self):
        lm = full_liquidity_map()
        assert SetupGrader()._check_htf_bias(lm) is True

    def test_check_htf_bias_false_when_neutral(self):
        lm = full_liquidity_map(
            htf_bias={
                Timeframe.D1.value: make_bias(Timeframe.D1, BiasDirection.NEUTRAL),
                Timeframe.W1.value: make_bias(Timeframe.W1, BiasDirection.BULLISH),
            }
        )
        assert SetupGrader()._check_htf_bias(lm) is False

    def test_check_draw_on_liquidity_true(self):
        lm = full_liquidity_map()
        assert SetupGrader()._check_draw_on_liquidity(lm) is True

    def test_check_liquidity_sweep_true(self):
        lm = full_liquidity_map(sweep_detected=True)
        assert SetupGrader()._check_liquidity_sweep(lm) is True

    def test_check_time_window_london(self):
        assert SetupGrader()._check_time_window(full_liquidity_map(), LONDON_TS) is True

    def test_check_time_window_ny_am(self):
        assert SetupGrader()._check_time_window(full_liquidity_map(), NY_AM_TS) is True

    def test_check_time_window_ny_pm(self):
        assert SetupGrader()._check_time_window(full_liquidity_map(), NY_PM_TS) is True

    def test_check_time_window_off_hours(self):
        assert SetupGrader()._check_time_window(full_liquidity_map(), OFF_HOURS_TS) is False


class TestSuggestedEntryAndStop:
    def test_suggested_entry_golden_level_when_ote(self):
        ote_zone = OTEZone(
            fib_62=100.8, fib_705=100.7, fib_79=100.6, ote_low=100.6, ote_high=100.8,
            golden_level=100.7, price_in_ote=True, displacement_leg_high=101.0, displacement_leg_low=100.5,
        )
        entry_array = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 100.9, 100.65, strength_score=0.95)
        lm = full_liquidity_map(pd_arrays=[entry_array], ote_zone=ote_zone)
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert detail.suggested_entry == ote_zone.golden_level

    def test_suggested_entry_array_midpoint_when_not_ote(self):
        entry_array = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, strength_score=0.95)
        lm = full_liquidity_map(pd_arrays=[entry_array], ote_zone=None)
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert detail.suggested_entry == (101.0 + 100.0) / 2

    def test_suggested_stop_below_array_low_bullish(self):
        entry_array = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, strength_score=0.95)
        lm = full_liquidity_map(pd_arrays=[entry_array])
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert detail.suggested_stop < 100.0

    def test_suggested_stop_above_array_high_bearish(self):
        entry_array = make_pdarray(PDArrayType.OB, BiasDirection.BEARISH, 101.0, 100.0, strength_score=0.95)
        lm = full_liquidity_map(pd_arrays=[entry_array])
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert detail.suggested_stop > 101.0


class TestGradeReasonContent:
    def test_grade_reason_mentions_structure_confirmed_when_true(self):
        entry_array = make_pdarray(
            PDArrayType.BREAKER, BiasDirection.BULLISH, 101.0, 100.0, structure_confirmed=True, strength_score=0.95
        )
        lm = full_liquidity_map(pd_arrays=[entry_array, make_pdarray(PDArrayType.OB, BiasDirection.BULLISH, 100.5, 100.1)])
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert "structure-confirmed" in detail.grade_reason

    def test_conditions_met_unaffected_by_structure_confirmed(self):
        entry_confirmed = make_pdarray(
            PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, structure_confirmed=True, strength_score=0.95
        )
        entry_unconfirmed = make_pdarray(
            PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, structure_confirmed=False, strength_score=0.95
        )
        ob = make_pdarray(PDArrayType.OB, BiasDirection.BULLISH, 100.5, 100.1)
        detail_confirmed = SetupGrader().grade(full_liquidity_map(pd_arrays=[entry_confirmed, ob]), LONDON_TS)
        detail_unconfirmed = SetupGrader().grade(full_liquidity_map(pd_arrays=[entry_unconfirmed, ob]), LONDON_TS)
        assert detail_confirmed.conditions_met == detail_unconfirmed.conditions_met
        assert detail_confirmed.grade == detail_unconfirmed.grade

    def test_grade_reason_may_reference_equilibrium(self):
        candle = Candle(
            timestamp=ts(0), open=100.0, high=101.0, low=99.0, close=100.5,
            timeframe=Timeframe.M5, instrument="EURUSD",
        )
        fractal_model = FractalModelResult(
            key_level=100.0,
            steps=[FractalCandleStep(step_number=1, candle=candle, closure_type=None)],
            range_high=101.0,
            range_low=99.0,
            equilibrium=100.0,
            price_above_equilibrium=True,
        )
        lm = full_liquidity_map(fractal_model=fractal_model)
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert "equilibrium" in detail.grade_reason.lower()


@st.composite
def _boolean_8tuple(draw):
    return tuple(draw(st.booleans()) for _ in range(8))


class TestPropertyBasedTests:
    @settings(max_examples=100)
    @given(flags=_boolean_8tuple())
    def test_property_setup_grade_conditions_met_accuracy(self, flags):
        """Property 15: conditions_met always equals the sum of the 8 booleans."""
        (
            htf_bias, draw, sweep, displacement, cisd, entry, stop, time_window,
        ) = flags
        pd_arrays = []
        if entry or stop:
            pd_arrays.append(make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, is_filled=not entry))
        if displacement:
            pd_arrays.append(make_pdarray(PDArrayType.OB, BiasDirection.BULLISH, 100.5, 100.1))
        lm = full_liquidity_map(
            htf_bias={
                Timeframe.D1.value: make_bias(Timeframe.D1, BiasDirection.BULLISH if htf_bias else BiasDirection.NEUTRAL),
                Timeframe.W1.value: make_bias(Timeframe.W1, BiasDirection.BULLISH if htf_bias else BiasDirection.NEUTRAL),
            },
            draw_on_liquidity=make_level() if draw else None,
            sweep_detected=sweep,
            cisd_cascade=CISDCascadeStatus(cascade_valid=cisd, cascade_chain=[]),
            pd_arrays=pd_arrays,
        )
        timestamp = LONDON_TS if time_window else OFF_HOURS_TS
        detail = SetupGrader().grade(lm, timestamp)
        expected = sum(
            (
                detail.htf_bias_confirmed,
                detail.draw_on_liquidity_identified,
                detail.liquidity_sweep_confirmed,
                detail.displacement_present,
                detail.cisd_confirmed,
                detail.entry_pd_array_present,
                detail.stop_placement_valid,
                detail.time_window_aligned,
            )
        )
        assert detail.conditions_met == expected

    def test_property_aplus_requires_all_8_conditions(self):
        """Property 16: A+ if and only if conditions_met == 8."""
        for missing_field, override in (
            ("sweep", dict(sweep_detected=False)),
            ("cisd", dict(cisd_cascade=CISDCascadeStatus(cascade_valid=False, cascade_chain=[]))),
        ):
            lm = full_liquidity_map(**override)
            detail = SetupGrader().grade(lm, LONDON_TS)
            assert detail.conditions_met < 8
            assert detail.grade != SetupGrade.A_PLUS

        detail_full = SetupGrader().grade(full_liquidity_map(), LONDON_TS)
        assert detail_full.conditions_met == 8
        assert detail_full.grade == SetupGrade.A_PLUS

    def test_property_no_trade_when_conditions_below_threshold(self):
        """Property 17: conditions_met < 6 always yields NO_TRADE."""
        lm = full_liquidity_map(
            pd_arrays=[],
            cisd_cascade=CISDCascadeStatus(cascade_valid=False, cascade_chain=[]),
            sweep_detected=False,
        )
        detail = SetupGrader().grade(lm, OFF_HOURS_TS)
        assert detail.conditions_met < 6
        assert detail.grade == SetupGrade.NO_TRADE
