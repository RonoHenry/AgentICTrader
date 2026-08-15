"""
AgentState Pydantic v2 model.

Carries the full agent context through every node of the
Observe → Analyse → Decide → Act → Review → Learn loop.

**Validates: Requirements FR-6, FR-3A**
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel

# liquidity_engine has no dependency on agent/*, so this is not actually a
# circular import — a plain top-level import keeps AgentState resolvable by
# Pydantic v2 without needing model_rebuild() against a TYPE_CHECKING-only name.
from liquidity_engine.models import Candle, LiquidityMap

# services/visual_model has no dependency on agent/* either (see
# services/visual_model/fusion/visual_modifier.py's module docstring) — same
# one-directional import safety as liquidity_engine above.
from services.visual_model.schemas.visual_analysis import VisualAnalysis


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Direction(str, Enum):
    """Trade direction."""
    LONG = "LONG"
    SHORT = "SHORT"


class AgentMode(str, Enum):
    """Agent operating mode.

    HUMAN_IN_LOOP — push alerts only, no autonomous execution.
    AUTONOMOUS    — full broker execution (feature-toggled per user).
    """
    HUMAN_IN_LOOP = "HUMAN_IN_LOOP"
    AUTONOMOUS = "AUTONOMOUS"


class DecisionAction(str, Enum):
    """Final decision action produced by decide_node."""
    EXECUTE = "EXECUTE"
    NOTIFY = "NOTIFY"
    SKIP = "SKIP"
    WAIT = "WAIT"


class RiskVerdictEnum(str, Enum):
    """Risk engine verdict."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------

class Pattern(BaseModel):
    """A detected price-action pattern with confidence score."""
    type: str
    confidence: float
    level: Optional[float] = None
    zone: Optional[Dict] = None


class TradePlan(BaseModel):
    """Computed trade plan with entry, SL, TP, and sizing."""
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float] = None
    r_ratio: float
    recommended_size: float


class RiskValidation(BaseModel):
    """Result from the Risk Engine gate."""
    verdict: RiskVerdictEnum
    rejection_reason: Optional[str] = None
    checks: Dict[str, str] = {}
    recommended_size: Optional[float] = None


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------

class AgentState(BaseModel):
    """
    Full agent context carried through every node of the execution graph.

    Required fields: setup_id, instrument, timeframe, detected_at.
    All other fields are optional and default to None / empty collections.
    """

    # ── Setup Data ──
    setup_id: str
    instrument: str
    timeframe: str
    direction: Optional[Direction] = None
    detected_at: datetime

    # ── ML Outputs ──
    regime: Optional[str] = None
    regime_confidence: Optional[float] = None
    patterns: List[Pattern] = []
    raw_confidence: Optional[float] = None
    htf_alignment: Dict[str, str] = {}

    # ── Sentiment ──
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    sentiment_aligned: Optional[bool] = None
    top_headlines: List[str] = []

    # ── Calendar ──
    calendar_clear: bool = True
    minutes_to_next_event: Optional[int] = None
    next_event_name: Optional[str] = None

    # ── Final Score ──
    final_confidence: Optional[float] = None

    # ── Trade Plan ──
    trade_plan: Optional[TradePlan] = None

    # ── Risk ──
    risk_validation: Optional[RiskValidation] = None

    # ── Decision ──
    decision: Optional[DecisionAction] = None
    decision_reason: Optional[str] = None
    mode: AgentMode = AgentMode.HUMAN_IN_LOOP

    # ── LLM Reasoning ──
    trade_reasoning: Optional[str] = None

    # ── Execution ──
    broker_order_id: Optional[str] = None
    trade_id: Optional[str] = None

    # ── Outcome (populated in review/learn) ──
    outcome: Optional[str] = None
    r_multiple: Optional[float] = None
    close_price: Optional[float] = None
    close_time: Optional[datetime] = None

    # ── Meta ──
    error: Optional[str] = None
    processing_times: Dict[str, float] = {}

    # ── Time Window Fields (FR-3A) ──
    # Populated by the TimeWindowClassifier from ml/features/session_features.py
    time_window: Optional[str] = None
    """e.g. 'LONDON_KILLZONE', 'NY_AM_KILLZONE', 'NY_AM_SILVER_BULLET', etc."""

    narrative_phase: Optional[str] = None
    """e.g. 'MANIPULATION', 'EXPANSION', 'ACCUMULATION', 'DISTRIBUTION', etc."""

    time_window_weight: Optional[float] = None
    """Probability weight 0.0–1.0 per ICT Silver Bullet hierarchy."""

    is_killzone: Optional[bool] = None
    """True when the time window is a killzone or silver bullet window."""

    price_vs_daily_open: Optional[str] = None
    """Price position relative to daily open: 'ABOVE', 'BELOW', or 'AT'."""

    price_vs_weekly_open: Optional[str] = None
    """Price position relative to weekly open: 'ABOVE', 'BELOW', or 'AT'."""

    price_vs_true_day_open: Optional[str] = None
    """Price position relative to true day open (00:00 NY): 'ABOVE', 'BELOW', or 'AT'."""

    # ── Shadow Period (FR-Shadow) ──
    shadow_period_active: bool = False
    """True when the agent is running in shadow period mode.
    During shadow period all users are forced into HUMAN_IN_LOOP mode."""

    # ── Liquidity Engine (Task 160) ──
    liquidity_map: Optional[LiquidityMap] = None
    """Populated by observe_node when the message carries candles_by_tf.
    None when no candle data was supplied, the setup was rejected as stale,
    or analysis failed (see observe_node's best-effort handling)."""

    # ── Visual Model (Task 173) ──
    candles_by_tf: Optional[Dict[str, List[Candle]]] = None
    """Retained by observe_node from the same parse that built liquidity_map,
    so analyse_node's visual-model call scores the identical candle snapshot
    the numerical engine already analysed. None when no candle data was
    supplied on the incoming message."""

    visual_analysis: Optional[VisualAnalysis] = None
    """Full structured VLM output from services/visual_model, when called.
    None when the setup graded below B, candles_by_tf was unavailable, or
    the visual-model call degraded (see analyse_node's grade-gated call)."""

    visual_modifier: Optional[float] = None
    """Bounded [-0.15, 0.15] float folded into final_confidence alongside
    sentiment_bonus/calendar_bonus. None when the visual model was never
    called; 0.0 when it was called but returned a neutral/degraded result."""

    visual_hard_block_reason: Optional[str] = None
    """Set by the visual model on a direction conflict or an active
    C2_MANIPULATION read — checked by decide_node alongside calendar_clear."""

    visual_narrative: Optional[str] = None
    """VisualAnalysis.visual_insights.narrative, surfaced for logging and
    trade_reasoning context."""
