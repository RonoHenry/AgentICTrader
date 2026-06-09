# PR: Liquidity Engine Spec — Design, Requirements & Task List

**Branch:** `feature/task-33-notification-service`
**Commit:** `8034505`
**Scope:** Spec documentation only — no production code changes

---

## Summary

Adds the complete spec for the **Liquidity Engine** — a pure-Python analytical package that encodes the full ICT/TTrades multi-timeframe Price Action methodology into a deterministic, stateless computation pipeline.

This is a **post-v1 feature** (parked until after task 143 ships). The spec is written to be self-contained and implementation-ready, requiring no further clarification to begin development.

---

## Files Added / Modified

| File | Change |
|---|---|
| `.kiro/specs/liquidity-engine/design.md` | Updated — added Correctness Properties section |
| `.kiro/specs/liquidity-engine/requirements.md` | New — 14 requirements, 23 PBT correctness properties |
| `.kiro/specs/liquidity-engine/tasks.md` | New — 17 tasks (144–160) with full TDD breakdown |

---

## What the Liquidity Engine Does

Called once per candle close from `agent/nodes/observe_node.py`, it consumes `Dict[Timeframe, List[Candle]]` and returns a single `LiquidityMap` object containing:

- **HTF Bias** — BULLISH/BEARISH/NEUTRAL per timeframe, anchored to candle opens (midnight, weekly, monthly)
- **Liquidity Levels** — BSL/SSL pools: PWH, PWL, PDH, PDL, PMH, PML, equal highs/lows, session highs/lows
- **PD Arrays** — FVG, Order Block, Breaker, IFVG, BPR, CISD levels across all timeframes
- **CRT Phases** — C1 Accumulation / C2 Manipulation / C3 Distribution / C4 Continuation per timeframe
- **CISD Cascade** — cross-timeframe Change in State of Delivery validation (MN1→D1, W1→H4, D1→H1, H4→M15, M30→M3, M15→M1)
- **Draw-on-Liquidity** — primary price target derived from HTF bias + nearest unswept level
- **Sweep Detection** — flags when draw-on-liquidity target has been taken
- **OTE Zone** — Fibonacci 0.62–0.79 retracement of the displacement leg, with golden level at 0.705
- **UNICORN Pattern** — Breaker Block + FVG overlapping at the same price level
- **Setup Grade** — A+ / A / B / NO_TRADE based on an 8-condition checklist
- **`to_agent_context()`** — serialises the LiquidityMap to a structured LLM prompt string

The output is stored on `AgentState.liquidity_map` and replaces `backend/trader/agents/power_of_3.py`, `backend/trader/analysis/patterns.py`, and the stub `backend/trader/agents/pd_array/` directory.

---

## Package Structure

```
liquidity_engine/
├── __init__.py              # exports: LiquidityMappingEngine, LiquidityMap
├── models.py                # all Pydantic v2 data models and enums
├── engine.py                # LiquidityMappingEngine orchestrator
├── detectors/
│   ├── external.py          # BSL/SSL, PWH/PWL/PDH/PDL, equal highs/lows
│   ├── internal.py          # FVG, OB, Breaker, IFVG, BPR, CISD levels
│   └── institutional.py     # session highs/lows, trendline liquidity
├── ipda/
│   ├── classifier.py        # CRT phase detection (C1/C2/C3/C4)
│   └── cisd.py              # CISD detection + cascade validation
├── ote/
│   └── calculator.py        # Fibonacci OTE zone (0.62–0.79)
├── unicorn/
│   └── detector.py          # Breaker + FVG overlap detection
├── grader/
│   └── setup_grader.py      # A+/A/B/NO_TRADE scoring
└── utils/
    ├── time_utils.py         # EST/UTC conversions, killzone windows
    └── candle_utils.py       # swing point detection, ATR, candle helpers
```

---

## Implementation Tasks (144–160)

| Task | Component | Key Deliverable |
|---|---|---|
| 144 | `models.py` + scaffold | All Pydantic v2 models, OHLC validators, package `__init__` files |
| 145 | `utils/` | EST/UTC conversion, killzone windows, swing detection, ATR |
| 146 | `detectors/external.py` | LiquidityLevelDetector — PWH/PWL/PDH/PDL, EQH/EQL, session levels |
| 147 | `detectors/internal.py` | PDArrayDetector — FVG, OB, Breaker, IFVG, BPR, CISD_LEVEL |
| 148 | Checkpoint | Tasks 144–147 all GREEN |
| 149 | `ipda/cisd.py` | CISDDetector — bearish/bullish CISD, swing prerequisite |
| 150 | `ipda/classifier.py` | IPDAClassifier — CRT phases, CISD cascade validation |
| 151 | `ote/calculator.py` | OTECalculator — Fibonacci levels, displacement leg, price_in_ote |
| 152 | `unicorn/detector.py` | UnicornDetector — Breaker+FVG overlap, recency tie-breaking |
| 153 | `grader/setup_grader.py` | SetupGrader — 8-condition A+/A/B/NO_TRADE grading |
| 154 | Checkpoint | Tasks 149–153 all GREEN |
| 155 | `engine.py` | LiquidityMappingEngine.analyze() — full orchestration |
| 156 | `to_agent_context()` + HTFBiasClassifier | LLM context serialisation, bias classification |
| 157 | Coverage checkpoint | ≥ 90% line coverage across `liquidity_engine/` |
| 158 | `observe_node` + `AgentState` | Integration — `AgentState.liquidity_map` field, observe_node wiring |
| 159 | Final checkpoint | Zero regressions, full coverage gate |
| 160* | `services/liquidity/` (optional) | FastAPI + Kafka microservice wrapper |

---

## Testing Approach

All tasks follow **RED → GREEN → REFACTOR**. Tests live in `backend/tests/test_liquidity_*.py`.

Property-based tests use `hypothesis` (`@given`, `@settings(max_examples=100)`) and cover all 23 correctness properties defined in `requirements.md`, including:

- Engine determinism and input immutability
- HTF bias direction correctness and neutral band
- All PDArray `high > low` invariant
- OTE zone structural ordering (`fib_62 < fib_705 < fib_79`)
- UNICORN overlap well-formed (`overlap_low < overlap_high`)
- Setup grade `conditions_met` accuracy
- A+ grade requires all 8 conditions
- CISD cascade validity requires both CISDs confirmed
- `draw_on_liquidity` reference integrity

---

## BRD Traceability

| BRD Requirement | Coverage |
|---|---|
| BR-ML01 — Detect PD Arrays, FVGs, OBs, Breakers, sweeps | PDArrayDetector, LiquidityLevelDetector |
| BR-ML03 — Confidence score per setup | SetupGrader (A+/A/B/NO_TRADE + conditions_met) |
| BR-ML04 — Multi-timeframe confluence scoring | HTFBiasClassifier, IPDAClassifier, CISD cascade |
| SO-01 — Encode discretionary methodology as machine logic | Full engine pipeline |
| BR-AG01 — Agent observe→analyse→decide loop | Integration with observe_node + AgentState |

---

## Notes

- This spec is **parked for post-v1** (after task 143 ships on the main platform spec)
- No production code is included in this commit — spec only
- The engine is pure Python with zero I/O side effects during `analyze()`
- Dependencies: Pydantic v2 + stdlib only (no new packages required)
