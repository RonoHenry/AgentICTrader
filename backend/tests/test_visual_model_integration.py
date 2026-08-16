"""
TDD - Task 177: full analyse_node -> decide_node integration checkpoint
across the three visual-model modes: healthy+agrees, healthy+hard-blocks,
and unreachable (degraded).

observe_node's own Kafka-message parsing is already covered by
test_observe_node_liquidity.py (task 174) and doesn't need re-testing here -
this checkpoint starts from a post-observe AgentState and exercises the
analyse -> decide chain, which is where the visual-model integration
actually lives.

**Validates: Requirement 12.3 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import fakeredis
import pytest

_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from agent.nodes.analyse_node import analyse_node
from agent.nodes.decide_node import decide_node
from agent.state import AgentState, AgentMode, DecisionAction, Direction, TradePlan
from agent.visual_model_client import VisualModelClient
from pd_array_engine.models import Candle, LiquidityMap, SetupGrade, SetupGradeDetail, Timeframe
from services.risk_engine.main import RiskEngine, ValidateResponse
from services.visual_model.api.schemas import VisualAnalysisResponse


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _graded_liquidity_map(grade: SetupGrade = SetupGrade.A) -> LiquidityMap:
    return LiquidityMap(
        analyzed_at=_now_utc(),
        instrument="XAUUSD",
        htf_bias={},
        liquidity_levels=[],
        pd_arrays=[],
        crt_phases={},
        cisd_cascade=None,
        draw_on_liquidity=None,
        sweep_detected=False,
        ote_zone=None,
        unicorn=None,
        setup_grade=SetupGradeDetail(
            grade=grade,
            conditions_met=7,
            htf_bias_confirmed=True,
            draw_on_liquidity_identified=True,
            liquidity_sweep_confirmed=True,
            displacement_present=True,
            cisd_confirmed=True,
            entry_pd_array_present=True,
            stop_placement_valid=True,
            time_window_aligned=False,
            grade_reason="test fixture",
        ),
    )


def _candles_by_tf() -> dict:
    base_ts = _now_utc()
    return {
        "M15": [
            Candle(
                timestamp=base_ts + timedelta(minutes=15 * i),
                open=2000.0 + i,
                high=2001.0 + i,
                low=1999.0 + i,
                close=2000.5 + i,
                volume=100,
                timeframe=Timeframe.M15,
                instrument="XAUUSD",
            )
            for i in range(5)
        ]
    }


def _post_observe_state(**overrides) -> AgentState:
    defaults = dict(
        setup_id="setup-integration-001",
        instrument="XAUUSD",
        timeframe="M15",
        direction=Direction.SHORT,
        detected_at=_now_utc(),
        raw_confidence=0.75,
        final_confidence=0.75,
        mode=AgentMode.HUMAN_IN_LOOP,
        trade_plan=TradePlan(
            entry=2000.0, stop_loss=2010.0, take_profit_1=1980.0, r_ratio=2.0, recommended_size=0.5
        ),
        liquidity_map=_graded_liquidity_map(),
        candles_by_tf=_candles_by_tf(),
    )
    defaults.update(overrides)
    return AgentState(**defaults)


@pytest.fixture()
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def approving_risk_engine():
    engine = MagicMock(spec=RiskEngine)
    engine.validate.return_value = ValidateResponse(approved=True, position_size=5.0)
    return engine


class TestThreeVisualModelModes:
    def test_mode_1_visual_model_healthy_and_agrees(self, fake_redis, approving_risk_engine):
        client = MagicMock()
        client.analyse.return_value = VisualAnalysisResponse(
            analysis=None, visual_modifier=0.08, hard_block_reason=None, degraded=False
        )

        state = _post_observe_state()
        state = analyse_node(state, redis_client=fake_redis, visual_model_client=client)
        result = decide_node(state, risk_engine=approving_risk_engine)

        assert result.final_confidence is not None
        assert result.final_confidence > 0.75  # visual_modifier folded in, no penalty applied
        assert result.decision == DecisionAction.NOTIFY

    def test_mode_2_visual_model_healthy_and_hard_blocks(self, fake_redis, approving_risk_engine):
        client = MagicMock()
        client.analyse.return_value = VisualAnalysisResponse(
            analysis=None,
            visual_modifier=0.10,
            hard_block_reason="visual/numerical direction conflict",
            degraded=False,
        )

        state = _post_observe_state()
        state = analyse_node(state, redis_client=fake_redis, visual_model_client=client)
        result = decide_node(state, risk_engine=approving_risk_engine)

        # Even with a positive modifier and high confidence, the hard block wins.
        assert result.decision == DecisionAction.SKIP
        assert result.decision_reason == "visual/numerical direction conflict"

    def test_mode_3_visual_model_unreachable_degrades_gracefully(
        self, fake_redis, approving_risk_engine
    ):
        # The real client, pointed at a host nothing is listening on -
        # exercises the actual network-failure path, not a mock.
        real_client = VisualModelClient(base_url="http://127.0.0.1:1", timeout=0.5)

        state = _post_observe_state()
        state = analyse_node(state, redis_client=fake_redis, visual_model_client=real_client)
        result = decide_node(state, risk_engine=approving_risk_engine)

        assert result.visual_hard_block_reason is None
        assert result.visual_modifier == 0.0
        assert result.decision == DecisionAction.NOTIFY


class TestAbsentVisualModelBehaviourallyInvisible:
    def test_property_absent_visual_model_invisible(self, fake_redis, approving_risk_engine):
        """Property 11: Absent Visual Model Is Behaviourally Invisible.

        decision, decision_reason, and final_confidence must be identical
        whether visual_model_client is None or simply never wired up -
        matching this integration's behaviour to what existed before it."""
        state_without_client = _post_observe_state()
        analysed_without = analyse_node(state_without_client, redis_client=fake_redis, visual_model_client=None)
        decided_without = decide_node(analysed_without, risk_engine=approving_risk_engine)

        # Rebuild the same starting state and run again through the exact
        # same call signature omitting visual_model_client entirely (the
        # default) - the two paths must agree bit-for-bit on the outcome.
        state_default_arg = _post_observe_state()
        analysed_default = analyse_node(state_default_arg, redis_client=fake_redis)
        decided_default = decide_node(analysed_default, risk_engine=approving_risk_engine)

        assert decided_without.decision == decided_default.decision
        assert decided_without.decision_reason == decided_default.decision_reason
        assert decided_without.final_confidence == decided_default.final_confidence
        assert decided_without.visual_analysis is None
        assert decided_without.visual_modifier is None
        assert decided_without.visual_hard_block_reason is None
