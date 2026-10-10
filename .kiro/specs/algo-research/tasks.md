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

- [ ] 269. The engine's draws as levels
  - **269a. RED** (`test_research_features.py`, `test_research_labels.py`, `test_research_events.py`, `test_research_baselines.py`, `test_research_hypothesis.py`)
    - `ant_draw_*_taken_at` on hand-made candles: the first M1 bar at or beyond the draw; null before it and before the anticipation is known. Property 1 covers them.
    - `ant_draw_*_hit_after`/`_hit_at`: strictly after t and before the D1 close. Property 2 covers them.
    - `anchor` with `level = "draw"`: LONG takes the draw above and SHORT the draw below; unknown levels are skipped as `no_level` and taken ones as `taken`.
    - `anchor` with a fixed `direction`; `direction` together with `direction_from` is refused.
    - `stratified` pools both engine draws when the event's level is one. The schema accepts it with `anchor` and `level = "draw"`.
  - **269b. GREEN** — `dataset.py`, `labels.py`, `events.py`, `baselines.py`, `hypothesis.py`.
  - **269c. REFACTOR** — rebuild the real tables, and record how often each draw is hit per instrument (exploration slice).
  - **Validates: Requirement 18**

- [ ] 270. The `objective_touch` event
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

- [ ] 271. The `complement` baseline
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

- [ ] 272. Session-volatility features and the `h4_range` geometry
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

- [ ] 273. The volatility profile
  - **273a. RED** (`test_research_profile.py`) — on a hand-made two-instrument data set:
    - the per-H4 median ranges and shares;
    - the hour of the high and of the low;
    - the weekday split;
    - the command writes the file and touches no ledger.
  - **273b. GREEN** — `profile.py`, `cli.py`.
  - **273c. REFACTOR** — write `docs/research/VOLATILITY_PROFILE.md` from the real exploration slice, and commit it.
  - **Validates: Requirement 21.3**

- [ ] 274. Redraft the first batch **(user review)**
  - Redraft H001 and H003, and draft H010, from design.md → "The redrafted first batch". The files stay uncommitted.
  - Mark H004 and H007 as withdrawn (AR-D21), leaving the files for the user.
  - `explore` the redrafts on the exploration slice and report the numbers.
  - The user confirms each file's rules. The commit is the pre-registration, and then task 259 runs them on the confirmation slice.

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
