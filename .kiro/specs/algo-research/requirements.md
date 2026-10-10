# Requirements Document

**Spec**: AlgoResearch

## Introduction

AlgoResearch measures whether a market condition carries information about what price does next, before any of it becomes a strategy rule. It answers one question, in seconds and with honest statistics:

> Does this condition predict what price does next better than chance, and better than the obvious simple rules, on data it wasn't designed on?

Where it sits:
- **Upstream of AlgoBacktester.** Research discovers; the backtester confirms with full costs, fills and the account; the study hold-out and the paper forward test decide.
- **Beside the Liquidity Engine.** It reads the engine's own outputs (the daily anticipation, the setup sequence) instead of re-implementing them, so a finding transfers to the strategy.

Why now. The baseline (task 211) and the setup-sequence runs (task 233) failed their pass mark. A whole-system run costs about 2 hours and returns one number, which says *that* the system fails but not *why*. The leads that exist came from diagnostics written by hand in scratch scripts:
- the hindsight split by the day's direction (+0.46R with the day, −0.68R against it);
- the market-timing statistics (daily extremes in the 01:00/05:00/09:00 H4 candles, 6–11 points above chance);
- the break-even replay (BODY trades follow through after +1R: 24% vs 18% by chance);
- the CRT C3 expansion test.

AlgoResearch makes that work repeatable, fast and honest:
- every question is written down, with its pass mark, before it runs;
- every number is shown next to baselines, with an interval that respects how correlated the data is;
- every test is counted.

**Guiding constraint**: validate before building. AlgoResearch changes no live code and no backtester code, adds no dependencies, and uses no machine learning until a rule-based finding exists (AR-D10).

---

## Glossary

- **Decision time (t)**: the instant a question is asked: the close of an M15 bar. Only data known at t may describe the situation at t.
- **Feature**: a value known at t (a column of the feature table). Example: whether the Asian low has been raided by t.
- **Label**: a value about what happened after t (a column of the label table). Example: whether the previous day's high traded later that day.
- **Trading date**: the New York date of the D1 candle containing t. The candle opens at 17:00 New York, so Sunday 17:00 belongs to Monday.
- **Event**: a named condition on features that selects decision times, with a direction where it implies one. Example: London raided the Asian low and an M15 bar closed back above it.
- **Race**: a hypothetical market order at t with a stop, a target and a time limit, run on the M1 path with the backtester's price rules. It ends at TARGET, STOP or TIMEOUT.
- **Baseline**: what a statistic would be without the information under test: a coin flip, the same trade at random times, a simple rule, or a shuffled price path.
- **Hypothesis**: a file stating a question, its event, its measure, its baselines and its pass rules. It is committed before the data that judges it is read.
- **Ledger**: the append-only record of every official test and its result.
- **Slices**: the research period split in two. The *exploration slice* is for building and debugging questions; the *confirmation slice* judges them. The study's hold-out is never read.
- **Day cluster**: all rows of one trading date, across instruments. EURUSD and GBPUSD on one morning are close to one observation, so intervals resample whole days.
- **Snapshot**: a frozen, fingerprinted copy of the candles a study uses.
- **Graduation**: turning a passed hypothesis into a strategy variant, specified in the `liquidity-engine` spec and judged by the backtester.

---

## Non-Goals

Recorded so they are not silently forgotten, and not bolted on mid-implementation.

- **Strategy rules.** A passed hypothesis becomes a proposal for a `StrategyConfig` variant in the `liquidity-engine` spec. AlgoResearch doesn't change the engine, the grader, the order logic or the backtester.
- **Automated search.** No grid search or optimiser. A hypothesis may list a few parameter values, and each one counts as a test.
- **The hold-out.** AlgoResearch never reads it. It is reserved for the backtester's `--final` run.
- **Account simulation.** Sizing, risk caps, concurrent trades, swap and compounding are the backtester's job. Races charge the spread, stop slippage and commission only.
- **Tick data.** M1 is the resolution. When one M1 bar reaches both a race's stop and target, the stop wins (the fill model's rule) and the share of such bars is reported.
- **Machine learning.** Gated behind AR-D10. Meta-labelling is specified only once its gate is met.
- **AlgoRAG and LLMs.** Not used.
- **A web interface.** Reports are Markdown files in the repository.

---

## Requirements

### Requirement 1: Research Data Snapshot

**User Story:** As the researcher, I want a frozen, fingerprinted copy of the study's candles, so that every result is reproducible and research runs without Docker.

#### Acceptance Criteria

1. `python -m algo_research snapshot` SHALL export, per instrument, every bar that `load_instrument()` reads for the research period: the M1 bars and the native bars of the warm-up. It reads them from the broker profile's candle store and writes Parquet files under `data/research/snapshots/<name>/`.
2. THE snapshot SHALL end at the study's `holdout_start`, and SHALL refuse a later end. No bar opening at or after `holdout_start` is ever written (Property 10).
3. A manifest SHALL record:
   - the profile, venue, source, instruments and period;
   - the `StrategyConfig` candle windows that set the warm-up;
   - per instrument: the row count, the `DataFingerprint` and the coverage problems;
   - the instrument spec source;
   - the git commit and the creation time.
4. `SnapshotSource` SHALL implement `CandleSource`. `load_instrument()` on a `SnapshotSource` SHALL return the same `InstrumentData.fingerprint` as on the store the snapshot came from.
5. Loading SHALL recompute each instrument's fingerprint, and SHALL refuse a snapshot whose data no longer matches its manifest.

### Requirement 2: Decision Grid and Trading Calendar

**User Story:** As the researcher, I want every question asked at the moments the engine decides, on the engine's calendar, so that findings transfer to the strategy.

#### Acceptance Criteria

1. THE grid SHALL be the close of every M15 bar of the strategy calendar that has M1 data, per instrument, within the research period. A row's t is that close.
2. EACH row SHALL carry:
   - `trading_date` and `weekday` (0 = Monday);
   - `ny_minute`, the minutes since 00:00 New York;
   - `h4_index`, 0 to 5: the H4 candle containing t, of those starting at 17:00, 21:00, 01:00, 05:00, 09:00 and 13:00 New York;
   - `in_window`, whether t is in the manipulation window, 01:00 to 13:00 New York (LE-D11);
   - `killzone`, from `get_killzone(t)`;
   - `slice`.
3. THESE values SHALL equal those of `StrategyCalendar` and the engine's time utilities at every instant, on both sides of each DST change (Property 3).
4. A feature that lacks the history it needs SHALL be null, never a guessed value. A hypothesis that reads a null feature skips the row and counts it.

### Requirement 3: Market Features

**User Story:** As the researcher, I want the facts a trader reads off the chart at t as columns, so that a condition is one line instead of a script.

#### Acceptance Criteria

1. THE feature table SHALL hold one row per grid time with the market features listed in design.md. They cover:
   - the opens (D1, midnight, H4) and price's side of each;
   - the candle so far;
   - the Asian range and its raids;
   - the previous day's and week's levels, and whether they were taken;
   - the W1 trend;
   - volatility and spread.

   Each feature SHALL be computed only from M1 bars and strategy-calendar bars that closed at or before t (Property 1).
2. Prices SHALL be bid, as stored.
3. WHERE the engine defines the same fact, the feature SHALL use the engine's definition, and SHALL equal the engine's value on fixture windows (Property 4):
   - the Asian range (LE-D12, Req 20.2);
   - the W1 trend (LE-D15);
   - the killzone;
   - the manipulation window.
4. Each feature's definition, unit and the time it becomes known SHALL be documented where it is computed.
5. THE table SHALL be cached as Parquet under a key over the snapshot fingerprint and the feature code, and rebuilt when either changes.

### Requirement 4: Daily Anticipation from the Engine

**User Story:** As the user, I want the engine's anticipation of each D1 candle on every row, so that my Power of 3 bias is tested as the engine implements it, not as a copy.

#### Acceptance Criteria

1. FOR each instrument and D1 candle, AlgoResearch SHALL run `LiquidityMappingEngine.analyze()` once:
   - at the candle's first M15 close (17:15 New York);
   - on the as-of view Phase A builds (`compose_as_of_view`);
   - with the base `StrategyConfig`.
2. EVERY row of that candle SHALL carry the candle profile's anticipation: trend, direction, draw, draw above and draw below (price, source and timeframe). Liquidity-engine Property 35 makes these equal at every t in the candle; a test SHALL check it on fixture days.
3. THE rows SHALL be cached under a key over the snapshot fingerprint, `engine_code_fingerprint()` and the `StrategyConfig`.
4. AN engine error on a day SHALL leave that day's anticipation null and be counted, not raised.

### Requirement 5: Engine Features at Every Close (stage 2)

**User Story:** As the researcher, I want what the engine saw at every M15 close, so that its setup sequence, its grade and its orders can be measured against chance.

#### Acceptance Criteria

1. AlgoResearch SHALL evaluate the engine at every grid time as Phase A does (`compose_as_of_view`, `analyze()`, `build_order_intent`). Each evaluation SHALL be recorded as one flat row:
   - the setup sequence: the raid, the CISD, the entry array and the protected swing;
   - the grade and the conditions met;
   - the candle profile's facts at t;
   - the decision: the order intent's direction, entry, stop, target and R:R, or the `NoTrade` reason.
2. IT SHALL run in parallel per instrument and be cached as in Requirement 4.3.
3. IT SHALL NOT change AlgoBacktester code or its Phase A cache.

### Requirement 6: Labels — What Happened Next

**User Story:** As the researcher, I want outcomes after t kept apart from the facts known at t, so that nothing about the future can leak into a condition.

#### Acceptance Criteria

1. LABELS SHALL be computed in their own module and table. The feature, event and filter code SHALL NOT import the label code, and a test SHALL check those imports. A hypothesis's event and filter SHALL read feature columns only. Label columns may appear only in its measure (Requirement 8).
2. THERE SHALL be two kinds of label:
   - **Forward labels** use only bars opening at or after t (Property 2).
   - **Candle labels** describe the whole D1 candle, so they include bars before t. They are valid only with the `daily` event, which asks descriptive questions about whole candles (e.g., when the day's low formed). Hypothesis validation SHALL refuse a candle label with any other event.
3. THE forward labels SHALL include, per row:
   - the remaining move to the D1 close (the last M1 close before 17:00 New York), and the move at fixed horizons (1 h and 4 h), in price and in ATR;
   - for each feature level (PDH, PDL, PWH, PWL, the Asian high and low): whether, and when, it traded after t within the candle.
4. THE candle labels SHALL include the D1 candle's final direction, its high and low, and the H4 candle each formed in.

### Requirement 7: Races Priced Like the Backtester

**User Story:** As the researcher, I want "does price reach the target before the stop" measured with the backtester's own price rules, so that a research edge doesn't vanish when it's backtested.

#### Acceptance Criteria

1. A race SHALL be defined by a row, a direction, a stop, a target and a time limit.
   - It enters as a MARKET order at the open of the first M1 bar at or after t.
   - It ends at the stop, the target or the time limit.
   - At the time limit it is a TIMEOUT, exited at the last M1 close before the limit, on the closing side.
2. FILLS, stops, targets, gaps, the stop-first rule, stop slippage and REJECTED entries SHALL follow `FillModel` (algo-backtester Requirement 4). Bars SHALL be priced as `fill_bars()` prices them (algo-backtester D10). The race engine SHALL agree with `FillModel` on every case (Property 5).
3. EACH race SHALL report:
   - the outcome, and the entry and exit times and prices;
   - gross and net R, with R as the backtester defines it: |entry − stop| on the executed entry;
   - MFE and MAE in R;
   - an `ambiguous` flag when one M1 bar reaches both the stop and the target.
4. COSTS SHALL be the bar spread (paid on the buy), stop slippage and the spec file's commission, converted to R per lot. Swap is not charged (AR-D6).

### Requirement 8: Hypotheses and Pre-registration

**User Story:** As the user, I want every question written down with its pass mark before it sees the data that judges it, so that a lucky result can't pass for an edge.

#### Acceptance Criteria

1. A hypothesis SHALL be a TOML file `config/research/hypotheses/H<nnn>-<slug>.toml` holding:
   - id, title, a plain-language statement, family and created date;
   - the event and an optional filter;
   - the measure, and the trade for races;
   - the baselines, and the pass rules with minimum sample sizes.

   Its schema SHALL be validated before any data is read, and errors SHALL name the field.
2. AN official run (`run`) SHALL refuse when the hypothesis file is uncommitted or has uncommitted changes, or when `algo_research/` has uncommitted changes.
3. THE ledger SHALL store the file's sha256 with its first result. A later run of the same id with a different hash SHALL be refused. A changed question is a new hypothesis, with a new id and `supersedes = "H<nnn>"`, and both count.
4. A rerun with the same hash SHALL reproduce the recorded result exactly; any difference is an error (Property 9).
5. A hypothesis MAY list a few values for one parameter. Each value counts as one test in the ledger.

### Requirement 9: Events and Filters

**User Story:** As the researcher, I want each condition defined once, in tested code, so that "London raided the Asian low and closed back inside" means the same thing in every test.

#### Acceptance Criteria

1. EVENTS SHALL be named, tested functions in `algo_research/events.py`. Each takes the feature table and its parameters, and returns event rows with a direction (LONG, SHORT or none) and the levels a trade may use (e.g., the raid's extreme).
2. AN event SHALL read only feature columns of rows at or before its own t (Property 1 applies).
3. A hypothesis MAY add `where`, a filter over feature columns using comparisons, `in`, `and`, `or` and `not`. Any other syntax, and any column that isn't a feature, SHALL be refused.
4. AN event SHALL fire at most once per instrument, trading date and direction, unless its parameters say otherwise.

### Requirement 10: Baselines

**User Story:** As the researcher, I want every number next to what chance and simple rules give, so that I can tell information apart from trend, time-of-day volatility and the arcsine law.

#### Acceptance Criteria

1. **Coin flip** (races): over the events, the mean of (bid at entry − stop) ÷ (target − stop) for LONG, mirrored for SHORT. That is a driftless path's chance of reaching the target first.
2. **Random time** (races, direction, moves): for each event, K draws (default 20) from the same instrument and New York 15-minute slot, on other trading dates of the same slice that have no event for that instrument. *Amended by update 2026-10d: only the event's own trading date is excluded.*
   - The draws take the event's direction.
   - They take the event's stop and target distances in units of `atr_d1`, rescaled by the drawn row's `atr_d1`.

   This controls for drift (gold rose through 2025), time-of-day volatility and the stop/target geometry.
3. **Naive rules** (direction): always long; the previous day's direction; the W1 trend; price's side of the D1 open at t; price's side of the midnight open at t. A hypothesis names the rules it must beat, and the verdict compares it with the best of them.
4. **Stratified rate** (day facts): the unconditional rate among rows in the same bucket of distance to the level (ATR deciles over the slice) and the same New York hour.
5. **Shuffled path** (timing statistics): the statistic recomputed after shuffling each trading date's M15 moves while keeping its open and close, averaged over 200 shuffles. This is the method of liquidity-engine design "Update 2026-10b".
6. BASELINE draws SHALL be reproducible: their seed derives from the hypothesis id and hash.

### Requirement 11: Statistics and Verdict

**User Story:** As the user, I want error bars that reflect how much independent evidence there really is, and a verdict decided by the rules written beforehand.

#### Acceptance Criteria

1. INTERVALS SHALL come from a bootstrap over trading dates:
   - each resample draws whole dates, with all of a date's instruments, events and baseline draws together;
   - 10,000 resamples, 95% percentile intervals;
   - a difference against a baseline is bootstrapped paired, date by date. When the comparison is with the best naive rule, the best rule is chosen again within each resample.
2. A pass rule SHALL read: the interval's lower bound for `stat − baseline` (or for `stat` alone) is above `min_effect`, which defaults to 0.
3. THE verdict SHALL be:
   - INSUFFICIENT when there are fewer events than `min_events` or fewer distinct dates than `min_days`;
   - otherwise PASS when every rule holds;
   - otherwise FAIL.
4. THE report SHALL show the effect per instrument, per quarter and per weekday, and the share of quarters where the effect has the same sign. A result carried by one instrument or one month is then visible. These breakdowns inform; only the declared rules decide.
5. DUPLICATING rows within a trading date SHALL NOT narrow an interval (Property 7).

### Requirement 12: Ledger and Reports

**User Story:** As the user, I want one place showing every question asked and its answer, so that I see how many ideas were tried, not just the ones that worked.

#### Acceptance Criteria

1. EVERY official run SHALL append one row to `docs/research/ledger.csv`. The ledger is append-only: earlier rows are never rewritten. Each row holds:
   - the sequence number and the time;
   - the hypothesis id and sha256, the family and the slice;
   - the snapshot fingerprint and the code commit;
   - the event and date counts, the statistic and each baseline;
   - the intervals, the verdict and the report path.
2. EVERY official run SHALL write `docs/research/reports/H<nnn>.md`, containing:
   - the statement, the event and the pass rules as registered;
   - event counts by instrument, year and weekday;
   - results against each baseline, with intervals, and the breakdowns of Requirement 11.4;
   - the share of ambiguous bars;
   - the first 20 event times per instrument, for checking by eye on a chart;
   - the inputs: snapshot, code commit and spec values.
3. `python -m algo_research ledger` SHALL render `docs/research/LEDGER.md`. It lists every test so far by family, with the number of official tests and the number of passes expected by chance (2.5% per rule when nothing is there).
4. EXPLORE runs (`explore`) SHALL print to the terminal and write only under `data/research/drafts/`. They never touch the ledger.

### Requirement 13: Out-of-Sample Discipline

**User Story:** As the user, I want ideas built on one part of the data and judged on another, so that a finding isn't the data describing itself.

#### Acceptance Criteria

1. THE research period SHALL be split into the exploration slice and the confirmation slice (AR-D3). `explore` reads only the exploration slice; `run` reads only the confirmation slice.
2. AlgoResearch SHALL NOT read the study hold-out (Property 10).
3. RANDOM-TIME and stratified baselines SHALL draw from the same slice as the events.
4. A PASS SHALL graduate only as a proposal:
   - a `StrategyConfig` variant specified in the `liquidity-engine` spec;
   - backtested on the study with its own pass mark, written before the run;
   - then the hold-out once.

### Requirement 14: Self-Validation

**User Story:** As the user, I want proof that the research tool finds nothing where there is nothing, and finds an edge where one is planted, so that I can trust a PASS.

#### Acceptance Criteria

1. **Null calibration.** On simulated random-walk markets (no edge, session-shaped volatility, a spread), a race hypothesis and a direction hypothesis SHALL each PASS in at most 5% of 200 simulated worlds; about 2.5% is expected (Property 8).
2. **Planted edge.** When a known drift is injected after the event in the same worlds, they SHALL PASS in at least 90% of worlds. The reported interval SHALL contain the planted effect in at least 90% of worlds.
3. **Golden research run.** A fixed fixture and hypothesis SHALL produce a byte-identical report and ledger row on every run. A change that alters them on purpose regenerates them in the same commit (`UPDATE_GOLDEN=1`).
4. **Speed.** On this machine, for 4 instruments and 18 months:
   - building the market features, the daily anticipation and the labels SHALL take under 10 minutes;
   - one hypothesis run SHALL take under 2 minutes;
   - the stage-2 engine features (Requirement 5) are excluded.

---

## Update 2026-10c: Ideas from the Fractal + POI Indicator

On 2026-10-09 the user shared a TradingView indicator ("Fractal + POI") that frames a higher-timeframe candle (C1, C2 sweeping it, C3) and executes on a lower one, with SMT divergence across correlated instruments and Quarterly Theory sessions. Its direction is a manual input. The ideas are tested here before any of them reaches the engine (Requirements 15–17, and 9.5).

Requirement 9 gains:

5. `where` MAY also read the event's own columns: its direction, its levels and its attributes (e.g. `smt`). They are computed from the event's row, so they are known at its t. A direction-relative filter, such as "with the W1 trend", is then written once for both sides.

### Requirement 15: Higher-Timeframe Candle Ranges

**User Story:** As the researcher, I want the indicator's candle-range model as features and an event, so that "C2 swept C1 and closed back inside" can be measured against chance, alone and with a bias.

#### Acceptance Criteria

1. For H1, H4 and D1, each row SHALL carry the last candle closed by t (C2) and the one before it (C1):
   - their highs and lows, and C2's close time;
   - C2's side: +1 when C2 traded below C1's low, not above its high, and closed above C1's low; −1 mirrored; 0 otherwise.

   They are known at C2's close (Property 1).
2. THE `crt` event SHALL fire at the M15 close equal to C2's close when C2's side is ±1: LONG when C1's low was swept, SHORT when its high was.
   - Its levels: C2's extreme on the swept side (the stop) and C1's opposite extreme (the target).
   - Its time limit: the close of the next candle (C3).
3. A race MAY use the event's own time limit (`time_limit = "event"`). Random-time draws keep the event's duration.

### Requirement 16: SMT Divergence

**User Story:** As the researcher, I want to know whether a sweep that a correlated instrument fails to confirm behaves differently, so that SMT divergence is tested, not assumed.

#### Acceptance Criteria

1. THE configuration SHALL name correlated pairs (default: EURUSD with GBPUSD). An instrument in no pair has null partner columns.
2. Each row SHALL carry its partner's facts at the same t:
   - whether the partner has raided its own Asian high and its own Asian low;
   - whether the partner's C2 swept its C1 high and its C1 low, on H1, H4 and D1.

   They are read from the partner's row at the same t, so they are known at t. A missing partner row, an unknown Asian range, or a partner C2 that is a different candle gives null.
3. THE `asia_raid_reclaim` and `crt` events SHALL carry the attribute `smt`: true when the partner did not take its own matching level on the event's side (a low for LONG, a high for SHORT), false when it did, null when unknown.

### Requirement 17: Daily Quarters

**User Story:** As the researcher, I want the Quarterly Theory's daily quarters as timing labels, so that "the manipulation forms in the London quarter" is checked against shuffled paths.

#### Acceptance Criteria

1. Candle labels SHALL include the daily quarter (New York) of the M1 bar that made the candle's high and of the one that made its low:
   - 0 = 17:00–00:00 (Asia, the rollover hour included);
   - 1 = 00:00–06:00 (London);
   - 2 = 06:00–12:00 (New York AM);
   - 3 = 12:00–17:00 (New York PM).
2. THE shuffled-path baseline SHALL recompute them.

---

## Update 2026-10d: Baseline Corrections

On 2026-10-09 the first explore runs showed two baseline problems:
- **Starved random-time draws.** The random-time baseline excluded every date with an event. H001's `anchor` event fires on every date, so each event got 0–2 draws instead of 20, and the baseline read 67% at 05:00 and 37% at 09:00. No verdict changed: H001's rule compares with the naive rules.
- **Timing measured against the wrong null.** The H4 timing result (lows of up days +8 points over `shuffled_path`) may be volatility, not timing. Shuffling a day's M15 bars spreads the London and New York volatility over the day. Even a random walk makes its extremes where it moves most, so `shuffled_path` overstates a timing effect.

Requirement 10 changes:

2. **Random time (amended).** The draws come from the same instrument, New York 15-minute slot and slice, on any trading date except the event's own.
   - Other event dates are allowed. They make the baseline more like the event, so a pass gets harder, never easier.
   - An event that fires every day still gets its K draws.
7. **Sign flip** (timing statistics). The statistic is recomputed after flipping each M15 bar's direction at random, averaged over the same number of draws as `shuffled_path`.
   - Each bar keeps its time slot and its size. A flipped bar is mirrored: its move changes sign, and its high and low swap roles.
   - The day's volatility therefore stays where it was, while direction is random. A timing effect that beats `sign_flip` is about when the turns happen, not when the moves are big.
   - Each event is compared with its own date's flips, conditioned the same way: for "lows of up days", over the flips in which that day closes up.
8. **Starved baselines.** WHEN a pass rule compares with `random_time` AND the measured events average fewer than K/2 draws, the verdict SHALL be INSUFFICIENT, and the report SHALL say why.

## Update 2026-10e: Bias as Delivery, and Session Volatility

On 2026-10-10 the user corrected three of the first drafts (H001, H003, H004, H007):
- **Bias is not a forecast of the close.** "We do not need to predict the close. We just need to identify bias and capitalize on that." Bias is also fractal: a bullish day can sit in a bearish month, and a bullish H4 looks bearish on M5–M1 while it seeks sell-side liquidity.
- **The method is a sequence, and it is probabilistic.** "Trading is a game of probabilities." With a bullish bias:
  1. find the sell-side objectives below the open (PD arrays, liquidity), using the regular and true day opens and the intraday price action;
  2. wait for price to go lower first and reach one;
  3. only there, look for the algorithmic signatures (the user's model), and go long toward buy-side.
- **Time works through volatility.** Highs and lows sit in the sessions that carry most of the range, and which sessions depends on the asset: Asian pairs often make the day's extremes in the first two H4 candles. "Volatility varies across sessions of the trading day", so it belongs in AlgoResearch and in AgenticTrader.

The 2026-10d results agree. The timing excess vanished against `sign_flip`: the extremes cluster where the market moves most.

So this update:
- measures bias by what the candle **delivers**: is the engine's draw on the bias side reached?
- tests the sequence as a race, with a control on the days the bias disagreed;
- makes session volatility a feature set and a descriptive per-instrument profile.

H001 and H003 are redrafted, and H004 and H007 are withdrawn. None of them was ever pre-registered.

### Requirement 18: The Engine's Draws as Levels

**User Story:** As the user, I want to know whether the objective my bias points to gets delivered, so that bias is judged the way I trade it, not by the close.

#### Acceptance Criteria

1. EACH row SHALL carry `ant_draw_above_taken_at` and `ant_draw_below_taken_at`: the close of the first M1 bar in the current D1 candle that traded beyond the engine's draw above (below) the open: a high above it (a low below it), as PDH and PDL are taken. They are known at that close, and null before it (Property 1).
2. THE forward labels SHALL include `ant_draw_above_hit_after`/`_hit_at` and `ant_draw_below_hit_after`/`_hit_at`: whether, and when, an M1 bar opening at or after t and before the D1 close trades beyond the draw (Property 2).
3. THE `anchor` event SHALL accept `level = "draw"`. Each row then carries the engine's draw on its direction's side as `level` (the draw above for LONG, below for SHORT), with `level_name`, so a rate measure can read `level_hit_after`. Rows whose level is unknown or already taken SHALL be skipped and counted. `anchor` SHALL also accept `at = "open"`, each candle's first M15 close with its D1 open known (17:15 for FX, after gold's daily break), and a fixed `direction` (LONG or SHORT) instead of `direction_from`, so "the draw above on bullish-bias days" can be compared with "the draw above on the other days" (`where` plus `complement`).
4. THE `stratified` baseline SHALL accept the engine's draws. Its pool is both draws on every row of the slice where they are known and untaken, bucketed by distance decile (in `atr_d1`) and New York hour.

### Requirement 19: The Objective-Touch Event

**User Story:** As the user, I want "price went lower first into a sell-side objective below the open" as an event, so that the second step of my sequence is measured on its own, before the algorithmic signature is added.

#### Acceptance Criteria

1. THE `objective_touch` event SHALL fire, per instrument and D1 candle and per side, at the first M15 close inside `window` (default 01:00–13:00 New York) after an M1 bar has traded below `ant_draw_below_price`.
   - It fires only while the draw above is still untaken.
   - Its direction is LONG.
   - Mirrored: above `ant_draw_above_price`, with the draw below untaken, it is SHORT.
2. ITS levels SHALL be:
   - `objective`, the touched draw;
   - `touch_extreme`, the furthest price beyond the objective from the touch to the event's close;
   - `draw_opposite`, the other draw.
3. ITS attribute `with_bias` SHALL be true when the engine's anticipated direction equals the event's direction, and false when it is the opposite. It is null when the anticipation is NEUTRAL or missing.
4. ALL of it SHALL be known at the event's t (Property 1).

### Requirement 20: The Complement Baseline

**User Story:** As the researcher, I want the same event measured where my condition does not hold, so that "with the bias" is compared with "against the bias" on the same footing.

#### Acceptance Criteria

1. **Complement** (race, rate, direction, move): the event's rows where the hypothesis's `where` is false, measured exactly as the event rows are. Rows where `where` is null are in neither group.
2. A hypothesis SHALL use `complement` only with a non-empty `where`.
3. COMPLEMENT rows SHALL enter the date bootstrap like the event rows, resampled by trading date. They are reported with their own counts and their own breakdown by instrument.
4. THE same baseline SHALL serve any twin comparison: in a time window against outside it (`where = "in_window"`), with SMT against without, and so on.

### Requirement 21: Session Volatility

**User Story:** As the user, I want each instrument's normal volatility per session, and whether today is running hotter or colder, so that stops, targets and activity follow when that market actually moves.

#### Acceptance Criteria

1. EACH row SHALL carry, from the previous 20 trading dates of the same instrument only (known at t):
   - `slot_range_norm`: the median range of M15 bars in this New York 15-minute slot;
   - `h4_range_norm`: the median full range of this H4 candle (by `h4_index`);
   - `h4_range_so_far_norm`: the median range of this H4 candle from its open up to the same minute;
   - `h4_range_ratio`: the current H4 candle's range so far ÷ `h4_range_so_far_norm`. Above 1 means hotter than normal.
2. A race's stop and target MAY be `{ kind = "h4_range", value = k }`: k × `h4_range_norm` from the row's close, as `atr` is measured.
3. `python -m algo_research profile` SHALL write `docs/research/VOLATILITY_PROFILE.md` from the exploration slice. Per instrument, it holds:
   - the median range of each H4 candle, and its share of the day's range;
   - the hour of the day's high and of its low;
   - the same split by weekday.

   It is descriptive, with no verdict and no ledger row.
4. Features that lack 20 prior dates SHALL be null (Req 2.4).

## Open Decisions

Proposed defaults apply unless the user changes them at review.

| # | Decision | Proposed default |
|---|---|---|
| AR-D1 | Names and numbering | Package `algo_research/`, spec `.kiro/specs/algo-research/`. Tasks continue the platform sequence from 244. |
| AR-D2 | Decision grid | M15 closes: the engine's entry timeframe and the backtester's evaluation times. |
| AR-D3 | Slices | Exploration 2025-01-01 → 2025-07-01; confirmation 2025-07-01 → 2026-07-07 (the study `baseline-2026q3` hold-out start). The hold-out is never read. The scratch diagnostics of 2026-10-08/09 used the whole period, so ideas drawn from them are not independent of the confirmation slice; the hold-out stays the final word. |
| AR-D4 | Default pass rules | Each required comparison's 95% lower bound above 0; at least 100 events on at least 60 trading dates. Race hypotheses also require the lower bound of mean net R above 0: an edge must survive costs, not just beat chance. |
| AR-D5 | Bootstrap | 10,000 resamples of trading dates; 95% percentile intervals; seed from the hypothesis hash. |
| AR-D6 | Race costs | Bar spread (floored at the typical spread), stop slippage and commission, from the broker profile's spec file. No swap; time limits default to the D1 close. |
| AR-D7 | Random-time baseline | 20 draws per event: same instrument and New York 15-minute slot, other dates of the same slice. |
| AR-D8 | What is committed | Hypotheses, reports and the ledger are committed. Snapshots and caches stay in `data/research/` (git-ignored). |
| AR-D9 | First batch | H001–H004 (design.md "First hypotheses"), then H005–H006 once stage 2 exists. The user confirms each file's pass rules before it is committed. |
| AR-D10 | Machine learning | Gated: considered only once a hypothesis passes in the confirmation slice and at least 2,000 labelled candidate setups exist. Then it is meta-labelling with simple models, walk-forward in time with a gap. It gets its own spec update. |
| AR-D11 | More history | Deferred. When added (e.g., Dukascopy FX and gold history before 2025), the older years become a second confirmation set, while costs stay modelled on the broker's data. |
| AR-D12 | SMT pairs (update 2026-10c) | EURUSD with GBPUSD only. DXY and the index futures aren't in the data; USDJPY's link to EURUSD is inverse and looser; gold has no partner. |
| AR-D13 | The `crt` trade (update 2026-10c) | Entry at C3's open (the first M1 bar at or after C2's close), stop at C2's sweep extreme, target C1's other side, limit C3's close: the geometry of the 2026-10-09 C3 test, so the lab reproduces that result before a bias is added. |
| AR-D14 | Quarter 0 (update 2026-10c) | 17:00–00:00, the rollover hour included (the indicator's first quarter starts 18:00). The trading day opens at 17:00 and every hour belongs to one quarter. |
| AR-D15 | Not built now (update 2026-10c) | IC-CISD, the C3/C4 entry zones and the London and New York session levels. They refine entries; the earlier results place the edge in direction and timing, which these updates test. |
| AR-D16 | Random-time pool (update 2026-10d) | Exclude only the event's own date. The alternative, excluding other events' rows, would starve events that fire every day again. |
| AR-D17 | Timing baseline (update 2026-10d) | `sign_flip` is required for any timing claim before pre-registration. `shuffled_path` stays, as the weaker null that reproduces the 2026-10-08 statistic. |
| AR-D18 | Bias, measured (update 2026-10e) | Bias is right when the engine's draw on the bias side is reached within the D1 candle after t; the close doesn't decide. User 2026-10-10: "We do not need to predict the close." |
| AR-D19 | Bias controls (update 2026-10e) | Two controls. `stratified`: an engine draw at the same distance and hour is reached anyway. `complement`: the same event where the bias disagreed. A bias earns its place only by beating both. |
| AR-D20 | Normal volatility (update 2026-10e) | The median over the previous 20 trading dates, per instrument and slot: robust to news spikes, and about a month of memory. The "so far" norm is time-matched, so a ratio early in an H4 candle isn't biased low. |
| AR-D21 | Timing claims (update 2026-10e) | H004 and H007 are withdrawn before pre-registration. Time of day enters through the volatility features, the per-instrument profile, and `where` filters with `complement` twins. |
| AR-D22 | Fractal frames (update 2026-10e) | Still deferred. The engine anticipates D1 candles only (Requirement 21 of liquidity-engine, stage 1). H001 and H003 test the D1 frame; the same tests apply to an H4 frame once the engine builds one. |
