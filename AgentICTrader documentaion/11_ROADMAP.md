# Development Roadmap & Milestones
**Project:** AgentICTrader.AI
**Version:** 1.0.0
**Last Updated:** 2026-04-04

---

## Overview

The build follows a strict phase-gate model. Each phase has a defined exit criteria — the next phase does not begin until the gate is passed. This prevents the most common failure mode: building the agent before the foundation is solid.

```
Phase 0          Phase 1          Phase 2          Phase 3
Foundation  ──→  Pattern ML  ──→  Intelligence ──→ Agent V1
(Weeks 1–4)     (Weeks 5–10)     (Weeks 11–16)    (Weeks 17–22)
                                                        │
                                                        ▼
                                                   Phase 4          Phase 5
                                                   Autonomous  ──→  Platform
                                                   (Month 6–9)      (Month 9+)
```

---

## Phase 0 — Foundation & Edge Quantification
**Duration:** 4 Weeks
**Goal:** Build the data layer and quantify the existing trading edge before any ML work begins.

### Deliverables

| Task | Owner | Week |
|---|---|---|
| Set up local dev environment (Docker Compose: TimescaleDB, Redis, Kafka) | Data Eng | 1 |
| Implement OANDA WebSocket connector + OHLCV normaliser | Data Eng | 1 |
| Design and create TimescaleDB schema (candles, indicators, events) | Data Eng | 1 |
| Load 3 years of historical OHLCV data (US500, US30, EURUSD, XAUUSD, GBPUSD) | Data Eng | 2 |
| Build trade journal importer (parse CSV/XLSX → MongoDB `trade_journal`) | Data Eng | 2 |
| Implement feature engineering pipeline (all features from ML doc §2) | ML Eng | 2–3 |
| Build Analytics Service: win rate, R-multiple, expectancy by condition | Analytics | 3 |
| Build Streamlit-based edge analysis dashboard (internal use) | Analytics | 3–4 |
| Economic calendar ingestion + storage | Data Eng | 4 |
| Deploy all Phase 0 services to staging environment | DevOps | 4 |

### Exit Criteria (Gate 0)
- [ ] Live market data flowing into TimescaleDB with < 2s latency
- [ ] 3+ years of clean historical data loaded and validated
- [ ] Trade journal imported and analytics dashboard live
- [ ] Edge analysis complete: win rate, R-multiple, best/worst conditions documented
- [ ] Feature pipeline producing validated output on live data

---

## Phase 1 — Pattern ML
**Duration:** 6 Weeks
**Goal:** Build, train, and validate the core ML models (regime, pattern, scorer).

### Deliverables

| Task | Owner | Week |
|---|---|---|
| Build pattern labelling tool (`ml/models/pattern_detector/labeller.py`) | ML Eng | 5 |
| Label minimum 500 examples per pattern from historical data | Trader + ML | 5–6 |
| Train and validate Regime Classifier (XGBoost) | ML Eng | 6–7 |
| Train and validate Pattern Detector (XGBoost multi-label) | ML Eng | 7–8 |
| Train and validate Confluence Scorer (ensemble) | ML Eng | 8–9 |
| Build backtesting engine and run full backtest on all models | ML Eng | 9 |
| Set up MLflow for experiment tracking | MLOps | 5 |
| Deploy ML inference service (FastAPI) to staging | ML Eng | 10 |
| Kafka integration: ML engine consumes candles, publishes setups | ML Eng | 10 |

### Exit Criteria (Gate 1)
- [ ] Pattern detection accuracy ≥ 80% on held-out test set
- [ ] False positive rate < 20% at confidence threshold 0.75
- [ ] Backtest Sharpe Ratio ≥ 1.5 on 2-year out-of-sample period
- [ ] Backtest max drawdown ≤ 10%
- [ ] ML engine publishing detected setups to Kafka in real-time
- [ ] Walk-forward validation completed (minimum 8 folds)

---

## Phase 2 — Intelligence Layer
**Duration:** 6 Weeks
**Goal:** Add NLP sentiment and LLM reasoning on top of the ML core.

### Deliverables

| Task | Owner | Week |
|---|---|---|
| Integrate news API (Benzinga / Alpha Vantage News / Reuters RSS) | NLP Eng | 11 |
| Implement FinBERT sentiment classifier per instrument | NLP Eng | 11–12 |
| Build sentiment signal publisher to Kafka + Redis cache | NLP Eng | 12 |
| Implement economic calendar monitor with blackout window detection | NLP Eng | 12 |
| Build LLM macro event summariser (Claude API) | NLP Eng | 13 |
| Build LLM trade reasoning generator | NLP Eng | 13–14 |
| Integrate sentiment into Confluence Scorer as additional feature | ML Eng | 14 |
| Retrain all models with sentiment features | ML Eng | 14–15 |
| Validate improvement in model performance with sentiment | ML Eng | 15 |
| NLP service deployed to staging with Kafka integration | DevOps | 16 |

### Exit Criteria (Gate 2)
- [ ] Sentiment updates for all instruments within 5 minutes of news publication
- [ ] Sentiment feature improves backtest metrics (Sharpe improvement ≥ 0.1)
- [ ] LLM reasoning output passes quality review (10 examples reviewed by trader)
- [ ] Calendar blackout windows correctly blocking setups during high-impact events
- [ ] Full pipeline (candle → setup → sentiment → reasoning) end-to-end in staging

---

## Phase 3 — Agent V1 (Human-in-the-Loop)
**Duration:** 6 Weeks
**Goal:** Deploy the agent in notification-only mode. Real setups, real push alerts, paper trading.

### Deliverables

| Task | Owner | Week |
|---|---|---|
| Build Risk Engine Service (position sizer, DD monitor, exposure tracker) | Backend | 17 |
| Implement LangGraph agent state graph (all nodes) | Agent Eng | 17–18 |
| Build notification service (FCM push + email) | Backend | 18 |
| Implement User/Auth Service + user risk config | Backend | 18–19 |
| Build initial web dashboard (Next.js): setups feed + alert log | Frontend | 19–20 |
| Connect agent to paper trading account (OANDA practice) | Agent Eng | 20 |
| Run 4-week live shadow period: agent alerts, trader validates | All | 19–22 |
| Build agent decision log viewer in dashboard | Frontend | 21 |
| Performance comparison: agent setups vs manual trader decisions | Analytics | 22 |

### Exit Criteria (Gate 3)
- [ ] Agent correctly identifies ≥ 80% of setups trader would have taken (shadow period)
- [ ] Alert delivery latency < 3 seconds from candle close
- [ ] Risk engine correctly blocking trades outside configured limits
- [ ] Dashboard displaying live setups, scores, and reasoning
- [ ] Zero agent crashes during 4-week shadow period
- [ ] Paper trading P&L positive over shadow period

---

## Phase 4 — Autonomous Execution
**Duration:** 3 Months
**Goal:** Enable the agent to execute trades autonomously with strict risk controls.

### Deliverables

| Task | Owner | Week |
|---|---|---|
| Implement broker execution tools (place order, set SL/TP, close) | Agent Eng | 23–25 |
| Build `execute_node` in LangGraph with full risk gate integration | Agent Eng | 25–26 |
| Build `review_node` for trade monitoring, partial exits, SL management | Agent Eng | 26–28 |
| Implement `learn_node` with retraining queue integration | Agent Eng | 28–30 |
| Feature toggle: HUMAN_IN_LOOP / AUTONOMOUS per user | Backend | 30 |
| 30-day live autonomous run on minimum capital (10% of account) | All | 31–34 |
| Monitor, review, adjust confidence thresholds based on live results | Trader + ML | 34–36 |

### Exit Criteria (Gate 4)
- [ ] 30-day live autonomous run: positive P&L, drawdown ≤ 5%
- [ ] Zero cases of risk engine bypass
- [ ] Autonomous performance within ±10% of Phase 3 paper trading metrics
- [ ] Full decision + execution audit trail for all trades
- [ ] Rollback mechanism tested and confirmed working

---

## Phase 5 — Platform
**Duration:** 3+ Months
**Goal:** Build AgentICTrader.AI as a multi-user platform product.

### Deliverables

| Task | Owner |
|---|---|
| Full web dashboard rebuild (professional UI, all analytics pages) | Frontend |
| React Native mobile app (iOS + Android) | Mobile |
| Multi-user support with RBAC | Backend |
| User onboarding flow (connect broker, set risk config, import journal) | Frontend |
| Backtesting visualiser (replay any historical period with agent logic) | ML + Frontend |
| Subscription billing integration (Stripe) | Backend |
| Landing page and marketing site | Frontend |
| Documentation and API for potential partner integrations | Backend |
| Security audit | Security |
| Public beta launch | All |

---

## Technology Decisions by Phase

| Phase | New Tech Introduced |
|---|---|
| 0 | TimescaleDB, Redis, Kafka, OANDA API, dbt, Streamlit |
| 1 | XGBoost, scikit-learn, MLflow, FastAPI (inference) |
| 2 | FinBERT, Claude API / OpenAI API, LangChain, news APIs |
| 3 | LangGraph, React/Next.js, FCM Push, OANDA Paper Trading |
| 4 | Live broker execution, Kubernetes (production), Terraform |
| 5 | React Native, Stripe, full AWS production stack |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Insufficient labelled training data | MEDIUM | HIGH | Use semi-supervised labelling + data augmentation |
| Model overfitting to historical data | HIGH | HIGH | Walk-forward validation mandatory before any promotion |
| Broker API rate limits blocking real-time data | LOW | HIGH | Implement retry logic + fallback data source |
| Agent placing erroneous trade (autonomous mode) | LOW | CRITICAL | Risk engine as synchronous gate; kill switch; max size limits |
| Model performance degrades in live market | MEDIUM | HIGH | Continuous monitoring + automatic confidence threshold adjustment |
| LLM API downtime (reasoning generation) | LOW | MEDIUM | Fallback to template-based reasoning if LLM unavailable |

---

*Document Owner: Founder / Lead Engineer | Review Cycle: Per Phase Gate*
