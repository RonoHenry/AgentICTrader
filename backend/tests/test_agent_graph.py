"""
Test suite for LangGraph agent graph and kill switch.

TDD Phase: RED → GREEN → REFACTOR

Tests cover:
- Integration test: full graph runs observe → analyse → decide → notify in HUMAN_IN_LOOP mode
- Integration test: full graph runs observe → analyse → decide → execute in AUTONOMOUS mode
- Test: kill switch message sets kill_switch_active=True in Redis
- Test: all nodes check kill_switch_active and halt when True
- Test: POST /agent/pause sets kill switch
- Test: POST /agent/resume clears kill switch

Validates: Requirements FR-6, FR-7
"""
from __future__ import annotations

import json
import sys
import os
import pytest
import fakeredis
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

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
    RiskVerdictEnum,
    TradePlan,
)
from services.risk_engine.main import RiskEngine, ValidateResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_kafka_message(
    instrument: str = "EURUSD",
    timeframe: str = "M5",
    direction: str = "LONG",
    confidence: float = 0.80,
    detected_at: datetime = None,
    mode: str = "HUMAN_IN_LOOP",
    **extra,
) -> dict:
    """Build a minimal Kafka setup message."""
    if detected_at is None:
        detected_at = _now_utc()
    return {
        "setup_id": "setup-graph-001",
        "instrument": instrument,
        "timeframe": timeframe,
        "direction": direction,
        "raw_confidence": confidence,
        "detected_at": detected_at.isoformat(),
        "regime": "TRENDING_BULLISH",
        "patterns": [],
        "mode": mode,
        "trade_plan": {
            "entry": 1.1050,
            "stop_loss": 1.1020,
            "take_profit_1": 1.1110,
            "r_ratio": 2.0,
            "recommended_size": 0.5,
        },
        "time_window": "LONDON_KILLZONE",
        "narrative_phase": "MANIPULATION",
        "time_window_weight": 0.9,
        "is_killzone": True,
        "price_vs_daily_open": "ABOVE",
        "price_vs_weekly_open": "ABOVE",
        "price_vs_true_day_open": "BELOW",
        **extra,
    }


@pytest.fixture
def fake_redis():
    """Provide a synchronous fakeredis client with decode_responses=True."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def mock_risk_engine_approved():
    """Mock RiskEngine that always approves."""
    engine = MagicMock(spec=RiskEngine)
    engine.validate.return_value = ValidateResponse(approved=True, position_size=5.0)
    return engine


@pytest.fixture
def mock_fcm_sender():
    """Mock FCM sender that always succeeds."""
    sender = MagicMock(return_value=True)
    return sender


@pytest.fixture
def mock_broker_client():
    """Mock broker client."""
    broker = MagicMock()
    broker.place_order.return_value = {"order_id": "ORD-GRAPH-001", "trade_id": "TRD-GRAPH-001"}
    return broker


@pytest.fixture
def mock_mongo_collection():
    """Mock MongoDB collection."""
    collection = MagicMock()
    collection.insert_one.return_value = MagicMock(inserted_id="doc-graph-001")
    return collection


# ---------------------------------------------------------------------------
# TestAgentGraphHumanInLoop
# ---------------------------------------------------------------------------

class TestAgentGraphHumanInLoop:
    """Integration tests for the full agent graph in HUMAN_IN_LOOP mode.

    Validates: Requirements FR-6
    """

    def test_full_graph_human_in_loop_runs_observe_analyse_decide_notify(
        self,
        fake_redis,
        mock_risk_engine_approved,
        mock_fcm_sender,
        mock_mongo_collection,
    ):
        """Integration test: full graph runs observe → analyse → decide → notify
        in HUMAN_IN_LOOP mode.

        Validates: Requirements FR-6
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=mock_fcm_sender,
            broker_client=None,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="HUMAN_IN_LOOP", confidence=0.80)
        result = graph.run(message)

        # Graph must complete without error
        assert isinstance(result, AgentState)
        assert result.error is None

        # In HUMAN_IN_LOOP mode, decision must be NOTIFY (not EXECUTE)
        assert result.decision == DecisionAction.NOTIFY

        # FCM sender must have been called
        mock_fcm_sender.assert_called_once()

        # Risk engine must have been called
        mock_risk_engine_approved.validate.assert_called()

    def test_full_graph_human_in_loop_does_not_call_broker(
        self,
        fake_redis,
        mock_risk_engine_approved,
        mock_fcm_sender,
        mock_broker_client,
        mock_mongo_collection,
    ):
        """Integration test: broker is NOT called in HUMAN_IN_LOOP mode.

        Validates: Requirements FR-6
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=mock_fcm_sender,
            broker_client=mock_broker_client,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="HUMAN_IN_LOOP", confidence=0.80)
        graph.run(message)

        # Broker must NOT be called in HUMAN_IN_LOOP mode
        mock_broker_client.place_order.assert_not_called()

    def test_full_graph_human_in_loop_skips_stale_setup(
        self,
        fake_redis,
        mock_risk_engine_approved,
        mock_fcm_sender,
        mock_mongo_collection,
    ):
        """Integration test: graph skips stale setups in HUMAN_IN_LOOP mode.

        Validates: Requirements FR-6
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=mock_fcm_sender,
            broker_client=None,
            trade_journal_collection=mock_mongo_collection,
        )

        stale_time = _now_utc() - timedelta(seconds=61)
        message = _make_kafka_message(mode="HUMAN_IN_LOOP", detected_at=stale_time)
        result = graph.run(message)

        assert result.decision == DecisionAction.SKIP
        # FCM must NOT be called for stale setups
        mock_fcm_sender.assert_not_called()

    def test_full_graph_human_in_loop_skips_low_confidence(
        self,
        fake_redis,
        mock_risk_engine_approved,
        mock_fcm_sender,
        mock_mongo_collection,
    ):
        """Integration test: graph skips low-confidence setups.

        Validates: Requirements FR-6, FR-7
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=mock_fcm_sender,
            broker_client=None,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="HUMAN_IN_LOOP", confidence=0.50)
        result = graph.run(message)

        assert result.decision == DecisionAction.SKIP
        mock_fcm_sender.assert_not_called()


# ---------------------------------------------------------------------------
# TestAgentGraphAutonomous
# ---------------------------------------------------------------------------

class TestAgentGraphAutonomous:
    """Integration tests for the full agent graph in AUTONOMOUS mode.

    Validates: Requirements FR-6
    """

    def test_full_graph_autonomous_runs_observe_analyse_decide_execute(
        self,
        fake_redis,
        mock_risk_engine_approved,
        mock_broker_client,
        mock_mongo_collection,
    ):
        """Integration test: full graph runs observe → analyse → decide → execute
        in AUTONOMOUS mode.

        Validates: Requirements FR-6
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=None,
            broker_client=mock_broker_client,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="AUTONOMOUS", confidence=0.80)
        result = graph.run(message)

        # Graph must complete without error
        assert isinstance(result, AgentState)
        assert result.error is None

        # In AUTONOMOUS mode, decision must be EXECUTE
        assert result.decision == DecisionAction.EXECUTE

        # Broker must have been called
        mock_broker_client.place_order.assert_called_once()

        # Risk engine must have been called (at least once for decide, once for recheck)
        assert mock_risk_engine_approved.validate.call_count >= 2

    def test_full_graph_autonomous_records_broker_order_id(
        self,
        fake_redis,
        mock_risk_engine_approved,
        mock_broker_client,
        mock_mongo_collection,
    ):
        """Integration test: graph records broker_order_id after execution.

        Validates: Requirements FR-6
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=None,
            broker_client=mock_broker_client,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="AUTONOMOUS", confidence=0.80)
        result = graph.run(message)

        assert result.broker_order_id == "ORD-GRAPH-001"
        assert result.trade_id == "TRD-GRAPH-001"

    def test_full_graph_autonomous_does_not_call_fcm(
        self,
        fake_redis,
        mock_risk_engine_approved,
        mock_broker_client,
        mock_mongo_collection,
    ):
        """Integration test: FCM is NOT called in AUTONOMOUS mode.

        Validates: Requirements FR-6
        """
        from agent.graph import AgentGraph

        mock_fcm = MagicMock(return_value=True)

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=mock_fcm,
            broker_client=mock_broker_client,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="AUTONOMOUS", confidence=0.80)
        graph.run(message)

        # FCM must NOT be called in AUTONOMOUS mode
        mock_fcm.assert_not_called()

    def test_full_graph_autonomous_skips_when_risk_recheck_fails(
        self,
        fake_redis,
        mock_broker_client,
        mock_mongo_collection,
    ):
        """Integration test: graph skips execution when risk recheck fails.

        Validates: Requirements FR-6, FR-7
        """
        from agent.graph import AgentGraph

        # First call (decide_node) approves, second call (execute_node recheck) rejects
        engine = MagicMock(spec=RiskEngine)
        engine.validate.side_effect = [
            ValidateResponse(approved=True, position_size=5.0),
            ValidateResponse(approved=False, reason="kill switch active"),
        ]

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=engine,
            fcm_sender=None,
            broker_client=mock_broker_client,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="AUTONOMOUS", confidence=0.80)
        result = graph.run(message)

        # Broker must NOT be called when recheck fails
        mock_broker_client.place_order.assert_not_called()
        assert result.decision == DecisionAction.SKIP


# ---------------------------------------------------------------------------
# TestKillSwitch
# ---------------------------------------------------------------------------

class TestKillSwitch:
    """Tests for the kill switch mechanism.

    Validates: Requirements FR-6, FR-7
    """

    def test_kill_switch_message_sets_kill_switch_active_in_redis(self, fake_redis):
        """Test: kill switch message sets kill_switch_active=True in Redis.

        Validates: Requirements FR-6, FR-7
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=MagicMock(),
            fcm_sender=None,
            broker_client=None,
            trade_journal_collection=MagicMock(),
        )

        # Simulate receiving a kill switch Kafka message
        graph.handle_kill_switch_message({"action": "PAUSE"})

        # Redis must have kill_switch_active=True
        raw = fake_redis.get("risk:kill_switch:global")
        assert raw is not None
        data = json.loads(raw)
        assert data["active"] is True

    def test_kill_switch_resume_clears_kill_switch_in_redis(self, fake_redis):
        """Test: resume message clears kill_switch_active in Redis.

        Validates: Requirements FR-6, FR-7
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=MagicMock(),
            fcm_sender=None,
            broker_client=None,
            trade_journal_collection=MagicMock(),
        )

        # First activate the kill switch
        graph.handle_kill_switch_message({"action": "PAUSE"})

        # Then resume
        graph.handle_kill_switch_message({"action": "RESUME"})

        raw = fake_redis.get("risk:kill_switch:global")
        assert raw is not None
        data = json.loads(raw)
        assert data["active"] is False

    def test_all_nodes_halt_when_kill_switch_active(
        self,
        fake_redis,
        mock_fcm_sender,
        mock_broker_client,
        mock_mongo_collection,
    ):
        """Test: all nodes check kill_switch_active and halt when True.

        When the kill switch is active, the graph must return SKIP without
        calling FCM, broker, or MongoDB.

        Validates: Requirements FR-6, FR-7
        """
        from agent.graph import AgentGraph

        # Activate kill switch in Redis
        fake_redis.set("risk:kill_switch:global", json.dumps({"active": True}))

        # Risk engine that would approve if kill switch weren't active
        engine = MagicMock(spec=RiskEngine)
        engine.validate.return_value = ValidateResponse(
            approved=False,
            reason="kill switch is active — trading halted",
        )

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=engine,
            fcm_sender=mock_fcm_sender,
            broker_client=mock_broker_client,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="HUMAN_IN_LOOP", confidence=0.80)
        result = graph.run(message)

        # Must be SKIP — kill switch halts execution
        assert result.decision == DecisionAction.SKIP

        # FCM and broker must NOT be called
        mock_fcm_sender.assert_not_called()
        mock_broker_client.place_order.assert_not_called()

    def test_kill_switch_active_blocks_autonomous_execution(
        self,
        fake_redis,
        mock_broker_client,
        mock_mongo_collection,
    ):
        """Test: kill switch blocks autonomous execution.

        Validates: Requirements FR-6, FR-7
        """
        from agent.graph import AgentGraph

        # Activate kill switch
        fake_redis.set("risk:kill_switch:global", json.dumps({"active": True}))

        engine = MagicMock(spec=RiskEngine)
        engine.validate.return_value = ValidateResponse(
            approved=False,
            reason="kill switch is active — trading halted",
        )

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=engine,
            fcm_sender=None,
            broker_client=mock_broker_client,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="AUTONOMOUS", confidence=0.80)
        result = graph.run(message)

        assert result.decision == DecisionAction.SKIP
        mock_broker_client.place_order.assert_not_called()


# ---------------------------------------------------------------------------
# TestAgentControlEndpoints
# ---------------------------------------------------------------------------

class TestAgentControlEndpoints:
    """Tests for POST /agent/pause and POST /agent/resume endpoints.

    Validates: Requirements FR-6, FR-9
    """

    def test_post_agent_pause_sets_kill_switch(self, fake_redis):
        """Test: POST /agent/pause sets kill switch active in Redis.

        Validates: Requirements FR-6, FR-9
        """
        from agent.graph import create_agent_app
        from fastapi.testclient import TestClient

        app = create_agent_app(redis_client=fake_redis)
        client = TestClient(app)

        response = client.post("/agent/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch_active"] is True

        # Verify Redis state
        raw = fake_redis.get("risk:kill_switch:global")
        assert raw is not None
        redis_data = json.loads(raw)
        assert redis_data["active"] is True

    def test_post_agent_resume_clears_kill_switch(self, fake_redis):
        """Test: POST /agent/resume clears kill switch in Redis.

        Validates: Requirements FR-6, FR-9
        """
        from agent.graph import create_agent_app
        from fastapi.testclient import TestClient

        # Pre-activate kill switch
        fake_redis.set("risk:kill_switch:global", json.dumps({"active": True}))

        app = create_agent_app(redis_client=fake_redis)
        client = TestClient(app)

        response = client.post("/agent/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch_active"] is False

        # Verify Redis state
        raw = fake_redis.get("risk:kill_switch:global")
        assert raw is not None
        redis_data = json.loads(raw)
        assert redis_data["active"] is False

    def test_post_agent_pause_returns_correct_schema(self, fake_redis):
        """Test: POST /agent/pause response has correct schema.

        Validates: Requirements FR-9
        """
        from agent.graph import create_agent_app
        from fastapi.testclient import TestClient

        app = create_agent_app(redis_client=fake_redis)
        client = TestClient(app)

        response = client.post("/agent/pause")

        assert response.status_code == 200
        data = response.json()
        assert "kill_switch_active" in data
        assert "message" in data

    def test_post_agent_resume_returns_correct_schema(self, fake_redis):
        """Test: POST /agent/resume response has correct schema.

        Validates: Requirements FR-9
        """
        from agent.graph import create_agent_app
        from fastapi.testclient import TestClient

        app = create_agent_app(redis_client=fake_redis)
        client = TestClient(app)

        response = client.post("/agent/resume")

        assert response.status_code == 200
        data = response.json()
        assert "kill_switch_active" in data
        assert "message" in data

    def test_agent_status_endpoint_returns_kill_switch_state(self, fake_redis):
        """Test: GET /agent/status returns current kill switch state.

        Validates: Requirements FR-9
        """
        from agent.graph import create_agent_app
        from fastapi.testclient import TestClient

        app = create_agent_app(redis_client=fake_redis)
        client = TestClient(app)

        # Initially not active
        response = client.get("/agent/status")
        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch_active"] is False

        # Activate kill switch
        client.post("/agent/pause")

        response = client.get("/agent/status")
        data = response.json()
        assert data["kill_switch_active"] is True


# ---------------------------------------------------------------------------
# TestAgentGraphEdgeRouting
# ---------------------------------------------------------------------------

class TestAgentGraphEdgeRouting:
    """Tests for edge routing logic in the agent graph.

    Validates: Requirements FR-6
    """

    def test_graph_routes_to_notify_when_decision_is_notify(
        self,
        fake_redis,
        mock_risk_engine_approved,
        mock_fcm_sender,
        mock_mongo_collection,
    ):
        """Test: graph routes to notify_node when decision=NOTIFY.

        Validates: Requirements FR-6
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=mock_fcm_sender,
            broker_client=None,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="HUMAN_IN_LOOP", confidence=0.80)
        result = graph.run(message)

        assert result.decision == DecisionAction.NOTIFY
        mock_fcm_sender.assert_called_once()

    def test_graph_routes_to_execute_when_decision_is_execute(
        self,
        fake_redis,
        mock_risk_engine_approved,
        mock_broker_client,
        mock_mongo_collection,
    ):
        """Test: graph routes to execute_node when decision=EXECUTE.

        Validates: Requirements FR-6
        """
        from agent.graph import AgentGraph

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=mock_risk_engine_approved,
            fcm_sender=None,
            broker_client=mock_broker_client,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="AUTONOMOUS", confidence=0.80)
        result = graph.run(message)

        assert result.decision == DecisionAction.EXECUTE
        mock_broker_client.place_order.assert_called_once()

    def test_graph_terminates_early_on_skip_decision(
        self,
        fake_redis,
        mock_fcm_sender,
        mock_broker_client,
        mock_mongo_collection,
    ):
        """Test: graph terminates early when decision=SKIP (no FCM, no broker).

        Validates: Requirements FR-6
        """
        from agent.graph import AgentGraph

        engine = MagicMock(spec=RiskEngine)
        engine.validate.return_value = ValidateResponse(
            approved=False,
            reason="daily drawdown limit reached",
        )

        graph = AgentGraph(
            redis_client=fake_redis,
            risk_engine=engine,
            fcm_sender=mock_fcm_sender,
            broker_client=mock_broker_client,
            trade_journal_collection=mock_mongo_collection,
        )

        message = _make_kafka_message(mode="HUMAN_IN_LOOP", confidence=0.80)
        result = graph.run(message)

        assert result.decision == DecisionAction.SKIP
        mock_fcm_sender.assert_not_called()
        mock_broker_client.place_order.assert_not_called()
