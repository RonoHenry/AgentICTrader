# The engine's scale fix: the exploration run (task 344)

**Run 2026-10-21/22.**
- **Command:** `python -m algo_backtester run config/backtests/focus.toml --snapshot focus-2025-2026h1` with eight variants (liquidity-engine tasks 342–343, Requirements 26.6 and 27).
- **Data:** the exploration slice (2025-01-01 to 2025-07-01), Exness M1 from the research snapshot.
- **Markets:** XAUUSD, EURUSD, GBPUSD, US100, US500, US30. GER40 and UK100 are waiting for the backtester's currency conversion.
- **Costs and account:** as in every run so far: 1% risk, 10,000 USD.

## The variants

| Variant | Entry | Fresh raid | Stop cap | TP1 | FVG |
|---|---|---|---|---|---|
| base | M15 | — | — | SD 2.0 | three candles |
| fresh | M15 | current or previous H4 candle | — | SD 2.0 | three candles |
| fresh_near | M15 | H4 | 1 M15 average range | nearer of SD 2.0 and the draw | three candles |
| gap | M15 | — | — | SD 2.0 | the gap, closed candles |
| fresh_gap | M15 | H4 | — | SD 2.0 | the gap |
| fresh_near_gap | M15 | H4 | 1 range | nearest | the gap |
| m5_gap | M5 | — | — | SD 2.0 | the gap |
| m5_fresh_near_gap | M5 | current or previous H1 candle | 1 range | nearest | the gap |

## The results

The interval is the backtester's 95% bootstrap on R per trade after costs. Stop and target are in M15 average ranges at the fill.

| Variant | Trades | Win | Before costs | After costs (95%) | Profit factor | Max drawdown | Stop | Target | Median hold |
|---|---|---|---|---|---|---|---|---|---|
| base | 181 | 15% | — | +0.02 [−0.35, +0.43] | 1.02 | 30R | 2.62 | 16.2 | 6.5 h |
| fresh | 254 | 16% | — | −0.07 [−0.35, +0.24] | 0.92 | 43R | 1.72 | 9.0 | 1.4 h |
| **fresh_near** | 109 | 16% | +0.52 | **+0.33 [−0.27, +1.00]** | 1.37 | 27R | 0.74 | 6.1 | 0.3 h |
| gap | 159 | 16% | — | +0.12 [−0.29, +0.59] | 1.15 | 30R | 2.63 | 15.9 | 7.1 h |
| fresh_gap | 285 | 17% | — | +0.07 [−0.25, +0.42] | 1.09 | 31R | 1.59 | 8.7 | 1.4 h |
| **fresh_near_gap** | 114 | 15% | +0.46 | **+0.27 [−0.30, +0.89]** | 1.31 | 27R | 0.77 | 5.9 | 0.3 h |
| m5_gap | 354 | 12% | −0.07 | −0.20 [−0.43, +0.05] | 0.76 | 82R | 1.59 | 9.3 | 1.5 h |
| m5_fresh_near_gap | 248 | 11% | −0.01 | −0.23 [−0.55, +0.11] | 0.75 | 73R | 0.62 | 3.8 | 0.2 h |

- **The scale fix works on M15.** Stops fall from 2.6 to 0.75 average ranges and targets from 16 to 6. The trader's execution (`fresh_near`, `fresh_near_gap`) makes +0.46 to +0.52R a trade before costs and +0.27 to +0.33R after. That is the best of any version so far.
  - Its interval still includes zero.
  - Its drawdown is 27R in six months, and its longest losing streak is 25–26 trades. It wins about one trade in six.
- **The FVG fix is neutral to slightly positive:** gap +0.12R against base +0.02R; with the execution, +0.27R against +0.33R. Both differences are well inside the noise.
- **M5 has no gross edge.** The same execution on M5 makes −0.01R before costs and −0.23R after: more trades, wins about one in nine, stops 0.62 ranges that noise reaches. The April 11–14 diagnostic, where M5 matched two of the trader's trades, didn't generalise.
- **The fresh raid alone doesn't help** (−0.07R). It pays only with the stop cap and the near target, as one execution.
- **Against the pass mark** of 2026-10-07 (100 trades; expectancy CI above zero; profit factor ≥ 1.3; drawdown ≤ 15R; costs ≤ 40%):

  | Variant | Fails |
  |---|---|
  | `fresh_near` | the CI and the drawdown (27R) |
  | `fresh_near_gap` | the CI, the drawdown, and costs (42%) |
  | M5 | everything but the trade count |

## What it means for the confirmation

The version registered for confirmation, `m5_fresh_near_gap`, lost on the exploration slice. It was chosen before its result existed, so that the choice couldn't follow the numbers. The confirmation is on hold (`CONFIRMATION_TRADER_EXECUTION.md`). What goes forward is the trader's decision.
