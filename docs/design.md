# AgentICTrader.AI — Technical Design Document
**Version:** 2.0.0
**Last Updated:** 2026-04-24

---

## 1. Architecture Overview

Event-driven microservices architecture. Each service is independently deployable and scalable.

```
Client Layer (Web Dashboard / Mobile App)
        │ HTTPS / WebSocket
API Gateway (Auth, Rate Limiting, Routing)
        │
┌───────┬──────────┬──────────┬──────────┐
Market  Analytics  Agent      User/Auth
Data    Service    Service    Service
Service
        │
Message Bus (Apache Kafka)
Topics: market.ticks | market.candles | setups.detected
        sentiment.signals | trades.executed | agent.decisions
        │
┌───────┬──────────┬──────────┐
ML      NLP/LLM    Risk
Engine  Service    Engine
        │
Data Layer: TimescaleDB | MongoDB | Redis | S3
        │
External: Broker APIs | News APIs | Economic Calendar
```

---

## 2. Service Decomposition

### 2.1 Market Data Service
- Connects to broker WebSocket feeds (OANDA, IBKR, Alpaca)
- Normalises tick data → OHLCV candles (M1–D1)
- Publishes to Kafka: `market.ticks`, `market.candles`
- Writes to TimescaleDB
- Exposes REST + WebSocket endpoints

### 2.2 ML Engine Service (FastAPI)
- Consumes `market.candles` from Kafka
- Runs feature engineering pipeline
- Regime Classifier (XGBoost) → market environment classification
- Pattern Detector (XGBoost multi-label) → BOS, CHoCH, FVG, S/D zones, etc.
- Confluence Scorer (weighted ensemble) → 0.0–1.0 confidence score
- Publishes detected setups to `setups.detected`
- Exposes `/predict` endpoint for on-demand inference

### 2.3 NLP / LLM Service (FastAPI)
- Polls news APIs → FinBERT sentiment classification per instrument
- Summarises macro events via LLM (Claude / GPT-4o fallback)
- Generates trade reasoning narratives per setup
- Publishes to `sentiment.signals`

### 2.4 Agent Service (LangGraph)
- Subscribes to `setups.detected` + `sentiment.signals`
- Runs Observe → Analyse → Decide → Act → Review → Learn loop
- Calls Risk Engine synchronously before any trade decision
- Routes to notify or execute based on user mode
- Logs all decisions to MongoDB

### 2.5 Risk Engine Service (FastAPI — synchronous gate)
- Validates trades against: max position size, daily DD, weekly DD, correlation, news blackout
- Returns APPROVE / REJECT with reason
- Maintains real-time equity curve and exposure state
- Never a subscriber — always called synchronously

### 2.6 Analytics Service (FastAPI + dbt)
- Processes trade journal history
- Calculates win rate, R-multiple, expectancy by condition
- Powers dashboard analytics endpoints

### 2.7 User / Auth Service
- JWT-based auth, RBAC (Admin, Trader, Viewer)
- User risk config and agent mode settings
- Broker API key management (encrypted via KMS)

---

## 3. Agent State Graph (LangGraph)

```
[observe_node] → [analyse_node] → [decide_node]
                                        │
                          ┌─────────────┴──────────────┐
                          ▼                             ▼
                    [notify_node]               [execute_node]
                          │                             │
                    [end / log]               [review_node] ←─┐
                                                    │          │
                                              trade open?──────┘
                                                    │
                                             [learn_node]
```

**Node responsibilities:**
- `observe_node` — Receives setup from Kafka, validates it's still actionable
- `analyse_node` — Enriches with sentiment, calendar check, computes final confidence
- `decide_node` — Confidence gate → Risk Engine → LLM reasoning → route decision
- `notify_node` — Formats and dispatches push notification (human-in-loop mode)
- `execute_node` — Places order via broker API (autonomous mode only)
- `review_node` — Monitors open trade, manages partial exits and SL to BE
- `learn_node` — Logs outcome, queues data for model retraining

**Safety layers (cannot be bypassed):**
1. Confidence threshold gate in `decide_node` (configurable, hard floor 0.65)
2. Risk Engine synchronous gate in `decide_node`
3. Pre-execution recheck in `execute_node`

---

## 4. ML Pipeline

```
Raw OHLCV → Feature Engineering
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
Regime Classifier         Pattern Detector
(XGBoost multi-class)     (XGBoost multi-label)
        │                       │
        └───────────┬───────────┘
                    ▼
           Confluence Scorer
           (Weighted ensemble)
                    │
           Confidence Score (0.0–1.0)
                    │
         < 0.65 → DISCARD
        0.65–0.74 → LOG ONLY
        0.75–0.84 → NOTIFY
          ≥ 0.85 → NOTIFY + AUTO-EXECUTE (if autonomous)
```

**Feature categories:**
- Candle structure (body size, wick %, close position, engulf)
- Zone & structure (BOS, CHoCH, FVG, liquidity sweep, swing distances)
- Momentum & indicators (ATR, RSI, ADX, EMA 50/200, volume ratio)
- Multi-timeframe alignment (H4, H1, D1 trend bias, HTF confluence score)
- Session & time (session, day of week, news window proximity)
- Sentiment (FinBERT score, alignment with direction, freshness)

**Model promotion gate:**
- Pattern accuracy ≥ 80%
- False positive rate < 20% at threshold 0.75
- Backtest Sharpe ≥ 1.5
- Max backtest DD ≤ 10%
- Walk-forward validation: minimum 8 folds

---

## 5. Database Architecture

### 5.1 TimescaleDB (Time-series market data)
- `candles` hypertable — OHLCV per instrument/timeframe
- `ticks` hypertable — raw tick data (90-day retention)
- `indicators` hypertable — pre-computed ATR, RSI, ADX, EMAs, session
- `economic_events` — calendar events with impact level

### 5.2 MongoDB (Documents)
- `trade_journal` — full trade history with setup context, outcome, R-multiple
- `agent_decisions` — complete decision log with input context, risk validation, reasoning
- `setups` — detected setup archive with outcome tags
- `users` — user config, risk settings, agent mode, broker credentials

### 5.3 Redis (Cache + State)
- Latest candle per instrument/timeframe (65s TTL)
- Latest indicator values (300s TTL)
- Latest sentiment per instrument (900s TTL)
- Agent state per user (3600s TTL)
- Risk exposure snapshot per user (60s TTL)
- Auth session tokens

### 5.4 S3 / Object Store
- ML model artefacts (versioned via MLflow)
- Training datasets
- Backtest result exports

---

## 6. Technology Stack

### Backend Services
- Python 3.11+, FastAPI, Pydantic v2
- SQLAlchemy 2.x + asyncpg (TimescaleDB)
- Motor (MongoDB async), redis-py (async)
- aiokafka (Kafka producer/consumer)
- APScheduler (scheduled jobs)

### ML / AI
- XGBoost 2.x (regime classifier, pattern detector)
- scikit-learn 1.x (preprocessing, pipelines, evaluation)
- PyTorch 2.x (LSTM if needed)
- MLflow 2.x (experiment tracking, model registry)
- SHAP (explainability), Optuna (hyperparameter tuning)
- TA-Lib (technical indicators)

### NLP / LLM
- HuggingFace Transformers (FinBERT)
- LangChain + LangGraph (agent orchestration)
- Anthropic Claude API (primary LLM)
- OpenAI API (fallback)

### Frontend
- Next.js 15+ (App Router), React 19+, TypeScript
- Tailwind CSS, shadcn/ui
- Zustand (state), TanStack Query (server state)
- Lightweight Charts (TradingView), Recharts (analytics)
- Socket.io-client (real-time updates)
- React Native 0.76+ (Phase 5 mobile)

### Infrastructure
- Docker + Kubernetes (EKS)
- Apache Kafka (MSK managed)
- TimescaleDB (RDS PostgreSQL extension)
- Redis (ElastiCache)
- AWS S3, KMS, ALB
- Terraform (IaC), Helm, Istio (service mesh)

### Observability
- Prometheus + Grafana (metrics + dashboards)
- Jaeger (distributed tracing)
- ELK Stack (log aggregation)
- MLflow (ML experiment tracking)
- PagerDuty (on-call alerting)

---

## 7. Existing Code — Migration Notes

| Existing File | Status | Action |
|---|---|---|
| `backend/trader/infrastructure/deriv_api.py` | ✅ Conflict resolved | Migrate to market-data service connector |
| `backend/trader/agents/power_of_3.py` | ✅ Partial impl | Refactor into ml/features/zone_features.py |
| `backend/trader/analysis/pdarray.py` | ✅ Partial impl | Refactor into ml/features/zone_features.py |
| `backend/trader/agents/market_structure.py` | ⚠️ Stub only | Implement BOS/CHoCH detection in pattern detector |
| `backend/trader/agents/cisd.py` | ❌ Empty | Implement as pattern in pattern detector |
| `backend/trader/agents/rl_agent.py` | ❌ Empty | Drop — replaced by XGBoost + LangGraph |
| `backend/trader/agents/execution.py` | ❌ Empty | Implement as agent/execute_node.py |
| `backend/trader/models.py` | ✅ Usable | Trade model maps to MongoDB trade_journal schema |
| `frontend/` (React/Redux) | ⚠️ Scaffold | Replace with Next.js App Router in Phase 3 |

---

## 8. API Design (Summary)

Base URL: `https://api.agentict.ai/v1`

Key endpoint groups:
- `/auth/*` — register, login, refresh, profile
- `/market/*` — instruments, candles, indicators, sessions, calendar, WebSocket stream
- `/setups/*` — detected setups feed, detail, feedback, WebSocket stream
- `/agent/*` — status, config, decisions, pause/resume
- `/trades/*` — journal CRUD, import/export
- `/analytics/*` — summary, edge analysis, equity curve, R-distribution
- `/risk/*` — exposure snapshot, trade validation, drawdown status
- `/sentiment/*` — per-instrument sentiment, news feed, macro summaries

All WebSocket connections authenticated via `?token={jwt}` query param.

---

## 9. Security

- mTLS between all services (Istio service mesh)
- JWT validation enforced at API Gateway on all external endpoints
- Broker API keys encrypted at rest (AWS KMS), injected via Kubernetes Secrets
- Full audit log of all agent decisions and trade executions
- Network policy: services communicate only on explicitly permitted routes
