# Directory Structure
**Project:** AgentICTrader.AI
**Version:** 1.0.0
**Pattern:** Monorepo (Turborepo)

---

## Full Project Tree

```
AgentICTrader.AI/
│
├── README.md                          # Project overview & doc index
├── DIRECTORY_STRUCTURE.md             # This file
├── CONTRIBUTING.md                    # Contribution guidelines
├── CHANGELOG.md                       # Version history
├── .env.example                       # Environment variable template
├── .gitignore
├── .editorconfig
├── docker-compose.yml                 # Local dev orchestration
├── docker-compose.prod.yml
├── turbo.json                         # Monorepo build config
├── package.json                       # Root workspace config
│
├── docs/                              # ── ALL DOCUMENTATION ──
│   ├── 01_BRD.md                      # Business Requirements Document
│   ├── 02_PRD.md                      # Product Requirements Document
│   ├── 03_ARCHITECTURE.md             # System Architecture Document
│   ├── 04_TECH_STACK.md               # Technology Stack
│   ├── 05_DATA_MODELS.md              # Data Models & Schema Design
│   ├── 06_API_DESIGN.md               # API Design & Endpoints
│   ├── 07_ML_PIPELINE.md              # ML Pipeline & Model Architecture
│   ├── 08_AGENT_DESIGN.md             # Agentic AI Design
│   ├── 09_SECURITY.md                 # Security Architecture
│   ├── 10_DEPLOYMENT.md               # Deployment & Infrastructure
│   ├── 11_ROADMAP.md                  # Development Roadmap
│   └── diagrams/                      # Architecture & flow diagrams
│       ├── system_architecture.png
│       ├── agent_state_graph.png
│       ├── data_flow.png
│       ├── ml_pipeline.png
│       └── erd.png
│
├── apps/                              # ── FRONTEND APPLICATIONS ──
│   │
│   ├── web/                           # Next.js Web Dashboard
│   │   ├── public/
│   │   ├── src/
│   │   │   ├── app/                   # App Router pages
│   │   │   │   ├── (auth)/
│   │   │   │   │   ├── login/
│   │   │   │   │   └── register/
│   │   │   │   ├── dashboard/
│   │   │   │   │   ├── page.tsx       # Main dashboard
│   │   │   │   │   ├── setups/        # Live setups feed
│   │   │   │   │   ├── backtest/      # Backtest visualiser
│   │   │   │   │   ├── analytics/     # Performance analytics
│   │   │   │   │   ├── journal/       # Trade journal
│   │   │   │   │   ├── agent/         # Agent status & config
│   │   │   │   │   └── settings/
│   │   │   │   └── api/               # Next.js API routes (BFF)
│   │   │   ├── components/
│   │   │   │   ├── ui/                # shadcn/ui base components
│   │   │   │   ├── charts/            # TradingView Lightweight Charts
│   │   │   │   ├── setups/            # Setup cards, detail panels
│   │   │   │   ├── agent/             # Agent status widgets
│   │   │   │   └── layout/            # Nav, sidebar, header
│   │   │   ├── hooks/                 # Custom React hooks
│   │   │   ├── lib/                   # Utilities, API client
│   │   │   ├── stores/                # Zustand state management
│   │   │   └── types/                 # TypeScript interfaces
│   │   ├── Dockerfile
│   │   ├── next.config.ts
│   │   ├── tailwind.config.ts
│   │   └── package.json
│   │
│   └── mobile/                        # React Native App (Phase 5)
│       ├── src/
│       │   ├── screens/
│       │   ├── components/
│       │   ├── navigation/
│       │   ├── hooks/
│       │   └── stores/
│       ├── android/
│       ├── ios/
│       └── package.json
│
├── services/                          # ── BACKEND MICROSERVICES ──
│   │
│   ├── market-data/                   # Market Data Ingestion Service
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── connectors/
│   │   │   │   ├── base.py
│   │   │   │   ├── oanda.py
│   │   │   │   ├── ibkr.py
│   │   │   │   └── alpaca.py
│   │   │   ├── normaliser/
│   │   │   │   ├── tick_normaliser.py
│   │   │   │   └── ohlcv_builder.py
│   │   │   ├── publishers/
│   │   │   │   ├── kafka_producer.py
│   │   │   │   └── db_writer.py
│   │   │   ├── api/
│   │   │   │   ├── router.py
│   │   │   │   └── schemas.py
│   │   │   └── config.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── analytics/                     # Analytics & Reporting Service
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── processors/
│   │   │   │   ├── journal_processor.py
│   │   │   │   ├── edge_analyser.py
│   │   │   │   └── performance_calc.py
│   │   │   ├── api/
│   │   │   │   ├── router.py
│   │   │   │   └── schemas.py
│   │   │   └── dbt/                   # dbt transformation models
│   │   │       ├── models/
│   │   │       ├── tests/
│   │   │       └── dbt_project.yml
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── risk-engine/                   # Risk Management Service
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── engine/
│   │   │   │   ├── position_sizer.py
│   │   │   │   ├── drawdown_monitor.py
│   │   │   │   ├── exposure_tracker.py
│   │   │   │   └── calendar_guard.py
│   │   │   ├── api/
│   │   │   │   ├── router.py          # /validate, /exposure, /status
│   │   │   │   └── schemas.py
│   │   │   └── config.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── user-service/                  # User / Auth Service
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── auth/
│   │   │   │   ├── jwt_handler.py
│   │   │   │   └── oauth.py
│   │   │   ├── models/
│   │   │   ├── api/
│   │   │   └── config.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── notification/                  # Push Notification Service
│       ├── src/
│       │   ├── main.py
│       │   ├── channels/
│       │   │   ├── push.py            # FCM / APNs
│       │   │   ├── email.py
│       │   │   └── webhook.py
│       │   └── formatter.py
│       ├── Dockerfile
│       └── requirements.txt
│
├── ml/                                # ── MACHINE LEARNING ──
│   │
│   ├── features/                      # Feature Engineering
│   │   ├── __init__.py
│   │   ├── price_features.py          # Candle structure, ATR, momentum
│   │   ├── zone_features.py           # S/D zone proximity, strength
│   │   ├── session_features.py        # Session, day-of-week, time
│   │   ├── volume_features.py         # Volume delta, profile
│   │   ├── htf_features.py            # Higher timeframe alignment
│   │   └── pipeline.py                # Sklearn pipeline orchestration
│   │
│   ├── models/                        # Model Definitions
│   │   ├── regime_classifier/
│   │   │   ├── model.py               # XGBoost regime classifier
│   │   │   ├── train.py
│   │   │   └── evaluate.py
│   │   ├── pattern_detector/
│   │   │   ├── model.py               # Pattern detection model
│   │   │   ├── labeller.py            # Manual/semi-auto labelling tool
│   │   │   ├── train.py
│   │   │   └── evaluate.py
│   │   └── confluence_scorer/
│   │       ├── model.py               # Ensemble scorer
│   │       ├── train.py
│   │       └── evaluate.py
│   │
│   ├── training/                      # Training Pipelines
│   │   ├── data_prep.py
│   │   ├── train_pipeline.py
│   │   ├── walk_forward.py            # Walk-forward validation
│   │   └── hyperparameter_tuning.py
│   │
│   ├── inference/                     # Inference Service (FastAPI)
│   │   ├── main.py
│   │   ├── predictor.py
│   │   ├── schemas.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── backtesting/                   # Backtesting Engine
│   │   ├── engine.py
│   │   ├── strategy.py
│   │   ├── metrics.py                 # Sharpe, Sortino, max DD, etc.
│   │   ├── visualiser.py
│   │   └── reports/
│   │
│   ├── notebooks/                     # Jupyter Notebooks (R&D)
│   │   ├── 01_data_exploration.ipynb
│   │   ├── 02_feature_engineering.ipynb
│   │   ├── 03_regime_classification.ipynb
│   │   ├── 04_pattern_detection.ipynb
│   │   ├── 05_backtesting.ipynb
│   │   └── 06_model_evaluation.ipynb
│   │
│   ├── experiments/                   # MLflow experiment configs
│   │   └── configs/
│   │
│   └── requirements.txt
│
├── agent/                             # ── AGENTIC AI CORE ──
│   │
│   ├── src/
│   │   ├── main.py                    # Agent entry point
│   │   ├── graph/                     # LangGraph state graph
│   │   │   ├── state.py               # AgentState definition
│   │   │   ├── nodes/
│   │   │   │   ├── observe.py
│   │   │   │   ├── analyse.py
│   │   │   │   ├── decide.py
│   │   │   │   ├── notify.py
│   │   │   │   ├── execute.py
│   │   │   │   ├── review.py
│   │   │   │   └── learn.py
│   │   │   ├── edges.py               # Conditional routing logic
│   │   │   └── builder.py             # Graph construction
│   │   │
│   │   ├── tools/                     # Agent tool definitions
│   │   │   ├── market_tools.py        # Fetch candles, zones, indicators
│   │   │   ├── ml_tools.py            # Call ML inference service
│   │   │   ├── sentiment_tools.py     # Fetch sentiment signals
│   │   │   ├── risk_tools.py          # Call risk engine
│   │   │   ├── broker_tools.py        # Place / manage orders
│   │   │   └── journal_tools.py       # Log decisions and outcomes
│   │   │
│   │   ├── prompts/                   # LLM prompt templates
│   │   │   ├── trade_reasoning.py
│   │   │   ├── market_summary.py
│   │   │   └── outcome_analysis.py
│   │   │
│   │   ├── memory/                    # Agent memory management
│   │   │   ├── short_term.py          # Redis-backed session memory
│   │   │   └── long_term.py           # MongoDB-backed trade memory
│   │   │
│   │   └── config.py
│   │
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── nlp/                               # ── NLP / LLM SERVICE ──
│   │
│   ├── src/
│   │   ├── main.py
│   │   ├── sentiment/
│   │   │   ├── finbert_classifier.py  # FinBERT sentiment pipeline
│   │   │   ├── news_scraper.py        # News feed ingestion
│   │   │   └── signal_publisher.py
│   │   ├── macro/
│   │   │   ├── calendar_monitor.py    # Economic calendar watcher
│   │   │   └── event_summariser.py    # LLM event summarisation
│   │   ├── reasoning/
│   │   │   └── trade_narrator.py      # LLM trade reasoning generation
│   │   └── api/
│   │       ├── router.py
│   │       └── schemas.py
│   │
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── data/                              # ── DATA ENGINEERING ──
│   │
│   ├── ingestion/
│   │   ├── historical_loader.py       # Bulk historical data load
│   │   ├── journal_importer.py        # Trade journal CSV/XLSX importer
│   │   └── seed_data/                 # Seed datasets for dev
│   │
│   ├── schemas/                       # Database schema definitions
│   │   ├── timescaledb/
│   │   │   ├── 001_create_candles.sql
│   │   │   ├── 002_create_ticks.sql
│   │   │   └── 003_create_indicators.sql
│   │   └── mongodb/
│   │       ├── trade_journal.json
│   │       └── agent_decisions.json
│   │
│   ├── migrations/                    # Alembic DB migrations
│   │   └── versions/
│   │
│   ├── pipelines/                     # Airflow / Prefect DAGs
│   │   ├── daily_data_refresh.py
│   │   ├── model_retraining.py
│   │   └── performance_report.py
│   │
│   └── quality/
│       ├── data_validator.py          # Great Expectations checks
│       └── expectations/
│
├── infra/                             # ── INFRASTRUCTURE AS CODE ──
│   │
│   ├── terraform/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── modules/
│   │   │   ├── eks/                   # Kubernetes cluster
│   │   │   ├── rds/                   # TimescaleDB (RDS Postgres)
│   │   │   ├── elasticache/           # Redis
│   │   │   ├── msk/                   # Managed Kafka
│   │   │   └── s3/                    # Object storage
│   │   └── environments/
│   │       ├── dev/
│   │       ├── staging/
│   │       └── prod/
│   │
│   ├── kubernetes/
│   │   ├── namespaces/
│   │   ├── deployments/
│   │   │   ├── market-data.yaml
│   │   │   ├── ml-engine.yaml
│   │   │   ├── agent.yaml
│   │   │   ├── nlp-service.yaml
│   │   │   ├── risk-engine.yaml
│   │   │   └── web.yaml
│   │   ├── services/
│   │   ├── ingress/
│   │   ├── configmaps/
│   │   └── secrets/                   # (templates only — actual via KMS)
│   │
│   └── monitoring/
│       ├── grafana/
│       │   └── dashboards/
│       │       ├── system_health.json
│       │       ├── ml_performance.json
│       │       └── trading_pnl.json
│       └── prometheus/
│           └── rules/
│
├── shared/                            # ── SHARED PACKAGES ──
│   ├── python/
│   │   ├── agentict_common/
│   │   │   ├── models/                # Shared Pydantic models
│   │   │   ├── kafka/                 # Kafka client utilities
│   │   │   ├── logging/               # Structured logging
│   │   │   └── utils/
│   │   └── setup.py
│   └── typescript/
│       ├── types/                     # Shared TypeScript types
│       └── package.json
│
├── scripts/                           # ── DEV & OPS SCRIPTS ──
│   ├── setup_dev.sh                   # Bootstrap local environment
│   ├── seed_db.sh                     # Seed development database
│   ├── run_backtest.sh
│   ├── deploy_staging.sh
│   └── rollback.sh
│
└── .github/                           # ── CI/CD ──
    ├── workflows/
    │   ├── ci.yml                     # Lint, test, build on PR
    │   ├── cd_staging.yml             # Deploy to staging on merge to main
    │   ├── cd_prod.yml                # Deploy to prod on release tag
    │   └── ml_retrain.yml             # Scheduled model retraining
    └── PULL_REQUEST_TEMPLATE.md
```

---

## Key Design Decisions

**Why a Monorepo?**
All services share types, Kafka schemas, and utility libraries. A monorepo enforces consistency and simplifies cross-service refactoring — critical when the ML models, agent logic, and API contracts are tightly coupled.

**Why separate `ml/`, `agent/`, `nlp/` from `services/`?**
These three domains have fundamentally different development cycles. ML requires notebooks, training runs, and experiment tracking. The agent requires graph state management and LangGraph tooling. NLP has its own model weights and scraper logic. Separating them keeps each domain focused and independently versioned.

**Why `shared/`?**
Kafka message schemas, Pydantic models for trade setups, and logging utilities are used across 6+ services. Shared packages prevent schema drift — the most common source of silent bugs in distributed systems.
