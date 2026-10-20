# Supply and demand, alone and with your indicator

**Task 339** (`.kiro/specs/algo-research`, update 2026-10j). **Exploration only:** the exploration slice (2025-01-01 → 2025-07-01) on XAUUSD, EURUSD, GBPUSD, US100 and US30. The confirmation slice has not been read. To rerun: `python -m algo_research.supply_demand [--paired <diff --save pickle>]`.

You asked (2026-10-20): "How about we pair the concept of Supply and Demand with what we already have... lets just test it and see how this goes."

## The definition, fixed before the run

The classic reading:
- **A zone** is a base and a leg-out on one timeframe (D1, H4 or H1):
  - **the base:** 1–3 candles with bodies at most half their range;
  - **the leg-out:** the next candle, explosive. Its body is at least 60% of its range, its range at least 1.5× the 20-candle average, and it closes beyond the base.
- **Demand or supply.** Up out of the base is demand; down is supply.
- **Its lines.** The proximal line is the base's body edge; the distal line is the far wick of the base and the leg-out. The zone is known at the leg-out's close.
- **Fresh** until price first returns to the proximal line.
- **The trade:** a limit at the proximal line. The stop is beyond the distal line by 10% of the zone's height; the target is 2R or 3R. It expires after 30 candles of the zone's timeframe and is held 10 candles at most once filled. It is priced as Noculus prices a pseudo trade.

## Results

**Supply and demand alone: the first return to a fresh zone.** "Chance" is a random walk's chance of the target before the stop.

| Zones | Trades | Hit | Chance | Gross R | Net R |
|---|---|---|---|---|---|
| D1, 2R | 15 | 0.20 | 0.33 | −0.09 | −0.12 |
| D1, 3R | 15 | 0.07 | 0.25 | −0.13 | −0.16 |
| H4, 2R | 116 | 0.32 | 0.33 | +0.08 | +0.04 [−0.20, +0.31] |
| H4, 3R | 116 | 0.18 | 0.25 | −0.03 | −0.06 |
| H1, 2R | 427 | 0.27 | 0.33 | −0.01 | −0.07 [−0.20, +0.06] |
| H1, 3R | 427 | 0.19 | 0.25 | +0.00 | −0.07 |

- **How often zones form, and come back.** D1 zones are rare, 24 in six months across the five markets, so D1 can't be judged here. Price returns to 87% of H4 zones (median 1.2 days) and 93% of H1 zones (median 9 hours).
- **The strongest zones did no better.** A one-candle base with a leg-out of 2.5+ average ranges: H1 2R, 44 trades, hit 27%, −0.08R.

**Paired with your indicator: C2 sweeps into a fresh zone of its kind.** That means supply for shorts and demand for longs, on D1, H4 or H1.

| Your setups | n | Win | Gross R | Net R |
|---|---|---|---|---|
| market at C2 + CISD, all | 710 | 0.48 | +0.03 | −0.03 |
| — C2 swept into a fresh zone | 51 | 0.45 | +0.12 | +0.08 [−0.13, +0.30] |
| — into no fresh zone | 659 | 0.48 | +0.02 | −0.04 |
| C3 zone EQ limit, all | 467 | 0.31 | −0.04 | −0.14 |
| — C2 swept into a fresh zone | 32 | 0.28 | +0.00 | −0.07 |
| — into no fresh zone | 435 | 0.31 | −0.05 | −0.14 |

## What it says

- **Supply and demand alone is a coin flip here.** Hit rates sit at or below a random walk's on H4 and H1, and the gross is about zero.
- **Pairing doesn't separate your setups.** The ones that swept into a fresh zone did +0.12R gross against +0.02R for the rest, but there are only 51 of them and the interval spans zero. Fresh zones are rarely where C2 sweeps: 7% of your setups.
- **It agrees with everything before it** (`docs/research/FRACTAL_POI_VS_ENGINE.md`). Location, like the setups and the trend rules, carries no measurable direction on these timeframes. D1, where the turn atlas found the one context effect, has too few zones in six months to test.
