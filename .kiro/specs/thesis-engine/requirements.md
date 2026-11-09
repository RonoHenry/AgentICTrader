# Requirements Document

**Spec**: Thesis Engine (the core engine, rebuilt as a state machine)

## Introduction

The liquidity engine reads every close from scratch, finds every setup with the right properties, and lets rules veto it afterwards (`liquidity_engine/engine.py`: "Stateless; safe to reuse across calls"). It never decides before it executes, so it trades both sides of one market and fires before price reaches any level (the trader, 2026-10-31 and 2026-11-02).

The trader works the other way round: one thesis or none, then the thesis's levels, then time, then the hand at the level, then one shot (thesis first; the blueprint of 2026-10-31; Model A).

The Thesis Engine is that order, built as a new core: a state machine per market, stepped by candle closes.
- **Direction comes in, never out.** A thesis (side, draw, protected level, valid from and until) arrives through one contract from a source: the trader's /context calls, AlgoMindDIS's contract, a thesis file (such as reader v0's), or, for research only, a hindsight or random side. With no thesis, nothing runs.
- **It waits, in stages.** At a level of the thesis's side, inside a time window, it watches the execution frame for the hand: a sweep at the level, then the execution frame's CISD. Then one order.
- **It remembers.** Each object (pool, array, range, thesis, order) is created once and carries its own life. Each change of state is recorded with its reason.

**Where it sits: the Setup Engine of AlgoMindDIS's architecture.** The trader's AlgoMindDIS specification (v1.0.0, §3, §22) splits the work: the Liquidity Engine detects, AlgoMindDIS holds the direction, the Setup Engine identifies and qualifies the opportunity, and execution and risk follow. The Thesis Engine is that Setup Engine, rebuilt as a state machine, under the specification's rules:
- it takes its side from AlgoMindDIS's versioned contract (`DirectionalBiasOutput`, §12) or the trader's calls, and never decides one itself (§2.5);
- it detects nothing itself (§19.2). Pools, arrays, ranges and structure come from AlgoMindDIS's analyzers, which read the engine's detectors. It adds only what happens below the D1 close: the level in play, the time, the hand and the order;
- it holds a thesis until it is invalidated, delivered, expired or replaced (§10.4), says why at every step (§2.6, §19.7), reads closed candles only (§19.6), replays deterministically (§15, §19.4), runs in shadow before it trades (§18, Phases 5 and 7), and has no learned or generated step in its decisions (§19.10).

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
- **A swing:** a candle beyond its neighbours. How many neighbours (the trader's three candles, or the analyzers' lookback of 2) is a decision for the trader (design.md).
- **ADR:** the mean D1 range over the last 20 closed days.
- **Typical spread:** the market's median M1 spread over the run's window.
- **A level:** where the engine waits, an array of the thesis's side together with what supports it (Requirement 6).
- **The hand:** a sweep at the level, then the E frame's CISD in the thesis's direction (Requirement 8).

## Requirements

### Requirement 1: Boundaries and the audit

**User Story:** As the trader, I want a new core built on my definitions, so that it does what I do and nothing else changes while it is proved.

#### Acceptance Criteria

1. THE audit (design.md, Phase 0) SHALL list each piece the engine needs, with the existing code it reuses or the reason it is new.
2. THE engine SHALL live in a new package, `thesis_engine/`. `liquidity_engine/`, `algo_backtester/`, `agent/` and `algomind_dis/` SHALL run unchanged: none of their outputs changes. The only additions outside the package are the Noculus layer and detection gaps filled in the array layer (`liquidity_engine/context`, Requirement 3.5), which nothing existing calls.
3. THE engine SHALL NOT place a live order. Paper follows Requirement 14.
4. Every rule and threshold SHALL sit in one frozen, versioned settings object (V1). A change is a new version and a new registration.
5. THE engine SHALL NOT detect what the detection layer detects (AlgoMindDIS §19.2: "AlgoMindDIS interprets; the Liquidity Engine detects"). A missing detection is added to the detection layer, and the audit records it.

### Requirement 2: The clock

**User Story:** As the trader, I want each timeframe read at its own close, so that a forming candle is never read as closed.

#### Acceptance Criteria

1. FROM M1 bars (bid OHLC and spread), THE clock SHALL build every configured frame's candles on the market's calendar and emit each candle once, at its close.
2. Candles that close at the same instant SHALL be emitted from the highest frame down, so each step sees everything closed by then.
3. A period with no bars SHALL have no candle. Weekend and holiday gaps create none.
4. THE same bars SHALL give the same events. A run stopped at t and resumed from its saved state SHALL give the same events as an uncut run.
5. **The live feed** (AlgoMindDIS §13.3):
   - a bar that repeats one already read, or is older than it, SHALL be dropped and journaled;
   - an M1 bar SHALL be read only once the next one opens, so a revision of the forming bar is never seen;
   - no bar for longer than the stale limit (V1: 15 minutes) inside the market's session SHALL make the data stale. Nothing new is armed until bars resume, and an open order is unaffected (AlgoMindDIS Requirement 14.4 treats stale data the same way).

### Requirement 3: The book, what the detectors see as of each close

**User Story:** As the trader, I want the engine to see the same pools, arrays and ranges that AlgoMindDIS sees, each with its history, so that the side and the setup are read from one picture.

#### Acceptance Criteria

1. THE book SHALL take the L frames' (D1, H4, H1) liquidity objectives, PD arrays, dealing ranges and structure from AlgoMindDIS's analyzers (`algomind_dis.analyzers`: objectives, arrays, ranges, structure), at the settings version named in V1. That is V2, whose arrays are the trader's order blocks and breakers (`array_rule = "cisd"`, `liquidity_engine/context/blocks.py`).
2. THE E frame's swings and down-close runs SHALL come from the functions the analyzers use (`liquidity_engine.context.measures`, `liquidity_engine.context.blocks.runs`).
3. Each object SHALL keep the analyzer's id and dates. THE book SHALL record each change of status (formed, swept or mitigated, invalidated) with its time, and add nothing to the detection.
4. THE book at t SHALL equal the analyzers run on the candles closed by t (a property test at every cut, as AlgoMindDIS's own replay is tested).
5. **Gaps, filled where the detection lives** (AlgoMindDIS Requirement 1.2):
   - the inverted FVG (an FVG closed through, read as an array of the other side) is not in the array layer AlgoMindDIS reads. It SHALL be added there (`liquidity_engine/context`), not in this package;
   - the analyzers read swings at the engine's lookback of 2, while the trader's swing is three candles. Which one holds is a decision for the trader (design.md).

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
   - **REPLACED:** a newer thesis for the market goes live;
   - **WITHDRAWN:** the source stops holding it (a FILE date with no entry, or AlgoMindDIS leaving the side).

   The first three match the THESIS mode's ends (`agent.order_intent._context_ended`) and AlgoMindDIS's (§10.4).
3. **Sources:**
   - **CALL:** the trader's /context calls (`agent.context_calls`). `since` is the call's and `until` is the week's close.
   - **DIS:** AlgoMindDIS's contract (`DirectionalBiasOutput` 1.0.0), read at each D1 close:
     - ACTIVE gives a live thesis, with the side, draw, protected level and `since` that `algomind_dis.contract.thesis_entry` writes, held until the side changes or ends;
     - TRANSITIONAL keeps the thesis live, but nothing new is armed while the side is challenged. An open order is unaffected;
     - NEUTRAL, UNDETERMINED, INVALIDATED or EXPIRED end the thesis.
   - **FILE:** a thesis file in the THESIS-mode format (`{instrument: {trading date: {side, draw, protected, since}}}`), such as reader v0's. Consecutive dates with the same entry are one thesis.
   - **ORACLE, MIRROR, RANDOM** (research only, never on paper):
     - the side is the week's real side (the New York W1 close against its open), its opposite, or a seeded coin flip;
     - the draw and the protected level come from the completion rule (4.4);
     - `since` is the week's open and `until` its close.
4. **The completion rule,** for the research sources only, at the week's open, for a bullish side (bearish is the mirror):
   - **the draw:** the nearest untaken pool above the open and at least 0.5 ADR away: the previous week's high, a D1 swing high or D1 equal highs;
   - **the protected level:** the nearest untaken D1 swing low below the open and at least 0.5 ADR away, else the previous week's low if it is below the open;
   - **no thesis that week** when either is missing or more than 5 ADR away (counted).

   For CALL, DIS and FILE the draw and the protected level are the source's. The nearest pool isn't automatically the draw (AlgoMindDIS §5.4). The rule takes it here only because H-AF's far draws made every race lopsided.
5. One thesis SHALL be live per market at a time.
6. **Activation** (AlgoMindDIS §18, Phase 7): the DIS source SHALL run in the mode the trader sets.
   - DIS_DISABLED reads no DIS thesis;
   - DIS_SHADOW and DIS_ADVISORY journal everything and place no order;
   - DIS_ENFORCED places paper orders, and only for an AlgoMindDIS version that has passed its own test.

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
   - ARMED → THESIS when the level fails or price moves away from it, as from AT_LEVEL;
   - ARMED → IN_TRADE when the hand completes and its order passes Requirement 9;
   - IN_TRADE → SPENT when the order closes, or → THESIS instead when the budget allows another entry;
   - IN_TRADE → AT_LEVEL when the order is rejected (its open was beyond the stop or the target);
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

1. **The sweep** (bullish; bearish is the mirror): while ARMED, an E candle trades below an untaken pool at the level. The pool is an E swing low or the previous H1 candle's low, inside the level or within 0.1 ADR below it. The sweep's extreme is the lowest low from that candle until the CISD.
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
   - never against the thesis, by construction (the trader's rule of 2026-10-29: a signal against the side is manipulation). AlgoMindDIS §12.1 allows a countertrend setup with its own justification (`algomind_dis.contract.qualify`: COUNTERTREND_JUSTIFIED). Whether the engine takes those is a decision for the trader (design.md).
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

1. An engine-chart layer, "Thesis Engine", beside the AlgoMindDIS layer, SHALL draw:
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
   - AlgoMindDIS §16.4's baselines on the same window:
     - the existing setup engine, without a side and with the same sides (THESIS mode);
     - this engine with a simple higher-timeframe side (the W1 trend at the week's open, LE-D15);
     - this engine fed by AlgoMindDIS V1, which H-AF already tested. V2 waits for its own registration;
   - the companions: a limit at the block's MT, break-even at +1R, the day's close as the exit, and M1 as the E frame.

### Requirement 14: Paper, later

**User Story:** As the trader, I want the engine to trade my weekly calls on paper once it has passed, so that my read and its execution are measured together.

#### Acceptance Criteria

1. Only after H-AG passes and the trader says go, a paper agent SHALL run the same `step` on the terminal's live M1, through the paper broker. Its source is the trader's /context calls, or AlgoMindDIS in the mode the trader sets (Requirement 4.6).
2. Its record SHALL sit beside the context agent's on the /context scorecard.


## Update 2026-11-05b: V2, the hand on the real manipulation

**Why.** The trader's October trades (the scenarios) and my own review of eight trades on Noculus (gold 9 Jun 2025 and three weeks drawn at random) show V1 failing the same way, with the right side:
- **It enters before the real manipulation.** It fires on the first small M5 sweep in a quiet range (a "CISD" 0.1-0.5 points beyond the run's open), with a stop inside the zone the real manipulation then raids. The Judas swing, the London sweep or the news spike takes the stop, and the day's budget is then spent. Across H-AG the median stopped trade never got past +0.6R.
- **It chases.** At market on the close of a big displacement or news candle, the stop is far and the pull-back takes it.
- **It holds right trades to a far draw with no management,** and some come all the way back (US100 17 Mar 2025 about +17R, EURUSD 12 May 2025 about +10R, both ended at −1R).

V2 makes the hand the trader's own rules: a real pool taken into the level, a displacement, and the entry on the array it leaves. It also makes the stack a gate. V1 stays as it is, and H-AG's result stays V1's.

### Requirement 15: V2, the trader's trigger

**User Story:** As the trader, I want the engine to enter where I would: on the manipulation into my level, after a real displacement, on the array it leaves, so that it stops buying the quiet range before the move.

#### Acceptance Criteria

1. V2 SHALL keep every V1 rule except those below. V1 SHALL run unchanged: its journals on the same bars and theses stay identical.
2. **The pools the hand may sweep** (a bullish hand; bearish is the mirror):
   - the previous D1 candle's low;
   - the trading day's Asia range low (from the day's open to 00:00 New York);
   - the previous H4 candle's low;
   - the previous H1 candle's low;
   - an untaken H1 swing low (the analyzers' swing).

   An M5 swing alone is no longer a pool. The pool still lies inside the level or within 0.1 ADR under it.
3. **The CISD shows displacement:** the candle that closes through the run's open has a body at least 1.5 times the M5 average range of the 20 candles before it (Model A's displacement).
4. **The entry is a limit at the run's mean threshold,** the midpoint of the CISD run's bodies (the trader's order block):
   - the stop stays at the sweep's extreme, and the target at the draw;
   - the limit expires at the window's end (12:00 New York), or 60 minutes after it is placed if that is later, or when the thesis ends;
   - an expired limit isn't an entry: the machine returns to AT_LEVEL, and the budget counts fills only.
5. **The stack is a gate:** a level counts only when arrays of the side on at least two level frames overlap it, or when it is a D1 array.
6. **Exits stay V1's:** the stop, the draw, or the thesis's `until`. A partial (a third off at +3R, the rest's stop to the fill) is reported as a companion, not judged.
7. **Ties between levels** of the same score and distance go to the higher frame (D1, then H4, then H1), then the tighter zone, then the latest formed, so a mirrored market chooses the same level. V1 keeps its order by the array's id. (Added before H-AH ran: the mirror test found it.)

### Requirement 16: H-AH, V2's conversion test

**User Story:** As the trader, I want V2 measured the way V1 was, registered before it runs, so that I know whether the trigger change helps before anything depends on it.

#### Acceptance Criteria

1. H-AH SHALL be registered in `docs/research/SEARCH_2018_2024.md` with V2's settings before V2's code exists.
2. **The arms, the data and the window** are H-AG's: ORACLE, MIRROR, RANDOM and W1TREND on the eight traded focus markets, `mt5-m1-develop`, theses from the week of 4 October 2021.
3. **Pass** (all three):
   - ORACLE's net R a trade is above zero, and so is its 95% interval (resampling market-weeks);
   - ORACLE is positive in at least 6 of the 8 markets;
   - the break-even weekly hit rate counted a week (the trades a week included) is below V1's 58.3%.
4. **Not a try:** its sides are hindsight. A pass gets one run on the test window (2023-2024), exported for it then. Nothing of 2023-2024 is read before.
5. **Reported beside it, not judged:**
   - V1 and V2 side by side;
   - the funnel, with limits placed, filled and expired;
   - the companion with the partial;
   - each market, and buys and sells apart.


## Update 2026-11-06: V3, the frame follows the manipulation

**Why.** V2 failed H-AH. Its funnel and five weeks on Noculus show three faults:
- **Its stops sat inside a bigger manipulation.** The stop was the M5 sweep's extreme, and the real manipulation ran through it (GBPUSD 30 May 2022, US100 9 Mar 2022). 56 of its 67 trades were stopped.
- **It missed moves whose M5 CISD didn't displace,** such as gold 9-13 Jun 2025, where V1 made +19.4R.
- **A third of its limits expired unfilled.**

The trader (2026-11-06): "the engine has to be dynamic then, we can execute anywhere from the M30, M20, M15, M10, M5, M3, M1". Asked how the frame is chosen, they chose the child of the swept pool's frame. On the entry: "If price is around the entry level, just go with a market order, if it has traded away from our entry level, I think we can just go with a limit order instead of chasing price."

### Requirement 17: V3, the execution frame follows the pool

**User Story:** As the trader, I want the engine to confirm a sweep on the frame that fits the liquidity taken, from M30 down to M1, so that a big manipulation gets a big frame and a small one a small frame, and its entry doesn't chase price.

#### Acceptance Criteria

1. V3 SHALL keep every V2 rule except those below. V1 and V2 SHALL run unchanged: their journals on the same bars and theses stay identical.
2. **The machine steps on M1 closes.** The execution frames are M30, M20, M15, M10, M5, M3 and M1, each built on the clock from the M1 bars, complete candles only.
3. **The pools** (a bullish hand; bearish is the mirror):
   - V2's: the previous D1, H4 and H1 lows, the trading day's Asia range low and untaken H1 swing lows;
   - new: untaken M30 and M15 swing lows (the analyzers' swing, lookback 2).

   A pool is taken by the first M1 bar to trade beyond it once it is known. The band rule is V2's.
4. **The frame:** a hand runs on its pool's child, the largest execution frame no longer than a tenth of the pool's frame:

   | Pool | Child |
   |---|---|
   | the previous D1 extreme, the Asia range | M30 |
   | the previous H4 | M20 |
   | the previous H1, H1 swings | M5 |
   | M30 swings | M3 |
   | M15 swings | M1 |

   M15 and M10 are the child of no pool.
   - When one bar takes several pools, the hand takes the pool of the largest frame, and the deepest of those.
   - While a hand waits, a later sweep of a larger frame's pool takes it over: the manipulation grew. The extreme so far carries over.
5. **The CISD is on the child frame:**
   - a child candle closes through the open of the run into the sweep;
   - the run ends at the sweep's child candle or the one before it;
   - the close comes within 12 child candles of the sweep's;
   - its body is at least 1.5 times the child frame's average range over the 20 candles before it.
6. **The entry:** the entry level is the mean threshold of the CISD run's bodies.
   - If the CISD close is within half the child frame's average range of it, the order goes at market.
   - Otherwise it is a limit at the mean threshold, with V2's expiry.
   - The stop stays beyond the sweep's extreme.
7. **Everything else is V2's:** the levels and the stack gate, the risk rules (a stop of at least 10 typical spreads, at least 2R to the draw), the budget, the window, the exits and the ties.

### Requirement 18: H-AI, V3's conversion test

**User Story:** As the trader, I want V3 measured the way V1 and V2 were, registered before it runs, so that I know whether the dynamic frame helps before anything depends on it.

#### Acceptance Criteria

1. H-AI SHALL be registered in `docs/research/SEARCH_2018_2024.md` with V3's settings before V3's code exists.
2. **The arms, the data and the window** are H-AG's: ORACLE, MIRROR, RANDOM and W1TREND on the eight traded focus markets, `mt5-m1-develop`, theses from the week of 4 October 2021.
3. **Pass** (all three):
   - ORACLE's net R a trade is above zero, and so is its 95% interval (resampling market-weeks);
   - ORACLE is positive in at least 6 of the 8 markets;
   - the break-even weekly hit rate counted a week is below V1's 58.3%.
4. **Not a try:** its sides are hindsight. A pass gets one run on the test window (2023-2024), exported for it then. Nothing of 2023-2024 is read before.
5. **Reported beside it, not judged:**
   - V1, V2 and V3 side by side;
   - the funnel by the pool's frame and the execution frame, with market and limit entries, and limits filled and expired;
   - each market, and buys and sells apart.


## Update 2026-11-06b: V4, setups on M30 and M15, entries refined below

**Why.** V3 failed H-AI. Read after the run:
- the hands confirmed on M30 and M20 made +1.33R a trade with the right side;
- every hand confirmed on M5 (from an H1 sweep) lost, whichever side it was given (−0.9 to −1.0R a trade on 109 trades);
- every V3 entry was a limit, and the wrong side's limits filled more often than the right side's (66% against 44%).

The trader (2026-11-06): "The fact that time is fractal does not mean that we can derive bias from the lower time frames. I think we should adjust this so that any time frame 5mins and below are just for entries and refining entries that we find on the M30 and M15. Sweeps can happen on the M15 and above, we can then utilize the m5 and below for refined entries."

They then chose:
- the setup frame by the pool's size;
- the entry on a lower frame's CISD inside the setup's order block;
- the stop beyond the setup's sweep;
- a test judged on a year the engine has never run on.

### Requirement 19: V4, setups on M30 and M15, entries refined on M3 and M1

**User Story:** As the trader, I want the sweep and its CISD read only on M30 and M15, and M5 and below used only to refine the entry inside that setup, so that a lower frame times the entry but never decides that the manipulation is over.

#### Acceptance Criteria

1. V4 SHALL keep every V3 rule except those below. V1, V2 and V3 SHALL run unchanged: their journals on the same bars and theses stay identical.
2. **The pools** are V2's: the previous D1, H4 and H1 extremes, the trading day's Asia range and untaken H1 swings. M30 and M15 swings are not pools.
3. **The setup frame follows the pool's size:**
   - the previous D1 extreme, the Asia range and the previous H4 → M30;
   - the previous H1 extreme and H1 swings → M15.

   A larger pool's sweep takes over a waiting hand, as in V3.
4. **The setup** is V3's CISD on the setup frame:
   - the close goes through the open of the run into the sweep;
   - within 12 setup candles;
   - with a body of at least 1.5 of that frame's average ranges.

   It places no order. Its order block is the bodies of the CISD's run.
5. **The refined entry:**
   - after the setup, the machine waits for price to trade back into the order block;
   - then the first CISD back the thesis's way on the refining frame (M3 for an M30 setup, M1 for an M15 setup) enters at market at its close;
   - that CISD's run must be the run into the pull-back: it ends at the candle that touched the order block or the one before.
6. **The stop is beyond the setup's sweep extreme.**
   - If price trades beyond it before the entry, the setup fails.
   - If there is no entry by the window's end, or 60 minutes after the setup if that is later, the setup expires. It never waits past the thesis's end.
7. **Everything else is V3's:**
   - the M1 step;
   - the levels and the stack gate;
   - the risk rules (a stop of at least 10 typical spreads, at least 2R to the draw);
   - the budget, the window, the exits and the ties.

### Requirement 20: H-AJ, V4's test on a year no version was shaped on

**User Story:** As the trader, I want V4 judged on a year none of the versions was built from, so that a pass means more than a fit to 2021-22.

#### Acceptance Criteria

1. H-AJ SHALL be registered in `docs/research/SEARCH_2018_2024.md` with V4's settings before V4's code exists.
2. **The judged year:**
   - the eight traded focus markets in `focus-2025-2026h1`;
   - its bars from 1 January 2025, so nothing before 2025 is read;
   - theses from the week of 6 July 2025 to the last complete week, which closes on 3 July 2026.

   The arms are ORACLE, MIRROR, RANDOM and W1TREND, each completed by the nearest-pool rule. V4 and V1 both run.
3. **Pass** (all three, on that year):
   - V4's ORACLE net R a trade is above zero, and so is its 95% interval (resampling market-weeks);
   - V4's ORACLE is positive in at least 6 of the 8 markets;
   - V4's break-even weekly hit rate counted a week is below V1's on the same year.
4. **Not a try:** the sides are hindsight. A pass gets one run on the test window (2023-2024), exported for it then. Nothing of 2023-2024 is read before.
5. **Reported beside it, not judged:**
   - V4 on the development window (H-AG's arms, data and theses);
   - the funnel: setups, pull-backs, refined entries, failures and expiries, by frame;
   - each market, and buys and sells apart.


## Update 2026-11-06c: V5, V1 in the London window

**Why.** The trader shared ICT's daytrade model. Of the five rules registered as H-AK (07e3d17) and read on V1's own hands, one held on a year no version was shaped on: entries between 02:00 and 04:00 New York ("buying between 2:00 am to 4:00 am NY Time seeking LOD"). Kept alone, V1's hands need 44.3% a week there (52.3% on 2021-22), against 58.8% (58.3%) with every hand. A filter on V1's hands is not the machine run in that window, since the day's budget then buys other hands. The trader chose to spend 2023-2024 on that version (2026-11-06).

### Requirement 21: V5, V1 entering only from 02:00 to 04:00 New York

**User Story:** As the trader, I want the engine to take its hand only in the London open, from 02:00 to 04:00 New York, so that it enters where the day's manipulation is, not in the quiet hours before it or the continuation after.

#### Acceptance Criteria

1. V5 SHALL keep every V1 rule except those below. V1 to V4 SHALL run unchanged: their journals on the same bars and theses stay identical.
2. **The window is 02:00 to 04:00 New York,** Monday to Friday. The machine arms at 02:00.
3. **A hand completes only inside the window.** The sweep and the CISD fall in M5 candles that open in it. A hand still waiting when the window closes ends, and the machine returns to AT_LEVEL.

### Requirement 22: H-AL, V5's judged run on 2023-2024

**User Story:** As the trader, I want V5 judged once on the years kept closed since the 2018-2024 search began, so that a pass means it holds on data nothing was built from.

#### Acceptance Criteria

1. H-AL SHALL be registered in `docs/research/SEARCH_2018_2024.md` before V5's code exists and before 2023-2024 is exported.
2. **The judged years:**
   - M1 for the eight traded focus markets, exported from the trader's MT5 terminal from 1 October 2022 to 1 January 2025 (`mt5-m1-test`);
   - theses from the week of 1 January 2023 to the last complete week of 2024.

   The arms are ORACLE, MIRROR, RANDOM and W1TREND, completed by the nearest-pool rule. V5 and V1 both run.
3. **V5 passes** (all three):
   - its ORACLE net R a trade is above zero, and so is its 95% interval (resampling market-weeks);
   - its ORACLE is positive in at least 6 of the 8 markets;
   - its break-even weekly hit rate counted a week is below V1's on the same years.
4. **V1 is judged on the same run by H-AG's own rule,** the test-window run its pass was owed:
   - ORACLE's net R a trade and its interval above zero;
   - at least 6 of 8 markets;
   - the break-even weekly hit rate (a trade) at most 60%.
5. **Reported, not judged:**
   - V5 on 2021-22 and 2025-26;
   - the funnel;
   - each market;
   - buys and sells apart.
6. **Not a try:** the sides are hindsight. After this run no year of 2018-2024 is unread.

### Requirement 23: Management settings, V1 unchanged

**User Story:** As the trader, I want the engine's trade management tunable as settings, so that it can need fewer right weeks to make money (2026-11-09: "We can still have a 40% win rate and be insanely profitable").

#### Acceptance Criteria

1. Each setting SHALL be off in V1 to V5, whose journals on the same bars and theses stay byte for byte the same.
2. **A stop move and a partial:** at `partial_r` R the stop moves to the fill, and `partial_fraction` of the position closes there (the fill model's, algo-backtester Requirement 28).
3. **A target cap:** with `target_cap_r` above zero, the target is that many R when the draw is farther. The minimum-reward check still reads the draw.
4. **A check:** with `check_at` "DAY_END" (the end of the fill's trading day: 17:00 New York, 18:00 for the indices) or "HOURS" (`check_hours` after the fill), an open position closes unless it has been `check_r` R beyond its fill.
   - "Has been" reads the best closing-side price since the fill, against the planned risk.
   - The close is at the M1 bar's close before the check time, as the TIME exit.
   - Its reason is CHECK.
5. The entries a thesis (`per_thesis`) stay a setting, as in V1.

### Requirement 24: H-AN, the management that lowers the bar

**User Story:** As the trader, I want V1's management tuned on the years already read and confirmed once on July to November 2026, so that the side it needs is easier to reach.

#### Acceptance Criteria

1. H-AN SHALL be registered in `docs/research/SEARCH_2018_2024.md` before its code exists. Its ten variants, its pick and its pass are frozen there.
2. **The tuning** runs V1 and each variant with ORACLE, MIRROR and RANDOM on H-AG's, H-AL's and H-AJ's windows. The code picks, by the registered rule:
   - p below V1's in all three windows;
   - ORACLE above zero a week;
   - pooled p at least 2 points under V1's;
   - the lowest pooled p.
   
   With no pick, it stops before the confirmation. The tuning log states the confirmation's power.
3. **The confirmation** runs the pick and V1 once, on `mt5-m1-2026-11`, with theses from the week of 6 July 2026 to the week of 26 October 2026. It passes when all hold:
   - the pick's p is below V1's;
   - the paired difference's 90% interval over market-weeks is below zero;
   - the pick's ORACLE is above zero a week.
4. **A pass makes the pick V6.** Not a try: the sides are hindsight.
