# System Architecture Document (SAD)
**Project:** AgentICTrader.AI
**Version:** 1.0.0
**Status:** Draft
**Architect:** Lead Engineer
**Last Updated:** 2026-04-04

---

## 1. Architecture Overview

AgentICTrader.AI is designed as a **microservices-based, event-driven system** with a layered AI pipeline at its core. Each layer is independently deployable, observable, and replaceable without disrupting adjacent systems.

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        AgentICTrader.AI — System Architecture            ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  ┌──────────────────────────────────────────────────────────────────┐   ║
║  │                    CLIENT LAYER                                   │   ║
║  │   [Web Dashboard]   [Mobile App]   [Push Notifications]          │   ║
║  └────────────────────────────┬─────────────────────────────────────┘   ║
║                               │ HTTPS / WebSocket                        ║
║  ┌──────────────────────────────────────────────────────────────────┐   ║
║  │                    API GATEWAY (Kong / Nginx)                     │   ║
║  │   Auth | Rate Limiting | Routing | SSL Termination               │   ║
║  └───────┬──────────────┬──────────────┬───────────────┬────────────┘   ║
║          │              │              │               │                  ║
║  ┌───────▼──┐  ┌────────▼───┐  ┌──────▼─────┐  ┌─────▼──────┐         ║
║  │  Market  │  │  Analytics │  │   Agent    │  │  User/Auth │         ║
║  │  Data    │  │  Service   │  │  Service   │  │  Service   │         ║
║  │  Service │  │            │  │            │  │            │         ║
║  └───────┬──┘  └────────┬───┘  └──────┬─────┘  └────────────┘         ║
║          │              │              │                                  ║
║  ┌───────▼──────────────▼──────────────▼──────────────────────────┐    ║
║  │                    MESSAGE BUS (Apache Kafka)                    │    ║
║  │  Topics: market.ticks | setups.detected | trades.executed       │    ║
║  │          sentiment.signals | agent.decisions | risk.alerts      │    ║
║  └───────┬──────────────┬──────────────┬───────────────────────────┘    ║
║          │              │              │                                  ║
║  ┌───────▼──┐  ┌────────▼───┐  ┌──────▼─────┐                          ║
║  │  ML      │  │  NLP /     │  │  Risk      │                          ║
║  │  Engine  │  │  LLM       │  │  Engine    │                          ║
║  │  Service │  │  Service   │  │  Service   │                          ║
║  └───────┬──┘  └────────┬───┘  └──────┬─────┘                          ║
║          │              │              │                                  ║
║  ┌───────▼──────────────▼──────────────▼──────────────────────────┐    ║
║  │                    DATA LAYER                                    │    ║
║  │  [TimescaleDB]  [Redis Cache]  [S3 / Object Store]  [MongoDB]   │    ║
║  └─────────────────────────────────────────────────────────────────┘    ║
║                                                                          ║
║  ┌──────────────────────────────────────────────────────────────────┐   ║
║  │                EXTERNAL INTEGRATIONS                              │   ║
║  │  [Broker APIs]  [News APIs]  [Economic Calendar]  [X/Twitter]   │   ║
║  └──────────────────────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## 2. Architectural Principles

| Principle | Rationale |
|---|---|
| **Event-Driven** | Market data is inherently event-based. Kafka enables decoupled, high-throughput messaging between services |
| **Microservices** | Each domain (ML, NLP, Agent, Risk) deploys and scales independently |
| **Fail-Safe Risk** | The Risk Engine is the only service with veto power over trade execution — it operates as a synchronous gate, not a subscriber |
| **Explainability-First** | Every ML prediction and agent decision must produce human-readable reasoning. No black-box outputs |
| **Human-in-Loop First** | Agent defaults to notification mode. Autonomous execution is a feature toggle requiring explicit enablement |
| **Observability** | Every service emits metrics, logs, and traces. Grafana + Prometheus + Jaeger from day one |

---

## 3. Service Decomposition

### 3.1 Market Data Service
**Responsibility:** Ingest, clean, normalise, and distribute market data
**Language:** Python
**Key functions:**
- Connect to broker WebSocket feeds (OANDA, IBKR, Alpaca)
- Normalise tick data → OHLCV candles (M1, M5, M15, H1, H4, D1)
- Publish to Kafka topic: `market.ticks`, `market.candles`
- Store to TimescaleDB
- Expose REST + WebSocket endpoints for downstream consumers

```
Broker Feed → WebSocket Client → Normaliser → Kafka Producer
                                            ↘ TimescaleDB Writer
```

### 3.2 ML Engine Service
**Responsibility:** Pattern detection, regime classification, confidence scoring
**Language:** Python (FastAPI)
**Key functions:**
- Consume `market.candles` from Kafka
- Run feature engineering pipeline
- Classify market regime
- Detect Price Action patterns (BOS, CHoCH, FVG, S/D zones, liquidity sweeps)
- Score setup confluence across timeframes
- Publish detected setups to `setups.detected`
- Expose `/predict` endpoint for on-demand inference

```
Kafka Consumer (candles) → Feature Engineering → Regime Classifier
                                              → Pattern Detector
                                              → Confluence Scorer
                                              → Kafka Producer (setups)
```

### 3.3 NLP / LLM Service
**Responsibility:** News sentiment, macro event analysis, trade reasoning generation
**Language:** Python (FastAPI)
**Key functions:**
- Poll news APIs (Reuters, Benzinga, Alpha Vantage News)
- Run FinBERT sentiment classification per instrument
- Summarise macro events via LLM (Claude / GPT-4o)
- Generate trade reasoning narratives for every setup
- Publish sentiment signals to `sentiment.signals`

```
News APIs → Scraper/Poller → FinBERT Classifier → Sentiment Signal
Economic Calendar → LLM Summariser → Event Signal
Setup Data → LLM Reasoner → Trade Narrative
```

### 3.4 Agent Service
**Responsibility:** Core orchestration of the Observe→Analyse→Decide→Act→Review→Learn loop
**Language:** Python (LangGraph)
**Key functions:**
- Subscribe to `setups.detected` + `sentiment.signals`
- Query Risk Engine before any trade decision
- Route to notification or execution based on mode
- Log every decision with full context to MongoDB
- Trigger model retraining pipeline post-trade outcome

```
setups.detected ─┐
                  ├→ Agent Orchestrator → Risk Gate → Notify / Execute
sentiment.signals─┘        ↓
                       Decision Log (MongoDB)
```

### 3.5 Risk Engine Service
**Responsibility:** Enforce all risk controls synchronously before execution
**Language:** Python (FastAPI)
**Key functions:**
- Validate trade against: max position size, daily DD limit, weekly DD limit, correlation exposure, news blackout windows
- Return APPROVE / REJECT with reason
- Maintain real-time equity curve and exposure state
- Never a subscriber — always a synchronous gate

### 3.6 Analytics Service
**Responsibility:** Performance analytics, edge quantification, reporting
**Language:** Python (FastAPI) + dbt
**Key functions:**
- Process trade journal history
- Calculate win rate, R-multiple, expectancy by condition
- Power dashboard analytics endpoints
- Run scheduled reports

### 3.7 User / Auth Service
**Responsibility:** Authentication, authorisation, user management
**Language:** Node.js (Express) or Python (FastAPI)
**Key functions:**
- JWT-based auth
- Role-based access control (RBAC): Admin, Trader, Viewer
- API key management for broker integrations
- User preferences (risk settings, notification config)

---

## 4. Data Flow — Setup Detection to Alert

```
Step 1: Market Data Service receives live M5 candle for US500
        → Published to Kafka: market.candles.US500.M5

Step 2: ML Engine consumes candle
        → Builds feature vector (ATR, candle structure, zone proximity, session, HTF bias)
        → Regime Classifier: TRENDING_BEARISH
        → Pattern Detector: BOS_CONFIRMED + BEARISH_ARRAY_REJECTION
        → Confluence Score: 0.83
        → Published to Kafka: setups.detected

Step 3: NLP Service reads setups.detected
        → Checks latest sentiment for US500: BEARISH (-0.71)
        → Generates trade narrative
        → Appends to setup object

Step 4: Agent Service receives enriched setup
        → Calls Risk Engine: APPROVED (within limits)
        → Mode = HUMAN_IN_LOOP
        → Sends push notification to trader:
          "US500 SHORT setup | M5 BOS + Bearish Array at Premium | Score: 0.83 |
           Sentiment: Bearish | SL: 6,528 | TP: 6,460 | 2.1R"

Step 5: Trader acts / ignores
        → Outcome logged
        → Feeds back into model retraining queue
```

---

## 5. Agent Architecture (LangGraph)

```
┌─────────────────────────────────────────────────────────┐
│                   AGENT STATE GRAPH                      │
│                                                          │
│  [observe_node] ──→ [analyse_node] ──→ [decide_node]    │
│       ↑                                      │           │
│       │                           ┌──────────┴──────┐   │
│       │                           ▼                  ▼   │
│  [learn_node] ←── [review_node]  [notify_node]  [execute_node] │
│                                                          │
│  State carries: setup_data, sentiment, risk_verdict,     │
│                 confidence_score, trade_reasoning,        │
│                 execution_result, outcome                 │
└─────────────────────────────────────────────────────────┘
```

**Node Descriptions:**
- `observe_node` — Listens for new setups from Kafka, builds initial context
- `analyse_node` — Enriches with sentiment, HTF alignment, calendar check
- `decide_node` — Queries risk engine, applies confidence threshold gate
- `notify_node` — Formats and dispatches push notification (human-in-loop mode)
- `execute_node` — Places order via broker API (autonomous mode)
- `review_node` — Monitors open trade, manages partials, SL management
- `learn_node` — Logs outcome, queues retraining data

---

## 6. Database Architecture

### 6.1 TimescaleDB (Primary Market Data Store)
- Hypertables partitioned by instrument + timeframe
- Continuous aggregates for OHLCV rollups
- Retention policies: Tick data 90 days, OHLCV candles indefinite

### 6.2 Redis (Cache + State)
- Latest candle cache per instrument/TF (sub-ms reads)
- Agent state cache
- Session/auth tokens
- Rate limit counters

### 6.3 MongoDB (Documents + Logs)
- Trade journal (historical + live)
- Agent decision logs (full reasoning, context snapshots)
- Setup archive with outcome tags
- User configuration documents

### 6.4 S3 / Object Store
- ML model artefacts (versioned)
- Training datasets
- Backtest result exports
- Chart snapshots for review

---

## 7. ML Model Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    ML PIPELINE                            │
│                                                          │
│  Raw OHLCV ──→ Feature Engineering                       │
│                      │                                   │
│          ┌───────────┴───────────┐                       │
│          ▼                       ▼                       │
│   Regime Classifier        Pattern Detector              │
│   (XGBoost)                (XGBoost / LSTM)              │
│          │                       │                       │
│          └───────────┬───────────┘                       │
│                      ▼                                   │
│              Confluence Scorer                           │
│              (Weighted ensemble)                         │
│                      │                                   │
│                      ▼                                   │
│          Confidence Score (0.0 → 1.0)                   │
│                      │                                   │
│              ┌───────┴────────┐                          │
│              ▼                ▼                          │
│         Score < 0.70    Score ≥ 0.70                    │
│           DISCARD         PUBLISH                        │
└──────────────────────────────────────────────────────────┘
```

---

## 8. Infrastructure Architecture

```
                          ┌─────────────────┐
                          │   Cloudflare    │
                          │   (DNS + CDN)   │
                          └────────┬────────┘
                                   │
                          ┌────────▼────────┐
                          │   Load Balancer │
                          │   (AWS ALB)     │
                          └────────┬────────┘
                                   │
             ┌─────────────────────┼─────────────────────┐
             │                     │                     │
    ┌────────▼──────┐    ┌─────────▼──────┐   ┌────────▼──────┐
    │  EKS Cluster  │    │  EKS Cluster   │   │  EKS Cluster  │
    │  (Services)   │    │  (ML/Agent)    │   │  (Data)       │
    └───────────────┘    └────────────────┘   └───────────────┘
             │                     │                     │
    ┌────────▼─────────────────────▼─────────────────────▼──────┐
    │                     AWS RDS / TimescaleDB Cloud            │
    │                     ElastiCache (Redis)                    │
    │                     MSK (Managed Kafka)                    │
    │                     S3 (Object Storage)                    │
    └────────────────────────────────────────────────────────────┘
```

---

## 9. Security Architecture

- All inter-service communication over mTLS within Kubernetes (Istio service mesh)
- API Gateway enforces JWT validation on all external endpoints
- Broker API keys encrypted at rest (AWS KMS) and injected via Kubernetes Secrets
- No PII stored beyond user account minimum — pseudonymised user IDs throughout
- Full audit log of all agent decisions and trade executions
- Network policy: services only communicate on explicitly permitted routes

---

## 10. Observability Stack

| Tool | Purpose |
|---|---|
| **Prometheus** | Metrics collection from all services |
| **Grafana** | Dashboards — system health, ML model performance, trade P&L |
| **Jaeger** | Distributed tracing across service calls |
| **ELK Stack** | Centralised log aggregation and search |
| **MLflow** | ML experiment tracking, model versioning, registry |
| **PagerDuty** | On-call alerting for system failures or risk breaches |

---

*Document Owner: Lead Architect | Review Cycle: Per Phase Milestone*
