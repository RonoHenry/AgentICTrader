# AgentICTrader Development Handoff

**Created:** 2026-09-22  
**Purpose:** Preserve the architecture discussion and recommended development direction for the next development session.

## Candid assessment

AgentICTrader has strong potential as a trustworthy, AI-assisted trading-decision platform. Its best idea is not simply an "AI that trades"; it is a system in which independent sources of evidence contribute to a decision while a separate risk authority controls whether an order may execute.

### Architectural strengths

- The event-driven approach fits streaming market data well.
- The agent lifecycle is sensibly separated: observe -> analyse -> decide -> notify/execute -> review -> learn.
- Risk is designed as a synchronous veto rather than an advisory event consumer.
- Human-in-the-loop mode, a shadow period, a kill switch, and an audit trail are excellent safety-oriented choices.
- Structured features, liquidity mapping, historical-similarity retrieval, sentiment, and visual chart analysis can be useful complementary evidence sources.

Relevant implementations include `agent/graph.py`, `agent/nodes/decide_node.py`, `agent/nodes/execute_node.py`, `agent/audit_trail.py`, and `services/risk_engine/main.py`.

### Main concern

The current vision has the surface area of a large platform before a narrow trading edge has been proven. Kafka, several databases, MLflow, Qdrant/RAG, vision, NLP, several brokers, and multiple services can slow down the central question:

> Does one clearly specified setup remain profitable out of sample after realistic costs?

The defensible moat will be trusted execution discipline, high-quality proprietary outcome data, and a feedback loop that demonstrably improves decisions—not the number of AI components.

## Recommended approach: prove the decision first

Use a deliberately narrow first release:

```text
Market data -> deterministic setup detector -> risk gate -> human review
            -> paper broker -> journal + outcome evaluator
```

Scope the milestone to:

- One broker.
- One or two liquid instruments.
- One setup family.
- One or two trading sessions.
- Human-in-the-loop only.
- Paper trading only.

Define every setup with a versioned **strategy card** containing entry conditions, invalidation, stop placement, target rules, spread/slippage limits, news restrictions, and explicit no-trade conditions. The deterministic logic should be capable of deciding to trade or reject a setup without an LLM, VLM, or RAG service.

## Proper role for AI components

- **ML:** Regime classification and calibrated probability estimates.
- **RAG:** Comparable historical cases and explanation; never execution authority.
- **VLM:** Chart-quality check or bounded veto; never an unbounded entry generator.
- **LLM:** Trader-facing rationale, summaries, and journal review; never direct execution logic.

All model influence must be bounded, versioned, logged, and tested against a deterministic baseline through ablation tests.

## Execution and risk requirements before live trading

The highest-priority technical improvement is a transactional execution boundary:

```text
Decision -> atomic risk reservation -> idempotent order submission
         -> broker confirmation -> exposure reconciliation -> immutable audit event
```

This removes the race between validating a trade and incrementing exposure after a broker order succeeds. A live-ready implementation also needs:

- Broker reconciliation for fills, rejections, cancellations, and partial fills.
- Idempotency keys for every order and event.
- Versioned event schemas, replay policy, and dead-letter handling.
- Per-instrument sizing that accounts for pip/tick value, contract size, quote-currency conversion, leverage/margin, and broker rounding.
- Immutable decision/audit records and a tested emergency kill switch.

The present sizing formula based only on equity and stop distance in pips is not sufficient by itself for safe multi-broker, multi-instrument live trading.

## Deployment recommendation

Keep clean service boundaries, but do not require every service to run in the first validation release. A small number of deployables is enough initially:

1. Agent/strategy service.
2. Risk and execution service.
3. Data stores plus a simple journal/reporting workflow.

Introduce Kafka, separately scaled model services, vector search, and the full observability stack when measured load or operating complexity justifies them. Before production, close the gap between the architecture document and deployment reality: the documented gateway and Prometheus/Grafana/Jaeger stack are not presently part of the development compose configuration.

## Evidence-based success criteria

- Every proposed and submitted order is traceable and reconciled with the broker.
- Zero risk-gate bypasses.
- Paper results include spreads, commission, slippage, rejected orders, and missed fills.
- Walk-forward results remain positive over enough trades and across relevant regimes.
- Human reviewers can explain acceptance or rejection of each proposal.
- Each AI enhancement produces a measurable improvement over the deterministic baseline.

## Rollout ladder

1. Human-reviewed paper trading.
2. Autonomous paper trading with hard limits.
3. Tiny-capital live trading with kill switch and strict daily-loss limits.
4. Gradual expansion to instruments, strategies, and users.

## Bottom line

Build an exceptionally trustworthy trading copilot first. If a narrow version proves a durable, cost-adjusted edge, autonomous execution becomes an earned extension rather than the premise the project must defend.
