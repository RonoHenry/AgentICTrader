"""
Tests for Task 38 — Autonomous Execution Mode.

TDD Phase: RED → GREEN → REFACTOR

Tests cover:
- Integration test: execute_node places live order via broker_tools
- Test: pre-execution risk recheck called before order placement
- Test: HUMAN_IN_LOOP / AUTONOMOUS toggle respected per user
- Test: partial exit at 1R triggered by review_node
- Test: retraining queue triggered in MLflow when 50 new outcomes logged

All tests MUST FAIL (RED) before any implementation changes.

Validates: Requirements FR-6, FR-7
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch, AsyncMock

import fakeredis
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from agent.state import (
    AgentMode,
    AgentState,
    DecisionAction,
    Direction,
    RiskValidation,
    RiskVerdictEnum,
    TradePlan,
)
from agent.nodes.execute_node import execute_node
from agent.nodes.review_node import review_node
from agent.nodes.learn_node import learn_node
from services.risk_engine.main import RiskEngine, ValidateResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_trade_plan(
    entry: float = 1.1050,
    stop_loss: float = 1.1020,
    take_profit_1: float = 1.1110,
    r_ratio: float = 2.0,
    size: float = 0.5,
) -> TradePlan:
    return TradePlan(
        entry=entry,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        r_ratio=r_ratio,
        recommended_size=size,
    )


def _make_state(
    mode: AgentMode = AgentMode.AUTONOMOUS,
    raw_confidence: float = 0.82,
    final_confidence: float = 0.82,
    r_multiple: float | None = None,
    broker_order_id: str | None = None,
    trade_id: str | None = None,
    outcome: str | None = None,
    instrument: str = "EURUSD",
    shadow_period_active: bool = False,
    **extra,
) -> AgentState:
    return AgentState(
        setup_id="setup-auto-001",
        instrument=instrument,
        timeframe="M5",
        direction=Direction.LONG,
        detected_at=_now_utc(),
        raw_confidence=raw_confidence,
        final_confidence=final_confidence,
        mode=mode,
        trade_plan=_make_trade_plan(),
        trade_reasoning="Bullish setup: price swept Asian range low, HTF open bias bullish.",
        time_window="NY_AM_KILLZONE",
        narrative_phase="EXPANSION",
        time_window_weight=0.9,
        is_killzone=True,
        price_vs_daily_open="BELOW",
        price_vs_weekly_open="BELOW",
        price_vs_true_day_open="BELOW",
        r_multiple=r_multiple,
        broker_order_id=broker_order_id,
        trade_id=trade_id,
        outcome=outcome,
        shadow_period_active=shadow_period_active,
        **extra,
    )


def _make_approved_risk_engine() -> MagicMock:
    """Return a mock RiskEngine that always approves."""
    mock = MagicMock(spec=RiskEngine)
    mock.validate.return_value = ValidateResponse(
        approved=True,
        position_size=5.0,
    )
    return mock


def _make_rejected_risk_engine(reason: str = "kill switch active") -> MagicMock:
    """Return a mock RiskEngine that always rejects."""
    mock = MagicMock(spec=RiskEngine)
    mock.validate.return_value = ValidateResponse(
        approved=False,
        reason=reason,
    )
    return mock


# ===========================================================================
# 1. Integration test: execute_node places live order via broker_tools
# ===========================================================================


class TestExecuteNodePlacesLiveOrder:
    """Integration tests verifying execute_node calls broker_tools."""

    def test_execute_node_calls_broker_place_order_in_autonomous_mode(self):
        """execute_node must call broker_client.place_order when risk passes."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {
            "order_id": "ORD-AUTO-001",
            "trade_id": "TRD-AUTO-001",
        }

        state = _make_state(mode=AgentMode.AUTONOMOUS)

        result = execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        mock_broker.place_order.assert_called_once()
        assert result.broker_order_id == "ORD-AUTO-001"
        assert result.trade_id == "TRD-AUTO-001"

    def test_execute_node_order_contains_correct_instrument(self):
        """Order sent to broker_tools must contain the correct instrument."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {
            "order_id": "ORD-002",
            "trade_id": "TRD-002",
        }

        state = _make_state(mode=AgentMode.AUTONOMOUS, instrument="XAUUSD")

        execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        order_arg = mock_broker.place_order.call_args[0][0]
        assert order_arg["instrument"] == "XAUUSD"

    def test_execute_node_order_contains_entry_sl_tp(self):
        """Order sent to broker_tools must contain entry, stop_loss, take_profit."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {
            "order_id": "ORD-003",
            "trade_id": "TRD-003",
        }

        state = _make_state(mode=AgentMode.AUTONOMOUS)

        execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        order_arg = mock_broker.place_order.call_args[0][0]
        assert "stop_loss" in order_arg
        assert "take_profit" in order_arg
        assert order_arg["stop_loss"] == 1.1020
        assert order_arg["take_profit"] == 1.1110

    def test_execute_node_order_contains_direction(self):
        """Order must include direction field mapping LONG/SHORT."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {
            "order_id": "ORD-004",
            "trade_id": "TRD-004",
        }

        state = _make_state(mode=AgentMode.AUTONOMOUS)

        execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        order_arg = mock_broker.place_order.call_args[0][0]
        assert order_arg["direction"] in ("LONG", "SHORT")
        assert order_arg["direction"] == "LONG"

    def test_execute_node_order_contains_setup_id(self):
        """Order must include setup_id for trade traceability."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {
            "order_id": "ORD-005",
            "trade_id": "TRD-005",
        }

        state = _make_state(mode=AgentMode.AUTONOMOUS)

        execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        order_arg = mock_broker.place_order.call_args[0][0]
        assert order_arg.get("setup_id") == "setup-auto-001"

    def test_execute_node_does_not_place_order_when_risk_fails(self):
        """execute_node must NOT call broker_tools if risk recheck fails."""
        risk_engine = _make_rejected_risk_engine("daily drawdown limit reached")
        mock_broker = MagicMock()

        state = _make_state(mode=AgentMode.AUTONOMOUS)

        result = execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        mock_broker.place_order.assert_not_called()
        assert result.decision == DecisionAction.SKIP


# ===========================================================================
# 2. Test: pre-execution risk recheck called before order placement
# ===========================================================================


class TestPreExecutionRiskRecheck:
    """Verify that the risk recheck is mandatory before placing any order."""

    def test_risk_recheck_is_called_before_place_order(self):
        """Risk engine validate() must be called before broker place_order()."""
        call_order = []

        mock_engine = MagicMock(spec=RiskEngine)
        mock_engine.validate.side_effect = lambda req: (
            call_order.append("validate") or ValidateResponse(approved=True, position_size=5.0)
        )

        mock_broker = MagicMock()
        mock_broker.place_order.side_effect = lambda order: (
            call_order.append("place_order") or {"order_id": "ORD-006", "trade_id": "TRD-006"}
        )

        state = _make_state(mode=AgentMode.AUTONOMOUS)

        execute_node(
            state,
            risk_engine=mock_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        assert call_order.index("validate") < call_order.index("place_order"), (
            "risk recheck (validate) must happen before place_order"
        )

    def test_risk_recheck_called_with_correct_instrument(self):
        """Risk recheck request must use the correct instrument from state."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {
            "order_id": "ORD-007",
            "trade_id": "TRD-007",
        }

        state = _make_state(mode=AgentMode.AUTONOMOUS, instrument="GBPUSD")

        execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        validate_arg = risk_engine.validate.call_args[0][0]
        assert validate_arg.instrument == "GBPUSD"

    def test_risk_recheck_called_with_correct_confidence(self):
        """Risk recheck request must pass the final_confidence value."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {
            "order_id": "ORD-008",
            "trade_id": "TRD-008",
        }

        state = _make_state(mode=AgentMode.AUTONOMOUS, final_confidence=0.88)

        execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        validate_arg = risk_engine.validate.call_args[0][0]
        assert validate_arg.confidence == 0.88

    def test_order_not_placed_when_risk_recheck_rejects(self):
        """Broker order must not be placed if risk recheck returns approved=False."""
        risk_engine = _make_rejected_risk_engine("news blackout is active for EURUSD")
        mock_broker = MagicMock()

        state = _make_state(mode=AgentMode.AUTONOMOUS)

        result = execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        mock_broker.place_order.assert_not_called()
        assert result.decision == DecisionAction.SKIP
        assert "blackout" in result.decision_reason.lower()

    def test_state_updated_with_rejection_reason_on_recheck_fail(self):
        """State decision_reason must reflect the rejection reason from Risk Engine."""
        rejection_reason = "weekly drawdown 6.50% has reached the 6% limit"
        risk_engine = _make_rejected_risk_engine(rejection_reason)
        mock_broker = MagicMock()

        state = _make_state(mode=AgentMode.AUTONOMOUS)

        result = execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        assert result.decision_reason is not None
        assert rejection_reason in result.decision_reason


# ===========================================================================
# 3. Test: HUMAN_IN_LOOP / AUTONOMOUS toggle respected per user
# ===========================================================================


class TestAgentModeToggle:
    """Verify the HUMAN_IN_LOOP vs AUTONOMOUS mode toggle is per-user."""

    def test_human_in_loop_mode_does_not_call_broker(self):
        """In HUMAN_IN_LOOP mode execute_node should NOT be reached,
        but if it is (mis-routed), it still skips order placement when
        mode toggle is respected."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()

        # In the full graph, decide_node routes HUMAN_IN_LOOP → notify_node
        # (never reaches execute_node). But we test execute_node in isolation:
        # it must check the mode and only place orders in AUTONOMOUS mode.
        state = _make_state(mode=AgentMode.HUMAN_IN_LOOP)

        result = execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        # execute_node when called in HUMAN_IN_LOOP must not place a live order
        mock_broker.place_order.assert_not_called()

    def test_autonomous_mode_calls_broker(self):
        """In AUTONOMOUS mode execute_node must call broker place_order."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()
        mock_broker.place_order.return_value = {
            "order_id": "ORD-AUTO-010",
            "trade_id": "TRD-AUTO-010",
        }

        state = _make_state(mode=AgentMode.AUTONOMOUS)

        result = execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        mock_broker.place_order.assert_called_once()
        assert result.broker_order_id == "ORD-AUTO-010"

    def test_feature_toggle_get_user_mode_returns_correct_mode(self):
        """UserModeService.get_agent_mode must return the stored mode for a user."""
        from services.auth.user_mode_service import UserModeService

        mock_db = MagicMock()
        service = UserModeService(db=mock_db)

        # Default mode for a new user must be HUMAN_IN_LOOP
        mock_db.get_user_mode.return_value = None
        mode = service.get_agent_mode("user-1")
        assert mode == AgentMode.HUMAN_IN_LOOP

    def test_feature_toggle_set_user_mode_stores_autonomous(self):
        """UserModeService.set_agent_mode must persist AUTONOMOUS for a user."""
        from services.auth.user_mode_service import UserModeService

        mock_db = MagicMock()
        mock_db.set_user_mode.return_value = True
        service = UserModeService(db=mock_db)

        service.set_agent_mode("user-1", AgentMode.AUTONOMOUS)

        mock_db.set_user_mode.assert_called_once_with("user-1", AgentMode.AUTONOMOUS.value)

    def test_feature_toggle_set_user_mode_stores_human_in_loop(self):
        """UserModeService.set_agent_mode must persist HUMAN_IN_LOOP for a user."""
        from services.auth.user_mode_service import UserModeService

        mock_db = MagicMock()
        mock_db.set_user_mode.return_value = True
        service = UserModeService(db=mock_db)

        service.set_agent_mode("user-1", AgentMode.HUMAN_IN_LOOP)

        mock_db.set_user_mode.assert_called_once_with(
            "user-1", AgentMode.HUMAN_IN_LOOP.value
        )

    def test_feature_toggle_get_user_mode_returns_stored_autonomous(self):
        """UserModeService.get_agent_mode returns AUTONOMOUS when stored as such."""
        from services.auth.user_mode_service import UserModeService

        mock_db = MagicMock()
        mock_db.get_user_mode.return_value = AgentMode.AUTONOMOUS.value
        service = UserModeService(db=mock_db)

        mode = service.get_agent_mode("user-1")
        assert mode == AgentMode.AUTONOMOUS


# ===========================================================================
# 4. Test: partial exit at 1R triggered by review_node
# ===========================================================================


class TestReviewNodePartialExit:
    """Verify review_node triggers partial exit behaviour in autonomous mode."""

    def test_review_node_calls_partial_close_at_exactly_1r(self):
        """review_node must call broker_client.partial_close when r_multiple == 1.0."""
        mock_broker = MagicMock()
        mock_broker.partial_close.return_value = {"success": True}

        state = _make_state(
            broker_order_id="ORD-100",
            trade_id="TRD-100",
            r_multiple=1.0,
        )

        result = review_node(state, broker_client=mock_broker)

        mock_broker.partial_close.assert_called_once()

    def test_review_node_partial_close_with_50_percent_ratio(self):
        """review_node must close exactly 50% of the position at 1R."""
        mock_broker = MagicMock()
        mock_broker.partial_close.return_value = {"success": True}

        state = _make_state(
            broker_order_id="ORD-101",
            trade_id="TRD-101",
            r_multiple=1.0,
        )

        review_node(state, broker_client=mock_broker)

        call_kwargs = mock_broker.partial_close.call_args
        # ratio must be 0.5 (50% partial close)
        ratio_arg = (
            call_kwargs[0][1]
            if len(call_kwargs[0]) > 1
            else call_kwargs[1].get("ratio")
        )
        assert ratio_arg == 0.5

    def test_review_node_calls_partial_close_above_1r(self):
        """review_node must trigger partial exit when r_multiple > 1.0."""
        mock_broker = MagicMock()
        mock_broker.partial_close.return_value = {"success": True}

        state = _make_state(
            broker_order_id="ORD-102",
            trade_id="TRD-102",
            r_multiple=1.75,
        )

        result = review_node(state, broker_client=mock_broker)

        mock_broker.partial_close.assert_called_once()

    def test_review_node_does_not_close_at_0_99r(self):
        """review_node must NOT trigger partial exit when r_multiple < 1.0."""
        mock_broker = MagicMock()

        state = _make_state(
            broker_order_id="ORD-103",
            trade_id="TRD-103",
            r_multiple=0.99,
        )

        result = review_node(state, broker_client=mock_broker)

        mock_broker.partial_close.assert_not_called()

    def test_review_node_does_not_close_at_negative_r(self):
        """review_node must NOT trigger partial exit when trade is in loss."""
        mock_broker = MagicMock()

        state = _make_state(
            broker_order_id="ORD-104",
            trade_id="TRD-104",
            r_multiple=-0.5,
        )

        result = review_node(state, broker_client=mock_broker)

        mock_broker.partial_close.assert_not_called()

    def test_review_node_uses_trade_id_for_partial_close(self):
        """review_node must pass trade_id (not order_id) to partial_close."""
        mock_broker = MagicMock()
        mock_broker.partial_close.return_value = {"success": True}

        state = _make_state(
            broker_order_id="ORD-105",
            trade_id="TRD-105",
            r_multiple=1.2,
        )

        review_node(state, broker_client=mock_broker)

        first_arg = mock_broker.partial_close.call_args[0][0]
        assert first_arg == "TRD-105"

    def test_review_node_handles_partial_close_exception_gracefully(self):
        """review_node must not crash if broker partial_close raises an exception."""
        mock_broker = MagicMock()
        mock_broker.partial_close.side_effect = Exception("Network error")

        state = _make_state(
            broker_order_id="ORD-106",
            trade_id="TRD-106",
            r_multiple=1.5,
        )

        result = review_node(state, broker_client=mock_broker)

        # Should return state with error, not raise
        assert result is not None
        assert result.error is not None


# ===========================================================================
# 5. Test: retraining queue triggered in MLflow when 50 new outcomes logged
# ===========================================================================


class TestRetrainingQueue:
    """Verify learn_node triggers MLflow retraining queue after 50 outcomes."""

    def test_learn_node_counts_outcomes_in_journal(self):
        """learn_node must track outcome count after inserting into trade_journal."""
        mock_collection = MagicMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id="doc-001")
        mock_collection.count_documents.return_value = 50

        state = _make_state(
            broker_order_id="ORD-200",
            trade_id="TRD-200",
            outcome="WIN",
            r_multiple=2.0,
        )

        with patch(
            "agent.nodes.learn_node.trigger_retraining_if_needed"
        ) as mock_trigger:
            result = learn_node(state, trade_journal_collection=mock_collection)

        # Should check outcome count after insert
        mock_collection.count_documents.assert_called_once()

    def test_learn_node_triggers_retraining_at_50_outcomes(self):
        """learn_node must call trigger_retraining_if_needed when count == 50."""
        mock_collection = MagicMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id="doc-50")
        mock_collection.count_documents.return_value = 50

        state = _make_state(
            broker_order_id="ORD-201",
            trade_id="TRD-201",
            outcome="WIN",
            r_multiple=1.5,
        )

        with patch(
            "agent.nodes.learn_node.trigger_retraining_if_needed"
        ) as mock_trigger:
            learn_node(state, trade_journal_collection=mock_collection)

        mock_trigger.assert_called_once_with(50)

    def test_learn_node_triggers_retraining_at_multiples_of_50(self):
        """learn_node must call trigger_retraining_if_needed at 100, 150, etc."""
        for count in [50, 100, 150, 200]:
            mock_collection = MagicMock()
            mock_collection.insert_one.return_value = MagicMock(inserted_id="doc-x")
            mock_collection.count_documents.return_value = count

            state = _make_state(
                broker_order_id=f"ORD-{count}",
                trade_id=f"TRD-{count}",
                outcome="WIN",
                r_multiple=1.0,
            )

            with patch(
                "agent.nodes.learn_node.trigger_retraining_if_needed"
            ) as mock_trigger:
                learn_node(state, trade_journal_collection=mock_collection)

            mock_trigger.assert_called_once_with(count), (
                f"retraining should be triggered at count={count}"
            )

    def test_learn_node_does_not_trigger_retraining_below_50(self):
        """learn_node must NOT trigger retraining when count < 50."""
        mock_collection = MagicMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id="doc-x")
        mock_collection.count_documents.return_value = 49

        state = _make_state(
            broker_order_id="ORD-202",
            trade_id="TRD-202",
            outcome="LOSS",
            r_multiple=-1.0,
        )

        with patch(
            "agent.nodes.learn_node.trigger_retraining_if_needed"
        ) as mock_trigger:
            learn_node(state, trade_journal_collection=mock_collection)

        mock_trigger.assert_not_called()

    def test_learn_node_does_not_trigger_retraining_at_non_multiple(self):
        """learn_node must NOT trigger retraining when count is not a multiple of 50."""
        for count in [1, 25, 51, 75, 99, 101]:
            mock_collection = MagicMock()
            mock_collection.insert_one.return_value = MagicMock(inserted_id="doc-x")
            mock_collection.count_documents.return_value = count

            state = _make_state(
                broker_order_id=f"ORD-{count}",
                trade_id=f"TRD-{count}",
                outcome="WIN",
                r_multiple=1.0,
            )

            with patch(
                "agent.nodes.learn_node.trigger_retraining_if_needed"
            ) as mock_trigger:
                learn_node(state, trade_journal_collection=mock_collection)

            mock_trigger.assert_not_called(), (
                f"retraining should NOT be triggered at count={count}"
            )

    def test_trigger_retraining_if_needed_queues_mlflow_run(self):
        """trigger_retraining_if_needed must enqueue an MLflow retraining run."""
        from agent.nodes.learn_node import trigger_retraining_if_needed

        with patch("agent.nodes.learn_node.MLflowTracker") as MockTracker:
            mock_tracker_instance = MagicMock()
            MockTracker.return_value = mock_tracker_instance

            trigger_retraining_if_needed(50)

        # Must interact with MLflow tracker (create run, log param, etc.)
        MockTracker.assert_called_once()

    def test_trigger_retraining_if_needed_logs_outcome_count(self):
        """trigger_retraining_if_needed must log outcome_count to MLflow."""
        from agent.nodes.learn_node import trigger_retraining_if_needed

        with patch("agent.nodes.learn_node.MLflowTracker") as MockTracker:
            mock_tracker_instance = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_tracker_instance.start_run.return_value = mock_ctx
            MockTracker.return_value = mock_tracker_instance

            trigger_retraining_if_needed(100)

        mock_tracker_instance.start_run.assert_called_once()


# ===========================================================================
# 6. End-to-end: shadow period forces HUMAN_IN_LOOP for all users
# ===========================================================================


class TestShadowPeriodModeEnforcement:
    """Verify that shadow_period_active=True forces HUMAN_IN_LOOP."""

    def test_execute_node_skips_broker_when_shadow_period_active(self):
        """When shadow_period_active=True, autonomous execution must be blocked."""
        risk_engine = _make_approved_risk_engine()
        mock_broker = MagicMock()

        state = _make_state(
            mode=AgentMode.AUTONOMOUS,
            shadow_period_active=True,
        )

        result = execute_node(
            state,
            risk_engine=risk_engine,
            broker_client=mock_broker,
            user_id="trader-1",
        )

        # Shadow period active — broker order must NOT be placed
        mock_broker.place_order.assert_not_called()
