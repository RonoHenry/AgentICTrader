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

- [x] 418. V2 written up and H-AH registered (Requirements 15, 16)
  - The trader (2026-11-05): "please", for writing V2 up and registering it.
  - Requirements 15-16, design.md's update (TE-D18 to TE-D23), and H-AH registered in `docs/research/SEARCH_2018_2024.md` before V2's code exists.
  - **Validates: Requirements 15, 16.1**

- [x] 419. V2 built (Requirement 15)
  - Built 2026-11-05: `backend/tests/test_thesis_engine_v2.py`. V1's journals are byte for byte the same on a synthetic walk and on gold's October 2026 month (ORACLE, MIRROR, W1TREND).
  - The mirror test found V1's tie-break by content id; V2 breaks ties by frame (TE-D24, Requirement 15.7), an amendment to H-AH made before it ran.
  - **419a. RED:**
    - V1's journals are unchanged on the same bars and theses;
    - the trader's pools (PDL, the Asia low, the previous H4 and H1 lows, untaken H1 swing lows) and no M5 swing;
    - the displacement test;
    - the limit at the run's MT with its expiry, and an expired limit back at AT_LEVEL without using the budget;
    - the stack gate;
    - mirrored bars give the mirrored journal.
  - **419b. GREEN:** `settings.V2` and the machine, the levels and the replay reading it.
  - **Validates: Requirement 15.1-15.7**

- [x] 420. H-AH run on development (Requirement 16)
  - The four arms with V2, V1 beside it, the companion with the partial.
  - The report goes to `docs/research/THESIS_ENGINE_HAH.md`, with a line in the search log.
  - If it passes: the test window's export and one run.
  - Run 2026-11-06 (runner 3318f67): **H-AH FAILS.**
    - V2 with the week's real side: +0.574R a trade [−0.352, +1.655] on 67 trades, positive in 4 of 8 markets.
    - Weekly break-even 71.2%, against V1's 58.3%.
    - V1, rerun, matches H-AG exactly. V1 stays the machine, and the test window stays closed.
  - **Validates: Requirement 16.2-16.5**

- [x] 421. V3 written up and H-AI registered (Requirements 17, 18)
  - The trader (2026-11-06):
    - "the engine has to be dynamic then, we can execute anywhere from the M30, M20, M15, M10, M5, M3, M1";
    - the frame is the child of the swept pool's;
    - market near the entry level, a limit when price has traded away.
  - Requirements 17-18, design.md's update (TE-D25 to TE-D30), and H-AI registered in `docs/research/SEARCH_2018_2024.md` before V3's code exists.
  - **Validates: Requirements 17, 18.1**

- [x] 422. V3 built (Requirement 17)
  - Built 2026-11-06: `backend/tests/test_thesis_engine_v3.py` (10). V1's and V2's journals are byte for byte the same on the walks and on gold's October 2026 month (8 fingerprints).
  - On the walks every V3 entry is a limit: after a 1.5 average-range displacement the close sits more than half an average range from the run's MT unless the run itself is big.
  - **422a. RED:**
    - V1's and V2's journals are unchanged on the same bars and theses;
    - the execution frames from M1;
    - each pool's child frame, with M30 and M15 swings as pools;
    - a larger pool takes a waiting hand over;
    - the CISD on the child (the run may end one candle before the sweep's), with displacement in the child's average range;
    - market near the MT, a limit when price is away;
    - mirrored bars give the mirrored journal.
  - **422b. GREEN:** `settings.V3`, the clock's frames, the book's execution frames and the machine reading them.
  - **Validates: Requirement 17.1-17.7**

- [x] 423. H-AI run on development (Requirement 18)
  - The four arms with V3; V1 and V2 beside it from H-AH's run.
  - The report goes to `docs/research/THESIS_ENGINE_HAI.md`, with a line in the search log.
  - If it passes: the test window's export and one run.
  - Run 2026-11-06 (runner 6a75578): **H-AI FAILS.**
    - V3 with the week's real side: +0.614R a trade [−0.240, +1.658] on 69 trades, positive in 3 of 8 markets.
    - Weekly break-even 77.4%.
    - Every entry was a limit, and wrong-side limits filled more often (66% against 44%).
    - Read after the run: the M30 and M20 hands made +1.33R a trade with the right side, and every H1 → M5 hand lost on either side. V1 stays the machine.
  - **Validates: Requirement 18.2-18.5**

- [ ] 424. V3 on Noculus beside V1 and V2
  - The layer's version menu gains V3. The card names each order's frame and whether it went at market or as a limit.
  - **Validates: Requirement 12**

- [x] 425. V4 written up and H-AJ registered (Requirements 19, 20)
  - The trader (2026-11-06):
    - "any time frame 5mins and below are just for entries and refining entries that we find on the M30 and M15";
    - the setup frame by the pool's size;
    - the entry on an M3 or M1 CISD inside the setup's order block;
    - the stop beyond the setup's sweep;
    - judged on 2025-26.
  - Requirements 19-20, design.md's update (TE-D31 to TE-D35), and H-AJ registered in `docs/research/SEARCH_2018_2024.md` before V4's code exists.
  - **Validates: Requirements 19, 20.1**

- [x] 426. V4 built (Requirement 19)
  - Built 2026-11-06: `backend/tests/test_thesis_engine_v4.py` (8). V1's, V2's and V3's journals are byte for byte the same (12 fingerprints: walks and gold's October 2026 month).
  - `clock.limit_expiry` is now shared by the replay's limits and V4's setups.
  - **426a. RED:**
    - V1's, V2's and V3's journals are unchanged on the same bars and theses;
    - each pool's setup frame, with no M30 or M15 swing pools;
    - the setup places no order;
    - the pull-back into the order block and the refining CISD, at market;
    - the stop at the sweep's extreme;
    - failure beyond the extreme, and expiry;
    - mirrored bars give the mirrored journal.
  - **426b. GREEN:** `settings.V4`, the clock's and the book's refining frames, and the machine's setup and refinement.
  - **Validates: Requirement 19.1-19.7**

- [x] 427. H-AJ run (Requirement 20)
  - V4 and V1 on 2025-26, which is judged; V4 on 2021-22, which is reported.
  - The report goes to `docs/research/THESIS_ENGINE_HAJ.md`, with a line in the search log.
  - If it passes: the test window's export and one run.
  - Run 2026-11-06 (runner 1ce75be): **H-AJ FAILS.**
    - V4 with the week's real side: +0.460R a trade [−0.034, +1.046] on 107 trades, 5 of 8 markets, weekly break-even 66.1%.
    - V1 on the same year: +0.682R [+0.301, +1.116], 7 of 8, 58.8%. V1's H-AG result held out of sample.
    - Read after the run: M30 setups with M3 entries made +1.12R a trade (46% win), and M15 setups with M1 entries −0.16R. V1 stays the machine.
  - **Validates: Requirement 20.2-20.5**

- [ ] 428. V4 on Noculus beside V3, V2 and V1
  - The layer's menu gains V4. The chart shows each setup's order block, the pull-back and the refined entry.
  - **Validates: Requirement 12**

- [x] 429. V5 written up and H-AL registered (Requirements 21, 22)
  - The trader (2026-11-06) chose to spend 2023-2024 on V5, V1 in the 02:00-04:00 New York window, after H-AK.
  - Requirements 21-22, design.md's update (TE-D36 to TE-D38), and H-AL registered in `docs/research/SEARCH_2018_2024.md` before V5's code exists and before 2023-2024 is exported.
  - **Validates: Requirements 21, 22.1**

- [x] 430. V5 built (Requirement 21)
  - Built 2026-11-06: `backend/tests/test_thesis_engine_v5.py` (7). V1 to V4 are byte for byte the same (15 fingerprints).
  - **430a. RED:**
    - V1 to V4 are unchanged on the same bars and theses;
    - V5 arms at 02:00, and its sweeps and orders fall inside 02:00-04:00 New York;
    - a hand waiting at 04:00 ends;
    - mirrored bars give the mirrored journal where no two levels tie. V1's tie-break by content id doesn't survive a mirror, and V5 keeps it, as H-AG ran V1.
  - **430b. GREEN:** `settings.V5`, and the machine reading `entry_in_window`.
  - **Validates: Requirement 21.1-21.3**

- [x] 431. H-AL run (Requirement 22)
  - The runner is committed first, then 2023-2024 is exported (`mt5-m1-test`) and run once: V5 and V1 judged, V5 on 2021-22 and 2025-26 reported.
  - The report goes to `docs/research/THESIS_ENGINE_HAL.md`, with a line in the search log.
  - Run 2026-11-06 (runner cb873d4, export after 4100a4e):
    - **H-AL FAILS:** V5 +0.609R a trade [+0.086, +1.230], 5 of 8 markets, 60.7% a week against V1's 50.0%.
    - **V1 PASSES H-AG's rule on 2023-2024:** +0.977R [+0.639, +1.353], 7 of 8 markets, 42.9% a trade, 50.0% a week. V1 stays the machine, now confirmed on the test window.
  - **Validates: Requirement 22.2-22.6**

- [ ] 432. V5 on Noculus beside V4 to V1
  - **Validates: Requirement 12**

- [x] 437. H-AN registered (Requirements 23, 24)
  - The trader (2026-11-09) chose to lower the bar: tune V1's management to need fewer right weeks, then confirm on July to November 2026, spending it.
  - H-AN is registered in `docs/research/SEARCH_2018_2024.md` before its code: ten single-change variants, the pick, the power statement and the pass.
  - **Validates: Requirement 24.1**

- [x] 438. The management settings and H-AN's runner (Requirements 23, 24)
  - `settings.py` gains `partial_r`, `partial_fraction`, `target_cap_r`, `check_at`, `check_hours` and `check_r`, all off in V1 to V5. The machine reads the cap, and the replay reads the rest.
  - `thesis_engine/han.py`: `tune` (the ten variants and V1 on the three read windows, the pick and its power) and `confirm` (the pick and V1 on July to November 2026).
  - Tests (built 2026-11-09):
    - `test_thesis_engine_management.py` (8): V5's fingerprint, recorded before the code, unchanged (V1 to V4: `test_thesis_engine_v5.py`), the trading day's end through both clock changes, and each setting on random walks;
    - `test_thesis_engine_han.py` (3): the bar, the registered pick, and one window end to end.
  - **Validates: Requirements 23.1-23.5, 24.2-24.3**

- [x] 439. H-AN tuned; the pick and its power logged before the confirmation runs (Requirement 24.2)
  - Run 2026-11-09 (commit 9ca0d22, 20 minutes): **no pick.** Every variant raises the pooled bar (V1 54.9%; ONE 55.2% is closest; DAY 66.8% is worst). None is below V1 in all three windows.
  - P2 reaches a 40% win rate on the right side but needs 60.3% right weeks.
  - Report: `docs/research/THESIS_ENGINE_HAN.md`; logged in the search log.

- [x] 440. H-AN confirmed once on July to November 2026, the result logged whatever it is (Requirements 24.3-24.4)
  - Not run, as registered: nothing qualified at the tuning stage, so July to November 2026 stays unspent.

- [x] 441. H-AO registered (Requirements 25, 26)
  - The trader (2026-11-09) chose to test Volume Profile, as a filter and as an entry. They named no profile, so the default stands: the previous week's POC and value area edges, with the previous day's beside it.
  - H-AO is registered in `docs/research/SEARCH_2018_2024.md` before its code: nine single-change variants, the pick and the pass.
  - **Validates: Requirement 26.1**

- [ ] 442. The volume settings and H-AO's runner (Requirements 25, 26)
  - `thesis_engine/volume.py`: the profile, the gates and the leg's POC. `settings.py` gains the volume settings, all off in V1 to V5. The machine reads the gate and the LIMIT_POC entry.
  - `thesis_engine/hao.py`: `tune` (the nine variants and V1 on the three read windows, the pick and its power) and `confirm` (the pick and V1 on July to November 2026).
  - **Validates: Requirements 25.1-25.6, 26.2-26.3**

- [ ] 443. H-AO tuned; the pick and its power logged before any confirmation runs (Requirement 26.2)

- [ ] 444. H-AO confirmed once on July to November 2026, on the trader's go, the result logged whatever it is (Requirements 26.3-26.4)

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
