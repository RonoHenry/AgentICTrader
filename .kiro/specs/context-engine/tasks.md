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
    - `test_modes_ship_with_their_ladders` — the four modes of CE-D1, bias frame and execution.
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

- [ ] 277. Frame state
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

- [ ] 278. The context chain
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
