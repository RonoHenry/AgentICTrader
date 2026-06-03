"""execute_node — fourth node in the LangGraph agent execution loop (AUTONOMOUS path).

Responsibilities:
  1. Guard: skip immediately if mode is HUMAN_IN_LOOP or shadow_period_active=True.
  2. Perform a pre-execution risk recheck via Risk Engine validate().
  3. Place the broker order only when the recheck passes.
  4. Record broker_order_id and trade_id on the state.
  5. Set decision=SKIP if the recheck fails or mode is not AUTONOMOUS.
  6. Return the updated AgentState.

Validates: Requirements FR-6, FR-7
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agent.state import AgentMode, AgentState, DecisionAction, RiskValidation, RiskVerdictEnum
from services.risk_engine.main import RiskEngine, ValidateRequest

logger = logging.getLogger(__name__)


def execute_node(
    state: AgentState,
    risk_engine: RiskEngine,
    broker_client: Any,
    user_id: str = "default",
) -> AgentState:
    """Pre-execution risk recheck then place broker order.

    Args:
        state:         Current AgentState (output of decide_node).
        risk_engine:   RiskEngine instance for the mandatory pre-execution recheck.
        broker_client: Broker client with a ``place_order(order: dict) -> dict``
                       method.  Injected for testability.
        user_id:       User identifier forwarded to the Risk Engine.

    Returns:
        Updated AgentState with broker_order_id / trade_id on success,
        or decision=SKIP on recheck failure / mode guard.
    """
    # ── 0. Mode guard — only execute in AUTONOMOUS mode ───────────────────
    if state.mode != AgentMode.AUTONOMOUS:
        logger.info(
            "execute_node: SKIP — mode is %s, not AUTONOMOUS for setup_id=%s",
            state.mode.value, state.setup_id,
        )
        return state.model_copy(update={
            "decision": DecisionAction.SKIP,
            "decision_reason": (
                f"execute_node: mode is {state.mode.value} — live orders only "
                "permitted in AUTONOMOUS mode"
            ),
        })

    # ── 0b. Shadow period guard ────────────────────────────────────────────
    if state.shadow_period_active:
        logger.warning(
            "execute_node: SKIP — shadow_period_active=True for setup_id=%s",
            state.setup_id,
        )
        return state.model_copy(update={
            "decision": DecisionAction.SKIP,
            "decision_reason": (
                "execute_node: shadow period is active — autonomous execution blocked"
            ),
        })

    confidence = state.final_confidence if state.final_confidence is not None else (
        state.raw_confidence if state.raw_confidence is not None else 0.0
    )

    # ── 1. Pre-execution risk recheck ──────────────────────────────────────
    sl_distance_pips: float = 10.0
    if state.trade_plan is not None:
        entry = state.trade_plan.entry
        sl = state.trade_plan.stop_loss
        raw_distance = abs(entry - sl)
        pip_size = 0.01 if entry > 10 else 0.0001
        sl_distance_pips = raw_distance / pip_size if pip_size > 0 else raw_distance * 10000
        sl_distance_pips = max(sl_distance_pips, 0.1)

    recheck_request = ValidateRequest(
        user_id=user_id,
        instrument=state.instrument,
        confidence=confidence,
        sl_distance_pips=sl_distance_pips,
    )

    recheck_response = risk_engine.validate(recheck_request)

    if not recheck_response.approved:
        logger.warning(
            "execute_node: pre-execution recheck FAILED for setup_id=%s reason=%s",
            state.setup_id, recheck_response.reason,
        )
        risk_validation = RiskValidation(
            verdict=RiskVerdictEnum.REJECTED,
            rejection_reason=recheck_response.reason,
        )
        return state.model_copy(update={
            "decision": DecisionAction.SKIP,
            "decision_reason": f"Pre-execution recheck failed: {recheck_response.reason}",
            "risk_validation": risk_validation,
        })

    # ── 2. Build and place broker order ───────────────────────────────────
    direction_str = state.direction.value if state.direction is not None else "LONG"
    position_size = recheck_response.position_size or (
        state.trade_plan.recommended_size if state.trade_plan else 0.01
    )

    order: dict = {
        "instrument": state.instrument,
        "direction": direction_str,
        "entry": state.trade_plan.entry if state.trade_plan else None,
        "stop_loss": state.trade_plan.stop_loss if state.trade_plan else None,
        "take_profit": state.trade_plan.take_profit_1 if state.trade_plan else None,
        "size": position_size,
        "setup_id": state.setup_id,
    }

    try:
        order_result = broker_client.place_order(order)
        broker_order_id = order_result.get("order_id")
        trade_id = order_result.get("trade_id")

        logger.info(
            "execute_node: order placed setup_id=%s order_id=%s trade_id=%s",
            state.setup_id, broker_order_id, trade_id,
        )

        return state.model_copy(update={
            "broker_order_id": broker_order_id,
            "trade_id": trade_id,
        })

    except Exception as exc:
        logger.error("execute_node: broker order failed: %s", exc)
        return state.model_copy(update={
            "error": f"Broker order failed: {exc}",
            "decision": DecisionAction.SKIP,
        })
