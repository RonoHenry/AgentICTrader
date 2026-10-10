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
