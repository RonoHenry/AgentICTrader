# H-AO: Volume Profile as a filter and as an entry on V1

Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-09, f3efe2d) before its code. Machine v1. Not a try: the sides are hindsight. The volume is tick volume.

## The tuning (2021-22, 2023-24, July 2025 to June 2026)

V1 reproduces H-AN's table: yes.

**The pick: none.**

- EPOC: below V1 in every window no; ORACLE above zero a week yes; pooled -0.7 points under V1; keeps a quarter of V1's trades yes; does not qualify
- MT: below V1 in every window no; ORACLE above zero a week yes; pooled -1.3 points under V1; keeps a quarter of V1's trades yes; does not qualify
- NEAR_D: below V1 in every window no; ORACLE above zero a week yes; pooled -2.9 points under V1; keeps a quarter of V1's trades yes; does not qualify
- NEAR_W: below V1 in every window no; ORACLE above zero a week yes; pooled -2.1 points under V1; keeps a quarter of V1's trades yes; does not qualify
- PATH_W: below V1 in every window no; ORACLE above zero a week yes; pooled +0.2 points under V1; keeps a quarter of V1's trades yes; does not qualify
- POC_D: below V1 in every window no; ORACLE above zero a week yes; pooled -1.3 points under V1; keeps a quarter of V1's trades yes; does not qualify
- POC_W: below V1 in every window no; ORACLE above zero a week yes; pooled -1.9 points under V1; keeps a quarter of V1's trades yes; does not qualify
- VA_D: below V1 in every window no; ORACLE above zero a week yes; pooled +0.2 points under V1; keeps a quarter of V1's trades yes; does not qualify
- VA_W: below V1 in every window no; ORACLE above zero a week yes; pooled -5.6 points under V1; keeps a quarter of V1's trades yes; does not qualify

No variant qualifies: H-AO fails at the tuning stage and July to November 2026 stays unspent.

## Every variant

| Window | Variant | p a week | p a trade | ORACLE R a week | MIRROR R a week | RANDOM R a week | ORACLE R a trade | ORACLE win | trades a week (O / M) |
|---|---|---|---|---|---|---|---|---|---|
| 2021-22 | V1 | 58.3% | 49.4% | +0.74 | -1.04 | -0.08 | +0.84 | 22.8% | 0.88 / 1.26 |
| 2021-22 | POC_W | 62.4% | 46.7% | +0.51 | -0.84 | -0.05 | +0.91 | 24.5% | 0.56 / 1.06 |
| 2021-22 | VA_W | 60.1% | 39.6% | +0.39 | -0.59 | -0.14 | +1.15 | 24.5% | 0.34 / 0.78 |
| 2021-22 | NEAR_W | 64.5% | 60.5% | +0.33 | -0.60 | -0.09 | +0.53 | 19.7% | 0.62 / 0.73 |
| 2021-22 | PATH_W | 56.3% | 47.3% | +0.63 | -0.81 | -0.23 | +0.89 | 24.5% | 0.70 / 1.01 |
| 2021-22 | POC_D | 56.8% | 43.9% | +0.68 | -0.89 | -0.08 | +1.01 | 25.4% | 0.67 / 1.12 |
| 2021-22 | VA_D | 53.8% | 38.2% | +0.61 | -0.71 | -0.07 | +1.20 | 29.4% | 0.50 / 0.95 |
| 2021-22 | NEAR_D | 64.7% | 56.6% | +0.48 | -0.88 | -0.09 | +0.65 | 19.9% | 0.74 / 1.04 |
| 2021-22 | EPOC | 55.6% | 46.6% | +0.55 | -0.69 | +0.10 | +0.93 | 22.2% | 0.59 / 0.85 |
| 2021-22 | MT | 67.0% | 56.6% | +0.29 | -0.59 | -0.09 | +0.57 | 19.7% | 0.51 / 0.80 |
| 2023-24 | V1 | 50.0% | 42.9% | +0.74 | -0.74 | -0.04 | +0.98 | 28.7% | 0.76 / 1.01 |
| 2023-24 | POC_W | 54.2% | 41.4% | +0.49 | -0.58 | -0.04 | +1.02 | 28.4% | 0.48 / 0.81 |
| 2023-24 | VA_W | 54.1% | 35.1% | +0.39 | -0.46 | -0.03 | +1.38 | 31.6% | 0.28 / 0.62 |
| 2023-24 | NEAR_W | 49.7% | 47.8% | +0.40 | -0.40 | -0.07 | +0.76 | 26.4% | 0.53 / 0.57 |
| 2023-24 | PATH_W | 52.3% | 42.5% | +0.49 | -0.53 | -0.08 | +0.93 | 28.1% | 0.52 / 0.78 |
| 2023-24 | POC_D | 56.1% | 43.0% | +0.50 | -0.64 | -0.08 | +0.95 | 27.4% | 0.53 / 0.89 |
| 2023-24 | VA_D | 53.1% | 36.0% | +0.50 | -0.56 | -0.11 | +1.33 | 30.8% | 0.38 / 0.75 |
| 2023-24 | NEAR_D | 54.8% | 51.0% | +0.44 | -0.54 | -0.08 | +0.71 | 27.4% | 0.62 / 0.73 |
| 2023-24 | EPOC | 61.8% | 50.7% | +0.24 | -0.39 | -0.13 | +0.67 | 24.9% | 0.36 / 0.57 |
| 2023-24 | MT | 57.4% | 47.0% | +0.28 | -0.38 | -0.09 | +0.83 | 24.5% | 0.34 / 0.52 |
| 2025-26 | V1 | 58.8% | 54.1% | +0.80 | -1.14 | -0.08 | +0.68 | 19.0% | 1.17 / 1.41 |
| 2025-26 | POC_W | 54.5% | 45.2% | +0.67 | -0.80 | -0.02 | +0.83 | 18.3% | 0.80 / 1.17 |
| 2025-26 | VA_W | 72.3% | 58.6% | +0.27 | -0.70 | -0.17 | +0.55 | 17.2% | 0.48 / 0.89 |
| 2025-26 | NEAR_W | 59.6% | 59.6% | +0.45 | -0.66 | -0.12 | +0.51 | 18.1% | 0.89 / 0.89 |
| 2025-26 | PATH_W | 56.0% | 49.3% | +0.75 | -0.96 | +0.06 | +0.83 | 23.1% | 0.90 / 1.18 |
| 2025-26 | POC_D | 56.2% | 47.5% | +0.79 | -1.01 | +0.02 | +0.86 | 20.4% | 0.92 / 1.30 |
| 2025-26 | VA_D | 58.2% | 45.0% | +0.58 | -0.81 | -0.02 | +0.87 | 19.4% | 0.66 / 1.13 |
| 2025-26 | NEAR_D | 54.5% | 50.5% | +0.72 | -0.86 | +0.00 | +0.71 | 18.6% | 1.02 / 1.19 |
| 2025-26 | EPOC | 51.7% | 45.2% | +0.87 | -0.93 | +0.32 | +1.02 | 15.7% | 0.85 / 1.10 |
| 2025-26 | MT | 49.3% | 43.8% | +0.94 | -0.92 | +0.30 | +1.15 | 17.9% | 0.82 / 1.02 |
| pooled | V1 | 54.9% | 48.0% | +0.76 | -0.92 | -0.06 | +0.85 | 24.0% | 0.89 / 1.18 |
| pooled | POC_W | 56.9% | 44.3% | +0.54 | -0.71 | -0.04 | +0.92 | 24.0% | 0.58 / 0.97 |
| pooled | VA_W | 60.5% | 42.2% | +0.36 | -0.55 | -0.10 | +1.04 | 24.8% | 0.35 / 0.73 |
| pooled | NEAR_W | 57.0% | 55.1% | +0.39 | -0.52 | -0.09 | +0.61 | 21.7% | 0.64 / 0.69 |
| pooled | PATH_W | 54.7% | 46.1% | +0.59 | -0.71 | -0.09 | +0.89 | 25.4% | 0.67 / 0.94 |
| pooled | POC_D | 56.3% | 44.7% | +0.62 | -0.80 | -0.05 | +0.94 | 24.5% | 0.66 / 1.05 |
| pooled | VA_D | 54.7% | 39.3% | +0.55 | -0.66 | -0.08 | +1.14 | 26.6% | 0.48 / 0.90 |
| pooled | NEAR_D | 57.9% | 52.7% | +0.52 | -0.71 | -0.06 | +0.69 | 22.4% | 0.75 / 0.93 |
| pooled | EPOC | 55.6% | 46.9% | +0.48 | -0.61 | +0.05 | +0.88 | 20.6% | 0.55 / 0.78 |
| pooled | MT | 56.2% | 47.5% | +0.44 | -0.57 | +0.00 | +0.87 | 20.5% | 0.51 / 0.72 |

## Orders (all windows)

| Variant | Arm | Orders | Limits | Filled | Expired | Cancelled | VOLUME skips |
|---|---|---|---|---|---|---|---|
| V1 | ORACLE | 1402 | 0 | 1402 | 0 | 0 | 0 |
| V1 | MIRROR | 1857 | 0 | 1857 | 0 | 0 | 0 |
| POC_W | ORACLE | 914 | 0 | 914 | 0 | 0 | 1947 |
| POC_W | MIRROR | 1524 | 0 | 1524 | 0 | 0 | 1940 |
| VA_W | ORACLE | 545 | 0 | 545 | 0 | 0 | 3582 |
| VA_W | MIRROR | 1148 | 0 | 1148 | 0 | 0 | 3855 |
| NEAR_W | ORACLE | 1003 | 0 | 1003 | 0 | 0 | 2042 |
| NEAR_W | MIRROR | 1090 | 0 | 1090 | 0 | 0 | 3880 |
| PATH_W | ORACLE | 1045 | 0 | 1045 | 0 | 0 | 1757 |
| PATH_W | MIRROR | 1482 | 0 | 1482 | 0 | 0 | 2188 |
| POC_D | ORACLE | 1037 | 0 | 1037 | 0 | 0 | 1755 |
| POC_D | MIRROR | 1661 | 0 | 1661 | 0 | 0 | 1398 |
| VA_D | ORACLE | 756 | 0 | 756 | 0 | 0 | 3170 |
| VA_D | MIRROR | 1418 | 0 | 1418 | 0 | 0 | 3080 |
| NEAR_D | ORACLE | 1180 | 0 | 1180 | 0 | 0 | 1063 |
| NEAR_D | MIRROR | 1463 | 0 | 1463 | 0 | 0 | 2101 |
| EPOC | ORACLE | 1033 | 946 | 858 | 162 | 13 | 0 |
| EPOC | MIRROR | 1372 | 1224 | 1225 | 144 | 3 | 0 |
| MT | ORACLE | 1008 | 1008 | 795 | 204 | 9 | 0 |
| MT | MIRROR | 1314 | 1314 | 1133 | 178 | 3 | 0 |

## Exits (all windows, ORACLE / MIRROR)

| Variant | ORACLE | MIRROR |
|---|---|---|
| V1 | {'SL': 1065, 'TP': 196, 'TIME': 141} | {'SL': 1737, 'TIME': 84, 'TP': 36} |
| POC_W | {'SL': 694, 'TP': 124, 'TIME': 96} | {'SL': 1414, 'TIME': 89, 'TP': 21} |
| VA_W | {'SL': 410, 'TIME': 72, 'TP': 63} | {'SL': 1059, 'TIME': 80, 'TP': 9} |
| NEAR_W | {'SL': 784, 'TP': 130, 'TIME': 89} | {'SL': 1021, 'TIME': 40, 'TP': 29} |
| PATH_W | {'SL': 775, 'TP': 141, 'TIME': 129} | {'SL': 1374, 'TIME': 86, 'TP': 22} |
| POC_D | {'SL': 781, 'TIME': 133, 'TP': 123} | {'SL': 1539, 'TIME': 100, 'TP': 22} |
| VA_D | {'SL': 550, 'TIME': 120, 'TP': 86} | {'SL': 1308, 'TIME': 99, 'TP': 11} |
| NEAR_D | {'SL': 916, 'TP': 144, 'TIME': 120} | {'SL': 1367, 'TIME': 68, 'TP': 28} |
| EPOC | {'SL': 677, 'TIME': 92, 'TP': 89} | {'SL': 1144, 'TIME': 68, 'TP': 13} |
| MT | {'SL': 630, 'TP': 91, 'TIME': 74} | {'SL': 1063, 'TIME': 60, 'TP': 10} |

Run time 27.8 minutes.
