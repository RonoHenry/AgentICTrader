"""analyse_node — second node in the LangGraph agent execution loop.

Responsibilities:
  1. Fetch sentiment score from Redis (key: sentiment:{instrument}).
  2. Determine if sentiment is aligned with the trade direction.
  3. Adjust final_confidence up (aligned) or down (misaligned).
  4. Check Redis blackout key (key: blackout:{instrument}).
  5. Set calendar_clear=False when a blackout is active.
  6. Return the updated AgentState.

Validates: Requirements FR-5, FR-6
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agent.state import AgentState, Direction

logger = logging.getLogger(__name__)

# Sentiment adjustment factors
_ALIGNED_BOOST: float = 0.03      # +3% when sentiment aligns with direction
_MISALIGNED_PENALTY: float = 0.03  # -3% when sentiment opposes direction

# Redis key patterns (must match redis_schema.py)
_SENTIMENT_KEY = "sentiment:{instrument}"
_BLACKOUT_KEY = "blackout:{instrument}"


def analyse_node(state: AgentState, redis_client: Any = None) -> AgentState:
    """Enrich AgentState with sentiment and calendar data from Redis.

    Args:
        state:        Current AgentState (output of observe_node).
        redis_client: Synchronous Redis-compatible client with
                      ``decode_responses=True``.  Accepts fakeredis in tests.

    Returns:
        Updated AgentState with sentiment_score, sentiment_aligned,
        calendar_clear, and adjusted final_confidence.
    """
    updates: dict = {}

    # ── 1. Fetch sentiment ──────────────────────────────────────────────────
    sentiment_score: Optional[float] = None
    sentiment_aligned: Optional[bool] = None

    if redis_client is not None:
        sentiment_key = _SENTIMENT_KEY.format(instrument=state.instrument)
        raw_sentiment = redis_client.get(sentiment_key)

        if raw_sentiment is not None:
            try:
                sentiment_data = json.loads(raw_sentiment)
                sentiment_score = float(sentiment_data.get("score", 0.0))
                sentiment_direction = sentiment_data.get("direction")

                # Determine alignment: sentiment direction matches trade direction
                if state.direction is not None and sentiment_direction is not None:
                    trade_dir = state.direction.value  # "LONG" or "SHORT"
                    sentiment_aligned = (trade_dir == sentiment_direction)
                else:
                    sentiment_aligned = None

                updates["sentiment_score"] = sentiment_score
                updates["sentiment_aligned"] = sentiment_aligned

                logger.info(
                    "analyse_node: sentiment for %s score=%.2f aligned=%s",
                    state.instrument, sentiment_score, sentiment_aligned,
                )
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.warning("analyse_node: failed to parse sentiment: %s", exc)

    # ── 2. Adjust final_confidence based on sentiment alignment ────────────
    base_confidence = state.final_confidence if state.final_confidence is not None else (
        state.raw_confidence if state.raw_confidence is not None else 0.0
    )

    adjusted_confidence = base_confidence
    if sentiment_aligned is True:
        adjusted_confidence = min(1.0, base_confidence + _ALIGNED_BOOST)
    elif sentiment_aligned is False:
        adjusted_confidence = max(0.0, base_confidence - _MISALIGNED_PENALTY)

    updates["final_confidence"] = adjusted_confidence

    # ── 3. Check calendar blackout ─────────────────────────────────────────
    calendar_clear = True

    if redis_client is not None:
        blackout_key = _BLACKOUT_KEY.format(instrument=state.instrument)
        raw_blackout = redis_client.get(blackout_key)

        if raw_blackout is not None:
            try:
                blackout_data = json.loads(raw_blackout)
                if blackout_data.get("active", False):
                    calendar_clear = False
                    logger.info(
                        "analyse_node: blackout active for %s event=%s",
                        state.instrument, blackout_data.get("event_name"),
                    )
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("analyse_node: failed to parse blackout: %s", exc)

    updates["calendar_clear"] = calendar_clear

    # ── 4. Return updated state ────────────────────────────────────────────
    return state.model_copy(update=updates)
