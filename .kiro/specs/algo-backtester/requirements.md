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
- **As-of view**: The multi-timeframe candle window passed to `LiquidityMappingEngine.analyze()` at time t: closed bars only for the entry timeframe and below, and for each higher timeframe its closed bars plus the in-progress bar aggregated from M1 bars that closed at or before t.
- **Entry timeframe**: The timeframe whose bar closes trigger evaluation (M1, M3, M5 or M15; see `setup_grader._ENTRY_ELIGIBLE_TIMEFRAMES`).
- **Simulation resolution**: M1. Every fill, exit and expiry is decided bar by bar on M1, whatever the entry timeframe.
- **Venue**: The data and execution source: an MT5 broker server, or Binance spot.
- **Venue session boundaries**: Where the venue's own HTF bars begin and end. For example, MT5 servers on the `ny_close` clock close D1 at 17:00 New York; Binance closes D1 at 00:00 UTC.
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
- **UI.** Outputs are files (CSV/JSON/Markdown). A chart or journal UI is the testing-frontend work, specified separately.

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
7. THE live runner SHALL build its candle window with the same as-of view builder, so the evaluation the backtest replays is the one live trading performs. This changes current live behaviour: the runner presently includes the forming entry-timeframe bar.

---

### Requirement 3: Historical Data and Timeframe Aggregation

**User Story:** As a strategy researcher, I want every timeframe built from one M1 source that matches the venue's own bars, so that the backtest sees the candles the live agent sees.

#### Acceptance Criteria

1. THE Backtester SHALL read M1 bars from the project candle store (TimescaleDB `candles` table, populated by `scripts/load_historical_data_mt5.py` and `scripts/load_historical_data_binance.py`).
2. ALL M1 timestamps SHALL be timezone-aware UTC. MT5 server times SHALL be converted with `MT5ServerClock` (`services/market_data/mt5_clock.py`).
3. THE Backtester SHALL aggregate higher timeframes from M1 using the venue's session boundaries.
4. A test SHALL compare aggregated HTF bars against the venue's natively downloaded HTF bars for the same period. Open, high, low and close SHALL agree to within one price increment. If they don't, the boundaries are wrong.
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

1. FOR MT5 venues, spread SHALL be taken from each bar's recorded spread (Requirement 3.5). IF a bar has none, a configured default per instrument SHALL apply, and the report SHALL count how many bars used the default.
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
3. A parity test SHALL replay a period the paper forward test has traded, with the same instruments, configuration and fill model, and SHALL produce the same trades: the same setup_ids, fills and exit reasons, with R within rounding.
4. A golden-run test SHALL run a small committed dataset end to end and compare the journal against a committed expected result. Any intended change to that result SHALL require updating the golden file in the same commit.
5. WHEN two runs have identical manifests, THEY SHALL produce byte-identical journals.

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
