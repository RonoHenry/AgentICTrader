# Baseline: the current grader on Exness history

Task 211 (`.kiro/specs/algo-backtester/tasks.md`). The first measured run of
today's grader, with no strategy changes. Every later grader change is measured
against it.

## Pass mark (pre-registered 2026-10-07, before the run)

Agreed with the user before any result was seen. All five must hold, on the
base run's full range, net of spread, slippage and commission:

| Criterion | Pass |
|---|---|
| Filled trades | ≥ 100 |
| Net expectancy | > 0R, and the lower bound of its 95% bootstrap CI > 0R |
| Profit factor (after costs) | ≥ 1.3 |
| Max drawdown | ≤ 15R |
| Cost share | costs ≤ 40% of gross R |

1R is the entry-to-stop distance the order was sized on. The hold-out (the
study's last 3 months) is not used here; it is kept for one `--final` run.

## Result: fail (1 of 5)

| Criterion | Pass | Baseline | |
|---|---|---|---|
| Filled trades | ≥ 100 | 216 | pass |
| Net expectancy | > 0R, CI low > 0R | −0.54R (95% CI −0.89 to −0.23) | **fail** |
| Profit factor | ≥ 1.3 | 0.45 | **fail** |
| Max drawdown | ≤ 15R | 117.4R (a 96% drawdown) | **fail** |
| Cost share | ≤ 40% | 192% | **fail** |

The upper end of the confidence interval is below zero: the current grader
loses money on this data, and that is not a small-sample effect.

## The run

- **Command:** `python -m algo_backtester run config/backtests/base.toml` (2026-10-07, about 80 minutes cold; Phase A is now cached).
- **Run id:** `4de46a99e6a0131c58c6f2c1ee871a7908d0e69fb52c8554a58144d109011144`, in `data/backtests/` (not committed).
- **Code:** commit `60f9efb` plus this task's `allow_gaps` change; the manifest records it as dirty.
- **Data:** Exness Standard demo (`ExnessKE-MT5Trial9`), M1 with spread, loaded 2026-10-07 with `--years 3`.
  - Instruments: EURUSD, GBPUSD, USDJPY, XAUUSD.
  - Range: 2025-01-01 to 2026-07-01, about 786k M1 bars per FX pair and 746k for gold.
  - Every warm-up came from M1.
- **Study:** `baseline-2026q3`, hold-out from 2026-07-07.
- **Account:** $10,000, 1% risk per trade, no compounding. Strategy: the live defaults (M15 entries, `min_rr` 3.0, pending orders expire at the killzone's end).

### Data gaps allowed

`check-data` flagged gaps that the weekend-only schedule doesn't explain, so `[data] allow_gaps = true` is set in `base.toml`. All of them are real closures or short feed outages, and the manifest lists each one:
- **Gold:** early closes and closed days on US holidays (MLK Day, Presidents' Day, Good Friday, Memorial Day, Juneteenth, July 4, Labor Day, Thanksgiving), and the 2025-11-28 CME outage.
- **All four instruments:** 62 minutes on 2025-01-03 from 11:46 UTC.
- **EURUSD:** 42 minutes on 2025-04-02 from 21:17 UTC.

## What the numbers say

**1. There is no edge before costs either.** The overall gross figure (+0.59R a trade) is an artefact of the trades in point 2. Leaving those out:

| Filled trades | n | Target hit | Gross R | Cost R | Net R | PF |
|---|---|---|---|---|---|---|
| All | 216 | 8.8% | +0.59 | 1.14 | −0.54 | 0.45 |
| Stop ≥ 2× typical spread | 188 | 10.1% | −0.02 | 0.25 | −0.27 | 0.65 |
| Stop ≥ 4× typical spread | 136 | 10.3% | −0.06 | 0.19 | −0.25 | 0.68 |

- With a sane stop, the target is hit about 10% of the time. At that rate a trade needs about 1:9 just to break even before costs, and the grader's target is almost always 1:5.
- All four instruments look alike (target hit 7.5–10.9%, net −0.21 to −0.37R).
- Losing trades barely move into profit first: the median MFE of a stopped trade is +0.07R.

**2. Stops narrower than the spread cause the drawdown.** 28 filled trades had a stop under 2× the typical spread, some as small as 0.01 pip:
- None of the 28 reached its target, and together they lost 66.6R net.
- 1R on those trades is only a fraction of a pip, so the spread alone moves price through the stop. The "gross" R in the journal ignores the spread, which is why it can read high even on a stopped trade.
- The position is sized on that tiny distance (up to the 300-lot maximum), so a stop-out costs many R. Example: a USDJPY short on 2025-06-24 with a stop 0.01 pip away lost **26R** on one trade.
- Five such trades lost 39R between them.
- The live agent would place the same orders today; nothing checks a stop against the spread.

**3. 85% of orders never fill.** 1,227 of the 1,445 orders were limit orders that expired at the killzone's end. The fill rate is 14–16% on every instrument.

**4. The target is effectively fixed.** 1,381 of 1,445 orders have R:R exactly 5.0: the grader's projection puts the target at 5× the stop distance.

**5. The risk limits shaped the sample.** 3,942 distinct setups were skipped by the account limits:
- 1,773 setups hit the weekly drawdown limit;
- 995 hit the daily drawdown limit;
- 192 hit the 3-trade concurrency cap.

The large losses in point 2 tripped the drawdown limits for days at a time. There is no sign that the skipped setups were better, but the 216 trades are what the account allowed, not every setup.

**6. Other patterns:**
- Every filled trade is grade A; no A+ or B setup was filled.
- Shorts did worse than longs (−0.78R vs −0.34R).
- Every killzone is negative: London −0.65R, NY AM −0.41R, NY PM −0.54R.

## Insufficient evidence (n < 30)

These buckets are not findings:
- the London and NY PM silver bullets, the news window, the NY PM killzone time window and off hours;
- every single month: 5–21 trades each. Four months (2025-04, 2025-05, 2025-11, 2026-03) were positive.

## Follow-up (not in this task)

This task makes no strategy changes. These go to the `liquidity-engine` spec update, each measured against this run with `compare`:
- a minimum stop relative to costs (point 2);
- target placement and the fixed 1:5 (points 1 and 4);
- entry placement and expiry (point 3).

The report is 48 MB (`report.html`) for 18 months of four instruments, mostly IN_TRADE rows. If it is too heavy to review, task 218's note applies: chart IN_TRADE rows through their order's row, or split the report by instrument.
