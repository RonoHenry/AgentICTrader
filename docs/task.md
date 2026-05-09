# AgentICTrader.AI — Development Task List
> Aligned with phase-gate roadmap. Each phase has exit criteria that must be met before the next phase begins.

---

## Phase 0 — Foundation & Edge Quantification
**Goal:** Build the data layer and quantify the existing trading edge before any ML work begins.

### 0.1 Environment & Infrastructure
- [x] Initialize project structure
- [x] Set up Docker environment (PostgreSQL, Redis)
- [x] Configure development environment
- [ ] Add TimescaleDB to Docker Compose (replace InfluxDB)
- [ ] Add Apache Kafka + Zookeeper to Docker Compose
- [ ] Configure TimescaleDB schema (candles, ticks, indicators, economic_events) — indicators table must store HTF projection levels (htf_open, htf_high, htf_low, htf_timeframe, price_vs_htf_open_bias)
- [ ] Set up Redis key schema per data models spec

### 0.2 Market Data Ingestion
- [x] Implement Deriv WebSocket API client (deriv_api.py — conflict resolved)
- [ ] Implement OANDA WebSocket connector (services/market-data/connectors/oanda.py)
- [ ] Build tick normaliser → OHLCV candle builder
- [ ] Implement Kafka producer for market.candles and market.ticks topics
- [ ] Build TimescaleDB writer for candle + tick data
- [ ] Load 3 years of historical OHLCV data (US500, US30, EURUSD, XAUUSD, GBPUSD)
- [ ] Implement economic calendar ingestion + storage

### 0.3 Feature Engineering Pipeline
> **Note:** The sole technical indicator used is the HTF Candle Projections indicator. It renders the last N candles from the auto-selected Higher TimeFrame (HTF) and projects the current HTF candle's Open, High, and Low as key price levels. HTF is auto-selected based on the current chart timeframe using the same logic as the Pine Script (e.g., M1→M5, M5→M15, M15→H1, H1→H4, H4→D1, D1→W1). Only regular OHLC candles are used (no Heikin Ashi). No other technical indicators (ATR, RSI, ADX, EMA, etc.) are used.

- [ ] Candle structure features (body size, wick %, close position, engulf detection)
- [ ] Zone & structure features (BOS, CHoCH, FVG, liquidity sweep, swing high/low distance)
- [ ] HTF Candle Projection features:
  - [ ] Implement auto-HTF timeframe selection logic (mirrors Pine Script: M1→M5, M5→M15, M15→H1, H1→H4, H4→D1, D1→W1, W1→M1, M1→M3, M3→M12)
  - [ ] Compute HTF OHLC values for the current and last N HTF candles (OHLC only, no Heikin Ashi)
  - [ ] Extract HTF Open projection level (bias anchor — price above = bullish, below = bearish)
  - [ ] Extract HTF High projection level (upper range boundary — potential rejection/breakout zone)
  - [ ] Extract HTF Low projection level (lower range boundary — potential support/bounce zone)
  - [ ] Compute price position relative to HTF Open (above/below bias)
  - [ ] Compute distance from current price to HTF High and HTF Low (range proximity %)
  - [ ] Compute HTF candle body size, wick %, and close position within range
  - [ ] Store HTF projection levels (O/H/L) per candle in TimescaleDB indicators table
- [ ] Multi-timeframe (HTF) alignment features (HTF trend bias derived from HTF candle direction, not EMA)
- [ ] Session & time features (session, day of week, news window proximity)
- [ ] Sklearn pipeline orchestration (ml/features/pipeline.py)
- [ ] Data quality validation (Great Expectations)

### 0.4 Trade Journal & Edge Analysis
- [ ] Build trade journal importer (CSV/XLSX → MongoDB trade_journal collection)
- [ ] Implement Analytics Service: win rate, R-multiple, expectancy by condition
- [ ] Build edge analysis dashboard (Streamlit, internal use)
- [ ] Document edge analysis results: best/worst conditions, session breakdown

### Phase 0 Exit Criteria
- [ ] Live market data flowing into TimescaleDB with < 2s latency
- [ ] 3+ years of clean historical data loaded and validated
- [ ] Trade journal imported and analytics dashboard live
- [ ] Feature pipeline producing validated output on live data

---

## Phase 1 — Pattern ML
**Goal:** Build, train, and validate the core ML models.

### 1.1 Data Labelling
- [ ] Build pattern labelling tool (ml/models/pattern_detector/labeller.py)
- [ ] Label minimum 500 examples per pattern from historical data
  - [ ] BOS_CONFIRMED
  - [ ] CHOCH_DETECTED
  - [ ] BEARISH_ARRAY_REJECTION
  - [ ] BULLISH_ARRAY_BOUNCE
  - [ ] FVG_PRESENT
  - [ ] LIQUIDITY_SWEEP
  - [ ] ORDER_BLOCK
  - [ ] INDUCEMENT

### 1.2 Model Training
- [ ] Set up MLflow for experiment tracking
- [ ] Train and validate Regime Classifier (XGBoost multi-class)
  - [ ] Classes: TRENDING_BULLISH, TRENDING_BEARISH, RANGING, BREAKOUT, NEWS_DRIVEN
  - [ ] Walk-forward validation (minimum 8 folds, 3-month expanding window)
  - [ ] Target: ≥ 75% accuracy on unseen data
- [ ] Train and validate Pattern Detector (XGBoost multi-label)
  - [ ] Walk-forward validation
  - [ ] Target: ≥ 80% accuracy on held-out test set
- [ ] Train and validate Confluence Scorer (weighted ensemble)
  - [ ] Logistic Regression over model outputs
  - [ ] Input features include HTF projection levels (O/H/L bias, range proximity) as primary confluence signals
  - [ ] Threshold calibration (0.65 / 0.75 / 0.85)

### 1.3 Backtesting
- [ ] Build backtesting engine (ml/backtesting/engine.py)
  - [ ] No look-ahead enforcement
  - [ ] Spread + slippage modelling
  - [ ] Dynamic position sizing (1% risk per trade)
  - [ ] Partial exit at 1R support
- [ ] Run full backtest on all models
- [ ] Report: Sharpe, Sortino, max DD, win rate, avg R, expectancy

### 1.4 ML Inference Service
- [ ] Build FastAPI inference service (ml/inference/main.py)
- [ ] Kafka integration: consume market.candles → publish setups.detected
- [ ] Deploy ML inference service to staging

### Phase 1 Exit Criteria
- [ ] Pattern detection accuracy ≥ 80% on held-out test set
- [ ] False positive rate < 20% at confidence threshold 0.75
- [ ] Backtest Sharpe Ratio ≥ 1.5 on 2-year out-of-sample period
- [ ] Backtest max drawdown ≤ 10%
- [ ] ML engine publishing detected setups to Kafka in real-time
- [ ] Walk-forward validation completed (minimum 8 folds)

---

## Phase 2 — Intelligence Layer (NLP + LLM)
**Goal:** Add sentiment analysis and LLM-generated trade reasoning.

### 2.1 Sentiment Pipeline
- [ ] Integrate news API (Benzinga / Alpha Vantage News / Reuters RSS)
- [ ] Implement FinBERT sentiment classifier per instrument
- [ ] Build sentiment signal publisher to Kafka (sentiment.signals) + Redis cache
- [ ] Implement economic calendar monitor with blackout window detection (±15 min)

### 2.2 LLM Integration
- [ ] Build LLM macro event summariser (Claude API)
- [ ] Build LLM trade reasoning generator (per setup)
- [ ] Fallback to template-based reasoning if LLM unavailable

### 2.3 Model Enhancement
- [ ] Integrate sentiment as additional feature in Confluence Scorer
- [ ] Retrain all models with sentiment features
- [ ] Validate improvement (Sharpe improvement ≥ 0.1)

### Phase 2 Exit Criteria
- [ ] Sentiment updates for all instruments within 5 minutes of news publication
- [ ] Sentiment feature improves backtest metrics
- [ ] LLM reasoning output passes quality review (10 examples reviewed by trader)
- [ ] Calendar blackout windows correctly blocking setups during high-impact events
- [ ] Full pipeline (candle → setup → sentiment → reasoning) end-to-end in staging

---

## Phase 3 — Agent V1 (Human-in-the-Loop)
**Goal:** Deploy agent in notification-only mode. Real setups, real push alerts, paper trading.

### 3.1 Risk Engine Service
- [ ] Position sizer (1% risk per trade, dynamic sizing by SL distance)
- [ ] Daily drawdown monitor (hard limit: 3%)
- [ ] Weekly drawdown monitor (hard limit: 6%)
- [ ] Correlation exposure tracker
- [ ] News blackout window guard
- [ ] FastAPI /validate, /exposure, /status endpoints

### 3.2 LangGraph Agent
- [ ] Define AgentState (typed Pydantic model per agent design spec)
- [ ] Implement observe_node (Kafka consumer, setup validation, staleness check)
- [ ] Implement analyse_node (sentiment enrichment, calendar check, final confidence)
- [ ] Implement decide_node (confidence gate, risk engine call, LLM reasoning)
- [ ] Implement notify_node (push notification formatting + dispatch)
- [ ] Implement execute_node (broker order placement — paper trading initially)
- [ ] Implement review_node (trade monitoring, partial exit at 1R, SL to BE)
- [ ] Implement learn_node (outcome logging, retraining queue)
- [ ] Build graph routing logic (edges.py)
- [ ] Kill switch implementation (Kafka agent.kill_switch topic + /agent/pause endpoint)

### 3.3 Notification Service
- [ ] FCM push notification integration
- [ ] Email notification channel
- [ ] Alert formatter (instrument, direction, score, entry/SL/TP, R-ratio, reasoning, HTF O/H/L levels, price bias vs HTF open)

### 3.4 User / Auth Service
- [ ] JWT-based authentication
- [ ] RBAC: Admin, Trader, Viewer roles
- [ ] User risk config (per-user thresholds, instruments, agent mode)
- [ ] Broker API key management (encrypted)

### 3.5 Web Dashboard (Phase 3 MVP)
- [ ] Next.js project setup (App Router, TypeScript, Tailwind, shadcn/ui)
- [ ] Live setups feed page
- [ ] Setup detail panel (patterns, scores, reasoning, trade plan)
- [ ] Agent decision log viewer
- [ ] Agent status + pause/resume controls

### 3.6 Shadow Period
- [ ] Connect agent to paper trading account (OANDA practice)
- [ ] Run 4-week live shadow period: agent alerts, trader validates
- [ ] Performance comparison: agent setups vs manual trader decisions

### Phase 3 Exit Criteria
- [ ] Agent correctly identifies ≥ 80% of setups trader would have taken
- [ ] Alert delivery latency < 3 seconds from candle close
- [ ] Risk engine correctly blocking trades outside configured limits
- [ ] Dashboard displaying live setups, scores, and reasoning
- [ ] Zero agent crashes during 4-week shadow period
- [ ] Paper trading P&L positive over shadow period

---

## Phase 4 — Autonomous Execution
**Goal:** Enable the agent to execute trades autonomously with strict risk controls.

### 4.1 Broker Execution
- [ ] Implement broker_tools.py (place order, set SL/TP, close position, get status)
- [ ] Live execute_node integration with full risk gate
- [ ] review_node: partial exits, trailing SL management
- [ ] learn_node: retraining queue integration
- [ ] Feature toggle: HUMAN_IN_LOOP / AUTONOMOUS per user

### 4.2 Live Validation
- [ ] 30-day live autonomous run on minimum capital (10% of account)
- [ ] Monitor and adjust confidence thresholds based on live results
- [ ] Full decision + execution audit trail for all trades
- [ ] Rollback mechanism tested and confirmed working

### Phase 4 Exit Criteria
- [ ] 30-day live run: positive P&L, drawdown ≤ 5%
- [ ] Zero cases of risk engine bypass
- [ ] Autonomous performance within ±10% of Phase 3 paper trading metrics
- [ ] Full audit trail for all trades

---

## Phase 5 — Platform
**Goal:** Build AgentICTrader.AI as a multi-user platform product.

- [ ] Full web dashboard rebuild (all analytics pages, backtesting visualiser)
- [ ] React Native mobile app (iOS + Android push notifications)
- [ ] Multi-user support with RBAC
- [ ] User onboarding flow (connect broker, set risk config, import journal)
- [ ] Subscription billing integration (Stripe)
- [ ] Security audit
- [ ] Public beta launch

---

## Immediate Next Steps (This Week)
1. [ ] Resolve TimescaleDB migration — add to Docker Compose, create schema
2. [ ] Add Kafka to Docker Compose
3. [ ] Build OANDA connector (market-data service)
4. [ ] Start feature engineering pipeline
