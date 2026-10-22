# The trader's execution: one confirmation run

> **On hold, 2026-10-22, before any run.** The trader chose to add the price-delivery phase logic first
> (consolidation → expansion, with time; liquidity-engine update 2026-10-22). The combined version will be
> registered here again, before it runs, and confirmed once on this same period. Nothing below was run.
>
> **2026-10-22:** the phase logic added no gate (`docs/research/PRICE_DELIVERY_PHASES.md`), and the M5 exploration of
> the version below lost (−0.01R a trade before costs, −0.23R after; `ENGINE_SCALE_FIX.md`). It has not been run on
> this period. What is confirmed here, and when, is the trader's decision.

**Pre-registered 2026-10-22.** The commit that adds this file is the pre-registration. It comes before the M5 exploration result was seen, and before any run of the version below on the confirmation period. Nothing in this section changes after that commit. The result is appended below it.

## Why

On 2026-10-21 the trader set their own positions beside the engine's trades on Noculus (US500, 11–14 April 2025). The engine's flaw was scale and timing, not the trader's read:
- its stops were 7–10 times the trader's;
- its targets reached beyond a day's range;
- it traded a sweep three days old, at the day's high.

The fixes are liquidity-engine tasks 342–343 (Requirement 27 and criterion 26.6). On the exploration slice (January–June 2025, M15) the trader's execution made about +0.3R a trade. That is the best of any version so far, but every interval included zero.

On 2026-10-21 the trader agreed ("proceed") to take the **M5** version forward, whatever the M5 exploration showed. They execute on M1–M5, and on 11–14 April the M5 engine found two of their trades at the same sweeps and stops, which the M15 engine did not.

## The version under test

`m5_fresh_near_gap` in `config/backtests/confirm.toml`, which is the same version as in `config/backtests/focus.toml` (a test holds them equal):

| Setting | Value | What it does |
|---|---|---|
| `entry_tf` | M5 | the setup (sweep → change in state of delivery → array) is read on M5 |
| `raid_window` | H1, 2 candles | the sweep must fall in the current or previous H1 candle, otherwise `STALE_RAID` |
| `max_stop_atr` | 1.0 | the stop at most one average range of the last 14 closed M15 candles from the entry, otherwise `STOP_TOO_WIDE` |
| `target_mode` | NEAREST | TP1 is the nearer of SD 2.0 of the setup leg and the day's draw |
| `fvg_zone` | gap | the FVG is the gap, read from closed candles only |
| everything else | the defaults | protected-swing wick stop, minimum R:R 3, pending orders expire at the killzone's end |

## Data, costs and account

- **Candles:** the research snapshot `focus-2025-2026h1` (Exness M1), read with `--snapshot`.
- **Markets:** XAUUSD, EURUSD, GBPUSD, US100, US500, US30. The rest of the trader's focus list is left out:
  - GER40 and UK100 wait for the backtester's currency conversion;
  - DXY is the trader's reference index;
  - BTC has no Exness spec.
- **Period:** [2025-07-01, 2026-07-01). The study hold-out (`baseline-2026q3`, from 2026-07-07) is not touched.
- **What this period has and hasn't been used for:**
  - The rules above were built from the trader's April 2025 trades and the January–June 2025 exploration; none of them comes from this period.
  - The engine's default version was run over this period before (task 242).
  - The trader's weekly calls were scored on part of it (H011). Neither involves these rules.
- **Costs:** the `exness-standard` profile, the backtester's fill model as in every run so far: spreads floored at the typical spread, stop slippage, commission.
  - The working tree holds uncommitted cost-code changes (the swap-cost work, 8 files). The exploration runs used them too.
  - Their diff is saved as `data/backtests/confirm-344-worktree.patch` (local), sha256 `3ca3d1b91a9da58f34030a13e35b785c920a3a442503662b1f311a87f0108f97`.
  - The run's manifest records the commit, `git_dirty` and the engine fingerprint.
- **Account:** 10,000 USD, 1% risk a trade, no compounding.

## The judgement, decided now

The backtester's pass mark, agreed with the trader on 2026-10-07 before the first baseline (`docs/backtests/BASELINE.md`), applied to the `m5_fresh_near_gap` run. All five must hold:

| Criterion | Pass |
|---|---|
| Filled trades | ≥ 100 |
| Net expectancy | > 0R, and the lower bound of its 95% bootstrap interval > 0R |
| Profit factor after costs | ≥ 1.3 |
| Max drawdown | ≤ 15R |
| Cost share | costs ≤ 40% of gross R |

- **Pass:** all five hold.
  - The version becomes the candidate for the hold-out `--final` run and a forward test.
  - The engine's default changes only after the trader's review (LE-D18).
- **Fail:** anything less.
  - The report names the criteria that failed.
  - No rule, market, cost or criterion is changed and rerun on this period.
  - What follows is decided afresh, on other data.
- **Reported, not judged:**
  - the reference engine (`base`) over the same period;
  - each market's result;
  - the win rate;
  - the stops and targets in M15 ranges;
  - the holding time;
  - the refusals by reason.

## The run

    python -m algo_backtester run config/backtests/confirm.toml --snapshot focus-2025-2026h1 \
        --variant base --variant m5_fresh_near_gap --workers 8

- It runs once.
- No partial result is looked at.
- If it stops for a technical reason (a crash or a sleep), it is resumed (Phase A is cached by the day) or rerun unchanged.

## Result

*(appended after the run)*
