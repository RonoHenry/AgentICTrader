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

- [ ] 256. Checkpoint
  - **Suite:** the full suite is green apart from the task-39 RED tests, with the `slow` research tests run once.
  - **Speed:** build and run times on the fixtures, recorded in design.md → Measured Performance.
  - **Review:** anything to change before real data is used.

### D. First results

- [ ] 257. Real snapshot and build **(user action: Docker running)**
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
