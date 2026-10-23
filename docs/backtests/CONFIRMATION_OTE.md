# The entry in the sweep's OTE: one confirmation, from the box run's trades

**Pre-registered 2026-10-23, while the confirmation run of `CONFIRMATION_D1_BOX.md` was still in its engine analysis.** None of its results had been read. The commit that adds this file is the pre-registration. Nothing in this section changes after it, and the result is appended below it.

## Why

The trader (2026-10-23) showed the engine's GBPUSD short of Wednesday 29 January 2025 on a lower timeframe: "look at the lower time frame algorithmic signatures here". The sequence:
- the sweep of the 01:43 high (1.24611) at 02:21 (1.24629);
- a displacement that broke the 02:00 swing low (1.24510), down to 1.24454;
- two retracements into 0.62-0.65 of that leg.

The engine's limit at 1.24559 (0.60 of the leg) filled at 03:05 and reached its 5.4R target at 07:18. That morning's loser (02:00) had entered on the smaller leg from the 01:43 high, which the real sweep later took.

The trader's Model A (2026-10-15, step 5) names the same zone: the retracement into the optimal trade entry, 0.62-0.79 of the new range, before entry.

**On the exploration slice** (`fresh_near_gap`, run `fb2bef51892d`, 114 trades; `scripts/ote_split.py`):

| Trades | n | R a trade (95%) | Total | Profit factor | Drawdown |
|---|---|---|---|---|---|
| Entry in 0.62-0.79 of the sweep's leg | 55 | +0.90 [−0.05, +1.94] | +49.5R | 2.14 | 13.3R |
| The rest | 59 | −0.32 [−0.88, +0.39] | −19.1R | 0.66 | 29.8R |

- The difference is +1.22R a trade [+0.07, +2.40]. It is better in the OTE in 5 of 6 markets (not US30) and 5 of 6 months (not April).
- Without its three largest winners, the OTE group still makes +20R over 52 trades; the rest, −48.5R over 56.
- **With the box** (`fresh_near_gap_box`, run `e5347180fc81`): 39 trades in the OTE, +1.23R [+0.05, +2.55], profit factor 2.65, drawdown 11.4R, costs 11%. The other 31 make +0.01R.
- **Disclosed:** the band is the trader's, set on 2026-10-15, not fitted here. But the leg position was one of five features tried on these 114 trades (a structure break after the sweep, the leg position, the displacement's size, a sweep inside a killzone, and their combination). And two hypotheses are now registered on this period (the box and this one), which doubles the chance that one passes by luck.

## What is tested

No new run. The trades of the registered confirmation run (`config/backtests/confirm.toml`, 2025-07-01 to 2026-07-01, the run of `CONFIRMATION_D1_BOX.md`) are split by `scripts/ote_split.py` as committed with this file:
- **The sweep extreme X:** the highest high (a short) or lowest low (a long) on M1 since the open of the strategy calendar's H4 candle before the one holding the decision time. H4 is anchored at 17:00 New York; this is the variants' raid window.
- **L:** the opposite extreme from X's minute to the decision time.
- **pos** = (entry − L) / (X − L), mirrored for longs. **In the OTE** when 0.62 ≤ pos ≤ 0.79.

**Judged:** the OTE trades of `fresh_near_gap`.
- They pass on the backtester's pass mark of 2026-10-07, with its own statistics (`algo_backtester.metrics`, 10,000 resamples, seed 20261007). All five must hold:

  | Criterion | Pass |
  |---|---|
  | Filled trades | ≥ 100 |
  | Net expectancy | > 0R, and the lower bound of its 95% bootstrap interval > 0R |
  | Profit factor after costs | ≥ 1.3 |
  | Max drawdown | ≤ 15R |
  | Cost share | costs ≤ 40% of gross R |

**Reported, not judged:**
- the rest of `fresh_near_gap`'s trades;
- the same split of `fresh_near_gap_box`'s trades;
- each market's split.

## The judgement, decided now

- **Pass:** the leg position becomes an order rule (a liquidity-engine task: refuse a setup whose entry is outside 0.62-0.79 of the sweep's leg), built and then tested on data after this period (the hold-out, the paper forward test). A split of finished trades ignores the 3-trade limit: refusing some trades frees slots for others, so the rule's own run is the measure.
- **Fail:** the report names the criteria that failed. No band, definition or criterion is changed and rerun on this period.

## Result

*(appended after the run)*
