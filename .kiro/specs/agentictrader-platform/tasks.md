# AgentICTrader.AI — Executable Task List

> Tasks are sequenced by phase gate. Each phase must pass its exit criteria before the next begins.
> Infrastructure (TimescaleDB, Kafka, MongoDB, Redis, MLflow) is already running in docker-compose.yml.
> The indicators table schema still has legacy ATR/RSI/ADX/EMA columns — Task 1.3 replaces them.

> **TDD Rule:** Every task follows RED → GREEN → REFACTOR. No production code is written without a failing test first.
> Sub-tasks are ordered: (a) write tests → confirm RED, (b) implement → confirm GREEN, (c) refactor → confirm still GREEN.

---

## Phase 0 — Foundation & Edge Quantification

- [x] 1. Update TimescaleDB indicators schema to replace legacy ATR/RSI/ADX/EMA columns with HTF Candle Projection columns
  - Drop columns: atr_14, atr_pct, rsi_14, adx_14, ema_50, ema_200, volume_sma_20, volume_delta
  - Add columns: htf_timeframe VARCHAR(5), htf_open NUMERIC(18,5), htf_high NUMERIC(18,5), htf_low NUMERIC(18,5), htf_open_bias VARCHAR(10) CHECK (htf_open_bias IN ('BULLISH','BEARISH','NEUTRAL')), htf_high_proximity_pct NUMERIC(8,4), htf_low_proximity_pct NUMERIC(8,4), htf_body_pct NUMERIC(8,4), htf_upper_wick_pct NUMERIC(8,4), htf_lower_wick_pct NUMERIC(8,4), htf_close_position NUMERIC(8,4)
  - Retain columns: time, instrument, timeframe, session, day_of_week, is_news_window
  - Update docker/init/timescaledb/001_schema.sql with the new column definitions
  - Write a migration script at backend/trader/infrastructure/migrations/001_htf_indicators.sql
  - Verify the schema applies cleanly with `docker compose exec timescaledb psql`

- [x] 2. Set up Redis key schema for market data caching
  - Define key patterns in backend/trader/infrastructure/redis_schema.py:
    - `candle:{instrument}:{timeframe}` → latest OHLCV (TTL 65s)
    - `htf:{instrument}:{timeframe}` → latest HTF projection levels (TTL 300s)
    - `sentiment:{instrument}` → latest FinBERT score (TTL 900s)
    - `agent:state:{user_id}` → agent state snapshot (TTL 3600s)
    - `risk:exposure:{user_id}` → risk exposure snapshot (TTL 60s)
  - Implement RedisCache class with typed get/set/delete methods using redis-py async
  - Write unit tests in backend/tests/test_redis_schema.py covering all key patterns and TTL enforcement

- [x] 3. Implement Brocker WebSocket connector
  - **3a. RED — Write failing tests** (`backend/tests/test_oanda_connector.py`)
    - Test: all 12 supported instruments present in SUPPORTED_INSTRUMENTS constant
    - Test: TickEvent schema has fields {instrument, bid, ask, time_utc, source} with source defaulting to "oanda"
    - Test: PRICE message is parsed and emits a TickEvent with correct values
    - Test: multiple PRICE messages emit multiple TickEvents
    - Test: Authorization header is sent with Bearer token on connect
    - Test: HEARTBEAT message does not emit a TickEvent
    - Test: HEARTBEAT between PRICE messages does not affect tick count
    - Test: connector reconnects after ConnectionClosed
    - Test: connector reconnects after OSError
    - Test: backoff delay sequence is 1s, 2s, 4s, 8s, 16s
    - Test: backoff is capped at 30s
    - Test: asyncio.sleep is called with correct backoff delays on retry
    - Test: OANDAConnectorError raised after max_retries (5) exhausted
    - Test: exactly 6 connection attempts made (1 initial + 5 retries) before error
    - Confirm all tests FAIL (RED) before writing any implementation
  - **3b. GREEN — Write minimal implementation**
    - Create `services/market-data/connectors/base.py`: BaseConnector ABC, TickEvent, ConnectorError, TickCallback
    - Create `services/market-data/connectors/oanda.py`: OANDAConnector implementing BaseConnector
    - Connect to OANDA v20 streaming API (wss://stream-fxtrade.oanda.com/v3/accounts/{id}/pricing/stream)
    - Support instruments: XAUUSD, EURUSD, GBPUSD, EURAUD, GBPAUD, USDJPY, US100, US30, US500, GER40, BTCUSD, ETHUSD
    - Emit normalised tick events: {instrument, bid, ask, time_utc, source="oanda"}
    - Handle reconnection with exponential backoff (max 5 retries, 30s cap)
    - Confirm all tests PASS (GREEN)
  - **3c. REFACTOR**
    - Update `services/market-data/connectors/__init__.py` to export public API
    - Ensure tests remain GREEN after refactor

- [x] 4. Build tick normaliser and OHLCV candle builder
  - **4a. RED — Write failing tests** (`backend/tests/test_candle_builder.py`)
    - Property: high >= open, high >= close, high >= low for all candles
    - Property: low <= open, low <= close, low <= high for all candles
    - Property: candle time is always aligned to timeframe boundary (M1, M5, M15, H1, H4, D1, W1)
    - Test: complete=True emitted exactly on timeframe boundary close
    - Test: complete=False emitted on intra-candle tick updates
    - Test: UTC timestamps used throughout
    - Confirm all tests FAIL (RED)
  - **4b. GREEN — Write minimal implementation**
    - Create `services/market-data/normaliser.py`
    - Consume raw ticks and aggregate into OHLCV candles for timeframes: M1, M5, M15, H1, H4, D1, W1
    - Confirm all tests PASS (GREEN)
  - **4c. REFACTOR** — clean up, confirm GREEN

- [x] 5. Implement Kafka producer for market data topics
  - **5a. RED — Write failing tests** (`backend/tests/test_kafka_producer.py`)
    - Integration test: ticks published to market.ticks topic with key=instrument
    - Integration test: completed candles published to market.candles with key=instrument:timeframe
    - Test: JSON schema matches {instrument, timeframe, time, open, high, low, close, volume, complete, source}
    - Test: producer health check returns healthy state
    - Test: graceful shutdown flushes pending messages
    - Confirm all tests FAIL (RED)
  - **5b. GREEN — Write minimal implementation**
    - Create `services/market-data/kafka_producer.py` using aiokafka
    - Confirm all tests PASS (GREEN)
  - **5c. REFACTOR** — clean up, confirm GREEN

- [x] 6. Build TimescaleDB writer for candle and tick data
  - **6a. RED — Write failing tests** (`backend/tests/test_timescaledb_writer.py`)
    - Integration test: candle upsert uses ON CONFLICT (time, instrument, timeframe) DO UPDATE
    - Integration test: ticks inserted in batches of 500
    - Integration test: batch flushed within 1s max interval
    - Integration test: write latency < 2s from candle close
    - Confirm all tests FAIL (RED)
  - **6b. GREEN — Write minimal implementation**
    - Create `services/market-data/timescaledb_writer.py` using asyncpg
    - Confirm all tests PASS (GREEN)
  - **6c. REFACTOR** — clean up, confirm GREEN

- [x] 7. Load 3 years of historical OHLCV data
  - Create scripts/load_historical_data.py
  - Fetch from OANDA v20 REST API: GET /v3/instruments/{instrument}/candles
  - Load all 5 instruments: EURUSD, GBPUSD, US500, US30, XAUUSD
  - Load all timeframes: M1, M5, M15, H1, H4, D1, W1
  - Handle pagination (max 5000 candles per request)
  - Validate loaded data: no gaps > 2x timeframe duration on trading days, no OHLC violations
  - Log summary: instrument, timeframe, row count, date range, gap count

- [x] 8. Implement economic calendar ingestion
  - **8a. RED — Write failing tests** (`backend/tests/test_calendar_ingestion.py`)
    - Test: events ingested for currencies USD, EUR, GBP, XAU
    - Test: events stored in TimescaleDB economic_events table with correct schema
    - Test: daily refresh scheduled at 00:05 UTC
    - Test: duplicate events are not inserted twice
    - Confirm all tests FAIL (RED)
  - **8b. GREEN — Write minimal implementation**
    - Create `services/market-data/calendar_ingestion.py`
    - Integrate with Investing.com economic calendar API or ForexFactory RSS
    - Schedule daily refresh at 00:05 UTC via APScheduler
    - Confirm all tests PASS (GREEN)
  - **8c. REFACTOR** — clean up, confirm GREEN

- [ ] 9. Implement HTF auto-timeframe selection logic
  - **9a. RED — Write failing tests** (`backend/tests/test_htf_selector.py`)
    - Test: all single-level mappings: M1→M5, M5→M15, M15→H1, H1→H4, H4→D1, D1→W1, W1→M1, M1→M3, M3→M12
    - Test: two-level mode returns correct tuple for each input timeframe
    - Property: get_htf_timeframe always returns a timeframe strictly higher than the input
    - Test: invalid timeframe raises ValueError
    - Confirm all tests FAIL (RED)
  - **9b. GREEN — Write minimal implementation**
    - Create `ml/features/htf_selector.py`
    - Implement get_htf_timeframe(current_tf: str) -> str
    - Implement get_htf_timeframes(current_tf: str) -> tuple[str, str]
    - Confirm all tests PASS (GREEN)
  - **9c. REFACTOR** — clean up, confirm GREEN

- [ ] 10. Implement HTF OHLC computation and projection feature extractor
  - **10a. RED — Write failing tests** (`backend/tests/test_htf_projections.py`)
    - Property: htf_high_proximity_pct + htf_low_proximity_pct = 100 when price is within range
    - Property: open_bias is BULLISH iff current_price > htf_open
    - Property: all percentage values are in [0, 100] when price is within HTF range
    - Property: htf_body_pct + htf_upper_wick_pct + htf_lower_wick_pct = 100
    - Test: open_bias is NEUTRAL when current_price == htf_open
    - Test: HTFProjection dataclass has all required fields
    - Confirm all tests FAIL (RED)
  - **10b. GREEN — Write minimal implementation**
    - Create `ml/features/htf_projections.py`
    - Implement HTFProjectionExtractor with fetch_htf_candles and compute_projections
    - Confirm all tests PASS (GREEN)
  - **10c. REFACTOR** — clean up, confirm GREEN

- [ ] 11. Implement candle structure feature extractor
  - **11a. RED — Write failing tests** (`backend/tests/test_candle_features.py`)
    - Property: body_pct + upper_wick_pct + lower_wick_pct = 100 for all valid candles
    - Property: close_position is always in [0, 1]
    - Test: is_bullish is True iff close > open
    - Test: is_engulfing returns True when body fully engulfs previous candle body
    - Test: is_engulfing returns False when body does not engulf
    - Test: CandleFeatures dataclass has all required fields
    - Confirm all tests FAIL (RED)
  - **11b. GREEN — Write minimal implementation**
    - Create `ml/features/candle_features.py`
    - Implement CandleFeatureExtractor.extract(ohlcv: dict) → CandleFeatures
    - Confirm all tests PASS (GREEN)
  - **11c. REFACTOR** — clean up, confirm GREEN

- [ ] 12. Implement zone and structure feature extractor
  - **12a. RED — Write failing tests** (`backend/tests/test_zone_features.py`)
    - Test: BOS detected when close breaks beyond last swing high/low (known candle sequence)
    - Test: CHoCH detected when BOS occurs in opposite direction
    - Test: FVG detected when gap exists between candle[i-2].high and candle[i].low
    - Test: liquidity_sweep detected when wick exceeds swing high/low but close is back inside
    - Test: swing_high_distance and swing_low_distance computed correctly
    - Test: htf_trend_bias derived from HTF candle direction, not EMA
    - Test: ZoneFeatures dataclass has all required fields
    - Confirm all tests FAIL (RED)
  - **12b. GREEN — Write minimal implementation**
    - Create `ml/features/zone_features.py`
    - Migrate logic from backend/trader/agents/power_of_3.py and backend/trader/analysis/pdarray.py
    - Implement ZoneFeatureExtractor.extract(candles: list[dict]) → ZoneFeatures
    - Confirm all tests PASS (GREEN)
  - **12c. REFACTOR** — clean up, confirm GREEN

- [ ] 13. Implement session and time feature extractor
  - **13a. RED — Write failing tests** (`backend/tests/test_session_features.py`)
    - Test: all time window boundaries with exact timestamps (ASIAN_RANGE, TRUE_DAY_OPEN, LONDON_KILLZONE, etc.)
    - Test: DST transitions — NY switches between UTC-4 and UTC-5
    - Test: narrative_phase derivation for all time_window values
    - Test: time_window_weight values for all windows match spec
    - Property: time_window_weight is always in [0.0, 1.0]
    - Property: is_killzone is True iff time_window in {LONDON_KILLZONE, NY_KILLZONE}
    - Property: is_high_probability_window is True iff time_window_weight >= 0.7
    - Test: price_vs_daily_open, price_vs_weekly_open, price_vs_true_day_open return ABOVE/BELOW/AT correctly
    - Test: get_narrative_context returns a non-empty string answering all 3 questions
    - Confirm all tests FAIL (RED)
  - **13b. GREEN — Write minimal implementation**
    - Create `ml/features/session_features.py`
    - Implement TimeWindowClassifier.classify(timestamp_utc, instrument) → TimeFeatures
    - Implement get_narrative_context(time_features, htf_features, zone_features) → str
    - Update TimescaleDB indicators schema to add time window columns
    - Confirm all tests PASS (GREEN)
  - **13c. REFACTOR** — clean up, confirm GREEN

- [ ] 14. Build sklearn feature pipeline orchestration
  - Create ml/features/pipeline.py
  - Compose HTFProjectionExtractor + CandleFeatureExtractor + ZoneFeatureExtractor + SessionFeatureExtractor into a single sklearn Pipeline
  - Output: flat feature vector as pandas DataFrame with named columns
  - Implement fit_transform and transform methods
  - Add Great Expectations data quality suite: validate no nulls in HTF projection columns, all pct values in [0,100], open_bias in valid enum set
  - Write integration tests in backend/tests/test_feature_pipeline.py using 100 real candles from TimescaleDB

- [ ] 15. Build trade journal importer
  - **15a. RED — Write failing tests** (`backend/tests/test_journal_importer.py`)
    - Test: CSV file imported and mapped to trade_journal schema correctly
    - Test: XLSX file imported and mapped correctly
    - Test: missing entry/exit prices raises ValidationError
    - Test: invalid direction (not BUY/SELL) raises ValidationError
    - Test: r_multiple computed when missing
    - Test: valid records inserted into MongoDB trade_journal collection
    - Confirm all tests FAIL (RED)
  - **15b. GREEN — Write minimal implementation**
    - Create `services/analytics/journal_importer.py`
    - Confirm all tests PASS (GREEN)
  - **15c. REFACTOR** — clean up, confirm GREEN

- [ ] 16. Implement Analytics Service for edge analysis
  - **16a. RED — Write failing tests** (`backend/tests/test_edge_analysis.py`)
    - Test: win_rate, avg_r_multiple, expectancy, trade_count computed correctly from known data
    - Test: grouping by session, day_of_week, instrument, setup_tag, htf_open_bias works
    - Test: GET /analytics/summary returns correct shape
    - Test: GET /analytics/edge returns grouped metrics
    - Test: GET /analytics/equity-curve returns time-ordered data points
    - Confirm all tests FAIL (RED)
  - **16b. GREEN — Write minimal implementation**
    - Create `services/analytics/edge_analysis.py`
    - Expose FastAPI endpoints: GET /analytics/summary, GET /analytics/edge, GET /analytics/equity-curve
    - Confirm all tests PASS (GREEN)
  - **16c. REFACTOR** — clean up, confirm GREEN

- [ ] 17. Build edge analysis Streamlit dashboard
  - Create services/analytics/dashboard.py using Streamlit
  - Pages: Win Rate by Condition, R-Multiple Distribution, Equity Curve, Session Breakdown, HTF Bias Performance
  - Connect to Analytics Service REST endpoints
  - Run on port 8501

---

## Phase 1 — Pattern ML

- [ ] 18. Build pattern labelling tool
  - Create ml/models/pattern_detector/labeller.py
  - Load historical candles from TimescaleDB
  - Present candle sequences in a Streamlit UI for manual labelling
  - Labels: BOS_CONFIRMED, CHOCH_DETECTED, SUPPLY_ZONE_REJECTION, DEMAND_ZONE_BOUNCE, FVG_PRESENT, LIQUIDITY_SWEEP, ORDER_BLOCK, INDUCEMENT
  - Save labelled examples to MongoDB setups collection with label, candle_window, instrument, timeframe, timestamp
  - Target: minimum 500 labelled examples per pattern

- [ ] 19. Set up MLflow experiment tracking
  - **19a. RED — Write failing tests** (`backend/tests/test_mlflow_client.py`)
    - Smoke test: MLflow connection succeeds
    - Test: experiment created with correct name
    - Test: log_params, log_metrics, log_model, register_model functions work
    - Confirm all tests FAIL (RED)
  - **19b. GREEN — Write minimal implementation**
    - Create `ml/tracking/mlflow_client.py`
    - Define experiment names: "regime-classifier", "pattern-detector", "confluence-scorer"
    - Confirm all tests PASS (GREEN)
  - **19c. REFACTOR** — clean up, confirm GREEN

- [ ] 20. Train and validate Regime Classifier
  - Create ml/models/regime_classifier/train.py
  - Features: HTF projection features + candle structure + zone features + session features
  - Target classes: TRENDING_BULLISH, TRENDING_BEARISH, RANGING, BREAKOUT, NEWS_DRIVEN
  - Model: XGBoost multi-class classifier
  - Walk-forward validation: minimum 8 folds, 3-month expanding window
  - Log all experiments to MLflow
  - Exit criterion: ≥ 75% accuracy on unseen data across all folds
  - Save best model to MLflow model registry as "regime-classifier"

- [ ] 21. Train and validate Pattern Detector
  - Create ml/models/pattern_detector/train.py
  - Features: same feature vector as Regime Classifier
  - Target: multi-label classification (one binary output per pattern)
  - Model: XGBoost multi-label (one classifier per label, wrapped in MultiOutputClassifier)
  - Walk-forward validation: minimum 8 folds
  - Log all experiments to MLflow
  - Exit criterion: ≥ 80% accuracy on held-out test set, false positive rate < 20% at threshold 0.75
  - Save best model to MLflow model registry as "pattern-detector"

- [ ] 22. Train and validate Confluence Scorer
  - Create ml/models/confluence_scorer/train.py
  - Inputs: Regime Classifier output + Pattern Detector outputs + HTF projection levels (open_bias, htf_high_proximity_pct, htf_low_proximity_pct) + time window weight + narrative_phase + price_vs_daily_open + price_vs_true_day_open as primary signals
  - Model: Logistic Regression ensemble over model outputs
  - Calibrate thresholds: 0.65 (hard floor), 0.75 (notify), 0.85 (auto-execute)
  - Note: setups during LONDON_KILLZONE or NY_KILLZONE (time_window_weight=1.0) should score significantly higher than identical setups during OFF_HOURS (weight=0.1)
  - Log calibration curves to MLflow
  - Save best model to MLflow model registry as "confluence-scorer"

- [ ] 23. Build backtesting engine
  - **23a. RED — Write failing tests** (`backend/tests/test_backtesting_engine.py`)
    - Property: no trade uses future data (look-ahead check via timestamp ordering)
    - Property: position size never exceeds 1% risk given any SL distance
    - Test: confidence < 0.65 discards setup (no trade simulated)
    - Test: confidence 0.65–0.74 logs only (no trade simulated)
    - Test: confidence ≥ 0.75 simulates trade
    - Test: Sharpe, Sortino, max drawdown, win rate, avg R-multiple, expectancy all returned
    - Confirm all tests FAIL (RED)
  - **23b. GREEN — Write minimal implementation**
    - Create `ml/backtesting/engine.py`
    - Replay historical candles in strict time order (no look-ahead)
    - Apply confidence threshold gates and trade simulation
    - Confirm all tests PASS (GREEN)
  - **23c. REFACTOR** — clean up, confirm GREEN

- [ ] 24. Build ML inference FastAPI service
  - Create ml/inference/main.py using FastAPI
  - Load models from MLflow registry: regime-classifier, pattern-detector, confluence-scorer
  - Expose POST /predict endpoint: accepts {instrument, timeframe, candles: list[OHLCV]} → returns {regime, patterns, confidence_score, htf_projections}
  - Implement Kafka consumer: consume market.candles → run inference → publish to setups.detected
  - setups.detected message schema: {instrument, timeframe, time, regime, patterns, confidence_score, htf_open, htf_high, htf_low, open_bias, entry_price, sl_price, tp_price}
  - Write integration tests in backend/tests/test_inference_service.py

---

## Phase 2 — Intelligence Layer

- [ ] 25. Integrate news API and implement FinBERT sentiment classifier
  - Create services/nlp/sentiment_pipeline.py
  - Integrate news API (Alpha Vantage News or Reuters RSS)
  - Run FinBERT (ProsusAI/finbert from HuggingFace) on each article headline + summary
  - Compute per-instrument directional sentiment score: -1.0 (bearish) to +1.0 (bullish)
  - Publish to Kafka topic sentiment.signals: {instrument, score, direction, freshness_seconds, source}
  - Cache latest score in Redis: key sentiment:{instrument}, TTL 900s
  - Write unit tests in backend/tests/test_sentiment_pipeline.py

- [ ] 26. Implement economic calendar blackout monitor
  - Create services/nlp/calendar_monitor.py
  - Poll TimescaleDB economic_events every 60s
  - Detect HIGH impact events within ±15 min window for each instrument's currency
  - Publish blackout state to Redis: key blackout:{instrument} → {active: bool, event_name, minutes_remaining}
  - Write unit tests in backend/tests/test_calendar_monitor.py

- [ ] 27. Build LLM macro event summariser and trade reasoning generator
  - Create services/nlp/llm_service.py
  - Implement summarise_macro_event(event: dict) → str using Claude API (anthropic SDK)
  - Implement generate_trade_reasoning(setup: dict) → str structured around the 3-question narrative framework:
    1. "Where has price come from?" — HTF context, previous session range, PD arrays swept/respected
    2. "Where is it now?" — current time window (e.g. London Killzone = manipulation phase), price vs daily/weekly/true day open, narrative_phase
    3. "Where is it likely to go?" — nearest liquidity pool (swing high/low) or imbalance (FVG/IFVG) to rebalance
    - Entry logic in reasoning: if bullish, note price is below session open (manipulation wick down expected before expansion up); if bearish, note price is above session open
    - Example output: "Price swept the Asian range low at 03:15 NY (London Killzone — manipulation phase). HTF open bias is bullish. Price is below the True Day Open with a bullish FVG at discount. Expecting expansion higher into the NY Killzone (07:00–10:00 NY) toward HTF high at {price}."
  - Fallback to template-based reasoning using get_narrative_context() if Claude API unavailable
  - Write unit tests in backend/tests/test_llm_service.py with mocked Claude responses

- [ ] 28. Integrate sentiment into Confluence Scorer and retrain
  - Update ml/features/pipeline.py to include sentiment score and blackout flag as features
  - Retrain Confluence Scorer (Task 22) with sentiment features added
  - Validate: Sharpe improvement ≥ 0.1 vs baseline from Task 22
  - Log comparison experiment to MLflow
  - Promote new model to MLflow registry if improvement validated

---

## Phase 3 — Agent V1 (Human-in-the-Loop)

- [ ] 29. Build Risk Engine FastAPI service
  - **29a. RED — Write failing tests** (`backend/tests/test_risk_engine.py`)
    - Property: position_size * sl_distance_pips always equals exactly 1% of equity
    - Property: /validate always returns approved=False when daily_dd >= 3%
    - Test: /validate rejects when weekly_dd >= 6%
    - Test: /validate rejects when concurrent trades >= 3
    - Test: /validate rejects when news blackout is active
    - Test: /validate rejects when confidence < 0.65
    - Test: /validate approves when all checks pass
    - Test: /exposure returns correct shape {daily_dd_pct, weekly_dd_pct, open_trades, equity}
    - Test: /status returns {healthy, kill_switch_active}
    - Confirm all tests FAIL (RED)
  - **29b. GREEN — Write minimal implementation**
    - Create `services/risk-engine/main.py` using FastAPI
    - Implement POST /validate, GET /exposure, GET /status
    - Maintain equity curve and exposure state in Redis
    - Confirm all tests PASS (GREEN)
  - **29c. REFACTOR** — clean up, confirm GREEN

- [ ] 30. Define AgentState Pydantic model
  - **30a. RED — Write failing tests** (`backend/tests/test_agent_state.py`)
    - Test: AgentState instantiates with all required fields
    - Test: Optional fields default to None
    - Test: mode field only accepts "HUMAN_IN_LOOP" or "AUTONOMOUS"
    - Test: all time window fields present and typed correctly
    - Confirm all tests FAIL (RED)
  - **30b. GREEN — Write minimal implementation**
    - Create `agent/state.py` with AgentState Pydantic v2 model
    - Confirm all tests PASS (GREEN)
  - **30c. REFACTOR** — clean up, confirm GREEN

- [ ] 31. Implement LangGraph agent nodes
  - **31a. RED — Write failing tests** (`backend/tests/test_agent_nodes.py`)
    - Test: observe_node rejects stale setups (> 60s old)
    - Test: observe_node populates AgentState from Kafka message
    - Test: analyse_node fetches sentiment from Redis and adjusts confidence
    - Test: analyse_node sets blackout_active from Redis blackout key
    - Test: decide_node rejects when confidence < 0.65
    - Test: decide_node calls Risk Engine /validate synchronously
    - Test: decide_node routes to notify_node in HUMAN_IN_LOOP mode
    - Test: decide_node routes to execute_node in AUTONOMOUS mode
    - Test: notify_node formats alert with all required fields and dispatches via FCM
    - Test: execute_node performs pre-execution risk recheck before placing order
    - Test: review_node triggers partial exit at 1R
    - Test: learn_node logs outcome to MongoDB trade_journal
    - Confirm all tests FAIL (RED)
  - **31b. GREEN — Write minimal implementation**
    - Create agent/nodes/observe_node.py, analyse_node.py, decide_node.py, notify_node.py, execute_node.py, review_node.py, learn_node.py
    - Confirm all tests PASS (GREEN)
  - **31c. REFACTOR** — clean up, confirm GREEN

- [ ] 32. Build LangGraph agent graph and kill switch
  - **32a. RED — Write failing tests** (`backend/tests/test_agent_graph.py`)
    - Integration test: full graph runs observe → analyse → decide → notify in HUMAN_IN_LOOP mode
    - Integration test: full graph runs observe → analyse → decide → execute in AUTONOMOUS mode
    - Test: kill switch message sets kill_switch_active=True in Redis
    - Test: all nodes check kill_switch_active and halt when True
    - Test: POST /agent/pause sets kill switch
    - Test: POST /agent/resume clears kill switch
    - Confirm all tests FAIL (RED)
  - **32b. GREEN — Write minimal implementation**
    - Create `agent/graph.py` and `agent/edges.py`
    - Wire all nodes with LangGraph StateGraph
    - Implement kill switch via Kafka topic agent.kill_switch
    - Confirm all tests PASS (GREEN)
  - **32c. REFACTOR** — clean up, confirm GREEN

- [ ] 33. Build Notification Service
  - **33a. RED — Write failing tests** (`backend/tests/test_notification_service.py`)
    - Test: send_setup_alert dispatches FCM message with all required payload fields
    - Test: alert payload includes instrument, direction, confidence_score, entry_price, sl_price, tp_price, r_ratio, reasoning, htf_open, htf_high, htf_low, open_bias, time_window, narrative_phase, price_vs_daily_open, price_vs_true_day_open, is_killzone
    - Test: email fallback triggered when FCM fails
    - Test: send_setup_alert returns True on success, False on failure
    - Confirm all tests FAIL (RED)
  - **33b. GREEN — Write minimal implementation**
    - Create `services/notifications/fcm_service.py` using firebase-admin SDK
    - Implement email fallback using smtplib
    - Confirm all tests PASS (GREEN)
  - **33c. REFACTOR** — clean up, confirm GREEN

- [ ] 34. Build User and Auth Service
  - **34a. RED — Write failing tests** (`backend/tests/test_auth_service.py`)
    - Test: POST /auth/register creates user and returns JWT
    - Test: POST /auth/login returns access token (15min TTL) and refresh token (7-day TTL)
    - Test: POST /auth/refresh returns new access token
    - Test: Admin role has full access, Trader has own data + agent control, Viewer is read-only
    - Test: broker API keys are encrypted before storing in MongoDB
    - Test: invalid credentials return 401
    - Confirm all tests FAIL (RED)
  - **34b. GREEN — Write minimal implementation**
    - Create `services/auth/main.py` using FastAPI
    - Implement JWT auth, RBAC, and encrypted broker key storage
    - Confirm all tests PASS (GREEN)
  - **34c. REFACTOR** — clean up, confirm GREEN

- [ ] 35. Build Next.js web dashboard
  - Create frontend/ directory with Next.js 15 App Router, TypeScript, Tailwind CSS, shadcn/ui
  - Pages:
    - /dashboard: live setups feed (WebSocket, real-time updates)
    - /setups/[id]: setup detail panel (patterns, HTF levels, confidence score, reasoning, trade plan)
    - /agent: agent status, pause/resume controls, decision log viewer
    - /journal: trade journal table with import button
    - /analytics: win rate by condition, R-distribution, equity curve, HTF bias performance
  - Connect to backend via REST + WebSocket (Socket.io-client)
  - Write component tests using Vitest + React Testing Library

- [ ] 36. Shadow period setup and validation
  - Connect agent to OANDA practice account (paper trading)
  - Set agent mode to HUMAN_IN_LOOP for all users
  - Run 4-week shadow period: agent fires alerts, trader validates each setup manually
  - Log trader feedback (taken/skipped/modified) against each agent alert in MongoDB
  - Generate weekly comparison report: agent setups vs trader decisions, match rate, P&L
  - Exit criterion: agent correctly identifies ≥ 80% of setups trader would have taken

---

## Phase 4 — Autonomous Execution

- [ ] 37. Implement broker execution tools
  - **37a. RED — Write failing tests** (`backend/tests/test_broker_tools.py`)
    - Test: place_order returns order_id on success (mocked OANDA response)
    - Test: set_sl_tp returns True on success
    - Test: close_position returns True on success
    - Test: get_position_status returns {status, unrealised_pnl, current_price}
    - Test: place_order raises BrokerError on API failure
    - Confirm all tests FAIL (RED)
  - **37b. GREEN — Write minimal implementation**
    - Create `agent/broker_tools.py` with OANDA v20 REST API support
    - Confirm all tests PASS (GREEN)
  - **37c. REFACTOR** — clean up, confirm GREEN

- [ ] 38. Enable autonomous execution mode
  - **38a. RED — Write failing tests** (`backend/tests/test_autonomous_execution.py`)
    - Integration test: execute_node places live order via broker_tools
    - Test: pre-execution risk recheck called before order placement
    - Test: HUMAN_IN_LOOP / AUTONOMOUS toggle respected per user
    - Test: partial exit at 1R triggered by review_node
    - Test: retraining queue triggered in MLflow when 50 new outcomes logged
    - Confirm all tests FAIL (RED)
  - **38b. GREEN — Write minimal implementation**
    - Update execute_node.py, review_node.py, learn_node.py for autonomous mode
    - Implement feature toggle in User Service
    - Confirm all tests PASS (GREEN)
  - **38c. REFACTOR** — clean up, confirm GREEN

- [ ] 39. Live validation run and audit trail
  - Deploy to staging with 10% of account capital
  - Run 30-day live autonomous period
  - Full audit trail: every decision logged to MongoDB agent_decisions with input context, risk validation result, reasoning, order details
  - Monitor: daily P&L, drawdown, confidence threshold performance
  - Rollback mechanism: POST /agent/pause immediately halts all new trades; existing positions managed to close
  - Exit criterion: positive P&L, drawdown ≤ 5%, zero risk engine bypasses

---

## Phase 5 — Platform

- [ ] 40. Full web dashboard rebuild with analytics and backtesting visualiser
  - Extend frontend/ with: full analytics pages, backtesting visualiser with trade replay, performance comparison charts
  - Add backtesting visualiser: replay detected setups on historical chart with entry/exit markers

- [ ] 41. React Native mobile app
  - Create mobile/ directory with React Native 0.76+, TypeScript, Expo
  - iOS and Android push notifications via FCM
  - Screens: live setups feed, setup detail, agent status, trade journal

- [ ] 42. Multi-user support and onboarding flow
  - User onboarding: connect broker API, set risk config, import trade journal
  - Multi-user RBAC fully enforced across all services
  - Subscription billing integration via Stripe (plans: Free, Pro, Enterprise)

- [ ] 43. Security audit and public beta launch
  - Third-party security audit of auth, broker key storage, and agent execution paths
  - Penetration testing on all public API endpoints
  - Fix all critical and high findings before launch
  - Public beta launch with monitoring dashboards live (Grafana, PagerDuty)
