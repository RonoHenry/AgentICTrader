# AgentICTrader.AI — Design Document

> Full technical design is maintained in `docs/design.md`.
> This file summarises the key design decisions relevant to task execution.

## Architecture
Event-driven microservices. Services communicate via Apache Kafka. Risk Engine is always called synchronously.

## Key Design Decisions

### Sole Technical Indicator: HTF Candle Projections
No ATR, RSI, ADX, EMA, or volume indicators. The HTF Candle Projections indicator provides:
- HTF Open → directional bias anchor
- HTF High → upper range boundary / rejection zone
- HTF Low → lower range boundary / support zone
- Auto-HTF selection: M1→M5, M5→M15, M15→H1, H1→H4, H4→D1, D1→W1

### Database Schema
- TimescaleDB: candles, ticks, indicators (HTF projection columns), economic_events
- MongoDB: trade_journal, agent_decisions, setups, users
- Redis: latest candle/indicator/sentiment cache, agent state, risk exposure

### ML Pipeline
Raw OHLCV → Feature Engineering → Regime Classifier (XGBoost) + Pattern Detector (XGBoost) → Confluence Scorer → Confidence Score (0.0–1.0)

### Confidence Thresholds
- < 0.65 → DISCARD
- 0.65–0.74 → LOG ONLY
- 0.75–0.84 → NOTIFY
- ≥ 0.85 → NOTIFY + AUTO-EXECUTE (autonomous mode only)

### Agent Graph (LangGraph)
observe_node → analyse_node → decide_node → notify_node / execute_node → review_node → learn_node

### Existing Code to Migrate
- `backend/trader/infrastructure/deriv_api.py` → market-data service connector
- `backend/trader/agents/power_of_3.py` + `analysis/pdarray.py` → ml/features/zone_features.py
- `backend/trader/agents/market_structure.py` → pattern detector BOS/CHoCH
- `backend/trader/agents/rl_agent.py` → DROP (replaced by XGBoost + LangGraph)

## Reference
See `docs/design.md` for full architecture diagrams, API design, and technology stack.
