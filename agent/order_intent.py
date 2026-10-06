"""The order the live runner and AlgoBacktester derive from a graded setup.

Task 189 (.kiro/specs/algo-backtester): a setup's id is derived from its
entry PD array instead of a fresh uuid4() per pass, so re-grading the same
array on the next bar yields the same setup. That identity is what allows
one attempt per setup (D6) and duplicate-order protection. Task 190 moves
the runner's order-building code here as build_order_intent().

Validates: Requirements 1.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from typing import Optional

from liquidity_engine.models import Timeframe
from liquidity_engine.utils.id_utils import deterministic_id

__all__ = ["setup_id_for"]


def setup_id_for(instrument: str, entry_tf: Timeframe, entry_array_id: Optional[str]) -> str:
    """The setup's id: the same instrument, entry timeframe and entry array
    (SetupGradeDetail.entry_array_id) always give the same id."""
    if entry_array_id is None:
        # Every array-less setup would otherwise share one id.
        raise ValueError(f"{instrument} {entry_tf.value}: a setup id needs an entry array")
    return deterministic_id("setup", instrument, entry_tf.value, entry_array_id)
