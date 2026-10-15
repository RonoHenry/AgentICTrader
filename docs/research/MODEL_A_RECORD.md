# The Model A record

Context-engine Requirement 16 (update 2026-10-15). Descriptive: no verdict and no ledger row. It feeds the review with the trader.

- **snapshot:** exness-2025-2026h1
- **slice:** exploration slice, 2025-01-01 to 2025-07-01 (end exclusive)
- **frame sets:** model_d1, model_h4, model_h4_m30, model_h4_m3, w1_d1_h4, d1_h4_m15, h1_m15_m1
- **code_commit:** e50365b5088082a386c735e41317f79478cf9ccb

**How to read it.**
- The funnel counts instances: each closed C candle in context starts one.
- **The premise:** once C2 has rejected, how often price reaches C1's opposite extreme before C2's extreme, within the F candle. It's compared with a coin flip from the same distances.
  - The interval is that difference, paired by trading date.
  - A lower bound above zero means the step carries information.
- **After the fill:** the outcomes of the few that reach the OTE and fill.
- **The baselines** read the same C and E rules. CRT has no F context; the random-POI baseline moves every POI.

## Summary: the premise against its coin flip

Once C2 has rejected: C1's opposite extreme before C2's extreme, minus the coin flip from the same distances, with its day-cluster interval. Fills: how many reached the 0.705 entry in six months.

| Instrument | Frame set | Model A | CRT (no context) | Random POI | Model A fills | R held to TP1 |
|---|---|---|---|---|---:|---|
| EURUSD | model_d1 (D1/H1/M5) | -4% [-12, +4] (n 96) | +2% [+0, +5] (n 1058) | +1% [-6, +8] (n 135) | 5 | -0.56 [-1.00, +0.33] |
| EURUSD | model_h4 (H4/M15/M1) | +2% [-3, +6] (n 376) | +1% [+0, +2] (n 3624) | -1% [-5, +3] (n 493) | 34 | -0.31 [-0.69, +0.12] |
| EURUSD | model_h4_m30 (H4/M30/M1) | +6% [+1, +11] (n 217) | +1% [-1, +4] (n 1280) | +0% [-6, +6] (n 178) | 34 | +0.53 [-0.22, +1.34] |
| EURUSD | model_h4_m3 (H4/M15/M3) | +3% [-0, +7] (n 463) | +3% [+2, +4] (n 4338) | +4% [+1, +7] (n 612) | 7 | -0.56 [-1.00, +0.04] |
| EURUSD | w1_d1_h4 (W1/D1/H4) | +24% [-10, +56] (n 6) | +7% [-11, +26] (n 26) | -16% [-65, +53] (n 4) | 0 | – |
| EURUSD | d1_h4_m15 (D1/H4/M15) | +17% [+4, +30] (n 35) | +6% [+0, +11] (n 219) | +5% [-8, +19] (n 36) | 3 | +0.58 [-1.00, +2.32] |
| EURUSD | h1_m15_m1 (H1/M15/M1) | -0% [-4, +3] (n 621) | +1% [+0, +2] (n 2751) | +1% [-2, +5] (n 429) | 67 | -0.14 [-0.43, +0.14] |
| GBPUSD | model_d1 (D1/H1/M5) | +8% [+1, +15] (n 111) | +2% [-0, +4] (n 1036) | -3% [-10, +4] (n 111) | 2 | -1.00 [-1.00, -1.00] |
| GBPUSD | model_h4 (H4/M15/M1) | -2% [-6, +2] (n 424) | -1% [-2, +1] (n 3866) | +0% [-3, +4] (n 528) | 25 | +0.07 [-0.48, +0.66] |
| GBPUSD | model_h4_m30 (H4/M30/M1) | +2% [-3, +8] (n 203) | -1% [-3, +1] (n 1403) | +4% [-2, +11] (n 189) | 35 | +0.31 [-0.38, +1.15] |
| GBPUSD | model_h4_m3 (H4/M15/M3) | +0% [-3, +4] (n 490) | +0% [-1, +2] (n 4497) | +1% [-2, +4] (n 626) | 8 | -0.08 [-0.72, +0.63] |
| GBPUSD | w1_d1_h4 (W1/D1/H4) | -3% [-21, +13] (n 8) | +11% [-1, +22] (n 32) | +5% [-17, +18] (n 4) | 0 | – |
| GBPUSD | d1_h4_m15 (D1/H4/M15) | +3% [-9, +17] (n 38) | -0% [-6, +5] (n 185) | +5% [-8, +20] (n 24) | 1 | -1.00 [-1.00, -1.00] |
| GBPUSD | h1_m15_m1 (H1/M15/M1) | -3% [-6, +0] (n 677) | -2% [-3, -1] (n 2962) | -2% [-6, +2] (n 429) | 74 | +0.32 [-0.07, +0.74] |
| USDJPY | model_d1 (D1/H1/M5) | -2% [-10, +7] (n 96) | +1% [-1, +3] (n 1060) | -1% [-7, +6] (n 131) | 2 | -0.06 [-1.00, +0.88] |
| USDJPY | model_h4 (H4/M15/M1) | +0% [-4, +5] (n 390) | +1% [-0, +2] (n 3656) | +0% [-3, +4] (n 513) | 31 | +1.23 [+0.53, +1.97] |
| USDJPY | model_h4_m30 (H4/M30/M1) | -4% [-9, +2] (n 212) | +1% [-1, +3] (n 1326) | -4% [-9, +2] (n 186) | 42 | +0.08 [-0.43, +0.61] |
| USDJPY | model_h4_m3 (H4/M15/M3) | +0% [-4, +5] (n 471) | +2% [+1, +3] (n 4402) | +0% [-4, +4] (n 611) | 7 | +0.01 [-0.86, +1.27] |
| USDJPY | w1_d1_h4 (W1/D1/H4) | -20% [-50, +12] (n 10) | -4% [-16, +7] (n 39) | -10% [-35, +15] (n 8) | 1 | -1.00 [-1.00, -1.00] |
| USDJPY | d1_h4_m15 (D1/H4/M15) | -11% [-26, +4] (n 32) | -3% [-8, +3] (n 187) | -9% [-24, +8] (n 22) | 4 | -0.46 [-1.00, +0.62] |
| USDJPY | h1_m15_m1 (H1/M15/M1) | +1% [-2, +4] (n 694) | +0% [-1, +1] (n 2791) | -0% [-4, +4] (n 413) | 66 | +0.24 [-0.13, +0.64] |
| XAUUSD | model_d1 (D1/H1/M5) | +7% [-2, +16] (n 98) | +3% [+1, +5] (n 971) | +5% [-4, +14] (n 95) | 5 | +0.68 [-0.63, +1.99] |
| XAUUSD | model_h4 (H4/M15/M1) | -1% [-6, +4] (n 389) | -1% [-2, +1] (n 3788) | -5% [-8, -1] (n 504) | 15 | -0.37 [-0.85, +0.23] |
| XAUUSD | model_h4_m30 (H4/M30/M1) | +1% [-5, +7] (n 197) | +0% [-2, +2] (n 1381) | -1% [-8, +5] (n 188) | 47 | +0.08 [-0.40, +0.67] |
| XAUUSD | model_h4_m3 (H4/M15/M3) | -0% [-5, +4] (n 440) | +0% [-1, +1] (n 4324) | -1% [-4, +2] (n 603) | 5 | -0.10 [-0.90, +0.69] |
| XAUUSD | w1_d1_h4 (W1/D1/H4) | -15% [-36, +10] (n 6) | -3% [-15, +10] (n 36) | +35% [+35, +35] (n 1) | 0 | – |
| XAUUSD | d1_h4_m15 (D1/H4/M15) | -1% [-13, +12] (n 47) | +3% [-2, +8] (n 198) | +3% [-15, +21] (n 17) | 7 | -0.80 [-1.00, -0.41] |
| XAUUSD | h1_m15_m1 (H1/M15/M1) | -2% [-5, +1] (n 691) | -1% [-3, +0] (n 2794) | -4% [-7, -0] (n 424) | 41 | -0.05 [-0.48, +0.43] |

## EURUSD

### model_d1: F D1, C H1, E M5

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 2607 | 2597 | 2610 | 4893 | 2413 |
| ARMED | 2415 | 2406 | 2419 | 4893 | 1587 |
| MANIPULATED | 269 | 270 | 271 | 2452 | 345 |
| REJECTED | 98 | 106 | 107 | 1176 | 148 |
| DISPLACED | 37 | 37 | 9 | 462 | 60 |
| IN_OTE | 7 | 10 | 0 | 62 | 6 |
| ENTERED | 5 | 8 | 0 | 48 | 6 |
| TP1 | 1 | 2 | 0 | 14 | 2 |
| SD_1 | 0 | 1 | 0 | 3 | 1 |
| SD_2 | 0 | 1 | 0 | 3 | 1 |
| SD_2.5 | 0 | 1 | 0 | 3 | 1 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 2338 | 2327 | 2339 | 2440 | 2068 |
| POI_FAILED | 26 | 27 | 27 | 0 | 34 |
| NO_REJECTION | 135 | 136 | 136 | 1149 | 146 |
| RETRACE_INVALID | 31 | 31 | 36 | 397 | 55 |
| MISSED | 26 | 13 | 8 | 318 | 42 |
| EXPIRED | 46 | 55 | 64 | 540 | 62 |
| STOPPED | 5 | 7 | 0 | 38 | 5 |
| HORIZON | 0 | 0 | 0 | 7 | 0 |
| TARGETS_DONE | 0 | 1 | 0 | 3 | 1 |
| UNFINISHED | 0 | 0 | 0 | 1 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 11% [9%, 13%] (n 2415) | 11% [9%, 13%] (n 2406) | 11% [9%, 13%] (n 2419) | 50% [49%, 51%] (n 4893) | 22% [19%, 24%] (n 1587) |
| REJECTED of MANIPULATED | 36% [32%, 41%] (n 269) | 39% [35%, 44%] (n 270) | 39% [35%, 44%] (n 271) | 48% [46%, 50%] (n 2452) | 43% [38%, 47%] (n 345) |
| DISPLACED of REJECTED | 28% [19%, 37%] (n 98) | 33% [24%, 43%] (n 106) | 7% [3%, 12%] (n 107) | 27% [25%, 29%] (n 1176) | 26% [20%, 33%] (n 148) |
| ENTERED of REJECTED and DISPLACED | 19% [4%, 32%] (n 27) | 23% [11%, 36%] (n 35) | 0% [0%, 0%] (n 8) | 15% [11%, 19%] (n 318) | 15% [5%, 26%] (n 39) |
| **Premise**: C1's opposite extreme before C2's extreme | 48% vs coin 52%: **-4% [-12%, 4%]** (n 96) | 52% vs coin 53%: **-1% [-9%, 7%]** (n 104) | 51% vs coin 53%: **-2% [-9%, 7%]** (n 105) | 52% vs coin 50%: **2% [0%, 5%]** (n 1058) | 50% vs coin 49%: **1% [-6%, 8%]** (n 135) |
| C2 had already reached C1's opposite extreme | 18% [11%, 26%] | 23% [15%, 31%] | 22% [14%, 30%] | 25% [22%, 27%] | 24% [17%, 31%] |
| TP1 before the stop | 20% [0%, 60%] (n 5) | 25% [0%, 62%] (n 8) | – (n 0) | 29% [16%, 44%] (n 48) | 33% [0%, 67%] (n 6) |
| -1 SD before the stop | 0% [0%, 0%] (n 5) | 12% [0%, 38%] (n 8) | – (n 0) | 6% [0%, 14%] (n 48) | 17% [0%, 50%] (n 6) |
| -2 SD before the stop | 0% [0%, 0%] (n 5) | 12% [0%, 38%] (n 8) | – (n 0) | 6% [0%, 14%] (n 48) | 17% [0%, 50%] (n 6) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 5) | 12% [0%, 38%] (n 8) | – (n 0) | 6% [0%, 14%] (n 48) | 17% [0%, 50%] (n 6) |
| R held to TP1 | -0.56 [-1.00, +0.33] (n 5) | -0.23 [-1.00, +0.76] (n 8) | – (n 0) | +0.05 [-0.41, +0.53] (n 48) | -0.29 [-1.00, +0.58] (n 6) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 5) | +0.14 [-1.00, +2.43] (n 8) | – (n 0) | -0.08 [-0.72, +0.71] (n 48) | +0.62 [-1.00, +3.86] (n 6) |


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

### model_h4: F H4, C M15, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 10452 | 10320 | 10421 | 20102 | 10108 |
| ARMED | 9751 | 9636 | 9720 | 20102 | 7226 |
| MANIPULATED | 1334 | 1314 | 1339 | 9858 | 1481 |
| REJECTED | 407 | 467 | 488 | 3987 | 542 |
| DISPLACED | 257 | 247 | 76 | 2510 | 327 |
| IN_OTE | 41 | 65 | 13 | 362 | 52 |
| ENTERED | 34 | 56 | 11 | 309 | 43 |
| TP1 | 6 | 14 | 4 | 62 | 5 |
| SD_1 | 1 | 4 | 0 | 24 | 0 |
| SD_2 | 1 | 4 | 0 | 10 | 0 |
| SD_2.5 | 1 | 3 | 0 | 6 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 9118 | 9006 | 9082 | 10244 | 8627 |
| POI_FAILED | 138 | 138 | 140 | 0 | 225 |
| NO_REJECTION | 667 | 668 | 686 | 4861 | 582 |
| RETRACE_INVALID | 115 | 116 | 137 | 1323 | 188 |
| MISSED | 183 | 107 | 48 | 1843 | 224 |
| EXPIRED | 197 | 229 | 317 | 1522 | 219 |
| STOPPED | 29 | 44 | 9 | 260 | 41 |
| HORIZON | 4 | 9 | 2 | 43 | 2 |
| TARGETS_DONE | 1 | 3 | 0 | 6 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [13%, 15%] (n 9751) | 14% [13%, 15%] (n 9636) | 14% [13%, 15%] (n 9720) | 49% [49%, 50%] (n 20102) | 20% [19%, 22%] (n 7226) |
| REJECTED of MANIPULATED | 31% [28%, 33%] (n 1334) | 36% [33%, 38%] (n 1314) | 36% [34%, 39%] (n 1339) | 40% [40%, 41%] (n 9858) | 37% [34%, 39%] (n 1481) |
| DISPLACED of REJECTED | 30% [26%, 35%] (n 407) | 40% [36%, 45%] (n 467) | 10% [7%, 12%] (n 488) | 36% [34%, 37%] (n 3987) | 35% [30%, 39%] (n 542) |
| ENTERED of REJECTED and DISPLACED | 27% [20%, 35%] (n 124) | 30% [24%, 36%] (n 189) | 23% [11%, 38%] (n 47) | 22% [19%, 24%] (n 1434) | 23% [17%, 29%] (n 187) |
| **Premise**: C1's opposite extreme before C2's extreme | 51% vs coin 49%: **2% [-3%, 6%]** (n 376) | 55% vs coin 52%: **3% [-1%, 7%]** (n 432) | 56% vs coin 53%: **3% [-1%, 7%]** (n 452) | 50% vs coin 48%: **1% [0%, 2%]** (n 3624) | 46% vs coin 48%: **-1% [-5%, 3%]** (n 493) |
| C2 had already reached C1's opposite extreme | 20% [16%, 24%] | 24% [19%, 28%] | 26% [22%, 29%] | 25% [24%, 27%] | 23% [19%, 27%] |
| TP1 before the stop | 18% [6%, 31%] (n 34) | 25% [14%, 37%] (n 56) | 36% [10%, 64%] (n 11) | 20% [16%, 24%] (n 309) | 12% [2%, 21%] (n 43) |
| -1 SD before the stop | 3% [0%, 9%] (n 34) | 7% [2%, 14%] (n 56) | 0% [0%, 0%] (n 11) | 8% [5%, 11%] (n 309) | 0% [0%, 0%] (n 43) |
| -2 SD before the stop | 3% [0%, 9%] (n 34) | 7% [2%, 14%] (n 56) | 0% [0%, 0%] (n 11) | 3% [1%, 5%] (n 309) | 0% [0%, 0%] (n 43) |
| -2.5 SD before the stop | 3% [0%, 9%] (n 34) | 5% [0%, 11%] (n 56) | 0% [0%, 0%] (n 11) | 2% [1%, 4%] (n 309) | 0% [0%, 0%] (n 43) |
| R held to TP1 | -0.31 [-0.69, +0.12] (n 34) | -0.05 [-0.42, +0.35] (n 56) | +0.20 [-0.37, +0.81] (n 11) | -0.21 [-0.38, -0.03] (n 309) | -0.55 [-0.85, -0.18] (n 43) |
| R held to -2 SD | -0.49 [-0.92, +0.18] (n 34) | +0.01 [-0.56, +0.68] (n 56) | -0.60 [-1.00, -0.00] (n 11) | -0.27 [-0.50, -0.02] (n 309) | -0.82 [-1.00, -0.51] (n 43) |


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

### model_h4_m30: F H4, C M30, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 5179 | 5083 | 5106 | 10536 | 5132 |
| ARMED | 4908 | 4814 | 4836 | 10536 | 3690 |
| MANIPULATED | 990 | 975 | 983 | 5185 | 815 |
| REJECTED | 253 | 311 | 354 | 1578 | 211 |
| DISPLACED | 354 | 342 | 134 | 2237 | 314 |
| IN_OTE | 38 | 66 | 19 | 244 | 32 |
| ENTERED | 34 | 57 | 15 | 206 | 22 |
| TP1 | 9 | 12 | 5 | 30 | 2 |
| SD_1 | 3 | 6 | 2 | 12 | 0 |
| SD_2 | 1 | 3 | 1 | 5 | 0 |
| SD_2.5 | 1 | 1 | 1 | 2 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 4189 | 4108 | 4123 | 5350 | 4317 |
| POI_FAILED | 153 | 160 | 161 | 0 | 155 |
| NO_REJECTION | 400 | 410 | 424 | 2344 | 273 |
| RETRACE_INVALID | 62 | 65 | 94 | 467 | 58 |
| MISSED | 276 | 193 | 87 | 1788 | 255 |
| EXPIRED | 65 | 90 | 202 | 380 | 52 |
| STOPPED | 27 | 40 | 13 | 169 | 21 |
| HORIZON | 6 | 16 | 1 | 35 | 1 |
| TARGETS_DONE | 1 | 1 | 1 | 2 | 0 |
| UNFINISHED | 0 | 0 | 0 | 1 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 20% [19%, 22%] (n 4908) | 20% [19%, 22%] (n 4814) | 20% [19%, 22%] (n 4836) | 49% [49%, 50%] (n 10536) | 22% [20%, 24%] (n 3690) |
| REJECTED of MANIPULATED | 26% [23%, 28%] (n 990) | 32% [29%, 35%] (n 975) | 36% [33%, 39%] (n 983) | 30% [29%, 32%] (n 5185) | 26% [23%, 29%] (n 815) |
| DISPLACED of REJECTED | 59% [53%, 65%] (n 253) | 67% [62%, 72%] (n 311) | 23% [19%, 27%] (n 354) | 56% [54%, 58%] (n 1578) | 61% [54%, 67%] (n 211) |
| ENTERED of REJECTED and DISPLACED | 23% [17%, 29%] (n 150) | 27% [22%, 33%] (n 209) | 18% [10%, 28%] (n 82) | 23% [21%, 26%] (n 886) | 17% [10%, 25%] (n 128) |
| **Premise**: C1's opposite extreme before C2's extreme | 54% vs coin 48%: **6% [1%, 11%]** (n 217) | 57% vs coin 51%: **6% [1%, 11%]** (n 265) | 61% vs coin 53%: **8% [3%, 11%]** (n 302) | 48% vs coin 46%: **1% [-1%, 4%]** (n 1280) | 48% vs coin 48%: **0% [-6%, 6%]** (n 178) |
| C2 had already reached C1's opposite extreme | 21% [16%, 26%] | 24% [20%, 29%] | 26% [22%, 31%] | 23% [21%, 25%] | 22% [16%, 28%] |
| TP1 before the stop | 26% [12%, 41%] (n 34) | 21% [10%, 32%] (n 57) | 33% [13%, 57%] (n 15) | 15% [9%, 20%] (n 206) | 9% [0%, 23%] (n 22) |
| -1 SD before the stop | 9% [0%, 21%] (n 34) | 11% [4%, 19%] (n 57) | 13% [0%, 36%] (n 15) | 6% [3%, 9%] (n 206) | 0% [0%, 0%] (n 22) |
| -2 SD before the stop | 3% [0%, 9%] (n 34) | 5% [0%, 12%] (n 57) | 7% [0%, 21%] (n 15) | 2% [0%, 5%] (n 206) | 0% [0%, 0%] (n 22) |
| -2.5 SD before the stop | 3% [0%, 9%] (n 34) | 2% [0%, 6%] (n 57) | 7% [0%, 21%] (n 15) | 1% [0%, 2%] (n 206) | 0% [0%, 0%] (n 22) |
| R held to TP1 | +0.53 [-0.22, +1.34] (n 34) | +0.50 [-0.10, +1.13] (n 57) | +0.80 [-0.48, +2.36] (n 15) | -0.14 [-0.37, +0.11] (n 206) | -0.76 [-1.00, -0.37] (n 22) |
| R held to -2 SD | -0.08 [-0.72, +0.76] (n 34) | +0.43 [-0.26, +1.24] (n 57) | +0.04 [-1.00, +1.72] (n 15) | -0.27 [-0.51, +0.01] (n 206) | -0.94 [-1.00, -0.82] (n 22) |


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

### model_h4_m3: F H4, C M15, E M3

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 10390 | 10382 | 10399 | 19650 | 10002 |
| ARMED | 9689 | 9681 | 9698 | 19650 | 7156 |
| MANIPULATED | 1333 | 1334 | 1339 | 9848 | 1509 |
| REJECTED | 499 | 506 | 507 | 4768 | 664 |
| DISPLACED | 62 | 62 | 13 | 604 | 96 |
| IN_OTE | 8 | 9 | 1 | 103 | 14 |
| ENTERED | 7 | 8 | 1 | 81 | 11 |
| TP1 | 2 | 3 | 0 | 33 | 3 |
| SD_1 | 0 | 0 | 0 | 6 | 1 |
| SD_2 | 0 | 0 | 0 | 4 | 1 |
| SD_2.5 | 0 | 0 | 0 | 3 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 9057 | 9048 | 9060 | 9802 | 8493 |
| POI_FAILED | 138 | 138 | 138 | 0 | 215 |
| NO_REJECTION | 687 | 688 | 691 | 4992 | 614 |
| RETRACE_INVALID | 144 | 146 | 147 | 1671 | 216 |
| MISSED | 41 | 10 | 11 | 371 | 62 |
| EXPIRED | 316 | 344 | 351 | 2732 | 391 |
| STOPPED | 6 | 6 | 1 | 64 | 7 |
| HORIZON | 1 | 2 | 0 | 14 | 4 |
| TARGETS_DONE | 0 | 0 | 0 | 3 | 0 |
| UNFINISHED | 0 | 0 | 0 | 1 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [13%, 15%] (n 9689) | 14% [13%, 15%] (n 9681) | 14% [13%, 15%] (n 9698) | 50% [50%, 51%] (n 19650) | 21% [20%, 23%] (n 7156) |
| REJECTED of MANIPULATED | 37% [35%, 40%] (n 1333) | 38% [35%, 40%] (n 1334) | 38% [35%, 40%] (n 1339) | 48% [47%, 49%] (n 9848) | 44% [42%, 46%] (n 1509) |
| DISPLACED of REJECTED | 10% [8%, 13%] (n 499) | 11% [9%, 14%] (n 506) | 2% [1%, 3%] (n 507) | 11% [10%, 12%] (n 4768) | 12% [9%, 15%] (n 664) |
| ENTERED of REJECTED and DISPLACED | 14% [4%, 25%] (n 50) | 14% [6%, 24%] (n 56) | 10% [0%, 30%] (n 10) | 16% [13%, 19%] (n 506) | 14% [7%, 21%] (n 80) |
| **Premise**: C1's opposite extreme before C2's extreme | 56% vs coin 53%: **3% [-0%, 7%]** (n 463) | 57% vs coin 53%: **3% [-0%, 7%]** (n 470) | 56% vs coin 53%: **3% [-0%, 7%]** (n 471) | 54% vs coin 52%: **3% [2%, 4%]** (n 4338) | 58% vs coin 54%: **4% [1%, 7%]** (n 612) |
| C2 had already reached C1's opposite extreme | 26% [22%, 29%] | 26% [23%, 30%] | 26% [23%, 30%] | 30% [28%, 31%] | 29% [26%, 32%] |
| TP1 before the stop | 29% [0%, 71%] (n 7) | 38% [12%, 75%] (n 8) | 0% [0%, 0%] (n 1) | 41% [31%, 51%] (n 81) | 27% [0%, 55%] (n 11) |
| -1 SD before the stop | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 1) | 7% [2%, 13%] (n 81) | 9% [0%, 27%] (n 11) |
| -2 SD before the stop | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 1) | 5% [1%, 10%] (n 81) | 9% [0%, 27%] (n 11) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 1) | 4% [0%, 8%] (n 81) | 0% [0%, 0%] (n 11) |
| R held to TP1 | -0.56 [-1.00, +0.04] (n 7) | -0.37 [-0.84, +0.27] (n 8) | -1.00 [-1.00, -1.00] (n 1) | -0.05 [-0.31, +0.23] (n 81) | -0.42 [-0.86, +0.11] (n 11) |
| R held to -2 SD | -0.88 [-1.00, -0.65] (n 7) | -0.66 [-1.00, -0.18] (n 8) | -1.00 [-1.00, -1.00] (n 1) | -0.05 [-0.48, +0.44] (n 81) | +0.09 [-0.92, +1.79] (n 11) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 60% vs 52%: 8% [2%, 14%] (n 217) | 2% [0%, 4%] (n 230) |
| True | 53% vs 54%: -1% [-6%, 4%] (n 246) | 1% [0%, 2%] (n 269) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 60% vs 50%: 10% [-21%, 41%] (n 5) | 0% [0%, 0%] (n 7) |
| None | 56% vs 53%: 3% [-1%, 7%] (n 458) | 1% [1%, 3%] (n 492) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 54% vs 43%: 11% [-4%, 29%] (n 13) | 0% [0%, 0%] (n 13) |
| FVG | 52% vs 53%: -0% [-13%, 14%] (n 40) | 2% [0%, 7%] (n 48) |
| OB | 61% vs 56%: 5% [-4%, 14%] (n 46) | 2% [0%, 6%] (n 55) |
| PDH | 63% vs 55%: 9% [-3%, 22%] (n 41) | 0% [0%, 0%] (n 41) |
| PMH | 0% vs 35%: -35% [-35%, -35%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | 50% vs 48%: 2% [-21%, 23%] (n 18) | 5% [0%, 17%] (n 20) |
| SWING_HIGH | 52% vs 55%: -4% [-13%, 6%] (n 60) | 0% [0%, 0%] (n 67) |
| previous H4 high | 57% vs 53%: 4% [-1%, 9%] (n 244) | 2% [0%, 3%] (n 254) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 57% vs 53%: 5% [-2%, 11%] (n 170) | 2% [0%, 4%] (n 182) |
| SHORT | 56% vs 53%: 2% [-2%, 8%] (n 293) | 1% [0%, 3%] (n 317) |

### w1_d1_h4: F W1, C D1, E H4

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 94 | 94 | 94 | 217 | 75 |
| ARMED | 93 | 93 | 93 | 217 | 46 |
| MANIPULATED | 25 | 25 | 25 | 93 | 12 |
| REJECTED | 7 | 7 | 7 | 37 | 5 |
| DISPLACED | 2 | 2 | 0 | 6 | 0 |
| IN_OTE | 0 | 0 | 0 | 0 | 0 |
| ENTERED | 0 | 0 | 0 | 0 | 0 |
| TP1 | 0 | 0 | 0 | 0 | 0 |
| SD_1 | 0 | 0 | 0 | 0 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 69 | 69 | 69 | 123 | 63 |
| POI_FAILED | 5 | 5 | 5 | 0 | 2 |
| NO_REJECTION | 12 | 12 | 12 | 55 | 5 |
| RETRACE_INVALID | 2 | 2 | 2 | 16 | 2 |
| MISSED | 2 | 0 | 0 | 4 | 0 |
| EXPIRED | 3 | 5 | 5 | 18 | 3 |
| UNFINISHED | 1 | 1 | 1 | 1 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 27% [18%, 35%] (n 93) | 27% [18%, 35%] (n 93) | 27% [18%, 35%] (n 93) | 43% [38%, 48%] (n 217) | 26% [13%, 39%] (n 46) |
| REJECTED of MANIPULATED | 28% [12%, 48%] (n 25) | 28% [12%, 48%] (n 25) | 28% [12%, 48%] (n 25) | 40% [30%, 50%] (n 93) | 42% [17%, 67%] (n 12) |
| DISPLACED of REJECTED | 29% [0%, 57%] (n 7) | 29% [0%, 57%] (n 7) | 0% [0%, 0%] (n 7) | 14% [3%, 25%] (n 37) | 0% [0%, 0%] (n 5) |
| ENTERED of REJECTED and DISPLACED | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 5) | – (n 0) |
| **Premise**: C1's opposite extreme before C2's extreme | 67% vs coin 43%: **24% [-10%, 56%]** (n 6) | 67% vs coin 43%: **24% [-10%, 56%]** (n 6) | 67% vs coin 43%: **24% [-10%, 56%]** (n 6) | 54% vs coin 47%: **7% [-11%, 26%]** (n 26) | 25% vs coin 41%: **-16% [-65%, 53%]** (n 4) |
| C2 had already reached C1's opposite extreme | 0% [0%, 0%] | 0% [0%, 0%] | 0% [0%, 0%] | 19% [6%, 34%] | 0% [0%, 0%] |
| TP1 before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| -1 SD before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| -2 SD before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| -2.5 SD before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| R held to TP1 | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| R held to -2 SD | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 0% vs 28%: -28% [-28%, -28%] (n 1) | 0% [0%, 0%] (n 2) |
| True | 80% vs 46%: 34% [-4%, 59%] (n 5) | 0% [0%, 0%] (n 5) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| None | 67% vs 43%: 24% [-10%, 56%] (n 6) | 0% [0%, 0%] (n 7) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| OB | 0% vs 28%: -28% [-28%, -28%] (n 1) | 0% [0%, 0%] (n 1) |
| SWING_HIGH | 100% vs 62%: 38% [38%, 38%] (n 1) | 0% [0%, 0%] (n 1) |
| previous W1 high | 75% vs 42%: 33% [-17%, 63%] (n 4) | 0% [0%, 0%] (n 5) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 100% vs 48%: 52% [52%, 52%] (n 1) | 0% [0%, 0%] (n 1) |
| SHORT | 60% vs 42%: 18% [-20%, 57%] (n 5) | 0% [0%, 0%] (n 6) |

### d1_h4_m15: F D1, C H4, E M15

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 634 | 629 | 635 | 1241 | 588 |
| ARMED | 610 | 605 | 611 | 1241 | 396 |
| MANIPULATED | 140 | 136 | 138 | 629 | 111 |
| REJECTED | 47 | 49 | 49 | 280 | 44 |
| DISPLACED | 32 | 31 | 8 | 162 | 28 |
| IN_OTE | 3 | 4 | 0 | 20 | 4 |
| ENTERED | 3 | 4 | 0 | 16 | 1 |
| TP1 | 1 | 2 | 0 | 4 | 1 |
| SD_1 | 0 | 0 | 0 | 2 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 494 | 493 | 497 | 611 | 477 |
| POI_FAILED | 36 | 34 | 36 | 0 | 23 |
| NO_REJECTION | 50 | 51 | 51 | 293 | 36 |
| RETRACE_INVALID | 9 | 10 | 13 | 100 | 12 |
| MISSED | 25 | 16 | 6 | 117 | 20 |
| EXPIRED | 17 | 21 | 32 | 102 | 19 |
| STOPPED | 2 | 4 | 0 | 12 | 1 |
| HORIZON | 1 | 0 | 0 | 4 | 0 |
| UNFINISHED | 0 | 0 | 0 | 2 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 23% [19%, 27%] (n 610) | 22% [18%, 26%] (n 605) | 23% [19%, 26%] (n 611) | 51% [49%, 53%] (n 1241) | 28% [23%, 33%] (n 396) |
| REJECTED of MANIPULATED | 34% [27%, 40%] (n 140) | 36% [29%, 43%] (n 136) | 36% [28%, 42%] (n 138) | 45% [41%, 48%] (n 629) | 40% [31%, 49%] (n 111) |
| DISPLACED of REJECTED | 51% [37%, 65%] (n 47) | 55% [41%, 68%] (n 49) | 10% [2%, 19%] (n 49) | 38% [32%, 43%] (n 280) | 45% [32%, 60%] (n 44) |
| ENTERED of REJECTED and DISPLACED | 12% [0%, 25%] (n 24) | 15% [4%, 30%] (n 27) | 0% [0%, 0%] (n 5) | 15% [9%, 21%] (n 106) | 5% [0%, 15%] (n 20) |
| **Premise**: C1's opposite extreme before C2's extreme | 69% vs coin 51%: **17% [4%, 30%]** (n 35) | 67% vs coin 51%: **16% [2%, 29%]** (n 36) | 65% vs coin 51%: **14% [-1%, 28%]** (n 37) | 56% vs coin 50%: **6% [0%, 11%]** (n 219) | 64% vs coin 59%: **5% [-8%, 19%]** (n 36) |
| C2 had already reached C1's opposite extreme | 23% [12%, 36%] | 27% [14%, 40%] | 24% [12%, 38%] | 32% [26%, 38%] | 32% [18%, 45%] |
| TP1 before the stop | 33% [0%, 100%] (n 3) | 50% [0%, 100%] (n 4) | – (n 0) | 25% [6%, 50%] (n 16) | 100% [100%, 100%] (n 1) |
| -1 SD before the stop | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 4) | – (n 0) | 12% [0%, 31%] (n 16) | 0% [0%, 0%] (n 1) |
| -2 SD before the stop | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 4) | – (n 0) | 0% [0%, 0%] (n 16) | 0% [0%, 0%] (n 1) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 4) | – (n 0) | 0% [0%, 0%] (n 16) | 0% [0%, 0%] (n 1) |
| R held to TP1 | +0.58 [-1.00, +2.32] (n 3) | +0.01 [-1.00, +1.01] (n 4) | – (n 0) | -0.06 [-0.60, +0.54] (n 16) | +0.41 [+0.41, +0.41] (n 1) |
| R held to -2 SD | +0.11 [-1.00, +2.32] (n 3) | -1.00 [-1.00, -1.00] (n 4) | – (n 0) | -0.20 [-0.90, +0.70] (n 16) | -1.00 [-1.00, -1.00] (n 1) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 61% vs 48%: 13% [-7%, 33%] (n 18) | 4% [0%, 13%] (n 23) |
| True | 76% vs 55%: 22% [5%, 37%] (n 17) | 8% [0%, 21%] (n 24) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 78% vs 56%: 22% [-10%, 48%] (n 9) | 15% [0%, 38%] (n 13) |
| None | 68% vs 51%: 17% [-0%, 33%] (n 22) | 3% [0%, 11%] (n 29) |
| TIGHT_RANGE | 50% vs 42%: 8% [-17%, 43%] (n 4) | 0% [0%, 0%] (n 5) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 0% vs 7%: -7% [-7%, -7%] (n 1) | 0% [0%, 0%] (n 1) |
| FVG | 100% vs 80%: 20% [20%, 20%] (n 1) | 0% [0%, 0%] (n 1) |
| OB | 0% vs 26%: -26% [-26%, -26%] (n 1) | 33% [0%, 100%] (n 3) |
| PWH | 17% vs 41%: -25% [-50%, 7%] (n 6) | 14% [0%, 43%] (n 7) |
| SWING_HIGH | 75% vs 30%: 45% [-36%, 82%] (n 4) | 0% [0%, 0%] (n 10) |
| previous D1 high | 86% vs 60%: 27% [15%, 38%] (n 22) | 4% [0%, 12%] (n 25) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 90% vs 61%: 29% [12%, 46%] (n 10) | 0% [0%, 0%] (n 15) |
| SHORT | 60% vs 47%: 13% [-5%, 29%] (n 25) | 9% [0%, 20%] (n 32) |

### h1_m15_m1: F H1, C M15, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 10121 | 9939 | 10040 | 20278 | 10149 |
| ARMED | 9557 | 9387 | 9486 | 20278 | 7394 |
| MANIPULATED | 2698 | 2672 | 2699 | 9949 | 1859 |
| REJECTED | 870 | 1006 | 1035 | 4016 | 655 |
| DISPLACED | 578 | 560 | 142 | 2527 | 411 |
| IN_OTE | 76 | 147 | 19 | 365 | 46 |
| ENTERED | 67 | 128 | 16 | 311 | 39 |
| TP1 | 16 | 30 | 4 | 55 | 7 |
| SD_1 | 1 | 3 | 0 | 11 | 1 |
| SD_2 | 0 | 1 | 0 | 2 | 0 |
| SD_2.5 | 0 | 1 | 0 | 1 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 7423 | 7267 | 7341 | 10329 | 8290 |
| POI_FAILED | 632 | 634 | 639 | 0 | 370 |
| NO_REJECTION | 955 | 972 | 984 | 4915 | 676 |
| RETRACE_INVALID | 254 | 253 | 300 | 1333 | 198 |
| MISSED | 403 | 217 | 90 | 1854 | 295 |
| EXPIRED | 387 | 468 | 670 | 1536 | 281 |
| STOPPED | 47 | 75 | 14 | 222 | 26 |
| HORIZON | 20 | 52 | 2 | 88 | 13 |
| TARGETS_DONE | 0 | 1 | 0 | 1 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 28% [27%, 29%] (n 9557) | 28% [28%, 29%] (n 9387) | 28% [28%, 29%] (n 9486) | 49% [49%, 50%] (n 20278) | 25% [24%, 26%] (n 7394) |
| REJECTED of MANIPULATED | 32% [31%, 34%] (n 2698) | 38% [36%, 39%] (n 2672) | 38% [37%, 40%] (n 2699) | 40% [39%, 41%] (n 9949) | 35% [33%, 37%] (n 1859) |
| DISPLACED of REJECTED | 36% [33%, 39%] (n 870) | 45% [42%, 48%] (n 1006) | 9% [7%, 10%] (n 1035) | 36% [34%, 37%] (n 4016) | 36% [32%, 40%] (n 655) |
| ENTERED of REJECTED and DISPLACED | 21% [17%, 26%] (n 313) | 28% [24%, 33%] (n 455) | 18% [10%, 26%] (n 90) | 22% [19%, 24%] (n 1442) | 17% [11%, 22%] (n 235) |
| **Premise**: C1's opposite extreme before C2's extreme | 49% vs coin 49%: **-0% [-4%, 3%]** (n 621) | 54% vs coin 52%: **2% [-1%, 5%]** (n 725) | 55% vs coin 53%: **2% [-1%, 5%]** (n 751) | 51% vs coin 50%: **1% [0%, 2%]** (n 2751) | 53% vs coin 52%: **1% [-2%, 5%]** (n 429) |
| C2 had already reached C1's opposite extreme | 20% [17%, 23%] | 24% [21%, 27%] | 25% [22%, 28%] | 25% [24%, 27%] | 23% [20%, 26%] |
| TP1 before the stop | 24% [14%, 34%] (n 67) | 23% [17%, 31%] (n 128) | 25% [6%, 47%] (n 16) | 18% [14%, 22%] (n 311) | 18% [6%, 31%] (n 39) |
| -1 SD before the stop | 1% [0%, 5%] (n 67) | 2% [0%, 5%] (n 128) | 0% [0%, 0%] (n 16) | 4% [2%, 6%] (n 311) | 3% [0%, 9%] (n 39) |
| -2 SD before the stop | 0% [0%, 0%] (n 67) | 1% [0%, 3%] (n 128) | 0% [0%, 0%] (n 16) | 1% [0%, 2%] (n 311) | 0% [0%, 0%] (n 39) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 67) | 1% [0%, 3%] (n 128) | 0% [0%, 0%] (n 16) | 0% [0%, 1%] (n 311) | 0% [0%, 0%] (n 39) |
| R held to TP1 | -0.14 [-0.43, +0.14] (n 67) | +0.04 [-0.14, +0.22] (n 128) | -0.28 [-0.73, +0.28] (n 16) | -0.17 [-0.33, -0.01] (n 311) | -0.09 [-0.52, +0.41] (n 39) |
| R held to -2 SD | -0.34 [-0.63, -0.04] (n 67) | +0.10 [-0.16, +0.36] (n 128) | -0.80 [-1.00, -0.47] (n 16) | -0.21 [-0.39, -0.02] (n 311) | -0.26 [-0.65, +0.29] (n 39) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 46% vs 49%: -3% [-9%, 2%] (n 234) | 7% [4%, 10%] (n 322) |
| True | 51% vs 49%: 2% [-2%, 6%] (n 387) | 8% [6%, 10%] (n 548) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 45% vs 46%: -1% [-8%, 6%] (n 154) | 11% [7%, 15%] (n 212) |
| None | 50% vs 50%: -0% [-4%, 4%] (n 457) | 7% [5%, 8%] (n 642) |
| TIGHT_RANGE | 60% vs 41%: 19% [-4%, 42%] (n 10) | 12% [0%, 29%] (n 16) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 57% vs 54%: 4% [-22%, 29%] (n 7) | 0% [0%, 0%] (n 21) |
| FVG | 54% vs 48%: 6% [-11%, 22%] (n 26) | 10% [2%, 19%] (n 50) |
| OB | 50% vs 49%: 1% [-9%, 10%] (n 38) | 8% [2%, 14%] (n 64) |
| PDH | 55% vs 50%: 5% [-11%, 22%] (n 20) | 7% [0%, 17%] (n 29) |
| PMH | 100% vs 27%: 73% [67%, 79%] (n 2) | 0% [0%, 0%] (n 3) |
| PWH | 43% vs 45%: -2% [-35%, 31%] (n 7) | 9% [0%, 27%] (n 11) |
| SWING_HIGH | 42% vs 46%: -4% [-17%, 9%] (n 52) | 8% [3%, 13%] (n 103) |
| previous H1 high | 49% vs 50%: -1% [-4%, 3%] (n 469) | 8% [6%, 10%] (n 589) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 47% vs 49%: -2% [-7%, 4%] (n 319) | 6% [4%, 8%] (n 441) |
| SHORT | 51% vs 49%: 2% [-3%, 7%] (n 302) | 10% [7%, 12%] (n 429) |

## GBPUSD

### model_d1: F D1, C H1, E M5

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 2528 | 2519 | 2519 | 4931 | 2345 |
| ARMED | 2395 | 2386 | 2386 | 4931 | 1506 |
| MANIPULATED | 323 | 321 | 322 | 2496 | 302 |
| REJECTED | 122 | 130 | 131 | 1142 | 120 |
| DISPLACED | 38 | 37 | 8 | 363 | 42 |
| IN_OTE | 2 | 7 | 1 | 47 | 4 |
| ENTERED | 2 | 5 | 1 | 40 | 4 |
| TP1 | 0 | 1 | 0 | 11 | 2 |
| SD_1 | 0 | 0 | 0 | 4 | 1 |
| SD_2 | 0 | 0 | 0 | 3 | 1 |
| SD_2.5 | 0 | 0 | 0 | 3 | 1 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 2204 | 2197 | 2196 | 2434 | 2043 |
| POI_FAILED | 23 | 23 | 23 | 0 | 39 |
| NO_REJECTION | 165 | 167 | 168 | 1244 | 127 |
| RETRACE_INVALID | 40 | 40 | 43 | 413 | 36 |
| MISSED | 30 | 12 | 6 | 258 | 29 |
| EXPIRED | 63 | 74 | 81 | 540 | 67 |
| STOPPED | 2 | 5 | 1 | 33 | 2 |
| HORIZON | 0 | 0 | 0 | 4 | 1 |
| TARGETS_DONE | 0 | 0 | 0 | 3 | 1 |
| UNFINISHED | 1 | 1 | 1 | 2 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 13% [11%, 16%] (n 2395) | 13% [11%, 16%] (n 2386) | 13% [11%, 16%] (n 2386) | 51% [50%, 52%] (n 4931) | 20% [18%, 23%] (n 1506) |
| REJECTED of MANIPULATED | 38% [34%, 42%] (n 323) | 40% [36%, 45%] (n 321) | 41% [36%, 45%] (n 322) | 46% [44%, 48%] (n 2496) | 40% [35%, 45%] (n 302) |
| DISPLACED of REJECTED | 18% [11%, 26%] (n 122) | 23% [17%, 31%] (n 130) | 6% [2%, 10%] (n 131) | 21% [19%, 24%] (n 1142) | 22% [14%, 29%] (n 120) |
| ENTERED of REJECTED and DISPLACED | 9% [0%, 22%] (n 22) | 17% [3%, 31%] (n 30) | 12% [0%, 38%] (n 8) | 17% [12%, 21%] (n 242) | 15% [4%, 30%] (n 26) |
| **Premise**: C1's opposite extreme before C2's extreme | 55% vs coin 47%: **8% [1%, 15%]** (n 111) | 57% vs coin 49%: **8% [1%, 15%]** (n 119) | 57% vs coin 49%: **8% [2%, 16%]** (n 120) | 51% vs coin 49%: **2% [-0%, 4%]** (n 1036) | 50% vs coin 53%: **-3% [-10%, 4%]** (n 111) |
| C2 had already reached C1's opposite extreme | 22% [16%, 29%] | 24% [17%, 30%] | 24% [17%, 30%] | 25% [22%, 28%] | 30% [22%, 39%] |
| TP1 before the stop | 0% [0%, 0%] (n 2) | 20% [0%, 60%] (n 5) | 0% [0%, 0%] (n 1) | 28% [15%, 40%] (n 40) | 50% [0%, 100%] (n 4) |
| -1 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 1) | 10% [2%, 20%] (n 40) | 25% [0%, 75%] (n 4) |
| -2 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 1) | 8% [0%, 16%] (n 40) | 25% [0%, 75%] (n 4) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 1) | 8% [0%, 16%] (n 40) | 25% [0%, 75%] (n 4) |
| R held to TP1 | -1.00 [-1.00, -1.00] (n 2) | -0.59 [-1.00, +0.23] (n 5) | -1.00 [-1.00, -1.00] (n 1) | -0.15 [-0.51, +0.24] (n 40) | +0.31 [-1.00, +1.81] (n 4) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 2) | -1.00 [-1.00, -1.00] (n 5) | -1.00 [-1.00, -1.00] (n 1) | -0.06 [-0.75, +0.80] (n 40) | +2.16 [-1.00, +6.23] (n 4) |


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

### model_h4: F H4, C M15, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 10323 | 10229 | 10292 | 19878 | 9857 |
| ARMED | 9681 | 9590 | 9651 | 19878 | 6964 |
| MANIPULATED | 1393 | 1374 | 1391 | 9758 | 1428 |
| REJECTED | 453 | 503 | 517 | 4243 | 575 |
| DISPLACED | 246 | 244 | 73 | 2240 | 285 |
| IN_OTE | 28 | 51 | 9 | 350 | 32 |
| ENTERED | 25 | 44 | 7 | 297 | 25 |
| TP1 | 7 | 13 | 3 | 77 | 7 |
| SD_1 | 4 | 6 | 2 | 33 | 5 |
| SD_2 | 1 | 2 | 1 | 11 | 3 |
| SD_2.5 | 1 | 2 | 1 | 8 | 2 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 8929 | 8854 | 8900 | 10120 | 8428 |
| POI_FAILED | 167 | 166 | 167 | 0 | 216 |
| NO_REJECTION | 676 | 675 | 693 | 4644 | 533 |
| RETRACE_INVALID | 143 | 145 | 165 | 1553 | 212 |
| MISSED | 175 | 103 | 40 | 1600 | 201 |
| EXPIRED | 207 | 241 | 319 | 1664 | 241 |
| STOPPED | 18 | 34 | 4 | 249 | 19 |
| HORIZON | 6 | 8 | 2 | 40 | 4 |
| TARGETS_DONE | 1 | 2 | 1 | 8 | 2 |
| UNFINISHED | 1 | 1 | 1 | 0 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [13%, 16%] (n 9681) | 14% [13%, 15%] (n 9590) | 14% [13%, 15%] (n 9651) | 49% [49%, 50%] (n 19878) | 21% [19%, 22%] (n 6964) |
| REJECTED of MANIPULATED | 33% [30%, 35%] (n 1393) | 37% [34%, 39%] (n 1374) | 37% [35%, 39%] (n 1391) | 43% [42%, 45%] (n 9758) | 40% [38%, 43%] (n 1428) |
| DISPLACED of REJECTED | 30% [26%, 34%] (n 453) | 38% [34%, 42%] (n 503) | 11% [8%, 14%] (n 517) | 31% [29%, 32%] (n 4243) | 29% [26%, 33%] (n 575) |
| ENTERED of REJECTED and DISPLACED | 18% [12%, 25%] (n 137) | 23% [17%, 29%] (n 192) | 12% [5%, 22%] (n 57) | 23% [21%, 25%] (n 1304) | 15% [10%, 21%] (n 167) |
| **Premise**: C1's opposite extreme before C2's extreme | 50% vs coin 51%: **-2% [-6%, 2%]** (n 424) | 54% vs coin 53%: **1% [-3%, 4%]** (n 469) | 54% vs coin 54%: **1% [-3%, 4%]** (n 483) | 48% vs coin 48%: **-1% [-2%, 1%]** (n 3866) | 49% vs coin 49%: **0% [-3%, 4%]** (n 528) |
| C2 had already reached C1's opposite extreme | 24% [20%, 28%] | 26% [22%, 30%] | 27% [24%, 31%] | 27% [25%, 28%] | 27% [23%, 31%] |
| TP1 before the stop | 28% [12%, 46%] (n 25) | 30% [16%, 44%] (n 44) | 43% [14%, 86%] (n 7) | 26% [21%, 31%] (n 297) | 28% [12%, 48%] (n 25) |
| -1 SD before the stop | 16% [4%, 32%] (n 25) | 14% [4%, 24%] (n 44) | 29% [0%, 57%] (n 7) | 11% [8%, 15%] (n 297) | 20% [4%, 37%] (n 25) |
| -2 SD before the stop | 4% [0%, 12%] (n 25) | 5% [0%, 12%] (n 44) | 14% [0%, 43%] (n 7) | 4% [2%, 6%] (n 297) | 12% [0%, 26%] (n 25) |
| -2.5 SD before the stop | 4% [0%, 12%] (n 25) | 5% [0%, 12%] (n 44) | 14% [0%, 43%] (n 7) | 3% [1%, 5%] (n 297) | 8% [0%, 21%] (n 25) |
| R held to TP1 | +0.07 [-0.48, +0.66] (n 25) | +0.08 [-0.37, +0.60] (n 44) | +0.55 [-0.54, +1.76] (n 7) | +0.04 [-0.16, +0.23] (n 297) | +0.10 [-0.50, +0.85] (n 25) |
| R held to -2 SD | -0.05 [-0.79, +0.90] (n 25) | -0.18 [-0.73, +0.54] (n 44) | +0.98 [-0.74, +3.69] (n 7) | -0.29 [-0.50, -0.07] (n 297) | +0.64 [-0.54, +2.16] (n 25) |


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

### model_h4_m30: F H4, C M30, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 5128 | 5066 | 5067 | 10325 | 4953 |
| ARMED | 4895 | 4836 | 4837 | 10325 | 3550 |
| MANIPULATED | 1015 | 1005 | 1017 | 5067 | 831 |
| REJECTED | 245 | 289 | 338 | 1703 | 235 |
| DISPLACED | 333 | 320 | 141 | 2093 | 318 |
| IN_OTE | 38 | 56 | 21 | 284 | 42 |
| ENTERED | 35 | 51 | 19 | 251 | 37 |
| TP1 | 9 | 17 | 5 | 51 | 12 |
| SD_1 | 7 | 9 | 2 | 23 | 4 |
| SD_2 | 3 | 5 | 1 | 12 | 1 |
| SD_2.5 | 2 | 3 | 0 | 8 | 1 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 4112 | 4060 | 4049 | 5257 | 4121 |
| POI_FAILED | 172 | 177 | 180 | 0 | 146 |
| NO_REJECTION | 425 | 441 | 456 | 2268 | 290 |
| RETRACE_INVALID | 64 | 67 | 89 | 555 | 63 |
| MISSED | 259 | 188 | 95 | 1597 | 240 |
| EXPIRED | 60 | 81 | 178 | 396 | 55 |
| STOPPED | 23 | 35 | 14 | 193 | 26 |
| HORIZON | 10 | 13 | 5 | 50 | 10 |
| TARGETS_DONE | 2 | 3 | 0 | 8 | 1 |
| UNFINISHED | 1 | 1 | 1 | 1 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 21% [19%, 22%] (n 4895) | 21% [20%, 22%] (n 4836) | 21% [20%, 22%] (n 4837) | 49% [48%, 50%] (n 10325) | 23% [22%, 25%] (n 3550) |
| REJECTED of MANIPULATED | 24% [22%, 27%] (n 1015) | 29% [26%, 32%] (n 1005) | 33% [30%, 36%] (n 1017) | 34% [32%, 35%] (n 5067) | 28% [25%, 32%] (n 831) |
| DISPLACED of REJECTED | 57% [50%, 63%] (n 245) | 63% [58%, 69%] (n 289) | 27% [23%, 33%] (n 338) | 53% [51%, 56%] (n 1703) | 59% [52%, 65%] (n 235) |
| ENTERED of REJECTED and DISPLACED | 25% [18%, 33%] (n 139) | 28% [21%, 34%] (n 183) | 21% [12%, 30%] (n 92) | 28% [25%, 31%] (n 907) | 27% [20%, 34%] (n 138) |
| **Premise**: C1's opposite extreme before C2's extreme | 50% vs coin 48%: **2% [-3%, 8%]** (n 203) | 54% vs coin 50%: **4% [-1%, 9%]** (n 241) | 56% vs coin 53%: **3% [-1%, 8%]** (n 286) | 46% vs coin 47%: **-1% [-3%, 1%]** (n 1403) | 52% vs coin 48%: **4% [-2%, 11%]** (n 189) |
| C2 had already reached C1's opposite extreme | 24% [19%, 30%] | 26% [21%, 31%] | 30% [25%, 35%] | 27% [24%, 30%] | 29% [24%, 35%] |
| TP1 before the stop | 26% [13%, 41%] (n 35) | 33% [20%, 47%] (n 51) | 26% [6%, 50%] (n 19) | 20% [15%, 25%] (n 251) | 32% [18%, 47%] (n 37) |
| -1 SD before the stop | 20% [8%, 35%] (n 35) | 18% [8%, 28%] (n 51) | 11% [0%, 28%] (n 19) | 9% [6%, 13%] (n 251) | 11% [2%, 22%] (n 37) |
| -2 SD before the stop | 9% [0%, 19%] (n 35) | 10% [2%, 18%] (n 51) | 5% [0%, 18%] (n 19) | 5% [2%, 8%] (n 251) | 3% [0%, 9%] (n 37) |
| -2.5 SD before the stop | 6% [0%, 15%] (n 35) | 6% [0%, 12%] (n 51) | 0% [0%, 0%] (n 19) | 3% [1%, 6%] (n 251) | 3% [0%, 9%] (n 37) |
| R held to TP1 | +0.31 [-0.38, +1.15] (n 35) | +0.57 [-0.03, +1.21] (n 51) | -0.08 [-0.77, +0.84] (n 19) | +0.02 [-0.21, +0.27] (n 251) | +0.46 [-0.18, +1.19] (n 37) |
| R held to -2 SD | +0.64 [-0.30, +1.71] (n 35) | +0.70 [-0.09, +1.59] (n 51) | +0.43 [-0.67, +1.83] (n 19) | +0.08 [-0.20, +0.41] (n 251) | +0.16 [-0.48, +0.98] (n 37) |


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

### model_h4_m3: F H4, C M15, E M3

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 10287 | 10295 | 10297 | 19502 | 9781 |
| ARMED | 9647 | 9655 | 9655 | 19502 | 6891 |
| MANIPULATED | 1391 | 1390 | 1390 | 9758 | 1473 |
| REJECTED | 524 | 529 | 529 | 4942 | 696 |
| DISPLACED | 53 | 53 | 13 | 529 | 71 |
| IN_OTE | 8 | 8 | 2 | 84 | 7 |
| ENTERED | 8 | 7 | 2 | 67 | 5 |
| TP1 | 4 | 2 | 0 | 32 | 3 |
| SD_1 | 2 | 0 | 0 | 7 | 2 |
| SD_2 | 1 | 0 | 0 | 3 | 0 |
| SD_2.5 | 1 | 0 | 0 | 3 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 8895 | 8904 | 8906 | 9744 | 8307 |
| POI_FAILED | 168 | 167 | 167 | 0 | 196 |
| NO_REJECTION | 693 | 694 | 694 | 4751 | 574 |
| RETRACE_INVALID | 166 | 167 | 172 | 1862 | 255 |
| MISSED | 35 | 8 | 9 | 329 | 41 |
| EXPIRED | 321 | 347 | 346 | 2748 | 402 |
| STOPPED | 6 | 7 | 2 | 58 | 4 |
| HORIZON | 1 | 0 | 0 | 6 | 1 |
| TARGETS_DONE | 1 | 0 | 0 | 3 | 0 |
| UNFINISHED | 1 | 1 | 1 | 1 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [13%, 16%] (n 9647) | 14% [13%, 15%] (n 9655) | 14% [13%, 15%] (n 9655) | 50% [49%, 51%] (n 19502) | 21% [20%, 23%] (n 6891) |
| REJECTED of MANIPULATED | 38% [35%, 40%] (n 1391) | 38% [36%, 40%] (n 1390) | 38% [36%, 40%] (n 1390) | 51% [50%, 52%] (n 9758) | 47% [45%, 50%] (n 1473) |
| DISPLACED of REJECTED | 9% [6%, 11%] (n 524) | 9% [7%, 12%] (n 529) | 2% [1%, 4%] (n 529) | 9% [8%, 10%] (n 4942) | 9% [7%, 11%] (n 696) |
| ENTERED of REJECTED and DISPLACED | 18% [7%, 29%] (n 45) | 14% [5%, 25%] (n 50) | 15% [0%, 38%] (n 13) | 15% [12%, 18%] (n 453) | 8% [2%, 16%] (n 61) |
| **Premise**: C1's opposite extreme before C2's extreme | 54% vs coin 54%: **0% [-3%, 4%]** (n 490) | 54% vs coin 54%: **1% [-3%, 4%]** (n 494) | 54% vs coin 54%: **1% [-3%, 4%]** (n 494) | 52% vs coin 51%: **0% [-1%, 2%]** (n 4497) | 53% vs coin 52%: **1% [-2%, 4%]** (n 626) |
| C2 had already reached C1's opposite extreme | 27% [23%, 31%] | 27% [23%, 31%] | 27% [23%, 31%] | 31% [29%, 32%] | 32% [28%, 35%] |
| TP1 before the stop | 50% [12%, 88%] (n 8) | 29% [0%, 57%] (n 7) | 0% [0%, 0%] (n 2) | 48% [35%, 60%] (n 67) | 60% [0%, 100%] (n 5) |
| -1 SD before the stop | 25% [0%, 50%] (n 8) | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 2) | 10% [4%, 18%] (n 67) | 40% [0%, 75%] (n 5) |
| -2 SD before the stop | 12% [0%, 38%] (n 8) | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 2) | 4% [0%, 11%] (n 67) | 0% [0%, 0%] (n 5) |
| -2.5 SD before the stop | 12% [0%, 38%] (n 8) | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 2) | 4% [0%, 11%] (n 67) | 0% [0%, 0%] (n 5) |
| R held to TP1 | -0.08 [-0.72, +0.63] (n 8) | -0.62 [-1.00, -0.16] (n 7) | -1.00 [-1.00, -1.00] (n 2) | +0.04 [-0.23, +0.33] (n 67) | +0.58 [-1.00, +1.64] (n 5) |
| R held to -2 SD | +0.34 [-1.00, +2.70] (n 8) | -1.00 [-1.00, -1.00] (n 7) | -1.00 [-1.00, -1.00] (n 2) | -0.31 [-0.75, +0.29] (n 67) | -0.17 [-1.00, +0.78] (n 5) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 55% vs 53%: 2% [-3%, 9%] (n 223) | 2% [0%, 4%] (n 234) |
| True | 53% vs 54%: -1% [-6%, 3%] (n 267) | 1% [0%, 2%] (n 290) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 64% vs 59%: 5% [-16%, 26%] (n 14) | 0% [0%, 0%] (n 15) |
| None | 54% vs 54%: 0% [-3%, 4%] (n 475) | 2% [1%, 3%] (n 508) |
| TIGHT_RANGE | 0% vs 6%: -6% [-6%, -6%] (n 1) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 65% vs 51%: 14% [2%, 32%] (n 17) | 0% [0%, 0%] (n 18) |
| FVG | 39% vs 51%: -12% [-26%, 4%] (n 36) | 0% [0%, 0%] (n 40) |
| OB | 51% vs 49%: 3% [-7%, 13%] (n 68) | 1% [0%, 4%] (n 75) |
| PDH | 50% vs 52%: -2% [-13%, 10%] (n 42) | 4% [0%, 12%] (n 46) |
| PMH | 43% vs 43%: 0% [-25%, 18%] (n 7) | 0% [0%, 0%] (n 7) |
| PWH | 62% vs 61%: 1% [-14%, 16%] (n 24) | 0% [0%, 0%] (n 27) |
| SWING_HIGH | 55% vs 54%: 1% [-10%, 12%] (n 60) | 1% [0%, 5%] (n 69) |
| previous H4 high | 56% vs 55%: 1% [-4%, 6%] (n 236) | 2% [0%, 4%] (n 242) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 56% vs 56%: -0% [-6%, 5%] (n 190) | 2% [0%, 4%] (n 206) |
| SHORT | 53% vs 52%: 1% [-4%, 6%] (n 300) | 1% [0%, 3%] (n 318) |

### w1_d1_h4: F W1, C D1, E H4

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 91 | 91 | 91 | 205 | 77 |
| ARMED | 88 | 88 | 88 | 205 | 43 |
| MANIPULATED | 29 | 29 | 29 | 105 | 13 |
| REJECTED | 9 | 9 | 9 | 49 | 4 |
| DISPLACED | 0 | 0 | 0 | 11 | 1 |
| IN_OTE | 0 | 0 | 0 | 0 | 0 |
| ENTERED | 0 | 0 | 0 | 0 | 0 |
| TP1 | 0 | 0 | 0 | 0 | 0 |
| SD_1 | 0 | 0 | 0 | 0 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 61 | 61 | 61 | 99 | 64 |
| POI_FAILED | 4 | 4 | 4 | 0 | 0 |
| NO_REJECTION | 16 | 16 | 16 | 54 | 9 |
| RETRACE_INVALID | 2 | 2 | 2 | 16 | 1 |
| MISSED | 0 | 0 | 0 | 5 | 0 |
| EXPIRED | 7 | 7 | 7 | 29 | 3 |
| UNFINISHED | 1 | 1 | 1 | 2 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 33% [23%, 43%] (n 88) | 33% [23%, 43%] (n 88) | 33% [23%, 43%] (n 88) | 51% [46%, 56%] (n 205) | 30% [19%, 44%] (n 43) |
| REJECTED of MANIPULATED | 31% [14%, 48%] (n 29) | 31% [14%, 48%] (n 29) | 31% [14%, 48%] (n 29) | 47% [37%, 57%] (n 105) | 31% [8%, 54%] (n 13) |
| DISPLACED of REJECTED | 0% [0%, 0%] (n 9) | 0% [0%, 0%] (n 9) | 0% [0%, 0%] (n 9) | 20% [10%, 32%] (n 49) | 25% [0%, 75%] (n 4) |
| ENTERED of REJECTED and DISPLACED | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 10) | 0% [0%, 0%] (n 1) |
| **Premise**: C1's opposite extreme before C2's extreme | 62% vs coin 66%: **-3% [-21%, 13%]** (n 8) | 62% vs coin 66%: **-3% [-21%, 13%]** (n 8) | 62% vs coin 66%: **-3% [-21%, 13%]** (n 8) | 66% vs coin 54%: **11% [-1%, 22%]** (n 32) | 75% vs coin 70%: **5% [-17%, 18%]** (n 4) |
| C2 had already reached C1's opposite extreme | 33% [0%, 67%] | 33% [0%, 67%] | 33% [0%, 67%] | 31% [15%, 46%] | 50% [0%, 100%] |
| TP1 before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| -1 SD before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| -2 SD before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| -2.5 SD before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| R held to TP1 | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| R held to -2 SD | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| True | 62% vs 66%: -3% [-21%, 13%] (n 8) | 0% [0%, 0%] (n 9) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 100% vs 89%: 11% [11%, 11%] (n 1) | 0% [0%, 0%] (n 1) |
| None | 57% vs 62%: -5% [-24%, 13%] (n 7) | 0% [0%, 0%] (n 8) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| OB | 0% vs 43%: -43% [-43%, -43%] (n 1) | 0% [0%, 0%] (n 1) |
| SWING_HIGH | 100% vs 63%: 37% [37%, 37%] (n 1) | 0% [0%, 0%] (n 1) |
| previous W1 high | 67% vs 70%: -3% [-16%, 7%] (n 6) | 0% [0%, 0%] (n 7) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 100% vs 89%: 11% [11%, 11%] (n 1) | 0% [0%, 0%] (n 2) |
| SHORT | 57% vs 62%: -5% [-24%, 13%] (n 7) | 0% [0%, 0%] (n 7) |

### d1_h4_m15: F D1, C H4, E M15

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 618 | 609 | 611 | 1280 | 581 |
| ARMED | 597 | 588 | 590 | 1280 | 388 |
| MANIPULATED | 161 | 158 | 160 | 653 | 98 |
| REJECTED | 48 | 53 | 56 | 245 | 34 |
| DISPLACED | 27 | 26 | 12 | 150 | 15 |
| IN_OTE | 2 | 6 | 1 | 12 | 1 |
| ENTERED | 1 | 3 | 1 | 8 | 1 |
| TP1 | 0 | 0 | 0 | 2 | 0 |
| SD_1 | 0 | 0 | 0 | 1 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 456 | 450 | 450 | 626 | 482 |
| POI_FAILED | 34 | 35 | 34 | 0 | 24 |
| NO_REJECTION | 68 | 67 | 68 | 337 | 34 |
| RETRACE_INVALID | 14 | 15 | 15 | 87 | 9 |
| MISSED | 23 | 12 | 9 | 112 | 10 |
| EXPIRED | 21 | 26 | 33 | 108 | 20 |
| STOPPED | 1 | 1 | 1 | 5 | 1 |
| HORIZON | 0 | 2 | 0 | 3 | 0 |
| UNFINISHED | 1 | 1 | 1 | 2 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 27% [23%, 31%] (n 597) | 27% [23%, 31%] (n 588) | 27% [23%, 31%] (n 590) | 51% [49%, 53%] (n 1280) | 25% [21%, 30%] (n 388) |
| REJECTED of MANIPULATED | 30% [23%, 37%] (n 161) | 34% [27%, 41%] (n 158) | 35% [28%, 42%] (n 160) | 38% [34%, 41%] (n 653) | 35% [25%, 45%] (n 98) |
| DISPLACED of REJECTED | 33% [20%, 46%] (n 48) | 42% [29%, 54%] (n 53) | 18% [8%, 28%] (n 56) | 32% [26%, 37%] (n 245) | 24% [10%, 38%] (n 34) |
| ENTERED of REJECTED and DISPLACED | 6% [0%, 19%] (n 16) | 14% [0%, 27%] (n 22) | 10% [0%, 30%] (n 10) | 10% [4%, 17%] (n 78) | 12% [0%, 38%] (n 8) |
| **Premise**: C1's opposite extreme before C2's extreme | 55% vs coin 52%: **3% [-9%, 17%]** (n 38) | 57% vs coin 54%: **3% [-10%, 17%]** (n 42) | 58% vs coin 54%: **3% [-9%, 16%]** (n 45) | 51% vs coin 51%: **-0% [-6%, 5%]** (n 185) | 67% vs coin 62%: **5% [-8%, 20%]** (n 24) |
| C2 had already reached C1's opposite extreme | 21% [11%, 31%] | 25% [14%, 36%] | 23% [13%, 34%] | 28% [22%, 35%] | 26% [12%, 40%] |
| TP1 before the stop | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 1) | 25% [0%, 50%] (n 8) | 0% [0%, 0%] (n 1) |
| -1 SD before the stop | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 1) | 12% [0%, 38%] (n 8) | 0% [0%, 0%] (n 1) |
| -2 SD before the stop | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 1) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 1) |
| R held to TP1 | -1.00 [-1.00, -1.00] (n 1) | -0.65 [-1.00, -0.46] (n 3) | -1.00 [-1.00, -1.00] (n 1) | +0.10 [-0.77, +1.33] (n 8) | -1.00 [-1.00, -1.00] (n 1) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 1) | -0.65 [-1.00, -0.46] (n 3) | -1.00 [-1.00, -1.00] (n 1) | -0.36 [-0.88, +0.42] (n 8) | -1.00 [-1.00, -1.00] (n 1) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 54% vs 50%: 4% [-13%, 21%] (n 26) | 3% [0%, 10%] (n 31) |
| True | 58% vs 56%: 2% [-22%, 26%] (n 12) | 0% [0%, 0%] (n 17) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 50% vs 57%: -7% [-36%, 22%] (n 8) | 0% [0%, 0%] (n 10) |
| None | 59% vs 52%: 7% [-9%, 23%] (n 29) | 3% [0%, 8%] (n 37) |
| TIGHT_RANGE | 0% vs 22%: -22% [-22%, -22%] (n 1) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |
| FVG | 100% vs 48%: 52% [52%, 52%] (n 1) | 0% [0%, 0%] (n 3) |
| OB | 50% vs 37%: 13% [-38%, 64%] (n 2) | 0% [0%, 0%] (n 3) |
| PMH | 100% vs 27%: 73% [67%, 79%] (n 2) | 0% [0%, 0%] (n 3) |
| PWH | 56% vs 58%: -3% [-25%, 19%] (n 9) | 0% [0%, 0%] (n 10) |
| SWING_HIGH | 50% vs 30%: 20% [-30%, 71%] (n 2) | 0% [0%, 0%] (n 4) |
| previous D1 high | 50% vs 55%: -5% [-22%, 12%] (n 22) | 4% [0%, 13%] (n 24) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 64% vs 65%: -0% [-23%, 22%] (n 14) | 0% [0%, 0%] (n 17) |
| SHORT | 50% vs 45%: 5% [-12%, 24%] (n 24) | 3% [0%, 10%] (n 31) |

### h1_m15_m1: F H1, C M15, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 9947 | 9818 | 9915 | 20048 | 9911 |
| ARMED | 9494 | 9378 | 9466 | 20048 | 7291 |
| MANIPULATED | 2747 | 2725 | 2751 | 9830 | 1779 |
| REJECTED | 935 | 1034 | 1061 | 4267 | 636 |
| DISPLACED | 531 | 525 | 148 | 2255 | 358 |
| IN_OTE | 80 | 148 | 20 | 352 | 49 |
| ENTERED | 74 | 121 | 16 | 299 | 46 |
| TP1 | 18 | 35 | 3 | 59 | 7 |
| SD_1 | 5 | 7 | 1 | 13 | 1 |
| SD_2 | 1 | 3 | 0 | 1 | 0 |
| SD_2.5 | 1 | 2 | 0 | 1 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 7199 | 7092 | 7163 | 10218 | 8131 |
| POI_FAILED | 635 | 642 | 647 | 0 | 333 |
| NO_REJECTION | 985 | 987 | 1004 | 4684 | 672 |
| RETRACE_INVALID | 281 | 281 | 322 | 1564 | 216 |
| MISSED | 361 | 204 | 90 | 1612 | 261 |
| EXPIRED | 411 | 490 | 672 | 1671 | 251 |
| STOPPED | 43 | 70 | 8 | 207 | 29 |
| HORIZON | 30 | 49 | 8 | 91 | 17 |
| TARGETS_DONE | 1 | 2 | 0 | 1 | 0 |
| UNFINISHED | 1 | 1 | 1 | 0 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 29% [28%, 30%] (n 9494) | 29% [28%, 30%] (n 9378) | 29% [28%, 30%] (n 9466) | 49% [48%, 50%] (n 20048) | 24% [23%, 26%] (n 7291) |
| REJECTED of MANIPULATED | 34% [32%, 36%] (n 2747) | 38% [36%, 40%] (n 2725) | 39% [37%, 40%] (n 2751) | 43% [42%, 45%] (n 9830) | 36% [34%, 38%] (n 1779) |
| DISPLACED of REJECTED | 33% [31%, 36%] (n 935) | 41% [38%, 43%] (n 1034) | 9% [8%, 11%] (n 1061) | 31% [29%, 32%] (n 4267) | 32% [28%, 36%] (n 636) |
| ENTERED of REJECTED and DISPLACED | 24% [19%, 29%] (n 312) | 29% [25%, 33%] (n 420) | 16% [10%, 23%] (n 100) | 23% [21%, 25%] (n 1310) | 23% [17%, 29%] (n 203) |
| **Premise**: C1's opposite extreme before C2's extreme | 49% vs coin 51%: **-3% [-6%, 0%]** (n 677) | 52% vs coin 54%: **-1% [-4%, 2%]** (n 745) | 54% vs coin 55%: **-1% [-4%, 2%]** (n 773) | 48% vs coin 50%: **-2% [-3%, -1%]** (n 2962) | 49% vs coin 51%: **-2% [-6%, 2%]** (n 429) |
| C2 had already reached C1's opposite extreme | 21% [18%, 23%] | 23% [21%, 26%] | 25% [22%, 27%] | 27% [25%, 28%] | 26% [23%, 29%] |
| TP1 before the stop | 24% [14%, 36%] (n 74) | 29% [21%, 38%] (n 121) | 19% [0%, 38%] (n 16) | 20% [15%, 24%] (n 299) | 15% [6%, 27%] (n 46) |
| -1 SD before the stop | 7% [1%, 14%] (n 74) | 6% [2%, 10%] (n 121) | 6% [0%, 19%] (n 16) | 4% [2%, 7%] (n 299) | 2% [0%, 7%] (n 46) |
| -2 SD before the stop | 1% [0%, 5%] (n 74) | 2% [0%, 6%] (n 121) | 0% [0%, 0%] (n 16) | 0% [0%, 1%] (n 299) | 0% [0%, 0%] (n 46) |
| -2.5 SD before the stop | 1% [0%, 5%] (n 74) | 2% [0%, 4%] (n 121) | 0% [0%, 0%] (n 16) | 0% [0%, 1%] (n 299) | 0% [0%, 0%] (n 46) |
| R held to TP1 | +0.32 [-0.07, +0.74] (n 74) | +0.27 [-0.02, +0.57] (n 121) | +0.36 [-0.40, +1.19] (n 16) | -0.01 [-0.17, +0.17] (n 299) | +0.03 [-0.39, +0.47] (n 46) |
| R held to -2 SD | +0.20 [-0.23, +0.66] (n 74) | +0.26 [-0.11, +0.65] (n 121) | +0.40 [-0.39, +1.31] (n 16) | -0.22 [-0.38, -0.05] (n 299) | -0.02 [-0.46, +0.51] (n 46) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 51% vs 52%: -0% [-6%, 5%] (n 261) | 8% [6%, 11%] (n 355) |
| True | 47% vs 51%: -4% [-8%, -0%] (n 416) | 8% [6%, 10%] (n 580) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 51% vs 54%: -3% [-8%, 3%] (n 189) | 9% [6%, 13%] (n 249) |
| None | 48% vs 50%: -2% [-6%, 2%] (n 479) | 8% [6%, 10%] (n 675) |
| TIGHT_RANGE | 56% vs 61%: -5% [-31%, 19%] (n 9) | 0% [0%, 0%] (n 11) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 31% vs 56%: -26% [-40%, -13%] (n 13) | 5% [0%, 14%] (n 22) |
| FVG | 28% vs 37%: -9% [-20%, 2%] (n 29) | 10% [4%, 18%] (n 59) |
| OB | 38% vs 47%: -9% [-24%, 6%] (n 21) | 11% [2%, 21%] (n 57) |
| PDH | 52% vs 55%: -4% [-19%, 9%] (n 31) | 10% [2%, 19%] (n 41) |
| PMH | 33% vs 51%: -18% [-33%, 14%] (n 3) | 0% [0%, 0%] (n 5) |
| PWH | 36% vs 57%: -21% [-35%, -8%] (n 14) | 11% [0%, 23%] (n 19) |
| SWING_HIGH | 65% vs 53%: 12% [1%, 22%] (n 52) | 2% [0%, 5%] (n 107) |
| previous H1 high | 50% vs 52%: -2% [-6%, 1%] (n 514) | 8% [6%, 11%] (n 625) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 50% vs 54%: -4% [-8%, 1%] (n 299) | 9% [6%, 12%] (n 401) |
| SHORT | 48% vs 50%: -2% [-6%, 3%] (n 378) | 7% [5%, 9%] (n 534) |

## USDJPY

### model_d1: F D1, C H1, E M5

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 2709 | 2703 | 2708 | 4870 | 2649 |
| ARMED | 2482 | 2476 | 2481 | 4870 | 1708 |
| MANIPULATED | 280 | 279 | 278 | 2493 | 337 |
| REJECTED | 100 | 106 | 108 | 1159 | 140 |
| DISPLACED | 38 | 37 | 14 | 458 | 66 |
| IN_OTE | 2 | 4 | 3 | 62 | 10 |
| ENTERED | 2 | 2 | 2 | 53 | 10 |
| TP1 | 0 | 0 | 0 | 18 | 3 |
| SD_1 | 0 | 0 | 0 | 4 | 1 |
| SD_2 | 0 | 0 | 0 | 1 | 0 |
| SD_2.5 | 0 | 0 | 0 | 1 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 2428 | 2423 | 2429 | 2376 | 2312 |
| POI_FAILED | 28 | 28 | 28 | 0 | 28 |
| NO_REJECTION | 139 | 140 | 139 | 1193 | 152 |
| RETRACE_INVALID | 29 | 32 | 33 | 403 | 40 |
| MISSED | 30 | 17 | 8 | 324 | 45 |
| EXPIRED | 52 | 60 | 68 | 519 | 61 |
| STOPPED | 1 | 1 | 2 | 43 | 8 |
| HORIZON | 1 | 1 | 0 | 9 | 2 |
| TARGETS_DONE | 0 | 0 | 0 | 1 | 0 |
| UNFINISHED | 1 | 1 | 1 | 2 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 11% [9%, 13%] (n 2482) | 11% [9%, 13%] (n 2476) | 11% [9%, 13%] (n 2481) | 51% [50%, 52%] (n 4870) | 20% [18%, 22%] (n 1708) |
| REJECTED of MANIPULATED | 36% [31%, 41%] (n 280) | 38% [33%, 43%] (n 279) | 39% [34%, 44%] (n 278) | 46% [45%, 48%] (n 2493) | 42% [36%, 47%] (n 337) |
| DISPLACED of REJECTED | 23% [15%, 32%] (n 100) | 28% [20%, 37%] (n 106) | 10% [5%, 16%] (n 108) | 27% [24%, 29%] (n 1159) | 34% [26%, 43%] (n 140) |
| ENTERED of REJECTED and DISPLACED | 9% [0%, 22%] (n 23) | 7% [0%, 17%] (n 30) | 18% [0%, 45%] (n 11) | 17% [13%, 22%] (n 311) | 21% [10%, 33%] (n 48) |
| **Premise**: C1's opposite extreme before C2's extreme | 52% vs coin 54%: **-2% [-10%, 7%]** (n 96) | 53% vs coin 54%: **-1% [-9%, 8%]** (n 101) | 52% vs coin 54%: **-1% [-10%, 7%]** (n 103) | 52% vs coin 50%: **1% [-1%, 3%]** (n 1060) | 50% vs coin 51%: **-1% [-7%, 6%]** (n 131) |
| C2 had already reached C1's opposite extreme | 23% [15%, 31%] | 25% [18%, 33%] | 25% [17%, 33%] | 28% [25%, 31%] | 26% [20%, 34%] |
| TP1 before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) | 34% [22%, 47%] (n 53) | 30% [0%, 60%] (n 10) |
| -1 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) | 8% [0%, 17%] (n 53) | 10% [0%, 30%] (n 10) |
| -2 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) | 2% [0%, 6%] (n 53) | 0% [0%, 0%] (n 10) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) | 2% [0%, 6%] (n 53) | 0% [0%, 0%] (n 10) |
| R held to TP1 | -0.06 [-1.00, +0.88] (n 2) | -0.06 [-1.00, +0.88] (n 2) | -1.00 [-1.00, -1.00] (n 2) | -0.13 [-0.45, +0.23] (n 53) | -0.05 [-0.81, +0.76] (n 10) |
| R held to -2 SD | -0.06 [-1.00, +0.88] (n 2) | -0.06 [-1.00, +0.88] (n 2) | -1.00 [-1.00, -1.00] (n 2) | -0.52 [-0.88, -0.04] (n 53) | -0.33 [-1.00, +0.63] (n 10) |


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

### model_h4: F H4, C M15, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 10327 | 10247 | 10333 | 20042 | 9960 |
| ARMED | 9701 | 9622 | 9708 | 20042 | 7100 |
| MANIPULATED | 1356 | 1334 | 1355 | 9877 | 1549 |
| REJECTED | 416 | 462 | 500 | 3994 | 553 |
| DISPLACED | 262 | 253 | 61 | 2473 | 342 |
| IN_OTE | 34 | 65 | 11 | 358 | 52 |
| ENTERED | 31 | 55 | 9 | 301 | 43 |
| TP1 | 18 | 22 | 5 | 93 | 21 |
| SD_1 | 6 | 7 | 4 | 44 | 7 |
| SD_2 | 4 | 3 | 3 | 24 | 4 |
| SD_2.5 | 4 | 3 | 3 | 16 | 2 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 8970 | 8912 | 8977 | 10165 | 8410 |
| POI_FAILED | 150 | 151 | 152 | 0 | 239 |
| NO_REJECTION | 682 | 678 | 690 | 4933 | 634 |
| RETRACE_INVALID | 139 | 136 | 160 | 1406 | 191 |
| MISSED | 191 | 110 | 34 | 1812 | 250 |
| EXPIRED | 163 | 204 | 310 | 1424 | 192 |
| STOPPED | 18 | 39 | 6 | 232 | 33 |
| HORIZON | 9 | 13 | 0 | 53 | 8 |
| TARGETS_DONE | 4 | 3 | 3 | 16 | 2 |
| UNFINISHED | 1 | 1 | 1 | 1 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [13%, 15%] (n 9701) | 14% [13%, 15%] (n 9622) | 14% [13%, 15%] (n 9708) | 49% [49%, 50%] (n 20042) | 22% [21%, 23%] (n 7100) |
| REJECTED of MANIPULATED | 31% [28%, 33%] (n 1356) | 35% [32%, 37%] (n 1334) | 37% [35%, 39%] (n 1355) | 40% [39%, 41%] (n 9877) | 36% [33%, 38%] (n 1549) |
| DISPLACED of REJECTED | 35% [30%, 40%] (n 416) | 42% [38%, 47%] (n 462) | 9% [7%, 12%] (n 500) | 36% [35%, 38%] (n 3994) | 38% [34%, 42%] (n 553) |
| ENTERED of REJECTED and DISPLACED | 22% [15%, 29%] (n 144) | 28% [22%, 35%] (n 195) | 20% [9%, 33%] (n 45) | 21% [19%, 22%] (n 1455) | 20% [15%, 26%] (n 210) |
| **Premise**: C1's opposite extreme before C2's extreme | 48% vs coin 48%: **0% [-4%, 5%]** (n 390) | 52% vs coin 51%: **1% [-4%, 5%]** (n 434) | 54% vs coin 52%: **1% [-3%, 6%]** (n 471) | 49% vs coin 48%: **1% [-0%, 2%]** (n 3656) | 48% vs coin 47%: **0% [-3%, 4%]** (n 513) |
| C2 had already reached C1's opposite extreme | 18% [14%, 22%] | 24% [19%, 28%] | 26% [22%, 30%] | 24% [22%, 25%] | 23% [19%, 26%] |
| TP1 before the stop | 58% [42%, 76%] (n 31) | 40% [27%, 53%] (n 55) | 56% [12%, 89%] (n 9) | 31% [26%, 36%] (n 301) | 49% [35%, 63%] (n 43) |
| -1 SD before the stop | 19% [4%, 36%] (n 31) | 13% [4%, 23%] (n 55) | 44% [0%, 80%] (n 9) | 15% [11%, 19%] (n 301) | 16% [5%, 30%] (n 43) |
| -2 SD before the stop | 13% [3%, 25%] (n 31) | 5% [0%, 12%] (n 55) | 33% [0%, 60%] (n 9) | 8% [5%, 11%] (n 301) | 9% [0%, 20%] (n 43) |
| -2.5 SD before the stop | 13% [3%, 25%] (n 31) | 5% [0%, 12%] (n 55) | 33% [0%, 60%] (n 9) | 5% [3%, 8%] (n 301) | 5% [0%, 11%] (n 43) |
| R held to TP1 | +1.23 [+0.53, +1.97] (n 31) | +0.50 [+0.07, +1.01] (n 55) | +0.82 [-0.65, +2.29] (n 9) | +0.17 [-0.02, +0.37] (n 301) | +0.64 [+0.16, +1.13] (n 43) |
| R held to -2 SD | +1.13 [+0.04, +2.31] (n 31) | +0.18 [-0.35, +0.84] (n 55) | +2.15 [-1.00, +4.99] (n 9) | +0.28 [-0.04, +0.61] (n 301) | +0.30 [-0.59, +1.38] (n 43) |


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

### model_h4_m30: F H4, C M30, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 5147 | 5065 | 5072 | 10417 | 5068 |
| ARMED | 4917 | 4835 | 4845 | 10417 | 3669 |
| MANIPULATED | 1011 | 992 | 1005 | 5194 | 871 |
| REJECTED | 244 | 303 | 356 | 1608 | 236 |
| DISPLACED | 380 | 357 | 142 | 2268 | 360 |
| IN_OTE | 47 | 86 | 26 | 292 | 35 |
| ENTERED | 42 | 77 | 22 | 255 | 32 |
| TP1 | 11 | 16 | 6 | 53 | 1 |
| SD_1 | 3 | 4 | 1 | 27 | 2 |
| SD_2 | 0 | 0 | 0 | 8 | 0 |
| SD_2.5 | 0 | 0 | 0 | 8 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 4135 | 4072 | 4066 | 5222 | 4196 |
| POI_FAILED | 163 | 171 | 172 | 0 | 152 |
| NO_REJECTION | 407 | 415 | 428 | 2395 | 299 |
| RETRACE_INVALID | 58 | 56 | 95 | 472 | 59 |
| MISSED | 295 | 213 | 100 | 1770 | 288 |
| EXPIRED | 46 | 60 | 188 | 302 | 41 |
| STOPPED | 35 | 61 | 19 | 198 | 25 |
| HORIZON | 7 | 16 | 3 | 49 | 7 |
| TARGETS_DONE | 0 | 0 | 0 | 8 | 0 |
| UNFINISHED | 1 | 1 | 1 | 1 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 21% [19%, 22%] (n 4917) | 21% [19%, 22%] (n 4835) | 21% [19%, 22%] (n 4845) | 50% [49%, 50%] (n 10417) | 24% [22%, 25%] (n 3669) |
| REJECTED of MANIPULATED | 24% [22%, 26%] (n 1011) | 31% [28%, 33%] (n 992) | 35% [33%, 38%] (n 1005) | 31% [30%, 32%] (n 5194) | 27% [24%, 30%] (n 871) |
| DISPLACED of REJECTED | 66% [60%, 71%] (n 244) | 73% [69%, 78%] (n 303) | 26% [21%, 30%] (n 356) | 60% [58%, 62%] (n 1608) | 66% [60%, 72%] (n 236) |
| ENTERED of REJECTED and DISPLACED | 26% [19%, 34%] (n 160) | 35% [28%, 41%] (n 222) | 24% [16%, 33%] (n 91) | 26% [24%, 29%] (n 968) | 21% [14%, 26%] (n 155) |
| **Premise**: C1's opposite extreme before C2's extreme | 42% vs coin 46%: **-4% [-9%, 2%]** (n 212) | 49% vs coin 50%: **-2% [-6%, 3%]** (n 263) | 54% vs coin 53%: **1% [-4%, 6%]** (n 313) | 46% vs coin 45%: **1% [-1%, 3%]** (n 1326) | 45% vs coin 49%: **-4% [-9%, 2%]** (n 186) |
| C2 had already reached C1's opposite extreme | 18% [14%, 24%] | 23% [19%, 28%] | 27% [22%, 31%] | 26% [24%, 29%] | 21% [16%, 26%] |
| TP1 before the stop | 26% [12%, 41%] (n 42) | 21% [12%, 30%] (n 77) | 27% [9%, 50%] (n 22) | 21% [16%, 26%] (n 255) | 3% [0%, 10%] (n 32) |
| -1 SD before the stop | 7% [0%, 15%] (n 42) | 5% [1%, 10%] (n 77) | 5% [0%, 13%] (n 22) | 11% [7%, 14%] (n 255) | 6% [0%, 17%] (n 32) |
| -2 SD before the stop | 0% [0%, 0%] (n 42) | 0% [0%, 0%] (n 77) | 0% [0%, 0%] (n 22) | 3% [1%, 5%] (n 255) | 0% [0%, 0%] (n 32) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 42) | 0% [0%, 0%] (n 77) | 0% [0%, 0%] (n 22) | 3% [1%, 5%] (n 255) | 0% [0%, 0%] (n 32) |
| R held to TP1 | +0.08 [-0.43, +0.61] (n 42) | -0.01 [-0.34, +0.33] (n 77) | -0.06 [-0.61, +0.59] (n 22) | +0.00 [-0.20, +0.22] (n 255) | -0.48 [-0.89, +0.08] (n 32) |
| R held to -2 SD | -0.43 [-0.81, +0.00] (n 42) | -0.31 [-0.61, +0.02] (n 77) | -0.69 [-1.00, -0.32] (n 22) | -0.04 [-0.33, +0.25] (n 255) | -0.43 [-0.89, +0.21] (n 32) |


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

### model_h4_m3: F H4, C M15, E M3

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 10340 | 10332 | 10340 | 19655 | 9950 |
| ARMED | 9715 | 9707 | 9715 | 19655 | 7076 |
| MANIPULATED | 1357 | 1352 | 1358 | 9898 | 1537 |
| REJECTED | 500 | 505 | 507 | 4778 | 671 |
| DISPLACED | 56 | 56 | 13 | 621 | 95 |
| IN_OTE | 7 | 8 | 3 | 95 | 12 |
| ENTERED | 7 | 7 | 3 | 78 | 9 |
| TP1 | 3 | 4 | 2 | 31 | 3 |
| SD_1 | 1 | 0 | 1 | 8 | 2 |
| SD_2 | 1 | 0 | 1 | 4 | 1 |
| SD_2.5 | 1 | 0 | 1 | 4 | 1 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 8982 | 8979 | 8981 | 9757 | 8412 |
| POI_FAILED | 153 | 154 | 154 | 0 | 215 |
| NO_REJECTION | 695 | 693 | 695 | 5035 | 634 |
| RETRACE_INVALID | 161 | 161 | 164 | 1732 | 230 |
| MISSED | 39 | 5 | 7 | 394 | 63 |
| EXPIRED | 302 | 332 | 335 | 2657 | 386 |
| STOPPED | 5 | 5 | 1 | 56 | 7 |
| HORIZON | 1 | 2 | 1 | 18 | 1 |
| TARGETS_DONE | 1 | 0 | 1 | 4 | 1 |
| UNFINISHED | 1 | 1 | 1 | 2 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [13%, 15%] (n 9715) | 14% [13%, 15%] (n 9707) | 14% [13%, 15%] (n 9715) | 50% [50%, 51%] (n 19655) | 22% [20%, 23%] (n 7076) |
| REJECTED of MANIPULATED | 37% [34%, 39%] (n 1357) | 37% [35%, 40%] (n 1352) | 37% [35%, 40%] (n 1358) | 48% [47%, 49%] (n 9898) | 44% [41%, 46%] (n 1537) |
| DISPLACED of REJECTED | 9% [6%, 12%] (n 500) | 11% [8%, 14%] (n 505) | 2% [1%, 4%] (n 507) | 11% [10%, 12%] (n 4778) | 12% [9%, 14%] (n 671) |
| ENTERED of REJECTED and DISPLACED | 16% [5%, 27%] (n 45) | 13% [5%, 21%] (n 54) | 27% [0%, 55%] (n 11) | 15% [11%, 18%] (n 531) | 12% [4%, 20%] (n 78) |
| **Premise**: C1's opposite extreme before C2's extreme | 53% vs coin 52%: **0% [-4%, 5%]** (n 471) | 54% vs coin 53%: **1% [-3%, 6%]** (n 476) | 53% vs coin 52%: **1% [-3%, 5%]** (n 478) | 54% vs coin 52%: **2% [1%, 3%]** (n 4402) | 53% vs coin 53%: **0% [-4%, 4%]** (n 611) |
| C2 had already reached C1's opposite extreme | 25% [21%, 29%] | 27% [22%, 31%] | 26% [22%, 30%] | 29% [28%, 31%] | 30% [27%, 34%] |
| TP1 before the stop | 43% [11%, 83%] (n 7) | 57% [14%, 86%] (n 7) | 67% [0%, 100%] (n 3) | 40% [30%, 51%] (n 78) | 33% [8%, 75%] (n 9) |
| -1 SD before the stop | 14% [0%, 50%] (n 7) | 0% [0%, 0%] (n 7) | 33% [0%, 100%] (n 3) | 10% [4%, 17%] (n 78) | 22% [0%, 50%] (n 9) |
| -2 SD before the stop | 14% [0%, 50%] (n 7) | 0% [0%, 0%] (n 7) | 33% [0%, 100%] (n 3) | 5% [1%, 11%] (n 78) | 11% [0%, 38%] (n 9) |
| -2.5 SD before the stop | 14% [0%, 50%] (n 7) | 0% [0%, 0%] (n 7) | 33% [0%, 100%] (n 3) | 5% [1%, 11%] (n 78) | 11% [0%, 38%] (n 9) |
| R held to TP1 | +0.01 [-0.86, +1.27] (n 7) | +0.18 [-0.47, +0.76] (n 7) | +0.74 [-1.00, +2.92] (n 3) | +0.02 [-0.23, +0.31] (n 78) | +0.25 [-0.82, +1.70] (n 9) |
| R held to -2 SD | +0.49 [-1.00, +3.50] (n 7) | -0.56 [-1.00, -0.04] (n 7) | +2.47 [-1.00, +7.99] (n 3) | +0.16 [-0.31, +0.71] (n 78) | +0.62 [-1.00, +3.07] (n 9) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 55% vs 50%: 5% [-1%, 10%] (n 218) | 1% [0%, 2%] (n 227) |
| True | 51% vs 54%: -3% [-8%, 2%] (n 253) | 2% [0%, 3%] (n 273) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 67% vs 53%: 14% [-20%, 47%] (n 6) | 0% [0%, 0%] (n 6) |
| None | 52% vs 52%: 0% [-4%, 4%] (n 464) | 1% [0%, 3%] (n 493) |
| TIGHT_RANGE | 100% vs 71%: 29% [29%, 29%] (n 1) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 77% vs 57%: 20% [-27%, 49%] (n 13) | 0% [0%, 0%] (n 14) |
| FVG | 59% vs 50%: 8% [-3%, 20%] (n 41) | 2% [0%, 9%] (n 43) |
| OB | 42% vs 51%: -9% [-21%, 4%] (n 50) | 4% [0%, 9%] (n 55) |
| PDH | 51% vs 50%: 1% [-9%, 13%] (n 51) | 2% [0%, 6%] (n 57) |
| PMH | 60% vs 57%: 3% [-37%, 44%] (n 5) | 0% [0%, 0%] (n 5) |
| PWH | 33% vs 46%: -13% [-34%, 10%] (n 9) | 0% [0%, 0%] (n 12) |
| SWING_HIGH | 53% vs 50%: 3% [-9%, 14%] (n 53) | 0% [0%, 0%] (n 56) |
| previous H4 high | 53% vs 54%: -0% [-5%, 4%] (n 249) | 1% [0%, 3%] (n 258) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 51% vs 54%: -3% [-8%, 3%] (n 224) | 1% [0%, 2%] (n 239) |
| SHORT | 54% vs 50%: 3% [-3%, 9%] (n 247) | 2% [0%, 4%] (n 261) |

### w1_d1_h4: F W1, C D1, E H4

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 99 | 99 | 100 | 200 | 101 |
| ARMED | 97 | 97 | 98 | 200 | 61 |
| MANIPULATED | 24 | 24 | 24 | 100 | 19 |
| REJECTED | 14 | 14 | 14 | 52 | 10 |
| DISPLACED | 4 | 4 | 0 | 11 | 1 |
| IN_OTE | 1 | 1 | 0 | 2 | 0 |
| ENTERED | 1 | 1 | 0 | 2 | 0 |
| TP1 | 0 | 0 | 0 | 0 | 0 |
| SD_1 | 0 | 0 | 0 | 0 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 75 | 75 | 76 | 99 | 81 |
| POI_FAILED | 3 | 3 | 3 | 0 | 4 |
| NO_REJECTION | 6 | 6 | 6 | 47 | 5 |
| RETRACE_INVALID | 3 | 3 | 3 | 16 | 5 |
| MISSED | 3 | 1 | 0 | 8 | 1 |
| EXPIRED | 7 | 9 | 11 | 26 | 4 |
| STOPPED | 1 | 1 | 0 | 2 | 0 |
| UNFINISHED | 1 | 1 | 1 | 2 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 25% [16%, 34%] (n 97) | 25% [16%, 34%] (n 97) | 24% [16%, 33%] (n 98) | 50% [44%, 56%] (n 200) | 31% [20%, 43%] (n 61) |
| REJECTED of MANIPULATED | 58% [38%, 75%] (n 24) | 58% [38%, 75%] (n 24) | 58% [38%, 75%] (n 24) | 52% [42%, 61%] (n 100) | 53% [32%, 74%] (n 19) |
| DISPLACED of REJECTED | 29% [7%, 57%] (n 14) | 29% [7%, 57%] (n 14) | 0% [0%, 0%] (n 14) | 21% [11%, 33%] (n 52) | 10% [0%, 30%] (n 10) |
| ENTERED of REJECTED and DISPLACED | 25% [0%, 75%] (n 4) | 25% [0%, 75%] (n 4) | – (n 0) | 18% [0%, 45%] (n 11) | 0% [0%, 0%] (n 1) |
| **Premise**: C1's opposite extreme before C2's extreme | 40% vs coin 60%: **-20% [-50%, 12%]** (n 10) | 40% vs coin 60%: **-20% [-50%, 12%]** (n 10) | 40% vs coin 60%: **-20% [-50%, 12%]** (n 10) | 54% vs coin 58%: **-4% [-16%, 7%]** (n 39) | 50% vs coin 60%: **-10% [-35%, 15%]** (n 8) |
| C2 had already reached C1's opposite extreme | 21% [0%, 43%] | 21% [0%, 43%] | 21% [0%, 43%] | 27% [12%, 41%] | 30% [0%, 60%] |
| TP1 before the stop | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) |
| -1 SD before the stop | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) |
| -2 SD before the stop | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) |
| R held to TP1 | -1.00 [-1.00, -1.00] (n 1) | -1.00 [-1.00, -1.00] (n 1) | – (n 0) | -1.00 [-1.00, -1.00] (n 2) | – (n 0) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 1) | -1.00 [-1.00, -1.00] (n 1) | – (n 0) | -1.00 [-1.00, -1.00] (n 2) | – (n 0) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | – vs –: – (n 0) | 0% [0%, 0%] (n 4) |
| True | 40% vs 60%: -20% [-50%, 12%] (n 10) | 10% [0%, 30%] (n 10) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| None | 40% vs 60%: -20% [-50%, 12%] (n 10) | 7% [0%, 21%] (n 14) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | – vs –: – (n 0) | 0% [0%, 0%] (n 3) |
| OB | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |
| PMH | 100% vs 19%: 81% [81%, 81%] (n 1) | 0% [0%, 0%] (n 1) |
| SWING_HIGH | 100% vs 76%: 24% [24%, 24%] (n 1) | 0% [0%, 0%] (n 1) |
| previous W1 high | 25% vs 63%: -38% [-62%, -11%] (n 8) | 12% [0%, 38%] (n 8) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 25% vs 64%: -39% [-61%, -14%] (n 8) | 9% [0%, 27%] (n 11) |
| SHORT | 100% vs 42%: 58% [35%, 81%] (n 2) | 0% [0%, 0%] (n 3) |

### d1_h4_m15: F D1, C H4, E M15

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 660 | 648 | 653 | 1253 | 660 |
| ARMED | 629 | 617 | 622 | 1253 | 456 |
| MANIPULATED | 147 | 146 | 148 | 634 | 104 |
| REJECTED | 49 | 58 | 57 | 262 | 36 |
| DISPLACED | 30 | 30 | 10 | 147 | 20 |
| IN_OTE | 4 | 8 | 1 | 19 | 2 |
| ENTERED | 4 | 8 | 1 | 18 | 2 |
| TP1 | 0 | 1 | 0 | 3 | 1 |
| SD_1 | 0 | 0 | 0 | 1 | 1 |
| SD_2 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 512 | 501 | 504 | 619 | 556 |
| POI_FAILED | 33 | 32 | 33 | 0 | 18 |
| NO_REJECTION | 55 | 55 | 55 | 311 | 43 |
| RETRACE_INVALID | 14 | 14 | 17 | 89 | 12 |
| MISSED | 20 | 14 | 7 | 103 | 15 |
| EXPIRED | 21 | 23 | 35 | 112 | 13 |
| STOPPED | 3 | 5 | 1 | 10 | 0 |
| HORIZON | 1 | 3 | 0 | 8 | 2 |
| UNFINISHED | 1 | 1 | 1 | 1 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 23% [20%, 27%] (n 629) | 24% [20%, 28%] (n 617) | 24% [20%, 28%] (n 622) | 51% [49%, 53%] (n 1253) | 23% [19%, 27%] (n 456) |
| REJECTED of MANIPULATED | 33% [26%, 42%] (n 147) | 40% [32%, 48%] (n 146) | 39% [30%, 47%] (n 148) | 41% [38%, 45%] (n 634) | 35% [26%, 43%] (n 104) |
| DISPLACED of REJECTED | 41% [27%, 55%] (n 49) | 50% [37%, 64%] (n 58) | 12% [5%, 21%] (n 57) | 33% [28%, 38%] (n 262) | 39% [23%, 54%] (n 36) |
| ENTERED of REJECTED and DISPLACED | 20% [5%, 42%] (n 20) | 28% [10%, 45%] (n 29) | 14% [0%, 43%] (n 7) | 21% [12%, 29%] (n 86) | 14% [0%, 31%] (n 14) |
| **Premise**: C1's opposite extreme before C2's extreme | 50% vs coin 61%: **-11% [-26%, 4%]** (n 32) | 56% vs coin 61%: **-5% [-19%, 8%]** (n 41) | 57% vs coin 61%: **-3% [-16%, 10%]** (n 40) | 51% vs coin 54%: **-3% [-8%, 3%]** (n 187) | 41% vs coin 50%: **-9% [-24%, 8%]** (n 22) |
| C2 had already reached C1's opposite extreme | 27% [15%, 39%] | 34% [23%, 47%] | 33% [21%, 46%] | 30% [24%, 36%] | 19% [8%, 34%] |
| TP1 before the stop | 0% [0%, 0%] (n 4) | 12% [0%, 30%] (n 8) | 0% [0%, 0%] (n 1) | 17% [0%, 35%] (n 18) | 50% [0%, 100%] (n 2) |
| -1 SD before the stop | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 1) | 6% [0%, 18%] (n 18) | 50% [0%, 100%] (n 2) |
| -2 SD before the stop | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 18) | 0% [0%, 0%] (n 2) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 18) | 0% [0%, 0%] (n 2) |
| R held to TP1 | -0.46 [-1.00, +0.62] (n 4) | -0.46 [-0.90, +0.05] (n 8) | -1.00 [-1.00, -1.00] (n 1) | +0.11 [-0.50, +0.74] (n 18) | +1.20 [+0.11, +2.28] (n 2) |
| R held to -2 SD | -0.46 [-1.00, +0.62] (n 4) | -0.25 [-0.90, +0.37] (n 8) | -1.00 [-1.00, -1.00] (n 1) | +0.21 [-0.45, +0.86] (n 18) | +1.35 [+0.11, +2.58] (n 2) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 50% vs 65%: -15% [-31%, 2%] (n 20) | 7% [0%, 19%] (n 28) |
| True | 50% vs 53%: -3% [-27%, 21%] (n 12) | 10% [0%, 24%] (n 21) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 43% vs 61%: -18% [-41%, 9%] (n 7) | 10% [0%, 33%] (n 10) |
| None | 50% vs 59%: -9% [-30%, 10%] (n 22) | 8% [0%, 19%] (n 36) |
| TIGHT_RANGE | 67% vs 72%: -5% [-20%, 4%] (n 3) | 0% [0%, 0%] (n 3) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | – vs –: – (n 0) | 0% [0%, 0%] (n 2) |
| FVG | 50% vs 50%: 0% [-79%, 58%] (n 4) | 0% [0%, 0%] (n 5) |
| OB | – vs –: – (n 0) | 0% [0%, 0%] (n 2) |
| PMH | 0% vs 42%: -42% [-42%, -42%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | 57% vs 63%: -6% [-31%, 27%] (n 7) | 9% [0%, 33%] (n 11) |
| SWING_HIGH | 0% vs 42%: -42% [-61%, -20%] (n 3) | 12% [0%, 38%] (n 8) |
| previous D1 high | 59% vs 67%: -8% [-26%, 9%] (n 17) | 10% [0%, 25%] (n 20) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 54% vs 61%: -7% [-26%, 12%] (n 24) | 6% [0%, 14%] (n 36) |
| SHORT | 38% vs 61%: -23% [-41%, -5%] (n 8) | 15% [0%, 38%] (n 13) |

### h1_m15_m1: F H1, C M15, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 10217 | 10089 | 10159 | 20233 | 10340 |
| ARMED | 9664 | 9541 | 9605 | 20233 | 7470 |
| MANIPULATED | 2788 | 2755 | 2789 | 9966 | 1889 |
| REJECTED | 916 | 1007 | 1051 | 4040 | 605 |
| DISPLACED | 551 | 535 | 145 | 2501 | 375 |
| IN_OTE | 78 | 147 | 18 | 362 | 53 |
| ENTERED | 66 | 122 | 14 | 304 | 48 |
| TP1 | 17 | 31 | 5 | 73 | 10 |
| SD_1 | 4 | 7 | 3 | 19 | 4 |
| SD_2 | 1 | 2 | 1 | 7 | 2 |
| SD_2.5 | 1 | 2 | 1 | 2 | 1 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 7428 | 7333 | 7369 | 10267 | 8450 |
| POI_FAILED | 695 | 690 | 703 | 0 | 393 |
| NO_REJECTION | 983 | 984 | 998 | 4965 | 740 |
| RETRACE_INVALID | 286 | 286 | 334 | 1422 | 205 |
| MISSED | 390 | 216 | 97 | 1835 | 275 |
| EXPIRED | 368 | 457 | 643 | 1439 | 228 |
| STOPPED | 37 | 69 | 6 | 195 | 30 |
| HORIZON | 28 | 51 | 7 | 107 | 17 |
| TARGETS_DONE | 1 | 2 | 1 | 2 | 1 |
| UNFINISHED | 1 | 1 | 1 | 1 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 29% [28%, 30%] (n 9664) | 29% [28%, 30%] (n 9541) | 29% [28%, 30%] (n 9605) | 49% [49%, 50%] (n 20233) | 25% [24%, 27%] (n 7470) |
| REJECTED of MANIPULATED | 33% [31%, 35%] (n 2788) | 37% [35%, 38%] (n 2755) | 38% [36%, 40%] (n 2789) | 41% [40%, 42%] (n 9966) | 32% [30%, 34%] (n 1889) |
| DISPLACED of REJECTED | 37% [34%, 40%] (n 916) | 42% [39%, 46%] (n 1007) | 10% [8%, 12%] (n 1051) | 36% [35%, 38%] (n 4040) | 35% [31%, 40%] (n 605) |
| ENTERED of REJECTED and DISPLACED | 20% [16%, 24%] (n 336) | 29% [25%, 32%] (n 427) | 13% [7%, 20%] (n 105) | 21% [19%, 22%] (n 1472) | 22% [17%, 28%] (n 214) |
| **Premise**: C1's opposite extreme before C2's extreme | 51% vs coin 50%: **1% [-2%, 4%]** (n 694) | 55% vs coin 52%: **2% [-1%, 5%]** (n 773) | 56% vs coin 53%: **3% [0%, 6%]** (n 808) | 50% vs coin 49%: **0% [-1%, 1%]** (n 2791) | 50% vs coin 50%: **-0% [-4%, 4%]** (n 413) |
| C2 had already reached C1's opposite extreme | 21% [18%, 24%] | 25% [22%, 27%] | 26% [23%, 29%] | 24% [22%, 25%] | 20% [17%, 24%] |
| TP1 before the stop | 26% [16%, 35%] (n 66) | 25% [18%, 33%] (n 122) | 36% [14%, 57%] (n 14) | 24% [19%, 29%] (n 304) | 21% [11%, 32%] (n 48) |
| -1 SD before the stop | 6% [1%, 12%] (n 66) | 6% [2%, 11%] (n 122) | 21% [0%, 43%] (n 14) | 6% [4%, 9%] (n 304) | 8% [2%, 16%] (n 48) |
| -2 SD before the stop | 2% [0%, 5%] (n 66) | 2% [0%, 4%] (n 122) | 7% [0%, 23%] (n 14) | 2% [1%, 4%] (n 304) | 4% [0%, 11%] (n 48) |
| -2.5 SD before the stop | 2% [0%, 5%] (n 66) | 2% [0%, 4%] (n 122) | 7% [0%, 23%] (n 14) | 1% [0%, 2%] (n 304) | 2% [0%, 7%] (n 48) |
| R held to TP1 | +0.24 [-0.13, +0.64] (n 66) | +0.23 [-0.04, +0.52] (n 122) | +0.57 [-0.44, +1.62] (n 14) | +0.09 [-0.08, +0.26] (n 304) | -0.03 [-0.41, +0.39] (n 48) |
| R held to -2 SD | +0.41 [-0.07, +0.97] (n 66) | +0.27 [-0.07, +0.64] (n 122) | +1.22 [-0.26, +2.80] (n 14) | +0.17 [-0.06, +0.41] (n 304) | +0.26 [-0.32, +0.94] (n 48) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 48% vs 46%: 1% [-4%, 6%] (n 235) | 6% [4%, 8%] (n 321) |
| True | 53% vs 52%: 1% [-3%, 5%] (n 459) | 8% [6%, 10%] (n 595) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 51% vs 48%: 3% [-4%, 10%] (n 174) | 7% [4%, 10%] (n 234) |
| None | 50% vs 50%: -0% [-4%, 4%] (n 513) | 7% [5%, 9%] (n 671) |
| TIGHT_RANGE | 100% vs 54%: 46% [29%, 63%] (n 7) | 9% [0%, 27%] (n 11) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 44% vs 41%: 4% [-24%, 33%] (n 9) | 9% [0%, 22%] (n 23) |
| FVG | 45% vs 47%: -1% [-16%, 13%] (n 31) | 4% [0%, 10%] (n 51) |
| OB | 46% vs 48%: -1% [-13%, 10%] (n 41) | 6% [1%, 12%] (n 66) |
| PDH | 43% vs 44%: -0% [-12%, 12%] (n 37) | 8% [2%, 17%] (n 49) |
| PMH | 50% vs 32%: 18% [-11%, 65%] (n 4) | 0% [0%, 0%] (n 6) |
| PWH | 60% vs 52%: 8% [-17%, 31%] (n 10) | 0% [0%, 0%] (n 10) |
| SWING_HIGH | 45% vs 46%: -2% [-12%, 10%] (n 56) | 8% [4%, 13%] (n 110) |
| previous H1 high | 53% vs 51%: 1% [-2%, 6%] (n 506) | 7% [5%, 10%] (n 601) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 53% vs 51%: 2% [-3%, 6%] (n 336) | 5% [3%, 8%] (n 441) |
| SHORT | 49% vs 49%: 0% [-4%, 5%] (n 358) | 9% [7%, 11%] (n 475) |

## XAUUSD

### model_d1: F D1, C H1, E M5

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 2145 | 2134 | 2143 | 4681 | 1974 |
| ARMED | 2012 | 2001 | 2010 | 4681 | 1181 |
| MANIPULATED | 291 | 289 | 291 | 2362 | 217 |
| REJECTED | 103 | 110 | 114 | 1087 | 99 |
| DISPLACED | 44 | 41 | 14 | 378 | 37 |
| IN_OTE | 5 | 11 | 1 | 52 | 2 |
| ENTERED | 5 | 9 | 1 | 44 | 2 |
| TP1 | 3 | 4 | 1 | 12 | 0 |
| SD_1 | 1 | 2 | 0 | 3 | 0 |
| SD_2 | 0 | 1 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 1853 | 1844 | 1851 | 2317 | 1756 |
| POI_FAILED | 30 | 29 | 29 | 0 | 21 |
| NO_REJECTION | 145 | 147 | 148 | 1148 | 86 |
| RETRACE_INVALID | 25 | 26 | 32 | 377 | 33 |
| MISSED | 32 | 16 | 8 | 279 | 31 |
| EXPIRED | 54 | 62 | 73 | 514 | 44 |
| STOPPED | 5 | 8 | 1 | 41 | 2 |
| HORIZON | 0 | 1 | 0 | 3 | 0 |
| UNFINISHED | 1 | 1 | 1 | 2 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [12%, 18%] (n 2012) | 14% [12%, 18%] (n 2001) | 14% [12%, 18%] (n 2010) | 50% [49%, 52%] (n 4681) | 18% [16%, 21%] (n 1181) |
| REJECTED of MANIPULATED | 35% [30%, 40%] (n 291) | 38% [33%, 43%] (n 289) | 39% [34%, 44%] (n 291) | 46% [44%, 48%] (n 2362) | 46% [39%, 52%] (n 217) |
| DISPLACED of REJECTED | 29% [21%, 38%] (n 103) | 33% [26%, 41%] (n 110) | 12% [6%, 19%] (n 114) | 22% [20%, 25%] (n 1087) | 26% [18%, 35%] (n 99) |
| ENTERED of REJECTED and DISPLACED | 17% [3%, 31%] (n 30) | 25% [11%, 38%] (n 36) | 7% [0%, 23%] (n 14) | 18% [14%, 22%] (n 244) | 8% [0%, 19%] (n 26) |
| **Premise**: C1's opposite extreme before C2's extreme | 61% vs coin 54%: **7% [-2%, 16%]** (n 98) | 63% vs coin 57%: **6% [-2%, 14%]** (n 105) | 64% vs coin 58%: **6% [-2%, 15%]** (n 109) | 52% vs coin 49%: **3% [1%, 5%]** (n 971) | 53% vs coin 48%: **5% [-4%, 14%]** (n 95) |
| C2 had already reached C1's opposite extreme | 25% [17%, 34%] | 30% [22%, 38%] | 31% [23%, 39%] | 28% [25%, 30%] | 30% [21%, 40%] |
| TP1 before the stop | 60% [20%, 100%] (n 5) | 44% [11%, 78%] (n 9) | 100% [100%, 100%] (n 1) | 27% [15%, 40%] (n 44) | 0% [0%, 0%] (n 2) |
| -1 SD before the stop | 20% [0%, 60%] (n 5) | 22% [0%, 56%] (n 9) | 0% [0%, 0%] (n 1) | 7% [0%, 16%] (n 44) | 0% [0%, 0%] (n 2) |
| -2 SD before the stop | 0% [0%, 0%] (n 5) | 11% [0%, 33%] (n 9) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 44) | 0% [0%, 0%] (n 2) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 9) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 44) | 0% [0%, 0%] (n 2) |
| R held to TP1 | +0.68 [-0.63, +1.99] (n 5) | +0.26 [-0.68, +1.27] (n 9) | +0.87 [+0.87, +0.87] (n 1) | -0.16 [-0.52, +0.29] (n 44) | -1.00 [-1.00, -1.00] (n 2) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 5) | +0.06 [-1.00, +2.19] (n 9) | -1.00 [-1.00, -1.00] (n 1) | -0.82 [-1.00, -0.55] (n 44) | -1.00 [-1.00, -1.00] (n 2) |


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

### model_h4: F H4, C M15, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 9420 | 9361 | 9377 | 18742 | 8870 |
| ARMED | 8820 | 8762 | 8778 | 18742 | 6354 |
| MANIPULATED | 1322 | 1310 | 1323 | 9366 | 1375 |
| REJECTED | 431 | 470 | 481 | 4182 | 545 |
| DISPLACED | 209 | 206 | 80 | 1982 | 242 |
| IN_OTE | 20 | 43 | 9 | 271 | 38 |
| ENTERED | 15 | 38 | 6 | 218 | 31 |
| TP1 | 3 | 9 | 3 | 52 | 5 |
| SD_1 | 2 | 4 | 1 | 19 | 4 |
| SD_2 | 1 | 2 | 1 | 11 | 1 |
| SD_2.5 | 1 | 2 | 1 | 10 | 1 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 8098 | 8051 | 8054 | 9375 | 7495 |
| POI_FAILED | 170 | 167 | 169 | 0 | 161 |
| NO_REJECTION | 643 | 645 | 648 | 4487 | 574 |
| RETRACE_INVALID | 139 | 139 | 152 | 1470 | 199 |
| MISSED | 159 | 87 | 55 | 1445 | 168 |
| EXPIRED | 196 | 234 | 293 | 1745 | 242 |
| STOPPED | 13 | 32 | 5 | 178 | 27 |
| HORIZON | 1 | 4 | 0 | 30 | 3 |
| TARGETS_DONE | 1 | 2 | 1 | 10 | 1 |
| UNFINISHED | 0 | 0 | 0 | 2 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 15% [14%, 16%] (n 8820) | 15% [14%, 16%] (n 8762) | 15% [14%, 16%] (n 8778) | 50% [49%, 51%] (n 18742) | 22% [20%, 23%] (n 6354) |
| REJECTED of MANIPULATED | 33% [30%, 35%] (n 1322) | 36% [34%, 38%] (n 1310) | 36% [34%, 39%] (n 1323) | 45% [44%, 46%] (n 9366) | 40% [37%, 42%] (n 1375) |
| DISPLACED of REJECTED | 28% [24%, 32%] (n 431) | 34% [30%, 39%] (n 470) | 10% [8%, 13%] (n 481) | 30% [28%, 31%] (n 4182) | 24% [21%, 28%] (n 545) |
| ENTERED of REJECTED and DISPLACED | 13% [7%, 18%] (n 119) | 24% [17%, 31%] (n 160) | 12% [4%, 22%] (n 49) | 18% [16%, 20%] (n 1238) | 23% [16%, 31%] (n 133) |
| **Premise**: C1's opposite extreme before C2's extreme | 49% vs coin 50%: **-1% [-6%, 4%]** (n 389) | 51% vs coin 51%: **-0% [-5%, 4%]** (n 426) | 52% vs coin 52%: **0% [-4%, 5%]** (n 436) | 48% vs coin 49%: **-1% [-2%, 1%]** (n 3788) | 43% vs coin 48%: **-5% [-8%, -1%]** (n 504) |
| C2 had already reached C1's opposite extreme | 17% [14%, 21%] | 20% [17%, 24%] | 21% [17%, 25%] | 25% [24%, 27%] | 23% [20%, 27%] |
| TP1 before the stop | 20% [0%, 40%] (n 15) | 24% [11%, 37%] (n 38) | 50% [17%, 83%] (n 6) | 24% [19%, 29%] (n 218) | 16% [3%, 30%] (n 31) |
| -1 SD before the stop | 13% [0%, 33%] (n 15) | 11% [3%, 21%] (n 38) | 17% [0%, 50%] (n 6) | 9% [5%, 12%] (n 218) | 13% [0%, 27%] (n 31) |
| -2 SD before the stop | 7% [0%, 20%] (n 15) | 5% [0%, 14%] (n 38) | 17% [0%, 50%] (n 6) | 5% [2%, 8%] (n 218) | 3% [0%, 11%] (n 31) |
| -2.5 SD before the stop | 7% [0%, 20%] (n 15) | 5% [0%, 14%] (n 38) | 17% [0%, 50%] (n 6) | 5% [2%, 7%] (n 218) | 3% [0%, 11%] (n 31) |
| R held to TP1 | -0.37 [-0.85, +0.23] (n 15) | -0.23 [-0.61, +0.22] (n 38) | +0.21 [-0.66, +1.20] (n 6) | -0.12 [-0.30, +0.08] (n 218) | -0.39 [-0.84, +0.08] (n 31) |
| R held to -2 SD | -0.20 [-1.00, +1.25] (n 15) | -0.04 [-0.76, +0.83] (n 38) | +0.62 [-1.00, +3.86] (n 6) | -0.10 [-0.38, +0.19] (n 218) | -0.40 [-0.94, +0.34] (n 31) |


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

### model_h4_m30: F H4, C M30, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 4659 | 4590 | 4618 | 9638 | 4471 |
| ARMED | 4435 | 4367 | 4394 | 9638 | 3262 |
| MANIPULATED | 953 | 942 | 951 | 4724 | 776 |
| REJECTED | 250 | 292 | 333 | 1721 | 241 |
| DISPLACED | 326 | 310 | 158 | 1825 | 291 |
| IN_OTE | 52 | 74 | 29 | 281 | 35 |
| ENTERED | 47 | 68 | 25 | 250 | 31 |
| TP1 | 10 | 14 | 4 | 42 | 6 |
| SD_1 | 5 | 7 | 2 | 20 | 2 |
| SD_2 | 1 | 2 | 1 | 7 | 1 |
| SD_2.5 | 0 | 1 | 0 | 6 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 3705 | 3647 | 3666 | 4913 | 3694 |
| POI_FAILED | 184 | 190 | 186 | 0 | 126 |
| NO_REJECTION | 360 | 376 | 380 | 2163 | 272 |
| RETRACE_INVALID | 59 | 59 | 87 | 537 | 71 |
| MISSED | 238 | 165 | 102 | 1362 | 219 |
| EXPIRED | 65 | 84 | 171 | 411 | 57 |
| STOPPED | 34 | 51 | 19 | 188 | 22 |
| HORIZON | 13 | 16 | 6 | 56 | 9 |
| TARGETS_DONE | 0 | 1 | 0 | 6 | 0 |
| UNFINISHED | 1 | 1 | 1 | 2 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 21% [20%, 23%] (n 4435) | 22% [20%, 23%] (n 4367) | 22% [20%, 23%] (n 4394) | 49% [48%, 50%] (n 9638) | 24% [22%, 26%] (n 3262) |
| REJECTED of MANIPULATED | 26% [23%, 29%] (n 953) | 31% [28%, 34%] (n 942) | 35% [32%, 38%] (n 951) | 36% [35%, 38%] (n 4724) | 31% [28%, 35%] (n 776) |
| DISPLACED of REJECTED | 59% [53%, 66%] (n 250) | 66% [60%, 71%] (n 292) | 29% [24%, 33%] (n 333) | 53% [51%, 56%] (n 1721) | 55% [49%, 60%] (n 241) |
| ENTERED of REJECTED and DISPLACED | 32% [23%, 40%] (n 148) | 35% [28%, 42%] (n 192) | 26% [17%, 35%] (n 95) | 27% [24%, 30%] (n 917) | 23% [16%, 31%] (n 132) |
| **Premise**: C1's opposite extreme before C2's extreme | 49% vs coin 48%: **1% [-5%, 7%]** (n 197) | 52% vs coin 51%: **1% [-4%, 6%]** (n 233) | 55% vs coin 53%: **1% [-4%, 7%]** (n 268) | 47% vs coin 47%: **0% [-2%, 2%]** (n 1381) | 45% vs coin 47%: **-1% [-8%, 5%]** (n 188) |
| C2 had already reached C1's opposite extreme | 18% [14%, 24%] | 22% [17%, 26%] | 24% [19%, 29%] | 24% [22%, 26%] | 21% [16%, 27%] |
| TP1 before the stop | 21% [10%, 35%] (n 47) | 21% [11%, 31%] (n 68) | 16% [4%, 31%] (n 25) | 17% [12%, 22%] (n 250) | 19% [7%, 35%] (n 31) |
| -1 SD before the stop | 11% [2%, 20%] (n 47) | 10% [4%, 17%] (n 68) | 8% [0%, 21%] (n 25) | 8% [5%, 11%] (n 250) | 6% [0%, 17%] (n 31) |
| -2 SD before the stop | 2% [0%, 7%] (n 47) | 3% [0%, 7%] (n 68) | 4% [0%, 13%] (n 25) | 3% [1%, 5%] (n 250) | 3% [0%, 11%] (n 31) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 47) | 1% [0%, 5%] (n 68) | 0% [0%, 0%] (n 25) | 2% [1%, 4%] (n 250) | 0% [0%, 0%] (n 31) |
| R held to TP1 | +0.08 [-0.40, +0.67] (n 47) | -0.06 [-0.43, +0.38] (n 68) | -0.12 [-0.71, +0.65] (n 25) | -0.12 [-0.33, +0.11] (n 250) | +0.14 [-0.49, +0.96] (n 31) |
| R held to -2 SD | +0.06 [-0.56, +0.88] (n 47) | +0.07 [-0.45, +0.70] (n 68) | -0.06 [-0.77, +0.94] (n 25) | +0.00 [-0.27, +0.29] (n 250) | +0.34 [-0.45, +1.36] (n 31) |


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

### model_h4_m3: F H4, C M15, E M3

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 9368 | 9365 | 9376 | 18401 | 8822 |
| ARMED | 8769 | 8766 | 8777 | 18401 | 6225 |
| MANIPULATED | 1318 | 1318 | 1320 | 9371 | 1423 |
| REJECTED | 486 | 498 | 498 | 4760 | 660 |
| DISPLACED | 60 | 60 | 16 | 517 | 69 |
| IN_OTE | 5 | 6 | 0 | 67 | 4 |
| ENTERED | 5 | 5 | 0 | 45 | 3 |
| TP1 | 2 | 3 | 0 | 16 | 0 |
| SD_1 | 2 | 1 | 0 | 4 | 0 |
| SD_2 | 1 | 0 | 0 | 1 | 0 |
| SD_2.5 | 1 | 0 | 0 | 1 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 8050 | 8047 | 8056 | 9029 | 7399 |
| POI_FAILED | 168 | 168 | 169 | 0 | 162 |
| NO_REJECTION | 651 | 652 | 652 | 4532 | 588 |
| RETRACE_INVALID | 159 | 160 | 160 | 1733 | 247 |
| MISSED | 44 | 6 | 14 | 349 | 50 |
| EXPIRED | 291 | 327 | 325 | 2711 | 373 |
| STOPPED | 2 | 1 | 0 | 37 | 2 |
| HORIZON | 2 | 4 | 0 | 7 | 1 |
| TARGETS_DONE | 1 | 0 | 0 | 1 | 0 |
| UNFINISHED | 0 | 0 | 0 | 2 | 0 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 15% [14%, 16%] (n 8769) | 15% [14%, 16%] (n 8766) | 15% [14%, 16%] (n 8777) | 51% [50%, 51%] (n 18401) | 23% [21%, 24%] (n 6225) |
| REJECTED of MANIPULATED | 37% [34%, 39%] (n 1318) | 38% [35%, 40%] (n 1318) | 38% [35%, 40%] (n 1320) | 51% [50%, 52%] (n 9371) | 46% [44%, 49%] (n 1423) |
| DISPLACED of REJECTED | 9% [7%, 12%] (n 486) | 12% [9%, 15%] (n 498) | 3% [2%, 4%] (n 498) | 9% [8%, 10%] (n 4760) | 8% [7%, 10%] (n 660) |
| ENTERED of REJECTED and DISPLACED | 11% [2%, 20%] (n 46) | 8% [2%, 16%] (n 59) | 0% [0%, 0%] (n 14) | 10% [7%, 13%] (n 438) | 5% [0%, 12%] (n 55) |
| **Premise**: C1's opposite extreme before C2's extreme | 51% vs coin 51%: **-0% [-5%, 4%]** (n 440) | 53% vs coin 52%: **0% [-4%, 5%]** (n 452) | 52% vs coin 52%: **0% [-5%, 5%]** (n 452) | 52% vs coin 52%: **0% [-1%, 1%]** (n 4324) | 50% vs coin 51%: **-1% [-4%, 2%]** (n 603) |
| C2 had already reached C1's opposite extreme | 19% [16%, 23%] | 21% [18%, 25%] | 21% [18%, 25%] | 29% [28%, 31%] | 28% [24%, 31%] |
| TP1 before the stop | 40% [0%, 80%] (n 5) | 60% [20%, 100%] (n 5) | – (n 0) | 36% [22%, 49%] (n 45) | 0% [0%, 0%] (n 3) |
| -1 SD before the stop | 40% [0%, 80%] (n 5) | 20% [0%, 60%] (n 5) | – (n 0) | 9% [2%, 18%] (n 45) | 0% [0%, 0%] (n 3) |
| -2 SD before the stop | 20% [0%, 60%] (n 5) | 0% [0%, 0%] (n 5) | – (n 0) | 2% [0%, 7%] (n 45) | 0% [0%, 0%] (n 3) |
| -2.5 SD before the stop | 20% [0%, 60%] (n 5) | 0% [0%, 0%] (n 5) | – (n 0) | 2% [0%, 7%] (n 45) | 0% [0%, 0%] (n 3) |
| R held to TP1 | -0.10 [-0.90, +0.69] (n 5) | +0.27 [-0.49, +0.99] (n 5) | – (n 0) | -0.19 [-0.43, +0.05] (n 45) | -0.83 [-1.00, -0.49] (n 3) |
| R held to -2 SD | +2.67 [-0.90, +6.35] (n 5) | +1.79 [-0.39, +4.75] (n 5) | – (n 0) | -0.10 [-0.70, +0.65] (n 45) | -0.83 [-1.00, -0.49] (n 3) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 52% vs 50%: 2% [-5%, 9%] (n 203) | 1% [0%, 3%] (n 228) |
| True | 50% vs 52%: -2% [-7%, 3%] (n 237) | 1% [0%, 2%] (n 258) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 45% vs 60%: -14% [-42%, 13%] (n 11) | 0% [0%, 0%] (n 13) |
| None | 51% vs 51%: 0% [-4%, 5%] (n 429) | 1% [0%, 2%] (n 473) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 40% vs 42%: -2% [-16%, 12%] (n 15) | 0% [0%, 0%] (n 17) |
| FVG | 40% vs 51%: -11% [-27%, 8%] (n 40) | 0% [0%, 0%] (n 48) |
| OB | 54% vs 51%: 3% [-8%, 14%] (n 69) | 1% [0%, 4%] (n 79) |
| PDH | 59% vs 56%: 4% [-11%, 18%] (n 32) | 0% [0%, 0%] (n 34) |
| PMH | 17% vs 40%: -24% [-51%, -1%] (n 6) | 0% [0%, 0%] (n 7) |
| PWH | 60% vs 53%: 7% [-18%, 28%] (n 15) | 0% [0%, 0%] (n 17) |
| SWING_HIGH | 37% vs 50%: -13% [-24%, -1%] (n 49) | 0% [0%, 0%] (n 53) |
| previous H4 high | 56% vs 52%: 3% [-3%, 10%] (n 214) | 2% [0%, 3%] (n 231) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 52% vs 53%: -1% [-9%, 6%] (n 149) | 1% [0%, 3%] (n 166) |
| SHORT | 51% vs 51%: 0% [-6%, 6%] (n 291) | 1% [0%, 2%] (n 320) |

### w1_d1_h4: F W1, C D1, E H4

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 78 | 78 | 78 | 202 | 59 |
| ARMED | 72 | 72 | 72 | 202 | 36 |
| MANIPULATED | 25 | 25 | 25 | 98 | 6 |
| REJECTED | 7 | 7 | 7 | 50 | 3 |
| DISPLACED | 0 | 0 | 0 | 4 | 0 |
| IN_OTE | 0 | 0 | 0 | 0 | 0 |
| ENTERED | 0 | 0 | 0 | 0 | 0 |
| TP1 | 0 | 0 | 0 | 0 | 0 |
| SD_1 | 0 | 0 | 0 | 0 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 53 | 53 | 53 | 103 | 52 |
| POI_FAILED | 10 | 10 | 10 | 0 | 1 |
| NO_REJECTION | 7 | 7 | 7 | 46 | 2 |
| RETRACE_INVALID | 3 | 3 | 3 | 17 | 0 |
| MISSED | 0 | 0 | 0 | 3 | 0 |
| EXPIRED | 4 | 4 | 4 | 31 | 3 |
| UNFINISHED | 1 | 1 | 1 | 2 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 35% [24%, 46%] (n 72) | 35% [24%, 46%] (n 72) | 35% [24%, 46%] (n 72) | 49% [43%, 54%] (n 202) | 17% [6%, 28%] (n 36) |
| REJECTED of MANIPULATED | 28% [12%, 44%] (n 25) | 28% [12%, 44%] (n 25) | 28% [12%, 44%] (n 25) | 51% [41%, 61%] (n 98) | 50% [17%, 83%] (n 6) |
| DISPLACED of REJECTED | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 7) | 6% [0%, 13%] (n 50) | 0% [0%, 0%] (n 3) |
| ENTERED of REJECTED and DISPLACED | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 3) | – (n 0) |
| **Premise**: C1's opposite extreme before C2's extreme | 33% vs coin 48%: **-15% [-36%, 10%]** (n 6) | 33% vs coin 48%: **-15% [-36%, 10%]** (n 6) | 33% vs coin 48%: **-15% [-36%, 10%]** (n 6) | 47% vs coin 50%: **-3% [-15%, 10%]** (n 36) | 100% vs coin 65%: **35% [35%, 35%]** (n 1) |
| C2 had already reached C1's opposite extreme | 43% [14%, 71%] | 43% [14%, 71%] | 43% [14%, 71%] | 34% [19%, 48%] | 33% [0%, 100%] |
| TP1 before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| -1 SD before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| -2 SD before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| -2.5 SD before the stop | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| R held to TP1 | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |
| R held to -2 SD | – (n 0) | – (n 0) | – (n 0) | – (n 0) | – (n 0) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |
| True | 33% vs 48%: -15% [-36%, 10%] (n 6) | 0% [0%, 0%] (n 6) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| None | 33% vs 48%: -15% [-36%, 10%] (n 6) | 0% [0%, 0%] (n 7) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 65%: 35% [35%, 35%] (n 1) | 0% [0%, 0%] (n 2) |
| PMH | 100% vs 93%: 7% [7%, 7%] (n 1) | 0% [0%, 0%] (n 1) |
| previous W1 high | 0% vs 33%: -33% [-46%, -20%] (n 4) | 0% [0%, 0%] (n 4) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 100% vs 65%: 35% [35%, 35%] (n 1) | 0% [0%, 0%] (n 2) |
| SHORT | 20% vs 45%: -25% [-42%, -7%] (n 5) | 0% [0%, 0%] (n 5) |

### d1_h4_m15: F D1, C H4, E M15

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 552 | 543 | 543 | 1244 | 523 |
| ARMED | 533 | 524 | 524 | 1244 | 326 |
| MANIPULATED | 144 | 142 | 143 | 631 | 68 |
| REJECTED | 60 | 68 | 69 | 267 | 22 |
| DISPLACED | 31 | 30 | 8 | 165 | 14 |
| IN_OTE | 7 | 10 | 3 | 22 | 2 |
| ENTERED | 7 | 10 | 3 | 20 | 2 |
| TP1 | 0 | 0 | 0 | 4 | 1 |
| SD_1 | 0 | 0 | 0 | 3 | 0 |
| SD_2 | 0 | 0 | 0 | 1 | 0 |
| SD_2.5 | 0 | 0 | 0 | 1 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 407 | 400 | 399 | 612 | 454 |
| POI_FAILED | 27 | 28 | 28 | 0 | 15 |
| NO_REJECTION | 47 | 45 | 46 | 307 | 26 |
| RETRACE_INVALID | 23 | 23 | 29 | 89 | 7 |
| MISSED | 20 | 11 | 3 | 116 | 10 |
| EXPIRED | 20 | 25 | 34 | 98 | 8 |
| STOPPED | 6 | 9 | 2 | 15 | 2 |
| HORIZON | 1 | 1 | 1 | 4 | 0 |
| TARGETS_DONE | 0 | 0 | 0 | 1 | 0 |
| UNFINISHED | 1 | 1 | 1 | 2 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 27% [23%, 32%] (n 533) | 27% [23%, 32%] (n 524) | 27% [23%, 32%] (n 524) | 51% [49%, 53%] (n 1244) | 21% [16%, 26%] (n 326) |
| REJECTED of MANIPULATED | 42% [33%, 50%] (n 144) | 48% [40%, 56%] (n 142) | 48% [40%, 56%] (n 143) | 42% [38%, 46%] (n 631) | 32% [22%, 44%] (n 68) |
| DISPLACED of REJECTED | 35% [23%, 47%] (n 60) | 43% [31%, 55%] (n 68) | 12% [5%, 20%] (n 69) | 39% [33%, 45%] (n 267) | 41% [20%, 62%] (n 22) |
| ENTERED of REJECTED and DISPLACED | 33% [14%, 52%] (n 21) | 34% [18%, 50%] (n 29) | 38% [12%, 75%] (n 8) | 19% [13%, 27%] (n 103) | 22% [0%, 50%] (n 9) |
| **Premise**: C1's opposite extreme before C2's extreme | 47% vs coin 47%: **-1% [-13%, 12%]** (n 47) | 50% vs coin 50%: **-0% [-11%, 11%]** (n 54) | 51% vs coin 50%: **1% [-10%, 12%]** (n 55) | 56% vs coin 53%: **3% [-2%, 8%]** (n 198) | 53% vs coin 50%: **3% [-15%, 21%]** (n 17) |
| C2 had already reached C1's opposite extreme | 30% [19%, 41%] | 32% [22%, 43%] | 32% [22%, 43%] | 37% [31%, 43%] | 32% [14%, 54%] |
| TP1 before the stop | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 10) | 0% [0%, 0%] (n 3) | 20% [5%, 38%] (n 20) | 50% [0%, 100%] (n 2) |
| -1 SD before the stop | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 10) | 0% [0%, 0%] (n 3) | 15% [0%, 32%] (n 20) | 0% [0%, 0%] (n 2) |
| -2 SD before the stop | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 10) | 0% [0%, 0%] (n 3) | 5% [0%, 16%] (n 20) | 0% [0%, 0%] (n 2) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 10) | 0% [0%, 0%] (n 3) | 5% [0%, 16%] (n 20) | 0% [0%, 0%] (n 2) |
| R held to TP1 | -0.80 [-1.00, -0.41] (n 7) | -0.86 [-1.00, -0.59] (n 10) | -0.54 [-1.00, +0.37] (n 3) | -0.17 [-0.73, +0.60] (n 20) | -0.31 [-1.00, +0.39] (n 2) |
| R held to -2 SD | -0.80 [-1.00, -0.41] (n 7) | -0.86 [-1.00, -0.59] (n 10) | -0.54 [-1.00, +0.37] (n 3) | -0.14 [-0.89, +0.90] (n 20) | -1.00 [-1.00, -1.00] (n 2) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 49% vs 47%: 2% [-12%, 16%] (n 35) | 8% [0%, 18%] (n 39) |
| True | 42% vs 49%: -8% [-27%, 13%] (n 12) | 19% [5%, 38%] (n 21) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 36% vs 40%: -4% [-29%, 26%] (n 11) | 0% [0%, 0%] (n 13) |
| None | 50% vs 50%: 0% [-13%, 14%] (n 36) | 15% [6%, 26%] (n 46) |
| TIGHT_RANGE | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 33% vs 42%: -8% [-24%, 22%] (n 3) | 0% [0%, 0%] (n 5) |
| OB | 25% vs 44%: -19% [-47%, 24%] (n 4) | 50% [17%, 83%] (n 6) |
| PMH | 100% vs 66%: 34% [30%, 37%] (n 2) | 0% [0%, 0%] (n 2) |
| PWH | 43% vs 45%: -2% [-24%, 25%] (n 7) | 0% [0%, 0%] (n 9) |
| SWING_HIGH | 0% vs 30%: -30% [-58%, -16%] (n 3) | 14% [0%, 43%] (n 7) |
| previous D1 high | 54% vs 50%: 4% [-12%, 20%] (n 28) | 10% [0%, 21%] (n 31) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 62% vs 48%: 15% [-13%, 46%] (n 8) | 0% [0%, 0%] (n 13) |
| SHORT | 44% vs 47%: -4% [-17%, 9%] (n 39) | 15% [6%, 24%] (n 47) |

### h1_m15_m1: F H1, C M15, E M1

| State reached | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| FRAMED | 9290 | 9186 | 9211 | 18852 | 9205 |
| ARMED | 8891 | 8799 | 8817 | 18852 | 6676 |
| MANIPULATED | 2634 | 2609 | 2624 | 9421 | 1711 |
| REJECTED | 960 | 1046 | 1073 | 4213 | 644 |
| DISPLACED | 450 | 438 | 161 | 1996 | 310 |
| IN_OTE | 54 | 105 | 22 | 273 | 42 |
| ENTERED | 41 | 86 | 15 | 220 | 37 |
| TP1 | 7 | 14 | 5 | 42 | 6 |
| SD_1 | 0 | 3 | 0 | 9 | 0 |
| SD_2 | 0 | 1 | 0 | 3 | 0 |
| SD_2.5 | 0 | 1 | 0 | 2 | 0 |

| How it ended | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 6655 | 6576 | 6586 | 9430 | 7493 |
| POI_FAILED | 635 | 634 | 632 | 0 | 341 |
| NO_REJECTION | 876 | 881 | 880 | 4506 | 615 |
| RETRACE_INVALID | 314 | 318 | 363 | 1480 | 226 |
| MISSED | 328 | 169 | 95 | 1456 | 229 |
| EXPIRED | 440 | 521 | 639 | 1758 | 263 |
| STOPPED | 31 | 65 | 11 | 153 | 29 |
| HORIZON | 10 | 20 | 4 | 65 | 8 |
| TARGETS_DONE | 0 | 1 | 0 | 2 | 0 |
| UNFINISHED | 1 | 1 | 1 | 2 | 1 |

| Measure | Model A | Model A, the leg runs to the swing low (MA-D5) | Model A, the engine's next-candle CISD (MA-D4) | CRT baseline: no F context | Random-POI baseline |
|---|---|---|---|---|---|
| MANIPULATED of ARMED | 30% [29%, 31%] (n 8891) | 30% [29%, 31%] (n 8799) | 30% [29%, 31%] (n 8817) | 50% [49%, 51%] (n 18852) | 26% [24%, 27%] (n 6676) |
| REJECTED of MANIPULATED | 36% [35%, 38%] (n 2634) | 40% [38%, 42%] (n 2609) | 41% [39%, 43%] (n 2624) | 45% [44%, 46%] (n 9421) | 38% [36%, 39%] (n 1711) |
| DISPLACED of REJECTED | 28% [26%, 31%] (n 960) | 35% [32%, 37%] (n 1046) | 11% [9%, 13%] (n 1073) | 30% [28%, 31%] (n 4213) | 29% [26%, 32%] (n 644) |
| ENTERED of REJECTED and DISPLACED | 15% [11%, 20%] (n 272) | 24% [19%, 28%] (n 362) | 13% [7%, 20%] (n 116) | 18% [16%, 20%] (n 1246) | 20% [15%, 25%] (n 187) |
| **Premise**: C1's opposite extreme before C2's extreme | 50% vs coin 51%: **-2% [-5%, 1%]** (n 691) | 53% vs coin 54%: **-1% [-4%, 1%]** (n 773) | 54% vs coin 54%: **-0% [-3%, 2%]** (n 788) | 50% vs coin 51%: **-1% [-3%, 0%]** (n 2794) | 48% vs coin 52%: **-4% [-7%, -0%]** (n 424) |
| C2 had already reached C1's opposite extreme | 21% [19%, 24%] | 24% [21%, 27%] | 25% [22%, 27%] | 25% [24%, 27%] | 21% [17%, 24%] |
| TP1 before the stop | 17% [8%, 28%] (n 41) | 16% [10%, 24%] (n 86) | 33% [12%, 60%] (n 15) | 19% [15%, 24%] (n 220) | 16% [6%, 28%] (n 37) |
| -1 SD before the stop | 0% [0%, 0%] (n 41) | 3% [0%, 8%] (n 86) | 0% [0%, 0%] (n 15) | 4% [2%, 7%] (n 220) | 0% [0%, 0%] (n 37) |
| -2 SD before the stop | 0% [0%, 0%] (n 41) | 1% [0%, 4%] (n 86) | 0% [0%, 0%] (n 15) | 1% [0%, 3%] (n 220) | 0% [0%, 0%] (n 37) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 41) | 1% [0%, 4%] (n 86) | 0% [0%, 0%] (n 15) | 1% [0%, 2%] (n 220) | 0% [0%, 0%] (n 37) |
| R held to TP1 | -0.05 [-0.48, +0.43] (n 41) | -0.18 [-0.41, +0.12] (n 86) | +0.30 [-0.31, +0.87] (n 15) | -0.05 [-0.22, +0.14] (n 220) | -0.18 [-0.61, +0.32] (n 37) |
| R held to -2 SD | -0.27 [-0.68, +0.17] (n 41) | -0.27 [-0.56, +0.11] (n 86) | -0.36 [-0.88, +0.18] (n 15) | -0.13 [-0.34, +0.10] (n 220) | -0.30 [-0.74, +0.21] (n 37) |


*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 46% vs 50%: -4% [-9%, 0%] (n 289) | 5% [3%, 7%] (n 396) |
| True | 52% vs 52%: 0% [-4%, 4%] (n 402) | 4% [2%, 6%] (n 564) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 40% vs 48%: -8% [-14%, -2%] (n 162) | 5% [3%, 8%] (n 247) |
| None | 53% vs 52%: 0% [-3%, 3%] (n 529) | 4% [3%, 5%] (n 712) |
| TIGHT_RANGE | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 69% vs 57%: 12% [-7%, 30%] (n 13) | 4% [0%, 14%] (n 25) |
| FVG | 42% vs 46%: -4% [-20%, 11%] (n 26) | 2% [0%, 6%] (n 52) |
| OB | 41% vs 49%: -7% [-20%, 5%] (n 46) | 7% [2%, 14%] (n 81) |
| PDH | 57% vs 55%: 2% [-12%, 16%] (n 23) | 3% [0%, 9%] (n 34) |
| PMH | 0% vs 30%: -30% [-35%, -25%] (n 2) | 0% [0%, 0%] (n 3) |
| PWH | 20% vs 40%: -20% [-42%, 8%] (n 5) | 0% [0%, 0%] (n 10) |
| SWING_HIGH | 47% vs 49%: -2% [-12%, 8%] (n 53) | 4% [1%, 8%] (n 109) |
| previous H1 high | 51% vs 52%: -1% [-4%, 2%] (n 523) | 4% [3%, 6%] (n 646) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 50% vs 55%: -4% [-9%, -0%] (n 252) | 4% [2%, 6%] (n 367) |
| SHORT | 49% vs 49%: -0% [-4%, 4%] (n 439) | 5% [3%, 7%] (n 593) |
