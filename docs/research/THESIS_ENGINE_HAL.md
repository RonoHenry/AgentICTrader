# H-AL: the Thesis Engine V5's judged run on 2023-2024

Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-06, 4100a4e) before V5's code existed and before 2023-2024 was exported. Machine v1. `mt5-m1-test`: 8 markets, M1 from 1 October 2022, theses from the week of 1 January 2023 to the last complete week of 2024. Not a try: its sides are hindsight. The last unread window of 2018-2024.

**Verdict: H-AL FAILS** (V5, V1 in the 02:00-04:00 New York window).

- ✓ ORACLE net R > 0 with its interval above 0
- ✗ positive in at least 6 of 8 markets
- ✗ break-even weekly hit rate, a week, below V1's 50.0%

**V1 by H-AG's own rule on the same years: PASSES.**

- ✓ ORACLE net R > 0 with its interval above 0
- ✓ positive in at least 6 of 8 markets
- ✓ break-even weekly hit rate at most 60%

Break-even weekly hit rate on 2023-2024, a week: V5 60.7%, V1 50.0%, V1's hands kept 02:00-04:00 (H-AK's filter) 53.1%. A trade: V5 54.2%, V1 42.9%.

## The judged years (2023-2024)

| Run | Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | Markets > 0 | Buys | Sells | Median stop (spreads) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V5 | ORACLE | 236 | 728 | +0.609 | [+0.086, +1.230] | +0.779 | +143.7 | +0.197 | 20% | 5/8 | +0.986 | +0.269 | 13.3 |
| V5 | MIRROR | 314 | 741 | -0.720 | [-0.867, -0.540] | -0.672 | -226.0 | -0.305 | 6% | 0/8 | -0.654 | -0.783 | 12.9 |
| V5 | RANDOM | 269 | 732 | -0.019 | [-0.427, +0.499] | +0.098 | -5.0 | -0.007 | 12% | 3/8 | +0.191 | -0.198 | 12.9 |
| V5 | W1TREND | 69 | 306 | +0.162 | [-0.501, +0.963] | +0.283 | +11.2 | +0.036 | 19% | 3/8 | +0.918 | -0.387 | 12.6 |
| V1 | ORACLE | 554 | 728 | +0.977 | [+0.639, +1.353] | +1.159 | +541.1 | +0.743 | 29% | 7/8 | +1.092 | +0.846 | 13.1 |
| V1 | MIRROR | 748 | 741 | -0.735 | [-0.814, -0.646] | -0.691 | -549.7 | -0.742 | 7% | 0/8 | -0.782 | -0.699 | 12.9 |
| V1 | RANDOM | 680 | 732 | -0.042 | [-0.267, +0.213] | +0.060 | -28.7 | -0.039 | 16% | 3/8 | +0.030 | -0.109 | 13.0 |
| V1 | W1TREND | 190 | 306 | +0.254 | [-0.229, +0.868] | +0.388 | +48.3 | +0.158 | 20% | 3/8 | +0.845 | -0.256 | 13.1 |
| V1 kept 02:00-04:00 | ORACLE | 151 | 728 | +0.999 | [+0.258, +1.925] | +1.211 | +150.8 | +0.207 | 23% | 5/8 | +1.181 | +0.824 | 12.7 |
| V1 kept 02:00-04:00 | MIRROR | 197 | 741 | -0.882 | [-0.974, -0.766] | -0.846 | -173.8 | -0.235 | 4% | 0/8 | -0.916 | -0.849 | 12.5 |
| V1 kept 02:00-04:00 | RANDOM | 176 | 732 | +0.159 | [-0.423, +0.910] | +0.295 | +28.1 | +0.038 | 12% | 3/8 | +0.092 | +0.227 | 12.1 |
| V1 kept 02:00-04:00 | W1TREND | 40 | 306 | +0.338 | [-0.521, +1.408] | +0.494 | +13.5 | +0.044 | 20% | 4/8 | +0.574 | +0.181 | 11.6 |

## By market on 2023-2024 (net R a trade)

| Market | V5 ORACLE | V5 MIRROR | V1 ORACLE | V1 MIRROR |
|---|---|---|---|---|
| XAUUSD | +0.758 | -0.574 | +1.567 | -0.971 |
| EURUSD | +0.423 | -0.674 | +0.439 | -0.605 |
| GBPUSD | +0.577 | -0.888 | +0.477 | -0.813 |
| US100 | +1.564 | -1.004 | +1.735 | -0.639 |
| US500 | -1.006 | -1.004 | +0.594 | -0.784 |
| US30 | -1.003 | -1.003 | +1.201 | -0.588 |
| GER40 | +0.661 | -0.655 | +0.756 | -0.572 |
| UK100 | – | – | – | – |

## V5's funnel on 2023-2024

| | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| at level → armed | 2012 | 2439 | 2248 | 593 |
| cancelled | 0 | 0 | 0 | 0 |
| ends delivered | 418 | 101 | 248 | 133 |
| ends expired | 271 | 357 | 327 | 160 |
| ends invalidated | 39 | 283 | 157 | 13 |
| expired | 0 | 0 | 0 | 0 |
| fills | 236 | 314 | 269 | 69 |
| hands failed | 527 | 812 | 673 | 176 |
| no displacement | 0 | 0 | 0 | 0 |
| orders | 236 | 314 | 269 | 69 |
| partials | 0 | 0 | 0 | 0 |
| refused: more than 5 ADR away | 29 | 28 | 26 | 29 |
| refused: no draw | 72 | 51 | 61 | 107 |
| refused: no protected level | 3 | 12 | 13 | 0 |
| refused: no side | 0 | 0 | 0 | 390 |
| rejected | 0 | 0 | 0 | 0 |
| skips | 1098 | 1613 | 1378 | 363 |
| skips stop_too_small | 1092 | 1606 | 1368 | 361 |
| skips target_too_close | 6 | 7 | 10 | 2 |
| sweeps | 1967 | 2889 | 2466 | 637 |
| theses | 728 | 741 | 732 | 306 |
| theses armed | 589 | 683 | 631 | 174 |
| theses at a level | 608 | 697 | 653 | 183 |

## V1's funnel on 2023-2024

| | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| at level → armed | 2971 | 3448 | 3213 | 824 |
| cancelled | 0 | 0 | 0 | 0 |
| ends delivered | 418 | 101 | 248 | 133 |
| ends expired | 271 | 357 | 327 | 160 |
| ends invalidated | 39 | 283 | 157 | 13 |
| expired | 0 | 0 | 0 | 0 |
| fills | 554 | 748 | 680 | 190 |
| hands failed | 968 | 1664 | 1347 | 362 |
| no displacement | 0 | 0 | 0 | 0 |
| orders | 554 | 748 | 680 | 190 |
| partials | 0 | 0 | 0 | 0 |
| refused: more than 5 ADR away | 29 | 28 | 26 | 29 |
| refused: no draw | 72 | 51 | 61 | 107 |
| refused: no protected level | 3 | 12 | 13 | 0 |
| refused: no side | 0 | 0 | 0 | 390 |
| rejected | 0 | 0 | 0 | 0 |
| skips | 4765 | 6850 | 5845 | 1462 |
| skips stop_too_small | 4741 | 6825 | 5820 | 1455 |
| skips target_too_close | 24 | 25 | 25 | 7 |
| sweeps | 6801 | 9947 | 8469 | 2136 |
| theses | 728 | 741 | 732 | 306 |
| theses armed | 603 | 694 | 647 | 182 |
| theses at a level | 608 | 697 | 653 | 183 |

## V5 on the windows it was chosen on (reported, not judged)

2021-22 (H-AG's data and theses) and July 2025 to June 2026 (H-AJ's), V1 from their registered runs.

| Run | Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | Markets > 0 | Buys | Sells | Median stop (spreads) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V5 2021-22 | ORACLE | 222 | 467 | +0.976 | [+0.486, +1.525] | +1.145 | +216.7 | +0.464 | 25% | 6/8 | +0.915 | +1.057 | 14.6 |
| V5 2021-22 | MIRROR | 318 | 465 | -0.708 | [-0.849, -0.541] | -0.668 | -225.3 | -0.485 | 6% | 0/8 | -0.638 | -0.795 | 14.3 |
| V5 2021-22 | RANDOM | 267 | 464 | +0.137 | [-0.230, +0.531] | +0.236 | +36.6 | +0.079 | 15% | 4/8 | +0.123 | +0.154 | 14.4 |
| V5 2021-22 | W1TREND | 76 | 230 | +0.070 | [-0.484, +0.742] | +0.176 | +5.3 | +0.023 | 16% | 4/8 | -0.018 | +0.169 | 13.7 |
| V1 2021-22 | ORACLE | 412 | 467 | +0.841 | [+0.461, +1.256] | +1.009 | +346.4 | +0.742 | 23% | 7/8 | +0.949 | +0.720 | 13.6 |
| V1 2021-22 | MIRROR | 586 | 465 | -0.821 | [-0.899, -0.729] | -0.792 | -481.3 | -1.035 | 5% | 1/8 | -0.808 | -0.837 | 13.6 |
| V1 2021-22 | RANDOM | 498 | 464 | -0.072 | [-0.319, +0.191] | +0.013 | -35.9 | -0.077 | 13% | 4/8 | -0.028 | -0.117 | 13.8 |
| V1 2021-22 | W1TREND | 166 | 230 | +0.021 | [-0.433, +0.560] | +0.118 | +3.4 | +0.015 | 14% | 3/8 | -0.315 | +0.399 | 13.4 |
| V5 2025-26 | ORACLE | 268 | 374 | +0.914 | [+0.296, +1.634] | +1.055 | +245.0 | +0.655 | 19% | 8/8 | +0.900 | +0.930 | 16.0 |
| V5 2025-26 | MIRROR | 357 | 370 | -0.688 | [-0.838, -0.510] | -0.650 | -245.8 | -0.664 | 6% | 0/8 | -0.532 | -0.779 | 15.6 |
| V5 2025-26 | RANDOM | 306 | 374 | +0.249 | [-0.240, +0.851] | +0.347 | +76.1 | +0.203 | 13% | 7/8 | +0.429 | +0.110 | 15.8 |
| V5 2025-26 | W1TREND | 122 | 161 | -0.003 | [-0.713, +1.131] | +0.087 | -0.3 | -0.002 | 10% | 2/8 | +0.028 | -0.017 | 15.2 |
| V1 2025-26 | ORACLE | 436 | 374 | +0.682 | [+0.301, +1.116] | +0.800 | +297.5 | +0.795 | 19% | 7/8 | +0.407 | +0.974 | 15.2 |
| V1 2025-26 | MIRROR | 523 | 370 | -0.804 | [-0.903, -0.686] | -0.773 | -420.4 | -1.136 | 4% | 0/8 | -0.795 | -0.809 | 14.7 |
| V1 2025-26 | RANDOM | 476 | 374 | -0.066 | [-0.357, +0.273] | +0.002 | -31.5 | -0.084 | 11% | 3/8 | -0.016 | -0.106 | 15.1 |
| V1 2025-26 | W1TREND | 187 | 161 | -0.403 | [-0.715, -0.031] | -0.351 | -75.4 | -0.468 | 9% | 2/8 | -0.659 | -0.282 | 16.0 |

Run time 17.0 minutes.
