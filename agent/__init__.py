"""agent package — LangGraph-style agent execution loop.

Public API:
  AgentGraph        — orchestrates the full Observe → Analyse → Decide → Act
                      → Review → Learn loop. Takes any BrokerClient.
  create_agent_app  — FastAPI app with /agent/pause, /agent/resume, /agent/status.
  AgentState        — Pydantic model carrying full agent context.
  log_agent_decision — writes the agent_decisions audit trail (Phase 4 Task 39).
  BrokerClient      — abstract interface every broker adapter implements
                      (agent.brokers.base). AgentGraph depends only on this.
  create_broker_client — factory: broker name + credentials -> BrokerClient
                      (agent.brokers.factory). This is how a caller picks
                      "whatever broker they want" without touching AgentGraph.
  OANDABrokerClient — Async HTTP client for OANDA v20 REST API order execution.
  BrokerError       — Exception raised on broker API failures.
  place_order       — Place a market order via OANDA.
  set_sl_tp         — Update SL/TP on an open trade.
  close_position    — Close an open trade at market.
  partial_close     — Close a fraction of an open trade at market.
  get_position_status — Fetch live trade status and unrealised P&L.

Execution flow:
    observe_node → analyse_node → decide_node
                                      ├─ HUMAN_IN_LOOP → notify_node  → learn_node
                                      └─ AUTONOMOUS    → execute_node → review_node → learn_node

Validates: Requirements FR-6, FR-7, FR-8, FR-9
"""
from agent.state import AgentState, AgentMode, DecisionAction
from agent.graph import AgentGraph, create_agent_app
from agent.audit_trail import log_agent_decision
from agent.broker_tools import (
    BrokerError,
    OANDABrokerClient,
    place_order,
    set_sl_tp,
    close_position,
    partial_close,
    get_position_status,
)
from agent.brokers import BrokerClient, create_broker_client

__all__ = [
    "AgentState",
    "AgentMode",
    "DecisionAction",
    "AgentGraph",
    "create_agent_app",
    "log_agent_decision",
    "BrokerClient",
    "create_broker_client",
    "BrokerError",
    "OANDABrokerClient",
    "place_order",
    "set_sl_tp",
    "close_position",
    "partial_close",
    "get_position_status",
]
