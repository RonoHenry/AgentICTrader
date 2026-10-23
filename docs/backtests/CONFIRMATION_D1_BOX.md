# Waiting out the expansion day's box: one confirmation run

**Pre-registered 2026-10-23.** The commit that adds this file is the pre-registration. It comes after the exploration run (`D1_BOX.md`), and before any run of the version below on the confirmation period. Nothing in this section changes after that commit. The result is appended below it.

The earlier registration on this period (`CONFIRMATION_TRADER_EXECUTION.md`, `m5_fresh_near_gap`) stays on hold and unrun. On 2026-10-23 the trader chose to confirm this version instead ("please", to pre-registering it and running it once).

## Why

On 2026-10-23 the trader showed the engine on Noculus (GBPUSD, 27-29 January 2025):
- Friday 24 January expanded 155 pips, and Monday to Thursday stayed inside that range.
- The engine traded both sides from the middle of that box, with expansion targets 140-226 pips away. Every trade was stopped after +0.15 to +0.6R.

Their read: the engine trades a consolidation as if it were an expansion. The rule (liquidity-engine task 353, Requirement 29, LE-D25-D27) waits until price leaves the last expansion day's range.

On the exploration slice (`D1_BOX.md`), with the trader's M15 execution:
- 70 trades, +0.69R a trade after costs [−0.13, +1.62], profit factor 1.83, drawdown 14.5R;
- without the box: 114 trades, +0.27R, drawdown 27.4R.

That rule was found on those same trades, so the exploration can't confirm it. This period can.

## The version under test

`fresh_near_gap_box` in `config/backtests/confirm.toml`, the same version as in `config/backtests/focus.toml` (`test_backtest_config.py` holds them equal):

| Setting | Value | What it does |
|---|---|---|
| `entry_tf` | M15 | the setup (sweep → change in state of delivery → array) is read on M15 |
| `raid_window` | H4, 2 candles | the sweep must fall in the current or previous H4 candle, otherwise `STALE_RAID` |
| `d1_box_expansion` | 1.2 | no order while every D1 close since the last D1 candle of at least 1.2 times the 20-day mean range is inside that candle's range, otherwise `IN_D1_BOX` |
| `max_stop_atr` | 1.0 | the stop at most one average range of the last 14 closed M15 candles from the entry, otherwise `STOP_TOO_WIDE` |
| `target_mode` | NEAREST | TP1 is the nearer of SD 2.0 of the setup leg and the day's draw |
| `fvg_zone` | gap | the FVG is the gap, read from closed candles only |
| everything else | the defaults | protected-swing wick stop, minimum R:R 3, pending orders expire at the killzone's end, 3 trades at a time |

## Data, costs and account

- **Candles:** the research snapshot `focus-2025-2026h1` (Exness M1), read with `--snapshot`.
- **Markets:** XAUUSD, EURUSD, GBPUSD, US100, US500, US30, the same six as the exploration. GER40 and UK100 wait for the backtester's currency conversion, DXY is the trader's reference index, and BTC has no Exness spec.
- **Period:** [2025-07-01, 2026-07-01). The study hold-out (`baseline-2026q3`, from 2026-07-07) is not touched.
- **What this period has and hasn't been used for:**
  - The box rule, its threshold and every other setting above come from January-June 2025 and the trader's April 2025 and January 2025 cases; none comes from this period.
  - The engine's default version was run over this period before (task 242). The trader's weekly calls were scored on part of it (H011). Neither involves these rules.
- **Costs:** the `exness-standard` profile and the backtester's fill model, as in every run so far: spreads floored at the typical spread, stop slippage, commission.
  - The working tree holds uncommitted cost-code changes (the swap-cost work, 15 files). The profile has no swap, and the exploration rerun reproduced task 344 exactly with them in place.
  - Their diff is saved as `data/backtests/confirm-354-worktree.patch` (local), sha256 `880ecf10871f253917acad359c3e078f9b247b15ac3d8a5388d51f9d4c6b7b34`.
  - The run's manifest records the commit, `git_dirty` and the engine fingerprint.
- **Account:** 10,000 USD, 1% risk a trade, no compounding.

## The judgement, decided now

The backtester's pass mark, agreed with the trader on 2026-10-07 before the first baseline (`docs/backtests/BASELINE.md`), applied to the `fresh_near_gap_box` run. All five must hold:

| Criterion | Pass |
|---|---|
| Filled trades | ≥ 100 |
| Net expectancy | > 0R, and the lower bound of its 95% bootstrap interval > 0R |
| Profit factor after costs | ≥ 1.3 |
| Max drawdown | ≤ 15R |
| Cost share | costs ≤ 40% of gross R |

- **Pass:** all five hold.
  - The version becomes the candidate for the hold-out `--final` run, and the forward paper test is its live record.
  - The engine's default changes only after the trader's review (LE-D18).
- **Fail:** anything less.
  - The report names the criteria that failed.
  - No rule, threshold, market, cost or criterion is changed and rerun on this period.
  - What follows is decided afresh, on other data.
- **Reported, not judged:**
  - `fresh_near_gap` over the same period, from the same engine analysis: what the box changed;
  - each market's result, the win rate, the longest losing streak;
  - the trades the box refused, and what the reference made on them;
  - the refusals by reason.

## The run

    python -m algo_backtester run config/backtests/confirm.toml --snapshot focus-2025-2026h1 \
        --variant fresh_near_gap --variant fresh_near_gap_box --workers 4

- It runs once.
- No partial result is looked at.
- If it stops for a technical reason (a crash or a sleep), it is resumed (Phase A is cached by the day) or rerun unchanged.

## Forward test (reported, not judged)

From 2026-10-23, a second paper runner trades `fresh_near_gap_box` on live Exness prices (`scripts/run_live_agent.py --config config/backtests/focus.toml --variant fresh_near_gap_box --broker paper`, state in `data/paper_trades_fresh_near_gap_box.json`), beside the one trading `fresh_near_gap`. Nothing is sent to the broker. Its record is reported with the result; it decides nothing here.

## Result

**Run 2026-10-23, once, as registered.** Runs `c0be82a2972a` (`fresh_near_gap`) and `3037e247bfb9` (`fresh_near_gap_box`). The code is 43d1db9, dirty with the registered swap-cost work only. Engine 395c889e4c1d.

**FAIL. All five criteria fail.**

| Criterion | Pass | fresh_near_gap_box |
|---|---|---|
| Filled trades | ≥ 100 | 98 ✗ |
| Expectancy and its interval | lower bound > 0 | −0.51R [−0.88, −0.05] ✗ |
| Profit factor after costs | ≥ 1.3 | 0.48 ✗ |
| Max drawdown | ≤ 15R | 55.6R ✗ |
| Cost share | ≤ 40% of gross R | gross R is negative (−0.27R a trade) ✗ |

**Reported, not judged:**
- **The reference** (`fresh_near_gap`): 175 trades, win rate 7%, −0.47R a trade [−0.76, −0.11], −0.25R before costs, profit factor 0.51, drawdown 84.9R, longest losing streak 26.
  - Every quarter lost: −5.4R, −23.4R, −27.4R, −25.1R.
  - 162 stops and 13 targets, with targets a median 8.6R away.
  - In January to June 2025 the same version made +0.27R a trade (+0.46R before costs).
- **What the box changed:**
  - it removed 89 of the reference's trades, worth −44.1R (−0.50R a trade);
  - it kept 86, worth −37.3R (−0.43R);
  - it added 12 that the freed slots allowed, worth −12.5R.

  So on this period it did not separate bad trades from good: the trades it refused were as bad as the ones it kept.
- **By market, with the box:** EURUSD −0.59, GBPUSD +0.08, US100 −0.99, US30 −0.35, US500 −0.28, XAUUSD −0.57 (R a trade; every market under 30 trades).
- **Refusals:** `IN_D1_BOX` 6,921, `STALE_RAID` 42,137, `STOP_TOO_WIDE` 4,422, `RR_BELOW_MIN` 65 decisions.

As registered, nothing is changed and rerun on this period. The box is not adopted, and the default engine is unchanged. What follows is decided afresh, on other data.
