"""
Test suite for LangGraph agent nodes.

TDD Phase: RED -> GREEN -> REFACTOR

Tests cover:
- observe_node rejects stale setups (> 60s old)
- observe_node populates AgentState from Kafka message
- analyse_node fetches sentiment from Redis and adjusts confidence
- analyse_node sets blackout_active from Redis blackout key
- decide_node rejects when confidence < 0.65
- decide_node calls Risk Engine /validate synchronously
- decide_node routes to notify_node in HUMAN_IN_LOOP mode
- decide_node routes to execute_node in AUTONOMOUS mode
- notify_node formats alert with all required fields and dispatches via FCM
- execute_node performs pre-execution risk recheck before placing order
- review_node triggers partial exit at 1R
- learn_node logs outcome to MongoDB trade_journal

Validates: Requirements FR-6, FR-7, FR-8
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
    RiskValidation,
)
from agent.nodes.observe_node import observe_node
from agent.nodes.analyse_node import analyse_node
from agent.nodes.decide_node import decide_node
from agent.nodes.notify_node import notify_node
from agent.nodes.execute_node import execute_node
from agent.nodes.review_node import review_node
from agent.nodes.learn_node import learn_node


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
    **extra,
) -> dict:
    """Build a minimal Kafka setup message."""
    if detected_at is None:
        detected_at = _now_utc()
    return {
        "setup_id": "setup-test-001",
        "instrument": instrument,
        "timeframe": timeframe,
        "direction": direction,
        "raw_confidence": confidence,
        "detected_at": detected_at.isoformat(),
        "regime": "TRENDING_BULLISH",
        "patterns": [],
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


def _make_state(
    instrument: str = "EURUSD",
    timeframe: str = "M5",
    direction: Direction = Direction.LONG,
    raw_confidence: float = 0.80,
    final_confidence: float = 0.80,
    mode: AgentMode = AgentMode.HUMAN_IN_LOOP,
    detected_at: datetime = None,
    **extra,
) -> AgentState:
    """Build a minimal AgentState for testing."""
    if detected_at is None:
        detected_at = _now_utc()
    trade_plan = TradePlan(
        entry=1.1050,
        stop_loss=1.1020,
        take_profit_1=1.1110,
        r_ratio=2.0,
        recommended_size=0.5,
    )
    return AgentState(
        setup_id="setup-test-001",
        instrument=instrument,
        timeframe=timeframe,
        direction=direction,
        detected_at=detected_at,
        raw_confidence=raw_confidence,
        final_confidence=final_confidence,
        mode=mode,
        trade_plan=trade_plan,
        trade_reasoning="Test reasoning",
        time_window="LONDON_KILLZONE",
        narrative_phase="MANIPULATION",
        time_window_weight=0.9,
        is_killzone=True,
        price_vs_daily_open="ABOVE",
        price_vs_weekly_open="ABOVE",
        price_vs_true_day_open="BELOW",
        **extra,
    )


@pytest.fixture
def fake_redis():
    """Provide a synchronous fakeredis client with decode_responses=True."""
    return fakeredis.FakeRedis(decode_responses=True)


# ---------------------------------------------------------------------------
# TestObserveNode
# ---------------------------------------------------------------------------

class TestObserveNode:
    """Tests for observe_node.

    Validates: Requirements FR-6
    """

    def test_observe_node_rejects_stale_setup(self):
        """Test: observe_node rejects stale setups (> 60s old).

        Validates: Requirements FR-6
        """
        stale_time = _now_utc() - timedelta(seconds=61)
        msg = _make_kafka_message(detected_at=stale_time)

        result = observe_node(msg)

        assert result.error is not None
        assert "stale" in result.error.lower() or "old" in result.error.lower() or "expired" in result.error.lower()
        assert result.decision == DecisionAction.SKIP

    def test_observe_node_rejects_exactly_60s_stale(self):
        """Test: observe_node rejects setups exactly 60s old (boundary).

        Validates: Requirements FR-6
        """
        stale_time = _now_utc() - timedelta(seconds=60)
        msg = _make_kafka_message(detected_at=stale_time)

        result = observe_node(msg)

        assert result.error is not None
        assert result.decision == DecisionAction.SKIP

    def test_observe_node_populates_state_from_kafka_message(self):
        """Test: observe_node populates AgentState from Kafka message.

        Validates: Requirements FR-6
        """
        msg = _make_kafka_message(
            instrument="GBPUSD",
            timeframe="H1",
            direction="SHORT",
            confidence=0.75,
        )

        result = observe_node(msg)

        assert result.error is None
        assert result.instrument == "GBPUSD"
        assert result.timeframe == "H1"
        assert result.direction == Direction.SHORT
        assert result.raw_confidence == 0.75
        assert result.setup_id == "setup-test-001"

    def test_observe_node_populates_trade_plan(self):
        """Test: observe_node populates trade_plan from Kafka message.

        Validates: Requirements FR-6
        """
        msg = _make_kafka_message()

        result = observe_node(msg)

        assert result.error is None
        assert result.trade_plan is not None
        assert result.trade_plan.entry == 1.1050
        assert result.trade_plan.stop_loss == 1.1020
        assert result.trade_plan.take_profit_1 == 1.1110
        assert result.trade_plan.r_ratio == 2.0

    def test_observe_node_populates_time_window_fields(self):
        """Test: observe_node populates time window fields from Kafka message.

        Validates: Requirements FR-6, FR-3A
        """
        msg = _make_kafka_message()

        result = observe_node(msg)

        assert result.error is None
        assert result.time_window == "LONDON_KILLZONE"
        assert result.narrative_phase == "MANIPULATION"
        assert result.time_window_weight == 0.9
        assert result.is_killzone is True
        assert result.price_vs_daily_open == "ABOVE"

    def test_observe_node_accepts_fresh_setup(self):
        """Test: observe_node accepts a fresh setup (< 60s old).

        Validates: Requirements FR-6
        """
        fresh_time = _now_utc() - timedelta(seconds=30)
        msg = _make_kafka_message(detected_at=fresh_time)

        result = observe_node(msg)

        assert result.error is None
        assert result.decision != DecisionAction.SKIP


# ---------------------------------------------------------------------------
# TestAnalyseNode
# ---------------------------------------------------------------------------

class TestAnalyseNode:
    """Tests for analyse_node.

    Validates: Requirements FR-5, FR-6
    """

    def test_analyse_node_fetches_sentiment_and_adjusts_confidence(self, fake_redis):
        """Test: analyse_node fetches sentiment from Redis and adjusts confidence.

        Validates: Requirements FR-5, FR-6
        """
        # Seed sentiment: bullish sentiment aligned with LONG direction
        fake_redis.set("sentiment:EURUSD", json.dumps({
            "score": 0.6,
            "direction": "LONG",
            "freshness_seconds": 300,
            "source": "finbert",
        }))

        state = _make_state(
            instrument="EURUSD",
            direction=Direction.LONG,
            raw_confidence=0.75,
            final_confidence=0.75,
        )

        result = analyse_node(state, redis_client=fake_redis)

        assert result.sentiment_score == 0.6
        assert result.sentiment_aligned is True
        # Aligned sentiment should boost confidence
        assert result.final_confidence is not None
        assert result.final_confidence >= state.raw_confidence

    def test_analyse_node_reduces_confidence_on_misaligned_sentiment(self, fake_redis):
        """Test: analyse_node reduces confidence when sentiment opposes direction.

        Validates: Requirements FR-5, FR-6
        """
        # Bearish sentiment but LONG direction -- misaligned
        fake_redis.set("sentiment:EURUSD", json.dumps({
            "score": -0.5,
            "direction": "SHORT",
            "freshness_seconds": 300,
            "source": "finbert",
        }))

        state = _make_state(
            instrument="EURUSD",
            direction=Direction.LONG,
            raw_confidence=0.75,
            final_confidence=0.75,
        )

        result = analyse_node(state, redis_client=fake_redis)

        assert result.sentiment_aligned is False
        # Misaligned sentiment should reduce confidence
        assert result.final_confidence is not None
        assert result.final_confidence <= state.raw_confidence

    def test_analyse_node_sets_calendar_clear_false_when_blackout_active(self, fake_redis):
        """Test: analyse_node sets calendar_clear=False from Redis blackout key.

        Validates: Requirements FR-5, FR-6
        """
        fake_redis.set("blackout:EURUSD", json.dumps({
            "active": True,
            "event_name": "NFP",
            "minutes_remaining": 10.0,
        }))

        state = _make_state(instrument="EURUSD")

        result = analyse_node(state, redis_client=fake_redis)

        assert result.calendar_clear is False

    def test_analyse_node_keeps_calendar_clear_when_no_blackout(self, fake_redis):
        """Test: analyse_node keeps calendar_clear=True when no blackout in Redis.

        Validates: Requirements FR-5, FR-6
        """
        # No blackout key in Redis
        state = _make_state(instrument="EURUSD")

        result = analyse_node(state, redis_client=fake_redis)

        assert result.calendar_clear is True

    def test_analyse_node_keeps_calendar_clear_when_blackout_inactive(self, fake_redis):
        """Test: analyse_node keeps calendar_clear=True when blackout active=False.

        Validates: Requirements FR-5, FR-6
        """
        fake_redis.set("blackout:EURUSD", json.dumps({
            "active": False,
            "event_name": "CPI",
            "minutes_remaining": 0.0,
        }))

        state = _make_state(instrument="EURUSD")

        result = analyse_node(state, redis_client=fake_redis)

        assert result.calendar_clear is True

    def test_analyse_node_handles_missing_sentiment(self, fake_redis):
        """Test: analyse_node handles missing sentiment gracefully.

        Validates: Requirements FR-5, FR-6
        """
        # No sentiment key in Redis
        state = _make_state(
            instrument="EURUSD",
            raw_confidence=0.75,
            final_confidence=0.75,
        )

        result = analyse_node(state, redis_client=fake_redis)

        # Should not crash; final_confidence should remain unchanged
        assert result.final_confidence is not None
        assert result.error is None


# ---------------------------------------------------------------------------
# TestDecideNode
# ---------------------------------------------------------------------------

class TestDecideNode:
    """Tests for decide_node.

    Validates: Requirements FR-6, FR-7
    """

    def test_decide_node_rejects_when_confidence_below_floor(self):
        """Test: decide_node rejects (decision=SKIP) when final_confidence < 0.65.

        Validates: Requirements FR-7
        """
        from services.risk_engine.main import RiskEngine
        risk_engine = RiskEngine(redis_client=None)

        state = _make_state(
            raw_confidence=0.60,
            final_confidence=0.60,
        )

        result = decide_node(state, risk_engine=risk_engine)

        assert result.decision == DecisionAction.SKIP
        assert result.decision_reason is not None
        assert "confidence" in result.decision_reason.lower()

    def test_decide_node_rejects_when_confidence_exactly_at_floor(self):
        """Test: decide_node rejects when final_confidence == 0.64.

        Validates: Requirements FR-7
        """
        from services.risk_engine.main import RiskEngine
        risk_engine = RiskEngine(redis_client=None)

        state = _make_state(
            raw_confidence=0.64,
            final_confidence=0.64,
        )

        result = decide_node(state, risk_engine=risk_engine)

        assert result.decision == DecisionAction.SKIP

    def test_decide_node_calls_risk_engine_validate(self):
        """Test: decide_node calls Risk Engine /validate synchronously.

        Validates: Requirements FR-6, FR-7
        """
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse
        mock_engine.validate.return_value = ValidateResponse(
            approved=True,
            position_size=5.0,
        )

        state = _make_state(
            raw_confidence=0.80,
            final_confidence=0.80,
        )

        decide_node(state, risk_engine=mock_engine, user_id="user1")

        mock_engine.validate.assert_called_once()
        call_args = mock_engine.validate.call_args[0][0]
        assert call_args.instrument == "EURUSD"
        assert call_args.confidence == 0.80

    def test_decide_node_routes_to_notify_in_human_in_loop_mode(self):
        """Test: decide_node routes to notify_node in HUMAN_IN_LOOP mode.

        Validates: Requirements FR-6
        """
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse
        mock_engine.validate.return_value = ValidateResponse(
            approved=True,
            position_size=5.0,
        )

        state = _make_state(
            raw_confidence=0.80,
            final_confidence=0.80,
            mode=AgentMode.HUMAN_IN_LOOP,
        )

        result = decide_node(state, risk_engine=mock_engine, user_id="user1")

        assert result.decision == DecisionAction.NOTIFY

    def test_decide_node_routes_to_execute_in_autonomous_mode(self):
        """Test: decide_node routes to execute_node in AUTONOMOUS mode.

        Validates: Requirements FR-6
        """
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse
        mock_engine.validate.return_value = ValidateResponse(
            approved=True,
            position_size=5.0,
        )

        state = _make_state(
            raw_confidence=0.80,
            final_confidence=0.80,
            mode=AgentMode.AUTONOMOUS,
        )

        result = decide_node(state, risk_engine=mock_engine, user_id="user1")

        assert result.decision == DecisionAction.EXECUTE

    def test_decide_node_skips_when_risk_engine_rejects(self):
        """Test: decide_node sets decision=SKIP when Risk Engine rejects.

        Validates: Requirements FR-6, FR-7
        """
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse
        mock_engine.validate.return_value = ValidateResponse(
            approved=False,
            reason="daily drawdown limit reached",
        )

        state = _make_state(
            raw_confidence=0.80,
            final_confidence=0.80,
        )

        result = decide_node(state, risk_engine=mock_engine, user_id="user1")

        assert result.decision == DecisionAction.SKIP
        assert result.risk_validation is not None
        assert result.risk_validation.verdict == RiskVerdictEnum.REJECTED

    def test_decide_node_sets_risk_validation_on_approval(self):
        """Test: decide_node sets risk_validation with APPROVED verdict.

        Validates: Requirements FR-6, FR-7
        """
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse
        mock_engine.validate.return_value = ValidateResponse(
            approved=True,
            position_size=5.0,
        )

        state = _make_state(
            raw_confidence=0.80,
            final_confidence=0.80,
        )

        result = decide_node(state, risk_engine=mock_engine, user_id="user1")

        assert result.risk_validation is not None
        assert result.risk_validation.verdict == RiskVerdictEnum.APPROVED


# ---------------------------------------------------------------------------
# TestNotifyNode
# ---------------------------------------------------------------------------

class TestNotifyNode:
    """Tests for notify_node.

    Validates: Requirements FR-8
    """

    def test_notify_node_formats_alert_with_all_required_fields(self):
        """Test: notify_node formats alert with all required fields and dispatches via FCM.

        Validates: Requirements FR-8
        """
        state = _make_state(
            instrument="EURUSD",
            direction=Direction.LONG,
            final_confidence=0.82,
        )

        captured_payload = {}

        def mock_send_fcm(payload: dict, token: str = None) -> bool:
            captured_payload.update(payload)
            return True

        result = notify_node(state, fcm_sender=mock_send_fcm)

        # Verify all required FR-8 fields are present
        required_fields = [
            "instrument",
            "direction",
            "confidence_score",
            "entry_price",
            "sl_price",
            "tp_price",
            "r_ratio",
            "reasoning",
            "time_window",
            "narrative_phase",
            "price_vs_daily_open",
            "price_vs_true_day_open",
            "is_killzone",
        ]
        for field in required_fields:
            assert field in captured_payload, f"Missing required field: {field}"

    def test_notify_node_dispatches_via_fcm(self):
        """Test: notify_node calls FCM sender.

        Validates: Requirements FR-8
        """
        state = _make_state()
        mock_fcm = MagicMock(return_value=True)

        result = notify_node(state, fcm_sender=mock_fcm)

        mock_fcm.assert_called_once()

    def test_notify_node_sets_correct_instrument_in_payload(self):
        """Test: notify_node includes correct instrument in alert payload.

        Validates: Requirements FR-8
        """
        state = _make_state(instrument="XAUUSD", direction=Direction.SHORT)
        captured = {}

        def capture(payload, token=None):
            captured.update(payload)
            return True

        notify_node(state, fcm_sender=capture)

        assert captured["instrument"] == "XAUUSD"
        assert captured["direction"] == "SHORT"

    def test_notify_node_includes_entry_sl_tp_prices(self):
        """Test: notify_node includes entry, SL, TP prices in alert.

        Validates: Requirements FR-8
        """
        state = _make_state()
        captured = {}

        def capture(payload, token=None):
            captured.update(payload)
            return True

        notify_node(state, fcm_sender=capture)

        assert captured["entry_price"] == 1.1050
        assert captured["sl_price"] == 1.1020
        assert captured["tp_price"] == 1.1110
        assert captured["r_ratio"] == 2.0


# ---------------------------------------------------------------------------
# TestExecuteNode
# ---------------------------------------------------------------------------

class TestExecuteNode:
    """Tests for execute_node.

    Validates: Requirements FR-6, FR-7
    """

    def test_execute_node_performs_pre_execution_risk_recheck(self):
        """Test: execute_node performs pre-execution risk recheck before placing order.

        Validates: Requirements FR-6, FR-7
        """
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse
        mock_engine.validate.return_value = ValidateResponse(
            approved=True,
            position_size=5.0,
        )

        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {"order_id": "ORD-001", "trade_id": "TRD-001"}

        state = _make_state(
            raw_confidence=0.80,
            final_confidence=0.80,
            mode=AgentMode.AUTONOMOUS,
        )

        result = execute_node(
            state,
            risk_engine=mock_engine,
            broker_client=mock_broker,
            user_id="user1",
        )

        # Risk engine must be called for recheck
        mock_engine.validate.assert_called_once()

    def test_execute_node_places_order_when_recheck_passes(self):
        """Test: execute_node places broker order when risk recheck passes.

        Validates: Requirements FR-6
        """
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse
        mock_engine.validate.return_value = ValidateResponse(
            approved=True,
            position_size=5.0,
        )

        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {"order_id": "ORD-001", "trade_id": "TRD-001"}

        state = _make_state(
            raw_confidence=0.80,
            final_confidence=0.80,
            mode=AgentMode.AUTONOMOUS,
        )

        result = execute_node(
            state,
            risk_engine=mock_engine,
            broker_client=mock_broker,
            user_id="user1",
        )

        mock_broker.place_order.assert_called_once()
        assert result.broker_order_id == "ORD-001"

    def test_execute_node_skips_order_when_recheck_fails(self):
        """Test: execute_node does not place order when risk recheck fails.

        Validates: Requirements FR-6, FR-7
        """
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse
        mock_engine.validate.return_value = ValidateResponse(
            approved=False,
            reason="kill switch active",
        )

        mock_broker = MagicMock()

        state = _make_state(
            raw_confidence=0.80,
            final_confidence=0.80,
            mode=AgentMode.AUTONOMOUS,
        )

        result = execute_node(
            state,
            risk_engine=mock_engine,
            broker_client=mock_broker,
            user_id="user1",
        )

        mock_broker.place_order.assert_not_called()
        assert result.decision == DecisionAction.SKIP


# ---------------------------------------------------------------------------
# TestReviewNode
# ---------------------------------------------------------------------------

class TestReviewNode:
    """Tests for review_node.

    Validates: Requirements FR-6
    """

    def test_review_node_triggers_partial_exit_at_1r(self):
        """Test: review_node triggers partial exit at 1R profit.

        Validates: Requirements FR-6
        """
        mock_broker = MagicMock()
        mock_broker.partial_close.return_value = {"success": True}

        # State with 1R profit reached (r_multiple >= 1.0)
        state = _make_state(
            broker_order_id="ORD-001",
            trade_id="TRD-001",
            r_multiple=1.0,
        )

        result = review_node(state, broker_client=mock_broker)

        mock_broker.partial_close.assert_called_once()

    def test_review_node_does_not_exit_below_1r(self):
        """Test: review_node does not trigger partial exit below 1R.

        Validates: Requirements FR-6
        """
        mock_broker = MagicMock()

        state = _make_state(
            broker_order_id="ORD-001",
            trade_id="TRD-001",
            r_multiple=0.5,
        )

        result = review_node(state, broker_client=mock_broker)

        mock_broker.partial_close.assert_not_called()

    def test_review_node_triggers_exit_above_1r(self):
        """Test: review_node triggers partial exit when r_multiple > 1.0.

        Validates: Requirements FR-6
        """
        mock_broker = MagicMock()
        mock_broker.partial_close.return_value = {"success": True}

        state = _make_state(
            broker_order_id="ORD-001",
            trade_id="TRD-001",
            r_multiple=1.5,
        )

        result = review_node(state, broker_client=mock_broker)

        mock_broker.partial_close.assert_called_once()


# ---------------------------------------------------------------------------
# TestLearnNode
# ---------------------------------------------------------------------------

class TestLearnNode:
    """Tests for learn_node.

    Validates: Requirements FR-6
    """

    def test_learn_node_logs_outcome_to_mongodb(self):
        """Test: learn_node logs outcome to MongoDB trade_journal collection.

        Validates: Requirements FR-6
        """
        mock_collection = MagicMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id="doc-001")

        state = _make_state(
            broker_order_id="ORD-001",
            trade_id="TRD-001",
            outcome="WIN",
            r_multiple=2.0,
            close_price=1.1110,
            close_time=_now_utc(),
        )

        result = learn_node(state, trade_journal_collection=mock_collection)

        mock_collection.insert_one.assert_called_once()
        inserted_doc = mock_collection.insert_one.call_args[0][0]

        # Verify key fields are logged
        assert inserted_doc["setup_id"] == "setup-test-001"
        assert inserted_doc["instrument"] == "EURUSD"
        assert inserted_doc["outcome"] == "WIN"
        assert inserted_doc["r_multiple"] == 2.0

    def test_learn_node_includes_trade_plan_in_journal(self):
        """Test: learn_node includes trade plan details in journal entry.

        Validates: Requirements FR-6
        """
        mock_collection = MagicMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id="doc-001")

        state = _make_state(
            broker_order_id="ORD-001",
            trade_id="TRD-001",
            outcome="LOSS",
            r_multiple=-1.0,
        )

        result = learn_node(state, trade_journal_collection=mock_collection)

        mock_collection.insert_one.assert_called_once()
        inserted_doc = mock_collection.insert_one.call_args[0][0]

        assert "entry_price" in inserted_doc or "trade_plan" in inserted_doc

    def test_learn_node_returns_updated_state(self):
        """Test: learn_node returns the updated AgentState.

        Validates: Requirements FR-6
        """
        mock_collection = MagicMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id="doc-001")

        state = _make_state(outcome="WIN", r_multiple=1.5)

        result = learn_node(state, trade_journal_collection=mock_collection)

        assert isinstance(result, AgentState)
        assert result.setup_id == state.setup_id
