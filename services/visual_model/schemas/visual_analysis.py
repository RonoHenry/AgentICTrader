"""
VisualAnalysis output schema for the Visual Model service.

The structured result of a single VLM chart-reasoning call. Vocabulary is
constrained to match the numerical engine's own terminology:
- crt phases use the same five values pd_array_engine.ipda.classifier
  .classify_crt_phase() can return (C1-C4/UNKNOWN) - no AMD, no sixth
  "reversal"/"retracement" value (see .kiro/specs/visual-model/design.md,
  Non-Goals: AMDX/X is deferred).
- structure section asks about BOS/CHoCH, not MSS, matching
  pd_array_engine.models.StructureEventType.

**Validates: Requirements 6.1-6.7 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CRTPhaseLiteral(str, Enum):
    """The same five values pd_array_engine.ipda.classifier.classify_crt_phase()
    can return. No REVERSAL/RETRACEMENT value - see Non-Goals in design.md."""

    C1_ACCUMULATION = "C1_ACCUMULATION"
    C2_MANIPULATION = "C2_MANIPULATION"
    C3_DISTRIBUTION = "C3_DISTRIBUTION"
    C4_CONTINUATION = "C4_CONTINUATION"
    UNKNOWN = "UNKNOWN"


class StructureSection(BaseModel):
    h4_direction: Literal["BULLISH", "BEARISH", "RANGING"]
    h4_bos_visible: bool
    h4_bos_description: str
    h1_direction: Literal["BULLISH", "BEARISH", "RANGING"]
    h1_choch_visible: bool
    h1_choch_description: str
    structure_clarity_score: float = Field(ge=0.0, le=10.0)


class DealingRangeSection(BaseModel):
    range_visible: bool
    price_position: Literal["PREMIUM", "DISCOUNT", "AT_EQUILIBRIUM"]
    bsl_pools_visible: bool
    bsl_description: str
    ssl_pools_visible: bool
    ssl_description: str
    liquidity_sweep_confirmed: bool
    sweep_description: str


class CRTSection(BaseModel):
    h4_phase: CRTPhaseLiteral
    h4_phase_description: str
    h1_phase: CRTPhaseLiteral
    h1_phase_description: str
    m15_phase: CRTPhaseLiteral
    m15_phase_description: str
    manipulation_complete: bool
    manipulation_evidence: str


class DisplacementCandle(BaseModel):
    visual_dominance: float = Field(ge=0.0, le=10.0)
    body_appears_large: bool
    wicks_minimal: bool
    closes_beyond_structure: bool
    description: str


class OrderBlockRead(BaseModel):
    identifiable: bool
    ambiguity: Literal["UNAMBIGUOUS", "MINOR", "SIGNIFICANT"]
    description: str


class IFVGRead(BaseModel):
    visible: bool
    gap_obvious: bool
    ce_approximate: str
    description: str


class CISDSection(BaseModel):
    detected: bool
    direction: Literal["BEARISH", "BULLISH", "NONE"]
    displacement_candle: DisplacementCandle
    order_block: OrderBlockRead
    ifvg: IFVGRead


class M5PrecisionSection(BaseModel):
    ob_visible_at_ce: bool
    ob_ifvg_confluence: bool
    m5_cisd_nested: bool
    description: str


class FractalSection(BaseModel):
    coherence_score: float = Field(ge=0.0, le=10.0)
    amd_phases_aligned: bool
    perceived_depth: int = Field(ge=1, le=4)
    description: str


class QualitySection(BaseModel):
    overall_score: float = Field(ge=0.0, le=10.0)
    strongest_element: str
    biggest_weakness: str
    take_this_trade: bool
    conviction_level: Literal["MAXIMUM", "HIGH", "MEDIUM", "LOW", "DO_NOT_TAKE"]


class VisualInsightsSection(BaseModel):
    what_numbers_miss: str
    visual_warnings: str
    narrative: str


class VisualAnalysis(BaseModel):
    instrument: str
    analysis_timestamp: datetime
    structure: StructureSection
    dealing_range: DealingRangeSection
    crt: CRTSection
    cisd: CISDSection
    m5_precision: M5PrecisionSection
    fractal: FractalSection
    quality: QualitySection
    visual_insights: VisualInsightsSection
