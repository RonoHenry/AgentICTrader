"""
Turns a qualitative VisualAnalysis into the two numbers analyse_node/
decide_node actually consume: a bounded float folded into final_confidence
the same way sentiment_bonus/calendar_bonus already are, and an optional
hard-block reason that joins decide_node's existing gate stack.

`numerical_direction` is a plain "BULLISH"/"BEARISH" string, not
agent.state.Direction - this module (and the whole services/visual_model
package) must stay importable and deployable independently of the agent
package.

**Validates: Requirements 7.1-7.6 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

from typing import Literal, Optional, Tuple

from services.visual_model.config import settings
from services.visual_model.schemas.visual_analysis import CRTPhaseLiteral, VisualAnalysis


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_visual_modifier(
    analysis: VisualAnalysis,
    numerical_direction: Optional[Literal["BULLISH", "BEARISH"]],
) -> Tuple[float, Optional[str]]:
    """Returns (modifier in [-0.15, 0.15], hard_block_reason or None).

    Never raises for any structurally valid VisualAnalysis - a result with
    no modifier/block condition returns (0.0, None).
    """
    visual_composite = (
        analysis.quality.overall_score / 10.0 * settings.quality_weight
        + analysis.fractal.coherence_score / 10.0 * settings.fractal_weight
        + analysis.structure.structure_clarity_score / 10.0 * settings.structure_weight
    )
    modifier = _clamp(
        (visual_composite - 0.5) * 0.30,
        settings.visual_modifier_min,
        settings.visual_modifier_max,
    )

    hard_block_reason = _compute_hard_block_reason(analysis, numerical_direction)

    return modifier, hard_block_reason


def _compute_hard_block_reason(
    analysis: VisualAnalysis,
    numerical_direction: Optional[Literal["BULLISH", "BEARISH"]],
) -> Optional[str]:
    if (
        analysis.cisd.direction != "NONE"
        and numerical_direction is not None
        and analysis.cisd.direction != numerical_direction
    ):
        return (
            "visual/numerical direction conflict: visual model read "
            f"{analysis.cisd.direction}, numerical engine read {numerical_direction}"
        )

    if analysis.crt.m15_phase == CRTPhaseLiteral.C2_MANIPULATION:
        return (
            "visual model: M15 still in C2_MANIPULATION, not yet distribution"
        )

    return None
