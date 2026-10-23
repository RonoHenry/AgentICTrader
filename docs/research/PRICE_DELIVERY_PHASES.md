# Price delivery phases: when the expansion comes, and which way

**Task 346** (liquidity-engine Requirement 28.2, update 2026-10-22). **Exploration slice only:** January to June 2025. The markets are the trader's focus list: XAUUSD, EURUSD, GBPUSD, US100, US500, US30, GER40 and UK100. Each timeframe is paired with its higher one: M15 with H4, H1 with D1, H4 with W1.

The trader (2026-10-22), from ICT's Interbank Price Delivery Algorithm: "A price move is always going to start from Consolidation - Expansion... Notice how easy it becomes then to arrive at a bias once you pair this logic with the element of time."

**How it was read.** `algo_research/phases.py` uses the engine's own CRT thresholds (LE-D23), from closed candles:
- a **consolidation** is 8 candles within 2 average true ranges;
- the **expansion** is the first close outside that box;
- a **manipulation** is a wick beyond the box that closed back inside it.

**The outcome:**
- the side of the first close outside the box;
- the side that first travelled 1.5 ranges beyond the box, within 16 candles ("delivered").

**The control.** The same pipeline was run on shuffled price paths. Each M1 bar's moves were reshuffled within its New York hour, which keeps each hour's volatility and removes any memory of direction. A read that only reflects the geometry of the box scores the same on both. The scratch scripts are `phases_diag.py` and `phases_diag.py --control`.

## 1. When: the expansions come when the sessions open

How often consolidations broke at each New York hour, against how often candles occur at that hour:

| | Real prices | Shuffled paths |
|---|---|---|
| M15 | 01:00 1.9×, 02:00 1.5×, 07:00–08:00 1.4×, 13:00–15:00 1.2–1.6×; 04:00–05:00 and 10:00–11:00 0.2× | 01:00 1.8×, 02:00 1.5×, 07:00–08:00 1.2–1.3×, 13:00–15:00 1.3–1.6×; the same lows |
| H1 | 02:00 2.0×, 03:00 3.1×, 08:00 2.0×, 09:00 1.8×; afternoon 0.1–0.3× | 02:00 2.1×, 03:00 2.7×, 09:00 2.1×; afternoon 0.0–0.2× |

Consolidations end in an expansion at the London and New York opens. The shuffled paths, which keep only each hour's volatility, do the same. So the time element is real, and it is the session clock: the expansion comes when volatility arrives. That tells you when to look. It doesn't say which way.

## 2. Which way: no read known before the break calls it

How often each read called the side that delivered first (95% interval). The setups need 56–61% to clear their costs (task 338).

| Read before the break | M15 real | M15 shuffled | H1 real | H1 shuffled |
|---|---|---|---|---|
| Opposite the manipulation (the stop run, then the other way) | 36.1% [33.5, 38.8] | 35.5% | 36.6% [32.4, 40.9] | 37.6% |
| With the manipulation (a breakout) | 63.9% [61.2, 66.5] | 64.5% | 63.4% [59.1, 67.6] | 62.4% |
| The higher timeframe's discount up, premium down | 47.4% [45.5, 49.3] | 50.4% | 48.5% [45.4, 51.6] | 50.3% |
| The previous expansion's side | 52.0% [50.1, 53.9] | 50.1% | 51.6% [48.5, 54.7] | 49.6% |
| Opposite the manipulation, in a killzone | 37.0% | — | 38.0% | — |
| Opposite the manipulation, with the higher timeframe agreeing | 32.7% | — | 33.3% | — |

H4 (260 consolidations) reads the same, with wider intervals.

- **The manipulation's side is geometry.** After a wick above the box, price sits at its top, and it leaves through the top about two times in three. The paths without any memory do exactly the same (64.5% against 63.9%). The wick carries no information about the side.
- **Position and trend add one or two points at most.** Discount or premium in the higher timeframe's last candle reads 47–49% (50% shuffled). The previous expansion's side reads 52% (50% shuffled). None comes near 56%.
- **Time doesn't add direction.** In the killzones, the reads score the same.

## 3. What it means

- **What the phase logic gives** is the context of a trade (ICT's A): where a move is likely to start (out of a consolidation), and when (at a session's open). As a filter it can keep the engine from chasing the middle of an expansion.
- **What it doesn't give** is the side. Read mechanically, none of the cycle, the manipulation, the higher timeframe's position or the time calls the expansion's direction above chance, once the box's geometry is accounted for.
- **So the side still has to come from the narrative:** the draw, the higher timeframe's story, the trader's thesis. That is what the thesis developer is for. The honest measure of it is the trader's own read, recorded before the move (Noculus positions with their clock).
- **Requirement 28.3** gates the engine only if a read clears the bar. None did, so no gate is added, and the version registered for confirmation (`m5_fresh_near_gap`) stands unchanged.
- **These are exploration numbers.** Nothing here was fitted. The thresholds are the engine's own, and the reads were fixed before the run.
