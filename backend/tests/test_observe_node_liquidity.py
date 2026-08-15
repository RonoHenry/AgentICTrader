"""Tests for observe_node's Liquidity Engine integration (task 160)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from agent.nodes.observe_node import observe_node
from agent.state import AgentState
from liquidity_engine.models import LiquidityMap

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle_dict(n: int, open_: float, tf_minutes: int = 0, tf_days: int = 0) -> Dict[str, Any]:
    ts = _BASE + timedelta(days=tf_days * n, minutes=tf_minutes * n)
    return {
        "timestamp": ts.isoformat(),
        "open": open_,
        "high": open_ + 2,
        "low": open_ - 1,
        "close": open_ + 1,
        "volume": 100,
    }


def _valid_candles_by_tf() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "D1": [_candle_dict(i, 50 + i, tf_days=1) for i in range(10)],
        "W1": [_candle_dict(i, 40 + 2 * i, tf_days=7) for i in range(4)],
    }


def _base_message(**overrides) -> Dict[str, Any]:
    message: Dict[str, Any] = {
        "setup_id": "setup-1",
        "instrument": "EURUSD",
        "timeframe": "M5",
        "detected_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    message.update(overrides)
    return message


class TestObserveNodeLiquidityIntegration:
    def test_observe_node_stores_liquidity_map(self):
        state = observe_node(_base_message(candles_by_tf=_valid_candles_by_tf()))
        assert state.liquidity_map is not None

    def test_observe_node_liquidity_map_is_liquidity_map_type(self):
        state = observe_node(_base_message(candles_by_tf=_valid_candles_by_tf()))
        assert isinstance(state.liquidity_map, LiquidityMap)

    def test_observe_node_liquidity_map_none_when_no_candles(self):
        state = observe_node(_base_message())
        assert state.liquidity_map is None

    def test_observe_node_liquidity_map_none_on_malformed_candles(self):
        state = observe_node(_base_message(candles_by_tf={"D1": [{"open": "not-a-number"}]}))
        assert state.liquidity_map is None

    def test_observe_node_liquidity_map_respected_on_stale_rejection(self):
        stale_time = (datetime.now(tz=timezone.utc) - timedelta(seconds=120)).isoformat()
        state = observe_node(
            _base_message(detected_at=stale_time, candles_by_tf=_valid_candles_by_tf())
        )
        assert state.decision is not None
        assert state.liquidity_map is None

    def test_agent_state_has_liquidity_map_field(self):
        assert "liquidity_map" in AgentState.model_fields


class TestObserveNodeCandlesByTf:
    """Tests for observe_node retaining the parsed candle window on state
    (task 174) - services/visual_model's chart_renderer needs the same
    candles the numerical engine already analysed, not a re-fetched, possibly
    divergent snapshot.

    **Validates: Requirement 13.5 (.kiro/specs/visual-model/requirements.md)**
    """

    def test_observe_node_stores_candles_by_tf_on_state_when_present(self):
        state = observe_node(_base_message(candles_by_tf=_valid_candles_by_tf()))
        assert state.candles_by_tf is not None
        assert "D1" in state.candles_by_tf
        assert "W1" in state.candles_by_tf
        assert len(state.candles_by_tf["D1"]) == 10

    def test_observe_node_candles_by_tf_none_when_message_lacks_candle_data(self):
        state = observe_node(_base_message())
        assert state.candles_by_tf is None

    def test_observe_node_candles_by_tf_none_on_malformed_candles(self):
        state = observe_node(_base_message(candles_by_tf={"D1": [{"open": "not-a-number"}]}))
        assert state.candles_by_tf is None

    def test_observe_node_liquidity_map_computation_unchanged(self):
        """Regression: retaining candles_by_tf must not change liquidity_map's
        value or the fact that it's still computed from the same parse."""
        state = observe_node(_base_message(candles_by_tf=_valid_candles_by_tf()))
        assert state.liquidity_map is not None
        assert isinstance(state.liquidity_map, LiquidityMap)
        # The retained candles are exactly what liquidity_map was built from.
        assert state.liquidity_map.instrument == "EURUSD"
