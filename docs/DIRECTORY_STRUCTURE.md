# AgentICTrader — Directory Structure

> Generated: May 26, 2026
> Excludes: node_modules, __pycache__, .hypothesis, .pytest_cache, .git, .venv

`
AgentICTrader/
│
├── agent/                          # LangGraph agent execution loop
│   ├── state.py                    # AgentState Pydantic model
│   ├── graph.py                    # AgentGraph + FastAPI kill switch endpoints
│   ├── edges.py                    # Conditional routing logic
│   └── nodes/
│       ├── observe_node.py
│       ├── analyse_node.py
│       ├── decide_node.py
│       ├── notify_node.py
│       ├── execute_node.py
│       ├── review_node.py
│       └── learn_node.py
│
├── backend/                        # Legacy Django backend (being superseded)
│   ├── agentictrader/              # Django project settings, URLs, ASGI/WSGI
       db/influx.py
    trader/                     # Core trading Django app
       agents/                 # Legacy agent logic (being migrated)
          power_of_3.py       #  migrated to ml/features/zone_features.py
          market_structure.py
          pd_array/           # Premium/discount array logic
          rl_agent.py         # DROPPED  replaced by XGBoost + LangGraph
       analysis/
          patterns.py         # Legacy liquidity pool detector
          pdarray.py          #  migrated to ml/features/zone_features.py
          timeframes.py
       infrastructure/
           deriv_api.py        # Legacy Deriv connector
           redis_schema.py
           timeseries.py
           migrations/
               001_htf_indicators.sql
    social/                     # Social media integrations (Facebook, X, etc.)
    users/                      # Django user management
    tests/                      # All Python tests (~45 test files)
        test_agent_graph.py
        test_agent_nodes.py
        test_shadow_period.py
        test_risk_engine.py
        ... (40+ more)

 ml/                             # Machine learning pipeline
    features/                   # Feature extractors
       htf_selector.py         # 3-tier HTF timeframe correlation
       htf_projections.py      # HTF OHLC projection features
       candle_features.py      # Body/wick/engulf features
       zone_features.py        # BOS, CHoCH, FVG, liquidity sweep
       session_features.py     # ICT time windows, killzones, narrative
       pipeline.py             # sklearn Pipeline composing all extractors
    models/
       regime_classifier/      # XGBoost multi-class (TRENDING/RANGING/etc.)
          train.py
       pattern_detector/       # XGBoost multi-label (BOS/FVG/SWEEP/etc.)
          train.py
          labeller.py         # Streamlit manual labelling tool
          labeller_ui.py
       confluence_scorer/      # Logistic Regression ensemble  0.01.0 score
           train.py
    backtesting/
       engine.py               # Historical replay, no look-ahead
    inference/
       main.py                 # FastAPI POST /predict + Kafka consumer
    tracking/
        mlflow_client.py        # MLflow experiment tracking

 services/                       # FastAPI microservices
    market-data/                # Tick ingestion, candle building, Kafka producer
       connectors/             # (stubs  actual connectors in market_data/)
       normaliser.py
       kafka_producer.py
       timescaledb_writer.py
       calendar_ingestion.py
    market_data/                # Active connectors (underscore version)
       connectors/
           base.py             # BaseConnector ABC, TickEvent
           oanda.py            # OANDA v20 streaming connector
    risk_engine/
       main.py                 # POST /validate, GET /exposure, GET /status
    auth/
       main.py                 # JWT auth, RBAC, encrypted broker key storage
    analytics/
       edge_analysis.py        # GET /analytics/summary|edge|equity-curve
       journal_importer.py     # CSV/XLSX trade journal importer
       dashboard.py            # Streamlit dashboard (port 8501)
    nlp/
       sentiment_pipeline.py   # FinBERT per-instrument sentiment
       calendar_monitor.py     # Economic calendar blackout monitor
       llm_service.py          # Claude/OpenAI trade reasoning generator
    notifications/
       fcm_service.py          # FCM push alerts + email fallback
    shadow_period/              # Phase 3 shadow period (paper trading)
        oanda_practice.py       # OANDA practice account config
        mode_enforcer.py        # Forces HUMAN_IN_LOOP during shadow period
        feedback_logger.py      # Logs trader feedback to MongoDB
        report_generator.py     # Weekly comparison reports
        main.py                 # FastAPI shadow period endpoints

 frontend/                       # Next.js 15 web dashboard
    src/
        app/                    # App Router pages
           dashboard/          # Live setups feed (WebSocket)
           analytics/          # Win rate, R-distribution, equity curve
           agent/              # Agent status, pause/resume, decision log
           journal/            # Trade journal table + import
           setups/[id]/        # Setup detail panel
        components/             # React components + Vitest tests
           SetupCard.tsx
           DecisionLog.tsx
           AgentStatusCard.tsx
           RDistributionChart.tsx
           WinRateChart.tsx
           ui/                 # shadcn/ui primitives
        hooks/
           useSetupsFeed.ts    # WebSocket live setups
           useAgentStatus.ts
        lib/api.ts              # REST client
        types/index.ts

 docker/
    docker-compose.yml          # infra (TimescaleDB, Kafka, MongoDB, Redis, MLflow, Qdrant)
                                 # + algorag, risk-engine, ml-inference, liquidity, auth, frontend
    docker-compose.test.yml     # InfluxDB stub used by run_tests.sh/ps1
    init/timescaledb/
        001_schema.sql          # HTF projection schema

 # Per-service Dockerfiles live next to their service code, not under docker/:
 #   services/algorag/Dockerfile   services/risk_engine/Dockerfile
 #   services/liquidity/Dockerfile services/auth/Dockerfile
 #   ml/inference/Dockerfile       frontend/Dockerfile
 # backend/ (legacy Django) is not containerized — manage.py has never been implemented.

 scripts/
    load_historical_data.py     # 3yr OANDA OHLCV loader
    load_historical_data_deriv.py
    data_seed.py

 docs/                           # Architecture and design docs
    design.md
    prd.md
    branch_strategy.md
    tdd_process.md
    RAG_ARCHITECTURE.md
    RAG_IMPLEMENTATION_GUIDE.md
    RAG_SYSTEM_DIAGRAM.md

 AgentICTrader documentaion/     # Original BRD and architecture docs
    01_BRD.md
    03_ARCHITECTURE.md
    04_TECH_STACK_AND_API.md
    05_DATA_MODELS.md
    07_ML_PIPELINE.md
    08_AGENT_DESIGN.md
    11_ROADMAP.md

 .kiro/specs/                    # Kiro spec files
    agentictrader-platform/     # Main platform spec (tasks 143)
       requirements.md
       design.md
       tasks.md
    rag-enhancement/            # RAG enhancement spec

 conftest.py                     # Root pytest fixtures
 pytest.ini                      # Test discovery config
 requirements.txt                # Python dependencies
 .env.example                    # Environment variable template
 SETUP_GUIDE.md                  # Setup instructions
`

---

## Key Architecture Notes

### Tech Stack
- **Agent**: LangGraph (Python), Pydantic v2
- **ML**: XGBoost, scikit-learn, MLflow, Hypothesis (PBT)
- **Backend services**: FastAPI, asyncpg, aiokafka, motor (async MongoDB)
- **Databases**: TimescaleDB (OHLCV), MongoDB (journal/decisions), Redis (cache/state), Kafka (event bus)
- **NLP**: FinBERT (HuggingFace), Claude API (Anthropic), OpenAI fallback
- **Frontend**: Next.js 15 App Router, TypeScript, Tailwind CSS, shadcn/ui, Recharts, Socket.io
- **Testing**: pytest, Hypothesis, fakeredis, Vitest + React Testing Library

### Known Issues / Tech Debt
- Two market-data directories exist: services/market-data/ (hyphen) and services/market_data/ (underscore)  needs consolidation
- ackend/trader/ is legacy Django code being progressively migrated into ml/ and services/
- All Python tests live in ackend/tests/ regardless of which service they test

### Confidence Thresholds
- < 0.65   DISCARD
- 0.650.74  LOG ONLY
- 0.750.84  NOTIFY
-  0.85   NOTIFY + AUTO-EXECUTE (autonomous mode only)

### Agent Graph Flow
observe  analyse  decide  notify / execute  review  learn
