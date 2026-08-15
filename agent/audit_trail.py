"""agent/audit_trail.py — agent_decisions audit trail (Phase 4 Task 39).

Logs a single audit document per graph run to MongoDB agent_decisions,
distinct from the trade_journal collection written by learn_node:

  - trade_journal    — ML/analytics record, keyed for outcome tracking and
                        the retraining pipeline (agent/nodes/learn_node.py).
  - agent_decisions  — compliance/audit record proving every decision was
                        gated through the Risk Engine, required for the
                        live-validation exit criterion "zero risk engine
                        bypasses".

Called by AgentGraph at the terminal point of every run (NOTIFY, EXECUTE,
or SKIP/WAIT path alike) — mirrors learn_node's "always the terminal node"
guarantee so no decision goes unlogged.

Validates: Requirements FR-6 (Phase 4 Task 39)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from agent.state import AgentState

logger = logging.getLogger(__name__)


def log_agent_decision(
    state: AgentState,
    agent_decisions_collection: Any,
    user_id: str = "default",
) -> AgentState:
    """Log one audit-trail document to MongoDB agent_decisions.

    Args:
        state:                      Current AgentState, after decide_node
                                     (and execute_node, when applicable) have run.
        agent_decisions_collection: PyMongo Collection (or mock) with
                                     ``insert_one(document: dict)``.
        user_id:                    User identifier this decision was made for.

    Returns:
        The same AgentState (unchanged — this is a terminal, side-effecting call).
    """
    risk_validation: Optional[dict] = None
    if state.risk_validation is not None:
        risk_validation = {
            "verdict": state.risk_validation.verdict.value,
            "rejection_reason": state.risk_validation.rejection_reason,
            "checks": state.risk_validation.checks,
            "recommended_size": state.risk_validation.recommended_size,
        }

    order_details: Optional[dict] = None
    if state.broker_order_id is not None or state.trade_id is not None:
        order_details = {
            "broker_order_id": state.broker_order_id,
            "trade_id": state.trade_id,
            "entry": state.trade_plan.entry if state.trade_plan else None,
            "stop_loss": state.trade_plan.stop_loss if state.trade_plan else None,
            "take_profit_1": state.trade_plan.take_profit_1 if state.trade_plan else None,
            "recommended_size": state.trade_plan.recommended_size if state.trade_plan else None,
        }

    document: dict = {
        "setup_id": state.setup_id,
        "user_id": user_id,
        "mode": state.mode.value,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        # Input context — everything the decision was based on
        "input_context": {
            "instrument": state.instrument,
            "timeframe": state.timeframe,
            "direction": state.direction.value if state.direction is not None else None,
            "detected_at": state.detected_at.isoformat() if state.detected_at else None,
            "regime": state.regime,
            "regime_confidence": state.regime_confidence,
            "patterns": [p.model_dump() for p in state.patterns],
            "raw_confidence": state.raw_confidence,
            "final_confidence": state.final_confidence,
            "htf_alignment": state.htf_alignment,
            "sentiment_score": state.sentiment_score,
            "sentiment_aligned": state.sentiment_aligned,
            "calendar_clear": state.calendar_clear,
            "time_window": state.time_window,
            "narrative_phase": state.narrative_phase,
            "is_killzone": state.is_killzone,
        },
        # Risk validation result — None only when decide_node never ran
        # (e.g. the stale-setup path routes straight to learn)
        "risk_validation": risk_validation,
        # Decision + reasoning
        "decision": state.decision.value if state.decision is not None else None,
        "decision_reason": state.decision_reason,
        "reasoning": state.trade_reasoning,
        # Order details — None unless execute_node placed a live order
        "order_details": order_details,
        "error": state.error,
    }

    try:
        agent_decisions_collection.insert_one(document)
        logger.info(
            "log_agent_decision: logged decision=%s for setup_id=%s",
            document["decision"], state.setup_id,
        )
    except Exception as exc:
        # Non-fatal — an audit-log failure must not break the agent loop.
        logger.error("log_agent_decision: MongoDB insert failed: %s", exc)

    return state
