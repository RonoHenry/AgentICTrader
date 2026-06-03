"""Agent nodes package for the LangGraph execution loop.

Each node is a pure function that accepts an AgentState (and optional
injected dependencies) and returns an updated AgentState.  This design
makes every node independently testable without a running LangGraph graph.

Execution order:
    observe_node  → analyse_node → decide_node
                                        ├─ HUMAN_IN_LOOP → notify_node
                                        └─ AUTONOMOUS    → execute_node
                                                              ↓
                                                         review_node
                                                              ↓
                                                         learn_node

Node responsibilities:
    observe_node  - Receives Kafka message, validates freshness (< 60s),
                    populates AgentState.
    analyse_node  - Fetches sentiment/blackout from Redis, adjusts
                    final_confidence, sets calendar_clear.
    decide_node   - Applies confidence floor (0.65), calls Risk Engine
                    /validate synchronously, routes to NOTIFY or EXECUTE.
    notify_node   - Formats FCM alert payload with all FR-8 required fields
                    and dispatches via the injected FCM sender.
    execute_node  - Pre-execution risk recheck, places broker order via
                    injected broker client.
    review_node   - Monitors open trade, triggers partial close at 1R profit.
    learn_node    - Logs full trade outcome to MongoDB trade_journal.

Validates: Requirements FR-5, FR-6, FR-7, FR-8
"""
from agent.nodes.observe_node import observe_node
from agent.nodes.analyse_node import analyse_node
from agent.nodes.decide_node import decide_node
from agent.nodes.notify_node import notify_node
from agent.nodes.execute_node import execute_node
from agent.nodes.review_node import review_node
from agent.nodes.learn_node import learn_node

__all__ = [
    "observe_node",
    "analyse_node",
    "decide_node",
    "notify_node",
    "execute_node",
    "review_node",
    "learn_node",
]
