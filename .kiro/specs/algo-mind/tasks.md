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

- [ ] 385. The brain on the context page (Requirements 4.2-4.3)
  - The brain's call, probability and the analogs' up share beside the trader's call. The scorecard scores the brain and the agreement too.

- [ ] 386. The hands (Requirements 5.2-5.3)
  - `fresh_near_gap_brain` and `fresh_near_gap_agree`, and their paper agents.

- [ ] 387. The bench and the third look (Requirements 6, 7.3)
  - The random-walk false-alarm rate and the planted effect's detection rate at H-Y's sample sizes; the brain's calls on the readable weeks of 2026.

- [ ] 388. The learning ledger (Requirement 7.1-7.2)
  - A refit is a candidate; it's judged on the weeks after it against the version in use, and every refit and judgement is logged.
