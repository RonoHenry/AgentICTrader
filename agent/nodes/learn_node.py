"""learn_node — sixth (final) node in the LangGraph agent execution loop.

Responsibilities:
  1. Build a complete trade journal document from AgentState.
  2. Insert the document into the MongoDB trade_journal collection.
  3. After insert, count completed outcomes and trigger MLflow retraining
     queue every 50 new outcomes.
  4. Return the updated AgentState.

Validates: Requirements FR-6
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agent.state import AgentState

# Top-level import so patch("agent.nodes.learn_node.MLflowTracker") works in tests.
# The import is deferred inside trigger_retraining_if_needed to avoid a hard
# dependency when MLflow is not configured, but we expose the name at module level.
try:
    from ml.tracking.mlflow_client import MLflowTracker
except ImportError:  # pragma: no cover — MLflow may not be installed in all envs
    MLflowTracker = None  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retraining queue threshold
# ---------------------------------------------------------------------------

_RETRAIN_EVERY_N_OUTCOMES: int = 50


def trigger_retraining_if_needed(outcome_count: int) -> None:
    """Enqueue an MLflow retraining run when *outcome_count* is a multiple of 50.

    Called by learn_node after each successful journal insert.  When the total
    number of logged outcomes reaches a threshold multiple of 50 (e.g. 50, 100,
    150, …) it queues a retraining run via the MLflow tracker so the three
    ML models (regime-classifier, pattern-detector, confluence-scorer) can be
    retrained with the new labelled data.

    Note: the caller is responsible for checking the threshold guard before
    calling this function (i.e. only call when count % 50 == 0).

    Args:
        outcome_count: Total number of trade outcomes recorded in the journal
                       (as returned by collection.count_documents({})).
    """
    logger.info(
        "trigger_retraining_if_needed: %d outcomes reached — queuing MLflow retraining",
        outcome_count,
    )

    try:
        tracker = MLflowTracker()
        with tracker.start_run(
            experiment_name="confluence-scorer",
            run_name=f"retrain_trigger_n{outcome_count}",
        ):
            tracker.log_params({"trigger": "auto", "outcome_count": outcome_count})
            tracker.log_metrics({"outcomes_at_trigger": float(outcome_count)})
        logger.info(
            "trigger_retraining_if_needed: MLflow retraining run queued for n=%d",
            outcome_count,
        )
    except Exception as exc:
        # Non-fatal — log and continue.  Retraining failure must not block the agent.
        logger.error(
            "trigger_retraining_if_needed: MLflow error at n=%d: %s",
            outcome_count, exc,
        )


def learn_node(
    state: AgentState,
    trade_journal_collection: Any,
) -> AgentState:
    """Log the trade outcome to MongoDB trade_journal.

    After inserting the record, counts total outcomes in the collection and
    calls :func:`trigger_retraining_if_needed` at every 50-outcome threshold.

    Args:
        state:                    Current AgentState with outcome populated.
        trade_journal_collection: PyMongo Collection (or mock) with:
                                  - ``insert_one(document: dict)``
                                  - ``count_documents(filter: dict) -> int``

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

    # ── Check retraining threshold ─────────────────────────────────────────
    try:
        outcome_count = trade_journal_collection.count_documents({})
        # Guard: only proceed when count_documents returns a real integer
        if isinstance(outcome_count, int) and outcome_count > 0 and outcome_count % _RETRAIN_EVERY_N_OUTCOMES == 0:
            trigger_retraining_if_needed(outcome_count)
    except Exception as exc:
        # Non-fatal — retraining check failure must not break the agent loop
        logger.error("learn_node: retraining check failed: %s", exc)

    return state
