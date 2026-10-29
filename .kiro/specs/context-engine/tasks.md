# Implementation Plan

**spec**: Context Engine

## Overview

Build order for `requirements.md` and `design.md` (decisions CE-D1 to CE-D13 at their proposed defaults unless the user changes them).
- **Numbering:** tasks continue the platform sequence from **275**.
- **TDD:** every code task follows the **RED → GREEN → REFACTOR** cycle in `.kiro/steering/tdd-and-testing.md`.
- **Tests:** they live in `backend/tests/test_context_*.py`, fixtures under `backend/tests/fixtures/context/`.
- **Properties:** "Property N" refers to this spec's `design.md` → Correctness Properties, tested with `hypothesis`. Other specs' properties are named with their spec (e.g., liquidity-engine Property 35).

**Stage 1 comes first, and needs no new code.** Liquidity-engine task 242 runs the D1 anticipation variants: the candle profile's bias, the false move, the manipulation window, the HTF POI and the draw target. Together they are a one-level context (W1 → D1). Their result is the bar the context modes must beat. Task 242 waits on task 240's swap export, but it can run swap-free now: the swap-free account's result is one of its required outputs anyway.

The plan runs in four groups:
- **A. Foundations (275–276):** ladders and modes; analysis prices.
- **B. The context model (277–280):** frame state, the chain, time, then a checkpoint with legacy parity.
- **C. Research before trading (281–283):** context features and labels, the user's journal, the first hypotheses.
- **D. Trading the context (284–289):** selection, orders, the backtester's modes, then the runs and the decision.

Tasks marked **(user action)** need Docker, the MT5 terminal, data or a decision from you. Tasks marked **(user review)** end with your review before the next one starts.

---

## Tasks

### A. Foundations

- [ ] 275. Ladders and modes
  - **275a. RED** (`backend/tests/test_context_ladder.py`)
    - `test_modes_ship_with_their_ladders` — the Model A sets of MA-D1 (`model_d1` D1 → H1, execution M5; `model_h4` H4 → M15, execution M1, with the M30 and M3 variants) and the four earlier ladders as custom ladders (update 2026-10-15).
    - `test_nesting_checked_on_the_calendar` — D1 → H4 → H1 → M15 → M5 → M1 nest; D1 → H6 is refused naming the pair; W1 under MN1 is allowed.
    - `test_execution_below_bias_frame` and `test_one_to_four_frames`
    - `test_custom_ladder_from_toml`
    - `test_mode_in_phase_a_cache_key` — two modes, two keys; `legacy` keeps today's key.
    - `test_legacy_is_default` — `StrategyConfig()` is unchanged in every existing field.
  - **275b. GREEN** — `liquidity_engine/context/ladder.py`; `StrategyConfig.mode`, `ladder` and the other C1 fields at their defaults; `cache.py`.
  - **275c. REFACTOR**
  - **Validates: Requirements 1.1–1.3**

- [ ] 276. Analysis prices: the rollover quarantine
  - **276a. RED** (`backend/tests/test_context_analysis_bars.py`)
    - `test_blowout_run_flattened_at_last_clean_close`
    - `test_run_ends_at_first_clean_bar_or_60_minutes`
    - `test_typical_spread_uses_only_past_bars`
    - `test_gold_without_blowout_unchanged`
    - `test_fill_bars_unchanged` — fills read raw prices, quarantine on or off.
    - `test_d1_open_is_last_clean_close`
    - Property 4 (Hypothesis): random M1 series with and without blowouts.
  - **276b. GREEN**
    - `services/market_data/analysis_bars.py`.
    - Wired into the engine's bars in `algo_backtester/data.py`, behind `StrategyConfig.rollover_quarantine`.
    - AlgoResearch's frames and labels read the quarantined bars. This fixes the research labels distorted on 2026-10-10: H001-bearish's draws taken by rollover dips.
    - The profile reports the quarantined share and the day extremes moved.
  - **276c. REFACTOR** — re-run `algo_research profile`; record in `docs/research/VOLATILITY_PROFILE.md` the 17:00-hour share of day lows before and after.
  - **Validates: Requirements 2.1–2.5**

### B. The context model

- [x] 277. Frame state
  - **Done 2026-10-24** (update 2026-10-24, CE-D14 to CE-D16). `frame_state(frame, price, parents, lower, path,
    forming, levels, asia)` in `context/frame_state.py`, beside Model A's functions, which are unchanged. 16 tests,
    Property 1 included. `lower` lets the candle profile's H4 pools count, for Property 6 (task 278).
  - **277a. RED** (`backend/tests/test_context_frame_state.py`)
    - `test_dealing_range_from_last_confirmed_swings`
    - `test_range_stretches_past_a_broken_swing_until_a_new_one_confirms`
    - `test_zone_bands` — 0.45 / 0.55; `UNRANGED` without a swing on a side.
    - `test_objectives_from_frame_and_parents_untaken_only`
    - `test_asian_range_only_at_d1_and_below`
    - `test_trend_closure_rule_at_any_frame` (LE-D15)
    - `test_own_direction_trending_and_not`
    - `test_poi_nearest_unfilled_array_in_zone`
    - `test_reasons_present_for_every_field`
    - Property 1 (Hypothesis): frame invariance.
  - **277b. GREEN** — `context/frame_state.py`, reusing `find_swing_highs`/`find_swing_lows`, `PDArrayDetector` output and the candle profile's `nearest_objectives()`.
  - **277c. REFACTOR**
  - **Validates: Requirements 3.1–3.3**

- [x] 278. The context chain
  - **Done 2026-10-24.** `chain(states, rule)` in `context/chain.py`: `Link` per frame (own and context direction,
    case, draw, the parent's POI, a reason), `Chain.armed` and `unarmed_reason` (`CONTEXT_NEUTRAL`, `NO_DRAW`).
    14 tests. Property 3: 300 random ladders, as well as the `PROFILE` draws. Property 6: `PROFILE` on W1 → D1
    equals `CandleProfileAnalyzer` on 40 random H4 walks and on the profile's own trending week, trend, both
    nearest objectives, direction and draw. A W1 draw, the trend's fallback to a D1 or H4 objective, and the nearer
    side are all exercised.
  - **278a. RED** (`backend/tests/test_context_chain.py`)
    - `test_top_frame_takes_its_own_direction`
    - `test_with_parent_in_the_right_zone`
    - `test_to_parent_poi_from_the_wrong_zone` — weekly bullish, price in weekly premium with an unreached bullish weekly FVG below: D1 is bearish, drawn to the FVG's high.
    - `test_with_parent_once_poi_reached`
    - `test_neutral_parent_gives_neutral_child`
    - `test_no_draw_means_not_armed`
    - `test_poi_reached_and_draw_taken_strictly` (liquidity-engine Requirement 13.5)
    - Property 3 (Hypothesis): chain consistency.
    - Property 6: `PROFILE` on W1 → D1 equals `CandleProfileAnalyzer` on the engine fixtures.
  - **278b. GREEN** — `context/chain.py` (`PD_POI`, `PROFILE`).
  - **278c. REFACTOR**
  - **Validates: Requirements 4.1–4.6**

- [ ] 279. Time in every frame
  - **279a. RED** (`backend/tests/test_context_anatomy.py`)
    - `test_false_move_against_context_in_normal_ranges`
    - `test_manipulation_objective_and_reached_at`
    - `test_slots_per_frame` — D1 by H4, H4 by H1, H1 by M15, W1 by weekday, MN1 by week; across DST.
    - `test_active_slot_above_even_share`
    - `test_windows_table_versioned_and_recorded`
  - **279b. GREEN**
    - `context/anatomy.py` and `windows.py`.
    - AlgoResearch's `profile` command extended to every frame, writing `config/context/windows/exness-standard-<version>.toml` from the exploration slice.
  - **279c. REFACTOR**
  - **Validates: Requirements 5.1–5.3**

- [ ] 280. Checkpoint: legacy parity
  - **Suite:** the full suite is green apart from the task-39 RED tests.
  - **Property 5:** `legacy` reproduces every `SignalRecord` on the backtester fixtures and the golden journal's rows.
  - **Speed:** `ContextEngine` state building timed per mode on the fixtures.
  - **Live:** nothing live changes yet; the paper trader keeps `legacy`.

### C. Research before trading

- [ ] 281. Context features and any-frame labels in AlgoResearch
  - **281a. RED** (`backend/tests/test_research_context.py`)
    - `test_context_columns_per_mode` — `ctx_<mode>_own`, `_context`, `_case`, `_zone`, `_poi_reached_at`, `_draw`, `_draw_taken_at`, `_manip_reached_at`.
    - `test_features_equal_engine_chain_at_sampled_times` (engine parity)
    - `test_ctx_draw_labels_any_frame` — hit after t within the bias candle, and when.
    - `test_anchor_level_ctx_draw`
    - Property 2: truncating after t leaves the row unchanged.
  - **281b. GREEN** — `algo_research/features/context.py`; `labels.py`; `events.py` (`level = "ctx_draw"`); `MARKET_SOURCES` gains `liquidity_engine/context/`.
  - **281c. REFACTOR** — time the build per mode; `scalp` (M1 grid) may need the build cached per month.
  - **Validates: Requirements 9.1, 9.2**

- [ ] 282. The user's journal **(user action: the data)**
  - **282a. RED** (`backend/tests/test_research_journal.py`, a synthetic export)
    - `test_import_maps_columns_and_keeps_the_rest_as_notes`
    - `test_new_york_times_and_units`
    - `test_score_day_cluster_intervals_by_mode_and_instrument`
    - `test_unmatched_records_listed`
    - `test_diff_agreement_per_frame_with_reasons`
    - `test_report_quotes_ids_not_notes_by_default`
    - Property 9: `calibrate` refuses confirmation-slice and hold-out records.
  - **282b. GREEN** — `algo_research/journal.py`; `config/research/journal.toml`; `.gitignore` gains `data/journal/` (C10); the commands `journal import`, `score`, `diff`, `calibrate`.
  - **282c. REFACTOR**
  - **282d. Your data.**
    - You export the journal from Notion (or the connector reads it once authorised in claude.ai → Settings → Connectors).
    - We write the column map together, import, score, and diff.
    - The diff report names the rules to revisit. Changes to CE-D2 to CE-D6 go through a spec update, before task 283's hypotheses are committed.
  - **Validates: Requirements 10.1–10.5**

- [ ] 283. Direction hypotheses H011–H014 **(user review)**
  - Drafts in `config/research/hypotheses/`, one per mode: the context draw is reached more often than on the `complement` days and than `stratified` objectives at the same distance and hour.
  - Explore each on the exploration slice; report the per-mode verdicts and sample sizes (`position` may be INSUFFICIENT, CE-D11).
  - You confirm each file's pass rules. The commit is the pre-registration, all four together. Then run each on the confirmation slice.
  - **Validates: Requirements 9.3**

### D. Trading the context

- [ ] 284. Selection
  - **284a. RED** (`backend/tests/test_context_selection.py`)
    - One test per rule, passing and failing: `CONTEXT_DIRECTION`, `CONTEXT_OBJECTIVE`, `CONTEXT_DRAW`, `CONTEXT_TIME`, `CANDLE_LIMIT`.
    - `test_first_failed_rule_is_the_reason`
    - `test_unarmed_reasons` — `CONTEXT_NEUTRAL`, `CONTEXT_DRAW_TAKEN`, `CONTEXT_NO_FALSE_MOVE`.
    - `test_each_rule_switchable`
    - Property 8 (Hypothesis over fixture windows and switch subsets).
  - **284b. GREEN** — `context/selection.py`, `context/engine.py`; `engine.analyze()` dispatches on the mode (C3); `NoTrade` reasons (C4).
  - **284c. REFACTOR**
  - **Validates: Requirements 6.1–6.5, 11.2**

- [ ] 285. Orders in context
  - **285a. RED** (`backend/tests/test_context_orders.py`)
    - `test_tp1_bias_draw_tp2_parent_draw`
    - `test_min_stop_spreads_default_two_in_context_modes`
    - `test_zero_risk_refused_in_every_mode` — the 2026-10-10 GBPUSD intent (stop = entry) is refused in `legacy` too.
    - `test_expiry_at_bias_candle_close` — SimBroker and paper broker honour the intent's `expires_at`.
    - `test_bias_candle_time_exit` — closed at that bar's close on the closing side, `exit_reason = TIME`.
  - **285b. GREEN** — `agent/order_intent.py` (C5); the SimBroker, the paper broker and `simulation.py` read `expires_at` and the time exit (C7).
  - **285c. REFACTOR**
  - **Validates: Requirements 7.1–7.4**

- [ ] 286. Modes in the backtester
  - **286a. RED** (`backend/tests/test_context_backtest.py`)
    - `test_context_tracker_recomputes_a_frame_only_on_its_close`
    - `test_unarmed_closes_counted_not_recorded`
    - Property 7: a gated run equals an ungated one on the fixtures.
    - `test_history_check_refuses_short_modes` (CE-D11)
    - `test_report_breakdowns` — by mode, case, rule removals, trades per bias candle; cost per trade and trades under 5 M1 bars for `mid` and `scalp`.
    - `test_chain_reasons_in_report`
  - **286b. GREEN** — `signals.py` (`ContextTracker`), `report.py`, `report_html.py`; `config/backtests/modes.toml` (one variant per mode, plus one ablation per selection rule).
  - **286c. REFACTOR** — Phase A speed per mode on the fixtures, gated against ungated.
  - **Validates: Requirements 8.1–8.4, 11.2**

- [ ] 287. Checkpoint
  - **Suite:** green apart from the task-39 RED tests.
  - **Parity:** Properties 5 and 7 hold.
  - **Fixture runs:** every mode runs end to end on the fixtures.
  - **Cost:** the Phase A time of each mode on the full study is estimated from the fixture timings.

- [ ] 288. Mode runs **(user action: Docker)**
  - Write each mode's pass mark into its run config, and commit the configs before any run (Requirement 12.1).
  - Run slowest first on study `baseline-2026q3`: `position`, `intraday`, `mid`, `scalp`. Run the selection-rule ablations for each mode that shows a positive mean.
  - Write `docs/backtests/CONTEXT_MODES.md`:
    - the pass-mark table per mode, against `legacy` and stage 1 (task 242);
    - each mode's direction verdict (task 283);
    - the breakdowns;
    - trades the user reviews in `report.html`.
  - The hold-out stays unused.
  - **Validates: Requirements 12.1, 12.3**

- [ ] 289. Decide the next step with the user **(user review)**
  - **If a mode passes:** the hold-out `--final` run for the modes you select (Requirement 12.2); then the live-parity update and an Exness demo forward test of that mode.
  - **If none passes:** use the journal diff (task 282) and the breakdowns to choose the next rule changes, as a spec update; the chain's reasons show where each losing trade's context went wrong.
  - **Validates: Requirements 12.2**

### E. Model A (update 2026-10-15)

Model A replaces the old selection (284) and orders (285) in the Model A modes. The plan builds what the record needs first, measures it, and reviews it with you before anything is traded. Order: 275 → 277 → 279 (the trader's windows) → 310 → 312 → 313 → 311 → your review → 314.

- [x] 310. The Model A reader (Requirement 13)
  - **310a. RED** (`backend/tests/test_context_model_a.py`, hand-built candle series)
    - `test_short_runs_framed_to_tp1` and `test_long_mirrors_it`
    - `test_no_manipulation_without_c1_high_into_poi`
    - One test per invalidation: `POI_FAILED`, `NO_REJECTION`, `NO_MANIPULATION`, `MISSED`, `RETRACE_INVALID`, `EXPIRED`.
    - `test_new_range_end_cisd_and_swing` (MA-D5)
    - `test_displacement_needs_body_and_fvg` (MA-D4)
    - `test_inducement_recorded_not_gating` (MA-D3)
    - `test_time_sync_recorded` (MA-D9)
    - `test_one_instance_per_direction` (MA-D10)
    - Properties 1, 2 and 10 (Hypothesis).
  - **310b. GREEN** — `context/model_a.py`, `context/measures.py`.
  - **310c. REFACTOR**
  - **Validates: Requirements 13.1–13.6**

- [ ] 312. The Model A record (Requirement 16) **(user review)**
  - **312a. RED** (`backend/tests/test_research_model_a.py`)
    - `test_funnel_counts_states_and_invalidations`
    - `test_outcome_rates_with_day_cluster_intervals`
    - `test_breakdowns_by_time_inducement_depth_and_variant`
    - `test_baselines_share_the_c_and_e_rules`
    - `test_random_poi_is_seeded`
    - Property 2 on the funnel's rows.
  - **312b. GREEN** — `algo_research/model_a.py`; the command `python -m algo_research model-a [--set model_d1] [--instrument XAUUSD]`; `docs/research/MODEL_A_RECORD.md`.
  - **312c. Your review.** Gold first, then the others. We read the funnel together, and the instances you'd label differently settle MA-D2 to MA-D11.
  - *Status 2026-10-15:* 312a and 312b are done. The report adds **the premise**: after C2 rejects, C1's opposite extreme before C2's extreme, against a coin flip from the same distances. It counts every rejected C2, not only the few fills. `--rerender` rebuilds the report from `data/research/model_a_instances.jsonl`. F's state is read from its last 600 candles (MA-D8). 312c, the review, is next.
  - *The record (2026-10-15):* 4 instruments × 7 frame sets, 908,469 instances. With the working defaults, Model A's premise doesn't beat its coin flip consistently: most cells sit within ±5% with intervals spanning zero. It doesn't beat CRT or random POIs either.
    - Three of 28 cells are positive: EURUSD H4/M30/M1 +6% [+1, +11], EURUSD D1/H4/M15 +17% [+4, +30] (n 35), GBPUSD D1/H1/M5 +8% [+1, +15]. With 28 cells, one or two would be expected by chance.
    - Fills are few, 2 to 74 per cell in six months.
    - The review decides whether the definitions miss the trader's selection.
  - **Validates: Requirements 16.1–16.5**

- [x] 313. Model A on the chart (Requirement 17)
  - The watch session runs both of the trader's sets over its window, both sides, on the snapshot's prices with 100 days of history (`WatchSession.model_a`). `model_a_at(set, t)` serves the live instance and those that reached the manipulation and ended within one F candle. Each level appears only once its state is reached: C2's extreme after C2's close; the order after the rejection and the displacement.
  - The Engine mode's **Model A** layer, on by default, with a set picker, draws:
    - F's 50%, the POI, C1's extremes and C2's;
    - the OTE band, the 0.705 entry, the stop and the SD levels, the fill;
    - a badge with the state.
    The panel shows each instance's state, reason, time window, inducement and levels. The log lists its state changes.
  - **RED:** `test_watch_session_keeps_model_a_instances`, and the walk-through (an instance drawn, its states logged, nothing after the clock).
  - **Validates: Requirements 17.1–17.3**

- [x] 315. Volatility and time in the reader (Requirement 18)
  - Added 2026-10-15 at the trader's request: "the mechanical aspect does not factor in the volatility aspect of the market".
  - `day_phase`, `EARLY` and `MODEL_A_VT` in `context/model_a.py`; the `Variant` fields `size_basis`, `phases`, `max_adr_used`, `max_size_adr` and `room`. Each instance records its phase, ADR, ADR used, size and TP1's reach.
  - The record's arms: Model A plain, + time, + volatility, + both, CRT and CRT + both, random POI + both. `--all-arms` adds the first record's variants. The breakdowns add the phase.
  - The Engine chart reads `MODEL_A_VT`, and its panel shows the phase and the ADR figures.
  - **RED:** `test_day_phase_labels`, `test_phase_gate_frames_only_in_its_phases`, `test_adr_and_its_gates`, `test_no_gate_without_enough_history`, `test_seasonal_sizes_read_the_same_hour_on_earlier_days`, `test_property_2_holds_with_volatility_and_time`. The record and watch tests pass with the new arms.
  - **Validates: Requirements 18.1-18.6**
  - *The record (2026-10-15b):* Volatility and time lifted most cells. Model A + time + volatility: XAUUSD D1/H1/M5 +16% [+1, +31], EURUSD H4/M30/M1 +10% [+1, +18], EURUSD H4/M15/M1 +8% [+2, +14]. Fills fell to 0–10 per cell.
  - *The oracle split (scratchpad `oracle_split.py`, hindsight on purpose):* Model A's rejected C2s were on the side the day went only 27–29% of the time, against 49% for CRT. On that side the premise beat its coin by +19% [+12, +26] (D1/H1/M5), +8% (H4/M30/M1) and +5% (H4/M15/M1); against it, −1% to −4%. The reader needs a thesis (task 316).

- [x] 316. A thesis first (Requirement 19)
  - Added 2026-10-15 at the trader's request ("yes" to giving the reader a thesis).
  - `ModelAReader(..., theses=)` and `Variant.thesis`: framing only on the thesis side; a thesis variant without theses is refused.
  - `algo_research/model_a.py`: `day_directions`, `daily_theses` (PROFILE from `CandleProfileAnalyzer` at each 17:00 open; PREV_DAY; ORACLE), `thesis_accuracy` with a day-bootstrap interval, `THESIS_ARMS`, and the report's "theses on their own" table. `--arms main,thesis,extra` picks the arms.
  - **RED:**
    - `test_reader_frames_only_on_the_thesis_side`;
    - `test_oracle_and_prev_day_theses`;
    - `test_profile_thesis_reads_only_the_past` (Property 2: cut an hour into a day, and every thesis up to that day is unchanged);
    - `test_thesis_accuracy_against_the_day`;
    - `test_the_record_scores_each_thesis`.
  - **Validates: Requirements 19.1-19.4**

- [ ] 311. Nesting (Requirement 15)
  - **RED:** `test_d1_ote_is_an_h4_poi_while_live`, `test_depth_two_inside_a_live_ote`, `test_extended_targets_from_the_higher_instance`.
  - **GREEN:** `context/nesting.py`; the funnel gains depth.
  - **Validates: Requirements 15.1–15.3**

- [ ] 314. Model A orders and the backtest modes (Requirement 14)
  - Starts after your review of 312. `engine.analyze` dispatches on the mode (C3). Order intents follow Requirement 14, and the modes go into `config/backtests/modes.toml`.
  - **RED:** `test_order_at_0705_stop_beyond_c2_high`, `test_tp1_c1_low_else_minus_one_sd`, `test_expiry_at_c3_close`, `test_horizon_close`, `test_legacy_cache_key_unchanged` (MA-D12).
  - **Validates: Requirements 14.1–14.3**

### Update 2026-10-23: the trader's trend

- [x] 355. The trend reader (Requirement 20)
  - **RED** — on hand-made candles:
    - lower highs and lower lows read bearish structure, their mirror bullish, a mix neither;
    - a down close with two of the last three down is a bearish close signal;
    - a sweep of a swing high closing back below it is bearish until a close above the sweep's wick;
    - a bullish FVG closed through and a bearish one respected read bearish arrays;
    - a down close opening low in its range with a wick above the open and closing near its low is a bearish PO3;
    - three signals in agreement name the trend;
    - no candle after the one labelled changes its label (Property 2).
  - **GREEN** — `algo_research/trend.py`: `trend_signals(bars, arrays)`.
  - **Done 2026-10-23.** `trend_signals` gives each closed candle structure, closes, liquidity, arrays and PO3, their
    score and the trend (MA-D18 to MA-D20). Arrays come from `algo_research.atlas.arrays` and count once per candle
    over 20 candles. 7 tests in `test_research_trend.py`, including that no later candle changes a label.
  - **Validates: Requirements 20.1–20.3**

- [x] 356. The trend before anything is built on it (Requirement 21) **(user review)**
  - The exploration slice; the focus markets; H1, H4 and D1. The hit rate of the trend, and of each signal, in the one-range race against 50% and each side's drift rate, with intervals, per frame and market.
  - Written to `docs/research/TRADER_TREND.md`.
  - **Done 2026-10-23** (`python -m algo_research.trend_study`). It **does not clear the bar.**
    - **The next move:** H1 50.1% (−0.1 points over drift), H4 49.1%. Each signal is within a point or two of 50%.
    - **Continuation,** added because a bearish trend often raids buy-side liquidity first (a lower low before a
      higher high): H1 61.5% against a geometry of 61.6%; H4 −2.5 points. The read fires near the last swing on its
      side, so it is right as often as a driftless walk from the same price.
    - **D1 is contrarian:** the trend −11 points, PO3 −13. Mostly the indices in April 2025.
    - As Requirement 21.3 says, nothing is tuned and the setup (358) is not built on it. The result went back to the
      trader. They chose (2026-10-23) to see the reader on the chart and call the trend blind (357), to test whether
      their own calls carry what these counts don't.
  - **Validates: Requirements 21.1–21.3**

- [x] 357. The trend on the chart (Requirement 23)
  - A Noculus layer: a chosen frame's trend and five signals per closed candle, up to the replay clock.
  - Added 2026-10-23 at the trader's request ("please do, this could be an additional filter"): their own trend
    calls, blind, scored the way 356 scored the reader.
  - **Done 2026-10-23.**
    - **The layer:** `WatchSession.trend` reads H1, H4 or D1 from the snapshot with its warm-up (10, 30 or 90 days),
      FVGs and order blocks from `algo_research.atlas.arrays`. Each closed candle up to the clock is served, and
      nothing while the session is blind. The page draws a strip along the chart's foot (Trend, with `trend: H1/H4/D1`)
      and spells out the last candle's five signals.
    - **The calls:** `trend_call` keeps a call (frame, bearish, bullish or unclear, a note) in the session's journal,
      with `engine_seen`. `trend_calls` scores each one from the minutes before the clock (`call_outcome`): the next
      move, and continuation beside geometry. The reader's call at the same candle is set beside it once in sight, and
      the blind calls are totalled. The Noculus panel gains "Your trend call".
    - 9 tests in `test_research_trend.py` (2 new) and 2 in `test_backtest_noculus.py`; the journal key test updated.
      Checked end to end on GBPUSD, 27 January 2025.
  - **Validates: Requirement 23.1**

- [ ] 358. The continuation setup (Requirement 22) — after 356 and the trader's answers to 22.3
  - **Validates: Requirements 22.1–22.3**

### Update 2026-10-23b: ranked swings and breaks

- [x] 359. Ranked swings and breaks, measured (Requirement 24) **(user review)**
  - **RED** — on hand-made candles:
    - an ITH is an STH higher than the STH on either side, known once the next STH is;
    - a wick through a swing that closes back inside is a sweep, and a close beyond it is the break;
    - with the FVG rule, the break waits for C3;
    - STH compare equals task 355's structure.
  - **GREEN** — `algo_research/trend.py`: `ranked_highs`, `ranked_lows`, `compare_state`, `break_state`.
  - **The study:** `python -m algo_research.structure_study` → `docs/research/TREND_STRUCTURE.md`.
  - **Done 2026-10-23.** 3 tests (12 in `test_research_trend.py`).
    - **Every version calls the next D1 candle 48-52% on both slices,** within ±3 points of drift: STH and ITH
      compare, STH and ITH breaks, the ITH break with an FVG, read on D1 or on the H4 at 17:00. The confirmation slice
      has 1,700-2,725 calls a version.
    - **Swapped into the trend score,** 44-50%.
    - None beats the earlier 45-49% by more than noise, or comes near 56-61%. As the plan's own test says, structure is
      for levels (the protected and the weak swing, and a break at a higher-frame level), not for the day's direction.
  - **Validates: Requirements 24.1–24.3**

### Update 2026-10-23c: the entry

- [x] 363. Model A's entry against the trader's two (Requirement 25) **(user review)**
  - `algo_research/entry_study.py` → `docs/research/MODEL_A_ENTRIES.md`. It reproduces the gold case: on 29 January B1, B2 and C each make 3R, and A has no fill.
  - **Done 2026-10-23** (the record: 446,720 setups, the exploration slice, 4 markets).
    - **The trader's entries fill far more often:**
      - at the level 1,825-8,677 times a cell;
      - the retest 46-978;
      - Model A's OTE 29-155 on the model arms.
    - **They lose like the rest:** at the level −0.11 to −0.20R a trade (3R target); at the midpoint −0.18 to −0.32R; the retest −0.06 to −0.29R; the OTE −0.02 to −0.22R (few fills, wide intervals).
    - **The POI adds nothing:** the same entries on random POIs did as well or better (at the level −0.07 to −0.10R), as did CRT with no context (the retest −0.07 to −0.13R). The time and volatility gates don't help either.
    - So fixing the entry would stop the misses, but it adds trades that lose on average. On 29 January the three entries won because the day fell (the FOMC drop), not because of the entry. As 25.2 says, nothing goes to Model A's orders.
  - **Validates: Requirements 25.1–25.2**

### Update 2026-10-24: C1 once C2 has run it

- [x] 364. The Model A layer draws a C1 once C2 has run it (Requirement 26)
  - `engine.js`: `maSwept` / `maShown`; the chart, the card and the log show MANIPULATED instances; the layer "Model A: unswept C1s" (off by default) shows the rest.
  - **Done 2026-10-24.** Three checks in `js/live_probe.txt` (live_ui.js: 22 ok). The page only: the reader and the engine are unchanged, so no cache is touched; a reload shows it.
  - **Validates: Requirements 26.1–26.2**

### Update 2026-10-24: the chain, tested whole

The trader's order: 277 → 278 → 365 → 366 (the pass rule confirmed before it runs) → 367. Tasks 275 and 276 stay open:
- The research doesn't need the engine's modes.
- The quarantine needs M1 bars, which the 2018-2021 history doesn't have. The 17:00 New York rollover falls inside the broker's server-day bars, so its dips can still set an FX day's low. The search's other D1 hypotheses read the same raw bars, so H-K is judged on the same footing. Its pass rule reads opens and closes only.

- [x] 365. The IPDA data ranges (Requirement 27)
  - **RED:** `test_ranges_are_the_20_40_60_day_extremes`, `test_a_candle_leading_two_ranges_is_listed_once`, `test_no_range_without_its_candles`, `test_ranges_feed_the_chain_as_objectives`.
  - **GREEN:** `context/ipda.py`: `ipda_ranges(d1)`.
  - **Done 2026-10-24.** 4 tests. Each range comes out as an `Objective` (`IPDA20_HIGH` ... `IPDA60_LOW`), formed at its candle's close. They pass through the frame state's taken check like any other level.
  - **Validates: Requirements 27.1–27.3**

- [x] 366. The chain's daily calls, measured (Requirement 28) **(user review: the pass rule)**
  - **Done 2026-10-24: H-K fails.** Registered at 8901bfe with the trader's pass rule (the daily calls'). On development (2018-07 to 2022), 8,888 calls hit 49.2% against a base of 49.0%: +0.2 points [−1.1, +1.5], positive in 3 of 9 markets.
    - Every ablation sits within ±1.5 points of drift, as does each frame alone. Without the IPDA ranges it is +0.9 [−0.5, +2.3], 8 of 9 markets: a lead from development data only.
    - The draw comes first as often as geometry once the bars that reached both levels are split.
    - Written up in `docs/research/SEARCH_2018_2024.md`. Tries 11, passes 0; 2023-2024 still unread.
  - **RED** (synthetic bars only, nothing read from the snapshot): `test_weeks_and_months_close_on_the_calendar`, `test_forming_week_stretches_the_range`, `test_call_reads_only_the_past` (Property 2), `test_no_call_until_every_frame_has_a_range`, `test_draw_race_against_geometry`.
  - **GREEN:** `algo_research/search_chain.py`; H-K appended to `docs/research/SEARCH_2018_2024.md`.
  - **The trader confirms H-K's pass rule.** The commit is the registration. Then one development run; the log records it, pass or fail.
  - *Status 2026-10-24:* the harness is built and committed before any data was read. `Ladder` builds the frames from D1 bars; `chain_rows` reads every arm at every close; `draw_race` and `judge_race` handle the companion; `run` judges with `search_calls.judge_calls`. 6 tests on synthetic bars, Property 2 included. About 47 s per market for the development window. The registration is next.
  - **Validates: Requirements 28.1–28.4**

- [x] 367. SMT and the dollar index (Requirement 29) — after 366 has reported
  - **Done 2026-10-24: H-L fails.** Registered at e791bef. On development, 1,957 calls hit 48.1% against a base of 49.0%: −0.9 points [−3.8, +1.9], 2 of 7 markets.
    - SMT with no gate is +0.4, and the gate lowers it: it passes 82% of SMT legs, so it selects little.
    - Where SMT agrees with H-K: −1.8.
    - The leg that took its level is −1.2; the leg that held is −0.2.
    - Tries 12, passes 0; 2023-2024 still unread.
  - **The trader's definition (2026-10-24):**
    - SMT on the previous day's high and low.
    - It is confluence only: a leg of the divergence is called only when its own day is at a major array. That means an unfilled D1 order block or breaker, a major pool taken (the previous week's extreme, an untaken D1 swing, the 20-day extreme), or the outer 25% of the W1 dealing range.
    - D1 arrays only: the broker has no H4 before July 2021.
    - The pass rule is the daily calls', over the 7 paired markets (need 5).
  - **The harness, before any data was read:** `algo_research/search_smt.py` (`market_days`, `smt_legs`, `arm_calls`). 7 tests on synthetic bars, Property 2 included.
  - **Validates: Requirements 29.1–29.2**

- [x] 368. The chain and the stack on the chart (Requirement 30)
  - **Done 2026-10-24.**
    - `algo_research/chain_view.py` (`ChainView`, `trading_days`): what H-K and H-M read at a D1 close, ready for the page.
    - `WatchSession.chain` and `/api/watch/chain`, withheld while blind. The chain is rebuilt once per trading day, from 550 days of warm-up.
    - The page's "Chain & stack" layer (`engine.js`: `paintChain`, `chainCard`, `loadChain`), on by default.
  - **Tests:** `test_research_chain_view.py` (4, parity with `stack_votes`); `test_the_chain_layer_is_withheld_while_blind_and_served_up_to_the_clock`; `js/chain_ui.js` (15 checks).
  - **Limit:** the watch tool's days are the exploration slice (2025-01 to 2025-06), and the snapshot's M1 starts in 2024-05. The MN1 frame is unranged until about May 2025, so the stack makes no calls before then.
  - **Validates: Requirements 30.1–30.3**

- [x] 371. H-N on the chart (Requirement 31)
  - **Done 2026-10-27.**
    - `search_crt.session_trades` (M15 built from the session's M1) and `race(legs=True)`; `WatchSession.crt` and `/api/watch/crt`. The trades are cached per M1 length, in wall seconds.
    - The page's "CRT (H-N)" layer (`engine.js`: `paintCrt`, `crtCard`, `loadCrt`), with a target menu (3R, 4R + partial, 5R + partial), on by default.
  - **Parity:** the refactored search gives EURUSD's 9,413 development trades unchanged. On a week of M1 (7-11 March 2022), `session_trades` gives the same 109 trades and results as `trades`.
  - **Tests:** `test_the_crt_layer_is_withheld_while_blind_and_shows_only_what_the_clock_has_seen`; the 7 tests of `test_research_search_crt.py`. `noculus_ui.js` still fails, as it has since task 357.
  - **Validates: Requirements 31.1–31.3**

- [x] 372. H-O's filter on the chart (Requirement 31.4)
  - **Done 2026-10-27.** `WatchSession.crt` tags each trade through `search_crt_context.Context` (a month of the session's M1): its pools, gaps, H4 trend and H-O's keep. The page has a second menu ("CRT trades: every one / at a gap (FVG) / H-O filter"), labels each C2 with its pools and gaps, and the card totals what is shown.
  - **US100, 21-25 April 2025, at 5R + partial:**
    - every CRT: 118 trades, −19.4R;
    - at a gap: 35 trades, +10.1R;
    - H-O: 22 trades, +12.1R.

    Up to Monday 09:00, the 18 CRTs (11 of them longs into the fall) keep 3, all shorts at H1 gaps with the H4 trend down. One week only: on development H-O is −0.17R a trade.
  - **Tests:** the session test checks the tags and the keep rule; `test_research_search_crt_context.py` (3).
  - **Validates: Requirement 31.4**

- [x] 378. The weekly context book and the end of a context (Requirement 32.1-32.3)
  - **378a. RED** — on hand-made calls and candles:
    - a call's week opens on the Sunday 17:00 New York before its trading dates;
    - a weekend time belongs to the next week;
    - a bullish call needs its protected swing below its draw, a bearish one above;
    - a call after its week's open is marked late, and its `since` is its own time;
    - the thesis file holds one entry per trading date of every called week, with NONE left out;
    - under `THESIS`, an entry with a draw refuses `THESIS_DELIVERED` once an H1 or entry candle since `since` reached the draw, and `THESIS_INVALIDATED` once a D1 candle closed beyond the protected swing;
    - a wick beyond the protected swing doesn't end it;
    - a plain side entry behaves as before.
  - **378b. GREEN** — `agent/context_calls.py` (`week_monday`, `week_open`, `Call`, `ContextBook`, `thesis_table`); `order_intent` reads either kind of entry.
  - Editing `agent/order_intent.py` changes `ENGINE_SOURCES`, so Phase A recomputes on the next backtest.
  - **Done 2026-10-29.**
    - Tests: `test_context_calls.py` (4) and, in `test_backtest_order_intent.py`, `test_a_weekly_context_trades_its_side_until_its_draw_trades` and `test_a_weekly_context_ends_at_a_d1_close_beyond_its_protected_swing_not_a_wick`.
    - Delivery reads the closed H1 and entry candles opened since `since`. The H1 candle holding `since` is left out, so a touch earlier in that hour doesn't count.
  - **Validates: Requirement 32.1-32.3**

- [x] 379. The context page on Noculus (Requirement 32.4)
  - `/context`: the week, the nine markets, their last prices from the terminal when connected, and each call's form. `GET /api/context`, `POST /api/context/call`. Saving rewrites the thesis file.
  - **Done 2026-10-29.**
    - `algo_research/replay/context.py` (`ContextApp`, `default_week`, `MARKETS`), with `static/context.html` and `context.js`; the shell links to the page.
    - The form checks the levels against each other (an error blocks the save) and against the last price (a warning). It also shows a random walk's chance of reaching the draw first from there.
    - Test: `test_the_context_page_keeps_a_call_per_market_and_week_and_writes_the_thesis_file`.
  - **Validates: Requirement 32.4**

- [x] 380. The context variant and its paper agent (Requirement 32.5)
  - `[variants.fresh_near_gap_context]`: `fresh_near_gap_partial` with `bias_mode = "THESIS"`, `thesis_file = "data/research/theses/context_theses.json"` and `min_stop_spreads = 10`.
  - A paper agent on the control agents' eight markets: `data/paper_trades_fresh_near_gap_context.json`.
  - **Done 2026-10-29.**
    - Test: `test_the_context_variant_trades_only_inside_the_calls`. It differs from the partial strategy only in the three settings.
    - The thesis file starts empty (`{}`), so the agent orders nothing until the first calls.
    - Its agent started 2026-10-29 beside the two controls; DXY is called and scored but not traded, as in the controls.
  - **Validates: Requirement 32.5**

- [x] 381. The weekly scorecard (Requirement 32.6)
  - `GET /api/context/scorecard` and the page's table: each called week and market, scored on the terminal's bars and the paper agents' records.
  - **Done 2026-10-29.**
    - `agent.context_calls.score_call` scores a call on its week's M15 bars from the terminal: its open and close, whether it closed on the call's side, the context's first end and a random walk's odds from `since`.
    - `paper_r` gives each paper agent's R in that market and week. `ContextApp.scorecard` totals the finished calls' hit rate against `BREAK_EVEN` (57-60%).
    - Tests: `test_a_call_is_scored_on_its_weeks_close_and_its_contexts_first_end` and `test_the_scorecard_sets_the_context_agent_against_the_controls`.
    - The order-intent context tests write a thesis file per entry. The reader caches by modification time and size, which two quick same-size writes can share.
  - **Validates: Requirement 32.6**

---

## Task Dependency Graph

Dependencies are denoted as `prerequisite → dependent`. Liquidity-engine task 242 (stage 1) runs any time before 288; its result is the bar the modes must beat.

```json
{
  "waves": [
    {
      "name": "Foundations",
      "tasks": ["275", "276"],
      "description": "Ladders and modes; the rollover quarantine"
    },
    {
      "name": "Context model",
      "tasks": ["277", "278", "279"],
      "description": "Frame state, the chain, time in every frame",
      "dependencies": ["Foundations"]
    },
    {
      "name": "Checkpoint A",
      "tasks": ["280"],
      "description": "Legacy parity and the full suite",
      "dependencies": ["Context model"]
    },
    {
      "name": "Research",
      "tasks": ["281", "282"],
      "description": "Context features and labels; the user's journal (needs the export)",
      "dependencies": ["Checkpoint A"]
    },
    {
      "name": "Direction hypotheses",
      "tasks": ["283"],
      "description": "H011-H014 explored, reviewed, pre-registered and run",
      "dependencies": ["Research"]
    },
    {
      "name": "Trading the context",
      "tasks": ["284", "285", "286"],
      "description": "Selection, orders, modes in the backtester",
      "dependencies": ["Direction hypotheses"]
    },
    {
      "name": "Checkpoint B",
      "tasks": ["287"],
      "description": "Parity, fixture runs, cost estimates",
      "dependencies": ["Trading the context"]
    },
    {
      "name": "Model A",
      "tasks": ["310", "312", "313", "315", "316", "311", "314"],
      "description": "Model A: the reader, its measured record (your review), the chart, nesting, then orders (update 2026-10-15)",
      "dependencies": ["Context model"]
    },
    {
      "name": "Runs and decision",
      "tasks": ["288", "289"],
      "description": "Mode runs slowest first, then the decision with the user",
      "dependencies": ["Checkpoint B"]
    }
  ]
}
```

---

## Notes

- Every implementation task follows RED → GREEN → REFACTOR. No production code without a failing test first.
- Hypothesis property tests run with `@settings(max_examples=100)` at least; the slow ones are marked `slow` and run at checkpoints.
- `legacy` must never move: any change that breaks Property 5 is a bug in the change, not in the test.
- `liquidity_engine/` keeps zero I/O during `analyze()` (liquidity-engine Requirement 14.1). The windows table is read by the caller and passed in.
- No new dependencies.
- The user's journal stays local (CE-D12). Nothing from it is committed unless the user says so.
