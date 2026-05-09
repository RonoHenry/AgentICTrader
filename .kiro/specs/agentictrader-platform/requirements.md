# AgentICTrader.AI — Requirements

## Overview
AgentICTrader.AI is an autonomous intelligent trading platform that encodes professional Price Action expertise into a scalable AI system. It combines real-time market data engineering, ML pattern recognition, NLP sentiment analysis, and an agentic execution loop to identify, score, and act on high-probability trade setups.

---

## Functional Requirements

### FR-1: Market Data Ingestion
- The system MUST ingest real-time multi-timeframe OHLCV data (M1, M5, M15, H1, H4, D1, W1)
- The system MUST support Forex majors (EURUSD, GBPUSD), US Indices (US500, US30), and Gold (XAUUSD)
- The system MUST normalise tick data into OHLCV candles and publish to Kafka topics
- The system MUST write candle and tick data to TimescaleDB
- The system MUST ingest economic calendar events and flag high-impact windows
- The system MUST load a minimum of 3 years of historical OHLCV data per instrument

### FR-2: HTF Candle Projection Feature Engineering
- The system MUST implement auto-HTF timeframe selection: M1→M5, M5→M15, M15→H1, H1→H4, H4→D1, D1→W1, W1→M1, M1→M3, M3→M12
- The system MUST compute HTF OHLC values for the current and last N HTF candles (regular OHLC only, no Heikin Ashi)
- The system MUST extract the HTF Open as a bias anchor (price above = bullish, price below = bearish)
- The system MUST extract the HTF High as an upper range boundary (potential rejection/breakout zone)
- The system MUST extract the HTF Low as a lower range boundary (potential support/bounce zone)
- The system MUST compute price position relative to HTF Open (above/below bias flag)
- The system MUST compute distance from current price to HTF High and HTF Low as range proximity percentages
- The system MUST compute HTF candle body size, wick percentages, and close position within range
- The system MUST store all HTF projection levels per candle in the TimescaleDB indicators table
- The HTF Candle Projections indicator is the SOLE technical indicator — no ATR, RSI, ADX, EMA, or volume indicators

### FR-3: Candle & Zone Structure Features
- The system MUST compute candle structure features: body size, wick %, close position, engulf detection
- The system MUST detect zone and structure features: BOS, CHoCH, FVG, liquidity sweep, swing high/low distance
- The system MUST derive multi-timeframe trend bias from HTF candle direction (not EMA)
- The system MUST compute session and time features: session name, day of week, news window proximity

### FR-3A: Time Window & Narrative Framework
> Time is the determinant factor. The same price structure has different probability depending on which time window it forms in.

- The system MUST classify every candle into one of the following time windows based on ICT Killzone methodology (all times NY, DST-aware):
  - ASIAN_RANGE (20:00–22:00 NY) — Accumulation phase: liquidity building, creates Asian Range that London/NY will sweep
  - TRUE_DAY_OPEN (00:00–01:00 NY) — NY midnight: key reference price for intraday bias
  - LONDON_KILLZONE (02:00–05:00 NY) — Manipulation phase: "Engine Room", often creates high/low of day, highly volatile for EUR/GBP pairs
  - LONDON_SILVER_BULLET (03:00–04:00 NY) — Highest probability London window (subset of London Killzone)
  - NY_AM_KILLZONE (07:00–10:00 NY) — Expansion/delivery phase: "Decisive Mover", correlates with US economic data releases (8:30 AM) and NYSE open (9:30 AM), best for Indices and USD pairs
  - NY_AM_SILVER_BULLET (10:00–11:00 NY) — Highest probability NY AM window
  - LONDON_CLOSE (10:00–12:00 NY) — Distribution phase: retracements/reversals as European traders square positions
  - NY_PM_KILLZONE (13:30–16:00 NY) — Expansion phase: best for Indices (NASDAQ/S&P), secondary expansion or "Power Hour" move
  - NY_PM_SILVER_BULLET (14:00–15:00 NY) — Highest probability NY PM window
  - NEWS_WINDOW (08:00–09:00 NY) — Volatility injection: US economic data releases (NFP, CPI, FOMC at 8:30 AM)
  - DAILY_CLOSE (17:00–18:00 NY) — Position squaring before daily candle transition
  - OFF_HOURS — all other times

- The system MUST track three key reference prices per instrument per day:
  - Daily Open: price at 18:00 NY (new daily candle open) — daily bias anchor
  - Weekly Open: price at Sunday 18:00 NY — weekly bias anchor
  - True Day Open: price at 00:00 NY — intraday bias anchor

- The system MUST compute price position relative to each reference price (ABOVE / BELOW / AT)

- The system MUST assign a time window probability weight to every candle based on ICT Silver Bullet hierarchy:
  - LONDON_SILVER_BULLET, NY_AM_SILVER_BULLET, NY_PM_SILVER_BULLET → 1.0 (highest probability - Silver Bullet windows)
  - LONDON_KILLZONE, NY_AM_KILLZONE, NY_PM_KILLZONE → 0.9 (high probability killzones)
  - NEWS_WINDOW → 0.8
  - TRUE_DAY_OPEN → 0.7
  - LONDON_CLOSE → 0.5
  - ASIAN_RANGE → 0.3
  - DAILY_CLOSE → 0.2
  - OFF_HOURS → 0.1

- The system MUST use time_window_weight as a primary input to the Confluence Scorer — setups during Silver Bullet windows and killzones score significantly higher than identical setups during off-hours

- The system MUST classify every setup into a narrative phase: ACCUMULATION | MANIPULATION | EXPANSION | DISTRIBUTION | TRANSITION | OFF

- The system MUST generate trade reasoning structured around the 3-question framework:
  1. Where has price come from? (HTF context, previous session range, PD arrays)
  2. Where is it now? (current time window phase, price vs reference opens)
  3. Where is it likely to go? (nearest liquidity pool or imbalance to rebalance)

- Entry bias rules encoded in reasoning:
  - Bullish setup: prefer entries BELOW the session/candle open (manipulation wick down first, then expansion up)
  - Bearish setup: prefer entries ABOVE the session/candle open (manipulation wick up first, then expansion down)
  - Price can only do two things: sweep liquidity (above swing highs / below swing lows) or rebalance an imbalance (FVG/IFVG at opposing PD array)

### FR-4: ML Pattern Detection
- The system MUST classify market regime into: TRENDING_BULLISH, TRENDING_BEARISH, RANGING, BREAKOUT, NEWS_DRIVEN
- The system MUST detect patterns: BOS_CONFIRMED, CHOCH_DETECTED, BEARISH_ARRAY_REJECTION, BULLISH_ARRAY_BOUNCE, FVG_PRESENT, LIQUIDITY_SWEEP, ORDER_BLOCK, INDUCEMENT
- Note: BEARISH_ARRAY_REJECTION = price rejected from a Bearish PD Array (Bearish OB / FVG / Breaker / IFVG) at PREMIUM of the Dealing Range (not a "supply zone")
- Note: BULLISH_ARRAY_BOUNCE = price bounced from a Bullish PD Array (Bullish OB / FVG / Breaker / IFVG) at DISCOUNT of the Dealing Range (not a "demand zone")
- The system MUST score every detected setup with a confidence value between 0.0 and 1.0
- The system MUST use HTF projection levels (O/H/L bias, range proximity) as primary confluence signals in the Confluence Scorer
- Pattern detection accuracy MUST be ≥ 80% on held-out test data
- False positive rate MUST be < 20% at confidence threshold 0.75
- Walk-forward validation MUST be completed with minimum 8 folds before model promotion

### FR-5: Intelligence Layer
- The system MUST classify news sentiment per instrument using FinBERT
- The system MUST summarise macro events (FOMC, CPI, NFP) via LLM (Claude primary, OpenAI fallback)
- The system MUST generate human-readable trade reasoning for every flagged setup
- The system MUST enforce economic calendar blackout windows (±15 min around high-impact events)

### FR-6: Agentic Execution Loop
- The system MUST run a continuous Observe → Analyse → Decide → Act → Review → Learn loop via LangGraph
- The system MUST support Human-in-the-Loop mode (push alerts only, no autonomous execution)
- The system MUST support Autonomous mode (full broker execution, feature-toggled per user)
- The system MUST call the Risk Engine synchronously before any trade decision — this gate cannot be bypassed
- The system MUST log every decision (taken or skipped) with full reasoning to MongoDB
- The system MUST implement a kill switch that halts the agent immediately on drawdown breach

### FR-7: Risk Management
- The system MUST enforce max risk per trade of 1% of account equity (user-configurable up to 2%)
- The system MUST enforce a hard daily drawdown limit of 3%
- The system MUST enforce a hard weekly drawdown limit of 6%
- The system MUST block new trades within ±15 minutes of high-impact economic events
- The system MUST gate setups below confidence threshold 0.65 (hard floor)
- The system MUST limit maximum concurrent open trades to 3

### FR-8: Notifications
- The system MUST deliver push notifications via FCM for setup alerts
- The system MUST include in every alert: instrument, direction, confidence score, entry/SL/TP, R-ratio, reasoning, HTF O/H/L levels, price bias vs HTF open
- Alert delivery latency MUST be < 3 seconds from setup detection

### FR-9: Web Dashboard
- The system MUST provide a real-time live setups feed
- The system MUST provide a setup detail panel showing patterns, scores, reasoning, and trade plan
- The system MUST provide an agent decision log viewer
- The system MUST provide agent status, pause, and resume controls

### FR-10: User & Auth
- The system MUST implement JWT-based authentication
- The system MUST implement RBAC with Admin, Trader, and Viewer roles
- The system MUST allow per-user risk configuration (thresholds, instruments, agent mode)
- The system MUST store broker API keys encrypted at rest

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
