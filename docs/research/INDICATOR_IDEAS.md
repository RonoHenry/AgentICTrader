# Fractal + POI indicator ideas: exploration

**Task 266** (`.kiro/specs/algo-research`, update 2026-10c). **Exploration only:** the exploration slice, trading dates 2025-01-01 → 2025-07-01, about 128 dates per instrument (EURUSD, GBPUSD, USDJPY, XAUUSD). The confirmation slice has not been read. Nothing here is a finding until it passes there, pre-registered.

**How to read the tables**
- **Win rate** is the share of trades reaching the target before the stop. A trade still open at its time limit scores its fair chance from where it stopped.
- **Coin** is a driftless market's chance of the same win from the same entry, stop and target: the bar to beat. The **Δ** columns are win rate minus coin, with the 95% interval from resampling whole trading days. A **lower bound above 0** is what a pass needs.
- **Net R** is after Exness spreads and slippage. **Gross R** is before costs.

About 47 variants were run. At this confidence, one or two would clear their bar by chance alone. The section tables come from in-memory runs (4,000 resamples); the drafts table comes from the official `explore` command (10,000 resamples, its own seed), so the two can differ in the third decimal. That is why everything promising goes to the confirmation slice, one pre-registered test each.

## 1. The C1/C2 sweep alone

The indicator's core pattern: C2 trades beyond one side of C1, not the other, and closes back inside. The trade enters at C3's open, puts its stop at C2's extreme, targets C1's other side, and exits at C3's close (AR-D13).

| Timeframe | Trades | Win rate | Coin | Δ vs coin | Net R | Gross R |
|---|---|---|---|---|---|---|
| D1 | 119 | 0.483 | 0.431 | +0.052 [−0.015, +0.123] | +0.01 [−0.18, +0.21] | +0.10 |
| H4 | 880 | 0.444 | 0.423 | +0.021 [−0.004, +0.046] | −0.06 [−0.13, +0.02] | +0.03 |
| H1 | 3,962 | 0.411 | 0.409 | +0.002 [−0.011, +0.015] | −0.17 [−0.22, −0.13] | −0.01 |

The pattern is a coin flip on every timeframe, which reproduces the 2026-10-09 C3 test. On H1, costs alone lose 0.17R a trade, because the candles are small next to the spread.

## 2. With a bias

The same trades, kept only when a bias agrees with the trade's direction. Each "against" row is a control.

| Filter | H4 trades | H4 Δ vs coin | H4 net R | H1 Δ vs coin | H1 net R |
|---|---|---|---|---|---|
| With the W1 trend | 201 | +0.027 [−0.020, +0.077] | −0.08 | +0.004 | −0.16 |
| Against the W1 trend | 214 | +0.036 [−0.012, +0.083] | +0.02 | +0.009 | −0.18 |
| With the engine's anticipated direction | 362 | +0.015 [−0.021, +0.053] | −0.07 | +0.009 | −0.13 |
| Against it | 403 | +0.026 [−0.015, +0.069] | +0.01 | +0.001 | −0.17 |
| With the previous day's direction | 439 | +0.013 [−0.020, +0.050] | −0.08 | −0.008 | −0.20 |
| PO3 side: long below the D1 open, short above | 483 | −0.007 [−0.038, +0.026] | −0.12 | +0.001 | −0.17 |
| PO3 side and the anticipated direction | 230 | −0.012 [−0.055, +0.033] | −0.17 | +0.007 | −0.15 |
| Raid in 01:00–13:00 New York | 465 | +0.018 [−0.022, +0.060] | −0.04 | +0.004 | −0.14 |

None of the mechanical biases moves the coin flip. On H4 the "against" controls do no worse than the biases.

## 3. The fractal chain: a lower sweep in the direction of the higher one

| Chain | Trades | Win rate | Δ vs coin | Net R |
|---|---|---|---|---|
| H4 with the last D1 C2 sweep | 134 | 0.492 | +0.039 [−0.030, +0.114] | +0.06 [−0.16, +0.29] |
| H4 against it | 134 | 0.446 | +0.015 [−0.043, +0.071] | −0.04 |
| H1 with the last H4 C2 sweep | 552 | 0.433 | +0.006 [−0.029, +0.038] | −0.15 |
| H1 against it | 657 | 0.385 | −0.012 [−0.040, +0.016] | −0.23 |
| H1 with the last D1 C2 sweep | 612 | 0.431 | +0.011 [−0.019, +0.042] | −0.13 |
| H1 against it | 643 | 0.396 | −0.010 [−0.043, +0.024] | −0.20 |

In all three pairs, "with" beats "against" by 2–4 points. That is the right sign, but small, and no single row clears the coin flip. H4 inside D1 is the only chain that isn't eaten by costs.

## 4. SMT divergence (EURUSD with GBPUSD)

"SMT" keeps a sweep only when the partner did not take its own matching level.

| Event | Trades | Win rate | Δ vs coin | Net R |
|---|---|---|---|---|
| H4 sweep, SMT | 124 | 0.465 | +0.054 [−0.004, +0.113] | +0.02 [−0.15, +0.20] |
| H4 sweep, no SMT | 313 | 0.457 | +0.035 [−0.014, +0.082] | −0.01 |
| D1 sweep, SMT | 16 | 0.511 | +0.115 [−0.044, +0.296] | too few |
| H1 sweep, SMT | 545 | 0.368 | −0.002 [−0.028, +0.024] | −0.24 |
| Asian raid and reclaim, SMT | 31 | 0.097 | −0.086 [−0.172, +0.018] | −0.78 |
| Asian raid and reclaim, no SMT | 70 | 0.200 | −0.001 [−0.084, +0.089] | −0.23 |
| Asian raid and reclaim, all four instruments (the H002 draft) | 192 | 0.172 | −0.006 [−0.057, +0.049] | −0.29 |

The H4 SMT sweeps are the best race result here: +5 points, with a lower bound just below 0. Unconfirmed sweeps did about as well, though, so most of the 5 points may belong to H4 sweeps in general. The Asian raid with SMT did worse. The H002 draft, which is the same Asian raid trade, explores at a coin flip with −0.29R, so it will most likely fail.

## 5. Daily quarters (Quarterly Theory)

Where the day's extreme forms, against the same days with their M15 bars shuffled. The indicator's names for the quarters are Q1 = 18:00–00:00 accumulation, Q2 = 00:00–06:00 manipulation, Q3 = 06:00–12:00 distribution and Q4 = 12:00–18:00. Our quarter 0 also includes the 17:00 hour (AR-D14).

| Question | Days | Rate | Shuffled | Δ |
|---|---|---|---|---|
| Up days' low in 00:00–06:00 (indicator Q2) | 276 | 0.203 | 0.187 | +0.016 [−0.037, +0.070] |
| Down days' high in 00:00–06:00 | 234 | 0.205 | 0.205 | +0.000 [−0.058, +0.060] |
| **Up days' low in 06:00–12:00 (indicator Q3)** | 276 | 0.159 | 0.098 | **+0.059 [+0.018, +0.103]** |
| **Down days' high in 06:00–12:00** | 234 | 0.184 | 0.121 | **+0.064 [+0.013, +0.120]** |
| Up days' low in 17:00–00:00 (Asia) | 276 | 0.616 | 0.683 | −0.067 [−0.122, −0.013] |
| Down days' high in 17:00–00:00 | 234 | 0.573 | 0.629 | −0.056 [−0.122, +0.010] |
| For comparison, H004: up days' low in the 01:00/05:00/09:00 H4 candles | 276 | 0.337 | 0.257 | +0.080 [+0.025, +0.138] |

The false move of the day, the up day's low or the down day's high, forms in New York's morning more often than chance. It forms in the indicator's "manipulation" quarter only at chance. It forms during Asia less often than a random path would put it there. This is where the H004 timing excess lives.

## What it suggests

1. **The pattern doesn't pick the direction.** The C1/C2 sweep is a coin flip on its own on every timeframe. None of the biases the lab can compute changes that: the weekly trend, the engine's anticipation, the previous day, the side of the open, or the higher-timeframe sweep. That agrees with the C3 test and the hindsight split by the day's direction: the missing piece is still a better call on direction, and nothing tested here provides it.
2. **Two weak hints are worth one confirmation each:** the H4 sweep with SMT, and the H4 sweep in the direction of the last D1 sweep. Both are about +4–5 points with intervals that touch zero on this small slice. The confirmation slice has about twice the trades.
3. **Timing is real, but later than the indicator says.** The day's false move tends to complete in the 06:00–12:00 New York quarter. For entries, that argues for waiting through London rather than fading the first London sweep.
4. **H1 is too small for the spread.** Even a perfect coin flip loses about 0.15–0.2R a trade there after costs.

## Proposed for pre-registration (drafts, uncommitted)

The pass rules are the defaults (AR-D4): the lower bound of each comparison above 0, at least 100 events on 60 trading dates, and for races, mean net R above 0.

| Draft | Question | Exploration result (official `explore`) |
|---|---|---|
| `H007-quarter-timing.toml` | Up days' low and down days' high in 06:00–12:00 vs shuffled (2 tests) | PASS: +0.059 [+0.018, +0.103] and +0.064 [+0.013, +0.120] |
| `H008-crt-h4-smt.toml` | H4 sweep with SMT reaches C1's other side: vs coin, random times, net R > 0 | FAIL: +0.054 [−0.006, +0.113]; net +0.02R |
| `H009-crt-fractal-h4-d1.toml` | H4 sweep in the direction of the last D1 sweep: same rules | FAIL: +0.039 [−0.031, +0.113]; net +0.06R |

Not built (AR-D15): IC-CISD, the C3/C4 entry zones, and the London and New York session levels. They decide where to enter once the direction is known, and the direction is what's still missing.

## Reproduce

```
python -m algo_research build
python -m algo_research explore H007        # H008, H009: drafts in data/research/drafts/
```

The other variants were the same hypotheses with a different `where`, run in memory on the exploration slice with 4,000 resamples and 10 random-time draws per event.
