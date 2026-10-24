# Model A's entry against the trader's two (task 363)

The Model A record (exploration slice; EURUSD, GBPUSD, USDJPY, XAUUSD). Every fill is held to the trading day's 17:00 New York close and pays the spread. R a trade at a fixed 3R target, and at Model A's TP1 (C1's opposite extreme) where it lies beyond the fill; 95% intervals resample trading dates. The arms are the controls: `random_poi_vt` draws the POI at random, `crt` reads the candles with no context.

## model_d1

| Arm | Entry | Fills | Win (3R) | R at 3R | 95% | R at TP1 | 95% |
|---|---|---|---|---|---|---|---|
| crt | A. OTE (Model A) | 167 | 20% | -0.28 | [-0.50, -0.04] | -0.32 | [-0.50, -0.13] |
| crt | C. re-anchored retest (0.5) | 966 | 32% | -0.07 | [-0.16, +0.01] | -0.10 | [-0.16, -0.04] |
| crt_vt | A. OTE (Model A) | 46 | 22% | -0.13 | [-0.57, +0.39] | +0.02 | [-0.39, +0.45] |
| crt_vt | C. re-anchored retest (0.5) | 435 | 33% | +0.02 | [-0.11, +0.16] | +0.00 | [-0.10, +0.11] |
| model | B1. at the level (near edge) | 1825 | 33% | -0.11 | [-0.22, +0.01] | -0.10 | [-0.15, -0.04] |
| model | B2. inside the level (midpoint) | 835 | 24% | -0.20 | [-0.34, -0.06] | -0.19 | [-0.31, -0.07] |
| model | C. re-anchored retest (0.5) | 103 | 27% | -0.06 | [-0.36, +0.24] | -0.22 | [-0.39, -0.04] |
| model_time | B1. at the level (near edge) | 828 | 28% | -0.18 | [-0.34, -0.03] | -0.12 | [-0.22, -0.03] |
| model_time | B2. inside the level (midpoint) | 380 | 20% | -0.32 | [-0.50, -0.13] | -0.25 | [-0.42, -0.07] |
| model_time | C. re-anchored retest (0.5) | 46 | 28% | +0.08 | [-0.36, +0.55] | -0.11 | [-0.38, +0.16] |
| model_vol | B1. at the level (near edge) | 1928 | 33% | -0.11 | [-0.21, -0.00] | -0.09 | [-0.15, -0.03] |
| model_vol | B2. inside the level (midpoint) | 882 | 25% | -0.19 | [-0.34, -0.05] | -0.19 | [-0.30, -0.07] |
| model_vol | C. re-anchored retest (0.5) | 83 | 27% | -0.15 | [-0.47, +0.19] | -0.18 | [-0.42, +0.07] |
| model_vt | B1. at the level (near edge) | 860 | 28% | -0.20 | [-0.35, -0.04] | -0.12 | [-0.21, -0.03] |
| model_vt | B2. inside the level (midpoint) | 395 | 20% | -0.32 | [-0.50, -0.13] | -0.25 | [-0.42, -0.08] |
| model_vt | C. re-anchored retest (0.5) | 47 | 21% | -0.26 | [-0.63, +0.14] | -0.23 | [-0.53, +0.10] |
| random_poi_vt | B1. at the level (near edge) | 1050 | 31% | -0.08 | [-0.19, +0.03] | -0.07 | [-0.13, -0.02] |
| random_poi_vt | B2. inside the level (midpoint) | 586 | 26% | -0.10 | [-0.24, +0.04] | -0.11 | [-0.22, -0.01] |
| random_poi_vt | C. re-anchored retest (0.5) | 48 | 23% | -0.13 | [-0.57, +0.35] | -0.20 | [-0.53, +0.15] |

## model_h4

| Arm | Entry | Fills | Win (3R) | R at 3R | 95% | R at TP1 | 95% |
|---|---|---|---|---|---|---|---|
| crt | A. OTE (Model A) | 1106 | 21% | -0.19 | [-0.28, -0.10] | -0.15 | [-0.24, -0.05] |
| crt | C. re-anchored retest (0.5) | 6208 | 26% | -0.13 | [-0.17, -0.09] | -0.16 | [-0.18, -0.13] |
| crt_vt | A. OTE (Model A) | 229 | 25% | -0.00 | [-0.22, +0.21] | -0.01 | [-0.23, +0.23] |
| crt_vt | C. re-anchored retest (0.5) | 2367 | 23% | -0.15 | [-0.21, -0.09] | -0.17 | [-0.21, -0.12] |
| model | A. OTE (Model A) | 104 | 22% | -0.14 | [-0.43, +0.19] | +0.03 | [-0.30, +0.40] |
| model | B1. at the level (near edge) | 8257 | 26% | -0.14 | [-0.20, -0.07] | -0.12 | [-0.16, -0.09] |
| model | B2. inside the level (midpoint) | 4325 | 21% | -0.22 | [-0.28, -0.16] | -0.23 | [-0.29, -0.17] |
| model | C. re-anchored retest (0.5) | 649 | 25% | -0.16 | [-0.28, -0.04] | -0.20 | [-0.28, -0.12] |
| model_time | A. OTE (Model A) | 45 | 24% | -0.02 | [-0.49, +0.51] | +0.14 | [-0.41, +0.81] |
| model_time | B1. at the level (near edge) | 3812 | 22% | -0.15 | [-0.24, -0.06] | -0.11 | [-0.16, -0.06] |
| model_time | B2. inside the level (midpoint) | 2028 | 21% | -0.18 | [-0.27, -0.08] | -0.22 | [-0.30, -0.14] |
| model_time | C. re-anchored retest (0.5) | 278 | 21% | -0.23 | [-0.41, -0.04] | -0.24 | [-0.37, -0.11] |
| model_vol | A. OTE (Model A) | 50 | 20% | -0.22 | [-0.61, +0.22] | -0.06 | [-0.57, +0.56] |
| model_vol | B1. at the level (near edge) | 8677 | 26% | -0.14 | [-0.20, -0.07] | -0.12 | [-0.16, -0.09] |
| model_vol | B2. inside the level (midpoint) | 4513 | 21% | -0.22 | [-0.28, -0.15] | -0.23 | [-0.28, -0.17] |
| model_vol | C. re-anchored retest (0.5) | 518 | 23% | -0.23 | [-0.36, -0.08] | -0.23 | [-0.32, -0.13] |
| model_vt | A. OTE (Model A) | 29 | 24% | -0.03 | [-0.60, +0.66] | +0.18 | [-0.58, +1.14] |
| model_vt | B1. at the level (near edge) | 3923 | 22% | -0.16 | [-0.24, -0.06] | -0.12 | [-0.17, -0.07] |
| model_vt | B2. inside the level (midpoint) | 2078 | 21% | -0.18 | [-0.28, -0.08] | -0.23 | [-0.31, -0.14] |
| model_vt | C. re-anchored retest (0.5) | 259 | 19% | -0.29 | [-0.47, -0.09] | -0.23 | [-0.36, -0.09] |
| random_poi_vt | A. OTE (Model A) | 21 | 24% | -0.05 | [-0.62, +0.71] | +0.33 | [-0.62, +1.56] |
| random_poi_vt | B1. at the level (near edge) | 4842 | 26% | -0.10 | [-0.17, -0.02] | -0.11 | [-0.14, -0.08] |
| random_poi_vt | B2. inside the level (midpoint) | 2845 | 21% | -0.18 | [-0.26, -0.10] | -0.18 | [-0.23, -0.12] |
| random_poi_vt | C. re-anchored retest (0.5) | 332 | 20% | -0.23 | [-0.39, -0.05] | -0.19 | [-0.31, -0.06] |

## model_h4_m30

| Arm | Entry | Fills | Win (3R) | R at 3R | 95% | R at TP1 | 95% |
|---|---|---|---|---|---|---|---|
| crt | A. OTE (Model A) | 944 | 21% | -0.17 | [-0.27, -0.07] | -0.21 | [-0.32, -0.10] |
| crt | C. re-anchored retest (0.5) | 6003 | 26% | -0.11 | [-0.15, -0.08] | -0.13 | [-0.15, -0.10] |
| crt_vt | A. OTE (Model A) | 165 | 16% | -0.35 | [-0.56, -0.13] | -0.38 | [-0.60, -0.16] |
| crt_vt | C. re-anchored retest (0.5) | 2469 | 23% | -0.13 | [-0.19, -0.07] | -0.15 | [-0.20, -0.11] |
| model | A. OTE (Model A) | 155 | 25% | -0.02 | [-0.28, +0.25] | -0.06 | [-0.36, +0.27] |
| model | B1. at the level (near edge) | 5857 | 26% | -0.13 | [-0.19, -0.07] | -0.13 | [-0.17, -0.08] |
| model | B2. inside the level (midpoint) | 3659 | 20% | -0.22 | [-0.28, -0.15] | -0.21 | [-0.28, -0.14] |
| model | C. re-anchored retest (0.5) | 978 | 26% | -0.13 | [-0.23, -0.03] | -0.14 | [-0.22, -0.07] |
| model_time | A. OTE (Model A) | 76 | 24% | -0.05 | [-0.41, +0.37] | -0.14 | [-0.51, +0.30] |
| model_time | B1. at the level (near edge) | 2756 | 23% | -0.13 | [-0.22, -0.03] | -0.10 | [-0.16, -0.04] |
| model_time | B2. inside the level (midpoint) | 1753 | 20% | -0.19 | [-0.28, -0.10] | -0.19 | [-0.29, -0.09] |
| model_time | C. re-anchored retest (0.5) | 459 | 23% | -0.17 | [-0.31, -0.03] | -0.16 | [-0.27, -0.05] |
| model_vol | A. OTE (Model A) | 51 | 25% | -0.04 | [-0.46, +0.42] | -0.21 | [-0.60, +0.23] |
| model_vol | B1. at the level (near edge) | 6086 | 26% | -0.13 | [-0.19, -0.07] | -0.13 | [-0.17, -0.08] |
| model_vol | B2. inside the level (midpoint) | 3781 | 20% | -0.22 | [-0.28, -0.16] | -0.22 | [-0.28, -0.14] |
| model_vol | C. re-anchored retest (0.5) | 898 | 25% | -0.15 | [-0.25, -0.05] | -0.14 | [-0.22, -0.06] |
| model_vt | A. OTE (Model A) | 29 | 21% | -0.17 | [-0.71, +0.43] | -0.44 | [-0.85, +0.07] |
| model_vt | B1. at the level (near edge) | 2819 | 23% | -0.12 | [-0.21, -0.03] | -0.10 | [-0.16, -0.03] |
| model_vt | B2. inside the level (midpoint) | 1781 | 20% | -0.19 | [-0.28, -0.09] | -0.19 | [-0.29, -0.09] |
| model_vt | C. re-anchored retest (0.5) | 446 | 22% | -0.18 | [-0.33, -0.03] | -0.14 | [-0.25, -0.02] |
| random_poi_vt | A. OTE (Model A) | 25 | 20% | -0.20 | [-0.83, +0.50] | -0.38 | [-0.81, +0.15] |
| random_poi_vt | B1. at the level (near edge) | 2575 | 27% | -0.07 | [-0.15, +0.02] | -0.08 | [-0.12, -0.03] |
| random_poi_vt | B2. inside the level (midpoint) | 1664 | 22% | -0.17 | [-0.26, -0.07] | -0.17 | [-0.25, -0.08] |
| random_poi_vt | C. re-anchored retest (0.5) | 400 | 22% | -0.14 | [-0.30, +0.03] | -0.16 | [-0.27, -0.03] |

