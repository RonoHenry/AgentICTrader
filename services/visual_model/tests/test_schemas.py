"""
TDD - Task 163: VisualAnalysis Pydantic schemas.

RED phase: assert the VisualAnalysis output schema, its CRT-phase vocabulary
(matching liquidity_engine's classify_crt_phase(), not the original AMD/MSS
draft), and score-field bounds.
GREEN phase: implementation in services/visual_model/schemas/visual_analysis.py
and services/visual_model/api/schemas.py satisfies all assertions.

**Validates: Requirements 6.1-6.7 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

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
from services.visual_model.api.schemas import VisualAnalysisResponse


def _build_valid_visual_analysis() -> VisualAnalysis:
    return VisualAnalysis(
        instrument="XAUUSD",
        analysis_timestamp=datetime.now(timezone.utc),
        structure=StructureSection(
            h4_direction="BEARISH",
            h4_bos_visible=True,
            h4_bos_description="Clean break below the prior swing low.",
            h1_direction="BEARISH",
            h1_choch_visible=True,
            h1_choch_description="CHoCH confirmed on the retest candle.",
            structure_clarity_score=8.5,
        ),
        dealing_range=DealingRangeSection(
            range_visible=True,
            price_position="PREMIUM",
            bsl_pools_visible=True,
            bsl_description="Equal highs at the session open.",
            ssl_pools_visible=False,
            ssl_description="No clear SSL pool visible.",
            liquidity_sweep_confirmed=True,
            sweep_description="Wick swept the equal highs and closed back inside.",
        ),
        crt=CRTSection(
            h4_phase=CRTPhaseLiteral.C3_DISTRIBUTION,
            h4_phase_description="Strong directional expansion candle.",
            h1_phase=CRTPhaseLiteral.C3_DISTRIBUTION,
            h1_phase_description="Follow-through in the same direction.",
            m15_phase=CRTPhaseLiteral.C4_CONTINUATION,
            m15_phase_description="Continuation candles after the initial move.",
            manipulation_complete=True,
            manipulation_evidence="Sweep wick rejected and closed back inside range.",
        ),
        cisd=CISDSection(
            detected=True,
            direction="BEARISH",
            displacement_candle=DisplacementCandle(
                visual_dominance=9.0,
                body_appears_large=True,
                wicks_minimal=True,
                closes_beyond_structure=True,
                description="Displacement candle dwarfs its neighbours.",
            ),
            order_block=OrderBlockRead(
                identifiable=True,
                ambiguity="UNAMBIGUOUS",
                description="Single clear up-close candle before the drop.",
            ),
            ifvg=IFVGRead(
                visible=True,
                gap_obvious=True,
                ce_approximate="around the midpoint of the displacement gap",
                description="Clear gap between the OB candle and the next candle.",
            ),
        ),
        m5_precision=M5PrecisionSection(
            ob_visible_at_ce=True,
            ob_ifvg_confluence=True,
            m5_cisd_nested=True,
            description="M5 OB aligns with the M15 IFVG CE level.",
        ),
        fractal=FractalSection(
            coherence_score=8.0,
            amd_phases_aligned=True,
            perceived_depth=3,
            description="H4/H1/M15 tell the same story at different scales.",
        ),
        quality=QualitySection(
            overall_score=8.5,
            strongest_element="Unambiguous displacement candle and OB.",
            biggest_weakness="SSL pool not clearly visible.",
            take_this_trade=True,
            conviction_level="HIGH",
        ),
        visual_insights=VisualInsightsSection(
            what_numbers_miss="The visual dominance of the displacement candle.",
            visual_warnings="None significant.",
            narrative="Clean bearish CISD with strong fractal coherence.",
        ),
    )


class TestVisualAnalysisConstruction:
    def test_visual_analysis_valid_construction(self) -> None:
        analysis = _build_valid_visual_analysis()
        assert analysis.instrument == "XAUUSD"
        assert analysis.cisd.direction == "BEARISH"
        assert analysis.quality.conviction_level == "HIGH"


class TestCRTPhaseVocabulary:
    """Property 10: CRT Vocabulary Consistency."""

    def test_crt_phase_literal_five_values(self) -> None:
        values = {member.value for member in CRTPhaseLiteral}
        assert values == {
            "C1_ACCUMULATION",
            "C2_MANIPULATION",
            "C3_DISTRIBUTION",
            "C4_CONTINUATION",
            "UNKNOWN",
        }

    def test_crt_phase_literal_rejects_reversal(self) -> None:
        with pytest.raises(ValueError):
            CRTPhaseLiteral("REVERSAL")
        with pytest.raises(ValueError):
            CRTPhaseLiteral("RETRACEMENT")


class TestStructureSectionUsesChochNotMss:
    def test_structure_section_uses_choch_not_mss(self) -> None:
        fields = StructureSection.model_fields
        assert "h1_choch_visible" in fields
        assert "h1_choch_description" in fields
        assert not any("mss" in name.lower() for name in fields)


class TestScoreFieldBounds:
    def test_score_fields_reject_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            StructureSection(
                h4_direction="BEARISH",
                h4_bos_visible=True,
                h4_bos_description="x",
                h1_direction="BEARISH",
                h1_choch_visible=True,
                h1_choch_description="x",
                structure_clarity_score=10.5,
            )
        with pytest.raises(ValidationError):
            FractalSection(
                coherence_score=-1.0,
                amd_phases_aligned=True,
                perceived_depth=1,
                description="x",
            )
        with pytest.raises(ValidationError):
            QualitySection(
                overall_score=11.0,
                strongest_element="x",
                biggest_weakness="x",
                take_this_trade=True,
                conviction_level="HIGH",
            )
        with pytest.raises(ValidationError):
            DisplacementCandle(
                visual_dominance=-0.5,
                body_appears_large=True,
                wicks_minimal=True,
                closes_beyond_structure=True,
                description="x",
            )


class TestVisualAnalysisResponseDefaults:
    def test_visual_analysis_response_defaults(self) -> None:
        response = VisualAnalysisResponse(
            analysis=None, visual_modifier=0.0, hard_block_reason=None
        )
        assert response.degraded is False

    def test_visual_analysis_response_with_analysis(self) -> None:
        response = VisualAnalysisResponse(
            analysis=_build_valid_visual_analysis(),
            visual_modifier=0.08,
            hard_block_reason=None,
        )
        assert response.degraded is False
        assert response.analysis is not None
        assert response.analysis.quality.overall_score == 8.5
