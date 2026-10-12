# Trading Method: Top-Down Narrative Backtesting

## Purpose of this file

This is the trader's method, the way Henry studies price and finds his model, written so that an agent working in this repository understands it and builds toward it. Read it before working on:
- the liquidity engine;
- the context engine (`.kiro/specs/context-engine/`): frames, dealing ranges, premium and discount, draws, the context chain;
- the market narrative (`.kiro/specs/market-narrative/`): how finished candles formed, and the trade autopsy that reads a backtest's trades against them;
- AlgoResearch hypotheses, or anything that claims to capture "context", "bias", "narrative" or "objectives".

How to use it:
- **Sections 1–6 describe the method.** They are the trader's view of how price works. Treat them as the requirements for what the system must be able to read. They are not proven facts.
- **Section 7 is the logging template.** It is how every move is annotated and how the knowledge base grows.
- **Section 8 lists what has been measured so far.** Do not restate a claim the evidence contradicts.
- **Section 9 lists the rules for implementing any of it.** Follow them without exception.
- **Section 10 lists the definitions still awaiting the trader.** Do not hard-code a guess for any of them.

Related:
- `.kiro/specs/context-engine/`, the context model (decisions CE-D);
- `.kiro/specs/market-narrative/`, the narrative and the autopsy (decisions ND-D);
- `.kiro/specs/algo-research/`, how a claim is tested (pre-registration, slices, baselines; decisions AR-D);
- `.kiro/specs/liquidity-engine/` and `.kiro/specs/algo-backtester/`, today's engine and how it is backtested;
- `.kiro/steering/project-conventions.md`, terminology.

---

## 1. The core belief

> There is a storyline that price is narrating, and it is logical. The narrative is hidden in price, it is cyclic, and it is algorithmic in nature, with **time** as its core element. The next move is anticipatable: the bias, the objectives, and how the next candle is likely to form.

What follows from it:
- **Every candle is a story.** It forms around its open through **PO3** (accumulation, manipulation, distribution/expansion).
- **Price has two kinds of objectives:**
  - **liquidity**: resting orders beyond swing highs and lows, old highs and lows, session ranges;
  - **inefficiencies**: FVGs, imbalances, gaps.
- **Context decides how price behaves.** It treats PD arrays and liquidity differently depending on whether it is in **premium or discount** of its dealing range.
- **Candles are nested.** A year contains quarters, a quarter months, a month weeks, a week days, a day sessions, killzones and macros. The same story repeats at every frame.
- **Time matters as much as price.** Specific opens, candles, sessions and minutes (e.g. the 01:00, 05:00 and 09:00 New York H4 candles; 08:30 and 09:30) carry the day's important moves.

**The project's stance.** The belief is the hypothesis this system exists to test and exploit. A part of the method becomes a trading rule only when its read at the open predicts its outcome better than chance and simple rules, on data it wasn't designed on: a hypothesis pre-registered and run on the confirmation slice (`algo-research` spec), then a backtest variant judged by its pass mark, with the hold-out used once (`context-engine` Requirement 12).

---

## 2. The three questions

Ask these at **every frame**, from the year down to the macro. The answers make up the context.

### 2.1 Where has price come from?

- **The previous timeframe's outlook.** What did the parent candle and the previous candle of this frame do?
- **Premium or discount.** Where is price in the dealing range of the higher frame?
- **Market structure.** Breaks of structure and changes of character, by tier.
- **PO3 so far.** Has the parent candle accumulated, manipulated or expanded?
- **PD array trend.** Which arrays has price respected, and which has it traded through (inverted)?
- **Liquidity.** Which pools were taken last, and on which side?

### 2.2 Where is it now?

- **The current candle at every frame:** quarter, month, week, day, session, killzone, macro.
- **Premium or discount** of the current range.
- **The current market phase:**
  - accumulating;
  - manipulating;
  - distributing or expanding;
  - reversing;
  - retracing or continuing.
- **How price is treating** PD arrays, liquidity, imbalances and gaps right now.
- **The opportunities so far:** how many there were today, this week, across which assets.

### 2.3 Where is it likely to go next?

- **How the next candle is likely to map out,** at every frame: year, quarter, month, week, day, session, killzone, macro.
- **The objective.** Which objective is price likely to reach for, and where will it find support or resistance on the way to its true move in expansion?
- **The behaviour.** Is it likely to accumulate, induce liquidity, manipulate, expand or distribute, retrace, or continue? What is the trend?
- **The trade.** What would a high-probability trade in this case have yielded? Some setups give exceptional R:R (1:20, 1:30). Scalps can still be framed for good R:R.

---

## 3. The top-down routine

The backtesting study is done across **all assets**, from the largest frame down. Each frame has the same steps: annotate the opens, study how the candle formed, note the objectives and the reactions, and log the narrative.

### 3.1 Year and quarters

- **Split the year into four quarters** (3-month candles).
- **Annotate the yearly opening price** (1 January) and the **true yearly open** (1 April).
- **For each quarter, study how the candle formed (PO3):**
  - which objectives price manipulated into around the open;
  - which objectives it reached for in expansion;
  - how it reacted to PD arrays and liquidity pools, on the premise of premium and discount.

### 3.2 Month and its weeks

- **Mark the monthly opening price** (the 1st of each month).
- **Study how the month's 4 weeks gradually formed:**
  - how each week formed, and which objectives price was reaching for;
  - whether the month was bullish or bearish;
  - the economic calendar for the month, and the geopolitical events.
- **Classify each week:**
  - **Expansion / distribution:** explosive weeks.
  - **Accumulation:** consolidating weeks, setting the stage for expansion. Look at body size.
  - **Manipulation:** false price moves, often creating **turtle soup** (C1/C2/C3/C4).
- **Notice which weeks tend to carry most of the monthly range.**
- **As at every frame,** understand the candle's formation: PO3, PD arrays and liquidity, in premium and discount.

### 3.3 Week and its days

- **Mark the weekly opening price.**
- **Note gaps:** the New Week Opening Gap (**NWOG**), from Friday's close to Sunday's open.
- **Study how each day of the week formed:** Monday, Tuesday, Wednesday, Thursday, Friday (plus Saturday and Sunday for crypto).
- **Note the landscape:** the economic calendar, geopolitical events and holidays.
- **Notice how the days play out across the week:**
  - **In a bearish week:** which objectives above the market is price reaching for, and what is it manipulating into? (Mirror this for a bullish week.)
  - **Which day creates the week's false move?**
  - **Which day forms the high of the week,** or the low in a bullish week?
  - **Which objectives below was price reaching for?**
  - **How did price close out the weekly range?** This is the **TGIF** model: Friday's behaviour after the week's expansion.
- **How did price play out in gaps, PD arrays and liquidity?**

### 3.4 Day and its intraday candles

- **Mark the opening price of the day.** The trader uses **18:00** New York (see ND-D1; the engine's calendar uses 17:00).
- **Annotate:**
  - the **Asian range**;
  - the **true day open** (00:00 New York);
  - the New Day Opening Gap (**NDOG**) where it exists.
- **Study how the H4 candles print out.** Do the same for **H12, H8, H7, H6, H3 and H1**.
  - Which objectives is price reaching for?
  - Where does it reject, and where does it hunt opposing objectives?
- **Notice which candles carry most of the day's range.** This is how the **01:00, 05:00 and 09:00** New York H4 candles were found.
- **Notice when price forms the high or low of the day** around specific times, and how candles form in the process.
- **Turtle soup:** C1/C2/C3/C4 at the daily and intraday frames.
- **Study the killzones:** London, NY AM, NY PM.

### 3.5 Lower timeframes and execution

- **Step down timeframes gradually.** Notice how it would have been possible to take the good moves at specific times of day, both **reversals and continuations**.
- **Sniper entries.** How would you have captured the explosive moves with precise entries on the lower timeframes?
- **Event minutes.** Notice how price behaves at **08:30** and **09:30** New York.
- **ICT macros.** Notice how they behave.
- **Bigger moves.** Notice how some moves play into **swing and position trades**.
- **SD projections.** Notice how standard deviation projections line up with logical targets, when projected from the **manipulation leg** or from the **new leg formed after the manipulation**.
- **Outside the killzones.** Notice that opportunities still exist there, and that sniper moves can still be caught with the same logic: liquidity, PD arrays and specific candle opens.
- **Gaps.** How does price play out within them?

---

## 4. Concepts as used in this method

Each concept with its meaning here and where it lives in code. Status:
- **exists**: in the code today;
- **specified**: in a spec, not built yet;
- **proposed**: a default awaiting the trader (section 10), in a spec's stage 2 or in no spec yet.

| Concept | Meaning in this method | Code / spec | Status |
|---|---|---|---|
| **Open** | The first price of a candle at any frame. The reference for PO3: manipulation happens around it | `HTFBias.reference_open`; `CandleProfile.frame_open` | exists |
| **True open** | The quarter-theory reference open: 1 April (year), the 2nd month (quarter), the 2nd week (month), Monday 18:00 NY (week), 00:00 NY (day) | `market-narrative` Req 6 (stage 2), ND-D2 | **proposed** |
| **PO3** | Accumulation, manipulation, distribution/expansion: how every candle forms around its open | `market-narrative` Req 7 (stage 2), ND-D3 | **proposed** |
| **False move** | The manipulation leg: the excursion beyond the open against the candle's eventual direction | `CandleProfile.false_move_taken` (D1, as of t); context-engine Req 5 (any frame, as of t); `market-narrative` Req 1 (any frame, outcome) | exists / specified |
| **Liquidity** | Resting orders beyond swing highs and lows, previous day/week/month highs and lows, session ranges (e.g. the Asian range), equal highs and lows | `SetupSequenceDetector.pools()`, `LiquidityLevelDetector` | exists |
| **Inefficiency / imbalance** | FVGs and gaps that price tends to rebalance | `PDArrayDetector` (FVG); gaps in `market-narrative` Req 6 | exists / proposed |
| **PD arrays** | Order blocks, FVGs, breakers, IFVGs, BPRs | `PDArrayDetector` | exists |
| **Respected / inverted** | An array price traded into and closed back out of (respected), or closed through (inverted). Order flow comes from the pattern of these | no spec yet (MC-D5) | **proposed** |
| **Premium / discount** | Above or below the equilibrium (50%) of the dealing range | context-engine Req 3 (zone), CE-D2 | specified |
| **Dealing range** | The range between the swing high and swing low bracketing price at the frame | context-engine Req 3, CE-D2 | specified |
| **Market structure** | BOS (continuation) and CHoCH (first sign of reversal), by tier | `SwingStructureClassifier` | exists |
| **CISD** | Change in state of delivery: price closes through the open of the delivery sequence that took it to the raid | `CISDDetector` | exists |
| **Raid / sweep** | Price trades beyond a pool and reclaims | `SetupSequenceDetector` | exists |
| **Draw on liquidity** | The objective price is drawn to next | `CandleProfile.draw` (D1); context-engine Req 3–4 (any frame), CE-D4 | exists / specified |
| **Turtle soup, C1/C2/C3/C4** | C2 sweeps one side of C1 and closes back inside; C3 expands toward C1's other side; C4 continues or completes | `algo_research` `crt` event (C1–C3) | exists (research); C4 undefined |
| **Market phase** | Accumulating, manipulating, expanding/distributing, retracing, reversing, continuing | `market-narrative` Req 7 (stage 2), ND-D3, ND-D4 | **proposed** |
| **Week classes** | Expansion/distribution, accumulation (consolidative, small bodies), manipulation (false move, turtle soup) | `market-narrative` Req 7 (stage 2), ND-D4 | **proposed** |
| **TGIF** | Friday's retracement into the week's range after the week's expansion | `market-narrative` Req 7 (stage 2) | **proposed** |
| **NWOG / NDOG** | New week opening gap (Friday close → Sunday open), new day opening gap (17:00 close → 18:00 reopen) | `market-narrative` Req 6 (stage 2) | **proposed** |
| **Asian range** | 20:00–00:00 New York high and low | `asian_pools()` | exists |
| **Killzones** | London, NY AM, NY PM | `get_killzone()` | exists |
| **Manipulation window** | 01:00–13:00 New York (the 01:00, 05:00, 09:00 H4 candles) | `MANIPULATION_WINDOW` | exists |
| **ICT macros** | Short windows within sessions (e.g. 08:50–09:10, 09:50–10:10 NY) | `market-narrative` Req 6 (stage 2), ND-D2 | **proposed** |
| **08:30 / 09:30** | The New York data release and equities open minutes | `market-narrative` Req 6 (stage 2) | **proposed** |
| **SD projections** | Standard deviation multiples projected from the manipulation leg or the new leg after it; targets at about 2–2.5 SD, "often around 3–5R" | `StandardDeviationCalculator`; `sd_projection` | exists |
| **Opportunity** | A clear move a sniper entry could have caught: a raid, a CISD, then a move to the next objective | `market-narrative` Req 8 (stage 2), ND-D9 | **proposed** (hindsight only) |

When a concept says **proposed**, its definition is a default awaiting the trader's confirmation (section 10). Do not treat it as settled. **Specified** definitions carry proposed defaults too (the spec's decision table); the trader may still change them at review.

---

## 5. Phases of a candle (how to read where price is)

For a candle that closes up (mirror for down):

```
open ──► accumulation ──► manipulation ──► expansion ──► distribution ──► close
          (small range,    (false move      (true move     (after the high:
           around open)     below open,      to the         retrace, TGIF
                            takes liquidity, objective)     on the week)
                            taps a discount
                            PD array)
```

- **Accumulation:** price holds near the open in a narrow range, building the stage. Look at small bodies and overlapping candles.
- **Manipulation:** the false move. Price runs against the coming direction, takes liquidity (often a known pool such as the Asian range or the previous day or week low), and reaches a PD array in discount. Turtle soup lives here.
- **Expansion / distribution:** displacement in the true direction toward the objective. Explosive candles carry most of the range.
- **Retracement:** a pullback inside expansion into a PD array, then continuation.
- **Reversal:** the objective is reached, or the premise breaks, and a new cycle starts the other way.
- **Continuation:** after a retracement or consolidation, the same direction resumes.

The same phases apply to the year, the week, the day and the killzone. The study notices **which child candle** (which week, day, H4 or session) holds each phase.

---

## 6. Time as the core element

The method holds that time structures price:
- **Opens anchor the cycle:** the year, true year, quarter, month, week, day, true day, sessions and macros.
- **Specific candles carry the range:** some weeks of the month, some days of the week, some H4 candles of the day (01:00, 05:00, 09:00 New York).
- **Extremes form at specific times:** the false move and the high or low of the day, week and month.
- **Event minutes move price:** 08:30 and 09:30 New York, and the macros.
- **Context outside time:** the economic calendar, geopolitical events and holidays shape whether a week expands or consolidates.

Every time claim is a counting question: how often, against shuffled and sign-flipped price paths.

---

## 7. The narrative log (how every move is annotated)

> Annotate your findings and log the narrative for every move. Build a compounded knowledge base with this.

### 7.1 The two-records rule

Every annotated candle or move has **two separate records**:

| Record | When it is written | Contains | Role |
|---|---|---|---|
| **Read** | at the candle's open, **before** seeing what follows | where price came from, where it is, the expected next candle | the input (feature) |
| **Narrative** | after the candle closes | how it actually formed | the outcome (label) |

A narrative written while looking at the result always fits. The knowledge base only compounds edge if reads and narratives are kept apart, and reads are scored against narratives. In replay, the read is written blind: only bars closed by the open are visible.

### 7.2 Read template (written at the open)

```yaml
read:
  instrument: EURUSD
  frame: W1                    # Y, Q, MN, W1, D1, H4, SESSION, MACRO
  candle_open: 2025-03-09T22:00:00Z
  written_at: 2025-03-09T21:55:00Z
  came_from:
    parent_outlook: "Feb closed bearish, March opened below Feb's equilibrium"
    premium_discount: DISCOUNT        # of the parent's dealing range
    last_liquidity_taken: {side: SSL, source: PWL, timeframe: W1, at: 2025-03-06}
    structure: "D1 CHoCH bullish on Thursday"
    pd_array_trend: "H4/D1 bullish FVGs respected since Thursday"
  now:
    phase: MANIPULATION_COMPLETE      # ACCUMULATING, MANIPULATING, EXPANDING, RETRACING, REVERSING, CONTINUING
    gaps: [{type: NWOG, low: 1.0832, high: 1.0841}]
    calendar: ["Wed 08:30 CPI (USD, high)"]
    geopolitical: []
  next:
    direction: BULLISH
    expected_profile: TUE_LOW_EXPANSION
    false_move: {expected_day: TUE, into: "Asian low / NWOG"}
    draw: {price: 1.0931, source: PWH}
    support_on_the_way: "H4 bullish FVG 1.0855-1.0862"
    invalidation: 1.0809
    confidence: 2                    # 1-3
  remembered: false                  # in replay: do I remember this date?
  note: ""
```

### 7.3 Narrative template (written after the close; computed automatically by `market-narrative`)

Stage 1 of the spec computes the direction, the extremes and their times and children, and the false move. The phases, child classes, profiles, gaps, objectives taken and opportunities are stage 2.

```yaml
narrative:
  instrument: EURUSD
  frame: W1
  candle_open: 2025-03-09T22:00:00Z
  direction: UP
  range_atr: 1.9
  false_move: {side: DOWN, size_atr: 0.4, child: TUE, at: 2025-03-11T07:00:00Z}
  low: {child: TUE, at: 2025-03-11T07:00:00Z}
  high: {child: THU, at: 2025-03-13T14:00:00Z}
  phases: {accumulation: [MON], manipulation: [TUE], expansion: [WED, THU], distribution: [FRI]}
  child_classes: {MON: CONSOLIDATION, TUE: MANIPULATION, WED: EXPANSION, THU: EXPANSION, FRI: RETRACEMENT}
  range_share: {MON: 0.12, TUE: 0.21, WED: 0.46, THU: 0.30, FRI: 0.18}
  objectives_taken:
    - {side: SSL, source: ASIA_LOW, at: 2025-03-11T03:00:00Z, phase: FALSE_MOVE}
    - {side: BSL, source: PWH, price: 1.0931, at: 2025-03-13T14:00:00Z, phase: EXPANSION}
  arrays: [{type: FVG, tf: H4, outcome: RESPECTED, at: 2025-03-11T09:00:00Z, zone: DISCOUNT}]
  gaps: [{type: NWOG, filled_at: 2025-03-10T03:00:00Z}]
  tgif_retrace: 0.28
  profile: TUE_LOW_EXPANSION
  news: ["Wed 08:30 CPI: expansion began 08:30"]
  opportunities:
    - {direction: LONG, raid: ASIA_LOW, entry_at: 2025-03-11T08:15:00Z, best_rr: 6.2, frame: INTRADAY}
  story: "Opened in discount of February. Tuesday's London took the Asian low into the NWOG and the H4 FVG; Wednesday's CPI expanded through, Thursday took the PWH. Friday retraced 28%."
```

### 7.4 Scoring a read against its narrative

| Read field | Scored as | Baseline |
|---|---|---|
| `next.direction` | the candle's direction | coin flip; best simple rule (previous candle's direction, W1 trend, side of the open) |
| `next.expected_profile` | profile hit | the profile's base rate |
| `next.false_move.expected_day` | false-move child hit | uniform over the children; shuffled paths |
| `next.draw` vs `next.invalidation` | which is reached first | `p_coin` from the distances |
| `now.phase` | agreement with the narrative's phase at that time | the phase's base rate |

---

## 8. What has been measured so far (do not contradict without new evidence)

As of 2026-10-12, on Exness M1, EURUSD, GBPUSD, USDJPY and XAUUSD, 2025-01 → 2026-07 (in-sample for the engine). "Exploration" results come from AlgoResearch's exploration slice (2025-01 → 2025-07): they guide, they aren't evidence until a pre-registered hypothesis confirms them.

**Direction**

| Claim | Result | Source |
|---|---|---|
| The engine picks the day's direction | 44–45% of trades go the way their D1 candle closed: no better than a coin flip | `docs/backtests/AUTOPSY.md` |
| Trades in the day's direction do well | +0.46R vs −0.68R against (WICK); +0.58R vs −0.49R (BODY). Hindsight upper bound | liquidity-engine design, update 2026-10b; `AUTOPSY.md` |
| C1/C2 turtle soup alone predicts direction | coin flip on D1, H4, H1 | `docs/research/INDICATOR_IDEAS.md` |
| Mechanical biases (W1 trend, previous day, anticipation, HTF sweep) pick direction | none beats a coin flip | `INDICATOR_IDEAS.md` |
| Side of the D1 open at 05:00 New York picks the draw delivered (H010) | 56%; +9.7 points [+2.7, +16.5] over the stratified baseline. Exploration only | algo-research tasks, task 274 |
| Bias judged by delivery: the bias-side draw is reached (H001) | bullish: +14.6 points over the complement, +7.2 over stratified (passes); bearish: fails against stratified. Exploration only | algo-research tasks, task 274 |

**The engine's flaws (`docs/backtests/AUTOPSY.md`: hindsight labels; BODY run, 686 trades, −8.8R, unless noted; WICK agrees)**

| Claim | Result | Source |
|---|---|---|
| The engine fades the day's expansion | a third of trades went against the day and filled while it was expanding: no target hit, −0.84R each, −189R in all, more than the run's whole loss. 194 of 224 reacted to M15 swing raids | `AUTOPSY.md` |
| The setup chain works when the direction is right | with the day, filled after its false move and before its high/low: +1.80R (19% of trades); with the day and the raid beyond the open (the real false move): +0.75R. In the baseline (stops inside the spread) the same fills lost −0.46R: the rewrite fixed execution, not direction | `AUTOPSY.md` |
| With the right direction, timing still costs | filled inside the false move: −0.54R (45 of 54 stopped by the false move itself); filled after the day's extreme: −0.32R | `AUTOPSY.md` |
| Targets overshoot the day | 88% of with-day targets lay beyond the day's extreme (22% hit, vs 53% inside it) | `AUTOPSY.md` |
| Rough payoff of direction accuracy, today's execution | BODY: ~46% breaks even, 60% ≈ +0.15R a trade. WICK: ~59% breaks even | `AUTOPSY.md` |

**Time**

| Claim | Result | Source |
|---|---|---|
| Daily extremes form in the 01:00/05:00/09:00 H4 candles | +6 to +11 points over shuffled paths, but **gone against `sign_flip`** (lows of up days −6.5 points): the clustering is the volatility schedule, not turning points. Hand-set timing claims are withdrawn (AR-D21) | algo-research requirements, update 2026-10e |
| The day's false move forms in 06:00–12:00 New York | +6 points over shuffled paths; not yet tested against `sign_flip` | `INDICATOR_IDEAS.md` |
| Up weeks make their low on Monday or Tuesday | +9 points over shuffled paths: Monday +8, Tuesday +1 (chance); not yet tested against `sign_flip` | liquidity-engine design |
| FX day lows at the 17:00 rollover | 18–21% of FX day lows form on bars whose spread is 5× typical or more: bid dips, not real lows. Gold has none | `docs/research/VOLATILITY_PROFILE.md`; context-engine CE-D3 |

**Execution**

| Claim | Result | Source |
|---|---|---|
| Entry style creates an edge | no: ~7,000 setups entered four ways (market, limit at the array's middle, at its near edge, stop on the break) all land near 0R | context-engine requirements, introduction |
| SD 2.0 targets at R:R 10+ | hit about 3% of the time; the worst R:R band | `docs/backtests/SETUP_SEQUENCE.md` |
| Stopped trades reach +1R first | 32–35% of all stopped trades; 46–51% of stopped trades that were with the day | `SETUP_SEQUENCE.md`; `AUTOPSY.md` |
| Full system, best variant (BODY stop) | −0.01R per trade, CI −0.20 to +0.18, n = 686 | `SETUP_SEQUENCE.md` |

**Reading:**
- Time says *when* price moves (the volatility schedule), not yet *where* it turns.
- Direction is the open problem, and it costs almost the whole loss. The execution chain (raid → CISD → array) pays when the direction is right.
- The engine treats every raid as a reversal. The method separates the manipulation raid (against the candle's coming direction, beyond its open) from the raids an expanding candle makes on its way to its objective. That separation, the direction-reading of sections 2–3, is what the system lacks.

---

## 9. Rules for an agent implementing any of this

1. **Read before outcome.**
   - Never compute a feature, gate or context value from bars that close after the decision time. Use `compose_as_of_view()` for candles.
   - Narrative and label code lives where feature, event, filter and engine code can't import it (`algo_research/narrative/`, `labels.py`).
2. **No hindsight in rules.** "The low of the week formed Tuesday" is a narrative fact. A rule may only say "at Tuesday's open, given the read, …". If a request reads like a pattern seen on finished candles, write the as-of version and say so.
3. **Reuse definitions.**
   - Pools, arrays, raids, CISD, swings, killzones and the calendar come from the existing engine (section 4).
   - Do not write a second FVG or sweep detector.
   - If a definition is missing, add it once, in the engine or the context engine (`liquidity_engine/context/`), with tests.
4. **Proposed definitions stay configurable.** Anything marked **proposed** in section 4, or listed in section 10, is a setting with a default (in `config/research/*.toml` or `StrategyConfig`), never a constant buried in code. Alternatives are named variants.
5. **Every claim gets a baseline.**
   - Timing: `shuffled_path` and `sign_flip`.
   - Direction: best naive rule and coin flip.
   - Races: `p_coin` and random time.
   - Report the day-cluster bootstrap interval.
6. **Count the tries.** Exploration runs on the exploration slice. Hypotheses are committed before they run on the confirmation slice. Backtest variants go in the variant ledger. The hold-out is used once.
7. **Engine changes follow the protocol** (as the liquidity-engine updates and context-engine Requirements 11–12 apply it):
   - a `StrategyConfig` flag defaulting to old behaviour;
   - the golden run unchanged;
   - a variant run, paired comparison and decision diff.
8. **ATR is a unit, not a signal.** `project-conventions.md` bans lagging indicators in trading logic. ATR may normalise sizes and distances in research and reports (e.g. `atr_d1`). It must never gate or trigger a trade.
9. **Terminology** follows `project-conventions.md` (premium, discount, PD arrays, bullish and bearish arrays; never "supply/demand zone").
10. **Time zones.** Store UTC. Classify sessions, opens, killzones and macros in New York time with `zoneinfo`, DST-aware. Test both DST changes.
11. **AI stays bounded.** ML, RAG and LLMs may render stories, retrieve similar cases or draft hypotheses. They never set direction until a rule-based read has passed its hypothesis (AR-D10). An agent-drafted hypothesis still needs the trader's confirmation and counts in the ledger.
12. **When unsure, ask the trader.** For anything in section 10, do not guess. Propose a default, mark it **user review**, and ask.

---

## 10. Definitions awaiting the trader

Each has a proposed default. ND-D decisions live in `.kiro/specs/market-narrative/`, CE-D in `.kiro/specs/context-engine/`. Those marked "not in a spec yet" are recorded only here; when one is specified, it goes into the context-engine spec. None is settled until the trader confirms.

| ID | Question | Proposed default |
|---|---|---|
| ND-D1 | Day open: 17:00 or 18:00 New York? | Boundaries at 17:00 (engine calendar); the 18:00 reopen recorded as a reference |
| ND-D2 | True opens and the macro list | 1 April; the 2nd month; the 2nd week's Monday; Monday 18:00 NY; 00:00 NY. Macros: 02:33–03:00, 04:03–04:30, 08:50–09:10, 09:50–10:10, 10:50–11:10, 11:50–12:10, 13:10–13:40, 15:15–15:45 NY |
| ND-D3 | How to cut a candle into phases | Undefined: awaiting the trader (`market-narrative` Req 7) |
| ND-D4 | How to classify a child candle (expansion, consolidation, manipulation, retracement) | Body ratio and range share rules |
| ND-D5 | Week and day profiles | `MON_LOW_EXPANSION`, `TUE_LOW_EXPANSION`, `WED_REVERSAL`, `CONSOLIDATION_THU_REVERSAL`, `SEEK_AND_DESTROY`; day: `ASIA_LOW`, `LONDON_LOW`, `NY_AM_LOW`, `LATE_LOW`, `CONSOLIDATION` |
| ND-D9 | What counts as an opportunity | Raid, then M15 CISD within 4 hours, then a move ≥ 1 D1 ATR to the next objective |
| MC-D5 | Order flow from PD arrays | The last 3 respected/inverted outcomes on H4/D1 all agree. Not in a spec yet |
| MC-D8 | What starts a delivery | Opposite-side pool taken, then an H4 CISD before the raid extreme breaks. Not in a spec yet |
| CE-D4 | Which objective is the draw (was MC-D10) | Specified in context-engine: with a trend, the nearest objective on the trend's side; otherwise the nearer objective. The earlier proposal here, the nearest untaken opposite-side pool, is an alternative to raise at review |
| MC-D11 | When the day's context is judged | The first M15 close of the day (alternatives: 00:00, 01:00 NY). Not in a spec yet: the context engine recomputes its chain at every execution close |
| ND-D6 | The narrative's direction | The close against the open; judging by the draw delivered (AR-D18) comes in stage 2 |
| ND-D7 | The narrative's price basis | FX bars 17:00–17:29 NY flattened at the last clean close, until the spread-based quarantine (CE-D3) is built |
| — | C4 in turtle soup | Undefined: what C4 does after C3 |
| — | H7 | Not in `Timeframe`; 7 hours doesn't tile the day. Add only if the trader confirms its use |
| — | Accumulation week: "body size" threshold | Undefined |
| — | "Specific candle opens" used for sniper entries | Undefined: which opens, at which frames |

When the trader answers one, update this table, the spec's decision table, and the config default together, in one commit.
