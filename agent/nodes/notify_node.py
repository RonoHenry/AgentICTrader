"""notify_node — fourth node in the LangGraph agent execution loop (HUMAN_IN_LOOP path).

Responsibilities:
  1. Build a complete FCM alert payload with all FR-8 required fields.
  2. Dispatch the alert via the provided FCM sender callable.
  3. Return the updated AgentState.

Required alert fields (FR-8):
  instrument, direction, confidence_score, entry_price, sl_price, tp_price,
  r_ratio, reasoning, time_window, narrative_phase, price_vs_daily_open,
  price_vs_true_day_open, is_killzone

Validates: Requirements FR-8
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from agent.state import AgentState

logger = logging.getLogger(__name__)

# Type alias for the FCM sender callable
FcmSender = Callable[[dict, Optional[str]], bool]


def notify_node(
    state: AgentState,
    fcm_sender: FcmSender,
    fcm_token: Optional[str] = None,
) -> AgentState:
    """Format and dispatch an FCM push notification for the detected setup.

    Args:
        state:      Current AgentState (output of decide_node).
        fcm_sender: Callable(payload: dict, token: str | None) -> bool.
                    Injected for testability; production uses firebase-admin.
        fcm_token:  Optional FCM device token.  Passed through to fcm_sender.

    Returns:
        Updated AgentState (unchanged aside from any error recording).
    """
    # ── Build alert payload ────────────────────────────────────────────────
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    r_ratio: Optional[float] = None

    if state.trade_plan is not None:
        entry_price = state.trade_plan.entry
        sl_price = state.trade_plan.stop_loss
        tp_price = state.trade_plan.take_profit_1
        r_ratio = state.trade_plan.r_ratio

    direction_str = state.direction.value if state.direction is not None else None

    payload: dict = {
        # Core setup fields (FR-8)
        "instrument": state.instrument,
        "direction": direction_str,
        "confidence_score": state.final_confidence,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "r_ratio": r_ratio,
        "reasoning": state.trade_reasoning,
        # Time window fields (FR-3A / FR-8)
        "time_window": state.time_window,
        "narrative_phase": state.narrative_phase,
        "time_window_weight": state.time_window_weight,
        "is_killzone": state.is_killzone,
        "price_vs_daily_open": state.price_vs_daily_open,
        "price_vs_weekly_open": state.price_vs_weekly_open,
        "price_vs_true_day_open": state.price_vs_true_day_open,
        # Setup metadata
        "setup_id": state.setup_id,
        "timeframe": state.timeframe,
        "regime": state.regime,
    }

    # ── Dispatch via FCM sender ────────────────────────────────────────────
    try:
        success = fcm_sender(payload, fcm_token)
        if success:
            logger.info(
                "notify_node: alert dispatched for setup_id=%s instrument=%s",
                state.setup_id, state.instrument,
            )
        else:
            logger.warning(
                "notify_node: FCM sender returned False for setup_id=%s",
                state.setup_id,
            )
    except Exception as exc:
        logger.error("notify_node: FCM dispatch failed: %s", exc)
        return state.model_copy(update={"error": f"FCM dispatch failed: {exc}"})

    return state
