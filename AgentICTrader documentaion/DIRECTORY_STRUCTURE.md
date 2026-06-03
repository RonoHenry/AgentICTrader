# AgentICTrader.AI  Directory Structure
**Project:** AgentICTrader.AI
**Version:** 2.0  May 26, 2026 (includes Liquidity Engine)
**Pattern:** Monorepo

---

## Full Project Tree

```
AgentICTrader/

 liquidity_engine/                          #  LIQUIDITY ENGINE (core shared package) 
    __init__.py                            # Exports LiquidityMappingEngine + all models
    models.py                              # LiquidityLevel, LiquidityMap, IPDARoute,
                                             # SweepEvent, all enums
                                             # LiquidityMap.to_agent_context()  str (LLM)
    engine.py                              # LiquidityMappingEngine  main orchestrator
                                             # engine.map(m15,h1,h4,daily,weekly,monthly,
                                             #            htf_bias, session)  LiquidityMap
                                             # engine.get_rag_query_context(lmap)  str
                                             # engine.get_high_probability_levels(lmap, 0.65)
    ipda_classifier.py                     # IPDAClassifier  IPDA delivery route
                                             # Outputs: IPDARoute (route_type, po3_phase,
                                             # primary_draw, judas_swing_detected,
                                             # route_confidence 01, confluence_score 06)
    detectors/
        __init__.py
        external.py                        # BSL/SSL: SwingDetector, EqualLevelDetector,
                                             # PriorPeriodDetector (PDH/PDL/PWH/PWL/PMH/PML),
                                             # OpeningRangeDetector
        internal.py                        # Imbalances: FVGDetector (FVG/IFVG/BPR),
                                             # VolumeImbalanceDetector, EquilibriumDetector
        institutional.py                   # Order flow: OrderBlockDetector
                                              # OB_Bull/Bear, Breaker blocks, Propulsion blocks

 agent/                                     #  AGENTIC AI CORE 
    __init__.py
    state.py                               # AgentState Pydantic v2 model
                                             # Core: setup_id, instrument, timeframe,
                                             # direction, detected_at, regime, patterns,
                                             # confidence, trade_plan, risk_validation,
                                             # decision, mode (HUMAN_IN_LOOP/AUTONOMOUS)
                                             # Time: time_window, narrative_phase,
                                             # time_window_weight, is_killzone,
                                             # price_vs_daily/weekly/true_day_open
                                             # Liquidity: liquidity_map, ipda_route_type,
                                             # draw_on_liq, liq_confluence, sweep_detected
    graph.py                               # AgentGraph + FastAPI kill switch
                                             # POST /agent/pause   activate kill switch
                                             # POST /agent/resume  clear kill switch
                                             # GET  /agent/status
    edges.py                               # Conditional routing logic
    nodes/
        __init__.py
        observe_node.py                    # Ingest Kafka setup  AgentState
                                             # Calls LiquidityMappingEngine.map()
                                             # Writes LiquidityMap  state.liquidity_map
        analyse_node.py                    # Fetch sentiment + blackout from Redis
                                             # Adjust final_confidence (3%)
        decide_node.py                     # Confidence gate (< 0.65  SKIP)
                                             # Call Risk Engine /validate synchronously
                                             # Route: NOTIFY or EXECUTE
        notify_node.py                     # Build FCM payload, dispatch push alert
        execute_node.py                    # Pre-execution risk recheck, place order
        review_node.py                     # Partial exit at 1R
        learn_node.py                      # Log outcome  MongoDB trade_journal

 ml/                                        #  MACHINE LEARNING 
    __init__.py
    features/
       __init__.py
       htf_selector.py                    # 3-tier HTF timeframe correlation
                                            # SCALPING(H1,M15,M1)
                                            # INTRADAY_STANDARD(D1,H1,M5)
                                            # INTRADAY_SIMPLE(D1,H4,M15)
                                            # SWING(W1,D1,H1)
                                            # POSITION(MN1,W1,H4)
       htf_projections.py                 # HTF OHLC projection features
                                            # htf_open_bias, htf_high/low_proximity_pct,
                                            # htf_body_pct, htf_wick_pcts, close_position
       candle_features.py                 # body_pct, wick_pcts, close_position,
                                            # is_bullish, is_engulfing
       zone_features.py                   # Consumes LiquidityMap  ML feature dict
                                            # nearest_bsl_pips, nearest_ssl_pips
                                            # bsl_strength, ssl_strength (01)
                                            # active_fvg_count, fvg_above/below_pips
                                            # ipda_route_type, route_confidence (01)
                                            # po3_phase, judas_swing (binary)
                                            # liq_confluence_score (06)
                                            # sweep_occurred, liq_imbalance_ratio
       session_features.py                # ICT time windows (DST-aware, NY times)
                                            # ASIAN_RANGE (20:0022:00)
                                            # TRUE_DAY_OPEN (00:0001:00)
                                            # LONDON_KILLZONE (02:0005:00)
                                            # LONDON_SILVER_BULLET (03:0004:00)
                                            # NY_AM_KILLZONE (07:0010:00)
                                            # NY_AM_SILVER_BULLET (10:0011:00)
                                            # NY_PM_KILLZONE (13:3016:00)
                                            # NY_PM_SILVER_BULLET (14:0015:00)
                                            # NEWS_WINDOW (08:0009:00)
                                            # LONDON_CLOSE (10:0012:00)
                                            # DAILY_CLOSE (17:0018:00)
                                            # OFF_HOURS
                                            # time_window_weight: 0.11.0
                                            # narrative_phase, price_vs_opens
       pipeline.py                        # sklearn Pipeline  all extractors composed
                                             # fit_transform / transform  flat DataFrame
                                             # Great Expectations data quality suite
    models/
       __init__.py
       regime_classifier/
          __init__.py
          train.py                       # XGBoost multi-class
                                            # TRENDING_BULLISH, TRENDING_BEARISH,
                                            # RANGING, BREAKOUT, NEWS_DRIVEN
                                            # Walk-forward 8 folds, 75% accuracy
       pattern_detector/
          __init__.py
          train.py                       # XGBoost multi-label
                                           # BOS_CONFIRMED, CHOCH_DETECTED,
                                           # BEARISH_ARRAY_REJECTION,
                                           # BULLISH_ARRAY_BOUNCE, FVG_PRESENT,
                                           # LIQUIDITY_SWEEP, ORDER_BLOCK, INDUCEMENT
                                           # 80% accuracy, FPR < 20% at 0.75
          labeller.py                    # Streamlit manual labelling tool
          labeller_ui.py                 # UI helpers
       confluence_scorer/
           __init__.py
           train.py                       # Logistic Regression ensemble  0.01.0
                                             # Weights:
                                             #   route_confidence     0.30
                                             #   liq_confluence_score 0.25
                                             #   judas_swing          0.20
                                             #   bsl_strength         0.10
                                             #   sweep_occurred       0.10
                                             #   fvg_above_strength   0.05
                                             # Thresholds:
                                             #   < 0.65     DISCARD
                                             #   0.650.74  LOG ONLY
                                             #   0.750.84  NOTIFY
                                             #    0.85     AUTO-EXECUTE
    backtesting/
       __init__.py
       engine.py                          # Historical replay, strict time order
                                             # No look-ahead, confidence gates
                                             # Metrics: Sharpe, Sortino, max DD,
                                             # win rate, avg R-multiple, expectancy
    inference/
       __init__.py
       main.py                            # FastAPI POST /predict
                                             # Kafka: market.candles  setups.detected
                                             # Loads models from MLflow registry
    tracking/
        __init__.py
        mlflow_client.py                   # MLflow experiment tracking
                                              # Experiments: regime-classifier,
                                              # pattern-detector, confluence-scorer

 services/                                  #  BACKEND MICROSERVICES 
    __init__.py
   
    liquidity/                             # Liquidity Mapping Service  [port 8006]
       __init__.py
       main.py                            # POST /liquidity/map
                                            # GET  /liquidity/rag-context?symbol=
                                            # GET  /liquidity/levels?symbol=&min_strength=
                                            # GET  /liquidity/status
       engine_instance.py                 # Singleton engine per symbol
       kafka_consumer.py                  # Consumes market.candles
                                            #  engine.map()  Redis cache
       timescaledb_writer.py              # Persists LiquidityMap snapshots
   
    market_data/                           # Market Data Connectors
       __init__.py
       normaliser.py                      # Tick  OHLCV candle builder
                                            # Timeframes: M1,M5,M15,H1,H4,D1,W1
       kafka_producer.py                  # Publishes market.ticks, market.candles
       connectors/
           __init__.py
           base.py                        # BaseConnector ABC, TickEvent,
                                            # ConnectorError, TickCallback
           oanda.py                       # OANDA v20 streaming
                                             # 12 instruments: XAUUSD, EURUSD,
                                             # GBPUSD, EURAUD, GBPAUD, USDJPY,
                                             # US100, US30, US500, GER40,
                                             # BTCUSD, ETHUSD
                                             # Reconnect: exp backoff, max 5 retries
   
    market-data/                           # Market Data Infrastructure
       __init__.py
       calendar_ingestion.py              # Economic calendar ingestion
                                            # Daily refresh 00:05 UTC (APScheduler)
       timescaledb_writer.py              # Candle/tick upsert
                                             # Batch 500, flush  1s
   
    risk_engine/                           # Risk Engine  [port 8001]
       __init__.py
       main.py                            # POST /validate  7-gate check:
                                             #   1. confidence  0.65
                                             #   2. kill switch inactive
                                             #   3. daily DD < 3%
                                             #   4. weekly DD < 6%
                                             #   5. open trades < 3
                                             #   6. no news blackout
                                             #   7. position size = 1% equity
                                             # GET /exposure
                                             # GET /status
   
    auth/                                  # Auth Service  [port 8002]
       __init__.py
       main.py                            # POST /auth/register
                                             # POST /auth/login
                                             # POST /auth/refresh
                                             # JWT: 15min access, 7-day refresh
                                             # RBAC: Admin, Trader, Viewer
                                             # Broker keys encrypted at rest
   
    analytics/                             # Analytics Service  [port 8003]
       __init__.py
       edge_analysis.py                   # GET /analytics/summary
                                            # GET /analytics/edge
                                            # GET /analytics/equity-curve
       journal_importer.py                # CSV/XLSX  MongoDB trade_journal
       dashboard.py                       # Streamlit dashboard  [port 8501]
                                             # Win Rate, R-Distribution,
                                             # Equity Curve, Session Breakdown,
                                             # HTF Bias Performance
   
    nlp/                                   # NLP / LLM Service  [port 8004]
       __init__.py
       sentiment_pipeline.py              # FinBERT sentiment (-1.0 to +1.0)
                                            # Kafka:  sentiment.signals
                                            # Redis: sentiment:{instrument} TTL 900s
       calendar_monitor.py                # Polls economic_events every 60s
                                            # Redis: blackout:{instrument} TTL 60s
       llm_service.py                     # Claude primary / OpenAI fallback
                                             # summarise_macro_event()  str
                                             # generate_trade_reasoning()  narrative
                                             # 3-question framework:
                                             #   1. Where has price come from?
                                             #   2. Where is it now?
                                             #   3. Where is it likely to go?
                                             # Injects lmap.to_agent_context()
                                             # Injects RAG journal analogs
   
    notifications/                         # Notification Service  [port 8005]
       __init__.py
       fcm_service.py                     # FCM push + email fallback
                                             # Payload: instrument, direction,
                                             # confidence, entry/SL/TP, R-ratio,
                                             # reasoning, HTF levels, time_window,
                                             # narrative_phase, killzone flags
   
    shadow_period/                         # Shadow Period Service  [port 8007]
        __init__.py
        oanda_practice.py                  # OANDA practice account config
                                             # Env: OANDA_PRACTICE_API_KEY,
                                             #      OANDA_PRACTICE_ACCOUNT_ID
        mode_enforcer.py                   # Forces HUMAN_IN_LOOP during shadow
                                             # Redis: shadow:active
        feedback_logger.py                 # Trader feedback  MongoDB
                                             # Actions: TAKEN / SKIPPED / MODIFIED
        report_generator.py                # Weekly comparison reports
                                             # match_rate_pct, win_rate, avg_R
                                             # Exit criterion:  80% match rate
        main.py                            # POST /shadow/feedback
                                              # GET  /shadow/report/weekly/{week}
                                              # GET  /shadow/report/exit-criterion
                                              # GET  /shadow/status

 frontend/                                  #  WEB DASHBOARD 
    next.config.ts
    tailwind.config.ts
    package.json                           # Next.js 15, React 19, TypeScript,
                                             # shadcn/ui, Recharts, Socket.io-client,
                                             # Vitest + React Testing Library
    src/
        app/
           layout.tsx
           page.tsx
           globals.css
           dashboard/                     # Live setups feed (WebSocket)
           setups/[id]/                   # Setup detail panel
                                            # patterns, HTF levels, confidence,
                                            # reasoning, trade plan,
                                            # draw_on_liquidity, ipda_route_type
           agent/                         # Agent status, pause/resume,
                                            # decision log viewer
           journal/                       # Trade journal + import
           analytics/                     # Win rate, R-distribution,
                                             # equity curve, HTF bias performance
        components/
           ui/                            # shadcn/ui primitives
           SetupCard.tsx
           DecisionLog.tsx
           AgentStatusCard.tsx
           ConfidenceBadge.tsx
           RDistributionChart.tsx
           WinRateChart.tsx
           EquityCurveChart.tsx
           JournalTable.tsx
           RiskExposureCard.tsx
           NavSidebar.tsx
        hooks/
           useSetupsFeed.ts               # WebSocket live setups
           useAgentStatus.ts
        lib/
           api.ts                         # REST client
           utils.ts
        types/
            index.ts

 backend/                                   #  LEGACY DJANGO BACKEND 
                                             # Migration in progress  services/ + ml/
                                             # Retained for: ORM models, social integrations
    agentictrader/                         # Django project settings, URLs, ASGI/WSGI
       db/
           influx.py
    trader/
       agents/
          market_structure.py            # BOS/CHoCH  keep until migrated
          power_of_3.py                  # RETIRED  liquidity_engine/ipda_classifier.py
          pd_array/                      # RETIRED  liquidity_engine/detectors/institutional.py
          rl_agent.py                    # DROPPED  replaced by XGBoost + LangGraph
       analysis/
          patterns.py                    # RETIRED  liquidity_engine/detectors/external.py
          pdarray.py                     # RETIRED  liquidity_engine/detectors/internal.py
          timeframes.py
       infrastructure/
           deriv_api.py                   # Legacy Deriv connector
           redis_schema.py
           timeseries.py
           migrations/
               001_htf_indicators.sql
    social/                                # Social media integrations
       generators/
          post_generator.py
       integrators/
           facebook.py
           instagram.py
           tiktok.py
           x_integrator.py
    users/                                 # Django user management
    tests/                                 # All Python tests (~45 files)
        test_agent_graph.py
        test_agent_nodes.py
        test_agent_state.py
        test_auth_service.py
        test_backtesting_engine.py
        test_calendar_ingestion.py
        test_calendar_monitor.py
        test_candle_builder.py
        test_candle_features.py
        test_edge_analysis.py
        test_feature_pipeline.py
        test_htf_projections.py
        test_htf_selector.py
        test_inference_service.py
        test_journal_importer.py
        test_kafka_producer.py
        test_llm_service.py
        test_mlflow_client.py
        test_notification_service.py
        test_oanda_connector.py
        test_pattern_detector_train.py
        test_redis_schema.py
        test_regime_classifier_train.py
        test_risk_engine.py
        test_sentiment_pipeline.py
        test_session_features.py
        test_shadow_period.py
        test_timescaledb_writer.py
        test_zone_features.py

 docker/                                    #  DOCKER / INFRASTRUCTURE 
    docker-compose.yml                     # All services: TimescaleDB, Kafka,
                                             # MongoDB, Redis, MLflow,
                                             # market-data, risk-engine,
                                             # ml-inference, agent, nlp, auth,
                                             # analytics, liquidity (port 8006)
    docker-compose.prod.yml
    docker-compose.test.yml
    Dockerfile.backend
    Dockerfile.frontend
    init/
        timescaledb/
            001_schema.sql                 # HTF projection schema

 scripts/                                   #  DEV SCRIPTS 
    load_historical_data.py                # 3yr OANDA OHLCV loader
                                             # 5 instruments  7 timeframes
    load_historical_data_deriv.py
    data_seed.py

 docs/                                      #  DOCUMENTATION 
    design.md                              # Full system design
    prd.md                                 # Product requirements
    branch_strategy.md
    tdd_process.md
    RAG_ARCHITECTURE.md
    RAG_IMPLEMENTATION_GUIDE.md
    RAG_SYSTEM_DIAGRAM.md
    LIQUIDITY_ENGINE.md                    # Liquidity engine design doc
                                              # LiquidityMap schema, IPDA logic,
                                              # detector behaviour, integration points

 AgentICTrader documentaion/                #  ORIGINAL DESIGN DOCS 
    01_BRD.md
    03_ARCHITECTURE.md
    04_TECH_STACK_AND_API.md
    05_DATA_MODELS.md
    07_ML_PIPELINE.md
    08_AGENT_DESIGN.md
    11_ROADMAP.md
    DIRECTORY_STRUCTURE.md                #  this file

 .kiro/specs/                               #  KIRO SPECS 
    agentictrader-platform/                # Main platform spec (tasks 143)
       requirements.md
       design.md
       tasks.md
    rag-enhancement/
        requirements.md
        tasks.md

 conftest.py                                # Root pytest fixtures
 pytest.ini                                 # Test discovery config
 requirements.txt                           # Python dependencies
 .env.example                               # Environment variable template
 SETUP_GUIDE.md
```

---

## Key Design Decisions

**Why `liquidity_engine/` at root level?**
It is a shared domain package consumed by `agent/`, `ml/`, and `services/` equally. Placing it inside any one of those would create circular imports. Root-level placement mirrors how `agent/` and `ml/` are structured  each is a first-class domain, not a sub-package of another.

**Why separate `services/market_data/` and `services/market-data/`?**
A naming inconsistency from early development. `market_data/` (underscore) holds the active OANDA connectors. `market-data/` (hyphen) holds the infrastructure writers and calendar ingestion. These will be consolidated into `services/market_data/` in a future cleanup PR.

**Why keep `backend/` at all?**
The Django ORM models, social media integrations, and user management are still live. The agent logic and analysis modules inside it are retired but kept in place until the test suite confirms all functionality is covered by the new modules.

**Why `liquidity_engine/` instead of `services/liquidity/` for the core logic?**
`services/liquidity/` is the HTTP/Kafka wrapper  it exposes the engine over the network. The engine itself must be importable directly by `agent/nodes/observe_node.py` without a network hop. Separating the pure Python package from the service wrapper follows the same pattern as `ml/` (pure logic) vs `ml/inference/` (FastAPI wrapper).
