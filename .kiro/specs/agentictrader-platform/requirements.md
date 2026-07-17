# Requirements Document

## Introduction

AgentICTrader.AI is an autonomous intelligent trading platform that encodes professional Price Action expertise into a scalable AI system. It combines real-time market data engineering, ML pattern recognition, NLP sentiment analysis, and an agentic execution loop to identify, score, and act on high-probability trade setups.

## Glossary

- **System**: The AgentICTrader Platform
- **HTF**: Higher Time Frame (H1, H4, D1, W1 relative to entry timeframe)
- **ICT**: Inner Circle Trader methodology
- **BOS**: Break of Structure (trend continuation signal)
- **CHoCH**: Change of Character (first sign of trend reversal)
- **FVG**: Fair Value Gap (price imbalance zone)
- **PD Array**: Price Delivery Array (Order Block, FVG, Breaker, IFVG)
- **Dealing_Range**: The range defined by HTF High and HTF Low
- **Premium**: Upper 50% of Dealing Range (where bearish PD arrays form)
- **Discount**: Lower 50% of Dealing Range (where bullish PD arrays form)
- **Killzone**: High-probability time window for trade execution (London, NY AM, NY PM)
- **Silver_Bullet**: Highest probability subset window within a Killzone
- **True_Day_Open**: Price at NY midnight (00:00 NY time)
- **Liquidity_Sweep**: False breakout above swing high or below swing low before true directional move
- **Order_Block**: Last opposing candle before strong directional move
- **Inducement**: Liquidity formation designed to trap traders before true move
- **Risk_Engine**: Synchronous service that validates trade requests against risk rules
- **Agent**: The LangGraph-based autonomous trading loop
- **Confluence_Scorer**: ML model that assigns confidence scores to detected setups
- **RAG**: Retrieval-Augmented Generation system for historical setup similarity

## Requirements

### Requirement 1: Market Data Ingestion

**User Story:** As a trading system, I want to ingest and store multi-timeframe market data, so that I can analyze price action across all relevant timeframes.

#### Acceptance Criteria

1. THE System SHALL ingest real-time multi-timeframe OHLCV data (M1, M5, M15, H1, H4, D1, W1)
2. THE System SHALL support Forex majors (EURUSD, GBPUSD), US Indices (US500, US30), and Gold (XAUUSD)
3. THE System SHALL normalise tick data into OHLCV candles and publish to Kafka topics
4. THE System SHALL write candle and tick data to TimescaleDB
5. THE System SHALL ingest economic calendar events and flag high-impact windows
6. THE System SHALL load a minimum of 3 years of historical OHLCV data per instrument

### Requirement 2: HTF Candle Projection Feature Engineering

**User Story:** As a trading system, I want to compute Higher Timeframe candle projection levels, so that I can establish price bias and dealing range boundaries for every setup.

#### Acceptance Criteria

1. THE System SHALL implement auto-HTF timeframe selection: M1→M5, M5→M15, M15→H1, H1→H4, H4→D1, D1→W1, W1→M1, M1→M3, M3→M12
2. THE System SHALL compute HTF OHLC values for the current and last N HTF candles (regular OHLC only, no Heikin Ashi)
3. THE System SHALL extract the HTF Open as a bias anchor (price above = bullish, price below = bearish)
4. THE System SHALL extract the HTF High as an upper range boundary (potential rejection/breakout zone)
5. THE System SHALL extract the HTF Low as a lower range boundary (potential support/bounce zone)
6. THE System SHALL compute price position relative to HTF Open (above/below bias flag)
7. THE System SHALL compute distance from current price to HTF High and HTF Low as range proximity percentages
8. THE System SHALL compute HTF candle body size, wick percentages, and close position within range
9. THE System SHALL store all HTF projection levels per candle in the TimescaleDB indicators table
10. THE System SHALL use HTF Candle Projections as the SOLE technical indicator — no ATR, RSI, ADX, EMA, or volume indicators

### Requirement 3: Candle and Zone Structure Features

**User Story:** As a trading system, I want to compute candle and market structure features, so that I can detect BOS, CHoCH, FVGs, and other ICT structural signals.

#### Acceptance Criteria

1. THE System SHALL compute candle structure features: body size, wick %, close position, engulf detection
2. THE System SHALL detect zone and structure features: BOS, CHoCH, FVG, liquidity sweep, swing high/low distance
3. THE System SHALL derive multi-timeframe trend bias from HTF candle direction (not EMA)
4. THE System SHALL compute session and time features: session name, day of week, news window proximity

### Requirement 4: Time Window and Narrative Framework

**User Story:** As a trading system, I want to classify every candle into ICT Killzone time windows and track key reference prices, so that I can weight setup probability based on time of day and narrative phase.

#### Acceptance Criteria

1. THE System SHALL classify every candle into one of the following time windows based on ICT Killzone methodology (all times NY, DST-aware): ASIAN_RANGE (20:00–22:00 NY), TRUE_DAY_OPEN (00:00–01:00 NY), LONDON_KILLZONE (02:00–05:00 NY), LONDON_SILVER_BULLET (03:00–04:00 NY), NY_AM_KILLZONE (07:00–10:00 NY), NY_AM_SILVER_BULLET (10:00–11:00 NY), LONDON_CLOSE (10:00–12:00 NY), NY_PM_KILLZONE (13:30–16:00 NY), NY_PM_SILVER_BULLET (14:00–15:00 NY), NEWS_WINDOW (08:00–09:00 NY), DAILY_CLOSE (17:00–18:00 NY), OFF_HOURS
2. THE System SHALL track three key reference prices per instrument per day: Daily Open (price at 18:00 NY), Weekly Open (price at Sunday 18:00 NY), True Day Open (price at 00:00 NY)
3. THE System SHALL compute price position relative to each reference price (ABOVE / BELOW / AT)
4. THE System SHALL assign a time window probability weight to every candle based on ICT Silver Bullet hierarchy: LONDON_SILVER_BULLET, NY_AM_SILVER_BULLET, NY_PM_SILVER_BULLET → 1.0; LONDON_KILLZONE, NY_AM_KILLZONE, NY_PM_KILLZONE → 0.9; NEWS_WINDOW → 0.8; TRUE_DAY_OPEN → 0.7; LONDON_CLOSE → 0.5; ASIAN_RANGE → 0.3; DAILY_CLOSE → 0.2; OFF_HOURS → 0.1
5. THE System SHALL use time_window_weight as a primary input to the Confluence_Scorer — setups during Silver Bullet windows and killzones score significantly higher than identical setups during off-hours
6. THE System SHALL classify every setup into a narrative phase: ACCUMULATION, MANIPULATION, EXPANSION, DISTRIBUTION, TRANSITION, OFF
7. THE System SHALL generate trade reasoning structured around the 3-question framework: (1) Where has price come from? (2) Where is it now? (3) Where is it likely to go?
8. WHEN generating entry bias reasoning, THE System SHALL prefer entries BELOW the session/candle open for bullish setups (manipulation wick down first, then expansion up)
9. WHEN generating entry bias reasoning, THE System SHALL prefer entries ABOVE the session/candle open for bearish setups (manipulation wick up first, then expansion down)

### Requirement 5: ML Pattern Detection

**User Story:** As a trading system, I want to detect market regimes and ICT patterns using ML models, so that I can score setups with a quantified confidence value before routing to the agent.

#### Acceptance Criteria

1. THE System SHALL classify market regime into: TRENDING_BULLISH, TRENDING_BEARISH, RANGING, BREAKOUT, NEWS_DRIVEN
2. THE System SHALL detect patterns: BOS_CONFIRMED, CHOCH_DETECTED, BEARISH_ARRAY_REJECTION, BULLISH_ARRAY_BOUNCE, FVG_PRESENT, LIQUIDITY_SWEEP, ORDER_BLOCK, INDUCEMENT
3. THE System SHALL define BEARISH_ARRAY_REJECTION as price rejected from a Bearish PD Array (Bearish OB / FVG / Breaker / IFVG) at PREMIUM of the Dealing_Range
4. THE System SHALL define BULLISH_ARRAY_BOUNCE as price bounced from a Bullish PD Array (Bullish OB / FVG / Breaker / IFVG) at DISCOUNT of the Dealing_Range
5. THE System SHALL score every detected setup with a confidence value between 0.0 and 1.0
6. THE System SHALL use HTF projection levels (O/H/L bias, range proximity) as primary confluence signals in the Confluence_Scorer
7. THE System SHALL achieve pattern detection accuracy ≥ 80% on held-out test data
8. THE System SHALL maintain a false positive rate < 20% at confidence threshold 0.75
9. THE System SHALL complete walk-forward validation with minimum 8 folds before model promotion

### Requirement 6: Intelligence Layer

**User Story:** As a trading system, I want to analyze news sentiment and economic events, so that I can enrich setups with fundamental context and avoid trades during high-risk windows.

#### Acceptance Criteria

1. THE System SHALL classify news sentiment per instrument using FinBERT
2. THE System SHALL summarise macro events (FOMC, CPI, NFP) via LLM (Claude primary, OpenAI fallback)
3. THE System SHALL generate human-readable trade reasoning for every flagged setup
4. THE System SHALL enforce economic calendar blackout windows (±15 min around high-impact events)

### Requirement 7: Agentic Execution Loop

**User Story:** As a trader, I want an autonomous agent to observe, analyse, decide, and act on setups, so that I can participate in high-probability trades without manual monitoring.

#### Acceptance Criteria

1. THE System SHALL run a continuous Observe → Analyse → Decide → Act → Review → Learn loop via LangGraph
2. THE System SHALL support Human-in-the-Loop mode (push alerts only, no autonomous execution)
3. THE System SHALL support Autonomous mode (full broker execution, feature-toggled per user)
4. THE System SHALL call the Risk_Engine synchronously before any trade decision — this gate cannot be bypassed
5. THE System SHALL log every decision (taken or skipped) with full reasoning to MongoDB
6. THE System SHALL implement a kill switch that halts the Agent immediately on drawdown breach

### Requirement 8: Risk Management

**User Story:** As a trader, I want all trades to pass automated risk checks before execution, so that drawdown is bounded and capital is protected at all times.

#### Acceptance Criteria

1. THE Risk_Engine SHALL enforce max risk per trade of 1% of account equity (user-configurable up to 2%)
2. THE Risk_Engine SHALL enforce a hard daily drawdown limit of 3%
3. THE Risk_Engine SHALL enforce a hard weekly drawdown limit of 6%
4. THE Risk_Engine SHALL block new trades within ±15 minutes of high-impact economic events
5. THE Risk_Engine SHALL gate setups below confidence threshold 0.65 (hard floor)
6. THE Risk_Engine SHALL limit maximum concurrent open trades to 3

### Requirement 9: Notifications

**User Story:** As a trader, I want to receive push notifications for detected setups, so that I can review and act on opportunities in real time.

#### Acceptance Criteria

1. THE System SHALL deliver push notifications via FCM for setup alerts
2. THE System SHALL include in every alert: instrument, direction, confidence score, entry/SL/TP, R-ratio, reasoning, HTF O/H/L levels, price bias vs HTF open
3. WHEN a setup is detected, THE System SHALL deliver the alert with latency < 3 seconds

### Requirement 10: Web Dashboard

**User Story:** As a trader, I want a real-time web dashboard, so that I can monitor live setups, agent decisions, and system status from one interface.

#### Acceptance Criteria

1. THE System SHALL provide a real-time live setups feed
2. THE System SHALL provide a setup detail panel showing patterns, scores, reasoning, and trade plan
3. THE System SHALL provide an agent decision log viewer
4. THE System SHALL provide agent status, pause, and resume controls

### Requirement 11: User and Authentication

**User Story:** As an administrator, I want role-based access control and encrypted credential storage, so that only authorized users can access and configure the trading system.

#### Acceptance Criteria

1. THE System SHALL implement JWT-based authentication
2. THE System SHALL implement RBAC with Admin, Trader, and Viewer roles
3. THE System SHALL allow per-user risk configuration (thresholds, instruments, agent mode)
4. THE System SHALL store broker API keys encrypted at rest

---

## Non-Functional Requirements

### NFR-1: Performance
- Setup detection latency: < 500ms from candle close
- Alert delivery: < 3 seconds from setup detection
- Trade execution: < 500ms from decision
- Live market data into TimescaleDB: < 2s latency

### NFR-2: Reliability
- System uptime: ≥ 99.5%
- Zero agent crashes during shadow period

### NFR-3: ML Quality Gates (must pass before production)
- Pattern accuracy ≥ 80% on held-out test set
- False positive rate < 20% at confidence threshold 0.75
- Backtest Sharpe Ratio ≥ 1.5 on 2-year out-of-sample period
- Backtest max drawdown ≤ 10%

### NFR-4: Security
- mTLS between all internal services
- JWT validation on all external endpoints
- Broker API keys encrypted via AWS KMS
- Full audit log of all agent decisions and trade executions
