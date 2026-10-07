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

- [x] 214. Remove `analyze()` hot spots without changing outputs (added by task 181)
  - Numbered 214 so tasks 182–213 keep their numbers. Not blocking the M15 baseline (task 211). Required before M5 studies longer than a few weeks.
  - **214a. RED**
    - Add `scripts/export_engine_windows.py` and capture the benchmark windows (BTCUSDT M5, BTCUSDT M15, EURUSD M15, EURUSD M5), plus today's `analyze()` output for each, to `backend/tests/fixtures/backtester/engine_windows/`.
    - `test_engine_output_unchanged_on_fixture_windows` (`backend/tests/test_liquidity_engine_perf.py`) — `LiquidityMap.model_dump_json()` is byte-identical to the captured output, including list order.
    - `test_atr_series_matches_per_candle_calculate_atr` — the new precomputed series equals `calculate_atr()` at every index.
    - `test_calculate_atr_not_called_per_candle` — a call-count spy (call counts are a deterministic stand-in for timing assertions, which flake). It asserts at most 4 calls per timeframe, from the CRT classifier's fixed 8-candle `_range_stats` windows, down from about 1,000 per-candle calls.
  - **214b. GREEN**
    - Precompute the ATR series once per timeframe in `PDArrayDetector`.
    - Replace pairwise BPR overlap with a sort-and-sweep that emits the same arrays in the same order.
    - Re-profile, and address `structure.py` only if it is still above 20%.
  - **214c. REFACTOR** — rerun the task 181 benchmark and add the new numbers to `design.md` → Measured performance. The full liquidity-engine test suite is still GREEN.
  - **Done 2026-10-05.**
    - **Fixtures:** captured from the unmodified engine, about 356 KiB. Output is byte-identical on all four windows.
    - **Speed-up:** 1.6–1.8× (BTCUSDT M5: 132.7 → 77.7 ms, best p50 of three interleaved rounds).
    - **Changes:** ATR series computed once per timeframe; `_break_confirmed` memoised per `classify()` call.
    - **Not applied:** the BPR sort-and-sweep, because the cost there is the outputs themselves, not the pairing loop.
    - **Tests:** 459 liquidity-engine and agent tests GREEN. Numbers are in `design.md` → Measured performance.
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

- [x] 183. `scripts/export_instrument_specs.py`: venue specs and commission (D2)
  - **183a. RED** (`backend/tests/test_backtest_export_specs.py`; a fake MT5 module and a canned Binance exchangeInfo payload)
    - `test_maps_symbol_info_fields` — point, tick size, contract size, volume min/step/max, currencies, account currency
    - Commission is total `|commission| + |fee|` divided by total traded volume:
      - `test_commission_per_side_when_split_across_deals`
      - `test_commission_per_side_when_charged_at_entry_only` — a median would get this case wrong
      - `test_commission_counts_fee_field_and_ignores_other_symbols_and_non_trade_deals`
      - `test_commission_none_without_deals_for_symbol`
    - No deals: `test_no_deals_for_symbol_is_a_problem_unless_overridden` — no placeholder is written, since a placeholder 0 would load later as free trading; `--commission SYMBOL=value` supplies it
    - Spread: `test_default_spread_from_recent_ticks_median` (median ask − bid over 72 h of ticks; bar spreads read 0 on some servers), `test_zero_spread_is_a_problem_unless_overridden` (`--spread SYMBOL=points`)
    - `test_stop_slippage_defaults_to_two_points`
    - Provenance: the file header records the source broker/server (`test_main_writes_loadable_file`, `test_dumps_specs_records_source_as_comment`)
    - `test_symbol_suffix_resolved_but_key_is_instrument`, `test_unknown_symbol_is_a_problem`
    - Broker cross-check: `test_tick_value_cross_check_flags_mismatch`, `test_tick_value_cross_check_passes_for_usd_base_pair` — our money-per-tick must match MT5's `trade_tick_value`
    - Binance: `test_binance_specs_from_exchange_info`, `test_binance_unknown_symbol_is_a_problem`
    - CLI: `test_main_writes_loadable_file`, `test_main_refuses_to_write_when_problems`
  - **183b. GREEN**
    - `--venue mt5` writes `config/instruments/mt5.toml` from the terminal.
    - `--venue binance` writes `config/instruments/binance.toml` from public exchangeInfo, replacing the planned hand-written file: fee 0.001 per side, one-tick default spread, stop slippage 0.05% of the export-time price in price units (D3).
  - **183c. (user action)** — run both exports; review and commit the two files.
    - **Status 2026-10-05: done.**
      - `binance.toml` exported from public exchangeInfo.
      - The first MT5 export ran against `MetaQuotes-Demo`, which is not a live broker. Its median EURUSD/GBPUSD spread is 0 and it charges no commission, so its numbers were rejected and not committed.
      - `config/instruments/exness-standard.toml` was then exported from an Exness Standard MT5 demo (`ExnessKE-MT5Trial9`, hedging, USD, server clock UTC+0 verified from live ticks). Median spreads: EURUSD 0.8 pip, GBPUSD 1.0, USDJPY 1.0, XAUUSD $0.24. The tick-value cross-check passed for all four.
      - Commission is passed as 0 (`--commission`). That is the Standard account's real pricing, costed through the spread, so no deals were needed to measure it.
      - Spread and slippage values are rounded to a tenth of a point (`_price_units`).
      - **Open:** stop slippage defaults to 2 points, which is 0.2 pip on 5-digit FX but only $0.002 on XAUUSD (point 0.001). Revisit before task 211.
  - **Validates: Requirements 5.1, 5.2**

- [x] 215. Broker profiles (L8, `agent/broker_profiles.py`, `config/brokers/*.toml`)
  - Numbered 215 so earlier task numbers stay stable. Added 2026-10-05 with Requirement 10.
  - **215a. RED** (`backend/tests/test_backtest_broker_profiles.py`)
    - `test_load_profile_resolves_credentials_from_named_env_vars`
    - `test_profile_file_never_contains_credential_values` — loading fails if `[credentials]` holds anything but env-var names
    - `test_symbol_map_resolves_and_defaults_to_instrument`
    - `test_profile_loads_its_spec_file`
    - `test_mt5_connect_refuses_on_server_clock_mismatch` (Req 10.6; fake MT5, no terminal)
    - `test_export_script_accepts_profile` and `test_history_loader_accepts_profile` (Req 10.5)
  - **215b. GREEN** — commit `config/brokers/exness-standard.toml` and `config/brokers/binance.toml`.
  - **215c. REFACTOR** — confirm GREEN.
  - **Validates: Requirements 10.1, 10.2, 10.3, 10.5, 10.6**

- [x] 216. Stop slippage as a share of the typical spread (D3 amended)
  - **216a. RED** (`backend/tests/test_backtest_export_specs.py`)
    - `test_stop_slippage_is_quarter_of_typical_spread_with_two_point_minimum` — EURUSD 0.8 pip spread → 0.2 pip; XAUUSD $0.24 → $0.06; a 1-point spread → 2 points
  - **216b. GREEN** — `scripts/export_instrument_specs.py`; then re-export `config/instruments/exness-standard.toml`.
  - **216c. REFACTOR** — confirm GREEN.
  - **Validates: Requirements 4.7, 5.3**

- [x] 184. `StrategyCalendar` (`services/market_data/strategy_calendar.py`, D9)
  - **184a. RED** (`backend/tests/test_backtest_strategy_calendar.py`)
    - `test_d1_starts_17_00_new_york_in_winter_and_summer`
    - `test_h4_starts_17_21_01_05_09_13_new_york`, `test_intraday_bars_nest_inside_d1`
    - `test_w1_period_matches_mt5_weekly_bar_labels` — boundary at Saturday 17:00 New York (the `ny_close` server's Sunday 00:00); the Sunday 17:00 open and Friday close share one period
    - `test_d1_stays_at_17_00_new_york_across_dst_change`
    - `test_periods_tile_time_without_gaps_or_overlaps_across_dst_change` — both US change days; this test found the fall-back repeated hour, now absorbed by the preceding period
    - `test_period_end_equals_next_period_start`, `test_naive_datetime_rejected`
    - `test_matches_native` — every TF for an MT5 `ny_close` clock; H1 and below for a UTC+0 MT5 clock (Exness) and for Binance
  - **184b. GREEN** — one `StrategyCalendar` for every broker and venue.
  - **184c. REFACTOR** — confirm GREEN.
  - **Validates: Requirements 3.3**

- [x] 185. `aggregate()` (`services/market_data/as_of_view.py`)
  - **185a. RED** (`backend/tests/test_backtest_aggregation.py`)
    - `test_aggregate_ohlcv_values` — open = first, high = max, low = min, close = last, volume = sum
    - `test_aggregate_skips_empty_periods` — weekend: no synthetic bars
    - `test_partial_trailing_period_not_emitted` — only closed periods; `test_as_of_controls_which_periods_count_as_closed` (default: the close of the last input bar)
    - `test_d1_follows_new_york_close_not_utc_midnight`, `test_volume_none_when_all_inputs_none`
    - `test_unsorted_input_rejected`, `test_input_coarser_than_target_rejected`, `test_empty_input`
    - **PBT — Property 3: Aggregation Consistency** (`@given` random-walk M1)
      - **Validates: Requirements 3.3**
  - **185b. GREEN** / **185c. REFACTOR**

- [x] 186. Aggregation parity against native venue bars
  - **186a.** `scripts/export_aggregation_fixture.py` (takes `--profile`) exports one week of M1 plus native H1/H4/D1/W1 to `backend/tests/fixtures/backtester/aggregation/`:
    - EURUSD and XAUUSD from `exness-standard` (UTC+0);
    - EURUSD from MetaQuotes-Demo (`ny_close`), used only as calendar test data;
    - BTCUSDT from Binance.

    **(user action** for the MT5 parts.)
  - **186b. RED** (`backend/tests/test_backtest_aggregation_parity.py`)
    - `test_aggregated_bars_match_native_within_one_tick` — parametrised over every (source, instrument, TF) where `StrategyCalendar.matches_native` is true: H1 and below everywhere; H4/D1/W1 only against the `ny_close` server
  - **186c. GREEN** — fix calendar boundaries until it passes. Never loosen the tolerance.
  - **Done 2026-10-06.**
    - **Fixtures** (week of 2026-09-26, about 816 KiB): EURUSD and XAUUSD from `metaquotes-demo` (a new data-only profile, `ny_close`) and `exness-standard`; BTCUSDT from `binance`. MetaQuotes also has 52 weeks of H1 plus native H4/D1/W1 (from 2025-10-04), because the terminal keeps only about 69 days of M1. That range spans both US DST changes, and H1 is what the live runner aggregates from (L3).
    - **Result:** GREEN on the first run with no calendar change: 17 cases, about 16,800 prices, every one exact (not just within a tick).
    - **The test can fail:** a calendar starting the day at 18:00 New York matches 0 of the H4/D1/W1 periods. A calendar ignoring DST matches 0 of the 528 winter H4 periods. `test_parity_check_detects_a_different_calendar` keeps a negative control in the suite (Exness's UTC D1 never lines up).
  - **Validates: Requirements 3.4**

- [x] 187. MT5 history loader stores spread (L6)
  - **187a. RED** (extend the existing loader tests)
    - `test_spread_points_converted_to_price_units` — `rates["spread"] × symbol point`
    - `test_spread_written_to_candles_spread_column`
  - **187b. GREEN** — `scripts/load_historical_data_mt5.py`.
  - **187c. REFACTOR** — confirm the existing loader tests are still GREEN.
  - **Validates: Requirements 3.5**

- [x] 188. `StrategyConfig` (`agent/strategy_config.py`, part of L1)
  - **188a. RED** (`backend/tests/test_backtest_strategy_config.py`)
    - `test_defaults_equal_current_runner_constants` — pins today's `_CANDLE_COUNT`, `_GRADE_TO_CONFIDENCE`, min R:R 3.0, TP levels 2.5/4.0, context TFs
    - `test_pending_expiry_default_killzone_end_with_3h_fallback`
    - `test_fingerprint_stable_and_changes_on_any_field`
    - `test_frozen`
  - **188b. GREEN** / **188c. REFACTOR**
  - **Validates: Requirements 1.6**

- [x] 189. `SetupGradeDetail.entry_array_id` and deterministic `setup_id` (L2)
  - **189a. RED** (`backend/tests/test_liquidity_grader.py`, `backend/tests/test_backtest_order_intent.py`)
    - `test_grade_detail_carries_selected_entry_array_id`
    - `test_entry_array_id_none_without_entry_array`
    - `test_setup_id_stable_for_same_array_across_consecutive_bars`
    - `test_setup_id_differs_for_different_arrays_or_entry_tf`
  - **189b. GREEN** — additive model field. The grader sets it.
  - **189c. REFACTOR** — the full liquidity-engine test suite is still GREEN.
  - **Validates: Requirements 1.3**

- [x] 190. `build_order_intent()` extraction and runner refactor (L1)
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

- [x] 191. `compose_as_of_view()`
  - **191a. RED** (`backend/tests/test_backtest_as_of_view.py`)
    - `test_entry_tf_and_below_closed_bars_only`
    - `test_htf_window_has_one_in_progress_bar_from_m1`
    - `test_no_in_progress_bar_before_first_m1_of_period`
    - `test_window_sizes_match_strategy_config`
    - `test_pure_no_clock_no_io` — same inputs give the same output
    - **PBT — Property 2: As-of View Contains Only Known Data**
      - **Validates: Requirements 2.1, 2.2, 2.3**
  - **191b. GREEN** / **191c. REFACTOR**
  - **Done 2026-10-06.**
    - `closed` may run past t; bars count as closed when their calendar period has ended. A closed bar off the strategy calendar (e.g. a UTC server's native H4) is rejected, since it could count as closed while still forming.
    - Property 2 is tested in its strong form: dropping every M1 bar that closes after t leaves the view unchanged. Two planted look-ahead bugs fail it: one minute of M1 in the forming bar, and a forming bar counted as closed.
  - **Validates: Requirements 2.4**

- [x] 192. Live runner builds its window with `compose_as_of_view()` (L3, D5, D9)
  - **192a. RED** (`backend/tests/test_backtest_runner_view.py`; fake fetchers, no MT5/Binance)
    - `test_forming_entry_bar_dropped`
    - `test_m1_fetched_to_cover_current_w1_period`
    - `test_htf_in_progress_bar_composed_from_m1`
    - `test_native_htf_bars_used_only_where_calendar_matches` — `ny_close` server: native H4/D1/W1; UTC+0 server or Binance: H4/D1/W1 aggregated from native H1
    - `test_evaluation_timestamp_is_last_entry_bar_close`
  - **192b. GREEN** — `scripts/run_live_agent.py` fetch path for MT5 and Binance.
  - **192c. REFACTOR** — confirm GREEN.
  - **Done 2026-10-06.** `_as_of_window()` in the runner; the same prices now give the engine identical candles from a `ny_close` server, a UTC server or Binance (tested). Found and fixed on the way:
    - **Staleness:** `observe_node` rejects setups detected over 60 s before it sees them. With data as of the bar close, a setup evaluated a few minutes later was dropped as stale. `OrderIntent.to_message(detected_at=...)` now carries the hand-off time live; it defaults to t, which is right for the backtest.
    - **One evaluation per closed bar:** t no longer moves with the wall clock, so over an FX weekend every pass would re-send Friday's last bar. `_process_instrument(evaluated=...)` skips a repeated (instrument, t) as `NO NEW BAR`.
    - **Short history refused:** a venue returning less history than the windows need would give the engine shorter windows than the backtest ever uses. The runner raises instead, and the next pass retries.
    - `--store-candles` stores the newest 300 bars of each fetch (the H1 and M1 fetches are now thousands of bars).
    - **Smoke runs** (alert only): Binance and Exness passes complete in about 25 s; XAUUSD graded A and reached a NOTIFY decision. One earlier Exness pass graded differently at the same t; it didn't reproduce (two runs since give identical windows and grades), and fresh symbols return full H1 history on the first request, so the cause is unknown.
  - **Validates: Requirements 2.7**

- [x] 193. Clock injection (L5)
  - **193a. RED** (`backend/tests/test_agent_graph.py`, `test_agent_nodes.py`, `test_agent_decisions_audit.py`)
    - `test_observe_node_staleness_uses_injected_now` — detected 30s before the clock is fresh; 61s is stale
    - `test_agent_graph_passes_clock_to_nodes`
    - `test_learn_and_audit_timestamps_from_clock`
    - `test_default_clock_is_wall_clock` — existing behaviour unchanged
  - **193b. GREEN** — optional `clock` / `now` parameters with wall-clock defaults.
  - **193c. REFACTOR** — confirm GREEN.
  - **Done 2026-10-06.** `agent/clock.py` (`Clock`, `wall_clock`). `observe_node`, `learn_node`, `log_agent_decision` and `AgentGraph` take an optional `clock`; the graph passes its clock to every node. Nothing else on the decision path reads the wall clock (the risk engine and the other nodes don't). The paper broker's clock is task 195.
  - **Validates: Requirements 2.5**

- [x] 194. `FillModel` and `KILLZONE_END` expiry (`agent/brokers/fill_model.py`)
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
  - **Done 2026-10-06.** Single-target orders (D19 scale-out deferred). Edge cases settled and recorded in `design.md` → FillModel: ideal (bid, pre-slippage) vs actual prices; MARKET orders already beyond their stop or target are REJECTED; limit-fill-bar stops exit at the stop; MAE/MFE start at the fill on the closing side. Literal `KILLZONE_END`: an order placed at a killzone's last instant (t = 10:00, 05:00 or 16:00 New York) expires at once.
    - The property tests were checked by planting bugs: target before stop, slippage in the trader's favour, and bars before placement accepted are each caught. The first was missed until the bar generator included wide outside bars: before that, no generated bar reached both stop and target after a fill.
  - **Validates: Requirements 4.2, 4.9, 4.11, 4.12**

- [x] 195. `PaperBrokerAdapter` on the shared `FillModel` (L4, D4)
  - **195a. RED** (`backend/tests/test_paper_broker.py`)
    - `test_paper_broker_uses_fill_model` — touch-only limit no longer fills; market fills at the next bar's open at the ask
    - `test_injected_clock_sets_placed_at`
    - `test_bar_spread_is_max_of_recorded_and_typical` (Req 5.1, D10) — including Binance klines, which record none
    - `test_fee_rate_maps_to_rate_per_side_commission`
    - `test_state_file_from_previous_version_still_loads`
    - Update only the existing assertions whose semantics change on purpose. Annotate each with "D4: stricter fill model".
  - **195b. GREEN** — `PaperBrokerAdapter` keeps its public API and report.
  - **195c. REFACTOR** — confirm GREEN.
  - **Done 2026-10-06.** Fills, stops, targets and expiry go through `FillModel`; spreads and slippage come from the venue's spec file (`binance` for the Binance feed; the MT5 feed has zero costs until task 219 gives it a profile). The expiry rule comes from `StrategyConfig` (the runner passes `KILLZONE_END`; the constructor default stays the old fixed TTL).
    - **Each bar is processed once.** `update()` takes closed bars and records `processed_through`, replacing the old re-scan workaround; the runner drops the forming M1 bar.
    - **Market orders** rest as PENDING until the next bar's open (the one D4-annotated assertion change). `place_order`'s `pending` flag still means "a resting limit".
    - **R:** gross on chart (bid) prices, net on executed prices less `fee_rate` per side, 1R = ideal fill to stop.
    - The live forward test's state file (one expired BNBUSDT order) loads and reports. Its stop was 0.38 on a 775 price: round-trip fees were about 4R, the Req 5.5 problem.
  - **Validates: Requirements 4.1, 4.2**

- [x] 196. Checkpoint: shared foundations live
  - `python scripts/run_all_tests.py` is green (apart from the task-39 RED file).
  - Rebuild and restart `docker/paper-trader`. **(user action** to confirm the restart.)
  - Record the restart date in this file. Only forward-test trades placed after it are valid parity data (task 212).
  - **Done 2026-10-06. Restarted 2026-10-06 09:28:20 UTC** (user confirmed). Only Binance forward-test trades placed after this are valid parity data.
    - The suites were green at task 195 (root 845, backend 1680; only the task-39 RED file fails).
    - **Fixed before the restart:** the image didn't copy `config/`, which the runner now reads (Binance profile and spec file). The rebuilt container would have crash-looped. `config/brokers/` and `config/instruments/` are now copied.
    - Checked inside the new image first, with throwaway containers (alert-only and paper on a temp state file). After the restart: backfill done, first pass at 09:29:59 UTC on all six pairs, container healthy, heartbeat current.

### B. Backtester core

- [x] 197. `algo_backtester` scaffold and configuration
  - **197a. RED** (`backend/tests/test_backtest_config.py`)
    - `test_variant_dotted_key_override`
    - `test_unknown_config_key_rejected`
    - `test_study_holdout_defaults_to_last_3_months_and_persists`
    - `test_run_config_resolves_strategy_config`
  - **197b. GREEN** — `algo_backtester/config.py`, `config/backtests/base.toml`, and `data/backtests/` added to `.gitignore`.
  - **197c. REFACTOR** — confirm GREEN.
  - **Done 2026-10-06.** `RunConfig` is frozen and rejects unknown keys in every section and in variants; its `[strategy]` table is the live `StrategyConfig`. Studies live in `config/backtests/studies/<study>.toml` (not beside `base.toml`, which a study named "base" would overwrite); the hold-out is written on first use and never moves. `check_holdout()` refuses a run reaching the hold-out unless final. The acceptance-criteria proposal (handoff brief) was deferred by the user until the backtester runs.
  - **Validates: Requirements 7.1, 7.2**

- [x] 198. `CandleSource`, coverage check, data fingerprint (`algo_backtester/data.py`)
  - **198a. RED** (`backend/tests/test_backtest_data.py`, using `CsvSource` fixtures)
    - `test_weekend_gap_allowed_midweek_gap_refused`
    - `test_late_history_start_refused`
    - `test_allow_gaps_flag_permits_and_is_reported`
    - `test_fingerprint_changes_when_one_row_changes`
    - `test_warmup_falls_back_to_native_htf_and_reports_source`
    - `test_bar_spread_floored_at_typical_and_floored_bars_counted` (Req 5.1, D10)
    - `test_timescale_source_reads_m1_utc` — marked `infrastructure`
  - **198b. GREEN** / **198c. REFACTOR**
  - **Done 2026-10-06.** `CsvSource`, `TimescaleSource` (rows of one `source`, since the candles key holds one row per time and instrument), `check_coverage` / `ensure_coverage`, `fingerprint`, `fill_bars`, `load_instrument`.
    - **Gap rules calibrated on real M1** (task 186 weeks), MT5 venues only:
      - the daily break around 17:00 New York, up to 3 h: gold stops 62 min at Exness and 120 min at MetaQuotes, FX rollover a few minutes;
      - the FX weekend, Friday 15:00 to Sunday 20:00 New York;
      - Christmas and New Year.
      Binance is 24/7, so none apply. All four real weeks pass. History ending before the run end is refused too.
    - **Warm-up:** M1 is used where it yields the window's closed bars before the start (counted, not estimated). Otherwise the earlier part comes from native bars (`native`), or native H1 at a UTC server (`native_h1`). The source is reported per timeframe; an incomplete warm-up is a coverage problem.
    - **Memory:** M1 stays as slim `StoredBar` rows, which `aggregate()` accepts. A year plus warm-up is about 700k rows per instrument; as Pydantic `Candle`s that would not fit four instruments in parallel.
    - The `infrastructure` test passes against the live candle store (Binance M1 from the paper trader).
  - **Validates: Requirements 3.1, 3.2, 3.6, 3.7**

- [x] 199. Phase A: `generate_signals()` (`algo_backtester/signals.py`)
  - **199a. RED** (`backend/tests/test_backtest_signals.py`, `test_backtest_truncation.py`)
    - `test_one_record_per_entry_tf_close`
    - `test_analyze_called_with_as_of_time`
    - `test_engine_exception_becomes_engine_error_record`
    - `test_parallel_per_instrument_equals_sequential`
    - **PBT — Property 1: No Look-Ahead (Truncation Invariance)** — fixture data, `max_examples=25`
      - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**
  - **199b. GREEN** / **199c. REFACTOR**
  - **Done 2026-10-06.** `signal_at()` / `generate_signals()` / `generate_all()` (one process per instrument). A failure in `analyze()` or `build_order_intent()` becomes an `EngineError` record, so one bad bar can't end a run. `TradeContext` is still task 217.
    - **Property 1** runs the real engine on the task 186 MetaQuotes data. A planted 15-minute look-ahead fails it.
    - **Fixed on the way:**
      - `compose_as_of_view()` copied each timeframe's whole history per call (quadratic over a run); it now slices just the window, with identical output.
      - `StrategyConfig` didn't pickle (read-only mappings), which worker processes need.
      - Warm-up falls back to native H1 when the store lacks a timeframe's native bars.
      - A warm-up with no source is a coverage problem, not a crash.
    - **Speed:** about 33 ms per entry close with the live defaults (M15, full windows), roughly 14 min per instrument-year.
    - **Findings on real data** (MetaQuotes week, test data only, D11):
      - R:R is exactly 5.0 on all 20 EURUSD setups (5.0-5.4 on gold): SD targets are a fixed multiple of the entry array's range, so `min_rr` 3.0 never filters.
      - EURUSD stops have a median of 2.6 pips (min 0.8; 7 of 20 are 2 pips or less). Exness's 0.8-pip spread is about 0.3R per trade at the median: costs are likely to decide FX results (Req 5.5).
  - **Validates: Requirements 1.1, 9.2**

- [x] 217. `TradeContext` on SignalRecords (Req 11.5)
  - Numbered 217 to keep earlier numbers stable. Added 2026-10-05 with Requirement 11.
  - **217a. RED** (`backend/tests/test_backtest_signals.py`)
    - `test_order_intent_records_carry_trade_context` — entry array, draw on liquidity and killzone, taken from the LiquidityMap at `t`
    - `test_no_trade_records_carry_no_context` — keeps the cache small
    - `test_trade_context_round_trips_through_cache`
  - **217b. GREEN** / **217c. REFACTOR**
  - **Done 2026-10-06** (after task 200, whose cache the round-trip test needs). `trade_context()` extracts the chosen entry array (by `entry_array_id`), the draw on liquidity and the killzone at `t`. The killzone uses the same windows as `KILLZONE_END` expiry. Values are JSON-ready for the report. `swept_level` stays None until the grader records the opposite-side raid (`liquidity-engine` spec update). Records without context omit the key in the cache.
    - **Seen on real data** (first intent of the 2026-09-30 test window, MetaQuotes EURUSD): a SHORT whose draw on liquidity is buy-side liquidity above price (PDH), with a 0.6-pip stop off a 1-pip M15 breaker, below Exness's 0.8-pip spread. This is for the baseline (task 211), not a change here.
  - **Validates: Requirements 11.5, 11.6**

- [x] 200. Phase A cache (`algo_backtester/cache.py`)
  - **200a. RED** (`backend/tests/test_backtest_cache.py`)
    - `test_key_changes_with_each_input`
    - `test_hit_returns_identical_records`
    - `test_corrupt_entry_recomputed`
    - `test_write_is_atomic`
    - `test_engine_source_edit_invalidates` — the engine code fingerprint changes when a `liquidity_engine` file changes
  - **200b. GREEN** / **200c. REFACTOR**
  - **Done 2026-10-06.** `SignalCache` (`signals()`, `load()`, `store()`), `cache_key()`, `engine_code_fingerprint()`; `generate_all(cache=...)` serves hits in the main process and sends only misses to workers, which store their own entries. Records are JSON lines (`SignalRecord.to_json()` / `from_json()`), restored with their types (an enum, not its string).
    - **Two refinements to the design** (recorded there):
      - The key leaves out `pending_expiry` and `fallback_ttl_minutes`, which only the fill model reads, so an expiry variant reuses Phase A as Req 7.4 intends.
      - The engine code fingerprint also covers the code that shapes what the engine sees or what a record holds (as-of view, calendar, MT5 clock, warm-up, record format, time features). Line endings are normalised, so Windows and Linux checkouts agree.
    - A trailer (key, record count, sha256) catches truncated, edited or unreadable entries; they are deleted and recomputed.
  - **Validates: Requirements 7.4**

- [x] 201. `SimBroker` (`algo_backtester/sim_broker.py`)
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
  - **Done 2026-10-06.** `SimBroker` (a `BrokerClient`), `SimTrade` (the fill model's order plus its sizing), `ClosedTrade` (R, cost split, MAE/MFE, P&L, cost flag; R fields None for orders that never filled). `advance()` returns the orders that closed; Phase B books them (task 203). The tests were mutation-checked: rounding to nearest, the wrong spread side, no tolerance, no stop check and the old R definition each fail them.
    - **R is measured on the distance the order was sized on**, `|entry - stop|`, not `|ideal_fill - stop|` as designed. The old definition reaches zero or goes negative when the spread is as wide as the stop, which real EURUSD setups do (task 217: a 0.6-pip stop against a 0.8-pip spread). It also inflated LONG losses and differed between a LONG and its mirror SHORT. Recorded in `design.md` → SimBroker.
    - **Also refused at placement:** `INVALID_STOPS` (a stop or target on the wrong side, as MT5 refuses it), `INVALID_ORDER`, `NO_PRICE`. `build_order_intent`'s draw-on-liquidity fallback target can land behind the entry and still pass `min_rr`, because the R:R check uses `abs()`.
    - **Seen in a test:** a 0.6-pip stop at $3.50/lot/side commission and a 0.8-pip spread loses 2.5R on a plain stop-out (1.33R spread, 0.33R slippage, 1.17R commission). The test's commission is hypothetical: `exness-standard` charges none (spread-only), so there the same stop-out costs about 1.67R (spread 0.8 pip and slippage 0.2 pip over a 0.6-pip stop).
  - **Validates: Requirements 5.1, 5.5**

- [x] 202. `SimAccount` (`algo_backtester/account.py`)
  - **202a. RED** (`backend/tests/test_backtest_account.py`)
    - `test_daily_anchor_resets_17_00_new_york_winter_and_summer`
    - `test_weekly_anchor_resets_sunday_open`
    - `test_drawdown_includes_open_positions_marked_to_close`
    - `test_exposure_dict_drives_risk_engine_daily_limit` — `RiskEngine.validate()` rejects at 3%
    - `test_non_compounding_risk_amount_fixed`
  - **202b. GREEN** / **202c. REFACTOR**
  - **Done 2026-10-06.** `SimAccount` (`book()`, `mark()`, `exposure()`); `SimBroker.open_pnl()` and `active_count()` feed its marks.
    - Anchors follow the strategy calendar's D1/W1 periods. An anchor is the last mark of the period before, and a mark at exactly 17:00 still belongs to the old day.
    - `RiskEngine` sizes at a fixed 1% of the equity it reads, so `exposure()["equity"]` is `risk_amount / 1%`. Without that, the run's `risk_per_trade` would never reach `execute_node`, and the budget would compound (`test_risk_per_trade_reaches_risk_engine`).
  - **Validates: Requirements 1.4, 6.3, 6.4**

- [x] 203. Phase B event loop (`algo_backtester/simulation.py`)
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
  - **Done 2026-10-06.** `simulate()` returns `SimulationResult(journal, trades, open_orders, account)`. Each `JournalRow` carries its intent, `TradeContext`, ICT time window and, once closed, its `ClosedTrade`. Mutation-checked: no D6 check, a stale open-trade count, the wall clock, and no re-mark after placements each fail the tests. Bars-before-signals ordering is structural, so that mutant was equivalent.
    - **No Mongo journal or audit collection** (the design had list-backed ones): `learn_node` queues MLflow retraining every 50 documents. Phase B's journal records every decision instead.
    - **Attempted (D6)** = the broker accepted an order for the `setup_id`. Refusals by risk rules or the broker are re-evaluated on the next close, as live.
    - The account is marked again before each `graph.run()`, so orders placed earlier at the same `t` count towards the concurrent-trade limit.
  - **Validates: Requirements 1.1, 7.5**

- [x] 204. Hold-out and walk-forward
  - **204a. RED** (`backend/tests/test_backtest_run_modes.py`)
    - `test_holdout_overlap_refused_without_final`
    - `test_final_flag_recorded_in_manifest`
    - `test_walk_forward_windows_and_warmup_before_window`
    - `test_walk_forward_combined_equals_concatenation`
  - **204b. GREEN** / **204c. REFACTOR**
  - **Done 2026-10-06.** `algo_backtester/run.py` (not in the design's layout; the CLI, task 208, calls it). `run_backtest()` checks the hold-out and refuses crosses before any work. It runs Phase A once (through the cache), then Phase B per window. `RunResult.manifest` holds the run-mode fields (study, hold-out start, final flag, variant, windows) for task 206 to extend.
    - Walk-forward windows step by `D`, `W` or `M` from the run start (`"3M"`); month steps clamp to month ends.
    - Each window is a fresh account and broker; the bar closing at its start prices its first decision.
    - Tested end to end on the real MetaQuotes week with the real engine and the `exness-standard` spec file.
  - **Validates: Requirements 7.2, 7.3**

### C. Reporting and CLI

- [x] 205. Metrics (`algo_backtester/metrics.py`)
  - **205a. RED** (`backend/tests/test_backtest_metrics.py`, known trade lists)
    - `test_win_rate_expectancy_profit_factor`
    - `test_max_drawdown_r_and_pct_and_losing_streak`
    - `test_holding_time_and_cost_share`
    - `test_bootstrap_ci_deterministic_for_seed_and_contains_mean`
    - `test_insufficient_evidence_below_min_trades`
    - `test_breakdowns_by_instrument_grade_killzone_direction_month`
  - **205b. GREEN** / **205c. REFACTOR**
  - **Done 2026-10-06.** `summarize(journal, ...)` → `Summary(overall, breakdowns, counts)`; `stats(trades, ...)` → `Stats`; `bootstrap_ci()` (numpy, seeded, chunked to bound memory). Definitions are in the module docstring:
    - Only filled trades count. Unfilled orders and orders still open at the end are counted separately.
    - Win/loss are net R > 0 / < 0. Profit factor is None without a loss. Cost share is None unless gross R is positive.
    - Max drawdown % is on closed-trade equity.
    - **Breakdowns:** instrument, grade, killzone (the engine's `TradeContext.killzone`: the same windows as `KILLZONE_END` expiry), direction, fill month (UTC). Also by ICT time window (`TimeWindowClassifier`, e.g. `LONDON_SILVER_BULLET`); the design had named it as the killzone source.
  - **Validates: Requirements 8.2, 8.3, 8.4**

- [x] 206. Report writers (`algo_backtester/report.py`)
  - **206a. RED** (`backend/tests/test_backtest_report.py`)
    - `test_run_id_is_manifest_hash_excluding_created_at`
    - `test_manifest_records_git_engine_data_and_flags` — including `ai_modifiers` and `news_filter`
    - `test_journal_includes_skipped_intents_with_reason`
    - `test_journal_columns_order_and_fixed_precision`
    - `test_summary_md_marks_insufficient_buckets`
  - **206b. GREEN** / **206c. REFACTOR**
  - **Done 2026-10-07.** `build_manifest()`, `run_id()`, `journal_csv()`, `summary_json()` / `summary_md()`, `write_run()` → `data/backtests/<run_id>/`. A generated report was read by eye.
    - `run_id` hashes everything except `created_at` and the bootstrap seed (derived from the id). A rewrite with the same inputs is byte-identical apart from `manifest.json`'s `created_at`.
    - **Journal:** adds `killzone` and `time_window` after `reason`, for the report's filters (Req 11.4). An order still open at the end shows its known lifecycle with `exit_reason = OPEN_AT_END`.
    - **Git:** `git_dirty` counts tracked changes only. Untracked notes (like the handoff brief) would otherwise mark every run dirty; the engine fingerprint covers the engine sources anyway.
    - **Summaries:** `summary.md` italicises insufficient buckets and labels them; walk-forward runs add a per-window table.
    - The SignalRecords file the HTML report needs (`TradeContext`) is left to task 218.
  - **Validates: Requirements 8.1, 8.6, 9.5**

- [x] 207. Run comparison (`algo_backtester/compare.py`)
  - **207a. RED** (`backend/tests/test_backtest_compare.py`)
    - `test_side_by_side_summary`
    - `test_refuses_different_data_fingerprint_or_range`
  - **207b. GREEN** / **207c. REFACTOR**
  - **Done 2026-10-07.** `compare(run_dirs, by=None)` reads each run's `manifest.json` and `summary.json`.
    - **Overall table:** a column per run (variant and run id), with code commit, engine fingerprint and final flag on top.
    - **`by=` a breakdown:** bucket by bucket, avg net R and n, insufficient buckets marked.
    - **Refused:** a different instrument set, or a different range, row count or fingerprint per instrument. Different code, settings or costs are allowed; that's what a comparison is for.
    - `report.stats_cells()` formats numbers the same way in `summary.md` and in comparisons.
  - **Validates: Requirements 8.5**

- [x] 208. CLI: `python -m algo_backtester run | compare | check-data`
  - **208a. RED** (`backend/tests/test_backtest_cli.py`)
    - `test_check_data_nonzero_exit_on_coverage_failure`
    - `test_run_writes_outputs_to_run_dir`
    - `test_variant_and_final_flags_parsed`
  - **208b. GREEN** / **208c. REFACTOR**
  - **Done 2026-10-07.** `algo_backtester/cli.py` (`main()`, `parse_args()`) and `__main__.py`, with the main-module guard that Phase A's worker processes need on Windows.
    - **Candles:** from the TimescaleDB store (`TIMESCALE_URL`, environment or `.env`), the rows of the profile's venue. The MT5 loader writes every MT5 broker as `source='mt5'`.
    - **Exit codes:** 0 done; 1 data problems; 2 refused (hold-out, or runs that can't be compared).
    - **check-data** prints coverage and warm-up sources per instrument. On first use it creates the study, with the hold-out counted back from the earliest instrument's latest stored M1 (`CandleSource.last_time()`, added to `data.py`). **Run it only once the full history is loaded (task 211):** the hold-out it sets never moves. Deleting the study file resets it.
    - **run** checks the hold-out before loading anything, then coverage (unless `allow_gaps`). It runs Phase A through the cache (`--no-cache` to recompute) and writes `data/backtests/<run_id>/`. Agent node logging is silenced during the run, since the journal records every refusal with its reason.
    - `compare` refuses a path that isn't a run directory instead of failing with a traceback.
  - **Validates: Requirements 7.1**

### D. Validation and first results

- [x] 218. HTML run report (`algo_backtester/report_html.py`, Req 11)
  - Numbered 218 to keep earlier numbers stable. Added 2026-10-05.
  - **218a. RED** (`backend/tests/test_backtest_report_html.py`, synthetic run directory)
    - `test_report_is_single_offline_file` — no `http://` or `https://` script, link or img references
    - `test_report_header_shows_manifest_essentials`
    - `test_every_journal_row_present_including_skipped`
    - `test_chart_window_spans_bars_before_decision_to_bars_after_close`
    - `test_markers_for_decision_entry_stop_target_fill_exit`
    - `test_context_drawn_only_from_recorded_signal_records` — no `analyze()` call during report generation
    - `test_insufficient_evidence_buckets_marked`
    - `test_forward_test_trades_file_renders_same_explorer`
  - **218b. GREEN** — CLI: `python -m algo_backtester report <run_dir>` and `report --forward-test <trades.json>`. `run` writes the report automatically.
  - **218c. REFACTOR** — open a generated report by hand to check it reads well. **(user action:** review one report.)
  - **Done 2026-10-07** (218c's review is still the user's: a sample is in `data/backtests/samples/`, two days of real EURUSD with the live defaults).
    - **Charts:** drawn as SVG by a small inline script; no plotly (4.8 MB per report). The run directory gains `context.json`, `candles.json` and `report.html`, and `run` writes them.
    - **Window lengths:** `[report] chart_bars_before` / `chart_bars_after`.
    - **The page script was smoke-run in Node** against a stub DOM: every row with a setup renders a valid chart (no NaN/undefined), with killzone bands, entry array, draw on liquidity, levels, fill, exit and decision.
    - **Size:** empty fields dropped, reasons and contexts stored once: about 100 KB for two days of one instrument. By extrapolation a year of four instruments is ~30 MB, mostly IN_TRADE rows. Measure at task 211; if too heavy, chart IN_TRADE rows via their order's row, or split per instrument.
    - **Fixed on the way:** a run config without `[strategy]` crashed (pydantic deep-copies a model default; `StrategyConfig`'s read-only mappings can't be). Defaults are now built by `default_factory`.
  - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7**

- [x] 209. Golden run
  - **209a.** Build `backend/tests/fixtures/backtester/golden/`: two weeks of EURUSD M1 plus native HTF warm-up, exported by `scripts/export_aggregation_fixture.py`. **(user action** for the export.)
  - **209b. RED** (`backend/tests/test_backtest_golden.py`)
    - `test_golden_journal_matches_expected`
    - `test_second_run_byte_identical`
    - **PBT — Property 10: Determinism and Cache Transparency** — cache-hit run equals empty-cache run
      - **Validates: Requirements 7.4, 9.5**
  - **209c. GREEN** — commit the expected journal. Any later intended change updates it in the same commit.
  - **Done 2026-10-07.** **The user chose the existing task 186 MetaQuotes week** over a fresh two-week Exness export.
    - **Inputs:** M1 from Sunday 2026-09-27 plus a year of native H1/H4/D1/W1; the run covers 2026-09-30 to 2026-10-03, once the live M15 window has its warm-up. Live default strategy settings, and a frozen copy of the exness-standard spec file (`golden/specs.toml`), so a spec re-export doesn't move the golden.
    - **The golden journal** (`golden/expected_journal.csv`, 277 rows): 6 orders (1 stop-out, 5 expired limits), 13 refusals, 42 IN_TRADE, 215 NO_TRADE. Regenerate on purpose with `UPDATE_GOLDEN=1 pytest tests/test_backtest_golden.py` in the same commit as the change.
    - **Byte-identity:** a second run writes byte-identical files: journal, summaries, `report.html`, `context.json`, `candles.json`, and the manifest with git state and `created_at` fixed.
    - **Property 10** (6 examples, two instruments, walk-forward or not): a run served from the cache, with the engine made to fail if called, writes the same journal and summaries as an empty-cache run.
    - `.gitattributes` stops line-ending conversion of the golden journal, which `core.autocrlf` would otherwise turn into CRLF on a Windows checkout.
  - **Validates: Requirements 9.4**

- [x] 210. Checkpoint: backtester complete
  - `python scripts/run_all_tests.py` is green (apart from the task-39 RED file).
  - Add a "Backtesting" section to `README.md`: setup, `check-data`, `run`, `compare`, hold-out rules.
  - **Done 2026-10-07.** Full suite: root 845 passed; backend 1842 passed, 8 skipped. The only failures are the 27 task-39 RED tests in `test_live_validation.py` (12 failed, 15 errors), as before.
    - **README:** a "Backtesting" section covers setup, the five commands, run outputs, the cache, variants, hold-out rules (including: run `check-data` only after the full history is loaded), the R definition and the golden run.

- [x] 211. First baseline of the current grader **(user action)**
  - Set the Exness terminal's Tools → Options → Charts → "Max bars in chart" to Unlimited and restart it.
  - Load M1 (with spread) plus native H1/D1/W1 for EURUSD, GBPUSD, USDJPY and XAUUSD (D1) from the `exness-standard` profile, with `scripts/load_historical_data_mt5.py --profile exness-standard`.
  - Run `check-data`. Create the study, which locks the hold-out (D7). Run `config/backtests/base.toml` (`profile = "exness-standard"`).
  - Write `docs/backtests/BASELINE.md`: the summary, cost share, insufficient-evidence buckets, and observations.
  - No strategy changes in this task. Grader changes are measured against this baseline in the `liquidity-engine` spec update.
  - **Done 2026-10-07.** The results are in `docs/backtests/BASELINE.md`, run `4de46a99e6a0`.
    - **Pass mark:** the user agreed it before the run. It is written at the top of BASELINE.md.
    - **Data:** the Exness terminal was set to unlimited bars. The loader ran with `--instruments EURUSD,GBPUSD,USDJPY,XAUUSD --timeframes M1,H1,D1,W1`; the default list holds symbols the profile doesn't map. That gave 3 years of M1 from 2023-10-08, and every warm-up came from M1.
    - **Study:** `baseline-2026q3`, hold-out from 2026-07-07.
    - **Gaps:** `check-data` flagged gold's US-holiday closes, the 2025-11-28 CME outage and two feed gaps under an hour. All are real, so `[data] allow_gaps = true` is set in `base.toml`.
    - **Result: fail, 1 of 5 criteria.** 216 trades; net −0.54R (95% CI −0.89 to −0.23); PF 0.45; max DD 117.4R; costs 192% of gross.
      - Trades with stops of at least 2× the spread show no gross edge: −0.02R gross, with the target hit 10% of the time.
      - 28 trades had stops narrower than 2× the spread. They lost 66.6R, one of them 26R.
      - 85% of orders expired unfilled.
    - **Runtime:** about 80 minutes cold.
    - **Report size:** `report.html` is 48 MB (see task 218's note).
    - **Noticed:** `CoverageError`'s message suggests `--allow-gaps`, but `run` has no such flag. Only `[data] allow_gaps` exists.

- [ ] 219. Exness FX/gold paper forward test on the Windows host (Req 9.6)
  - Numbered 219 to keep earlier numbers stable. Added 2026-10-05: the `exness-standard` account offers no crypto, so the Binance forward test cannot be evidence for the Exness strategy.
  - **219a. RED** (`backend/tests/test_backtest_runner_view.py`)
    - `test_runner_accepts_profile` — symbols resolved through the profile (EURUSD → EURUSDm), clock from the profile, verified on connect
    - `test_runner_paper_state_and_log_paths_configurable`
  - **219b. GREEN** — `--profile` in `scripts/run_live_agent.py`; `scripts/run_fx_forward_test.ps1` with `data/paper_trades_fx.json` and `data/fx_forward_test.log`.
  - **219c. (user action)** — create the documented Task Scheduler entry and start it during FX market hours. Record the start date here: it is the earliest date for FX parity data.
  - **Validates: Requirements 9.6**

- [ ] 212. Parity with the paper forward test
  - **Blocked until** the forward test has at least 20 closed trades placed after the task 196 restart date. Primary target: the Exness FX forward test (task 219); Binance optional.
  - **First:** move `PaperBrokerAdapter._r_multiples` to the SimBroker R definition (1R = `|entry - stop|`, task 201), ideally one shared function, so both sides measure R alike.
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
      "name": "Broker Profiles",
      "tasks": ["215", "216"],
      "description": "Broker profiles (credentials from .env, symbol map, server clock, spec file) and the amended stop slippage rule",
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
      "dependencies": ["Calendar and Aggregation", "Shared Decision Path", "Broker Profiles"]
    },
    {
      "name": "Signals",
      "tasks": ["199", "217", "200"],
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
      "tasks": ["205", "206", "207", "208", "218"],
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
      "name": "FX Forward Test",
      "tasks": ["219"],
      "description": "Exness FX/gold paper forward test on the Windows host; its trades are the primary parity data",
      "dependencies": ["Checkpoint: Shared Foundations Live", "Broker Profiles"]
    },
    {
      "name": "Parity",
      "tasks": ["212"],
      "description": "Backtest reproduces the paper forward test's trades. Also blocked on at least 20 forward-test trades placed after the task 196 restart.",
      "dependencies": ["Checkpoint: Shared Foundations Live", "Golden Run and Checkpoint", "FX Forward Test"]
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
