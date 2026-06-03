"""review_node — fifth node in the LangGraph agent execution loop.

Responsibilities:
  1. Monitor the open trade's current R-multiple.
  2. Trigger a partial close (50% of position) when r_multiple >= 1.0.
  3. Return the updated AgentState.

Validates: Requirements FR-6
"""
from __future__ import annotations

import logging
from typing import Any

from agent.state import AgentState

logger = logging.getLogger(__name__)

# Partial exit threshold: trigger at 1R profit
_PARTIAL_EXIT_R: float = 1.0


def review_node(
    state: AgentState,
    broker_client: Any,
) -> AgentState:
    """Monitor trade and trigger partial exit at 1R profit.

    Args:
        state:         Current AgentState with r_multiple populated.
        broker_client: Broker client with a
                       ``partial_close(trade_id: str, ratio: float) -> dict``
                       method.  Injected for testability.

    Returns:
        Updated AgentState (unchanged if r_multiple < 1.0).
    """
    r_multiple = state.r_multiple

    if r_multiple is None:
        logger.debug(
            "review_node: r_multiple not set for setup_id=%s — skipping review",
            state.setup_id,
        )
        return state

    if r_multiple >= _PARTIAL_EXIT_R:
        trade_id = state.trade_id or state.broker_order_id
        logger.info(
            "review_node: r_multiple=%.2f >= %.2f — triggering partial exit for trade_id=%s",
            r_multiple, _PARTIAL_EXIT_R, trade_id,
        )
        try:
            result = broker_client.partial_close(trade_id, ratio=0.5)
            logger.info("review_node: partial close result: %s", result)
        except Exception as exc:
            logger.error("review_node: partial close failed: %s", exc)
            return state.model_copy(update={"error": f"Partial close failed: {exc}"})
    else:
        logger.debug(
            "review_node: r_multiple=%.2f < %.2f — no action for setup_id=%s",
            r_multiple, _PARTIAL_EXIT_R, state.setup_id,
        )

    return state
