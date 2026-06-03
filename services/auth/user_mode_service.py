"""UserModeService — per-user HUMAN_IN_LOOP / AUTONOMOUS feature toggle.

Stores each user's preferred agent operating mode and exposes simple
get/set methods for the agent graph to query at decision time.

The backing store is an injectable ``db`` object that must implement:
  - ``get_user_mode(user_id: str) -> str | None``
  - ``set_user_mode(user_id: str, mode: str) -> bool``

This thin wrapper means the service is testable with a plain MagicMock
and deployable against any persistent store (MongoDB, Redis, etc.).

Validates: Requirements FR-6 (per-user mode toggle)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agent.state import AgentMode

logger = logging.getLogger(__name__)

# Default mode when no preference is stored for a user
_DEFAULT_MODE: AgentMode = AgentMode.HUMAN_IN_LOOP


class UserModeService:
    """Per-user feature toggle for HUMAN_IN_LOOP / AUTONOMOUS agent mode.

    Args:
        db: An object with ``get_user_mode(user_id)`` and
            ``set_user_mode(user_id, mode_value)`` methods.
            Pass a MagicMock in tests; a real DB adapter in production.

    Example::

        service = UserModeService(db=mongo_adapter)
        mode = service.get_agent_mode("user-1")
        service.set_agent_mode("user-1", AgentMode.AUTONOMOUS)
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    def get_agent_mode(self, user_id: str) -> AgentMode:
        """Return the stored agent mode for *user_id*.

        Falls back to HUMAN_IN_LOOP when no preference is stored.

        Args:
            user_id: The user whose mode to retrieve.

        Returns:
            :class:`AgentMode` enum value.
        """
        raw: Optional[str] = self._db.get_user_mode(user_id)
        if raw is None:
            logger.debug(
                "UserModeService: no mode stored for user_id=%s — defaulting to %s",
                user_id, _DEFAULT_MODE.value,
            )
            return _DEFAULT_MODE
        try:
            return AgentMode(raw)
        except ValueError:
            logger.warning(
                "UserModeService: unknown mode value '%s' for user_id=%s — defaulting to %s",
                raw, user_id, _DEFAULT_MODE.value,
            )
            return _DEFAULT_MODE

    def set_agent_mode(self, user_id: str, mode: AgentMode) -> bool:
        """Persist the agent mode preference for *user_id*.

        Args:
            user_id: The user whose mode to update.
            mode:    The :class:`AgentMode` to store.

        Returns:
            ``True`` on success (delegates to backing store).
        """
        logger.info(
            "UserModeService: setting mode=%s for user_id=%s",
            mode.value, user_id,
        )
        return self._db.set_user_mode(user_id, mode.value)
