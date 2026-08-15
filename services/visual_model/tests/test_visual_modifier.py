"""
TDD - Task 169: fusion/visual_modifier.py.

RED phase: bounded modifier computation and hard-block detection
(direction conflict, active C2_MANIPULATION).

**Validates: Requirements 7.1-7.6 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from hypothesis import given, settings as hyp_settings, strategies as st

from services.visual_model.fusion.visual_modifier import compute_visual_modifier
from services.visual_model.schemas.visual_analysis import (
    CISDSection,
    CRTPhaseLiteral,
    CRTSection,
    DealingRangeSection,
    DisplacementCandle,
    FractalSection,
    IFVGRead,
    M5PrecisionSection,
    OrderBlockRead,
    QualitySection,
    StructureSection,
    VisualAnalysis,
    VisualInsightsSection,
)


def _build_analysis(
    overall_score: float = 5.0,
    coherence_score: float = 5.0,
    structure_clarity_score: float = 5.0,
    cisd_direction: str = "NONE",
    m15_phase: CRTPhaseLiteral = CRTPhaseLiteral.C3_DISTRIBUTION,
) -> VisualAnalysis:
    return VisualAnalysis(
        instrument="XAUUSD",
        analysis_timestamp=datetime.now(timezone.utc),
        structure=StructureSection(
            h4_direction="BEARISH",
            h4_bos_visible=True,
            h4_bos_description="x",
            h1_direction="BEARISH",
            h1_choch_visible=True,
            h1_choch_description="x",
            structure_clarity_score=structure_clarity_score,
        ),
        dealing_range=DealingRangeSection(
            range_visible=True,
            price_position="PREMIUM",
            bsl_pools_visible=True,
            bsl_description="x",
            ssl_pools_visible=False,
            ssl_description="x",
            liquidity_sweep_confirmed=True,
            sweep_description="x",
        ),
        crt=CRTSection(
            h4_phase=CRTPhaseLiteral.C3_DISTRIBUTION,
            h4_phase_description="x",
            h1_phase=CRTPhaseLiteral.C3_DISTRIBUTION,
            h1_phase_description="x",
            m15_phase=m15_phase,
            m15_phase_description="x",
            manipulation_complete=True,
            manipulation_evidence="x",
        ),
        cisd=CISDSection(
            detected=cisd_direction != "NONE",
            direction=cisd_direction,
            displacement_candle=DisplacementCandle(
                visual_dominance=8.0,
                body_appears_large=True,
                wicks_minimal=True,
                closes_beyond_structure=True,
                description="x",
            ),
            order_block=OrderBlockRead(identifiable=True, ambiguity="UNAMBIGUOUS", description="x"),
            ifvg=IFVGRead(visible=True, gap_obvious=True, ce_approximate="x", description="x"),
        ),
        m5_precision=M5PrecisionSection(
            ob_visible_at_ce=True, ob_ifvg_confluence=True, m5_cisd_nested=True, description="x"
        ),
        fractal=FractalSection(
            coherence_score=coherence_score, amd_phases_aligned=True, perceived_depth=3, description="x"
        ),
        quality=QualitySection(
            overall_score=overall_score,
            strongest_element="x",
            biggest_weakness="x",
            take_this_trade=True,
            conviction_level="HIGH",
        ),
        visual_insights=VisualInsightsSection(
            what_numbers_miss="x", visual_warnings="x", narrative="x"
        ),
    )


class TestVisualCompositeFormula:
    def test_visual_composite_formula(self) -> None:
        analysis = _build_analysis(
            overall_score=10.0, coherence_score=10.0, structure_clarity_score=10.0
        )
        modifier, _ = compute_visual_modifier(analysis, numerical_direction=None)
        assert modifier == 0.15  # max quality clamps to the upper bound

    def test_modifier_formula_and_clamping(self) -> None:
        analysis = _build_analysis(overall_score=0.0, coherence_score=0.0, structure_clarity_score=0.0)
        modifier, _ = compute_visual_modifier(analysis, numerical_direction=None)
        assert modifier == -0.15

        analysis_mid = _build_analysis(
            overall_score=5.0, coherence_score=5.0, structure_clarity_score=5.0
        )
        modifier_mid, _ = compute_visual_modifier(analysis_mid, numerical_direction=None)
        assert abs(modifier_mid) < 1e-9


class TestHardBlocks:
    def test_direction_conflict_returns_hard_block_reason(self) -> None:
        analysis = _build_analysis(cisd_direction="BULLISH")
        _, reason = compute_visual_modifier(analysis, numerical_direction="BEARISH")
        assert reason is not None
        assert "conflict" in reason.lower()

    def test_no_direction_conflict_when_visual_direction_none(self) -> None:
        analysis = _build_analysis(cisd_direction="NONE")
        _, reason = compute_visual_modifier(analysis, numerical_direction="BEARISH")
        assert reason is None

    def test_no_direction_conflict_when_directions_agree(self) -> None:
        analysis = _build_analysis(cisd_direction="BEARISH")
        _, reason = compute_visual_modifier(analysis, numerical_direction="BEARISH")
        assert reason is None

    def test_c2_manipulation_returns_hard_block_reason(self) -> None:
        analysis = _build_analysis(m15_phase=CRTPhaseLiteral.C2_MANIPULATION)
        _, reason = compute_visual_modifier(analysis, numerical_direction=None)
        assert reason is not None
        assert "manipulation" in reason.lower() or "C2_MANIPULATION" in reason

    def test_no_hard_block_when_neither_condition_met_returns_zero_none(self) -> None:
        analysis = _build_analysis(
            overall_score=5.0,
            coherence_score=5.0,
            structure_clarity_score=5.0,
            cisd_direction="NONE",
            m15_phase=CRTPhaseLiteral.C3_DISTRIBUTION,
        )
        modifier, reason = compute_visual_modifier(analysis, numerical_direction="BEARISH")
        assert reason is None
        assert abs(modifier) < 1e-9


class TestNeverRaises:
    @hyp_settings(max_examples=50, deadline=None)
    @given(
        overall=st.floats(min_value=0.0, max_value=10.0),
        coherence=st.floats(min_value=0.0, max_value=10.0),
        clarity=st.floats(min_value=0.0, max_value=10.0),
        cisd_direction=st.sampled_from(["BEARISH", "BULLISH", "NONE"]),
        numerical_direction=st.sampled_from(["BEARISH", "BULLISH", None]),
        m15_phase=st.sampled_from(list(CRTPhaseLiteral)),
    )
    def test_never_raises_on_any_structurally_valid_input(
        self, overall, coherence, clarity, cisd_direction, numerical_direction, m15_phase
    ) -> None:
        analysis = _build_analysis(
            overall_score=overall,
            coherence_score=coherence,
            structure_clarity_score=clarity,
            cisd_direction=cisd_direction,
            m15_phase=m15_phase,
        )
        modifier, reason = compute_visual_modifier(analysis, numerical_direction=numerical_direction)
        assert isinstance(modifier, float)
        assert reason is None or isinstance(reason, str)

    @hyp_settings(max_examples=100, deadline=None)
    @given(
        overall=st.floats(min_value=0.0, max_value=10.0),
        coherence=st.floats(min_value=0.0, max_value=10.0),
        clarity=st.floats(min_value=0.0, max_value=10.0),
    )
    def test_property_modifier_bounds(self, overall, coherence, clarity) -> None:
        """Property 2: Visual Modifier Bounds."""
        analysis = _build_analysis(
            overall_score=overall, coherence_score=coherence, structure_clarity_score=clarity
        )
        modifier, _ = compute_visual_modifier(analysis, numerical_direction=None)
        assert -0.15 <= modifier <= 0.15
