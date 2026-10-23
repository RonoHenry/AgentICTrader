# The CISD the trader's indicator draws: the exploration run (task 362)

**Run 2026-10-23.**
- **Command:** `python -m algo_backtester run config/backtests/focus.toml --snapshot focus-2025-2026h1 --variant fresh_near_gap --variant fresh_near_gap_run --variant fresh_near_gap_crt --workers 8`. That is three engine analyses, because `cisd` changes the engine's own map (liquidity-engine tasks 360–361, Requirement 30).
- **Data:** the exploration slice (2025-01-01 to 2025-07-01), Exness M1 from the research snapshot.
- **Markets:** XAUUSD, EURUSD, GBPUSD, US100, US500, US30.
- **Costs and account:** as in task 344: 1% risk, 10,000 USD.
- **Runs:**
  - `3f1dac662643` (`fresh_near_gap`)
  - `90fdbd000381` (`fresh_near_gap_run`)
  - `2c4d1dbb9d5b` (`fresh_near_gap_crt`)
- **The reference reproduces:** `fresh_near_gap` gives the same 114 trades and +0.27R as tasks 344 and 354. So the code change leaves the default engine as it was.

## Why

The trader, on Noculus with the Fractal + POI layer beside the engine: the indicator shows a high-probability CISD while the engine shows its own. The two rules differ:

- **The engine's (`"next"`):** a bar closing beyond the first open of the run *right before it*. A setup takes the first such bar after the raid.
- **The indicator's (`"run"`):** the run that made the sweep's extreme gives the level (the open of its first candle, dojis skipped). Any later close through that level is the CISD.
- **`"crt"`:** the indicator's CISD, plus its context. The only pools are the previous H4 candle's high and low (C1), swept during the next H4 candle (C2).

All three variants share the trader's execution:
- a fresh raid (H4);
- the stop at most one M15 range;
- TP1 the nearer of SD 2.0 and the draw;
- the FVG as the gap.

## The results

The interval is the backtester's 95% bootstrap on R per trade after costs.

| Variant | Trades | Win | Before costs | After costs (95%) | Total | Profit factor | Max drawdown | Losing streak |
|---|---|---|---|---|---|---|---|---|
| **fresh_near_gap** (`next`) | 114 | 15% | +0.46 | **+0.27 [−0.29, +0.90]** | **+30.4R** | 1.31 | **27.4R** | 26 |
| fresh_near_gap_run | 147 | 7% | −0.20 | −0.49 [−0.83, −0.10] | −72.7R | 0.50 | 78.1R | 35 |
| fresh_near_gap_crt | 147 | 11% | +0.03 | −0.14 [−0.54, +0.32] | −20.0R | 0.85 | 50.9R | 36 |

- **The indicator's CISD alone (`run`) is worse, and its interval excludes zero.**
  - Win rate halves: 15% to 7%.
  - Drawdown nearly triples: 27R to 78R.
- **With the indicator's C1/C2 context (`crt`) it is about 0R before costs (+0.03).** Task 338 found the same for the indicator's setups traded at C2 + CISD (+0.03 gross).
- **Where the trades sit didn't change** (medians; the stop is in M15 average true ranges at the decision):

  | | next | run | crt |
  |---|---|---|---|
  | Stop from entry | 0.80 | 0.81 | 0.79 |
  | Raid age at the fill | 2.4 h | 1.9 h | 2.5 h |
  | Raid to entry array | 4 M15 | 2 M15 | 4 M15 |

  The stop cap (one M15 range) and the fresh-raid rule already bound the stop and the timing. The CISD rule only changes which setups qualify.
- **Different setups, not better ones** (trades matched on market, decision time and side):

  | | Shared with `next` | New trades | `next`'s trades they lost |
  |---|---|---|---|
  | run | 33 (−0.87R, the same in both) | 114: −0.39R (−0.06 gross), win 8% | 81: +0.73R |
  | crt | 35 (+0.33R, the same in both) | 112: −0.28R (−0.12 gross), win 10% | 79: +0.24R |

- **Why `run` loses `next`'s winners:**
  - The indicator's CISD accepts any later close through the level, so many more raids qualify.
  - The detector ranks setups by the most recent raid, so a newer one often wins: mostly M15 swings, 129 of the 147.
  - That displaces the setup the engine's own rule would have taken.
  - More of those picks are refused for a wide stop: 18,159 `STOP_TOO_WIDE` against 5,412.
- **What `next`'s rule adds:** it needs a reversal candle that closes straight through the open of the run just before it, which is a displacement. On these trades, that requirement filters out bad setups.
- **By market** (R a trade after costs; every bucket is under 30 trades except crt's US100 and US30):

  | Market | next | run | crt |
  |---|---|---|---|
  | EURUSD | +1.07 (15) | +1.55 (17) | +0.91 (22) |
  | GBPUSD | +0.25 (22) | −1.04 (24) | −0.24 (25) |
  | US100 | +0.50 (18) | −1.09 (26) | +0.09 (30) |
  | US30 | +0.82 (23) | −0.40 (29) | −0.39 (30) |
  | US500 | −0.66 (24) | −0.56 (24) | −0.43 (27) |
  | XAUUSD | −0.25 (12) | −0.77 (27) | −1.02 (13) |

- **Against the pass mark** of 2026-10-07: neither variant passes any criterion except the trade count.

## What it means

- **The default stays `"next"`.** Nothing here is worth a confirmation run.
- **The indicator's CISD reads the chart the way the trader sees it,** so the settings stay for Noculus. A `run` or `crt` session puts the engine's CISD where the indicator draws it. That is a visual match, not an edge.
- **The engine's own CISD was not the flaw it looked like.** Its insistence on an immediate close through the run is displacement, and it is part of what makes `fresh_near_gap` positive on this slice (which still failed its confirmation, −0.47R).
- **The C1/C2 frame alone carries no edge** in the engine's execution either, as in task 338. The edge, if any, is in which side the trader picks (the bias), not in the setup's anatomy.
- **A possible next step, not built:** the indicator's anchored level combined with a displacement requirement, meaning a close through the level within a few candles of the extreme, leaving an FVG. That is Model A's `DISPLACED`. It would need its own pre-registration; nothing here is tuned.

Scratch analysis: `cisd_362_analysis.py` (the shared and new trades, stop distances in M15 ATR, raid ages).
