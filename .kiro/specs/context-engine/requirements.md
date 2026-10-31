# Requirements Document

**Spec**: Context Engine

## Introduction

The speculator has no edge. The baseline (task 211) and the setup-sequence runs (task 233) failed their pass mark, and the replays of 2026-10-10 placed the flaw:
- **Not execution.** The same ~7,000 setups entered four ways (market, limit at the array's middle, limit at its near edge, stop on the break) all land near 0R. Cancelling limits at day end, or lifting the one-order-per-instrument rule, adds nothing.
- **Selection and direction.** The engine finds 4–5 setups per instrument per trading day, and its daily direction was right about 45% of the time. A setup pays when the day goes its way (+0.46R) and loses against it (−0.68R).

The user's diagnosis (2026-10-10): PD arrays, liquidity and PO3 are universal; what the engine lacks is context. A trader's skill is knowing which pool or array matters right now. Context comes top-down and is chained across timeframes, with time inside it: "I can be selling short term in a long term bull market." And the engine must adapt: scalping, mid-frequency, intraday and position are the same logic at different scales, so they should be settings of one engine.

What the engine does today (liquidity-engine spec):
- **Bias** is price against each timeframe's open (`HTFBiasClassifier`). The grader requires D1 and W1.
- **The draw** is the strongest untaken pool on the D1-bias side, from any timeframe.
- **Setups** are any raid of any swing (lookback 2) on any timeframe, then a CISD and a PD array. Every pool gates alike (LE-D2), so nothing selects.
- **The D1 candle profile** (update 2026-10b) is a two-level chain, W1 trend to D1 anticipation, at D1 only (stage 1).

The Context Engine changes how the engine thinks, not how it executes:
1. **Frames, not fixed timeframes.** Every analysis is defined relative to a frame and runs unchanged at any timeframe (Property 1).
2. **A context chain.** A mode is a ladder of frames, highest first. Each frame's state is read in the light of the frame above it: its dealing range, premium or discount, objectives, draw, and whether its point of interest was reached. A lower frame may trade against a higher one on the way to the higher frame's point of interest.
3. **Time inside every frame.** The frame candle's anatomy (open, false move, manipulation objective) at every frame, and volatility windows measured per instrument.
4. **Selection.** A setup on the execution timeframe is taken only when it agrees with the chain: its direction, the objective it raided, the draw ahead, and the time.
5. **Modes.** Position, intraday, mid-frequency and scalp are ladders of the same engine, each judged on its own.
6. **Calibration against the user.** The user's own backtest journal is scored, and compared with the engine's calls on the same days. Each disagreement names a rule to fix.

Where it sits:
- **Inside `liquidity_engine`**, as the package `liquidity_engine/context/`. Today's engine stays as mode `legacy` and is reproduced exactly (Property 5), so every comparison has its baseline.
- **AlgoResearch tests the chain first.** Its direction calls are measured before any mode is backtested (Requirement 9).
- **AlgoBacktester runs the modes** as variants (Requirement 8).

**Guiding constraint**: validate before building. Each layer is measured in AlgoResearch before the next is traded. Stage 1 is task 242 of the liquidity-engine plan (the D1 anticipation variants), which needs no new code.

---

## Glossary

- **Frame**: a timeframe in the role of "the candle whose delivery we anticipate". Its candles follow the strategy calendar: D1 opens at 17:00 New York; H4 at 17:00, 21:00, 01:00, 05:00, 09:00 and 13:00.
- **Ladder**: a mode's frames, highest first, and an execution timeframe below the lowest. Example (intraday): W1 → D1, execution M15.
- **Bias frame**: the lowest frame of a ladder. Its candle is the one a trade is taken in, and its draw is the target.
- **Parent / child**: adjacent frames of a ladder.
- **Dealing range**: the range a frame is delivering within: from its last confirmed swing low to its last confirmed swing high, stretched by any later extreme beyond them (CE-D2).
- **Equilibrium**: the dealing range's midpoint. Above it is **premium**, below it **discount**.
- **Objective**: an untaken pool (a swing high or low, a previous candle's high or low, the Asian range at D1 and below) or an unfilled FVG, on the frame or a frame above it (as liquidity-engine Requirement 21).
- **Draw**: the objective a frame is delivering toward.
- **POI (point of interest)**: on a frame with a direction, the nearest unfilled PD array of that direction on the far side of price, in the frame's discount (bullish) or premium (bearish). It is where a retracement is expected to end.
- **Own direction**: a frame's direction from its own candles and objectives alone (Requirement 3).
- **Context direction**: a frame's direction once its parent is taken into account (Requirement 4).
- **Manipulation objective**: in the bias frame's candle, the nearest objective beyond the candle's open against the context direction: the sell-side objective below the open in a bullish candle.
- **Armed**: the chain allows the execution timeframe to take a setup at t (Requirement 8.2).
- **Journal**: the user's own backtest records, imported in the journal schema (Requirement 10).

---

## Non-Goals

Recorded so they are not silently forgotten, and not bolted on mid-implementation.

- **Changing the user's method.** The rules encode it. Where a rule disagrees with the user's calls, the rule changes (Requirement 10).
- **Execution.** Entry styles, break-even and other trade management stay as measured on 2026-10-10. Each can return as a setting once a mode has a direction that carries information.
- **Dynamic sizing.** Deferred until a mode passes.
- **Live parity.** The live MT5 gaps found on 2026-10-10 (no limit expiry, open-trade count never freed, drawdown stops inert, unsafe sizing on tiny stops) get their own update. This spec only requires that the live runner can select a mode.
- **Automated rule search and machine learning.** AR-D10 still governs.
- **Tick data.** M1 is the finest resolution. The scalp mode's report says how many trades lasted under 5 M1 bars, where the order of prices inside a bar is unknown.

---

## Requirements

### Requirement 1: Frames and Ladders

**User Story:** As the user, I want position, intraday, mid-frequency and scalp trading to be settings of one engine, so that the same logic is tested at every scale.

#### Acceptance Criteria

1. A ladder SHALL list one to four frames, highest first, and one execution timeframe below the lowest frame.
   - Each frame's candles SHALL nest inside its parent's on the strategy calendar.
   - The one exception is W1 under MN1: a week belongs to the month its open falls in.
   - A ladder that breaks either rule SHALL be refused at load, naming the pair.
2. THE engine SHALL ship these named modes (CE-D1):

   | Mode | Ladder | Execution |
   |---|---|---|
   | `position` | MN1 → W1 | H4 |
   | `intraday` | W1 → D1 | M15 |
   | `mid` | D1 → H4 → H1 | M5 |
   | `scalp` | H4 → H1 → M15 | M1 |

   Custom ladders SHALL be accepted from TOML and validated the same way.
3. `StrategyConfig.mode` SHALL select the mode. The default is `legacy`, today's engine. The mode and its ladder SHALL be part of the Phase A cache key.
4. A frame's analysis SHALL read only the frame's bars, its parents' bars and the execution timeframe's bars that closed by t, plus the forming candles' opens (as the as-of view composes them).

### Requirement 2: Analysis Prices

**User Story:** As the user, I want the engine's highs and lows to be market prices, not the bid dipping while the spread blows out at the 17:00 rollover, so that pools, raids and day lows are real.

#### Acceptance Criteria

1. M1 bars from 17:00 New York until the first bar whose spread is back under k times the typical spread SHALL be quarantined for analysis, for at most 60 minutes (CE-D3: k = 3).
   - A quarantined bar's open, high, low and close SHALL be set to the last clean close, as if the market had paused, the way gold pauses through its daily break.
   - The typical spread is the median of the previous 1,440 M1 spreads, known at t.
2. THE quarantine SHALL apply to every analysis input: the engine's bars at every timeframe, and AlgoResearch's features and labels.
   - It SHALL NOT apply to fills. The fill model keeps the recorded bid and spread, because a live stop can be hit by the blowout.
3. `StrategyConfig.rollover_quarantine` SHALL switch it, on by default in the context modes and off in `legacy`, so legacy parity holds (Property 5).
4. Instruments without a rollover blowout, such as gold, SHALL come out unchanged (Property 4).
5. THE volatility profile SHALL report per instrument the share of bars quarantined, and of day highs and lows that the quarantine moved.
6. THE live runner SHALL apply the same rule to its M1 feed, so the live engine sees what the backtest saw.

### Requirement 3: Frame State

**User Story:** As the user, I want each frame to know where it stands (its range, premium or discount, objectives and draw), so that the engine knows which pool matters.

#### Acceptance Criteria

1. FOR each frame F at t, the engine SHALL compute a `FrameState` from F's closed bars, its parents' closed bars and the forming candle's open:
   - **dealing range:** low and high from the last confirmed swing low and swing high (lookback 2), each stretched to any later extreme beyond it until a new swing confirms (CE-D2);
   - **zone:** price's position in the range (0 at the low, 1 at the high), and PREMIUM, DISCOUNT or EQUILIBRIUM (within 5% either side of the middle);
   - **objectives** above and below, from F and the frames above it:
     - untaken pools: swings with lookback 2, F's previous candle high and low, the parent's previous candle high and low, and the Asian range when F is D1 or below;
     - unfilled FVGs, at their near edge;
     - each tagged with its timeframe and when it formed;
   - **trend:** UP when F's last closed candle closed above the previous candle's high, DOWN when below its low, else NONE (LE-D15 at any frame);
   - **own direction:** trending, toward the nearest objective in the trend's direction; not trending, toward the nearer objective; NEUTRAL when that side has none (CE-D4);
   - **POIs:** for each direction, the nearest unfilled FVG or order block of that direction on the far side of price, whose near edge is inside the matching zone (CE-D2).
2. THE frame state SHALL depend only on the candles, their order and the calendar position of each bar. No rule may read a clock constant other than through the calendar and the windows of Requirement 5, so relabelling a candle series as another timeframe leaves the state unchanged (Property 1).
3. EVERY field SHALL carry a short reason string, for example "range 1.0712–1.0896 from the swings of 03-04 and 03-11; price at 71%, premium".

### Requirement 4: The Context Chain

**User Story:** As the user, I want each frame's direction to come from the frame above it, so that the engine can sell short-term inside a long-term bull market, as I do.

#### Acceptance Criteria

1. THE top frame's context direction SHALL be its own direction.
2. FOR a child C of parent P whose context direction D is not NEUTRAL, C's context direction SHALL follow the chain rule `PD_POI` (CE-D5):
   - **Against the parent, toward its POI:** when price is in P's premium (D bullish) or discount (D bearish), and P has a POI for D that hasn't been reached since P's dealing range formed. C's draw is then the POI's near edge.
   - **With the parent:** in every other case. C's draw is C's nearest objective in D's direction.
   - When P's context direction is NEUTRAL, C's SHALL be NEUTRAL.
3. THE alternative chain rule `PROFILE` SHALL generalise today's anticipation: the child goes with the parent's trend toward the parent's nearest objective when the parent is trending, else toward its own nearer objective. With W1 → D1, it SHALL reproduce the D1 candle profile (Property 6).
4. THE chain SHALL record per frame:
   - its own and its context direction;
   - which case applied;
   - the POI (zone, timeframe, formed at), whether it was reached, and when;
   - the draw and whether it was taken.
5. A POI is reached when a bar of a ladder frame or the execution timeframe trades into it after it formed. A draw is taken when such a bar trades strictly beyond it (as liquidity-engine Requirement 13.5).
6. THE chain SHALL be deterministic and SHALL use only data known at t (Property 2). Every child direction SHALL be either the parent's, or toward the parent's POI, or NEUTRAL (Property 3).

### Requirement 5: Time in Every Frame

**User Story:** As the user, I want each frame candle's anatomy and its volatility windows, so that time is part of the context, per instrument and session.

#### Acceptance Criteria

1. FOR each frame, the candle containing t SHALL record (liquidity-engine Requirement 22, at any frame):
   - its open, and the elapsed fraction of the candle at t;
   - the false move so far: whether price traded beyond the open against the context direction, and how far, in the frame's normal range;
   - the manipulation objective, and whether and when it was reached.
2. Volatility windows SHALL be measured, not hand-set (CE-D6).
   - Per instrument and frame, the profile gives the median share of the frame candle's range delivered in each sub-candle slot, on the exploration slice (D1 by H4 slot, H4 by H1, H1 by M15, W1 by weekday, MN1 by week).
   - A slot is **active** when its median share is above an even share.
   - The table is versioned with the profile, and a run records which version it used.
3. EACH setup SHALL record whether its raid fell in an active slot of the bias frame.

### Requirement 6: Setup Selection

**User Story:** As the user, I want the engine to take only the setups that matter in context, so that it trades the few setups I would, not five a day.

#### Acceptance Criteria

1. ON the execution timeframe, a setup (raid → CISD → PD array, liquidity-engine Requirement 18) SHALL be taken only when every enabled rule holds:
   - **direction:** its direction is the bias frame's context direction;
   - **objective:** its raid took the bias candle's manipulation objective, or a pool beyond the candle's open on the same side, within the current bias candle;
   - **draw:** the bias frame's draw is untaken and at least `min_rr` away in R;
   - **time:** the raid fell in an active slot of the bias frame.
2. EACH rule SHALL be a setting, on by default in the context modes, so the backtester can remove one at a time.
3. A setup a rule refuses SHALL be journaled as a `NoTrade` naming the first failed rule (`CONTEXT_DIRECTION`, `CONTEXT_OBJECTIVE`, `CONTEXT_DRAW`, `CONTEXT_TIME`), and the report SHALL count what each rule removed.
4. THE engine SHALL take at most one setup per bias candle and direction by default (CE-D8). The limit is a setting.
5. Enabling a rule SHALL never add a setup (Property 8).

### Requirement 7: Orders in Context

**User Story:** As the user, I want targets, stops and expiry set by the frames, so that each mode trades its own candle.

#### Acceptance Criteria

1. TP1 SHALL be the bias frame's draw. TP2 SHALL be the parent's draw when it lies beyond TP1 (CE-D7).
2. THE stop SHALL go behind the protected swing, per `stop_mode`, as today.
   - A stop nearer than `min_stop_spreads` typical spreads SHALL be refused (`STOP_TOO_CLOSE`; default 2 in the context modes).
   - A stop within one point of the entry SHALL always be refused, in every mode. This closes the zero-risk order of 2026-10-10.
3. THE entry SHALL follow today's rule: `suggested_entry`, as a limit when beyond the market, else at market.
4. Pending orders SHALL expire at the bias candle's close (CE-D10).
   - Open trades are held to stop or target by default.
   - `time_limit = BIAS_CANDLE` SHALL instead close them at the bias candle's close.

### Requirement 8: Modes in the Backtester

**User Story:** As the user, I want each mode backtested on its own, so that we see how each one plays out.

#### Acceptance Criteria

1. A run config SHALL select `strategy.mode`. The modes' variants SHALL live in `config/backtests/modes.toml`.
2. Phase A SHALL run the execution analysis only while the chain is armed (CE-D9). Armed means:
   - the bias frame's context direction is not NEUTRAL;
   - its draw is untaken;
   - when the objective rule is on, the bias candle's false move has happened.

   The chain itself SHALL be updated at every execution close from frame states that are recomputed only when one of their bars closes. A gated run SHALL equal an ungated one (Property 7).
3. THE report SHALL break results down by:
   - mode;
   - chain case (with the parent, or toward its POI);
   - each selection rule's removals;
   - trades per bias candle;
   - for `mid` and `scalp`, the cost per trade in R and the share of trades under 5 M1 bars.
4. A run SHALL check each frame's warm-up and history before it starts, and refuse a mode without enough of either, saying what is missing (CE-D11).

### Requirement 9: Research Before Trading

**User Story:** As the researcher, I want the chain's direction calls tested in AlgoResearch before any mode is backtested, so that a mode is built only on a direction that carries information.

#### Acceptance Criteria

1. AlgoResearch SHALL build context features per mode on the bias frame's grid:
   - own and context direction, and the chain case;
   - zone, POI reached, draw price and draw taken at;
   - the manipulation objective, reached or not.
2. ITS labels SHALL work at any frame: whether the bias candle reaches its draw after t (H001's measure at any frame).
3. THE first hypotheses (H011–H014, one per mode) SHALL test whether the context direction's draw is reached more often than:
   - the same draw on the days the legacy bias disagreed (`complement`);
   - any engine objective at the same distance and hour (`stratified`).

   They SHALL be pre-registered together, so the ledger counts all four tries.
4. A mode's backtest report SHALL show its direction hypothesis's verdict beside its own result.

### Requirement 10: Calibration Against the User's Journal

**User Story:** As the user, I want my own backtest records compared with the engine's calls, so that every disagreement points to a rule to fix.

#### Acceptance Criteria

1. A journal importer SHALL read the user's records (a CSV or Markdown export from Notion, or the Notion connector once authorised) into the journal schema:
   - instrument, date and time (New York), mode or frames;
   - the user's bias per frame, the expected draw, the POI or pool traded from;
   - entry, stop, target, result in R;
   - whether it was skipped, and why;
   - notes.

   The field mapping SHALL live in `config/research/journal.toml`. Fields it doesn't map SHALL be kept as notes.
2. THE journal SHALL be scored with AlgoResearch's statistics: win rate and mean R with day-cluster intervals, by mode and instrument. Records outside the candle data SHALL be listed, not silently dropped.
3. FOR each journal record, the chain SHALL be replayed as of the record's time. A diff report SHALL show agreement per frame on bias, draw and POI. Each disagreement SHALL show the engine's reason strings next to the user's notes.
4. Journal data SHALL stay local, git-ignored under `data/journal/`, unless the user says otherwise. Reports quote no more of it than they need.
5. Rule changes SHALL be calibrated only on journal records outside the confirmation slice and the hold-out. Records inside them SHALL be scored only after the rules are frozen; the calibrate command enforces this (Property 9).

### Requirement 11: Legacy Parity and Explanations

**User Story:** As the user, I want today's engine kept exactly as a baseline, and every context decision explained, so that a change can be judged and a trade can be read.

#### Acceptance Criteria

1. Mode `legacy` SHALL reproduce today's engine: every `SignalRecord` equal on the backtester fixtures and on the 2026-10-08 golden journal (Property 5).
2. EVERY context-mode order intent and `NoTrade` SHALL carry the chain's reason strings, and the backtest report SHALL show them per trade.

### Requirement 12: Evaluation Protocol

**User Story:** As the user, I want the modes judged the same honest way, so that a mode that passes by luck isn't mistaken for an edge.

#### Acceptance Criteria

1. Modes SHALL be run slowest first (`position`, `intraday`, `mid`, `scalp`), each with its pass mark written in its run config and committed before the run.
2. THE backtester's pass mark SHALL apply on the study period. The hold-out `--final` run SHALL come only after every mode has been reported, for the modes the user selects.
3. A mode that can't reach the pass mark's minimum trade count SHALL be reported as INSUFFICIENT, not as a failure or a pass.

---

## Open Decisions

Proposed defaults apply unless the user changes them at review.

| # | Decision | Proposed default |
|---|---|---|
| CE-D1 | Modes | `position` MN1 → W1 (H4); `intraday` W1 → D1 (M15), today's frames, so it compares with `legacy` and stage 1; `mid` D1 → H4 → H1 (M5); `scalp` H4 → H1 → M15 (M1), the user's "bias from M15, execute on M1". The faster modes carry two context frames, because a short candle needs more context. |
| CE-D2 | Dealing range and zones | Swing lookback 2 (the engine's everywhere else); the range stretches to any later extreme until a new swing confirms. EQUILIBRIUM is within 5% of the middle. A POI's near edge must lie inside its zone. The CRT alternative (the previous candle's range) is a later variant. |
| CE-D3 | Rollover quarantine | k = 3 typical spreads, at most 60 minutes from 17:00 New York, bars flat at the last clean close. Measured 2026-10-10: FX spreads stay 3–8× typical through 17:00–17:15. Dropping bars of at least 2–3× takes the day lows in the 17:00 hour from 12–20% to 1–4%. Replacing only the blown bar's low barely helps, because the whole bar is depressed. |
| CE-D4 | Own direction | The candle profile's rule (LE-D15) at any frame: trending toward the trend's nearest objective, else the nearer objective. |
| CE-D5 | Chain rule | `PD_POI`, the premium/discount and POI rule: a child goes against its parent only toward an unreached parent POI, from the parent's wrong zone. A NEUTRAL parent gives a NEUTRAL child (no trade without context). `PROFILE` stays available as the stage-1 rule. |
| CE-D6 | Volatility windows | Measured per instrument and frame on the exploration slice. A slot is active above an even share. Nothing is hand-set: AR-D21 withdrew the hand-set timing claims. |
| CE-D7 | Targets and holding | TP1 the bias frame's draw, TP2 the parent's. Held to stop or target, with `BIAS_CANDLE` as the time-exit variant. |
| CE-D8 | Setups per candle | One per bias candle and direction. The 2026-10-10 replay found the extra setups add nothing (BODY extras −0.35R, WICK +0.00R) and stack the same bet. |
| CE-D9 | Phase A gating | Execution analysis only while armed. The chain is recomputed only when a frame bar closes. This is what keeps `scalp` (M1) affordable. |
| CE-D10 | Expiry | At the bias candle's close. On 2026-10-10 day-end expiry hurt `legacy`, mostly by blocking later setups; with one setup per bias candle there is nothing left to block. Measured per mode. |
| CE-D11 | History | `position` needs MN1 and W1 history before 2025. With today's data (M1 from 2024-05) it may be INSUFFICIENT; longer D1 and H4 history from MT5 would fix that (AR-D11). |
| CE-D12 | The user's journal | Local and git-ignored. Calibration reads only records outside the confirmation slice and the hold-out; the others are scored once the rules are frozen. |
| CE-D13 | Names and numbering | Package `liquidity_engine/context/`, spec `.kiro/specs/context-engine/`, decisions CE-D. Tasks continue the platform sequence from 275; hypotheses continue from H011. |

---

## Update 2026-10-15: Model A

The trader wrote down their model, Model A, and said the engine's model is broken. It is: the engine reads bottom-up. It takes any recent sweep on M15, then lets the context grade or veto it, so a filter can remove a bad pick but never choose the right one. Every task 242 variant landed near +0.1R with an interval spanning zero. This spec's own Requirement 6 repeated the pattern ("the setup sequence stays the trigger").

Model A reads top-down. The context frame picks the place and the time; the lower frames time the entry. Its six steps, for a short (a long mirrors them):
1. Premium on the context frame's dealing range.
2. A point of interest (POI) above.
3. Inducement at the POI.
4. C2 runs C1's high into the POI, closes back inside C1's range, and price displaces.
5. C3 retraces into the OTE of the new range.
6. A sell limit there, with the stop above C2's high and targets at C1's low and the SD levels.

Time is its core element.

The model is universal: it is read on every frame, and traded on the trader's frame sets (MA-D1):

| Set | F, context | C, the CRT candles | E, execution |
|---|---|---|---|
| `model_d1` | D1 | H1 | M5 |
| `model_h4` | H4 | M15 (M30 a variant) | M1 (M3 a variant) |

`model_h4` nests inside `model_d1`: the higher set's OTE is a POI of the lower one, and the higher set's targets extend the lower set's (the "sniper entry").

What this update does:
- **Keeps** Requirements 1–5 and 8–12. They are the foundation Model A needs: frames, analysis prices, the frame state (dealing range, premium/discount, POIs), time in every frame, research before trading, calibration, parity and evaluation.
- **Replaces** Requirements 6 and 7 in the Model A modes, with the Model A sequence (Requirement 13) and its orders (Requirement 14). `legacy` keeps its own path.
- **Adds** nesting (Requirement 15), the state record measured before anything is traded (Requirement 16), and Model A drawn on the Engine chart (Requirement 17).
- **Changes CE-D1.** The modes are the trader's sets. The four earlier ladders stay available as custom ladders, for the universality check (Requirement 16.4).

Where the trader's model leaves a definition open, its working defaults apply (MA-D2 to MA-D12) until labelled examples settle them. Variants of the open ones are measured side by side.

### Requirement 13: The Model A Sequence

**User Story:** As the trader, I want the engine to read my sequence in my order, so that it takes the setup I would take, where and when I would.

#### Acceptance Criteria

1. FOR each frame set and direction, a reader SHALL follow Model A's states. Each instance records the time of every state and a reason string. Written for a short:
   - **FRAMED:** a C candle closes (it becomes C1) while price is in premium of F's dealing range (Requirement 3) and F has a bearish POI above price (MA-D2). C1's high and low are recorded.
   - **ARMED:** price comes within one F average range of the POI. Inducement between price and the POI (MA-D3) is recorded, not required.
   - **MANIPULATED:** the next C candle, C2, trades above C1's high and into the POI.
   - **REJECTED:** C2 closes back inside C1's range.
   - **DISPLACED:** on E, a bearish CISD after C2's high, with a candle body of at least 1.5 E average ranges and a bearish FVG left by the leg (MA-D4). This fixes the new range, from C2's high to the leg's low (MA-D5).
   - **IN_OTE:** price retraces into 0.62–0.79 of the new range.
   - **ENTERED:** a sell limit at 0.705 of the new range fills (MA-D6).
   - **Outcome:** TP1 (C1's low), each of −1, −2 and −2.5 SD of the new range (MA-D7), or STOPPED (above C2's high), within the horizon (MA-D11).
2. AN instance SHALL end at the first invalidation, recorded by name:
   - `POI_FAILED`: a C candle closes above the POI's far side.
   - `NO_REJECTION`: C2 closes above C1's high.
   - `NO_MANIPULATION`: C2 closes without having traded above C1's high into the POI.
   - `MISSED`: price breaks the new range's low before reaching the OTE.
   - `RETRACE_INVALID`: price trades above C2's high before the entry fills.
   - `EXPIRED`: C3 closes without a fill, or without displacement.

   The trader's `REFRAMED` (F's range changes before the manipulation) can't occur. Before MANIPULATED an instance lives one C candle, and C candles nest inside F candles, so F never closes under it.
3. EVERY size SHALL be measured in the frame's own average range (MA-D8), and every duration in the frame's own candles. So the reader is the same code on every frame set, and relabelling the candles as another timeframe leaves its states unchanged (Property 1).
4. THE reader SHALL read only bars closed by t (Property 2). It SHALL carry its instances from close to close; it does not re-derive them each time.
5. **Time.** EACH MANIPULATED SHALL record whether C2 opened in the trader's window for its parent candle (MA-D9), and in a measured active slot (Requirement 5). Neither gates the reader; both are recorded.
6. AT most one instance per direction SHALL run at a time on a frame set. A new C1 is taken only once the instance before it has ended (MA-D10).

### Requirement 14: Model A Orders

**User Story:** As the trader, I want the engine to place my order where I would, so that a backtest trades my model and not an approximation of it.

#### Acceptance Criteria

1. Once an instance is REJECTED and DISPLACED, the order SHALL be:
   - a sell limit at 0.705 of the new range;
   - the stop above C2's high by 0.1 E average ranges;
   - TP1 at C1's low when it lies beyond the entry, else at −1 SD; TP2 at −2 SD.
2. THE order SHALL expire at C3's close. Trades are held to stop or target within the horizon (MA-D11), and closed at its end otherwise.
3. Each Model A order intent SHALL carry the instance's states and reasons. The backtest report SHALL show them per trade.

### Requirement 15: Nesting

**User Story:** As the trader, I want the lower frame set to trade inside the higher set's OTE, and to aim for the higher set's targets, so that a small stop carries a large target.

#### Acceptance Criteria

1. WHILE a `model_d1` instance is DISPLACED and not yet ended, its OTE zone SHALL be a POI of `model_h4` in the same direction, beside `model_h4`'s own F POIs.
2. A `model_h4` instance SHALL record its nesting depth: 2 when its C2 traded into a live `model_d1` OTE, else 1.
3. A nested instance SHALL carry the higher instance's C1 opposite extreme and SD levels beside its own, as its extended targets.

### Requirement 16: The Model A Record

**User Story:** As the trader, I want to know how often each step of my model happens and what follows, so that the model becomes a measured edge before anything is traded.

#### Acceptance Criteria

1. AlgoResearch SHALL run the readers over the exploration slice (AR-D3) per instrument and frame set. It SHALL report the funnel:
   - how many instances reached each state, and each invalidation's count;
   - **the premise**: once C2 has rejected, how often price reaches C1's opposite extreme before C2's extreme, within the F candle. It is compared with a coin flip from the same distances (the chance a driftless walk gets there first), paired by trading date. It counts every rejected C2, not only the few that fill;
   - after ENTERED, how often TP1 and each SD level were reached before the stop, and the mean R at TP1 and at TP2;
   - day-cluster intervals for every rate (AlgoResearch's statistics).
2. THE report SHALL break the funnel down by:
   - time sync (the trader's windows and the measured slots);
   - inducement;
   - nesting depth;
   - each variant of MA-D5 to MA-D7.
3. TWO baselines SHALL run beside it with the same C and E rules:
   - **`CRT`:** no F. Any C2 that trades above C1's high and closes back inside counts as MANIPULATED and REJECTED.
   - **`RANDOM_POI`:** each POI is moved by a random 0.5–2 F average ranges, up or down, from a fixed seed.

   Model A's context earns an edge only if its rates beat both.
4. **The universality check.** The same reader SHALL also run on W1/D1/H4, D1/H4/M15 and H1/M15/M1, report-only.
5. NOTHING is traded and no hypothesis is pre-registered from this report. It feeds a review with the trader (task 312) and the next spec update.

### Requirement 17: Model A on the Chart

**User Story:** As the trader, I want to watch the engine read Model A on the chart, so that I can see each step it takes and where it goes wrong.

#### Acceptance Criteria

1. THE Engine mode of the charts (market-narrative Requirement 15) SHALL draw each live instance of a chosen frame set:
   - F's dealing range and its 50%, and the POI;
   - C1 and C2 marked;
   - the new range with 0.62, 0.705 and 0.79;
   - the SD levels and the stop;
   - a badge with the state and its reason.

   An ended instance fades, with its outcome or invalidation shown.
2. THE events log SHALL list every instance's state changes, and jump to each.
3. NOTHING after the session's time SHALL be shown (algo-backtester Requirement 15.4).

### Open Decisions: Model A

| # | Decision | Proposed default |
|---|---|---|
| MA-D1 | Frame sets | `model_d1` D1 / H1 / M5. `model_h4` H4 / M15 / M1, with variants C = M30 and E = M3. |
| MA-D2 | POI | F's unfilled order block, FVG or breaker of the trade's direction, in the matching zone (Requirement 3, CE-D2). Also untaken liquidity on that side: the previous month, week and day high (low), F's swing highs (lows), and F's equal highs (lows) within 0.1 F average ranges. A liquidity POI is the level ± 0.1 F average ranges. NWOG/NDOG and trendline liquidity come later. |
| MA-D3 | Inducement | Between price and the POI on E: equal highs within 0.1 E average ranges, or at least 6 E candles inside a range smaller than one E average range. Recorded, not gating. |
| MA-D4 | Displacement | In the leg down from C2's high: a CISD, a candle body ≥ 1.5 E average ranges, and an FVG. The CISD (`RUN`) is a close below the open of the up-close run that made C2's high, at any time after it. The engine's `CISDDetector` needs the very next candle to break the run (`NEXT`, kept as a variant). On gold, `NEXT` let 14 of 114 rejected C2s displace (model_d1), against 44 for `RUN`. |
| MA-D5 | Where the new range ends | The trader's default, `CISD`: the lowest low between C2's high and the CISD's confirmation. Variant `SWING`: the leg extends to the first confirmed E swing low (lookback 2), so a continuation isn't counted as MISSED. Both are measured; the trader picks. |
| MA-D6 | Entry | 0.705 of the new range. Variant: the near edge of a bearish array inside the OTE. |
| MA-D7 | SD anchor | The new range. Variant: the manipulation leg, from C2's open to its high. |
| MA-D8 | Average range | The mean high minus low of the frame's last 20 closed candles. F's state (dealing range, POI candidates) is read from its last 600 closed candles: on D1 the whole history, on H4 about four months, on H1 about a month. |
| MA-D9 | The trader's time windows | H1 C2: opening at 02:00, 03:00, 07:00 or 08:00 New York (the first hours of London and NY AM). M15 or M30 C2: opening at :45 or :00, around the hour's macro. D1 C2: Monday to Wednesday. H4 C2: the 01:00, 05:00 and 09:00 candles. *(The trader confirms these.)* |
| MA-D10 | Instances | One per direction per frame set at a time. |
| MA-D11 | Outcome horizon | The close of the F candle in which the entry filled. Variant: the next F candle's close. |
| MA-D12 | Cache key | `legacy`'s key excludes `liquidity_engine/context/`, so adding Model A leaves the cached legacy runs valid. The Model A modes carry their own key. |

---

## Update 2026-10-15b: Volatility and Time in the Reader

The first record (task 312) found that Model A's premise doesn't beat its coin flip with the working definitions. The trader's diagnosis: the mechanical model ignores the market's volatility. Split by the phase of the day, the record agreed:
- **Early is better.** With C2 opening between 20:00 and 07:00 New York, the premise beat its coin on the H4 sets: H4/M30/M1 +7% [+4, +11], H4/M15/M1 +3% [0, +6].
- **Late is worse.** From 07:00 to 20:00 it lost: −5% [−9, −1] and −3% [−7, 0], NY PM worst at −9% on both.
- **The context is what flips.** Plain CRT moved by 1–2 points across the day, so it's the context that changes value with time.
- **The range spent.** Setups after the day's average range was spent, and setups larger than about a third of it, did worse.

The split was chosen after seeing the data, across about 60 comparisons. It is a lead to build in and confirm, not an edge.

The reader's sizes also adapted to quiet markets: "large" was measured against E's last 20 candles, so in a dead hour ordinary noise could pass as displacement.

### Requirement 18: Volatility and Time in the Reader

**User Story:** As the trader, I want the reader to know the phase of the day and how much range the day has left, so that it reads my sequence where it delivers, and not where it is noise or continuation.

#### Acceptance Criteria

1. EACH instance SHALL record the phase of its cycle that C2 opened in (MA-D13): the phase of the day for intraday C candles, the trading date's weekday for D1, the week of the month for W1. A variant MAY allow only some phases; C1s whose C2 would open outside them start no instance.
2. AT C2's close, each instance SHALL record, in the ADR (the mean range of the 20 trading days before, MA-D15):
   - the day's range so far;
   - the setup's size, C2's extreme to C1's opposite extreme;
   - the reach of C1's opposite extreme from the day's extreme on C2's side.

   A variant MAY end the instance there with `RANGE_SPENT`, `TOO_LARGE` or `NO_ROOM` (MA-D15 to MA-D17), before REJECTED, so a gated instance doesn't count in the premise. Without enough history (10 trading days), nothing is gated.
3. A variant MAY measure E's sizes (the displacement body, inducement's tolerances, the stop buffer) against E's candles in the same slot of the day over the previous 20 trading days, instead of its last 20 candles (MA-D14).
4. `MODEL_A_VT` SHALL combine them:
   - the early phases;
   - sizes against the same hour;
   - 70% of the ADR;
   - setups up to 0.35 ADR;
   - C1's opposite extreme within one ADR.

   The Engine chart SHALL read it, and show each instance's phase and ADR figures.
5. THE record SHALL read Model A plain, with time, with volatility and with both, beside CRT and random POIs under the same gates as both. Then the context has to beat its baselines where the gates let it trade.
6. NOTHING here is a verdict. Whether "early" holds is decided once, on the confirmation slice, by a hypothesis the trader confirms before it runs.

| # | Decision | Proposed default |
|---|---|---|
| MA-D13 | Phases | New York wall time: ASIA 20–24, MIDNIGHT 0–2, LONDON 2–5, PRE_NY 5–7, NY_AM 7–10, NY_MID 10–13:30, NY_PM 13:30–16, CLOSE 16–20. Early = ASIA to PRE_NY; for D1 C candles Monday to Wednesday; for W1 weeks 1–2. |
| MA-D14 | Sizes | `SEASONAL`: E's average range in the same 15-minute slot (or the candle itself when longer) over the previous 20 trading days (at least 5), falling back to the rolling 20 candles. |
| MA-D15 | Range spent | ADR: the mean daily range (17:00 to 17:00) of the previous 20 trading days, at least 10. `RANGE_SPENT` past 70% by C2's close. |
| MA-D16 | Setup size | `TOO_LARGE` past 0.35 ADR, from C2's extreme to C1's opposite extreme. |
| MA-D17 | Room | `NO_ROOM` when C1's opposite extreme lies more than one ADR from the day's extreme on C2's side. |

---

## Update 2026-10-15c: A Thesis First

The trader asked how a trader with their experience would turn it into a model. The answer: split the skill into three predictions, each scored against its own baseline, in order:
1. where the day is going (the thesis);
2. where and when it turns to get there (location and time);
3. how to get on (execution).

The oracle split showed why the order matters:
- **On the day's side, the sequence works.** Model A's rejected C2s on the side the day went (hindsight) beat their coin by +19% [+12, +26] on D1/H1/M5.
- **The reader rarely picks that side.** Only 27–29% of its rejected C2s were on it. "Premium with a POI above, so sell" fires all through up days, because price spends them in premium.
- **The trader does it differently.** They sell premium only when they already expect the day down, with one thesis per day or none (*thesis first, not every move*). The reader had no thesis and traded both sides.

### Requirement 19: A Thesis First

**User Story:** As the trader, I want Model A to trade only the side my daily thesis names, so that the sequence I read is the manipulation before the move I expect, not every counter-move.

#### Acceptance Criteria

1. A reader MAY be handed a thesis: one direction per trading day (17:00 to 17:00 New York), bullish, bearish or none. It SHALL frame only on the thesis side, and SHALL start nothing on a day without one.
2. THE theses SHALL be:
   - **PROFILE:** the engine's D1 candle profile at the day's 17:00 open (liquidity-engine Requirement 21), read only from the H4, D1 and W1 candles closed by then (Property 2);
   - **PREV_DAY:** the day before's direction, a naive baseline;
   - **ORACLE:** the day's own direction (its D1 candle closing above or below its open). This is hindsight, never tradeable: it is the upper bound, so the gap between it and PROFILE is what a better thesis can win.
3. THE record SHALL score each thesis on its own: how often it named the day's direction among the days it named one, against 50%. It SHALL read Model A (plain, and with time and volatility) and CRT under each thesis, in arms chosen with `--arms thesis`.
4. A thesis that beats its coin is the precondition for trading Model A in a mode. The trader's own blind reads (market-narrative task 301) set the bar the engine's thesis must reach.

**First scores (exploration slice), the theses alone:**
- **PROFILE:** XAUUSD 53% [44, 61], EURUSD 48%, GBPUSD 47%, USDJPY 53%. A coin flip.
- **PREV_DAY:** 40% to 51%.

## Update 2026-10-23: The Trader's Trend

Both confirmations of 2026-10-23 failed (liquidity-engine Requirement 29; `docs/backtests/CONFIRMATION_D1_BOX.md`, `CONFIRMATION_OTE.md`). The M15 execution lost out of sample: −0.47R a trade, and −0.25R before costs. Filters on an engine that takes both sides only reshuffled its losers.

The trader then described the model they trade, which sets the side first:
- in a bearish trend, price raids buy-side liquidity and continues lower, so that is where shorts are hunted;
- from the raid, project the Fibonacci and anticipate the OTE retracement;
- at the OTE, to the left of the displacement, look for the PD array that supports the setup;
- targets are the standard deviation levels in confluence with a PD array or a liquidity pool;
- the up-close candles left on the way down (bearish order blocks, propulsion blocks) are continuation order blocks. When one traded into an important level (an FVG or a liquidity pool), its tip is a protected swing, and price should not trade through it unless the read is wrong.

How they know the trend is bearish (2026-10-23), in a fractal framework, mostly on the parent timeframe from H1 up:
1. a consistent bearish structure: lower highs and lower lows;
2. consecutive bearish closes;
3. buy-side liquidity swept, with price failing to displace higher;
4. bearish arrays respected and structure broken lower, while bullish arrays are disrespected and traded through;
5. bearish PO3 in the down-close candles.

The bullish trend is the mirror. ICT's Market Maker Models are to come later.

### Requirement 20: The Trader's Trend

**User Story:** As the trader, I want the engine to read the trend the way I do, from the five things I look at on the parent timeframe, so that it hunts only the side the trend is delivering.

#### Acceptance Criteria

1. A trend reader SHALL read each closed candle of a frame (H1, H4 and D1 to begin with) and give five signals, each bearish (−1), bullish (+1) or neither (0), from that frame's closed candles only. The working definitions (MA-D19) are to be corrected on the chart by the trader:
   - **structure:** the last two three-candle swing highs and lows: lower high and lower low, or higher high and higher low;
   - **closes:** the last closed candle and at least two of the last three closed the same way;
   - **liquidity:** the most recent sweep of an untaken three-candle swing high (low) that closed back below (above) it. A later close beyond the sweep's wick cancels it;
   - **arrays:** over the last 20 candles, bearish arrays respected and bullish arrays traded through, against the mirror. Arrays are the frame's FVGs and order blocks (`algo_research/atlas/arrays.py`). Respected means traded into and not closed beyond; traded through means closed beyond the far edge;
   - **PO3:** among the last three candles, the bearish PO3s against the bullish ones. A bearish PO3 is a down close whose high is at least 20% of its range above the open, closing in the bottom 30% of its range.
2. THE frame's trend SHALL be the sum of the five: bearish at −3 or below, bullish at +3 or above, otherwise none (MA-D20). Every signal is kept, so the trader can see which ones disagree with their eye.
3. NO value SHALL be read from a candle after the one it labels (Property 2).

### Requirement 21: The Trend Before Anything Is Built On It

**User Story:** As the trader, I want to know whether the trend read calls the next move better than chance before setups are built on it, so that the engine's side comes from something that carries information.

#### Acceptance Criteria

1. ON the exploration slice and the trader's focus markets, for each frame and each closed candle with a trend, the research SHALL race, on M1 from the next open, one average range (the frame's last 14 candles) in the trend's direction against one in the other, for up to three candles of the frame (MA-D21).
2. THE hit rate SHALL be read against 50% and against each side's rate over all of the frame's candles (drift), with a trading-date bootstrap interval. The same SHALL be done for each signal on its own, and per market.
3. THE bar SHALL be the 56-61% a bias needs for the trader's executions to clear their costs (task 338). The continuation setup (Requirement 22) is built on the trend only if it clears that bar. Otherwise the result goes back to the trader with the signals that disagreed, before anything is tuned.

### Requirement 22: The Continuation Setup

**User Story:** As the trader, I want the engine to hunt only the trend's side, at the OTE of a displacement that followed a raid of the opposite liquidity, with targets where the standard deviations meet an array or a pool, and with the continuation order blocks' tips as protected swings.

#### Acceptance Criteria

1. IN a bearish trend (Requirement 20), a setup SHALL be:
   - a raid of buy-side liquidity, the raiding swing being the protected swing;
   - a displacement lower;
   - the Fibonacci from the protected swing to the displacement's low;
   - an entry in the OTE (0.62-0.79) where a bearish PD array to the left of the displacement lies in it;
   - the stop beyond the protected swing;
   - TP at the first standard deviation level of the leg in confluence with a PD array or a liquidity pool.

   The bullish setup is the mirror.
2. AS price continues, an up-close candle before a down move (a bearish order block or propulsion block) that traded into an FVG or a liquidity pool SHALL make its tip a protected swing. Price trading through it means the read was wrong.
3. Open until the trader answers (defaults in MA-D22):
   - which buy-side liquidity counts;
   - which frames read the trend, and which read the setup;
   - which standard deviation levels count, and how close confluence must be.

### Requirement 23: The Trend on the Chart

**User Story:** As the trader, I want to see each frame's trend and its five signals on Noculus, so that I can correct the reader where it disagrees with my read.

#### Acceptance Criteria

1. NOCULUS SHALL draw, for a chosen frame, each closed candle's trend and the five signals behind it, without revealing anything after the replay clock.

### Decisions (2026-10-23)

| Id | Topic | Decision |
|---|---|---|
| MA-D18 | Source | Every signal comes from the frame's own closed candles and its three-candle swings, the trader's foundation ("a swing point can only be formed by three candles"). |
| MA-D19 | Working definitions | As in Requirement 20.1. They are not fitted to outcomes; they are the trader's words made countable, and the chart (Requirement 23) is where they get corrected. |
| MA-D20 | The state | The sum of the five signals; three in agreement name the trend. |
| MA-D21 | The race | One frame average range each way (the mean range of the 14 candles before), from the next M1 open; a bar reaching both is a loss for the trend; unresolved after three candles of the frame is counted apart. |
| MA-D22 | Setup defaults | Buy-side liquidity: the setup frame's untaken three-candle swing highs, equal highs and the previous day's high. Frames: the trend on H1 (and H4 above it); raid, displacement, OTE and array on M15, the entry on M5. Standard deviations: −1, −2, −2.5 and −4 of the leg; confluence within 10% of the leg. |

## Update 2026-10-23b: Ranked Swings and Breaks

Task 356 found that the trader's trend, counted from every three-candle swing, calls the next move no better than a coin. A reading plan the trader shared the same day proposed reading structure as ICT ranks it, instead of counting every swing:
1. **Rank the swings.** Short-term highs (three-candle swings), intermediate-term highs (an STH higher than the STH on either side) and long-term highs (the same one rank up). Structure changes only when an ITH or ITL breaks. An ITH is known only once the next, lower STH has formed, and that lag is kept.
2. **A break is not a sweep.** A break (MSS or BOS) is a candle closing beyond the swing, with a displacement that leaves an FVG. A wick through the swing that closes back inside is a sweep: liquidity taken, structure unchanged.
3. **Output levels, not only a sign.** In an uptrend these are the protected low (the swing that launched the break: the stop, the invalidation) and the weak high (the high not yet exceeded: the draw).
4. **Read top-down, one job per frame.** The higher frame's weak swing is the draw, and the lower frame times the entry. A lower-frame break against the higher-frame trend at a higher-frame level is a Smart Money Reversal candidate (MMXM, later). Elsewhere it is a retracement.
5. **A market-structure shift at a higher-frame level is the main event.** It is the one place the turn atlas found structure carrying information: D1 swings that took the previous week's extreme, +15 points over geometry.

The plan's own test: whether intermediate-term swings, or breaks read from closes, make structure (or the trend score) call the next day better than the earlier mechanical reads' 45-49%. If none does, structure is mostly for levels, not direction.

### Requirement 24: Ranked Swings and Breaks

**User Story:** As the trader, I want structure read from ranked swings and from breaks rather than sweeps, and measured before the engine uses it, so that a better definition earns its place.

#### Acceptance Criteria

1. THE reader SHALL rank a frame's swings into STH/STL, ITH/ITL and LTH/LTL, each known only from its own candles and the next lower-rank swing's closed candles (`ranked_highs`, `ranked_lows`).
2. A structure state SHALL be readable:
   - by comparing the last two swings of a rank (`compare_state`);
   - from breaks (`break_state`): a close beyond the latest unbroken swing of a rank, held until the other side breaks. A wick beyond that closes back inside changes nothing. Optionally the breaking candle must be C2 of an FVG in the break's direction, known at C3's close.
3. THE research SHALL measure five versions on both slices and the focus markets: STH compare (task 355), ITH compare, STH break, ITH break, ITH break with FVG. Each is read on D1 and on the H4 candle closing at 17:00 New York, alone and swapped into the trend score. Each calls the next D1 candle against 50% and drift, with intervals. A version that clears 56-61% on both slices goes to the trader before any engine use. If none does, structure is kept for levels (points 3-5), not direction.

## Update 2026-10-23c: The Entry

Gold, Wednesday 29 January 2025, the trader on Noculus: "notice the contrast in the trades the engine takes and the ones we anticipate it should be taking". The trader shorted the previous day's high twice. The first was a limit filled at 03:34 while C2 ran into the level (+5.4R). The second came on the 05:00 retest after the leg extended (+12.4R). Both stops were about a point away.

Model A (H4/M15/M1) framed the same short at 03:15 (premium; POI the previous day's high). It saw the manipulation and the displacement, with its stop above C2's high and its targets at the same standard deviations. Then it **missed**: its entry waits for the OTE after the displacement, and price broke the new range's low first. On that day the gap between the trader and the model was the entry, not the scale.

### Requirement 25: The Entry

**User Story:** As the trader, I want Model A's entry measured against mine (at the level as price runs into it, or on the retest after the leg extends), so that the engine stops missing setups it has already read, if that pays.

#### Acceptance Criteria

1. ON the Model A record and its arms (the model's, CRT with no context, and random POIs as controls), the research SHALL replay:
   - **A:** Model A's own OTE fills;
   - **B1, B2:** a limit at the POI's near edge or midpoint once armed, until C3 closes, with the stop beyond the POI's far edge;
   - **C:** after a MISSED, a limit at the midpoint of the leg from C2's extreme to the running low until C2's extreme is taken or the day ends, with the stop beyond C2's extreme.

   Each is held to the day's close, paying the spread, at a fixed 3R and at Model A's TP1.
2. AN entry that beats A, and beats the same entry on random POIs, SHALL go to the trader before Model A's orders (Requirement 14) are built on it.

## Update 2026-10-24: C1 Once C2 Has Run It

The trader (2026-10-24), on Noculus: "the engine keeps firing C1 all over while the fractals indicator actually shows the right logic for C1 C2 and C3." The C1s on the engine's side are Model A's (Requirement 17). The reader frames a candidate C1 at every C close where price is in F's premium with a POI above (discount with one below for longs), on both sides, and the chart drew the live candidate at every moment. Most end `NO_MANIPULATION` one candle later. The indicator marks a C1 only after the next candle, C2, has traded beyond it.

The trading logic already matches: only an instance whose C2 runs C1's high into the POI goes on (MANIPULATED, then REJECTED, DISPLACED and the entry). So the difference was the drawing.

### Requirement 26: C1 Once C2 Has Run It

**User Story:** As the trader, I want the engine's C1s drawn the way my indicator draws them, so that I see only the C1s price actually ran.

#### Acceptance Criteria

1. THE Model A layer SHALL draw an instance, list it and log its events only once it is MANIPULATED (C2 has run C1), as the indicator draws a C1.
2. A separate layer, "Model A: unswept C1s", off by default, SHALL show the framed candidates too. The card SHALL say how many are framed and unswept when none is shown.
3. THE reader is unchanged: when the premium is read (at C1's close, not at the sweep) and what happens when C3 takes C2's high before the order (RETRACE_INVALID, where the indicator makes C2 the next C1) are the remaining differences, left to the trader's choice. Task 363's re-anchored retest lost (−0.06 to −0.29R).

## Update 2026-10-24: The Chain, Tested Whole

Every layer of ICT's bias hierarchy has now been measured on its own, and each came out at chance:
- the draw on liquidity (the nearest pool is taken first as often as a random walk predicts);
- premium and discount on W1-H1;
- the previous candle's close (the 3-candle CRT);
- structure, ranked swings and breaks, and the trader's five-signal trend;
- delivery phases, time windows and macros;
- COT and news sentiment.

What was never tested is the hierarchy itself: each frame read in the light of the frame above it, from the monthly down to the day. The engine's grader reads bottom-up, so its filters can't choose. The trader's weekly calls (H011) and the LLM thesis are combined reads, but they are judgment, not a rule you can inspect, and their samples are small. Requirement 4's chain was specified on 2026-10-10 and never built.

The trader chose (2026-10-24), in this order:
1. build the frame state and the chain (tasks 277 and 278);
2. add ICT's IPDA data ranges as objectives;
3. pre-register the chain's daily calls as one hypothesis, with the pass rule confirmed before it runs;
4. score them before anything trades on them;
5. then SMT and the dollar index, as a separate hypothesis, so their own contribution shows.

Whatever its result, the chain is the first top-down reading the engine can explain frame by frame.

### Requirement 27: The IPDA Data Ranges

**User Story:** As the trader, I want the 20, 40 and 60-day highs and lows as objectives, so that the chain reads the reference points ICT says the algorithm reads.

#### Acceptance Criteria

1. FROM a market's closed D1 candles, the highest high and the lowest low of the last 20, 40 and 60 SHALL be objectives (CE-D17):
   - a high lies above price and a low below it;
   - each one formed at the close of the candle that made it;
   - a candle that leads more than one range is listed once, under its longest range.
2. A range SHALL be read only when that many closed D1 candles exist.
3. THEY SHALL be passed to every frame of the chain as objectives (Requirement 3's `levels`).

### Requirement 28: The Chain's Daily Calls, Measured

**User Story:** As the trader, I want the chain's daily calls tested on data nobody has read, so that a combined hierarchy is judged as strictly as each of its layers was.

#### Acceptance Criteria

1. ON the 2018-2024 search's broker D1 bars (`docs/research/SEARCH_2018_2024.md`, Amendment 1), the research SHALL build MN1 and W1 candles from the D1 candles and read the ladder MN1 → W1 → D1 at every D1 close (CE-D18):
   - the D1 frame's closed candles end with the candle just closed, and price is its close;
   - the W1 and MN1 frames' closed candles are the weeks and months already complete. The current ones are forming, and their extremes stretch the range;
   - the path is the D1 candles to t;
   - the IPDA ranges are objectives in every frame.
2. THE call SHALL be the D1 link's context direction under `PD_POI`, made only while the chain is armed and every frame has a dealing range. It is judged against the next D1 candle exactly as the search's daily calls are: the hit rate against the market's drift, with a trading-date interval, per market.
3. THE hypothesis (H-K) SHALL be written into the search's log, with its pass rule, and confirmed by the trader before it runs on the development window. The test window is read only if it passes.
4. Reported beside the pass rule, not part of it:
   - the absolute hit rate, against the 56-61% the executions need;
   - the draw reached before the opposite objective, against a driftless walk's chance;
   - the chain's cases apart;
   - the ablations: `PROFILE`, W1 → D1, the ladder without the IPDA ranges, and each frame's own direction alone.

### Requirement 29: SMT and the Dollar Index

**User Story:** As the trader, I want SMT divergence and the dollar index tested as their own layer, after the chain, so that what they add is measured apart.

#### Acceptance Criteria

1. AFTER Requirement 28 has reported, an SMT and dollar-index hypothesis (H-L) SHALL be registered in the search's log before it runs, with its own pass rule. The pairs: EURUSD-GBPUSD, US100-US500-US30, and DXY against EURUSD, GBPUSD and gold.
2. IT SHALL be judged alone and on top of the chain's calls, so the report shows whether it adds to the chain.

### Decisions (2026-10-24)

| Id | Topic | Decision |
|---|---|---|
| CE-D14 | The frame state's form | NumPy arrays and frozen dataclasses (`Candles`, `Objective`, `ArrayPOI`, `FrameState` in `context/frame_state.py`), like Model A's reader, not the design's Pydantic models: the research reads it at every D1 close of nine markets. |
| CE-D15 | POIs | The frame's and its parents' order blocks, breakers and gaps (Model A's arrays, gaps as the gap only). Liquidity is an objective, not a POI. |
| CE-D16 | Reached | A POI is spent if traded into between its forming and the close of the dealing range's later anchor candle. After that, the first bar trading into it reaches it. POIs are timed on the path, the finest bars given, or on the frame's own candles. A stretch past an anchor doesn't reset it. |
| CE-D17 | IPDA ranges | The last 20, 40 and 60 closed D1 candles, as ICT's lookback ranges. The forward-looking ranges and the quarterly shifts are left out. |
| CE-D18 | Weeks and months on D1 bars | A week closes with its Friday candle, and a month with its last weekday's. A week or month whose last trading day falls earlier closes when the next one opens. This is calendar only, never a later bar's price. |

## Update 2026-10-24b: The Chain on the Chart

H-K, H-L and H-M failed on 2018-2022. The trader asked to see the chain's reads on the candles, to judge whether its definitions read price the way they do before anything else is built on them.

### Requirement 30: The Chain and the Stack on the Chart

**User Story:** As the trader, I want the chain's frames, links and the stack's votes drawn on Noculus at each D1 close, so that I can see where its reading of price differs from mine.

#### Acceptance Criteria

1. NOCULUS SHALL serve, for each D1 candle closed by the replay clock (and ten before the session), exactly what H-K and H-M read at its close:
   - each frame's dealing range, zone, trend, own direction, draw and POIs, with their reasons;
   - the chain's links and the candle profile's;
   - the thirteen votes, the score and the stack's call. SMT abstains, because a session loads one market.
2. THE layer SHALL draw:
   - a strip of the D1 calls with their scores, and a tick or a cross once the next candle has closed;
   - the latest close's W1 and D1 ranges with their 50%, and the MN1 range faint;
   - the POIs (dashed once reached) and the chain's draw.

   A panel card SHALL spell out the frames, the links and the votes.
3. NOTHING SHALL be served while a session is blind, and nothing after the clock.

### Requirement 31: H-N, the M15 CRT, on the Chart

**User Story:** As the trader, I want H-N's trades drawn on Noculus (my M15 CRT at market on M1, with fixed targets and the partial), so that I can see on the candles what the rule takes and why it loses.

#### Acceptance Criteria

1. NOCULUS SHALL serve H-N's trades on the session's own M1 and spreads, through the search's own code (`algo_research.search_crt`), for each C3 that has opened by the replay clock:
   - C1's swept level and C2's wick;
   - the fill, the stop and 1R;
   - for each target (3R; 4R and 5R with the partial), the exits taken by the clock, and the R net once every exit is in the past.

   A trade the session's bars end before closing has no result.
2. THE layer SHALL draw, at the target chosen in a menu:
   - the risk and the target;
   - the 3R partial's level;
   - the exits, and the result after the last one.

   A panel card SHALL give the session's totals at the three targets, and the development result.
3. NOTHING SHALL be served while a session is blind, and nothing after the clock.
4. Added 2026-10-27 (H-O): each trade SHALL carry H-O's context:
   - the pools C2 took and the gaps it reached into, labelled at C2's wick;
   - the H4 trend;
   - whether H-O keeps it.

   This SHALL come through the search's own `algo_research.search_crt_context`, read on a month of the session's M1. A menu SHALL show every trade, only those at a gap, or only H-O's, with the card's totals for what is shown.

## Update 2026-10-29: The Trader's Weekly Context

Every mechanical side tried on the search's unread years came out at a random walk from the same close:
- the chain (H-K) and the stack (H-M);
- the turtle soup with the trader's raid, pool and discount (H-U);
- the side kept by the frames above, with the flip after delivery (H-V).

Meanwhile H-N's trades take both sides on 97% of market-days, and the losing side pays for the winning one. Sorted by the week's own close against its open, a hindsight upper bound, the trades on that side made +0.18R before costs and the others −0.07R. With stops of ten spreads or more, the week's side made +0.16R (3R) and +0.19R (5R) after costs. Called right 57-60% of the time, one weekly side clears the costs.

The trader (2026-10-29): "a trade with context beats a trade that was basically just Model A showing". They will call the context of all nine markets each week. The engine executes only inside it.

### Requirement 32: The Trader's Weekly Context

**User Story:** As the trader, I want to give each market's context once a week (the side, the draw and the protected swing) and have the engine trade only inside it, so that its execution follows my read instead of every setup that shows.

#### Acceptance Criteria

1. **A call.** A CALL SHALL be one market's context for one trading week (Sunday 17:00 to Friday 17:00 New York):
   - the side: BULLISH, BEARISH or NONE;
   - the draw;
   - the protected swing (a bullish call's protected swing is below its draw, and a bearish call's above);
   - an optional note;
   - the time it was made.

   A call made after its week opened is kept but marked late. The calls are journal data: local and git-ignored.
2. **The thesis file.** THE calls SHALL write the engine's thesis file (market-narrative Requirement 17), one entry per trading date of the week: the side, the draw, the protected swing and `since`, the later of the week's open and the call's time.
3. **When a context ends.** UNDER `bias_mode = THESIS`, a setup against the entry's side is refused as before (`AGAINST_THESIS`), and a date with no entry as before (`NO_THESIS`). When an entry carries a draw, the context ends:
   - **delivered:** once price has traded at the draw since `since`, refused as `THESIS_DELIVERED`;
   - **invalidated:** once a D1 candle has closed beyond the protected swing since `since`, refused as `THESIS_INVALIDATED`. A wick beyond it is liquidation and does not end the context.

   A plain side entry keeps its old meaning.
4. **The page.** NOCULUS SHALL have a context page:
   - for a chosen week (by default the next to open), the nine markets with their last price when the terminal is connected;
   - each market's call, with its side, draw and protected swing checked on entry;
   - saving a call rewrites the thesis file.
5. **The variant.** THE configuration SHALL have a variant that trades the partial strategy only inside the calls: `bias_mode = THESIS` on the calls' thesis file, with stops of at least ten typical spreads. A paper agent SHALL run it on the control agents' markets, beside them.
6. **The scorecard.** A SCORECARD SHALL give, for each called week and market:
   - **the call:** side, draw and protected swing, and whether it was late;
   - **the week:** its open and close, and whether it closed on the call's side;
   - **the context:** delivered, invalidated or still open, and when, with a random walk's chance of reaching the draw before the protected swing from the price at `since`;
   - **the paper agents:** the R net of the trades placed in the week by the context agent and by each control.

   Its totals SHALL give the hit rate of the week's close against the 57-60% the costs need.

### Requirement 33: The Trader's Sequence

**User Story:** As the trader, I want the engine to read a market-day the way I do, top-down, time first and then price, so that it takes the one setup my narrative allows instead of every setup that shows.

The rules come from the trader's Backtest Diary for GBPUSD, Thursday 29 Oct 2026, and their answers of 31 Oct 2026. New York time throughout.

#### Acceptance Criteria

1. **The soup.** A TURTLE SOUP on any frame SHALL be two candles, named by the first: C2 trades beyond C1's low (high) and closes back inside C1. It SHALL be valid once the frame below confirms a CISD: a close beyond the open of the run of opposite candles that delivered C2's extreme. A candle of the trade's colour, or a doji (a body under a tenth of its range), ends the run.
2. **The narrative.** THE side SHALL come from the latest valid W1 soup:
   - its C2 falls in the month's first two weeks;
   - its extreme took an untaken low (high) of the last four quarters or three months (external range liquidity);
   - a D1 CISD confirmed it by C2's close.

   Its draw SHALL be the nearest W1 gap beyond C2's close whose CE price hasn't reached (internal range liquidity), else a D1 one. The side SHALL end when price reaches the draw's CE (delivered) or a D1 candle closes beyond C2's extreme (invalidated; a wick beyond it is liquidation). A soup against a live side SHALL be ignored as manipulation.
3. **The setup.** A DAY SHALL be C3 only after a D1 soup on the side whose C2 falls on Monday to Wednesday, whose extreme lies inside a key level, and whose H4 or H1 CISD confirmed by C2's close. A key level is a D1 or W1 gap of the side, an inverted gap of the other side, or an opening gap (NDOG, NWOG) of the last ten trading days.
4. **C3.** Q1 (18:00-00:00) SHALL set the range. In Q2 (00:00-06:00) price SHALL take Q1's extreme against the side (the Judas swing), and an M5 CISD before 12:00 SHALL confirm it.
   - The limit SHALL go at the open of the run's last candle (the order block), when that is in discount (premium) of the leg from the Judas extreme.
   - It is good until 12:00.
   - Its stop is the Judas extreme.
5. **The targets.** THE read SHALL list the Judas swing's deviations (−1, −2, −2.5, −4 and −4.5, from the last M5 swing before the extreme). For each it SHALL give the pools and gaps within a fifth of a deviation and the distance in average daily ranges, and it SHALL mark the deviation in confluence with the narrative's draw.
6. **The acceptance test.** ON the trader's GBPUSD long of Thursday 29 Oct 2026, the reader SHALL find, from the bars closed at each step:
   - their narrative: the Q2 low taken, and the September W1 gap as the draw;
   - their soup: Tuesday-Wednesday, into the D1 inverted gap and the 16 Oct NDOG;
   - their H4 and H1 CISD runs;
   - their order block (1.33030, filled 09:18) and their stop (1.32956);
   - their target: the −4 deviation at the W1 gap's edge.
7. **Frozen per sample.** THE reader SHALL be committed before each new sample of the trader's is read, and the committed version reads each sample first. Changes a sample prompts SHALL come after that read, as a new version.
