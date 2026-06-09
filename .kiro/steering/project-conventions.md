# Project Conventions

## Core Principle
This platform encodes **ICT (Inner Circle Trader) Price Action methodology**. The sole technical indicator is the HTF Candle Projection (Open, High, Low of the Higher Timeframe candle). No ATR, RSI, EMA, ADX, or lagging indicators anywhere in the codebase.

## ICT Terminology (use these exact terms)
- **HTF** — Higher Time Frame (H1, H4, D1 relative to the entry timeframe)
- **Dealing Range** — The range defined by HTF High and HTF Low
- **Premium** — Upper 50% of Dealing Range (where bearish arrays sit)
- **Discount** — Lower 50% of Dealing Range (where bullish arrays sit)
- **PD Arrays** — Price Delivery Arrays: Order Blocks, FVGs, Breakers, IFVGs
- **Bearish Array** — Bearish OB / FVG / Breaker / IFVG at **Premium** of Dealing Range (not "supply zone")
- **Bullish Array** — Bullish OB / FVG / Breaker / IFVG at **Discount** of Dealing Range (not "demand zone")
- **BOS** — Break of Structure (trend continuation)
- **CHoCH** — Change of Character (first sign of reversal)
- **FVG** — Fair Value Gap (price imbalance)
- **Killzones** — High-probability session windows (London, NY AM, NY PM, Silver Bullets)
- **Liquidity Sweep** — False breakout over swing high/low before true move

## Confidence Score Thresholds
| Score | Action |
|---|---|
| ≥ 0.85 | NOTIFY + AUTO-EXECUTE (autonomous mode) |
| 0.75–0.84 | NOTIFY trader |
| 0.65–0.74 | LOG only / watchlist |
| < 0.65 | DISCARD |

## Directory Structure
```
ml/features/          # Feature extractors (HTFProjectionExtractor, ZoneFeatureExtractor, etc.)
ml/models/            # Model training scripts (regime_classifier, pattern_detector, confluence_scorer)
ml/inference/         # FastAPI inference service (port 8002)
services/algorag/     # AlgoRAG FastAPI service (port 8003)
scripts/rag/          # Data preparation scripts for RAG pipeline
scripts/rag/utils/    # SetupEnricher, NarrativeGenerator
scripts/rag/tests/    # Tests for RAG scripts
agent/nodes/          # LangGraph agent nodes (observe, analyse, decide, execute, review, learn)
agent/state.py        # AgentState — the single typed state object flowing through the graph
backend/              # Django legacy backend (TimescaleDB, MongoDB, Redis connectivity)
services/analytics/   # Analytics dashboard (Streamlit)
services/risk_engine/ # Risk Engine FastAPI service (synchronous gate, never a subscriber)
docker/               # docker-compose.yml and init scripts
```

## Python Code Style
- Always use `from __future__ import annotations` at the top of new files
- Use `@dataclass` for plain data containers; use `pydantic.BaseModel` for request/response models and anything that crosses service boundaries
- Type-annotate all function signatures
- Use `Optional[X]` not `X | None` for compatibility
- Module-level docstring on every new file explaining its purpose and usage example
- Keep `sys.path` manipulation isolated to the top of scripts (before other imports), using `os.path.abspath`

## Feature Extractor Pattern
All feature extractors follow this interface:
```python
class SomeFeatureExtractor:
    def __init__(self): ...

    def extract(self, candles: List[Dict[str, Any]], ...) -> SomeFeatures:
        """Returns a dataclass with all computed features."""
        ...
```
Extractors are **stateless** — no `fit()` required. `HTFProjectionExtractor`, `ZoneFeatureExtractor`, `CandleFeatureExtractor`, and `TimeWindowClassifier` are the four canonical extractors. Always reuse them; do not reimplement their logic.

## EnrichedSetup Data Model
The canonical enriched trade document used throughout the RAG pipeline:
```python
# scripts/rag/utils/setup_enricher.py → EnrichedSetup
# Fields: trade_id, timestamp, instrument, direction, entry_price, exit_price,
#         stop_loss, take_profit, r_multiple, outcome_result,
#         htf_timeframe, htf_open, htf_high, htf_low, htf_open_bias,
#         htf_high_proximity_pct, htf_low_proximity_pct, htf_body_pct, htf_close_position,
#         bos_detected, choch_detected, fvg_present, liquidity_sweep,
#         swing_high_distance, swing_low_distance, htf_trend_bias,
#         time_window, narrative_phase, time_window_weight, is_killzone,
#         narrative, confluence_count, full_setup
```

## Agent State
`AgentState` in `agent/state.py` is the single typed Pydantic model that flows through every LangGraph node. Never pass raw dicts between nodes — always update and return `AgentState`.

## Instruments
Supported: EURUSD, GBPUSD, USDJPY, XAUUSD, US500, US30. Always store instrument names in UPPERCASE.

## Timestamps
- All timestamps stored and compared in **UTC**
- Always use `timezone.utc` when constructing `datetime` objects
- Parse ISO 8601 strings with `.replace("Z", "+00:00")` before `fromisoformat()`
- Session/killzone classification uses **NY timezone** (America/New_York, DST-aware via `zoneinfo`)
