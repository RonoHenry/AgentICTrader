# Implementation Plan

**spec**: AlgoBacktester

## Overview

Build order for `requirements.md` and `design.md` (decisions D1–D8 at their defaults).
- **Numbering:** tasks continue the platform sequence from **181**.
- **TDD:** every code task follows the **RED → GREEN → REFACTOR** cycle in `.kiro/steering/tdd-and-testing.md`.
- **Tests:** they live in `backend/tests/test_backtest_*.py`, fixtures under `backend/tests/fixtures/backtester/`.
- **Properties:** "Property N" refers to `design.md` → Correctness Properties, tested with `hypothesis`.

The plan runs in four groups:
- **A. Shared foundations (181–196)** changes live code first (L1–L6 in the design), so the backtester is built on the modules live trading uses. Task 196 restarts the paper forward test on the shared fill model, which starts the clock on the parity data needed by task 212.
- **B. Backtester core (197–204).**
- **C. Reporting and CLI (205–208).**
- **D. Validation and first results (209–213).** The deliverable is task 211: a measured baseline of today's grader. Every later grader change must beat it.

Tasks marked **(user action)** need your MT5 terminal or a decision from you.

---

## Tasks

### A. Shared foundations

- [x] 181. Spike: measure `LiquidityMappingEngine.analyze()` cost
  - Build realistic windows (`_CANDLE_COUNT`, entry M15 and M5) for EURUSD and BTCUSDT from the candle store.
  - Time 200 calls each; record p50/p95 per call and the projected Phase A time per instrument-year.
  - Record the numbers in `design.md` under a "Measured performance" note. If one instrument-year at M5 takes more than 30 minutes, profile `analyze()` before task 199 and add an optimisation task here.
  - No production code. This sizes Phase A and the cache.
  - **Done 2026-10-05.** The candle store was offline (Docker not running), so the windows were fetched with the live runner's own helpers: Binance public klines and the local MT5 terminal.
    - M15 runs at about 50 ms per call, practical as-is.
    - M5 BTCUSDT runs at 225 ms per call, about 6.6 h per instrument-year, which is over the threshold. The profile found a quadratic ATR recomputation and pairwise BPR detection.
    - Results are in `design.md` → Measured performance. Task 214 added.

- [ ] 214. Remove `analyze()` hot spots without changing outputs (added by task 181)
  - Numbered 214 so tasks 182–213 keep their numbers. Not blocking the M15 baseline (task 211). Required before M5 studies longer than a few weeks.
  - **214a. RED**
    - Add `scripts/export_engine_windows.py` and capture the benchmark windows (BTCUSDT M5, BTCUSDT M15, EURUSD M15, EURUSD M5), plus today's `analyze()` output for each, to `backend/tests/fixtures/backtester/engine_windows/`.
    - `test_engine_output_unchanged_on_fixture_windows` (`backend/tests/test_liquidity_engine_perf.py`) — `LiquidityMap.model_dump_json()` is byte-identical to the captured output, including list order.
    - `test_atr_series_matches_per_candle_calculate_atr` — the new precomputed series equals `calculate_atr()` at every index.
    - `test_calculate_atr_called_at_most_once_per_timeframe` — a call-count spy. Call counts are a deterministic stand-in for timing assertions, which flake.
  - **214b. GREEN**
    - Precompute the ATR series once per timeframe in `PDArrayDetector`.
    - Replace pairwise BPR overlap with a sort-and-sweep that emits the same arrays in the same order.
    - Re-profile, and address `structure.py` only if it is still above 20%.
  - **214c. REFACTOR** — rerun the task 181 benchmark and add the new numbers to `design.md` → Measured performance. The full liquidity-engine test suite is still GREEN.
  - **Validates: Requirements 1.1, 7.5**

- [x] 182. `InstrumentSpec` and spec loading (`agent/instruments.py`, `config/instruments/*.toml`)
  - **182a. RED** (`backend/tests/test_backtest_instruments.py`)
    - `test_money_per_price_unit_usd_quote` — EURUSD: equals `contract_size`
    - `test_money_per_price_unit_usd_base` — USDJPY: equals `contract_size / price`
    - `test_money_per_price_unit_cross_uses_conversion` — EURGBP: multiplied by the GBPUSD rate
    - `test_cross_without_conversion_raises`
    - `test_load_specs_from_toml_round_trip`
    - `test_commission_spec_per_lot_and_rate_variants`
    - `test_unknown_instrument_raises_with_available_list`
  - **182b. GREEN** — frozen dataclasses and the TOML loader (`tomllib`).
  - **182c. REFACTOR** — confirm GREEN.
  - **Validates: Requirements 5.2, 6.1**

- [ ] 183. `scripts/export_instrument_specs.py`: MT5 specs and commission (D2)
  - **183a. RED** (`backend/tests/test_backtest_export_specs.py`; mock `MetaTrader5` the same way `test_mt5_broker_adapter.py` does)
    - `test_maps_symbol_info_fields` — point, tick size, contract size, volume min/step/max, currencies
    - `test_commission_per_lot_per_side_from_deal_history` — `abs(deal.commission) / deal.volume`, median over recent deals
    - `test_no_deals_for_symbol_requires_manual_value` — writes a placeholder and exits non-zero naming the symbol
    - `test_default_spread_from_recent_bars_median`
  - **183b. GREEN** — the script writes `config/instruments/mt5.toml`. Hand-write `config/instruments/binance.toml`: fee 0.001 per side, a default spread per symbol, stop slippage 0.0005 (D3).
  - **183c. (user action)** — run the script against your terminal; review and commit `mt5.toml`.
  - **Validates: Requirements 5.1, 5.2**

- [ ] 184. `VenueCalendar` (`services/market_data/venue_calendar.py`)
  - **184a. RED** (`backend/tests/test_backtest_venue_calendar.py`)
    - `test_mt5_d1_starts_17_00_new_york_in_winter_and_summer`
    - `test_mt5_intraday_bars_nest_in_d1` — H3/H4/H6/H8/H12 boundaries align to server midnight
    - `test_mt5_w1_starts_server_sunday`
    - `test_mt5_boundaries_across_dst_change_days` — US spring-forward and fall-back weeks
    - `test_binance_d1_utc_midnight_w1_monday`
    - `test_period_end_equals_next_period_start`
  - **184b. GREEN** — `Mt5Calendar(MT5ServerClock)`, `BinanceCalendar`.
  - **184c. REFACTOR** — confirm GREEN.
  - **Validates: Requirements 3.3**

- [ ] 185. `aggregate()` (`services/market_data/as_of_view.py`)
  - **185a. RED** (`backend/tests/test_backtest_aggregation.py`)
    - `test_aggregate_ohlcv_values` — open = first, high = max, low = min, close = last, volume = sum
    - `test_aggregate_skips_empty_periods` — weekend: no synthetic bars
    - `test_partial_trailing_period_not_emitted` — only closed periods
    - **PBT — Property 3: Aggregation Consistency** (`@given` random-walk M1)
      - **Validates: Requirements 3.3**
  - **185b. GREEN** / **185c. REFACTOR**

- [ ] 186. Aggregation parity against native venue bars
  - **186a.** `scripts/export_aggregation_fixture.py` exports one week of M1 plus native H1/H4/D1/W1 for EURUSD and XAUUSD (MT5) and BTCUSDT (Binance) to `backend/tests/fixtures/backtester/aggregation/`. **(user action** for the MT5 part.)
  - **186b. RED** (`backend/tests/test_backtest_aggregation_parity.py`)
    - `test_aggregated_bars_match_native_within_one_tick` — parametrised per venue, instrument and TF
  - **186c. GREEN** — fix calendar boundaries until it passes. Never loosen the tolerance.
  - **Validates: Requirements 3.4**

- [ ] 187. MT5 history loader stores spread (L6)
  - **187a. RED** (extend the existing loader tests)
    - `test_spread_points_converted_to_price_units` — `rates["spread"] × symbol point`
    - `test_spread_written_to_candles_spread_column`
  - **187b. GREEN** — `scripts/load_historical_data_mt5.py`.
  - **187c. REFACTOR** — confirm the existing loader tests are still GREEN.
  - **Validates: Requirements 3.5**

- [ ] 188. `StrategyConfig` (`agent/strategy_config.py`, part of L1)
  - **188a. RED** (`backend/tests/test_backtest_strategy_config.py`)
    - `test_defaults_equal_current_runner_constants` — pins today's `_CANDLE_COUNT`, `_GRADE_TO_CONFIDENCE`, min R:R 3.0, TP levels 2.5/4.0, context TFs
    - `test_pending_expiry_default_killzone_end_with_3h_fallback`
    - `test_fingerprint_stable_and_changes_on_any_field`
    - `test_frozen`
  - **188b. GREEN** / **188c. REFACTOR**
  - **Validates: Requirements 1.6**

- [ ] 189. `SetupGradeDetail.entry_array_id` and deterministic `setup_id` (L2)
  - **189a. RED** (`backend/tests/test_liquidity_grader.py`, `backend/tests/test_backtest_order_intent.py`)
    - `test_grade_detail_carries_selected_entry_array_id`
    - `test_entry_array_id_none_without_entry_array`
    - `test_setup_id_stable_for_same_array_across_consecutive_bars`
    - `test_setup_id_differs_for_different_arrays_or_entry_tf`
  - **189b. GREEN** — additive model field. The grader sets it.
  - **189c. REFACTOR** — the full liquidity-engine test suite is still GREEN.
  - **Validates: Requirements 1.3**

- [ ] 190. `build_order_intent()` extraction and runner refactor (L1)
  - **190a. RED** (`backend/tests/test_backtest_order_intent.py`)
    - `test_no_grade_returns_no_trade_no_grade`
    - `test_no_trade_grade_returns_no_trade`
    - `test_rr_below_min_returns_rr_below_min`
    - `test_direction_from_stop_vs_entry`
    - `test_sd_target_used_when_on_correct_side_else_draw_on_liquidity`
    - `test_confidence_from_grade_mapping`
    - `test_to_message_matches_runner_message_minus_candles` — same keys and values the runner built before the refactor, captured on a fixture view
    - `test_runner_delegates_to_build_order_intent`
  - **190b. GREEN** — move `_process_instrument` lines 447–509 and `_pick_sd_targets`. The runner calls the module.
  - **190c. REFACTOR** — remove the moved constants from the runner; confirm GREEN.
  - **Validates: Requirements 1.2, 1.3**

- [ ] 191. `compose_as_of_view()`
  - **191a. RED** (`backend/tests/test_backtest_as_of_view.py`)
    - `test_entry_tf_and_below_closed_bars_only`
    - `test_htf_window_has_one_in_progress_bar_from_m1`
    - `test_no_in_progress_bar_before_first_m1_of_period`
    - `test_window_sizes_match_strategy_config`
    - `test_pure_no_clock_no_io` — same inputs give the same output
    - **PBT — Property 2: As-of View Contains Only Known Data**
      - **Validates: Requirements 2.1, 2.2, 2.3**
  - **191b. GREEN** / **191c. REFACTOR**
  - **Validates: Requirements 2.4**

- [ ] 192. Live runner builds its window with `compose_as_of_view()` (L3, D5)
  - **192a. RED** (`backend/tests/test_backtest_runner_view.py`; fake fetchers, no MT5/Binance)
    - `test_forming_entry_bar_dropped`
    - `test_m1_fetched_to_cover_current_w1_period`
    - `test_htf_in_progress_bar_composed_from_m1`
    - `test_evaluation_timestamp_is_last_entry_bar_close`
  - **192b. GREEN** — `scripts/run_live_agent.py` fetch path for MT5 and Binance.
  - **192c. REFACTOR** — confirm GREEN.
  - **Validates: Requirements 2.7**

- [ ] 193. Clock injection (L5)
  - **193a. RED** (`backend/tests/test_agent_graph.py`, `test_agent_nodes.py`, `test_agent_decisions_audit.py`)
    - `test_observe_node_staleness_uses_injected_now` — detected 30s before the clock is fresh; 61s is stale
    - `test_agent_graph_passes_clock_to_nodes`
    - `test_learn_and_audit_timestamps_from_clock`
    - `test_default_clock_is_wall_clock` — existing behaviour unchanged
  - **193b. GREEN** — optional `clock` / `now` parameters with wall-clock defaults.
  - **193c. REFACTOR** — confirm GREEN.
  - **Validates: Requirements 2.5**

- [ ] 194. `FillModel` and `KILLZONE_END` expiry (`agent/brokers/fill_model.py`)
  - **194a. RED** (`backend/tests/test_backtest_fill_model.py`, hand-built bars)
    - Market: `test_market_long_fills_next_open_at_ask`, `test_market_short_fills_next_open_at_bid`
    - Limit: `test_limit_long_touch_does_not_fill`, `test_limit_long_trades_through_fills_at_entry`, `test_limit_short_mirror`
    - Stops: `test_long_stop_triggers_on_bid`, `test_short_stop_triggers_on_ask`, `test_gap_beyond_stop_fills_at_open`, `test_stop_slippage_applied`
    - Targets: `test_target_exit_no_slippage`, `test_same_bar_stop_and_target_is_stop`, `test_fill_bar_allows_stop_not_target`
    - Expiry: `test_expiry_killzone_end`, `test_expiry_fallback_ttl_outside_killzone`, `test_order_expiring_over_weekend_expires_on_first_bar_after_open`
    - Other: `test_bars_before_placement_ignored`, `test_mae_mfe_tracked_on_closing_side`
    - **PBT — Property 4: No Fill Before Placement or After Expiry**
      - **Validates: Requirements 4.3, 4.10**
    - **PBT — Property 5: Fills Are Never Better Than the Order's Levels**
      - **Validates: Requirements 4.4, 4.5, 4.6, 4.7, 4.8**
    - **PBT — Property 7: Loss Is Bounded by the Stop Unless Price Gapped**
      - **Validates: Requirements 4.6**
  - **194b. GREEN** / **194c. REFACTOR**
  - **Validates: Requirements 4.2, 4.9, 4.11, 4.12**

- [ ] 195. `PaperBrokerAdapter` on the shared `FillModel` (L4, D4)
  - **195a. RED** (`backend/tests/test_paper_broker.py`)
    - `test_paper_broker_uses_fill_model` — touch-only limit no longer fills; market fills at the next bar's open at the ask
    - `test_injected_clock_sets_placed_at`
    - `test_binance_bars_use_instrument_default_spread`
    - `test_fee_rate_maps_to_rate_per_side_commission`
    - `test_state_file_from_previous_version_still_loads`
    - Update only the existing assertions whose semantics change on purpose. Annotate each with "D4: stricter fill model".
  - **195b. GREEN** — `PaperBrokerAdapter` keeps its public API and report.
  - **195c. REFACTOR** — confirm GREEN.
  - **Validates: Requirements 4.1, 4.2**

- [ ] 196. Checkpoint: shared foundations live
  - `python scripts/run_all_tests.py` is green (apart from the task-39 RED file).
  - Rebuild and restart `docker/paper-trader`. **(user action** to confirm the restart.)
  - Record the restart date in this file. Only forward-test trades placed after it are valid parity data (task 212).

### B. Backtester core

- [ ] 197. `algo_backtester` scaffold and configuration
  - **197a. RED** (`backend/tests/test_backtest_config.py`)
    - `test_variant_dotted_key_override`
    - `test_unknown_config_key_rejected`
    - `test_study_holdout_defaults_to_last_3_months_and_persists`
    - `test_run_config_resolves_strategy_config`
  - **197b. GREEN** — `algo_backtester/config.py`, `config/backtests/base.toml`, and `data/backtests/` added to `.gitignore`.
  - **197c. REFACTOR** — confirm GREEN.
  - **Validates: Requirements 7.1, 7.2**

- [ ] 198. `CandleSource`, coverage check, data fingerprint (`algo_backtester/data.py`)
  - **198a. RED** (`backend/tests/test_backtest_data.py`, using `CsvSource` fixtures)
    - `test_weekend_gap_allowed_midweek_gap_refused`
    - `test_late_history_start_refused`
    - `test_allow_gaps_flag_permits_and_is_reported`
    - `test_fingerprint_changes_when_one_row_changes`
    - `test_warmup_falls_back_to_native_htf_and_reports_source`
    - `test_timescale_source_reads_m1_utc` — marked `infrastructure`
  - **198b. GREEN** / **198c. REFACTOR**
  - **Validates: Requirements 3.1, 3.2, 3.6, 3.7**

- [ ] 199. Phase A: `generate_signals()` (`algo_backtester/signals.py`)
  - **199a. RED** (`backend/tests/test_backtest_signals.py`, `test_backtest_truncation.py`)
    - `test_one_record_per_entry_tf_close`
    - `test_analyze_called_with_as_of_time`
    - `test_engine_exception_becomes_engine_error_record`
    - `test_parallel_per_instrument_equals_sequential`
    - **PBT — Property 1: No Look-Ahead (Truncation Invariance)** — fixture data, `max_examples=25`
      - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**
  - **199b. GREEN** / **199c. REFACTOR**
  - **Validates: Requirements 1.1, 9.2**

- [ ] 200. Phase A cache (`algo_backtester/cache.py`)
  - **200a. RED** (`backend/tests/test_backtest_cache.py`)
    - `test_key_changes_with_each_input`
    - `test_hit_returns_identical_records`
    - `test_corrupt_entry_recomputed`
    - `test_write_is_atomic`
    - `test_engine_source_edit_invalidates` — the engine code fingerprint changes when a `liquidity_engine` file changes
  - **200b. GREEN** / **200c. REFACTOR**
  - **Validates: Requirements 7.4**

- [ ] 201. `SimBroker` (`algo_backtester/sim_broker.py`)
  - **201a. RED** (`backend/tests/test_backtest_sim_broker.py`)
    - `test_limit_vs_market_selection_like_mt5_adapter`
    - `test_sizing_rounds_down_per_instrument_class` — USD quote, USD base, cross
    - `test_min_volume_over_risk_raises_and_execute_node_skips`
    - `test_missing_direction_or_stop_raises`
    - `test_sequential_order_ids`
    - `test_r_and_cost_split_accounting`
    - `test_cost_flag_above_fraction_of_risk`
    - **PBT — Property 6: Costs Only Subtract**
      - **Validates: Requirements 5.3**
    - **PBT — Property 8: Sizing Never Over-Risks**
      - **Validates: Requirements 6.1, 6.2**
  - **201b. GREEN** / **201c. REFACTOR**
  - **Validates: Requirements 5.1, 5.5**

- [ ] 202. `SimAccount` (`algo_backtester/account.py`)
  - **202a. RED** (`backend/tests/test_backtest_account.py`)
    - `test_daily_anchor_resets_17_00_new_york_winter_and_summer`
    - `test_weekly_anchor_resets_sunday_open`
    - `test_drawdown_includes_open_positions_marked_to_close`
    - `test_exposure_dict_drives_risk_engine_daily_limit` — `RiskEngine.validate()` rejects at 3%
    - `test_non_compounding_risk_amount_fixed`
  - **202b. GREEN** / **202c. REFACTOR**
  - **Validates: Requirements 1.4, 6.3, 6.4**

- [ ] 203. Phase B event loop (`algo_backtester/simulation.py`)
  - **203a. RED** (`backend/tests/test_backtest_simulation.py`; a two-instrument synthetic fixture with scripted SignalRecords)
    - `test_fills_processed_before_decisions_at_same_t`
    - `test_in_trade_signal_journaled_not_evaluated`
    - `test_setup_already_attempted_after_stop_out` (D6)
    - `test_concurrent_trade_limit_across_instruments`
    - `test_risk_rejection_journaled_with_reason`
    - `test_agent_graph_runs_with_ai_clients_disabled_and_sim_clock`
    - `test_order_not_eligible_on_bar_opening_before_t`
    - `test_same_t_processed_in_alphabetical_instrument_order`
    - **PBT — Property 9: Account State Matches Positions**
      - **Validates: Requirements 1.4, 1.5, 6.3**
  - **203b. GREEN** / **203c. REFACTOR**
  - **Validates: Requirements 1.1, 7.5**

- [ ] 204. Hold-out and walk-forward
  - **204a. RED** (`backend/tests/test_backtest_run_modes.py`)
    - `test_holdout_overlap_refused_without_final`
    - `test_final_flag_recorded_in_manifest`
    - `test_walk_forward_windows_and_warmup_before_window`
    - `test_walk_forward_combined_equals_concatenation`
  - **204b. GREEN** / **204c. REFACTOR**
  - **Validates: Requirements 7.2, 7.3**

### C. Reporting and CLI

- [ ] 205. Metrics (`algo_backtester/metrics.py`)
  - **205a. RED** (`backend/tests/test_backtest_metrics.py`, known trade lists)
    - `test_win_rate_expectancy_profit_factor`
    - `test_max_drawdown_r_and_pct_and_losing_streak`
    - `test_holding_time_and_cost_share`
    - `test_bootstrap_ci_deterministic_for_seed_and_contains_mean`
    - `test_insufficient_evidence_below_min_trades`
    - `test_breakdowns_by_instrument_grade_killzone_direction_month`
  - **205b. GREEN** / **205c. REFACTOR**
  - **Validates: Requirements 8.2, 8.3, 8.4**

- [ ] 206. Report writers (`algo_backtester/report.py`)
  - **206a. RED** (`backend/tests/test_backtest_report.py`)
    - `test_run_id_is_manifest_hash_excluding_created_at`
    - `test_manifest_records_git_engine_data_and_flags` — including `ai_modifiers` and `news_filter`
    - `test_journal_includes_skipped_intents_with_reason`
    - `test_journal_columns_order_and_fixed_precision`
    - `test_summary_md_marks_insufficient_buckets`
  - **206b. GREEN** / **206c. REFACTOR**
  - **Validates: Requirements 8.1, 8.6, 9.5**

- [ ] 207. Run comparison (`algo_backtester/compare.py`)
  - **207a. RED** (`backend/tests/test_backtest_compare.py`)
    - `test_side_by_side_summary`
    - `test_refuses_different_data_fingerprint_or_range`
  - **207b. GREEN** / **207c. REFACTOR**
  - **Validates: Requirements 8.5**

- [ ] 208. CLI: `python -m algo_backtester run | compare | check-data`
  - **208a. RED** (`backend/tests/test_backtest_cli.py`)
    - `test_check_data_nonzero_exit_on_coverage_failure`
    - `test_run_writes_outputs_to_run_dir`
    - `test_variant_and_final_flags_parsed`
  - **208b. GREEN** / **208c. REFACTOR**
  - **Validates: Requirements 7.1**

### D. Validation and first results

- [ ] 209. Golden run
  - **209a.** Build `backend/tests/fixtures/backtester/golden/`: two weeks of EURUSD M1 plus native HTF warm-up, exported by `scripts/export_aggregation_fixture.py`. **(user action** for the export.)
  - **209b. RED** (`backend/tests/test_backtest_golden.py`)
    - `test_golden_journal_matches_expected`
    - `test_second_run_byte_identical`
    - **PBT — Property 10: Determinism and Cache Transparency** — cache-hit run equals empty-cache run
      - **Validates: Requirements 7.4, 9.5**
  - **209c. GREEN** — commit the expected journal. Any later intended change updates it in the same commit.
  - **Validates: Requirements 9.4**

- [ ] 210. Checkpoint: backtester complete
  - `python scripts/run_all_tests.py` is green (apart from the task-39 RED file).
  - Add a "Backtesting" section to `README.md`: setup, `check-data`, `run`, `compare`, hold-out rules.

- [ ] 211. First baseline of the current grader **(user action)**
  - Set MT5 Tools → Options → Charts → "Max bars in chart" to Unlimited and restart the terminal.
  - Load M1 (with spread) plus native D1/W1 for EURUSD, GBPUSD, USDJPY and XAUUSD (D1) with `scripts/load_historical_data_mt5.py`.
  - Run `check-data`. Create the study, which locks the hold-out (D7). Run `config/backtests/base.toml`.
  - Write `docs/backtests/BASELINE.md`: the summary, cost share, insufficient-evidence buckets, and observations.
  - No strategy changes in this task. Grader changes are measured against this baseline in the `liquidity-engine` spec update.

- [ ] 212. Parity with the paper forward test
  - **Blocked until** the forward test has at least 20 closed trades placed after the task 196 restart date.
  - **212a. RED** (`backend/tests/test_backtest_export_forward_fixture.py`)
    - `test_export_includes_m1_window_and_trades_after_restart_date`
  - **212b. GREEN** — `scripts/export_forward_test_fixture.py`; export to `backend/tests/fixtures/backtester/parity/`.
  - **212c. RED → GREEN** (`backend/tests/test_backtest_parity.py`)
    - `test_backtest_reproduces_forward_test_trades` — same setup_ids, fills and exit reasons; R within rounding
  - **Validates: Requirements 9.3**

- [ ] 213. Remove the superseded backtester (L7)
  - Delete `ml/backtesting/engine.py` and `backend/tests/test_backtesting_engine.py`.
  - Confirm with `grep` that nothing imports `ml.backtesting`.
  - `python scripts/run_all_tests.py` is green.

---

## Task Dependency Graph

Tasks are grouped into waves. A wave can start once every wave in its `dependencies` is complete. Tasks inside a wave can run in any order unless a task's text says otherwise (183 needs 182; 185 needs 184; 186 needs 185; 190 needs 188 and 189).

```json
{
  "waves": [
    {
      "name": "Measurement and Instruments",
      "tasks": ["181", "182", "183"],
      "description": "Engine cost spike, InstrumentSpec, MT5 spec and commission export"
    },
    {
      "name": "Engine Performance",
      "tasks": ["214"],
      "description": "Remove analyze() hot spots found by task 181 without changing outputs. Not blocking the M15 baseline; required before long M5 studies.",
      "dependencies": ["Measurement and Instruments"]
    },
    {
      "name": "Calendar and Aggregation",
      "tasks": ["184", "185", "186", "187"],
      "description": "Venue period boundaries, M1 aggregation, parity with native bars, spread in the MT5 loader"
    },
    {
      "name": "Shared Decision Path",
      "tasks": ["188", "189", "190"],
      "description": "StrategyConfig, deterministic setup_id, build_order_intent extracted from the live runner"
    },
    {
      "name": "As-of View",
      "tasks": ["191", "192"],
      "description": "compose_as_of_view and the live runner switched onto it",
      "dependencies": ["Calendar and Aggregation", "Shared Decision Path"]
    },
    {
      "name": "Clock and Fill Model",
      "tasks": ["193", "194", "195"],
      "description": "Clock injection, shared FillModel with killzone expiry, PaperBroker on the FillModel",
      "dependencies": ["Measurement and Instruments", "Shared Decision Path"]
    },
    {
      "name": "Checkpoint: Shared Foundations Live",
      "tasks": ["196"],
      "description": "Full suite green; paper forward test restarted on the shared fill model",
      "dependencies": ["As-of View", "Clock and Fill Model"]
    },
    {
      "name": "Backtester Config and Data",
      "tasks": ["197", "198"],
      "description": "Run/study configuration, CandleSource, coverage check, data fingerprint",
      "dependencies": ["Calendar and Aggregation", "Shared Decision Path"]
    },
    {
      "name": "Signals",
      "tasks": ["199", "200"],
      "description": "Phase A signal generation with the truncation property, and its cache",
      "dependencies": ["As-of View", "Backtester Config and Data"]
    },
    {
      "name": "Account Simulation",
      "tasks": ["201", "202", "203", "204"],
      "description": "SimBroker, SimAccount, Phase B event loop, hold-out and walk-forward",
      "dependencies": ["Clock and Fill Model", "Signals"]
    },
    {
      "name": "Reporting and CLI",
      "tasks": ["205", "206", "207", "208"],
      "description": "Metrics, manifest/journal/summary writers, run comparison, CLI",
      "dependencies": ["Account Simulation"]
    },
    {
      "name": "Golden Run and Checkpoint",
      "tasks": ["209", "210"],
      "description": "End-to-end golden fixture, determinism, README",
      "dependencies": ["Reporting and CLI"]
    },
    {
      "name": "Baseline",
      "tasks": ["211"],
      "description": "First measured baseline of the current grader on MT5 history",
      "dependencies": ["Golden Run and Checkpoint"]
    },
    {
      "name": "Parity",
      "tasks": ["212"],
      "description": "Backtest reproduces the paper forward test's trades. Also blocked on at least 20 forward-test trades placed after the task 196 restart.",
      "dependencies": ["Checkpoint: Shared Foundations Live", "Golden Run and Checkpoint"]
    },
    {
      "name": "Cleanup",
      "tasks": ["213"],
      "description": "Remove the superseded ml/backtesting engine",
      "dependencies": ["Baseline"]
    }
  ]
}
```

---

## Notes

- Every implementation task follows RED → GREEN → REFACTOR. No production code is written without a failing test first.
- Hypothesis property tests run with `@settings(max_examples=100)`. The one exception is the truncation property (task 199), which uses 25 because each example runs `analyze()`.
- Test files are named `backend/tests/test_backtest_*.py`. Live-code changes extend the existing test files for the module they touch.
- No new dependencies. Use what `requirements.txt` already has (pandas, numpy, hypothesis, fakeredis) and the standard library (`tomllib` for configuration).
- Live-code changes (tasks 187–195) must leave live behaviour identical, except for the two intended changes: D4 (stricter paper fills) and D5 (closed-bar evaluation). Tests pin everything else.
- Group A is useful even before the backtester exists. A deterministic `setup_id` is the duplicate-order guard, and the stricter fill model makes the forward test's numbers honest.
- Strategy changes are out of scope. Grader rules (sweep, protected-swing stops, counter-trend cap, HTF-target entries, minimum stop vs costs) are specified in a `liquidity-engine` spec update, and their effect is measured against the task 211 baseline.
- The parity test (task 212) is written only once its fixture can exist. It is never added as a skipped or xfail placeholder.
