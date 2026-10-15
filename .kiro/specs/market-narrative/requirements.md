# Requirements Document

**Spec**: Market Narrative

## Introduction

`trading-method.md` (the trader's method) keeps two records for every candle: the **read**, written at the open before anything that follows is known, and the **narrative**, written after the close, telling how the candle actually formed. Reads are scored against narratives, and the knowledge base compounds only while the two stay apart.

This spec builds the narrative side, then uses it first to diagnose the engine.

The diagnosis comes first because a prototype (2026-10-12) already showed what it can do. Every filled trade of the BODY run (`475491a89d91`, 686 trades, −8.8R) was labelled against how its D1 candle formed:
- **Direction.** Trades went the day's way 44% of the time.
- **The chain works when the direction is right.** With the day and filled after the day's false move, the same raid → CISD → array chain made +1.80R a trade (19% of trades, +239R).
- **The engine fades the day's expansion.** Against the day and filled while the day was expanding: a third of all trades, no target hit, −0.84R each, −189R. That is more than the run's whole loss. 194 of the 224 reacted to M15 swing raids: the engine reads every raid as a reversal, including the raids an expanding day makes on its way to its objective.

So the backtest's "−0.01R" breaks down into flaws, ranked by cost, in the trader's own terms. This spec turns the prototype into a tool that does this for every run.

What it builds:
1. **Stage 1 (now):**
   - **The candle narrative:** at any frame, how each finished candle formed.
   - **The trade autopsy:** every filled trade of a run, labelled against the narratives of its candles, and the run's R split by failure mode.
   - It is written for every new run, and by a command for any old run, without Docker.
2. **Stage 2 (later, each waiting on the trader's definitions):**
   - opens and reference times;
   - phases and child classes;
   - profiles;
   - opportunities;
   - reads and their scoring, including the blind-read tool.

Where it sits:
- **`algo_research/narrative/`**, beside AlgoResearch's labels. It is hindsight code: nothing that decides (the engine, features, events, filters, `agent/`) may import it (Requirement 5).
- **`algo_backtester/autopsy.py`** reads a run directory and writes the autopsy beside the report.

**Guiding constraint:** the narrative is hindsight, so it **diagnoses**; it never decides. A flaw it finds becomes an engine change only through the existing route: a configurable rule, tested in AlgoResearch or as a backtest variant, on data the diagnosis didn't use.

---

## Glossary

- **Frame candle**: one candle of a frame on the strategy calendar (D1 opens at 17:00 New York; H4 at 17:00, 21:00, 01:00, 05:00, 09:00 and 13:00; W1 at Sunday 17:00).
- **Narrative**: the description of a finished frame candle (Requirement 1).
- **Direction**: UP when the candle closed above its open, DOWN below it, FLAT otherwise (ND-D6).
- **False-move extreme**: the extreme on the side against the candle's direction: the low of an UP candle, the high of a DOWN candle.
- **Expansion extreme**: the extreme on the direction's side: the high of an UP candle, the low of a DOWN candle.
- **Inverted candle**: one whose expansion extreme formed before its false-move extreme (an UP day that made its high, then its low, then closed above its open).
- **Child**: the next frame down, used to say where in the candle each extreme formed (D1 by H4, W1 by D1, H4 by H1).
- **Bias frame (of an autopsy)**: the frame whose candle the failure modes are judged against. Default D1.
- **With / against**: a trade is *with* a candle when its direction matches the candle's (LONG and UP, SHORT and DOWN).
- **Fill phase**: where in the bias candle's formation the fill landed (Requirement 3.2).
- **Failure mode**: the one bucket the autopsy gives each trade (Requirement 3.4).

---

## Non-Goals

- **Rules.** Nothing here gates or triggers a trade. A finding becomes a rule only through a hypothesis or a variant (trading-method.md, section 9).
- **Re-running the engine.** The autopsy reads what a run already wrote. It needs no Phase A and no candle store.
- **Stage 2 definitions.** Phases, child classes, profiles, opportunities and reads wait for the trader (ND-D1 to ND-D5, ND-D9). Requirements 6–9 record them so they aren't lost; they aren't scheduled.
- **A second rollover rule.** Stage 1 uses a time window, because a run's candles carry no spread. When context-engine task 276 builds the spread-based quarantine, the narrative takes it as a price basis, and the time window stays a named alternative (ND-D7).

---

## Requirements

### Requirement 1: The Candle Narrative

**User Story:** As the trader, I want every finished candle described the way I study it (its open, its false move, its expansion, and where each formed), so that the engine's trades can be read against what price actually did.

#### Acceptance Criteria

1. FROM a series of bars finer than the frame (each with its opening time, open, high, low and close), THE narrative SHALL describe each frame candle on the strategy calendar:
   - its start and end, open (the first bar's open), high, low, close (the last bar's close), and range;
   - the opening times of the bars that made the high and the low (the first such bar on a tie);
   - its direction (ND-D6);
   - its false-move extreme and expansion extreme, their prices and times, and whether it is inverted;
   - the false move's size (the open to the false-move extreme) and its share of the range;
   - the child holding each extreme, as the child candle's index within the frame candle (0 for the first child).
2. A candle SHALL be marked incomplete when the bar series starts or ends inside it. An incomplete candle's fields describe only the bars present, and consumers SHALL treat it as unknown.
3. THE narrative SHALL work unchanged at any frame. It reads the bars and the calendar, never a timeframe constant (Property 1).
4. A candle's narrative SHALL depend only on its own bars (Property 2).
5. THE frames SHALL be configurable; the default is W1, D1 and H4.

### Requirement 2: Analysis Prices for the Narrative

**User Story:** As the trader, I want the narrative's highs and lows to be market prices, not the bid dipping at the 17:00 rollover, so that a fake day low doesn't mislabel the day.

#### Acceptance Criteria

1. THE narrative SHALL read bars through a configurable price basis (ND-D7):
   - `NONE`: the bars as recorded;
   - `ROLLOVER_WINDOW` (default): for the configured instruments, a bar opening in the first `minutes` after 17:00 New York (default 30) is flattened: its open, high, low and close are all set to one price.
2. THE flattening price SHALL depend on what came before the bar:
   - **After a pause** (the last clean bar within `closure_minutes`, default 60): the last clean close, as context-engine CE-D3 does.
   - **After a closure** (the weekly reopen, a holiday) **or at the start of a series:** the open of the first clean bar after the window. Friday's close is days old by Sunday's reopen, so the gap between them is real (an NWOG); only the blown-out minutes after the reopen are not.
   - **With no clean bar after the window:** the bar is dropped.

   Added 2026-10-13: flattening to Friday's close erased the NWOG and moved Monday's D1 open (EURUSD 2026-10-12: 1.12011 instead of 1.11861). Dropping the leading bars made a short run's first day incomplete.
3. Instruments not configured SHALL be unchanged (gold by default).
4. THE price basis SHALL apply only to the narrative. Fills and the run's journal are never touched.

### Requirement 3: The Trade Autopsy

**User Story:** As the trader, I want each of the engine's trades labelled against how its candles formed, and the run's result split by failure mode, so that every backtest tells me which part of the engine to fix first.

#### Acceptance Criteria

1. FOR every filled trade of a run, closed by stop, target or time, THE autopsy SHALL record:
   - from the journal: time, instrument, setup, direction, entry, stop, target, fill time, exit reason, net R, MFE;
   - for each frame: the direction of the frame candle holding the fill, and whether the trade was with it;
   - the bias frame's candle: its start, the fill phase, and the fields of 3.3.

   Trades still open at the end of the run SHALL be counted and left out.
2. THE fill phase SHALL compare the opening time of the bar holding the fill with the bias candle's extremes:
   - `BEFORE_FALSE_EXTREME`: earlier than the false-move extreme's bar;
   - `AT_FALSE_EXTREME`: the same bar;
   - `IN_EXPANSION`: after it, up to and including the expansion extreme's bar;
   - `AFTER_EXPANSION`: after the expansion extreme's bar;
   - `INVERTED`: the candle is inverted;
   - `UNKNOWN`: the candle is FLAT, incomplete or missing.
3. FOR the bias candle, THE autopsy SHALL also record:
   - **stopped by the false move:** the trade is with the candle, filled `BEFORE_FALSE_EXTREME`, stopped out, and the false-move extreme lies beyond the stop;
   - **target beyond the expansion:** the trade is with the candle and its target lies beyond the expansion extreme;
   - **raid side:** whether the setup's swept level (from the run's recorded context) lay beyond the candle's open on the side opposite the trade (below the open for a long), and whether the raid happened inside the same candle;
   - **fill side:** whether the fill was on the trade's favourable side of the open (a long below it, a short above it);
   - **as-of shape**, from the bias candle's bars that closed before the fill only:
     - `WITH_SHAPE` when the trade follows the shape so far;
     - `FADES_SHAPE` when it opposes it;
     - `UNFORMED` otherwise.

     The shape is UP when the candle's low so far came before its high and the last close is above the open, and DOWN in the mirror case.
4. EACH trade SHALL get one failure mode, from the bias candle (ND-D8):
   - `UNKNOWN`: the fill phase is UNKNOWN;
   - `AGAINST_EXPANSION`: against the candle, filled `IN_EXPANSION`;
   - `AGAINST_OTHER`: against the candle, any other phase;
   - `WITH_EARLY`: with it, filled `BEFORE_FALSE_EXTREME` or `AT_FALSE_EXTREME`;
   - `WITH_ON_TIME`: with it, filled `IN_EXPANSION`;
   - `WITH_LATE`: with it, filled `AFTER_EXPANSION`;
   - `WITH_INVERTED`: with it, the candle inverted.
5. THE split SHALL give, per failure mode and for any other autopsy column asked:
   - the count and the share of trades;
   - the share that hit the target;
   - mean net R with a 95% day-cluster bootstrap interval (AlgoResearch's `Bootstrap`, resampling trading dates);
   - the sum of net R.

   The sums over the failure modes SHALL equal the run's net R over the labelled trades.
6. THE autopsy SHALL be deterministic: the same run directory and configuration give byte-identical files. The bootstrap seed derives from the run id.

### Requirement 4: The Autopsy Report

**User Story:** As the trader, I want the autopsy beside every backtest report, and for the runs we already have, so that I read it with the trades.

#### Acceptance Criteria

1. `write_autopsy(run_dir)` SHALL write `autopsy.csv` (one row per labelled trade) and `autopsy.md` into the run directory.
2. `autopsy.md` SHALL hold:
   - a header that says the labels use hindsight and diagnose, never decide;
   - the configuration (frames, bias frame, price basis);
   - the share of trades with each frame's candle;
   - the split by failure mode;
   - the with-candle failures (stopped by the false move, target beyond the expansion, stopped trades that first reached +1R);
   - the splits by raid side, fill side, as-of shape, instrument and New York hour of the fill.
3. `python -m algo_backtester autopsy <run_dir> [--config <toml>]` SHALL write the autopsy for any run directory that holds `journal.csv`, `context.json` and `candles.json`, and refuse any other directory with exit code 2.
4. `python -m algo_backtester run` SHALL write the autopsy after the report.
   - A run with no filled trades SHALL still get an autopsy that says so.
   - When the autopsy can't apply (5 below), the run SHALL say why and still succeed.
5. THE autopsy SHALL refuse a run whose recorded candles are not finer than every configured frame, naming the frame.

### Requirement 5: Hindsight Isolation

**User Story:** As the researcher, I want the narrative kept out of everything that decides, so that no rule can read the future through it.

#### Acceptance Criteria

1. NOTHING in `liquidity_engine/`, `agent/`, `algo_research/features/`, `algo_research/frame.py`, `algo_research/events.py` or `algo_research/filters.py` SHALL import `algo_research.narrative` or `algo_backtester.autopsy` (a test checks the imports).
2. THE as-of shape (Requirement 3.3) SHALL read only bars that closed before the fill. It is the only as-of column, and it is reported as exploration, not as a rule.

---

## Stage 2: Recorded, Not Scheduled

Each waits on the trader's definitions (the Open Decisions below). None is built until the trader confirms its decision.

### Requirement 6: Opens and Reference Times

The narrative SHALL record, per candle where they apply:
- the true opens (ND-D2);
- the 18:00 New York reopen beside the 17:00 open (ND-D1);
- NWOG and NDOG, and when each was filled;
- the macros and the 08:30 and 09:30 New York minutes: the move within each.

### Requirement 7: Phases and Child Classes

The narrative SHALL:
- cut each candle into accumulation, manipulation, expansion and distribution (ND-D3);
- classify each child as expansion, consolidation, manipulation or retracement, by its body ratio and range share (ND-D4);
- give each child's share of the range;
- measure Friday's retracement into the week's range (TGIF).

### Requirement 8: Profiles and Opportunities

The narrative SHALL:
- name each week's and day's profile (ND-D5);
- list its opportunities: a raid, then a CISD, then a move to the next objective (ND-D9).

The autopsy SHALL then list the opportunities the engine missed, with the rule or absence that missed each.

### Requirement 9: Reads and Their Scoring

1. A read (trading-method.md, section 7.2) SHALL be stored per candle, written before the candle's first bar closes, and scored against its narrative (section 7.4) with the baselines given there.
2. A blind-read tool SHALL show the trader:
   - the as-of chart at a candle's open, with the date (and optionally the instrument) hidden;
   - the frames above.

   It SHALL record the read, then reveal the narrative. Reads made after the reveal never count.
3. THE scoring SHALL report the trader's direction accuracy with a day-cluster interval, against the coin flip and the best naive rule. A pilot of about 200 reads separates 60% from a coin flip.

---

## Open Decisions

Proposed defaults apply unless the trader changes them. Stage 1 uses ND-D6 to ND-D8 and ND-D10; the rest belong to stage 2. The IDs ND-D1 to ND-D5 and ND-D9 are those of `trading-method.md`, section 10.

| # | Decision | Proposed default |
|---|---|---|
| ND-D1 | Day open: 17:00 or 18:00 New York? | Boundaries at 17:00 (the engine's calendar); the 18:00 reopen recorded as a reference (stage 2). The 17:00–18:00 hour is where the FX bid dips (Requirement 2). |
| ND-D2 | True opens and the macro list | 1 April (year); the 2nd month (quarter); the 2nd week (month); Monday 18:00 NY (week); 00:00 NY (day). Macros: 02:33–03:00, 04:03–04:30, 08:50–09:10, 09:50–10:10, 10:50–11:10, 11:50–12:10, 13:10–13:40, 15:15–15:45 NY. |
| ND-D3 | How to cut a candle into phases | Awaiting the trader. |
| ND-D4 | How to classify a child candle | Body ratio and range share rules; awaiting the trader. |
| ND-D5 | Week and day profiles | Week: `MON_LOW_EXPANSION`, `TUE_LOW_EXPANSION`, `WED_REVERSAL`, `CONSOLIDATION_THU_REVERSAL`, `SEEK_AND_DESTROY`. Day: `ASIA_LOW`, `LONDON_LOW`, `NY_AM_LOW`, `LATE_LOW`, `CONSOLIDATION`. |
| ND-D6 | The narrative's direction | `CLOSE_VS_OPEN`. The trader judges bias by delivery, not the close (AR-D18): `DRAW_DELIVERED` is the stage-2 alternative, once the draw is defined at every frame (context-engine Requirement 3). |
| ND-D7 | The narrative's price basis | `ROLLOVER_WINDOW`: EURUSD, GBPUSD and USDJPY bars opening 17:00–17:29 New York flattened at the last clean close after a pause, or at the first clean open after a closure of more than 60 minutes (CE-D3 measured FX spreads 3–8× typical through 17:00–17:15). Replaced by the spread-based quarantine once context-engine task 276 exists. |
| ND-D8 | Fill phases and failure modes | As Requirements 3.2 and 3.4, judged on the bias frame. A trade held past its candle is still judged by the candle it filled in. |
| ND-D9 | What counts as an opportunity | A raid, then an M15 CISD within 4 hours, then a move of at least one D1 ATR to the next objective (ATR as a unit only). |
| ND-D10 | Frames and bias frame | W1, D1 and H4; bias frame D1, the frame the engine's daily bias targets. |
| ND-D11 | Names and numbering | Package `algo_research/narrative/`, module `algo_backtester/autopsy.py`, spec `.kiro/specs/market-narrative/`, decisions ND-D. Tasks continue the platform sequence from 290. |

---

## Update 2026-10-14: The Blind Replay

Requirement 9 is brought forward, for gold first. On 2026-10-13 the trader explained the read behind a gold trade: one thesis carried across days (the phase, the one array that matters, a realistic draw, an invalidation), with lower timeframes only timing the entry. The engine has no such thesis, and the trader's own read has never been measured where hindsight can't help. The blind replay measures it, and gives the engine its first honest labels.

### Requirement 10: The Blind Replay

**User Story:** As the trader, I want to read days I don't remember, as of their open, and be scored on them, so that we know whether my read beats chance before the engine is taught it.

#### Acceptance Criteria

1. THE replay SHALL offer one instrument's trading dates from the exploration slice (AR-D3), in a fixed shuffled order, resuming a day in progress first and skipping days already revealed. The chart SHALL hide the date and year until the reveal and show the weekday; prices are real. A "show date" switch SHALL be recorded on the day.
2. Before the read is saved, the chart SHALL show only bars that closed by the trading day's open (17:00 New York), at W1, D1, H4, H1, M15, M5 and M1. THE server SHALL refuse any bar after the day's revealed time.
3. THE read (the daily thesis, a reduced trading-method.md section 7.2) SHALL hold:
   - a bias: `BULLISH`, `BEARISH` or `NO_THESIS`;
   - for a thesis: a draw above the open price and an invalidation below it (mirrored for bearish), and optionally the key array (low, high, timeframe, kind);
   - confidence 1 to 3, a "remembered" flag and a note.
   A read that breaks these rules SHALL be refused, naming the field.
4. ONCE the read is saved it SHALL NOT change. THE trader then steps time forward (by an M1, M5, M15 or H1 bar, or to a New York time within the day); each timeframe shows its forming candle as of the revealed time.
5. AT the revealed time the trader MAY mark a trade (direction, entry, stop, target; at most three a day). It SHALL be refused unless stop and target lie on opposite sides of the entry.
6. ENDING the day SHALL reveal the rest of the D1 candle, its narrative (Requirement 1) and the scores. Nothing is accepted after the reveal.
7. THE scores SHALL be computed from the M1 bars after the read (or after the mark, for a trade) up to the D1 close:
   - **thesis:** `DRAW` when the draw is reached before the invalidation, `INVALIDATED` when the invalidation is reached first or in the same M1 bar, `NEITHER` otherwise; with `p_coin`, the chance a driftless path reaches the draw first, `|open − invalidation| / (|draw − open| + |open − invalidation|)`; and the direction against the candle's close (ND-D6);
   - **trade:** filled at the first bar after the mark whose range holds the entry; then `STOP` or `TARGET`, whichever comes first, the stop winning a tie and counting from the fill bar, the target from the next bar; else `OPEN`, marked to the D1 close; `NOT_FILLED` when never filled. The result is in R, before costs.
8. EACH day SHALL be stored as one JSON file under `data/journal/blind/<instrument>/`, which git ignores, written whole or not at all, with the wall-clock time of the read, of each trade and of the reveal.
9. THE summary SHALL report, over revealed days: thesis and no-thesis days; the `DRAW` rate of thesis days with a 95% bootstrap interval over trading dates, beside the mean `p_coin` and the coin flip; direction accuracy; and trades (count, mean R, total R).

---

## Update 2026-10-14b: The Replay as a Chart Workstation

The trader asked for the replay to work like their TradingView: the timeframes they use, the day printing as if live, and the tools to mark PD arrays, anchor targets and place trades, with a written narrative. Their marks become data: each drawing is kept with the moment it was made, so later the engine's arrays can be set beside the ones the trader marked.

### Requirement 11: The Replay Chart

**User Story:** As the trader, I want to read, mark and trade a replayed day the way I do on my own charts, so that what I see and do is recorded honestly and can be compared with the engine.

#### Acceptance Criteria

1. THE chart SHALL offer M1, M2, M3, M4, M5, M10, M15, M20, M30, M45, H1, H3, H4, H6, H7, H8, H12, D1, W1 and MN1. Intraday bars SHALL be counted from the trading day's 17:00 New York open, so a timeframe that doesn't divide the day (H7, M45) restarts at each open; W1 opens Sunday 17:00; MN1 holds the trading dates of a calendar month. Where the engine's calendar has the timeframe, the bars SHALL be the same.
2. M1 is the finest data: there are no second charts (the MT5 terminal gives no tick history for these dates). Playing SHALL reveal one step at a time, the newest minute drawn open → extreme → extreme → close; the page says that the path inside a minute is simulated.
3. A step that reveals no bar, into a market pause, SHALL land that step past the reopen.
4. THE drawing tools SHALL be: horizontal line and ray, vertical line, trend line, box (a PD array: side, kind, timeframe, an optional 50% line, extend right), fib/SD projection (editable levels; default 1, 0.786, 0.705, 0.618, 0.5, 0, −0.5, −1, −1.5, −2, −2.5, −4), long and short position (entry, stop, target), and text; with select, drag, delete, undo, a magnet to the bar's open, high, low and close, and hide.
5. EACH drawing SHALL be stored with the day, stamped with the phase (`read`, `intraday`, `narrative`) and the revealed time it was made in; an edit SHALL be stamped too. THE read SHALL keep a copy of the drawings made before it was saved, and the reveal a copy of those made before it; later edits never change those copies.
6. A position drawing MAY be placed as a trade at the revealed time (Requirement 10.5, linked to the drawing). WHILE the day is live, each trade SHALL show its state as of the revealed time: `PENDING` until filled, then `OPEN` with its R, `STOP` or `TARGET`.
7. AFTER the reveal, the trader MAY write the day's narrative in their own words; it is stored apart from the read.

---

## Update 2026-10-14c: Chart Settings, Favourites and More Tools

TradingView's own chart can't be used: its charting library is licensed to companies for public products only, and the free widget runs on TradingView's data with no replay and no access to the drawings. So the replay chart takes on the free tier's conveniences the trader asked for.

### Requirement 12: The Chart, Made the Trader's Own

1. EACH drawing SHALL have a settings dialog (double-click, or its right-click menu): line colour, width and style; fill and opacity; the box's 50% line; extend left and right; price labels; label text, colour and size; fib levels (value, colour, visible; add, remove, defaults); coordinates; lock and hide. "Save as default" SHALL make it the look of new drawings of that kind.
2. THE tools SHALL add: ray, extended line, arrow, parallel channel, trend-based fib extension, date and price range, brush; and Shift + drag SHALL measure (price, percent, bars, time) without saving a drawing.
3. FAVOURITES: a tool's right-click menu SHALL add it to or remove it from a movable favourites bar; the timeframe menu SHALL star the timeframes the bar shows.
4. THE chart settings SHALL set: candle and wick colours, borders; background, grid, theme (system, light, dark), crosshair, watermark; price scale (regular, logarithmic, percent) and auto-scale; day separators, the day (17:00) and midnight (00:00) opens per day, and shading of the engine's killzones (London 02–05, NY AM 07–10, NY PM 13:30–16, New York time) and the Asian range (20–00).
5. A right-click on a drawing SHALL offer settings, clone, lock, hide, bring to front, send to back and delete; on the chart, chart settings, reset view, hide drawings and remove all. An object list SHALL show, select, hide, lock and delete drawings.
6. PREFERENCES (chart settings, favourites, defaults per tool, the last timeframe and speed) SHALL be kept in this browser only; the page SHALL work without them. Drawings and their styles are stored with the day (Requirement 11.5).

---

## Update 2026-10-15: The Analyst's Chart

The trader wants AgentICTrader to become "a technical analyst living in the charts". The engine would mark up, execute and manage its trades on the same chart where the trader marks up their own read. They asked for TradingView itself. Its charting library is free only for public deployments with TradingView's attribution, not for private use, so the chart stays on Lightweight Charts and takes on the free tier's behaviour. The chart code stays separate from the pages, so the library could replace it if AgentICTrader is ever published.

### Requirement 13: A Chart That Moves Freely

1. THE chart SHALL move in any direction. Dragging the pane moves time and price together, and a vertical drag switches the price scale from auto-fit to manual, as TradingView does. Dragging the price axis stretches or squeezes the price range, and a double-click on it fits the data again.
2. AN **A** button at the price scale SHALL show whether the scale fits the data, and switch it back. The chart's right-click menu and the Scales settings SHALL offer the same, and **Lock price to bar ratio**: while it is on, zooming time zooms price by the same factor, so candles keep their shape.
3. THE price scale SHALL show the time left in the current bar under the last price, measured from the replay's clock, not the computer's.
4. THE page's own controls (reset view, timeframe change, play) SHALL leave a manual price range as the trader set it, until they fit it again.

### Requirement 14: Visibility Intervals

1. EACH drawing SHALL have a Visibility tab, as TradingView's: minutes 1-59, hours 1-24, days, weeks and months, each switched on or off with its own from-to range. A drawing shows only on the chart timeframes inside its intervals. A new drawing is visible everywhere, unless the tool's saved default says otherwise.
2. THE intervals SHALL be kept with the drawing (Requirement 11.5), and checked by the server like its other options.
3. THE engine's PD arrays SHALL follow the same rule. Each array timeframe has an interval of chart timeframes it shows on, M15 arrays from M1 to H1 by default, for example. The trader can change the intervals; they are kept in this browser.

### Requirement 15: One Chart, Two Analysts

1. THE replay page and the engine watch SHALL become one app with a mode: **You** (the blind replay, Requirements 10-12) and **Engine** (the watch, algo-backtester Requirement 15). Both modes use the same chart, tools, settings, favourites and visibility intervals. Blindness holds: the You mode never shows an engine layer for a day the trader has not revealed.
2. THE layout SHALL follow TradingView's:
   - instrument tabs along the top;
   - the timeframe and tool bars;
   - the drawing strip on the left;
   - a right-hand panel with a watchlist (each instrument's last price and change as of the replay's clock, never later) above the mode's own panel.
