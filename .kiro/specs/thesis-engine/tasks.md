# Implementation Plan

**spec**: Thesis Engine

## Overview

- **Numbering:** tasks continue the platform sequence from **408**.
- **Order:** the audit and the spec; the thesis; the clock; the book; the machine; the replay; watching it with the trader; H-AG registered, then run; paper only after a pass and the trader's go.
- **TDD:** every code task follows RED → GREEN → REFACTOR. Tests live in `backend/tests/test_thesis_engine_*.py`.
- **The development window stays unread:** nothing reads `mt5-m1-develop` before H-AG's registration commit (TE-D14).
- **Paper only, and later:** nothing here places a live order (Requirement 1.3).
- **One commit per task**, pushed to the open PR.

## Tasks

- [x] 408. Phase 0: the audit and this spec (Requirement 1)
  - The requirements, the design with the Phase 0 table, and this plan.
  - The decisions for the trader are listed in design.md. Defaults stand until they answer.
  - **Amended the same day, before any code** (the trader: AlgoMindDIS's specification must hold). The engine is AlgoMindDIS's Setup Engine:
    - it reads the contract as a source (DIS, with the activation modes);
    - it detects nothing itself: the book is an as-of view over AlgoMindDIS's analyzers;
    - it handles the live feed (§13.3);
    - H-AG reports §16.4's baselines beside it.
  - **Validates: Requirement 1.1**

- [ ] 409. Phase 1: the settings, the records and the thesis (Requirements 1.4, 4)
  - **409a. RED:**
    - each record round-trips through JSON, and its id is the same for the same content;
    - V1 is frozen;
    - the thesis's checks;
    - each end (DELIVERED, INVALIDATED, EXPIRED, REPLACED), with a wick beyond the protected level that isn't one;
    - CALL reads `agent.context_calls` and FILE reads the THESIS-mode format;
    - the completion rule's choices and refusals;
    - ORACLE and MIRROR are opposite every week, and RANDOM is the same for the same seed;
    - the DIS source: ACTIVE gives a thesis, TRANSITIONAL arms nothing, and the other states end it (WITHDRAWN), under each activation mode.
  - **409b. GREEN:** `thesis_engine/__init__.py`, `settings.py`, `records.py` and `thesis.py`.
  - **Validates: Requirements 1.4, 4.1-4.6**

- [ ] 410. Phase 2: the clock (Requirement 2)
  - **410a. RED** on hand-made M1 bars:
    - D1 from 17:00 for FX and gold, and from 18:00 for the indices;
    - H4 every four hours from the day's open;
    - W1 from Sunday's open to Friday's close;
    - daylight-saving changes;
    - no candle for a gap;
    - each candle emitted once at its close, highest frame first;
    - stop and resume equal an uncut run;
    - repeated and out-of-order bars are dropped, the forming bar is never read, and stale data is flagged.
  - **410b. GREEN:** `thesis_engine/clock.py`.
  - **Validates: Requirement 2.1-2.5**

- [ ] 411. Phase 3: the book, as of each close (Requirement 3)
  - **411a. RED:**
    - at every cut of random walks with dojis, the book equals AlgoMindDIS's analyzers (V2) run on the candles closed by the cut;
    - each status change (formed, swept or mitigated, invalidated) is recorded once, with its time;
    - the E frame's swings and down-close runs;
    - the inverted FVG on hand-made bars, in the array layer's own tests (`liquidity_engine/context`), with every existing output unchanged.
  - **411b. GREEN:** `thesis_engine/book.py`, and the inverted FVG in the array layer.
  - **Validates: Requirement 3.1-3.5**

- [ ] 412. Phase 4: the machine (Requirements 5-9)
  - **412a. RED:**
    - each row of the transition table with its reason, and no other transition (every state against every event kind);
    - the levels of the side: inside the thesis's range, in discount, at most 1 ADR tall, never the other side's arrays, with the score;
    - the window;
    - the hand: the sweep at the level, the CISD within 12 E candles, its failure;
    - the order: stop, target, the skips (under 10 spreads, under 2R) and the budget;
    - mirrored bars give the mirrored transitions.
  - **412b. GREEN:** `thesis_engine/levels.py`, `machine.py` and `orders.py`.
  - **Validates: Requirements 5.1-5.4, 6.1-6.3, 7.1-7.2, 8.1-8.4, 9.1-9.5**

- [ ] 413. Phase 5: the journal and the replay (Requirements 10, 11)
  - **413a. RED:**
    - the loop's order: fills, then closes, highest frame first;
    - orders act from the next bar, through the shared `FillModel`;
    - costs follow H-N's spread rule and the broker profile;
    - the same bars and theses give the same journal byte for byte;
    - a stopped and resumed run equals an uncut one;
    - hand-made and October 2026 bars only.
  - **413b. GREEN:** `thesis_engine/journal.py`, `replay.py` and `__main__.py` (`python -m thesis_engine replay`, with a speed check on one market).
  - **Validates: Requirements 10.1-10.3, 11.1-11.3**

- [ ] 414. Phase 6: watching it, with the trader (Requirement 12)
  - **The layer:** "Thesis Engine" on the Noculus engine chart:
    - the thesis's draw and protected level;
    - the side's levels, with the one in use highlighted;
    - the state strip and the transition marks with their reasons;
    - each hand's sweep and CISD;
    - the trades.

    It goes in `algo_backtester/watch.py` (a route beside `/api/watch/dis`) and `algo_research/replay/static/engine.js`.
  - **The scenarios:** the trader's October 2026 trades, each with the call they held:
    - UK100 15 Oct, XAUUSD 5 and 14 Oct, and the US500 read of 14 Oct, from `mt5-m1-2026-10`;
    - EURUSD 12 Oct and GBPUSD 29 Oct, from a terminal export;
    - the trader is asked for any call their notes don't give.
  - **The review:** the trader judges the layer. Changes to the definitions happen here. At the end of the review V1 is frozen (TE-D13).
  - **Validates: Requirement 12.1-12.2**

- [ ] 415. Phase 7: H-AG, registered, then run (Requirement 13)
  - **415a.** H-AG registered in `docs/research/SEARCH_2018_2024.md` with V1's settings, in its own commit, before anything reads `mt5-m1-develop`.
  - **415b.** The run:
    - ORACLE, MIRROR and RANDOM on the eight traded focus markets, 2021-07-16 to 2022-12-30;
    - the pass rule, and everything reported beside it, with AlgoMindDIS §16.4's baselines:
      - the existing setup engine, without a side and with the same sides;
      - a simple W1-trend side;
      - AlgoMindDIS V1 as the source.

    The report goes to `docs/research/THESIS_ENGINE_HAG.md`, with a line in the search log.
  - **Validates: Requirement 13.1-13.5**

- [ ] 416. Phase 8: paper with the trader's calls (Requirement 14)
  - Only if H-AG passes and the trader says go.
  - A paper agent runs the same `step` on the terminal's live M1, through the paper broker. Its source is the /context calls, or AlgoMindDIS in the trader's mode.
  - Its record goes beside the context agent's on the /context scorecard.
  - **Validates: Requirement 14.1-14.2**

## Task Dependency Graph

Dependencies are denoted as `prerequisite → dependent`. The trader's answers to design.md's decisions are needed by 412 (the machine) and close at 414 (V1 frozen).

```json
{
  "waves": [
    {
      "name": "Spec",
      "tasks": ["408"],
      "description": "The audit and this spec; the decisions put to the trader"
    },
    {
      "name": "Foundations",
      "tasks": ["409", "410"],
      "description": "The settings, records and thesis; the clock",
      "dependencies": ["Spec"]
    },
    {
      "name": "The book",
      "tasks": ["411"],
      "description": "Pools, arrays and ranges with a life, equal to the batch rules",
      "dependencies": ["Foundations"]
    },
    {
      "name": "The machine",
      "tasks": ["412"],
      "description": "Levels, time, the hand, risk and the budget; the trader's answers",
      "dependencies": ["The book"]
    },
    {
      "name": "The replay",
      "tasks": ["413"],
      "description": "The journal and the loop through the shared fill model",
      "dependencies": ["The machine"]
    },
    {
      "name": "The trader's review",
      "tasks": ["414"],
      "description": "The Noculus layer and the scenarios; V1 frozen",
      "dependencies": ["The replay"]
    },
    {
      "name": "H-AG",
      "tasks": ["415"],
      "description": "Registered, then run on the development window",
      "dependencies": ["The trader's review"]
    },
    {
      "name": "Paper",
      "tasks": ["416"],
      "description": "Only after a pass and the trader's go",
      "dependencies": ["H-AG"]
    }
  ]
}
```

## Notes

- Every implementation task follows RED → GREEN → REFACTOR. No production code without a failing test first.
- Property tests run with `@settings(max_examples=100)` at least. The slow ones are marked `slow`.
- No new dependencies.
- AlgoMindDIS's specification (v1.0.0) holds: the engine detects nothing itself (§19.2), takes its side only from a source (§2.5), and changes no existing output (§19.1, §19.8).
- `liquidity_engine/`, `algo_backtester/` (apart from the layer's route), `agent/` and `algomind_dis/` don't change. The paper agents keep running on the old engine.
- Nothing reads `mt5-m1-develop` before H-AG's registration commit. Runs go one market at a time (the PC's memory limits).
- The trader's journal and `docs/research/THESIS_METHOD.md` stay out of the repo.
