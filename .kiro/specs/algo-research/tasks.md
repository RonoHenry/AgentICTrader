# Implementation Plan

**spec**: AlgoResearch

## Overview

Build order for `requirements.md` and `design.md` (decisions AR-D1 to AR-D11 at their proposed defaults unless the user changes them).
- **Numbering:** tasks continue the platform sequence from **244**.
- **TDD:** every code task follows the **RED → GREEN → REFACTOR** cycle in `.kiro/steering/tdd-and-testing.md`.
- **Tests:** they live in `backend/tests/test_research_*.py`, fixtures under `backend/tests/fixtures/research/`.
- **Properties:** "Property N" refers to this spec's `design.md` → Correctness Properties, tested with `hypothesis`. Other specs' properties are named with their spec (e.g., liquidity-engine Property 35).

The plan runs in five groups:
- **A. Foundations (244–246):** configuration and slices, the snapshot, frames and the calendar.
- **B. Features, labels and races (247–250).**
- **C. Questions, baselines and statistics (251–256):** hypotheses, events, the bootstrap, the baselines, the runner and ledger, self-validation, then a checkpoint.
- **D. First results (257–259):** the real snapshot, then H001–H004 pre-registered and run. The deliverable is task 259, the first verdicts.
- **E. Stage 2 (260–262):** the engine at every close, H005–H006, and the next decision.

Tasks marked **(user action)** need Docker, the MT5 terminal or a decision from you. Tasks marked **(user review)** end with your review before the next one starts.

---

## Tasks

### A. Foundations

- [x] 244. Package, `ResearchConfig` and slices
  - **244a. RED** (`backend/tests/test_research_config.py`)
    - `test_loads_research_toml_defaults` — profile, study, instruments, slices, bootstrap and baseline settings.
    - `test_slices_must_be_contiguous_and_end_at_holdout` — a gap, an overlap, or a confirm end other than the study's `holdout_start` raises, naming the slice.
    - `test_period_reaching_holdout_refused` (Property 10).
    - `test_slice_of_boundaries` — a time maps to `explore`, `confirm` or None; starts inclusive, ends exclusive.
  - **244b. GREEN**
    - `algo_research/__init__.py`, `config.py` and `config/research/research.toml`.
    - `.gitignore` gets `data/research/` (C1); `requirements.txt` lists `pyarrow` (C2).
  - **244c. REFACTOR**
  - **Validates: Requirements 13.1, 13.2**

- [x] 245. Snapshot: export, `SnapshotSource`, manifest, fingerprint
  - **245a. RED** (`backend/tests/test_research_snapshot.py`, with `CsvSource` over the backtester's fixtures)
    - `test_recording_source_keeps_every_row_load_instrument_reads`
    - `test_snapshot_round_trip_same_fingerprint` — `load_instrument()` on a `SnapshotSource` gives the `InstrumentData.fingerprint` it gives on the original source (Req 1.4).
    - `test_export_refuses_end_after_holdout` — refused before any read; a spy source records no calls.
    - `test_no_row_at_or_after_holdout` (Property 10).
    - `test_manifest_records_inputs` — every field of Req 1.3.
    - `test_changed_snapshot_refused` — one edited price fails the fingerprint check, naming the instrument.
  - **245b. GREEN** — `snapshot.py`; the `snapshot` command (`--profile`, `--name`).
  - **245c. REFACTOR**
  - **Validates: Requirements 1.1–1.5**

- [x] 246. Frames and the trading calendar
  - **246a. RED** (`backend/tests/test_research_frame.py`)
    - `test_trading_date_17_00_boundary` — Sunday 17:00 is Monday; Friday 16:59 is Friday.
    - `test_h4_index_on_both_sides_of_dst`
    - `test_spread_priced_as_fill_bars` — the larger of the recorded spread and the typical spread (algo-backtester D10).
    - `test_grid_is_m15_closes_with_m1` — no rows over weekends or data gaps.
    - Property 3 (Hypothesis): `trading_date`, `h4_index` and `weekday` equal `StrategyCalendar`'s at random instants, weighted toward DST changes and 17:00.
  - **246b. GREEN** — `frame.py`.
  - **246c. REFACTOR**
  - **Validates: Requirements 2.1–2.3**

### B. Features, labels and races

- [x] 247. Market features
  - **247a. RED** (`backend/tests/test_research_features.py`, hand-made frames)
    - `test_opens_and_sides` — `d1_open`, `midnight_open` (null before 00:00), `h4_open` and the sign columns.
    - `test_day_extremes_so_far_earliest_on_tie`
    - `test_asia_range_known_at_midnight` and `test_asia_raided_at_first_m1_beyond`
    - `test_previous_levels_and_taken_at` — PDH/PDL within the candle, PWH/PWL within the week.
    - `test_w1_trend_closure_rule` — UP, DOWN and NEUTRAL (LE-D15).
    - `test_atr_matches_calculate_atr`
    - `test_null_without_history` (Req 2.4).
    - `test_cache_key_changes_with_snapshot_and_code`
    - Property 1 (Hypothesis, 25 examples): the vectorised row at t equals the row rebuilt from data truncated at t.
    - Property 4, on the engine fixtures:
      - `asia_high`/`asia_low` equal `asian_pools()`;
      - `killzone` and `in_window` equal the engine's.
  - **247b. GREEN** — `features/market.py`, `features/cache.py`; the `build` command.
  - **247c. REFACTOR** — time the build on the fixtures.
  - **Validates: Requirements 2.4, 3.1–3.5**

- [x] 248. Daily anticipation from the engine
  - **248a. RED** (`backend/tests/test_research_anticipation.py`, golden-week fixture)
    - `test_one_engine_call_per_instrument_day_at_17_15` — a call-count spy.
    - `test_anticipation_equals_profile_at_any_t_in_the_candle` — liquidity-engine Property 35, checked on the fixture's days.
    - `test_engine_error_leaves_the_day_null_and_counted`
    - `test_w1_trend_equals_ant_trend` (Property 4).
    - `test_cache_key_includes_engine_fingerprint_and_config`
  - **248b. GREEN** — `features/anticipation.py`; `build` includes it.
  - **248c. REFACTOR**
  - **Validates: Requirements 4.1–4.4**

- [x] 249. Labels
  - **249a. RED** (`backend/tests/test_research_labels.py`)
    - `test_rem_move_to_last_m1_before_17_00` — including a Friday and both DST changes.
    - `test_forward_horizons`
    - `test_level_hit_after_strictly_after_t_and_before_the_close`
    - `test_candle_labels` — `day_dir`, the final extremes and their H4 indices.
    - `test_features_events_filters_do_not_import_labels` — an AST scan.
    - Property 2 (Hypothesis): perturbing the bars that closed by t leaves the forward labels unchanged.
  - **249b. GREEN** — `labels.py`; `build` includes it.
  - **249c. REFACTOR**
  - **Validates: Requirements 6.1–6.4**

- [x] 250. Race engine
  - **250a. RED** (`backend/tests/test_research_races.py`)
    - Known cases:
      - LONG and SHORT to the target and to the stop;
      - a gap through the stop, and stop slippage;
      - a bar reaching both (stop wins, `ambiguous`);
      - REJECTED when the entry open is beyond a level;
      - TIMEOUT at the last close on the closing side;
      - commission in R.
    - Property 5 (Hypothesis): outcome, exit time and exit price equal stepping `FillModel` with the same MARKET `SimOrder`.
    - Property 6: on seeded driftless paths, the win rate lies within the `coin_flip` interval.
  - **250b. GREEN** — `races.py`.
  - **250c. REFACTOR** — measure races per second, and record it in design.md → Measured Performance. Not a timing test: those flake under load.
  - **Validates: Requirements 7.1–7.4**

### C. Questions, baselines and statistics

- [x] 251. Hypothesis schema, events and filters
  - **251a. RED** (`backend/tests/test_research_hypothesis.py`, `backend/tests/test_research_events.py`)
    - **Schema:**
      - the design's H002 example loads;
      - each missing or invalid field is named;
      - a race without `[trade]` is refused;
      - a candle label with an event other than `daily` is refused (Req 6.2);
      - a parameter list expands to one test per value;
      - the hash ignores line-ending differences.
    - **Filters:**
      - comparisons, `in`, `and`, `or` and `not` are accepted;
      - calls, attributes, subscripts and lambdas are refused;
      - label columns in `where` are refused, and so are unknown columns.
    - **Events, on hand-made frames:**
      - `anchor` skips and counts rows without a direction;
      - `asia_raid_reclaim`:
        - the window edges and `reclaim_within`;
        - no event once the other side is taken;
        - at most one per side per day;
        - `raid_extreme` and `asia_opposite`;
      - `level_open`: the `trend` mapping, untaken levels only, and the `level_hit_after` alias;
      - `daily`.
    - Property 1, extended: an event at t is unchanged when the data after t is removed.
  - **251b. GREEN** — `hypothesis.py`, `events.py`, `filters.py`.
  - **251c. REFACTOR**
  - **Validates: Requirements 6.2, 8.1, 8.5, 9.1–9.4**

- [x] 252. Statistics: day bootstrap and verdict
  - **252a. RED** (`backend/tests/test_research_stats.py`)
    - A constant series gives a zero-width interval at the constant.
    - With independent dates, the interval is close to the analytic binomial one.
    - A paired difference uses the same drawn dates for both series.
    - `best_naive` is re-chosen within each resample, so its bound is never looser than with a fixed choice.
    - The verdict: INSUFFICIENT below `min_events` or `min_days`; PASS or FAIL by the rules; `min_effect` respected.
    - The breakdowns per instrument, quarter and weekday, and the same-sign share.
    - A given seed gives identical results.
    - Property 7 (Hypothesis): duplicating rows within their dates leaves the interval identical.
  - **252b. GREEN** — `stats.py`.
  - **252c. REFACTOR**
  - **Validates: Requirements 11.1–11.5**

- [x] 253. Baselines
  - **253a. RED** (`backend/tests/test_research_baselines.py`)
    - `coin_flip` on known geometry, LONG and SHORT.
    - `random_time`:
      - draws from the same instrument and slot, on other dates of the same slice, never on event dates;
      - K draws, with ATR rescaling;
      - reproducible by seed;
      - when fewer than K candidates exist, it uses those and reports the count.
    - The naive rules on hand-made rows.
    - `stratified` buckets by distance decile and hour.
    - `shuffled_path` keeps each date's open and close. On a random walk, the real and shuffled statistics agree within their intervals.
  - **253b. GREEN** — `baselines.py`.
  - **253c. REFACTOR**
  - **Validates: Requirements 10.1–10.6, 13.3**

- [x] 254. Runner, ledger, reports and CLI
  - **254a. RED** (`backend/tests/test_research_runner.py`, with a temporary git repository in `tmp_path`)
    - Property 11:
      - `run` refuses an uncommitted hypothesis file, a modified one, uncommitted changes in `algo_research/`, and an id already in the ledger under another hash;
      - `explore` never writes the ledger.
    - `run` appends exactly one row, and earlier rows stay byte-identical.
    - A rerun with the same hash recomputes and matches (Property 9). A mismatch is an error naming the fields.
    - `run` reads only the confirmation slice; `explore` reads only the exploration slice (Req 13.1).
    - The report has every section of the design's outline, including the first 20 event times per instrument.
    - `LEDGER.md` shows counts per family and the passes expected by chance.
  - **254b. GREEN** — `cli.py` (`explore`, `run`, `ledger`), `ledger.py`, `report.py`.
  - **254c. REFACTOR**
  - **Validates: Requirements 8.2–8.4, 12.1–12.4, 13.1**

- [x] 255. Self-validation
  - **255a. RED** (`backend/tests/test_research_selfcheck.py`)
    - **A seeded world generator:**
      - the FX calendar: Sunday 17:00 to Friday 17:00 New York;
      - session-shaped volatility;
      - a constant spread.
    - Property 8 (`slow`):
      - on 200 null worlds, a race hypothesis (`asia_raid_reclaim`) and a direction hypothesis PASS in at most 5%;
      - with a planted post-event drift, they PASS in at least 90%, and the interval covers the planted effect in at least 90%.
    - **The golden research run:** the report and ledger row are byte-identical on every run; regenerate with `UPDATE_GOLDEN=1`.
  - **255b. GREEN** — no new production code is expected. Any failure here is a tooling bug, fixed under its own RED test.
  - **255c. REFACTOR**
  - **Validates: Requirements 14.1–14.3**

- [x] 256. Checkpoint
  - **Suite:** the full suite is green apart from the task-39 RED tests, with the `slow` research tests run once.
  - **Speed:** build and run times on the fixtures, recorded in design.md → Measured Performance.
  - **Review:** anything to change before real data is used.

### D. First results

- [x] 257. Real snapshot and build **(user action: Docker running)**
  - `python -m algo_research snapshot` for `exness-standard`, the four instruments, 2025-01-01 → 2026-07-07.
  - `python -m algo_research build`, then:
    - record the snapshot size and build times (Req 14.4);
    - list the coverage problems;
    - check Property 4 on the real build: `w1_trend` equals `ant_trend` on every date.
  - Smoke test: `explore` a draft of H004 on the exploration slice (drafts only).

- [ ] 258. Pre-register the first batch **(user review)**
  - Write H001–H004 from design.md → First Hypotheses: statements, events, measures, baselines and pass rules.
  - `explore` runs on the exploration slice may debug the events (counts, skipped rows) before the files are final. Nothing is run on the confirmation slice.
  - The user confirms each file. The commit is the pre-registration.

- [ ] 259. Run the first batch **(user review)**
  - Run H004 first: a tooling check that should reproduce the direction of the 2026-10-08 timing statistic. Then H001, H002 and H003.
  - Write `docs/research/FIRST_BATCH.md`:
    - the verdicts and effects with their intervals;
    - the stability breakdowns;
    - what each result means for the strategy;
    - the graduation proposals, if any, for a `liquidity-engine` spec update.
  - The user reviews the reports and checks event times by eye on the chart.

### E. Stage 2

- [ ] 260. Engine features at every close
  - **260a. RED** (`backend/tests/test_research_engine_features.py`, golden week)
    - Each row's decision, reason and intent fields equal Phase A's `signal_at()` record at the same t.
    - The setup-sequence fields are flattened as the design lists them.
    - The cache key includes the engine fingerprint.
    - The backtester's cache directory is untouched.
    - `engine_intent` fires once per intent.
    - The +1R re-entry (H006) fires when +1R is first reached, using only bars up to then.
  - **260b. GREEN**
    - `features/engine.py` and `build --engine`;
    - the `engine_intent` event and its +1R re-entry.
  - **260c. REFACTOR** — the real stage-2 build (about 2 h, from the snapshot, no Docker), timed and recorded.
  - **Validates: Requirements 5.1–5.3**

- [ ] 261. H005 and H006 **(user review)**
  - Pre-register them (the user confirms the rules), run them, and add the results to `docs/research/FIRST_BATCH.md`.

- [ ] 262. Decide the next step with the user
  - **If anything passed:** write graduation proposals as a `liquidity-engine` spec update: a `StrategyConfig` variant, and its backtest pass mark written before the run.
  - **If nothing passed:** pick the next hypotheses from the breakdowns.
    - Consider more history (AR-D11) for statistical power.
    - Check the machine-learning gate (AR-D10).

### F. Update 2026-10c: ideas from the Fractal + POI indicator

These come after 257 and don't wait for 258–262: they explore only, and pre-register nothing without the user.

- [x] 263. Candle ranges, the `crt` event and filters over event columns
  - **263a. RED** (`test_research_features.py`, `test_research_events.py`, `test_research_hypothesis.py`, `test_research_runner.py`)
    - `crt_<tf>_*` on hand-made paths:
      - a low sweep closed back inside is +1, a high sweep −1;
      - both sides swept, or no close back inside, is 0;
      - C1 is the previous bar with data.
    - Property 1 covers the new columns.
    - `crt` fires at C2's close with `c2_extreme`, `c1_opposite` and `limit` (C3's close). It doesn't fire for a C2 closing Friday at 17:00. Property 1 holds for events with `crt` added.
    - `where` reads `direction`, levels and attributes; an unknown column is still refused.
    - `time_limit = "event"` is refused for an event without limits. A race uses the event's limit, and random-time draws keep its duration.
  - **263b. GREEN**: `features/market.py`, `events.py`, `hypothesis.py`, `runner.py`, `baselines.py`.
  - **263c. REFACTOR**: rebuild the real tables and record the event counts per timeframe.
  - **Validates: Requirements 9.5, 15**

- [x] 264. SMT partner features
  - **264a. RED** (`test_research_partner.py`, `test_research_config.py`, `test_research_events.py`)
    - `[smt] pairs` is loaded. An unknown instrument, or one in two pairs, is refused.
    - Partner columns equal the partner's own facts at the same t. They are null without a partner row, with an unknown Asian range, or with a different C2.
    - `smt` on `asia_raid_reclaim` and `crt`, both sides; null without a partner.
    - `build_dataset` adds the columns to every instrument's table.
  - **264b. GREEN**: `config.py`, `features/partner.py`, `events.py`, `dataset.py`, `research.toml`.
  - **Validates: Requirement 16**

- [x] 265. Daily quarters
  - **265a. RED** (`test_research_labels.py`, `test_research_baselines.py`)
    - `day_high_q` and `day_low_q` on a hand-made candle, at the quarter edges (17:00, 00:00, 06:00, 12:00) and across both DST changes.
    - The unshuffled path gives back the labels exactly. The shuffled rate matches the real one on a random walk.
  - **265b. GREEN**: `labels.py`, `baselines.py`.
  - **Validates: Requirement 17**

- [ ] 266. Explore the ideas **(user review)**
  - Run design.md → "Exploration plan (task 266)" on the exploration slice. Nothing is run on the confirmation slice.
  - Write `docs/research/INDICATOR_IDEAS.md`: the exploration numbers, labelled as exploration, and what they suggest.
  - Draft H007 onward for what shows promise, uncommitted. The user confirms the pass rules before the pre-registration commit.


### G. Update 2026-10d: baseline corrections

Both come before any pre-registration (258, 266): H001 needs the random-time fix, and H004/H007 need `sign_flip`.

- [x] 267. Random-time draws exclude only the event's own date; a starved baseline is INSUFFICIENT
  - **Done 2026-10-10.**
    - **The pool:** `random_time_draws` drops only the event's own date. A starved rule gives INSUFFICIENT, and the report's Sample section says why.
    - **A report bug fixed on the way:** the draws line used `min(initial=0)`, so it always printed 0 as the minimum. It now prints the true range.
    - **The golden run, re-baselined:** all 31 events now get their 5 draws (16 used to get fewer). The random-time win rate moved from 0.1447 to 0.1724, next to the coin flip's 0.1712. The verdict is still FAIL.
    - **Re-explored, exploration slice:**
      - H001's random time is now 0.515 at 05:00 and 0.510 at 09:00, from 20 draws per event; it used to read 0.671 and 0.369 from 0–2 draws.
      - H002's win rate minus random time is now −0.001; it was −0.017.
      - No verdict changed.
  - **267a. RED** (`test_research_baselines.py`, `test_research_runner.py`)
    - `test_random_time_draws_same_instrument_slot_and_slice_never_the_events_own_date` replaces the "never event dates" test. Other events' dates may be drawn; the event's own date never is.
    - `test_random_time_daily_event_still_gets_k_draws` — an event on every date gets K draws each.
    - `test_random_time_starved_rule_is_insufficient` — a rule against `random_time` with fewer than K/2 draws per event on average gives INSUFFICIENT, and the report says why.
  - **267b. GREEN** — `baselines.random_time_draws`, `runner.run_test`, `report.py`.
    - Re-baseline the golden research run: its random-time pool changes.
  - **267c. REFACTOR** — re-`explore` H001 and H002 on the exploration slice; note the new random-time values.
  - **Validates: Requirements 10.2 (amended), 10.8**

- [x] 268. The `sign_flip` baseline
  - **Done 2026-10-10.**
    - **The baseline:** `sign_flip` and `_path_labels(..., signs=)`. A flipped bar is mirrored and keeps its slot. The schema accepts it beside `shuffled_path`, for daily rate measures only. The runner pairs each real day where `given` holds with that day's own conditional flip rate.
    - **The key test:** on a random walk whose moves are big only from 01:00 to 13:00, `sign_flip` matches the real statistic, while `shuffled_path` sits more than 3 SE below it. That gap is the false timing edge a shuffle creates.
    - **268c, exploration slice, copies of the H004 and H007 drafts with `sign_flip` added:**

      | Claim | Real | vs `shuffled_path` | vs `sign_flip` |
      |---|---|---|---|
      | H004, lows of up days in the 01/05/09 H4 candles | 0.337 | +0.081 [+0.024, +0.137] | −0.065 [−0.126, −0.006] |
      | H004, highs of down days | 0.402 | +0.104 [+0.038, +0.170] | −0.024 [−0.089, +0.043] |
      | H007, lows of up days in the 06:00–12:00 quarter | 0.159 | +0.060 [+0.018, +0.105] | −0.031 [−0.076, +0.016] |
      | H007, highs of down days | 0.184 | +0.062 [+0.011, +0.119] | −0.019 [−0.067, +0.034] |

      **Every timing excess disappears against `sign_flip`.** The extremes cluster in those windows because the market moves most there, not because it turns there. Lows of up days even fall *outside* the 01/05/09 H4 candles more often than a volatility-matched walk would put them (exploration only).
  - **268a. RED** (`test_research_baselines.py`, `test_research_hypothesis.py`, `test_research_runner.py`)
    - `test_unflipped_path_gives_back_the_candle_labels`
    - `test_sign_flip_keeps_each_bar_in_its_slot_and_size` — a flipped bar's move changes sign, and its high and low swap.
    - `test_sign_flip_keeps_volatility_where_it_was` — on a day whose bars are large only in the 01:00–13:00 window, the flips keep the low of up days there far more often than the shuffles do.
    - `test_sign_flip_matches_the_real_statistic_on_a_random_walk`
    - `test_sign_flip_reproducible_by_seed`
    - The schema accepts `sign_flip` for rate measures on the `daily` event, under the same label rules as `shuffled_path`, and refuses it elsewhere.
    - The runner gives `sign_flip:rate` per real day where `given` holds, from that day's flips.
  - **268b. GREEN** — `baselines.sign_flip`, `hypothesis.py`, `runner._rate`.
  - **268c. REFACTOR** — `explore` the H004 and H007 drafts with `sign_flip` added (without editing the drafts: a scratch copy). Record how much of the timing excess survives it.
  - **Validates: Requirement 10.7**

### H. Update 2026-10e: bias as delivery, and session volatility

These replace the timing drafts and reframe bias before any pre-registration (258, 266). Task 274 ends with the user's review of the redrafted hypotheses.

- [x] 269. The engine's draws as levels
  - **Done 2026-10-10.**
    - **The code:** `features/draws.py` (taken-at), `labels.draw_labels` (`DRAW_LABELS`, joined into `LABEL_COLUMNS`), and `anchor` with `level = "draw"`, a fixed `direction` and `at = "open"`. `stratified` pools both draws. `dataset.py` adds the draws after the anticipation join, and keeps the label table in `LABEL_COLUMNS` order.
    - **Tests:** in `test_research_draws.py`, plus the dataset check in `test_research_runner.py`.
    - **"Beyond", not "at or beyond":** a draw counts as taken or hit only when price trades beyond it, as PDH and PDL are and as the engine's own `untaken` check works. Requirements 18 and 19 are worded to match.
    - **`at = "open"` was added on the way:** gold pauses after 17:00 New York, so its first close is 18:15. A fixed 17:15 anchor would have dropped gold from H001.
    - **269c, exploration slice, from each candle's open:**

      | Instrument | Draw above reached | Distance (ATR) | Draw below reached | Distance (ATR) | Bias-side draw reached |
      |---|---|---|---|---|---|
      | EURUSD | 0.602 | 0.33 | 0.500 | 0.25 | 0.570 |
      | GBPUSD | 0.656 | 0.36 | 0.504 | 0.24 | 0.646 |
      | USDJPY | 0.594 | 0.31 | 0.609 | 0.22 | 0.773 |
      | XAUUSD | 0.694 | 0.21 | 0.496 | 0.34 | 0.680 |

      The draws are close, so they're reached often. The bias side tends to be the nearer draw (LE-D10), which is why H001 compares with a distance-matched (`stratified`) and an against-bias (`complement`) baseline before reading anything into these rates.
  - **269a. RED** (`test_research_features.py`, `test_research_labels.py`, `test_research_events.py`, `test_research_baselines.py`, `test_research_hypothesis.py`)
    - `ant_draw_*_taken_at` on hand-made candles: the first M1 bar at or beyond the draw; null before it and before the anticipation is known. Property 1 covers them.
    - `ant_draw_*_hit_after`/`_hit_at`: strictly after t and before the D1 close. Property 2 covers them.
    - `anchor` with `level = "draw"`: LONG takes the draw above and SHORT the draw below; unknown levels are skipped as `no_level` and taken ones as `taken`.
    - `anchor` with a fixed `direction`; `direction` together with `direction_from` is refused.
    - `stratified` pools both engine draws when the event's level is one. The schema accepts it with `anchor` and `level = "draw"`.
  - **269b. GREEN** — `dataset.py`, `labels.py`, `events.py`, `baselines.py`, `hypothesis.py`.
  - **269c. REFACTOR** — rebuild the real tables, and record how often each draw is hit per instrument (exploration slice).
  - **Validates: Requirement 18**

- [x] 270. The `objective_touch` event
  - **Done 2026-10-10.** `events.objective_touch`, tested in `test_research_draws.py`: both sides, the window edges, the opposite draw untaken, once per side, `touch_extreme`, `with_bias` (true, false and null), and data cut off at t.
  - **270c, exploration slice:** 150 events on 82 of 516 instrument-candles. 70 are with the bias and 80 against.

    | | LONG with | LONG against | SHORT with | SHORT against |
    |---|---|---|---|---|
    | EURUSD | 13 | 13 | 14 | 12 |
    | GBPUSD | 9 | 9 | 8 | 15 |
    | USDJPY | 5 | 7 | 5 | 9 |
    | XAUUSD | 10 | 4 | 6 | 11 |

    The confirmation slice is twice as long, so H003 should clear AR-D4's 100 events on 60 dates.
  - **270a. RED** (`test_research_events.py`)
    - On hand-made candles, LONG and SHORT:
      - the touch inside and outside the window;
      - no event once the opposite draw is taken;
      - at most one event per side per candle;
      - `touch_extreme` is the low (high) since the touch;
      - `objective`, `draw_opposite` and `with_bias` (true, false, null).
    - Property 1 holds with `objective_touch` added.
  - **270b. GREEN** — `events.py`.
  - **270c. REFACTOR** — event counts per instrument and side, with and against the bias, on the real tables.
  - **Validates: Requirement 19**

- [x] 271. The `complement` baseline
  - **Done 2026-10-10.**
    - **How it works:** `run_test` keeps the `where`-false rows (null rows go in neither group) and runs the same measure on them, with no other baselines. Their series sit in the same table as `complement:<stat>`, after the event rows, so the date bootstrap pairs them.
    - **The report:** the Sample section shows the complement's counts and its statistic per instrument.
    - **The checks:**
      - the complement's point estimate equals the same race run with the opposite `where`;
      - event and complement rows never overlap;
      - null rows are counted out of both groups;
      - Property 7 still holds with complement rows.
    - **The golden research run is unchanged.**
  - **271a. RED** (`test_research_runner.py`, `test_research_hypothesis.py`, `test_research_stats.py`)
    - `complement` without `where` is refused.
    - Complement rows are the `where`-false rows; null rows are in neither group.
    - The complement is measured like the events: a race, a rate, a direction.
    - Each row counts in one series only, and the date bootstrap pairs them by date.
    - Property 7 still holds with complement rows.
    - The report shows the complement's counts and its rate per instrument.
  - **271b. GREEN** — `runner.py`, `hypothesis.py`, `report.py`.
  - **271c. REFACTOR** — re-run the golden research run, unchanged since it has no complement.
  - **Validates: Requirement 20**

- [x] 272. Session-volatility features and the `h4_range` geometry
  - **Done 2026-10-10.**
    - **The features:** `features/volatility.py`, cached with the market table (it is in `MARKET_SOURCES`). Each M15 bar belongs to the trading date, H4 candle and slot of its open. Norms are rolling 20-date medians, shifted one date. The "so far" norm and the ratio are null until one bar of the H4 candle has closed.
    - **The geometry:** `h4_range` is measured from the row's close, as `atr` is. The spec is worded to match.
    - **Tests:** in `test_research_volatility.py`, on synthetic markets whose bar ranges follow a formula, so every median is exact:
      - by date, including a spike that never reaches its own date's norm;
      - by position in the H4 candle, where the ratio is exactly 1 because the norm is time-matched;
      - with data cut off at t (Property 1).
    - **272c:** the real build's market step went from 2.9 s to 4.0 s for four instruments; 46 s in all.
  - **272a. RED** (`test_research_volatility.py`, `test_research_races.py`)
    - On a hand-made 25-date instrument:
      - the four norms equal medians over the previous 20 dates only, never the current one;
      - null with fewer than 20 earlier dates;
      - `h4_range_ratio` time-matched within the H4 candle.
    - Property 1 covers the new columns.
    - `{ kind = "h4_range", value = k }` puts the stop or target at k × `h4_range_norm` from the closing-side entry.
  - **272b. GREEN** — `features/volatility.py`, `dataset.py`, `hypothesis.py`, `runner.py`.
  - **272c. REFACTOR** — build time on the real tables.
  - **Validates: Requirements 21.1, 21.2, 21.4**

- [x] 273. The volatility profile
  - **Done 2026-10-10.**
    - **The code:** `profile.py` and the `profile` command. Tested in `test_research_profile.py` and the CLI test in `test_research_runner.py`. `docs/research/VOLATILITY_PROFILE.md` is written from the real exploration slice and committed.
    - **What it shows:** the 09:00 New York H4 candle carries the most range everywhere (a median 48–55% of the day's). USDJPY's 17:00 H4 (the Tokyo morning) carries 43%, against 28% for EURUSD and GBPUSD. 40% of USDJPY's highs and lows form between 17:00 and 01:00, against 30–31% for EURUSD and GBPUSD. This bears out the user's point about Asian pairs.
    - **A data finding, added to the profile as a caveat:**
      - 18–21% of the FX days' lows formed in the 17:00 rollover hour, on spreads 10–15× typical. Other lows sit at about 1× typical, and highs are barely affected (1%).
      - The bars are bid, and the bid dips when the spread blows out, so these lows are artefacts, not selling. Gold has none, because it pauses through the rollover.
      - **Follow-up for the user:** the same bid prices feed the day's lows, the false move, which draws count as taken, the candle labels, and possibly the engine's sell-side raids in the backtests. A price-basis rule is needed: extremes on mid prices, or a filter for spread blowouts.
  - **273a. RED** (`test_research_profile.py`) — on a hand-made two-instrument data set:
    - the per-H4 median ranges and shares;
    - the hour of the high and of the low;
    - the weekday split;
    - the command writes the file and touches no ledger.
  - **273b. GREEN** — `profile.py`, `cli.py`.
  - **273c. REFACTOR** — write `docs/research/VOLATILITY_PROFILE.md` from the real exploration slice, and commit it.
  - **Validates: Requirement 21.3**

- [ ] 274. Redraft the first batch **(user review)**
  - **Drafted and explored 2026-10-10; waiting for the user's review.**
    - **Drafts, uncommitted:** `H001-bias-draw-delivered.toml`, `H003-bias-objective-touch.toml` and `H010-side-of-open-at-0500.toml`. The old H001 and H003 drafts were replaced; they were never pre-registered. H004 and H007 carry a WITHDRAWN header and are left for the user.
    - **Exploration slice (not evidence):**

      | Test | Verdict | Against the rule's baselines |
      |---|---|---|
      | H001, bullish → draw above | PASS | +0.146 [+0.052, +0.240] vs complement; +0.072 [+0.012, +0.132] vs stratified |
      | H001, bearish → draw below | FAIL | +0.143 [+0.047, +0.238] vs complement; −0.056 [−0.123, +0.009] vs stratified |
      | H003 (stop at the touch's low) | INSUFFICIENT (69 events) | win rate −0.039 vs coin flip [−0.056, −0.021]; net −0.93R |
      | H010 | PASS | +0.097 [+0.027, +0.165] vs stratified |

    - **H003's stop.** With stops of 0.5× and 1× the session's normal H4 range (scratch copies, not drafts), H003 stays negative: win rate 6–8 points below the coin flip, net −0.40R and −0.27R, and no better than its complement. After the touch, price tends to continue rather than reverse, without the user's step-3 signature (stage 2).
    - **The rollover distorts H001's bearish test.** Of the draws below taken before the open's first close, 92% (36 of 39) were taken at the 17:00–17:14 rollover: the bid dips as the spread blows out (task 273). None of the draws above were. A price-basis fix should come before pre-registration.
  - Redraft H001 and H003, and draft H010, from design.md → "The redrafted first batch". The files stay uncommitted.
  - Mark H004 and H007 as withdrawn (AR-D21), leaving the files for the user.
  - `explore` the redrafts on the exploration slice and report the numbers.
  - The user confirms each file's rules. The commit is the pre-registration, and then task 259 runs them on the confirmation slice.

### I. Update 2026-10f: the user's markets

The user's ten markets, in their order (Requirement 22). Task 319 needs Docker for the candle store and the MT5 terminal for the Exness history.

- [x] 317. The Exness focus instruments, and chart precision and order
  - **Done 2026-10-16.** Specs exported from ExnessKE-MT5Trial9 with no commission (a Standard account):

    | Instrument | Symbol | Point | Contract | Quote | Typical spread (median of the day's ticks) |
    |---|---|---|---|---|---|
    | DXY | DXYm | 0.001 | 1000 | USD | 0.013 |
    | US100 | USTECm | 0.01 | 1 | USD | 1.12 |
    | US500 | US500m | 0.01 | 1 | USD | 0.40 |
    | US30 | US30m | 0.1 | 1 | USD | 1.0 |
    | GER40 | DE30m | 0.1 | 1 | EUR | 0.70 |
    | UK100 | UK100m | 0.01 | 1 | GBP | 0.98 |

    - **UK100's spread varies by session:** 3.0 in the Asian hours of 2026-10-15 against the 0.98 median. Races floor each bar at the typical spread and charge the bar's own spread when it is wider (D10). A stop of a few points is spread-sensitive there.
    - **The swap-free profile:** the uncommitted task-240 profile `exness-standard-swapfree.toml` got the same six symbols, so its same-symbols test still holds. It stays uncommitted with task 240.
  - **317a. RED** (`test_research_markets.py`)
    - The `exness-standard` profile maps DXY, US100, US500, US30, GER40 and UK100 to DXYm, USTECm, US500m, US30m, DE30m and UK100m, and keeps its four old symbols.
    - The spec file loads them with the terminal's quote currencies: USD for DXY and the US indices, EUR for GER40, GBP for UK100. EURUSD, GBPUSD, USDJPY and XAUUSD are unchanged.
    - `ReplayBars.digits` on hand-made prices: 10708.61 → 2, 44120.5 → 1, 98.123 → 3, 1.16512 → 5, and float noise (1.1 + 0.2) doesn't add decimals. Empty data, or prices on no grid of up to 6 decimals, fall back to the old rule.
    - `ChartsApp` lists the snapshot's instruments in the configured order, then any others sorted.
  - **317b. GREEN**
    - `config/brokers/exness-standard.toml`: the six symbols.
    - `config/instruments/exness-standard.toml`: their specs, exported from the terminal into a scratch file and merged. The four old entries and the source line stay as they are.
    - `replay/bars.py` and `replay/charts.py`; `charts.serve` passes the research instruments.
  - **317c. REFACTOR** — none planned.
  - **Validates: Requirements 22.2, 22.5**

- [x] 318. Instruments from several profiles, and Saturday for 24/7 venues
  - **Done 2026-10-16.**
    - **What changed:** `ResearchConfig.profiles` and `profile_of`; `snapshot.Origin` and per-instrument origins in the manifest; `specs.ResearchSpecs`. The `snapshot` command reads each profile from its own store.
    - **Caches:** the market and label caches gain `all_week` in their key, and `frame.py`'s change re-keys them all, so the next `build` recomputes them (a few minutes). The anticipation cache (the engine) doesn't read `frame.py`, so instruments whose data is unchanged keep theirs.
    - **Tests:** the research, replay and watch suites pass: 380 passed, 1 skipped (the slow self-check).
  - **318a. RED** (`test_research_config.py`, `test_research_snapshot.py`, `test_research_frame.py`, `test_research_markets.py`)
    - `profiles` maps an instrument to another profile; a key that isn't an instrument is refused; `profile_of` falls back to `profile`.
    - A snapshot exported from two in-memory sources (an MT5 venue and a Binance venue) records each instrument's origin, and loads back with the same fingerprints. The Binance instrument's weekend shows as a gap there, and the MT5 instrument's weekend doesn't.
    - A manifest without origins (the old format) still loads.
    - `ResearchSpecs` gives each instrument its own profile's spec and account currency. Race costs for a Binance spec are charged in USDT.
    - `build_grid` keeps Saturday's trading date for an `all_week` frame and drops it otherwise. Property 1 still holds.
  - **318b. GREEN** — `config.py`, `snapshot.py`, `specs.py` (new), `cli.py`, `frame.py`, `dataset.py`.
  - **318c. REFACTOR** — none planned.
  - **Validates: Requirements 22.3, 22.4**

- [ ] 319. The focus snapshot **(user review)**
  - **Exported 2026-10-16; the build and the user's look at the charts are next.**
    - **The store:** M1 for the six new Exness instruments, 2023-10-17 to 2026-10-16, 1.01–1.11 million rows each. BTCUSDT was already there from Binance, from 2023-10-04.
    - **The Docker crash:** starting Docker Desktop brought up the whole stack, and it crashed once mid-load. Afterwards the store's counts matched the terminal's to a few bars, so no rows were lost. Only TimescaleDB is needed here.
    - **`focus-2025-2026h1`** (code 2e8a590):

      | Instrument | M1 rows | Coverage problems | What they are |
      |---|---|---|---|
      | DXY | 788,575 | 4 | Exness outages of 34–86 minutes |
      | XAUUSD | 751,095 | 17 | as in `exness-2025-2026h1` |
      | EURUSD | 791,537 | 2 | as before |
      | GBPUSD | 791,387 | 1 | as before |
      | US100, US500, US30 | ~747,000 each | 19 each | US holidays and early closes (MLK, Presidents', Good Friday, Memorial, Juneteenth, 3–4 July, Labor, Thanksgiving) |
      | GER40 | 726,193 | 7 | Easter, 1 May, Christmas, and a late Sunday open (2026-05-10) |
      | UK100 | 719,596 | 11 | Easter, the UK bank holidays, Christmas |
      | BTCUSDT | 1,118,820 | 0 | none |

      Every instrument also has a 47-minute Exness outage on 2025-01-03 at 11:46 UTC. Every warm-up comes from M1.
    - **Fingerprints:** EURUSD, GBPUSD and XAUUSD are identical to `exness-2025-2026h1`, so their engine anticipations come from the cache.
    - **`build --workers 4`:** 394 s, of which the anticipation (the seven new instruments) took 214 s.
      - Feature rows: about 37,000 per FX pair, 35,400 per US index, 34,500–34,700 for GER40 and UK100, and 53,000 for BTCUSDT (its weekends).
      - 22 days have no anticipation, all market closures: New Year, Christmas and Good Friday.
      - Docker was shut down first (`wsl --shutdown` freed 8.6 GB); the build doesn't need the store.
    - **The charts:** `python -m algo_research.replay` lists the ten tabs in the user's order, with prices at each instrument's own precision.
    - **Waiting on the user:** a look at the ten charts.
  - Start Docker. Load M1 into the store: the six new Exness instruments from 2024-09-30, and BTCUSDT from Binance over the same span.
  - research.toml:
    - the ten instruments in the user's order;
    - `[profiles] BTCUSDT = "binance"`;
    - `snapshot = "focus-2025-2026h1"`.
  - Export the snapshot. Compare the EURUSD, GBPUSD and gold fingerprints with `exness-2025-2026h1`. Record each instrument's coverage problems here.
  - `build` the feature tables.
  - Open the charts with all ten tabs for the user.
  - **Validates: Requirements 22.1, 22.3; AR-D26**

### J. Update 2026-10g: the turn atlas

The user's framework, reverse-engineered on the exploration slice (Requirements 23–28). Every module is new, under `algo_research/atlas/`, and is tested in `test_research_atlas.py` on hand-made bars, plus one real-data smoke test on the fixture week.

- [x] 320. Arrays as the user reads them
  - **Done 2026-10-16.** `atlas/arrays.py`, tested in `test_research_atlas.py`.
    - **UK100 over the snapshot** (warm-up included): 26,351 arrays in 0.9 s (loading the snapshot takes 23 s).

      | Timeframe | FVGs | OBs | Inverted by the data's end |
      |---|---|---|---|
      | M15 | 12,028 | 7,846 | 98% / 97% |
      | H1 | 2,745 | 2,365 | 97% / 94% |
      | H4 | 675 | 505 | 93% / 90% |
      | D1 | 82 | 68 | 78% / 76% |
      | W1 | 23 | 14 | 61% / 64% |

    - **Reading:** almost every lower-timeframe gap is closed through in the end. So "an FVG below" is nearly always true somewhere, which is why the atlas compares against base rates.
  - **320a. RED**
    - **FVG:** a bullish and a bearish FVG on hand-made bars give the gap's low, high, CE and formation time (C3's close). Three candles without a gap give none. The FVG survives a wick into it and a close inside it. A close beyond its far edge flips it, and its state at a time before that close is still FVG.
    - **Order block:** it matches `measures.bearish_order_blocks` and the mirror. The MT is the body's midpoint. A close beyond it flips it into a breaker.
    - **Property 1:** the state at t never reads a bar that closes after t.
  - **320b. GREEN** — `atlas/arrays.py`.
  - **Validates: Requirement 23**

- [x] 321. Swings and what they delivered
  - **Done 2026-10-16.** `atlas/swings.py`.
    - **The slice only:** `build_swings(frame, tf, since, until)` judges outcomes on M1 before `until`, so the atlas never reads past the exploration slice. A swing unresolved by then is open.
    - **UK100, exploration slice:** M15 has 6,618 swings (1,563 of them engulfing), scored in 2.5 s; D1 has 80. Three-candle base rates, held among those resolved:

      | Timeframe | `crt` | `same_tf` | `next_tf` |
      |---|---|---|---|
      | M15 | 72% | 56% | 28% |
      | H1 | 72% | 56% | 28% |
      | H4 | 69% | 53% | 23% |
      | D1 | 71% | 61% | 32% |

    - **Reading:** the rates barely change across timeframes, as a random walk's do (it looks the same at every scale). The information, if any, lies in the context (task 322) measured against these rates.
  - **321a. RED**
    - **Three-candle swings:** a low and a high. Equal neighbours are not swings, and an outside bar is both.
    - **Engulfing swings:** the low (the sweep, then a close above the previous body), and `engulf_full`. The link to the same extreme's three-candle swing.
    - **The three objectives** on a hand-made path, each held, failed and open. An objective reached at once is marked.
    - **Order within one bar:** a T bar that takes both the extreme and the objective is settled on M1. One M1 bar doing both is failed.
    - **Excursion** in average ranges.
    - **Mirroring:** lows and highs agree on the mirrored path.
  - **321b. GREEN** — `atlas/swings.py`.
  - **Validates: Requirement 24**

- [x] 322. The context at a swing
  - **Done 2026-10-16.** `atlas/context.py`. UK100 over the exploration slice: 8,974 swings on every timeframe in 4.4 s.
    - **Process slip:** the module was written before its tests (RED wasn't first). The tests were then written from the requirement, not the code. They found two bugs: the session and month "known" times overflowed through float64, and two swings sharing one price needed a list lookup.
    - **A level is untaken at the bar's open** when the first M1 bar beyond it, after it was known, opens at or after the bar's open. This is computed once per level, so the check is vectorised.
    - **First look, UK100 three-candle M15 swings (not evidence):** 96% traded into some facing higher-timeframe array, and their held rate equals the base rate (56%). Turtle soups held 63%. On H4, a swept previous-day low held 32% (base 53%). Task 323 ranks these across all ten markets with intervals.
  - **322a. RED**
    - **Arrays traded into:**
      - an H4 bullish FVG under an M15 swing low gives `edge`, `mid` or `through` by the wick's depth;
      - an array formed during the extreme bar doesn't count;
      - an array facing the other way doesn't count.
    - **Liquidity:** the previous day's low taken, the Asian low taken, equal lows within 0.1 of the average range, and an untaken H1 swing low taken.
    - **Dealing range:** 0.2 is discount and 0.8 is premium, for a low.
    - **Time and anatomy:** the turtle soup, the wick share, displacement and `closes_beyond`, the swing's own FVG.
    - **Property 1:** over every context column.
  - **322b. GREEN** — `atlas/context.py`.
  - **Validates: Requirement 25**

- [ ] 323. The atlas report **(user review)**
  - **Built and run 2026-10-16; waiting for the user's review.** `atlas/report.py` and the `atlas` command; `docs/research/TURN_ATLAS.md`. The run covered 94,232 swings of the ten markets in 425 s, and each frame is cut at the slice's end first.
  - **The first run was corrected before review (AR-D33).** It ranked values by raw held rate. Own FVG (91%), displacement and close-beyond came top, but each matched what a random walk from the confirming close delivers, within 1–3 points. "Sweeps hold less" was geometry too. Also:
    - a touch had counted as held, a 1–3 point head start;
    - counting each extreme once had kept only the engulfing swings whose next bar took their extreme, and those fail by construction.

    Now outcomes are strict, every swing carries its geometry, base rates count every swing, and values are ranked by excess over geometry on the three-candle swings.
  - **What the corrected atlas shows (exploration slice; leads, not findings).** About 1,100 values were tested, so about 55 clear the 95% bar by chance.
    - **Intraday swings behave like a random walk.** The base excess on M15, H1 and H4 is within ±1 point for both types and all objectives, and nearly every context value is within ±2.
      - The M15 17:00 hour (+7.5) is mostly EURUSD, GBPUSD and DXY: the rollover bid-dip (task 273).
      - Trading *through* a W1 or D1 order block's far edge is consistently worse, by 4 to 9 points.
    - **Daily swings deliver beyond geometry.** D1 three-candle swings: +3.4 points (`same_tf`) and +5.7 (`next_tf`). D1 engulfing swings: +11.7 (`next_tf`, 156 resolved). Within D1, `next_tf`:
      - `liq_pw` (the swing took the previous week's extreme): +14.9 [+2.7, +26.7], positive in all ten markets;
      - `twin` (the user's engulfing variation printing as a three-candle swing): +14.7 [+4.5, +24.2], positive in 9 of 10;
      - an IFVG traded through: +7.7 [+1.6, +13.8].

      This is the user's framework: a higher-timeframe swing formed after price traded into an important level. Samples are small (100–480 swings), so these are the candidates to pre-register for the confirmation slice.
  - **323a. RED** (`test_research_atlas.py`, `test_research_runner.py`)
    - The base rates, and a value's lift and complement with resampled intervals, on a hand-made table.
    - The minimum-count rule.
    - The `atlas` command writes the report and the tables, reads only the exploration slice, and adds no ledger row.
  - **323b. GREEN** — `atlas/report.py`, `cli.py`.
  - **323c. REFACTOR** — run it on `focus-2025-2026h1`, commit `docs/research/TURN_ATLAS.md`, and record the timings and the strongest values here.
  - **Validates: Requirement 26**

- [ ] 324. The fold **(user review)**
  - **324a. RED**
    - **Nesting:** on a hand-made D1 swing low built from M1, the H4, H1 and M15 swings at its extreme are found with their types, and the turtle soup on a lower timeframe is marked.
    - **The first retracement:** its depth, the OTE flag, and whether the objective came after.
  - **324b. GREEN** — `atlas/fold.py`; the report gains the fold.
  - **324c. REFACTOR** — rerun on the snapshot and update the report.
  - **Validates: Requirement 27**

- [ ] 325. The Atlas mode **(user review)**
  - **325a. RED** (`test_replay_charts.py`)
    - `/atlas` and its API serve the swings and arrays of an instrument and timeframe as of a time, with outcomes and context.
    - The You pages don't reference it.
  - **325b. GREEN** — `replay/charts.py`, `replay/static/atlas.html` and `atlas.js` (on `shell.js` and `drawings.js`).
  - **325c. REFACTOR** — check the page in headless Chrome.
  - **Validates: Requirement 28**

### K. Update 2026-10i: the economic calendar

News as context (Requirements 29–30). Task 327 needs the user once: to run the export script in the MT5 terminal.

- [x] 327. Calendar history
  - **Done 2026-10-16.**
    - **Running the script:** dragging it onto a chart never started it. Each drag loaded it; it never initialised ("failed with code 0"), and the next drag replaced it. No dialog was open, visible or hidden. It ran when MT5 was restarted with a start config (`[StartUp] Script=AgentICTrader\AgenticCalendarExport`). The first run timed out on USD (error 5401) while the terminal was still downloading the calendar, so the script now queries a month at a time and retries a month that times out. It was then rerun.
    - **The import:** the file is cp1252 (FILE_ANSI; an en dash broke the UTF-8 read), so the import falls back to cp1252.
    - **`mt5-calendar`:** 16,451 values from 2024-09-02 to 2026-10-16, 15,211 of them with an exact time. High importance: USD 1,052, EUR 315, GBP 165.
    - **Times checked:** NFP 12:30 UTC in summer; the Fed at 18:00 UTC, and 19:00 after the clocks changed; the ECB 12:15; the BoE 11:00.
    - **A caveat:** MetaQuotes rates some routine releases high (weekly crude stocks, jobless claims, Treasury auctions). `algo_research/calendar.py`, `calendar --import`, `scripts/mql5/AgenticCalendarExport.mq5`.
    - MetaEditor (build 6241) compiled the script with 0 errors and 0 warnings. It is installed as `MQL5\Scripts\AgentICTrader\AgenticCalendarExport` in the Exness terminal's data folder.
    - It writes `Common\Files\agentic_calendar_<from>_<to>.csv`.
  - **327a. RED** (`test_research_calendar.py`)
    - On a hand-written export (with server offsets of +0 and +3):
      - the import gives UTC times;
      - blank values are nulls, and values are numbers;
      - rows are de-duplicated by `value_id` and sorted.
    - The manifest's sha256 changes with the data.
    - `releases` keeps exact-time, high-importance rows of the given currencies only.
  - **327b. GREEN**
    - `scripts/mql5/AgenticCalendarExport.mq5`, compiled with MetaEditor.
    - `algo_research/calendar.py`, and `calendar --import` in `cli.py`.
  - **327c. REFACTOR**
    - The user runs the script.
    - Import its file, and record the counts per currency and importance.
  - **Validates: Requirement 29**

- [ ] 328. News in the atlas **(user review)**
  - **Built and run 2026-10-16; waiting for the user's review.** The atlas ran with the calendar in 278 s.
    - **How often:** 2.4% of three-candle swings had their extreme printed by a release (`news_made`). 41% fell on days with two or more high releases.
    - **Against geometry (leads only):**
      - **A release printed the extreme:** on H1 and H4 these swings delivered beyond a random walk: H1 +5.3 [+1.5, +9.0] (`same_tf`, 392 swings) and +6.8 [+0.8, +12.7] (`next_tf`); H4 +6.6 [+0.8, +12.8] (`same_tf`, 158). On M15 the effect is nil (+0.4, 1,121 swings).
      - **An extreme that ran before a release** (`news_ahead`): nothing (−4 to +2, intervals spanning zero).
      - **D1** (small samples): days without a high release, +12.9 [+1.7, +24.4] (`same_tf`, 163); a release in the next daily bar, +8.8 [+1.1, +17.1] (`next_tf`, 305).
    - **Reading:** news doesn't change the intraday random walk. The exception is the release that itself prints the turn on H1 and H4, the news spike that reverses.
    - **Possible refinement:** a curated release list (NFP, CPI, FOMC, ECB, BoE, GDP, PMIs) in place of MetaQuotes' broad high-importance tag.
    - `atlas/news.py`, `CalendarSection` (`[calendar]` in research.toml, `name = "mt5-calendar"`, HIGH only), and the report's news values.
    - Without an imported calendar, the atlas runs without news and says so in its Inputs.
    - The research and replay suites pass: 412 passed, 1 skipped.
  - **328a. RED** (`test_research_atlas.py`, `test_research_config.py`)
    - On hand-made swings and releases: each flag at its window's edges, `news_day` per trading date, and only an instrument's own currencies and importance counting.
    - `[calendar]` in research.toml, with the AR-D35 defaults.
    - The atlas builds without a calendar.
  - **328b. GREEN** — `config.py`, `atlas/news.py`, `atlas/report.py`, `cli.py`.
  - **328c. REFACTOR** — rerun the atlas with the calendar, and record what the news columns show against geometry.
  - **Validates: Requirement 30**

### L. Update 2026-10j: supply and demand

- [x] 339. Supply and demand zones **(user review)**
  - **339a. RED** (`test_research_supply_demand.py`)
    - A base and an explosive leg-out make a zone, known at the leg-out's close, with its proximal and distal lines.
    - No base, or no explosion, makes none.
    - A zone is fresh until price returns, and broken by a close beyond its far line.
  - **339b. GREEN** — `algo_research/supply_demand.py`: `zones`, `zone_life`, `trade_zones`; `python -m algo_research.supply_demand [--paired]`.
  - **Done 2026-10-20.** 3 tests. Exploration slice, five markets:
    - **Alone, a coin flip:** H4 2R hit 0.32 vs chance 0.33, +0.04R net [−0.20, +0.31]; H1 2R 0.27 vs 0.33, −0.07R. D1 has 24 zones in six months, too few to judge.
    - **Paired, no separation:** the indicator's setups that swept into a fresh zone made +0.08R net (51 trades, [−0.13, +0.30]) against −0.04R for the rest.
    - The findings are in `docs/research/SUPPLY_DEMAND.md`.
  - **Validates: Requirements 31.1–31.3**

---

## Task Dependency Graph

Tasks are grouped into waves. A wave can start once every wave in its `dependencies` is complete. Tasks inside a wave can run in any order unless a task's text says otherwise (245 needs 244; 253 needs 250 and 251).

```json
{
  "waves": [
    {
      "name": "Foundations",
      "tasks": ["244", "245", "246"],
      "description": "Configuration and slices, the snapshot, frames and the trading calendar"
    },
    {
      "name": "Features and Labels",
      "tasks": ["247", "248", "249"],
      "description": "Market features, daily anticipation from the engine, forward and candle labels",
      "dependencies": ["Foundations"]
    },
    {
      "name": "Races",
      "tasks": ["250"],
      "description": "Race engine with the FillModel's price rules",
      "dependencies": ["Foundations"]
    },
    {
      "name": "Questions and Statistics",
      "tasks": ["251", "252", "253"],
      "description": "Hypothesis schema, events and filters; day-cluster bootstrap and verdict; baselines",
      "dependencies": ["Features and Labels", "Races"]
    },
    {
      "name": "Runner",
      "tasks": ["254"],
      "description": "explore / run / ledger commands, pre-registration checks, reports",
      "dependencies": ["Questions and Statistics"]
    },
    {
      "name": "Self-Validation and Checkpoint",
      "tasks": ["255", "256"],
      "description": "Null calibration, planted edge, golden research run; full suite and speed",
      "dependencies": ["Runner"]
    },
    {
      "name": "First Results",
      "tasks": ["257", "258", "259"],
      "description": "Real snapshot (Docker), H001-H004 pre-registered with the user, run and reviewed",
      "dependencies": ["Self-Validation and Checkpoint"]
    },
    {
      "name": "Stage 2",
      "tasks": ["260", "261", "262"],
      "description": "Engine features at every close, H005-H006, decide the next step",
      "dependencies": ["First Results"]
    },
    {
      "name": "Indicator Ideas",
      "tasks": ["263", "264", "265", "266"],
      "description": "Update 2026-10c: candle ranges and crt, SMT, daily quarters, then exploration (264 needs 263; 266 needs 263-265)",
      "dependencies": ["Self-Validation and Checkpoint"]
    },
    {
      "name": "Baseline Corrections",
      "tasks": ["267", "268"],
      "description": "Update 2026-10d: random-time pool and the sign_flip baseline, before any pre-registration (258, 266)",
      "dependencies": ["Self-Validation and Checkpoint"]
    },
    {
      "name": "Bias as Delivery and Session Volatility",
      "tasks": ["269", "270", "271", "272", "273", "274"],
      "description": "Update 2026-10e: engine draws as levels, objective touch, complement baseline, session volatility, profile; then the redrafted batch (270 needs 269; 274 needs 269-273)",
      "dependencies": ["Baseline Corrections"]
    },
    {
      "name": "The User's Markets",
      "tasks": ["317", "318", "319"],
      "description": "Update 2026-10f: the Exness focus instruments and chart precision, several profiles and 24/7 Saturdays, then the focus snapshot (319 needs 317 and 318, Docker and the MT5 terminal)",
      "dependencies": ["Self-Validation and Checkpoint"]
    },
    {
      "name": "The Turn Atlas",
      "tasks": ["320", "321", "322", "323", "324", "325"],
      "description": "Update 2026-10g: arrays as the user reads them, swings and outcomes, context, the report, the fold, the Atlas mode (in order; each needs the one before)",
      "dependencies": ["The User's Markets"]
    },
    {
      "name": "The Economic Calendar",
      "tasks": ["327", "328"],
      "description": "Update 2026-10i: calendar history from the MT5 terminal (the user runs the export once), then news in the atlas (328 needs 327 and the atlas report, 323)",
      "dependencies": ["The User's Markets"]
    }
  ]
}
```

---

## Notes

- Every implementation task follows RED → GREEN → REFACTOR. No production code is written without a failing test first.
- Hypothesis property tests run with `@settings(max_examples=100)`. Property 1 uses 25, because each example rebuilds the features. Property 8 is marked `slow`.
- **No new packages are installed:**
  - pandas, numpy, pydantic and hypothesis are already listed in `requirements.txt`;
  - `pyarrow` is already installed (an MLflow dependency) and only gets listed (C2);
  - `tomllib` is in the standard library.
- AlgoResearch changes no live code, no backtester code and no Phase A cache key. Its only edits outside its own package are C1 and C2.
- One commit per task, pushed (as for the other specs). Hypothesis files are committed in their own commit before they run, which is the pre-registration. The ledger, its reports and `FIRST_BATCH.md` are committed with the task that ran them.
- Strategy changes are out of scope. A PASS becomes a proposal in a `liquidity-engine` spec update, judged by the backtester, then the hold-out.
- The study hold-out (`baseline-2026q3`, from 2026-07-07) is never read by AlgoResearch.
