# Implementation Plan

**spec**: Thesis Engine

## Overview

- **Numbering:** tasks continue the platform sequence from **408**.
- **Order:** the audit and the spec; the thesis; the clock; the book; the machine; the replay; watching it with the trader; H-AG registered, then run; paper only after a pass and the trader's go.
- **Order changed 2026-11-05:** the trader asked to test the engine first ("test the new engine"), so H-AG (415) runs before the Noculus review (414). V1 is frozen at the defaults for H-AG; a change after the review is V2 and a new registration.
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

- [x] 409. Phase 1: the settings, the records and the thesis (Requirements 1.4, 4)
  - **Done 2026-11-05** (the trader: "test the new engine"; the tests were written with the code, not before it).
    - `thesis_engine/__init__.py`, `settings.py` (V1: the defaults put to the trader), `records.py` (Thesis, Level, Hand, Intent, Skip, Transition; ids and JSON are AlgoMindDIS's) and `thesis.py`.
    - Ends in AlgoMindDIS's order: INVALIDATED (a D1 close), DELIVERED, then `until` (EXPIRED, or WITHDRAWN for a file). REPLACED happens in the machine.
    - Sources: CALL (`agent.context_calls`), FILE (consecutive dates joined), and ORACLE, MIRROR, RANDOM and W1TREND (the last W1 candle's LE-D15 trend), each completed by the nearest-pool rule.
    - Tests: `test_thesis_engine_thesis.py` (8).
  - **Moved to 417:** the DIS source and the activation modes.
  - **Validates: Requirements 1.4, 4.1-4.5**

- [x] 410. Phase 2: the clock (Requirement 2)
  - **Done 2026-11-05.** `thesis_engine/clock.py`:
    - W1, D1, H4, H1 and M5 from M1 on the market's New York calendar (17:00 for FX, gold and DXY; 18:00 for the indices);
    - a candle exists from its close, and one still forming at the end is left out;
    - repeated or older bars and leading stand-ins are dropped and counted;
    - the window (Q2-Q3, Monday to Friday) and the trading day;
    - the first candle after a silence of more than 15 minutes inside the day is stale.
    - Tests: `test_thesis_engine_clock.py` (7).
  - **Moved to 416 (paper):** stopping and resuming from a saved state. The replay reads only the past (Property 1, tested in 413); a saved state matters for a live agent.
  - **Validates: Requirement 2.1-2.3, 2.5**

- [x] 411. Phase 3: the book, as of each close (Requirement 3)
  - **Done 2026-11-05.**
    - `thesis_engine/book.py`. Each level frame's arrays come from AlgoMindDIS's `array_table` at V2 (the trader's blocks and breakers, FVGs as the gap), with their high-probability grade from `blocks.delivery_blocks`. Swings and SWING ranges are the analyzers'. The E frame's three-candle swings, the pools each candle takes, the previous H1 candle's pool and the CISD come from `blocks.runs`.
    - `liquidity_engine/context/inversions.py`: inverted FVGs, dated by the close through, ended like any array. Nothing existing calls it.
    - Tests: `test_thesis_engine_book.py` (7), with the book at random cuts equal to the analyzers run on the cut (Property 4), and the pools and CISD against brute force; `test_context_inversions.py` (3).
  - **Validates: Requirement 3.1-3.5**

- [x] 412. Phase 4: the machine (Requirements 5-9)
  - **Done 2026-11-05.**
    - `thesis_engine/levels.py`: the side's live arrays between the protected level and the draw, CE in discount (premium) of the D1 or W1 SWING range, at most 1 ADR tall, scored by frames, ranges, resting liquidity and a high-probability block.
    - `thesis_engine/machine.py`: `TABLE`, `State`, `on_close` and `on_fill`. Every move is checked against the table.
    - The table gained two rows the requirements lacked: ARMED → THESIS (the level fails or price leaves it while armed) and IN_TRADE → AT_LEVEL (a rejected order).
  - **Validates: Requirements 5.1-5.4, 6.1-6.3, 7.1-7.2, 8.1-8.4, 9.1-9.5**

- [x] 413. Phase 5: the journal and the replay (Requirements 10, 11)
  - **Done 2026-11-05.**
    - `thesis_engine/replay.py`: the loop through the shared `FillModel` (an order acts from the next bar). Spreads follow H-N's rule, stop slippage comes from the Exness specs, and the swap-free account charges no commission or swap. A position open at its thesis's `until` is closed at the last bar before it (TIME).
    - The journal is JSON lines with sorted keys; `python -m thesis_engine replay MARKET --snapshot NAME --source ...` refuses the development window.
    - Speed: about 1.5 s a run on eight months of gold M1, after a 5 s build of the book.
    - Tests: `test_thesis_engine_machine.py` (8) on random-walk markets with the hindsight side:
      - the stages are reached;
      - every move is in the table (Property 6);
      - the side is the thesis's, one position at a time (Property 7);
      - the budget holds (Property 8);
      - a stop without a gap is −1R;
      - the same journal twice (Property 2);
      - only the past (Property 1);
      - the mirror (Property 5).
  - **A bug the October 2026 dry run caught:** an intent's own `kind` field overwrote the journal's record type, so intents were invisible and one test passed on an empty list. The discriminator is now `record`, and the test asserts it saw intents.
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
  - **Built 2026-11-05, awaiting the trader's review:**
    - **The layer:** `WatchSession.thesis` and `/api/watch/thesis` (`algo_backtester/watch.py`), and the "Thesis Engine" layer, card and source menu in `engine.js`. The sources: your calls from your notes, your /context calls, the week's real side, its opposite, a coin flip, or the last W1 trend. Hidden while blind. The journal now records each level's geometry when it is reached.
    - **The scenarios:** `thesis_engine/scenarios.py` and `python -m thesis_engine scenarios`, on a fresh terminal export (`mt5-m1-2026-11`, M1 from 15 Feb to 5 Nov 2026, nine markets). The six calls, read from the trader's notes and not yet confirmed, sit in their git-ignored journal (`data/journal/thesis_engine/scenarios.json`); the report is local (`data/research/thesis_engine/scenarios.md`).
    - **First read of the scenarios:**
      - gold 14 Oct is taken almost as the trader took it (+20.9R);
      - GBPUSD 29 Oct and US500 14 Oct are entered on an earlier M5 sweep, stopped by the real manipulation, and then the day's budget is spent;
      - UK100's H1 FVG fails the discount test by a hair;
      - three draws, set at the trades' targets, are delivered before any level forms.
    - Tests: `test_thesis_engine_watch.py` (5).
  - **Open:**
    - **Noculus can't open October 2026 yet.** Sessions there run the old engine's backtest inside its study's hold-out (from 2026-07-07). Treating the recent months like a live session (D40) is the trader's call.
    - The calls need the trader's confirmation.
  - **Validates: Requirement 12.1-12.2**

- [x] 415. Phase 7: H-AG, registered, then run (Requirement 13)
  - **Done 2026-11-05: H-AG passes** (registered in b88c70a before it ran).
    - ORACLE: +0.841R a trade [+0.461, +1.256] on 412 trades, 7 of 8 markets positive (UK100 had none: every M5 stop was under 10 spreads).
    - Break-even weekly hit rate: 49.4% a trade, 58.3% a week.
    - MIRROR −0.821, RANDOM −0.072, W1TREND +0.021.
    - The existing setup engine and AlgoMindDIS V1 as a source, §16.4's other baselines, are not built yet.
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
  - Stopping and resuming from a saved state (Requirement 2.4, Property 3), moved here from 410.
  - **Started 2026-11-05** (the trader: "Run the engine please"; H-AG had passed):
    - `thesis_engine/live.py`, `python -m thesis_engine live [--once] [--every 300]`. Each cycle it reads the /context calls, and for each market with a call live (or ended within a day) reads the terminal's closed M1 (150 days, then only the new minutes) and runs the machine from the start: a restart is a replay. The journal and `status.json` go in `data/research/thesis_engine/live/`.
    - Paper only: the shared fill model on the terminal's bars, nothing sent to the broker. A market without a call isn't read.
    - Tests: `test_thesis_engine_live.py` (2), with a fake terminal.
    - **First run (12:18, 5 Nov 2026): FLAT on all eight markets.** No /context calls were logged, and AlgoMindDIS V2 held no side on any of them.
  - **Still to do:** the record beside the context agent's on the /context scorecard (14.2); the DIS source (417).
  - **Validates: Requirement 14.1-14.2, 2.4**

- [ ] 417. The DIS source and the activation modes (Requirements 4.3 DIS, 4.6)
  - Moved from 409.
  - AlgoMindDIS's timeline as theses: ACTIVE gives a thesis (`thesis_entry`'s side, draw, protected level and since), TRANSITIONAL arms nothing, and the other states end it (WITHDRAWN).
  - The modes DIS_DISABLED, DIS_SHADOW, DIS_ADVISORY and DIS_ENFORCED.
  - **Validates: Requirements 4.3, 4.6**

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
