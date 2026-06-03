"""agent/graph.py — LangGraph agent graph and kill switch.

Wires all agent nodes into a sequential execution graph and exposes:
  - AgentGraph.run(message)                    — execute the full graph for one setup
  - AgentGraph.handle_kill_switch_message(msg) — process a kill switch command
  - create_agent_app(redis_client)             — FastAPI app with /agent/pause,
                                                 /agent/resume, /agent/status endpoints

Kill switch:
  - Stored in Redis key ``risk:kill_switch:global`` → {active: bool}
  - Activated by POST /agent/pause  or a Kafka message {action: "PAUSE"}
  - Cleared  by POST /agent/resume or a Kafka message {action: "RESUME"}
  - The Risk Engine reads this key on every validate() call — when active,
    all trade decisions are rejected with reason "kill switch is active".
  - This means the kill switch is enforced at the Risk Engine gate, which is
    called synchronously by both decide_node and execute_node (recheck).

Graph topology:
    observe → [stale? → learn] → analyse → decide
                                              ├─ NOTIFY  → notify  → learn
                                              ├─ EXECUTE → execute → review → learn
                                              └─ SKIP    → learn

Design notes:
  - All dependencies (redis, risk_engine, fcm_sender, broker_client, journal)
    are injected at construction time for full testability.
  - The graph is implemented as a plain Python class rather than a LangGraph
    StateGraph to avoid the LangGraph runtime dependency in tests.  The edge
    routing logic in agent/edges.py is identical to what would be registered
    as conditional edges in a StateGraph.
  - learn_node is always the terminal node — it logs every outcome (including
    skipped setups) to MongoDB for full auditability (FR-6).

Validates: Requirements FR-6, FR-7, FR-9
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from agent.state import AgentState, AgentMode, DecisionAction
from agent.nodes.observe_node import observe_node
from agent.nodes.analyse_node import analyse_node
from agent.nodes.decide_node import decide_node
from agent.nodes.notify_node import notify_node
from agent.nodes.execute_node import execute_node
from agent.nodes.review_node import review_node
from agent.nodes.learn_node import learn_node
from agent.edges import route_after_decide, route_after_observe, NOTIFY, EXECUTE, LEARN
from services.risk_engine.main import RiskEngine

# Optional import — shadow period enforcer may not be installed in all environments
try:
    from services.shadow_period.mode_enforcer import ShadowPeriodModeEnforcer
    _SHADOW_ENFORCER_AVAILABLE = True
except ImportError:
    ShadowPeriodModeEnforcer = None  # type: ignore[assignment,misc]
    _SHADOW_ENFORCER_AVAILABLE = False

logger = logging.getLogger(__name__)

# Redis key for the global kill switch (must match risk_engine/main.py)
_KILL_SWITCH_KEY = "risk:kill_switch:global"


# ---------------------------------------------------------------------------
# AgentGraph
# ---------------------------------------------------------------------------

class AgentGraph:
    """Orchestrates the full Observe → Analyse → Decide → Act → Review → Learn
    agent execution loop.

    Dependencies are injected at construction time to keep every node
    independently testable.

    Args:
        redis_client:             Synchronous Redis client (fakeredis in tests).
        risk_engine:              RiskEngine instance.
        fcm_sender:               Callable(payload, token) → bool for FCM alerts.
                                  May be None in AUTONOMOUS mode.
        broker_client:            Broker client with place_order / partial_close.
                                  May be None in HUMAN_IN_LOOP mode.
        trade_journal_collection: PyMongo Collection for learn_node.
        user_id:                  User identifier forwarded to the Risk Engine.
    """

    def __init__(
        self,
        redis_client: Any,
        risk_engine: RiskEngine,
        fcm_sender: Optional[Callable],
        broker_client: Any,
        trade_journal_collection: Any,
        user_id: str = "default",
        shadow_enforcer: Optional[Any] = None,
    ) -> None:
        self._redis = redis_client
        self._risk_engine = risk_engine
        self._fcm_sender = fcm_sender
        self._broker_client = broker_client
        self._journal = trade_journal_collection
        self._user_id = user_id
        self._shadow_enforcer = shadow_enforcer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, message: dict) -> AgentState:
        """Execute the full agent graph for a single setup message.

        Args:
            message: Raw Kafka setup message dict.

        Returns:
            Final AgentState after all applicable nodes have run.
        """
        # ── Node 1: observe ────────────────────────────────────────────
        state = observe_node(message)

        # Parse mode from message (observe_node doesn't handle mode field)
        mode_raw = message.get("mode", "HUMAN_IN_LOOP")
        try:
            mode = AgentMode(mode_raw)
        except ValueError:
            mode = AgentMode.HUMAN_IN_LOOP

        # Enforce HUMAN_IN_LOOP during shadow period
        if self._shadow_enforcer is not None:
            mode = self._shadow_enforcer.enforce_human_in_loop(mode)

        state = state.model_copy(update={"mode": mode})

        # Route: stale setup → skip to learn
        if route_after_observe(state) == LEARN:
            return self._run_learn(state)

        # ── Node 2: analyse ────────────────────────────────────────────
        state = analyse_node(state, redis_client=self._redis)

        # ── Node 3: decide ─────────────────────────────────────────────
        state = decide_node(state, risk_engine=self._risk_engine, user_id=self._user_id)

        # ── Route after decide ─────────────────────────────────────────
        route = route_after_decide(state)

        if route == NOTIFY:
            return self._run_notify_path(state)

        if route == EXECUTE:
            return self._run_execute_path(state)

        # SKIP / WAIT — log and return
        return self._run_learn(state)

    def handle_kill_switch_message(self, message: dict) -> None:
        """Process a kill switch Kafka message.

        Args:
            message: Dict with ``action`` key: "PAUSE" activates the kill
                     switch; "RESUME" clears it.
        """
        action = message.get("action", "").upper()
        if action == "PAUSE":
            self._set_kill_switch(active=True)
            logger.warning("AgentGraph: kill switch ACTIVATED via Kafka message")
        elif action == "RESUME":
            self._set_kill_switch(active=False)
            logger.info("AgentGraph: kill switch CLEARED via Kafka message")
        else:
            logger.warning("AgentGraph: unknown kill switch action: %s", action)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_notify_path(self, state: AgentState) -> AgentState:
        """Run notify_node → learn_node."""
        if self._fcm_sender is not None:
            state = notify_node(state, fcm_sender=self._fcm_sender)
        else:
            logger.warning(
                "AgentGraph: notify path selected but no fcm_sender configured"
            )
        return self._run_learn(state)

    def _run_execute_path(self, state: AgentState) -> AgentState:
        """Run execute_node → review_node → learn_node."""
        if self._broker_client is not None:
            state = execute_node(
                state,
                risk_engine=self._risk_engine,
                broker_client=self._broker_client,
                user_id=self._user_id,
            )
            state = review_node(state, broker_client=self._broker_client)
        else:
            logger.warning(
                "AgentGraph: execute path selected but no broker_client configured"
            )
        return self._run_learn(state)

    def _run_learn(self, state: AgentState) -> AgentState:
        """Run learn_node (always the terminal node)."""
        if self._journal is not None:
            state = learn_node(state, trade_journal_collection=self._journal)
        return state

    def _set_kill_switch(self, active: bool) -> None:
        """Write kill switch state to Redis."""
        if self._redis is not None:
            self._redis.set(
                _KILL_SWITCH_KEY,
                json.dumps({"active": active}),
            )


# ---------------------------------------------------------------------------
# FastAPI control endpoints
# ---------------------------------------------------------------------------

class KillSwitchResponse(BaseModel):
    """Response schema for /agent/pause and /agent/resume."""
    kill_switch_active: bool
    message: str


class AgentStatusResponse(BaseModel):
    """Response schema for GET /agent/status."""
    kill_switch_active: bool
    healthy: bool


def create_agent_app(redis_client: Any = None) -> FastAPI:
    """Create and return the FastAPI application for agent control endpoints.

    Exposes:
        POST /agent/pause   — activate kill switch
        POST /agent/resume  — clear kill switch
        GET  /agent/status  — return current kill switch state

    Args:
        redis_client: Synchronous Redis-compatible client.  Pass
            ``fakeredis.FakeRedis`` in tests; real ``redis.Redis`` in production.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="Agent Control", version="1.0.0")

    def _is_kill_switch_active() -> bool:
        if redis_client is None:
            return False
        raw = redis_client.get(_KILL_SWITCH_KEY)
        if raw is None:
            return False
        return bool(json.loads(raw).get("active", False))

    def _set_kill_switch(active: bool) -> None:
        if redis_client is not None:
            redis_client.set(_KILL_SWITCH_KEY, json.dumps({"active": active}))

    @app.post("/agent/pause", response_model=KillSwitchResponse)
    def pause_agent() -> KillSwitchResponse:
        """Activate the kill switch — halts all new trade decisions."""
        _set_kill_switch(active=True)
        logger.warning("Agent paused via /agent/pause endpoint")
        return KillSwitchResponse(
            kill_switch_active=True,
            message="Agent paused. Kill switch is now active.",
        )

    @app.post("/agent/resume", response_model=KillSwitchResponse)
    def resume_agent() -> KillSwitchResponse:
        """Clear the kill switch — resumes normal operation."""
        _set_kill_switch(active=False)
        logger.info("Agent resumed via /agent/resume endpoint")
        return KillSwitchResponse(
            kill_switch_active=False,
            message="Agent resumed. Kill switch is now inactive.",
        )

    @app.get("/agent/status", response_model=AgentStatusResponse)
    def agent_status() -> AgentStatusResponse:
        """Return current agent status and kill switch state."""
        return AgentStatusResponse(
            kill_switch_active=_is_kill_switch_active(),
            healthy=True,
        )

    return app
