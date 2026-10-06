"""AlgoBacktester: replays the live agent's decisions over history.

The backtester runs the same decision code as live trading (build_order_intent,
AgentGraph, RiskEngine) on candles built the way the live runner builds them
(compose_as_of_view), and fills orders with the shared FillModel, so its
results say what the agent would have done (.kiro/specs/algo-backtester).

Modules:
    config    RunConfig (config/backtests/base.toml + variants), studies and the hold-out
"""
