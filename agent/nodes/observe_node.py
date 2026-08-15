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
from typing import Any, Dict, List, Optional

from agent.state import AgentState, DecisionAction, Direction, TradePlan
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Candle, LiquidityMap, Timeframe

logger = logging.getLogger(__name__)

# Maximum age of a setup before it is considered stale
_MAX_AGE_SECONDS: int = 60


def _parse_candle_timestamp(raw: Any) -> Optional[datetime]:
    if isinstance(raw, str):
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
    return None


def _parse_candles_by_tf(
    raw: Dict[str, Any], instrument: str
) -> Optional[Dict[Timeframe, List[Candle]]]:
    """Deserialise a Kafka message's candles_by_tf into engine-ready Candle objects.

    Best-effort: unknown timeframe keys and individually malformed candles are
    skipped with a warning rather than failing the whole setup.
    """
    if not raw:
        return None
    result: Dict[Timeframe, List[Candle]] = {}
    for tf_key, candle_dicts in raw.items():
        try:
            tf = Timeframe(tf_key)
        except ValueError:
            logger.warning("Unknown timeframe in candles_by_tf: %s", tf_key)
            continue
        candles: List[Candle] = []
        for c in candle_dicts or []:
            candle_ts = _parse_candle_timestamp(c.get("timestamp"))
            if candle_ts is None:
                continue
            try:
                candles.append(
                    Candle(
                        timestamp=candle_ts,
                        open=c["open"],
                        high=c["high"],
                        low=c["low"],
                        close=c["close"],
                        volume=c.get("volume"),
                        timeframe=tf,
                        instrument=instrument,
                    )
                )
            except Exception as exc:
                logger.warning("Invalid candle skipped for %s: %s", tf_key, exc)
        if candles:
            result[tf] = candles
    return result or None


def _build_liquidity_context(
    message: Dict[str, Any], instrument: str, detected_at: datetime
) -> tuple[Optional[LiquidityMap], Optional[Dict[Timeframe, List[Candle]]]]:
    """Parse candles_by_tf once and return both the computed LiquidityMap and
    the parsed candles themselves.

    The candles are retained (not just the derived LiquidityMap) so that
    services/visual_model's chart renderer, called later from analyse_node,
    scores the identical candle snapshot the numerical engine already
    analysed rather than a re-fetched, possibly divergent one.
    """
    candles_raw = message.get("candles_by_tf")
    if not candles_raw:
        return None, None
    try:
        candles_by_tf = _parse_candles_by_tf(candles_raw, instrument)
        if not candles_by_tf:
            return None, None
        liquidity_map = LiquidityMappingEngine().analyze(candles_by_tf, instrument, detected_at)
        return liquidity_map, candles_by_tf
    except Exception as exc:
        logger.warning("Liquidity engine analysis failed for instrument=%s: %s", instrument, exc)
        return None, None


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

    # Liquidity Engine (Task 160) + retained candle window (Task 174)
    liquidity_map, candles_by_tf = _build_liquidity_context(message, instrument, detected_at)

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
        # Liquidity Engine (Task 160)
        liquidity_map=liquidity_map,
        # Visual Model (Task 174)
        candles_by_tf=candles_by_tf,
    )

    logger.info(
        "observe_node: accepted setup_id=%s instrument=%s age=%.1fs",
        setup_id, instrument, age_seconds,
    )
    return state
