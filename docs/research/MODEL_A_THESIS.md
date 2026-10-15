# The Model A record

Context-engine Requirement 16 (update 2026-10-15). Descriptive: no verdict and no ledger row. It feeds the review with the trader.

- **snapshot:** exness-2025-2026h1
- **slice:** exploration slice, 2025-01-01 to 2025-07-01 (end exclusive)
- **frame sets:** model_d1, model_h4, model_h4_m30
- **code_commit:** 7aa6dba2bac70cac637ad2f1bc0a87fc99d3de78

**How to read it.**
- The funnel counts instances: each closed C candle in context starts one.
- **The premise:** once C2 has rejected, how often price reaches C1's opposite extreme before C2's extreme, within the F candle. It's compared with a coin flip from the same distances.
  - The interval is that difference, paired by trading date.
  - A lower bound above zero means the step carries information.
- **After the fill:** the outcomes of the few that reach the OTE and fill.
- **The baselines** read the same C and E rules. CRT has no F context; the random-POI baseline moves every POI.

## The theses on their own

How often each thesis named the trading day's direction (its D1 candle closing above or below its open), among the days it named one; a coin flip is 50%. ORACLE is that direction itself: hindsight, the upper bound.

| Instrument | Thesis | Days named | Right |
|---|---|---:|---|
| EURUSD | ORACLE | 128 of 128 | 100% [100%, 100%] |
| EURUSD | PREV_DAY | 128 of 128 | 51% [42%, 59%] |
| EURUSD | PROFILE | 128 of 128 | 48% [39%, 57%] |
| GBPUSD | ORACLE | 128 of 128 | 100% [100%, 100%] |
| GBPUSD | PREV_DAY | 128 of 128 | 46% [38%, 55%] |
| GBPUSD | PROFILE | 128 of 128 | 47% [38%, 55%] |
| USDJPY | ORACLE | 128 of 128 | 100% [100%, 100%] |
| USDJPY | PREV_DAY | 128 of 128 | 45% [36%, 53%] |
| USDJPY | PROFILE | 128 of 128 | 53% [45%, 61%] |
| XAUUSD | ORACLE | 127 of 127 | 100% [100%, 100%] |
| XAUUSD | PREV_DAY | 127 of 127 | 40% [32%, 49%] |
| XAUUSD | PROFILE | 125 of 127 | 53% [44%, 61%] |

## Summary: the premise against its coin flip

Once C2 has rejected: C1's opposite extreme before C2's extreme, minus the coin flip from the same distances, with its day-cluster interval. The last arm with fills gives the fills and the R held to TP1.

| Instrument | Frame set | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) | Fills | R held to TP1 |
|---|---|---|---|---|---|---|---|---|---:|---|
| EURUSD | model_d1 (D1/H1/M5) | -13% [-37, +13] (n 11) | -16% [-53, +45] (n 3) | +5% [-46, +39] (n 4) | -8% [-20, +4] (n 46) | +16% [-1, +30] (n 23) | +3% [-3, +8] (n 236) | +10% [+5, +16] (n 225) | 0 | – |
| EURUSD | model_h4 (H4/M15/M1) | +1% [-9, +10] (n 73) | +15% [+3, +28] (n 36) | +10% [-0, +19] (n 62) | +2% [-5, +9] (n 179) | +3% [-4, +11] (n 129) | +0% [-2, +3] (n 778) | +4% [+1, +7] (n 754) | 6 | -0.57 [-1.00, +0.30] |
| EURUSD | model_h4_m30 (H4/M30/M1) | +18% [+5, +31] (n 46) | +19% [+0, +37] (n 24) | +6% [-8, +19] (n 37) | +10% [+3, +16] (n 105) | +7% [-1, +15] (n 76) | +1% [-4, +6] (n 282) | +4% [-1, +9] (n 285) | 6 | +0.25 [-1.00, +1.77] |
| GBPUSD | model_d1 (D1/H1/M5) | +20% [+1, +38] (n 16) | +20% [+3, +41] (n 11) | +12% [-8, +30] (n 19) | +8% [-3, +21] (n 41) | +24% [+9, +38] (n 34) | +5% [-1, +10] (n 229) | +9% [+3, +14] (n 218) | 0 | – |
| GBPUSD | model_h4 (H4/M15/M1) | +0% [-10, +11] (n 61) | +3% [-8, +13] (n 54) | +3% [-9, +14] (n 57) | -0% [-7, +6] (n 176) | -1% [-10, +7] (n 106) | +1% [-2, +4] (n 781) | +3% [+0, +6] (n 787) | 7 | +0.41 [-0.82, +2.16] |
| GBPUSD | model_h4_m30 (H4/M30/M1) | +6% [-9, +21] (n 36) | -2% [-16, +15] (n 31) | +18% [+7, +30] (n 36) | +4% [-3, +12] (n 88) | +8% [-4, +21] (n 52) | -0% [-5, +5] (n 330) | +7% [+2, +12] (n 310) | 2 | -1.00 [-1.00, -1.00] |
| USDJPY | model_d1 (D1/H1/M5) | +1% [-11, +19] (n 6) | -15% [-44, +19] (n 9) | +29% [+15, +45] (n 13) | +10% [-1, +22] (n 21) | +11% [-0, +21] (n 38) | +4% [-1, +9] (n 192) | +11% [+5, +16] (n 184) | 0 | – |
| USDJPY | model_h4 (H4/M15/M1) | -6% [-20, +9] (n 37) | -1% [-11, +10] (n 49) | +6% [-5, +18] (n 48) | +8% [-1, +16] (n 136) | +9% [+2, +16] (n 111) | +0% [-4, +3] (n 711) | +6% [+3, +10] (n 689) | 4 | +0.04 [-1.00, +2.12] |
| USDJPY | model_h4_m30 (H4/M30/M1) | +7% [-9, +23] (n 25) | -1% [-13, +11] (n 28) | +11% [-1, +23] (n 34) | -4% [-14, +6] (n 69) | +6% [-4, +17] (n 68) | +0% [-4, +4] (n 276) | +9% [+4, +14] (n 266) | 2 | -0.69 [-1.00, -0.37] |
| XAUUSD | model_d1 (D1/H1/M5) | +13% [-16, +43] (n 10) | +33% [+10, +51] (n 12) | +36% [+16, +55] (n 11) | +12% [-5, +30] (n 25) | +21% [+5, +35] (n 28) | +3% [-3, +9] (n 195) | +14% [+8, +19] (n 202) | 0 | – |
| XAUUSD | model_h4 (H4/M15/M1) | +6% [-5, +17] (n 51) | +10% [-4, +26] (n 33) | +16% [+3, +28] (n 53) | -0% [-8, +8] (n 147) | +7% [-2, +17] (n 115) | -0% [-4, +3] (n 725) | +5% [+2, +8] (n 711) | 1 | +1.27 [+1.27, +1.27] |
| XAUUSD | model_h4_m30 (H4/M30/M1) | +13% [-1, +25] (n 32) | +7% [-12, +27] (n 19) | +17% [+3, +31] (n 27) | +5% [-4, +15] (n 73) | +11% [+1, +21] (n 53) | +2% [-3, +7] (n 278) | +7% [+3, +12] (n 267) | 2 | -1.00 [-1.00, -1.00] |

*Fills and R are for + time + volatility, PROFILE thesis.*

## EURUSD

### model_d1: F D1, C H1, E M5

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 497 | 426 | 564 | 1040 | 1127 | 1175 | 1189 |
| ARMED | 479 | 413 | 531 | 976 | 1050 | 1175 | 1189 |
| MANIPULATED | 65 | 31 | 24 | 123 | 54 | 620 | 519 |
| REJECTED | 11 | 3 | 4 | 47 | 23 | 236 | 225 |
| DISPLACED | 4 | 1 | 2 | 17 | 8 | 69 | 88 |
| IN_OTE | 0 | 0 | 0 | 4 | 1 | 9 | 6 |
| ENTERED | 0 | 0 | 0 | 2 | 1 | 7 | 5 |
| TP1 | 0 | 0 | 0 | 1 | 0 | 3 | 2 |
| SD_1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 432 | 395 | 540 | 917 | 1073 | 555 | 670 |
| POI_FAILED | 9 | 5 | 3 | 11 | 3 | 0 | 0 |
| NO_REJECTION | 38 | 21 | 15 | 62 | 27 | 318 | 220 |
| RANGE_SPENT | 4 | 1 | 1 | 0 | 0 | 37 | 35 |
| TOO_LARGE | 2 | 0 | 0 | 0 | 0 | 6 | 5 |
| RETRACE_INVALID | 2 | 0 | 1 | 13 | 5 | 92 | 68 |
| MISSED | 2 | 1 | 1 | 10 | 7 | 50 | 71 |
| EXPIRED | 8 | 3 | 3 | 25 | 11 | 110 | 115 |
| STOPPED | 0 | 0 | 0 | 2 | 1 | 7 | 5 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [9%, 18%] (n 479) | 8% [4%, 12%] (n 413) | 5% [3%, 7%] (n 531) | 13% [10%, 16%] (n 976) | 5% [4%, 7%] (n 1050) | 53% [50%, 56%] (n 1175) | 44% [41%, 46%] (n 1189) |
| REJECTED of MANIPULATED | 17% [8%, 27%] (n 65) | 10% [0%, 20%] (n 31) | 17% [4%, 30%] (n 24) | 38% [32%, 45%] (n 123) | 43% [31%, 53%] (n 54) | 38% [34%, 42%] (n 620) | 43% [38%, 48%] (n 519) |
| DISPLACED of REJECTED | 18% [0%, 45%] (n 11) | 0% [0%, 0%] (n 3) | 25% [0%, 75%] (n 4) | 30% [17%, 43%] (n 47) | 30% [11%, 50%] (n 23) | 18% [13%, 23%] (n 236) | 22% [17%, 27%] (n 225) |
| ENTERED of REJECTED and DISPLACED | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 1) | 14% [0%, 33%] (n 14) | 14% [0%, 50%] (n 7) | 17% [7%, 28%] (n 42) | 10% [2%, 19%] (n 49) |
| **Premise**: C1's opposite extreme before C2's extreme | 36% vs coin 49%: **-13% [-37%, 13%]** (n 11) | 33% vs coin 49%: **-16% [-53%, 45%]** (n 3) | 75% vs coin 70%: **5% [-46%, 39%]** (n 4) | 43% vs coin 52%: **-8% [-20%, 4%]** (n 46) | 74% vs coin 58%: **16% [-1%, 30%]** (n 23) | 53% vs coin 50%: **3% [-3%, 8%]** (n 236) | 64% vs coin 53%: **10% [5%, 16%]** (n 225) |
| C2 had already reached C1's opposite extreme | 9% [0%, 30%] | 0% [0%, 0%] | 50% [0%, 100%] | 21% [10%, 32%] | 26% [9%, 44%] | 27% [22%, 32%] | 31% [25%, 37%] |
| TP1 before the stop | – (n 0) | – (n 0) | – (n 0) | 50% [0%, 100%] (n 2) | 0% [0%, 0%] (n 1) | 43% [14%, 86%] (n 7) | 40% [0%, 80%] (n 5) |
| -1 SD before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 5) |
| -2 SD before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 5) |
| -2.5 SD before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 5) |
| R held to TP1 | – (n 0) | – (n 0) | – (n 0) | +0.11 [-1.00, +1.22] (n 2) | -1.00 [-1.00, -1.00] (n 1) | +0.20 [-0.79, +1.62] (n 7) | -0.26 [-1.00, +0.64] (n 5) |
| R held to -2 SD | – (n 0) | – (n 0) | – (n 0) | -1.00 [-1.00, -1.00] (n 2) | -1.00 [-1.00, -1.00] (n 1) | -1.00 [-1.00, -1.00] (n 7) | -1.00 [-1.00, -1.00] (n 5) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 0% vs 57%: -57% [-65%, -40%] (n 3) | 0% [0%, 0%] (n 3) |
| LONDON | 50% vs 50%: -0% [-32%, 32%] (n 4) | 0% [0%, 0%] (n 4) |
| MIDNIGHT | 50% vs 34%: 16% [-18%, 50%] (n 2) | 0% [0%, 0%] (n 2) |
| PRE_NY | 50% vs 53%: -3% [-40%, 33%] (n 2) | 0% [0%, 0%] (n 2) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 44% vs 53%: -9% [-38%, 24%] (n 9) | 0% [0%, 0%] (n 9) |
| True | 0% vs 32%: -32% [-41%, -23%] (n 2) | 0% [0%, 0%] (n 2) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 100% vs 66%: 34% [19%, 50%] (n 2) | 0% [0%, 0%] (n 2) |
| None | 25% vs 46%: -21% [-47%, 13%] (n 8) | 0% [0%, 0%] (n 8) |
| TIGHT_RANGE | 0% vs 41%: -41% [-41%, -41%] (n 1) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| PWH | 0% vs 32%: -32% [-40%, -23%] (n 2) | 0% [0%, 0%] (n 2) |
| SWING_HIGH | 0% vs 18%: -18% [-18%, -18%] (n 1) | 0% [0%, 0%] (n 1) |
| previous D1 high | 50% vs 58%: -8% [-41%, 33%] (n 8) | 0% [0%, 0%] (n 8) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 100% vs 52%: 48% [45%, 50%] (n 2) | 0% [0%, 0%] (n 2) |
| SHORT | 22% vs 49%: -27% [-47%, -6%] (n 9) | 0% [0%, 0%] (n 9) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 63%: -13% [-71%, 45%] (n 2) | 0% [0%, 0%] (n 2) |
| LONDON | 100% vs 76%: 24% [19%, 29%] (n 2) | 0% [0%, 0%] (n 2) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 67% vs 69%: -2% [-71%, 45%] (n 3) | 0% [0%, 0%] (n 3) |
| True | 100% vs 71%: 29% [29%, 29%] (n 1) | 0% [0%, 0%] (n 1) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 100% vs 81%: 19% [19%, 19%] (n 1) | 0% [0%, 0%] (n 1) |
| None | 100% vs 55%: 45% [45%, 45%] (n 1) | 0% [0%, 0%] (n 1) |
| TIGHT_RANGE | 50% vs 71%: -21% [-71%, 29%] (n 2) | 0% [0%, 0%] (n 2) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| previous D1 high | 75% vs 70%: 5% [-46%, 39%] (n 4) | 0% [0%, 0%] (n 4) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 67% vs 66%: 1% [-71%, 45%] (n 3) | 0% [0%, 0%] (n 3) |
| SHORT | 100% vs 81%: 19% [19%, 19%] (n 1) | 0% [0%, 0%] (n 1) |

### model_h4: F H4, C M15, E M1

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 2321 | 1074 | 1965 | 4947 | 3845 | 4760 | 4793 |
| ARMED | 2210 | 1029 | 1858 | 4603 | 3615 | 4760 | 4793 |
| MANIPULATED | 320 | 150 | 185 | 655 | 389 | 2469 | 2250 |
| REJECTED | 76 | 37 | 63 | 195 | 137 | 856 | 819 |
| DISPLACED | 40 | 14 | 22 | 121 | 83 | 427 | 425 |
| IN_OTE | 6 | 0 | 4 | 21 | 14 | 43 | 31 |
| ENTERED | 6 | 0 | 4 | 18 | 12 | 38 | 28 |
| TP1 | 1 | 0 | 0 | 4 | 3 | 4 | 6 |
| SD_1 | 0 | 0 | 0 | 1 | 0 | 2 | 4 |
| SD_2 | 0 | 0 | 0 | 1 | 0 | 2 | 1 |
| SD_2.5 | 0 | 0 | 0 | 1 | 0 | 2 | 1 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 2001 | 924 | 1780 | 4292 | 3456 | 2291 | 2543 |
| POI_FAILED | 42 | 19 | 17 | 73 | 30 | 0 | 0 |
| NO_REJECTION | 161 | 71 | 82 | 328 | 181 | 1257 | 1072 |
| RANGE_SPENT | 20 | 13 | 10 | 0 | 0 | 148 | 145 |
| RETRACE_INVALID | 20 | 9 | 16 | 52 | 41 | 300 | 274 |
| MISSED | 29 | 14 | 17 | 86 | 60 | 325 | 338 |
| EXPIRED | 42 | 24 | 39 | 98 | 65 | 401 | 393 |
| STOPPED | 6 | 0 | 4 | 14 | 11 | 32 | 25 |
| HORIZON | 0 | 0 | 0 | 3 | 1 | 4 | 2 |
| TARGETS_DONE | 0 | 0 | 0 | 1 | 0 | 2 | 1 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [12%, 17%] (n 2210) | 15% [12%, 18%] (n 1029) | 10% [8%, 12%] (n 1858) | 14% [13%, 16%] (n 4603) | 11% [9%, 12%] (n 3615) | 52% [50%, 53%] (n 4760) | 47% [46%, 48%] (n 4793) |
| REJECTED of MANIPULATED | 24% [19%, 29%] (n 320) | 25% [17%, 33%] (n 150) | 34% [27%, 42%] (n 185) | 30% [26%, 33%] (n 655) | 35% [31%, 40%] (n 389) | 35% [31%, 38%] (n 2469) | 36% [33%, 40%] (n 2250) |
| DISPLACED of REJECTED | 21% [13%, 30%] (n 76) | 11% [2%, 23%] (n 37) | 13% [5%, 22%] (n 63) | 30% [25%, 36%] (n 195) | 30% [23%, 38%] (n 137) | 20% [17%, 24%] (n 856) | 21% [17%, 24%] (n 819) |
| ENTERED of REJECTED and DISPLACED | 38% [12%, 62%] (n 16) | 0% [0%, 0%] (n 4) | 50% [12%, 88%] (n 8) | 31% [19%, 43%] (n 59) | 29% [16%, 44%] (n 41) | 22% [17%, 28%] (n 173) | 17% [10%, 23%] (n 168) |
| **Premise**: C1's opposite extreme before C2's extreme | 52% vs coin 52%: **1% [-9%, 10%]** (n 73) | 69% vs coin 54%: **15% [3%, 28%]** (n 36) | 63% vs coin 53%: **10% [-0%, 19%]** (n 62) | 51% vs coin 49%: **2% [-5%, 9%]** (n 179) | 55% vs coin 52%: **3% [-4%, 11%]** (n 129) | 50% vs coin 50%: **0% [-2%, 3%]** (n 778) | 54% vs coin 50%: **4% [1%, 7%]** (n 754) |
| C2 had already reached C1's opposite extreme | 18% [11%, 27%] | 27% [14%, 41%] | 24% [14%, 35%] | 22% [16%, 27%] | 22% [16%, 28%] | 25% [22%, 28%] | 29% [25%, 32%] |
| TP1 before the stop | 17% [0%, 50%] (n 6) | – (n 0) | 0% [0%, 0%] (n 4) | 22% [6%, 39%] (n 18) | 25% [0%, 50%] (n 12) | 11% [2%, 22%] (n 38) | 21% [7%, 38%] (n 28) |
| -1 SD before the stop | 0% [0%, 0%] (n 6) | – (n 0) | 0% [0%, 0%] (n 4) | 6% [0%, 18%] (n 18) | 0% [0%, 0%] (n 12) | 5% [0%, 14%] (n 38) | 14% [3%, 29%] (n 28) |
| -2 SD before the stop | 0% [0%, 0%] (n 6) | – (n 0) | 0% [0%, 0%] (n 4) | 6% [0%, 18%] (n 18) | 0% [0%, 0%] (n 12) | 5% [0%, 14%] (n 38) | 4% [0%, 12%] (n 28) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 6) | – (n 0) | 0% [0%, 0%] (n 4) | 6% [0%, 18%] (n 18) | 0% [0%, 0%] (n 12) | 5% [0%, 14%] (n 38) | 4% [0%, 12%] (n 28) |
| R held to TP1 | -0.57 [-1.00, +0.30] (n 6) | – (n 0) | -1.00 [-1.00, -1.00] (n 4) | -0.10 [-0.69, +0.58] (n 18) | -0.30 [-0.84, +0.33] (n 12) | -0.38 [-0.80, +0.23] (n 38) | -0.24 [-0.81, +0.59] (n 28) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 6) | – (n 0) | -1.00 [-1.00, -1.00] (n 4) | -0.15 [-0.89, +1.01] (n 18) | -0.82 [-1.00, -0.47] (n 12) | -0.31 [-0.90, +0.49] (n 38) | -0.28 [-1.00, +0.69] (n 28) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 63% vs 51%: 12% [-2%, 27%] (n 30) | 3% [0%, 10%] (n 31) |
| LONDON | 39% vs 55%: -17% [-32%, -1%] (n 18) | 20% [5%, 37%] (n 20) |
| MIDNIGHT | 40% vs 43%: -3% [-22%, 18%] (n 15) | 0% [0%, 0%] (n 15) |
| PRE_NY | 60% vs 60%: 0% [-23%, 20%] (n 10) | 10% [0%, 33%] (n 10) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 56% vs 51%: 5% [-13%, 20%] (n 34) | 12% [3%, 24%] (n 34) |
| True | 49% vs 52%: -4% [-16%, 9%] (n 39) | 5% [0%, 11%] (n 42) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 56% vs 54%: 2% [-19%, 25%] (n 16) | 6% [0%, 19%] (n 18) |
| None | 53% vs 50%: 3% [-9%, 13%] (n 51) | 8% [2%, 15%] (n 52) |
| TIGHT_RANGE | 33% vs 59%: -25% [-48%, 0%] (n 6) | 17% [0%, 50%] (n 6) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 0% vs 27%: -27% [-27%, -27%] (n 1) | 0% [0%, 0%] (n 1) |
| FVG | 58% vs 52%: 6% [-16%, 24%] (n 12) | 17% [0%, 45%] (n 12) |
| OB | 100% vs 89%: 11% [11%, 11%] (n 1) | 100% [100%, 100%] (n 1) |
| PDH | 50% vs 53%: -3% [-27%, 28%] (n 6) | 0% [0%, 0%] (n 6) |
| PMH | 0% vs 35%: -35% [-35%, -35%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |
| SWING_HIGH | 40% vs 44%: -4% [-26%, 22%] (n 10) | 0% [0%, 0%] (n 12) |
| previous H4 high | 55% vs 53%: 2% [-13%, 15%] (n 42) | 7% [0%, 15%] (n 42) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 50% vs 53%: -3% [-18%, 11%] (n 24) | 8% [0%, 22%] (n 25) |
| SHORT | 53% vs 51%: 2% [-10%, 14%] (n 49) | 8% [2%, 15%] (n 51) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 62% vs 53%: 9% [-4%, 23%] (n 24) | 4% [0%, 12%] (n 24) |
| LONDON | 62% vs 56%: 6% [-15%, 28%] (n 21) | 5% [0%, 17%] (n 22) |
| MIDNIGHT | 56% vs 49%: 6% [-17%, 30%] (n 9) | 11% [0%, 33%] (n 9) |
| PRE_NY | 75% vs 49%: 26% [5%, 51%] (n 8) | 12% [0%, 43%] (n 8) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 62% vs 52%: 10% [-8%, 28%] (n 29) | 10% [0%, 23%] (n 29) |
| True | 64% vs 53%: 10% [-2%, 23%] (n 33) | 3% [0%, 10%] (n 34) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 72% vs 58%: 14% [-9%, 34%] (n 18) | 6% [0%, 18%] (n 18) |
| None | 59% vs 49%: 10% [-3%, 21%] (n 39) | 8% [0%, 18%] (n 40) |
| TIGHT_RANGE | 60% vs 62%: -2% [-29%, 24%] (n 5) | 0% [0%, 0%] (n 5) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 86% vs 60%: 25% [9%, 47%] (n 7) | 0% [0%, 0%] (n 7) |
| PDH | 60% vs 51%: 9% [-16%, 36%] (n 5) | 0% [0%, 0%] (n 5) |
| PWH | 100% vs 48%: 52% [40%, 64%] (n 2) | 0% [0%, 0%] (n 2) |
| SWING_HIGH | 67% vs 35%: 32% [-26%, 68%] (n 3) | 0% [0%, 0%] (n 3) |
| previous H4 high | 58% vs 53%: 4% [-8%, 16%] (n 45) | 9% [2%, 18%] (n 46) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 60% vs 52%: 8% [-5%, 20%] (n 35) | 6% [0%, 15%] (n 36) |
| SHORT | 67% vs 54%: 12% [-3%, 28%] (n 27) | 7% [0%, 17%] (n 27) |

### model_h4_m30: F H4, C M30, E M1

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 1148 | 529 | 981 | 2452 | 1891 | 2457 | 2477 |
| ARMED | 1107 | 511 | 943 | 2318 | 1804 | 2457 | 2477 |
| MANIPULATED | 235 | 109 | 137 | 489 | 282 | 1260 | 1121 |
| REJECTED | 50 | 25 | 40 | 123 | 88 | 346 | 341 |
| DISPLACED | 73 | 31 | 41 | 180 | 117 | 373 | 372 |
| IN_OTE | 6 | 1 | 3 | 18 | 13 | 27 | 23 |
| ENTERED | 6 | 0 | 2 | 16 | 12 | 24 | 18 |
| TP1 | 2 | 0 | 0 | 7 | 4 | 6 | 4 |
| SD_1 | 0 | 0 | 0 | 1 | 2 | 1 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 913 | 420 | 844 | 1963 | 1609 | 1197 | 1356 |
| POI_FAILED | 44 | 19 | 17 | 76 | 29 | 0 | 0 |
| NO_REJECTION | 81 | 36 | 48 | 194 | 108 | 604 | 486 |
| RANGE_SPENT | 10 | 6 | 6 | 0 | 0 | 48 | 39 |
| RETRACE_INVALID | 15 | 7 | 11 | 29 | 21 | 132 | 107 |
| MISSED | 63 | 28 | 35 | 142 | 93 | 316 | 320 |
| EXPIRED | 16 | 13 | 18 | 32 | 19 | 136 | 151 |
| STOPPED | 5 | 0 | 2 | 13 | 9 | 20 | 15 |
| HORIZON | 1 | 0 | 0 | 3 | 2 | 4 | 3 |
| TARGETS_DONE | 0 | 0 | 0 | 0 | 1 | 0 | 0 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 21% [18%, 24%] (n 1107) | 21% [17%, 26%] (n 511) | 15% [12%, 17%] (n 943) | 21% [19%, 23%] (n 2318) | 16% [14%, 18%] (n 1804) | 51% [49%, 53%] (n 2457) | 45% [43%, 47%] (n 2477) |
| REJECTED of MANIPULATED | 21% [16%, 27%] (n 235) | 23% [15%, 33%] (n 109) | 29% [22%, 37%] (n 137) | 25% [21%, 29%] (n 489) | 31% [26%, 36%] (n 282) | 27% [24%, 31%] (n 1260) | 30% [27%, 34%] (n 1121) |
| DISPLACED of REJECTED | 42% [29%, 55%] (n 50) | 28% [12%, 48%] (n 25) | 32% [21%, 45%] (n 40) | 60% [53%, 68%] (n 123) | 61% [51%, 72%] (n 88) | 25% [21%, 30%] (n 346) | 28% [23%, 34%] (n 341) |
| ENTERED of REJECTED and DISPLACED | 29% [10%, 50%] (n 21) | 0% [0%, 0%] (n 7) | 15% [0%, 38%] (n 13) | 22% [14%, 30%] (n 74) | 22% [12%, 34%] (n 54) | 27% [18%, 36%] (n 88) | 19% [12%, 26%] (n 97) |
| **Premise**: C1's opposite extreme before C2's extreme | 65% vs coin 47%: **18% [5%, 31%]** (n 46) | 67% vs coin 48%: **19% [0%, 37%]** (n 24) | 51% vs coin 45%: **6% [-8%, 19%]** (n 37) | 56% vs coin 46%: **10% [3%, 16%]** (n 105) | 53% vs coin 46%: **7% [-1%, 15%]** (n 76) | 47% vs coin 46%: **1% [-4%, 6%]** (n 282) | 53% vs coin 48%: **4% [-1%, 9%]** (n 285) |
| C2 had already reached C1's opposite extreme | 16% [7%, 25%] | 20% [4%, 36%] | 22% [9%, 38%] | 19% [12%, 26%] | 18% [10%, 28%] | 22% [17%, 27%] | 27% [23%, 32%] |
| TP1 before the stop | 33% [0%, 67%] (n 6) | – (n 0) | 0% [0%, 0%] (n 2) | 44% [19%, 69%] (n 16) | 33% [8%, 58%] (n 12) | 25% [9%, 43%] (n 24) | 22% [6%, 44%] (n 18) |
| -1 SD before the stop | 0% [0%, 0%] (n 6) | – (n 0) | 0% [0%, 0%] (n 2) | 6% [0%, 19%] (n 16) | 17% [0%, 42%] (n 12) | 4% [0%, 13%] (n 24) | 0% [0%, 0%] (n 18) |
| -2 SD before the stop | 0% [0%, 0%] (n 6) | – (n 0) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 16) | 8% [0%, 25%] (n 12) | 0% [0%, 0%] (n 24) | 0% [0%, 0%] (n 18) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 6) | – (n 0) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 16) | 8% [0%, 25%] (n 12) | 0% [0%, 0%] (n 24) | 0% [0%, 0%] (n 18) |
| R held to TP1 | +0.25 [-1.00, +1.77] (n 6) | – (n 0) | -1.00 [-1.00, -1.00] (n 2) | +1.13 [-0.02, +2.37] (n 16) | +0.92 [-0.46, +2.52] (n 12) | +0.22 [-0.38, +0.96] (n 24) | -0.01 [-0.67, +0.76] (n 18) |
| R held to -2 SD | -0.38 [-1.00, +0.40] (n 6) | – (n 0) | -1.00 [-1.00, -1.00] (n 2) | -0.19 [-1.00, +0.76] (n 16) | +0.07 [-1.00, +1.79] (n 12) | -0.41 [-0.91, +0.12] (n 24) | -0.40 [-1.00, +0.32] (n 18) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 75% vs 50%: 25% [7%, 41%] (n 20) | 4% [0%, 13%] (n 23) |
| LONDON | 38% vs 44%: -7% [-29%, 18%] (n 8) | 22% [0%, 56%] (n 9) |
| MIDNIGHT | 62% vs 42%: 21% [-15%, 57%] (n 8) | 12% [0%, 38%] (n 8) |
| PRE_NY | 70% vs 48%: 22% [-6%, 51%] (n 10) | 20% [0%, 44%] (n 10) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 44% vs 46%: -3% [-20%, 18%] (n 16) | 22% [6%, 41%] (n 18) |
| True | 77% vs 48%: 29% [10%, 43%] (n 30) | 6% [0%, 15%] (n 32) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 61% vs 43%: 18% [1%, 35%] (n 28) | 20% [6%, 37%] (n 30) |
| None | 73% vs 58%: 15% [-3%, 32%] (n 15) | 0% [0%, 0%] (n 16) |
| TIGHT_RANGE | 67% vs 35%: 32% [-43%, 90%] (n 3) | 0% [0%, 0%] (n 4) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 57%: 43% [23%, 62%] (n 6) | 0% [0%, 0%] (n 6) |
| OB | 0% vs 41%: -41% [-41%, -41%] (n 1) | 100% [100%, 100%] (n 1) |
| PDH | 75% vs 61%: 14% [-65%, 59%] (n 4) | 0% [0%, 0%] (n 4) |
| PMH | 0% vs 43%: -43% [-43%, -43%] (n 1) | 0% [0%, 0%] (n 1) |
| PWH | 100% vs 31%: 69% [69%, 69%] (n 1) | 0% [0%, 0%] (n 2) |
| SWING_HIGH | 50% vs 42%: 8% [-24%, 40%] (n 4) | 0% [0%, 0%] (n 6) |
| previous H4 high | 62% vs 45%: 17% [2%, 31%] (n 29) | 17% [3%, 32%] (n 30) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 55% vs 50%: 4% [-20%, 27%] (n 11) | 8% [0%, 21%] (n 13) |
| SHORT | 69% vs 46%: 22% [6%, 37%] (n 35) | 14% [3%, 26%] (n 37) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 59% vs 45%: 14% [-3%, 32%] (n 17) | 0% [0%, 0%] (n 18) |
| LONDON | 29% vs 43%: -15% [-36%, 12%] (n 7) | 12% [0%, 38%] (n 8) |
| MIDNIGHT | 57% vs 46%: 11% [-19%, 37%] (n 7) | 0% [0%, 0%] (n 8) |
| PRE_NY | 50% vs 47%: 3% [-21%, 29%] (n 6) | 17% [0%, 50%] (n 6) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 43% vs 41%: 2% [-18%, 25%] (n 14) | 6% [0%, 19%] (n 17) |
| True | 57% vs 48%: 9% [-7%, 24%] (n 23) | 4% [0%, 14%] (n 23) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 50% vs 43%: 7% [-7%, 20%] (n 28) | 3% [0%, 11%] (n 29) |
| None | 56% vs 50%: 5% [-19%, 32%] (n 9) | 10% [0%, 25%] (n 10) |
| TIGHT_RANGE | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 50%: 50% [35%, 76%] (n 3) | 0% [0%, 0%] (n 3) |
| PDH | 75% vs 60%: 15% [-13%, 43%] (n 4) | 0% [0%, 0%] (n 4) |
| PWH | 100% vs 59%: 41% [20%, 62%] (n 2) | 0% [0%, 0%] (n 2) |
| SWING_HIGH | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |
| previous H4 high | 39% vs 41%: -2% [-15%, 11%] (n 28) | 7% [0%, 17%] (n 30) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 41% vs 43%: -2% [-18%, 14%] (n 17) | 0% [0%, 0%] (n 20) |
| SHORT | 60% vs 47%: 13% [-7%, 31%] (n 20) | 10% [0%, 25%] (n 20) |

## GBPUSD

### model_d1: F D1, C H1, E M5

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 375 | 395 | 608 | 794 | 1150 | 1195 | 1193 |
| ARMED | 368 | 388 | 575 | 772 | 1073 | 1195 | 1193 |
| MANIPULATED | 57 | 47 | 38 | 112 | 73 | 637 | 530 |
| REJECTED | 16 | 11 | 19 | 44 | 34 | 229 | 218 |
| DISPLACED | 2 | 4 | 4 | 13 | 6 | 77 | 81 |
| IN_OTE | 0 | 0 | 0 | 2 | 0 | 8 | 8 |
| ENTERED | 0 | 0 | 0 | 2 | 0 | 5 | 6 |
| TP1 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SD_1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SD_2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 318 | 348 | 570 | 682 | 1077 | 558 | 663 |
| POI_FAILED | 4 | 5 | 0 | 7 | 1 | 0 | 0 |
| NO_REJECTION | 30 | 22 | 17 | 56 | 36 | 324 | 232 |
| RANGE_SPENT | 3 | 5 | 0 | 0 | 0 | 46 | 43 |
| TOO_LARGE | 3 | 2 | 0 | 0 | 0 | 9 | 5 |
| RETRACE_INVALID | 4 | 3 | 7 | 10 | 13 | 91 | 74 |
| MISSED | 1 | 2 | 2 | 10 | 6 | 52 | 56 |
| EXPIRED | 12 | 8 | 12 | 27 | 17 | 110 | 114 |
| STOPPED | 0 | 0 | 0 | 2 | 0 | 5 | 6 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 15% [10%, 21%] (n 368) | 12% [8%, 17%] (n 388) | 7% [4%, 9%] (n 575) | 15% [11%, 19%] (n 772) | 7% [5%, 9%] (n 1073) | 53% [50%, 56%] (n 1195) | 44% [42%, 47%] (n 1193) |
| REJECTED of MANIPULATED | 28% [18%, 39%] (n 57) | 23% [11%, 36%] (n 47) | 50% [37%, 66%] (n 38) | 39% [32%, 46%] (n 112) | 47% [35%, 58%] (n 73) | 36% [32%, 40%] (n 637) | 41% [36%, 46%] (n 530) |
| DISPLACED of REJECTED | 6% [0%, 20%] (n 16) | 9% [0%, 30%] (n 11) | 11% [0%, 26%] (n 19) | 18% [7%, 32%] (n 44) | 12% [3%, 24%] (n 34) | 18% [13%, 24%] (n 229) | 19% [14%, 25%] (n 218) |
| ENTERED of REJECTED and DISPLACED | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 2) | 25% [0%, 50%] (n 8) | 0% [0%, 0%] (n 4) | 12% [3%, 22%] (n 42) | 14% [5%, 25%] (n 42) |
| **Premise**: C1's opposite extreme before C2's extreme | 75% vs coin 55%: **20% [1%, 38%]** (n 16) | 73% vs coin 53%: **20% [3%, 41%]** (n 11) | 63% vs coin 52%: **12% [-8%, 30%]** (n 19) | 54% vs coin 45%: **8% [-3%, 21%]** (n 41) | 71% vs coin 46%: **24% [9%, 38%]** (n 34) | 56% vs coin 52%: **5% [-1%, 10%]** (n 229) | 59% vs coin 51%: **9% [3%, 14%]** (n 218) |
| C2 had already reached C1's opposite extreme | 31% [7%, 59%] | 45% [20%, 70%] | 32% [10%, 56%] | 23% [11%, 34%] | 26% [11%, 43%] | 34% [28%, 40%] | 33% [28%, 40%] |
| TP1 before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 20% [0%, 60%] (n 5) | 17% [0%, 50%] (n 6) |
| -1 SD before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 6) |
| -2 SD before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 6) |
| -2.5 SD before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 6) |
| R held to TP1 | – (n 0) | – (n 0) | – (n 0) | -1.00 [-1.00, -1.00] (n 2) | – (n 0) | -0.64 [-1.00, +0.07] (n 5) | -0.51 [-1.00, +0.48] (n 6) |
| R held to -2 SD | – (n 0) | – (n 0) | – (n 0) | -1.00 [-1.00, -1.00] (n 2) | – (n 0) | -1.00 [-1.00, -1.00] (n 5) | -1.00 [-1.00, -1.00] (n 6) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 78% vs 53%: 24% [1%, 45%] (n 9) | 0% [0%, 0%] (n 9) |
| LONDON | 100% vs 84%: 16% [16%, 16%] (n 1) | 0% [0%, 0%] (n 1) |
| MIDNIGHT | 50% vs 56%: -6% [-47%, 34%] (n 4) | 0% [0%, 0%] (n 4) |
| PRE_NY | 100% vs 46%: 54% [46%, 62%] (n 2) | 0% [0%, 0%] (n 2) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 75% vs 55%: 20% [1%, 38%] (n 16) | 0% [0%, 0%] (n 16) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 100% vs 57%: 43% [43%, 43%] (n 1) | 0% [0%, 0%] (n 1) |
| None | 85% vs 59%: 26% [6%, 47%] (n 13) | 0% [0%, 0%] (n 13) |
| TIGHT_RANGE | 0% vs 30%: -30% [-41%, -20%] (n 2) | 0% [0%, 0%] (n 2) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| OB | 67% vs 64%: 3% [-15%, 39%] (n 3) | 0% [0%, 0%] (n 3) |
| PMH | 100% vs 59%: 41% [30%, 62%] (n 3) | 0% [0%, 0%] (n 3) |
| PWH | 75% vs 52%: 23% [-20%, 52%] (n 4) | 0% [0%, 0%] (n 4) |
| previous D1 high | 67% vs 51%: 16% [-18%, 47%] (n 6) | 0% [0%, 0%] (n 6) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 67% vs 31%: 35% [-20%, 66%] (n 3) | 0% [0%, 0%] (n 3) |
| SHORT | 77% vs 61%: 16% [-3%, 36%] (n 13) | 0% [0%, 0%] (n 13) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 64% vs 50%: 14% [-6%, 37%] (n 14) | 0% [0%, 0%] (n 14) |
| LONDON | 100% vs 69%: 31% [16%, 46%] (n 3) | 0% [0%, 0%] (n 3) |
| MIDNIGHT | 0% vs 37%: -37% [-52%, -23%] (n 2) | 0% [0%, 0%] (n 2) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 59% vs 50%: 8% [-12%, 27%] (n 17) | 0% [0%, 0%] (n 17) |
| True | 100% vs 62%: 38% [30%, 46%] (n 2) | 0% [0%, 0%] (n 2) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 67% vs 54%: 12% [-48%, 43%] (n 3) | 0% [0%, 0%] (n 3) |
| None | 62% vs 50%: 11% [-12%, 35%] (n 13) | 0% [0%, 0%] (n 13) |
| TIGHT_RANGE | 67% vs 54%: 13% [-23%, 37%] (n 3) | 0% [0%, 0%] (n 3) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| PMH | 100% vs 70%: 30% [30%, 30%] (n 2) | 0% [0%, 0%] (n 2) |
| PWH | 80% vs 50%: 30% [3%, 51%] (n 5) | 0% [0%, 0%] (n 5) |
| previous D1 high | 50% vs 49%: 1% [-23%, 27%] (n 12) | 0% [0%, 0%] (n 12) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 60% vs 43%: 17% [-22%, 56%] (n 5) | 0% [0%, 0%] (n 5) |
| SHORT | 64% vs 55%: 10% [-12%, 30%] (n 14) | 0% [0%, 0%] (n 14) |

### model_h4: F H4, C M15, E M1

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 1928 | 1247 | 1953 | 4283 | 3658 | 4739 | 4708 |
| ARMED | 1858 | 1198 | 1809 | 4045 | 3391 | 4739 | 4708 |
| MANIPULATED | 283 | 216 | 189 | 587 | 344 | 2367 | 2184 |
| REJECTED | 66 | 56 | 61 | 190 | 113 | 868 | 866 |
| DISPLACED | 35 | 22 | 29 | 105 | 73 | 372 | 368 |
| IN_OTE | 7 | 1 | 4 | 13 | 9 | 44 | 42 |
| ENTERED | 7 | 1 | 4 | 12 | 8 | 39 | 36 |
| TP1 | 3 | 1 | 1 | 3 | 1 | 13 | 10 |
| SD_1 | 2 | 1 | 1 | 2 | 0 | 5 | 6 |
| SD_2 | 1 | 1 | 1 | 0 | 0 | 2 | 3 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 1645 | 1031 | 1764 | 3696 | 3314 | 2372 | 2524 |
| POI_FAILED | 31 | 29 | 15 | 66 | 33 | 0 | 0 |
| NO_REJECTION | 151 | 104 | 100 | 290 | 168 | 1162 | 987 |
| RANGE_SPENT | 20 | 19 | 1 | 0 | 0 | 167 | 169 |
| RETRACE_INVALID | 20 | 16 | 18 | 56 | 33 | 332 | 311 |
| MISSED | 20 | 13 | 21 | 75 | 53 | 277 | 284 |
| EXPIRED | 34 | 34 | 30 | 88 | 49 | 390 | 397 |
| STOPPED | 6 | 1 | 4 | 8 | 7 | 36 | 29 |
| HORIZON | 1 | 0 | 0 | 4 | 1 | 2 | 6 |
| TARGETS_DONE | 0 | 0 | 0 | 0 | 0 | 1 | 1 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 15% [13%, 17%] (n 1858) | 18% [16%, 21%] (n 1198) | 10% [9%, 12%] (n 1809) | 15% [13%, 16%] (n 4045) | 10% [9%, 12%] (n 3391) | 50% [48%, 52%] (n 4739) | 46% [45%, 48%] (n 4708) |
| REJECTED of MANIPULATED | 23% [18%, 29%] (n 283) | 26% [20%, 33%] (n 216) | 32% [26%, 38%] (n 189) | 32% [28%, 36%] (n 587) | 33% [28%, 38%] (n 344) | 37% [33%, 40%] (n 2367) | 40% [36%, 43%] (n 2184) |
| DISPLACED of REJECTED | 23% [11%, 37%] (n 66) | 18% [8%, 29%] (n 56) | 26% [16%, 38%] (n 61) | 31% [25%, 37%] (n 190) | 35% [28%, 41%] (n 113) | 20% [16%, 23%] (n 868) | 21% [18%, 24%] (n 866) |
| ENTERED of REJECTED and DISPLACED | 47% [23%, 67%] (n 15) | 10% [0%, 25%] (n 10) | 25% [7%, 44%] (n 16) | 21% [11%, 31%] (n 58) | 21% [10%, 33%] (n 39) | 23% [17%, 29%] (n 172) | 20% [15%, 26%] (n 178) |
| **Premise**: C1's opposite extreme before C2's extreme | 56% vs coin 55%: **0% [-10%, 11%]** (n 61) | 59% vs coin 57%: **3% [-8%, 13%]** (n 54) | 54% vs coin 52%: **3% [-9%, 14%]** (n 57) | 52% vs coin 52%: **-0% [-7%, 6%]** (n 176) | 51% vs coin 52%: **-1% [-10%, 7%]** (n 106) | 49% vs coin 48%: **1% [-2%, 4%]** (n 781) | 53% vs coin 50%: **3% [0%, 6%]** (n 787) |
| C2 had already reached C1's opposite extreme | 29% [17%, 40%] | 29% [17%, 41%] | 26% [17%, 37%] | 25% [20%, 31%] | 28% [20%, 37%] | 27% [24%, 30%] | 29% [26%, 32%] |
| TP1 before the stop | 43% [11%, 83%] (n 7) | 100% [100%, 100%] (n 1) | 25% [0%, 75%] (n 4) | 25% [7%, 55%] (n 12) | 12% [0%, 38%] (n 8) | 33% [18%, 49%] (n 39) | 28% [14%, 42%] (n 36) |
| -1 SD before the stop | 29% [0%, 67%] (n 7) | 100% [100%, 100%] (n 1) | 25% [0%, 75%] (n 4) | 17% [0%, 42%] (n 12) | 0% [0%, 0%] (n 8) | 13% [3%, 24%] (n 39) | 17% [5%, 30%] (n 36) |
| -2 SD before the stop | 14% [0%, 50%] (n 7) | 100% [100%, 100%] (n 1) | 25% [0%, 75%] (n 4) | 0% [0%, 0%] (n 12) | 0% [0%, 0%] (n 8) | 5% [0%, 13%] (n 39) | 8% [0%, 19%] (n 36) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 7) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 12) | 0% [0%, 0%] (n 8) | 3% [0%, 8%] (n 39) | 3% [0%, 9%] (n 36) |
| R held to TP1 | +0.41 [-0.82, +2.16] (n 7) | +3.92 [+3.92, +3.92] (n 1) | +0.23 [-1.00, +2.69] (n 4) | +0.10 [-0.65, +0.98] (n 12) | -0.40 [-1.00, +0.43] (n 8) | +0.10 [-0.39, +0.61] (n 39) | +0.14 [-0.38, +0.72] (n 36) |
| R held to -2 SD | +0.99 [-1.00, +4.34] (n 7) | +8.06 [+8.06, +8.06] (n 1) | +1.27 [-1.00, +5.80] (n 4) | -0.12 [-0.97, +0.96] (n 12) | -0.77 [-1.00, -0.31] (n 8) | -0.24 [-0.85, +0.51] (n 39) | +0.15 [-0.63, +1.11] (n 36) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 56% vs 48%: 7% [-10%, 28%] (n 18) | 10% [0%, 25%] (n 21) |
| LONDON | 53% vs 54%: -1% [-21%, 16%] (n 17) | 11% [0%, 29%] (n 19) |
| MIDNIGHT | 50% vs 47%: 3% [-26%, 30%] (n 10) | 10% [0%, 30%] (n 10) |
| PRE_NY | 62% vs 69%: -7% [-23%, 10%] (n 16) | 12% [0%, 29%] (n 16) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 56% vs 53%: 3% [-14%, 19%] (n 25) | 8% [0%, 21%] (n 26) |
| True | 56% vs 57%: -1% [-12%, 11%] (n 36) | 12% [3%, 23%] (n 40) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 69% vs 53%: 17% [-13%, 41%] (n 13) | 21% [0%, 43%] (n 14) |
| None | 48% vs 52%: -5% [-16%, 6%] (n 42) | 9% [2%, 17%] (n 46) |
| TIGHT_RANGE | 83% vs 82%: 2% [-37%, 20%] (n 6) | 0% [0%, 0%] (n 6) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 54%: 46% [31%, 62%] (n 2) | 0% [0%, 0%] (n 2) |
| OB | 40% vs 51%: -11% [-30%, 15%] (n 5) | 12% [0%, 50%] (n 8) |
| PDH | 33% vs 40%: -7% [-38%, 49%] (n 3) | 33% [0%, 100%] (n 3) |
| PMH | 50% vs 47%: 3% [3%, 3%] (n 2) | 0% [0%, 0%] (n 2) |
| PWH | 100% vs 58%: 42% [14%, 70%] (n 2) | 0% [0%, 0%] (n 3) |
| SWING_HIGH | 70% vs 59%: 11% [-9%, 36%] (n 10) | 20% [0%, 44%] (n 10) |
| previous H4 high | 51% vs 56%: -5% [-18%, 7%] (n 37) | 8% [0%, 17%] (n 38) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 47% vs 56%: -9% [-22%, 3%] (n 32) | 3% [0%, 10%] (n 34) |
| SHORT | 66% vs 54%: 11% [-5%, 28%] (n 29) | 19% [6%, 33%] (n 32) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 59% vs 54%: 4% [-15%, 22%] (n 29) | 6% [0%, 18%] (n 31) |
| LONDON | 45% vs 61%: -15% [-36%, 6%] (n 11) | 8% [0%, 25%] (n 13) |
| MIDNIGHT | 50% vs 33%: 17% [-9%, 49%] (n 8) | 0% [0%, 0%] (n 8) |
| PRE_NY | 56% vs 50%: 6% [-15%, 25%] (n 9) | 11% [0%, 38%] (n 9) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 50% vs 49%: 1% [-21%, 19%] (n 20) | 5% [0%, 16%] (n 22) |
| True | 57% vs 53%: 4% [-9%, 16%] (n 37) | 8% [0%, 18%] (n 39) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 62% vs 45%: 17% [-17%, 45%] (n 13) | 14% [0%, 33%] (n 14) |
| None | 51% vs 53%: -2% [-12%, 8%] (n 43) | 4% [0%, 11%] (n 46) |
| TIGHT_RANGE | 100% vs 91%: 9% [9%, 9%] (n 1) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 75% vs 73%: 2% [-24%, 24%] (n 4) | 0% [0%, 0%] (n 4) |
| OB | 50% vs 43%: 7% [-12%, 30%] (n 6) | 0% [0%, 0%] (n 6) |
| PDH | 29% vs 37%: -9% [-43%, 32%] (n 7) | 14% [0%, 43%] (n 7) |
| PWH | 67% vs 63%: 4% [-42%, 26%] (n 6) | 0% [0%, 0%] (n 6) |
| SWING_HIGH | 80% vs 40%: 40% [-26%, 93%] (n 5) | 29% [0%, 80%] (n 7) |
| previous H4 high | 52% vs 54%: -2% [-16%, 10%] (n 29) | 3% [0%, 11%] (n 31) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 44% vs 47%: -3% [-15%, 11%] (n 25) | 0% [0%, 0%] (n 25) |
| SHORT | 62% vs 56%: 7% [-12%, 23%] (n 32) | 11% [2%, 23%] (n 36) |

### model_h4_m30: F H4, C M30, E M1

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 961 | 606 | 972 | 2126 | 1823 | 2419 | 2445 |
| ARMED | 936 | 593 | 919 | 2039 | 1724 | 2419 | 2445 |
| MANIPULATED | 203 | 153 | 147 | 413 | 266 | 1259 | 1109 |
| REJECTED | 39 | 37 | 39 | 105 | 59 | 396 | 362 |
| DISPLACED | 51 | 38 | 40 | 144 | 96 | 377 | 367 |
| IN_OTE | 2 | 3 | 3 | 14 | 11 | 29 | 29 |
| ENTERED | 2 | 3 | 3 | 12 | 10 | 27 | 26 |
| TP1 | 0 | 2 | 2 | 1 | 4 | 5 | 6 |
| SD_1 | 0 | 0 | 0 | 1 | 2 | 0 | 0 |
| SD_2 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 758 | 453 | 825 | 1713 | 1557 | 1160 | 1336 |
| POI_FAILED | 31 | 25 | 13 | 68 | 31 | 0 | 0 |
| NO_REJECTION | 92 | 62 | 78 | 165 | 125 | 577 | 475 |
| RANGE_SPENT | 8 | 8 | 2 | 0 | 0 | 56 | 59 |
| TOO_LARGE | 1 | 1 | 0 | 0 | 0 | 2 | 1 |
| RETRACE_INVALID | 11 | 10 | 6 | 31 | 10 | 143 | 120 |
| MISSED | 42 | 31 | 28 | 117 | 74 | 304 | 293 |
| EXPIRED | 16 | 13 | 17 | 20 | 16 | 150 | 135 |
| STOPPED | 2 | 2 | 2 | 9 | 6 | 24 | 19 |
| HORIZON | 0 | 1 | 1 | 2 | 3 | 3 | 7 |
| TARGETS_DONE | 0 | 0 | 0 | 1 | 1 | 0 | 0 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 22% [19%, 24%] (n 936) | 26% [23%, 29%] (n 593) | 16% [13%, 19%] (n 919) | 20% [18%, 22%] (n 2039) | 15% [13%, 17%] (n 1724) | 52% [50%, 54%] (n 2419) | 45% [43%, 47%] (n 2445) |
| REJECTED of MANIPULATED | 19% [13%, 26%] (n 203) | 24% [17%, 32%] (n 153) | 27% [20%, 34%] (n 147) | 25% [21%, 31%] (n 413) | 22% [17%, 28%] (n 266) | 31% [28%, 35%] (n 1259) | 33% [29%, 36%] (n 1109) |
| DISPLACED of REJECTED | 31% [18%, 46%] (n 39) | 38% [22%, 56%] (n 37) | 46% [31%, 63%] (n 39) | 59% [50%, 70%] (n 105) | 61% [48%, 74%] (n 59) | 30% [25%, 35%] (n 396) | 33% [29%, 38%] (n 362) |
| ENTERED of REJECTED and DISPLACED | 17% [0%, 42%] (n 12) | 21% [7%, 43%] (n 14) | 17% [0%, 33%] (n 18) | 19% [10%, 30%] (n 62) | 28% [15%, 44%] (n 36) | 23% [16%, 31%] (n 117) | 21% [15%, 29%] (n 121) |
| **Premise**: C1's opposite extreme before C2's extreme | 58% vs coin 53%: **6% [-9%, 21%]** (n 36) | 48% vs coin 51%: **-2% [-16%, 15%]** (n 31) | 69% vs coin 52%: **18% [7%, 30%]** (n 36) | 51% vs coin 47%: **4% [-3%, 12%]** (n 88) | 60% vs coin 51%: **8% [-4%, 21%]** (n 52) | 48% vs coin 48%: **-0% [-5%, 5%]** (n 330) | 56% vs coin 49%: **7% [2%, 12%]** (n 310) |
| C2 had already reached C1's opposite extreme | 36% [22%, 50%] | 27% [15%, 38%] | 26% [13%, 37%] | 25% [18%, 33%] | 29% [17%, 40%] | 26% [21%, 31%] | 26% [20%, 31%] |
| TP1 before the stop | 0% [0%, 0%] (n 2) | 67% [0%, 100%] (n 3) | 67% [0%, 100%] (n 3) | 8% [0%, 27%] (n 12) | 40% [10%, 70%] (n 10) | 19% [7%, 35%] (n 27) | 23% [8%, 40%] (n 26) |
| -1 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 3) | 8% [0%, 27%] (n 12) | 20% [0%, 50%] (n 10) | 0% [0%, 0%] (n 27) | 0% [0%, 0%] (n 26) |
| -2 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 3) | 8% [0%, 27%] (n 12) | 10% [0%, 30%] (n 10) | 0% [0%, 0%] (n 27) | 0% [0%, 0%] (n 26) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 3) | 8% [0%, 27%] (n 12) | 10% [0%, 30%] (n 10) | 0% [0%, 0%] (n 27) | 0% [0%, 0%] (n 26) |
| R held to TP1 | -1.00 [-1.00, -1.00] (n 2) | +1.49 [-1.00, +3.75] (n 3) | +1.38 [-1.00, +3.42] (n 3) | -0.44 [-1.00, +0.52] (n 12) | +0.41 [-0.71, +1.63] (n 10) | -0.38 [-0.80, +0.15] (n 27) | -0.09 [-0.55, +0.43] (n 26) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 2) | +0.46 [-1.00, +3.38] (n 3) | +0.46 [-1.00, +3.38] (n 3) | -0.08 [-1.00, +1.70] (n 12) | +1.08 [-0.56, +3.23] (n 10) | -0.74 [-1.00, -0.40] (n 27) | -0.28 [-0.77, +0.27] (n 26) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 64% vs 56%: 7% [-15%, 30%] (n 11) | 8% [0%, 27%] (n 12) |
| LONDON | 62% vs 49%: 13% [-8%, 35%] (n 13) | 7% [0%, 23%] (n 14) |
| MIDNIGHT | 67% vs 48%: 18% [-43%, 66%] (n 3) | 0% [0%, 0%] (n 4) |
| PRE_NY | 44% vs 55%: -11% [-38%, 21%] (n 9) | 0% [0%, 0%] (n 9) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 54% vs 49%: 5% [-21%, 31%] (n 13) | 0% [0%, 0%] (n 14) |
| True | 61% vs 55%: 6% [-10%, 23%] (n 23) | 8% [0%, 19%] (n 25) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 67% vs 52%: 14% [-3%, 32%] (n 24) | 4% [0%, 13%] (n 26) |
| None | 50% vs 51%: -1% [-23%, 22%] (n 8) | 0% [0%, 0%] (n 9) |
| TIGHT_RANGE | 25% vs 58%: -33% [-67%, 23%] (n 4) | 25% [0%, 100%] (n 4) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 77%: 23% [23%, 23%] (n 1) | 0% [0%, 0%] (n 1) |
| OB | 50% vs 50%: -0% [-19%, 19%] (n 2) | 0% [0%, 0%] (n 3) |
| PDH | 100% vs 58%: 42% [42%, 42%] (n 1) | 0% [0%, 0%] (n 1) |
| PMH | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |
| PWH | 50% vs 38%: 12% [12%, 12%] (n 2) | 0% [0%, 0%] (n 2) |
| SWING_HIGH | 50% vs 42%: 8% [-25%, 44%] (n 6) | 0% [0%, 0%] (n 6) |
| previous H4 high | 58% vs 55%: 3% [-14%, 22%] (n 24) | 8% [0%, 19%] (n 25) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 50% vs 48%: 2% [-20%, 25%] (n 16) | 6% [0%, 16%] (n 17) |
| SHORT | 65% vs 56%: 9% [-8%, 30%] (n 20) | 5% [0%, 16%] (n 22) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 44%: 6% [-13%, 24%] (n 16) | 12% [0%, 31%] (n 16) |
| LONDON | 88% vs 60%: 28% [3%, 47%] (n 8) | 11% [0%, 33%] (n 9) |
| MIDNIGHT | 80% vs 67%: 13% [-13%, 42%] (n 5) | 0% [0%, 0%] (n 7) |
| PRE_NY | 86% vs 47%: 39% [11%, 61%] (n 7) | 0% [0%, 0%] (n 7) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 88% vs 45%: 42% [21%, 61%] (n 8) | 12% [0%, 38%] (n 8) |
| True | 64% vs 53%: 11% [-1%, 24%] (n 28) | 6% [0%, 16%] (n 31) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 80% vs 51%: 29% [16%, 43%] (n 25) | 4% [0%, 12%] (n 26) |
| None | 40% vs 50%: -10% [-28%, 12%] (n 10) | 17% [0%, 42%] (n 12) |
| TIGHT_RANGE | 100% vs 94%: 6% [6%, 6%] (n 1) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 69%: 31% [23%, 38%] (n 2) | 0% [0%, 0%] (n 2) |
| OB | 0% vs 14%: -14% [-14%, -14%] (n 1) | 0% [0%, 0%] (n 2) |
| PDH | 40% vs 45%: -5% [-39%, 28%] (n 5) | 20% [0%, 60%] (n 5) |
| PWH | 100% vs 77%: 23% [2%, 43%] (n 2) | 50% [0%, 100%] (n 2) |
| previous H4 high | 73% vs 51%: 22% [8%, 37%] (n 26) | 4% [0%, 12%] (n 28) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 58% vs 52%: 6% [-13%, 28%] (n 12) | 8% [0%, 25%] (n 13) |
| SHORT | 75% vs 51%: 24% [11%, 38%] (n 24) | 8% [0%, 19%] (n 26) |

## USDJPY

### model_d1: F D1, C H1, E M5

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 328 | 393 | 573 | 736 | 1170 | 1205 | 1219 |
| ARMED | 317 | 376 | 537 | 699 | 1033 | 1205 | 1219 |
| MANIPULATED | 28 | 36 | 42 | 67 | 83 | 616 | 519 |
| REJECTED | 6 | 9 | 13 | 23 | 38 | 192 | 184 |
| DISPLACED | 4 | 7 | 4 | 9 | 16 | 78 | 84 |
| IN_OTE | 0 | 0 | 0 | 2 | 0 | 8 | 10 |
| ENTERED | 0 | 0 | 0 | 2 | 0 | 8 | 7 |
| TP1 | 0 | 0 | 0 | 0 | 0 | 4 | 3 |
| SD_1 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SD_2 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 300 | 357 | 531 | 669 | 1087 | 589 | 700 |
| POI_FAILED | 5 | 2 | 4 | 6 | 4 | 0 | 0 |
| NO_REJECTION | 13 | 17 | 20 | 37 | 38 | 312 | 232 |
| RANGE_SPENT | 1 | 1 | 1 | 0 | 0 | 73 | 64 |
| TOO_LARGE | 1 | 3 | 3 | 0 | 0 | 11 | 10 |
| RETRACE_INVALID | 1 | 5 | 0 | 4 | 7 | 66 | 52 |
| MISSED | 3 | 4 | 4 | 6 | 14 | 53 | 62 |
| EXPIRED | 4 | 4 | 10 | 12 | 20 | 93 | 92 |
| STOPPED | 0 | 0 | 0 | 1 | 0 | 7 | 6 |
| HORIZON | 0 | 0 | 0 | 1 | 0 | 1 | 1 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 9% [5%, 14%] (n 317) | 10% [6%, 15%] (n 376) | 8% [5%, 11%] (n 537) | 10% [7%, 13%] (n 699) | 8% [6%, 11%] (n 1033) | 51% [48%, 55%] (n 1205) | 43% [40%, 45%] (n 1219) |
| REJECTED of MANIPULATED | 21% [5%, 34%] (n 28) | 25% [11%, 39%] (n 36) | 31% [16%, 48%] (n 42) | 34% [25%, 43%] (n 67) | 46% [37%, 56%] (n 83) | 31% [27%, 36%] (n 616) | 35% [30%, 41%] (n 519) |
| DISPLACED of REJECTED | 33% [0%, 75%] (n 6) | 11% [0%, 30%] (n 9) | 23% [0%, 50%] (n 13) | 35% [16%, 57%] (n 23) | 32% [18%, 47%] (n 38) | 22% [16%, 28%] (n 192) | 27% [21%, 34%] (n 184) |
| ENTERED of REJECTED and DISPLACED | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 3) | 25% [0%, 62%] (n 8) | 0% [0%, 0%] (n 12) | 19% [7%, 32%] (n 42) | 14% [4%, 24%] (n 50) |
| **Premise**: C1's opposite extreme before C2's extreme | 50% vs coin 49%: **1% [-11%, 19%]** (n 6) | 33% vs coin 48%: **-15% [-44%, 19%]** (n 9) | 92% vs coin 64%: **29% [15%, 45%]** (n 13) | 71% vs coin 62%: **10% [-1%, 22%]** (n 21) | 71% vs coin 60%: **11% [-0%, 21%]** (n 38) | 55% vs coin 52%: **4% [-1%, 9%]** (n 192) | 64% vs coin 53%: **11% [5%, 16%]** (n 184) |
| C2 had already reached C1's opposite extreme | 17% [0%, 43%] | 11% [0%, 38%] | 31% [8%, 57%] | 30% [11%, 50%] | 29% [15%, 44%] | 32% [25%, 38%] | 36% [29%, 43%] |
| TP1 before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 50% [12%, 88%] (n 8) | 43% [14%, 86%] (n 7) |
| -1 SD before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 12% [0%, 38%] (n 8) | 14% [0%, 43%] (n 7) |
| -2 SD before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 12% [0%, 38%] (n 8) | 14% [0%, 43%] (n 7) |
| -2.5 SD before the stop | – (n 0) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 2) | – (n 0) | 0% [0%, 0%] (n 8) | 0% [0%, 0%] (n 7) |
| R held to TP1 | – (n 0) | – (n 0) | – (n 0) | -0.06 [-1.00, +0.88] (n 2) | – (n 0) | +0.16 [-0.68, +0.99] (n 8) | +0.01 [-0.83, +1.08] (n 7) |
| R held to -2 SD | – (n 0) | – (n 0) | – (n 0) | -0.06 [-1.00, +0.88] (n 2) | – (n 0) | +0.31 [-1.00, +2.93] (n 8) | +0.50 [-1.00, +3.49] (n 7) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 58%: -8% [-65%, 32%] (n 4) | 0% [0%, 0%] (n 4) |
| LONDON | 100% vs 44%: 56% [56%, 56%] (n 1) | 0% [0%, 0%] (n 1) |
| MIDNIGHT | 0% vs 18%: -18% [-18%, -18%] (n 1) | 0% [0%, 0%] (n 1) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 40% vs 50%: -10% [-42%, 19%] (n 5) | 0% [0%, 0%] (n 5) |
| True | 100% vs 44%: 56% [56%, 56%] (n 1) | 0% [0%, 0%] (n 1) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 67% vs 59%: 7% [-5%, 32%] (n 3) | 0% [0%, 0%] (n 3) |
| None | 50% vs 50%: 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 2) |
| TIGHT_RANGE | 0% vs 18%: -18% [-18%, -18%] (n 1) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| previous D1 high | 50% vs 49%: 1% [-11%, 19%] (n 6) | 0% [0%, 0%] (n 6) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 67% vs 56%: 11% [0%, 32%] (n 3) | 0% [0%, 0%] (n 3) |
| SHORT | 33% vs 42%: -9% [-18%, -5%] (n 3) | 0% [0%, 0%] (n 3) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 90% vs 68%: 22% [-3%, 42%] (n 10) | 0% [0%, 0%] (n 10) |
| LONDON | 100% vs 59%: 41% [27%, 56%] (n 2) | 0% [0%, 0%] (n 2) |
| MIDNIGHT | 100% vs 30%: 70% [70%, 70%] (n 1) | 0% [0%, 0%] (n 1) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 91% vs 65%: 26% [3%, 46%] (n 11) | 0% [0%, 0%] (n 11) |
| True | 100% vs 59%: 41% [27%, 56%] (n 2) | 0% [0%, 0%] (n 2) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 75% vs 65%: 10% [-5%, 32%] (n 4) | 0% [0%, 0%] (n 4) |
| None | 100% vs 57%: 43% [27%, 58%] (n 7) | 0% [0%, 0%] (n 7) |
| TIGHT_RANGE | 100% vs 84%: 16% [2%, 30%] (n 2) | 0% [0%, 0%] (n 2) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| SWING_HIGH | 100% vs 98%: 2% [2%, 2%] (n 1) | 0% [0%, 0%] (n 1) |
| previous D1 high | 92% vs 61%: 31% [16%, 48%] (n 12) | 0% [0%, 0%] (n 12) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 100% vs 58%: 42% [27%, 60%] (n 7) | 0% [0%, 0%] (n 7) |
| SHORT | 83% vs 70%: 13% [0%, 32%] (n 6) | 0% [0%, 0%] (n 6) |

### model_h4: F H4, C M15, E M1

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 1703 | 1178 | 2167 | 3934 | 3759 | 4835 | 4864 |
| ARMED | 1575 | 1136 | 2036 | 3673 | 3551 | 4835 | 4864 |
| MANIPULATED | 203 | 169 | 203 | 502 | 390 | 2401 | 2267 |
| REJECTED | 39 | 51 | 49 | 146 | 114 | 776 | 750 |
| DISPLACED | 41 | 25 | 35 | 101 | 83 | 402 | 406 |
| IN_OTE | 4 | 2 | 5 | 11 | 9 | 35 | 34 |
| ENTERED | 4 | 2 | 4 | 10 | 9 | 30 | 27 |
| TP1 | 0 | 0 | 2 | 5 | 4 | 9 | 11 |
| SD_1 | 0 | 0 | 0 | 3 | 1 | 1 | 2 |
| SD_2 | 0 | 0 | 0 | 2 | 1 | 0 | 1 |
| SD_2.5 | 0 | 0 | 0 | 2 | 1 | 0 | 1 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 1500 | 1009 | 1964 | 3432 | 3369 | 2434 | 2597 |
| POI_FAILED | 25 | 15 | 28 | 59 | 44 | 0 | 0 |
| NO_REJECTION | 96 | 83 | 97 | 254 | 193 | 1157 | 1061 |
| RANGE_SPENT | 18 | 7 | 10 | 0 | 0 | 253 | 250 |
| TOO_LARGE | 0 | 0 | 0 | 0 | 0 | 1 | 2 |
| RETRACE_INVALID | 12 | 20 | 13 | 35 | 36 | 300 | 254 |
| MISSED | 30 | 20 | 25 | 79 | 65 | 311 | 312 |
| EXPIRED | 18 | 22 | 26 | 65 | 43 | 349 | 361 |
| STOPPED | 3 | 2 | 3 | 5 | 7 | 21 | 21 |
| HORIZON | 1 | 0 | 1 | 3 | 1 | 9 | 5 |
| TARGETS_DONE | 0 | 0 | 0 | 2 | 1 | 0 | 1 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 13% [11%, 15%] (n 1575) | 15% [13%, 17%] (n 1136) | 10% [8%, 12%] (n 2036) | 14% [12%, 15%] (n 3673) | 11% [10%, 12%] (n 3551) | 50% [48%, 51%] (n 4835) | 47% [45%, 48%] (n 4864) |
| REJECTED of MANIPULATED | 19% [13%, 26%] (n 203) | 30% [24%, 37%] (n 169) | 24% [17%, 31%] (n 203) | 29% [25%, 33%] (n 502) | 29% [25%, 33%] (n 390) | 32% [29%, 36%] (n 2401) | 33% [30%, 37%] (n 2267) |
| DISPLACED of REJECTED | 26% [14%, 38%] (n 39) | 20% [9%, 31%] (n 51) | 24% [13%, 36%] (n 49) | 38% [30%, 45%] (n 146) | 36% [28%, 45%] (n 114) | 19% [16%, 22%] (n 776) | 21% [18%, 24%] (n 750) |
| ENTERED of REJECTED and DISPLACED | 40% [9%, 78%] (n 10) | 20% [0%, 45%] (n 10) | 33% [9%, 58%] (n 12) | 18% [9%, 30%] (n 55) | 22% [11%, 35%] (n 41) | 20% [14%, 27%] (n 148) | 17% [12%, 23%] (n 157) |
| **Premise**: C1's opposite extreme before C2's extreme | 46% vs coin 52%: **-6% [-20%, 9%]** (n 37) | 49% vs coin 50%: **-1% [-11%, 10%]** (n 49) | 56% vs coin 50%: **6% [-5%, 18%]** (n 48) | 55% vs coin 47%: **8% [-1%, 16%]** (n 136) | 57% vs coin 48%: **9% [2%, 16%]** (n 111) | 48% vs coin 48%: **0% [-4%, 3%]** (n 711) | 56% vs coin 50%: **6% [3%, 10%]** (n 689) |
| C2 had already reached C1's opposite extreme | 13% [3%, 23%] | 20% [9%, 30%] | 27% [15%, 38%] | 15% [9%, 22%] | 20% [14%, 28%] | 26% [23%, 29%] | 29% [26%, 32%] |
| TP1 before the stop | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 2) | 50% [0%, 100%] (n 4) | 50% [18%, 89%] (n 10) | 44% [11%, 78%] (n 9) | 30% [16%, 46%] (n 30) | 41% [23%, 59%] (n 27) |
| -1 SD before the stop | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 4) | 30% [0%, 67%] (n 10) | 11% [0%, 33%] (n 9) | 3% [0%, 12%] (n 30) | 7% [0%, 18%] (n 27) |
| -2 SD before the stop | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 4) | 20% [0%, 44%] (n 10) | 11% [0%, 33%] (n 9) | 0% [0%, 0%] (n 30) | 4% [0%, 12%] (n 27) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 4) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 4) | 20% [0%, 44%] (n 10) | 11% [0%, 33%] (n 9) | 0% [0%, 0%] (n 30) | 4% [0%, 12%] (n 27) |
| R held to TP1 | +0.04 [-1.00, +2.12] (n 4) | -1.00 [-1.00, -1.00] (n 2) | +0.70 [-1.00, +2.62] (n 4) | +1.16 [-0.05, +2.54] (n 10) | +0.44 [-0.78, +1.81] (n 9) | +0.18 [-0.28, +0.62] (n 30) | +0.42 [-0.13, +1.01] (n 27) |
| R held to -2 SD | +0.04 [-1.00, +2.12] (n 4) | -1.00 [-1.00, -1.00] (n 2) | -0.50 [-1.00, +0.51] (n 4) | +1.67 [-0.36, +4.48] (n 10) | +0.24 [-1.00, +2.27] (n 9) | -0.18 [-0.64, +0.31] (n 30) | -0.12 [-0.79, +0.68] (n 27) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 57% vs 46%: 11% [-16%, 37%] (n 14) | 19% [0%, 38%] (n 16) |
| LONDON | 80% vs 57%: 23% [-10%, 53%] (n 5) | 0% [0%, 0%] (n 5) |
| MIDNIGHT | 33% vs 58%: -24% [-47%, -2%] (n 12) | 8% [0%, 21%] (n 12) |
| PRE_NY | 17% vs 47%: -31% [-42%, -23%] (n 6) | 0% [0%, 0%] (n 6) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 59% vs 51%: 8% [-11%, 29%] (n 17) | 6% [0%, 17%] (n 17) |
| True | 35% vs 52%: -17% [-39%, 6%] (n 20) | 14% [0%, 29%] (n 22) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 45% vs 48%: -3% [-28%, 26%] (n 11) | 8% [0%, 27%] (n 12) |
| None | 48% vs 54%: -6% [-22%, 10%] (n 25) | 12% [0%, 25%] (n 26) |
| TIGHT_RANGE | 0% vs 36%: -36% [-36%, -36%] (n 1) | 0% [0%, 0%] (n 1) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 40% vs 47%: -7% [-27%, 9%] (n 5) | 20% [0%, 50%] (n 5) |
| OB | 50% vs 52%: -2% [-46%, 43%] (n 4) | 25% [0%, 50%] (n 4) |
| PDH | 100% vs 59%: 41% [41%, 41%] (n 2) | 33% [0%, 100%] (n 3) |
| PWH | 0% vs 40%: -40% [-43%, -37%] (n 2) | 0% [0%, 0%] (n 2) |
| SWING_HIGH | 50% vs 37%: 13% [-38%, 64%] (n 2) | 0% [0%, 0%] (n 2) |
| previous H4 high | 45% vs 54%: -9% [-27%, 10%] (n 22) | 4% [0%, 13%] (n 23) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 55% vs 55%: -1% [-28%, 25%] (n 11) | 8% [0%, 30%] (n 12) |
| SHORT | 42% vs 50%: -8% [-23%, 11%] (n 26) | 11% [0%, 21%] (n 27) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 65% vs 50%: 14% [-6%, 35%] (n 17) | 12% [0%, 31%] (n 17) |
| LONDON | 57% vs 56%: 1% [-19%, 29%] (n 7) | 0% [0%, 0%] (n 8) |
| MIDNIGHT | 57% vs 56%: 1% [-24%, 26%] (n 14) | 7% [0%, 20%] (n 14) |
| PRE_NY | 40% vs 38%: 2% [-19%, 28%] (n 10) | 10% [0%, 33%] (n 10) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 57% vs 49%: 8% [-8%, 25%] (n 21) | 5% [0%, 14%] (n 22) |
| True | 56% vs 51%: 4% [-14%, 22%] (n 27) | 11% [0%, 23%] (n 27) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 50% vs 48%: 2% [-25%, 31%] (n 12) | 8% [0%, 25%] (n 13) |
| None | 53% vs 48%: 5% [-7%, 20%] (n 30) | 7% [0%, 16%] (n 30) |
| TIGHT_RANGE | 83% vs 66%: 17% [2%, 33%] (n 6) | 17% [0%, 50%] (n 6) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 75% vs 58%: 17% [-30%, 48%] (n 4) | 0% [0%, 0%] (n 4) |
| OB | 100% vs 56%: 44% [39%, 50%] (n 3) | 0% [0%, 0%] (n 3) |
| PDH | 50% vs 43%: 7% [-12%, 35%] (n 8) | 11% [0%, 43%] (n 9) |
| SWING_HIGH | 50% vs 43%: 7% [-37%, 52%] (n 2) | 50% [0%, 100%] (n 2) |
| previous H4 high | 52% vs 51%: 1% [-15%, 15%] (n 31) | 6% [0%, 16%] (n 31) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 50% vs 51%: -1% [-19%, 22%] (n 16) | 0% [0%, 0%] (n 16) |
| SHORT | 59% vs 50%: 10% [-5%, 24%] (n 32) | 12% [3%, 23%] (n 33) |

### model_h4_m30: F H4, C M30, E M1

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 839 | 579 | 1082 | 1958 | 1871 | 2465 | 2488 |
| ARMED | 796 | 563 | 1035 | 1867 | 1793 | 2465 | 2488 |
| MANIPULATED | 153 | 124 | 152 | 366 | 287 | 1227 | 1116 |
| REJECTED | 29 | 29 | 37 | 83 | 75 | 335 | 316 |
| DISPLACED | 47 | 33 | 49 | 137 | 136 | 408 | 380 |
| IN_OTE | 2 | 3 | 2 | 13 | 18 | 33 | 24 |
| ENTERED | 2 | 3 | 2 | 12 | 16 | 26 | 19 |
| TP1 | 0 | 0 | 1 | 2 | 6 | 2 | 5 |
| SD_1 | 0 | 0 | 0 | 1 | 0 | 2 | 2 |
| SD_2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 686 | 455 | 930 | 1592 | 1584 | 1238 | 1372 |
| POI_FAILED | 24 | 17 | 19 | 61 | 35 | 0 | 0 |
| NO_REJECTION | 57 | 51 | 52 | 145 | 110 | 557 | 473 |
| RANGE_SPENT | 13 | 7 | 5 | 0 | 0 | 84 | 74 |
| TOO_LARGE | 0 | 0 | 1 | 0 | 0 | 1 | 3 |
| RETRACE_INVALID | 7 | 6 | 9 | 23 | 11 | 121 | 101 |
| MISSED | 40 | 27 | 46 | 110 | 106 | 328 | 322 |
| EXPIRED | 10 | 13 | 18 | 15 | 9 | 110 | 124 |
| STOPPED | 1 | 2 | 1 | 10 | 15 | 18 | 14 |
| HORIZON | 1 | 1 | 1 | 2 | 1 | 8 | 5 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 19% [16%, 23%] (n 796) | 22% [18%, 25%] (n 563) | 15% [12%, 17%] (n 1035) | 20% [17%, 22%] (n 1867) | 16% [14%, 18%] (n 1793) | 50% [48%, 52%] (n 2465) | 45% [43%, 47%] (n 2488) |
| REJECTED of MANIPULATED | 19% [12%, 26%] (n 153) | 23% [15%, 32%] (n 124) | 24% [17%, 32%] (n 152) | 23% [19%, 26%] (n 366) | 26% [21%, 31%] (n 287) | 27% [24%, 31%] (n 1227) | 28% [25%, 32%] (n 1116) |
| DISPLACED of REJECTED | 41% [23%, 58%] (n 29) | 34% [14%, 55%] (n 29) | 30% [17%, 44%] (n 37) | 64% [54%, 74%] (n 83) | 83% [74%, 90%] (n 75) | 37% [31%, 43%] (n 335) | 34% [28%, 40%] (n 316) |
| ENTERED of REJECTED and DISPLACED | 17% [0%, 38%] (n 12) | 30% [9%, 50%] (n 10) | 18% [0%, 45%] (n 11) | 23% [11%, 35%] (n 53) | 26% [16%, 37%] (n 62) | 21% [14%, 28%] (n 124) | 18% [11%, 25%] (n 106) |
| **Premise**: C1's opposite extreme before C2's extreme | 52% vs coin 45%: **7% [-9%, 23%]** (n 25) | 54% vs coin 55%: **-1% [-13%, 11%]** (n 28) | 65% vs coin 54%: **11% [-1%, 23%]** (n 34) | 38% vs coin 41%: **-4% [-14%, 6%]** (n 69) | 57% vs coin 51%: **6% [-4%, 17%]** (n 68) | 49% vs coin 49%: **0% [-4%, 4%]** (n 276) | 57% vs coin 48%: **9% [4%, 14%]** (n 266) |
| C2 had already reached C1's opposite extreme | 14% [3%, 25%] | 31% [16%, 45%] | 30% [16%, 46%] | 12% [6%, 20%] | 23% [14%, 32%] | 28% [23%, 32%] | 29% [25%, 34%] |
| TP1 before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 3) | 50% [0%, 100%] (n 2) | 17% [0%, 36%] (n 12) | 38% [12%, 67%] (n 16) | 8% [0%, 20%] (n 26) | 26% [6%, 45%] (n 19) |
| -1 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 2) | 8% [0%, 27%] (n 12) | 0% [0%, 0%] (n 16) | 8% [0%, 20%] (n 26) | 11% [0%, 26%] (n 19) |
| -2 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 12) | 0% [0%, 0%] (n 16) | 0% [0%, 0%] (n 26) | 0% [0%, 0%] (n 19) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 3) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 12) | 0% [0%, 0%] (n 16) | 0% [0%, 0%] (n 26) | 0% [0%, 0%] (n 19) |
| R held to TP1 | -0.69 [-1.00, -0.37] (n 2) | -0.79 [-1.00, -0.37] (n 3) | -0.20 [-1.00, +0.60] (n 2) | -0.09 [-1.00, +0.87] (n 12) | +0.05 [-0.63, +0.92] (n 16) | -0.34 [-0.77, +0.22] (n 26) | -0.17 [-0.72, +0.50] (n 19) |
| R held to -2 SD | -0.69 [-1.00, -0.37] (n 2) | -0.79 [-1.00, -0.37] (n 3) | -0.19 [-1.00, +0.63] (n 2) | -0.50 [-1.00, +0.08] (n 12) | -0.90 [-1.00, -0.67] (n 16) | -0.18 [-0.74, +0.51] (n 26) | +0.08 [-0.72, +1.02] (n 19) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 51%: -1% [-32%, 25%] (n 8) | 8% [0%, 21%] (n 12) |
| LONDON | 60% vs 56%: 4% [-32%, 41%] (n 5) | 20% [0%, 60%] (n 5) |
| MIDNIGHT | 57% vs 33%: 25% [-17%, 58%] (n 7) | 0% [0%, 0%] (n 7) |
| PRE_NY | 40% vs 40%: -0% [-13%, 9%] (n 5) | 0% [0%, 0%] (n 5) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 60% vs 47%: 13% [-16%, 42%] (n 10) | 9% [0%, 25%] (n 11) |
| True | 47% vs 44%: 3% [-15%, 23%] (n 15) | 6% [0%, 14%] (n 18) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 57% vs 48%: 9% [-10%, 28%] (n 21) | 9% [0%, 20%] (n 23) |
| None | 25% vs 26%: -1% [-23%, 37%] (n 4) | 0% [0%, 0%] (n 6) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 45%: 55% [44%, 67%] (n 2) | 0% [0%, 0%] (n 3) |
| OB | 50% vs 35%: 15% [-19%, 48%] (n 2) | 0% [0%, 0%] (n 2) |
| PDH | 100% vs 45%: 55% [55%, 55%] (n 1) | 0% [0%, 0%] (n 2) |
| PWH | 50% vs 17%: 33% [-9%, 75%] (n 2) | 0% [0%, 0%] (n 3) |
| SWING_HIGH | – vs –: – (n 0) | 0% [0%, 0%] (n 1) |
| previous H4 high | 44% vs 49%: -4% [-24%, 15%] (n 18) | 11% [0%, 25%] (n 18) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 33% vs 42%: -8% [-28%, 2%] (n 9) | 10% [0%, 23%] (n 10) |
| SHORT | 62% vs 47%: 16% [-8%, 38%] (n 16) | 5% [0%, 16%] (n 19) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 73% vs 55%: 18% [-5%, 38%] (n 11) | 8% [0%, 23%] (n 13) |
| LONDON | 67% vs 50%: 16% [-17%, 49%] (n 6) | 0% [0%, 0%] (n 7) |
| MIDNIGHT | 50% vs 49%: 1% [-28%, 31%] (n 8) | 0% [0%, 0%] (n 8) |
| PRE_NY | 67% vs 58%: 9% [-2%, 23%] (n 9) | 11% [0%, 30%] (n 9) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 67% vs 47%: 20% [-3%, 42%] (n 9) | 0% [0%, 0%] (n 11) |
| True | 64% vs 56%: 8% [-5%, 21%] (n 25) | 8% [0%, 19%] (n 26) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 67% vs 48%: 19% [2%, 35%] (n 18) | 0% [0%, 0%] (n 20) |
| None | 25% vs 37%: -12% [-39%, 20%] (n 8) | 11% [0%, 33%] (n 9) |
| TIGHT_RANGE | 100% vs 84%: 16% [5%, 34%] (n 8) | 12% [0%, 38%] (n 8) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 56%: 44% [20%, 67%] (n 3) | 0% [0%, 0%] (n 3) |
| OB | 100% vs 52%: 48% [48%, 48%] (n 1) | 0% [0%, 0%] (n 1) |
| PDH | 100% vs 98%: 2% [1%, 3%] (n 2) | 0% [0%, 0%] (n 3) |
| PWH | 0% vs 9%: -9% [-9%, -9%] (n 1) | 0% [0%, 0%] (n 2) |
| SWING_HIGH | 100% vs 81%: 19% [18%, 21%] (n 2) | 50% [0%, 100%] (n 2) |
| previous H4 high | 56% vs 49%: 7% [-9%, 21%] (n 25) | 4% [0%, 11%] (n 26) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 50% vs 52%: -2% [-20%, 10%] (n 12) | 0% [0%, 0%] (n 13) |
| SHORT | 73% vs 54%: 18% [3%, 35%] (n 22) | 8% [0%, 19%] (n 24) |

## XAUUSD

### model_d1: F D1, C H1, E M5

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 326 | 461 | 485 | 652 | 947 | 1182 | 1198 |
| ARMED | 303 | 446 | 454 | 608 | 875 | 1182 | 1198 |
| MANIPULATED | 34 | 63 | 40 | 72 | 64 | 587 | 507 |
| REJECTED | 10 | 12 | 11 | 28 | 28 | 195 | 202 |
| DISPLACED | 4 | 15 | 6 | 13 | 14 | 80 | 98 |
| IN_OTE | 0 | 1 | 0 | 0 | 1 | 6 | 6 |
| ENTERED | 0 | 1 | 0 | 0 | 1 | 6 | 5 |
| TP1 | 0 | 1 | 0 | 0 | 0 | 3 | 3 |
| SD_1 | 0 | 1 | 0 | 0 | 0 | 1 | 1 |
| SD_2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 292 | 398 | 445 | 580 | 882 | 595 | 691 |
| POI_FAILED | 3 | 2 | 2 | 11 | 6 | 0 | 0 |
| NO_REJECTION | 12 | 33 | 19 | 29 | 26 | 289 | 196 |
| RANGE_SPENT | 7 | 7 | 4 | 0 | 0 | 63 | 57 |
| TOO_LARGE | 0 | 1 | 0 | 0 | 0 | 7 | 4 |
| RETRACE_INVALID | 2 | 0 | 1 | 8 | 5 | 66 | 55 |
| MISSED | 3 | 12 | 5 | 10 | 8 | 59 | 75 |
| EXPIRED | 7 | 7 | 9 | 14 | 18 | 97 | 115 |
| STOPPED | 0 | 1 | 0 | 0 | 1 | 5 | 4 |
| HORIZON | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| UNFINISHED | 0 | 0 | 0 | 0 | 1 | 0 | 0 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 11% [6%, 17%] (n 303) | 14% [9%, 20%] (n 446) | 9% [5%, 13%] (n 454) | 12% [7%, 17%] (n 608) | 7% [5%, 10%] (n 875) | 50% [46%, 53%] (n 1182) | 42% [39%, 45%] (n 1198) |
| REJECTED of MANIPULATED | 29% [16%, 48%] (n 34) | 19% [10%, 30%] (n 63) | 28% [14%, 47%] (n 40) | 39% [28%, 51%] (n 72) | 44% [32%, 55%] (n 64) | 33% [29%, 38%] (n 587) | 40% [35%, 45%] (n 507) |
| DISPLACED of REJECTED | 10% [0%, 33%] (n 10) | 42% [17%, 67%] (n 12) | 18% [0%, 45%] (n 11) | 29% [8%, 48%] (n 28) | 36% [19%, 52%] (n 28) | 20% [14%, 26%] (n 195) | 21% [16%, 27%] (n 202) |
| ENTERED of REJECTED and DISPLACED | 0% [0%, 0%] (n 1) | 20% [0%, 60%] (n 5) | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 8) | 10% [0%, 33%] (n 10) | 15% [5%, 28%] (n 39) | 12% [2%, 22%] (n 43) |
| **Premise**: C1's opposite extreme before C2's extreme | 60% vs coin 47%: **13% [-16%, 43%]** (n 10) | 92% vs coin 58%: **33% [10%, 51%]** (n 12) | 91% vs coin 55%: **36% [16%, 55%]** (n 11) | 64% vs coin 52%: **12% [-5%, 30%]** (n 25) | 75% vs coin 54%: **21% [5%, 35%]** (n 28) | 54% vs coin 51%: **3% [-3%, 9%]** (n 195) | 68% vs coin 54%: **14% [8%, 19%]** (n 202) |
| C2 had already reached C1's opposite extreme | 30% [0%, 60%] | 25% [0%, 55%] | 27% [0%, 55%] | 29% [17%, 42%] | 29% [13%, 50%] | 34% [28%, 41%] | 37% [31%, 43%] |
| TP1 before the stop | – (n 0) | 100% [100%, 100%] (n 1) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 1) | 50% [17%, 83%] (n 6) | 60% [20%, 100%] (n 5) |
| -1 SD before the stop | – (n 0) | 100% [100%, 100%] (n 1) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 1) | 17% [0%, 50%] (n 6) | 20% [0%, 60%] (n 5) |
| -2 SD before the stop | – (n 0) | 0% [0%, 0%] (n 1) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 6) | 0% [0%, 0%] (n 5) |
| -2.5 SD before the stop | – (n 0) | 0% [0%, 0%] (n 1) | – (n 0) | – (n 0) | 0% [0%, 0%] (n 1) | 0% [0%, 0%] (n 6) | 0% [0%, 0%] (n 5) |
| R held to TP1 | – (n 0) | +2.66 [+2.66, +2.66] (n 1) | – (n 0) | – (n 0) | -1.00 [-1.00, -1.00] (n 1) | +0.28 [-0.69, +1.30] (n 6) | +0.42 [-0.63, +1.48] (n 5) |
| R held to -2 SD | – (n 0) | -1.00 [-1.00, -1.00] (n 1) | – (n 0) | – (n 0) | -1.00 [-1.00, -1.00] (n 1) | -0.23 [-1.00, +1.30] (n 6) | -0.08 [-1.00, +1.76] (n 5) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 33% vs 44%: -10% [-47%, 33%] (n 6) | 0% [0%, 0%] (n 6) |
| LONDON | 100% vs 17%: 83% [83%, 83%] (n 1) | 0% [0%, 0%] (n 1) |
| MIDNIGHT | 100% vs 65%: 35% [21%, 45%] (n 3) | 0% [0%, 0%] (n 3) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 60% vs 47%: 13% [-16%, 43%] (n 10) | 0% [0%, 0%] (n 10) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 0% vs 68%: -68% [-68%, -68%] (n 1) | 0% [0%, 0%] (n 1) |
| None | 86% vs 52%: 34% [8%, 69%] (n 7) | 0% [0%, 0%] (n 7) |
| TIGHT_RANGE | 0% vs 22%: -22% [-28%, -15%] (n 2) | 0% [0%, 0%] (n 2) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| previous D1 high | 60% vs 47%: 13% [-16%, 43%] (n 10) | 0% [0%, 0%] (n 10) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 50% vs 73%: -23% [-68%, 21%] (n 2) | 0% [0%, 0%] (n 2) |
| SHORT | 62% vs 41%: 22% [-6%, 58%] (n 8) | 0% [0%, 0%] (n 8) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 89% vs 58%: 31% [10%, 53%] (n 9) | 0% [0%, 0%] (n 9) |
| LONDON | 100% vs 17%: 83% [83%, 83%] (n 1) | 0% [0%, 0%] (n 1) |
| PRE_NY | 100% vs 70%: 30% [30%, 30%] (n 1) | 0% [0%, 0%] (n 1) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 91% vs 55%: 36% [16%, 55%] (n 11) | 0% [0%, 0%] (n 11) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 100% vs 90%: 10% [10%, 10%] (n 1) | 0% [0%, 0%] (n 1) |
| None | 100% vs 52%: 48% [26%, 69%] (n 7) | 0% [0%, 0%] (n 7) |
| TIGHT_RANGE | 67% vs 51%: 15% [-28%, 39%] (n 3) | 0% [0%, 0%] (n 3) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 100% vs 32%: 68% [68%, 68%] (n 1) | 0% [0%, 0%] (n 1) |
| OB | 100% vs 61%: 39% [39%, 39%] (n 1) | 0% [0%, 0%] (n 1) |
| SWING_HIGH | 100% vs 70%: 30% [30%, 30%] (n 1) | 0% [0%, 0%] (n 1) |
| previous D1 high | 88% vs 55%: 32% [6%, 58%] (n 8) | 0% [0%, 0%] (n 8) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 100% vs 75%: 25% [16%, 35%] (n 2) | 0% [0%, 0%] (n 2) |
| SHORT | 89% vs 51%: 38% [14%, 62%] (n 9) | 0% [0%, 0%] (n 9) |

### model_h4: F H4, C M15, E M1

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 1959 | 1072 | 1951 | 3965 | 3480 | 4703 | 4777 |
| ARMED | 1819 | 1048 | 1819 | 3679 | 3210 | 4703 | 4777 |
| MANIPULATED | 255 | 184 | 207 | 523 | 358 | 2320 | 2199 |
| REJECTED | 57 | 41 | 56 | 166 | 126 | 785 | 773 |
| DISPLACED | 42 | 23 | 25 | 86 | 62 | 355 | 373 |
| IN_OTE | 1 | 3 | 2 | 8 | 3 | 28 | 27 |
| ENTERED | 1 | 3 | 2 | 5 | 2 | 20 | 19 |
| TP1 | 0 | 1 | 1 | 1 | 0 | 4 | 7 |
| SD_1 | 0 | 1 | 1 | 0 | 0 | 2 | 5 |
| SD_2 | 0 | 1 | 1 | 0 | 0 | 2 | 4 |
| SD_2.5 | 0 | 1 | 1 | 0 | 0 | 2 | 4 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 1704 | 888 | 1744 | 3442 | 3122 | 2383 | 2578 |
| POI_FAILED | 29 | 22 | 20 | 74 | 39 | 0 | 0 |
| NO_REJECTION | 115 | 93 | 99 | 249 | 169 | 1091 | 972 |
| RANGE_SPENT | 25 | 18 | 19 | 0 | 0 | 257 | 263 |
| TOO_LARGE | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| RETRACE_INVALID | 16 | 15 | 11 | 48 | 36 | 281 | 241 |
| MISSED | 35 | 13 | 21 | 64 | 50 | 278 | 289 |
| EXPIRED | 34 | 20 | 35 | 83 | 62 | 392 | 414 |
| STOPPED | 0 | 1 | 1 | 4 | 2 | 12 | 10 |
| HORIZON | 1 | 1 | 0 | 1 | 0 | 6 | 5 |
| TARGETS_DONE | 0 | 1 | 1 | 0 | 0 | 2 | 4 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 14% [12%, 17%] (n 1819) | 18% [15%, 21%] (n 1048) | 11% [9%, 14%] (n 1819) | 14% [12%, 16%] (n 3679) | 11% [10%, 13%] (n 3210) | 49% [48%, 51%] (n 4703) | 46% [45%, 47%] (n 4777) |
| REJECTED of MANIPULATED | 22% [16%, 29%] (n 255) | 22% [16%, 30%] (n 184) | 27% [20%, 34%] (n 207) | 32% [29%, 35%] (n 523) | 35% [31%, 40%] (n 358) | 34% [30%, 38%] (n 2320) | 35% [31%, 39%] (n 2199) |
| DISPLACED of REJECTED | 14% [6%, 25%] (n 57) | 17% [7%, 31%] (n 41) | 18% [9%, 29%] (n 56) | 28% [22%, 35%] (n 166) | 27% [20%, 34%] (n 126) | 16% [13%, 19%] (n 785) | 18% [15%, 21%] (n 773) |
| ENTERED of REJECTED and DISPLACED | 12% [0%, 38%] (n 8) | 43% [14%, 86%] (n 7) | 20% [0%, 50%] (n 10) | 11% [2%, 20%] (n 47) | 6% [0%, 15%] (n 34) | 16% [10%, 22%] (n 128) | 14% [8%, 20%] (n 140) |
| **Premise**: C1's opposite extreme before C2's extreme | 55% vs coin 49%: **6% [-5%, 17%]** (n 51) | 52% vs coin 42%: **10% [-4%, 26%]** (n 33) | 68% vs coin 52%: **16% [3%, 28%]** (n 53) | 50% vs coin 50%: **-0% [-8%, 8%]** (n 147) | 57% vs coin 50%: **7% [-2%, 17%]** (n 115) | 51% vs coin 52%: **-0% [-4%, 3%]** (n 725) | 58% vs coin 53%: **5% [2%, 8%]** (n 711) |
| C2 had already reached C1's opposite extreme | 23% [12%, 34%] | 15% [4%, 27%] | 27% [17%, 37%] | 16% [10%, 22%] | 18% [12%, 25%] | 28% [25%, 31%] | 30% [27%, 34%] |
| TP1 before the stop | 0% [0%, 0%] (n 1) | 33% [0%, 100%] (n 3) | 50% [0%, 100%] (n 2) | 20% [0%, 60%] (n 5) | 0% [0%, 0%] (n 2) | 20% [5%, 40%] (n 20) | 37% [17%, 59%] (n 19) |
| -1 SD before the stop | 0% [0%, 0%] (n 1) | 33% [0%, 100%] (n 3) | 50% [0%, 100%] (n 2) | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 2) | 10% [0%, 25%] (n 20) | 26% [10%, 47%] (n 19) |
| -2 SD before the stop | 0% [0%, 0%] (n 1) | 33% [0%, 100%] (n 3) | 50% [0%, 100%] (n 2) | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 2) | 10% [0%, 25%] (n 20) | 21% [5%, 44%] (n 19) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 1) | 33% [0%, 100%] (n 3) | 50% [0%, 100%] (n 2) | 0% [0%, 0%] (n 5) | 0% [0%, 0%] (n 2) | 10% [0%, 25%] (n 20) | 21% [5%, 44%] (n 19) |
| R held to TP1 | +1.27 [+1.27, +1.27] (n 1) | +0.49 [-1.00, +1.27] (n 3) | +0.87 [-1.00, +2.75] (n 2) | -0.14 [-1.00, +0.77] (n 5) | -1.00 [-1.00, -1.00] (n 2) | +0.60 [-0.24, +1.46] (n 20) | +0.57 [-0.22, +1.43] (n 19) |
| R held to -2 SD | +1.27 [+1.27, +1.27] (n 1) | +2.99 [-1.00, +8.69] (n 3) | +3.76 [-1.00, +8.52] (n 2) | -0.55 [-1.00, +0.36] (n 5) | -1.00 [-1.00, -1.00] (n 2) | +0.81 [-0.35, +2.15] (n 20) | +1.76 [+0.18, +3.70] (n 19) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 50% vs 48%: 2% [-16%, 21%] (n 22) | 4% [0%, 13%] (n 26) |
| LONDON | 71% vs 62%: 9% [-35%, 43%] (n 7) | 0% [0%, 0%] (n 8) |
| MIDNIGHT | 50% vs 49%: 1% [-19%, 24%] (n 14) | 0% [0%, 0%] (n 15) |
| PRE_NY | 62% vs 39%: 23% [-5%, 45%] (n 8) | 0% [0%, 0%] (n 8) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 56% vs 54%: 2% [-22%, 22%] (n 18) | 4% [0%, 14%] (n 24) |
| True | 55% vs 46%: 8% [-5%, 21%] (n 33) | 0% [0%, 0%] (n 33) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 38% vs 43%: -5% [-30%, 21%] (n 13) | 0% [0%, 0%] (n 16) |
| None | 58% vs 48%: 10% [-4%, 24%] (n 31) | 3% [0%, 10%] (n 34) |
| TIGHT_RANGE | 71% vs 65%: 7% [-19%, 29%] (n 7) | 0% [0%, 0%] (n 7) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| FVG | 67% vs 69%: -2% [-36%, 28%] (n 3) | 0% [0%, 0%] (n 3) |
| OB | 67% vs 33%: 34% [-53%, 87%] (n 3) | 25% [0%, 75%] (n 4) |
| PDH | 50% vs 52%: -2% [-40%, 55%] (n 4) | 0% [0%, 0%] (n 5) |
| SWING_HIGH | 17% vs 43%: -26% [-42%, -1%] (n 6) | 0% [0%, 0%] (n 6) |
| previous H4 high | 60% vs 49%: 11% [-2%, 24%] (n 35) | 0% [0%, 0%] (n 39) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 52% vs 49%: 3% [-9%, 15%] (n 33) | 0% [0%, 0%] (n 35) |
| SHORT | 61% vs 49%: 12% [-10%, 34%] (n 18) | 5% [0%, 16%] (n 22) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 68% vs 50%: 18% [0%, 34%] (n 31) | 3% [0%, 10%] (n 31) |
| LONDON | 88% vs 73%: 15% [-8%, 29%] (n 8) | 0% [0%, 0%] (n 9) |
| MIDNIGHT | 50% vs 48%: 2% [-27%, 33%] (n 8) | 10% [0%, 30%] (n 10) |
| PRE_NY | 67% vs 44%: 23% [-13%, 50%] (n 6) | 0% [0%, 0%] (n 6) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 84% vs 58%: 26% [8%, 43%] (n 19) | 0% [0%, 0%] (n 21) |
| True | 59% vs 49%: 10% [-5%, 25%] (n 34) | 6% [0%, 15%] (n 35) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 71% vs 57%: 15% [-8%, 32%] (n 14) | 0% [0%, 0%] (n 15) |
| None | 67% vs 51%: 15% [0%, 30%] (n 36) | 5% [0%, 13%] (n 38) |
| TIGHT_RANGE | 67% vs 43%: 24% [-34%, 68%] (n 3) | 0% [0%, 0%] (n 3) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 100% vs 40%: 60% [60%, 60%] (n 1) | 0% [0%, 0%] (n 1) |
| FVG | 100% vs 55%: 45% [2%, 67%] (n 3) | 0% [0%, 0%] (n 4) |
| OB | 50% vs 42%: 8% [-53%, 69%] (n 2) | 0% [0%, 0%] (n 2) |
| PDH | 62% vs 49%: 13% [-26%, 48%] (n 8) | 0% [0%, 0%] (n 8) |
| PWH | 100% vs 57%: 43% [43%, 43%] (n 1) | 0% [0%, 0%] (n 1) |
| SWING_HIGH | 25% vs 37%: -12% [-29%, 13%] (n 4) | 0% [0%, 0%] (n 4) |
| previous H4 high | 71% vs 55%: 15% [1%, 29%] (n 34) | 6% [0%, 14%] (n 36) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 70% vs 55%: 15% [-2%, 30%] (n 23) | 0% [0%, 0%] (n 25) |
| SHORT | 67% vs 50%: 16% [-3%, 33%] (n 30) | 6% [0%, 17%] (n 31) |

### model_h4_m30: F H4, C M30, E M1

| State reached | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FRAMED | 975 | 537 | 985 | 1931 | 1716 | 2418 | 2485 |
| ARMED | 925 | 530 | 934 | 1826 | 1617 | 2418 | 2485 |
| MANIPULATED | 188 | 131 | 151 | 367 | 258 | 1149 | 1050 |
| REJECTED | 39 | 25 | 31 | 98 | 68 | 334 | 319 |
| DISPLACED | 62 | 34 | 46 | 137 | 98 | 336 | 335 |
| IN_OTE | 2 | 4 | 0 | 28 | 11 | 18 | 8 |
| ENTERED | 2 | 4 | 0 | 26 | 9 | 16 | 7 |
| TP1 | 0 | 0 | 0 | 8 | 4 | 1 | 1 |
| SD_1 | 0 | 0 | 0 | 4 | 2 | 1 | 1 |
| SD_2 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| SD_2.5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| How it ended | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NO_MANIPULATION | 787 | 406 | 834 | 1563 | 1458 | 1269 | 1435 |
| POI_FAILED | 31 | 25 | 24 | 71 | 43 | 0 | 0 |
| NO_REJECTION | 63 | 51 | 56 | 131 | 100 | 504 | 412 |
| RANGE_SPENT | 10 | 8 | 5 | 0 | 0 | 76 | 80 |
| TOO_LARGE | 0 | 0 | 0 | 0 | 0 | 1 | 2 |
| RETRACE_INVALID | 8 | 7 | 5 | 20 | 9 | 118 | 109 |
| MISSED | 56 | 26 | 43 | 93 | 73 | 288 | 296 |
| EXPIRED | 18 | 10 | 18 | 26 | 24 | 146 | 144 |
| STOPPED | 2 | 4 | 0 | 16 | 4 | 16 | 7 |
| HORIZON | 0 | 0 | 0 | 10 | 5 | 0 | 0 |
| UNFINISHED | 0 | 0 | 0 | 1 | 0 | 0 | 0 |

| Measure | + time + volatility, PROFILE thesis | + time + volatility, PREV_DAY thesis | + time + volatility, ORACLE (hindsight) | Model A, PROFILE thesis | Model A, ORACLE (hindsight) | CRT + time + volatility, PROFILE thesis | CRT + time + volatility, ORACLE (hindsight) |
|---|---|---|---|---|---|---|---|
| MANIPULATED of ARMED | 20% [17%, 24%] (n 925) | 25% [21%, 29%] (n 530) | 16% [14%, 19%] (n 934) | 20% [18%, 23%] (n 1826) | 16% [14%, 18%] (n 1617) | 48% [45%, 50%] (n 2418) | 42% [41%, 44%] (n 2485) |
| REJECTED of MANIPULATED | 21% [14%, 28%] (n 188) | 19% [12%, 28%] (n 131) | 21% [13%, 28%] (n 151) | 27% [23%, 31%] (n 367) | 26% [21%, 31%] (n 258) | 29% [25%, 33%] (n 1149) | 30% [26%, 34%] (n 1050) |
| DISPLACED of REJECTED | 36% [20%, 54%] (n 39) | 32% [12%, 55%] (n 25) | 29% [13%, 48%] (n 31) | 63% [54%, 73%] (n 98) | 62% [50%, 73%] (n 68) | 23% [18%, 28%] (n 334) | 23% [19%, 28%] (n 319) |
| ENTERED of REJECTED and DISPLACED | 14% [0%, 38%] (n 14) | 50% [20%, 86%] (n 8) | 0% [0%, 0%] (n 9) | 42% [28%, 56%] (n 62) | 21% [9%, 36%] (n 42) | 21% [13%, 29%] (n 77) | 9% [4%, 16%] (n 74) |
| **Premise**: C1's opposite extreme before C2's extreme | 62% vs coin 50%: **13% [-1%, 25%]** (n 32) | 53% vs coin 45%: **7% [-12%, 27%]** (n 19) | 70% vs coin 54%: **17% [3%, 31%]** (n 27) | 53% vs coin 48%: **5% [-4%, 15%]** (n 73) | 66% vs coin 55%: **11% [1%, 21%]** (n 53) | 54% vs coin 52%: **2% [-3%, 7%]** (n 278) | 61% vs coin 54%: **7% [3%, 12%]** (n 267) |
| C2 had already reached C1's opposite extreme | 21% [9%, 34%] | 16% [4%, 33%] | 32% [14%, 50%] | 15% [9%, 23%] | 21% [10%, 32%] | 32% [27%, 37%] | 33% [27%, 38%] |
| TP1 before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 4) | – (n 0) | 31% [13%, 50%] (n 26) | 44% [12%, 80%] (n 9) | 6% [0%, 19%] (n 16) | 14% [0%, 43%] (n 7) |
| -1 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 4) | – (n 0) | 15% [4%, 30%] (n 26) | 22% [0%, 45%] (n 9) | 6% [0%, 19%] (n 16) | 14% [0%, 43%] (n 7) |
| -2 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 4) | – (n 0) | 4% [0%, 12%] (n 26) | 11% [0%, 27%] (n 9) | 0% [0%, 0%] (n 16) | 0% [0%, 0%] (n 7) |
| -2.5 SD before the stop | 0% [0%, 0%] (n 2) | 0% [0%, 0%] (n 4) | – (n 0) | 0% [0%, 0%] (n 26) | 0% [0%, 0%] (n 9) | 0% [0%, 0%] (n 16) | 0% [0%, 0%] (n 7) |
| R held to TP1 | -1.00 [-1.00, -1.00] (n 2) | -1.00 [-1.00, -1.00] (n 4) | – (n 0) | +0.48 [-0.24, +1.34] (n 26) | +0.86 [-0.69, +2.41] (n 9) | -0.76 [-1.00, -0.28] (n 16) | -0.45 [-1.00, +0.65] (n 7) |
| R held to -2 SD | -1.00 [-1.00, -1.00] (n 2) | -1.00 [-1.00, -1.00] (n 4) | – (n 0) | +0.63 [-0.37, +1.93] (n 26) | +1.88 [-0.68, +4.30] (n 9) | -1.00 [-1.00, -1.00] (n 16) | -1.00 [-1.00, -1.00] (n 7) |


**Breakdowns: + time + volatility, PROFILE thesis**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 67% vs 53%: 14% [-8%, 33%] (n 12) | 0% [0%, 0%] (n 16) |
| LONDON | 100% vs 68%: 32% [8%, 47%] (n 3) | 0% [0%, 0%] (n 3) |
| MIDNIGHT | 78% vs 50%: 28% [4%, 51%] (n 9) | 8% [0%, 27%] (n 12) |
| PRE_NY | 25% vs 38%: -13% [-41%, 24%] (n 8) | 12% [0%, 43%] (n 8) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 57% vs 44%: 13% [-20%, 45%] (n 7) | 0% [0%, 0%] (n 9) |
| True | 64% vs 51%: 13% [-3%, 28%] (n 25) | 7% [0%, 18%] (n 30) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 62% vs 46%: 17% [-4%, 38%] (n 16) | 0% [0%, 0%] (n 20) |
| None | 43% vs 39%: 4% [-23%, 31%] (n 7) | 10% [0%, 33%] (n 10) |
| TIGHT_RANGE | 78% vs 66%: 12% [-6%, 27%] (n 9) | 11% [0%, 33%] (n 9) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| OB | 100% vs 54%: 46% [46%, 46%] (n 1) | 0% [0%, 0%] (n 1) |
| SWING_HIGH | 33% vs 38%: -5% [-28%, 19%] (n 6) | 12% [0%, 43%] (n 8) |
| previous H4 high | 68% vs 52%: 16% [-0%, 30%] (n 25) | 3% [0%, 11%] (n 30) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 62% vs 52%: 10% [-6%, 25%] (n 21) | 8% [0%, 23%] (n 24) |
| SHORT | 64% vs 46%: 18% [-3%, 42%] (n 11) | 0% [0%, 0%] (n 15) |


**Breakdowns: + time + volatility, ORACLE (hindsight)**


*C2's phase of the day (MA-D13)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| ASIA | 91% vs 64%: 27% [6%, 42%] (n 11) | 0% [0%, 0%] (n 13) |
| LONDON | 29% vs 41%: -13% [-33%, 15%] (n 7) | 0% [0%, 0%] (n 7) |
| MIDNIGHT | 100% vs 54%: 46% [21%, 71%] (n 4) | 0% [0%, 0%] (n 6) |
| PRE_NY | 60% vs 48%: 12% [-34%, 54%] (n 5) | 0% [0%, 0%] (n 5) |

*C2 in the trader's time window (MA-D9)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| False | 57% vs 38%: 19% [-15%, 50%] (n 7) | 0% [0%, 0%] (n 9) |
| True | 75% vs 59%: 16% [-2%, 33%] (n 20) | 0% [0%, 0%] (n 22) |

*Inducement (MA-D3)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| EQUAL_HIGHS | 63% vs 55%: 8% [-11%, 27%] (n 19) | 0% [0%, 0%] (n 20) |
| None | 80% vs 38%: 42% [13%, 74%] (n 5) | 0% [0%, 0%] (n 8) |
| TIGHT_RANGE | 100% vs 71%: 29% [21%, 40%] (n 3) | 0% [0%, 0%] (n 3) |

*The POI's kind (MA-D2)*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| BREAKER | 100% vs 54%: 46% [46%, 46%] (n 1) | 0% [0%, 0%] (n 1) |
| OB | 100% vs 54%: 46% [46%, 46%] (n 1) | 0% [0%, 0%] (n 1) |
| PDH | 60% vs 56%: 4% [-27%, 16%] (n 5) | 0% [0%, 0%] (n 5) |
| SWING_HIGH | 100% vs 62%: 38% [38%, 38%] (n 1) | 0% [0%, 0%] (n 1) |
| previous H4 high | 68% vs 53%: 16% [-1%, 33%] (n 19) | 0% [0%, 0%] (n 23) |

*Side*, among C2s that rejected:

| | Premise vs coin | Filled |
|---|---|---|
| LONG | 73% vs 58%: 15% [-12%, 37%] (n 11) | 0% [0%, 0%] (n 12) |
| SHORT | 69% vs 51%: 18% [2%, 37%] (n 16) | 0% [0%, 0%] (n 19) |
