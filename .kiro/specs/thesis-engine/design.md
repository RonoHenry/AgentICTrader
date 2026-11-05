# Design Document

**Spec**: Thesis Engine
**Requirements**: `.kiro/specs/thesis-engine/requirements.md`

## Overview

A new package, `thesis_engine/`, with one machine per market. It is stepped by events: each frame's candle close, and each fill or exit of its own order. The state at t is every event up to t folded through one pure `step`. So a replay and a restart are the same computation, and a paper agent runs the same code with live bars and a paper broker.

The thesis is the outer state, and the stages (at a level, armed, in a trade, spent) live inside it, so the end of the thesis ends them all. Direction only ever comes in with a thesis.

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
| Three-candle swings | `algo_research.atlas.swings` (AR-D28: strict, known at the third candle's close) | The batch reference for the book's pools |
| FVGs: gap, CE, time | `algo_research.atlas.arrays`; `liquidity_engine.context.measures.bearish_fvgs` (the gap only) | The batch reference |
| Order blocks and breakers | `liquidity_engine.context.blocks` (`delivery_blocks`, `runs`): the trader's rule, at parity with `ob_rule = "cisd"` | The batch reference. The book's version, updated close by close, must equal it at every cut. `runs` also defines the hand's CISD |
| Dealing ranges | `liquidity_engine.context.frame_state.dealing_range` (lookback 2, stretched to later extremes) | The same reading on the trader's three-candle swing. **New:** updated close by close |
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
  book.py         Book(market, frames).update(candle); .pools(frame), .arrays(frame), .range(frame), .get(id)
  thesis.py       ends(thesis, book, t) → (end, reason) | None; calls(path), thesis_file(path),
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
- **Pool:** `id, market, frame, kind (SWING | PREVIOUS | EQUAL), side (HIGH | LOW), price, formed_at, taken_at`.
- **Array:** `id, market, frame, kind (FVG | IFVG | OB | BREAKER), side, low, high, mid (the CE or the MT), formed_at, ended_at, inverted_from, high_probability`.
- **Range:** `market, frame, low, high, low_at, high_at`, with `zone(price)` → PREMIUM | EQUILIBRIUM | DISCOUNT.
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
| AT_LEVEL | ARMED | the window opens, or price reaches the level inside it | "00:00 New York: Q2 opened" |
| ARMED | AT_LEVEL | the window closes with no hand in progress | "12:00 New York: the window closed without a hand" |
| ARMED | IN_TRADE | the hand completes and the order passes the risk rules | "M5 took the 04:10 swing low 1.08590, then closed above the run's open 1.08630 (CISD): buy at market, stop 1.08560, target 1.09500 (12.6R)" |
| IN_TRADE | SPENT or THESIS | the order closes or is rejected | "stopped at 1.08560 (−1.0R)" |
| SPENT | THESIS | a new trading day, with entries left on the thesis | "a new day: 1 of 2 entries left" |
| any | FLAT | the thesis ends | "delivered: the draw 1.09500 traded at 09:41" |

A skipped order (a stop under 10 spreads, a draw under 2R, or the budget used) is journaled with its reason and changes no state.

## Decisions

- **TE-D1. Direction is an input.** Only a thesis gives a side. With no thesis the machine is FLAT and reads nothing but the clock and the book.
- **TE-D2. One instant, highest frame first.** Candles closing together are stepped from the highest frame down, so the E frame's step sees the D1, H4 and H1 candles that closed at the same time.
- **TE-D3. Closed candles only.** A candle exists from its close. The forming candle is never read. The old engine's default still reads it (`engine.py`, the `else` branch at the array detector).
- **TE-D4. The trader's definitions:**
  - a swing is three candles;
  - an FVG is the gap, its CE and its time;
  - an order block is the CISD run's bodies, with the MT at their midpoint;
  - a close through ends or inverts an array;
  - a wick beyond a level is liquidation, not an end.
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
- **TE-D10. The completion rule** for side-only sources (Requirement 4.4) takes the nearest pools. H-AF's far draw (a median 14 ADR away, against a protected level at 0.7 ADR) made every race lopsided.
- **TE-D11. The market's calendar:** the day opens at 17:00 New York for FX, gold and DXY, and at 18:00 for the indices.
- **TE-D12. The ladder:** T is W1, L is D1, H4 and H1, and E is M5. M5 can form the trader's sequence where M15 can't (tasks 342-344). M1 is a companion.
- **TE-D13. V1 is frozen at the trader's review** (task 414). After that, a change is V2 and a new registration.
- **TE-D14. The development window stays unread** until H-AG is registered. Before that, the code runs only on hand-made bars and on October 2026 bars (the scenarios).

## Decisions for the Trader

The defaults above stand until the trader answers.

1. **The budget:** one filled entry per market per day and two per thesis, or strictly one shot per thesis?
2. **The exit:** hold to the draw until the thesis's `until` (the week's close for a weekly call), or close at the day's close (17:00 New York)?
3. **The window:** Q2-Q3 (00:00-12:00 New York), or only the London and New York AM killzones that the trader's journal names?
4. **The stop floor:** 10 typical spreads, the floor the data supports (stops under 8 spreads lost in every market out of sample). The trader's GBPUSD 29 Oct stop was about 7 Exness spreads, so the floor would have skipped it.
5. **The execution frame:** M5, or M1?
6. **The entry:** at market at the CISD close, or a limit at the run's MT (the trader's OB entry)?
7. **The name:** "Thesis Engine" is a working name.

## Correctness Properties

Each property is a test. "Hypothesis" means a property-based test with the `hypothesis` library.

### Property 1: Only the Past
*For any* bars and cut t (Hypothesis), the state, the book and the journal at t SHALL equal those of a run on the bars before t only.
**Validates: Requirements 2.1, 3.6**

### Property 2: Determinism
*For any* bars and theses, two runs SHALL write the same journal, byte for byte.
**Validates: Requirements 2.4, 10.3**

### Property 3: A Restart Is a Replay
*For any* cut t, a run stopped at t and resumed from its saved state SHALL write the same journal as an uncut run.
**Validates: Requirements 2.4, 11.3**

### Property 4: The Book Equals the Batch Rules
*For any* random walk with dojis and any cut, the book's swings, gaps, blocks, breakers and ranges SHALL equal the batch references run on the closed candles.
**Validates: Requirements 3.6**

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

## Testing Strategy

- **The clock:**
  - candles on hand-made bars, at both day opens, with daylight-saving changes and weekend gaps;
  - each candle emitted once, at its close, highest frame first;
  - cut-and-resume.
- **The book:**
  - each object's life on hand-made bars;
  - Property 4 against `atlas.swings`, the gap rule, `blocks.delivery_blocks` and `dealing_range` on the three-candle swing.
- **The thesis:**
  - the contract's checks;
  - each end, including a wick beyond the protected level that is not an end;
  - CALL and FILE read the formats that exist;
  - the completion rule's choices and its counted refusals;
  - ORACLE and MIRROR are opposite every week.
- **The machine:**
  - each row of the table with its reason, and Property 6;
  - the hand's sweep, CISD and failure;
  - each skip;
  - Properties 5, 7 and 8.
- **The replay:** Properties 1-3.
- **Scenarios** (task 414): the trader's October 2026 trades, each with their call, drawn on the layer and judged by the trader.
- **Speed target:** one market's 18 months of M1 in under two minutes, one market at a time (the PC's memory limits).

## What It Can and Can't Show

- **It can show:**
  - whether the trader's order of work, run as rules, turns a right side into R (H-AG);
  - how often it waits, and why;
  - where it differs from the trader's own trades (the scenarios).
- **It can't show an edge on its own.** Its side comes from a source. A pass on H-AG says the machine is ready for a side. The trader's blind calls, at about 300, say whether their read gives that side.
