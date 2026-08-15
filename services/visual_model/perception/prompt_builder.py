"""
ICT-specific prompt construction for the VLM chart-reasoning call.

Vocabulary is constrained to match this codebase's own terminology, not the
original draft's AMD/MSS framing (see .kiro/specs/visual-model/design.md,
Non-Goals):
- Asks about BOS and CHoCH (liquidity_engine.models.StructureEventType),
  never MSS.
- Offers exactly the five CRTPhaseLiteral values
  (liquidity_engine.ipda.classifier.classify_crt_phase() can never return a
  sixth "reversal"/"retracement" phase), never AMD's six-value set.

**Validates: Requirements 4.1-4.5 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

from services.visual_model.schemas.visual_analysis import CRTPhaseLiteral

_CRT_PHASE_VALUES = ", ".join(member.value for member in CRTPhaseLiteral)


def build_system_prompt(
    instrument: str,
    timestamp: str,
    session: str,
    kill_zone: str,
) -> str:
    return f"""You are an expert ICT (Inner Circle Trader) price action analyst with
years of screen time executing the Sniper Series methodology. You perceive
price action through the ICT lens: CISD events, PD Arrays, CRT phases,
fractal structure, liquidity, and dealing ranges.

You are looking at a 2x2 candlestick chart grid showing {instrument} at a
specific moment in time:
- TOP LEFT: H4 timeframe (macro context)
- TOP RIGHT: H1 timeframe (intermediate structure)
- BOTTOM LEFT: M15 timeframe (model confirmation - where CISD fires)
- BOTTOM RIGHT: M5 timeframe (precision entry level)

Time of analysis: {timestamp}
Session: {session}
Kill Zone: {kill_zone}
Instrument: {instrument}

Your analysis must be PRECISE and VISUAL. Reference specific candles and
zones you can SEE in the chart. Do not infer from context - only describe
what is visually present."""


def build_user_prompt() -> str:
    return f"""Analyse this chart grid through the strict ICT Sniper Series lens.

Answer each section precisely:

SECTION 1 - MARKET STRUCTURE (H4 and H1)
- What is the clear structural direction on H4? (BULLISH / BEARISH / RANGING)
- Is there a visible BOS (Break of Structure) on H4? Describe it.
- What is the structural direction on H1?
- Is there a visible CHoCH (Change of Character) on H1? Describe which
  candle caused it.
- How CLEAN is the structure? (0-10 where 10 = textbook unambiguous)

SECTION 2 - DEALING RANGE AND LIQUIDITY
- Can you identify a clear dealing range (high and low) on H4 or H1?
- Is price currently in PREMIUM (above 50% of range), DISCOUNT (below 50%),
  or AT_EQUILIBRIUM?
- Can you see visible BSL pools (equal highs, swing highs)? Where?
- Can you see visible SSL pools (equal lows, swing lows)? Where?
- Has there been a liquidity sweep? Describe the wick that swept the level
  and whether it closed back inside.

SECTION 3 - CRT PHASE IDENTIFICATION
- H4: what CRT phase is visually present? Choose exactly one of:
  {_CRT_PHASE_VALUES}
  Describe what you SEE that indicates this phase.
- H1: what CRT phase, from the same five values?
- M15: what CRT phase, from the same five values?
- Is there visual evidence that manipulation (C2_MANIPULATION) has
  completed? (A wick sweep that rejected and closed back inside)

SECTION 4 - CISD ANALYSIS (M15 - most critical)
- Is there a visible CISD (Change in State of Delivery) on M15?
- Describe the DISPLACEMENT CANDLE: body size vs neighbours, wick minimality,
  whether it closes beyond a structural level, whether it is visually
  DOMINANT or merely adequate.
- Identify the ORDER BLOCK: which candle immediately before the displacement
  is the OB, and is it UNAMBIGUOUS or does it have MINOR/SIGNIFICANT
  ambiguity?
- Identify the IFVG: is there a visible gap between the OB candle and the
  candles that follow, is it obvious or subtle, and estimate the CE
  (midpoint) level visually.
- CISD direction: BEARISH, BULLISH, or NONE.

SECTION 5 - M5 PRECISION ENTRY
- On M5, is there a visible OB that corresponds to the M15 IFVG CE level?
- Is there any visual evidence of a nested M5 CISD within the M15 CISD?

SECTION 6 - FRACTAL COHERENCE
- Does the M15 pattern visually mirror the H4/H1 structure?
- Are the CRT phases aligned across timeframes?
- Rate the fractal coherence (0-10) and estimate the perceived depth
  (1=M15 only, 2=M15+H1, 3=M15+H1+H4, 4=M15+H1+H4+D1).

SECTION 7 - PATTERN QUALITY ASSESSMENT
- Overall pattern quality score (0-10).
- What is the single most compelling visual element of this setup?
- What is the single biggest visual weakness?

SECTION 8 - WHAT NUMBERS MIGHT MISS
- Is there anything you perceive VISUALLY that pure numerical analysis
  might fail to capture?
- Are there any visual warning signs that should reduce conviction?

Return your analysis as VALID JSON ONLY. No preamble, no explanation outside
the JSON structure."""
