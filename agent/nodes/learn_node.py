"""learn_node — sixth (final) node in the LangGraph agent execution loop.

Responsibilities:
  1. Build a complete trade journal document from AgentState.
  2. Insert the document into the MongoDB trade_journal collection.
  3. Return the updated AgentState.

Validates: Requirements FR-6
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agent.state import AgentState

logger = logging.getLogger(__name__)


def learn_node(
    state: AgentState,
    trade_journal_collection: Any,
) -> AgentState:
    """Log the trade outcome to MongoDB trade_journal.

    Args:
        state:                    Current AgentState with outcome populated.
        trade_journal_collection: PyMongo Collection (or mock) with an
                                  ``insert_one(document: dict)`` method.

    Returns:
        The same AgentState (unchanged — learn_node is a terminal node).
    """
    # ── Build journal document ─────────────────────────────────────────────
    trade_plan_dict: dict = {}
    if state.trade_plan is not None:
        trade_plan_dict = {
            "entry_price": state.trade_plan.entry,
            "stop_loss": state.trade_plan.stop_loss,
            "take_profit_1": state.trade_plan.take_profit_1,
            "r_ratio": state.trade_plan.r_ratio,
            "recommended_size": state.trade_plan.recommended_size,
        }

    risk_dict: dict = {}
    if state.risk_validation is not None:
        risk_dict = {
            "verdict": state.risk_validation.verdict.value,
            "recommended_size": state.risk_validation.recommended_size,
        }

    document: dict = {
        # Identity
        "setup_id": state.setup_id,
        "broker_order_id": state.broker_order_id,
        "trade_id": state.trade_id,
        # Setup context
        "instrument": state.instrument,
        "timeframe": state.timeframe,
        "direction": state.direction.value if state.direction is not None else None,
        "detected_at": state.detected_at.isoformat() if state.detected_at else None,
        # ML outputs
        "regime": state.regime,
        "raw_confidence": state.raw_confidence,
        "final_confidence": state.final_confidence,
        # Sentiment
        "sentiment_score": state.sentiment_score,
        "sentiment_aligned": state.sentiment_aligned,
        # Trade plan
        "trade_plan": trade_plan_dict,
        # Flatten key trade plan fields for easy querying
        **trade_plan_dict,
        # Risk
        "risk_validation": risk_dict,
        # Decision
        "decision": state.decision.value if state.decision is not None else None,
        "decision_reason": state.decision_reason,
        "trade_reasoning": state.trade_reasoning,
        # Time window (FR-3A)
        "time_window": state.time_window,
        "narrative_phase": state.narrative_phase,
        "time_window_weight": state.time_window_weight,
        "is_killzone": state.is_killzone,
        "price_vs_daily_open": state.price_vs_daily_open,
        "price_vs_weekly_open": state.price_vs_weekly_open,
        "price_vs_true_day_open": state.price_vs_true_day_open,
        # Outcome
        "outcome": state.outcome,
        "r_multiple": state.r_multiple,
        "close_price": state.close_price,
        "close_time": (
            state.close_time.isoformat() if state.close_time is not None else None
        ),
        # Metadata
        "logged_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": state.mode.value,
    }

    # ── Insert into MongoDB ────────────────────────────────────────────────
    try:
        result = trade_journal_collection.insert_one(document)
        logger.info(
            "learn_node: logged trade outcome for setup_id=%s inserted_id=%s",
            state.setup_id, result.inserted_id,
        )
    except Exception as exc:
        logger.error("learn_node: MongoDB insert failed: %s", exc)
        return state.model_copy(update={"error": f"MongoDB insert failed: {exc}"})

    return state
