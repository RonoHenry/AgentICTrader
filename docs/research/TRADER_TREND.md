# The trader's trend: does it call the next move? (task 356)

Exploration slice, the focus markets. For each closed candle of the frame, a race on M1 from the next open: one average range of the frame up against one down, for up to three candles. A call is right when its side comes first (a minute reaching both counts against it). **Excess** is the rate minus the same side's rate over all candles of that market and frame (drift). Intervals resample trading dates. The bar a bias needs to clear the trader's costs: 56%-61% (task 338).

## H1

| Call | n | Right | 95% | Excess over drift | 95% | Unresolved |
|---|---|---|---|---|---|---|
| trend | 4859 | 50.1% | [48.4%, 51.7%] | -0.1 pts | [-1.7, +1.5] | 37% |
| structure | 10997 | 50.7% | [49.5%, 51.9%] | +0.6 pts | [-0.6, +1.8] | 39% |
| closes | 13817 | 50.1% | [49.2%, 51.1%] | +0.2 pts | [-0.8, +1.1] | 40% |
| liquidity | 11837 | 49.3% | [48.2%, 50.6%] | -0.6 pts | [-1.7, +0.7] | 40% |
| arrays | 17373 | 49.9% | [49.0%, 50.9%] | -0.1 pts | [-1.0, +0.9] | 40% |
| po3 | 11022 | 50.0% | [48.8%, 51.0%] | +0.1 pts | [-1.1, +1.2] | 40% |

By market, the trend:

| Market | n | Right | Excess |
|---|---|---|---|
| DXY | 511 | 52% | +1.1 pts |
| XAUUSD | 514 | 53% | +2.5 pts |
| EURUSD | 484 | 52% | +1.6 pts |
| GBPUSD | 503 | 53% | +2.6 pts |
| US100 | 457 | 47% | -2.3 pts |
| US500 | 450 | 49% | -0.8 pts |
| US30 | 425 | 50% | -0.2 pts |
| GER40 | 439 | 50% | -1.0 pts |
| UK100 | 430 | 44% | -5.4 pts |
| BTCUSDT | 646 | 50% | +0.2 pts |

The trend named a side on 25% of the H1 candles.

Continuation (the call's side's last swing taken first), against geometry:

| Call | n | Right | Geometry | Excess | 95% |
|---|---|---|---|---|---|
| trend | 4373 | 61.5% | 61.6% | -0.1 pts | [-1.8, +1.5] |
| structure | 12312 | 52.0% | 52.8% | -0.9 pts | [-2.1, +0.3] |
| closes | 14465 | 62.7% | 62.5% | +0.2 pts | [-0.6, +1.0] |
| liquidity | 14689 | 43.7% | 42.3% | +1.3 pts | [+0.2, +2.5] |
| arrays | 19368 | 52.7% | 53.6% | -0.9 pts | [-2.0, +0.2] |
| po3 | 12175 | 58.4% | 57.9% | +0.5 pts | [-0.5, +1.5] |

## H4

| Call | n | Right | 95% | Excess over drift | 95% | Unresolved |
|---|---|---|---|---|---|---|
| trend | 1313 | 49.1% | [45.9%, 52.3%] | -1.3 pts | [-4.5, +1.9] | 36% |
| structure | 3009 | 50.1% | [47.9%, 52.5%] | +0.0 pts | [-2.2, +2.4] | 35% |
| closes | 3838 | 49.4% | [47.6%, 51.2%] | -0.8 pts | [-2.6, +1.0] | 35% |
| liquidity | 3464 | 50.4% | [48.1%, 52.5%] | +0.6 pts | [-1.7, +2.6] | 33% |
| arrays | 4882 | 49.5% | [47.7%, 51.5%] | -0.8 pts | [-2.7, +1.1] | 35% |
| po3 | 3151 | 49.2% | [47.0%, 51.4%] | -1.0 pts | [-3.1, +1.2] | 35% |

By market, the trend:

| Market | n | Right | Excess |
|---|---|---|---|
| DXY | 108 | 40% | -11.5 pts |
| XAUUSD | 164 | 53% | +2.5 pts |
| EURUSD | 115 | 49% | -0.9 pts |
| GBPUSD | 120 | 48% | -4.2 pts |
| US100 | 132 | 45% | -3.9 pts |
| US500 | 118 | 48% | -1.6 pts |
| US30 | 130 | 46% | -3.6 pts |
| GER40 | 162 | 59% | +6.9 pts |
| UK100 | 130 | 43% | -7.3 pts |
| BTCUSDT | 134 | 55% | +5.5 pts |

The trend named a side on 26% of the H4 candles.

Continuation (the call's side's last swing taken first), against geometry:

| Call | n | Right | Geometry | Excess | 95% |
|---|---|---|---|---|---|
| trend | 1166 | 59.1% | 61.6% | -2.5 pts | [-5.7, +0.6] |
| structure | 3214 | 50.3% | 52.7% | -2.3 pts | [-4.7, -0.1] |
| closes | 3774 | 63.2% | 61.8% | +1.4 pts | [-0.2, +2.9] |
| liquidity | 3892 | 42.9% | 43.3% | -0.4 pts | [-2.5, +1.8] |
| arrays | 5063 | 51.9% | 54.0% | -2.2 pts | [-4.0, -0.2] |
| po3 | 3270 | 59.2% | 58.5% | +0.7 pts | [-1.2, +2.5] |

## D1

| Call | n | Right | 95% | Excess over drift | 95% | Unresolved |
|---|---|---|---|---|---|---|
| trend | 239 | 42.7% | [36.4%, 49.0%] | -11.2 pts | [-17.4, -5.1] | 28% |
| structure | 535 | 49.3% | [45.2%, 53.8%] | -3.9 pts | [-8.1, +0.5] | 31% |
| closes | 671 | 46.1% | [42.3%, 49.8%] | -5.2 pts | [-8.9, -1.6] | 33% |
| liquidity | 475 | 49.7% | [45.3%, 54.3%] | +0.5 pts | [-3.9, +5.1] | 32% |
| arrays | 829 | 52.6% | [49.2%, 56.0%] | -0.6 pts | [-4.0, +2.8] | 33% |
| po3 | 531 | 36.9% | [32.8%, 41.1%] | -13.0 pts | [-17.0, -9.0] | 34% |

By market, the trend:

| Market | n | Right | Excess |
|---|---|---|---|
| DXY | 24 | 54% | -7.1 pts |
| XAUUSD | 33 | 67% | +5.3 pts |
| EURUSD | 16 | 44% | -10.6 pts |
| GBPUSD | 25 | 40% | -13.4 pts |
| US100 | 14 | 21% | -27.9 pts |
| US500 | 19 | 21% | -28.7 pts |
| US30 | 25 | 28% | -21.6 pts |
| GER40 | 38 | 50% | -3.5 pts |
| UK100 | 25 | 32% | -20.0 pts |
| BTCUSDT | 20 | 45% | -3.7 pts |

The trend named a side on 25% of the D1 candles.

Continuation (the call's side's last swing taken first), against geometry:

| Call | n | Right | Geometry | Excess | 95% |
|---|---|---|---|---|---|
| trend | 197 | 58.9% | 65.6% | -6.7 pts | [-13.2, -0.3] |
| structure | 511 | 51.1% | 53.9% | -2.8 pts | [-6.6, +0.9] |
| closes | 597 | 62.0% | 63.3% | -1.3 pts | [-4.6, +2.1] |
| liquidity | 521 | 43.4% | 42.9% | +0.4 pts | [-3.1, +3.9] |
| arrays | 788 | 55.3% | 54.8% | +0.6 pts | [-2.5, +3.7] |
| po3 | 501 | 51.1% | 58.9% | -7.8 pts | [-11.5, -4.2] |

