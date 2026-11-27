# H-AI: the Thesis Engine V3's conversion test

Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-06, 3ef61a3) before V3's code existed. Machine v1, settings v3; `mt5-m1-develop`, 8 markets, H-AG's theses from the week of 4 October 2021. Not a try: its sides are hindsight. The development data favours V3: it was designed after V2's results on these data and a review of five weeks chosen from V2's trades.

**Verdict: H-AI FAILS.**

- ✗ ORACLE net R > 0 with its interval above 0
- ✗ positive in at least 6 of 8 markets
- ✗ break-even weekly hit rate, a week, below V1's 58.3%

Break-even weekly hit rate: 77.4% a week, the registered measure (V1 58.3%, V2 71.2%); 57.6% a trade.

## The arms

| Run | Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | Markets > 0 | Buys | Sells | Median stop (spreads) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V3 | ORACLE | 69 | 467 | +0.614 | [-0.240, +1.658] | +0.751 | +42.4 | +0.091 | 19% | 3/8 | +1.389 | +0.052 | 13.8 |
| V3 | MIRROR | 173 | 465 | -0.834 | [-0.941, -0.702] | -0.806 | -144.3 | -0.310 | 6% | 0/8 | -0.801 | -0.862 | 14.7 |
| V3 | RANDOM | 115 | 464 | -0.202 | [-0.667, +0.407] | -0.135 | -23.2 | -0.050 | 12% | 1/8 | +0.097 | -0.448 | 14.7 |
| V3 | W1TREND | 45 | 230 | -0.014 | [-0.793, +1.180] | +0.077 | -0.6 | -0.003 | 16% | 2/8 | +0.752 | -0.573 | 13.9 |
| V2 | ORACLE | 67 | 467 | +0.574 | [-0.352, +1.655] | +0.716 | +38.5 | +0.082 | 16% | 4/8 | +0.928 | +0.287 | 13.0 |
| V2 | MIRROR | 126 | 465 | -0.751 | [-0.903, -0.573] | -0.710 | -94.7 | -0.204 | 8% | 0/8 | -0.750 | -0.753 | 13.0 |
| V2 | RANDOM | 95 | 464 | -0.120 | [-0.652, +0.565] | -0.036 | -11.4 | -0.025 | 15% | 2/8 | +0.005 | -0.237 | 13.0 |
| V2 | W1TREND | 28 | 230 | -0.519 | [-0.960, +0.023] | -0.438 | -14.5 | -0.063 | 14% | 2/8 | -0.221 | -0.776 | 11.3 |
| V1 | ORACLE | 412 | 467 | +0.841 | [+0.461, +1.256] | +1.009 | +346.4 | +0.742 | 23% | 7/8 | +0.949 | +0.720 | 13.6 |
| V1 | MIRROR | 586 | 465 | -0.821 | [-0.899, -0.729] | -0.792 | -481.3 | -1.035 | 5% | 1/8 | -0.808 | -0.837 | 13.6 |
| V1 | RANDOM | 498 | 464 | -0.072 | [-0.319, +0.191] | +0.013 | -35.9 | -0.077 | 13% | 4/8 | -0.028 | -0.117 | 13.8 |
| V1 | W1TREND | 166 | 230 | +0.021 | [-0.433, +0.560] | +0.118 | +3.4 | +0.015 | 14% | 3/8 | -0.315 | +0.399 | 13.4 |

## ORACLE's robustness

| Run | Without the ten best | Median | Win | 2021 | 2022 | Exits (count, mean R) |
|---|---|---|---|---|---|---|
| V3 | -0.795 | -1.012 | 19% | -0.024 | +0.807 | SL 55 (-1.02), TIME 6 (+7.47), TP 8 (+6.70) |
| V2 | -0.972 | -1.014 | 16% | +1.125 | +0.441 | SL 56 (-1.02), TIME 5 (+6.51), TP 6 (+10.47) |
| V1 | +0.426 | -1.006 | 23% | +0.537 | +0.916 | SL 318 (-1.02), TIME 48 (+6.34), TP 46 (+7.94) |

## ORACLE by execution frame and entry

| Frame | Pool | Entry | Trades | Net R a trade | Win |
|---|---|---|---|---|---|
| M30 | D1 | limit | 8 | +1.835 | 38% |
| M30 | ASIA | limit | 22 | +1.010 | 27% |
| M20 | H4 | limit | 18 | +1.495 | 22% |
| M5 | H1 | limit | 19 | -1.022 | 0% |
| M3 | M30 | limit | 2 | -1.004 | 0% |

## By market (net R a trade)

| Market | V3 ORACLE | V3 MIRROR | V2 ORACLE | V1 ORACLE |
|---|---|---|---|---|
| XAUUSD | +0.511 | -0.943 | +2.590 | +0.236 |
| EURUSD | +2.337 | -0.700 | +0.078 | +1.182 |
| GBPUSD | -0.177 | -0.793 | -0.189 | +1.827 |
| US100 | +1.054 | -1.006 | -1.005 | +1.078 |
| US500 | -1.006 | -0.895 | +0.667 | +0.517 |
| US30 | -1.003 | -0.703 | -1.002 | +0.476 |
| GER40 | -0.331 | -1.003 | +0.584 | +0.258 |
| UK100 | – | – | – | – |

## The funnel (all markets)

| | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| at level → armed | 2067 | 2512 | 2285 | 692 |
| cancelled | 2 | 5 | 3 | 1 |
| ends delivered | 251 | 62 | 156 | 109 |
| ends expired | 197 | 232 | 218 | 109 |
| ends invalidated | 19 | 171 | 90 | 12 |
| expired | 85 | 84 | 88 | 35 |
| fills | 69 | 173 | 115 | 45 |
| hands failed | 1288 | 2002 | 1618 | 500 |
| no displacement | 2529 | 3557 | 3029 | 943 |
| orders | 156 | 262 | 206 | 81 |
| partials | 0 | 0 | 0 | 0 |
| refused: more than 5 ADR away | 10 | 17 | 14 | 17 |
| refused: no draw | 27 | 25 | 28 | 45 |
| refused: no protected level | 8 | 5 | 6 | 0 |
| refused: no side | 0 | 0 | 0 | 220 |
| rejected | 0 | 0 | 0 | 0 |
| skips | 431 | 494 | 441 | 157 |
| skips stop_too_small | 427 | 494 | 439 | 157 |
| skips target_too_close | 4 | 0 | 2 | 0 |
| sweeps | 3440 | 5249 | 4297 | 1345 |
| theses | 467 | 465 | 464 | 230 |
| theses armed | 369 | 433 | 400 | 143 |
| theses at a level | 372 | 436 | 402 | 143 |

## The hands by frame (all markets)

| | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| no displacement: M1 | 124 | 149 | 141 | 41 |
| no displacement: M20 | 434 | 656 | 559 | 167 |
| no displacement: M3 | 45 | 56 | 53 | 14 |
| no displacement: M30 | 494 | 770 | 628 | 219 |
| no displacement: M5 | 1432 | 1926 | 1648 | 502 |
| orders: M20 limit | 50 | 55 | 53 | 16 |
| orders: M3 limit | 2 | 0 | 0 | 0 |
| orders: M30 limit | 77 | 148 | 113 | 42 |
| orders: M5 limit | 27 | 59 | 40 | 23 |
| skips: M1 stop_too_small | 28 | 27 | 31 | 4 |
| skips: M20 stop_too_small | 56 | 53 | 47 | 23 |
| skips: M20 target_too_close | 2 | 0 | 1 | 0 |
| skips: M3 stop_too_small | 9 | 9 | 10 | 1 |
| skips: M30 stop_too_small | 67 | 109 | 77 | 33 |
| skips: M30 target_too_close | 2 | 0 | 1 | 0 |
| skips: M5 stop_too_small | 267 | 296 | 274 | 96 |
| sweeps: ASIA pool, M30 child | 578 | 929 | 740 | 246 |
| sweeps: D1 pool, M30 child | 197 | 373 | 283 | 91 |
| sweeps: H1 pool, M5 child | 1715 | 2529 | 2108 | 648 |
| sweeps: H4 pool, M20 child | 715 | 1145 | 918 | 292 |
| sweeps: M15 pool, M1 child | 156 | 194 | 175 | 48 |
| sweeps: M30 pool, M3 child | 79 | 79 | 73 | 20 |
| takeovers | 1001 | 1727 | 1352 | 428 |

Run time 16.6 minutes.
