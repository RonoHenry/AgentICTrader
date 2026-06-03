"""
ShadowPeriodModeEnforcer — ensures all users are in HUMAN_IN_LOOP mode during shadow period.

During shadow period:
  - All agent mode overrides to AUTONOMOUS are rejected
  - All setups are processed in HUMAN_IN_LOOP mode regardless of user setting
  - Shadow period active flag stored in Redis: key shadow:active → {active: bool, started_at: str}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agent.state import AgentMode

logger = logging.getLogger(__name__)

# Redis key for shadow period state
_SHADOW_ACTIVE_KEY = "shadow:active"


class ShadowPeriodModeEnforcer:
    """Ensures all users are in HUMAN_IN_LOOP mode during the shadow period.

    Shadow period state is stored in Redis under the key ``shadow:active``
    as a JSON object: ``{active: bool, started_at: str}``.

    Args:
        redis_client: Synchronous Redis-compatible client with
            ``get``, ``set``, and ``delete`` methods.
            Must have ``decode_responses=True``.
    """

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    def activate_shadow_period(self) -> None:
        """Activate the shadow period.

        Sets ``shadow:active`` in Redis to ``{active: true, started_at: <now>}``.
        """
        payload = {
            "active": True,
            "started_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._redis.set(_SHADOW_ACTIVE_KEY, json.dumps(payload))
        logger.info("ShadowPeriodModeEnforcer: shadow period ACTIVATED")

    def deactivate_shadow_period(self) -> None:
        """Deactivate the shadow period.

        Sets ``shadow:active`` in Redis to ``{active: false, started_at: <original>}``.
        """
        # Preserve started_at if it exists
        existing = self._read_shadow_state()
        started_at = existing.get("started_at") if existing else None

        payload: dict = {"active": False}
        if started_at:
            payload["started_at"] = started_at

        self._redis.set(_SHADOW_ACTIVE_KEY, json.dumps(payload))
        logger.info("ShadowPeriodModeEnforcer: shadow period DEACTIVATED")

    def is_shadow_active(self) -> bool:
        """Return True if the shadow period is currently active.

        Reads from Redis key ``shadow:active``.
        Returns False if the key is missing or ``active`` is False.

        Returns:
            True if shadow period is active, False otherwise.
        """
        state = self._read_shadow_state()
        if state is None:
            return False
        return bool(state.get("active", False))

    def enforce_human_in_loop(self, mode: AgentMode) -> AgentMode:
        """Return HUMAN_IN_LOOP if shadow period is active, else return original mode.

        During shadow period, any attempt to use AUTONOMOUS mode is overridden
        to HUMAN_IN_LOOP to ensure all setups are reviewed by the trader.

        Args:
            mode: The requested AgentMode.

        Returns:
            AgentMode.HUMAN_IN_LOOP if shadow is active, else the original mode.
        """
        if self.is_shadow_active():
            if mode == AgentMode.AUTONOMOUS:
                logger.info(
                    "ShadowPeriodModeEnforcer: overriding AUTONOMOUS → HUMAN_IN_LOOP "
                    "(shadow period active)"
                )
            return AgentMode.HUMAN_IN_LOOP
        return mode

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_shadow_state(self) -> dict | None:
        """Read and parse the shadow state from Redis.

        Returns:
            Parsed dict or None if key is missing.
        """
        raw = self._redis.get(_SHADOW_ACTIVE_KEY)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "ShadowPeriodModeEnforcer: could not parse shadow state from Redis"
            )
            return None
