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
# TestAnalyseNodeVisualModel
# ---------------------------------------------------------------------------

class TestAnalyseNodeVisualModel:
    """Tests for analyse_node's grade-gated services/visual_model integration
    (task 175) - the visual client is only called for setups already graded
    B or better, and its modifier folds into the same final_confidence
    arithmetic sentiment_bonus already contributes to.

    **Validates: Requirements 8.1-8.5 (.kiro/specs/visual-model/requirements.md)**
    """

    @staticmethod
    def _make_liquidity_map(grade):
        from pd_array_engine.models import LiquidityMap, SetupGradeDetail

        setup_grade = None
        if grade is not None:
            setup_grade = SetupGradeDetail(
                grade=grade,
                conditions_met=8 if grade.value == "A+" else 6,
                htf_bias_confirmed=True,
                draw_on_liquidity_identified=True,
                liquidity_sweep_confirmed=True,
                displacement_present=True,
                cisd_confirmed=True,
                entry_pd_array_present=True,
                stop_placement_valid=True,
                time_window_aligned=True,
                grade_reason="test fixture",
            )
        return LiquidityMap(
            analyzed_at=_now_utc(),
            instrument="EURUSD",
            htf_bias={},
            liquidity_levels=[],
            pd_arrays=[],
            crt_phases={},
            cisd_cascade=None,
            draw_on_liquidity=None,
            sweep_detected=False,
            ote_zone=None,
            unicorn=None,
            setup_grade=setup_grade,
        )

    @staticmethod
    def _make_candles_by_tf():
        from pd_array_engine.models import Candle, Timeframe

        base_ts = _now_utc()
        return {
            "M15": [
                Candle(
                    timestamp=base_ts + timedelta(minutes=15 * i),
                    open=1.1000 + i * 0.0001,
                    high=1.1005 + i * 0.0001,
                    low=1.0995 + i * 0.0001,
                    close=1.1002 + i * 0.0001,
                    volume=100,
                    timeframe=Timeframe.M15,
                    instrument="EURUSD",
                )
                for i in range(5)
            ]
        }

    @staticmethod
    def _mock_visual_client(visual_modifier=0.08, hard_block_reason=None, degraded=False):
        from services.visual_model.api.schemas import VisualAnalysisResponse

        client = MagicMock()
        client.analyse.return_value = VisualAnalysisResponse(
            analysis=None,
            visual_modifier=visual_modifier,
            hard_block_reason=hard_block_reason,
            degraded=degraded,
        )
        return client

    def test_analyse_node_calls_visual_client_when_grade_b_or_better(self, fake_redis):
        from pd_array_engine.models import SetupGrade

        liquidity_map = self._make_liquidity_map(SetupGrade.B)
        state = _make_state(
            liquidity_map=liquidity_map, candles_by_tf=self._make_candles_by_tf()
        )
        client = self._mock_visual_client()

        analyse_node(state, redis_client=fake_redis, visual_model_client=client)

        client.analyse.assert_called_once()

    def test_analyse_node_skips_visual_client_when_grade_no_trade(self, fake_redis):
        from pd_array_engine.models import SetupGrade

        liquidity_map = self._make_liquidity_map(SetupGrade.NO_TRADE)
        state = _make_state(
            liquidity_map=liquidity_map, candles_by_tf=self._make_candles_by_tf()
        )
        client = self._mock_visual_client()

        analyse_node(state, redis_client=fake_redis, visual_model_client=client)

        client.analyse.assert_not_called()

    def test_analyse_node_skips_visual_client_when_setup_grade_none(self, fake_redis):
        liquidity_map = self._make_liquidity_map(None)
        state = _make_state(
            liquidity_map=liquidity_map, candles_by_tf=self._make_candles_by_tf()
        )
        client = self._mock_visual_client()

        analyse_node(state, redis_client=fake_redis, visual_model_client=client)

        client.analyse.assert_not_called()

    def test_analyse_node_skips_visual_client_when_candles_by_tf_none(self, fake_redis):
        from pd_array_engine.models import SetupGrade

        liquidity_map = self._make_liquidity_map(SetupGrade.A)
        state = _make_state(liquidity_map=liquidity_map, candles_by_tf=None)
        client = self._mock_visual_client()

        analyse_node(state, redis_client=fake_redis, visual_model_client=client)

        client.analyse.assert_not_called()

    def test_analyse_node_folds_visual_modifier_into_final_confidence(self, fake_redis):
        from pd_array_engine.models import SetupGrade

        liquidity_map = self._make_liquidity_map(SetupGrade.A_PLUS)
        state = _make_state(
            liquidity_map=liquidity_map,
            candles_by_tf=self._make_candles_by_tf(),
            raw_confidence=0.70,
            final_confidence=0.70,
        )
        client = self._mock_visual_client(visual_modifier=0.10)

        result = analyse_node(state, redis_client=fake_redis, visual_model_client=client)

        assert result.final_confidence is not None
        assert result.final_confidence > 0.70

    def test_analyse_node_stores_visual_fields_on_state(self, fake_redis):
        from pd_array_engine.models import SetupGrade

        liquidity_map = self._make_liquidity_map(SetupGrade.A)
        state = _make_state(
            liquidity_map=liquidity_map, candles_by_tf=self._make_candles_by_tf()
        )
        client = self._mock_visual_client(visual_modifier=0.05, hard_block_reason=None)

        result = analyse_node(state, redis_client=fake_redis, visual_model_client=client)

        assert result.visual_modifier == 0.05
        assert result.visual_hard_block_reason is None

    def test_analyse_node_no_visual_client_leaves_fields_unset(self, fake_redis):
        """When visual_model_client is not injected at all (feature not
        wired up / disabled), behaviour must match today's numerical-only
        flow exactly - no crash, no visual fields populated."""
        state = _make_state()
        result = analyse_node(state, redis_client=fake_redis, visual_model_client=None)
        assert result.visual_analysis is None
        assert result.visual_modifier is None

    @pytest.mark.parametrize(
        "sentiment_bonus,calendar_dummy,visual_modifier",
        [(0.0, None, m) for m in (-0.15, -0.05, 0.0, 0.05, 0.15)],
    )
    def test_property_final_confidence_clamped(
        self, fake_redis, sentiment_bonus, calendar_dummy, visual_modifier
    ):
        """Property 3: final_confidence Remains Clamped."""
        from pd_array_engine.models import SetupGrade

        liquidity_map = self._make_liquidity_map(SetupGrade.A_PLUS)
        state = _make_state(
            liquidity_map=liquidity_map,
            candles_by_tf=self._make_candles_by_tf(),
            raw_confidence=0.95,
            final_confidence=0.95,
        )
        client = self._mock_visual_client(visual_modifier=visual_modifier)

        result = analyse_node(state, redis_client=fake_redis, visual_model_client=client)

        assert 0.0 <= result.final_confidence <= 1.0

    @pytest.mark.parametrize("grade_value", ["A+", "A", "B", "NO_TRADE", None])
    def test_property_visual_gate_only_on_graded_setups(self, fake_redis, grade_value):
        """Property 9: Visual Model Only Runs on Graded Setups."""
        from pd_array_engine.models import SetupGrade

        grade = SetupGrade(grade_value) if grade_value is not None else None
        liquidity_map = self._make_liquidity_map(grade)
        state = _make_state(
            liquidity_map=liquidity_map, candles_by_tf=self._make_candles_by_tf()
        )
        client = self._mock_visual_client()

        analyse_node(state, redis_client=fake_redis, visual_model_client=client)

        if grade_value in ("A+", "A", "B"):
            client.analyse.assert_called_once()
        else:
            client.analyse.assert_not_called()


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
# TestDecideNodeVisualHardBlock
# ---------------------------------------------------------------------------

class TestDecideNodeVisualHardBlock:
    """Tests for decide_node's visual hard-block gate (task 176) - joins the
    existing gate stack (calendar_clear, confidence floor, Risk Engine)
    rather than replacing or bypassing any of them.

    **Validates: Requirements 9.1-9.4 (.kiro/specs/visual-model/requirements.md)**
    """

    def test_decide_node_skips_on_visual_hard_block_reason_regardless_of_confidence(self):
        from services.risk_engine.main import RiskEngine

        risk_engine = RiskEngine(redis_client=None)
        state = _make_state(
            raw_confidence=0.95,
            final_confidence=0.95,
            visual_hard_block_reason="visual/numerical direction conflict",
        )

        result = decide_node(state, risk_engine=risk_engine)

        assert result.decision == DecisionAction.SKIP
        assert result.decision_reason == "visual/numerical direction conflict"

    def test_decide_node_hard_block_check_before_confidence_threshold(self):
        """Ordering: the visual hard-block fires even when confidence is well
        above the 0.65 floor - proving it runs as an independent gate, not
        merely a tie-breaker applied only to already-low-confidence setups.

        Note: agent-architecture.md documents a calendar_clear hard block in
        decide_node, but the current implementation never reads
        state.calendar_clear (analyse_node sets it; nothing consumes it) -
        that is a pre-existing gap unrelated to this spec, so this test does
        not assert on it."""
        from services.risk_engine.main import RiskEngine

        risk_engine = RiskEngine(redis_client=None)
        state = _make_state(
            raw_confidence=0.95,
            final_confidence=0.95,
            visual_hard_block_reason="visual model: M15 still in C2_MANIPULATION",
        )
        result = decide_node(state, risk_engine=risk_engine)
        assert result.decision == DecisionAction.SKIP
        assert "manipulation" in (result.decision_reason or "").lower()

    def test_decide_node_unaffected_when_hard_block_reason_none(self):
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse

        mock_engine.validate.return_value = ValidateResponse(approved=True, position_size=5.0)
        state = _make_state(
            raw_confidence=0.80, final_confidence=0.80, visual_hard_block_reason=None
        )

        result = decide_node(state, risk_engine=mock_engine, user_id="user1")

        assert result.decision == DecisionAction.NOTIFY

    def test_decide_node_unaffected_when_visual_analysis_none(self):
        """Visual model never called / degraded - decide_node behaves exactly
        as it did before this integration existed."""
        mock_engine = MagicMock()
        from services.risk_engine.main import ValidateResponse

        mock_engine.validate.return_value = ValidateResponse(approved=True, position_size=5.0)
        state = _make_state(raw_confidence=0.80, final_confidence=0.80)

        result = decide_node(state, risk_engine=mock_engine, user_id="user1")

        assert result.decision == DecisionAction.NOTIFY

    @pytest.mark.parametrize(
        "reason", ["visual/numerical direction conflict: BULLISH vs BEARISH"]
    )
    def test_property_direction_conflict_always_blocks(self, reason):
        """Property 4: Direction Conflict Always Blocks."""
        from services.risk_engine.main import RiskEngine

        risk_engine = RiskEngine(redis_client=None)
        for confidence in (0.66, 0.80, 0.99):
            state = _make_state(
                raw_confidence=confidence,
                final_confidence=confidence,
                visual_hard_block_reason=reason,
            )
            result = decide_node(state, risk_engine=risk_engine)
            assert result.decision == DecisionAction.SKIP

    @pytest.mark.parametrize(
        "reason", ["visual model: M15 still in C2_MANIPULATION, not yet distribution"]
    )
    def test_property_manipulation_always_blocks(self, reason):
        """Property 5: Active Manipulation Always Blocks."""
        from services.risk_engine.main import RiskEngine

        risk_engine = RiskEngine(redis_client=None)
        for confidence in (0.66, 0.80, 0.99):
            state = _make_state(
                raw_confidence=confidence,
                final_confidence=confidence,
                visual_hard_block_reason=reason,
            )
            result = decide_node(state, risk_engine=risk_engine)
            assert result.decision == DecisionAction.SKIP


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
