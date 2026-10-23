# Waiting out the expansion day's box: the exploration run (task 354)

**Run 2026-10-23.**
- **Command:** `python -m algo_backtester run config/backtests/focus.toml --snapshot focus-2025-2026h1 --variant fresh_near_gap --variant fresh_near_gap_box --workers 3`: one engine analysis, shared by both (liquidity-engine task 353, Requirement 29).
- **Data:** the exploration slice (2025-01-01 to 2025-07-01), Exness M1 from the research snapshot.
- **Markets:** XAUUSD, EURUSD, GBPUSD, US100, US500, US30.
- **Costs and account:** as in task 344: 1% risk, 10,000 USD.
- **Runs:** `fb2bef51892d` (`fresh_near_gap`) and `e5347180fc81` (`fresh_near_gap_box`).
- **The reference reproduces:** `fresh_near_gap` gives the same 114 trades and +0.27R as task 344's run of 2026-10-21. The uncommitted swap-cost work in the tree changes nothing here: the profile has no swap.

## Why

The trader, on Noculus (GBPUSD, 27-29 January 2025, the base engine):
- Friday 24 January expanded 155 pips. Monday to Thursday stayed inside that range, on days of 70-97 pips against a 117-pip average.
- The engine traded both sides from the middle of it, with expansion targets 140-226 pips away. Its trades reached +0.15 to +0.6R and were stopped.

`fresh_near_gap_box` is `fresh_near_gap` with `d1_box_expansion = 1.2`. While every D1 close since the last D1 candle of at least 1.2 times the 20-day mean range is inside that candle's range, a setup is refused (`IN_D1_BOX`). Only closed D1 candles are read.

## The results

The interval is the backtester's 95% bootstrap on R per trade after costs.

| Variant | Trades | Win | Before costs | After costs (95%) | Total | Profit factor | Max drawdown | Losing streak | Cost share |
|---|---|---|---|---|---|---|---|---|---|
| fresh_near_gap | 114 | 15% | +0.46 | +0.27 [−0.30, +0.87] | +30.4R | 1.31 | 27.4R | 26 | 42% |
| **fresh_near_gap_box** | 70 | 19% | +0.87 | **+0.69 [−0.13, +1.62]** | **+48.5R** | **1.83** | **14.5R** | 14 | **20%** |

- **The box removed 46 trades worth −20.0R** (−0.44R a trade, 1 win in 11), and kept the other 68 with the same outcomes (+50.5R). Skipping them freed the 3-trade limit for 2 trades the reference never took, both −1R. The box refused 2,978 decisions in all.
- **By market** (R a trade after costs; every bucket is under 30 trades, so none is a finding on its own):

  | Market | fresh_near_gap | With the box | The box removed |
  |---|---|---|---|
  | EURUSD | +1.07 (15) | +1.02 (11) | 4 trades, +4.8R |
  | GBPUSD | +0.25 (22) | +0.91 (10) | 12, −3.6R |
  | US100 | +0.50 (18) | +1.05 (11) | 7, −2.6R |
  | US30 | +0.82 (23) | +1.16 (17) | 7, −2.0R |
  | US500 | −0.66 (24) | −0.39 (14) | 11, −11.4R |
  | XAUUSD | −0.25 (12) | +0.33 (7) | 5, −5.3R |

  Five of six markets improve; EURUSD's removed trades were winners.
- **Against the pass mark** of 2026-10-07 (`CONFIRMATION_TRADER_EXECUTION.md`):

  | Criterion | Pass | fresh_near_gap | fresh_near_gap_box |
  |---|---|---|---|
  | Filled trades | ≥ 100 | 114 ✓ | 70 ✗ |
  | Expectancy, its interval's lower bound | > 0 | −0.30 ✗ | −0.13 ✗ |
  | Profit factor after costs | ≥ 1.3 | 1.31 ✓ | 1.83 ✓ |
  | Max drawdown | ≤ 15R | 27.4R ✗ | 14.5R ✓ |
  | Costs of gross R | ≤ 40% | 42% ✗ | 20% ✓ |

  The box passes three of five, against two. It fails on the trade count (six months) and on the interval, whose lower bound is still below zero.

## What it means

- **The rule cuts the drawdown in half** (27R to 14.5R) and doubles the R a trade, by refusing the trades the trader pointed at: the middle of a consolidated range with targets that only an expansion reaches.
- **It is not independent evidence yet.** The rule came from looking at these same trades on the exploration slice: the GBPUSD case, then the post-filter (`d1_box_gate.py`: 46 trades, −0.44R). This run confirms that the order rule does what the post-filter did, with the trade limit in play. It cannot confirm that the edge is real.
- **The test is the confirmation slice:** 2025-07-01 to 2026-07-07, twelve months the research has not read, run once, pre-registered, with the same pass mark. Twelve months at this rate is about 140 trades, which clears the count.
- **The default engine is unchanged** until the trader's review (LE-D18).
