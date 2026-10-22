# ICT Silver Bullet and macros

**Asked 2026-10-22:** "What about the idea of ICT silver bullets and Macros, have we tested them yet?" Neither had been tested. The Silver Bullet hours were only a label in the backtest reports, and the macros were a proposal in `trading-method.md`.

**What was used.**
- **Data:** the exploration slice only, January to June 2025.
- **Markets:** the trader's focus list (XAUUSD, EURUSD, GBPUSD, US100, US500, US30, GER40 and UK100), from the research snapshot.
- **Rules:** fixed before any run.
- **Scripts:** scratch `silver_bullet.py` and `macros.py` (session 8d8f848c).

## 1. The Silver Bullet as a model

**The rules:**
- **Window:** one New York hour; the Silver Bullet hours are 03:00, 10:00 and 14:00.
- **Sweep:** inside the window or the 30 minutes before it, an M5 candle trades beyond a pool known before it. A pool is an untaken M5 swing (two candles each side), the day's high or low so far, or the previous day's high or low.
- **Gap:** after the sweep, an M5 FVG forms the other way, its third candle closing inside the window.
- **Entry:** a limit at the gap's near edge, expiring at the window's end.
- **Stop:** the sweep's extreme.
- **Target:** the nearest opposing pool at least 1R away.
- **Exit:** at the stop, the target, or two hours after the window.

There is one trade per window, costed as Noculus costs its pseudo trades. The control is the same model in every other hour from 02:00 to 15:00.

| | Trades | Win | R:R | R per trade before costs (95%) | After costs |
|---|---|---|---|---|---|
| Silver Bullet hours | 1,222 | 37% | 1.6 | +0.05 [−0.03, +0.13] | −0.12 |
| — on the side the day went (hindsight) | 505 | 49% | 1.5 | +0.30 [+0.18, +0.42] | +0.14 |
| — against it | 714 | 29% | 1.6 | −0.13 [−0.22, −0.04] | −0.31 |
| The other hours | 4,564 | 32% | 1.7 | +0.01 [−0.03, +0.05] | −0.21 |
| — on the day's side (hindsight) | 1,848 | 39% | 1.6 | +0.18 | −0.03 |

**After costs, by hour:**
- 04:00 −0.05;
- 10:00 −0.11;
- 03:00, 11:00 and 14:00 −0.12 to −0.13;
- 12:00 −0.14;
- 02:00 −0.17;
- 07:00 −0.17, 08:00 −0.19, 13:00 −0.19;
- 06:00 −0.28, 15:00 −0.29, 09:00 −0.30, 05:00 −0.34.

**By market, Silver Bullet hours, after costs:** US100 +0.07, US500 +0.07, US30 +0.05, XAUUSD −0.09, GBPUSD −0.13, EURUSD −0.17, GER40 −0.24, UK100 −0.67 (costs).

**What it says:**
- **The Silver Bullet hours are better hours for this setup, but not special ones.** It loses less there (−0.12R against −0.21R elsewhere), and 04:00, 11:00 and 12:00 do about as well.
- **Without a bias, the model is a coin flip:** +0.05R before costs, with an interval spanning zero. This is the same as every execution model before it (the C3 expansion, the indicator's setups, the body expansion).
- **With the day's real direction it pays:** +0.14R after costs. A bias right **about 69%** of the time would be needed to break even, close to the 66–79% the body expansion needed. ICT himself teaches that the Silver Bullet times a trade toward a draw on liquidity decided beforehand, and the data agrees: the window times it, but the side has to come from the draw.
- **The indices carry it** (+0.05 to +0.07R after costs); UK100 doesn't survive its spread.

## 2. Macros

**The windows,** in New York time: 02:33–03:00, 04:03–04:30, 08:50–09:10, 09:50–10:10, 10:50–11:10, 11:50–12:10, 13:10–13:40, 15:15–15:45 (`trading-method.md`, ND-D2).

**The claim tested:** inside a macro, price seeks liquidity or rebalances a gap. At each window's start, from closed bars only, three things were measured:
- **took:** price took the nearest untaken M5 swing, or the day's high or low, on either side;
- **raid:** price took one and closed the window back beyond it;
- **gap:** price traded into the nearest M5 gap not yet traded into.

**The controls:**
- **Nearby windows:** equal windows shifted 40 and 80 minutes, where they don't overlap a macro.
- **Shuffled paths:** the same measures on paths whose M1 bars were reshuffled across days within each 10-minute slot of the day. Each slot's volatility is kept, and any memory of direction is gone.
- **The macro effect** is (real macro − real control) − (shuffled macro − shuffled control): what macros add beyond the volatility of the time they sit in.

| | Real: macro | Real: control | Shuffled: macro | Shuffled: control | Macro effect |
|---|---|---|---|---|---|
| A pool taken | 58.7% | 57.2% | 60.6% | 59.1% | −0.1 pts |
| A raid | 29.9% | 28.4% | 30.3% | 28.9% | +0.1 pts |
| A gap traded into | 38.4% | 39.7% | 39.3% | 40.2% | −0.4 pts |

There were 8,060 macro windows and 26,213 control windows. Taken one at a time, every macro is within ±5 points of its shuffled twin, and none stands out:
- 02:33 raid −4.9;
- 09:50 gap −4.7;
- 13:10 took −4.4;
- 15:15 raid +3.8;
- 11:50 raid +2.8.

**What it says:**
- **Macros add nothing measurable** to how often price takes liquidity or rebalances a gap. Inside a macro, price does about 1.5 points more of each than in nearby windows, and paths with no memory do the same, so it is the volatility of those times.
- **Real prices take nearby pools about 2 points less often than paths without memory,** in macros and controls alike. Nearby swings hold slightly more often than chance would suggest, but no more so in a macro.

## 3. Together

**The Silver Bullet hours and the macros sit inside the busy hours.** That is where moves start (`PRICE_DELIVERY_PHASES.md`, section 1), and where this setup costs least relative to its stop. That makes them useful as when-to-look windows.

**Neither carries direction.** The Silver Bullet model needs the side right about 69% of the time, and macros show no liquidity-seeking beyond their volatility.

**This is the ninth result to point the same way:** the timing and execution can be coded, and the side has to come from the narrative, decided before the window.

These are exploration numbers. Nothing was fitted, and no rule here is proposed for the engine.
