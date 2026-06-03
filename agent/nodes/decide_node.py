"""decide_node — third node in the LangGraph agent execution loop.

Responsibilities:
  1. Apply confidence floor gate (< 0.65 → SKIP).
  2. Call Risk Engine validate() synchronously.
  3. Route to NOTIFY (HUMAN_IN_LOOP) or EXECUTE (AUTONOMOUS) on approval.
  4. Set SKIP on Risk Engine rejection.
  5. Return the updated AgentState.

Validates: Requirements FR-6, FR-7
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agent.state import (
    AgentState,
    DecisionAction,
    RiskValidation,
    RiskVerdictEnum,
)
from services.risk_engine.main import RiskEngine, ValidateRequest

logger = logging.getLogger(__name__)

# Confidence floor — must match Risk Engine constant
_CONFIDENCE_FLOOR: float = 0.65


def decide_node(
    state: AgentState,
    risk_engine: RiskEngine,
    user_id: str = "default",
) -> AgentState:
    """Apply confidence gate, call Risk Engine, and route the decision.

    Args:
        state:       Current AgentState (output of analyse_node).
        risk_engine: RiskEngine instance (injected for testability).
        user_id:     User identifier forwarded to the Risk Engine.

    Returns:
        Updated AgentState with decision, decision_reason, and risk_validation.
    """
    confidence = state.final_confidence if state.final_confidence is not None else (
        state.raw_confidence if state.raw_confidence is not None else 0.0
    )

    # ── 1. Confidence floor gate ───────────────────────────────────────────
    if confidence < _CONFIDENCE_FLOOR:
        logger.info(
            "decide_node: SKIP — confidence %.2f below floor %.2f",
            confidence, _CONFIDENCE_FLOOR,
        )
        return state.model_copy(update={
            "decision": DecisionAction.SKIP,
            "decision_reason": (
                f"confidence {confidence:.2f} is below the floor {_CONFIDENCE_FLOOR}"
            ),
        })

    # ── 2. Build Risk Engine request ───────────────────────────────────────
    # Derive SL distance in pips from trade_plan if available
    sl_distance_pips: float = 10.0  # safe default
    if state.trade_plan is not None:
        entry = state.trade_plan.entry
        sl = state.trade_plan.stop_loss
        raw_distance = abs(entry - sl)
        # Convert to pips: for most FX pairs 1 pip = 0.0001; for JPY pairs 0.01
        # Use a simple heuristic: if price > 10 assume JPY-style, else standard
        pip_size = 0.01 if entry > 10 else 0.0001
        sl_distance_pips = raw_distance / pip_size if pip_size > 0 else raw_distance * 10000
        sl_distance_pips = max(sl_distance_pips, 0.1)  # guard against zero

    validate_request = ValidateRequest(
        user_id=user_id,
        instrument=state.instrument,
        confidence=confidence,
        sl_distance_pips=sl_distance_pips,
    )

    # ── 3. Call Risk Engine synchronously ─────────────────────────────────
    validate_response = risk_engine.validate(validate_request)

    if not validate_response.approved:
        logger.info(
            "decide_node: SKIP — Risk Engine rejected: %s", validate_response.reason
        )
        risk_validation = RiskValidation(
            verdict=RiskVerdictEnum.REJECTED,
            rejection_reason=validate_response.reason,
        )
        return state.model_copy(update={
            "decision": DecisionAction.SKIP,
            "decision_reason": validate_response.reason,
            "risk_validation": risk_validation,
        })

    # ── 4. Risk Engine approved — route by mode ────────────────────────────
    from agent.state import AgentMode
    risk_validation = RiskValidation(
        verdict=RiskVerdictEnum.APPROVED,
        recommended_size=validate_response.position_size,
    )

    if state.mode == AgentMode.AUTONOMOUS:
        decision = DecisionAction.EXECUTE
        reason = "Risk Engine approved — autonomous execution"
    else:
        decision = DecisionAction.NOTIFY
        reason = "Risk Engine approved — human-in-the-loop notification"

    logger.info(
        "decide_node: %s — confidence=%.2f mode=%s",
        decision.value, confidence, state.mode.value,
    )

    return state.model_copy(update={
        "decision": decision,
        "decision_reason": reason,
        "risk_validation": risk_validation,
    })
