# Setup sequence: the rewritten grader against the baseline

Task 233 (`.kiro/specs/liquidity-engine/tasks.md`). It measures the grader
rewrite (liquidity-engine tasks 227–231) against the baseline (`BASELINE.md`),
on the same data, against the same pre-registered pass mark.

What changed in the grader:
- **Sweep gate.** A trade needs a raid of an opposite-side liquidity pool, a reclaim, a CISD in the trade direction, then a PD array that forms after the raid.
- **Entry array.** It's the array of that sequence.
- **Stop.** Behind the sequence's protected swing, with a buffer of 10% of the bar's range. `WICK` (the default) or `BODY`.
- **Counter-trend setups.** Allowed, but against the D1 bias they're capped at grade B.
- **Targets.** SD levels of the setup leg: TP1 at 2.0 SD, TP2 recorded at 2.5 SD. The trade exits at TP1.

## Result: both runs fail (1 of 5); BODY is at break-even

| Criterion | Pass | Baseline | WICK stop | BODY stop |
|---|---|---|---|---|
| Filled trades | ≥ 100 | 216 | 537 | 686 |
| Net expectancy (95% CI) | > 0R, CI low > 0R | −0.54R (−0.90 to −0.23) | −0.16R (−0.33 to +0.01) | −0.01R (−0.20 to +0.18) |
| Profit factor | ≥ 1.3 | 0.45 | 0.79 | 0.98 |
| Max drawdown | ≤ 15R | 117.4R (96%) | 100.2R (89%) | 44.0R (35%) |
| Cost share | ≤ 40% | 192% | none: gross R is negative | 110% |
| **Passed** | | 1 of 5 | 1 of 5 | 1 of 5 |

- **Overall.** The rewrite moves expectancy from −0.54R to −0.16R (WICK) and −0.01R (BODY), and cuts the drawdown from 117R to 44R. That's a large improvement, but neither run shows an edge: both confidence intervals include zero.
- **BODY.** The first run with a positive gross result (+0.13R a trade), but costs (0.14R) take all of it.

## The runs

- **Commands** (2026-10-08):
  - `python -m algo_backtester run config/backtests/base.toml` (WICK);
  - the same with `--variant stop_body` (BODY).
- **Run ids** (in `data/backtests/`, not committed):
  - WICK `ec4876ba87a1955e5f7d64f16813aaffb5f12954b40a21530a407bba5449cb22`;
  - BODY `475491a89d9156c6e398ffad9fbb71c1b901c61f31c18bc29c1dceec0cef7be9`.
- **Code:** commit `9a51304`, clean; engine fingerprint `41993b341a2f`.
- **Data, study and account:** as in the baseline.
  - Exness Standard M1, 2025-01-01 to 2026-07-01, EURUSD, GBPUSD, USDJPY and XAUUSD.
  - Study `baseline-2026q3`; **the hold-out is unused**.
  - $10,000 at 1% risk, no compounding, M15 entries, `min_rr` 3.0.
- **Run time:** Phase A recomputed (new engine): 70 min for WICK, and 106 min for BODY, which ran partly on battery.

## Counts

| | Baseline | WICK | BODY |
|---|---|---|---|
| NO_TRADE rows | 119,259 | 93,003 | 93,003 |
| …of which the reason names the missing raid | – | 3,658 | 3,658 |
| RR_BELOW_MIN rows | 379 | 13,200 | 8,066 |
| INVALID_STOP rows (stop not beyond the entry) | – | 3 | 503 |
| Orders placed | 1,445 | 973 | 1,217 |
| Filled | 216 (15%) | 539 (55%) | 689 (57%) |
| Never filled (expired) | 1,227 | 434 | 528 |
| Target hit / stopped / open at the end | 19 / 197 / 0 | 72 / 465 / 2 | 93 / 593 / 3 |
| Setups skipped: 3-trade concurrency cap | 192 | 932 | 1,410 |
| Setups skipped: daily / weekly drawdown limit | 995 / 1,773 | 797 / 1,178 | 322 / 496 |
| Average hold | 56 min | 2,395 min (median 397) | 2,271 min (median 263) |

The grade doesn't depend on the stop mode, so NO_TRADE is identical in both new runs. Every grade-B trade is a counter-trend setup capped at B. No A+ setup filled.

## Stops against the spread

Median stop distance of the orders, in pips (gold: 0.1):

| | EURUSD | GBPUSD | USDJPY | XAUUSD |
|---|---|---|---|---|
| Baseline | 3.2 | 4.0 | 4.6 | 25.0 |
| WICK | 23.6 | 23.2 | 34.7 | 181.5 |
| BODY | 22.3 | 21.9 | 32.3 | 147.3 |

Stops narrower than 2× the typical spread (EURUSD 0.8, GBPUSD 1.0, USDJPY 1.0 and XAUUSD 2.4 pips):

| | Orders | Filled | Net R of those filled |
|---|---|---|---|
| Baseline | 113 (7.8%) | 28 | −66.6R |
| WICK | 0 | 0 | – |
| BODY | 21 (1.7%) | 10 | −19.0R |

**BODY needs a minimum stop.** Without its 10 sub-spread trades, BODY is +0.02R a trade (PF 1.02).

## What the numbers say

**1. The mechanical failures of the baseline are gone.**
- **Costs:** 0.07R (WICK) and 0.14R (BODY) a trade, down from 1.14R.
- **Blow-ups:** no WICK loss is worse than −1.5R; BODY has 4 such losses (−13.2R in total).
- **Fills:** 55–57% of orders fill, up from 15%.
- **R:R:** it varies with the setup, no longer fixed at 1:5. Median about 1:5; quartiles 1:3.6–1:8.3 (WICK) and 1:3.9–1:10.2 (BODY).

**2. Far targets rarely hit, in both runs.**

| R:R | WICK n | WICK hit | WICK net | BODY n | BODY hit | BODY net |
|---|---|---|---|---|---|---|
| 3–4 | 182 | 22% | +0.07 | 194 | 18% | −0.04 |
| 4–5 | 91 | 15% | −0.05 | 116 | 22% | +0.35 |
| 5–7 | 89 | 11% | −0.16 | 113 | 14% | +0.11 |
| 7–10 | 74 | 7% | −0.32 | 95 | 13% | +0.34 |
| 10+ | 101 | **3%** | **−0.58** | 166 | **3%** | **−0.46** |

- **R:R of 10 or more** loses 59R (WICK) and 77R (BODY), the largest loss of any R:R band in each run.
- **Why:** a 2.0 SD projection of a long setup leg can land far beyond any logical target. The user's own targets are 2–2.5 SD, "often around 3–5R".

**3. Counter-trend setups are worse, in both runs.** Counter-trend means against the D1 bias, i.e. price vs the D1 open.

| | WICK | BODY |
|---|---|---|
| With the D1 bias (grade A) | −0.01R, n = 258 | +0.04R, n = 338 |
| Counter-trend (grade B) | −0.31R, n = 279 | −0.06R, n = 348 |

**4. Trades often go the right way first.**
- **Stopped trades that reached +1R before the stop:** 35% (WICK) and 32% (BODY).
- **Median MFE of a stopped trade:** +0.53R (WICK) and +0.49R (BODY), against +0.07R in the baseline.
- **Implication:** trade management (breakeven, partials) is a real lever. Fixed-R exits alone don't create an edge: exiting everything at +1R to +3R comes out between −0.03R and −0.14R a trade in both runs.

**5. Patterns that repeat in both runs.** These are leads, not findings (see the caveats):
- NY AM is the best killzone (WICK −0.01R, BODY +0.21R); London is weak (−0.12R, −0.17R).
- EURUSD is the best instrument (+0.01R, +0.30R); USDJPY the worst (−0.42R, −0.30R).
- Longs do better than shorts (WICK −0.08R vs −0.23R; BODY +0.08R vs −0.10R).

**6. The concurrency cap now binds.**
- It skipped 932 (WICK) and 1,410 (BODY) setups, against 192 in the baseline.
- Pending orders count toward the 3, and trades now last hours to days.
- Counter-trend trades take slots that with-trend setups could have used.

**7. Swap isn't modelled.** Trades now average about 40 hours, so overnight financing would lower these results somewhat.

## Timeframe alignment (WICK run)

**Method:**
- Every filled WICK trade was rebuilt at its decision time from the same stored data. All 537 setups matched their trade's direction.
- The engine then recorded, per timeframe:
  - price vs the period open (the engine's bias today);
  - the direction of the latest BOS/CHoCH, at any tier and at intermediate or long-term tiers.

| Trade direction vs… | With | Against |
|---|---|---|
| Today's D1 candle (price vs D1 open) | −0.01R, n = 258 | −0.31R, n = 279 |
| This week's candle (price vs W1 open) | −0.12R, n = 241 | −0.20R, n = 296 |
| D1 structure (latest intermediate BOS/CHoCH) | −0.25R, n = 265 | −0.12R, n = 265 |
| H4 structure (latest intermediate BOS/CHoCH) | −0.23R, n = 249 | −0.11R, n = 288 |

Layers agreeing with the trade (W1, D1 and H4 intermediate structure):

| 0 of 3 | 1 of 3 | 2 of 3 | 3 of 3 |
|---|---|---|---|
| +0.02R, n = 156 | −0.20R, n = 188 | −0.34R, n = 144 | −0.10R, n = 49 |

**What it shows:**
- **The daily candle matters.** Only the direction of today's D1 candle clearly separates results.
- **Structural alignment doesn't help.** Trades against the H4/D1 BOS/CHoCH structure did slightly better, and more agreeing layers didn't improve results. A raid followed by a CISD is a reversal entry, so higher-timeframe structure often still points the old way when the trade is taken. Alternatively, the engine's BOS/CHoCH isn't what the user means by order flow.
- **Bias alone won't create the edge.** Even the best bias filter leaves trades at break-even.

The user's own bias definition is the open question for the frame/execution spec.

## Caveats

- **In-sample.** These results come from the data the rewrite was designed on, and about 60 breakdown cells were inspected. At these sample sizes (CIs of ±0.2–0.5R per bucket), some cells look good by chance.
- **Leads, not findings.** Single cells (NY AM with-trend +0.27R, n = 82; with the D1 candle but against D1 structure +0.14R, n = 127) are not findings.
- **The hold-out (2026-07-07 on) is untouched.** It confirms or rejects a final version once, with `--final`.

## Proposed next variants (not in this task)

Each would be a backtest variant, compared with `ec4876ba87a1` and `475491a89d91` on the same pass mark:
1. **No counter-trend:** trade only with today's D1 candle (point 3, and the alignment table).
2. **Realistic targets:** TP1 at the nearer of 2 SD and the next opposing liquidity pool, or an R:R ceiling (point 2).
3. **Trade management:** breakeven at +1R and/or partials at 2 and 2.5 SD, in the fill model (point 4).
4. **Minimum stop:** at least k× the typical spread, for BODY above all.
5. **Swap** in the cost model (point 7).
6. **Risk limits:** an open-risk budget instead of a 3-trade count, with correlated groups and pending orders not counted until filled (point 6).
7. **Frame bias:** the user's definition, in the frame/execution spec.

## Review

The reports, with every trade drawn (the position tool, the raid, the protected swing and the M1 execution):
- `data/backtests/ec4876ba87a1…/report.html` (WICK)
- `data/backtests/475491a89d91…/report.html` (BODY)

Useful filters:
- outcome SL, then look at trades that went +1R first;
- decision RR_BELOW_MIN;
- grade B (counter-trend).
