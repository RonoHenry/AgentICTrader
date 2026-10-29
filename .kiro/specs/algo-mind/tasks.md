# Implementation Plan

**spec**: Algo Mind

## Overview

- **Numbering:** tasks continue the platform sequence from **382**.
- **TDD:** every code task follows RED → GREEN → REFACTOR. Tests live in `backend/tests/test_algo_mind_*.py`.
- **Paper only:** nothing here places a live order.

---

## Tasks

- [x] 382. The brain and its versions (Requirement 2)
  - **382a. RED:**
    - a version fitted twice on the same rows gives the same probabilities;
    - its thresholds are its training probabilities' thirds;
    - its meta holds the window, features, settings, thresholds and commit;
    - a loaded version predicts as the fitted one.
  - **382b. GREEN:** `algo_mind/brain.py`; `python -m algo_mind fit` fits v1 on Yahoo's weeks before 2023-01-01.
  - **Done 2026-10-29.**
    - v1: 13,092 weeks, 1981-04-06 to 2022, nine markets, thirds at 0.4812 and 0.5187.
    - The states are cached at `data/algo_mind/states_to_2022.parquet`.
    - Tests: `test_algo_mind_brain.py` (2).

- [x] 383. The live senses and memory (Requirements 1.2-1.3, 3)
  - **383a. RED:**
    - the live state of a week reads only days before its Monday and before the run's day;
    - a week missing its Friday is provisional;
    - the analogs are 20 training weeks, the nearest on the z-scores, with their outcomes.
  - **383b. GREEN:** `algo_mind/sources.py` and `algo_mind/memory.py`.
  - **Done 2026-10-29.**
    - `search_state.week_state` is the per-week reading, shared by training and live; H-Y's table is unchanged (checked on EURUSD and US500).
    - Live, a month still running at the Monday isn't a closed candle, as in training.
    - The last closed FX day closes at the last price.
    - Tests: `test_algo_mind_senses.py` (3), including live = training on mid-month and month-turn weeks, and nothing read from the week on.

- [x] 384. The brief and the thesis files (Requirements 4.1, 5.1)
  - **384a. RED:**
    - a brief holds every market's state, probability, call, analogs and provisional flag;
    - it writes the brain's thesis file with its calls for every trading date of the week;
    - the agreement's file holds only the markets where the trader and the brain agree, with the trader's levels.
  - **384b. GREEN:** `algo_mind/brief.py`; `python -m algo_mind brief --week`.
  - **Done 2026-10-29.**
    - Tests: `test_algo_mind_brief.py` (2).
    - The first real brief, for the week of 2026-11-02, was made Thursday 29 Oct and is provisional (last day 28 Oct).
      - **Calls:** DXY, EURUSD, GBPUSD, US500, US30 and GER40 BULLISH; XAUUSD BEARISH; US100 and UK100 NONE.
      - DXY and the euro and pound all up is the brain reading each market alone. It needs re-running after Friday's close.

- [x] 385. The brain on the context page (Requirements 4.2-4.3)
  - The brain's call, probability and the analogs' up share beside the trader's call. The scorecard scores the brain and the agreement too.
  - **Done 2026-10-29.**
    - The view carries the week's brief and coherence notes: DXY called the same way as EURUSD, GBPUSD or gold, and the US indices called apart.
    - "Run the brain" (`POST /api/context/brief`) makes the brief again, and saving a call rewrites the agreement file.
    - The scorecard keeps rows the brain called but the trader didn't, and totals the trader, the brain and the agreement.
    - `agent.context_calls.week_move` is shared by both.
    - **The thesis reader's cache key** now includes the file's identity. In-place same-size rewrites could serve stale content, and task 351's test was flaky for that reason.
    - Tests: `test_algo_mind_context.py` (3).

- [x] 386. The hands (Requirements 5.2-5.3)
  - `fresh_near_gap_brain` and `fresh_near_gap_agree`, and their paper agents.
  - **Done 2026-10-29.**
    - Both differ from `fresh_near_gap_context` only in their thesis file (test: `test_the_hands_differ_from_the_context_variant_only_in_their_thesis_file`).
    - Their records (`data/paper_trades_fresh_near_gap_brain.json`, `..._agree.json`) join the scorecard's agents.
    - The two paper agents started 2026-10-29 on the controls' eight markets. With the brain's first calls dated 2 November, they order nothing before then.

- [x] 387. The bench and the third look (Requirements 6, 7.3)
  - The random-walk false-alarm rate and the planted effect's detection rate at H-Y's sample sizes; the brain's calls on the readable weeks of 2026.
  - **Done 2026-10-29** (`algo_mind/bench.py`, tests `test_algo_mind_bench.py` (2)).
    - **Random walks** (each market's dates, volatility and day ranges, no drift), 20 runs: the judged thirds averaged +0.27 pts (sd 1.31).
      - None reached H-Y's +2.9, and 1 in 20 passed H-Y's rule.
      - The walks move independently, while real markets move together and have fat tails, so the real chance spread is wider.
    - **A planted 5-point lean** (up in the bottom third of the 26-week range, down in the top third), 10 runs: +4.59 pts (sd 0.98), and every run passed.
      - Its absolute hit rate was only 53-55%, so a real, detectable weekly lean of 5 points still falls short of the 57-60% the trades need.
    - **Third look** (brain v1 on the 261 whole weeks its live senses read, 2026-04-06 to 2026-10-19): thirds +0.2 pts [−9.0, +9.2] (174 calls), every week +0.9 [−5.8, +7.8]. Too few weeks to tell.

- [x] 388. The learning ledger (Requirement 7.1-7.2)
  - A refit is a candidate; it's judged on the weeks after it against the version in use, and every refit and judgement is logged.
  - **Done 2026-10-29** (`algo_mind/ledger.py`, tests `test_algo_mind_ledger.py` (2)).
    - `python -m algo_mind refit --version vN` fits a candidate on the history before 2023 plus the live weeks since 2025.
    - `python -m algo_mind judge --candidate vN` compares it with the version in use, on the weeks after its window (at least 150 calls each). It adopts, keeps or waits.
    - The brief uses the version in use. The ledger opens with v1's fit and adoption.
