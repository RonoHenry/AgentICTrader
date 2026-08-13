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
