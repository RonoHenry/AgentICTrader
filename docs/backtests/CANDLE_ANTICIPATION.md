# Candle Anticipation (liquidity-engine task 242)

Run 2026-10-14. Four runs on the same data, the same costs and the same pre-registered pass mark as the
baseline (`BASELINE.md`), compared with the setup-sequence runs `ec4876ba87a1` (WICK stop) and
`475491a89d91` (BODY stop).

- **Data:** Exness M1, EURUSD, GBPUSD, USDJPY and XAUUSD, 2025-01-01 to 2026-07-01, study `baseline-2026q3`.
  The hold-out (from 2026-07-07) was not used. This is the period the engine was developed on, so every
  breakdown below is exploration, not evidence.
- **The four runs** shared one engine pass (algo-backtester task 298):

| Label | Run | What changes from `base.toml` |
|---|---|---|
| base | `72b9ce1fd2ca` | Nothing: the new reference, the setup-sequence engine (WICK stop) |
| anticipation | `335eec26f2a7` | Trade only in the direction the D1 candle profile anticipates (`bias_mode = PROFILE`); the protected swing beyond the candle's open (`require_false_move`); the raid inside 01:00–13:00 New York (`time_window = MANIPULATION`); TP1 the nearer of SD 2.0 and the profile's draw (`target_mode = NEAREST`); a stop of at least two typical spreads |
| anticipation_body | `a11314f6c70c` | The same, with the stop behind the protected swing's body |
| anticipation_poi | `b17bcdc7925e` | The same as anticipation, with the protected swing inside an unfilled H4 or D1 PD array (LE-D14) |

## Result: no run passes (each meets 1 of 5)

| Run | Trades | Net R a trade [95% CI] | Profit factor | Max DD R | Cost share | Total R |
|---|---|---|---|---|---|---|
| base | 533 | −0.19 [−0.35, −0.01] | 0.76 | 113.3 | – | −101.0 |
| anticipation | 225 | +0.08 [−0.24, +0.43] | 1.09 | 42.1 | 55% | +17.1 |
| **anticipation_body** | 276 | **+0.12 [−0.20, +0.48]** | 1.15 | 39.4 | 51% | +33.8 |
| anticipation_poi | 218 | +0.11 [−0.20, +0.48] | 1.14 | 37.3 | 46% | +23.9 |
| WICK `ec4876ba87a1` | 537 | −0.16 [−0.33, +0.01] | 0.79 | 100.2 | – | −87.9 |
| BODY `475491a89d91` | 686 | −0.01 [−0.19, +0.17] | 0.98 | 44.0 | 110% | −8.8 |
| *Pass mark* | *≥ 100* | *> 0, CI low > 0* | *≥ 1.3* | *≤ 15* | *≤ 40%* | |

The anticipation rules removed about 58% of the trades and about two thirds of the drawdown, and turned
−0.19R a trade into +0.08 to +0.12R. That improvement isn't proven: every interval spans zero, the profit
factor stays below 1.3, the drawdown is 37–42R, and costs take about half of the gross.

## Why it improved: delivery, not the day's close

From each run's autopsy (`autopsy.md`; the failure modes of `AUTOPSY.md`, judged on the D1 candle's close):

| Run | With the day's close | WITH_ON_TIME | AGAINST_OTHER | AGAINST_EXPANSION |
|---|---|---|---|---|
| base | 45% | 97 trades, +1.67R | 104, −0.32R | 189, −0.90R |
| anticipation | 28% | 22, +2.06R | 77, **+0.75R** | 85, −0.82R |
| anticipation_body | 29% | 29, +1.47R | 101, **+0.96R** | 93, −0.90R |
| anticipation_poi | 28% | 21, +2.20R | 75, **+0.79R** | 82, −0.81R |

- **Fewer trades went the day's way, not more.** The profile's direction matched the D1 close less often than the base engine did.
- **They won anyway.** The nearer, realistic target (the profile's draw) was reached first, and the day closed the other way afterwards. That's the trader's point: judge a read by what it delivered to, not by the close (AR-D18).
- **What still loses:** 82–93 trades a run fade the day's expansion, at −0.8 to −0.9R each, about −75R a run. These are days the profile read the wrong side, which is what the trader's daily thesis has to fix.

## Breakdowns (exploration)

**By instrument (net R a trade, trades):**

| | base | anticipation | anticipation_body | anticipation_poi |
|---|---|---|---|---|
| EURUSD | −0.01 (124) | −0.03 (57) | +0.02 (66) | −0.02 (56) |
| GBPUSD | −0.16 (165) | −0.55 (59) | −0.27 (68) | −0.53 (56) |
| USDJPY | −0.43 (133) | +0.01 (50) | +0.01 (59) | +0.01 (50) |
| XAUUSD | −0.14 (111) | **+0.86 (59)** | **+0.60 (83)** | **+0.96 (56)** |

Gold carries the anticipation runs (anticipation: profit factor 2.16, 95% CI −0.02 to +1.83); GBPUSD loses in all of them.

**Fill against the midnight (00:00 New York) open:**

| | base | anticipation | anticipation_body | anticipation_poi |
|---|---|---|---|---|
| long below / short above (discount buys, premium sells) | −0.23 (335) | **+0.16 (169)** | **+0.34 (192)** | **+0.20 (164)** |
| long above / short below | −0.12 (198) | −0.19 (56) | −0.38 (84) | −0.16 (54) |

With the anticipated direction, buying below the true day open and selling above it pays, and the reverse loses. Without anticipation, neither side pays. This is the clearest lead in the breakdowns, and it belongs in a pre-registered test, not a rule.

**Stop distance in typical spreads (net R a trade, trades):**

| | base | anticipation | anticipation_body | anticipation_poi |
|---|---|---|---|---|
| < 2 | – | −0.13 (1) | −0.05 (1) | −0.13 (1) |
| 2–5 | −0.09 (16) | −0.19 (10) | −0.46 (33) | −0.19 (10) |
| 5–10 | −0.69 (55) | −0.14 (36) | +0.36 (49) | −0.12 (35) |
| 10–20 | +0.02 (136) | −0.20 (66) | −0.01 (87) | −0.17 (63) |
| > 20 | −0.20 (326) | **+0.33 (112)** | **+0.30 (106)** | **+0.37 (109)** |

**By trading day** (Monday opens Sunday 17:00 New York; net R a trade): the anticipation runs make their money on Friday (+0.27 to +0.42R) and lose on Thursday (−0.05 to −0.14R). At 40–60 trades a day per run, this is likely noise.

| | Mon | Tue | Wed | Thu | Fri |
|---|---|---|---|---|---|
| base | −0.17 | −0.17 | −0.02 | −0.33 | −0.36 |
| anticipation | −0.07 | +0.11 | +0.14 | −0.14 | +0.28 |
| anticipation_body | +0.42 | +0.04 | −0.01 | −0.05 | +0.27 |
| anticipation_poi | −0.05 | +0.13 | +0.14 | −0.14 | +0.42 |

**NoTrade decisions** (M15 closes the anticipation rules refused, from 146,737 decisions a run):

| Decision | base | anticipation | anticipation_body | anticipation_poi |
|---|---|---|---|---|
| AGAINST_PROFILE | – | 26,690 | 26,690 | 26,690 |
| OUTSIDE_WINDOW | – | 18,098 | 18,098 | 18,098 |
| NO_FALSE_MOVE | – | 2,619 | 2,619 | 2,619 |
| NO_ANTICIPATION | – | 278 | 278 | 278 |
| NO_POI | – | – | – | 83 |
| STOP_TOO_TIGHT | – | 5 | 120 | 5 |
| RR_BELOW_MIN | 13,267 | 3,054 | 2,294 | 3,024 |

**Swap:** none was charged. The cost spec has no swap in effect (the swap-free account, LE-D16), so each run's result without swap is the same as the result above.

## What it points to (task 243, decided with the trader)

1. **Ablations are cheap now.** Shared Phase A runs several variants for about the cost of one. Removing one anticipation rule at a time shows which carries the improvement: the nearer target, the direction filter, the window, or the false move.
2. **The midnight-open side** is worth a pre-registered hypothesis, on the exploration slice first: buy below the 00:00 open and sell above it, in the anticipated direction.
3. **The engine flaws found on 2026-10-13/14** are separate variants, each with a flag that defaults to today's behaviour:
   - FVG zones drawn over all three candles;
   - raids of any age counted as the false move;
   - M15-only execution.
4. **The losses that remain** (fading the day's expansion) are a direction-read problem. The trader's blind daily theses (market-narrative task 301) measure the read that should replace the profile's.
