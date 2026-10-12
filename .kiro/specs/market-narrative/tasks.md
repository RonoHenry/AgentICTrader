# Implementation Plan

**spec**: Market Narrative

## Overview

Build order for stage 1 of `requirements.md` and `design.md` (decisions ND-D6, ND-D7, ND-D8 and ND-D10 at their proposed defaults unless the trader changes them).
- **Numbering:** tasks continue the platform sequence from **290**.
- **TDD:** every code task follows the **RED → GREEN → REFACTOR** cycle in `.kiro/steering/tdd-and-testing.md`.
- **Tests:** they live in `backend/tests/test_narrative.py` and `backend/tests/test_backtest_autopsy.py`. Run them from `backend/` with `.venv/Scripts/python.exe -m pytest`.
- **Properties:** "Property N" refers to this spec's `design.md` → Correctness Properties, tested with `hypothesis`.

Stage 2 (Requirements 6–9) isn't scheduled. Each part waits for the trader's decision on ND-D1 to ND-D5 or ND-D9.

Tasks marked **(user review)** end with your review before the next one starts.

---

## Tasks

- [x] 290. The candle narrative
  - **290a. RED** (`backend/tests/test_narrative.py`)
    - `test_up_day_low_first` — open, extremes, their times, the false move and its share, child indexes (H4 slots of a D1).
    - `test_down_day_and_flat_day` — a FLAT candle has no false-move or expansion fields.
    - `test_inverted_day` — the expansion extreme came first.
    - `test_ties_take_the_first_bar`
    - `test_incomplete_edges` — a series starting or ending inside a candle; one starting at a candle's start is complete.
    - `test_week_child_index_from_sunday` — W1 by D1: Monday is 1, and a missing Monday still counts.
    - `test_refuses_bars_not_finer_than_frame`
    - `test_fill_phase_cases` — every phase of Requirement 3.2, including UNKNOWN.
    - `test_rollover_window_flattens_fx` — 17:00–17:29 New York bars set to the last kept close, in summer and in winter time.
    - `test_rollover_window_drops_leading_bars` and `test_gold_untouched` and `test_price_basis_none`
    - `test_config_defaults_and_toml` and `test_config_rejects_unknown_keys_and_values`
    - Property 1 (Hypothesis): M15 against H1 bars, for D1 and H4 frames.
    - Property 2 (Hypothesis): bars outside a candle perturbed.
    - `test_research_labels.py`: the import guard also covers `algo_research.narrative` and `algo_backtester.autopsy`, and `liquidity_engine/` and `agent/`.
  - **290b. GREEN**
    - `algo_research/narrative/__init__.py`, `config.py`, `prices.py` and `candles.py`.
    - `config/research/narrative.toml` with the defaults, commented.
  - **290c. REFACTOR**
  - **Validates: Requirements 1.1–1.5, 2.1–2.4, 5.1**

- [x] 291. The trade autopsy
  - **291a. RED** (`backend/tests/test_backtest_autopsy.py`)
    - A synthetic run directory (`journal.csv`, `context.json`, `candles.json`) with one trade per failure mode on hand-built days.
    - `test_load_run_keeps_closed_fills_and_counts_open_at_end`
    - `test_frame_directions_and_with` — W1, D1 and H4 for each trade.
    - `test_failure_modes` — each trade lands in its mode.
    - `test_stopped_by_false_move_and_target_beyond_expansion`
    - `test_raid_side_and_raid_in_candle` and `test_missing_raid_leaves_columns_empty`
    - `test_fill_side`
    - `test_asof_shape_cases` — WITH_SHAPE, FADES_SHAPE, UNFORMED.
    - `test_unknown_when_candle_incomplete_or_missing`
    - `test_split_counts_shares_and_intervals` — the interval contains the mean; a fixed seed repeats.
    - Property 3 (Hypothesis): the split adds up.
    - Property 4 (Hypothesis): bars after the fill perturbed.
  - **291b. GREEN** — `algo_backtester/autopsy.py`: `load_run`, `autopsy_table` and `split`.
  - **291c. REFACTOR**
  - **Validates: Requirements 3.1–3.6, 5.2**

- [x] 292. The autopsy report and commands
  - **292a. RED**
    - `test_autopsy_md_sections` — the hindsight header, the configuration, and each split of Requirement 4.2.
    - `test_write_autopsy_is_byte_identical` — written twice, the same bytes.
    - `test_no_filled_trades` — files written; the report says so.
    - `test_refuses_coarse_candles`
    - `test_backtest_cli.py`:
      - the run directory lists `autopsy.csv` and `autopsy.md`;
      - `autopsy <run_dir>` writes them;
      - a directory without run files exits 2.
  - **292b. GREEN** — `autopsy_md` and `write_autopsy`; the `autopsy` command; the hook in `run`.
  - **292c. REFACTOR** — the module docstring and the CLI's usage text.
  - **Validates: Requirements 4.1–4.5**

- [ ] 293. Autopsy of the reference runs **(user review)**
  - Run `python -m algo_backtester autopsy` on WICK `ec4876ba87a1`, BODY `475491a89d91` and the baseline `5d241691c701`.
  - Write `docs/backtests/AUTOPSY.md`:
    - each run's split by failure mode;
    - the with-candle failures;
    - the raid side and the as-of shape;
    - what each finding points to in the engine: context-engine Requirement 4 (direction), Requirement 6 (selection) and Requirement 7 (targets).
  - Update `trading-method.md`, section 8, to cite it.
  - You review, then decide with me which context-engine task the autopsy ranks first.

---

## Task Dependency Graph

```json
{
  "waves": [
    {
      "name": "Narrative",
      "tasks": ["290"],
      "description": "The candle narrative, the price basis, the import guard"
    },
    {
      "name": "Autopsy",
      "tasks": ["291", "292"],
      "description": "The trade autopsy, its report and commands",
      "dependencies": ["Narrative"]
    },
    {
      "name": "Reference runs",
      "tasks": ["293"],
      "description": "The autopsy of WICK, BODY and the baseline; your review",
      "dependencies": ["Autopsy"]
    }
  ]
}
```

---

## Notes

- Every implementation task follows RED → GREEN → REFACTOR. No production code without a failing test first.
- Hypothesis property tests run with `@settings(max_examples=100)` at least.
- The narrative is hindsight. Nothing that decides imports it (Requirement 5); a finding becomes a rule only through a hypothesis or a backtest variant.
- No new dependencies.
