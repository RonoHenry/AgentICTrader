# Design Document

**Spec**: Algo Mind
**Requirements**: `.kiro/specs/algo-mind/requirements.md`

## Overview

Algo Mind is a new package, `algo_mind/`, between the senses that exist (H-Y's state, the liquidity engine) and the hands that exist (the context variant's execution). It adds:
- the brain's fit and its versions;
- the live state;
- memory;
- the brief;
- the thesis files for the hands;
- the bench;
- the learning ledger.

```
Yahoo daily (≤2022: fit; ≥2025: live) → algo_research.search_state (the senses)
        → algo_mind.brain (fit, version, probability, call) + algo_mind.memory (analogs)
        → algo_mind.brief (data/algo_mind/briefs/<week>.json) → brain_theses.json / agree_theses.json
        → Noculus /context (beside the trader's call; the scorecard) → paper agents (brain, agreement)
```

## Decisions

| # | Decision | Why |
|---|---|---|
| AM-D1 | The brain v1 is H-Y's model, settings unchanged, fitted on every week before 2023-01-01 | The search's protocol: the test window is never read. A model tuned after H-Y's result would be a new try |
| AM-D2 | The live state is read from Yahoo daily from 2025-01-01, with the same cleaning | The brain sees live what it learned on; the broker's bars differ (CFD, server day). 2023-2024 stays unread. MN1's twelve-month range is complete from 2026-03 |
| AM-D3 | Untaken swings and gaps older than 2025 are invisible live | Their only source would be the unread years. The cap (10 mean ranges) limits the difference to far levels |
| AM-D4 | Calls at the fitted thirds | H-Y's rule; the thresholds are saved with the version |
| AM-D5 | Memory is 20 nearest training weeks on z-scored features, Euclidean | Simple, explainable, and it doesn't decide |
| AM-D6 | Versions live in `data/algo_mind/models/<version>/` (git-ignored): the pickled model, `meta.json` and the training rows' z-scores | Reproducible from the code and the snapshot; the pickle saves a refit |
| AM-D7 | The hands are thesis files, read by the existing `bias_mode = THESIS` | No engine change: the side's source is a file |
| AM-D8 | The agreement's file carries the trader's draw and protected swing | The context ends on the trader's levels; the brain gives no levels |

## Changes

| # | Change | Requirement |
|---|---|---|
| C1 | `algo_mind/sources.py`: the live Yahoo fetch from 2025-01-01 (cached under `data/algo_mind/live/`) | 1.2-1.3 |
| C2 | `algo_mind/brain.py`: `fit_version`, `load_version`, `Brain.probability`, `Brain.call` | 2 |
| C3 | `algo_mind/memory.py`: `analogs` | 3 |
| C4 | `algo_mind/brief.py` and `algo_mind/__main__.py` (`fit`, `brief`, `third-look`, `bench`) | 4.1, 5.1, 7.3 |
| C5 | `algo_research/replay/context.py` and `context.js`: the brain beside the trader; the scorecard's brain and agreement totals | 4.2-4.3 |
| C6 | `config/backtests/focus.toml`: `fresh_near_gap_brain`, `fresh_near_gap_agree` | 5.2 |
| C7 | `algo_mind/bench.py` | 6 |
| C8 | `algo_mind/ledger.py` | 7.1-7.2 |

## Correctness Properties

1. **No lookahead:** a week's state reads only days dated before its Monday, and a day not closed at the run is never read.
2. **Determinism:** two fits on the same rows give the same probabilities.
3. **The thirds:** on its training weeks, a version calls about a third of the weeks up and a third down.
4. **Analogs are training weeks:** no analog's week is on or after the version's training end.
5. **The agreement holds only agreeing sides,** with the trader's levels.
