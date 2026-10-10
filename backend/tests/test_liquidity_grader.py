"""Tests for liquidity_engine.grader.setup_grader.SetupGrader.

Update 2026-10 (task 230, Requirement 18.9-18.14): the grader reads the
setup sequence the engine records. Its array is the entry array, the sweep
condition means a sequence exists and gates any trade, the stop goes behind
the protected swing, and counter-trend setups cap at B.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings, strategies as st

from liquidity_engine.grader.setup_grader import SetupGrader
from liquidity_engine.models import (
    BiasDirection,
    CISDCascadeStatus,
    FractalModelResult,
    FractalCandleStep,
    Candle,
    HTFBias,
    LiquidityLevel,
    LiquidityMap,
    LiquidityPool,
    LiquidityRaid,
    LiquiditySource,
    LiquidityType,
    OTEZone,
    PDArray,
    PDArrayType,
    ProtectedSwing,
    SetupGrade,
    SetupSequence,
    Timeframe,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
NY = ZoneInfo("America/New_York")
_ENTRY_TFS = {Timeframe.M1, Timeframe.M3, Timeframe.M5, Timeframe.M15}


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


def make_sequence(array: PDArray, wick: Optional[float] = None, body: Optional[float] = None,
                  candle_range: float = 1.0) -> SetupSequence:
    """A sequence on ``array``: by default its protected swing sits 0.5 beyond the array's far side
    (body 0.2 beyond), after a raid of an M15 swing on the opposite side."""
    bullish = array.direction == BiasDirection.BULLISH
    if wick is None:
        wick = array.low - 0.5 if bullish else array.high + 0.5
    if body is None:
        body = array.low - 0.2 if bullish else array.high + 0.2
    pool = LiquidityPool(
        side=LiquidityType.SSL if bullish else LiquidityType.BSL,
        source=LiquiditySource.SWING_LOW if bullish else LiquiditySource.SWING_HIGH,
        timeframe=Timeframe.M15, price=wick + (0.3 if bullish else -0.3), formed_at=ts(-6), known_at=ts(-5),
    )
    return SetupSequence(
        entry_array_id=array.array_id,
        direction=array.direction,
        raid=LiquidityRaid(pool=pool, raided_at=ts(-2), reclaimed_at=ts(-2)),
        cisd_at=ts(-1),
        protected_swing=ProtectedSwing(candle_at=ts(-2), wick=wick, body=body, candle_range=candle_range),
        leg_extreme=array.high + 2.0 if bullish else array.low - 2.0,
    )


def _strongest_entry_array(pd_arrays):
    eligible = [a for a in pd_arrays if not a.is_filled and a.timeframe in _ENTRY_TFS]
    return max(eligible, key=lambda a: a.strength_score) if eligible else None


def full_liquidity_map(**overrides) -> LiquidityMap:
    """All 8 SetupGrader conditions satisfied by default; tests override specific fields.

    Unless given, the setup sequence is built on the strongest entry-eligible array
    (None when there is none), and sweep_detected follows it, as the engine sets it."""
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
        ote_zone=None,
        unicorn=None,
        setup_grade=None,
        swing_structure={},
        fractal_model=None,
    )
    defaults.update(overrides)
    if "setup_sequence" not in overrides:
        entry = _strongest_entry_array(defaults["pd_arrays"])
        defaults["setup_sequence"] = make_sequence(entry) if entry is not None else None
    defaults.setdefault("sweep_detected", defaults["setup_sequence"] is not None)
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

    def test_sweep_condition_follows_setup_sequence(self):
        # Requirement 13.4 / 18.4: the sweep is the raid sequence, not the old target-side flag.
        assert SetupGrader()._check_liquidity_sweep(full_liquidity_map()) is True
        no_sequence = full_liquidity_map(setup_sequence=None, sweep_detected=True)
        assert SetupGrader()._check_liquidity_sweep(no_sequence) is False

    def test_check_time_window_london(self):
        assert SetupGrader()._check_time_window(full_liquidity_map(), LONDON_TS) is True

    def test_check_time_window_ny_am(self):
        assert SetupGrader()._check_time_window(full_liquidity_map(), NY_AM_TS) is True

    def test_check_time_window_ny_pm(self):
        assert SetupGrader()._check_time_window(full_liquidity_map(), NY_PM_TS) is True

    def test_check_time_window_off_hours(self):
        assert SetupGrader()._check_time_window(full_liquidity_map(), OFF_HOURS_TS) is False


class TestSweepGate:
    """Requirement 18.9 (LE-D1): no raid sequence, no trade."""

    def test_no_trade_without_setup_sequence(self):
        detail = SetupGrader().grade(full_liquidity_map(setup_sequence=None), LONDON_TS)
        assert detail.grade == SetupGrade.NO_TRADE
        assert not detail.liquidity_sweep_confirmed and not detail.stop_placement_valid
        assert "no opposite-side raid" in detail.grade_reason.lower()
        assert detail.suggested_stop is None and detail.protected_swing_body_stop is None


class TestEntryArrayFromSequence:
    """Requirement 18.10: the entry array is the one the raid sequence produced."""

    def test_entry_array_is_the_sequence_array(self):
        ob = make_pdarray(PDArrayType.OB, BiasDirection.BULLISH, 100.5, 100.0, array_id="m5-ob")
        fvg = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.2, strength_score=0.9, array_id="m5-fvg")
        lm = full_liquidity_map(pd_arrays=[ob, fvg], setup_sequence=make_sequence(ob))
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert detail.entry_array_id == "m5-ob"                     # though the FVG is stronger
        assert (detail.entry_array_high, detail.entry_array_low) == (100.5, 100.0)
        assert detail.suggested_entry == (100.5 + 100.0) / 2


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

    def test_stop_behind_protected_swing_wick_with_buffer(self):
        # Requirement 18.11: wick less 10% of the protected bar's range (bullish); plus it (bearish).
        bull = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, strength_score=0.95)
        lm = full_liquidity_map(pd_arrays=[bull], setup_sequence=make_sequence(bull, wick=99.4, candle_range=0.8))
        assert SetupGrader().grade(lm, LONDON_TS).suggested_stop == pytest.approx(99.4 - 0.08)

        bear = make_pdarray(PDArrayType.OB, BiasDirection.BEARISH, 101.0, 100.0, strength_score=0.95)
        lm = full_liquidity_map(pd_arrays=[bear], setup_sequence=make_sequence(bear, wick=101.6, candle_range=0.5))
        assert SetupGrader().grade(lm, LONDON_TS).suggested_stop == pytest.approx(101.6 + 0.05)

    def test_body_stop_recorded(self):
        bull = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, strength_score=0.95)
        sequence = make_sequence(bull, wick=99.4, body=99.7, candle_range=0.8)
        detail = SetupGrader().grade(full_liquidity_map(pd_arrays=[bull], setup_sequence=sequence), LONDON_TS)
        assert detail.protected_swing_body_stop == pytest.approx(99.7 - 0.08)

    def test_stop_placement_valid_requires_stop_beyond_array(self):
        bull = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, strength_score=0.95)
        ob = make_pdarray(PDArrayType.OB, BiasDirection.BULLISH, 100.5, 100.1)              # displacement
        inside = make_sequence(bull, wick=100.3, body=100.4, candle_range=0.1)    # stop 100.29: inside the array
        detail = SetupGrader().grade(full_liquidity_map(pd_arrays=[bull, ob], setup_sequence=inside), LONDON_TS)
        assert detail.stop_placement_valid is False and detail.conditions_met == 7
        assert SetupGrader().grade(full_liquidity_map(pd_arrays=[bull, ob]), LONDON_TS).stop_placement_valid is True


class TestCounterTrendCap:
    """Requirement 18.13 (LE-D6): an entry array against the D1 bias grades at most B."""

    def test_counter_trend_capped_at_b(self):
        bear = make_pdarray(PDArrayType.OB, BiasDirection.BEARISH, 101.0, 100.0, strength_score=0.95)
        detail = SetupGrader().grade(full_liquidity_map(pd_arrays=[bear]), LONDON_TS)      # D1 is bullish
        assert detail.conditions_met == 8 and detail.grade == SetupGrade.B
        assert detail.counter_trend is True
        assert "counter-trend" in detail.grade_reason.lower()

    def test_aligned_setup_not_capped(self):
        detail = SetupGrader().grade(full_liquidity_map(), LONDON_TS)
        assert detail.grade == SetupGrade.A_PLUS and detail.counter_trend is False
        assert "counter-trend" not in detail.grade_reason.lower()


class TestEntryArrayTimeframeRestriction:
    """HTF PD arrays (D1/W1/H4/...) inform bias and the draw-on-liquidity
    target but must never be selected as the entry array itself — only
    M15-and-below is entry-eligible (see setup_grader._ENTRY_ELIGIBLE_TIMEFRAMES).
    A wide HTF Breaker previously out-ranked a precise LTF FVG purely by
    array-type weight, regardless of timeframe."""

    def test_htf_array_never_selected_as_entry_even_with_higher_strength(self):
        htf_breaker = make_pdarray(
            PDArrayType.BREAKER, BiasDirection.BULLISH, 105.0, 95.0, strength_score=0.99, tf=Timeframe.D1,
        )
        ltf_fvg = make_pdarray(
            PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.2, strength_score=0.5, tf=Timeframe.M5,
        )
        lm = full_liquidity_map(pd_arrays=[htf_breaker, ltf_fvg])
        detail = SetupGrader().grade(lm, LONDON_TS)
        assert detail.suggested_entry == (101.0 + 100.2) / 2

    def test_htf_only_arrays_do_not_satisfy_entry_pd_array_present(self):
        htf_only = make_pdarray(PDArrayType.BREAKER, BiasDirection.BULLISH, 105.0, 95.0, tf=Timeframe.D1)
        lm = full_liquidity_map(pd_arrays=[htf_only])
        assert SetupGrader()._check_entry_pd_array(lm) is False

    def test_h1_array_does_not_satisfy_entry_pd_array_present(self):
        # M15-and-below only — H1 is HTF-side for this purpose, same as H4/D1/W1.
        h1_only = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, tf=Timeframe.H1)
        lm = full_liquidity_map(pd_arrays=[h1_only])
        assert SetupGrader()._check_entry_pd_array(lm) is False

    def test_m15_array_satisfies_entry_pd_array_present(self):
        m15_only = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, tf=Timeframe.M15)
        lm = full_liquidity_map(pd_arrays=[m15_only])
        assert SetupGrader()._check_entry_pd_array(lm) is True

    def test_b_grade_breaker_exclusion_scoped_to_ltf(self):
        # An HTF Breaker sitting alongside an LTF FVG must not disqualify B
        # grade — only a Breaker in the entry-eligible pool should.
        htf_breaker = make_pdarray(PDArrayType.BREAKER, BiasDirection.BULLISH, 105.0, 95.0, tf=Timeframe.D1)
        ltf_fvg = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.2, tf=Timeframe.M5)
        lm = full_liquidity_map(pd_arrays=[htf_breaker, ltf_fvg])
        detail = SetupGrader().grade(lm, OFF_HOURS_TS)
        assert detail.grade == SetupGrade.B


class TestEntryArrayId:
    """The grade carries the selected entry array's id, so a setup keeps
    one identity while the same array stays selected (AlgoBacktester task
    189, Requirement 1.3)."""

    def test_grade_detail_carries_selected_entry_array_id(self):
        # The D1 Breaker out-scores both, but only M15-and-below can be the entry.
        htf_breaker = make_pdarray(
            PDArrayType.BREAKER, BiasDirection.BULLISH, 105.0, 95.0, strength_score=0.99,
            tf=Timeframe.D1, array_id="d1-breaker",
        )
        ob = make_pdarray(PDArrayType.OB, BiasDirection.BULLISH, 100.5, 100.0, array_id="m5-ob")
        fvg = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.2, strength_score=0.9, array_id="m5-fvg")
        lm = full_liquidity_map(pd_arrays=[htf_breaker, ob, fvg])

        detail = SetupGrader().grade(lm, LONDON_TS)

        assert detail.entry_array_id == "m5-fvg"
        assert (detail.entry_array_high, detail.entry_array_low) == (101.0, 100.2)

    def test_entry_array_id_none_without_entry_array(self):
        filled = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.2, is_filled=True)
        htf_only = make_pdarray(PDArrayType.BREAKER, BiasDirection.BULLISH, 105.0, 95.0, tf=Timeframe.D1)
        lm = full_liquidity_map(pd_arrays=[filled, htf_only])

        detail = SetupGrader().grade(lm, LONDON_TS)

        assert detail.entry_array_id is None
        assert detail.suggested_entry is None


class TestGradeReasonContent:
    def test_grade_reason_names_raid_and_protected_swing(self):
        # The default sequence: an M15 swing low at 100.0 raided, its protected swing at 99.7.
        reason = SetupGrader().grade(full_liquidity_map(), LONDON_TS).grade_reason
        assert "Raid of SWING_LOW (M15) at 100;" in reason and "protected swing 99.7" in reason

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
        entry_array = None
        if entry or stop:
            entry_array = make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, is_filled=not entry)
            pd_arrays.append(entry_array)
        if displacement:
            pd_arrays.append(make_pdarray(PDArrayType.OB, BiasDirection.BULLISH, 100.5, 100.1))
        lm = full_liquidity_map(
            htf_bias={
                Timeframe.D1.value: make_bias(Timeframe.D1, BiasDirection.BULLISH if htf_bias else BiasDirection.NEUTRAL),
                Timeframe.W1.value: make_bias(Timeframe.W1, BiasDirection.BULLISH if htf_bias else BiasDirection.NEUTRAL),
            },
            draw_on_liquidity=make_level() if draw else None,
            setup_sequence=make_sequence(entry_array) if sweep and entry and entry_array is not None else None,
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
            ("sweep", dict(setup_sequence=None)),
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
        )
        detail = SetupGrader().grade(lm, OFF_HOURS_TS)
        assert detail.conditions_met < 6
        assert detail.grade == SetupGrade.NO_TRADE

    @settings(max_examples=100)
    @given(flags=_boolean_8tuple(), bullish_d1=st.booleans())
    def test_property_sweep_gate(self, flags, bullish_d1):
        """Property 29: without a setup sequence the grade is NO_TRADE, whatever else holds."""
        htf_bias, draw, _, displacement, cisd, entry, _, time_window = flags
        d1 = BiasDirection.BULLISH if bullish_d1 else BiasDirection.BEARISH
        pd_arrays = [make_pdarray(PDArrayType.FVG, BiasDirection.BULLISH, 101.0, 100.0, is_filled=not entry)]
        if displacement:
            pd_arrays.append(make_pdarray(PDArrayType.OB, BiasDirection.BULLISH, 100.5, 100.1))
        lm = full_liquidity_map(
            htf_bias={Timeframe.D1.value: make_bias(Timeframe.D1, d1 if htf_bias else BiasDirection.NEUTRAL),
                      Timeframe.W1.value: make_bias(Timeframe.W1, d1)},
            draw_on_liquidity=make_level() if draw else None, setup_sequence=None, sweep_detected=True,
            cisd_cascade=CISDCascadeStatus(cascade_valid=cisd, cascade_chain=[]), pd_arrays=pd_arrays,
        )
        assert SetupGrader().grade(lm, LONDON_TS if time_window else OFF_HOURS_TS).grade == SetupGrade.NO_TRADE

    @settings(max_examples=100)
    @given(flags=_boolean_8tuple(), array_bullish=st.booleans(), d1_bullish=st.booleans())
    def test_property_counter_trend_cap(self, flags, array_bullish, d1_bullish):
        """Property 30: an entry array against the D1 bias never grades above B."""
        _, draw, _, displacement, cisd, _, _, time_window = flags
        direction = BiasDirection.BULLISH if array_bullish else BiasDirection.BEARISH
        d1 = BiasDirection.BULLISH if d1_bullish else BiasDirection.BEARISH
        entry = make_pdarray(PDArrayType.FVG, direction, 101.0, 100.0, strength_score=0.9)
        pd_arrays = [entry] + ([make_pdarray(PDArrayType.OB, direction, 100.5, 100.1)] if displacement else [])
        lm = full_liquidity_map(
            htf_bias={Timeframe.D1.value: make_bias(Timeframe.D1, d1), Timeframe.W1.value: make_bias(Timeframe.W1, d1)},
            draw_on_liquidity=make_level() if draw else None, pd_arrays=pd_arrays,
            cisd_cascade=CISDCascadeStatus(cascade_valid=cisd, cascade_chain=[]),
        )
        detail = SetupGrader().grade(lm, LONDON_TS if time_window else OFF_HOURS_TS)
        assert detail.counter_trend == (direction != d1)
        if direction != d1:
            assert detail.grade in (SetupGrade.B, SetupGrade.NO_TRADE)

    @settings(max_examples=200)
    @given(st.booleans(), st.floats(0.0, 3.0), st.floats(0.0, 3.0), st.one_of(st.just(0.0), st.floats(0.01, 2.0)))
    def test_property_protected_swing_ordering(self, bullish, wick_gap, body_gap, candle_range):
        """Property 31: wick at or beyond body; the wick stop at or beyond the wick (strictly when the bar
        has range) and at or beyond the body stop; valid placement exactly when beyond the array's far side."""
        direction = BiasDirection.BULLISH if bullish else BiasDirection.BEARISH
        array = make_pdarray(PDArrayType.FVG, direction, 101.0, 100.0, strength_score=0.9)
        sign = -1 if bullish else 1                                # beyond = lower for bullish, higher for bearish
        far = array.low if bullish else array.high
        body = far + sign * body_gap - sign * 0.5                  # anywhere around the far side
        wick = body + sign * wick_gap
        sequence = make_sequence(array, wick=wick, body=body, candle_range=candle_range)
        detail = SetupGrader().grade(full_liquidity_map(pd_arrays=[array], setup_sequence=sequence), LONDON_TS)
        stop, body_stop = detail.suggested_stop, detail.protected_swing_body_stop
        beyond = (lambda a, b: a < b) if bullish else (lambda a, b: a > b)
        assert not beyond(body, wick) or body == wick
        assert stop == wick or beyond(stop, wick)
        assert beyond(stop, wick) == (candle_range > 0)
        assert stop == body_stop or beyond(stop, body_stop)
        assert detail.stop_placement_valid == beyond(stop, far)
