# Design Document

**Spec**: Thesis Engine
**Requirements**: `.kiro/specs/thesis-engine/requirements.md`

## Overview

A new package, `thesis_engine/`, with one machine per market. It is stepped by events: each frame's candle close, and each fill or exit of its own order. The state at t is every event up to t folded through one pure `step`. So a replay and a restart are the same computation, and a paper agent runs the same code with live bars and a paper broker.

The thesis is the outer state, and the stages (at a level, armed, in a trade, spent) live inside it, so the end of the thesis ends them all. Direction only ever comes in with a thesis.

**Where it sits.** In the trader's AlgoMindDIS architecture (§3) this is the Setup Engine. The detection layer detects, and AlgoMindDIS interprets and holds the side. This engine takes the side and the detections as they are, and decides only where, when and how to enter.

```
liquidity_engine.context      detects: arrays, swings, blocks (the inverted FVG is added here)
  → algomind_dis.analyzers    interpret: objectives, arrays in context, ranges, structure (V2: the trader's arrays)
  → algomind_dis.state        the side, one step per D1 close → DirectionalBiasOutput 1.0.0
  → thesis_engine             the thesis (DIS / CALL / FILE / research) · the book as of t · level · time · hand · order
  → FillModel / paper broker  → risk, unchanged
```

## Architecture

```
M1 bars (snapshot / terminal)
  → thesis_engine.clock     candles per frame on the market's New York calendar; one event per close
  → thesis_engine.book      pools, arrays, dealing ranges: objects with ids and a life, updated per close
  → thesis_engine.thesis    the contract and its ends; sources CALL, FILE, ORACLE / MIRROR / RANDOM
  → thesis_engine.levels    the side's levels and their scores
  → thesis_engine.machine   step(state, event) → state, transitions, intents        (pure)
  → thesis_engine.orders    intents → skips or SimOrders → agent.brokers.fill_model (shared)
  → thesis_engine.journal   transitions, intents, skips, trades (JSON lines)
  → thesis_engine.replay    the loop over a snapshot; H-AG's arms and report
  → Noculus                 the "Thesis Engine" layer on the engine chart
```

**The loop.** A replay runs it as below. Paper differs only in where the bars and the fills come from.

```
for bar in M1 bars, oldest first:
    for order in open orders:
        for fill in FillModel.step(order, bar):
            state, transitions, intents = step(state, fill)
    for candle in clock.closed_at(bar):            # highest frame first (TE-D2)
        book.update(candle)
        state, transitions, intents = step(state, Close(candle))
        journal(transitions); place(intents)       # an order acts from the next bar
```

Theses go live and end inside `step`, from the source's records and the book.

## Phase 0: What Exists, and What Is Reused (Requirement 1)

| Need | Existing code | Use |
|---|---|---|
| M1 bars | `data/research/snapshots/mt5-m1-develop` (the nine focus markets, 2021-07-16 to 2022-12-30); `mt5-m1-2026-10` (XAUUSD, UK100, US100, US500, GER40, 2026-02-15 to 2026-10-23); the terminal (Noculus sessions) | Read as they are. EURUSD and GBPUSD for October 2026 come from a fresh terminal export |
| The New York calendar | `liquidity_engine.utils.time_utils` (the 17:00 day open, `KILLZONE_WINDOWS`); `services/market_data/strategy_calendar.py` | **New:** the clock. The indices' day opens at 18:00 (the trader's H4 clock), and the strategy calendar has one 17:00 open |
| Liquidity objectives | `algomind_dis.analyzers.objectives`: swings, previous candles, equal highs and lows, gaps; typed EXTERNAL, INTERNAL or TEMPORAL; SWEPT or MITIGATED, with the time | Reused as the book's pools |
| PD arrays | `algomind_dis.analyzers.arrays` on V2 (`frame_state._arrays`: FVGs as the gap; order blocks and breakers by the trader's rule, `liquidity_engine.context.blocks`), dated, with mitigation and invalidation | Reused as the book's arrays. **Gap:** the inverted FVG, added to the array layer |
| Dealing ranges | `algomind_dis.analyzers.ranges` (SWING, PREVIOUS and DISPLACEMENT, each with its validity; zones at 0.45 and 0.55) | Reused |
| Structure and swings | `algomind_dis.analyzers.structure` (the engine's swings, lookback 2; BOS and MSS); `algo_research.atlas.swings` (the trader's three candles) | Reused. The lookback is a decision for the trader |
| Reading as of t | `algomind_dis.observe.prepare`: each frame's history read once, with dated objects filtered by t | The book's as-of view |
| The E frame's CISD | `liquidity_engine.context.blocks.runs` | The hand's CISD |
| The side from AlgoMindDIS | `algomind_dis.contract` (`output`, `thesis_entry`, `qualify`); `algomind_dis.state` (`Held`, TRANSITIONAL, stale) | The DIS source |
| Levels | `liquidity_engine.context.levels` (Requirement 34, read from the old engine's `PDArray`s) | The same characteristics, rebuilt on the book's objects, on the thesis's side only |
| The thesis | `agent.context_calls` (`Call`, `ContextBook`, `week_open`, `week_close`, `thesis_table`); `agent.order_intent.theses` and `_context_ended` | CALL and FILE read through them. The ends match `_context_ended` |
| Fills and costs | `agent.brokers.fill_model` (`FillModel`, `SimOrder`, `Bar`, `swap_nights`); `agent.broker_profiles.load_profile`; H-N's spread rule (`algo_research.search_crt`) | Reused as they are |
| The week's real side | the both-sides decomposition (the New York W1 close against its open) | A few lines in `thesis_engine.thesis` |
| The chart | `algo_backtester/watch.py` (`WatchSession`, `/api/watch/*`); `algo_research/replay/static/engine.js` (the AlgoMindDIS layer of task 407 is the pattern) | A new layer and route |
| **Not reused** | `LiquidityMappingEngine`, `SetupSequenceDetector`, `SetupGrader`, the order policy's vetoes | The old decision path, which this replaces |

## Components and Interfaces

```
thesis_engine/
  __init__.py     VERSION = "v1"
  __main__.py     python -m thesis_engine replay | scenario
  settings.py     Settings (frozen); V1
  records.py      the records below; to_json / from_json
  clock.py        Clock(market, frames, day_open).push(bar) → [Candle closed at the bar's close], highest frame first
  book.py         Book(market, frames, settings).at(t): AlgoMindDIS's objectives, arrays, ranges and structure as of t;
                  .changes(t0, t1): their status changes; .e_swings(t), .e_runs(t): the E frame's
  thesis.py       ends(thesis, book, t) → (end, reason) | None; calls(path), thesis_file(path), dis(timeline, mode),
                  oracle(bars, market, kind="ORACLE" | "MIRROR" | "RANDOM", seed), complete(side, book, t)
  levels.py       levels(thesis, book, t) → [Level], best first
  machine.py      step(state, event, ctx) → (state, [Transition], [Intent]); TABLE (the allowed transitions)
  orders.py       order(intent, spread, settings) → SimOrder | Skip
  journal.py      Journal(dir).write(record); read(dir)
  replay.py       replay(market, bars, theses, settings, profile) → Journal; hag(window) → report
```

- **`step` is the only place a state changes.** It reads the event, the book and the theses, and returns the new state with what changed and why.
- **`ctx`** carries the book, the market's theses in time order, the settings and the typical spread. It holds no state of its own.
- **Events:** `Close(frame, candle)` from the clock, and `Fill(order_id, FillEvent)` from the fill model.
- **The Noculus layer** calls `replay` on a session's bars with a chosen source, and draws the journal (`/api/watch/thesis`).

## Data Models

All records are frozen dataclasses. Times are UTC nanoseconds, prices floats, and ids are stable hashes of the content that defines the record.

- **Thesis:** `id, market, side, draw, protected, since, until, source, note`.
- **Pools, arrays, ranges and structure:** AlgoMindDIS's records as they are (`algomind_dis.records`: `LiquidityObjective`, `ArrayContext`, `DealingRange`, `PricePosition`, `StructureEvent`), with their ids and dates. The book adds no fields.
- **Level:** `array_id, low, high, score, reasons`.
- **Hand:** `pool_id, swept_at, extreme, run_open, run_first_at, cisd_at`.
- **Intent:** `market, thesis_id, level_id, side, kind (MARKET | LIMIT), entry, stop, target, at`.
- **Skip:** `intent, reason (STOP_TOO_SMALL | TARGET_TOO_CLOSE | BUDGET)`.
- **Transition:** `market, t, from, to, reason, frame, thesis_id, level_id, pool_id, order_id`.
- **Trade:** the fill model's `SimOrder` at its close, with gross and net R and the costs.
- **State:** `name, thesis_id, level_id, hand, order_id, entries_today, entries_thesis, day`.

## The State Machine (Requirement 5)

**At each event, in this order:**
1. **The thesis.** A newer one goes live (the live one ends as REPLACED), or the live one ends (DELIVERED, INVALIDATED, EXPIRED). An end goes to FLAT.
2. **The trading day.** At a new day's open the day's budget resets, and SPENT returns to THESIS if the thesis has entries left.
3. **A fill event.** The open order filled, closed or was rejected: IN_TRADE → SPENT, or THESIS.
4. **A close event.** In THESIS, AT_LEVEL or ARMED: look after the level, the window and the hand.

| From | To | When | The reason as journaled (example) |
|---|---|---|---|
| FLAT | THESIS | a thesis goes live | "CALL, bullish: draw 1.09500, protected 1.08200 (week of 2 Nov)" |
| THESIS | AT_LEVEL | an E candle trades into a level of the side | "at the H1 bullish FVG 1.08610-1.08680 (score 3)" |
| AT_LEVEL | THESIS | the level fails, or price moves away | "an H1 close 1.08550 through the level's far edge 1.08610" |
| AT_LEVEL | ARMED | the window opens, or price reaches the level inside it; never while a DIS side is TRANSITIONAL or the data is stale | "00:00 New York: Q2 opened" |
| ARMED | AT_LEVEL | the window closes with no hand in progress, the DIS side turns TRANSITIONAL, or the data goes stale | "12:00 New York: the window closed without a hand" |
| ARMED | THESIS | the level fails, or price moves away, while armed | "an H1 close 1.08550 through the level's far edge 1.08610" |
| ARMED | IN_TRADE | the hand completes and the order passes the risk rules | "M5 took the 04:10 swing low 1.08590, then closed above the run's open 1.08630 (CISD): buy at market, stop 1.08560, target 1.09500 (12.6R)" |
| IN_TRADE | SPENT or THESIS | the order closes or is rejected | "stopped at 1.08560 (−1.0R)" |
| IN_TRADE | AT_LEVEL | the order is rejected (it opened beyond the stop or the target) | "rejected: the open was beyond the stop or the target" |
| SPENT | THESIS | a new trading day, with entries left on the thesis | "a new day: 1 of 2 entries left" |
| any | FLAT | the thesis ends | "delivered: the draw 1.09500 traded at 09:41" |

A skipped order (a stop under 10 spreads, a draw under 2R, or the budget used) is journaled with its reason and changes no state.

## Decisions

- **TE-D1. Direction is an input.** Only a thesis gives a side. With no thesis the machine is FLAT and reads nothing but the clock and the book.
- **TE-D2. One instant, highest frame first.** Candles closing together are stepped from the highest frame down, so the E frame's step sees the D1, H4 and H1 candles that closed at the same time.
- **TE-D3. Closed candles only.** A candle exists from its close. The forming candle is never read. The old engine's default still reads it (`engine.py`, the `else` branch at the array detector).
- **TE-D4. The definitions are the detection layer's,** read through AlgoMindDIS at V2, and they are the trader's:
  - an FVG is the gap, its CE and its time;
  - an order block is the CISD run's bodies, with the MT at their midpoint;
  - a close through ends or inverts an array;
  - a wick beyond a level is liquidation, not an end;
  - the swing's lookback is the trader's decision: three candles, or the analyzers' 2.
- **TE-D5. Levels** are Requirement 34's characteristics, on the thesis's side only and inside the thesis's range (between the protected level and the draw).
- **TE-D6. The window** is Q2-Q3, 00:00-12:00 New York: the trader's quarters and the levels gate's window. The killzones alone (London 02:00-05:00, New York AM 07:00-10:00) would miss two of the trader's own samples:
  - the GBPUSD 29 Oct Judas swing bottomed at 05:27;
  - the UK100 15 Oct entry filled at 01:51.
- **TE-D7. The hand:**
  - a sweep of an E swing low, or of the previous H1 candle's low, at the level, inside the window;
  - then the E frame's CISD within 12 candles;
  - a market entry at the CISD close, with the stop at the sweep's extreme.
- **TE-D8. Risk:**
  - the stop at least 10 typical spreads (skip, don't widen);
  - the draw at least 2R away;
  - one filled entry per market per trading day, and two per thesis.
- **TE-D9. Exits:** the stop, the draw, or the thesis's `until`. V1 has no break-even or partial; both changed the shape of the results, not the sign (2026-10-27).
- **TE-D10. The completion rule** is for the research sources only (Requirement 4.4). It takes the nearest pools because H-AF's far draw (a median 14 ADR away, against a protected level at 0.7 ADR) made every race lopsided. It is not a claim about the draw: for the trader's calls and AlgoMindDIS, the draw is theirs (§5.4).
- **TE-D11. The market's calendar:** the day opens at 17:00 New York for FX, gold and DXY, and at 18:00 for the indices.
- **TE-D12. The ladder:** T is W1, L is D1, H4 and H1, and E is M5. M5 can form the trader's sequence where M15 can't (tasks 342-344). M1 is a companion.
- **TE-D13. V1 is frozen at the trader's review** (task 414). After that, a change is V2 and a new registration.
- **TE-D14. The development window stays unread** until H-AG is registered. Before that, the code runs only on hand-made bars and on October 2026 bars (the scenarios).
- **TE-D15. No re-detection** (AlgoMindDIS §19.2). The book is an as-of view over AlgoMindDIS's analyzers, and a missing detection is added to the detection layer. This replaces the first draft's own detection, before any code (task 408).
- **TE-D16. AlgoMindDIS's contract is a source.** ACTIVE gives a thesis, TRANSITIONAL arms nothing new, and any other state ends it. Its activation modes (§18, Phase 7) decide whether orders are placed.
- **TE-D17. The live feed** (§13.3): repeated or out-of-order bars are dropped, the forming bar is never read, and stale data arms nothing.

## Decisions for the Trader

The defaults above stand until the trader answers.

1. **The budget:** one filled entry per market per day and two per thesis, or strictly one shot per thesis?
2. **The exit:** hold to the draw until the thesis's `until` (the week's close for a weekly call), or close at the day's close (17:00 New York)?
3. **The window:** Q2-Q3 (00:00-12:00 New York), or only the London and New York AM killzones that the trader's journal names?
4. **The stop floor:** 10 typical spreads, the floor the data supports (stops under 8 spreads lost in every market out of sample). The trader's GBPUSD 29 Oct stop was about 7 Exness spreads, so the floor would have skipped it.
5. **The execution frame:** M5, or M1?
6. **The entry:** at market at the CISD close, or a limit at the run's MT (the trader's OB entry)?
7. **The name:** "Thesis Engine" is a working name. In AlgoMindDIS's architecture (§3) this is the Setup Engine.
8. **Countertrend:** never against the side (the 2026-10-29 rule), or also AlgoMindDIS's justified countertrend (§12.1: a target inside the D1 range, from an opposing higher-timeframe array, after a sweep)?
9. **The swing:** three candles (the trader's, 2026-10-16), or the analyzers' lookback of 2? Three candles would become part of AlgoMindDIS V2, which is still untested, so no registered test changes.

## Correctness Properties

Each property is a test. "Hypothesis" means a property-based test with the `hypothesis` library.

### Property 1: Only the Past
*For any* bars and cut t (Hypothesis), the state, the book and the journal at t SHALL equal those of a run on the bars before t only.
**Validates: Requirements 2.1, 3.4**

### Property 2: Determinism
*For any* bars and theses, two runs SHALL write the same journal, byte for byte.
**Validates: Requirements 2.4, 10.3**

### Property 3: A Restart Is a Replay
*For any* cut t, a run stopped at t and resumed from its saved state SHALL write the same journal as an uncut run.
**Validates: Requirements 2.4, 11.3**

### Property 4: The Book Equals the Analyzers
*For any* random walk with dojis and any cut, the book's objectives, arrays, ranges and structure SHALL equal AlgoMindDIS's analyzers run on the candles closed by the cut.
**Validates: Requirements 3.4**

### Property 5: The Mirror
*For any* bars, the bars turned upside down with the mirrored thesis SHALL give the mirrored journal.
**Validates: Requirements 6.1, 8.1, 8.2**

### Property 6: The Table Is Closed
*For any* sequence of events, every transition SHALL be a row of `TABLE`.
**Validates: Requirements 5.4**

### Property 7: The Side Is the Thesis's
*For any* run, no intent SHALL be placed while FLAT, none against the live thesis's side, and the market SHALL never hold both sides.
**Validates: Requirements 4.5, 9.4**

### Property 8: The Budget Holds
*For any* run, the filled entries SHALL number at most one per market per trading day and two per thesis.
**Validates: Requirements 9.4**

## Error Handling

- **Gaps in the bars** (weekends, holidays, a feed outage): the clock makes no candle for an empty period, and the machine sees no event. A thesis whose `until` passes during a gap expires at the first event after it.
- **A thesis that fails its checks** (the protected level on the wrong side of the draw, a missing price): it is refused with the reason, journaled and counted, and the state is unchanged.
- **The completion rule finds no draw or no protected level:** no thesis that week, counted (Requirement 4.4).
- **An order the fill model rejects** (it opened beyond the stop or the target): the entry is not counted against the budget, and the machine returns to AT_LEVEL with the reason.
- **A level of zero height, or a range with no swing:** not a level, and no zone. Neither is an error.
- **A saved state from another version:** refused. A resume needs the same `VERSION` and settings.
- **Repeated, out-of-order or revised bars** (§13.3): dropped and journaled. The forming bar is never read.
- **Stale data:** nothing new is armed until bars resume. An open order is unaffected.
- **AlgoMindDIS unavailable or failing:** no DIS thesis. The engine keeps its other sources, and nothing else changes (§19.8).

## Testing Strategy

- **The clock:**
  - candles on hand-made bars, at both day opens, with daylight-saving changes and weekend gaps;
  - each candle emitted once, at its close, highest frame first;
  - cut-and-resume.
- **The book:**
  - Property 4 against AlgoMindDIS's analyzers at every cut;
  - the inverted FVG on hand-made bars, in the array layer's own tests;
  - the E frame's swings and runs.
- **The thesis:**
  - the contract's checks;
  - each end, including a wick beyond the protected level that is not an end;
  - CALL and FILE read the formats that exist;
  - the completion rule's choices and its counted refusals;
  - ORACLE and MIRROR are opposite every week;
  - the DIS source: ACTIVE, TRANSITIONAL and each end, under each activation mode.
- **The machine:**
  - each row of the table with its reason, and Property 6;
  - the hand's sweep, CISD and failure;
  - each skip;
  - Properties 5, 7 and 8.
- **The replay:** Properties 1-3, and the live feed's repeated, out-of-order and stale bars.
- **Scenarios** (task 414): the trader's October 2026 trades, each with their call, drawn on the layer and judged by the trader.
- **Speed target:** one market's 18 months of M1 in under two minutes, one market at a time (the PC's memory limits).

## What It Can and Can't Show

- **It can show:**
  - whether the trader's order of work, run as rules, turns a right side into R (H-AG);
  - how often it waits, and why;
  - where it differs from the trader's own trades (the scenarios);
  - once an AlgoMindDIS version passes its own test, whether its side, run through this machine, pays.
- **It can't show an edge on its own.** Its side comes from a source. A pass on H-AG says the machine is ready for a side. The trader's blind calls, at about 300, say whether their read gives that side.


## Update 2026-11-05b: V2 (Requirements 15, 16)

V2 is `thesis_engine.settings.V2`, a copy of V1 with six settings changed. The machine reads them, so V1 runs exactly as it did.

| Setting | V1 | V2 |
|---|---|---|
| `hand_pools` | `"M5_SWINGS"` (E swings and the previous H1 extreme) | `"TRADER"` (PDL, the Asia low, the previous H4 and H1 lows, untaken H1 swing lows) |
| `displacement_body` | `0.0` | `1.5` (times the M5 average range of 20 candles) |
| `entry` | `"MARKET"` (at the CISD close) | `"LIMIT_MT"` (the CISD run's bodies' midpoint) |
| `limit_minutes` | — | `60` (and at least to the window's end) |
| `stack_min_frames` | `1` | `2` (or a D1 array) |
| `level_tiebreak` | `"ID"` (the array's content id) | `"FRAME"` (the higher frame, the tighter zone, the latest formed) |

- **TE-D18. The pools are the trader's liquidity,** not M5 swings: the previous day's and the previous H4's and H1's extremes, the Asia range and the H1 swings. These are the pools their manipulation takes (the Judas swing under the Asia low, the London sweep of the previous H4, the news sweep of equal highs).
- **TE-D19. Displacement** is Model A §10's default: a body of 1.5 times the frame's average range. Without it a 0.1-point close through counted as a CISD.
- **TE-D20. The limit at the run's MT** is the trader's answer of 2026-10-28: the order block is the whole series, and its MT is the entry for a large series. The stop stays beyond the manipulation's extreme, so the risk is smaller than V1's market entry.
- **TE-D21. Expiry** is the trader's rule of 2026-10-02: a pending limit expires at the end of the killzone, here the window's end, and never sooner than 60 minutes after it is placed.
- **TE-D22. The stack gate** follows the post-hoc check on H-AG's trades: on the right side, heavy stacks made +0.99R a trade and thin ones +0.59R. That look was on the development data, so H-AH's development run favours V2. Only the test window can confirm it.
- **TE-D23. Management stays a companion.** The 2026-10-27 replay found that management changes the shape of results, not their sign.
- **TE-D24. Ties between levels go to the higher frame,** then the tighter zone, then the latest formed. V1 broke ties by the array's content id, a hash that differs in a mirrored market, so V2's mirror test chose another level and diverged. The higher frame first follows the trader's rule that the higher frame outweighs the lower. It was added after H-AH's registration and before its run, and is recorded there as an amendment.


## Update 2026-11-06: V3 (Requirements 17, 18)

V3 is `thesis_engine.settings.V3`: a copy of V2 with the settings below. The machine reads them, so V1 and V2 run exactly as they did.

| Setting | V2 | V3 |
|---|---|---|
| `e_frame` | `"M5"` | `"M1"`: the machine steps on M1 closes |
| `exec_child` | `""` (the hand on the E frame) | `"POOL"`: the hand on its pool's child frame |
| `exec_frames` | `()` | `("M30", "M20", "M15", "M10", "M5", "M3", "M1")` |
| `swing_pools` | `()` | `("M30", "M15")`: their untaken swings are pools too |
| `run_slack` | `0` | `1`: the run into the sweep may end one child candle before the sweep's |
| `entry` | `"LIMIT_MT"` | `"NEAR_MT"`: at market when the close is near the MT, else a limit at it |
| `near_mt` | — | `0.5` (child average ranges) |

- **TE-D25. The frame follows the pool.** This is the trader's choice of 2026-11-06, and their rule that a turtle soup is valid when the parent's child frame confirms a CISD.
  - The child is the largest execution frame no longer than a tenth of the pool's frame.
  - H1 → M5 is their GBPUSD diary: an H1 turtle soup confirmed by an M5 CISD.
  - D1 → M30 is the top of their list. Their own D1 turtle soup is confirmed on H1, a twenty-fourth.
- **TE-D26. A larger pool takes the hand over.** The trader frames the biggest liquidity taken. A small pool's hand waiting when the Judas swing takes the Asia high becomes the Asia hand on M30, with its stop beyond the whole swing.
- **TE-D27. The run into the sweep may end one candle before the sweep's.** On M30 the sweep and the rejection often sit in one candle, a wick. V2's rule would wait for a second run.
- **TE-D28. The entry follows the trader's words.** It goes at market when price is around the entry level and as a limit when price has traded away from it. "Around" is half the child frame's average range. The number is mine; theirs is "around".
- **TE-D29. M1 is the step.** Every child candle is read at its own close, and pools are taken at the minute.
- **TE-D30. The bias.** V3 follows V2's development results and my review of five weeks on Noculus, four of them chosen because V2 traded them. H-AI's development run favours V3. Only the test window can confirm it.


## Update 2026-11-06b: V4 (Requirements 19, 20)

V4 is `thesis_engine.settings.V4`: a copy of V3 with the settings below. V1, V2 and V3 run exactly as they did.

| Setting | V3 | V4 |
|---|---|---|
| `exec_frames` | `("M30", "M20", "M15", "M10", "M5", "M3", "M1")` | `("M30", "M15")`: the setup frames |
| `child_map` | `()` (a tenth of the pool's frame) | D1, the Asia range and H4 → M30; H1 → M15 |
| `swing_pools` | `("M30", "M15")` | `()` |
| `entry` | `"NEAR_MT"` | `"REFINED"`: market on the refining frame's CISD inside the order block |
| `refine` | `()` | M30 → M3, M15 → M1 |

- **TE-D31. Setups live on M30 and M15 only.**
  - This is the trader's rule of 2026-11-06: the lower frames are for entries and their refinement, never for deciding that the manipulation is over.
  - H-AI agreed after the run: every H1 → M5 hand lost, on either side.
  - Answering the trader's question that day: the engine never takes its side from M5. The side is the thesis's. "Either side" in H-AI was the MIRROR control.
- **TE-D32. The setup frame by the pool's size** (the trader's choice): the previous day, the Asia range and the previous H4 → M30; the previous H1 and H1 swings → M15.
- **TE-D33. The refined entry** (the trader's choice): the pull-back into the setup's order block, then an M3 or M1 CISD back the thesis's way, at market.
  - It fills only once price turns the thesis's way. That answers H-AI's adverse fills.
  - M3 for M30 and M1 for M15 are the trader's Model A sets, (H4, M15/M30, M3/M1).
- **TE-D34. The stop is beyond the setup's sweep** (the trader's choice). The M5 sweep's extreme lost on every trade in V3. The refined entry is where the R comes from.
- **TE-D35. The year that judges** is July 2025 to June 2026 in `focus-2025-2026h1`.
  - No version of the Thesis Engine has run on it. The five weeks I viewed on Noculus in 2025 come before it.
  - The bars are read from 1 January 2025, so nothing of 2023-2024 is read, and the 2026-07-07 hold-out of the old engine's study is after it.
  - 2021-22 is reported but no longer judges. V4 was shaped by H-AI's results there.


## Update 2026-11-06c: V5 (Requirements 21, 22)

V5 is `thesis_engine.settings.V5`: V1 with two settings changed. V1 to V4 run exactly as they did.

| Setting | V1 | V5 |
|---|---|---|
| `window` | `(0, 12)` | `(2, 4)`: New York hours, Monday to Friday |
| `entry_in_window` | `False` (a hand may complete after the window closes) | `True`: a hand completes only inside the window and ends when it closes |

- **TE-D36. The London window comes from ICT's daytrade model,** which the trader shared on 2026-11-06. It is the only one of five rules (H-AK) that held on the unseen year. Its hands are no more often on the right side, but with the right side they pay more (+1.12R against +0.49R). It is also inside the trader's own Q2, the manipulation quarter.
- **TE-D37. The hand completes inside the window.** That is what the filter kept: entries between 02:00 and 04:00. V1's rule, letting a hand finish within 12 candles after the window, would have let entries run to 05:00.
- **TE-D38. One run on 2023-2024 judges both V5 and V1.** V1's run there has been owed since H-AG's pass.
