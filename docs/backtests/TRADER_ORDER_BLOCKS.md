# The trader's order blocks: the exploration run (task 377)

**Run 2026-10-28.**
- **Command:** `python -m algo_backtester run config/backtests/focus.toml --snapshot focus-2025-2026h1 --variant fresh_near_gap --variant fresh_near_gap_ob --variant fresh_near_gap_partial --variant fresh_near_gap_partial_ob --workers 8`. That is two engine analyses, since `ob_rule` changes the engine's own map (liquidity-engine Requirement 31).
- **Data:** the exploration slice, 2025-01-01 to 2025-07-01, Exness M1 from the research snapshot.
- **Markets:** XAUUSD, EURUSD, GBPUSD, US100, US500, US30.
- **Costs and account:** as in task 344: 1% risk, 10,000 USD. Code `53ebc7e`.
- **Runs:**
  - `94c351fb279d` (`fresh_near_gap`);
  - `0600059372c1` (`fresh_near_gap_ob`);
  - `5ca677266892` (`fresh_near_gap_partial`);
  - `422de9bdeb8c` (`fresh_near_gap_partial_ob`).
- **The reference reproduces:** `fresh_near_gap` gives the same 114 trades and +0.27R as tasks 344, 354 and 362. The code change leaves the default engine as it was.

## Why

The trader (2026-10-28): the engine "is not computing arrays as it is supposed to". The audit (https://claude.ai/artifact/WTEUrp8ukte5ESEJaqRbeN) measured the engine against the trader's definitions:
- 22-27% of the engine's order blocks are no change in the state of delivery;
- their zones are 1.5-1.8× wider;
- they find about half of the trader's high-probability order blocks.

The trader then fixed the definition (LE-D31 to D33):
- the run, from its bodies;
- the mean threshold at their 50%;
- a close through the far side inverts it into a breaker.

Each variant is the trader's execution (`fresh_near_gap`, unmanaged and with the partial) with `ob_rule = "cisd"`.

## The results

The interval is the backtester's 95% bootstrap on R per trade after costs.

| Variant | Trades | Win | Gross R | Net R [95%] | Max DD |
|---|---|---|---|---|---|
| fresh_near_gap | 114 | 15% | +0.46 | +0.27 [−0.28, +0.88] | 27.4R |
| fresh_near_gap_ob | 100 | 12% | +0.12 | −0.03 [−0.54, +0.57] | 31.5R |
| fresh_near_gap_partial | 116 | 28% | +0.44 | +0.25 [−0.19, +0.73] | 21.2R |
| fresh_near_gap_partial_ob | 99 | 21% | +0.04 | −0.12 [−0.49, +0.28] | 25.8R |

The trader's order blocks come out 0.30-0.37R a trade lower. Every interval spans zero and they overlap, so on 100 trades this can't tell the two apart.

**The entry arrays.** The type of array each trade entered on (from the run's `context.json`), unmanaged:

| Entry array | fresh_near_gap: trades, net R | fresh_near_gap_ob: trades, net R |
|---|---|---|
| order block | 74, +0.22 | 27, +0.39 |
| breaker | 15, +0.52 | 65, −0.10 |
| IFVG | 13, +0.70 | 6, −1.02 |
| CISD level | 8, +0.19 | 1, −0.45 |
| FVG | 4, −1.02 | 1, −1.02 |

**Breakers take over under the new rule.** Two causes:
- The trader's rule finds about twice as many order blocks (25 against 11-15 per 100 candles in the audit). Each one closed through becomes a breaker.
- Breakers never end, under either rule: nothing marks a breaker filled.

The sequence also ranks a breaker (strength 0.8) above an order block (0.7). So two thirds of the entries were breakers, from blocks that had failed, often long before. Those entries lost (−0.10R).

The entries on the trader's order blocks themselves made +0.39R unmanaged over 27 trades. That's too few to be a finding.

## What it means

The variant doesn't yet measure the trader's order blocks as an entry. It measures the breakers they leave behind. Two choices are the trader's before a second run:
1. **When does a breaker end?** Is it at a close back through its far side, as an order block ends?
2. **Should a breaker outrank an order block** as the entry, as the engine's weights have it?

Not adopted. The default stays `"candle"` until the trader's review (LE-D18).
