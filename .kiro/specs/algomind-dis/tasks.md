# Implementation Plan

**spec**: AlgoMindDIS

## Overview

- **Numbering:** tasks continue the platform sequence from **398**.
- **Order:** §18's phases: audit, records, analyzers, reasoning, state, contract and shadow, evaluation, activation.
- **TDD:** every code task follows RED → GREEN → REFACTOR. Tests live in `backend/tests/test_algomind_dis_*.py`.
- **Paper only:** nothing here places a live order. Reader v0 keeps the paper agent until a version passes H-AF (DIS-D11).
- **One commit per task**, pushed to the open PR.

## Tasks

- [x] 398. Phase 0: the audit, this spec, and H-AF registered (Requirements 1, 15.2)
  - The compatibility report (design.md), the requirements, the design and this plan.
  - H-AF registered in `docs/research/SEARCH_2018_2024.md` before any of its code exists, with v1's settings named.
  - **Validates: Requirement 1.1, 15.2**

- [x] 399. Phase 1: the records and the settings (Requirement 2)
  - **399a. RED:** each record round-trips through JSON; the ids are the same for the same content and differ for different content; the settings are frozen and versioned.
  - **399b. GREEN:** `algomind_dis/__init__.py`, `settings.py`, `records.py`, `frames.py`. `frames.py` covers MN1 from D1, closed by t, New York days.
  - **Done 2026-11-03.**
    - Eleven frozen records. Times are UTC ns; only the contract carries ISO strings. `to_json`/`from_json` rebuild nested records from their type hints.
    - `V1` holds exactly H-AF's registered values.
    - `Frames` drops a week that ends before its Friday and a month that ends before its last business day, so a forming candle is never read as closed.
    - Tests: `test_algomind_dis_records.py` (4).
  - **Validates: Requirement 2.1-2.3, 8.1**

- [ ] 400. Phase 2a: structure, ranges and premium/discount (Requirements 3, 4)
  - **400a. RED** on hand-made bars:
    - swings are known only from their confirming close;
    - a BOS and an MSS fire at the right closes;
    - the three ranges each have their origin and invalidation;
    - the zones' bounds hold;
    - mirrored bars give mirrored results.
  - **400b. GREEN:** `analyzers/structure.py`, `analyzers/ranges.py`.
  - **Validates: Requirement 3.1-3.2, 4.1-4.4**

- [ ] 401. Phase 2b: objectives and PD array context (Requirements 5, 6)
  - **401a. RED:**
    - the typing (external, internal, temporal);
    - the status changes (approaching, swept with close-back, invalidated);
    - significance ignores distance, and the ranking breaks ties by distance;
    - an array's nine evaluations;
    - an FVG alone gives no evidence.
  - **401b. GREEN:** `analyzers/objectives.py`, `analyzers/arrays.py`.
  - **Validates: Requirement 5.1-5.4, 6.1-6.3**

- [ ] 402. Phase 2c: delivery, time and volatility (Requirements 7, 8)
  - **402a. RED:**
    - sweep → displacement → CISD gives BULLISH_DELIVERY, and a close under the run's low ends it;
    - a sweep and displacement without a CISD gives TRANSITIONAL;
    - a tight box gives CONSOLIDATION;
    - New York time across the clocks' change;
    - news carries no direction.
  - **402b. GREEN:** `analyzers/delivery.py`, `analyzers/context.py`.
  - **Validates: Requirement 7.1-7.2, 8.1-8.4**

- [ ] 403. Phase 3: evidence, synthesis, narrative and the timeframe hierarchy (Requirements 9, 10, 11)
  - **403a. RED:**
    - correlation control (a duplicated source event changes nothing);
    - the weights add to 1;
    - the scores on scenario bars;
    - lower-timeframe evidence classified as retracement, internal delivery or developing reversal;
    - the narrative's text comes from its record.
  - **403b. GREEN:** `evidence.py`, `narrative.py`.
  - **Validates: Requirement 9.1-9.5, 10.1-10.2, 11.1-11.2**

- [ ] 404. Phase 4: the state machine and the timeline (Requirements 12, 14)
  - **404a. RED:**
    - every transition of §10.2 and none outside it;
    - establish, hold, delivered, invalidated (a close, not a wick), expired, challenged, resolved;
    - no look-ahead and determinism (property tests);
    - the timeline is rebuilt the same after a cut;
    - a stale frame gives UNDETERMINED.
  - **404b. GREEN:** `state.py`; the weekly records and `transitions.jsonl`.
  - **Validates: Requirement 12.1-12.6, 14.1-14.4**

- [ ] 405. Phase 5: the contract, qualification and shadow (Requirements 13, 16.1-16.3, 17)
  - **405a. RED:**
    - the contract's fields and version;
    - `qualify`'s four outcomes with reasons;
    - the thesis adapter's file read by `agent.order_intent.theses`;
    - scenarios A-G;
    - DIS_DISABLED changes no order.
  - **405b. GREEN:**
    - `contract.py`;
    - `python -m algomind_dis read --week` and `--loop`;
    - /context shows v1 beside reader v0 and the trader's call;
    - the paper setups' qualification is recorded.
  - **Validates: Requirement 13.1-13.3, 16.1-16.3, 17.1**

- [ ] 406. Phase 6: H-AF, the historical evaluation (Requirement 15)
  - The replay over 1996-2022, the two cells with H-AE's scorer, state quality, the regime split and the two baselines. Run once.
  - The result goes into the search log (one try) and this task's notes, whatever it is.
  - **Validates: Requirement 15.1-15.4**

- [ ] 407. Phase 7: controlled activation (Requirement 16.4)
  - **If v1 passed H-AF:** DIS_ENFORCED writes the paper agent's thesis file in place of reader v0's, after the trader's go.
  - **If not:** v1 stays in shadow, and the trader chooses the next version's change.
  - **Validates: Requirement 16.4**
