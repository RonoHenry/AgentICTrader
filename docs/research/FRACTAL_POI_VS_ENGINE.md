# Your Fractal + POI indicator against the engine

**Task 338** (`.kiro/specs/algo-backtester`, update 2026-10-20). **Exploration only:** the exploration slice, 2025-01-01 → 2025-07-01, on XAUUSD, EURUSD and GBPUSD. The confirmation slice has not been read. Nothing here is a finding until it passes there, pre-registered.

You asked (2026-10-20): "try to use now the setups that the indicator is suggesting and lets see where the flaw is in our engine. I noticed that it does not interpret C1, C2 and C3 like it is supposed to. FVG the same thing, and then this will allow us to refine our executions."

**How it was measured**
- **Your setups:** the indicator on an M15 chart (HTF H4, your default inputs), read candle by candle. 911 setups qualify: C2 closed back inside C1 and the CISD broke.
- **The engine's decisions:** from the base backtest's journal (`72b9ce1fd2ca`), its decision at every M15 close, with each order's raid and entry array. Its bars equal the snapshot's exactly.
- **Your setups as trades:** priced as Noculus prices a pseudo trade: bid and ask, the spread floor, stop slippage and commission.
- **To rerun:** `python -m algo_research.fractal_poi.diff`.

## 1. Where the engine reads C1, C2, C3 and FVGs differently

| | Your indicator | The engine |
|---|---|---|
| **C1** | the previous HTF candle (H4 on an M15 chart) | No candle at all. A "pool" is any swing point (two candles each side) on any timeframe, the previous day, week or month high and low, or the Asian range. The CRT classifier's "C1" (`ipda/classifier.py`) is an 8-candle tight range of at most 2 ATR. Its phases are stored on the map but never used to trade. |
| **C2** | the next HTF candle trades beyond C1's extreme **and closes back inside it** | Any M15 bar beyond a pool, then any later M15 close back over it. No HTF candle has to close back inside anything (`grader/sequence.py`). |
| **CISD** | the open of the last run of same-direction candles into C2's extreme; any later close through it | The run must be broken by the **very next** candle, with a three-candle swing inside the run (`ipda/cisd.py`). |
| **When** | C3, then C4, then the setup is over | Any time. The raid it trades was a median **10.5 h** old at the order: 87% older than 4 h, 21% older than a day. |
| **Entry** | the C3 zone (C2's EQ to the CISD bodies' mid, or C3's open), then the C4 zone | An M15 array: breakers 192 of 255 orders, order blocks 37, FVGs and IFVGs 25. |
| **Stop** | beyond C2's extreme (the setup is void when C3 takes it: xC2) | behind the protected swing, the extreme since the raid |
| **Target** | C1's opposite extreme (formation liquidity), then the SD levels | the grader's, with a 3R floor |
| **FVG** | the HTF gap (H4 on an M15 chart), closed candles only, the newest three, deleted when a close goes through | Every timeframe. By default the whole three candles, and a wick through it makes an IFVG. The forming HTF candle is read as if closed, and an IFVG never ends (the 2026-10-17 audit). Task 326 made the gap available behind `fvg_zone`; the forming candle is not fixed yet. |

## 2. What the engine did during your setups

| During your 911 setups the engine… | Setups |
|---|---|
| was out by its own limits (3 trades open, the weekly drawdown stop) | 223 |
| raided only the other side's pools | 160 |
| had its own setup on your side but its R:R was under 3 | 131 |
| raided another pool on your side, graded out | 130 |
| **traded with you** | **85** |
| was in another trade | 67 |
| raided your C1, graded out | 55 |
| traded against you | 46 |
| had no setup at all | 15 |

- Of its 92 orders that fell inside one of your setups, the raid was your C1's extreme in **26**.
- Its 132 filled trades made **−29.1R**. By where they fell (R per filled trade):

  | Where the trade fell | Net R per trade | Trades |
  |---|---|---|
  | With your setup | −0.18 | 45 |
  | Against it | +0.24 | 26 |
  | Outside any setup | −0.44 | 61 |

  The samples are too small to read either way.

## 3. Your setups, traded your way

| All three markets | Filled | Win | Break-even win | Gross R | Net R |
|---|---|---|---|---|---|
| A: market once C2 + CISD are in | 710 | 0.48 | 0.57 | +0.03 | −0.03 |
| — with the day's real direction (hindsight) | 350 | 0.65 | 0.62 | +0.29 | +0.23 |
| — against it | 358 | 0.31 | 0.53 | −0.23 | −0.29 |
| — with the previous day's direction | 349 | 0.47 | 0.57 | +0.02 | −0.05 |
| B: limit at the C3 zone's EQ edge, until C3 closes | 467 | 0.31 | 0.40 | −0.04 | −0.14 |
| — with the day's real direction (hindsight) | 191 | 0.49 | 0.43 | +0.37 | +0.27 |
| — against it | 276 | 0.19 | 0.37 | −0.33 | −0.42 |
| — with the previous day's direction | 237 | 0.30 | 0.39 | −0.10 | −0.19 |
| C: limit at the C4 zone, stop at C3's extreme | 277 | 0.34 | 0.43 | +0.05 | −0.24 |
| — with the day's real direction (hindsight) | 142 | 0.42 | 0.48 | +0.23 | −0.14 |

- Stops are at C2's extreme (C: at C3's) and targets at C1's opposite extreme. A trade still open at C4's close exits there.
- The per-market tables are in the report the command writes. The three markets agree.

**A trap, and the test that now guards it.** The first run of B showed **+0.58R** a trade. That was look-ahead. The limit's expiry (C3's close) was read from the setup's record, and only a setup that survives C3 has a C4 in it. So every setup that went on to fail was silently dropped. Taken from the HTF clock instead, B is −0.14R a trade (95% interval −0.24 to −0.03). The 225 trades the bug had removed lost −0.86R each. `test_a_setup_that_fails_in_c3_is_still_traded_from_c3` now holds this.

## 4. What it says

1. **The engine doesn't see your C1, C2 and C3 at all.** It trades a raid of whatever swing is nearest, often hours old, with no HTF candle closing back inside, no C3 window and no C2 stop. Its FVGs are not your FVGs either. The flaw you saw is real and structural.
2. **Your setups on their own are a coin flip.** Read exactly as the indicator reads them and traded three ways, they make 0R gross (+0.03, −0.04, +0.05) and lose the costs. This matches the earlier C1/C2 sweep and C3 expansion tests.
3. **The direction is the whole edge.** With the day's real direction the same setups make +0.29R to +0.37R gross; against it they lose about as much. In the indicator, the direction is the one thing it doesn't decide: your Bias input. The previous day's direction is no stand-in.
4. **How right a bias must be.** Taking these setups only on your bias's side pays if your bias calls the day right about **56%** of the time for A (market), or **61%** for B (the C3 limit), after costs. Those are the break-even points from the hindsight rows above.

   The bias must be decided **before the day**, as at the 17:00 open in your blind sessions. A read taken during the day "calls the day" more often, but only because part of the day has already happened (section 6).

## 6. With the HTF trend (asked 2026-10-20)

You asked: "have we factored in the trend in which we are trading, like trading in the direction of the HTF trend and using the Fractals indicator to show us where to position ourselves?"

Each read below is known when the setup can be traded. "Calls the day" is how often the read points the way the trading day closed. Cells give trades, gross R and net R.

| HTF trend read | Calls the day | A with it | A against it | B with it | B against it |
|---|---|---|---|---|---|
| the last D1 close above (below) its 20-day average | 45% | 318, +0.04, −0.02 | 355, +0.01, −0.06 | 212, −0.01, −0.09 | 232, −0.08, −0.18 |
| the last D1 break of structure up (down) | 49% | 335, +0.01, −0.05 | 372, +0.05, −0.02 | 223, −0.10, −0.18 | 243, +0.01, −0.09 |
| last week's candle up (down) | 47% | 365, +0.04, −0.02 | 345, +0.02, −0.04 | 233, −0.10, −0.18 | 234, +0.01, −0.10 |
| the D1 average, the D1 structure and last week agree | 46% | 197, +0.04, −0.02 | 209, +0.03, −0.05 | 132, −0.07, −0.15 | 138, −0.02, −0.14 |
| price above (below) this week's open (the engine's W1 bias) | 58% | 323, −0.02, −0.08 | 387, +0.07, +0.01 | 220, −0.01, −0.10 | 247, −0.08, −0.17 |
| price above (below) today's 17:00 open (the engine's D1 bias) | 69% | 336, +0.04, −0.02 | 373, +0.02, −0.05 | 230, −0.02, −0.11 | 236, −0.08, −0.17 |

- **The HTF trend reads don't call the day.** The D1 average, the D1 structure and last week's candle point the day's way 45–49% of the time, alone or together. So trading only with them changes nothing: with and against are within 0.06R of each other, both near 0.
- **The open-side reads call it more often, and still don't help.** Price against today's or this week's open points the day's way 58–69% of the time. But it is read when the setup appears, after part of the day has moved, so it is calling the part already behind it. With it and against it the setups are the same.
- **What's needed.** A direction for the rest of the day, decided before it, that is right more often than these. A mechanical HTF trend isn't that, on this sample. Whether your own read is, is what the blind sessions can measure.

## 5. Next steps (yours to choose)

1. **Make the engine read your way.** The indicator's CRT becomes the engine's setup model, behind a strategy setting:
   - C1 is the previous HTF candle, and C2 must close back inside it;
   - the CISD uses the run rule;
   - entry is in the C3 or C4 zone, the stop beyond C2, the target C1's opposite extreme;
   - the setup expires at C3 or C4.

   Add the FVG fix for the forming candle. This makes the engine's executions yours. It changes engine code, so the 539 MB Phase A cache is rebuilt, which takes hours.
2. **Supply the bias.** Your blind Noculus sessions already record your direction per day. Scoring your calls against the day's real direction measures what the 56–61% bar asks. If you clear it, the engine executes your bias with your setups.
3. **Confirm first.** Whichever goes forward is pre-registered and tested once on the confirmation slice before it counts.
