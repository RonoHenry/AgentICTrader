# Design Document

**Spec**: AlgoMindDIS
**Requirements**: `.kiro/specs/algomind-dis/requirements.md`

## Overview

AlgoMindDIS is a new package, `algomind_dis/`, between the detections that exist (`liquidity_engine.context`, `algo_research`) and the hands that exist (the THESIS mode's paper agent). Every function is pure: closed candles in, records out. The state is a fold over D1 closes, so a replay and a restart are the same computation.

```
bars (terminal H1 live / Yahoo daily 1996-2022 / snapshot M1 2018-2022)
  → algomind_dis.frames      MN1, W1, D1 (+H4, H1) as Candles, closed by t, New York days
  → algomind_dis.analyzers   structure · ranges · premium/discount · objectives · arrays · delivery · time · volatility
  → algomind_dis.evidence    Evidence items → correlation control → S_B, S_S (§9.4 weights, v1 settings)
  → algomind_dis.narrative   MarketNarrative (templates, no generated text)
  → algomind_dis.state       the state machine, one step per D1 close → timeline of transitions
  → algomind_dis.contract    DirectionalBiasOutput 1.0.0 · qualify(setup) · thesis-file adapter
  → algomind_dis.replay      the timeline over history; H-AF's cells and §16's report
  → Noculus /context (shadow) · paper agent (enforced, once H-AF passes)
```

## Phase 0: The Compatibility Report (Requirement 1)

What §4-§8 asks for, and where it already lives. AlgoMindDIS calls these and does not re-detect.

| Spec component | Existing function | Notes |
|---|---|---|
| Candles per frame, closed only | `liquidity_engine.context.frame_state.Candles`; `algo_mind.dis.terminal_market` (H1 → NY D1/W1) and `daily_market` (Yahoo) | MN1 is grouped from D1 here (gap) |
| Swings (§5.1) | `liquidity_engine.context.measures.swing_highs/swing_lows` (lookback 2) | Ranked STH/ITH/LTH in `algo_research.trend.ranked_highs/lows` |
| BOS / MSS (§7.1) | `algo_research.trend.break_state` (closes beyond ranked swings) | It gives the state per candle, not the events. **Gap:** the event list with levels and times |
| Dealing range (§5.2) | `frame_state.dealing_range` (swing-anchored) | **Gap:** the previous-candle and displacement ranges, and range validity |
| Premium/discount (§5.3) | `DealingRange.position/zone` (0.45/0.55) | **Gap:** the deep zones (0.25/0.75) |
| Pools and gaps as objectives (§5.4) | `frame_state._objectives` (swings, previous candle, FVG near edges); `_Later.taken` | **Gap:** EXTERNAL/INTERNAL/TEMPORAL typing, status, significance and ranking |
| Equal highs/lows | `measures.equal_highs` | Bearish side; mirrored for lows |
| Sessions (Asia) | `frame_state` `asia=`; `liquidity_engine.utils.time_utils` killzones | H1 only |
| PD arrays (§6) | `frame_state._arrays` (FVG, OB, BREAKER both ways, from `measures`) | **Gap:** §6.2's evaluations (displacement, after-sweep, mitigation, invalidation, alignment) |
| CISD (§7) | `algo_research.sequence.cisd` (the trader's run-open rule); `measures.bearish_cisd` | `sequence.cisd` takes DataFrames; a thin array adapter is added |
| Turtle soup / sweep-and-close-back | `algo_research.sequence.soups` | |
| Delivery phase (§7.2) | `algo_research.phases.label_phases` (consolidation, expansion, retracement, reversal) | |
| Trend (LE-D15) | `frame_state._trend` | The §16.4 simple HTF filter |
| Time (§8) | `liquidity_engine.utils.time_utils`, `zoneinfo` | |
| News (§8.1) | `algo_research.calendar` (MT5 calendar to 2026-10-16) | Live context only: no history before 2026 |
| Volatility | `phases` (ATR, tight box) | ADR from D1 |
| Held state, delivered/invalidated (§10) | `algo_mind.dis` (`states`, `state_at`, `DirectionalState`) | Reader v0's: its end rules are reused |
| Race and matched control (§16) | `algo_research.search_narrative.race/control_share` (H-AE) | The same scorer, so H-AF and H-AE are comparable |
| Setup engine boundary (§12) | `agent.order_intent` THESIS mode (`theses`, `_context_ended`) | The contract enters through a thesis file; no engine change |
| Paper agents | `scripts/run_live_agent.py`, `config/backtests/focus.toml` | |
| Shadow page | `algo_research/replay/context.py`, `static/context.*` | |

**Not built, and kept out (§14):** the knowledge graph, AlgoRAG retrieval and an event bus. The object layer (`LiquidityMap`, pydantic) is too slow to replay 27 years at every close. AlgoMindDIS reads the array layer above, which applies the same rules (`frame_state` documents the engine's rules it mirrors).

**The integration contract:** frames in (`Candles` per timeframe at t), `DirectionalBiasOutput` out. The setup engine sees only the thesis file (Requirement 13.3).

## Package

```
algomind_dis/
  __init__.py      VERSION = "v1", CONTRACT = "1.0.0"
  settings.py      every weight and threshold (frozen as v1)
  records.py       the records of Requirement 2, to_json/from_json
  frames.py        bars → Candles per timeframe, closed by t
  analyzers/
    structure.py   swings, BOS/MSS events, structural direction
    ranges.py      SWING, PREVIOUS, DISPLACEMENT ranges; positions and zones
    objectives.py  typed, statused, ranked objectives
    arrays.py      ArrayContext
    delivery.py    DeliveryState
    context.py     time and volatility
  evidence.py      items, correlation control, scores
  narrative.py     MarketNarrative and its templates
  state.py         the state machine and the timeline
  contract.py      DirectionalBiasOutput, qualify, the thesis adapter
  replay.py        history, H-AF's cells, the §16 report
```

## Decisions

| # | Decision | Why |
|---|---|---|
| DIS-D1 | A new package, `algomind_dis/`, beside `algo_mind/` | §4's own structure. `algo_mind.dis` keeps reader v0's state; the new package reuses its end rules |
| DIS-D2 | The array layer (`frame_state`, `measures`, `trend`, `sequence`, `phases`) is the detection boundary | It applies the engine's rules on arrays and replays decades in minutes. The object layer can't |
| DIS-D3 | D1 is the primary timeframe; W1 and MN1 are context. H4 and H1 join live and on the intraday snapshot | §11. The 27-year history is daily, so H-AF tests the D1-and-above service |
| DIS-D4 | The state steps only at D1 closes | §10.3's hysteresis at the primary frame. Lower frames add evidence and can't move the state (§11.2) |
| DIS-D5 | v1's settings are §9.4's starting weights and Requirements 4-12's bounds, frozen before H-AF | §9.4 calls them experimental. Tuning them on the test window would make the test meaningless |
| DIS-D6 | Significance is timeframe × type, never distance | §5.4: "the nearest pool is not automatically the draw". The nearest pool tested as a random walk |
| DIS-D7 | Correlation control by source event: candles that produce several observations (a displacement's BOS, FVG and range) share one id, and count once per direction at their greatest significance | §9.3 |
| DIS-D8 | The thesis file is the only way into the setup engine | Requirement 13.3, §19.8: with DIS off, nothing changes |
| DIS-D9 | The state is rebuilt by replay. Files are records, not memory | §15's recovery without a database. Idempotent by construction |
| DIS-D10 | H-AF uses H-AE's scorer, window and pass rule | The two held-state sources can be compared like for like |
| DIS-D11 | Reader v0 keeps the paper agent until a version passes H-AF | The trader's choice, 2026-11-03 |

## Correctness Properties

1. **No look-ahead:** the output at t is identical with or without any bar closing after t.
2. **Determinism:** the same bars and settings give the same records, ids and timeline.
3. **Hysteresis:** a lower-timeframe observation never changes the state.
4. **Ends:** an ACTIVE side ends at the first D1 close beyond its protected level, or the first touch of its draw, or its 20th close; a wick beyond the protected level doesn't end it.
5. **Correlation:** duplicating an observation with the same source event doesn't change S_B or S_S.
6. **Mirror:** mirrored bars (prices negated) give the mirrored side, ranges, objectives and state.
7. **Boundary:** with DIS_DISABLED or on any exception, the setup engine's orders are unchanged.

## Testing Strategy

- **Unit tests per analyzer** on hand-made bars (`backend/tests/test_algomind_dis_*.py`). The mirror property is checked for each.
- **Scenario tests A-G** (§17.4, Requirement 17) on hand-made multi-timeframe bars.
- **Property tests:** no look-ahead (truncate after t) and determinism, with Hypothesis on random walks. `@settings(max_examples=100)`; the slow ones are marked `slow`.
- **Contract tests:** JSON round-trip, `contract_version`, the thesis file's format read by `agent.order_intent.theses`.
- **One fixture from the real market:** the Exness GBPUSD H1 fixture (2026), already used by the reader's tests.
