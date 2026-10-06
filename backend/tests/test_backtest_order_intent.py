"""
Tests for agent/order_intent.py — the order the live runner and the
backtester derive from a graded setup.

Task 189 (.kiro/specs/algo-backtester/tasks.md): deterministic setup_id.
Validates: Requirements 1.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import pytest

from agent.order_intent import setup_id_for
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Timeframe
from tests.test_liquidity_engine_perf import FIXTURES, _load


def test_setup_id_stable_for_same_array_across_consecutive_bars():
    # A real window the live runner graded A (MT5 EURUSD, M5 entries). One
    # and two bars earlier the engine selects the same entry array, so the
    # setup must keep its id: D6 allows one attempt per setup_id, and a
    # fresh id every bar would let it re-enter after a stop-out.
    record, candles_by_tf, t = _load(FIXTURES / "EURUSD_M5.json.gz")
    entry_tf = Timeframe(record["entry_tf"])
    bar = candles_by_tf[entry_tf][-1].timestamp - candles_by_tf[entry_tf][-2].timestamp

    ids = []
    for bars_back in (2, 1, 0):
        window = {
            tf: candles[: len(candles) - bars_back] if tf == entry_tf else candles
            for tf, candles in candles_by_tf.items()
        }
        grade = LiquidityMappingEngine().analyze(window, record["instrument"], t - bars_back * bar).setup_grade
        assert grade.entry_array_id is not None
        ids.append(setup_id_for(record["instrument"], entry_tf, grade.entry_array_id))

    assert len(set(ids)) == 1


def test_setup_id_differs_for_different_arrays_or_entry_tf():
    base = setup_id_for("EURUSD", Timeframe.M5, "array-1")

    assert setup_id_for("EURUSD", Timeframe.M5, "array-1") == base
    assert setup_id_for("EURUSD", Timeframe.M5, "array-2") != base
    assert setup_id_for("EURUSD", Timeframe.M15, "array-1") != base
    assert setup_id_for("GBPUSD", Timeframe.M5, "array-1") != base


def test_setup_id_requires_an_entry_array():
    # Without an array every array-less setup would share one id, and D6
    # would then block all of them after the first attempt.
    with pytest.raises(ValueError, match="entry array"):
        setup_id_for("EURUSD", Timeframe.M5, None)
