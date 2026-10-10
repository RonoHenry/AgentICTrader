# Volatility profile

Where each instrument makes its range, by H4 candle, by New York hour and by weekday (AlgoResearch update 2026-10e, Requirement 21.3). Descriptive only: no verdict, no ledger row. Times are New York; the trading day opens at 17:00.

## EURUSD

128 trading dates.

**Data caveat:** 20% of the days' lows and 1% of their highs formed on a bar whose spread was 5x typical or more. Prices are bid, and the bid dips when the spread widens at the 17:00 rollover, so these are likely spread artefacts, not real extremes.

### By H4 candle

| H4 candle | Median range | Median share of the day's range |
|---|---|---|
| 17:00 | 0.00237 | 28% |
| 21:00 | 0.00228 | 27% |
| 01:00 | 0.003785 | 47% |
| 05:00 | 0.003745 | 43% |
| 09:00 | 0.00472 | 54% |
| 13:00 | 0.002465 | 30% |

### Hour of the day's high and low

Share of days whose high, and whose low, formed in each New York hour (hours with neither are left out).

| Hour | High | Low |
|---|---|---|
| 00:00 | 1% | 3% |
| 01:00 | 4% | 2% |
| 02:00 | 4% | 2% |
| 03:00 | 2% | 7% |
| 04:00 | 4% | 3% |
| 05:00 | 5% | 1% |
| 06:00 | 4% | 2% |
| 07:00 | 2% | 4% |
| 08:00 | 9% | 8% |
| 09:00 | 5% | 7% |
| 10:00 | 9% | 2% |
| 11:00 | 3% | 6% |
| 12:00 | 4% | 4% |
| 13:00 | 5% | 5% |
| 14:00 | 4% | 3% |
| 15:00 | 6% | 3% |
| 16:00 | 9% | 5% |
| 17:00 | 1% | 19% |
| 18:00 | 5% | 5% |
| 19:00 | 2% | 4% |
| 20:00 | 5% | 2% |
| 21:00 | 3% | 1% |
| 22:00 | 4% | 2% |
| 23:00 | 2% | 1% |

### By weekday

| Weekday | Days | Median day range | High most often in | Low most often in |
|---|---|---|---|---|
| Mon | 26 | 0.008555 | 05:00 (27%) | 17:00 (38%) |
| Tue | 25 | 0.00893 | 13:00 (36%) | 17:00 (20%) |
| Wed | 25 | 0.00846 | 05:00 (28%) | 13:00 (28%) |
| Thu | 26 | 0.00892 | 21:00 (23%) | 17:00 (35%) |
| Fri | 26 | 0.00831 | 09:00 (38%) | 17:00 (31%) |

## GBPUSD

128 trading dates.

**Data caveat:** 21% of the days' lows and 1% of their highs formed on a bar whose spread was 5x typical or more. Prices are bid, and the bid dips when the spread widens at the 17:00 rollover, so these are likely spread artefacts, not real extremes.

### By H4 candle

| H4 candle | Median range | Median share of the day's range |
|---|---|---|
| 17:00 | 0.002405 | 28% |
| 21:00 | 0.00256 | 27% |
| 01:00 | 0.004455 | 47% |
| 05:00 | 0.004145 | 45% |
| 09:00 | 0.00457 | 54% |
| 13:00 | 0.00287 | 31% |

### Hour of the day's high and low

Share of days whose high, and whose low, formed in each New York hour (hours with neither are left out).

| Hour | High | Low |
|---|---|---|
| 00:00 | 1% | 2% |
| 01:00 | 3% | 2% |
| 02:00 | 6% | 2% |
| 03:00 | 3% | 8% |
| 04:00 | 2% | 1% |
| 05:00 | 6% | 2% |
| 06:00 | 5% | 3% |
| 07:00 | 2% | 3% |
| 08:00 | 7% | 9% |
| 09:00 | 6% | 8% |
| 10:00 | 6% | 2% |
| 11:00 | 2% | 3% |
| 12:00 | 6% | 4% |
| 13:00 | 2% | 2% |
| 14:00 | 6% | 3% |
| 15:00 | 7% | 5% |
| 16:00 | 8% | 6% |
| 17:00 | 2% | 23% |
| 18:00 | 5% | 3% |
| 19:00 | 2% | 2% |
| 20:00 | 6% | 1% |
| 21:00 | 4% | 2% |
| 22:00 | 2% | 3% |
| 23:00 | 2% | 2% |

### By weekday

| Weekday | Days | Median day range | High most often in | Low most often in |
|---|---|---|---|---|
| Mon | 26 | 0.01037 | 05:00 (31%) | 17:00 (50%) |
| Tue | 25 | 0.00943 | 13:00 (32%) | 05:00 (28%) |
| Wed | 25 | 0.0087 | 05:00 (28%) | 09:00 (24%) |
| Thu | 26 | 0.00913 | 09:00 (38%) | 17:00 (35%) |
| Fri | 26 | 0.00797 | 09:00 (23%) | 17:00 (27%) |

## USDJPY

128 trading dates.

**Data caveat:** 18% of the days' lows and 1% of their highs formed on a bar whose spread was 5x typical or more. Prices are bid, and the bid dips when the spread widens at the 17:00 rollover, so these are likely spread artefacts, not real extremes.

### By H4 candle

| H4 candle | Median range | Median share of the day's range |
|---|---|---|
| 17:00 | 0.585 | 43% |
| 21:00 | 0.518 | 34% |
| 01:00 | 0.564 | 40% |
| 05:00 | 0.593 | 40% |
| 09:00 | 0.67 | 48% |
| 13:00 | 0.3915 | 26% |

### Hour of the day's high and low

Share of days whose high, and whose low, formed in each New York hour (hours with neither are left out).

| Hour | High | Low |
|---|---|---|
| 00:00 | 2% | 1% |
| 01:00 | 2% | 1% |
| 02:00 | 1% | 2% |
| 03:00 | 4% | 5% |
| 04:00 | 2% | 2% |
| 05:00 | 0% | 3% |
| 06:00 | 2% | 1% |
| 07:00 | 3% | 2% |
| 08:00 | 6% | 7% |
| 09:00 | 2% | 6% |
| 10:00 | 5% | 13% |
| 11:00 | 7% | 3% |
| 12:00 | 5% | 2% |
| 13:00 | 2% | 2% |
| 14:00 | 5% | 5% |
| 15:00 | 4% | 2% |
| 16:00 | 5% | 7% |
| 17:00 | 5% | 16% |
| 18:00 | 14% | 2% |
| 19:00 | 7% | 5% |
| 20:00 | 13% | 5% |
| 21:00 | 4% | 4% |
| 22:00 | 1% | 2% |

### By weekday

| Weekday | Days | Median day range | High most often in | Low most often in |
|---|---|---|---|---|
| Mon | 26 | 1.4505 | 17:00 (46%) | 09:00 (27%) |
| Tue | 25 | 1.397 | 17:00 (32%) | 17:00 (32%) |
| Wed | 25 | 1.355 | 17:00 (32%) | 17:00 (40%) |
| Thu | 26 | 1.469 | 17:00 (54%) | 09:00 (27%) |
| Fri | 26 | 1.447 | 17:00 (31%) | 17:00 (35%) |

## XAUUSD

127 trading dates.

### By H4 candle

| H4 candle | Median range | Median share of the day's range |
|---|---|---|
| 17:00 | 12.999 | 28% |
| 21:00 | 17.62 | 38% |
| 01:00 | 18.011 | 38% |
| 05:00 | 19.291 | 42% |
| 09:00 | 24.445 | 55% |
| 13:00 | 12.29 | 25% |

### Hour of the day's high and low

Share of days whose high, and whose low, formed in each New York hour (hours with neither are left out).

| Hour | High | Low |
|---|---|---|
| 00:00 | 2% | 1% |
| 01:00 | 2% | 2% |
| 02:00 | 2% | 3% |
| 03:00 | 1% | 4% |
| 04:00 | 3% | 1% |
| 05:00 | 3% | 2% |
| 06:00 | 2% | 2% |
| 07:00 | 2% | 2% |
| 08:00 | 3% | 6% |
| 09:00 | 6% | 11% |
| 10:00 | 10% | 9% |
| 11:00 | 2% | 3% |
| 12:00 | 6% | 2% |
| 13:00 | 3% | 3% |
| 14:00 | 1% | 3% |
| 15:00 | 8% | 3% |
| 16:00 | 11% | 5% |
| 18:00 | 9% | 13% |
| 19:00 | 3% | 6% |
| 20:00 | 8% | 6% |
| 21:00 | 6% | 7% |
| 22:00 | 5% | 5% |
| 23:00 | 1% | 2% |

### By weekday

| Weekday | Days | Median day range | High most often in | Low most often in |
|---|---|---|---|---|
| Mon | 26 | 45.64 | 13:00 (31%) | 17:00 (31%) |
| Tue | 25 | 47.202 | 13:00 (28%) | 09:00 (32%) |
| Wed | 25 | 39.472 | 13:00 (28%) | 13:00 (24%) |
| Thu | 26 | 47.675 | 21:00 (27%) | 09:00 (31%) |
| Fri | 25 | 48.05 | 09:00 (40%) | 09:00 (28%) |

## Inputs

- Snapshot: exness-2025-2026h1
- Dates: exploration slice, 2025-01-01 to 2025-07-01 (end exclusive)
- Code commit: `75743f9f0ed1e2bc016a5fdcf9de01e3282eef93`
