# Requirements Document

**Spec**: AlgoBacktester

## Introduction

AlgoBacktester replays historical market data through the **same** decision code the live agent runs, and measures whether the resulting trades have positive expectancy **after realistic costs**. The live code in question is `LiquidityMappingEngine` → `SetupGrader` → setup-to-order logic → `RiskEngine`.

It exists to answer one question before any money is at risk, and again after every strategy change:

> Does this setup definition stay profitable, out of sample, after spread, commission and slippage?

AlgoBacktester sits between two existing pieces:
- **The live runner** (`scripts/run_live_agent.py`), whose decisions it must reproduce exactly.
- **The paper forward test** (`agent/brokers/paper.py`, `docker/paper-trader/`), whose results it must match when both cover the same period.

The backtester is only trustworthy if it is provably free of look-ahead, prices fills conservatively, and charges real costs. Those properties are therefore requirements, each with a test, not implementation details.

**Guiding constraint**: per the project's "validate before building" approach (`docs/DEVELOPMENT_HANDOFF.md`), this spec covers only what the backtester's correctness depends on. Anything else is a Non-Goal.

---

## Glossary

- **As-of time (t)**: The instant a decision is evaluated. Only data that was fully known at t may influence that decision.
- **As-of view**: The multi-timeframe candle window passed to `LiquidityMappingEngine.analyze()` at time t: closed bars only for the entry timeframe and below, and for each higher timeframe its closed bars plus the in-progress bar aggregated from M1 bars that closed at or before t. All bars follow the strategy calendar.
- **Entry timeframe**: The timeframe whose bar closes trigger evaluation (M1, M3, M5 or M15; see `setup_grader._ENTRY_ELIGIBLE_TIMEFRAMES`).
- **Simulation resolution**: M1. Every fill, exit and expiry is decided bar by bar on M1, whatever the entry timeframe.
- **Venue**: The data and execution source: an MT5 broker server, or Binance spot.
- **Strategy calendar**: The one fixed calendar every strategy candle follows, whatever the broker or venue. D1 runs 17:00 to 17:00 New York (DST-aware), the FX market's daily close. W1 periods start at Saturday 17:00 New York, the New York-close server's Sunday 00:00 and the label MT5 gives weekly bars. The FX week that opens Sunday 17:00 therefore falls inside one W1 period. Intraday higher timeframes (H1–H12) align to the 17:00 New York day start, so H4 bars start at 17:00, 21:00, 01:00, 05:00, 09:00 and 13:00 New York.
- **Native bars**: The venue's own HTF bars. They follow the venue's server clock, which may differ from the strategy calendar. Example: an MT5 server on UTC closes D1 at 00:00 UTC; Binance does too. Native bars are used directly only where they coincide with the strategy calendar.
- **Broker profile**: One broker account's configuration: venue (`mt5` or `binance`), the names of the environment variables holding its credentials, its server clock, its symbol map (instrument → broker symbol, e.g. `EURUSD` → `EURUSDm`), and its instrument spec file. Different profiles let the same strategy be priced at different brokers.
- **Order intent**: The order the live runner derives from a graded setup: direction, entry, stop, targets, R:R, confidence and setup_id.
- **Fill model**: The rules that turn an order intent plus M1 bars into fills, exits, expiries and costs.
- **Gross R / Net R**: A trade's result in multiples of its initial risk, before and after costs.
- **MAE / MFE**: Maximum Adverse / Favourable Excursion. The worst and best price reached while a trade was open, expressed in R.
- **Run**: One backtest execution over a fixed venue, instrument set, date range and configuration.
- **Run manifest**: The record that makes a run reproducible: code commit, dirty-tree flag, configuration, data range, data fingerprint and engine version.
- **Variant**: A run that differs from another only in named configuration values. Examples: stop mode Full vs Body, or minimum R:R 3 vs 5.
- **Hold-out period**: A date range reserved for final validation. It is never used to choose between variants.
- **Truncation test**: A test that removes all data after t and asserts the decision at t is unchanged.
- **Parity test**: A test that replays a period the paper forward test has already traded and asserts the backtest produces the same trades.

---

## Non-Goals (v1)

Recorded so they are not silently forgotten, and not bolted on mid-implementation.

- **Strategy changes.** Grader rules (opposite-side sweep, protected-swing stops, counter-trend cap at B, HTF-target "sniper" entries, minimum stop vs costs) belong in a `liquidity-engine` spec update. AlgoBacktester measures them; it does not define them.
- **Parameter optimisation / search.** v1 runs named variants that a person chooses. It does not grid-search or auto-tune, because automated search over many variants is the fastest route to overfitting.
- **AI modifiers in the loop.** Visual model, AlgoRAG and sentiment are disabled in backtests, and the run manifest records that. Replaying them historically is either leaky (AlgoRAG could retrieve trades from the future) or costly (paid VLM calls per bar). The deterministic baseline comes first; AI influence gets its own ablation spec later.
- **News blackout.** No historical economic-calendar source exists yet (`calendar_ingestion` is a placeholder). Runs report that the news filter was not applied.
- **Swap / financing, tick-level simulation, partial fills, order-book depth.** Reports include holding time per trade, so financing impact can be estimated afterwards.
- **A web application.** The run report (Requirement 11) is a static HTML file. A served testing frontend, with live data or multi-user access, is specified separately.

---

## Requirements

### Requirement 1: Same Decision Code as Live

**User Story:** As a strategy researcher, I want the backtester to make exactly the decisions the live agent would make, so that backtest results transfer to live trading instead of describing a different system.

#### Acceptance Criteria

1. THE Backtester SHALL call `LiquidityMappingEngine.analyze()` for analysis and grading. It SHALL NOT use any copy or reimplementation of engine or grader logic.
2. THE setup-to-order logic now inside `scripts/run_live_agent.py` SHALL move into one importable module used by both the live runner and the Backtester. That logic covers direction inference, target selection (`_pick_sd_targets`), the R:R calculation, the minimum-R:R gate and the grade-to-confidence mapping.
3. WHEN the live runner and the Backtester are given the same as-of view, instrument, as-of time and configuration, THEY SHALL produce identical order intents. A test SHALL assert this.
4. THE Backtester SHALL apply risk rules by calling `RiskEngine.validate()`, with exposure state (equity, open trades, daily and weekly drawdown) derived from the simulated account.
5. THE Backtester SHALL apply the live runner's position rules, at minimum one active trade per instrument. Any rule the live runner adds later SHALL be applied through the shared module, not duplicated.
6. EVERY strategy parameter the Backtester uses SHALL come from one configuration object, which the run manifest records. Examples: entry timeframe, minimum R:R, candle window lengths, pending-order expiry rule, stop mode.

---

### Requirement 2: No Look-Ahead

**User Story:** As a strategy researcher, I want proof that no decision used information from its future, so that I can trust a profitable result.

#### Acceptance Criteria

1. AT each as-of time t, THE Backtester SHALL build the as-of view only from M1 bars whose close time is at or before t.
2. FOR the entry timeframe and lower timeframes, THE as-of view SHALL contain closed bars only.
3. FOR each higher timeframe, THE as-of view SHALL contain that timeframe's closed bars plus one in-progress bar, aggregated from the M1 bars that closed within the current HTF period at or before t.
4. THE as-of view SHALL contain the same number of bars per timeframe as the live runner requests (`_CANDLE_COUNT`, moved into the shared configuration per Requirement 1.6).
5. THE `timestamp` passed to `analyze()` SHALL be t. Killzone and session logic therefore see the as-of time, never wall-clock time.
6. THE Backtester SHALL include a property-based truncation test (Hypothesis). For randomly chosen t, removing all data after t SHALL leave the order intent (or NO_TRADE) at t unchanged.
7. THE live runner SHALL build its candle window with the same as-of view builder, so the evaluation the backtest replays is the one live trading performs. This changes current live behaviour in two ways:
   - the runner presently includes the forming entry-timeframe bar;
   - it uses the venue's native HTF bars even where they don't follow the strategy calendar. It SHALL instead aggregate those timeframes from finer bars.

---

### Requirement 3: Historical Data and Timeframe Aggregation

**User Story:** As a strategy researcher, I want every timeframe built from one M1 source that matches the venue's own bars, so that the backtest sees the candles the live agent sees.

#### Acceptance Criteria

1. THE Backtester SHALL read M1 bars from the project candle store (TimescaleDB `candles` table, populated by `scripts/load_historical_data_mt5.py` and `scripts/load_historical_data_binance.py`).
2. ALL M1 timestamps SHALL be timezone-aware UTC. MT5 server times SHALL be converted with `MT5ServerClock` (`services/market_data/mt5_clock.py`).
3. THE Backtester SHALL aggregate higher timeframes from M1 on the strategy calendar, identically for every broker profile.
4. A test SHALL compare aggregated bars against native bars for the same period, to within one price increment:
   - H1 and lower against any venue's native bars;
   - H4, D1 and W1 against native bars from a server whose clock follows the strategy calendar (an MT5 `ny_close` server).

   A mismatch means the calendar is wrong.
5. FOR MT5 venues, THE history loader SHALL also store each bar's recorded spread, because the cost model (Requirement 5) needs it.
6. BEFORE a run starts, THE Backtester SHALL check data coverage per instrument. Weekends and venue holidays are allowed gaps. IF any other gap exceeds a configured limit, OR the history starts after the requested start date, THEN THE Backtester SHALL report it and SHALL refuse to run unless the user explicitly allows it.
7. THE run manifest SHALL record a fingerprint of the M1 data used (row count plus a hash per instrument), so a rerun on changed data is detectable.

---

### Requirement 4: Fill Model

**User Story:** As a strategy researcher, I want fills priced the way a broker would price them, so that results are not flattered by impossible executions.

#### Acceptance Criteria

1. THE Backtester and `PaperBrokerAdapter` SHALL use one shared fill model implementation, so backtest and forward-test results are comparable (Requirement 9.3).
2. THE fill model SHALL use an injectable clock. Simulated time SHALL never read wall-clock time.
3. A market entry SHALL fill at the open of the next M1 bar after t, adjusted for side. Longs fill at the ask (bid + spread); shorts fill at the bid.
4. A long limit entry SHALL fill only when an M1 bar's ask-side low trades strictly below the limit price. A short limit entry fills only when the bid-side high trades strictly above it. A touch alone is not a fill.
5. A long position's stop SHALL trigger on the bid; a short position's stop SHALL trigger on the ask. Targets SHALL use the same side convention.
6. IF a bar opens beyond the stop (a gap, including after weekends), THEN the stop SHALL fill at that bar's open, not at the stop price.
7. Stop exits SHALL apply a configured slippage on top of rule 4.6.
8. IF one M1 bar reaches both the stop and the target, THEN THE fill model SHALL assume the stop was hit first.
9. ON the bar where a limit entry fills, THE fill model SHALL allow a stop-out but SHALL NOT allow a target exit.
10. A pending order SHALL expire according to the configured expiry rule. The default SHALL follow the user's strategy rule: expire at the end of the killzone in which it was placed.
11. THE fill model SHALL NOT fill an order while the venue is closed (for example the FX weekend).
12. EACH closed trade SHALL record entry, stop, target, fill price, exit price, exit reason, placed / filled / closed times, gross R, net R, costs in R, MAE and MFE (in R) and holding time.

---

### Requirement 5: Costs

**User Story:** As a strategy researcher, I want every trade charged what my broker would charge, so that a tight-stop setup that only works before fees shows up as the loser it is.

#### Acceptance Criteria

1. THE spread applied to each bar SHALL be the larger of the bar's recorded spread (Requirement 3.5) and the instrument's typical spread from the broker profile's spec file. Some servers record 0 for almost every bar, and many record the bar's minimum, so the recorded value alone runs optimistic. The report SHALL count how many bars were priced at the typical spread.
2. Commission SHALL be configurable per venue and instrument: per lot per side for MT5, or a rate on notional per side for Binance (default 0.001).
3. Net R SHALL equal gross R minus spread, commission and slippage, each converted to R using the trade's initial risk.
4. THE report SHALL show, for every result, what share of gross R went to costs.
5. THE report SHALL flag trades where round-trip cost exceeds a configured fraction of initial risk (default 25%). The forward test has already found stops tighter than fees.

---

### Requirement 6: Position Sizing and Account Simulation

**User Story:** As a strategy researcher, I want sizing and risk limits simulated like the live account, so that drawdown and trade counts are realistic.

#### Acceptance Criteria

1. Position size SHALL be computed from the configured risk per trade, the fill price and the stop, using the instrument's contract size and tick value, then rounded to the instrument's volume step.
2. IF the minimum tradable volume would risk more than the configured tolerance above the risk budget (default 10%), THEN THE Backtester SHALL skip the trade with reason `MIN_VOLUME_OVER_RISK`. It SHALL NOT round the size up.
3. THE Backtester SHALL track simulated equity, open trades, and daily and weekly drawdown, with daily and weekly boundaries at 17:00 New York. That state SHALL feed `RiskEngine.validate()` (Requirement 1.4).
4. THE primary performance metric SHALL be R-based (fixed fractional risk, non-compounding). A compounding equity curve MAY be reported in addition.

---

### Requirement 7: Run Modes and Out-of-Sample Discipline

**User Story:** As a strategy researcher, I want variants compared fairly on unseen data, so that I adopt changes that generalise rather than ones that fit the past.

#### Acceptance Criteria

1. A run SHALL accept a venue, an instrument list, a date range and a configuration. Variants SHALL be named configuration overrides on top of a base configuration.
2. THE Backtester SHALL support a hold-out period, set once per study. A run SHALL refuse to include the hold-out period unless explicitly flagged as the final validation run, and the manifest SHALL record that flag.
3. THE Backtester SHALL support walk-forward evaluation over consecutive windows, reporting results per window and combined.
4. Engine analysis results MAY be cached, keyed by data fingerprint, engine version, instrument, as-of time and engine-relevant configuration. That way, variants that change only execution or risk settings do not re-run analysis. A cache hit SHALL produce results identical to a fresh run.
5. Instruments SHALL be processed independently (in parallel where possible), except for rules that span the whole account, which are applied in time order across instruments: concurrent-trade limit and drawdown.

---

### Requirement 8: Reporting

**User Story:** As a strategy researcher, I want results I can trust, drill into and compare, so that I can tell an edge from noise.

#### Acceptance Criteria

1. EVERY run SHALL write a run manifest, a trade journal (one row per order intent, including skipped intents and their reason) and a summary report.
2. THE summary SHALL report:
   - trade count
   - win rate
   - average gross and net R
   - expectancy in net R, with a bootstrap 95% confidence interval
   - profit factor
   - maximum drawdown (R and %)
   - longest losing streak
   - average holding time
3. THE summary SHALL break results down by instrument, grade, killzone, direction and calendar month.
4. IF a result is based on fewer than a configured minimum number of trades (default 30), THEN THE report SHALL mark it as insufficient evidence instead of presenting it as a finding.
5. A comparison command SHALL put two or more runs side by side, and SHALL refuse to compare runs whose data range or data fingerprint differ.
6. Each journal row SHALL contain enough levels and timestamps to locate and review the trade on a chart: entry, stop, target, fill, exit and the setup_id.

---

### Requirement 9: Backtester Self-Validation

**User Story:** As a strategy researcher, I want the backtester itself tested against known answers, so that a bug in the backtester can't masquerade as an edge.

#### Acceptance Criteria

1. THE fill model SHALL have unit tests on hand-built M1 bars covering every rule in Requirement 4, including the gap, same-bar and weekend cases.
2. THE truncation test (Requirement 2.6) SHALL run in the default test suite.
3. A parity test SHALL replay a period the paper forward test has traded, with the same instruments, configuration and fill model, and SHALL produce the same trades: the same setup_ids, fills and exit reasons, with R within rounding. The primary parity target is the forward test on the first real broker profile's market (9.6).
4. A golden-run test SHALL run a small committed dataset end to end and compare the journal against a committed expected result. Any intended change to that result SHALL require updating the golden file in the same commit.
5. WHEN two runs have identical manifests, THEY SHALL produce byte-identical journals.
6. A paper forward test SHALL run on the first real broker profile's market: Exness FX and gold, through the `exness-standard` profile, with paper fills on the shared fill model. That way, forward evidence and parity (9.3) come from the market the strategy would trade. The existing Binance crypto forward test continues as a 24/7 plumbing check; its results are not evidence for the Exness strategy.

---

### Requirement 10: Broker Profiles

**User Story:** As a strategy researcher, I want each broker described by a profile, so that the same strategy can be priced and traded at any broker without code changes, and costs always come from the broker I would actually use.

#### Acceptance Criteria

1. A broker profile SHALL be a file in `config/brokers/<profile>.toml` naming:
   - its venue (`mt5` or `binance`);
   - the environment variables that hold its credentials;
   - its server clock (`ny_close` or a fixed UTC offset);
   - its symbol map;
   - its instrument spec file.
2. NO committed file SHALL contain a credential. Profiles SHALL name environment variables, and the variables' values live in the git-ignored `.env`.
3. EVERY run SHALL name one broker profile. The run manifest SHALL record the profile and the source line of its instrument spec file (Requirement 5).
4. A variant MAY swap only the cost profile while keeping the same price data. This compares brokers' costs on identical trades, and runs differing only that way SHALL be comparable under Requirement 8.5.
5. THE spec export script and the MT5 history loader SHALL accept `--profile` and connect through it. Instruments SHALL be resolved through the profile's symbol map, and bar times converted with its server clock.
6. WHEN connecting to an MT5 profile, THE system SHALL verify the profile's server clock against live ticks (`MT5ServerClock.check`) and SHALL refuse to continue on a mismatch.

---

### Requirement 11: Run Report

**User Story:** As a strategy researcher, I want to see every trade and every skipped setup on a chart, with what the engine saw at the time, so that I can judge with my own eyes whether its setups are the ones I would take.

#### Acceptance Criteria

1. EVERY run SHALL write `report.html`: one self-contained file that opens in a browser offline. Chart libraries are embedded; no server and no network access are needed.
2. THE report header SHALL show the run manifest's essentials: broker profile and spec source, variant, data range, code commit and dirty flag, and the AI-modifier and news-filter flags.
3. A summary section SHALL show:
   - the equity curve and drawdown in R;
   - the distribution of net R;
   - the Requirement 8.3 breakdowns;
   - the cost share of gross R.

   Buckets with insufficient evidence SHALL be marked as such (Requirement 8.4).
4. A trade explorer SHALL list every journal row, both trades and skipped intents, filterable by outcome, decision or skip reason, instrument, grade and killzone.
5. FOR each row, THE report SHALL draw a candlestick chart of the entry timeframe around the setup. The window runs from a configured number of bars before the decision to a configured number after the trade closes (defaults 60 and 20). The chart SHALL mark:
   - the decision time, entry, stop and target;
   - fill and exit, where they occurred;
   - the engine's context at decision time: the selected entry PD array, the draw on liquidity, and the swept level, where present;
   - the killzone shading.
6. Charts SHALL be drawn only from the run's own recorded data: its journal, its signal records and its fingerprinted candles. A report never re-analyses with different code.
7. THE same report generator SHALL accept a paper forward test's trade file and candles, so forward-test trades are reviewed the same way as backtested ones.

---

## Update 2026-10f: The Engine on the Trader's Own Charts

Added 2026-10-13 at the user's request. The user judges the engine by eye, on TradingView: every timeframe, drawing tools, snapshots, and Bar Replay to read a day without seeing what follows. The trade autopsy (`.kiro/specs/market-narrative`, task 291) splits a run by failure mode, and the user wants to pull up those trades and replay them.

TradingView's embeddable Advanced Charts library is licensed only to companies for public web projects, so the engine's trades go to the user's own TradingView as a generated Pine Script overlay. The run report stays the place to check executions: exact M1 fills and the spread used.

Requirement 12 stays reserved for the deferred setup-review brief (`docs/ALGO_BACKTESTER_VALIDATION_HANDOFF.md`).

### Requirement 13: TradingView Overlay

**User Story:** As the trader, I want the engine's trades drawn on my own TradingView charts, so that I can switch timeframes, annotate, take snapshots and replay each day to judge whether its logic is right.

#### Acceptance Criteria

1. `python -m algo_backtester pine <run_dir> --instrument <symbol>` with `--month YYYY-MM` (or `--start` and `--end` trading dates) SHALL write a Pine Script v6 indicator into `<run_dir>/pine/`, built only from the run's own files.
2. FOR each filled trade of the instrument whose decision falls in the window, THE overlay SHALL draw:
   - the risk box (entry to stop) and reward box (entry to target), from the decision to the exit, TradingView position-tool style;
   - a label at the decision: direction, grade, and the pool the setup raided;
   - the raided pool, as a dotted line from where it formed to where it was raided;
   - the draw on liquidity, as a dashed line while the trade is open;
   - a marker at the fill;
   - a label at the exit: the result in R, the exit reason, and the trade's failure mode (D25).
3. THE overlay SHALL also draw each D1 candle's open (17:00 New York), from the run's own candles on the narrative's price basis.
4. THE overlay SHALL be safe in Bar Replay (D25):
   - each drawing is created only on the chart bar that contains its event's time;
   - an open trade's boxes grow bar by bar until its exit;
   - nothing on the chart reveals an outcome before the replay reaches it.
5. Inputs SHALL switch each layer on and off: raided pool, draw, D1 open, and the exit result. A failure-mode input SHALL show only the trades of one mode. Its label SHALL say that it is hindsight.
6. THE overlay SHALL say on the chart when the chart's symbol doesn't match the instrument.
7. A window with no trades, or more trades than the overlay's limit (D26), SHALL be refused, with the count and a shorter window suggested.

### Requirement 14: Failure Modes in the Run Report

**User Story:** As the trader, I want to filter the run report by failure mode, so that I can check how the trades of each mode were executed.

#### Acceptance Criteria

1. WHEN a run directory holds `autopsy.csv`, THE report SHALL show each trade's failure mode in its details and offer a failure-mode filter beside the existing ones.
2. Runs without `autopsy.csv` SHALL render as before.

---

## Open Decisions

To be settled by the user before `design.md`. Proposed defaults are shown; they apply if not changed.

| # | Decision | Proposed default |
|---|---|---|
| D1 | First venue to validate on | MT5 FX majors + XAUUSD, the strategy's home market. Requires MT5 "Max bars in chart" = Unlimited for years of M1. Binance supported second. |
| D2 | MT5 commission | Read per-deal commission from the account's deal history, and store it as config per instrument. |
| D3 | Stop-exit slippage | FX: 0.2 pip per stop exit. Crypto: 0.05%. Both on top of the gap rule. |
| D4 | Paper broker adopts the shared, stricter fill model | Yes. Forward-test numbers from then on are more conservative, and parity (9.3) is impossible otherwise. |
| D5 | Live runner switches to the shared as-of view (closed entry-TF bars) | Yes. Signals arrive at most one entry bar later, but live and backtest then evaluate the same thing (2.7). |
| D6 | Re-entry after a stop-out on the same setup | Not allowed. One attempt per setup_id; a new setup_id needs a new grade. |
| D7 | Hold-out period | The most recent 3 months of available data. |
| D8 | Minimum trades before a result counts | 30 per reported bucket. |

Decided 2026-10-05, after the first spec export (task 183) showed the connected MT5 account was `MetaQuotes-Demo`, whose pricing is not a live broker's (zero EURUSD/GBPUSD spread, no commission):

| # | Decision | Outcome |
|---|---|---|
| D3 (amended) | Stop-exit slippage | 25% of the instrument's typical spread, with a minimum of 2 points; crypto 0.05%. A fixed 2 points is 0.2 pip on 5-digit FX but only $0.002 on XAUUSD. |
| D9 | Candle calendar | One strategy calendar, New York close (17:00 New York), for every broker and venue (Requirements 2.7, 3.3). |
| D10 | Spread per bar | The larger of the bar's recorded spread and the typical spread (Requirement 5.1). |
| D11 | First real broker profile | `exness-standard`: an Exness Standard MT5 demo. Server clock UTC+0, hedging, costs costed through the spread. MetaQuotes-Demo data is test data only and never used for results. |
| D12 | Visual review | A self-contained HTML run report per run (Requirement 11), built before the first baseline. A served frontend stays deferred. |
| D13 | Forward test on the real market | An Exness FX and gold paper forward test on the Windows host (Requirement 9.6). The `exness-standard` account offers no crypto, so the Binance forward test is a plumbing check only. |

Update 2026-10f (proposed; D14–D24 are reserved by the setup-review brief):

| # | Decision | Proposed default |
|---|---|---|
| D25 | What the overlay shows, and when | Everything known at the decision appears on the decision's bar: levels, grade, the raided pool, the draw, and the D1 open from its own open. Hindsight (the result, the exit reason, the failure mode) appears only on the exit's bar. The failure-mode filter is hindsight by nature, so its input says so; for a blind replay, leave it at ALL and switch the exit result off. |
| D26 | Overlay size | At most 120 trades per script. A trade uses 3 labels, 2 boxes and 2 lines, and Pine shows at most 500 of each. One instrument-month of the BODY run averages about 10 trades. |

---

## Update 2026-10-14d: Watch the Engine Work

The trader can't judge the engine from tables: "something is still broken, but I can't judge it if it isn't happening visually." They want to start a backtesting session and watch the core engine interpret the chart, annotate it, execute and manage the trades. The first session shown already put two known flaws on screen: a grade-A short against the day profile's bullish draw, built on a raid two and a half days old.

### Requirement 15: The Engine Watch

1. `python -m algo_backtester watch [config]` SHALL serve a page on 127.0.0.1. There the trader picks an instrument, a first trading day in the research snapshot's exploration slice (AR-D3), up to 5 days, and the configuration or one of its variants.
   - **Amended 2026-10-28 (D47):** the first day may be in any open period, each read from its own snapshot:
     - the research snapshot's exploration and confirmation slices, up to the study's hold-out;
     - the 2018-2024 search's development years (from 2021-08-16, a month into their M1 export).

     The search's test years (2023-2024) stay closed.
   - **Amended 2026-10-28 (D48):** when the configuration has variants, the strategy menu SHALL offer only them, and SHALL preselect `fresh_near_gap_partial`.
2. THE session SHALL run the backtest over those days as `run` does: the same Phase A and Phase B, the broker profile's costs, M1 from the research snapshot (no Docker). At every entry-timeframe close it SHALL replay the engine and keep:
   - its unfilled PD arrays near price, as the engine draws them (the order block's 50% too);
   - the liquidity pools it could still raid;
   - the D1 candle profile (open, midnight open, trend, direction, draw);
   - the setup sequence (raid, reclaim, CISD, protected swing, entry array);
   - the grade with its eight conditions, and the journal's decision and reason.
3. THE page SHALL play the days forward (play, speeds, step, next order, next event), with any of the replay chart's timeframes. Engine layers can be switched on and off, and arrays filtered by timeframe. It SHALL draw:
   - each order from its placement until it fills or expires;
   - each trade's fill, stop, target and exit with its R;
   - a log of orders, fills and exits that jumps to each one.
4. NOTHING the page shows SHALL come from after the session's current time: bars, states and events are revealed as the clock passes them. The trader's own drawing tools work on top, kept in that browser per session. The page decides nothing.

### Requirement 16: The Engine's Trades and Choices on the Chart

Added 2026-10-15. After watching, the trader placed the engine's flaw "between the logical steps of my model execution and the right array, the high-probability point of interest". The sequence detector takes any untouched M1-M15 array with a raid, CISD and intact swing behind it, and ranks them by how recent the raid is. The grade then counts conditions; it is not an ordered chain.

1. THE watch SHALL draw each trade's life: placement, fill, the exit with its R, and the path between them (the best and worst point it reached, in R, at their times). Unless the run manages its trades (Requirement 28), the backtest never moves a stop or takes a partial: the page SHALL say so, since that is the management a trader would have done. Until the trade closes, only the best so far is shown.
2. AT each close where the engine looked for a setup, the page SHALL list every candidate array the sequence detector considered: its timeframe, type, zone, raid (pool and age), CISD, and the key it was ranked by. It SHALL mark the one the engine chose, and draw the candidates on the chart when asked.
3. THE trader MAY mark the candidate they would have chosen, or "none". The picks are kept in a file under `data/journal/` (local, git-ignored), one line per close, with the engine's choice beside it, so the two can be compared over many sessions.

## Update 2026-10-16: Noculus, the Trader Against the Engine

The trader asked (2026-10-16): "Within our engine chart (Noculus, just a fancy name I want to call it) I want to be able to mark out PD arrays back in time and place pseudo trades as though they were live, and then you will compare with the ones the engine is outputting. I think it brings us close to how I actually see the market."

The research so far says the edge, if any, is in the trader's selection (which array, which side, which day), not in arrays as such. The watch already shows the engine's choices (Requirements 15–16). Noculus records the trader's own, made the same way and at the same moments, so the two can be compared on the same bars. Two choices are the trader's (2026-10-16):
- the engine stays hidden until they reveal it (D27);
- arrays are marked by clicking their candles (D28).

### Requirement 17: Noculus Sessions

1. THE charts app SHALL be called Noculus. The engine chart is its Engine mode.
2. A watch session MAY be **blind**: until the trader reveals it, the server sends the bars and the clock only. It withholds the engine's arrays, pools, profile, setup, grade, candidates, orders and trades.
3. REVEAL SHALL show everything up to the clock, then play on as an ordinary session. It can't be undone.
4. THE trader's marks, trades and the comparison SHALL be kept per session in `data/journal/noculus/<instrument>/<session>.json` (local, git-ignored). Each item is stamped with the replay clock at which it was made.

### Requirement 18: Arrays Marked by Their Candles

1. THE trader SHALL mark an array with a tool (FVG, IFVG, order block, breaker) and a timeframe, then click candles of that timeframe:
   - **FVG:** its third candle (C3), with C1 the candle two before. It is bullish when C3's low is above C1's high: the gap from C1's high to C3's low, and the CE its midpoint (AR-D27). A bearish FVG is the mirror. Three candles without a gap are refused.
   - **IFVG:** the C3 of an FVG that a later candle of its timeframe closed beyond, by the clock. The zone is the FVG's, facing the other way.
   - **Order block:** the order-block candle. The zone is its high to low, the MT is its body's midpoint, and the direction is the trader's (proposed: opposite to the candle's colour).
   - **Breaker:** an order-block candle that a later candle closed beyond, by the clock. Facing the other way.
2. EACH mark SHALL keep:
   - its tool, timeframe, direction, low, high and mid (CE or MT);
   - the time it formed (the close that made it), the times of the candles clicked, and the clock;
   - an optional note.

   No candle closing after the clock can be used. A mark that would need one is refused, with the reason.
3. MARKS are drawn as boxes with their mid line. A deleted mark is kept as deleted, with its clock.

### Requirement 19: Pseudo Trades

1. AT the clock, the trader MAY place a trade: LONG or SHORT; market or limit; with a stop and a target; optionally tied to one of their marks.
   - A market order fills at the next M1 bar's open.
   - A limit order sits at a price until an expiry: the session day's close by default, or a chosen time.
2. TRADES SHALL play out as the clock advances, priced with AlgoResearch's race rules (its Requirement 7): bid and ask, each bar's spread floored at the typical spread, stop slippage, and the stop winning a bar that reaches both. Each shows its fill, its exit and its net R.
3. THE trader MAY close a trade at the clock, at the closing side's price.

### Requirement 20: The Comparison

1. ON reveal, a panel SHALL compare the session up to the clock:
   - **arrays:**
     - each of the trader's marks against the engine's arrays of the same kind (an IFVG counts as FVG family, a breaker as OB family), timeframe, direction and formation candle (within one candle of that timeframe);
     - counts of matched marks, marks only the trader made, and the engine's arrays the trader didn't mark (its unfilled arrays of the marked timeframes);
   - **trades:** the trader's and the engine's trades side by side, by day: direction, entry, stop, target, outcome and net R; whether they took the same side, and how far apart in time.
2. THE comparison SHALL be saved with the session.
3. `python -m algo_backtester noculus` SHALL summarise every saved session in `data/journal/noculus/REPORT.md` (local):
   - the match rates per array kind and timeframe;
   - the trader's and the engine's net R on the same days;
   - the days on which they disagreed.

### Decisions (2026-10-16)

| Id | Decision | Source |
|---|---|---|
| D27 | Blind until reveal | The trader's choice. Seeing the engine's arrays first (30 candidates at one close on 2026-01-27) would pull the marks toward them, and the comparison would measure the engine, not the trader. |
| D28 | Marking by candles; matching by formation candle | The trader's choice. Matching uses the candle that formed an array, not its edges, because the engine's FVG spans all three candles until the liquidity-engine fix (task 326) while the trader marks the gap. |
| D29 | Pseudo trades priced as races | They are the rules AlgoResearch already checks against the fill model (its Property 5). No management yet: a manual exit is the one action. Partials and break-even wait until an edge exists. |
| D30 | The name | Noculus: the trader's name for the chart, for both modes of the charts app. |

## Update 2026-10-19: The Trader's Fractal + POI Indicator on Noculus

The trader asked (2026-10-19): "I have something new I would like us to introduce to noculus that will aid the Engine through this process. Please find a copy of an Fractal POI indicator and take it to Noculus, we will then begin to adjust how our engine sees PD Arrays."

The indicator is the trader's own TradingView tool: Pine v6, 3,501 lines, in `backend/FractalPOI.md`. On Noculus it shows what the trader sees on TradingView, on the same bars and at the same moments as the engine's work. It then becomes the reference that the engine's PD arrays are adjusted against: how many arrays, which ones, and from which timeframe.

### Requirement 21: The Indicator, Ported

1. THE indicator SHALL be ported to Python as `algo_research.fractal_poi`. It is one definition: Noculus draws it, and the engine can later be measured against it.
2. IT SHALL do what the Pine script does, rule for rule:
   - **the Fractal modes** (Automatic, Intraday, Scalp, Swing, Quarterly, Custom and the fixed pairs) and the HTF each one picks for each chart timeframe;
   - **the HTF candles** drawn to the right of price, with their opens, highs, lows, labels and timer, and the optional HTF2 preview;
   - **the model:**
     - C1 swept by C2, which closes back inside;
     - CISD (the open of the run that made the sweep's extreme), early CISD and IC-CISD;
     - the C3 and C4 entry zones and EQ lines, and their invalidation (xC2, xC4);
     - the SD projections, formation liquidity, and SMT against two correlated symbols;
   - **the liquidity suite:** sessions, the true day open, PDH/PDL, PWH/PWL, PMH/PML, BSL/SSL on up to three HTFs, purged levels, relevant swings and the relevance filter;
   - **the HTF fair value gaps.**
3. CANDLES SHALL start where TradingView's FX charts start them: the trading day opens at 17:00 New York, as Noculus already counts.
4. THE settings SHALL be the indicator's inputs, with its defaults. Colours, line styles and sizes stay at its defaults, painted in the page's theme.

### Requirement 22: Read on Closed Candles, at the Clock

1. THE indicator SHALL read each chart candle once it has closed by the replay clock, which is its own default ("Calculate on Close"). It then draws what it would show on its last bar.
2. NOTHING sent to the page SHALL come from a candle that closes after the clock (Property 11).

### Requirement 23: On the Chart

1. NOCULUS'S Engine mode SHALL have a Fractal + POI layer, on by default, with:
   - a settings dialog of the indicator's inputs;
   - its dashboard in the side panel;
   - its alerts in the event log.
2. A BLIND session SHALL show it too: it is the trader's tool, not the engine's (D33).
3. CHANGING an input that only chooses what is drawn SHALL redraw at once. Changing one that changes what is read rereads the window.

### Decisions (2026-10-19)

| Id | Decision | Source |
|---|---|---|
| D31 | A Python port, served at the clock | It gives one definition, which the engine can be diffed against or built on. The page can't leak what the server never sends, and tests pin the port to Pine's rules. A JavaScript port would be a second definition. |
| D32 | Calculate on Close | The indicator's own default. On TradingView a realtime tick can show a setup intrabar and then take it back. The replay reads closed candles, so the layer moves when a chart candle closes. |
| D33 | Shown in blind sessions | It is what the trader uses on TradingView, so a blind read includes it, as a live read would. The engine's work stays withheld (D27). |
| D34 | SMT partners from the focus triads | The indicator resolves its partners with the fstarcapital AssetCorrelationUtils library, which isn't part of its source. Until the trader names that library's pairs: EURUSD with GBPUSD and DXY (inverse); GBPUSD with EURUSD and DXY (inverse); DXY with EURUSD and GBPUSD (both inverse); XAUUSD with DXY (inverse) and EURUSD; US100, US500 and US30 with each other; GER40 with UK100 and US500; UK100 with GER40 and US500. BTCUSDT has no partner in the snapshot. Manual mode takes any two. |
| D35 | The script's quirks are kept | For example, the micro cycle lists no session from 21:45 to midnight, so its 21:22 candle runs to midnight. The FVG list keeps only the newest three, and a gap that is closed through is deleted, not inverted. The port shows what TradingView shows. Where the trader means otherwise, the Pine script changes first. |

## Update 2026-10-20: The Indicator's Setups Against the Engine

The trader asked (2026-10-20): "try to use now the setups that the indicator is suggesting and lets see where the flaw is in our engine. I noticed that it does not interpret C1, C2 and C3 like it is supposed to. FVG the same thing, and then this will allow us to refine our executions."

### Requirement 24: The Diff

1. THE indicator's setups SHALL be a table (`fractal_poi.setups.setup_rows`): one row per setup that reached its history, with every level and the time each became known.
2. `python -m algo_research.fractal_poi.diff` SHALL compare them with a backtest run's journal over the exploration slice, per instrument and in total:
   - each engine order is with, against, or outside a live setup, and its raid is or isn't C1's extreme;
   - for each setup, what the engine did during it;
   - the setups traded three ways (market at C2 + CISD; a limit at the C3 zone's EQ edge; a limit at the C4 zone with the stop at C3), alone, with the day's real direction (hindsight) and with the previous day's.
   - the same, with and against seven HTF trend reads known in advance (`TRENDS`), and how often each read calls the day.
   - the same against the trader's trend definition (higher highs and higher lows on confirmed swings, per timeframe and tier, with the leg's discount and OTE).
3. AN order SHALL use only what was known when it is placed. C3's and C4's closes come from the HTF clock, never from the setup's later record.

The findings are in `docs/research/FRACTAL_POI_VS_ENGINE.md`. The "day's real direction" rows are an upper bound, not a strategy (D36).

| Id | Decision | Source |
|---|---|---|
| D36 | Exploration only; hindsight as the bound | The comparison reads the exploration slice. A rule that comes out of it is pre-registered and tested once on the confirmation slice. The hindsight rows measure what a right bias is worth, not a rule that can be traded. |

## Update 2026-10-21: Your Position Against the Engine's Trade

The trader asked (2026-10-21), after watching the engine short GBPUSD into a long they saw on 15 April 2025: "the targets are so huge and the stops so wide that by the time price has moved a short distance, our order barely has even a single [R]… I do not know if that is scale or perception… I want a feature in Noculus that will allow me to place the long short pnl tool alongside what the engine is perceiving as the high probability trade, you will do the comparison and discover the flaw there after."

Noculus already prices the trader's trades (Requirement 19), but only from a typed ticket and only in a blind session. The You mode has TradingView's position tools; the Engine mode does not. The engine's trade is drawn only once it is an order, and an order its limits blocked (a SKIP) is not drawn at all.

### Requirement 25: The Position Tool on the Engine Chart

1. THE Engine mode's toolbar SHALL carry the Long Position and Short Position tools (Alt+L, Alt+S): entry, stop and target, with the distances and the R:R on the drawing, as in the You mode.
2. A position drawn SHALL be placed as a pseudo trade at the replay clock, in any session, blind or open:
   - **at market** when its entry is within two typical spreads of the price on its side (the ask for a long, the bid for a short); it keeps the drawn stop and target;
   - **as a limit at its entry** when the entry is further away on the pullback side (below the ask for a long, above the bid for a short), until the session ends;
   - **refused, with the reason,** when the entry is further away on the other side: a stop entry is not simulated.
3. EACH placed position SHALL be kept in the session's Noculus journal with its drawing, and record whether the engine was in sight when it was placed (an open session, or a blind one already revealed). A blind session's journal is unchanged; an open session keeps its own, apart from the blind one over the same days.
4. THE drawing SHALL show its trade as the clock advances: waiting, open with its live R, or its outcome and net R.
5. MARKS stay blind-only (Requirement 18, D27).

### Requirement 26: The Engine's Trade Beside Yours

1. THE engine's idea at the clock SHALL be drawn as a position in the same look: every order it placed, and every trade it wanted but its limits refused (a SKIP), labelled with the reason. A run of SKIPs at consecutive closes with the same side, entry and stop is one idea.
   - A SKIP idea is priced by the race rules (Requirement 19.2) as the engine would have placed it at the first close that wanted it: a limit at its entry when the entry is better than the price (the sim broker's rule), lasting while the engine still wants it; otherwise at market. It keeps its own stop and target. An order's outcome is the backtest's.
2. EACH of the trader's positions SHALL be paired with the engine's idea live at its placement (placed by then and not yet closed, expired or given up); failing that, with the engine's next idea of the same trading day; failing that, it stands alone.
3. A pair SHALL be compared on the market's own scale at the placement clock:
   - **the side**: the same or the other;
   - **the entry, the stop and the target**: in price, and in the average true range of the last 14 closed M15, H1 and D1 candles (the D1 one is the ADR);
   - **the R:R** of each;
   - **the time** between them;
   - **the outcome** of each: outcome, net R, and the best R reached;
   - **a label** for where they part (D38): *the other side* (perception); *scale*, when on the same side one stop or target is at least twice the other's; *location*, when on the same side and scale the entries are more than the trader's stop apart; *agree* otherwise; *the engine had none*.
4. WHILE a blind session is unrevealed, the engine's side of each pair SHALL stay hidden.
5. `python -m algo_backtester noculus` SHALL add the positions to `REPORT.md`: each pair, the labels counted, how often the sides agreed, both sides' median stop and target in M15 ATR and median R:R, and both net Rs.

| Id | Decision | Source |
|---|---|---|
| D37 | A drawn position is a market or a limit by where its entry sits; no stop entries | Within two typical spreads the trader means "now". The race rules model market and limit fills only (D29); a buy-stop would need a new fill rule, so it is refused with the reason. |
| D38 | The labels are a first sort, not a verdict | "Scale or perception" is the trader's question. The 2× and one-stop thresholds are round numbers chosen before any position exists. Each pair keeps its raw measures, so the sort can be redone. |
| D39 | Open sessions keep a journal too | The trader wants their position beside the engine's. Positions placed with the engine in sight carry `engine_seen`, so they are never counted as blind reads (D27). |

## Update 2026-10-22: Live on Noculus

The trader ran the fixed engine on the live market with paper orders (`run_live_agent.py --config config/backtests/focus.toml --variant fresh_near_gap`), then said: "i can't see the live session on noculus". A Noculus session replays the research snapshot's exploration slice only, and the live runner writes its decisions to a log. The trader judges visually (Requirement 15), so the live engine belongs on the same chart.

### Requirement 27: A Live Session

1. THE Engine mode SHALL start a session **live**, from the broker's MT5 terminal instead of the snapshot:
   - the terminal is the configuration's profile: its symbols, its server clock, and the credentials in `.env`;
   - the session covers today's trading date and the `days - 1` trading dates before it (a weekend's trading date is Friday's);
   - it runs up to the terminal's last closed minute.
2. WHILE the page watches a live session, the session SHALL move on with the market:
   - the new closed minutes are read;
   - the engine reads each new entry-timeframe close, and only the new ones (earlier closes read the same closed candles);
   - the backtest's account runs again.

   The page's clock follows the end unless the trader stepped back. A forming candle is never served.
3. A live session SHALL be the backtest's own, as a replayed session is:
   - the configuration's strategy, Phase A and Phase B, and the profile's costs;
   - Model A and the Fractal + POI indicator;
   - blind or open;
   - the trader's positions, kept in a journal of its own (`live-<first day>-<days>d-<variant>[-open].json`).
4. IN a live session, the watchlist SHALL read the terminal's prices, never the snapshot's.
5. A server whose profile is not an MT5 broker's SHALL refuse a live start with the reason.
6. WHILE the trader's clock is at the end of a live session, the chart SHALL show the market now, every second: the forming candle of the chart's timeframe, and the last bid and ask.
   - The engine and the account still read closed candles only, so the price moves through what the engine drew at its last close.
   - Within seconds of a minute's close, the session reads that minute. Within seconds of an entry-timeframe close, the engine's reading of it is on the chart.
   - The replay controls give way to **Live**, and to **Back to live** when the trader has stepped back.
7. A market priced in neither currency of the account (a cross, such as GER40 or UK100 on a USD account) SHALL be watched, replayed or live, in an account of its own quote currency.

The trader's first look at a live session (2026-10-22): "its not working. It is as though it is on backtesting mode, Though I should be seeing live markets while on noculus while the engine craws price in real time". The first version served closed minutes only, stepped once a minute up to 40 s late, and kept the replay's Play and speed. Their GER40 session was refused as a cross. Criteria 6 and 7 answer both.

| Id | Decision | Source |
|---|---|---|
| D40 | A live session waives the study hold-out guard | The guard keeps a fixed past unread until the final run (Requirement 7.2). A live session is forward data, the days being traded now, as the paper runner's are; refusing it would make the live chart impossible. The trader's live days do fall after the study's hold-out start (2026-07-07), so a final validation run over them would not be blind to the trader. |
| D41 | The page drives the refresh | A live session reads the terminal again only while a page asks after it, so a kept session left alone costs nothing. The page asks every second for the market now; the session asks the terminal for a newly closed minute at most every 5 s, and runs the rest only when one has closed. That rest takes about 4 s on a quiet machine (15 s seen while the paper runner and a pilot ran): the backtester's aggregation, the engine at the new closes, and Phase B. |
| D42 | A cross is watched in its own currency | The backtester can't convert a cross's results to the account's currency yet, so real runs still refuse one. The watch shows R, and R is the same in any currency: risk and result are both in the quote currency. GER40 and UK100 carry no commission on the Exness profile. |

## Update 2026-10-27: Partials and Break-Even

### Requirement 28: A Partial, Then Break-Even

Added 2026-10-27. The trader noticed that "when most trades have run for like 3-4 rr, they tend to come back and take out stops" and asked for management: "Edge is not just in the technicals but also how we manage the trade in the process." An exact replay of `fresh_near_gap`'s 289 filled trades through the fill model (it reproduced every journal result) compared about 30 exit rules:
- fixed 3R, 4R and 5R targets lost against the engine's own targets in both periods;
- break-even alone at +1R or +1.5R cost the big winners when the engine was right;
- a third off at 3R, with the rest moved to break-even at that moment, was the best rule in January–June 2025: +29.0R against +30.4R, return over drawdown 1.38 against 1.14, wins 27% against 15%, the longest run of full losses 11 against 26. From July 2025 it lost at the same rate per unit of drawdown as every other rule (−0.99 against −0.96).

The trader chose it: "We move to BE as we take partials". It is an exit rule, not an edge, and is judged on forward data from here on.

1. A run's configuration SHALL take a `[management]` table:
   - `partial_r`, a multiple of the trade's risk; 0 (the default) is off;
   - `partial_fraction`, the share of the position closed there, strictly between 0 and 1 (default ⅓).

   A variant sets them with dotted keys, as it sets the strategy's.
2. WHEN a filled trade's closing-side price reaches its fill plus `partial_r` times the fill-to-stop distance, THE fill model SHALL close `partial_fraction` of it at that price (a limit exit, without slippage) and move the rest's stop to the fill.
   - The new stop holds from the next bar: the bar that took the partial was checked against the old stop.
   - A bar that reaches both the stop and the partial is the stop's, as with a target.
   - No partial on a limit's fill bar, as no target.
   - The target may close the rest on the partial's own bar.
   - A partial at or beyond the target is not taken: the trade runs as an unmanaged one.
3. THE broker SHALL size the partial in lots, rounded down to the volume step. WHEN the partial or the rest would be under the minimum volume, the trade SHALL run without a partial and without the stop move.
4. A trade with a partial SHALL be one journal row and one result. R is the lots-weighted sum of the two exits on the risk the order was sized on. The costs split the same way:
   - spread: a LONG's is paid once on entry; a SHORT's is paid on each part's exit;
   - slippage: on the rest's stop exit only;
   - commission: on every lot, both sides;
   - swap: on each part's own nights.

   The journal SHALL carry `partial_at`, `partial_exit` and `partial_fraction` (the actual share, after rounding).
5. Engine mode SHALL draw the partial: where and when it was taken, with its share. A rest stopped at the fill reads "BE". Requirement 16.1's note becomes conditional: when the run manages no trade, the page says the backtest never moves a stop or takes a partial.
6. WHEN the live runner trades a configuration on paper (`scripts/run_live_agent.py --config … --broker paper`), THE paper broker SHALL manage its trades by that configuration's `[management]`, through the same fill model (added 2026-10-27: "run a paper agent session across all assets … see how our implementation works").
   - The trade keeps its planned stop, which R is measured on, and records the partial (share, price, bid, time).
   - The partial's level is recomputed from the fill after a restart. A trade whose partial was taken keeps its stop at the fill.
   - Paper has no lots: the share is exact and every trade splits (D46).
7. WHEN the live runner trades a configuration on the MT5 feed, THE paper broker SHALL take its spreads and stop slippage from that configuration's broker profile. Until now the MT5 paper test ran without costs. Swap is still not charged on paper.

| Id | Decision | Source |
|---|---|---|
| D43 | Management lives in the run configuration, not the StrategyConfig | `agent/strategy_config.py` is one of `ENGINE_SOURCES`: any edit to it changes the engine fingerprint and invalidates every Phase A cache entry (about 540 MB, hours to rebuild). Exits are read by the broker only, after Phase A, so they belong beside the account. Runs that differ only in management share Phase A's entries. |
| D44 | A position too small to split runs unmanaged | Sizing never rounds up past the risk budget (Requirement 6.2). Rounding a partial up would close more than the share, and rounding the rest up is impossible. At $10,000 and 1% risk, no `fresh_near_gap` trade of 2025-26 was under two minimum lots. A small live account would be, and its trades would run unmanaged. |
| D45 | Break-even is the fill, from the next bar | The stop moves to the price the position was opened at, as a trader moves it in MT5. M1 bars can't order the partial and a dip on the same minute, so the move waits for the next bar: that is the replay's rule, and it never improves a result. Once its partial is taken, a trade can lose only the rest's spread, slippage and commission. |
| D46 | Paper always splits | The paper broker sizes in risk units, not lots, and scores trades in R. D44 is a lot-rounding rule: on paper it would only skip trades the backtest manages at $10,000. A live MT5 account at the runner's $200 seed equity would be under two minimum lots on most trades, so live management needs its own rule. |
| D47 | Noculus opens the studied years, not the unread ones | The trader found sessions could only start in January-June 2025 and chose, on 2026-10-28, to open July 2025 - July 2026 and July 2021 - December 2022. The confirmation slice's pre-registered tests have run, and the development years are the search's own. What the trader reads there can't be confirmed there any more. 2023-2024 judges the search's leads once, so it stays closed, and the hold-out is reached only by live sessions (D40). |
| D48 | Noculus drops the pre-fix base | The trader (2026-10-28): "since the base strategy is wrong, why not do away with it". A configuration's own [strategy] is the engine's defaults: the FVG as the three candles, a wick filling it, the forming HTF candle read as closed (the 2026-10-17 audit). It was the menu's default, so the trader kept watching it. Only the menu changes. The defaults themselves sit in `agent/strategy_config.py`, whose edit rebuilds the whole Phase A cache and the golden journal, so that change is a separate decision. |
