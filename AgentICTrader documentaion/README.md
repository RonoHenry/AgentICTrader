# AgentICTrader.AI

> Autonomous Intelligent Trading Agent — powered by Price Action expertise, Machine Learning, and Agentic AI.

---

## What Is This?

AgentICTrader.AI is an end-to-end intelligent trading platform that encodes 6+ years of professional Price Action trading knowledge into a scalable, autonomous AI system. It combines real-time market data engineering, machine learning pattern recognition, NLP-driven sentiment analysis, and an agentic execution loop to identify, score, and act on high-probability trade setups — the same way a seasoned discretionary trader would, but at machine speed and scale.

---

## Documentation Index

| Document | Description |
|---|---|
| [`docs/01_BRD.md`](docs/01_BRD.md) | Business Requirements Document |
| [`docs/02_PRD.md`](docs/02_PRD.md) | Product Requirements Document |
| [`docs/03_ARCHITECTURE.md`](docs/03_ARCHITECTURE.md) | System Architecture Document |
| [`docs/04_TECH_STACK.md`](docs/04_TECH_STACK.md) | Full Technology Stack |
| [`docs/05_DATA_MODELS.md`](docs/05_DATA_MODELS.md) | Data Models & Schema Design |
| [`docs/06_API_DESIGN.md`](docs/06_API_DESIGN.md) | API Design & Endpoints |
| [`docs/07_ML_PIPELINE.md`](docs/07_ML_PIPELINE.md) | ML Pipeline & Model Architecture |
| [`docs/08_AGENT_DESIGN.md`](docs/08_AGENT_DESIGN.md) | Agentic AI Design |
| [`docs/09_SECURITY.md`](docs/09_SECURITY.md) | Security Architecture |
| [`docs/10_DEPLOYMENT.md`](docs/10_DEPLOYMENT.md) | Deployment & Infrastructure |
| [`docs/11_ROADMAP.md`](docs/11_ROADMAP.md) | Development Roadmap & Milestones |
| [`DIRECTORY_STRUCTURE.md`](DIRECTORY_STRUCTURE.md) | Full Project Directory Structure |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution Guidelines |

---

## Quick Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     AgentICTrader.AI                        │
│                                                             │
│  Data Layer → ML Layer → Intelligence Layer → Agent Loop   │
│       ↓            ↓              ↓                ↓        │
│   Ingest       Detect          Score           Execute      │
│   Clean        Pattern         Sentiment       Review       │
│   Store        Regime          Confidence      Learn        │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Pillars

1. **Data Engineering** — Real-time multi-timeframe market data pipelines
2. **Data Analytics** — Trader performance quantification and edge analysis
3. **Machine Learning** — Pattern detection, regime classification, probability scoring
4. **NLP / LLMs** — News sentiment, macro event analysis, autonomous trade journaling
5. **Agentic AI** — Observe → Analyse → Decide → Act → Review → Learn loop
6. **Platform** — Mobile/web dashboard, alerts, backtesting, risk management

---

## Repository Structure (Summary)

```
AgentICTrader.AI/
├── apps/                   # Frontend applications
├── services/               # Backend microservices
├── ml/                     # Machine learning pipelines
├── agent/                  # Agentic AI core
├── data/                   # Data engineering
├── infra/                  # Infrastructure as code
├── docs/                   # All documentation
└── scripts/                # Dev & ops utilities
```

See [`DIRECTORY_STRUCTURE.md`](DIRECTORY_STRUCTURE.md) for the full expanded tree.

---

## Current Status

| Phase | Status |
|---|---|
| Phase 0 — Foundation & Data | 🟡 In Progress |
| Phase 1 — Pattern ML | 🔴 Not Started |
| Phase 2 — Intelligence Layer | 🔴 Not Started |
| Phase 3 — Agent V1 (Human-in-Loop) | 🔴 Not Started |
| Phase 4 — Autonomous Execution | 🔴 Not Started |
| Phase 5 — Platform | 🔴 Not Started |

---

## Stack at a Glance

- **Backend:** Python (FastAPI), Node.js
- **ML/AI:** PyTorch, XGBoost, LangChain, LangGraph, FinBERT
- **Data:** TimescaleDB, Redis, Apache Kafka, dbt
- **Frontend:** React (Next.js), React Native
- **Infra:** Docker, Kubernetes, Terraform, AWS
- **Monitoring:** Grafana, Prometheus, MLflow

---

*Built at the intersection of discretionary trading mastery and modern AI engineering.*
