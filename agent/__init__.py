"""agent package — LangGraph-style agent execution loop.

Public API:
  AgentGraph        — orchestrates the full Observe → Analyse → Decide → Act
                      → Review → Learn loop.
  create_agent_app  — FastAPI app with /agent/pause, /agent/resume, /agent/status.
  AgentState        — Pydantic model carrying full agent context.
  OANDABrokerClient — Async HTTP client for OANDA v20 REST API order execution.
  BrokerError       — Exception raised on broker API failures.
  place_order       — Place a market order via OANDA.
  set_sl_tp         — Update SL/TP on an open trade.
  close_position    — Close an open trade at market.
  get_position_status — Fetch live trade status and unrealised P&L.

Execution flow:
    observe_node → analyse_node → decide_node
                                      ├─ HUMAN_IN_LOOP → notify_node  → learn_node
                                      └─ AUTONOMOUS    → execute_node → review_node → learn_node

Validates: Requirements FR-6, FR-7, FR-8, FR-9
"""
from agent.state import AgentState, AgentMode, DecisionAction
from agent.graph import AgentGraph, create_agent_app
from agent.broker_tools import (
    BrokerError,
    OANDABrokerClient,
    place_order,
    set_sl_tp,
    close_position,
    get_position_status,
)

__all__ = [
    "AgentState",
    "AgentMode",
    "DecisionAction",
    "AgentGraph",
    "create_agent_app",
    "BrokerError",
    "OANDABrokerClient",
    "place_order",
    "set_sl_tp",
    "close_position",
    "get_position_status",
]
