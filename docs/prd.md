# AgentICTrader.AI — Product Requirements Document
**Version:** 2.0.0
**Last Updated:** 2026-04-24

---

## 1. Product Overview

AgentICTrader.AI is an autonomous intelligent trading platform that encodes 6+ years of professional Price Action expertise into a scalable AI system. It combines real-time market data engineering, ML pattern recognition, NLP sentiment analysis, and an agentic execution loop to identify, score, and act on high-probability trade setups at machine speed.

**Target Users:** Professional discretionary traders, algorithmic trading enthusiasts, investment firms.

---

## 2. Feature Requirements

### 2.1 Market Data
- Real-time multi-timeframe OHLCV ingestion (M1, M5, M15, H1, H4, D1, W1)
- Support for Forex majors, US Indices (US500, US30), and Gold (XAUUSD)
- Historical data going back minimum 3 years
- Economic calendar ingestion with high-impact event flagging
- All data normalised, timestamped in UTC, and validated before use

### 2.2 Machine Learning
- Regime classification: TRENDING_BULLISH, TRENDING_BEARISH, RANGING, BREAKOUT, NEWS_DRIVEN
- Pattern detection: BOS, CHoCH, Supply/Demand zones, FVGs, Liquidity sweeps, Order Blocks
- Confidence scoring (0.0–1.0) for every identified setup
- Multi-timeframe confluence scoring
- Minimum 80% pattern detection accuracy on held-out data
- Walk-forward validation mandatory before any model promotion
- Models retrain incrementally on new trade outcomes

### 2.3 Intelligence / NLP
- News sentiment per instrument via FinBERT (directional bias score)
- Macro event summarisation (FOMC, CPI, NFP) via LLM
- Human-readable trade reasoning generated for every flagged setup
- Economic calendar blackout windows (±15 min around high-impact events)

### 2.4 Agentic System
- Continuous Observe → Analyse → Decide → Act → Review → Learn loop
- Human-in-the-loop mode: push alerts to trader, no autonomous execution
- Autonomous mode: full execution via broker API (feature-toggled per user)
- Hard risk controls enforced at all times — agent cannot override
- Full decision log with reasoning for every setup (taken or skipped)
- Kill switch: agent halts immediately on daily/weekly drawdown breach

### 2.5 Risk Management
- Max risk per trade: 1–2% of account equity (user-configurable)
- Max daily drawdown: 3% (hard limit)
- Max weekly drawdown: 6% (hard limit)
- Max concurrent open trades: 3
- Confidence threshold gate: minimum 0.75 to notify, 0.65 hard floor
- News blackout: no new trades within ±15 minutes of high-impact events

### 2.6 Platform / UI
- Real-time web dashboard: live setups feed, scores, reasoning, agent status
- Trade journal with import (CSV/XLSX) and export
- Performance analytics: win rate, R-multiple, expectancy by condition
- Backtesting visualiser with detailed trade replay
- Mobile push notifications for setup alerts (Phase 3+)
- Mobile app iOS/Android (Phase 5)

---

## 3. Technical Requirements

### 3.1 Performance
- Setup detection latency: < 500ms from candle close
- Alert delivery: < 3 seconds from setup detection
- Trade execution: < 500ms from decision
- System uptime: ≥ 99.5%

### 3.2 ML Quality Gates
- Pattern accuracy ≥ 80% on held-out test set
- False positive rate < 20% at confidence threshold 0.75
- Backtest Sharpe Ratio ≥ 1.5 on 2-year out-of-sample period
- Backtest max drawdown ≤ 10%
- Minimum Sharpe 1.5 required before any model goes to production

### 3.3 Security
- JWT-based authentication with RBAC (Admin, Trader, Viewer)
- Broker API keys encrypted at rest (AWS KMS)
- mTLS between all internal services
- Full audit log of all agent decisions and trade executions

---

## 4. Success Metrics

| Metric | Target |
|---|---|
| Setup detection accuracy vs manual | ≥ 80% match rate |
| False positive rate at confidence > 0.75 | < 20% |
| Automated trade win rate | ≥ trader's historical win rate (±5%) |
| Average R-multiple per trade | ≥ 1.5R |
| Maximum automated monthly drawdown | ≤ 8% |
| Platform uptime | ≥ 99.5% |
| Alert delivery latency | < 3 seconds |

---

## 5. Out of Scope (v1.0)

- High-frequency trading or sub-second execution
- Options, futures, or crypto (Phase 1 scope: Forex + Indices)
- Social copy-trading
- Automated tax reporting
- Mobile app (Phase 5)

---

## 6. Phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Foundation & Edge Quantification | 🟡 In Progress |
| 1 | Pattern ML (Regime + Pattern + Scorer) | 🔴 Not Started |
| 2 | Intelligence Layer (NLP + LLM) | 🔴 Not Started |
| 3 | Agent V1 — Human-in-the-Loop | 🔴 Not Started |
| 4 | Autonomous Execution | 🔴 Not Started |
| 5 | Platform (Multi-user, Mobile) | 🔴 Not Started |
