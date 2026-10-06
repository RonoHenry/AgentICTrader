"""The agent's source of "now".

Nodes on the decision path take a ``Clock`` instead of reading the wall clock,
so AlgoBacktester can replay setups at simulated times (.kiro/specs/
algo-backtester, task 193, L5). Without it, observe_node's 60-second staleness
check would reject every replayed setup. Live code passes nothing and gets
the wall clock:

    graph = AgentGraph(..., clock=lambda: sim_now)   # backtest
    graph = AgentGraph(...)                          # live: wall_clock

Validates: Requirements 2.5 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

__all__ = ["Clock", "wall_clock"]

Clock = Callable[[], datetime]


def wall_clock() -> datetime:
    """The current time, timezone-aware UTC."""
    return datetime.now(tz=timezone.utc)
