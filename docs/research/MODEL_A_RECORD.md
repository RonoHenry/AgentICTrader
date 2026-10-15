# The Model A record

Context-engine Requirement 16 (update 2026-10-15). Descriptive: no verdict and no ledger row. It feeds the review with the trader.

- **snapshot:** exness-2025-2026h1
- **slice:** exploration slice, 2025-01-01 to 2025-07-01 (end exclusive)
- **frame sets:** model_d1, model_h4, model_h4_m30
- **code_commit:** d0da2f345a017c17ccb74d4874650a82d8b8cc43

**How to read it.**
- The funnel counts instances: each closed C candle in context starts one.
- **The premise:** once C2 has rejected, how often price reaches C1's opposite extreme before C2's extreme, within the F candle. It's compared with a coin flip from the same distances.
  - The interval is that difference, paired by trading date.
  - A lower bound above zero means the step carries information.
- **After the fill:** the outcomes of the few that reach the OTE and fill.
- **The baselines** read the same C and E rules. CRT has no F context; the random-POI baseline moves every POI.

## Summary: the premise against its coin flip

Once C2 has rejected: C1's opposite extreme before C2's extreme, minus the coin flip from the same distances, with its day-cluster interval. The last arm with fills gives the fills and the R held to TP1.

| Instrument | Frame set | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility | Fills | R held to TP1 |
|---|---|---|---|---|---|---|---|---|---:|---|
| EURUSD | model_d1 (D1/H1/M5) | -4% [-12, +4] (n 96) | -8% [-22, +6] (n 35) | +1% [-10, +12] (n 60) | -4% [-21, +12] (n 27) | +2% [+0, +5] (n 1058) | +4% [+1, +7] (n 468) | -2% [-14, +11] (n 56) | 0 | – |
| EURUSD | model_h4 (H4/M15/M1) | +2% [-3, +6] (n 376) | +5% [-1, +11] (n 177) | +7% [+3, +11] (n 265) | +8% [+2, +14] (n 149) | +1% [+0, +2] (n 3624) | +2% [+1, +4] (n 1515) | +5% [-1, +11] (n 220) | 8 | -0.67 [-1.00, -0.02] |
| EURUSD | model_h4_m30 (H4/M30/M1) | +6% [+1, +11] (n 217) | +11% [+4, +18] (n 108) | +9% [+3, +16] (n 165) | +10% [+1, +18] (n 96) | +1% [-1, +4] (n 1280) | +2% [-1, +5] (n 571) | -5% [-14, +4] (n 82) | 10 | +0.30 [-0.71, +1.50] |
| GBPUSD | model_d1 (D1/H1/M5) | +8% [+1, +15] (n 111) | +1% [-9, +11] (n 52) | +12% [+1, +22] (n 69) | +8% [-3, +20] (n 38) | +2% [-0, +4] (n 1036) | +3% [-0, +6] (n 444) | -1% [-14, +10] (n 53) | 1 | -1.00 [-1.00, -1.00] |
| GBPUSD | model_h4 (H4/M15/M1) | -2% [-6, +2] (n 424) | +2% [-3, +8] (n 206) | -1% [-6, +4] (n 263) | +2% [-4, +8] (n 170) | -1% [-2, +1] (n 3866) | +2% [-0, +4] (n 1591) | +5% [-0, +11] (n 210) | 8 | +0.23 [-0.86, +1.81] |
| GBPUSD | model_h4_m30 (H4/M30/M1) | +2% [-3, +8] (n 203) | +8% [+0, +15] (n 110) | +3% [-4, +11] (n 141) | +7% [-2, +15] (n 94) | -1% [-3, +1] (n 1403) | +1% [-2, +4] (n 643) | +10% [+1, +19] (n 85) | 7 | +1.13 [-0.32, +2.58] |
| USDJPY | model_d1 (D1/H1/M5) | -2% [-10, +7] (n 96) | +5% [-8, +17] (n 43) | +1% [-11, +14] (n 65) | +6% [-11, +21] (n 28) | +1% [-1, +3] (n 1060) | +3% [-0, +7] (n 385) | +16% [+2, +29] (n 38) | 0 | – |
| USDJPY | model_h4 (H4/M15/M1) | +0% [-4, +5] (n 390) | +2% [-4, +8] (n 184) | +1% [-4, +5] (n 250) | +1% [-6, +8] (n 130) | +1% [-0, +2] (n 3656) | +1% [-2, +3] (n 1395) | +5% [-1, +11] (n 192) | 8 | +1.02 [-0.48, +2.55] |
| USDJPY | model_h4_m30 (H4/M30/M1) | -4% [-9, +2] (n 212) | +4% [-4, +11] (n 116) | -0% [-6, +5] (n 145) | +3% [-5, +11] (n 80) | +1% [-1, +3] (n 1326) | +2% [-0, +5] (n 556) | +5% [-3, +13] (n 93) | 6 | -0.63 [-1.00, -0.09] |
| XAUUSD | model_d1 (D1/H1/M5) | +7% [-2, +16] (n 98) | +15% [+2, +28] (n 52) | +10% [-1, +22] (n 59) | +16% [+1, +31] (n 34) | +3% [+1, +5] (n 971) | +5% [+2, +9] (n 393) | +0% [-11, +12] (n 37) | 1 | +2.66 [+2.66, +2.66] |
| XAUUSD | model_h4 (H4/M15/M1) | -1% [-6, +4] (n 389) | +3% [-4, +9] (n 195) | -1% [-7, +6] (n 227) | +4% [-3, +12] (n 145) | -1% [-2, +1] (n 3788) | +0% [-2, +2] (n 1454) | -2% [-8, +4] (n 180) | 5 | +0.65 [-0.56, +1.86] |
| XAUUSD | model_h4_m30 (H4/M30/M1) | +1% [-5, +7] (n 197) | +6% [-1, +14] (n 103) | +3% [-4, +11] (n 118) | +9% [-0, +18] (n 76) | +0% [-2, +2] (n 1381) | +3% [+0, +6] (n 552) | -1% [-9, +8] (n 83) | 6 | -1.00 [-1.00, -1.00] |

*Fills and R are for + time + volatility.*

## EURUSD

### model_d1: F D1, C H1, E M5

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 2607 | 1235 | 2653 | 1245 | 4893 | 2364 | 1140 |
| ARMED | 2415 | 1158 | 2462 | 1169 | 4893 | 2364 | 764 |
| MANIPULATED | 269 | 119 | 285 | 122 | 2452 | 1197 | 147 |
| REJECTED | 98 | 35 | 60 | 27 | 1176 | 468 | 56 |
| DISPLACED | 37 | 9 | 28 | 12 | 462 | 154 | 17 |
| IN_OTE | 7 | 1 | 1 | 0 | 62 | 14 | 2 |
| ENTERED | 5 | 1 | 0 | 0 | 48 | 11 | 1 |
| TP1 | 1 | 0 | 0 | 0 | 14 | 4 | 0 |
| SD_1 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 2338 | 1116 | 2368 | 1123 | 2440 | 1167 | 993 |
| POI_FAILED | 26 | 14 | 27 | 14 | 0 | 0 | 15 |
| NO_REJECTION | 135 | 68 | 142 | 70 | 1149 | 587 | 65 |
| RANGE_SPENT | 0 | 0 | 35 | 5 | 0 | 72 | 2 |
| TOO_LARGE | 0 | 0 | 7 | 2 | 0 | 14 | 3 |
| RETRACE_INVALID | 31 | 6 | 19 | 5 | 397 | 171 | 20 |
| MISSED | 26 | 6 | 20 | 8 | 318 | 113 | 11 |
| EXPIRED | 46 | 24 | 35 | 18 | 540 | 229 | 30 |
| STOPPED | 5 | 1 | 0 | 0 | 38 | 11 | 1 |
| HORIZON | 0 | 0 | 0 | 0 | 7 | 0 | 0 |
| TARGETS_DONE | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| UNFINISHED | 0 | 0 | 0 | 0 | 1 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 11% [9%, 13%] (n 2415) | 10% [8%, 13%] (n 1158) | 12% [10%, 14%] (n 2462) | 10% [8%, 13%] (n 1169) | 50% [49%, 51%] (n 4893) | 51% [49%, 52%] (n 2364) | 19% [16%, 23%] (n 764) |
| REJECTED of MANIPULATED | 36% [32%, 41%] (n 269) | 29% [21%, 37%] (n 119) | 21% [16%, 26%] (n 285) | 22% [14%, 30%] (n 122) | 48% [46%, 50%] (n 2452) | 39% [35%, 43%] (n 1197) | 38% [30%, 48%] (n 147) |
| DISPLACED of REJECTED | 28% [19%, 37%] (n 98) | 20% [8%, 33%] (n 35) | 13% [5%, 22%] (n 60) | 19% [6%, 35%] (n 27) | 27% [25%, 29%] (n 1176) | 18% [15%, 22%] (n 468) | 16% [7%, 25%] (n 56) |
| ENTERED of REJECTED and DISPLACED | 19% [4%, 32%] (n 27) | 14% [0%, 43%] (n 7) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 5) | 15% [11%, 19%] (n 318) | 13% [7%, 20%] (n 85) | 11% [0%, 33%] (n 9) |
| **Premise**: C1's opposite extreme before C2's extreme | 48% vs coin 52%: **-4% [-12%, 4%]** (n 96) | 43% vs coin 51%: **-8% [-22%, 6%]** (n 35) | 55% vs coin 54%: **1% [-10%, 12%]** (n 60) | 52% vs coin 56%: **-4% [-21%, 12%]** (n 27) | 52% vs coin 50%: **2% [0%, 5%]** (n 1058) | 55% vs coin 51%: **4% [1%, 7%]** (n 468) | 50% vs coin 52%: **-2% [-14%, 11%]** (n 56) |
| C2 had already reached C1's opposite extreme | 18% [11%, 26%] | 23% [9%, 35%] | 23% [13%, 33%] | 26% [9%, 41%] | 25% [22%, 27%] | 29% [25%, 33%] | 29% [17%, 40%] |
| TP1 before the stop | 20% [0%, 60%] (n 5) | 0% [0%, 0%] (n 1) | – (n 0) | – (n 0) | 29% [16%, 44%] (n 48) | 36% [9%, 64%] (n 11) | 0% [0%, 0%] (n 1) |
| -1 SD before the stop | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 1) | – (n 0) | – (n 0) | 6% [0%, 14%] (n 48) | 0% [0%, 0%] (n 11) | 0% [0%, 0%] (n 1) |
| -2 SD before the stop | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 1) | – (n 0) | – (n 0) | 6% [0%, 14%] (n 48) | 0% [0%, 0%] (n 11) | 0% [0%, 0%] (n 1) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 1) | – (n 0) | – (n 0) | 6% [0%, 14%] (n 48) | 0% [0%, 0%] (n 11) | 0% [0%, 0%] (n 1) |
| R held to TP1 | -0.56 [-1.00, +0.33] (n 5) | -1.00 [-1.00, -1.00] (n 1) | – (n 0) | – (n 0) | +0.05 [-0.41, +0.53] (n 48) | +0.06 [-0.73, +1.05] (n 11) | -1.00 [-1.00, -1.00] (n 1) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 5) | -1.00 [-1.00, -1.00] (n 1) | – (n 0) | – (n 0) | -0.08 [-0.72, +0.71] (n 48) | -1.00 [-1.00, -1.00] (n 11) | -1.00 [-1.00, -1.00] (n 1) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 56%: -6% [-34%, 27%] (n 10) | 10% [0%, 33%] (n 10) |
| CLOSE | 50% vs 53%: -3% [-20%, 16%] (n 26) | 7% [0%, 19%] (n 27) |
| LONDON | 43% vs 49%: -6% [-24%, 11%] (n 14) | 0% [0%, 0%] (n 14) |
| MIDNIGHT | 25% vs 36%: -11% [-46%, 33%] (n 4) | 0% [0%, 0%] (n 4) |
| NY_AM | 56% vs 59%: -2% [-23%, 17%] (n 16) | 6% [0%, 19%] (n 16) |
| NY_MID | 45% vs 48%: -3% [-19%, 16%] (n 20) | 5% [0%, 16%] (n 20) |
| NY_PM | 0% vs 32%: -32% [-32%, -32%] (n 1) | 0% [0%, 0%] (n 2) |
| PRE_NY | 60% vs 55%: 5% [-31%, 40%] (n 5) | 0% [0%, 0%] (n 5) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 45% vs 50%: -4% [-14%, 5%] (n 77) | 5% [1%, 10%] (n 79) |
| True | 58% vs 60%: -2% [-20%, 15%] (n 19) | 5% [0%, 16%] (n 19) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 83% vs 61%: 22% [3%, 41%] (n 12) | 0% [0%, 0%] (n 12) |
| None | 41% vs 49%: -7% [-16%, 2%] (n 68) | 4% [0%, 9%] (n 70) |
| TIGHT_RANGE | 50% vs 58%: -8% [-30%, 15%] (n 16) | 12% [0%, 31%] (n 16) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 0% vs 46%: -46% [-46%, -46%] (n 2) | 0% [0%, 0%] (n 2) |
| FVG | 20% vs 50%: -30% [-52%, -3%] (n 5) | 0% [0%, 0%] (n 5) |
| OB | 71% vs 53%: 19% [-2%, 39%] (n 7) | 0% [0%, 0%] (n 8) |
| PWH | 28% vs 53%: -25% [-38%, -10%] (n 18) | 6% [0%, 20%] (n 18) |
| SWING_HIGH | 53% vs 43%: 10% [-7%, 24%] (n 15) | 6% [0%, 21%] (n 16) |
| previous D1 high | 55% vs 54%: 1% [-12%, 13%] (n 49) | 6% [0%, 13%] (n 49) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 53% vs 55%: -2% [-14%, 14%] (n 30) | 7% [0%, 17%] (n 30) |
| SHORT | 45% vs 50%: -5% [-15%, 5%] (n 66) | 4% [0%, 10%] (n 68) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 63%: -13% [-42%, 21%] (n 10) | 0% [0%, 0%] (n 10) |
| LONDON | 75% vs 62%: 13% [-7%, 31%] (n 8) | 0% [0%, 0%] (n 8) |
| MIDNIGHT | 20% vs 34%: -14% [-41%, 22%] (n 5) | 0% [0%, 0%] (n 5) |
| PRE_NY | 50% vs 53%: -3% [-46%, 40%] (n 4) | 0% [0%, 0%] (n 4) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 48% vs 55%: -7% [-28%, 14%] (n 21) | 0% [0%, 0%] (n 21) |
| True | 67% vs 60%: 7% [-17%, 28%] (n 6) | 0% [0%, 0%] (n 6) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 100% vs 66%: 34% [19%, 50%] (n 2) | 0% [0%, 0%] (n 2) |
| None | 47% vs 53%: -5% [-26%, 17%] (n 19) | 0% [0%, 0%] (n 19) |
| TIGHT_RANGE | 50% vs 63%: -13% [-46%, 18%] (n 6) | 0% [0%, 0%] (n 6) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| PWH | 17% vs 50%: -33% [-46%, -26%] (n 6) | 0% [0%, 0%] (n 6) |
| SWING_HIGH | 60% vs 40%: 20% [-21%, 48%] (n 5) | 0% [0%, 0%] (n 5) |
| previous D1 high | 62% vs 63%: -1% [-24%, 21%] (n 16) | 0% [0%, 0%] (n 16) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 73% vs 60%: 13% [-15%, 38%] (n 11) | 0% [0%, 0%] (n 11) |
| SHORT | 38% vs 53%: -16% [-33%, 6%] (n 16) | 0% [0%, 0%] (n 16) |

### model_h4: F H4, C M15, E M1

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 10452 | 4729 | 10615 | 4763 | 20102 | 9540 | 4603 |
| ARMED | 9751 | 4494 | 9911 | 4527 | 20102 | 9540 | 3260 |
| MANIPULATED | 1334 | 596 | 1382 | 605 | 9858 | 4777 | 714 |
| REJECTED | 407 | 185 | 280 | 154 | 3987 | 1656 | 239 |
| DISPLACED | 257 | 95 | 174 | 74 | 2510 | 819 | 113 |
| IN_OTE | 41 | 15 | 15 | 9 | 362 | 73 | 8 |
| ENTERED | 34 | 13 | 14 | 8 | 309 | 67 | 7 |
| TP1 | 6 | 2 | 3 | 1 | 62 | 13 | 0 |
| SD_1 | 1 | 1 | 1 | 0 | 24 | 5 | 0 |
| SD_2 | 1 | 1 | 0 | 0 | 10 | 2 | 0 |
| SD_2.5 | 1 | 1 | 0 | 0 | 6 | 2 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 9118 | 4133 | 9233 | 4158 | 10244 | 4763 | 3889 |
| POI_FAILED | 138 | 66 | 143 | 65 | 0 | 0 | 99 |
| NO_REJECTION | 667 | 304 | 693 | 307 | 4861 | 2397 | 288 |
| RANGE_SPENT | 0 | 0 | 156 | 38 | 0 | 309 | 35 |
| TOO_LARGE | 0 | 0 | 4 | 1 | 0 | 3 | 0 |
| RETRACE_INVALID | 115 | 48 | 74 | 39 | 1323 | 583 | 85 |
| MISSED | 183 | 69 | 132 | 55 | 1843 | 640 | 88 |
| EXPIRED | 197 | 96 | 166 | 92 | 1522 | 778 | 112 |
| STOPPED | 29 | 10 | 14 | 8 | 260 | 57 | 7 |
| HORIZON | 4 | 2 | 0 | 0 | 43 | 8 | 0 |
| TARGETS_DONE | 1 | 1 | 0 | 0 | 6 | 2 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [13%, 15%] (n 9751) | 13% [12%, 15%] (n 4494) | 14% [13%, 15%] (n 9911) | 13% [12%, 15%] (n 4527) | 49% [49%, 50%] (n 20102) | 50% [49%, 51%] (n 9540) | 22% [20%, 24%] (n 3260) |
| REJECTED of MANIPULATED | 31% [28%, 33%] (n 1334) | 31% [28%, 35%] (n 596) | 20% [17%, 23%] (n 1382) | 25% [22%, 30%] (n 605) | 40% [40%, 41%] (n 9858) | 35% [32%, 37%] (n 4777) | 33% [30%, 38%] (n 714) |
| DISPLACED of REJECTED | 30% [26%, 35%] (n 407) | 26% [20%, 33%] (n 185) | 16% [11%, 21%] (n 280) | 17% [12%, 23%] (n 154) | 36% [34%, 37%] (n 3987) | 20% [17%, 22%] (n 1656) | 20% [14%, 25%] (n 239) |
| ENTERED of REJECTED and DISPLACED | 27% [20%, 35%] (n 124) | 27% [15%, 40%] (n 49) | 32% [19%, 48%] (n 44) | 31% [15%, 50%] (n 26) | 22% [19%, 24%] (n 1434) | 20% [16%, 25%] (n 327) | 15% [6%, 25%] (n 47) |
| **Premise**: C1's opposite extreme before C2's extreme | 51% vs coin 49%: **2% [-3%, 6%]** (n 376) | 55% vs coin 49%: **5% [-1%, 11%]** (n 177) | 59% vs coin 52%: **7% [3%, 11%]** (n 265) | 60% vs coin 52%: **8% [2%, 14%]** (n 149) | 50% vs coin 48%: **1% [0%, 2%]** (n 3624) | 53% vs coin 50%: **2% [1%, 4%]** (n 1515) | 55% vs coin 50%: **5% [-1%, 11%]** (n 220) |
| C2 had already reached C1's opposite extreme | 20% [16%, 24%] | 20% [14%, 26%] | 23% [19%, 28%] | 22% [16%, 28%] | 25% [24%, 27%] | 26% [24%, 29%] | 26% [21%, 32%] |
| TP1 before the stop | 18% [6%, 31%] (n 34) | 15% [0%, 38%] (n 13) | 21% [0%, 43%] (n 14) | 12% [0%, 38%] (n 8) | 20% [16%, 24%] (n 309) | 19% [10%, 30%] (n 67) | 0% [0%, 0%] (n 7) |
| -1 SD before the stop | 3% [0%, 9%] (n 34) | 8% [0%, 23%] (n 13) | 7% [0%, 19%] (n 14) | 0% [0%, 0%] (n 8) | 8% [5%, 11%] (n 309) | 7% [2%, 14%] (n 67) | 0% [0%, 0%] (n 7) |
| -2 SD before the stop | 3% [0%, 9%] (n 34) | 8% [0%, 23%] (n 13) | 0% [0%, 0%] (n 14) | 0% [0%, 0%] (n 8) | 3% [1%, 5%] (n 309) | 3% [0%, 8%] (n 67) | 0% [0%, 0%] (n 7) |
| -2.5 SD before the stop | 3% [0%, 9%] (n 34) | 8% [0%, 23%] (n 13) | 0% [0%, 0%] (n 14) | 0% [0%, 0%] (n 8) | 2% [1%, 4%] (n 309) | 3% [0%, 8%] (n 67) | 0% [0%, 0%] (n 7) |
| R held to TP1 | -0.31 [-0.69, +0.12] (n 34) | -0.12 [-0.83, +0.83] (n 13) | -0.24 [-1.00, +0.52] (n 14) | -0.67 [-1.00, -0.02] (n 8) | -0.21 [-0.38, -0.03] (n 309) | -0.32 [-0.63, +0.05] (n 67) | -1.00 [-1.00, -1.00] (n 7) |
| R held to -2 SD | -0.49 [-0.92, +0.18] (n 34) | +0.00 [-1.00, +1.57] (n 13) | -1.00 [-1.00, -1.00] (n 14) | -1.00 [-1.00, -1.00] (n 8) | -0.27 [-0.50, -0.02] (n 309) | -0.35 [-0.76, +0.13] (n 67) | -1.00 [-1.00, -1.00] (n 7) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 57% vs 47%: 9% [-1%, 20%] (n 53) | 7% [2%, 14%] (n 56) |
| CLOSE | 59% vs 46%: 14% [-0%, 28%] (n 37) | 16% [7%, 28%] (n 44) |
| LONDON | 49% vs 51%: -2% [-14%, 10%] (n 51) | 11% [4%, 19%] (n 56) |
| MIDNIGHT | 43% vs 46%: -3% [-20%, 14%] (n 28) | 7% [0%, 18%] (n 28) |
| NY_AM | 54% vs 54%: 0% [-9%, 11%] (n 57) | 3% [0%, 8%] (n 62) |
| NY_MID | 43% vs 47%: -4% [-14%, 7%] (n 60) | 9% [3%, 15%] (n 69) |
| NY_PM | 35% vs 47%: -13% [-25%, 0%] (n 46) | 12% [4%, 23%] (n 48) |
| PRE_NY | 66% vs 52%: 14% [3%, 26%] (n 44) | 2% [0%, 8%] (n 44) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 56% vs 49%: 7% [1%, 14%] (n 184) | 9% [6%, 13%] (n 193) |
| True | 46% vs 49%: -4% [-9%, 2%] (n 192) | 7% [4%, 11%] (n 214) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 55% vs 52%: 3% [-7%, 13%] (n 73) | 6% [1%, 12%] (n 79) |
| None | 50% vs 48%: 2% [-3%, 7%] (n 297) | 9% [6%, 12%] (n 322) |
| TIGHT_RANGE | 50% vs 58%: -8% [-43%, 27%] (n 6) | 17% [0%, 50%] (n 6) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 45% vs 37%: 8% [-12%, 29%] (n 11) | 18% [0%, 33%] (n 11) |
| FVG | 50% vs 51%: -1% [-15%, 14%] (n 36) | 14% [5%, 24%] (n 43) |
| OB | 50% vs 52%: -2% [-14%, 10%] (n 36) | 9% [2%, 18%] (n 45) |
| PDH | 58% vs 50%: 8% [-5%, 26%] (n 31) | 6% [0%, 17%] (n 31) |
| PMH | 0% vs 35%: -35% [-35%, -35%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | 47% vs 46%: 1% [-25%, 27%] (n 15) | 0% [0%, 0%] (n 16) |
| SWING_HIGH | 48% vs 51%: -3% [-14%, 7%] (n 48) | 9% [2%, 17%] (n 55) |
| previous H4 high | 52% vs 49%: 3% [-3%, 10%] (n 198) | 7% [4%, 11%] (n 205) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 52% vs 50%: 2% [-5%, 10%] (n 139) | 8% [4%, 12%] (n 148) |
| SHORT | 50% vs 49%: 2% [-4%, 7%] (n 237) | 8% [5%, 12%] (n 259) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 62% vs 50%: 12% [1%, 23%] (n 58) | 2% [0%, 5%] (n 60) |
| LONDON | 58% vs 55%: 3% [-12%, 17%] (n 36) | 10% [2%, 21%] (n 39) |
| MIDNIGHT | 48% vs 45%: 3% [-12%, 19%] (n 27) | 4% [0%, 12%] (n 27) |
| PRE_NY | 68% vs 56%: 11% [-2%, 25%] (n 28) | 7% [0%, 19%] (n 28) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 66% vs 50%: 16% [5%, 26%] (n 68) | 7% [2%, 14%] (n 68) |
| True | 54% vs 53%: 1% [-7%, 10%] (n 81) | 3% [0%, 8%] (n 86) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 66% vs 55%: 10% [-4%, 23%] (n 35) | 3% [0%, 8%] (n 38) |
| None | 59% vs 49%: 10% [2%, 17%] (n 100) | 6% [2%, 11%] (n 102) |
| TIGHT_RANGE | 50% vs 61%: -11% [-29%, 7%] (n 14) | 7% [0%, 23%] (n 14) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 67% vs 41%: 26% [-27%, 52%] (n 3) | 0% [0%, 0%] (n 3) |
| FVG | 68% vs 55%: 13% [-2%, 28%] (n 19) | 11% [0%, 28%] (n 19) |
| OB | 100% vs 89%: 11% [11%, 11%] (n 1) | 100% [100%, 100%] (n 1) |
| PDH | 58% vs 53%: 5% [-12%, 26%] (n 12) | 0% [0%, 0%] (n 12) |
| PMH | 0% vs 35%: -35% [-35%, -35%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | 75% vs 38%: 37% [0%, 64%] (n 4) | 0% [0%, 0%] (n 5) |
| SWING_HIGH | 53% vs 47%: 6% [-13%, 26%] (n 15) | 0% [0%, 0%] (n 17) |
| previous H4 high | 59% vs 52%: 6% [-3%, 14%] (n 94) | 5% [1%, 10%] (n 96) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 58% vs 51%: 7% [-2%, 16%] (n 62) | 5% [0%, 10%] (n 65) |
| SHORT | 61% vs 52%: 9% [-1%, 18%] (n 87) | 6% [1%, 10%] (n 89) |

### model_h4_m30: F H4, C M30, E M1

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 5179 | 2325 | 5261 | 2347 | 10536 | 4917 | 2311 |
| ARMED | 4908 | 2241 | 4989 | 2263 | 10536 | 4917 | 1688 |
| MANIPULATED | 990 | 448 | 1015 | 452 | 5185 | 2452 | 377 |
| REJECTED | 253 | 122 | 187 | 106 | 1578 | 691 | 98 |
| DISPLACED | 354 | 150 | 287 | 131 | 2237 | 768 | 112 |
| IN_OTE | 38 | 19 | 14 | 11 | 244 | 53 | 7 |
| ENTERED | 34 | 17 | 12 | 10 | 206 | 44 | 6 |
| TP1 | 9 | 6 | 2 | 2 | 30 | 12 | 1 |
| SD_1 | 3 | 3 | 1 | 1 | 12 | 3 | 0 |
| SD_2 | 1 | 1 | 0 | 0 | 5 | 1 | 0 |
| SD_2.5 | 1 | 1 | 0 | 0 | 2 | 1 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 4189 | 1877 | 4246 | 1895 | 5350 | 2465 | 1934 |
| POI_FAILED | 153 | 76 | 150 | 69 | 0 | 0 | 59 |
| NO_REJECTION | 400 | 178 | 398 | 173 | 2344 | 1136 | 128 |
| RANGE_SPENT | 0 | 0 | 73 | 16 | 0 | 92 | 11 |
| TOO_LARGE | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| RETRACE_INVALID | 62 | 29 | 52 | 29 | 467 | 244 | 31 |
| MISSED | 276 | 115 | 239 | 108 | 1788 | 657 | 97 |
| EXPIRED | 65 | 33 | 89 | 47 | 380 | 279 | 45 |
| STOPPED | 27 | 13 | 10 | 8 | 169 | 36 | 5 |
| HORIZON | 6 | 3 | 2 | 2 | 35 | 7 | 1 |
| TARGETS_DONE | 1 | 1 | 0 | 0 | 2 | 1 | 0 |
| UNFINISHED | 0 | 0 | 0 | 0 | 1 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 20% [19%, 22%] (n 4908) | 20% [18%, 22%] (n 2241) | 20% [19%, 22%] (n 4989) | 20% [18%, 22%] (n 2263) | 49% [49%, 50%] (n 10536) | 50% [49%, 51%] (n 4917) | 22% [20%, 24%] (n 1688) |
| REJECTED of MANIPULATED | 26% [23%, 28%] (n 990) | 27% [23%, 31%] (n 448) | 18% [15%, 21%] (n 1015) | 23% [19%, 28%] (n 452) | 30% [29%, 32%] (n 5185) | 28% [25%, 31%] (n 2452) | 26% [21%, 31%] (n 377) |
| DISPLACED of REJECTED | 59% [53%, 65%] (n 253) | 59% [51%, 67%] (n 122) | 30% [24%, 37%] (n 187) | 33% [24%, 42%] (n 106) | 56% [54%, 58%] (n 1578) | 28% [25%, 32%] (n 691) | 28% [19%, 37%] (n 98) |
| ENTERED of REJECTED and DISPLACED | 23% [17%, 29%] (n 150) | 24% [15%, 33%] (n 72) | 21% [10%, 33%] (n 57) | 29% [14%, 45%] (n 35) | 23% [21%, 26%] (n 886) | 23% [17%, 29%] (n 195) | 22% [7%, 38%] (n 27) |
| **Premise**: C1's opposite extreme before C2's extreme | 54% vs coin 48%: **6% [1%, 11%]** (n 217) | 59% vs coin 48%: **11% [4%, 18%]** (n 108) | 59% vs coin 50%: **9% [3%, 16%]** (n 165) | 58% vs coin 49%: **10% [1%, 18%]** (n 96) | 48% vs coin 46%: **1% [-1%, 4%]** (n 1280) | 49% vs coin 47%: **2% [-1%, 5%]** (n 571) | 48% vs coin 53%: **-5% [-14%, 4%]** (n 82) |
| C2 had already reached C1's opposite extreme | 21% [16%, 26%] | 21% [15%, 28%] | 22% [17%, 28%] | 22% [14%, 29%] | 23% [21%, 25%] | 23% [20%, 27%] | 27% [18%, 35%] |
| TP1 before the stop | 26% [12%, 41%] (n 34) | 35% [12%, 59%] (n 17) | 17% [0%, 38%] (n 12) | 20% [0%, 42%] (n 10) | 15% [9%, 20%] (n 206) | 27% [14%, 41%] (n 44) | 17% [0%, 50%] (n 6) |
| -1 SD before the stop | 9% [0%, 21%] (n 34) | 18% [0%, 35%] (n 17) | 8% [0%, 27%] (n 12) | 10% [0%, 33%] (n 10) | 6% [3%, 9%] (n 206) | 7% [0%, 15%] (n 44) | 0% [0%, 0%] (n 6) |
| -2 SD before the stop | 3% [0%, 9%] (n 34) | 6% [0%, 18%] (n 17) | 0% [0%, 0%] (n 12) | 0% [0%, 0%] (n 10) | 2% [0%, 5%] (n 206) | 2% [0%, 7%] (n 44) | 0% [0%, 0%] (n 6) |
| -2.5 SD before the stop | 3% [0%, 9%] (n 34) | 6% [0%, 18%] (n 17) | 0% [0%, 0%] (n 12) | 0% [0%, 0%] (n 10) | 1% [0%, 2%] (n 206) | 2% [0%, 7%] (n 44) | 0% [0%, 0%] (n 6) |
| R held to TP1 | +0.53 [-0.22, +1.34] (n 34) | +1.23 [+0.03, +2.55] (n 17) | +0.08 [-1.00, +1.31] (n 12) | +0.30 [-0.71, +1.50] (n 10) | -0.14 [-0.37, +0.11] (n 206) | +0.32 [-0.25, +0.96] (n 44) | -0.52 [-1.00, +0.44] (n 6) |
| R held to -2 SD | -0.08 [-0.72, +0.76] (n 34) | +0.31 [-0.74, +1.77] (n 17) | -0.23 [-1.00, +0.74] (n 12) | -0.07 [-1.00, +1.03] (n 10) | -0.27 [-0.51, +0.01] (n 206) | -0.15 [-0.67, +0.46] (n 44) | -0.38 [-1.00, +0.87] (n 6) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 59% vs 49%: 11% [-2%, 23%] (n 37) | 17% [7%, 29%] (n 42) |
| CLOSE | 58% vs 48%: 10% [-10%, 31%] (n 19) | 12% [0%, 25%] (n 26) |
| LONDON | 52% vs 52%: 0% [-13%, 15%] (n 21) | 11% [0%, 22%] (n 27) |
| MIDNIGHT | 56% vs 41%: 16% [-7%, 38%] (n 16) | 17% [0%, 33%] (n 18) |
| NY_AM | 50% vs 49%: 1% [-12%, 13%] (n 36) | 12% [3%, 23%] (n 41) |
| NY_MID | 52% vs 46%: 6% [-8%, 21%] (n 29) | 8% [0%, 19%] (n 37) |
| NY_PM | 40% vs 50%: -10% [-26%, 4%] (n 25) | 22% [8%, 38%] (n 27) |
| PRE_NY | 65% vs 48%: 16% [5%, 28%] (n 34) | 11% [3%, 22%] (n 35) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 48% vs 49%: -1% [-9%, 7%] (n 90) | 17% [11%, 24%] (n 113) |
| True | 59% vs 48%: 11% [5%, 18%] (n 127) | 11% [6%, 16%] (n 140) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 55% vs 47%: 7% [-0%, 15%] (n 128) | 14% [9%, 20%] (n 148) |
| None | 54% vs 49%: 5% [-3%, 14%] (n 83) | 12% [7%, 19%] (n 97) |
| TIGHT_RANGE | 50% vs 57%: -7% [-38%, 24%] (n 6) | 12% [0%, 38%] (n 8) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 67% vs 37%: 30% [27%, 37%] (n 3) | 25% [0%, 100%] (n 4) |
| FVG | 59% vs 50%: 9% [-8%, 27%] (n 17) | 17% [4%, 33%] (n 24) |
| OB | 47% vs 42%: 5% [-13%, 21%] (n 19) | 8% [0%, 23%] (n 24) |
| PDH | 52% vs 53%: -1% [-17%, 19%] (n 21) | 5% [0%, 17%] (n 22) |
| PMH | 0% vs 43%: -43% [-43%, -43%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | 56% vs 47%: 9% [-24%, 42%] (n 9) | 9% [0%, 27%] (n 11) |
| SWING_HIGH | 50% vs 50%: 0% [-15%, 16%] (n 24) | 18% [6%, 30%] (n 33) |
| previous H4 high | 56% vs 48%: 8% [2%, 14%] (n 123) | 14% [9%, 20%] (n 134) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 51% vs 49%: 2% [-5%, 9%] (n 88) | 10% [5%, 16%] (n 101) |
| SHORT | 57% vs 48%: 9% [3%, 15%] (n 129) | 16% [11%, 21%] (n 152) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 64% vs 51%: 13% [1%, 25%] (n 39) | 7% [0%, 16%] (n 44) |
| LONDON | 47% vs 51%: -5% [-20%, 12%] (n 15) | 12% [0%, 29%] (n 17) |
| MIDNIGHT | 53% vs 42%: 11% [-10%, 32%] (n 17) | 11% [0%, 26%] (n 19) |
| PRE_NY | 60% vs 48%: 12% [-3%, 27%] (n 25) | 12% [0%, 25%] (n 26) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 46% vs 46%: -0% [-13%, 13%] (n 35) | 15% [5%, 26%] (n 41) |
| True | 66% vs 50%: 15% [5%, 26%] (n 61) | 6% [1%, 12%] (n 65) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 56% vs 47%: 9% [-2%, 19%] (n 66) | 13% [4%, 22%] (n 71) |
| None | 65% vs 55%: 11% [-5%, 25%] (n 23) | 4% [0%, 11%] (n 27) |
| TIGHT_RANGE | 57% vs 45%: 13% [-27%, 59%] (n 7) | 0% [0%, 0%] (n 8) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | – vs –: – (n 0) | 100% [100%, 100%] (n 1) |
| FVG | 88% vs 54%: 34% [12%, 54%] (n 8) | 0% [0%, 0%] (n 8) |
| OB | 50% vs 62%: -12% [-41%, 17%] (n 2) | 50% [0%, 100%] (n 2) |
| PDH | 73% vs 60%: 13% [-14%, 36%] (n 11) | 0% [0%, 0%] (n 11) |
| PMH | 0% vs 43%: -43% [-43%, -43%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | 100% vs 50%: 50% [20%, 69%] (n 3) | 0% [0%, 0%] (n 5) |
| SWING_HIGH | 50% vs 39%: 11% [-15%, 36%] (n 6) | 0% [0%, 0%] (n 10) |
| previous H4 high | 52% vs 47%: 6% [-4%, 16%] (n 65) | 12% [4%, 21%] (n 68) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 49% vs 47%: 1% [-11%, 13%] (n 35) | 2% [0%, 8%] (n 41) |
| SHORT | 64% vs 49%: 14% [3%, 26%] (n 61) | 14% [6%, 23%] (n 65) |

## GBPUSD

### model_d1: F D1, C H1, E M5

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 2528 | 1200 | 2581 | 1213 | 4931 | 2386 | 1105 |
| ARMED | 2395 | 1139 | 2445 | 1152 | 4931 | 2386 | 709 |
| MANIPULATED | 323 | 145 | 340 | 150 | 2496 | 1237 | 153 |
| REJECTED | 122 | 52 | 70 | 38 | 1142 | 444 | 53 |
| DISPLACED | 38 | 13 | 36 | 13 | 363 | 144 | 19 |
| IN_OTE | 2 | 1 | 1 | 1 | 47 | 16 | 3 |
| ENTERED | 2 | 1 | 1 | 1 | 40 | 13 | 3 |
| TP1 | 0 | 0 | 0 | 0 | 11 | 3 | 0 |
| SD_1 | 0 | 0 | 0 | 0 | 4 | 0 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 2204 | 1055 | 2240 | 1063 | 2434 | 1149 | 952 |
| POI_FAILED | 23 | 11 | 26 | 11 | 0 | 0 | 20 |
| NO_REJECTION | 165 | 76 | 174 | 79 | 1244 | 626 | 63 |
| RANGE_SPENT | 0 | 0 | 47 | 11 | 0 | 94 | 11 |
| TOO_LARGE | 0 | 0 | 5 | 3 | 0 | 14 | 1 |
| RETRACE_INVALID | 40 | 18 | 24 | 13 | 413 | 174 | 19 |
| MISSED | 30 | 12 | 23 | 8 | 258 | 98 | 11 |
| EXPIRED | 63 | 27 | 40 | 24 | 540 | 218 | 25 |
| STOPPED | 2 | 1 | 1 | 1 | 33 | 13 | 3 |
| HORIZON | 0 | 0 | 0 | 0 | 4 | 0 | 0 |
| TARGETS_DONE | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| UNFINISHED | 1 | 0 | 1 | 0 | 2 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 13% [11%, 16%] (n 2395) | 13% [10%, 16%] (n 1139) | 14% [12%, 16%] (n 2445) | 13% [10%, 16%] (n 1152) | 51% [50%, 52%] (n 4931) | 52% [51%, 53%] (n 2386) | 22% [18%, 25%] (n 709) |
| REJECTED of MANIPULATED | 38% [34%, 42%] (n 323) | 36% [29%, 43%] (n 145) | 21% [16%, 26%] (n 340) | 25% [18%, 33%] (n 150) | 46% [44%, 48%] (n 2496) | 36% [32%, 39%] (n 1237) | 35% [27%, 42%] (n 153) |
| DISPLACED of REJECTED | 18% [11%, 26%] (n 122) | 13% [5%, 24%] (n 52) | 13% [6%, 21%] (n 70) | 8% [0%, 18%] (n 38) | 21% [19%, 24%] (n 1142) | 16% [12%, 20%] (n 444) | 23% [12%, 35%] (n 53) |
| ENTERED of REJECTED and DISPLACED | 9% [0%, 22%] (n 22) | 14% [0%, 43%] (n 7) | 11% [0%, 33%] (n 9) | 33% [0%, 100%] (n 3) | 17% [12%, 21%] (n 242) | 18% [10%, 27%] (n 71) | 25% [0%, 50%] (n 12) |
| **Premise**: C1's opposite extreme before C2's extreme | 55% vs coin 47%: **8% [1%, 15%]** (n 111) | 48% vs coin 47%: **1% [-9%, 11%]** (n 52) | 61% vs coin 49%: **12% [1%, 22%]** (n 69) | 61% vs coin 52%: **8% [-3%, 20%]** (n 38) | 51% vs coin 49%: **2% [-0%, 4%]** (n 1036) | 54% vs coin 51%: **3% [-0%, 6%]** (n 444) | 51% vs coin 52%: **-1% [-14%, 10%]** (n 53) |
| C2 had already reached C1's opposite extreme | 22% [16%, 29%] | 23% [11%, 35%] | 23% [14%, 32%] | 29% [15%, 44%] | 25% [22%, 28%] | 32% [27%, 36%] | 30% [19%, 42%] |
| TP1 before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | 28% [15%, 40%] (n 40) | 23% [0%, 46%] (n 13) | 0% [0%, 0%] (n 3) |
| -1 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | 10% [2%, 20%] (n 40) | 0% [0%, 0%] (n 13) | 0% [0%, 0%] (n 3) |
| -2 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | 8% [0%, 16%] (n 40) | 0% [0%, 0%] (n 13) | 0% [0%, 0%] (n 3) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | 8% [0%, 16%] (n 40) | 0% [0%, 0%] (n 13) | 0% [0%, 0%] (n 3) |
| R held to TP1 | -1.00 [-1.00, -1.00] (n 2) | -1.00 [-1.00, -1.00] (n 1) | -1.00 [-1.00, -1.00] (n 1) | -1.00 [-1.00, -1.00] (n 1) | -0.15 [-0.51, +0.24] (n 40) | -0.43 [-1.00, +0.14] (n 13) | -1.00 [-1.00, -1.00] (n 3) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 2) | -1.00 [-1.00, -1.00] (n 1) | -1.00 [-1.00, -1.00] (n 1) | -1.00 [-1.00, -1.00] (n 1) | -0.06 [-0.75, +0.80] (n 40) | -1.00 [-1.00, -1.00] (n 13) | -1.00 [-1.00, -1.00] (n 3) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 57% vs 49%: 7% [-8%, 24%] (n 23) | 4% [0%, 14%] (n 23) |
| CLOSE | 58% vs 40%: 18% [0%, 34%] (n 26) | 3% [0%, 10%] (n 31) |
| LONDON | 40% vs 46%: -6% [-22%, 11%] (n 15) | 0% [0%, 0%] (n 15) |
| MIDNIGHT | 17% vs 42%: -25% [-43%, -1%] (n 6) | 0% [0%, 0%] (n 6) |
| NY_AM | 80% vs 65%: 15% [-8%, 37%] (n 10) | 0% [0%, 0%] (n 11) |
| NY_MID | 56% vs 47%: 9% [-11%, 29%] (n 18) | 0% [0%, 0%] (n 19) |
| NY_PM | 50% vs 47%: 3% [-17%, 32%] (n 6) | 0% [0%, 0%] (n 10) |
| PRE_NY | 71% vs 47%: 24% [-6%, 52%] (n 7) | 0% [0%, 0%] (n 7) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 54% vs 44%: 9% [1%, 18%] (n 93) | 2% [0%, 5%] (n 103) |
| True | 61% vs 60%: 1% [-14%, 16%] (n 18) | 0% [0%, 0%] (n 19) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 50% vs 47%: 3% [-14%, 21%] (n 16) | 0% [0%, 0%] (n 20) |
| None | 54% vs 48%: 6% [-2%, 14%] (n 82) | 2% [0%, 5%] (n 89) |
| TIGHT_RANGE | 69% vs 40%: 29% [8%, 51%] (n 13) | 0% [0%, 0%] (n 13) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 100% vs 39%: 61% [53%, 69%] (n 2) | 25% [0%, 100%] (n 4) |
| FVG | 40% vs 55%: -15% [-24%, -7%] (n 5) | 0% [0%, 0%] (n 5) |
| OB | 29% vs 36%: -7% [-23%, 3%] (n 14) | 6% [0%, 18%] (n 17) |
| PMH | 86% vs 56%: 30% [17%, 39%] (n 7) | 0% [0%, 0%] (n 7) |
| PWH | 56% vs 49%: 7% [-6%, 24%] (n 25) | 0% [0%, 0%] (n 27) |
| SWING_HIGH | 55% vs 48%: 7% [-12%, 31%] (n 11) | 0% [0%, 0%] (n 14) |
| previous D1 high | 57% vs 47%: 10% [-1%, 22%] (n 47) | 0% [0%, 0%] (n 48) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 52% vs 46%: 6% [-6%, 20%] (n 29) | 3% [0%, 8%] (n 33) |
| SHORT | 56% vs 47%: 9% [0%, 17%] (n 82) | 1% [0%, 4%] (n 89) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 65% vs 53%: 13% [-2%, 28%] (n 23) | 4% [0%, 12%] (n 23) |
| LONDON | 57% vs 59%: -2% [-25%, 24%] (n 7) | 0% [0%, 0%] (n 7) |
| MIDNIGHT | 33% vs 45%: -11% [-37%, 16%] (n 6) | 0% [0%, 0%] (n 6) |
| PRE_NY | 100% vs 46%: 54% [46%, 62%] (n 2) | 0% [0%, 0%] (n 2) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 61% vs 51%: 10% [-4%, 23%] (n 33) | 3% [0%, 9%] (n 33) |
| True | 60% vs 61%: -1% [-34%, 32%] (n 5) | 0% [0%, 0%] (n 5) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 43% vs 44%: -1% [-27%, 30%] (n 7) | 14% [0%, 43%] (n 7) |
| None | 71% vs 55%: 16% [1%, 32%] (n 24) | 0% [0%, 0%] (n 24) |
| TIGHT_RANGE | 43% vs 52%: -9% [-31%, 14%] (n 7) | 0% [0%, 0%] (n 7) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| OB | 67% vs 64%: 3% [-15%, 39%] (n 3) | 0% [0%, 0%] (n 3) |
| PMH | 100% vs 59%: 41% [30%, 62%] (n 3) | 0% [0%, 0%] (n 3) |
| PWH | 67% vs 53%: 14% [-3%, 34%] (n 12) | 0% [0%, 0%] (n 12) |
| SWING_HIGH | 50% vs 54%: -4% [-4%, -4%] (n 2) | 0% [0%, 0%] (n 2) |
| previous D1 high | 50% vs 48%: 2% [-16%, 20%] (n 18) | 6% [0%, 16%] (n 18) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 44% vs 41%: 3% [-21%, 32%] (n 9) | 0% [0%, 0%] (n 9) |
| SHORT | 66% vs 56%: 10% [-3%, 22%] (n 29) | 3% [0%, 10%] (n 29) |

### model_h4: F H4, C M15, E M1

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 10323 | 4659 | 10518 | 4697 | 19878 | 9418 | 4541 |
| ARMED | 9681 | 4409 | 9871 | 4447 | 19878 | 9418 | 3246 |
| MANIPULATED | 1393 | 663 | 1455 | 680 | 9758 | 4723 | 674 |
| REJECTED | 453 | 217 | 278 | 180 | 4243 | 1751 | 228 |
| DISPLACED | 246 | 96 | 204 | 93 | 2240 | 749 | 114 |
| IN_OTE | 28 | 15 | 14 | 9 | 350 | 78 | 6 |
| ENTERED | 25 | 13 | 13 | 8 | 297 | 67 | 5 |
| TP1 | 7 | 4 | 3 | 3 | 77 | 23 | 3 |
| SD_1 | 4 | 2 | 2 | 2 | 33 | 9 | 0 |
| SD_2 | 1 | 1 | 1 | 1 | 11 | 4 | 0 |
| SD_2.5 | 1 | 1 | 0 | 0 | 8 | 1 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 8929 | 3996 | 9062 | 4017 | 10120 | 4695 | 3867 |
| POI_FAILED | 167 | 78 | 170 | 78 | 0 | 0 | 93 |
| NO_REJECTION | 676 | 339 | 703 | 343 | 4644 | 2300 | 257 |
| RANGE_SPENT | 0 | 0 | 191 | 35 | 0 | 323 | 38 |
| TOO_LARGE | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| RETRACE_INVALID | 143 | 67 | 85 | 55 | 1553 | 654 | 84 |
| MISSED | 175 | 59 | 145 | 63 | 1600 | 576 | 88 |
| EXPIRED | 207 | 107 | 146 | 98 | 1664 | 803 | 109 |
| STOPPED | 18 | 10 | 12 | 7 | 249 | 57 | 5 |
| HORIZON | 6 | 2 | 1 | 1 | 40 | 9 | 0 |
| TARGETS_DONE | 1 | 1 | 0 | 0 | 8 | 1 | 0 |
| UNFINISHED | 1 | 0 | 1 | 0 | 0 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [13%, 16%] (n 9681) | 15% [14%, 17%] (n 4409) | 15% [14%, 16%] (n 9871) | 15% [14%, 17%] (n 4447) | 49% [49%, 50%] (n 19878) | 50% [49%, 51%] (n 9418) | 21% [19%, 22%] (n 3246) |
| REJECTED of MANIPULATED | 33% [30%, 35%] (n 1393) | 33% [29%, 36%] (n 663) | 19% [17%, 22%] (n 1455) | 26% [23%, 30%] (n 680) | 43% [42%, 45%] (n 9758) | 37% [34%, 40%] (n 4723) | 34% [29%, 38%] (n 674) |
| DISPLACED of REJECTED | 30% [26%, 34%] (n 453) | 28% [22%, 34%] (n 217) | 21% [15%, 27%] (n 278) | 19% [13%, 26%] (n 180) | 31% [29%, 32%] (n 4243) | 19% [17%, 22%] (n 1751) | 17% [12%, 23%] (n 228) |
| ENTERED of REJECTED and DISPLACED | 18% [12%, 25%] (n 137) | 22% [11%, 32%] (n 60) | 22% [13%, 33%] (n 58) | 23% [9%, 36%] (n 35) | 23% [21%, 25%] (n 1304) | 20% [16%, 25%] (n 332) | 13% [3%, 24%] (n 39) |
| **Premise**: C1's opposite extreme before C2's extreme | 50% vs coin 51%: **-2% [-6%, 2%]** (n 424) | 54% vs coin 52%: **2% [-3%, 8%]** (n 206) | 52% vs coin 53%: **-1% [-6%, 4%]** (n 263) | 54% vs coin 52%: **2% [-4%, 8%]** (n 170) | 48% vs coin 48%: **-1% [-2%, 1%]** (n 3866) | 51% vs coin 49%: **2% [-0%, 4%]** (n 1591) | 55% vs coin 50%: **5% [-0%, 11%]** (n 210) |
| C2 had already reached C1's opposite extreme | 24% [20%, 28%] | 24% [18%, 29%] | 26% [21%, 31%] | 23% [17%, 29%] | 27% [25%, 28%] | 28% [25%, 30%] | 29% [23%, 36%] |
| TP1 before the stop | 28% [12%, 46%] (n 25) | 31% [7%, 58%] (n 13) | 23% [0%, 50%] (n 13) | 38% [10%, 75%] (n 8) | 26% [21%, 31%] (n 297) | 34% [23%, 46%] (n 67) | 60% [20%, 100%] (n 5) |
| -1 SD before the stop | 16% [4%, 32%] (n 25) | 15% [0%, 38%] (n 13) | 15% [0%, 38%] (n 13) | 25% [0%, 62%] (n 8) | 11% [8%, 15%] (n 297) | 13% [5%, 23%] (n 67) | 0% [0%, 0%] (n 5) |
| -2 SD before the stop | 4% [0%, 12%] (n 25) | 8% [0%, 25%] (n 13) | 8% [0%, 25%] (n 13) | 12% [0%, 43%] (n 8) | 4% [2%, 6%] (n 297) | 6% [1%, 12%] (n 67) | 0% [0%, 0%] (n 5) |
| -2.5 SD before the stop | 4% [0%, 12%] (n 25) | 8% [0%, 25%] (n 13) | 0% [0%, 0%] (n 13) | 0% [0%, 0%] (n 8) | 3% [1%, 5%] (n 297) | 1% [0%, 5%] (n 67) | 0% [0%, 0%] (n 5) |
| R held to TP1 | +0.07 [-0.48, +0.66] (n 25) | -0.10 [-0.80, +0.87] (n 13) | -0.24 [-1.00, +0.70] (n 13) | +0.23 [-0.86, +1.81] (n 8) | +0.04 [-0.16, +0.23] (n 297) | +0.21 [-0.19, +0.64] (n 67) | +0.91 [-0.57, +2.56] (n 5) |
| R held to -2 SD | -0.05 [-0.79, +0.90] (n 25) | +0.12 [-1.00, +1.95] (n 13) | +0.07 [-1.00, +1.72] (n 13) | +0.74 [-1.00, +3.58] (n 8) | -0.29 [-0.50, -0.07] (n 297) | -0.12 [-0.62, +0.54] (n 67) | -1.00 [-1.00, -1.00] (n 5) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 59% vs 54%: 5% [-4%, 15%] (n 71) | 5% [1%, 11%] (n 76) |
| CLOSE | 54% vs 56%: -2% [-15%, 10%] (n 37) | 11% [2%, 21%] (n 44) |
| LONDON | 48% vs 50%: -2% [-14%, 10%] (n 52) | 9% [2%, 18%] (n 57) |
| MIDNIGHT | 46% vs 47%: -1% [-17%, 16%] (n 28) | 10% [0%, 21%] (n 29) |
| NY_AM | 55% vs 53%: 3% [-7%, 13%] (n 74) | 5% [1%, 10%] (n 80) |
| NY_MID | 34% vs 46%: -11% [-22%, -0%] (n 61) | 3% [0%, 7%] (n 64) |
| NY_PM | 36% vs 49%: -13% [-22%, -2%] (n 47) | 2% [0%, 7%] (n 49) |
| PRE_NY | 59% vs 56%: 4% [-7%, 15%] (n 54) | 2% [0%, 6%] (n 54) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 52% vs 51%: 1% [-5%, 7%] (n 192) | 3% [1%, 6%] (n 201) |
| True | 48% vs 52%: -4% [-8%, 1%] (n 232) | 8% [5%, 11%] (n 252) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 48% vs 48%: 1% [-8%, 9%] (n 95) | 5% [1%, 10%] (n 100) |
| None | 50% vs 52%: -2% [-6%, 2%] (n 320) | 6% [4%, 8%] (n 344) |
| TIGHT_RANGE | 67% vs 73%: -7% [-33%, 14%] (n 9) | 0% [0%, 0%] (n 9) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 62% vs 50%: 12% [-2%, 32%] (n 16) | 12% [0%, 33%] (n 17) |
| FVG | 29% vs 48%: -19% [-35%, -4%] (n 31) | 0% [0%, 0%] (n 32) |
| OB | 47% vs 46%: 1% [-10%, 12%] (n 58) | 6% [1%, 12%] (n 65) |
| PDH | 48% vs 52%: -5% [-16%, 8%] (n 40) | 2% [0%, 8%] (n 44) |
| PMH | 20% vs 42%: -22% [-45%, -4%] (n 5) | 0% [0%, 0%] (n 5) |
| PWH | 63% vs 56%: 7% [-11%, 23%] (n 19) | 0% [0%, 0%] (n 21) |
| SWING_HIGH | 51% vs 53%: -2% [-13%, 8%] (n 53) | 6% [2%, 13%] (n 62) |
| previous H4 high | 52% vs 53%: -0% [-6%, 5%] (n 202) | 7% [3%, 10%] (n 207) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 53% vs 54%: -1% [-7%, 5%] (n 162) | 5% [2%, 9%] (n 175) |
| SHORT | 48% vs 50%: -2% [-7%, 3%] (n 262) | 6% [3%, 9%] (n 278) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 55% vs 51%: 5% [-7%, 15%] (n 65) | 4% [0%, 10%] (n 70) |
| LONDON | 48% vs 53%: -5% [-18%, 8%] (n 40) | 5% [0%, 12%] (n 44) |
| MIDNIGHT | 46% vs 46%: 0% [-17%, 20%] (n 26) | 4% [0%, 12%] (n 27) |
| PRE_NY | 64% vs 60%: 4% [-7%, 17%] (n 39) | 5% [0%, 13%] (n 39) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 55% vs 50%: 5% [-4%, 14%] (n 73) | 3% [0%, 7%] (n 76) |
| True | 54% vs 54%: -1% [-8%, 7%] (n 97) | 6% [2%, 11%] (n 104) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 59% vs 51%: 7% [-7%, 21%] (n 41) | 9% [2%, 19%] (n 43) |
| None | 51% vs 51%: -0% [-6%, 5%] (n 116) | 3% [1%, 7%] (n 124) |
| TIGHT_RANGE | 69% vs 68%: 2% [-21%, 22%] (n 13) | 0% [0%, 0%] (n 13) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 100% vs 48%: 52% [52%, 52%] (n 1) | 0% [0%, 0%] (n 2) |
| FVG | 56% vs 52%: 3% [-25%, 31%] (n 9) | 0% [0%, 0%] (n 10) |
| OB | 57% vs 47%: 10% [-0%, 30%] (n 14) | 6% [0%, 25%] (n 17) |
| PDH | 42% vs 48%: -6% [-30%, 20%] (n 12) | 8% [0%, 30%] (n 12) |
| PMH | 25% vs 41%: -16% [-45%, 3%] (n 4) | 0% [0%, 0%] (n 4) |
| PWH | 80% vs 64%: 16% [-11%, 35%] (n 10) | 0% [0%, 0%] (n 11) |
| SWING_HIGH | 62% vs 57%: 6% [-11%, 22%] (n 24) | 12% [0%, 25%] (n 26) |
| previous H4 high | 51% vs 52%: -1% [-9%, 7%] (n 96) | 3% [0%, 7%] (n 98) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 48% vs 52%: -4% [-13%, 4%] (n 71) | 1% [0%, 5%] (n 74) |
| SHORT | 59% vs 53%: 6% [-3%, 14%] (n 99) | 7% [2%, 12%] (n 106) |

### model_h4_m30: F H4, C M30, E M1

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 5128 | 2307 | 5234 | 2333 | 10325 | 4848 | 2280 |
| ARMED | 4895 | 2220 | 4999 | 2247 | 10325 | 4848 | 1678 |
| MANIPULATED | 1015 | 485 | 1051 | 492 | 5067 | 2452 | 410 |
| REJECTED | 245 | 125 | 159 | 106 | 1703 | 761 | 104 |
| DISPLACED | 333 | 139 | 278 | 128 | 2093 | 746 | 130 |
| IN_OTE | 38 | 18 | 14 | 7 | 284 | 57 | 8 |
| ENTERED | 35 | 16 | 14 | 7 | 251 | 52 | 8 |
| TP1 | 9 | 5 | 5 | 4 | 51 | 14 | 2 |
| SD_1 | 7 | 2 | 1 | 0 | 23 | 0 | 0 |
| SD_2 | 3 | 1 | 0 | 0 | 12 | 0 | 0 |
| SD_2.5 | 2 | 0 | 0 | 0 | 8 | 0 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 4112 | 1822 | 4182 | 1841 | 5257 | 2396 | 1870 |
| POI_FAILED | 172 | 88 | 161 | 78 | 0 | 0 | 79 |
| NO_REJECTION | 425 | 216 | 434 | 210 | 2268 | 1112 | 131 |
| RANGE_SPENT | 0 | 0 | 105 | 19 | 0 | 116 | 9 |
| TOO_LARGE | 0 | 0 | 5 | 2 | 0 | 5 | 0 |
| RETRACE_INVALID | 64 | 30 | 38 | 24 | 555 | 272 | 27 |
| MISSED | 259 | 103 | 220 | 103 | 1597 | 603 | 112 |
| EXPIRED | 60 | 32 | 74 | 49 | 396 | 292 | 44 |
| STOPPED | 23 | 9 | 11 | 6 | 193 | 42 | 6 |
| HORIZON | 10 | 7 | 3 | 1 | 50 | 10 | 2 |
| TARGETS_DONE | 2 | 0 | 0 | 0 | 8 | 0 | 0 |
| UNFINISHED | 1 | 0 | 1 | 0 | 1 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 21% [19%, 22%] (n 4895) | 22% [20%, 24%] (n 2220) | 21% [20%, 22%] (n 4999) | 22% [20%, 24%] (n 2247) | 49% [48%, 50%] (n 10325) | 51% [50%, 52%] (n 4848) | 24% [22%, 27%] (n 1678) |
| REJECTED of MANIPULATED | 24% [22%, 27%] (n 1015) | 26% [22%, 29%] (n 485) | 15% [13%, 18%] (n 1051) | 22% [18%, 25%] (n 492) | 34% [32%, 35%] (n 5067) | 31% [28%, 34%] (n 2452) | 25% [20%, 30%] (n 410) |
| DISPLACED of REJECTED | 57% [50%, 63%] (n 245) | 56% [47%, 65%] (n 125) | 33% [25%, 40%] (n 159) | 33% [24%, 42%] (n 106) | 53% [51%, 56%] (n 1703) | 29% [25%, 33%] (n 761) | 34% [25%, 43%] (n 104) |
| ENTERED of REJECTED and DISPLACED | 25% [18%, 33%] (n 139) | 23% [13%, 34%] (n 70) | 27% [16%, 38%] (n 52) | 20% [8%, 34%] (n 35) | 28% [25%, 31%] (n 907) | 23% [18%, 29%] (n 222) | 23% [9%, 39%] (n 35) |
| **Premise**: C1's opposite extreme before C2's extreme | 50% vs coin 48%: **2% [-3%, 8%]** (n 203) | 56% vs coin 49%: **8% [0%, 15%]** (n 110) | 55% vs coin 52%: **3% [-4%, 11%]** (n 141) | 60% vs coin 53%: **7% [-2%, 15%]** (n 94) | 46% vs coin 47%: **-1% [-3%, 1%]** (n 1403) | 50% vs coin 49%: **1% [-2%, 4%]** (n 643) | 64% vs coin 54%: **10% [1%, 19%]** (n 85) |
| C2 had already reached C1's opposite extreme | 24% [19%, 30%] | 26% [19%, 34%] | 30% [23%, 36%] | 29% [21%, 37%] | 27% [24%, 30%] | 27% [23%, 31%] | 31% [22%, 40%] |
| TP1 before the stop | 26% [13%, 41%] (n 35) | 31% [12%, 53%] (n 16) | 36% [14%, 64%] (n 14) | 57% [14%, 86%] (n 7) | 20% [15%, 25%] (n 251) | 27% [15%, 40%] (n 52) | 25% [0%, 57%] (n 8) |
| -1 SD before the stop | 20% [8%, 35%] (n 35) | 12% [0%, 31%] (n 16) | 7% [0%, 21%] (n 14) | 0% [0%, 0%] (n 7) | 9% [6%, 13%] (n 251) | 0% [0%, 0%] (n 52) | 0% [0%, 0%] (n 8) |
| -2 SD before the stop | 9% [0%, 19%] (n 35) | 6% [0%, 20%] (n 16) | 0% [0%, 0%] (n 14) | 0% [0%, 0%] (n 7) | 5% [2%, 8%] (n 251) | 0% [0%, 0%] (n 52) | 0% [0%, 0%] (n 8) |
| -2.5 SD before the stop | 6% [0%, 15%] (n 35) | 0% [0%, 0%] (n 16) | 0% [0%, 0%] (n 14) | 0% [0%, 0%] (n 7) | 3% [1%, 6%] (n 251) | 0% [0%, 0%] (n 52) | 0% [0%, 0%] (n 8) |
| R held to TP1 | +0.31 [-0.38, +1.15] (n 35) | +0.28 [-0.54, +1.31] (n 16) | +0.42 [-0.47, +1.39] (n 14) | +1.13 [-0.32, +2.58] (n 7) | +0.02 [-0.21, +0.27] (n 251) | -0.04 [-0.44, +0.35] (n 52) | +0.24 [-0.73, +1.54] (n 8) |
| R held to -2 SD | +0.64 [-0.30, +1.71] (n 35) | +1.00 [-0.38, +2.84] (n 16) | -0.38 [-1.00, +0.40] (n 14) | -0.37 [-1.00, +0.88] (n 7) | +0.08 [-0.20, +0.41] (n 251) | -0.52 [-0.78, -0.21] (n 52) | -0.15 [-1.00, +1.23] (n 8) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 57% vs 51%: 6% [-7%, 19%] (n 42) | 12% [4%, 22%] (n 48) |
| CLOSE | 33% vs 46%: -12% [-36%, 9%] (n 15) | 23% [8%, 43%] (n 22) |
| LONDON | 59% vs 46%: 13% [-2%, 28%] (n 27) | 15% [3%, 26%] (n 34) |
| MIDNIGHT | 75% vs 58%: 17% [-3%, 35%] (n 12) | 0% [0%, 0%] (n 14) |
| NY_AM | 59% vs 54%: 5% [-7%, 18%] (n 29) | 17% [7%, 29%] (n 41) |
| NY_MID | 30% vs 38%: -8% [-22%, 8%] (n 27) | 9% [0%, 21%] (n 34) |
| NY_PM | 41% vs 49%: -8% [-20%, 7%] (n 22) | 17% [5%, 32%] (n 23) |
| PRE_NY | 48% vs 45%: 3% [-14%, 22%] (n 29) | 17% [4%, 31%] (n 29) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 51% vs 50%: 1% [-9%, 11%] (n 81) | 13% [7%, 19%] (n 110) |
| True | 50% vs 47%: 3% [-3%, 10%] (n 122) | 16% [9%, 22%] (n 135) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 55% vs 49%: 6% [-2%, 13%] (n 121) | 12% [7%, 17%] (n 144) |
| None | 44% vs 45%: -1% [-8%, 6%] (n 75) | 15% [9%, 22%] (n 93) |
| TIGHT_RANGE | 43% vs 60%: -17% [-52%, 22%] (n 7) | 50% [12%, 88%] (n 8) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 29% vs 40%: -11% [-34%, 25%] (n 7) | 18% [0%, 33%] (n 11) |
| FVG | 46% vs 40%: 6% [-11%, 25%] (n 13) | 13% [0%, 31%] (n 15) |
| OB | 29% vs 32%: -3% [-20%, 14%] (n 14) | 12% [0%, 26%] (n 24) |
| PDH | 42% vs 47%: -5% [-25%, 13%] (n 19) | 12% [0%, 28%] (n 24) |
| PMH | 0% vs 13%: -13% [-13%, -13%] (n 1) | 0% [0%, 0%] (n 2) |
| PWH | 45% vs 52%: -7% [-28%, 13%] (n 11) | 33% [8%, 64%] (n 12) |
| SWING_HIGH | 50% vs 50%: 0% [-17%, 19%] (n 22) | 23% [10%, 37%] (n 30) |
| previous H4 high | 57% vs 51%: 6% [-2%, 14%] (n 116) | 11% [6%, 17%] (n 127) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 49% vs 47%: 2% [-7%, 11%] (n 74) | 15% [9%, 22%] (n 93) |
| SHORT | 51% vs 48%: 3% [-4%, 9%] (n 129) | 14% [8%, 20%] (n 152) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 61% vs 51%: 10% [-3%, 23%] (n 36) | 12% [3%, 23%] (n 40) |
| LONDON | 55% vs 52%: 3% [-15%, 22%] (n 22) | 7% [0%, 19%] (n 28) |
| MIDNIGHT | 79% vs 62%: 17% [-0%, 32%] (n 14) | 0% [0%, 0%] (n 16) |
| PRE_NY | 50% vs 50%: -0% [-19%, 21%] (n 22) | 0% [0%, 0%] (n 22) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 59% vs 50%: 9% [-9%, 27%] (n 29) | 8% [0%, 19%] (n 36) |
| True | 60% vs 54%: 6% [-3%, 16%] (n 65) | 6% [1%, 12%] (n 70) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 63% vs 54%: 9% [-2%, 20%] (n 62) | 4% [0%, 10%] (n 67) |
| None | 50% vs 47%: 3% [-9%, 18%] (n 24) | 10% [0%, 21%] (n 31) |
| TIGHT_RANGE | 62% vs 63%: -0% [-31%, 34%] (n 8) | 12% [0%, 43%] (n 8) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |
| FVG | 100% vs 58%: 42% [27%, 60%] (n 4) | 0% [0%, 0%] (n 4) |
| OB | 33% vs 38%: -5% [-19%, 19%] (n 3) | 0% [0%, 0%] (n 7) |
| PDH | 43% vs 43%: 0% [-35%, 28%] (n 7) | 14% [0%, 50%] (n 7) |
| PMH | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |
| PWH | 80% vs 60%: 20% [9%, 38%] (n 5) | 17% [0%, 60%] (n 6) |
| SWING_HIGH | 40% vs 46%: -6% [-28%, 20%] (n 10) | 0% [0%, 0%] (n 12) |
| previous H4 high | 62% vs 55%: 7% [-4%, 17%] (n 65) | 7% [3%, 14%] (n 68) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 50% vs 50%: -0% [-14%, 16%] (n 34) | 5% [0%, 13%] (n 38) |
| SHORT | 65% vs 54%: 11% [2%, 21%] (n 60) | 7% [2%, 14%] (n 68) |

## USDJPY

### model_d1: F D1, C H1, E M5

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 2709 | 1225 | 2746 | 1237 | 4870 | 2425 | 1219 |
| ARMED | 2482 | 1148 | 2519 | 1160 | 4870 | 2425 | 821 |
| MANIPULATED | 280 | 127 | 288 | 129 | 2493 | 1243 | 154 |
| REJECTED | 100 | 43 | 67 | 28 | 1159 | 385 | 38 |
| DISPLACED | 38 | 15 | 36 | 20 | 458 | 170 | 25 |
| IN_OTE | 2 | 0 | 2 | 0 | 62 | 16 | 1 |
| ENTERED | 2 | 0 | 2 | 0 | 53 | 13 | 0 |
| TP1 | 0 | 0 | 0 | 0 | 18 | 5 | 0 |
| SD_1 | 0 | 0 | 0 | 0 | 4 | 2 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 1 | 1 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 2428 | 1098 | 2457 | 1108 | 2376 | 1182 | 1065 |
| POI_FAILED | 28 | 16 | 29 | 17 | 0 | 0 | 16 |
| NO_REJECTION | 139 | 62 | 142 | 62 | 1193 | 620 | 60 |
| RANGE_SPENT | 0 | 0 | 26 | 5 | 0 | 140 | 20 |
| TOO_LARGE | 0 | 0 | 10 | 7 | 0 | 30 | 6 |
| RETRACE_INVALID | 29 | 8 | 23 | 7 | 403 | 135 | 12 |
| MISSED | 30 | 12 | 24 | 15 | 324 | 117 | 21 |
| EXPIRED | 52 | 29 | 32 | 16 | 519 | 188 | 19 |
| STOPPED | 1 | 0 | 2 | 0 | 43 | 12 | 0 |
| HORIZON | 1 | 0 | 0 | 0 | 9 | 1 | 0 |
| TARGETS_DONE | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| UNFINISHED | 1 | 0 | 1 | 0 | 2 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 11% [9%, 13%] (n 2482) | 11% [9%, 14%] (n 1148) | 11% [10%, 13%] (n 2519) | 11% [9%, 14%] (n 1160) | 51% [50%, 52%] (n 4870) | 51% [50%, 53%] (n 2425) | 19% [16%, 22%] (n 821) |
| REJECTED of MANIPULATED | 36% [31%, 41%] (n 280) | 34% [27%, 42%] (n 127) | 23% [18%, 29%] (n 288) | 22% [15%, 30%] (n 129) | 46% [45%, 48%] (n 2493) | 31% [27%, 35%] (n 1243) | 25% [18%, 32%] (n 154) |
| DISPLACED of REJECTED | 23% [15%, 32%] (n 100) | 21% [10%, 33%] (n 43) | 24% [14%, 35%] (n 67) | 25% [10%, 41%] (n 28) | 27% [24%, 29%] (n 1159) | 21% [17%, 25%] (n 385) | 24% [10%, 39%] (n 38) |
| ENTERED of REJECTED and DISPLACED | 9% [0%, 22%] (n 23) | 0% [0%, 0%] (n 9) | 12% [0%, 28%] (n 16) | 0% [0%, 0%] (n 7) | 17% [13%, 22%] (n 311) | 16% [9%, 25%] (n 80) | 0% [0%, 0%] (n 9) |
| **Premise**: C1's opposite extreme before C2's extreme | 52% vs coin 54%: **-2% [-10%, 7%]** (n 96) | 60% vs coin 56%: **5% [-8%, 17%]** (n 43) | 57% vs coin 56%: **1% [-11%, 14%]** (n 65) | 61% vs coin 55%: **6% [-11%, 21%]** (n 28) | 52% vs coin 50%: **1% [-1%, 3%]** (n 1060) | 55% vs coin 52%: **3% [-0%, 7%]** (n 385) | 66% vs coin 50%: **16% [2%, 29%]** (n 38) |
| C2 had already reached C1's opposite extreme | 23% [15%, 31%] | 23% [11%, 38%] | 30% [19%, 40%] | 25% [10%, 42%] | 28% [25%, 31%] | 31% [27%, 36%] | 21% [8%, 33%] |
| TP1 before the stop | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 34% [22%, 47%] (n 53) | 38% [15%, 69%] (n 13) | – (n 0) |
| -1 SD before the stop | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 8% [0%, 17%] (n 53) | 15% [0%, 38%] (n 13) | – (n 0) |
| -2 SD before the stop | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 2% [0%, 6%] (n 53) | 8% [0%, 23%] (n 13) | – (n 0) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 2% [0%, 6%] (n 53) | 0% [0%, 0%] (n 13) | – (n 0) |
| R held to TP1 | -0.06 [-1.00, +0.88] (n 2) | – (n 0) | -1.00 [-1.00, -1.00] (n 2) | – (n 0) | -0.13 [-0.45, +0.23] (n 53) | +0.06 [-0.71, +0.95] (n 13) | – (n 0) |
| R held to -2 SD | -0.06 [-1.00, +0.88] (n 2) | – (n 0) | -1.00 [-1.00, -1.00] (n 2) | – (n 0) | -0.52 [-0.88, -0.04] (n 53) | -0.19 [-1.00, +1.42] (n 13) | – (n 0) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 59% vs 55%: 4% [-13%, 22%] (n 27) | 0% [0%, 0%] (n 27) |
| CLOSE | 57% vs 59%: -2% [-18%, 14%] (n 30) | 0% [0%, 0%] (n 33) |
| LONDON | 50% vs 55%: -5% [-36%, 30%] (n 8) | 0% [0%, 0%] (n 8) |
| MIDNIGHT | 80% vs 63%: 17% [-5%, 45%] (n 5) | 0% [0%, 0%] (n 5) |
| NY_AM | 25% vs 39%: -14% [-28%, -1%] (n 8) | 11% [0%, 33%] (n 9) |
| NY_MID | 38% vs 50%: -11% [-30%, 9%] (n 13) | 8% [0%, 25%] (n 13) |
| NY_PM | 33% vs 55%: -21% [-58%, 14%] (n 3) | 0% [0%, 0%] (n 3) |
| PRE_NY | 50% vs 28%: 22% [-28%, 72%] (n 2) | 0% [0%, 0%] (n 2) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 52% vs 54%: -2% [-11%, 8%] (n 85) | 2% [0%, 6%] (n 89) |
| True | 55% vs 55%: -0% [-19%, 20%] (n 11) | 0% [0%, 0%] (n 11) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 44% vs 61%: -17% [-38%, 5%] (n 16) | 0% [0%, 0%] (n 17) |
| None | 59% vs 53%: 6% [-4%, 15%] (n 66) | 3% [0%, 8%] (n 68) |
| TIGHT_RANGE | 29% vs 50%: -21% [-42%, 1%] (n 14) | 0% [0%, 0%] (n 15) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 33% vs 29%: 4% [-18%, 50%] (n 3) | 0% [0%, 0%] (n 3) |
| FVG | 33% vs 49%: -16% [-33%, -1%] (n 9) | 9% [0%, 38%] (n 11) |
| OB | 50% vs 30%: 20% [-5%, 72%] (n 4) | 0% [0%, 0%] (n 4) |
| PMH | 40% vs 55%: -15% [-42%, 24%] (n 5) | 0% [0%, 0%] (n 5) |
| PWH | 44% vs 57%: -12% [-35%, 16%] (n 18) | 0% [0%, 0%] (n 18) |
| SWING_HIGH | 25% vs 45%: -20% [-37%, -2%] (n 8) | 10% [0%, 30%] (n 10) |
| previous D1 high | 65% vs 59%: 7% [-5%, 18%] (n 49) | 0% [0%, 0%] (n 49) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 51% vs 55%: -4% [-16%, 8%] (n 59) | 3% [0%, 8%] (n 62) |
| SHORT | 54% vs 52%: 2% [-10%, 14%] (n 37) | 0% [0%, 0%] (n 38) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 68% vs 60%: 8% [-12%, 27%] (n 19) | 0% [0%, 0%] (n 19) |
| LONDON | 60% vs 57%: 3% [-39%, 49%] (n 5) | 0% [0%, 0%] (n 5) |
| MIDNIGHT | 33% vs 27%: 6% [-34%, 70%] (n 3) | 0% [0%, 0%] (n 3) |
| PRE_NY | 0% vs 28%: -28% [-28%, -28%] (n 1) | 0% [0%, 0%] (n 1) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 58% vs 56%: 3% [-17%, 20%] (n 24) | 0% [0%, 0%] (n 24) |
| True | 75% vs 52%: 23% [-12%, 49%] (n 4) | 0% [0%, 0%] (n 4) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 43% vs 56%: -13% [-42%, 10%] (n 7) | 0% [0%, 0%] (n 7) |
| None | 65% vs 54%: 11% [-12%, 32%] (n 17) | 0% [0%, 0%] (n 17) |
| TIGHT_RANGE | 75% vs 58%: 17% [-8%, 42%] (n 4) | 0% [0%, 0%] (n 4) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 50% vs 45%: 5% [5%, 5%] (n 2) | 0% [0%, 0%] (n 2) |
| PMH | 0% vs 34%: -34% [-34%, -34%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | 0% vs 76%: -76% [-76%, -76%] (n 1) | 0% [0%, 0%] (n 1) |
| SWING_HIGH | 100% vs 98%: 2% [2%, 2%] (n 1) | 0% [0%, 0%] (n 1) |
| previous D1 high | 65% vs 54%: 11% [-6%, 31%] (n 23) | 0% [0%, 0%] (n 23) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 62% vs 53%: 10% [-11%, 29%] (n 16) | 0% [0%, 0%] (n 16) |
| SHORT | 58% vs 58%: 0% [-24%, 28%] (n 12) | 0% [0%, 0%] (n 12) |

### model_h4: F H4, C M15, E M1

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 10327 | 4785 | 10559 | 4874 | 20042 | 9690 | 4721 |
| ARMED | 9701 | 4448 | 9927 | 4534 | 20042 | 9690 | 3379 |
| MANIPULATED | 1356 | 606 | 1402 | 622 | 9877 | 4839 | 751 |
| REJECTED | 416 | 191 | 261 | 136 | 3994 | 1522 | 209 |
| DISPLACED | 262 | 105 | 188 | 98 | 2473 | 823 | 136 |
| IN_OTE | 34 | 15 | 15 | 9 | 358 | 70 | 12 |
| ENTERED | 31 | 15 | 14 | 8 | 301 | 57 | 8 |
| TP1 | 18 | 9 | 5 | 3 | 93 | 19 | 3 |
| SD_1 | 6 | 3 | 1 | 1 | 44 | 5 | 1 |
| SD_2 | 4 | 3 | 1 | 1 | 24 | 4 | 1 |
| SD_2.5 | 4 | 3 | 1 | 1 | 16 | 4 | 1 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 8970 | 4179 | 9156 | 4252 | 10165 | 4851 | 3970 |
| POI_FAILED | 150 | 67 | 151 | 70 | 0 | 0 | 116 |
| NO_REJECTION | 682 | 311 | 709 | 315 | 4933 | 2386 | 291 |
| RANGE_SPENT | 0 | 0 | 168 | 44 | 0 | 487 | 62 |
| TOO_LARGE | 0 | 0 | 1 | 0 | 0 | 3 | 0 |
| RETRACE_INVALID | 139 | 63 | 90 | 48 | 1406 | 588 | 66 |
| MISSED | 191 | 74 | 143 | 73 | 1812 | 638 | 103 |
| EXPIRED | 163 | 76 | 126 | 64 | 1424 | 680 | 105 |
| STOPPED | 18 | 7 | 11 | 5 | 232 | 42 | 7 |
| HORIZON | 9 | 5 | 2 | 2 | 53 | 11 | 0 |
| TARGETS_DONE | 4 | 3 | 1 | 1 | 16 | 4 | 1 |
| UNFINISHED | 1 | 0 | 1 | 0 | 1 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [13%, 15%] (n 9701) | 14% [12%, 15%] (n 4448) | 14% [13%, 15%] (n 9927) | 14% [12%, 15%] (n 4534) | 49% [49%, 50%] (n 20042) | 50% [49%, 51%] (n 9690) | 22% [20%, 24%] (n 3379) |
| REJECTED of MANIPULATED | 31% [28%, 33%] (n 1356) | 32% [28%, 35%] (n 606) | 19% [16%, 21%] (n 1402) | 22% [18%, 26%] (n 622) | 40% [39%, 41%] (n 9877) | 31% [28%, 35%] (n 4839) | 28% [24%, 32%] (n 751) |
| DISPLACED of REJECTED | 35% [30%, 40%] (n 416) | 35% [28%, 42%] (n 191) | 20% [14%, 25%] (n 261) | 20% [13%, 26%] (n 136) | 36% [35%, 38%] (n 3994) | 19% [17%, 22%] (n 1522) | 22% [16%, 28%] (n 209) |
| ENTERED of REJECTED and DISPLACED | 22% [15%, 29%] (n 144) | 23% [13%, 32%] (n 66) | 27% [17%, 39%] (n 51) | 30% [14%, 46%] (n 27) | 21% [19%, 22%] (n 1455) | 19% [15%, 24%] (n 294) | 17% [7%, 28%] (n 46) |
| **Premise**: C1's opposite extreme before C2's extreme | 48% vs coin 48%: **0% [-4%, 5%]** (n 390) | 50% vs coin 48%: **2% [-4%, 8%]** (n 184) | 51% vs coin 50%: **1% [-4%, 5%]** (n 250) | 48% vs coin 48%: **1% [-6%, 8%]** (n 130) | 49% vs coin 48%: **1% [-0%, 2%]** (n 3656) | 49% vs coin 48%: **1% [-2%, 3%]** (n 1395) | 55% vs coin 50%: **5% [-1%, 11%]** (n 192) |
| C2 had already reached C1's opposite extreme | 18% [14%, 22%] | 17% [12%, 23%] | 26% [21%, 31%] | 21% [14%, 27%] | 24% [22%, 25%] | 27% [24%, 29%] | 29% [24%, 35%] |
| TP1 before the stop | 58% [42%, 76%] (n 31) | 60% [35%, 86%] (n 15) | 36% [14%, 64%] (n 14) | 38% [0%, 75%] (n 8) | 31% [26%, 36%] (n 301) | 33% [21%, 45%] (n 57) | 38% [12%, 75%] (n 8) |
| -1 SD before the stop | 19% [4%, 36%] (n 31) | 20% [0%, 43%] (n 15) | 7% [0%, 21%] (n 14) | 12% [0%, 38%] (n 8) | 15% [11%, 19%] (n 301) | 9% [2%, 17%] (n 57) | 12% [0%, 38%] (n 8) |
| -2 SD before the stop | 13% [3%, 25%] (n 31) | 20% [0%, 43%] (n 15) | 7% [0%, 21%] (n 14) | 12% [0%, 38%] (n 8) | 8% [5%, 11%] (n 301) | 7% [2%, 15%] (n 57) | 12% [0%, 38%] (n 8) |
| -2.5 SD before the stop | 13% [3%, 25%] (n 31) | 20% [0%, 43%] (n 15) | 7% [0%, 21%] (n 14) | 12% [0%, 38%] (n 8) | 5% [3%, 8%] (n 301) | 7% [2%, 15%] (n 57) | 12% [0%, 38%] (n 8) |
| R held to TP1 | +1.23 [+0.53, +1.97] (n 31) | +1.22 [+0.21, +2.34] (n 15) | +0.35 [-0.55, +1.38] (n 14) | +1.02 [-0.48, +2.55] (n 8) | +0.17 [-0.02, +0.37] (n 301) | +0.19 [-0.20, +0.59] (n 57) | +0.62 [-0.64, +2.23] (n 8) |
| R held to -2 SD | +1.13 [+0.04, +2.31] (n 31) | +1.70 [+0.00, +3.74] (n 15) | +0.12 [-1.00, +1.64] (n 14) | +0.96 [-0.75, +3.35] (n 8) | +0.28 [-0.04, +0.61] (n 301) | +0.21 [-0.40, +0.94] (n 57) | +0.19 [-1.00, +2.57] (n 8) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 49%: 1% [-9%, 11%] (n 68) | 7% [1%, 14%] (n 71) |
| CLOSE | 50% vs 52%: -2% [-14%, 11%] (n 48) | 10% [2%, 18%] (n 52) |
| LONDON | 58% vs 50%: 9% [-4%, 22%] (n 36) | 10% [2%, 21%] (n 39) |
| MIDNIGHT | 58% vs 51%: 7% [-10%, 22%] (n 38) | 13% [3%, 23%] (n 39) |
| NY_AM | 53% vs 47%: 6% [-4%, 18%] (n 60) | 5% [0%, 11%] (n 65) |
| NY_MID | 37% vs 47%: -10% [-21%, 2%] (n 60) | 9% [2%, 17%] (n 69) |
| NY_PM | 45% vs 44%: 1% [-12%, 14%] (n 38) | 5% [0%, 14%] (n 39) |
| PRE_NY | 36% vs 43%: -7% [-17%, 4%] (n 42) | 2% [0%, 8%] (n 42) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 48% vs 45%: 3% [-3%, 9%] (n 178) | 8% [5%, 12%] (n 185) |
| True | 48% vs 50%: -2% [-8%, 4%] (n 212) | 7% [4%, 10%] (n 231) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 49% vs 47%: 2% [-8%, 11%] (n 94) | 10% [5%, 16%] (n 101) |
| None | 48% vs 48%: -0% [-6%, 5%] (n 292) | 7% [4%, 10%] (n 311) |
| TIGHT_RANGE | 50% vs 51%: -1% [-25%, 13%] (n 4) | 0% [0%, 0%] (n 4) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 75% vs 57%: 18% [-32%, 49%] (n 12) | 23% [7%, 46%] (n 13) |
| FVG | 55% vs 44%: 11% [-4%, 25%] (n 31) | 3% [0%, 10%] (n 34) |
| OB | 36% vs 45%: -9% [-24%, 6%] (n 42) | 4% [0%, 14%] (n 46) |
| PDH | 40% vs 46%: -6% [-17%, 7%] (n 42) | 11% [2%, 20%] (n 47) |
| PMH | 50% vs 48%: 2% [-49%, 52%] (n 4) | 0% [0%, 0%] (n 4) |
| PWH | 25% vs 41%: -16% [-38%, 7%] (n 8) | 0% [0%, 0%] (n 11) |
| SWING_HIGH | 47% vs 46%: 1% [-13%, 15%] (n 43) | 11% [4%, 22%] (n 45) |
| previous H4 high | 50% vs 49%: 1% [-4%, 6%] (n 208) | 7% [4%, 11%] (n 216) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 46% vs 51%: -4% [-10%, 1%] (n 188) | 4% [1%, 7%] (n 202) |
| SHORT | 50% vs 45%: 4% [-3%, 11%] (n 202) | 11% [7%, 15%] (n 214) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 47%: 3% [-8%, 15%] (n 54) | 9% [2%, 17%] (n 56) |
| LONDON | 57% vs 47%: 10% [-5%, 27%] (n 21) | 0% [0%, 0%] (n 24) |
| MIDNIGHT | 48% vs 56%: -7% [-23%, 9%] (n 31) | 3% [0%, 9%] (n 32) |
| PRE_NY | 38% vs 41%: -3% [-18%, 13%] (n 24) | 8% [0%, 22%] (n 24) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 51% vs 44%: 7% [-3%, 19%] (n 53) | 2% [0%, 6%] (n 55) |
| True | 47% vs 50%: -4% [-14%, 7%] (n 77) | 9% [4%, 15%] (n 81) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 43% vs 45%: -2% [-17%, 15%] (n 28) | 3% [0%, 10%] (n 32) |
| None | 46% vs 47%: -1% [-9%, 8%] (n 84) | 7% [2%, 12%] (n 86) |
| TIGHT_RANGE | 67% vs 56%: 11% [-7%, 31%] (n 18) | 6% [0%, 19%] (n 18) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 67% vs 74%: -7% [-20%, 19%] (n 3) | 0% [0%, 0%] (n 4) |
| FVG | 50% vs 47%: 3% [-16%, 21%] (n 12) | 8% [0%, 23%] (n 12) |
| OB | 33% vs 38%: -4% [-28%, 28%] (n 9) | 11% [0%, 30%] (n 9) |
| PDH | 56% vs 46%: 10% [-7%, 28%] (n 18) | 15% [0%, 32%] (n 20) |
| PWH | 0% vs 30%: -30% [-43%, -11%] (n 3) | 0% [0%, 0%] (n 3) |
| SWING_HIGH | 45% vs 36%: 9% [-17%, 37%] (n 11) | 9% [0%, 33%] (n 11) |
| previous H4 high | 50% vs 51%: -1% [-11%, 9%] (n 74) | 3% [0%, 7%] (n 77) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 43% vs 48%: -5% [-15%, 6%] (n 49) | 2% [0%, 7%] (n 53) |
| SHORT | 52% vs 48%: 4% [-5%, 14%] (n 81) | 8% [3%, 15%] (n 83) |

### model_h4_m30: F H4, C M30, E M1

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 5147 | 2391 | 5256 | 2428 | 10417 | 4950 | 2365 |
| ARMED | 4917 | 2264 | 5023 | 2299 | 10417 | 4950 | 1744 |
| MANIPULATED | 1011 | 460 | 1036 | 466 | 5194 | 2488 | 417 |
| REJECTED | 244 | 131 | 160 | 89 | 1608 | 667 | 108 |
| DISPLACED | 380 | 174 | 292 | 136 | 2268 | 789 | 131 |
| IN_OTE | 47 | 23 | 15 | 6 | 292 | 49 | 8 |
| ENTERED | 42 | 18 | 13 | 6 | 255 | 39 | 5 |
| TP1 | 11 | 5 | 3 | 1 | 53 | 6 | 1 |
| SD_1 | 3 | 0 | 0 | 0 | 27 | 3 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 8 | 1 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 8 | 1 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 4135 | 1931 | 4219 | 1962 | 5222 | 2462 | 1948 |
| POI_FAILED | 163 | 72 | 156 | 68 | 0 | 0 | 62 |
| NO_REJECTION | 407 | 187 | 402 | 180 | 2395 | 1124 | 123 |
| RANGE_SPENT | 0 | 0 | 105 | 32 | 0 | 168 | 33 |
| TOO_LARGE | 0 | 0 | 2 | 1 | 0 | 3 | 1 |
| RETRACE_INVALID | 58 | 28 | 48 | 27 | 472 | 250 | 41 |
| MISSED | 295 | 133 | 243 | 117 | 1770 | 664 | 115 |
| EXPIRED | 46 | 22 | 67 | 35 | 302 | 240 | 37 |
| STOPPED | 35 | 17 | 11 | 4 | 198 | 28 | 3 |
| HORIZON | 7 | 1 | 2 | 2 | 49 | 10 | 2 |
| TARGETS_DONE | 0 | 0 | 0 | 0 | 8 | 1 | 0 |
| UNFINISHED | 1 | 0 | 1 | 0 | 1 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 21% [19%, 22%] (n 4917) | 20% [18%, 23%] (n 2264) | 21% [19%, 22%] (n 5023) | 20% [18%, 23%] (n 2299) | 50% [49%, 50%] (n 10417) | 50% [49%, 51%] (n 4950) | 24% [22%, 26%] (n 1744) |
| REJECTED of MANIPULATED | 24% [22%, 26%] (n 1011) | 28% [25%, 32%] (n 460) | 15% [13%, 18%] (n 1036) | 19% [15%, 23%] (n 466) | 31% [30%, 32%] (n 5194) | 27% [24%, 30%] (n 2488) | 26% [22%, 31%] (n 417) |
| DISPLACED of REJECTED | 66% [60%, 71%] (n 244) | 72% [64%, 79%] (n 131) | 32% [25%, 40%] (n 160) | 34% [23%, 44%] (n 89) | 60% [58%, 62%] (n 1608) | 32% [28%, 36%] (n 667) | 33% [25%, 41%] (n 108) |
| ENTERED of REJECTED and DISPLACED | 26% [19%, 34%] (n 160) | 19% [12%, 27%] (n 94) | 25% [14%, 37%] (n 52) | 20% [7%, 34%] (n 30) | 26% [24%, 29%] (n 968) | 18% [14%, 24%] (n 212) | 14% [3%, 26%] (n 36) |
| **Premise**: C1's opposite extreme before C2's extreme | 42% vs coin 46%: **-4% [-9%, 2%]** (n 212) | 51% vs coin 47%: **4% [-4%, 11%]** (n 116) | 52% vs coin 52%: **-0% [-6%, 5%]** (n 145) | 52% vs coin 50%: **3% [-5%, 11%]** (n 80) | 46% vs coin 45%: **1% [-1%, 3%]** (n 1326) | 49% vs coin 47%: **2% [-0%, 5%]** (n 556) | 51% vs coin 45%: **5% [-3%, 13%]** (n 93) |
| C2 had already reached C1's opposite extreme | 18% [14%, 24%] | 18% [11%, 24%] | 31% [25%, 38%] | 26% [17%, 34%] | 26% [24%, 29%] | 28% [24%, 31%] | 23% [16%, 31%] |
| TP1 before the stop | 26% [12%, 41%] (n 42) | 28% [10%, 50%] (n 18) | 23% [0%, 46%] (n 13) | 17% [0%, 50%] (n 6) | 21% [16%, 26%] (n 255) | 15% [5%, 26%] (n 39) | 20% [0%, 60%] (n 5) |
| -1 SD before the stop | 7% [0%, 15%] (n 42) | 0% [0%, 0%] (n 18) | 0% [0%, 0%] (n 13) | 0% [0%, 0%] (n 6) | 11% [7%, 14%] (n 255) | 8% [0%, 17%] (n 39) | 0% [0%, 0%] (n 5) |
| -2 SD before the stop | 0% [0%, 0%] (n 42) | 0% [0%, 0%] (n 18) | 0% [0%, 0%] (n 13) | 0% [0%, 0%] (n 6) | 3% [1%, 5%] (n 255) | 3% [0%, 8%] (n 39) | 0% [0%, 0%] (n 5) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 42) | 0% [0%, 0%] (n 18) | 0% [0%, 0%] (n 13) | 0% [0%, 0%] (n 6) | 3% [1%, 5%] (n 255) | 3% [0%, 8%] (n 39) | 0% [0%, 0%] (n 5) |
| R held to TP1 | +0.08 [-0.43, +0.61] (n 42) | -0.20 [-0.79, +0.53] (n 18) | -0.34 [-0.90, +0.43] (n 13) | -0.63 [-1.00, -0.09] (n 6) | +0.00 [-0.20, +0.22] (n 255) | -0.25 [-0.65, +0.23] (n 39) | -0.16 [-1.00, +0.99] (n 5) |
| R held to -2 SD | -0.43 [-0.81, +0.00] (n 42) | -0.91 [-1.00, -0.71] (n 18) | -0.83 [-1.00, -0.58] (n 13) | -0.62 [-1.00, -0.08] (n 6) | -0.04 [-0.33, +0.25] (n 255) | -0.05 [-0.62, +0.60] (n 39) | +0.21 [-1.00, +2.11] (n 5) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 46% vs 41%: 4% [-9%, 18%] (n 37) | 12% [2%, 22%] (n 43) |
| CLOSE | 35% vs 52%: -17% [-33%, 1%] (n 20) | 30% [13%, 52%] (n 23) |
| LONDON | 75% vs 55%: 20% [2%, 37%] (n 20) | 0% [0%, 0%] (n 28) |
| MIDNIGHT | 46% vs 50%: -4% [-23%, 13%] (n 24) | 29% [12%, 48%] (n 24) |
| NY_AM | 36% vs 50%: -14% [-29%, 3%] (n 33) | 19% [6%, 34%] (n 36) |
| NY_MID | 33% vs 39%: -5% [-22%, 12%] (n 27) | 22% [9%, 37%] (n 37) |
| NY_PM | 19% vs 32%: -13% [-28%, 1%] (n 16) | 12% [0%, 29%] (n 17) |
| PRE_NY | 46% vs 47%: -1% [-15%, 12%] (n 35) | 17% [6%, 29%] (n 36) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 41% vs 48%: -7% [-18%, 3%] (n 78) | 19% [11%, 27%] (n 96) |
| True | 43% vs 45%: -1% [-8%, 6%] (n 134) | 16% [11%, 23%] (n 148) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 43% vs 44%: -2% [-9%, 6%] (n 122) | 15% [9%, 21%] (n 139) |
| None | 42% vs 49%: -7% [-16%, 2%] (n 86) | 20% [12%, 28%] (n 101) |
| TIGHT_RANGE | 50% vs 40%: 10% [-30%, 49%] (n 4) | 25% [0%, 75%] (n 4) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 67% vs 49%: 17% [-8%, 56%] (n 3) | 25% [0%, 75%] (n 4) |
| FVG | 54% vs 44%: 10% [-18%, 39%] (n 13) | 19% [0%, 38%] (n 16) |
| OB | 33% vs 43%: -9% [-31%, 18%] (n 18) | 17% [4%, 31%] (n 24) |
| PDH | 24% vs 46%: -23% [-37%, -7%] (n 21) | 42% [24%, 60%] (n 24) |
| PWH | 43% vs 33%: 10% [-29%, 49%] (n 7) | 33% [11%, 62%] (n 9) |
| SWING_HIGH | 54% vs 48%: 6% [-11%, 21%] (n 26) | 23% [10%, 37%] (n 31) |
| previous H4 high | 43% vs 47%: -4% [-11%, 3%] (n 124) | 10% [6%, 16%] (n 136) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 42% vs 47%: -6% [-13%, 2%] (n 115) | 16% [10%, 23%] (n 131) |
| SHORT | 43% vs 45%: -1% [-9%, 7%] (n 97) | 19% [12%, 26%] (n 113) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 47%: 3% [-10%, 15%] (n 30) | 11% [3%, 22%] (n 36) |
| LONDON | 71% vs 57%: 14% [-8%, 36%] (n 14) | 6% [0%, 19%] (n 17) |
| MIDNIGHT | 44% vs 44%: -1% [-24%, 24%] (n 16) | 0% [0%, 0%] (n 16) |
| PRE_NY | 50% vs 52%: -2% [-17%, 14%] (n 20) | 5% [0%, 14%] (n 20) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 55% vs 49%: 6% [-9%, 21%] (n 29) | 6% [0%, 15%] (n 34) |
| True | 51% vs 50%: 1% [-8%, 11%] (n 51) | 7% [2%, 14%] (n 55) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 52% vs 47%: 5% [-6%, 17%] (n 46) | 6% [0%, 13%] (n 52) |
| None | 33% vs 40%: -7% [-24%, 12%] (n 21) | 8% [0%, 21%] (n 24) |
| TIGHT_RANGE | 85% vs 74%: 10% [2%, 24%] (n 13) | 8% [0%, 25%] (n 13) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 50% vs 52%: -2% [-8%, 4%] (n 2) | 0% [0%, 0%] (n 2) |
| FVG | 100% vs 64%: 36% [21%, 53%] (n 5) | 14% [0%, 43%] (n 7) |
| OB | 33% vs 37%: -4% [-41%, 48%] (n 3) | 0% [0%, 0%] (n 3) |
| PDH | 71% vs 58%: 14% [-11%, 40%] (n 7) | 0% [0%, 0%] (n 9) |
| PWH | 50% vs 17%: 33% [-9%, 75%] (n 2) | 0% [0%, 0%] (n 3) |
| SWING_HIGH | 50% vs 50%: 0% [-31%, 24%] (n 8) | 22% [0%, 45%] (n 9) |
| previous H4 high | 47% vs 49%: -2% [-11%, 8%] (n 53) | 5% [0%, 11%] (n 56) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 39% vs 46%: -7% [-17%, 3%] (n 36) | 7% [0%, 15%] (n 41) |
| SHORT | 64% vs 53%: 11% [-1%, 23%] (n 44) | 6% [0%, 14%] (n 48) |

## XAUUSD

### model_d1: F D1, C H1, E M5

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 2145 | 1059 | 2187 | 1073 | 4681 | 2407 | 975 |
| ARMED | 2012 | 1005 | 2053 | 1018 | 4681 | 2407 | 588 |
| MANIPULATED | 291 | 152 | 302 | 152 | 2362 | 1229 | 121 |
| REJECTED | 103 | 53 | 59 | 34 | 1087 | 393 | 37 |
| DISPLACED | 44 | 23 | 39 | 21 | 378 | 174 | 14 |
| IN_OTE | 5 | 1 | 4 | 1 | 52 | 12 | 0 |
| ENTERED | 5 | 1 | 4 | 1 | 44 | 9 | 0 |
| TP1 | 3 | 1 | 2 | 1 | 12 | 5 | 0 |
| SD_1 | 1 | 1 | 1 | 1 | 3 | 2 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 1853 | 907 | 1884 | 921 | 2317 | 1178 | 854 |
| POI_FAILED | 30 | 10 | 30 | 10 | 0 | 0 | 20 |
| NO_REJECTION | 145 | 81 | 150 | 81 | 1148 | 611 | 47 |
| RANGE_SPENT | 0 | 0 | 40 | 13 | 0 | 126 | 9 |
| TOO_LARGE | 0 | 0 | 3 | 2 | 0 | 13 | 0 |
| RETRACE_INVALID | 25 | 10 | 15 | 7 | 377 | 139 | 16 |
| MISSED | 32 | 17 | 26 | 16 | 279 | 130 | 9 |
| EXPIRED | 54 | 33 | 34 | 22 | 514 | 201 | 20 |
| STOPPED | 5 | 1 | 4 | 1 | 41 | 8 | 0 |
| HORIZON | 0 | 0 | 0 | 0 | 3 | 1 | 0 |
| UNFINISHED | 1 | 0 | 1 | 0 | 2 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [12%, 18%] (n 2012) | 15% [12%, 19%] (n 1005) | 15% [12%, 18%] (n 2053) | 15% [11%, 19%] (n 1018) | 50% [49%, 52%] (n 4681) | 51% [50%, 53%] (n 2407) | 21% [17%, 25%] (n 588) |
| REJECTED of MANIPULATED | 35% [30%, 40%] (n 291) | 35% [28%, 42%] (n 152) | 20% [15%, 25%] (n 302) | 22% [15%, 30%] (n 152) | 46% [44%, 48%] (n 2362) | 32% [28%, 36%] (n 1229) | 31% [22%, 39%] (n 121) |
| DISPLACED of REJECTED | 29% [21%, 38%] (n 103) | 28% [17%, 41%] (n 53) | 19% [9%, 30%] (n 59) | 18% [6%, 32%] (n 34) | 22% [20%, 25%] (n 1087) | 17% [14%, 21%] (n 393) | 11% [3%, 21%] (n 37) |
| ENTERED of REJECTED and DISPLACED | 17% [3%, 31%] (n 30) | 7% [0%, 21%] (n 15) | 36% [8%, 70%] (n 11) | 17% [0%, 50%] (n 6) | 18% [14%, 22%] (n 244) | 13% [6%, 21%] (n 68) | 0% [0%, 0%] (n 4) |
| **Premise**: C1's opposite extreme before C2's extreme | 61% vs coin 54%: **7% [-2%, 16%]** (n 98) | 69% vs coin 54%: **15% [2%, 28%]** (n 52) | 66% vs coin 56%: **10% [-1%, 22%]** (n 59) | 71% vs coin 55%: **16% [1%, 31%]** (n 34) | 52% vs coin 49%: **3% [1%, 5%]** (n 971) | 56% vs coin 51%: **5% [2%, 9%]** (n 393) | 49% vs coin 48%: **0% [-11%, 12%]** (n 37) |
| C2 had already reached C1's opposite extreme | 25% [17%, 34%] | 25% [14%, 35%] | 36% [24%, 48%] | 29% [15%, 45%] | 28% [25%, 30%] | 33% [27%, 38%] | 38% [23%, 54%] |
| TP1 before the stop | 60% [20%, 100%] (n 5) | 100% [100%, 100%] (n 1) | 50% [0%, 100%] (n 4) | 100% [100%, 100%] (n 1) | 27% [15%, 40%] (n 44) | 56% [22%, 89%] (n 9) | – (n 0) |
| -1 SD before the stop | 20% [0%, 60%] (n 5) | 100% [100%, 100%] (n 1) | 25% [0%, 75%] (n 4) | 100% [100%, 100%] (n 1) | 7% [0%, 16%] (n 44) | 22% [0%, 45%] (n 9) | – (n 0) |
| -2 SD before the stop | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 44) | 0% [0%, 0%] (n 9) | – (n 0) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 44) | 0% [0%, 0%] (n 9) | – (n 0) |
| R held to TP1 | +0.68 [-0.63, +1.99] (n 5) | +2.66 [+2.66, +2.66] (n 1) | +0.38 [-1.00, +1.77] (n 4) | +2.66 [+2.66, +2.66] (n 1) | -0.16 [-0.52, +0.29] (n 44) | +0.51 [-0.42, +1.44] (n 9) | – (n 0) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 5) | -1.00 [-1.00, -1.00] (n 1) | -1.00 [-1.00, -1.00] (n 4) | -1.00 [-1.00, -1.00] (n 1) | -0.82 [-1.00, -0.55] (n 44) | -0.49 [-1.00, +0.53] (n 9) | – (n 0) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 65% vs 50%: 15% [-4%, 33%] (n 23) | 4% [0%, 13%] (n 23) |
| CLOSE | 52% vs 54%: -2% [-15%, 10%] (n 25) | 12% [0%, 24%] (n 25) |
| LONDON | 67% vs 58%: 9% [-24%, 41%] (n 9) | 0% [0%, 0%] (n 10) |
| MIDNIGHT | 80% vs 67%: 13% [-11%, 33%] (n 10) | 0% [0%, 0%] (n 10) |
| NY_AM | 57% vs 52%: 5% [-17%, 25%] (n 14) | 7% [0%, 21%] (n 14) |
| NY_MID | 43% vs 44%: -1% [-25%, 27%] (n 7) | 0% [0%, 0%] (n 10) |
| NY_PM | 50% vs 54%: -4% [-23%, 16%] (n 2) | 0% [0%, 0%] (n 3) |
| PRE_NY | 75% vs 58%: 17% [-12%, 44%] (n 8) | 0% [0%, 0%] (n 8) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 59% vs 53%: 5% [-5%, 16%] (n 80) | 5% [1%, 10%] (n 85) |
| True | 72% vs 59%: 14% [-6%, 33%] (n 18) | 6% [0%, 16%] (n 18) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 73% vs 59%: 13% [-8%, 34%] (n 11) | 27% [7%, 60%] (n 11) |
| None | 60% vs 54%: 6% [-3%, 16%] (n 87) | 2% [0%, 6%] (n 92) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 100% vs 81%: 19% [19%, 19%] (n 1) | 0% [0%, 0%] (n 1) |
| FVG | 57% vs 43%: 14% [-12%, 62%] (n 7) | 0% [0%, 0%] (n 9) |
| OB | 67% vs 55%: 11% [-8%, 32%] (n 21) | 0% [0%, 0%] (n 24) |
| PWH | 100% vs 63%: 37% [21%, 50%] (n 8) | 0% [0%, 0%] (n 8) |
| SWING_HIGH | 30% vs 45%: -15% [-36%, 11%] (n 10) | 10% [0%, 33%] (n 10) |
| previous D1 high | 59% vs 56%: 3% [-7%, 14%] (n 51) | 8% [2%, 16%] (n 51) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 50% vs 52%: -2% [-18%, 17%] (n 24) | 4% [0%, 12%] (n 26) |
| SHORT | 65% vs 55%: 10% [0%, 20%] (n 74) | 5% [1%, 11%] (n 77) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 65% vs 52%: 13% [-6%, 32%] (n 20) | 5% [0%, 15%] (n 20) |
| LONDON | 67% vs 49%: 18% [-23%, 58%] (n 6) | 0% [0%, 0%] (n 6) |
| MIDNIGHT | 83% vs 61%: 22% [-5%, 41%] (n 6) | 0% [0%, 0%] (n 6) |
| PRE_NY | 100% vs 81%: 19% [7%, 30%] (n 2) | 0% [0%, 0%] (n 2) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 70% vs 54%: 16% [0%, 32%] (n 30) | 3% [0%, 11%] (n 30) |
| True | 75% vs 58%: 17% [-26%, 57%] (n 4) | 0% [0%, 0%] (n 4) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 60% vs 61%: -1% [-57%, 36%] (n 5) | 0% [0%, 0%] (n 5) |
| None | 82% vs 56%: 26% [10%, 44%] (n 22) | 5% [0%, 15%] (n 22) |
| TIGHT_RANGE | 43% vs 46%: -3% [-33%, 27%] (n 7) | 0% [0%, 0%] (n 7) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 32%: 68% [68%, 68%] (n 1) | 0% [0%, 0%] (n 1) |
| OB | 100% vs 45%: 55% [39%, 70%] (n 2) | 0% [0%, 0%] (n 2) |
| PWH | 100% vs 50%: 50% [49%, 53%] (n 4) | 0% [0%, 0%] (n 4) |
| SWING_HIGH | 33% vs 53%: -19% [-44%, 30%] (n 3) | 0% [0%, 0%] (n 3) |
| previous D1 high | 67% vs 58%: 9% [-6%, 26%] (n 24) | 4% [0%, 14%] (n 24) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 67% vs 63%: 4% [-29%, 32%] (n 9) | 0% [0%, 0%] (n 9) |
| SHORT | 72% vs 52%: 20% [4%, 39%] (n 25) | 4% [0%, 14%] (n 25) |

### model_h4: F H4, C M15, E M1

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 9420 | 4523 | 9585 | 4572 | 18742 | 9540 | 4402 |
| ARMED | 8820 | 4249 | 8983 | 4296 | 18742 | 9540 | 3145 |
| MANIPULATED | 1322 | 655 | 1366 | 671 | 9366 | 4809 | 705 |
| REJECTED | 431 | 219 | 245 | 159 | 4182 | 1581 | 198 |
| DISPLACED | 209 | 98 | 182 | 94 | 1982 | 718 | 82 |
| IN_OTE | 20 | 7 | 11 | 5 | 271 | 51 | 3 |
| ENTERED | 15 | 4 | 10 | 5 | 218 | 38 | 1 |
| TP1 | 3 | 1 | 3 | 2 | 52 | 13 | 0 |
| SD_1 | 2 | 1 | 3 | 2 | 19 | 7 | 0 |
| SD_2 | 1 | 1 | 2 | 2 | 11 | 6 | 0 |
| SD_2.5 | 1 | 1 | 2 | 2 | 10 | 5 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 8098 | 3868 | 8219 | 3901 | 9375 | 4731 | 3697 |
| POI_FAILED | 170 | 82 | 174 | 83 | 0 | 0 | 94 |
| NO_REJECTION | 643 | 315 | 651 | 316 | 4487 | 2302 | 295 |
| RANGE_SPENT | 0 | 0 | 192 | 59 | 0 | 547 | 76 |
| TOO_LARGE | 0 | 0 | 2 | 0 | 0 | 2 | 0 |
| RETRACE_INVALID | 139 | 73 | 88 | 54 | 1470 | 575 | 73 |
| MISSED | 159 | 81 | 137 | 73 | 1445 | 556 | 63 |
| EXPIRED | 196 | 100 | 112 | 81 | 1745 | 789 | 103 |
| STOPPED | 13 | 2 | 6 | 2 | 178 | 22 | 0 |
| HORIZON | 1 | 1 | 2 | 1 | 30 | 11 | 1 |
| TARGETS_DONE | 1 | 1 | 2 | 2 | 10 | 5 | 0 |
| UNFINISHED | 0 | 0 | 0 | 0 | 2 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 15% [14%, 16%] (n 8820) | 15% [14%, 17%] (n 4249) | 15% [14%, 16%] (n 8983) | 16% [14%, 17%] (n 4296) | 50% [49%, 51%] (n 18742) | 50% [50%, 51%] (n 9540) | 22% [21%, 24%] (n 3145) |
| REJECTED of MANIPULATED | 33% [30%, 35%] (n 1322) | 33% [30%, 37%] (n 655) | 18% [15%, 21%] (n 1366) | 24% [20%, 28%] (n 671) | 45% [44%, 46%] (n 9366) | 33% [29%, 36%] (n 4809) | 28% [23%, 33%] (n 705) |
| DISPLACED of REJECTED | 28% [24%, 32%] (n 431) | 25% [19%, 31%] (n 219) | 21% [16%, 26%] (n 245) | 16% [10%, 22%] (n 159) | 30% [28%, 31%] (n 4182) | 16% [14%, 18%] (n 1581) | 13% [8%, 18%] (n 198) |
| ENTERED of REJECTED and DISPLACED | 13% [7%, 18%] (n 119) | 7% [2%, 15%] (n 55) | 20% [10%, 31%] (n 51) | 20% [4%, 38%] (n 25) | 18% [16%, 20%] (n 1238) | 15% [11%, 20%] (n 251) | 4% [0%, 12%] (n 25) |
| **Premise**: C1's opposite extreme before C2's extreme | 49% vs coin 50%: **-1% [-6%, 4%]** (n 389) | 51% vs coin 48%: **3% [-4%, 9%]** (n 195) | 49% vs coin 50%: **-1% [-7%, 6%]** (n 227) | 52% vs coin 48%: **4% [-3%, 12%]** (n 145) | 48% vs coin 49%: **-1% [-2%, 1%]** (n 3788) | 51% vs coin 51%: **0% [-2%, 2%]** (n 1454) | 48% vs coin 50%: **-2% [-8%, 4%]** (n 180) |
| C2 had already reached C1's opposite extreme | 17% [14%, 21%] | 18% [13%, 23%] | 20% [16%, 25%] | 19% [14%, 25%] | 25% [24%, 27%] | 28% [26%, 31%] | 24% [18%, 30%] |
| TP1 before the stop | 20% [0%, 40%] (n 15) | 25% [0%, 75%] (n 4) | 30% [0%, 60%] (n 10) | 40% [0%, 80%] (n 5) | 24% [19%, 29%] (n 218) | 34% [21%, 49%] (n 38) | 0% [0%, 0%] (n 1) |
| -1 SD before the stop | 13% [0%, 33%] (n 15) | 25% [0%, 75%] (n 4) | 30% [0%, 60%] (n 10) | 40% [0%, 80%] (n 5) | 9% [5%, 12%] (n 218) | 18% [8%, 31%] (n 38) | 0% [0%, 0%] (n 1) |
| -2 SD before the stop | 7% [0%, 20%] (n 15) | 25% [0%, 75%] (n 4) | 20% [0%, 50%] (n 10) | 40% [0%, 80%] (n 5) | 5% [2%, 8%] (n 218) | 16% [5%, 28%] (n 38) | 0% [0%, 0%] (n 1) |
| -2.5 SD before the stop | 7% [0%, 20%] (n 15) | 25% [0%, 75%] (n 4) | 20% [0%, 50%] (n 10) | 40% [0%, 80%] (n 5) | 5% [2%, 7%] (n 218) | 13% [3%, 24%] (n 38) | 0% [0%, 0%] (n 1) |
| R held to TP1 | -0.37 [-0.85, +0.23] (n 15) | +0.12 [-1.00, +1.24] (n 4) | +0.03 [-0.77, +0.89] (n 10) | +0.65 [-0.56, +1.86] (n 5) | -0.12 [-0.30, +0.08] (n 218) | +0.53 [-0.00, +1.14] (n 38) | +1.27 [+1.27, +1.27] (n 1) |
| R held to -2 SD | -0.20 [-1.00, +1.25] (n 15) | +2.00 [-1.00, +6.29] (n 4) | +1.46 [-0.55, +4.02] (n 10) | +3.30 [-0.55, +7.11] (n 5) | -0.10 [-0.38, +0.19] (n 218) | +1.25 [+0.19, +2.40] (n 38) | +1.27 [+1.27, +1.27] (n 1) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 52% vs 46%: 6% [-5%, 17%] (n 79) | 2% [0%, 6%] (n 90) |
| CLOSE | 37% vs 49%: -12% [-26%, 2%] (n 41) | 8% [2%, 16%] (n 49) |
| LONDON | 66% vs 52%: 13% [0%, 27%] (n 32) | 0% [0%, 0%] (n 42) |
| MIDNIGHT | 39% vs 47%: -7% [-20%, 6%] (n 38) | 2% [0%, 8%] (n 41) |
| NY_AM | 57% vs 57%: -1% [-12%, 11%] (n 69) | 4% [0%, 9%] (n 72) |
| NY_MID | 46% vs 46%: -0% [-13%, 13%] (n 52) | 2% [0%, 5%] (n 58) |
| NY_PM | 39% vs 49%: -10% [-27%, 7%] (n 33) | 9% [0%, 18%] (n 34) |
| PRE_NY | 49% vs 49%: -0% [-13%, 14%] (n 45) | 2% [0%, 7%] (n 45) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 52% vs 50%: 2% [-5%, 9%] (n 186) | 3% [1%, 6%] (n 208) |
| True | 46% vs 50%: -3% [-9%, 2%] (n 203) | 4% [1%, 6%] (n 223) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 51% vs 52%: -0% [-10%, 9%] (n 88) | 2% [0%, 5%] (n 98) |
| None | 48% vs 49%: -1% [-7%, 5%] (n 299) | 4% [2%, 6%] (n 331) |
| TIGHT_RANGE | 50% vs 49%: 1% [-38%, 40%] (n 2) | 0% [0%, 0%] (n 2) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 36% vs 40%: -5% [-19%, 10%] (n 14) | 0% [0%, 0%] (n 16) |
| FVG | 38% vs 50%: -12% [-29%, 7%] (n 37) | 0% [0%, 0%] (n 44) |
| OB | 53% vs 48%: 5% [-5%, 17%] (n 62) | 4% [0%, 9%] (n 71) |
| PDH | 54% vs 52%: 1% [-13%, 16%] (n 28) | 7% [0%, 16%] (n 30) |
| PMH | 0% vs 42%: -42% [-57%, -26%] (n 4) | 0% [0%, 0%] (n 5) |
| PWH | 50% vs 49%: 1% [-27%, 26%] (n 12) | 0% [0%, 0%] (n 14) |
| SWING_HIGH | 32% vs 48%: -16% [-29%, -4%] (n 41) | 2% [0%, 7%] (n 45) |
| previous H4 high | 54% vs 51%: 3% [-3%, 10%] (n 191) | 4% [2%, 7%] (n 206) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 51% vs 52%: -1% [-9%, 7%] (n 138) | 1% [0%, 3%] (n 153) |
| SHORT | 48% vs 48%: -1% [-7%, 6%] (n 251) | 5% [2%, 7%] (n 278) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 53% vs 47%: 6% [-6%, 17%] (n 72) | 3% [0%, 7%] (n 79) |
| LONDON | 67% vs 53%: 14% [-3%, 30%] (n 24) | 0% [0%, 0%] (n 28) |
| MIDNIGHT | 39% vs 49%: -10% [-24%, 5%] (n 28) | 6% [0%, 16%] (n 31) |
| PRE_NY | 48% vs 42%: 6% [-17%, 30%] (n 21) | 5% [0%, 16%] (n 21) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 57% vs 49%: 9% [-2%, 20%] (n 61) | 3% [0%, 7%] (n 70) |
| True | 48% vs 47%: 1% [-9%, 11%] (n 84) | 3% [0%, 8%] (n 89) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 50% vs 52%: -2% [-15%, 11%] (n 42) | 0% [0%, 0%] (n 46) |
| None | 52% vs 45%: 7% [-3%, 17%] (n 90) | 4% [1%, 8%] (n 99) |
| TIGHT_RANGE | 54% vs 50%: 4% [-19%, 26%] (n 13) | 7% [0%, 21%] (n 14) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 100% vs 40%: 60% [60%, 60%] (n 1) | 0% [0%, 0%] (n 1) |
| FVG | 62% vs 51%: 11% [-37%, 51%] (n 8) | 0% [0%, 0%] (n 10) |
| OB | 42% vs 36%: 5% [-16%, 51%] (n 12) | 7% [0%, 27%] (n 15) |
| PDH | 47% vs 47%: -1% [-23%, 23%] (n 15) | 0% [0%, 0%] (n 16) |
| PWH | 57% vs 50%: 7% [-19%, 32%] (n 7) | 0% [0%, 0%] (n 7) |
| SWING_HIGH | 15% vs 47%: -32% [-45%, -18%] (n 13) | 0% [0%, 0%] (n 14) |
| previous H4 high | 57% vs 49%: 8% [1%, 17%] (n 89) | 4% [1%, 9%] (n 96) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 53% vs 51%: 2% [-10%, 14%] (n 53) | 0% [0%, 0%] (n 57) |
| SHORT | 51% vs 46%: 6% [-4%, 16%] (n 92) | 5% [1%, 10%] (n 102) |

### model_h4_m30: F H4, C M30, E M1

| State reached | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 4659 | 2244 | 4811 | 2301 | 9638 | 4924 | 2199 |
| ARMED | 4435 | 2137 | 4584 | 2194 | 9638 | 4924 | 1578 |
| MANIPULATED | 953 | 478 | 990 | 488 | 4724 | 2408 | 382 |
| REJECTED | 250 | 129 | 141 | 92 | 1721 | 665 | 101 |
| DISPLACED | 326 | 160 | 290 | 141 | 1825 | 681 | 97 |
| IN_OTE | 52 | 29 | 13 | 6 | 281 | 34 | 7 |
| ENTERED | 47 | 25 | 13 | 6 | 250 | 30 | 6 |
| TP1 | 10 | 5 | 2 | 0 | 42 | 4 | 1 |
| SD_1 | 5 | 3 | 1 | 0 | 20 | 3 | 1 |
| SD_2 | 1 | 1 | 0 | 0 | 7 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 6 | 0 | 0 |

| How it ended | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 3705 | 1766 | 3820 | 1813 | 4913 | 2516 | 1817 |
| POI_FAILED | 184 | 97 | 177 | 96 | 0 | 0 | 54 |
| NO_REJECTION | 360 | 184 | 355 | 175 | 2163 | 1087 | 145 |
| RANGE_SPENT | 0 | 0 | 93 | 22 | 0 | 170 | 20 |
| TOO_LARGE | 0 | 0 | 5 | 1 | 0 | 5 | 0 |
| RETRACE_INVALID | 59 | 21 | 48 | 24 | 537 | 254 | 33 |
| MISSED | 238 | 117 | 249 | 125 | 1362 | 588 | 81 |
| EXPIRED | 65 | 34 | 50 | 39 | 411 | 274 | 43 |
| STOPPED | 34 | 18 | 11 | 6 | 188 | 26 | 6 |
| HORIZON | 13 | 7 | 2 | 0 | 56 | 4 | 0 |
| TARGETS_DONE | 0 | 0 | 0 | 0 | 6 | 0 | 0 |
| UNFINISHED | 1 | 0 | 1 | 0 | 2 | 0 | 0 |

| Measure | Model A | + time | + volatility | + time + volatility | CRT: no context | CRT + time + volatility | Random POI + time + volatility |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 21% [20%, 23%] (n 4435) | 22% [20%, 25%] (n 2137) | 22% [20%, 23%] (n 4584) | 22% [20%, 25%] (n 2194) | 49% [48%, 50%] (n 9638) | 49% [48%, 50%] (n 4924) | 24% [22%, 27%] (n 1578) |
| REJECTED of MANIPULATED | 26% [23%, 29%] (n 953) | 27% [23%, 31%] (n 478) | 14% [11%, 17%] (n 990) | 19% [15%, 23%] (n 488) | 36% [35%, 38%] (n 4724) | 28% [24%, 31%] (n 2408) | 26% [21%, 32%] (n 382) |
| DISPLACED of REJECTED | 59% [53%, 66%] (n 250) | 66% [57%, 74%] (n 129) | 33% [25%, 43%] (n 141) | 33% [23%, 43%] (n 92) | 53% [51%, 56%] (n 1721) | 23% [20%, 27%] (n 665) | 27% [19%, 35%] (n 101) |
| ENTERED of REJECTED and DISPLACED | 32% [23%, 40%] (n 148) | 29% [20%, 40%] (n 85) | 28% [16%, 40%] (n 47) | 20% [7%, 34%] (n 30) | 27% [24%, 30%] (n 917) | 20% [14%, 25%] (n 153) | 22% [7%, 40%] (n 27) |
| **Premise**: C1's opposite extreme before C2's extreme | 49% vs coin 48%: **1% [-5%, 7%]** (n 197) | 55% vs coin 49%: **6% [-1%, 14%]** (n 103) | 52% vs coin 48%: **3% [-4%, 11%]** (n 118) | 57% vs coin 48%: **9% [-0%, 18%]** (n 76) | 47% vs coin 47%: **0% [-2%, 2%]** (n 1381) | 53% vs coin 50%: **3% [0%, 6%]** (n 552) | 46% vs coin 47%: **-1% [-9%, 8%]** (n 83) |
| C2 had already reached C1's opposite extreme | 18% [14%, 24%] | 17% [11%, 24%] | 24% [17%, 31%] | 23% [14%, 32%] | 24% [22%, 26%] | 30% [26%, 34%] | 21% [13%, 28%] |
| TP1 before the stop | 21% [10%, 35%] (n 47) | 20% [4%, 38%] (n 25) | 15% [0%, 38%] (n 13) | 0% [0%, 0%] (n 6) | 17% [12%, 22%] (n 250) | 13% [3%, 26%] (n 30) | 17% [0%, 50%] (n 6) |
| -1 SD before the stop | 11% [2%, 20%] (n 47) | 12% [0%, 27%] (n 25) | 8% [0%, 23%] (n 13) | 0% [0%, 0%] (n 6) | 8% [5%, 11%] (n 250) | 10% [0%, 21%] (n 30) | 17% [0%, 50%] (n 6) |
| -2 SD before the stop | 2% [0%, 7%] (n 47) | 4% [0%, 13%] (n 25) | 0% [0%, 0%] (n 13) | 0% [0%, 0%] (n 6) | 3% [1%, 5%] (n 250) | 0% [0%, 0%] (n 30) | 0% [0%, 0%] (n 6) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 47) | 0% [0%, 0%] (n 25) | 0% [0%, 0%] (n 13) | 0% [0%, 0%] (n 6) | 2% [1%, 4%] (n 250) | 0% [0%, 0%] (n 30) | 0% [0%, 0%] (n 6) |
| R held to TP1 | +0.08 [-0.40, +0.67] (n 47) | +0.16 [-0.49, +0.94] (n 25) | -0.19 [-1.00, +0.83] (n 13) | -1.00 [-1.00, -1.00] (n 6) | -0.12 [-0.33, +0.11] (n 250) | -0.54 [-0.94, -0.11] (n 30) | -0.36 [-1.00, +0.92] (n 6) |
| R held to -2 SD | +0.06 [-0.56, +0.88] (n 47) | +0.21 [-0.64, +1.34] (n 25) | -0.57 [-1.00, +0.11] (n 13) | -1.00 [-1.00, -1.00] (n 6) | +0.00 [-0.27, +0.29] (n 250) | -0.64 [-0.96, -0.22] (n 30) | -1.00 [-1.00, -1.00] (n 6) |


**Breakdowns: Model A**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 58% vs 51%: 7% [-6%, 20%] (n 36) | 16% [7%, 27%] (n 50) |
| CLOSE | 44% vs 47%: -4% [-23%, 17%] (n 16) | 18% [4%, 36%] (n 22) |
| LONDON | 60% vs 50%: 10% [-7%, 27%] (n 20) | 22% [7%, 42%] (n 27) |
| MIDNIGHT | 72% vs 44%: 28% [9%, 46%] (n 18) | 17% [4%, 33%] (n 23) |
| NY_AM | 51% vs 49%: 3% [-11%, 18%] (n 35) | 13% [5%, 23%] (n 45) |
| NY_MID | 31% vs 48%: -17% [-32%, -1%] (n 29) | 24% [11%, 38%] (n 37) |
| NY_PM | 43% vs 45%: -2% [-22%, 20%] (n 14) | 18% [0%, 35%] (n 17) |
| PRE_NY | 38% vs 48%: -10% [-26%, 5%] (n 29) | 24% [10%, 40%] (n 29) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 48% vs 50%: -2% [-11%, 7%] (n 80) | 18% [10%, 26%] (n 109) |
| True | 50% vs 47%: 3% [-5%, 11%] (n 117) | 19% [13%, 26%] (n 141) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 48% vs 47%: 1% [-6%, 9%] (n 114) | 18% [12%, 25%] (n 142) |
| None | 52% vs 51%: 1% [-7%, 11%] (n 81) | 20% [11%, 29%] (n 102) |
| TIGHT_RANGE | 0% vs 31%: -31% [-32%, -30%] (n 2) | 17% [0%, 50%] (n 6) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 60% vs 61%: -1% [-48%, 41%] (n 5) | 33% [0%, 75%] (n 6) |
| FVG | 39% vs 45%: -6% [-29%, 19%] (n 18) | 12% [0%, 24%] (n 26) |
| OB | 38% vs 46%: -8% [-24%, 9%] (n 24) | 23% [7%, 38%] (n 31) |
| PDH | 67% vs 55%: 12% [-3%, 27%] (n 21) | 15% [4%, 30%] (n 26) |
| PMH | 100% vs 63%: 37% [37%, 37%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | 0% vs 42%: -42% [-65%, -20%] (n 2) | 0% [0%, 0%] (n 4) |
| SWING_HIGH | 39% vs 45%: -6% [-22%, 11%] (n 18) | 25% [10%, 42%] (n 28) |
| previous H4 high | 52% vs 48%: 4% [-3%, 11%] (n 108) | 19% [12%, 26%] (n 128) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 51% vs 51%: 0% [-11%, 12%] (n 65) | 22% [12%, 33%] (n 90) |
| SHORT | 48% vs 47%: 1% [-5%, 8%] (n 132) | 17% [11%, 23%] (n 160) |


**Breakdowns: + time + volatility**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 68% vs 52%: 16% [2%, 30%] (n 28) | 5% [0%, 14%] (n 37) |
| LONDON | 50% vs 49%: 1% [-18%, 19%] (n 16) | 0% [0%, 0%] (n 19) |
| MIDNIGHT | 75% vs 46%: 29% [9%, 50%] (n 16) | 10% [0%, 25%] (n 20) |
| PRE_NY | 25% vs 42%: -17% [-34%, 5%] (n 16) | 12% [0%, 33%] (n 16) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 53% vs 43%: 9% [-9%, 28%] (n 19) | 4% [0%, 12%] (n 26) |
| True | 58% vs 49%: 9% [-2%, 19%] (n 57) | 8% [2%, 14%] (n 66) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 54% vs 47%: 7% [-4%, 19%] (n 52) | 6% [2%, 13%] (n 62) |
| None | 50% vs 38%: 12% [-10%, 35%] (n 14) | 5% [0%, 17%] (n 20) |
| TIGHT_RANGE | 80% vs 67%: 13% [-2%, 26%] (n 10) | 10% [0%, 30%] (n 10) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 100% vs 54%: 46% [46%, 46%] (n 1) | 0% [0%, 0%] (n 1) |
| FVG | 50% vs 38%: 12% [-38%, 63%] (n 2) | 0% [0%, 0%] (n 3) |
| OB | 33% vs 37%: -4% [-32%, 46%] (n 3) | 0% [0%, 0%] (n 4) |
| PDH | 56% vs 48%: 8% [-22%, 33%] (n 9) | 10% [0%, 38%] (n 10) |
| SWING_HIGH | 43% vs 44%: -1% [-22%, 22%] (n 7) | 8% [0%, 27%] (n 12) |
| previous H4 high | 59% vs 49%: 10% [0%, 21%] (n 54) | 6% [1%, 13%] (n 62) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 56% vs 52%: 4% [-11%, 17%] (n 27) | 10% [0%, 23%] (n 31) |
| SHORT | 57% vs 45%: 12% [2%, 24%] (n 49) | 5% [0%, 11%] (n 61) |
