"""agent/edges.py — Edge routing logic for the LangGraph agent graph.

Defines the conditional routing functions that determine which node to
execute next based on the current AgentState.  These functions are pure
(no side effects) and independently testable.

Execution flow:
    observe_node → [stale? → learn] → analyse_node → decide_node
                                                          ├─ NOTIFY  → notify_node  → learn_node
                                                          ├─ EXECUTE → execute_node → review_node → learn_node
                                                          └─ SKIP    → learn_node

Design notes:
  - All routing decisions are based solely on AgentState fields.
  - String constants (NOTIFY, EXECUTE, LEARN) are used as node name keys
    so they can be referenced consistently in both graph.py and tests.
  - route_after_observe provides an early-exit path for stale setups,
    avoiding unnecessary Redis/Risk Engine calls.

Validates: Requirements FR-6
"""
from __future__ import annotations

import logging

from agent.state import AgentState, DecisionAction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Edge destination constants
# ---------------------------------------------------------------------------
# These string values are used as LangGraph node name keys.  They must match
# the node names registered in AgentGraph._build_graph().

NOTIFY = "notify"
EXECUTE = "execute"
LEARN = "learn"
ANALYSE = "analyse"
END = "__end__"


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_decide(state: AgentState) -> str:
    """Determine the next node after decide_node.

    Routing rules:
      - NOTIFY  → notify_node  (HUMAN_IN_LOOP path: push alert, no execution)
      - EXECUTE → execute_node (AUTONOMOUS path: place broker order)
      - SKIP    → learn_node   (rejected setup: log and terminate)
      - WAIT    → learn_node   (deferred setup: log and terminate)

    Args:
        state: Current AgentState with ``decision`` populated by decide_node.

    Returns:
        One of the edge destination constants: NOTIFY, EXECUTE, or LEARN.
    """
    decision = state.decision

    if decision == DecisionAction.NOTIFY:
        logger.debug("route_after_decide: → notify_node (decision=NOTIFY)")
        return NOTIFY

    if decision == DecisionAction.EXECUTE:
        logger.debug("route_after_decide: → execute_node (decision=EXECUTE)")
        return EXECUTE

    # SKIP or WAIT — log outcome and terminate
    logger.debug(
        "route_after_decide: → learn_node (decision=%s reason=%s)",
        decision,
        state.decision_reason,
    )
    return LEARN


def route_after_observe(state: AgentState) -> str:
    """Determine the next node after observe_node.

    Provides an early-exit path for stale setups: if observe_node set
    ``decision=SKIP`` (because the setup is older than 60 seconds), route
    directly to learn_node to log the rejection without calling Redis or
    the Risk Engine.

    Args:
        state: Current AgentState returned by observe_node.

    Returns:
        LEARN    — when the setup is stale (decision=SKIP).
        ANALYSE  — otherwise (proceed to analyse_node).
    """
    if state.decision == DecisionAction.SKIP:
        logger.debug("route_after_observe: → learn_node (stale setup)")
        return LEARN
    return ANALYSE
