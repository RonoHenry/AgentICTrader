# H-AG: the Thesis Engine's conversion test

Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-05) before it ran. Machine v1, settings v1; `mt5-m1-develop`, 8 markets, theses from the week of 4 October 2021. Not a try: its sides are hindsight.

**Verdict: H-AG PASSES.**

- ✓ ORACLE net R > 0 with its interval above 0
- ✓ positive in at least 6 of 8 markets
- ✓ break-even weekly hit rate at most 60%

Break-even weekly hit rate: +0.494 a trade (the registered measure), +0.583 a week (the trades a week included).

## The arms

| Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | Markets > 0 | Buys | Sells | Median stop (spreads) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ORACLE | 412 | 467 | +0.841 | [+0.461, +1.256] | +1.009 | +346.4 | +0.742 | 23% | 7/8 | +0.949 | +0.720 | 13.6 |
| MIRROR | 586 | 465 | -0.821 | [-0.899, -0.729] | -0.792 | -481.3 | -1.035 | 5% | 1/8 | -0.808 | -0.837 | 13.6 |
| RANDOM | 498 | 464 | -0.072 | [-0.319, +0.191] | +0.013 | -35.9 | -0.077 | 13% | 4/8 | -0.028 | -0.117 | 13.8 |
| W1TREND | 166 | 230 | +0.021 | [-0.433, +0.560] | +0.118 | +3.4 | +0.015 | 14% | 3/8 | -0.315 | +0.399 | 13.4 |

For comparison, H-N's selection stack with the week's real side made +0.17R a trade (2026-10-30, a different trigger and exits).

## By market (net R a trade)

| Market | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| XAUUSD | +0.236 | -0.953 | -0.185 | -0.247 |
| EURUSD | +1.182 | -0.740 | +0.022 | +0.189 |
| GBPUSD | +1.827 | -0.787 | +0.676 | +0.622 |
| US100 | +1.078 | -0.947 | -0.393 | +0.147 |
| US500 | +0.517 | -0.821 | -0.412 | -0.285 |
| US30 | +0.476 | -0.739 | +0.151 | -0.079 |
| GER40 | +0.258 | -0.760 | -0.804 | -1.004 |
| UK100 | – | +0.136 | +0.136 | – |

## Exits

| Arm | SL | TP | TIME | END |
|---|---|---|---|---|
| ORACLE | 318 | 46 | 48 | 0 |
| MIRROR | 555 | 7 | 24 | 0 |
| RANDOM | 430 | 29 | 39 | 0 |
| W1TREND | 139 | 11 | 16 | 0 |

## The funnel (all markets)

| | ORACLE | MIRROR | RANDOM | W1TREND |
|---|---|---|---|---|
| at level → armed | 1563 | 1825 | 1724 | 511 |
| ends delivered | 250 | 62 | 155 | 109 |
| ends expired | 198 | 232 | 219 | 109 |
| ends invalidated | 19 | 171 | 90 | 12 |
| fills | 412 | 586 | 498 | 166 |
| hands failed | 442 | 835 | 629 | 229 |
| orders | 412 | 586 | 498 | 166 |
| refused: more than 5 ADR away | 10 | 17 | 14 | 17 |
| refused: no draw | 27 | 25 | 28 | 45 |
| refused: no protected level | 8 | 5 | 6 | 0 |
| refused: no side | 0 | 0 | 0 | 220 |
| rejected | 0 | 0 | 0 | 0 |
| skips | 2430 | 3280 | 2875 | 945 |
| skips stop_too_small | 2413 | 3269 | 2862 | 939 |
| skips target_too_close | 17 | 11 | 13 | 6 |
| sweeps | 3516 | 5021 | 4290 | 1400 |
| theses | 467 | 465 | 464 | 230 |
| theses armed | 373 | 439 | 405 | 143 |
| theses at a level | 375 | 442 | 407 | 143 |

## The data

Bars dropped by the clock: {"XAUUSD": {"repeated_or_older": 0, "leading_stand_ins": 1}, "EURUSD": {"repeated_or_older": 0, "leading_stand_ins": 1}, "GBPUSD": {"repeated_or_older": 0, "leading_stand_ins": 1}, "US100": {"repeated_or_older": 0, "leading_stand_ins": 1}, "US500": {"repeated_or_older": 0, "leading_stand_ins": 1}, "US30": {"repeated_or_older": 0, "leading_stand_ins": 1}, "GER40": {"repeated_or_older": 0, "leading_stand_ins": 1}, "UK100": {"repeated_or_older": 0, "leading_stand_ins": 1}}.
Run time 2.6 minutes.

## Reading it

- **The machine turns a right weekly side into +0.84R a trade** (412 trades, 7 of 8 markets positive):
  - without its ten best trades it still makes +0.43R;
  - both periods are positive: Q4 2021 +0.54, 2022 +0.92;
  - most trades lose a little and a few win big: 23% win, median −1R. Stops are tight (a median 13.6 spreads) and the draws are far.
- **The wrong side loses −0.82R a trade, and trades more** (586 trades). That is why the break-even is 49% counted a trade but 58% counted a week. For a weekly call, 58% is the practical bar.
- **UK100 never traded.** Its 2021-22 spread (5.9 points) put every M5 stop under the 10-spread floor, the cost rule doing its job.
- **A simple higher-timeframe side (W1TREND) is at zero,** as every mechanical side has been.
- **It is not an edge,** since the side was hindsight. The engine is ready for a side. Whether the trader's read gives one at 58% is what the blind weekly calls will say.
