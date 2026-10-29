# Implementation Plan

**spec**: Algo Mind

## Overview

- **Numbering:** tasks continue the platform sequence from **382**.
- **TDD:** every code task follows RED → GREEN → REFACTOR. Tests live in `backend/tests/test_algo_mind_*.py`.
- **Paper only:** nothing here places a live order.

---

## Tasks

- [ ] 382. The brain and its versions (Requirement 2)
  - **382a. RED:**
    - a version fitted twice on the same rows gives the same probabilities;
    - its thresholds are its training probabilities' thirds;
    - its meta holds the window, features, settings, thresholds and commit;
    - a loaded version predicts as the fitted one.
  - **382b. GREEN:** `algo_mind/brain.py`; `python -m algo_mind fit` fits v1 on Yahoo's weeks before 2023-01-01.

- [ ] 383. The live senses and memory (Requirements 1.2-1.3, 3)
  - **383a. RED:**
    - the live state of a week reads only days before its Monday and before the run's day;
    - a week missing its Friday is provisional;
    - the analogs are 20 training weeks, the nearest on the z-scores, with their outcomes.
  - **383b. GREEN:** `algo_mind/sources.py` and `algo_mind/memory.py`.

- [ ] 384. The brief and the thesis files (Requirements 4.1, 5.1)
  - **384a. RED:**
    - a brief holds every market's state, probability, call, analogs and provisional flag;
    - it writes the brain's thesis file with its calls for every trading date of the week;
    - the agreement's file holds only the markets where the trader and the brain agree, with the trader's levels.
  - **384b. GREEN:** `algo_mind/brief.py`; `python -m algo_mind brief --week`.

- [ ] 385. The brain on the context page (Requirements 4.2-4.3)
  - The brain's call, probability and the analogs' up share beside the trader's call. The scorecard scores the brain and the agreement too.

- [ ] 386. The hands (Requirements 5.2-5.3)
  - `fresh_near_gap_brain` and `fresh_near_gap_agree`, and their paper agents.

- [ ] 387. The bench and the third look (Requirements 6, 7.3)
  - The random-walk false-alarm rate and the planted effect's detection rate at H-Y's sample sizes; the brain's calls on the readable weeks of 2026.

- [ ] 388. The learning ledger (Requirement 7.1-7.2)
  - A refit is a candidate; it's judged on the weeks after it against the version in use, and every refit and judgement is logged.
