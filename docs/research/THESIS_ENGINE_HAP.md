# H-AP: AlgoMindDIS v4, the week as it unfolds

Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-09, 3bf3e87) before its code. Try 32. The Thesis Engine runs at V1.

## 2021-22

**H-AP FAILS on 2021-22.**

- ✗ net R a trade above zero, with its 95% market-week interval above zero
- ✗ positive in at least 6 of 8 markets
- ✗ positive without its 5 best trades

| Arm | Trades | Net R a trade | 95% (market-weeks) | Total R | Win | Without its 5 best | Markets > 0 | Buys | Sells |
|---|---|---|---|---|---|---|---|---|---|
| UNFOLD | 143 | -0.121 | [-0.427, +0.223] | -17.2 | 19% | -0.386 | 1/8 | -0.436 | +0.157 |
| MIRROR | 69 | -0.086 | [-0.568, +0.529] | -5.9 | 19% | -0.583 | 2/8 | -0.379 | +0.369 |
| RANDOM | 106 | -0.166 | [-0.509, +0.231] | -17.6 | 19% | -0.495 | 4/8 | -0.567 | +0.357 |
| NO_WITHDRAW | 167 | -0.154 | [-0.442, +0.173] | -25.7 | 19% | -0.398 | 1/8 | -0.519 | +0.173 |
| V1_GEOMETRY | 41 | +0.016 | [-0.756, +1.047] | +0.7 | 15% | -0.959 | 3/8 | +1.028 | -0.776 |

Break-even side, a trade: –.

**The funnel and the reads.**

- events: 296
- reads: 276
- refused: {'no reachable draw': 15, "at the week's close": 5}
- market_weeks: 512
- market_weeks_with_a_side: 220
- hours_in_median: 60.0
- draw_adr_median: 1.408
- protected_adr_median: 0.478
- right_to_close: 0.493
- bullish_share: 0.42
- withdrawn_share: 0.678

**By market (UNFOLD: events, reads, net R a trade).**

| Market | Events | Reads | Net R | Exits by arm |
|---|---|---|---|---|
| XAUUSD | 46 | 46 | +0.090 | {'WITHDRAWN': 27, 'INVALIDATED': 3, 'EXPIRED': 9, 'DELIVERED': 7} |
| EURUSD | 37 | 34 | -0.199 | {'INVALIDATED': 3, 'WITHDRAWN': 17, 'DELIVERED': 2, 'EXPIRED': 12} |
| GBPUSD | 43 | 37 | -0.006 | {'INVALIDATED': 6, 'WITHDRAWN': 19, 'DELIVERED': 6, 'EXPIRED': 6} |
| US100 | 42 | 40 | -0.110 | {'EXPIRED': 9, 'INVALIDATED': 6, 'WITHDRAWN': 21, 'DELIVERED': 4} |
| US500 | 32 | 29 | -0.430 | {'INVALIDATED': 6, 'WITHDRAWN': 13, 'EXPIRED': 7, 'DELIVERED': 3} |
| US30 | 32 | 32 | -0.418 | {'WITHDRAWN': 21, 'EXPIRED': 4, 'DELIVERED': 4, 'INVALIDATED': 3} |
| GER40 | 35 | 31 | -0.240 | {'WITHDRAWN': 16, 'INVALIDATED': 6, 'EXPIRED': 8, 'DELIVERED': 1} |
| UK100 | 29 | 27 | – | {'WITHDRAWN': 18, 'INVALIDATED': 2, 'EXPIRED': 6, 'DELIVERED': 1} |

Run time 1.2 minutes.
