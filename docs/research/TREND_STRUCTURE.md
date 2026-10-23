# Ranked swings and breaks: does structure call the next day? (task 359)

Each version's state at the 17:00 New York close, on D1 and on the H4 candle closing then, calls the next D1 candle. **Right** is the share of calls whose next day closed that way (dojis left out); **excess** is that minus the market's share of days closing the called way in the slice (drift). Intervals resample trading dates. Earlier mechanical reads called the day 45-49% (task 338); a bias needs 56-61% to pay. The ten focus markets.

## explore slice (2025-01-01 to 2025-07-01)

| Frame | Call | n | Right | 95% | Excess over drift | 95% |
|---|---|---|---|---|---|---|
| D1 | A. STH compare (task 355) | 776 | 48.8% | [44.2%, 53.4%] | -3.2 pts | [-7.7, +1.4] |
| D1 | trend with A. | 333 | 43.8% | [37.6%, 50.3%] | -9.1 pts | [-15.5, -2.4] |
| D1 | B. ITH compare | 869 | 52.1% | [47.8%, 56.6%] | +0.1 pts | [-4.2, +4.5] |
| D1 | trend with B. | 344 | 45.6% | [38.9%, 52.4%] | -7.4 pts | [-14.1, -0.6] |
| D1 | C. STH break | 1320 | 50.3% | [46.9%, 53.6%] | -1.3 pts | [-4.8, +1.9] |
| D1 | trend with C. | 454 | 46.0% | [40.6%, 51.8%] | -6.4 pts | [-11.7, -0.8] |
| D1 | D. ITH break | 1320 | 51.1% | [47.2%, 55.0%] | -0.9 pts | [-4.9, +2.9] |
| D1 | trend with D. | 448 | 46.2% | [40.3%, 52.4%] | -6.6 pts | [-12.5, -0.5] |
| D1 | E. ITH break + FVG | 1320 | 51.0% | [47.2%, 54.7%] | -0.8 pts | [-4.5, +2.9] |
| D1 | trend with E. | 406 | 45.8% | [39.7%, 52.2%] | -7.1 pts | [-13.2, -0.8] |
| H4 | A. STH compare (task 355) | 787 | 48.9% | [44.0%, 53.9%] | -1.8 pts | [-6.6, +3.1] |
| H4 | trend with A. | 359 | 44.6% | [38.9%, 50.5%] | -7.0 pts | [-12.6, -1.2] |
| H4 | B. ITH compare | 814 | 49.8% | [45.3%, 54.3%] | -1.5 pts | [-5.9, +3.1] |
| H4 | trend with B. | 376 | 47.9% | [41.8%, 53.6%] | -4.2 pts | [-10.3, +1.5] |
| H4 | C. STH break | 1320 | 48.0% | [44.1%, 51.9%] | -2.7 pts | [-6.6, +1.1] |
| H4 | trend with C. | 526 | 45.6% | [40.7%, 50.8%] | -5.8 pts | [-10.6, -0.8] |
| H4 | D. ITH break | 1320 | 51.5% | [47.8%, 55.0%] | +0.2 pts | [-3.4, +3.5] |
| H4 | trend with D. | 494 | 48.2% | [43.0%, 53.3%] | -3.9 pts | [-9.1, +1.3] |
| H4 | E. ITH break + FVG | 1320 | 51.2% | [47.7%, 54.7%] | -0.2 pts | [-3.6, +3.3] |
| H4 | trend with E. | 472 | 47.9% | [42.7%, 53.0%] | -4.2 pts | [-9.4, +0.9] |

## confirm slice (2025-07-01 to 2026-07-07)

| Frame | Call | n | Right | 95% | Excess over drift | 95% |
|---|---|---|---|---|---|---|
| D1 | A. STH compare (task 355) | 1700 | 49.8% | [46.7%, 52.8%] | -1.0 pts | [-4.2, +2.0] |
| D1 | trend with A. | 732 | 48.0% | [43.5%, 52.4%] | -3.8 pts | [-8.3, +0.6] |
| D1 | B. ITH compare | 1701 | 50.1% | [46.8%, 53.2%] | -1.2 pts | [-4.4, +1.9] |
| D1 | trend with B. | 765 | 49.2% | [44.9%, 53.5%] | -2.9 pts | [-7.2, +1.5] |
| D1 | C. STH break | 2725 | 49.3% | [46.7%, 51.8%] | -1.5 pts | [-4.0, +1.0] |
| D1 | trend with C. | 991 | 48.1% | [44.4%, 52.0%] | -3.5 pts | [-7.2, +0.3] |
| D1 | D. ITH break | 2725 | 49.9% | [47.6%, 52.3%] | -1.0 pts | [-3.4, +1.4] |
| D1 | trend with D. | 967 | 48.3% | [44.3%, 52.2%] | -3.5 pts | [-7.5, +0.3] |
| D1 | E. ITH break + FVG | 2725 | 49.9% | [47.5%, 52.3%] | -1.4 pts | [-3.9, +1.0] |
| D1 | trend with E. | 930 | 47.8% | [44.0%, 51.9%] | -4.2 pts | [-8.0, -0.1] |
| H4 | A. STH compare (task 355) | 1712 | 48.8% | [45.7%, 51.9%] | -1.7 pts | [-4.8, +1.4] |
| H4 | trend with A. | 741 | 50.1% | [45.5%, 54.6%] | -1.0 pts | [-5.5, +3.5] |
| H4 | B. ITH compare | 1690 | 50.8% | [47.7%, 53.9%] | +0.2 pts | [-2.9, +3.2] |
| H4 | trend with B. | 759 | 49.9% | [45.2%, 54.7%] | -1.0 pts | [-5.7, +3.8] |
| H4 | C. STH break | 2725 | 49.5% | [46.9%, 52.1%] | -0.8 pts | [-3.4, +1.8] |
| H4 | trend with C. | 995 | 49.4% | [45.4%, 53.6%] | -1.3 pts | [-5.3, +2.7] |
| H4 | D. ITH break | 2725 | 49.3% | [46.9%, 51.7%] | -1.2 pts | [-3.6, +1.2] |
| H4 | trend with D. | 963 | 48.8% | [44.7%, 53.0%] | -2.1 pts | [-6.2, +2.1] |
| H4 | E. ITH break + FVG | 2725 | 48.5% | [46.2%, 50.9%] | -2.0 pts | [-4.4, +0.4] |
| H4 | trend with E. | 912 | 48.7% | [44.4%, 53.0%] | -2.3 pts | [-6.5, +2.0] |

