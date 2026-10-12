# Trade autopsy: where the engine loses

Task 293 (`.kiro/specs/market-narrative/tasks.md`). Every filled trade of the three reference runs, read against how its candles actually formed (`trading-method.md`, section 7: the narrative). The autopsy splits each run's net R by failure mode, judged on the trade's D1 candle, so the flaws are ranked by what they cost.

**Hindsight.** The labels use how the candles finished. They show where the R was won and lost. They are not rules: "filled after the day's false move" can't be known at the fill. A finding becomes a rule only through a pre-registered hypothesis or a backtest variant, on data this diagnosis didn't use.

## The runs

| Run | What it is | Trades | Net |
|---|---|---|---|
| `5d241691c701` | the baseline (task 211): the first engine | 216 | −0.54R a trade |
| `ec4876ba87a1` | the setup sequence, stop behind the protected swing's wick (task 233) | 537 | −0.16R |
| `475491a89d91` | the same, stop behind its body (task 233) | 686 | −0.01R |

All on Exness M1, EURUSD, GBPUSD, USDJPY and XAUUSD, 2025-01 → 2026-07 (study `baseline-2026q3`; the hold-out is untouched).

Reproduce:

```
python -m algo_backtester autopsy data/backtests/<run_id>
```

It writes `autopsy.md` and `autopsy.csv` into the run directory in about 10 seconds, from the run's own files. New runs get it automatically.

Settings: `config/research/narrative.toml` at its defaults:
- frames W1, D1 and H4; failure modes judged on D1;
- a candle's direction is its close against its open (ND-D6);
- FX bars in the first 30 minutes after 17:00 New York are flattened at the last clean close, so rollover bid dips don't fake day lows (ND-D7).

---

## Result: the setup chain works; the direction doesn't

| | Baseline | WICK | BODY |
|---|---|---|---|
| Trades with their D1 candle | 47% | 45% | 44% |
| Mean R with the D1 candle | −0.48R | +0.48R | +0.58R |
| Mean R against it | −0.60R | −0.68R | −0.49R |
| With the day, filled on time (`WITH_ON_TIME`) | −0.46R (17% hit) | **+1.66R** (49% hit) | **+1.80R** (46% hit) |
| Against the day, filled while it expanded (`AGAINST_EXPANSION`) | −0.67R (33%) | **−0.90R** (36%) | **−0.84R** (33%) |

- **The rewrite fixed execution.**
  - In the baseline, even right-direction trades lost: on-time fills hit their target 17% of the time and averaged −0.46R. Its stops sat inside the spread (`BASELINE.md`).
  - In WICK and BODY, the same kind of fill makes +1.7 to +1.8R a trade. The raid → CISD → array chain, the stop and the target all work when the direction is right.
- **What's left is direction.**
  - The engine trades with its D1 candle 44–45% of the time, no better than a coin flip.
  - The single biggest loss is a third of all trades, taken against the day while it expanded. They never reach their target and lose more than the whole run.

## Failure modes

BODY (`475491a89d91`), 686 trades, −8.8R:

| Mode | Trades | Share | Target hit | Mean R | 95% interval | Sum R |
|---|---|---|---|---|---|---|
| `WITH_ON_TIME`: with the day, filled after its false move, up to its high or low | 133 | 19% | 46% | +1.80R | [+1.25, +2.37] | +239.3R |
| `WITH_EARLY`: with the day, filled inside its false move | 54 | 8% | 7% | −0.54R | [−0.94, −0.09] | −29.4R |
| `WITH_LATE`: with the day, filled after its high or low | 75 | 11% | 9% | −0.32R | [−0.72, +0.17] | −23.9R |
| `WITH_INVERTED`: with the day, which made its extreme on the close side first | 41 | 6% | 12% | −0.22R | [−0.74, +0.40] | −8.9R |
| `AGAINST_EXPANSION`: against the day, filled while it expanded | 224 | 33% | 0% | −0.84R | [−0.89, −0.80] | −189.2R |
| `AGAINST_OTHER`: against the day, any other time | 159 | 23% | 10% | +0.02R | [−0.42, +0.55] | +3.3R |

WICK (`ec4876ba87a1`), 537 trades, −87.9R:

| Mode | Trades | Share | Target hit | Mean R | 95% interval | Sum R |
|---|---|---|---|---|---|---|
| `WITH_ON_TIME` | 103 | 19% | 49% | +1.66R | [+1.07, +2.28] | +170.5R |
| `WITH_EARLY` | 51 | 9% | 6% | −0.62R | [−0.93, −0.22] | −31.6R |
| `WITH_LATE` | 61 | 11% | 11% | −0.31R | [−0.70, +0.21] | −18.8R |
| `WITH_INVERTED` | 24 | 4% | 12% | −0.18R | [−0.96, +0.77] | −4.4R |
| `AGAINST_EXPANSION` | 192 | 36% | 0% | −0.90R | [−0.92, −0.87] | −172.1R |
| `AGAINST_OTHER` | 105 | 20% | 9% | −0.29R | [−0.66, +0.14] | −30.6R |
| `UNKNOWN` | 1 | 0% | 0% | −1.01R | | −1.0R |

Intervals resample trading dates (day-cluster bootstrap, 2,000 resamples).

---

## Findings, ranked by cost, and where each points in the engine

### 1. Direction: the engine fades the day's expansion (−189R BODY, −172R WICK)

A third of the trades went against the day while it expanded. 194 of BODY's 224 reacted to a raid of an M15 swing.

**The mechanism.** On an up day, price takes swing highs on its way to its objective. The engine reads each of those raids as a reversal: raid, bearish CISD, short. In the method, those raids are the expansion consuming liquidity. Only the false move's raid, against the coming direction and beyond the open, is the manipulation.

**Where the raid sat doesn't decide it.** "Raid beyond the open" means below the open for a long and above it for a short.

| | BODY | WICK |
|---|---|---|
| With the day, raid beyond the open | +0.75R (193 trades) | +0.73R (143) |
| Against the day, raid beyond the open | −0.47R (315) | −0.75R (237) |

The raid looks the same either way; only the day's direction separates winners from losers.

**Points to:** context-engine Requirement 4 (the context chain decides the direction) and Requirement 6's direction rule. The engine needs the method's section 2: which way the bias candle is delivering, and whether its false move has happened.

### 2. Timing, with the right direction (−53R BODY, −50R WICK)

- **Early.** Filled inside the false move: −0.54R. 45 of BODY's 54 were stopped by the false move itself, the false-move extreme lying beyond the stop.
- **Late.** Filled after the day's high or low: −0.32R. The move had already been delivered.

**Points to:**
- the objective rule of context-engine Requirement 6: take the setup only after the bias candle's manipulation objective has been raided, i.e. the false move has happened;
- the draw rule: the draw must still be untaken.

### 3. Targets overshoot the day

88% of BODY's with-day trades aimed beyond the day's high or low:

| With the day, target | Trades | Target hit | Mean R |
|---|---|---|---|
| inside the day's range | 36 | 53% | +2.25R |
| beyond the day's extreme | 267 | 22% | +0.36R |

This is partly circular, because a closer target is easier to reach. The size of the gap still matters: the SD 2.0 targets reach for objectives the day doesn't deliver.

**Points to:** context-engine Requirement 7: TP1 at the bias frame's draw (CE-D7).

### 4. Trade management

Of the with-day trades that were stopped, 46% (BODY) and 51% (WICK) first reached +1R. This agrees with the break-even replay (BE at 0.5R lifted BODY to about +0.07R, interval spanning zero). It is a management question, worth asking only once direction carries information.

### 5. A lead to test, not a rule: the shape of the day so far

The one as-of column. From the D1 bars closed before the fill:
- the shape is UP when the low so far came before the high and the price is back above the open;
- DOWN is the mirror;
- otherwise it is unformed.

| As of the fill | BODY trades | With the day | Mean R | WICK trades | With the day | Mean R |
|---|---|---|---|---|---|---|
| Fades the shape | 286 | 20% | −0.13R | 244 | 19% | −0.34R |
| Follows the shape | 298 | 69% | −0.01R | 229 | 74% | −0.05R |
| Unformed | 102 | 39% | +0.29R | 64 | 38% | +0.08R |

- The shape so far is strongly tied to the day's direction, but it pays little. By the time it has formed, much of the day's move is gone.
- Dropping the trades that fade it would give BODY about +0.07R and WICK about −0.02R a trade.
- It is in-sample and found by looking, so it can only become a hypothesis for the confirmation slice. Its test is AlgoResearch's H010 family: the side of the D1 open at a fixed time. The lesson is the same as the method's: the edge is in reading the direction before the false move, not after.

---

## What direction accuracy is worth

With today's execution, and assuming the with-day and against-day payoffs above hold:

| | Breaks even at | At 55% | At 60% |
|---|---|---|---|
| BODY (+0.58R with, −0.49R against) | ~46% | +0.10R a trade | +0.15R a trade |
| WICK (+0.48R with, −0.68R against) | ~59% | −0.04R | +0.02R |

A read that also gets the timing right (filling after the false move) is worth far more: on-time fills make +1.7 to +1.8R. That is the ceiling the method is aiming at, measured in hindsight.

## Caveats

- **Hindsight.** Phases, failure modes and the with/against split use the finished candle. They rank flaws; they don't estimate what a rule would earn.
- **In-sample.** These are the same runs and period every engine change so far has been judged on.
- **Direction is the close against the open.** The trader judges bias by whether the draw was delivered (AR-D18). That label (ND-D6's alternative) comes with stage 2.
- **Trades are judged by the candle they filled in,** even when held into the next one.
- **The price basis is a time window,** not the spread-based quarantine (context-engine task 276).

## Next

The autopsy ranks direction and phase first, by a wide margin. The context engine's first layer addresses it:
- task 277: frame state, the dealing range and premium/discount;
- task 278: the chain;
- task 279: time in every frame, the false move.

AlgoResearch tests their direction calls before any backtest (task 281). The objective rule (task 284) addresses timing.

Which to start with is decided with the user. Each change is then judged by re-running the autopsy on its variant run, next to this one.
