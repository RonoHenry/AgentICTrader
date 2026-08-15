"""
Test suite for the agent_decisions audit trail (Task 39).

TDD Phase: RED -> GREEN -> REFACTOR

Tests cover:
- log_agent_decision inserts a document into the agent_decisions collection
- Document includes input context (setup/ML/sentiment/time-window fields)
- Document includes the risk validation result when present, None when absent
- Document includes reasoning (trade_reasoning, decision_reason)
- Document includes order details when the setup was executed, None otherwise
- Insert failure is non-fatal — logged, does not crash the graph
- AgentGraph writes to agent_decisions on every route (NOTIFY / EXECUTE / SKIP)
- agent_decisions_collection is optional — AgentGraph still works without it

Validates: Requirements FR-6 (Phase 4 Task 39 — Live validation run and audit trail)
"""
from __future__ import annotations

import sys
import os
import pytest
import fakeredis
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from agent.state import (
    AgentState,
    AgentMode,
    Direction,
    DecisionAction,
    RiskValidation,
    RiskVerdictEnum,
    TradePlan,
    Pattern,
)
from agent.audit_trail import log_agent_decision
from services.risk_engine.main import RiskEngine, ValidateResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_state(**extra) -> AgentState:
    """Build a minimal AgentState for testing, mirroring test_agent_nodes.py."""
    defaults = dict(
        setup_id="setup-audit-001",
        instrument="EURUSD",
        timeframe="M5",
        direction=Direction.LONG,
        detected_at=_now_utc(),
        raw_confidence=0.80,
        final_confidence=0.82,
        mode=AgentMode.HUMAN_IN_LOOP,
        trade_plan=TradePlan(
            entry=1.1050,
            stop_loss=1.1020,
            take_profit_1=1.1110,
            r_ratio=2.0,
            recommended_size=0.5,
        ),
        trade_reasoning="Bullish OTE at discount of HTF dealing range",
        time_window="LONDON_KILLZONE",
        narrative_phase="MANIPULATION",
        is_killzone=True,
    )
    defaults.update(extra)
    return AgentState(**defaults)


@pytest.fixture
def mock_collection():
    """Mock MongoDB agent_decisions collection."""
    collection = MagicMock()
    collection.insert_one.return_value = MagicMock(inserted_id="audit-doc-001")
    return collection


# ---------------------------------------------------------------------------
# TestLogAgentDecision
# ---------------------------------------------------------------------------

class TestLogAgentDecision:
    """Unit tests for log_agent_decision (agent/audit_trail.py)."""

    def test_inserts_document_into_collection(self, mock_collection):
        state = _make_state(
            decision=DecisionAction.NOTIFY,
            decision_reason="Risk Engine approved — human-in-the-loop notification",
            risk_validation=RiskValidation(
                verdict=RiskVerdictEnum.APPROVED, recommended_size=0.5,
            ),
        )

        log_agent_decision(state, agent_decisions_collection=mock_collection)

        mock_collection.insert_one.assert_called_once()

    def test_document_includes_input_context(self, mock_collection):
        state = _make_state(
            regime="TRENDING_BULLISH",
            regime_confidence=0.9,
            patterns=[Pattern(type="FVG", confidence=0.85)],
            sentiment_score=0.6,
            sentiment_aligned=True,
            decision=DecisionAction.SKIP,
            decision_reason="confidence 0.40 is below the floor 0.65",
        )

        log_agent_decision(state, agent_decisions_collection=mock_collection)
        doc = mock_collection.insert_one.call_args[0][0]

        assert doc["input_context"]["instrument"] == "EURUSD"
        assert doc["input_context"]["timeframe"] == "M5"
        assert doc["input_context"]["regime"] == "TRENDING_BULLISH"
        assert doc["input_context"]["final_confidence"] == 0.82
        assert doc["input_context"]["sentiment_score"] == 0.6
        assert doc["input_context"]["time_window"] == "LONDON_KILLZONE"
        assert len(doc["input_context"]["patterns"]) == 1

    def test_document_includes_risk_validation_when_present(self, mock_collection):
        state = _make_state(
            decision=DecisionAction.SKIP,
            decision_reason="daily drawdown 3.10% has reached the 3.0% limit",
            risk_validation=RiskValidation(
                verdict=RiskVerdictEnum.REJECTED,
                rejection_reason="daily drawdown 3.10% has reached the 3.0% limit",
            ),
        )

        log_agent_decision(state, agent_decisions_collection=mock_collection)
        doc = mock_collection.insert_one.call_args[0][0]

        assert doc["risk_validation"]["verdict"] == "REJECTED"
        assert "drawdown" in doc["risk_validation"]["rejection_reason"]

    def test_document_risk_validation_is_none_when_absent(self, mock_collection):
        # Stale-setup path: observe_node routes straight to learn, decide_node
        # never ran, so risk_validation was never populated on the state.
        state = _make_state(decision=None, decision_reason=None, risk_validation=None)

        log_agent_decision(state, agent_decisions_collection=mock_collection)
        doc = mock_collection.insert_one.call_args[0][0]

        assert doc["risk_validation"] is None

    def test_document_includes_reasoning(self, mock_collection):
        state = _make_state(
            trade_reasoning="Bullish OTE at discount of HTF dealing range",
            decision=DecisionAction.NOTIFY,
            decision_reason="Risk Engine approved — human-in-the-loop notification",
        )

        log_agent_decision(state, agent_decisions_collection=mock_collection)
        doc = mock_collection.insert_one.call_args[0][0]

        assert doc["reasoning"] == "Bullish OTE at discount of HTF dealing range"
        assert doc["decision_reason"] == "Risk Engine approved — human-in-the-loop notification"
        assert doc["decision"] == "NOTIFY"

    def test_document_includes_order_details_when_executed(self, mock_collection):
        state = _make_state(
            mode=AgentMode.AUTONOMOUS,
            decision=DecisionAction.EXECUTE,
            broker_order_id="ORD-AUDIT-001",
            trade_id="TRD-AUDIT-001",
            risk_validation=RiskValidation(
                verdict=RiskVerdictEnum.APPROVED, recommended_size=0.5,
            ),
        )

        log_agent_decision(state, agent_decisions_collection=mock_collection)
        doc = mock_collection.insert_one.call_args[0][0]

        assert doc["order_details"]["broker_order_id"] == "ORD-AUDIT-001"
        assert doc["order_details"]["trade_id"] == "TRD-AUDIT-001"
        assert doc["order_details"]["entry"] == 1.1050

    def test_document_order_details_none_when_not_executed(self, mock_collection):
        state = _make_state(
            decision=DecisionAction.SKIP,
            broker_order_id=None,
            trade_id=None,
        )

        log_agent_decision(state, agent_decisions_collection=mock_collection)
        doc = mock_collection.insert_one.call_args[0][0]

        assert doc["order_details"] is None

    def test_document_includes_user_id(self, mock_collection):
        state = _make_state(decision=DecisionAction.NOTIFY)

        log_agent_decision(
            state, agent_decisions_collection=mock_collection, user_id="user-42",
        )
        doc = mock_collection.insert_one.call_args[0][0]

        assert doc["user_id"] == "user-42"

    def test_returns_updated_state(self, mock_collection):
        state = _make_state(decision=DecisionAction.NOTIFY)

        result = log_agent_decision(state, agent_decisions_collection=mock_collection)

        assert isinstance(result, AgentState)
        assert result.setup_id == state.setup_id

    def test_insert_failure_is_non_fatal(self, mock_collection):
        mock_collection.insert_one.side_effect = Exception("Mongo connection lost")
        state = _make_state(decision=DecisionAction.NOTIFY)

        # Must not raise
        result = log_agent_decision(state, agent_decisions_collection=mock_collection)

        assert isinstance(result, AgentState)


# ---------------------------------------------------------------------------
# TestAgentGraphAuditTrailIntegration
# ---------------------------------------------------------------------------

class TestAgentGraphAuditTrailIntegration:
    """Integration tests: AgentGraph writes to agent_decisions on every route."""

    def _make_kafka_message(self, **extra) -> dict:
        detected_at = _now_utc()
        message = {
            "setup_id": "setup-graph-audit-001",
            "instrument": "EURUSD",
            "timeframe": "M5",
            "direction": "LONG",
            "raw_confidence": 0.80,
            "detected_at": detected_at.isoformat(),
            "regime": "TRENDING_BULLISH",
            "patterns": [],
            "mode": "HUMAN_IN_LOOP",
            "trade_plan": {
                "entry": 1.1050,
                "stop_loss": 1.1020,
                "take_profit_1": 1.1110,
                "r_ratio": 2.0,
                "recommended_size": 0.5,
            },
        }
        message.update(extra)
        return message

    @pytest.fixture
    def fake_redis(self):
        return fakeredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def mock_risk_engine_approved(self):
        engine = MagicMock(spec=RiskEngine)
        engine.validate.return_value = ValidateResponse(approved=True, position_size=5.0)
        return engine

    @pytest.fixture
    def mock_fcm_sender(self):
        return MagicMock(return_value=True)

    @pytest.fixture
    def mock_journal(self):
        collection = MagicMock()
        collection.insert_one.return_value = MagicMock(inserted_id="journal-001")
        collection.count_documents.return_value = 1
        return collection

    @pytest.fixture
    def mock_agent_decisions(self):
        collection = MagicMock()
        collection.insert_one.return_value = MagicMock(inserted_id="audit-001")
        return collection

    def test_graph_logs_to_agent_decisions_on_notify_path(
        self, fake_redis, mock_risk_engine_approved, mock_fcm_sender,
        mock_journal, mock_agent_decisions,
    ):
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=mock_fcm_sender,
            broker_client=None,
            trade_journal_collection=mock_journal,
            agent_decisions_collection=mock_agent_decisions,
        )

        graph.run(self._make_kafka_message(mode="HUMAN_IN_LOOP"))

        mock_agent_decisions.insert_one.assert_called_once()
        doc = mock_agent_decisions.insert_one.call_args[0][0]
        assert doc["decision"] == "NOTIFY"
        assert doc["risk_validation"]["verdict"] == "APPROVED"

    def test_graph_logs_to_agent_decisions_on_skip_path(
        self, fake_redis, mock_risk_engine_approved, mock_fcm_sender,
        mock_journal, mock_agent_decisions,
    ):
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=mock_fcm_sender,
            broker_client=None,
            trade_journal_collection=mock_journal,
            agent_decisions_collection=mock_agent_decisions,
        )

        # Below the 0.65 confidence floor -> SKIP, no risk engine call
        graph.run(self._make_kafka_message(raw_confidence=0.30))

        mock_agent_decisions.insert_one.assert_called_once()
        doc = mock_agent_decisions.insert_one.call_args[0][0]
        assert doc["decision"] == "SKIP"

    def test_graph_logs_to_agent_decisions_on_execute_path(
        self, fake_redis, mock_risk_engine_approved, mock_journal, mock_agent_decisions,
    ):
        from agent.graph import AgentGraph

        broker = MagicMock()
        broker.place_order.return_value = {"order_id": "ORD-1", "trade_id": "TRD-1"}

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=None,
            broker_client=broker,
            trade_journal_collection=mock_journal,
            agent_decisions_collection=mock_agent_decisions,
        )

        graph.run(self._make_kafka_message(mode="AUTONOMOUS"))

        mock_agent_decisions.insert_one.assert_called_once()
        doc = mock_agent_decisions.insert_one.call_args[0][0]
        assert doc["decision"] == "EXECUTE"
        assert doc["order_details"]["broker_order_id"] == "ORD-1"

    def test_graph_works_without_agent_decisions_collection(
        self, fake_redis, mock_risk_engine_approved, mock_fcm_sender, mock_journal,
    ):
        """Backward compatibility: agent_decisions_collection is optional."""
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=mock_fcm_sender,
            broker_client=None,
            trade_journal_collection=mock_journal,
        )

        result = graph.run(self._make_kafka_message())

        assert isinstance(result, AgentState)
        assert result.error is None
