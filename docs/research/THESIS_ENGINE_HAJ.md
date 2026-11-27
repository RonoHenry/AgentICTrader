# H-AJ: the Thesis Engine V4's test on a year no version was shaped on

Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-06, 959c2cc) before V4's code existed. Machine v1, settings v4. Judged on `focus-2025-2026h1`: 8 markets, bars from 1 January 2025, theses from the week of 6 July 2025 to the week closing 3 July 2026, against V1 on the same year. Not a try: its sides are hindsight. 2021-22 is reported, not judged: V4 was shaped by H-AI's results there.

**Verdict: H-AJ FAILS.**

- ✗ ORACLE net R > 0 with its interval above 0
- ✗ positive in at least 6 of 8 markets
- ✗ break-even weekly hit rate, a week, below V1's 58.8%

Break-even weekly hit rate on the judged year: V4 66.1% a week (the registered measure), V1 58.8%; a trade: V4 60.1%, V1 54.1%.

## The judged year (July 2025 to June 2026)

| Run | Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | Markets > 0 | Buys | Sells | Median stop (spreads) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V4 | ORACLE | 107 | 374 | +0.460 | [-0.034, +1.046] | +0.519 | +49.2 | +0.132 | 29% | 5/8 | -0.328 | +1.031 | 23.4 |
| V4 | MIRROR | 137 | 370 | -0.693 | [-0.868, -0.456] | -0.661 | -94.9 | -0.256 | 9% | 0/8 | -0.491 | -0.816 | 28.5 |
| V4 | RANDOM | 122 | 374 | -0.199 | [-0.560, +0.244] | -0.157 | -24.3 | -0.065 | 17% | 2/8 | -0.461 | -0.046 | 25.1 |
| V4 | W1TREND | 67 | 161 | -0.357 | [-0.718, +0.110] | -0.330 | -23.9 | -0.149 | 16% | 2/8 | -0.556 | -0.273 | 28.6 |
| V1 | ORACLE | 436 | 374 | +0.682 | [+0.301, +1.116] | +0.800 | +297.5 | +0.795 | 19% | 7/8 | +0.407 | +0.974 | 15.2 |
| V1 | MIRROR | 523 | 370 | -0.804 | [-0.903, -0.686] | -0.773 | -420.4 | -1.136 | 4% | 0/8 | -0.795 | -0.809 | 14.7 |
| V1 | RANDOM | 476 | 374 | -0.066 | [-0.357, +0.273] | +0.002 | -31.5 | -0.084 | 11% | 3/8 | -0.016 | -0.106 | 15.1 |
| V1 | W1TREND | 187 | 161 | -0.403 | [-0.715, -0.031] | -0.351 | -75.4 | -0.468 | 9% | 2/8 | -0.659 | -0.282 | 16.0 |

## By market on the judged year (net R a trade)

| Market | V4 ORACLE | V4 MIRROR | V1 ORACLE | V1 MIRROR |
|---|---|---|---|---|
| XAUUSD | +1.952 | -1.007 | +1.554 | -0.995 |
| EURUSD | +0.887 | -0.551 | +0.628 | -0.899 |
| GBPUSD | +0.145 | -0.125 | +0.924 | -0.804 |
| US100 | -0.167 | -0.827 | -0.001 | -0.986 |
| US500 | -1.009 | -1.006 | +0.007 | -0.522 |
| US30 | +0.776 | -0.947 | +0.664 | -1.007 |
| GER40 | +0.190 | -0.382 | +0.949 | -0.427 |
| UK100 | -0.475 | -1.005 | +0.434 | -0.678 |

## V4's ORACLE by setup frame on the judged year

| Setup | Refining CISD | Trades | Net R a trade | Win |
|---|---|---|---|---|
| M15 | M1 | 55 | -0.163 | 13% |
| M30 | M3 | 52 | +1.118 | 46% |

V4's ORACLE without its ten best trades: -0.282; median -1.004; win 29%; exits SL 75 (-1.01), TIME 19 (+3.01), TP 13 (+5.19).

## V4's hands by frame on the judged year

| | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| entries: M15 setup, M1 CISD | 55 | 52 | 57 | 30 |
| entries: M30 setup, M3 CISD | 52 | 85 | 65 | 37 |
| expired, after pull-back: M30 | 5 | 6 | 4 | 2 |
| expired, with no pull-back: M15 | 11 | 14 | 12 | 10 |
| expired, with no pull-back: M30 | 27 | 36 | 37 | 13 |
| failed beyond the sweep: M15 | 14 | 17 | 14 | 6 |
| failed beyond the sweep: M30 | 14 | 23 | 16 | 5 |
| no displacement: M15 | 679 | 770 | 669 | 276 |
| no displacement: M30 | 697 | 936 | 773 | 314 |
| pull-backs: M15 | 86 | 89 | 92 | 42 |
| pull-backs: M30 | 83 | 135 | 100 | 47 |
| setups: M15 | 120 | 124 | 123 | 60 |
| setups: M30 | 154 | 197 | 169 | 68 |
| skips: stop_too_small | 22 | 35 | 30 | 8 |
| skips: target_too_close | 5 | 3 | 6 | 1 |
| sweeps: ASIA pool, M30 setup | 405 | 650 | 494 | 192 |
| sweeps: D1 pool, M30 setup | 120 | 247 | 161 | 77 |
| sweeps: H1 pool, M15 setup | 982 | 1295 | 1063 | 431 |
| sweeps: H4 pool, M30 setup | 514 | 816 | 605 | 239 |
| takeovers | 680 | 1131 | 838 | 334 |

## V4's funnel on the judged year

| | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| at level → armed | 1569 | 1874 | 1599 | 608 |
| cancelled | 0 | 0 | 0 | 0 |
| ends delivered | 206 | 51 | 131 | 55 |
| ends expired | 142 | 195 | 167 | 95 |
| ends invalidated | 26 | 124 | 76 | 11 |
| expired | 0 | 0 | 0 | 0 |
| fills | 107 | 137 | 122 | 67 |
| hands failed | 563 | 832 | 648 | 282 |
| no displacement | 1376 | 1706 | 1442 | 590 |
| orders | 107 | 137 | 122 | 67 |
| partials | 0 | 0 | 0 | 0 |
| refused: more than 5 ADR away | 9 | 9 | 10 | 9 |
| refused: no draw | 27 | 28 | 25 | 45 |
| refused: no protected level | 6 | 9 | 7 | 0 |
| refused: no side | 0 | 0 | 0 | 201 |
| rejected | 0 | 0 | 0 | 0 |
| skips | 27 | 38 | 36 | 9 |
| skips stop_too_small | 22 | 35 | 30 | 8 |
| skips target_too_close | 5 | 3 | 6 | 1 |
| sweeps | 2021 | 3008 | 2323 | 939 |
| theses | 374 | 370 | 374 | 161 |
| theses armed | 312 | 336 | 317 | 123 |
| theses at a level | 315 | 341 | 322 | 124 |

## V1's funnel on the judged year

| | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| at level → armed | 968 | 1101 | 987 | 343 |
| cancelled | 0 | 0 | 0 | 0 |
| ends delivered | 207 | 51 | 131 | 55 |
| ends expired | 141 | 195 | 167 | 95 |
| ends invalidated | 26 | 124 | 76 | 11 |
| expired | 0 | 0 | 0 | 0 |
| fills | 436 | 523 | 476 | 187 |
| hands failed | 229 | 412 | 304 | 109 |
| no displacement | 0 | 0 | 0 | 0 |
| orders | 436 | 523 | 476 | 187 |
| partials | 0 | 0 | 0 | 0 |
| refused: more than 5 ADR away | 9 | 9 | 10 | 9 |
| refused: no draw | 27 | 28 | 25 | 45 |
| refused: no protected level | 6 | 9 | 7 | 0 |
| refused: no side | 0 | 0 | 0 | 201 |
| rejected | 0 | 0 | 0 | 0 |
| skips | 950 | 1254 | 1023 | 323 |
| skips stop_too_small | 935 | 1252 | 1016 | 323 |
| skips target_too_close | 15 | 2 | 7 | 0 |
| sweeps | 1729 | 2357 | 1932 | 657 |
| theses | 374 | 370 | 374 | 161 |
| theses armed | 317 | 341 | 322 | 124 |
| theses at a level | 320 | 350 | 329 | 127 |

## The development window, 2021-22 (reported, not judged)

V4 on H-AG's arms, data and theses; V1, V2 and V3 from their own registered runs.

| Run | Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | Markets > 0 | Buys | Sells | Median stop (spreads) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V4 | ORACLE | 125 | 467 | +0.929 | [+0.434, +1.460] | +1.050 | +116.1 | +0.249 | 36% | 6/8 | +1.224 | +0.600 | 19.4 |
| V4 | MIRROR | 225 | 465 | -0.801 | [-0.895, -0.681] | -0.780 | -180.2 | -0.387 | 8% | 0/8 | -0.788 | -0.814 | 21.8 |
| V4 | RANDOM | 178 | 464 | -0.038 | [-0.346, +0.321] | +0.025 | -6.7 | -0.014 | 19% | 4/8 | +0.242 | -0.288 | 19.6 |
| V4 | W1TREND | 62 | 230 | -0.411 | [-0.803, +0.082] | -0.366 | -25.5 | -0.111 | 11% | 1/8 | -0.245 | -0.627 | 19.2 |
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

## V4's hands by frame on 2021-22

| | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| entries: M15 setup, M1 CISD | 51 | 72 | 63 | 24 |
| entries: M30 setup, M3 CISD | 74 | 153 | 115 | 38 |
| expired, after pull-back: M15 | 0 | 1 | 0 | 0 |
| expired, after pull-back: M30 | 4 | 5 | 5 | 4 |
| expired, with no pull-back: M15 | 15 | 12 | 12 | 7 |
| expired, with no pull-back: M30 | 50 | 57 | 51 | 21 |
| failed beyond the sweep: M15 | 17 | 33 | 25 | 7 |
| failed beyond the sweep: M30 | 12 | 45 | 23 | 8 |
| no displacement: M15 | 800 | 1035 | 864 | 280 |
| no displacement: M30 | 815 | 1202 | 1025 | 331 |
| pull-backs: M15 | 130 | 181 | 154 | 52 |
| pull-backs: M30 | 136 | 249 | 182 | 65 |
| setups: M15 | 175 | 216 | 190 | 66 |
| setups: M30 | 218 | 353 | 268 | 105 |
| skips: stop_too_small | 91 | 112 | 96 | 31 |
| skips: target_too_close | 17 | 14 | 10 | 6 |
| sweeps: ASIA pool, M30 setup | 544 | 891 | 703 | 230 |
| sweeps: D1 pool, M30 setup | 190 | 349 | 268 | 88 |
| sweeps: H1 pool, M15 setup | 1262 | 1809 | 1504 | 475 |
| sweeps: H4 pool, M30 setup | 654 | 1063 | 828 | 276 |
| takeovers | 934 | 1618 | 1246 | 404 |

Run time 20.8 minutes.
