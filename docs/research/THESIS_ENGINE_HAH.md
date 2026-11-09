# H-AH: the Thesis Engine V2's conversion test

Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-05) before V2's code existed, and amended before it ran (ties between levels). Machine v1, settings v2; `mt5-m1-develop`, 8 markets, H-AG's theses from the week of 4 October 2021. Not a try: its sides are hindsight. The development data favours V2, because the stack gate came from a look at H-AG's trades.

**Verdict: H-AH FAILS.**

- ✗ ORACLE net R > 0 with its interval above 0
- ✗ positive in at least 6 of 8 markets
- ✗ break-even weekly hit rate, a week, below V1's 58.3%

Break-even weekly hit rate: 71.2% a week, the registered measure (V1 58.3%); 56.7% a trade (V1 49.4%).

V1, rerun on the same theses, matches H-AG's trades.

## The arms

| Run | Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | Markets > 0 | Buys | Sells | Median stop (spreads) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V2 | ORACLE | 67 | 467 | +0.574 | [-0.352, +1.655] | +0.716 | +38.5 | +0.082 | 16% | 4/8 | +0.928 | +0.287 | 13.0 |
| V2 | MIRROR | 126 | 465 | -0.751 | [-0.903, -0.573] | -0.710 | -94.7 | -0.204 | 8% | 0/8 | -0.750 | -0.753 | 13.0 |
| V2 | RANDOM | 95 | 464 | -0.120 | [-0.652, +0.565] | -0.036 | -11.4 | -0.025 | 15% | 2/8 | +0.005 | -0.237 | 13.0 |
| V2 | W1TREND | 28 | 230 | -0.519 | [-0.960, +0.023] | -0.438 | -14.5 | -0.063 | 14% | 2/8 | -0.221 | -0.776 | 11.3 |
| V1 | ORACLE | 412 | 467 | +0.841 | [+0.461, +1.256] | +1.009 | +346.4 | +0.742 | 23% | 7/8 | +0.949 | +0.720 | 13.6 |
| V1 | MIRROR | 586 | 465 | -0.821 | [-0.899, -0.729] | -0.792 | -481.3 | -1.035 | 5% | 1/8 | -0.808 | -0.837 | 13.6 |
| V1 | RANDOM | 498 | 464 | -0.072 | [-0.319, +0.191] | +0.013 | -35.9 | -0.077 | 13% | 4/8 | -0.028 | -0.117 | 13.8 |
| V1 | W1TREND | 166 | 230 | +0.021 | [-0.433, +0.560] | +0.118 | +3.4 | +0.015 | 14% | 3/8 | -0.315 | +0.399 | 13.4 |
| V2 + partial | ORACLE | 67 | 467 | +0.250 | [-0.421, +1.036] | +0.370 | +16.8 | +0.036 | 21% | 3/8 | +0.495 | +0.051 | 13.0 |
| V2 + partial | MIRROR | 127 | 465 | -0.578 | [-0.730, -0.417] | -0.529 | -73.5 | -0.158 | 19% | 0/8 | -0.604 | -0.557 | 13.0 |
| V2 + partial | RANDOM | 96 | 464 | -0.225 | [-0.603, +0.253] | -0.148 | -21.6 | -0.047 | 22% | 2/8 | -0.215 | -0.234 | 13.1 |
| V2 + partial | W1TREND | 28 | 230 | -0.631 | [-0.915, -0.310] | -0.580 | -17.7 | -0.077 | 18% | 1/8 | -0.709 | -0.563 | 11.3 |

## Break-even weekly hit rates

| Run | A week | A trade |
|---|---|---|
| V2 | 71.2% | 56.7% |
| V1 | 58.3% | 49.4% |
| V2 + partial | 81.5% | 69.8% |

## ORACLE's robustness

| Run | Without the ten best | Median | Win | 2021 | 2022 | Exits (count, mean R) |
|---|---|---|---|---|---|---|
| V2 | -0.972 | -1.014 | 16% | +1.125 | +0.441 | SL 56 (-1.02), TIME 5 (+6.51), TP 6 (+10.47) |
| V1 | +0.426 | -1.006 | 23% | +0.537 | +0.916 | SL 318 (-1.02), TIME 48 (+6.34), TP 46 (+7.94) |
| V2 + partial | -0.876 | -1.013 | 21% | +0.873 | +0.100 | SL 57 (-0.88), TIME 4 (+4.70), TP 6 (+7.98) |

## By market (net R a trade)

| Market | V2 ORACLE | V2 MIRROR | V1 ORACLE | V1 MIRROR | V2 + partial ORACLE | V2 + partial MIRROR |
|---|---|---|---|---|---|---|
| XAUUSD | +2.590 | -0.751 | +0.236 | -0.953 | +1.524 | -0.616 |
| EURUSD | +0.078 | -0.750 | +1.182 | -0.740 | -0.184 | -0.358 |
| GBPUSD | -0.189 | -1.026 | +1.827 | -0.787 | -0.185 | -0.762 |
| US100 | -1.005 | -0.552 | +1.078 | -0.947 | -1.005 | -0.378 |
| US500 | +0.667 | -1.005 | +0.517 | -0.821 | +0.443 | -1.005 |
| US30 | -1.002 | -0.256 | +0.476 | -0.739 | -0.602 | -0.485 |
| GER40 | +0.584 | -1.003 | +0.258 | -0.760 | +0.500 | -1.003 |
| UK100 | – | – | – | +0.136 | – | – |

## The funnel (all markets)

| | V1 ORACLE | V2 ORACLE | V1 MIRROR | V2 MIRROR | V2 RANDOM | V2 W1TREND |
|---|---|---|---|---|---|---|
| at level → armed | 1563 | 2065 | 1825 | 2571 | 2349 | 722 |
| cancelled | 0 | 0 | 0 | 2 | 1 | 1 |
| ends delivered | 250 | 250 | 62 | 62 | 155 | 109 |
| ends expired | 198 | 198 | 232 | 232 | 219 | 109 |
| ends invalidated | 19 | 19 | 171 | 171 | 90 | 12 |
| expired | 0 | 33 | 0 | 34 | 34 | 15 |
| fills | 412 | 67 | 586 | 126 | 95 | 28 |
| hands failed | 442 | 2309 | 835 | 3830 | 3021 | 1013 |
| no displacement | 0 | 3328 | 0 | 4938 | 4025 | 1391 |
| orders | 412 | 100 | 586 | 162 | 130 | 44 |
| partials | 0 | 0 | 0 | 0 | 0 | 0 |
| refused: more than 5 ADR away | 10 | 10 | 17 | 17 | 14 | 17 |
| refused: no draw | 27 | 27 | 25 | 25 | 28 | 45 |
| refused: no protected level | 8 | 8 | 5 | 5 | 6 | 0 |
| refused: no side | 0 | 0 | 0 | 0 | 0 | 220 |
| rejected | 0 | 0 | 0 | 0 | 0 | 0 |
| skips | 2430 | 494 | 3280 | 697 | 593 | 190 |
| skips stop_too_small | 2413 | 493 | 3269 | 697 | 593 | 190 |
| skips target_too_close | 17 | 1 | 11 | 0 | 0 | 0 |
| sweeps | 3516 | 3179 | 5021 | 5086 | 4089 | 1334 |
| theses | 467 | 467 | 465 | 465 | 464 | 230 |
| theses armed | 373 | 369 | 439 | 433 | 400 | 143 |
| theses at a level | 375 | 372 | 442 | 436 | 402 | 143 |

Run time 21.1 minutes.
