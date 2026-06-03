"""observe_node  first node in the LangGraph agent execution loop.

Responsibilities:
  1. Receive a Kafka message dict containing setup data.
  2. Reject the setup if it is stale (detected_at > 60 seconds ago).
  3. Populate AgentState from the message fields.
  4. Return the updated AgentState.

Validates: Requirements FR-6
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from agent.state import AgentState, DecisionAction, Direction, TradePlan

logger = logging.getLogger(__name__)

# Maximum age of a setup before it is considered stale
_MAX_AGE_SECONDS: int = 60


def observe_node(message: Dict[str, Any]) -> AgentState:
    """Validate and ingest a Kafka setup message into AgentState.

    Args:
        message: Raw Kafka message dict with setup data.  Must contain at
            minimum: setup_id, instrument, timeframe, detected_at.

    Returns:
        AgentState populated from the message.  If the setup is stale,
        the returned state has ``error`` set and ``decision=SKIP``.
    """
    # Parse detected_at  accept ISO-format string or datetime
    detected_at_raw = message.get("detected_at")
    if isinstance(detected_at_raw, str):
        detected_at = datetime.fromisoformat(detected_at_raw)
        # Ensure timezone-aware
        if detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=timezone.utc)
    elif isinstance(detected_at_raw, datetime):
        detected_at = detected_at_raw
        if detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=timezone.utc)
    else:
        detected_at = datetime.now(tz=timezone.utc)

    now = datetime.now(tz=timezone.utc)
    age_seconds = (now - detected_at).total_seconds()

    # Build base state fields
    setup_id = message.get("setup_id", "unknown")
    instrument = message.get("instrument", "UNKNOWN")
    timeframe = message.get("timeframe", "M5")

    # Parse direction
    direction_raw = message.get("direction")
    direction = None
    if direction_raw:
        try:
            direction = Direction(direction_raw)
        except ValueError:
            logger.warning("Unknown direction value: %s", direction_raw)

    # Parse trade_plan
    trade_plan = None
    tp_data = message.get("trade_plan")
    if tp_data:
        try:
            trade_plan = TradePlan(**tp_data)
        except Exception as exc:
            logger.warning("Failed to parse trade_plan: %s", exc)

    # Check staleness  reject if age >= MAX_AGE_SECONDS
    if age_seconds >= _MAX_AGE_SECONDS:
        logger.warning(
            "Stale setup rejected: setup_id=%s age=%.1fs", setup_id, age_seconds
        )
        return AgentState(
            setup_id=setup_id,
            instrument=instrument,
            timeframe=timeframe,
            detected_at=detected_at,
            direction=direction,
            trade_plan=trade_plan,
            error=f"Setup is stale: age {age_seconds:.1f}s exceeds {_MAX_AGE_SECONDS}s limit",
            decision=DecisionAction.SKIP,
        )

    # Build full state from message
    state = AgentState(
        setup_id=setup_id,
        instrument=instrument,
        timeframe=timeframe,
        detected_at=detected_at,
        direction=direction,
        raw_confidence=message.get("raw_confidence"),
        final_confidence=message.get("raw_confidence"),  # initial value; analyse_node adjusts
        regime=message.get("regime"),
        patterns=message.get("patterns", []),
        trade_plan=trade_plan,
        trade_reasoning=message.get("trade_reasoning"),
        # Time window fields (FR-3A)
        time_window=message.get("time_window"),
        narrative_phase=message.get("narrative_phase"),
        time_window_weight=message.get("time_window_weight"),
        is_killzone=message.get("is_killzone"),
        price_vs_daily_open=message.get("price_vs_daily_open"),
        price_vs_weekly_open=message.get("price_vs_weekly_open"),
        price_vs_true_day_open=message.get("price_vs_true_day_open"),
    )

    logger.info(
        "observe_node: accepted setup_id=%s instrument=%s age=%.1fs",
        setup_id, instrument, age_seconds,
    )
    return state
