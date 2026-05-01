# Technology Stack
**Project:** AgentICTrader.AI
**Version:** 1.0.0
**Last Updated:** 2026-04-04

---

## Full Stack Overview

### Backend Services — Python

| Library / Tool | Version | Purpose |
|---|---|---|
| **FastAPI** | 0.115+ | Primary web framework for all microservices |
| **Pydantic v2** | 2.x | Data validation and schema models |
| **SQLAlchemy** | 2.x | ORM for TimescaleDB (sync + async) |
| **asyncpg** | latest | Async PostgreSQL/TimescaleDB driver |
| **Motor** | latest | Async MongoDB driver |
| **redis-py** | latest | Redis client (async) |
| **aiokafka** | latest | Async Kafka producer/consumer |
| **httpx** | latest | Async HTTP client for external APIs |
| **APScheduler** | latest | Scheduled jobs (data refresh, retraining) |
| **websockets** | latest | WebSocket client for broker feeds |
| **python-jose** | latest | JWT encoding/decoding |
| **passlib** | latest | Password hashing |
| **boto3** | latest | AWS SDK (S3, KMS, SES) |
| **structlog** | latest | Structured logging |
| **prometheus-client** | latest | Metrics exposition |

### ML & AI — Python

| Library / Tool | Version | Purpose |
|---|---|---|
| **PyTorch** | 2.x | Deep learning (LSTM models if needed) |
| **XGBoost** | 2.x | Primary ML framework (regime, pattern, scorer) |
| **scikit-learn** | 1.x | Preprocessing, pipelines, evaluation |
| **pandas** | 2.x | Data manipulation |
| **numpy** | latest | Numerical computing |
| **ta-lib** | latest | Technical indicator calculation |
| **MLflow** | 2.x | Experiment tracking, model registry |
| **optuna** | latest | Hyperparameter optimisation |
| **shap** | latest | Model explainability |
| **great-expectations** | latest | Data quality validation |

### NLP & LLM

| Library / Tool | Version | Purpose |
|---|---|---|
| **transformers** | latest | FinBERT and other HuggingFace models |
| **LangChain** | 0.3+ | LLM chaining and tool use |
| **LangGraph** | latest | Agent state graph orchestration |
| **anthropic** | latest | Claude API client |
| **openai** | latest | OpenAI API client (fallback LLM) |
| **sentence-transformers** | latest | Semantic similarity for news deduplication |

### Frontend — TypeScript

| Library / Tool | Version | Purpose |
|---|---|---|
| **Next.js** | 15+ | Web dashboard framework (App Router) |
| **React** | 19+ | UI library |
| **TypeScript** | 5.x | Type safety |
| **Tailwind CSS** | 4.x | Styling |
| **shadcn/ui** | latest | Component library |
| **Zustand** | latest | Client state management |
| **TanStack Query** | 5.x | Server state, caching, data fetching |
| **Lightweight Charts** | 4.x | TradingView chart library |
| **Recharts** | latest | Analytics charts |
| **Socket.io-client** | latest | Real-time WebSocket updates |
| **Zod** | latest | Schema validation |
| **React Native** | 0.76+ | Mobile app (Phase 5) |

### Data & Infrastructure

| Tool | Purpose |
|---|---|
| **TimescaleDB** | Time-series market data (PostgreSQL extension) |
| **MongoDB** | Document storage (trade journal, agent logs) |
| **Redis** | Cache, pub/sub, rate limiting |
| **Apache Kafka** | Event streaming between services |
| **Apache Airflow** | Workflow orchestration (data pipelines, retraining) |
| **dbt** | SQL transformation layer |
| **AWS S3** | Object storage (model artefacts, datasets) |
| **AWS KMS** | Encryption key management (broker API keys) |
| **Docker** | Containerisation |
| **Kubernetes (EKS)** | Container orchestration |
| **Terraform** | Infrastructure as Code |
| **Helm** | Kubernetes package management |
| **Istio** | Service mesh (mTLS, traffic management) |

### Observability

| Tool | Purpose |
|---|---|
| **Prometheus** | Metrics collection |
| **Grafana** | Dashboards and alerting |
| **Jaeger** | Distributed tracing |
| **ELK Stack** | Log aggregation |
| **MLflow** | ML experiment + model tracking |
| **PagerDuty** | On-call incident alerting |

### Development Tools

| Tool | Purpose |
|---|---|
| **Turborepo** | Monorepo build system |
| **GitHub Actions** | CI/CD pipelines |
| **pytest** | Python testing |
| **Vitest** | TypeScript testing |
| **Ruff** | Python linter + formatter |
| **ESLint / Prettier** | TypeScript linting |
| **pre-commit** | Pre-commit hooks |
| **Alembic** | Database migrations |
| **Docker Compose** | Local development orchestration |

---

---

# API Design
**Project:** AgentICTrader.AI
**Version:** 1.0.0

---

## Base URL

```
Production:  https://api.agentict.ai/v1
Staging:     https://staging-api.agentict.ai/v1
Local:       http://localhost:8000/v1
```

All requests require `Authorization: Bearer {jwt_token}` header unless marked public.

---

## Authentication Endpoints

```
POST   /auth/register          Register new user
POST   /auth/login             Login, receive JWT
POST   /auth/refresh           Refresh access token
POST   /auth/logout            Revoke token
GET    /auth/me                Current user profile
PATCH  /auth/me                Update user profile
```

---

## Market Data Endpoints

```
GET    /market/instruments             List available instruments
GET    /market/candles/{instrument}    OHLCV candles
       ?timeframe=M5&limit=200&from=ISO8601&to=ISO8601
GET    /market/live/{instrument}       Latest live candle (WebSocket preferred)
GET    /market/indicators/{instrument} Latest indicator values
       ?timeframe=M5
GET    /market/sessions/current        Current active trading session
GET    /market/calendar                Upcoming economic events
       ?days_ahead=7&impact=HIGH
WS     /market/stream/{instrument}     Real-time candle stream
```

**Example Response: GET /market/candles/US500?timeframe=M5&limit=3**
```json
{
  "instrument": "US500",
  "timeframe": "M5",
  "candles": [
    {"time": "2026-04-04T14:00:00Z", "open": 6519.0, "high": 6528.0, "low": 6510.0, "close": 6512.0, "volume": 15420},
    {"time": "2026-04-04T14:05:00Z", "open": 6512.0, "high": 6515.0, "low": 6498.0, "close": 6499.0, "volume": 18230},
    {"time": "2026-04-04T14:10:00Z", "open": 6499.0, "high": 6501.0, "low": 6487.0, "close": 6488.0, "volume": 21005}
  ]
}
```

---

## Setup Endpoints

```
GET    /setups                    Paginated list of detected setups
       ?status=ACTIVE&instrument=US500&min_confidence=0.75&limit=20
GET    /setups/{setup_id}         Full setup detail
GET    /setups/live               Currently active setups (WebSocket preferred)
WS     /setups/stream             Real-time setup feed
POST   /setups/{setup_id}/feedback   Trader feedback on setup quality
       Body: {"action": "TAKEN|IGNORED|INVALID", "notes": "..."}
```

**Example Response: GET /setups/SET-20260404-0231**
```json
{
  "setup_id": "SET-20260404-0231",
  "detected_at": "2026-04-04T14:00:00Z",
  "instrument": "US500",
  "direction": "SHORT",
  "timeframe": "M5",
  "confidence": 0.83,
  "regime": "TRENDING_BEARISH",
  "session": "NEW_YORK",
  "patterns": [
    {"type": "BOS_CONFIRMED", "confidence": 0.91, "level": 6512.0},
    {"type": "SUPPLY_ZONE_REJECTION", "confidence": 0.87, "zone": {"high": 6528.0, "low": 6519.0}}
  ],
  "htf_alignment": {"D1": "BEARISH", "H4": "BEARISH", "H1": "BEARISH"},
  "sentiment": {"score": -0.71, "label": "BEARISH"},
  "trade_plan": {
    "entry": 6519.0,
    "stop_loss": 6528.0,
    "take_profit_1": 6490.0,
    "take_profit_2": 6460.0,
    "r_ratio": 3.22
  },
  "reasoning": "Short US500 on confirmed M5 BOS below 6,512. Daily, H4, and H1 all aligned bearish. Supply zone confluence at 6,519–6,528 overhead. Negative sentiment following tariff escalation. Calendar clear for next 90 minutes. Confidence: 0.83."
}
```

---

## Agent Endpoints

```
GET    /agent/status                  Agent operational status
GET    /agent/config                  Current agent configuration
PATCH  /agent/config                  Update agent config (mode, thresholds)
GET    /agent/decisions               Paginated agent decision log
GET    /agent/decisions/{decision_id} Full decision detail
POST   /agent/pause                   Pause agent (halt new setups)
POST   /agent/resume                  Resume agent
GET    /agent/health                  Agent loop health check
```

---

## Trade Journal Endpoints

```
GET    /trades                        Paginated trade history
       ?status=CLOSED&instrument=US500&from=ISO&to=ISO&source=AGENT
GET    /trades/{trade_id}             Full trade detail
POST   /trades                        Manually log a trade
PATCH  /trades/{trade_id}             Update trade (close, add notes)
DELETE /trades/{trade_id}             Delete trade (soft delete)
POST   /trades/import                 Import journal CSV/XLSX
GET    /trades/export                 Export journal CSV
```

---

## Analytics Endpoints

```
GET    /analytics/summary             Overall performance summary
GET    /analytics/edge                Edge analysis by condition
       ?group_by=session|instrument|regime|day_of_week|setup_type
GET    /analytics/equity-curve        Equity curve data points
       ?from=ISO&to=ISO&resolution=daily
GET    /analytics/r-distribution      R-multiple distribution histogram
GET    /analytics/win-rate            Win rate breakdown
GET    /analytics/best-conditions     Top performing conditions
GET    /analytics/worst-conditions    Worst performing conditions
```

---

## Risk Endpoints

```
GET    /risk/status                   Current risk exposure snapshot
GET    /risk/validate                 Validate a hypothetical trade
       Body: {"instrument": "US500", "direction": "SHORT", "size": 2.5, "stop_loss": 6528.0}
PATCH  /risk/config                   Update risk configuration
GET    /risk/drawdown                 Daily/weekly drawdown status
```

---

## Sentiment Endpoints

```
GET    /sentiment/{instrument}        Latest sentiment for instrument
GET    /sentiment/news                Recent processed news items
       ?instrument=US500&limit=10
GET    /sentiment/macro               Latest macro event summaries
```

---

## WebSocket Events

All WebSocket connections authenticated via `?token={jwt}` query param.

```
WS /market/stream/{instrument}
   Emits: { type: "CANDLE_CLOSED", candle: {...} }
          { type: "CANDLE_UPDATE", candle: {...} }

WS /setups/stream
   Emits: { type: "SETUP_DETECTED", setup: {...} }
          { type: "SETUP_EXPIRED", setup_id: "..." }

WS /agent/stream
   Emits: { type: "DECISION_MADE", decision: {...} }
          { type: "TRADE_OPENED", trade: {...} }
          { type: "TRADE_CLOSED", trade: {...} }
          { type: "AGENT_PAUSED", reason: "..." }
          { type: "RISK_BREACH", detail: {...} }
```

---

## Error Response Format

```json
{
  "error": {
    "code": "RISK_VALIDATION_FAILED",
    "message": "Trade rejected: daily drawdown limit reached (3.0%)",
    "details": {
      "current_daily_dd": -3.1,
      "limit": -3.0
    },
    "timestamp": "2026-04-04T14:00:00Z",
    "request_id": "req_abc123"
  }
}
```

---

## Standard HTTP Status Codes

| Code | Meaning |
|---|---|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized (missing/invalid token) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not Found |
| 422 | Unprocessable Entity (schema validation failed) |
| 429 | Too Many Requests (rate limited) |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

---

*Document Owner: Backend Lead | Review Cycle: Per API Version*
