"""
TraderFeedbackLogger — logs trader feedback against agent alerts in MongoDB.

Feedback document schema (stored in MongoDB `shadow_feedback` collection):
{
    "setup_id": str,           # matches AgentState.setup_id
    "instrument": str,
    "timeframe": str,
    "direction": str,
    "detected_at": str,        # ISO format
    "agent_confidence": float,
    "agent_decision": str,     # NOTIFY / SKIP / EXECUTE
    "trader_action": str,      # "TAKEN" | "SKIPPED" | "MODIFIED"
    "trader_entry": float | None,   # actual entry if taken/modified
    "trader_sl": float | None,
    "trader_tp": float | None,
    "trader_notes": str | None,
    "trader_pnl_r": float | None,   # outcome in R-multiples
    "feedback_at": str,        # ISO format when feedback was logged
    "week_number": int,        # ISO week number for weekly grouping
}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Valid trader actions
VALID_TRADER_ACTIONS = {"TAKEN", "SKIPPED", "MODIFIED"}


class TraderFeedbackLogger:
    """Logs trader feedback against agent alerts in MongoDB.

    Args:
        shadow_feedback_collection: PyMongo Collection (or mock) with
            ``insert_one``, ``find_one``, and ``find`` methods.
        alert_collection: Optional PyMongo Collection for agent alerts
            (used to enrich feedback with alert metadata).
    """

    def __init__(
        self,
        shadow_feedback_collection: Any,
        alert_collection: Optional[Any] = None,
    ) -> None:
        self._collection = shadow_feedback_collection
        self._alert_collection = alert_collection

    def log_feedback(
        self,
        setup_id: str,
        trader_action: str,
        instrument: str = "",
        timeframe: str = "",
        direction: str = "",
        detected_at: Optional[str] = None,
        agent_confidence: Optional[float] = None,
        agent_decision: Optional[str] = None,
        trader_entry: Optional[float] = None,
        trader_sl: Optional[float] = None,
        trader_tp: Optional[float] = None,
        trader_notes: Optional[str] = None,
        trader_pnl_r: Optional[float] = None,
    ) -> str:
        """Insert a trader feedback document into MongoDB.

        Args:
            setup_id:         Matches AgentState.setup_id.
            trader_action:    One of "TAKEN", "SKIPPED", "MODIFIED".
            instrument:       Trading instrument (e.g. "EURUSD").
            timeframe:        Timeframe (e.g. "M5").
            direction:        Trade direction (e.g. "LONG").
            detected_at:      ISO format datetime when setup was detected.
            agent_confidence: Agent's confidence score for the setup.
            agent_decision:   Agent's decision (NOTIFY / SKIP / EXECUTE).
            trader_entry:     Actual entry price if taken/modified.
            trader_sl:        Actual stop-loss if taken/modified.
            trader_tp:        Actual take-profit if taken/modified.
            trader_notes:     Free-text notes from the trader.
            trader_pnl_r:     Outcome in R-multiples.

        Returns:
            String representation of the inserted document's _id.

        Raises:
            ValueError: If trader_action is not one of the valid values.
        """
        if trader_action not in VALID_TRADER_ACTIONS:
            raise ValueError(
                f"Invalid trader_action '{trader_action}'. "
                f"Must be one of: {sorted(VALID_TRADER_ACTIONS)}"
            )

        now = datetime.now(tz=timezone.utc)
        week_number = now.isocalendar().week

        document: dict = {
            "setup_id": setup_id,
            "instrument": instrument,
            "timeframe": timeframe,
            "direction": direction,
            "detected_at": detected_at,
            "agent_confidence": agent_confidence,
            "agent_decision": agent_decision,
            "trader_action": trader_action,
            "trader_entry": trader_entry,
            "trader_sl": trader_sl,
            "trader_tp": trader_tp,
            "trader_notes": trader_notes,
            "trader_pnl_r": trader_pnl_r,
            "feedback_at": now.isoformat(),
            "week_number": week_number,
        }

        result = self._collection.insert_one(document)
        inserted_id = str(result.inserted_id)

        logger.info(
            "TraderFeedbackLogger: logged feedback setup_id=%s action=%s inserted_id=%s",
            setup_id, trader_action, inserted_id,
        )

        return inserted_id

    def get_feedback_for_setup(self, setup_id: str) -> Optional[dict]:
        """Retrieve feedback document by setup_id.

        Args:
            setup_id: The setup identifier to look up.

        Returns:
            The feedback document dict, or None if not found.
        """
        doc = self._collection.find_one({"setup_id": setup_id})
        if doc is None:
            return None
        # Convert ObjectId to string for JSON serialisability
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def get_all_feedback(self, week_number: Optional[int] = None) -> list[dict]:
        """Retrieve all feedback documents, optionally filtered by ISO week.

        Args:
            week_number: If provided, only return documents for this ISO week.

        Returns:
            List of feedback document dicts.
        """
        query: dict = {}
        if week_number is not None:
            query["week_number"] = week_number

        cursor = self._collection.find(query)
        docs = list(cursor)

        # Convert ObjectId to string
        for doc in docs:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])

        return docs
