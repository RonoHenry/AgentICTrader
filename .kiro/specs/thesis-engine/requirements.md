# Requirements Document

**Spec**: Thesis Engine (the core engine, rebuilt as a state machine)
**Asked for**: 2026-11-05. After "is our current Engine a state machine?" (no: `liquidity_engine` is stateless per close) and "how should we have built it?", the trader: "Can we try the second approach (I know we are building everything from scratch...)".

## Introduction

The liquidity engine reads every close from scratch, finds every setup with the right properties, and lets rules veto it afterwards (`liquidity_engine/engine.py`: "Stateless; safe to reuse across calls"). It never decides before it executes, so it trades both sides of one market and fires before price reaches any level (the trader, 2026-10-31 and 2026-11-02).

The trader works the other way round: one thesis or none, then the thesis's levels, then time, then the hand at the level, then one shot (thesis first; the blueprint of 2026-10-31; Model A).

The Thesis Engine is that order, built as a new core: a state machine per market, stepped by candle closes.
- **Direction comes in, never out.** A thesis (side, draw, protected level, valid from and until) arrives through one contract from a source: the trader's /context calls, a thesis file (AlgoMindDIS, reader v0), or, for research only, a hindsight or random side. With no thesis, nothing runs.
- **It waits, in stages.** At a level of the thesis's side, inside a time window, it watches the execution frame for the hand: a sweep at the level, then the execution frame's CISD. Then one order.
- **It remembers.** Each object (pool, array, range, thesis, order) is created once and carries its own life. Each change of state is recorded with its reason.

**What it isn't: a direction source.** It can't make a wrong side pay. Every test so far puts the information in the side:
- the setups alone make about 0R, and pay only when the side is known in hindsight (H-N's selection stack with the week's real side: +0.17R [−0.01, +0.35] a trade);
- with H-N's trades at stops of 10 spreads or more, a weekly call has to be right 57-60% of the time to clear costs.

So the first test (H-AG, Requirement 13) asks only how well the machine turns a right side into R. The trader's blind weekly calls (context-engine Requirement 36) measure the side.

**What a stricter machine already showed.** Model A's reader (context-engine Requirement 13) is a state machine on the trader's exact path: FRAMED → ARMED → MANIPULATED → REJECTED → DISPLACED → IN_OTE → ENTERED.
- On the 2025 exploration slice its funnel collapses: EURUSD D1/H1/M5 framed 2,607 instances and entered 5.
- So even with the day's real side it had too few fills to judge.

The trader's answer (2026-10-31, "blueprint, not template"): a level is the characteristics that line up at a price, not a fixed path. This spec follows the blueprint: location, then time, then the hand.

**Boundaries.** The liquidity engine, the backtester and the paper agents keep running unchanged. Nothing here places a live order. The Thesis Engine goes on paper only after H-AG passes and the trader says go.

## Glossary

- **Closed candle at t:** a candle whose close is at or before t. Nothing reads a candle before its close.
- **The market's calendar:** New York wall time.
  - The trading day opens at 17:00 for FX, gold and DXY, and at 18:00 for the indices (the trader's H4 clock, 2026-10-20).
  - H4 candles open every four hours from the day's open.
  - The week runs from Sunday's open to Friday's close.
- **The ladder:** the frames by role.
  - **T**, the thesis's frame (W1 for a weekly call);
  - **L**, the level frames (D1, H4, H1);
  - **E**, the execution frame (M5).
- **ADR:** the mean D1 range over the last 20 closed days.
- **Typical spread:** the market's median M1 spread over the run's window.
- **A level:** where the engine waits, an array of the thesis's side together with what supports it (Requirement 6).
- **The hand:** a sweep at the level, then the E frame's CISD in the thesis's direction (Requirement 8).

## Requirements

### Requirement 1: Boundaries and the audit

**User Story:** As the trader, I want a new core built on my definitions, so that it does what I do and nothing else changes while it is proved.

#### Acceptance Criteria

1. THE audit (design.md, Phase 0) SHALL list each piece the engine needs, with the existing code it reuses or the reason it is new.
2. THE engine SHALL live in a new package, `thesis_engine/`. `liquidity_engine/`, `algo_backtester/`, `agent/` and `algomind_dis/` SHALL run unchanged. The only addition outside the package is a Noculus layer.
3. THE engine SHALL NOT place a live order. Paper follows Requirement 14.
4. Every rule and threshold SHALL sit in one frozen, versioned settings object (V1). A change is a new version and a new registration.

### Requirement 2: The clock

**User Story:** As the trader, I want each timeframe read at its own close, so that a forming candle is never read as closed.

#### Acceptance Criteria

1. FROM M1 bars (bid OHLC and spread), THE clock SHALL build every configured frame's candles on the market's calendar and emit each candle once, at its close.
2. Candles that close at the same instant SHALL be emitted from the highest frame down, so each step sees everything closed by then.
3. A period with no bars SHALL have no candle. Weekend and holiday gaps create none.
4. THE same bars SHALL give the same events. A run stopped at t and resumed from its saved state SHALL give the same events as an uncut run.

### Requirement 3: The book, objects with a life

**User Story:** As the trader, I want pools, arrays and ranges kept as things that form, get touched, get taken or broken, so that the engine knows a level's history the way I do.

#### Acceptance Criteria

1. **Pools:**
   - three-candle swing highs and lows (the trader's swing: a candle beyond both neighbours, known at the third candle's close);
   - the previous D1, W1 and MN1 highs and lows;
   - equal highs and lows within 0.1 of the frame's average range.

   A pool is UNTAKEN until a candle trades beyond it (a wick takes it), then TAKEN, with the time.
2. **Fair value gaps:** the gap only, with its high, low, CE and the time it formed (the trader's FVG). An FVG ends when a candle of its frame closes beyond its far edge, and it inverts into an IFVG of the other side.
3. **Order blocks and breakers:** the trader's rule (liquidity-engine Requirement 31, `liquidity_engine/context/blocks.py`):
   - the zone is the CISD run's bodies, with the MT at their midpoint;
   - a block is high probability when the run took a swing and the move away left a gap;
   - a close through inverts it into a breaker;
   - a close back through ends the breaker.
4. **Dealing ranges,** per frame: from the last three-candle swing low to the last three-candle swing high, stretched to any later extreme. Premium is above 0.55 and discount below 0.45 (CE-D2).
5. Each object SHALL have a stable id (market, frame, kind, formed at) and record each change of status with its time.
6. THE book, updated close by close, SHALL equal the batch rules run on the closed candles at every cut (a property test on random walks with dojis).

### Requirement 4: The thesis

**User Story:** As the trader, I want the engine to trade only my side, with my draw and my invalidation, so that no trade is taken without context.

#### Acceptance Criteria

1. A thesis SHALL hold:
   - the market and the side (BULLISH or BEARISH);
   - the draw and the protected level;
   - `since` and `until`;
   - its source, an id and a note.

   A bullish thesis's protected level is below its draw, and a bearish one's above, as `agent.context_calls.Call` checks.
2. A thesis SHALL end at the first of:
   - **DELIVERED:** an E candle after `since` trades at or beyond the draw;
   - **INVALIDATED:** a D1 candle closing after `since` closes beyond the protected level (a wick is liquidation);
   - **EXPIRED:** `until` passes;
   - **REPLACED:** a newer thesis for the market goes live.

   These match the THESIS mode's ends (`agent.order_intent._context_ended`).
3. **Sources:**
   - **CALL:** the trader's /context calls (`agent.context_calls`). `since` is the call's and `until` is the week's close.
   - **FILE:** a thesis file in the THESIS-mode format (`{instrument: {trading date: {side, draw, protected, since}}}`), such as AlgoMindDIS's or reader v0's.
   - **ORACLE, MIRROR, RANDOM** (research only, never on paper):
     - the side is the week's real side (the New York W1 close against its open), its opposite, or a seeded coin flip;
     - the draw and the protected level come from the completion rule (4.4);
     - `since` is the week's open and `until` its close.
4. **The completion rule,** at the week's open, for a bullish side (bearish is the mirror):
   - **the draw:** the nearest untaken pool above the open and at least 0.5 ADR away: the previous week's high, a D1 three-candle swing high or D1 equal highs;
   - **the protected level:** the nearest untaken D1 three-candle swing low below the open and at least 0.5 ADR away, else the previous week's low if it is below the open;
   - **no thesis that week** when either is missing or more than 5 ADR away (counted).
5. One thesis SHALL be live per market at a time.

### Requirement 5: The state machine

**User Story:** As the trader, I want the engine to move through my stages and say why at each step, so that I can see it decide before it executes.

#### Acceptance Criteria

1. THE states SHALL be:
   - **FLAT:** no live thesis, so nothing runs (the default);
   - **THESIS:** a live thesis, with price not at a level of its side;
   - **AT_LEVEL:** price at a level of the thesis's side (Requirement 6);
   - **ARMED:** at the level and inside a time window (Requirement 7), watching the E frame for the hand;
   - **IN_TRADE:** an order from the hand is open;
   - **SPENT:** the entry budget is used (Requirement 9.4).
2. THE transitions SHALL be:
   - FLAT → THESIS when a thesis goes live;
   - THESIS → AT_LEVEL when an E candle trades into a level of the side;
   - AT_LEVEL → THESIS when the level fails (a candle of its own frame closes through its far edge), or price moves away from it by more than one average range of that frame;
   - AT_LEVEL → ARMED when a window opens, or when price reaches the level inside one;
   - ARMED → AT_LEVEL when the window closes with no hand in progress;
   - ARMED → IN_TRADE when the hand completes and its order passes Requirement 9;
   - IN_TRADE → SPENT when the order closes or is rejected, or → THESIS instead when the budget allows another entry;
   - SPENT → THESIS at the next trading day's open, when the thesis's budget allows;
   - any state → FLAT when the thesis ends (Requirement 4.2).
3. THE machine SHALL be one pure function, `step(state, event) → (state, transitions, intents)`, the same in a replay and on paper.
4. No other transition SHALL occur (tested against the table).

### Requirement 6: Levels, where it waits

**User Story:** As the trader, I want the engine to wait only where discount, a PD array, liquidity and time line up on my side, so that it stops firing before any POI.

#### Acceptance Criteria

1. A level for a bullish thesis (bearish is the mirror) SHALL be a live bullish array of an L frame (an FVG or IFVG gap, an order block's bodies or a breaker) that is:
   - between the thesis's protected level and its draw;
   - in discount: its CE below the equilibrium of the D1 or the W1 dealing range;
   - at most 1 ADR tall.

   These are context-engine Requirement 34's characteristics, kept on the thesis's side only.
2. A level's score SHALL count:
   - the L frames with an array there;
   - the ranges it is in discount of;
   - untaken sell-side liquidity within 0.1 ADR below it;
   - a high-probability block.

   The score is reported, and it picks among levels price is in at once.
3. Arrays of the other side SHALL never be levels.

### Requirement 7: Time

**User Story:** As the trader, I want the engine to look for the hand only when price delivers, so that a level touched at the wrong hour isn't traded.

#### Acceptance Criteria

1. THE window SHALL be Q2 and Q3 of the New York day, 00:00-12:00 New York wall time, Monday to Friday. These are the trader's quarters (Q2 manipulation, Q3 distribution) and the levels gate's window (context-engine Requirement 34).
2. A hand's sweep SHALL fall inside the window. Its CISD may complete after the window closes, within the hand's limit (Requirement 8.2).

### Requirement 8: The hand

**User Story:** As the trader, I want the entry to come from price showing its hand at my level on the execution frame, so that the stop sits behind the manipulation.

#### Acceptance Criteria

1. **The sweep** (bullish; bearish is the mirror): while ARMED, an E candle trades below an untaken pool at the level. The pool is an E three-candle swing low or the previous H1 candle's low, inside the level or within 0.1 ADR below it. The sweep's extreme is the lowest low from that candle until the CISD.
2. **The CISD:** within 12 E candles of the sweep, an E candle closes above the open of the first candle of the latest run of down-closing E candles that ended at or after the sweep (dojis skipped). This is the trader's CISD (`blocks.runs`).
3. **The hand fails** when 12 E candles pass without the CISD, or when the level fails. The engine then looks for a new sweep.
4. **The order (V1):**
   - at market at the CISD candle's close (the next M1 bar's open, at the ask for a buy);
   - the stop at the sweep's extreme;
   - the target at the thesis's draw.

### Requirement 9: Risk and the budget

**User Story:** As the trader, I want few, considered trades with stops the costs can't eat, so that the engine stops firing like a machine gun.

#### Acceptance Criteria

1. A stop closer than 10 typical spreads SHALL skip the order, with the reason. The stop is not widened, and the machine stays ARMED.
2. A draw closer than 2R SHALL skip the order, with the reason.
3. Each trade SHALL risk a fixed amount, and results SHALL be read in R.
4. **The budget:**
   - at most one filled entry per market per trading day;
   - at most two per thesis;
   - never against the thesis (by construction).
5. **Exits (V1):** the stop, the draw, or the thesis's `until` at market. V1 has no break-even and no partial.

### Requirement 10: The journal

**User Story:** As the trader, I want every step the engine takes written down with its reason, so that I can check any decision against the chart.

#### Acceptance Criteria

1. Every transition SHALL be recorded with:
   - the market, the time, the state it left and the one it entered;
   - the reason in plain words;
   - the frame;
   - the ids of the thesis, level, pool and order involved.
2. Every intent, every skip (with its reason) and every trade SHALL be recorded. A trade is the fill model's record: fill, exit, reason, MAE and MFE, gross and net R, costs.
3. THE journal SHALL round-trip through JSON. The same bars and theses SHALL give the same journal, byte for byte.

### Requirement 11: The replay

**User Story:** As the trader, I want the backtest and the paper run to be the same code, so that what the test shows is what paper does.

#### Acceptance Criteria

1. `python -m thesis_engine replay` SHALL run the machine over a snapshot's M1 bars with a chosen source.
2. Fills SHALL go through the shared `agent.brokers.fill_model.FillModel`.
   - Each bar's spread is the recorded one or the market's typical spread, whichever is larger (H-N's rule).
   - Slippage, commission and swap come from the broker profile.
3. THE replay and a paper agent SHALL call the same `step`. Only the source of the bars and the broker differ.

### Requirement 12: Watching it on Noculus

**User Story:** As the trader, I want to see the engine at work on the chart, so that I judge it with my own eyes before any test.

#### Acceptance Criteria

1. An engine-chart layer, "Thesis Engine", SHALL draw:
   - the live thesis: the draw dashed, the protected level solid;
   - the side's levels, with the one in use highlighted;
   - a state strip, one cell per E candle, coloured by state;
   - a mark at each transition, with its reason;
   - each hand's sweep and CISD;
   - the trades.
2. THE trader's documented October 2026 trades SHALL be replayed as scenarios, each with the call they held, and shown on the layer: UK100 15 Oct, XAUUSD 5 and 14 Oct, EURUSD 12 Oct and GBPUSD 29 Oct, with their US500 read of 14 Oct.
   - Where the trader's notes don't give the call, the trader is asked.
   - They are checks that the engine reads like the trader, not evidence.

### Requirement 13: H-AG, the conversion test

**User Story:** As the trader, I want to know whether the machine turns a right side into money before any of my calls depend on it.

#### Acceptance Criteria

1. H-AG SHALL be registered in `docs/research/SEARCH_2018_2024.md` with V1's settings, after the trader's review on Noculus (Requirement 12) and before anything reads the development window.
2. **The arms:**
   - ORACLE, MIRROR and RANDOM sides (Requirement 4.3), all with the same completion rule and the same V1 machine;
   - the eight traded focus markets: XAUUSD, EURUSD, GBPUSD, US100, US500, US30, GER40 and UK100;
   - 2021-07-16 to 2022-12-30 (`mt5-m1-develop`).
3. **Pass:**
   - ORACLE's net R per trade is above zero, with its 95% interval (resampling weeks) above zero;
   - it is positive in at least 6 of the 8 markets;
   - the break-even weekly hit rate, −MIRROR / (ORACLE − MIRROR), is at most 60%.
4. **Not a try.** Its side is hindsight, so it can't show an edge. It measures the machine's ceiling, and it is registered so that V1 isn't tuned on its result.
5. **Reported beside it, not judged:**
   - RANDOM;
   - trades per market-week;
   - the funnel: theses, at a level, armed, hands, orders, fills;
   - how theses ended;
   - stops in spreads;
   - each market, and buys and sells apart;
   - H-N's stack with the same side (+0.17R a trade);
   - the companions: a limit at the block's MT, break-even at +1R, the day's close as the exit, and M1 as the E frame.

### Requirement 14: Paper, later

**User Story:** As the trader, I want the engine to trade my weekly calls on paper once it has passed, so that my read and its execution are measured together.

#### Acceptance Criteria

1. Only after H-AG passes and the trader says go, a paper agent SHALL run the same `step` on the terminal's live M1, with the trader's /context calls as the source, through the paper broker.
2. Its record SHALL sit beside the context agent's on the /context scorecard.
