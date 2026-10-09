# Design Document

**Spec**: AlgoResearch
**Requirements**: `.kiro/specs/algo-research/requirements.md`

## Overview

AlgoResearch turns "does this condition tell us where price goes next?" into a file, a command and a verdict. It rests on four design choices:

1. **What was known is kept apart from what happened.**
   - The *feature table* holds facts known at each decision time t.
   - The *label table* holds what happened after t.
   - Events and filters read features only; labels enter only through a hypothesis's measure. The separation is enforced in code: the feature, event and filter modules can't import the label module.
2. **Every number has a baseline and an honest interval.** Results are shown against a coin flip, the same trade at random times, simple rules or shuffled paths, as each measure calls for. Intervals resample whole trading dates, because instruments on one morning move together.
3. **Questions are files, written first and counted.**
   - A hypothesis is committed before it runs on the confirmation slice. The ledger records every official run, so a pass is read against the number of tries.
   - Ideas are built on the exploration slice. The study hold-out is never read.
4. **Reuse, not re-implementation.** AlgoResearch reuses the backtester's and the engine's own code:
   - candles: `load_instrument()`, `StrategyCalendar`, `fill_bars()`;
   - the engine path: `compose_as_of_view()`, `LiquidityMappingEngine.analyze()`, `build_order_intent()`;
   - definitions: `asian_pools()`, `get_killzone()`, `calculate_atr()`;
   - prices: the `FillModel` rules.

   A finding therefore describes the strategy's world, priced the way the backtester will price it.

### Changes to existing code

| # | Change | Why |
|---|---|---|
| C1 | `.gitignore`: add `data/research/` | Snapshots and caches stay local (AR-D8) |
| C2 | `requirements.txt`: list `pyarrow` | Parquet needs it. It's already installed as an MLflow dependency; listing it makes the direct use explicit. Nothing new is installed. |

Nothing else changes outside the new package: no live code, no backtester code, no Phase A cache key.

---

## Architecture

```mermaid
flowchart TB
    subgraph Snap["Snapshot (once per study, needs Docker)"]
        DB[(TimescaleDB candles)]
        REC[RecordingSource]
        PQ[(data/research/snapshots/name/<br/>Parquet + manifest)]
        DB --> REC -->|"load_instrument() reads,<br/>every row recorded"| PQ
    end

    subgraph Build["Build (offline, cached by fingerprint)"]
        SS[SnapshotSource : CandleSource]
        LI["load_instrument()<br/>InstrumentData: M1 + calendar bars"]
        FR[frames: pandas, calendar columns]
        MF[market features<br/>vectorised]
        AN[daily anticipation<br/>analyze() once per instrument-day]
        EF[engine features<br/>stage 2: every close]
        LB[labels<br/>remaining moves, day facts]
        PQ --> SS --> LI --> FR
        FR --> MF
        LI --> AN
        LI --> EF
        FR --> LB
        MF --> FT[(feature table)]
        AN --> FT
        EF --> FT
        LB --> LT[(label table)]
    end

    subgraph Ask["Run one hypothesis"]
        HY[H-nnn.toml<br/>committed first]
        EV[event + where<br/>features only]
        ME[measure<br/>races / direction / rate / move]
        RC[race engine<br/>= FillModel rules]
        BL[baselines<br/>coin flip, random time,<br/>naive rules, stratified, shuffled]
        ST[day-cluster bootstrap<br/>verdict]
        HY --> EV --> ME
        FT --> EV
        LT --> ME
        ME --> RC
        ME --> BL --> ST
        RC --> ST
    end

    subgraph Out["Outputs"]
        RP[docs/research/reports/H-nnn.md]
        LG[docs/research/ledger.csv<br/>LEDGER.md]
        DR[data/research/drafts/<br/>explore only]
    end
    ST --> RP
    ST --> LG
    ST --> DR
```

**Graduation path** (outside this package):

```
PASS in the confirmation slice → the user decides → a liquidity-engine spec update adds a StrategyConfig variant
  → backtest on the study (pass mark written first) → hold-out --final once → paper forward test
```

### Package layout

```
algo_research/                       # NEW package: offline research; nothing live imports it
  __init__.py
  __main__.py, cli.py                # snapshot | build | explore | run | ledger
  config.py                          # ResearchConfig (config/research/research.toml), slices
  snapshot.py                        # RecordingSource, export, SnapshotSource, manifest, fingerprint check
  frame.py                           # InstrumentData → pandas frames with calendar columns
  features/
    __init__.py
    market.py                        # market features (Req 3), vectorised
    anticipation.py                  # daily anticipation (Req 4)
    engine.py                        # engine features at every close (Req 5, stage 2)
    cache.py                         # Parquet cache keyed by fingerprints
  labels.py                          # labels (Req 6); never imported by features/, events.py, filters.py
  races.py                           # race engine (Req 7)
  events.py                          # named events (Req 9)
  filters.py                         # the `where` filter: AST whitelist, then pandas eval
  hypothesis.py                      # hypothesis schema (pydantic), loading, hashing
  baselines.py                       # Req 10
  stats.py                           # day-cluster bootstrap, rules, verdict (Req 11)
  ledger.py                          # append-only ledger, LEDGER.md
  report.py                          # Markdown reports
config/research/
  research.toml                      # ResearchConfig
  hypotheses/H001-....toml           # one file per hypothesis
docs/research/
  ledger.csv, LEDGER.md
  reports/H001.md, ...
data/research/                       # git-ignored
  snapshots/<name>/manifest.json, <INSTRUMENT>_<TF>.parquet
  cache/{features,anticipation,engine,labels}/<key>.parquet
  drafts/
```

Tests follow the backtester's convention: `backend/tests/test_research_*.py`, with fixtures under `backend/tests/fixtures/research/`.

---

## Components and Interfaces

### ResearchConfig (`config/research/research.toml`)

```toml
profile = "exness-standard"          # broker profile: candle source, spec file (spread, slippage, commission)
study = "baseline-2026q3"            # its holdout_start ends the research period; the hold-out is never read
instruments = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
start = 2025-01-01
snapshot = "exness-2025-2026h1"

[slices]                             # AR-D3; confirm must end at the study's holdout_start
explore = [2025-01-01, 2025-07-01]
confirm = [2025-07-01, 2026-07-07]

[bootstrap]
resamples = 10000

[baselines]
random_time_draws = 20
shuffles = 200
```

- **Validation:** the slices must be contiguous, start at `start` and end at the study's `holdout_start`.
- **Strategy settings:** the `StrategyConfig` (candle windows, entry timeframe) is the backtester's base configuration, `config/backtests/base.toml`, so the engine sees what Phase A sees.

### Snapshot (`algo_research/snapshot.py`)

- **`RecordingSource(inner)`** is a `CandleSource` that passes every `bars()` call to `inner` and keeps the rows it returns.
- **Export** runs `load_instrument(RecordingSource(TimescaleSource(...)), ...)` for each instrument, over [start, holdout_start), with the base `StrategyConfig`. It then writes the recorded rows, per instrument and timeframe and de-duplicated by time, to Parquet. Columns: time, open, high, low, close, volume, spread. The snapshot therefore holds exactly what the loader reads: the M1 bars and the native warm-up bars.
- **`SnapshotSource(path)`** is a `CandleSource` over those files.
- **On load**, `load_instrument(SnapshotSource(...))` runs and its `InstrumentData.fingerprint` is compared with the manifest's. A mismatch refuses, naming the instrument.
- **The hold-out guard:** an export whose end is after the study's `holdout_start` is refused before any data is read.

### Frames (`algo_research/frame.py`)

Per instrument, from `InstrumentData`:
- **M1 frame:**
  - indexed by UTC open time, with bid OHLC;
  - `spread` priced as `fill_bars()` prices it: the larger of the recorded spread and the spec's `default_spread`;
  - New York local time.
- **Calendar bars:** M15, H1, H4, D1 and W1 frames from `InstrumentData.closed`, each with its close time (`StrategyCalendar.period_end`).
- **Calendar columns, vectorised:**
  - `trading_date` = the date of (New York local time + 7 h): 17:00 becomes midnight of the next date.
  - `h4_index` = the hour of (New York local time + 7 h), divided by 4 and rounded down: 17:00 → 0, 21:00 → 1, 01:00 → 2, 05:00 → 3, 09:00 → 4, 13:00 → 5.
  - `weekday` of `trading_date`.
  - Property 3 checks all three against `StrategyCalendar` at random instants, including both sides of each DST change.

### Market features (`algo_research/features/market.py`)

One row per instrument per M15 close t. All prices are bid. "Known at" is when a value first becomes available; at any earlier t it is null.

| Column | Definition | Known at |
|---|---|---|
| `t`, `instrument` | the M15 close (UTC); the instrument | t |
| `trading_date`, `weekday`, `ny_minute`, `h4_index` | calendar columns (Req 2.2) | t |
| `in_window` | 01:00 ≤ New York time < 13:00 (LE-D11) | t |
| `killzone` | `get_killzone(t)` | t |
| `slice` | `explore` or `confirm` | t |
| `close` | the M15 bar's close | t |
| `d1_open` | the open of the current D1 candle (17:00 New York) | 17:00 |
| `midnight_open` | the open of the first M1 bar at or after 00:00 New York in the candle | 00:00 |
| `h4_open` | the open of the current H4 candle | H4 open |
| `side_d1_open`, `side_midnight_open`, `side_h4_open` | sign of `close` minus each open | t |
| `day_high`, `day_low`, `day_high_at`, `day_low_at` | the candle's extremes so far from M1; the earliest bar on ties | t |
| `prev_h4_dir`, `prev_day_dir`, `prev_week_dir` | sign of close − open of the previous H4, D1 and W1 candle | that candle's close |
| `asia_high`, `asia_low` | the highest high and lowest low of the candle's 20:00–23:00 New York H1 bars, as `asian_pools()` computes them (LE-D12) | 00:00 |
| `asia_high_raided_at`, `asia_low_raided_at` | the close of the first M1 bar after 00:00 whose high is above `asia_high` (low below `asia_low`) | that bar's close |
| `pdh`, `pdl` | the previous D1 candle's high and low | 17:00 |
| `pwh`, `pwl` | the previous W1 candle's high and low | the W1 open |
| `pdh_taken_at`, `pdl_taken_at` | the close of the first M1 bar in the current candle trading beyond the level | that bar's close |
| `pwh_taken_at`, `pwl_taken_at` | the same within the current W1 candle | that bar's close |
| `w1_trend` | UP when the last closed W1 candle closed above the previous W1's high; DOWN when below its low; else NEUTRAL (LE-D15) | W1 close |
| `atr_d1` | `calculate_atr()` over the last 14 closed D1 candles | 17:00 |
| `atr_m15` | `calculate_atr()` over the last 14 closed M15 bars | t |
| `typical_spread`, `spread_to_atr` | the spec's `default_spread`, and that divided by `atr_d1` | – |

**How it's computed.** Per instrument and trading date:
- **Running values:** a cumulative max/min over the M1 bars, sampled at each M15 close with `searchsorted`.
- **"Taken" times:** the first M1 index where the running extreme crosses the level.
- **Previous candles:** the closed D1, W1 and H4 frames, picked with `searchsorted` on their close times.

Property 1 compares the vectorised table with a slow reference that rebuilds each value from data truncated at t.

### Daily anticipation (`algo_research/features/anticipation.py`)

- **When:** for each instrument and D1 candle, at its first M15 close t_a (17:15 New York).
- **How:** `view = compose_as_of_view(data.closed, data.m1, t_a, cfg.entry_tf, cfg.candle_counts, calendar)`, then `LiquidityMappingEngine().analyze(view, instrument, t_a).candle_profile`.
- **Columns** (copied to every row of the candle):
  - `ant_trend`, `ant_direction`;
  - `ant_draw_price`, `ant_draw_source`, `ant_draw_tf`;
  - the same three fields for `ant_draw_above_*` and `ant_draw_below_*`.
- **Errors:** an engine error, or a missing profile, leaves the candle's columns null and is counted in the build summary.
- **Cost:** about 400 trading dates × 4 instruments × ~80 ms ≈ 2 minutes.
- **Checks:**
  - **Equality within the candle (liquidity-engine Property 35):** on fixture days, the profile at random t in the candle equals the profile at t_a.
  - **Parity:** `w1_trend` equals `ant_trend` on every date (Property 4).

### Engine features, stage 2 (`algo_research/features/engine.py`)

- **What:** for every grid time, the Phase A path: `compose_as_of_view`, `analyze()`, `build_order_intent` with the spec's typical spread. Each evaluation becomes one flat row:
  - **the setup sequence:** direction; the raid's source, side, timeframe, price and bar time; `cisd_at`; the protected swing's wick and body; `leg_extreme`; the entry array's type, timeframe, high and low;
  - **the grade** and each of its conditions;
  - **the candle profile at t:** `false_move_taken`, `asia_raided`, `raid_in_window`;
  - **the decision:** the order intent's direction, entry, stop, target and R:R, or the `NoTrade` reason.
- **Cost:** it runs in parallel per instrument; about Phase A's cost, ~2 h for 4 instruments and 18 months. It runs once per engine version, cached under a key over the snapshot fingerprint, `engine_code_fingerprint()` and the `StrategyConfig`.
- **Isolation:** it imports the backtester's functions and changes none of them.

### Labels (`algo_research/labels.py`)

**Forward labels** use only bars opening at or after t:

| Column | Definition |
|---|---|
| `rem_close` | the close of the last M1 bar before the D1 close (17:00 New York) |
| `rem_move`, `rem_move_atr` | `rem_close − close`, and that divided by `atr_d1` |
| `fwd_1h_atr`, `fwd_4h_atr` | the close of the last M1 bar at or before t + h, minus `close`, divided by `atr_d1` |
| `<level>_hit_after`, `<level>_hit_at` | for `pdh`, `pdl`, `pwh`, `pwl`, `asia_high`, `asia_low`: whether, and when, an M1 bar opening at or after t and before the D1 close trades beyond the level |

**Candle labels** describe the whole D1 candle, including bars before t. Hypothesis validation accepts them only with the `daily` event:

| Column | Definition |
|---|---|
| `day_dir` | the sign of the D1 candle's final close − `d1_open` |
| `day_high_final`, `day_low_final` | the candle's final high and low |
| `day_high_h4`, `day_low_h4` | the H4 index each formed in |

- **How it's computed:** reverse cumulative max/min over the M1 bars within each trading date for forward labels; one aggregate per trading date for candle labels.
- **Separation:**
  - `test_features_do_not_import_labels` parses the imports of `features/`, `events.py` and `filters.py`.
  - Property 2 checks that forward labels never depend on bars that closed by t.
  - Why candle labels are fenced off: asked at 09:00, "did the day close up?" partly restates what has already happened by 09:00 and inflates accuracy. Direction questions therefore use `rem_move`, the move still to come.

### Race engine (`algo_research/races.py`)

- **Inputs per instrument:** NumPy arrays of M1 open times and bid OHLC, `spread` priced as by `fill_bars()`, and the spec's `stop_slippage`.
- **Inputs per race:** t, direction, stop, target and time limit.
- **Rules** (the `FillModel` rules for a MARKET order, algo-backtester Req 4):
  1. The entry bar is the first M1 bar opening at or after t. LONG fills at its ask open (open + spread), SHORT at its bid open. When that open is already beyond the stop or the target, the race is REJECTED.
  2. From the entry bar to the last bar before the limit:
     - the stop triggers on the closing side (bid low for LONG, ask high for SHORT);
     - the target triggers on the closing side as well (bid high for LONG, ask low for SHORT).
  3. When one bar reaches both, the stop wins, and the race is flagged `ambiguous`.
  4. A bar opening beyond the stop exits at its open (a gap). Stop exits are worsened by `stop_slippage`. Targets exit at the target.
  5. With neither hit, the race is a TIMEOUT, exited at the last bar's close on the closing side.
- **R and costs:**
  - R = |entry − stop| on the executed entry (the backtester's definition, task 201).
  - Gross R is measured on bid prices, net R on executed prices.
  - Commission per lot per side is converted to R per lot (both scale with lots, so no sizing is needed).
- **Implementation:** one NumPy slice per race and `argmax` on the boolean hit arrays. Target: 50,000 races in under 30 s.
- **Property 5:** on random paths and orders, the outcome, exit time and exit price equal those from stepping `FillModel` with the same MARKET `SimOrder`.

### Events and filters (`algo_research/events.py`, `filters.py`)

An event function takes the feature table and its parameters, and returns rows of `(t, instrument, direction, levels)`. The first events:

| Event | Parameters | Fires | Direction | Levels |
|---|---|---|---|---|
| `anchor` | `at` (New York time), `direction_from` (a feature column, optional) | at the M15 close at `at`, each instrument and trading date | from the column (rows with no direction are skipped and counted), or none | – |
| `asia_raid_reclaim` | `window` (default 01:00–09:00), `reclaim_within` (M15 bars, default 4) | the first M15 close back inside the Asian range after a bar in the window traded beyond one side, while the other side is untaken | LONG after a low raid, SHORT after a high raid | `raid_extreme` (the furthest price from the raid bar to the reclaim), `asia_opposite` |
| `level_open` | `level` (`pdh`/`pdl`/`pwh`/`pwl` or `trend`: PDH when `w1_trend` is UP, PDL when DOWN), `at` | at `at`, when the level is untaken | toward the level | `level` (price) and `level_name`. A measure may read `level_hit_after` / `level_hit_at`, resolved per row to `<level_name>_hit_after` / `_hit_at`; the `stratified` baseline buckets by the distance to `level` |
| `daily` | – | once per instrument and trading date, at the last M15 close of the candle; for day-fact and timing measures | none | – |
| `engine_intent` (stage 2) | `decisions` (default: every order intent) | each M15 close where the engine produced an order intent | the intent's | `stop`, `target` |

- **The `daily` event and the last close:** firing at the candle's last M15 close keeps it a decision time like any other. Its measures read candle labels, which describe the whole candle, so the firing time doesn't change them.
- **Filters:** `where` is parsed with `ast`. Only these are allowed: feature column names, constants, comparisons, `in`, `and`, `or` and `not`. The filter is then evaluated with `DataFrame.eval`. Anything else is refused, naming the offending part.

### Hypothesis (`algo_research/hypothesis.py`)

A pydantic model, loaded from TOML. An example (H002):

```toml
id = "H002"
title = "A London raid of the Asian range reverses to the range's other side"
statement = """
When price trades through the Asian low between 01:00 and 09:00 New York, and an M15 bar
closes back above it before the Asian high is taken, price reaches the Asian high before it
breaks the raid's low more often than a coin flip and than the same trade at random times,
and the trade is profitable after costs. Mirrored for the Asian high.
"""
family = "po3"
created = 2026-10-10
slice = "confirm"
# supersedes = "H00x"                  # when this replaces a changed question

[event]
name = "asia_raid_reclaim"
params = { window = ["01:00", "09:00"], reclaim_within = 4 }
where = ""                               # e.g. "w1_trend == 'UP'"

[measure]
kind = "race"                            # race | direction | rate | move

[trade]                                  # races only
direction = "event"                      # the event's own direction
stop = { kind = "level", name = "raid_extreme" }
target = { kind = "level", name = "asia_opposite" }   # or { kind = "r", value = 2.0 } / { kind = "atr", value = 0.5 }
time_limit = "day_close"                 # or { minutes = 240 }

[baselines]
use = ["coin_flip", "random_time"]

[pass]
min_events = 100
min_days = 60
require = [
  { stat = "win_rate", versus = "coin_flip" },
  { stat = "win_rate", versus = "random_time" },
  { stat = "mean_net_r" },                # versus nothing: its own lower bound above min_effect
]
```

**Measures and their statistics:**

| `measure.kind` | Statistics | Reads |
|---|---|---|
| `race` | `win_rate`, `mean_net_r`, `mean_gross_r` | races |
| `direction` | `accuracy` (share where the sign of `rem_move` (or `fwd_*`) equals the direction; zero moves skipped and counted), `mean_move_atr` (signed by the direction) | labels |
| `rate` | `rate` of a label condition `of`, optionally `given` another label condition, e.g. `of = "day_low_h4 in [2, 3, 4]"`, `given = "day_dir == 1"` | labels |
| `move` | `mean_move_atr` over a label column | labels |

- **Label expressions:** label columns appear only in `measure`, never in `event` or `where`. They are parsed by the same AST whitelist, over label columns.
- **Hash:** the sha256 of the file's bytes with line endings normalised.

### Baselines (`algo_research/baselines.py`)

| Baseline | Measures | Definition |
|---|---|---|
| `coin_flip` | race | Mean over events of (entry bid − stop) ÷ (target − stop), mirrored for SHORT. Analytic, no draws. |
| `random_time` | race, direction, move | K draws per event: same instrument and New York 15-minute slot, other trading dates of the same slice without an event for that instrument. The draws keep the event's direction and its stop/target distances in `atr_d1` units, rescaled by the drawn row's `atr_d1`. |
| `naive:<rule>` | direction | `always_long`, `prev_day_dir`, `w1_trend`, `side_d1_open`, `side_midnight_open`, each applied to the event rows. `best_naive` is the best of those the hypothesis lists, re-chosen within each bootstrap resample. |
| `stratified` | rate | The unconditional rate among rows of the slice in the same decile of distance to the level (in `atr_d1`) and the same New York hour, averaged over the event rows' cells. |
| `shuffled_path` | rate (timing) | For each trading date, permute its M15 close-to-close moves while keeping its open and close, rebuild the path, and recompute the statistic. Averaged over 200 shuffles. Removes the arcsine artefact: an up day tends to show its low early even at random. |

**Seed:** one per hypothesis, from the first 8 bytes of its sha256. Draws are reproducible, so a rerun reproduces its result exactly (Property 9).

### Statistics and verdict (`algo_research/stats.py`)

- **Per date:** for each trading date d and each series (the events, and each baseline), the sum of the statistic's values and the count of rows.
- **Bootstrap:** draw dates with replacement, B = 10,000 times (a NumPy integer matrix of shape B × number of dates, seeded). Each resample's statistic is Σ sums ÷ Σ counts over the drawn dates. A paired difference uses the same drawn dates for both series.
- **Interval:** the 2.5th and 97.5th percentiles.
- **Verdict:** INSUFFICIENT if `n_events < min_events` or `n_dates < min_days`; PASS if every `require` rule's lower bound is above its `min_effect`; otherwise FAIL.
- **Breakdowns** for the report: the same statistic per instrument, per calendar quarter and per weekday, each with its count. Also the share of quarters whose effect has the sign of the overall effect.

### Runner, ledger and report (`cli.py`, `ledger.py`, `report.py`)

```
python -m algo_research snapshot            # export the study's candles (needs Docker, once)
python -m algo_research build               # market features, anticipation, labels (cached)
python -m algo_research build --engine      # stage 2 engine features (~2 h, cached)
python -m algo_research explore H002        # exploration slice, terminal + drafts only
python -m algo_research run H002            # confirmation slice: report + ledger row
python -m algo_research ledger              # render docs/research/LEDGER.md
```

**`run`** goes through these steps in order, stopping at the first failure:
1. Load and validate the hypothesis.
2. Pre-registration checks:
   - the file is tracked and unchanged against HEAD;
   - `algo_research/` has no uncommitted changes;
   - the ledger has no other hash for this id.
3. Load the snapshot and check its fingerprint.
4. Load the features and labels from the cache, building them if missing.
5. Keep the confirmation slice.
6. Run the event, then `where`.
7. Run the measure (races if needed), then the baselines.
8. Compute the statistics and the verdict.
9. Write the report, and append the ledger row.

**`explore`** skips step 2, keeps the exploration slice, and writes to `data/research/drafts/<id>-<time>.md` only.

When the ledger already holds the hypothesis's hash, `run` recomputes and compares, instead of appending:
- an equal result says so;
- a different result is an error naming the differing fields.

**Report outline** (`docs/research/reports/H<nnn>.md`):
1. **Verdict line:** PASS, FAIL or INSUFFICIENT; the main statistic with its interval; each baseline.
2. **The question as registered:** the statement, event, filter, measure, trade, baselines and pass rules (copied from the file), and the file's hash.
3. **Sample:**
   - events, dates and skipped rows (null features, REJECTED races, zero moves);
   - counts by instrument, year and weekday.
4. **Results:** a table of each `require` rule (statistic, comparison, interval, rule, result), then the other statistics.
5. **Stability:** by instrument, by quarter and by weekday, and the share of quarters with the same sign.
6. **Races** (race measures only):
   - the outcome counts;
   - the ambiguous share, with "needs tick data" above 10%;
   - the mean holding time, and MFE/MAE quantiles.
7. **Check by eye:** the first 20 event times per instrument, with direction and levels.
8. **Inputs:** the snapshot name and fingerprints, the code commit, the spec values (spread, slippage, commission), the slice, the seed, and the run's place in the ledger (test k of n).

---

## Data Models

### Snapshot manifest (`manifest.json`)

```json
{
  "name": "exness-2025-2026h1",
  "profile": "exness-standard", "venue": "mt5", "source": "mt5",
  "instruments": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
  "start": "2025-01-01", "end": "2026-07-07", "study": "baseline-2026q3",
  "candle_counts": {"M15": 200, "D1": 90, "W1": 30, "...": "..."},
  "spec_source": "Exness (KE) Limited / ExnessKE-MT5Trial9, exported 2026-10-05",
  "data": {"EURUSD": {"rows": 790000, "sha256": "...", "coverage_problems": []}},
  "git_commit": "...", "created_at": "..."
}
```

### Ledger (`docs/research/ledger.csv`)

```
seq, run_at, hypothesis, sha256, family, title, slice, snapshot, code_commit, measure,
n_events, n_dates, stat_name, stat, stat_lo, stat_hi,
baseline_1, value_1, diff_lo_1, diff_hi_1, ..., verdict, report
```

Up to four baselines per row, each with its value and the difference's interval. `LEDGER.md` groups the rows by family and states how many official tests have run, and how many passes chance alone would produce (2.5% per rule).

### Race results (in memory, and in the drafts for `explore`)

`t, instrument, direction, entry_time, entry, stop, target, outcome (TARGET | STOP | TIMEOUT | REJECTED), exit_time, exit, gross_r, net_r, mfe_r, mae_r, ambiguous, holding_minutes`

---

## First Hypotheses

These are proposals. Each file is written in task 258, and the user confirms its rules before it is committed (AR-D9). The pass rules follow AR-D4 unless stated otherwise.

| Id | Question | Event | Measure | Baselines | Proposed rules |
|---|---|---|---|---|---|
| H001 | Does the engine's daily anticipation call the rest of the day? Two tests: at 05:00 and at 09:00 New York | `anchor`, `at` = 05:00 / 09:00, `direction_from` = `ant_direction` | `direction` on `rem_move` | `naive:` all five rules, `random_time` | lower bound of `accuracy − best_naive` > 0; at least 150 events on 100 dates |
| H002 | After a London raid of the Asian range and a close back inside, does price reach the other side first? | `asia_raid_reclaim` | `race`: stop `raid_extreme`, target `asia_opposite`, limit at the D1 close | `coin_flip`, `random_time` | `win_rate` above both baselines; `mean_net_r` > 0 |
| H003 | With the W1 trend, is the previous day's level in the trend's direction traded more often than its distance alone predicts? | `level_open`, `level` = `trend`, `at` = 09:00 | `rate` of `<level>_hit_after` | `stratified` | lower bound of `rate − stratified` > 0 |
| H004 | Replication: do daily extremes form in the 01:00/05:00/09:00 H4 candles more often than shuffled paths? Two tests: the low on up days, the high on down days | `daily` | `rate` of `day_low_h4 in [2,3,4]` given `day_dir == 1` (and the mirror) | `shuffled_path` | lower bound of `rate − shuffled_path` > 0. Family `replication`: the tooling should reproduce the 2026-10-08 statistic (+6 and +11 points) |
| H005 | Stage 2: are the engine's setup-sequence entries better than the same trade at random times? Two tests: target at 1R (low variance) and the intent's own target | `engine_intent` | `race` with the intent's direction and stop | `random_time`, `coin_flip` | `win_rate` above `random_time` |
| H006 | Stage 2: after an intent reaches +1R, does price reach its target more often than chance (the break-even lead)? | `engine_intent`, re-entered when +1R is first reached: a stopping time, known when it happens | `race`: stop at the entry, target the intent's | `coin_flip` | `win_rate` above `coin_flip` |

**Candidates not yet written as hypotheses:**
- CRT C3 expansion on M15/M30/H1 frames (the 2026-10-09 scratch diagnostic);
- the Monday/Tuesday weekly extreme;
- break-even exit policies, which belong to the backtester once a stage-2 lead holds.

---

## Correctness Properties

Each property is a test; "Hypothesis" means a property-based test with the `hypothesis` library.

### Property 1: Features Use Only the Past

*For any* instrument and grid time t (Hypothesis, random t in a fixture), the feature row at t SHALL equal the row computed from the same data with every bar after t removed.
**Validates: Requirements 3.1, 9.2**

### Property 2: Forward Labels Use Only the Future

- *For any* t, a row's forward labels SHALL be unchanged when every bar that closed at or before t is perturbed, its prices changed but not its times. The labels expressed in `atr_d1` units are compared before that scaling, since `atr_d1` is a feature.
- The feature module SHALL NOT import the label module.
- Hypothesis validation SHALL refuse candle labels with any event but `daily`.

**Validates: Requirements 6.1, 6.2**

### Property 3: Calendar Parity

*For any* instant (Hypothesis, 2024–2027, weighted toward DST changes and 17:00 New York), `trading_date`, `h4_index` and `weekday` SHALL equal those derived from `StrategyCalendar.period_start` for D1, H4 and W1.
**Validates: Requirements 2.2, 2.3**

### Property 4: Engine Parity

- On the fixture windows, `asia_high`/`asia_low` SHALL equal `asian_pools()`.
- On every trading date of a build, `w1_trend` SHALL equal `ant_trend`.
- At every t, `killzone` and `in_window` SHALL equal the engine's.

**Validates: Requirements 3.3, 4.2**

### Property 5: Races Equal the Fill Model

*For any* random M1 path (gaps, spreads, bars reaching both levels) and race (Hypothesis), the race engine's outcome, exit time and exit price SHALL equal those from stepping `FillModel` with the same MARKET `SimOrder` until it exits, or until the time limit (TIMEOUT).
**Validates: Requirements 7.1, 7.2**

### Property 6: Coin-Flip Consistency

On simulated driftless paths with small steps, the observed win rate of many races SHALL lie within the interval of `coin_flip`, and so SHALL `random_time`.
**Validates: Requirements 10.1, 10.2**

### Property 7: Duplicates Don't Shrink Intervals

*For any* data set and seed, duplicating every row within its trading date SHALL leave the bootstrap interval unchanged. Each date's sum and count double, so every resample's ratio is identical.
**Validates: Requirements 11.1, 11.5**

### Property 8: Null Calibration and Power

- On 200 simulated random-walk worlds, registered race and direction hypotheses SHALL PASS in at most 5% (expected ≈ 2.5%).
- With a planted post-event drift, they SHALL PASS in at least 90%, and the interval SHALL cover the planted effect in at least 90%.

Marked `slow`; it runs at checkpoints.
**Validates: Requirements 14.1, 14.2**

### Property 9: Determinism

Two runs of one hypothesis on one snapshot SHALL produce identical results, report and ledger fields (apart from `run_at`). A ledgered rerun SHALL be checked against its recorded row.
**Validates: Requirements 8.4, 10.6, 14.3**

### Property 10: The Hold-out Is Unreachable

No snapshot, feature, label or race row SHALL have a time at or after the study's `holdout_start`. The snapshot export and `ResearchConfig` SHALL refuse a period that reaches it.
**Validates: Requirements 1.2, 13.2**

### Property 11: Pre-registration Is Enforced

`run` SHALL refuse:
- an uncommitted or modified hypothesis file;
- uncommitted changes in `algo_research/`;
- an id already in the ledger with another hash.

`explore` SHALL never write the ledger.
**Validates: Requirements 8.2, 8.3, 12.4**

---

## Error Handling

| Situation | Behaviour |
|---|---|
| No snapshot | Refuse: name the snapshot and the export command (it needs Docker running) |
| Fingerprint mismatch | Refuse: name the instrument; the data changed since export, so re-export under a new name |
| A period reaching the hold-out | Refuse before reading data, naming `holdout_start` |
| Invalid hypothesis | Refuse before reading data, naming the field and the allowed values |
| A `where` or label expression outside the whitelist, or naming an unknown or wrong-table column | Refuse, naming the offending node or column |
| Pre-registration failures (Property 11) | Refuse, naming the file or path and how to fix it (commit it, or write a new hypothesis that supersedes it) |
| An engine error during a build | Count it, leave the affected rows null, list the count in the build summary |
| No events | Verdict INSUFFICIENT, with the report still written |
| A race whose entry is already beyond a level | Outcome REJECTED: counted and excluded, as the backtester rejects invalid stops |

---

## Testing Strategy

- **Unit tests** on small, hand-made frames for each feature, label, event, filter rule, baseline and statistic, with known answers (e.g., an analytic coin flip, a bootstrap of a constant).
- **Property tests** (Hypothesis): Properties 1, 2, 3, 5, 6 and 7, with `max_examples=100`. The exception is Property 1's truncation, which uses 25 because each example rebuilds the features.
- **Parity with the engine** (Property 4) on the backtester's engine-window and golden-week fixtures.
- **Self-validation** (Property 8), marked `slow`:
  - simulated worlds of 120 trading dates of M1 for one instrument;
  - session-shaped volatility: lower in the Asian session, higher at the London and New York opens;
  - a constant spread.
- **Golden research run:**
  - **Fixture:** a deterministic synthetic data set (6 weeks, 2 instruments) in `backend/tests/fixtures/research/golden/`, with one registered fixture hypothesis.
  - **Check:** the report and ledger row are byte-identical on every run.
  - **Regenerate** with `UPDATE_GOLDEN=1` in the commit that changes them on purpose.
- **Where tests live:** `backend/tests/test_research_*.py`. Nothing needs Docker except the real snapshot export, which is a user-run command, not a test.

---

## Measured Performance

To be filled at the checkpoint (task 256) and the first real build (task 257):
- snapshot size;
- build times per tier;
- races per second;
- one hypothesis run end to end.

Measured so far (this machine, synthetic 18-month M1 of one instrument, 786,420 bars):

| What | Time | Task |
|---|---|---|
| Market features, 37,824 rows | 0.7 s | 247 |
| Races, 50,000 with 16-hour limits | 0.6 s (about 89,000 races/s) | 250 |

---

## Requirement Traceability

| Requirement | Components | Properties | Tasks |
|---|---|---|---|
| 1 Snapshot | `snapshot.py` | 10 | 245, 257 |
| 2 Grid and calendar | `frame.py` | 3 | 246 |
| 3 Market features | `features/market.py`, `features/cache.py` | 1, 4 | 247 |
| 4 Daily anticipation | `features/anticipation.py` | 4 | 248 |
| 5 Engine features | `features/engine.py` | – | 260 |
| 6 Labels | `labels.py` | 2 | 249 |
| 7 Races | `races.py` | 5, 6 | 250 |
| 8 Hypotheses | `hypothesis.py`, `cli.py` | 9, 11 | 251, 254 |
| 9 Events and filters | `events.py`, `filters.py` | 1 | 251 |
| 10 Baselines | `baselines.py` | 6 | 253 |
| 11 Statistics | `stats.py` | 7 | 252 |
| 12 Ledger and reports | `ledger.py`, `report.py` | 9 | 254 |
| 13 Out-of-sample | `config.py`, `cli.py` | 10, 11 | 244, 254 |
| 14 Self-validation | tests | 8, 9 | 255, 256 |
