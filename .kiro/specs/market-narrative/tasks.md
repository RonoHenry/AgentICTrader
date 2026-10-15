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
  - **Done 2026-10-12; waiting for your review.**
    - `docs/backtests/AUTOPSY.md` is written. `trading-method.md`, section 8, cites it.
    - Headline: the rewrite fixed execution. Right-direction fills on time make +1.7 to +1.8R in WICK and BODY, against −0.46R in the baseline. Direction is what's left: 45–46% with the day, and a third of trades fade the day's expansion (−187R BODY, −171R WICK; re-run 2026-10-13 after the price-basis fix).
  - Run `python -m algo_backtester autopsy` on WICK `ec4876ba87a1`, BODY `475491a89d91` and the baseline `5d241691c701`.
  - Write `docs/backtests/AUTOPSY.md`:
    - each run's split by failure mode;
    - the with-candle failures;
    - the raid side and the as-of shape;
    - what each finding points to in the engine: context-engine Requirement 4 (direction), Requirement 6 (selection) and Requirement 7 (targets).
  - Update `trading-method.md`, section 8, to cite it.
  - You review, then decide with me which context-engine task the autopsy ranks first.

- [x] 299. The blind replay: bars, journal and scores (`algo_research/replay/`)
  - Added 2026-10-14 (Requirement 10). `ReplayBars.as_of`, `Journal` with its state rules and atomic files, `score_thesis`, `score_trade`, `summarize`.
  - **RED:** perturbing every M1 bar after `until` leaves `as_of` unchanged; the forming bar equals the closed bar at its period's end; a read is refused after it is saved and every write after the reveal; reads that break 10.3 are refused naming the field; `revealed_until` is monotone and capped; trades are refused unless stop and target straddle the entry; thesis outcomes, including the same-bar tie and `p_coin`; trade outcomes; days resume and skip revealed ones.
  - **Validates: Requirements 10.1-10.9**

- [x] 300. The replay page and its server (`algo_research/replay/server.py`, `static/index.html`, `__main__.py`)
  - `ReplayApp` and the HTTP handler; `python -m algo_research.replay`; `data/journal/` added to `.gitignore`.
  - **RED:** an HTTP round trip on a synthetic instrument: state, bars as of the open, read, advance, trade, reveal, a refused second read (409), summary.
  - **Validates: Requirements 10.1-10.6, 10.9**

- [x] 303. The replay chart (Requirement 11)
  - Added 2026-10-14 at the trader's request: TradingView-like reading and marking, the day printing live, the trader's timeframes.
  - `timeframes.py`; `ReplayBars.as_of(tf, until, since)` and `next_open`; drawings, narrative and live trades in the journal; `/api/meta`, `update` on advance, `/api/drawings`, `/api/narrative`; `static/drawings.js`, `app.js`, `app.css`.
  - **RED:** bars anchored at the New York open (H4, H7, H12, M45, M20, D1, W1, MN1); the same bars as the strategy calendar for M5, M15, H1, H4, D1; `since`; drawings checked, stamped and copied into the read and the reveal; the narrative only after the reveal; trades followed live; a step into the gold pause lands past the reopen; the HTTP round trip with the new endpoints and static files.
  - **Validates: Requirements 11.1-11.7**

- [x] 304. Chart settings, favourites and more tools (Requirement 12)
  - Added 2026-10-14 at the trader's request ("TradingView's free tier plus our own"). TradingView's chart itself can't be embedded: its library is licensed to companies for public products, and the free widget can't replay our data or hand back the drawings.
  - `static/settings.js` (preferences in this browser, the drawing and chart settings dialogs, context menus, the object list); `drawings.js` v3 (a look per drawing from type defaults, the trader's saved default and its own style; ray, extended line, arrow, channel, fib extension, range, brush; lock, hide, clone, Shift-drag measure); `app.js` (timeframe and tool favourites, the favourites bar, sessions layer: day separators, day and midnight opens, killzone shading). The server keeps a drawing's `style`, coloured fib `levels`, `locked`, and paths of 2 to 400 points.
  - **RED:** `test_drawings_take_a_style_coloured_levels_and_freehand_paths`; the HTTP round trip serves `settings.js`; the browser walk-through (scratchpad `uitest/ui.js`) covers every step of Requirements 11 and 12 with no console errors.
  - **Validates: Requirements 12.1-12.6**

- [x] 306. A chart that moves freely (Requirement 13)
  - Added 2026-10-15 at the trader's request: "unlock price to bar ratio ... makes the charting intuitive".
  - `static/motion.js`, shared by both pages:
    - a manual price range kept by the series' autoscale provider;
    - a vertical pan and price-axis stretch;
    - the **A** button, lock price to bar ratio, and the bar countdown on the price scale.
  - Drawings restore the chart's scroll and scale options after a drag, instead of switching them all back on.
  - **RED:** the browser walk-throughs. A diagonal drag moves time and price and turns auto-fit off; **A** fits again; with the ratio locked, zooming time zooms price; the countdown follows the replay clock; a timeframe change keeps the manual range. No console errors.
  - **Validates: Requirements 13.1-13.4**

- [x] 307. Visibility intervals (Requirement 14)
  - Visibility is kept on the drawing (`journal._visibility` checks it). `Drawings` shows a drawing only on timeframes inside its intervals, and the drawing dialog gets a Visibility tab. The engine layer uses intervals per array timeframe, with defaults.
  - **RED:** `test_drawings_keep_visibility_intervals`; the walk-throughs check that an H4-only box hides on M15 and shows on H4, and that an engine M15 array hides on H4.
  - **Validates: Requirements 14.1-14.3**

- [x] 309. One chart, two analysts (Requirement 15)
  - `replay/charts.py`: one server for both modes, You at `/` and Engine at `/engine`.
    - A blind journal per instrument, opened when its tab is first chosen; the replay API takes `?inst=`.
    - `/api/instruments`.
    - `/api/watchlist`: the You mode names its instrument and the server reads that day's revealed time; the Engine mode names `t`, held to the session's end. No time is returned, so the blind day stays unnamed.
    - `/api/blind`: a session's days still unread in the blind journal (`Journal.unrevealed`).
  - `python -m algo_research.replay` (port 8765) and `python -m algo_backtester watch` (8767, opening on Engine) both serve it.
  - `static/shell.js`: the mode switch, the instrument tabs (with each one's change) and the watchlist, for both pages.
    - A You tab opens that instrument's own blind day.
    - An Engine tab runs the same days on the other instrument. The watch keeps its last three sessions, so going back is instant.
  - **RED:** `test_the_charts_serve_both_modes`, `test_the_watchlist_never_shows_a_price_after_the_clock`, `test_the_you_mode_watchlist_is_read_at_its_days_clock_and_names_no_time`, `test_each_instrument_has_its_own_blind_journal`, `test_the_engine_mode_is_warned_of_days_still_unread_in_the_blind_replay`, `test_a_watch_session_is_kept_for_its_tab`.
  - The walk-through (scratchpad `uitest/charts_ui.js`) covers:
    - tabs and watchlist;
    - the You mode makes no engine call;
    - a tab's own blind day;
    - the watchlist follows play;
    - the Engine mode keeps the instrument and warns of unread days;
    - a session, a tab to another instrument and back in under a second.
    Every earlier walk-through passes on the merged server.
  - **Validates: Requirements 15.1-15.3**

- [ ] 301. Pilot: 50 blind gold days **(user action)**
  - You read 50 exploration-slice gold days; then we look at the summary together, and at the days where your thesis and the engine's candle profile disagreed.

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
    },
    {
      "name": "Blind replay",
      "tasks": ["299", "300", "303", "304", "306", "307", "309", "301"],
      "description": "The trader's blind daily reads, scored (update 2026-10-14)",
      "dependencies": ["Narrative"]
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
