"""
Shadow Period FastAPI service.

Exposes endpoints for logging trader feedback, generating weekly reports,
and checking the shadow period exit criterion.

Endpoints:
  POST /shadow/feedback                  — log trader feedback for a setup
  GET  /shadow/feedback/{setup_id}       — get feedback for a specific setup
  GET  /shadow/report/weekly/{week_number} — get weekly comparison report
  GET  /shadow/report/full               — get all weekly reports
  GET  /shadow/report/exit-criterion     — check if exit criterion (≥80%) is met
  GET  /shadow/status                    — shadow period status
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    """Request body for POST /shadow/feedback."""
    setup_id: str
    trader_action: str          # "TAKEN" | "SKIPPED" | "MODIFIED"
    instrument: str = ""
    timeframe: str = ""
    direction: str = ""
    detected_at: Optional[str] = None
    agent_confidence: Optional[float] = None
    agent_decision: Optional[str] = None
    trader_entry: Optional[float] = None
    trader_sl: Optional[float] = None
    trader_tp: Optional[float] = None
    trader_notes: Optional[str] = None
    trader_pnl_r: Optional[float] = None


class FeedbackResponse(BaseModel):
    """Response body for POST /shadow/feedback."""
    inserted_id: str
    setup_id: str
    trader_action: str


class ExitCriterionResponse(BaseModel):
    """Response body for GET /shadow/report/exit-criterion."""
    exit_criterion_met: bool
    match_rate_pct: float
    required_pct: float


class ShadowStatusResponse(BaseModel):
    """Response body for GET /shadow/status."""
    mode: str
    shadow_active: bool
    weeks_elapsed: int
    exit_criterion_met: bool


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_shadow_app(
    shadow_feedback_collection: Any,
    redis_client: Any = None,
) -> FastAPI:
    """Create and return the FastAPI application for shadow period endpoints.

    Args:
        shadow_feedback_collection: PyMongo Collection for feedback documents.
        redis_client: Synchronous Redis client for shadow period state.

    Returns:
        Configured FastAPI application.
    """
    from services.shadow_period.feedback_logger import TraderFeedbackLogger
    from services.shadow_period.report_generator import ShadowPeriodReportGenerator
    from services.shadow_period.mode_enforcer import ShadowPeriodModeEnforcer

    app = FastAPI(title="Shadow Period Service", version="1.0.0")

    feedback_logger = TraderFeedbackLogger(
        shadow_feedback_collection=shadow_feedback_collection
    )
    report_generator = ShadowPeriodReportGenerator(
        shadow_feedback_collection=shadow_feedback_collection
    )
    mode_enforcer = ShadowPeriodModeEnforcer(redis_client=redis_client) if redis_client else None

    # ------------------------------------------------------------------
    # Feedback endpoints
    # ------------------------------------------------------------------

    @app.post("/shadow/feedback", response_model=FeedbackResponse, status_code=201)
    def log_feedback(request: FeedbackRequest) -> FeedbackResponse:
        """Log trader feedback for an agent alert."""
        try:
            inserted_id = feedback_logger.log_feedback(
                setup_id=request.setup_id,
                trader_action=request.trader_action,
                instrument=request.instrument,
                timeframe=request.timeframe,
                direction=request.direction,
                detected_at=request.detected_at,
                agent_confidence=request.agent_confidence,
                agent_decision=request.agent_decision,
                trader_entry=request.trader_entry,
                trader_sl=request.trader_sl,
                trader_tp=request.trader_tp,
                trader_notes=request.trader_notes,
                trader_pnl_r=request.trader_pnl_r,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return FeedbackResponse(
            inserted_id=inserted_id,
            setup_id=request.setup_id,
            trader_action=request.trader_action,
        )

    @app.get("/shadow/feedback/{setup_id}")
    def get_feedback(setup_id: str) -> dict:
        """Get feedback for a specific setup."""
        doc = feedback_logger.get_feedback_for_setup(setup_id)
        if doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"No feedback found for setup_id={setup_id}",
            )
        return doc

    # ------------------------------------------------------------------
    # Report endpoints
    # ------------------------------------------------------------------

    @app.get("/shadow/report/weekly/{week_number}")
    def get_weekly_report(week_number: int) -> dict:
        """Get weekly comparison report for a given ISO week number."""
        return report_generator.generate_weekly_report(week_number)

    @app.get("/shadow/report/full")
    def get_full_report() -> list:
        """Get all weekly reports."""
        return report_generator.generate_full_report()

    @app.get("/shadow/report/exit-criterion", response_model=ExitCriterionResponse)
    def get_exit_criterion() -> ExitCriterionResponse:
        """Check if the exit criterion (≥80% match rate) is met."""
        exit_met = report_generator.check_exit_criterion()

        # Compute overall match rate for the response
        from services.shadow_period.report_generator import EXIT_CRITERION_THRESHOLD
        all_docs = list(shadow_feedback_collection.find({}))
        total_alerts = sum(
            1 for d in all_docs
            if d.get("agent_decision") in (None, "NOTIFY", "EXECUTE")
        )
        total_taken = sum(1 for d in all_docs if d.get("trader_action") == "TAKEN")
        match_rate = (total_taken / total_alerts * 100.0) if total_alerts > 0 else 0.0

        return ExitCriterionResponse(
            exit_criterion_met=exit_met,
            match_rate_pct=round(match_rate, 2),
            required_pct=EXIT_CRITERION_THRESHOLD,
        )

    # ------------------------------------------------------------------
    # Status endpoint
    # ------------------------------------------------------------------

    @app.get("/shadow/status", response_model=ShadowStatusResponse)
    def get_shadow_status() -> ShadowStatusResponse:
        """Return shadow period status."""
        shadow_active = mode_enforcer.is_shadow_active() if mode_enforcer else False
        exit_met = report_generator.check_exit_criterion()

        # Compute weeks elapsed from feedback data
        all_docs = list(shadow_feedback_collection.find({}))
        week_numbers = {d.get("week_number") for d in all_docs if d.get("week_number")}
        weeks_elapsed = len(week_numbers)

        return ShadowStatusResponse(
            mode="HUMAN_IN_LOOP",
            shadow_active=shadow_active,
            weeks_elapsed=weeks_elapsed,
            exit_criterion_met=exit_met,
        )

    return app
