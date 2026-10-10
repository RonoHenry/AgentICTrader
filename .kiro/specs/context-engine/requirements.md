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
