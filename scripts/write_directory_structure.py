"""Write the canonical DIRECTORY_STRUCTURE.md with proper Unicode box-drawing characters."""
import pathlib

CONTENT = """\
# AgentICTrader.AI — Directory Structure
> Version: 2.0  |  May 26, 2026  |  Includes Liquidity Engine
> Excludes: node_modules, __pycache__, .hypothesis, .pytest_cache, .git, .venv

```
AgentICTrader/
│
├── liquidity_engine/                    # Core liquidity mapping package
│   │                                    # Imported by agent/, ml/, and services/
│   ├── __init__.py                      # Exports LiquidityMappingEngine + all models
│   ├── models.py                        # LiquidityLevel, LiquidityMap, IPDARoute,
│   │                                    # SweepEvent, all enums
│   │                                    # LiquidityMap.to_agent_context() → str
│   ├── engine.py                        # LiquidityMappingEngine — main orchestrator
│   │                                    # engine.map(m15,h1,h4,daily,weekly,monthly,
│   │                                    #            htf_bias, session) → LiquidityMap
│   │                                    # engine.get_rag_query_context(lmap) → str
│   │                                    # engine.get_high_probability_levels(lmap, 0.65)
│   ├── ipda_classifier.py               # IPDAClassifier — IPDA delivery route
│   │                                    # Outputs: IPDARoute (route_type, po3_phase,
│   │                                    # primary_draw, judas_swing_detected,
│   │                                    # route_confidence 0–1, confluence_score 0–6)
│   └── detectors/
│       ├── __init__.py
│       ├── external.py                  # BSL/SSL: SwingDetector, EqualLevelDetector,
│       │                                # PriorPeriodDetector (PDH/PDL/PWH/PWL/PMH/PML),
│       │                                # OpeningRangeDetector
│       ├── internal.py                  # Imbalances: FVGDetector (FVG/IFVG/BPR),
│       │                                # VolumeImbalanceDetector, EquilibriumDetector
│       └── institutional.py             # Order flow: OrderBlockDetector
│                                        # OB_Bull/Bear, Breaker blocks, Propulsion blocks
│
├── agent/                               # LangGraph agent execution loop
│   ├── __init__.py
│   ├── state.py                         # AgentState Pydantic v2 model
│   │                                    # Core: setup_id, instrument, timeframe,
│   │                                    # direction, detected_at, regime, patterns,
│   │                                    # confidence, trade_plan, risk_validation,
│   │                                    # decision, mode (HUMAN_IN_LOOP / AUTONOMOUS)
│   │                                    # Time: time_window, narrative_phase,
│   │                                    # time_window_weight, is_killzone,
│   │                                    # price_vs_daily/weekly/true_day_open
│   │                                    # Liquidity: liquidity_map, ipda_route_type,
│   │                                    # draw_on_liq, liq_confluence, sweep_detected
│   ├── graph.py                         # AgentGraph + FastAPI kill switch
│   │                                    # POST /agent/pause  POST /agent/resume
│   │                                    # GET  /agent/status
│   ├── edges.py                         # Conditional routing logic
│   └── nodes/
│       ├── __init__.py
│       ├── observe_node.py              # Ingest Kafka message → AgentState
│       │                                # Calls engine.map() → state.liquidity_map
│       │                                # Rejects stale setups (> 60s old)
│       ├── analyse_node.py              # Fetch sentiment + blackout from Redis
│       │                                # Adjust final_confidence (±3%)
│       ├── decide_node.py               # Confidence gate (< 0.65 → SKIP)
│       │                                # Call Risk Engine /validate synchronously
│       │                                # Route: NOTIFY or EXECUTE
│       ├── notify_node.py               # Build FCM payload, dispatch push alert
│       ├── execute_node.py              # Pre-execution risk recheck, place order
│       ├── review_node.py               # Partial exit at 1R
│       └── learn_node.py                # Log outcome → MongoDB trade_journal
│
├── ml/                                  # Machine learning pipeline
│   ├── __init__.py
│   ├── features/
│   │   ├── __init__.py
│   │   ├── htf_selector.py              # 3-tier HTF timeframe correlation
│   │   │                                # SCALPING → (H1, M15, M1)
│   │   │                                # INTRADAY_STANDARD → (D1, H1, M5)
│   │   │                                # INTRADAY_SIMPLE  → (D1, H4, M15)
│   │   │                                # SWING → (W1, D1, H1)
│   │   │                                # POSITION → (MN1, W1, H4)
│   │   ├── htf_projections.py           # HTF OHLC projection features
│   │   │                                # htf_open_bias, htf_high/low_proximity_pct,
│   │   │                                # htf_body_pct, htf_upper/lower_wick_pct,
│   │   │                                # htf_close_position
│   │   ├── candle_features.py           # body_pct, upper/lower_wick_pct,
│   │   │                                # close_position, is_bullish, is_engulfing
│   │   ├── zone_features.py             # Consumes LiquidityMap → ML feature dict
│   │   │                                # nearest_bsl_pips, nearest_ssl_pips
│   │   │                                # bsl_strength, ssl_strength (0–1)
│   │   │                                # active_fvg_count, fvg_above/below_pips
│   │   │                                # ipda_route_type, route_confidence (0–1)
│   │   │                                # po3_phase, judas_swing (binary)
│   │   │                                # liq_confluence_score (0–6)
│   │   │                                # sweep_occurred, liq_imbalance_ratio
│   │   ├── session_features.py          # ICT time windows (DST-aware, NY time):
│   │   │                                # ASIAN_RANGE (20:00–22:00)
│   │   │                                # TRUE_DAY_OPEN (00:00–01:00)
│   │   │                                # LONDON_KILLZONE (02:00–05:00)
│   │   │                                # LONDON_SILVER_BULLET (03:00–04:00)
│   │   │                                # NY_AM_KILLZONE (07:00–10:00)
│   │   │                                # NY_AM_SILVER_BULLET (10:00–11:00)
│   │   │                                # LONDON_CLOSE (10:00–12:00)
│   │   │                                # NY_PM_KILLZONE (13:30–16:00)
│   │   │                                # NY_PM_SILVER_BULLET (14:00–15:00)
│   │   │                                # NEWS_WINDOW (08:00–09:00)
│   │   │                                # DAILY_CLOSE (17:00–18:00)
│   │   │                                # OFF_HOURS
│   │   │                                # time_window_weight: Silver Bullet=1.0,
│   │   │                                # Killzone=0.9, News=0.8, TDO=0.7,
│   │   │                                # London Close=0.5, Asian=0.3, Off=0.1
│   │   └── pipeline.py                  # sklearn Pipeline composing all extractors
│   │                                    # fit_transform / transform → flat DataFrame
│   │                                    # Great Expectations data quality suite
│   ├── models/
│   │   ├── __init__.py
│   │   ├── regime_classifier/
│   │   │   ├── __init__.py
│   │   │   └── train.py                 # XGBoost multi-class
│   │   │                                # TRENDING_BULLISH, TRENDING_BEARISH,
│   │   │                                # RANGING, BREAKOUT, NEWS_DRIVEN
│   │   │                                # Walk-forward ≥8 folds, ≥75% accuracy
│   │   ├── pattern_detector/
│   │   │   ├── __init__.py
│   │   │   ├── train.py                 # XGBoost multi-label (one per pattern)
│   │   │   │                            # BOS_CONFIRMED, CHOCH_DETECTED,
│   │   │   │                            # BEARISH_ARRAY_REJECTION,
│   │   │   │                            # BULLISH_ARRAY_BOUNCE, FVG_PRESENT,
│   │   │   │                            # LIQUIDITY_SWEEP, ORDER_BLOCK, INDUCEMENT
│   │   │   │                            # ≥80% accuracy, FPR < 20% @ threshold 0.75
│   │   │   ├── labeller.py              # Streamlit manual labelling tool
│   │   │   └── labeller_ui.py           # UI helpers
│   │   └── confluence_scorer/
│   │       ├── __init__.py
│   │       └── train.py                 # Logistic Regression ensemble → 0.0–1.0
│   │                                    # Feature weights:
│   │                                    #   route_confidence     0.30
│   │                                    #   liq_confluence_score 0.25
│   │                                    #   judas_swing          0.20
│   │                                    #   bsl_strength         0.10
│   │                                    #   sweep_occurred       0.10
│   │                                    #   fvg_above_strength   0.05
│   │                                    # Thresholds:
│   │                                    #   < 0.65   → DISCARD
│   │                                    #   0.65–0.74 → LOG ONLY
│   │                                    #   0.75–0.84 → NOTIFY
│   │                                    #   ≥ 0.85   → AUTO-EXECUTE
│   ├── backtesting/
│   │   ├── __init__.py
│   │   └── engine.py                    # Historical replay, strict time order
│   │                                    # No look-ahead, confidence threshold gates
│   │                                    # Metrics: Sharpe, Sortino, max DD, win rate
│   ├── inference/
│   │   ├── __init__.py
│   │   └── main.py                      # FastAPI POST /predict
│   │                                    # Kafka: market.candles → setups.detected
│   │                                    # Loads models from MLflow registry
│   └── tracking/
│       ├── __init__.py
│       └── mlflow_client.py             # MLflow experiment tracking
│                                        # Experiments: regime-classifier,
│                                        # pattern-detector, confluence-scorer
│
├── services/                            # FastAPI microservices
│   ├── __init__.py
│   │
│   ├── liquidity/                       # Liquidity mapping service (port 8006)
│   │   ├── __init__.py
│   │   ├── main.py                      # POST /liquidity/map → LiquidityMap JSON
│   │   │                                # GET  /liquidity/rag-context?symbol=
│   │   │                                # GET  /liquidity/levels?symbol=&min_strength=
│   │   │                                # GET  /liquidity/status
│   │   ├── engine_instance.py           # Singleton LiquidityMappingEngine per symbol
│   │   ├── kafka_consumer.py            # Consumes candle-close → engine.map()
│   │   │                                # Caches result in Redis (TTL: 1 candle)
│   │   └── timescaledb_writer.py        # Persists LiquidityMap snapshots
│   │                                    # Enables historical replay in backtesting
│   │
│   ├── market_data/                     # Market data connectors
│   │   ├── __init__.py
│   │   ├── normaliser.py                # Tick → OHLCV candle builder
│   │   ├── kafka_producer.py            # Publishes market.ticks, market.candles
│   │   └── connectors/
│   │       ├── __init__.py
│   │       ├── base.py                  # BaseConnector ABC, TickEvent, ConnectorError
│   │       └── oanda.py                 # OANDA v20 streaming (12 instruments)
│   │                                    # Exponential backoff, max 5 retries, 30s cap
│   │
│   ├── market-data/                     # Market data infrastructure
│   │   ├── __init__.py
│   │   ├── calendar_ingestion.py        # Economic calendar ingestion
│   │   │                                # Daily refresh 00:05 UTC via APScheduler
│   │   └── timescaledb_writer.py        # Candle/tick upsert, batch 500, flush ≤1s
│   │
│   ├── risk_engine/
│   │   ├── __init__.py
│   │   └── main.py                      # POST /validate — 7-gate risk check:
│   │                                    #   1. confidence ≥ 0.65
│   │                                    #   2. kill switch inactive
│   │                                    #   3. daily drawdown < 3%
│   │                                    #   4. weekly drawdown < 6%
│   │                                    #   5. open trades < 3
│   │                                    #   6. no news blackout
│   │                                    #   7. position size = 1% equity / SL pips
│   │                                    # GET /exposure  GET /status
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   └── main.py                      # JWT auth (15min access / 7-day refresh)
│   │                                    # RBAC: Admin, Trader, Viewer
│   │                                    # Broker API keys encrypted at rest (KMS)
│   │
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── edge_analysis.py             # GET /analytics/summary
│   │   │                                # GET /analytics/edge
│   │   │                                # GET /analytics/equity-curve
│   │   ├── journal_importer.py          # CSV/XLSX → MongoDB trade_journal
│   │   └── dashboard.py                 # Streamlit dashboard (port 8501)
│   │                                    # Win Rate, R-Distribution, Equity Curve,
│   │                                    # Session Breakdown, HTF Bias Performance
│   │
│   ├── nlp/
│   │   ├── __init__.py
│   │   ├── sentiment_pipeline.py        # FinBERT sentiment (−1.0 to +1.0)
│   │   │                                # Kafka: → sentiment.signals
│   │   │                                # Redis: sentiment:{instrument} TTL 900s
│   │   ├── calendar_monitor.py          # Polls economic_events every 60s
│   │   │                                # Redis: blackout:{instrument} TTL 60s
│   │   └── llm_service.py               # Claude primary / OpenAI fallback
│   │                                    # summarise_macro_event() → str
│   │                                    # generate_trade_reasoning() → 3Q narrative:
│   │                                    #   1. Where has price come from?
│   │                                    #   2. Where is it now?
│   │                                    #   3. Where is it likely to go?
│   │                                    # Injects lmap.to_agent_context() + RAG analogs
│   │
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── fcm_service.py               # FCM push + email fallback
│   │                                    # Alert payload: instrument, direction,
│   │                                    # confidence, entry/SL/TP, R-ratio, reasoning,
│   │                                    # HTF O/H/L, time_window, narrative_phase
│   │
│   └── shadow_period/                   # Phase 3 — 4-week paper trading
│       ├── __init__.py
│       ├── oanda_practice.py            # OANDA practice account config
│       │                                # OANDA_PRACTICE_API_KEY
│       │                                # OANDA_PRACTICE_ACCOUNT_ID
│       ├── mode_enforcer.py             # Forces HUMAN_IN_LOOP during shadow period
│       │                                # Redis: shadow:active → {active, started_at}
│       ├── feedback_logger.py           # Trader feedback → MongoDB shadow_feedback
│       │                                # Actions: TAKEN / SKIPPED / MODIFIED
│       ├── report_generator.py          # Weekly reports: match_rate, win_rate, avg_R
│       │                                # Exit criterion: ≥ 80% match rate
│       └── main.py                      # POST /shadow/feedback
│                                        # GET  /shadow/report/weekly/{week_number}
│                                        # GET  /shadow/report/exit-criterion
│                                        # GET  /shadow/status
│
├── frontend/                            # Next.js 15 App Router dashboard
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── package.json                     # React 19, TypeScript, shadcn/ui,
│   │                                    # Recharts, Socket.io-client, Vitest
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx
│       │   ├── globals.css
│       │   ├── dashboard/               # Live setups feed (WebSocket)
│       │   ├── setups/[id]/             # Setup detail panel
│       │   │                            # patterns, HTF levels, confidence,
│       │   │                            # reasoning, trade plan
│       │   ├── agent/                   # Agent status, pause/resume, decision log
│       │   ├── journal/                 # Trade journal + CSV/XLSX import
│       │   └── analytics/               # Win rate, R-distribution, equity curve
│       ├── components/
│       │   ├── ui/                      # shadcn/ui primitives
│       │   ├── SetupCard.tsx
│       │   ├── DecisionLog.tsx
│       │   ├── AgentStatusCard.tsx
│       │   ├── ConfidenceBadge.tsx
│       │   ├── RDistributionChart.tsx
│       │   ├── WinRateChart.tsx
│       │   ├── EquityCurveChart.tsx
│       │   ├── JournalTable.tsx
│       │   ├── RiskExposureCard.tsx
│       │   └── NavSidebar.tsx
│       ├── hooks/
│       │   ├── useSetupsFeed.ts         # WebSocket live setups
│       │   └── useAgentStatus.ts
│       ├── lib/
│       │   ├── api.ts                   # REST client
│       │   └── utils.ts
│       └── types/
│           └── index.ts
│
├── backend/                             # Legacy Django backend
│   │                                    # Being superseded by services/ and ml/
│   │                                    # Retained for: ORM models, social integrations
│   ├── agentictrader/                   # Django project settings, URLs, ASGI/WSGI
│   │   └── db/influx.py
│   ├── trader/
│   │   ├── agents/
│   │   │   ├── market_structure.py      # Keep until fully migrated to liquidity_engine
│   │   │   ├── power_of_3.py            # ⚠ RETIRED → liquidity_engine/ipda_classifier.py
│   │   │   ├── pd_array/                # ⚠ RETIRED → liquidity_engine/detectors/institutional.py
│   │   │   └── rl_agent.py              # ⚠ DROPPED  — replaced by XGBoost + LangGraph
│   │   ├── analysis/
│   │   │   ├── patterns.py              # ⚠ RETIRED → liquidity_engine/detectors/external.py
│   │   │   ├── pdarray.py               # ⚠ RETIRED → liquidity_engine/detectors/internal.py
│   │   │   └── timeframes.py
│   │   └── infrastructure/
│   │       ├── deriv_api.py             # Legacy Deriv connector
│   │       ├── redis_schema.py
│   │       ├── timeseries.py
│   │       └── migrations/
│   │           └── 001_htf_indicators.sql
│   ├── social/                          # Social media integrations
│   │   ├── generators/post_generator.py
│   │   └── integrators/                 # Facebook, Instagram, TikTok, X
│   ├── users/                           # Django user management
│   └── tests/                           # All Python tests (~45 files)
│       ├── test_agent_graph.py
│       ├── test_agent_nodes.py
│       ├── test_agent_state.py
│       ├── test_auth_service.py
│       ├── test_backtesting_engine.py
│       ├── test_calendar_ingestion.py
│       ├── test_calendar_monitor.py
│       ├── test_candle_builder.py
│       ├── test_candle_features.py
│       ├── test_edge_analysis.py
│       ├── test_feature_pipeline.py
│       ├── test_htf_projections.py
│       ├── test_htf_selector.py
│       ├── test_inference_service.py
│       ├── test_journal_importer.py
│       ├── test_kafka_producer.py
│       ├── test_llm_service.py
│       ├── test_mlflow_client.py
│       ├── test_notification_service.py
│       ├── test_oanda_connector.py
│       ├── test_pattern_detector_train.py
│       ├── test_redis_schema.py
│       ├── test_regime_classifier_train.py
│       ├── test_risk_engine.py
│       ├── test_sentiment_pipeline.py
│       ├── test_session_features.py
│       ├── test_shadow_period.py
│       ├── test_timescaledb_writer.py
│       └── test_zone_features.py
│
├── docker/
│   ├── docker-compose.yml               # infra (TimescaleDB, Kafka, MongoDB, Redis,
│   │                                    # MLflow, Qdrant) + algorag (8003),
│   │                                    # risk-engine (8004), ml-inference (8001),
│   │                                    # liquidity (8006), auth (8007), frontend (3000)
│   ├── docker-compose.test.yml          # InfluxDB stub used by run_tests.sh/ps1
│   └── init/timescaledb/
│       └── 001_schema.sql               # HTF projection schema
│                                        # Future: liquidity_snapshots hypertable
│
│   # Per-service Dockerfiles live next to their service code:
│   #   services/algorag/Dockerfile   services/risk_engine/Dockerfile
│   #   services/liquidity/Dockerfile services/auth/Dockerfile
│   #   ml/inference/Dockerfile       frontend/Dockerfile
│   # backend/ (legacy Django) is not containerized — manage.py has never been implemented.
│
├── scripts/
│   ├── load_historical_data.py          # 3yr OANDA OHLCV (5 instruments, 7 timeframes)
│   ├── load_historical_data_deriv.py
│   └── data_seed.py
│
├── docs/
│   ├── design.md                        # Full system design
│   ├── prd.md                           # Product requirements
│   ├── branch_strategy.md
│   ├── tdd_process.md
│   ├── RAG_ARCHITECTURE.md
│   ├── RAG_IMPLEMENTATION_GUIDE.md
│   ├── RAG_SYSTEM_DIAGRAM.md
│   └── LIQUIDITY_ENGINE.md              # LiquidityMap schema, IPDA logic,
│                                        # detector behaviour, integration points
│
├── AgentICTrader documentaion/          # Original BRD and architecture docs
│   ├── 01_BRD.md
│   ├── 03_ARCHITECTURE.md
│   ├── 04_TECH_STACK_AND_API.md
│   ├── 05_DATA_MODELS.md
│   ├── 07_ML_PIPELINE.md
│   ├── 08_AGENT_DESIGN.md
│   ├── 11_ROADMAP.md
│   └── DIRECTORY_STRUCTURE.md          # ← this file
│
├── .kiro/specs/
│   ├── agentictrader-platform/          # Main platform spec (tasks 1–43)
│   │   ├── requirements.md
│   │   ├── design.md
│   │   └── tasks.md
│   └── rag-enhancement/
│
├── conftest.py                          # Root pytest fixtures
├── pytest.ini                           # Test discovery config
├── requirements.txt                     # Python dependencies
├── .env.example                         # Environment variable template
└── SETUP_GUIDE.md
```

---

## Data Flow

```
OANDA v20 Streaming
        │  ticks
        ▼
services/market_data/connectors/oanda.py
        │  normalised ticks
        ▼
services/market_data/normaliser.py
        │                    │
        ▼                    ▼
market.ticks (Kafka)   market.candles (Kafka)
        │                    │
        ▼                    ▼
timescaledb_writer     services/liquidity/kafka_consumer.py
                             │
                             ▼
                       liquidity_engine/engine.map()
                             │  LiquidityMap
                             ├──→ Redis cache (TTL: 1 candle)
                             └──→ TimescaleDB snapshot
                                          │
                                          ▼
                             ml/inference/main.py
                             (Regime + Pattern + Confluence)
                                          │  setups.detected (Kafka)
                                          ▼
                             agent/nodes/observe_node.py
                             AgentState + LiquidityMap
                                          │
                                          ▼
                             agent/nodes/analyse_node.py
                             sentiment + blackout (Redis)
                                          │
                                          ▼
                             agent/nodes/decide_node.py
                             services/risk_engine/main.py
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
                    NOTIFY path                    EXECUTE path
                          │                               │
                    notify_node.py               execute_node.py
                    FCM push alert               OANDA order
                          │                               │
                          └───────────────┬───────────────┘
                                          ▼
                             agent/nodes/review_node.py
                             (partial exit at 1R)
                                          │
                                          ▼
                             agent/nodes/learn_node.py
                             MongoDB trade_journal
```

---

## Confidence Thresholds

| Score      | Action                                    |
|------------|-------------------------------------------|
| < 0.65     | DISCARD — not logged, no alert            |
| 0.65–0.74  | LOG ONLY — stored, no alert               |
| 0.75–0.84  | NOTIFY — push alert to trader             |
| ≥ 0.85     | NOTIFY + AUTO-EXECUTE (autonomous mode)   |

---

## Redis Key Schema

| Key                           | Value                          | TTL       |
|-------------------------------|--------------------------------|-----------|
| candle:{instrument}:{tf}      | latest OHLCV                   | 65s       |
| htf:{instrument}:{tf}         | HTF projection levels          | 300s      |
| sentiment:{instrument}        | FinBERT score + direction      | 900s      |
| blackout:{instrument}         | {active, event_name, mins}     | 60s       |
| agent:state:{user_id}         | AgentState snapshot            | 3600s     |
| risk:exposure:{user_id}       | {daily_dd, weekly_dd, trades}  | 60s       |
| risk:kill_switch:global       | {active}                       | permanent |
| shadow:active                 | {active, started_at}           | permanent |
| liquidity:{instrument}:{tf}   | LiquidityMap JSON              | 1 candle  |

---

## Kafka Topics

| Topic               | Producer                    | Consumer(s)                          |
|---------------------|-----------------------------|--------------------------------------|
| market.ticks        | market_data/normaliser      | timescaledb_writer                   |
| market.candles      | market_data/normaliser      | timescaledb_writer, liquidity/       |
| setups.detected     | ml/inference                | agent/observe_node                   |
| sentiment.signals   | nlp/sentiment_pipeline      | agent/analyse_node                   |
| agent.kill_switch   | /agent/pause endpoint       | agent/graph.py                       |
"""

out = pathlib.Path("AgentICTrader documentaion/DIRECTORY_STRUCTURE.md")
out.write_text(CONTENT, encoding="utf-8")
print(f"Written {len(CONTENT):,} chars to {out}")
