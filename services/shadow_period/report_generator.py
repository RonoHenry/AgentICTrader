"""
ShadowPeriodReportGenerator — generates weekly comparison reports.

Report schema:
{
    "week_number": int,
    "report_date": str,
    "total_agent_alerts": int,
    "total_trader_responses": int,
    "trader_taken": int,
    "trader_skipped": int,
    "trader_modified": int,
    "match_rate_pct": float,       # % of agent alerts trader would have taken
    "agent_win_rate_pct": float,   # % of taken setups that were profitable
    "avg_r_multiple": float,       # average R-multiple on taken trades
    "total_pnl_r": float,          # total P&L in R-multiples
    "setups_by_instrument": dict,  # {instrument: count}
    "setups_by_session": dict,     # {time_window: count}
    "exit_criterion_met": bool,    # True if match_rate_pct >= 80.0
}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Exit criterion threshold
EXIT_CRITERION_THRESHOLD: float = 80.0


class ShadowPeriodReportGenerator:
    """Generates weekly comparison reports for the shadow period.

    Args:
        shadow_feedback_collection: PyMongo Collection (or mock) with
            ``find`` method for querying feedback documents.
    """

    def __init__(self, shadow_feedback_collection: Any) -> None:
        self._collection = shadow_feedback_collection

    def generate_weekly_report(self, week_number: int) -> dict:
        """Generate a comparison report for a given ISO week number.

        Match rate is calculated as:
            match_rate_pct = (trader_taken / total_agent_alerts) * 100

        Only NOTIFY decisions are counted as agent alerts (not SKIP).

        Args:
            week_number: ISO week number (1–53).

        Returns:
            Report dict matching the report schema.
        """
        # Fetch all feedback for this week
        cursor = self._collection.find({"week_number": week_number})
        all_docs = list(cursor)

        # Only count NOTIFY decisions as agent alerts
        agent_alerts = [
            d for d in all_docs
            if d.get("agent_decision") in (None, "NOTIFY", "EXECUTE")
        ]
        total_agent_alerts = len(agent_alerts)

        # Count trader responses
        total_trader_responses = len(all_docs)
        trader_taken = sum(1 for d in all_docs if d.get("trader_action") == "TAKEN")
        trader_skipped = sum(1 for d in all_docs if d.get("trader_action") == "SKIPPED")
        trader_modified = sum(1 for d in all_docs if d.get("trader_action") == "MODIFIED")

        # Match rate: taken / total_agent_alerts
        if total_agent_alerts > 0:
            match_rate_pct = (trader_taken / total_agent_alerts) * 100.0
        else:
            match_rate_pct = 0.0

        # Win rate and R-multiple stats (only on taken trades with pnl data)
        taken_docs = [
            d for d in all_docs
            if d.get("trader_action") == "TAKEN" and d.get("trader_pnl_r") is not None
        ]
        profitable = [d for d in taken_docs if d["trader_pnl_r"] > 0]

        if taken_docs:
            agent_win_rate_pct = (len(profitable) / len(taken_docs)) * 100.0
            avg_r_multiple = sum(d["trader_pnl_r"] for d in taken_docs) / len(taken_docs)
            total_pnl_r = sum(d["trader_pnl_r"] for d in taken_docs)
        else:
            agent_win_rate_pct = 0.0
            avg_r_multiple = 0.0
            total_pnl_r = 0.0

        # Setups by instrument
        setups_by_instrument: dict = {}
        for doc in all_docs:
            instrument = doc.get("instrument", "UNKNOWN")
            setups_by_instrument[instrument] = setups_by_instrument.get(instrument, 0) + 1

        # Setups by session (time_window)
        setups_by_session: dict = {}
        for doc in all_docs:
            session = doc.get("time_window") or doc.get("session", "UNKNOWN")
            setups_by_session[session] = setups_by_session.get(session, 0) + 1

        exit_criterion_met = match_rate_pct >= EXIT_CRITERION_THRESHOLD

        return {
            "week_number": week_number,
            "report_date": datetime.now(tz=timezone.utc).isoformat(),
            "total_agent_alerts": total_agent_alerts,
            "total_trader_responses": total_trader_responses,
            "trader_taken": trader_taken,
            "trader_skipped": trader_skipped,
            "trader_modified": trader_modified,
            "match_rate_pct": round(match_rate_pct, 2),
            "agent_win_rate_pct": round(agent_win_rate_pct, 2),
            "avg_r_multiple": round(avg_r_multiple, 4),
            "total_pnl_r": round(total_pnl_r, 4),
            "setups_by_instrument": setups_by_instrument,
            "setups_by_session": setups_by_session,
            "exit_criterion_met": exit_criterion_met,
        }

    def generate_full_report(self) -> list[dict]:
        """Generate reports for all weeks that have feedback data.

        Returns:
            List of weekly report dicts, sorted by week_number ascending.
        """
        # Find all distinct week numbers
        cursor = self._collection.find({})
        all_docs = list(cursor)

        week_numbers = sorted({d.get("week_number") for d in all_docs if d.get("week_number") is not None})

        reports = [self.generate_weekly_report(wn) for wn in week_numbers]
        return reports

    def check_exit_criterion(self) -> bool:
        """Check if the overall match rate across all weeks meets the exit criterion.

        Exit criterion: overall match_rate_pct >= 80.0%

        Returns:
            True if the overall match rate is >= 80%, False otherwise.
        """
        cursor = self._collection.find({})
        all_docs = list(cursor)

        if not all_docs:
            return False

        # Count overall totals
        total_agent_alerts = sum(
            1 for d in all_docs
            if d.get("agent_decision") in (None, "NOTIFY", "EXECUTE")
        )
        total_taken = sum(1 for d in all_docs if d.get("trader_action") == "TAKEN")

        if total_agent_alerts == 0:
            return False

        overall_match_rate = (total_taken / total_agent_alerts) * 100.0
        return overall_match_rate >= EXIT_CRITERION_THRESHOLD
