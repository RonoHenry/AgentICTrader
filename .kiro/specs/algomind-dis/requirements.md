# Requirements Document

**Spec**: AlgoMindDIS (Directional Intelligence Service)
**Source**: the trader's specification "AlgoMindDIS — Technical Architecture & Development Specification" v1.0.0 (2026-11-02). Section numbers (§) below are that document's.

## Introduction

AlgoMindDIS is the new version of Algo Mind (2026-11-03, the trader: "AlgoMindDIS is the new version"). It is a deterministic reasoning service that answers five questions for each market (§1.3):
1. What is the current market context?
2. Where is price relative to the dealing ranges that matter?
3. Which liquidity objectives could be drawing price?
4. What does the current delivery say about intent?
5. Does the evidence support a bullish, bearish or neutral hypothesis?

It holds that hypothesis as a state with its evidence and its invalidation (§10). The setup engine is qualified against it (§12).

**What exists already.**
- Context-engine Requirement 35 built the held state (§10's record and its delivered/invalidated ends), filled by reader v0's turtle-soup narrative. It failed H-AE.
- Context-engine Requirement 37 put that state on paper (2026-11-03).

That is one source in AlgoMindDIS's container, not this specification. This spec builds the rest:
- the analyzers (§5-8);
- the evidence synthesis (§9);
- the multi-timeframe reasoning (§11);
- the contract and the setup qualification (§12);
- the replay and evaluation (§16);
- the activation modes (§18 Phase 7).

**The order is §18's.** Reader v0 keeps the paper agent until AlgoMindDIS passes its test (the trader, 2026-11-03: "Build the full spec", shadow first, the §16 test before it drives the paper agent).

**What we already know about the inputs.** Each of §9.4's evidence categories, tested alone as a direction source, came out no better than a random walk from the same close:
- trend and structure: H-K and the trader's five trend signals;
- the draw on liquidity: the nearest pool;
- premium and discount;
- PD arrays;
- the delivery phase.

§9 combines them with relationships and holds the result, which none of those tests did. §16 decides whether the combination adds what the parts lack.

## Glossary

- **Closed candle at t:** a candle whose close time is at or before t. Every analyzer reads only these (§16.1, §19.6).
- **Frame:** one timeframe's closed candles, oldest first (`liquidity_engine.context.frame_state.Candles`).
- **Primary timeframe:** D1 (§11). **Higher timeframes:** W1 and MN1. **Lower timeframes:** H4 and H1, live and on the intraday snapshot only.
- **ADR:** the mean D1 range over the last 20 closed days.

## Requirements

### Requirement 1: The Audit and the Boundaries (§3, §18 Phase 0, §19.1-19.3)

**User Story:** As the trader, I want AlgoMindDIS built on the engine's own detections, so that it interprets what the engine already sees and never re-detects it differently.

#### Acceptance Criteria

1. THE audit (design.md, "Phase 0: the compatibility report") SHALL map every component of §4-§8 to the module that already detects it, or name it a gap.
2. AlgoMindDIS SHALL read swings, gaps, order blocks, breakers, pools, dealing ranges, CISD and delivery phases through the existing functions named in the audit. A gap is filled in AlgoMindDIS only when no function exists, and the audit records it.
3. AlgoMindDIS SHALL NOT place, change or close an order, set a stop or size a position (§2.5, §19.3).
4. THE liquidity engine, the setup engine and the paper agents SHALL run unchanged when AlgoMindDIS is disabled or fails (§19.8).
5. The knowledge graph, AlgoRAG and an event bus are out of scope (§14: not a runtime dependency). "Events" are observations computed from closed candles (Requirement 14).

### Requirement 2: The Records (§4, §5, §6, §7.2, §9.1, §9.3)

**User Story:** As the trader, I want every judgment kept as a record with its origin, so that any decision can be traced.

#### Acceptance Criteria

1. THE package SHALL define frozen records for:
   - `DealingRange` (§5.2): id, timeframe, high, low, equilibrium, origin, established at, validity and its invalidation;
   - `PricePosition` (§5.3): the range, position 0-1, and zone;
   - `LiquidityObjective` (§5.4): id, price, type (EXTERNAL, INTERNAL, TEMPORAL), source, side, timeframe, range, status (IDENTIFIED, APPROACHING, SWEPT, INVALIDATED), significance, formed and swept times;
   - `ArrayContext` (§6.2): the array and its nine evaluations;
   - `StructureEvent`: BOS or MSS, with direction, level and time;
   - `DeliveryState` (§7.2): BULLISH_DELIVERY, BEARISH_DELIVERY, CONSOLIDATION, TRANSITIONAL or UNCONFIRMED, with its evidence;
   - `TimeframeContext` (§5.1);
   - `Evidence` (§9.3): id, category, direction, timeframe, source event, significance, time, validity, dependencies;
   - `MarketNarrative` (§9.1);
   - `DirectionalBiasOutput` (§12).
2. EVERY record SHALL serialize to JSON and back unchanged.
3. Identifiers SHALL be derived from content (market, timeframe, kind, formation time, price), so that the same bars always give the same ids (§13.3, §19.4).

### Requirement 3: Market Context and Structure (§5.1, §7.1)

**User Story:** As the trader, I want each timeframe's structure kept apart from its location and its delivery, so that a bearish H1 inside a bullish daily isn't read as a daily reversal.

#### Acceptance Criteria

1. FOR each timeframe THE analyzer SHALL give:
   - its swing highs and lows (the engine's lookback-2 swings), each known from the close of the candle that confirms it;
   - its structure events: a BOS is a close beyond the latest swing in the structure's direction, an MSS a close beyond the latest swing against it;
   - its structural direction: the direction of the latest BOS or MSS, NEUTRAL before the first.
2. Structural direction, price location, delivery direction and the objective SHALL be separate fields of `TimeframeContext` (§5.1).

### Requirement 4: Dealing Ranges and Premium/Discount (§5.2, §5.3)

**User Story:** As the trader, I want several ranges held at once, each with its origin and its invalidation, and price's place in each, so that premium and discount are read against the right range.

#### Acceptance Criteria

1. FOR each timeframe THE analyzer SHALL keep three kinds of range, each with its origin and invalidation:
   - **SWING:** the engine's `dealing_range`, anchored on confirmed swings; invalid once a candle closes outside it;
   - **PREVIOUS:** the previous candle's high and low (PDH/PDL, PWH/PWL, PMH/PML); replaced at the next close;
   - **DISPLACEMENT:** the leg of the latest displacement, from its origin to its extreme; invalid once a candle closes beyond its origin.
2. THE position SHALL be (price − low)/(high − low). THE zone SHALL be one of:
   - DEEP_DISCOUNT: under 0.25;
   - DISCOUNT: under 0.45;
   - EQUILIBRIUM: 0.45-0.55;
   - PREMIUM: over 0.55;
   - DEEP_PREMIUM: over 0.75.

   The bounds are settings.
3. THE primary range for a question SHALL be chosen by rule (§5.2, "contextual range selection"):
   - for the side: the W1 SWING range;
   - for the trade's location: the D1 SWING range, falling back to D1 PREVIOUS when there is none.

   The other ranges stay in the record.
4. Premium and discount are location, never a direction on their own (§5.3). Their evidence weight is §9.4's alone.

### Requirement 5: Liquidity Objectives (§5.4)

**User Story:** As the trader, I want the pools that could draw price ranked by significance, not just by distance, so that the draw is the meaningful one.

#### Acceptance Criteria

1. THE objectives SHALL be:
   - **EXTERNAL:** each SWING range's high and low, and untaken MN1 and W1 swing highs and lows beyond them;
   - **INTERNAL:** untaken swings inside the range, relative equal highs and lows, and unfilled gaps at their near edge;
   - **TEMPORAL:** the previous day's, week's and month's high and low. The sessions' (Asia, London, New York) are added on H1 when it is present.
2. STATUS, in the engine's terms (a pool is swept, a gap is filled):
   - IDENTIFIED once known;
   - APPROACHING within 0.5 ADR;
   - SWEPT once a candle trades beyond a pool, keeping whether that candle closed back inside;
   - MITIGATED once a candle trades into a gap's near edge.

   Objectives are read afresh at each close: one taken more than 3 candles ago, or whose range is replaced, is no longer listed (INVALIDATED is never stored).
3. SIGNIFICANCE SHALL be the timeframe's weight × the type's weight (EXTERNAL 1.0, TEMPORAL 0.8, INTERNAL 0.6), raised by 0.25 for equal highs or lows. It is never set by distance.
4. THE ranking per side SHALL be by significance, then by distance. The primary objective of a side is the first. The output is the ranked list, never a single prediction (§5.4).

### Requirement 6: PD Array Context (§6)

**User Story:** As the trader, I want each PD array judged in its context, so that an FVG alone never sets a bias.

#### Acceptance Criteria

1. THE arrays SHALL be the engine's FVGs, order blocks and breakers on W1, D1 and (when present) H4 and H1, both directions.
2. EACH array SHALL be evaluated for (§6.2):
   - its timeframe;
   - price's location against it (above, inside, below);
   - its parent SWING range;
   - the zone of its near edge;
   - whether a displacement formed it (a body of at least 1.5 times the mean body of the 20 candles before);
   - whether a liquidity sweep came within the 3 candles before it formed;
   - HTF alignment (its direction against the W1 structural direction);
   - mitigation (traded into);
   - invalidation (a close beyond its far edge).
3. An array SHALL count as directional evidence only when it is valid, on its side's zone (a bullish array in discount, a bearish one in premium), and price is in it or has just left it on its side (§6.2).

### Requirement 7: Delivery (§7)

**User Story:** As the trader, I want the delivery state read from the sequence of events, not from one event, so that a single break never flips the read.

#### Acceptance Criteria

1. FOR each timeframe THE delivery state SHALL come from the last sequence of:
   - a sweep of a pool;
   - a displacement away from it;
   - a CISD (the engine's: a close beyond the open of the run that delivered the sweep).

   It reads:
   - **BULLISH_DELIVERY** (BEARISH the mirror): a bullish CISD after a sell-side sweep, with no close since below the CISD run's low;
   - **TRANSITIONAL:** a sweep and a displacement against the prior delivery without a CISD yet;
   - **CONSOLIDATION:** `algo_research.phases` reads the frame in consolidation;
   - **UNCONFIRMED:** none of the above.
2. Other valid sequences (§7.2) are allowed. Each is added as a named rule with a test, never by loosening this one.

### Requirement 8: Time, News and Volatility (§8)

**User Story:** As the trader, I want time and volatility as context, so that a news spike explains volatility without setting the side.

#### Acceptance Criteria

1. Times SHALL be stored in UTC and read in New York time through `zoneinfo`, never a fixed offset (§8).
2. THE temporal context SHALL give, for each D1 close:
   - the day of the week;
   - the week's and month's open, and price against them;
   - whether the week is the month's first or second;
   - the NY midnight open and the killzone, live and on H1.
3. THE volatility context SHALL give the ADR, the last candle's range against it, and expansion or contraction (`algo_research.phases`).
4. Scheduled news (the MT5 calendar, `algo_research.calendar`) SHALL be context only. It carries no direction (§8.1).

### Requirement 9: Evidence and Synthesis (§9.3, §9.4)

**User Story:** As the trader, I want each piece of evidence counted once and weighed openly, so that one move doesn't vote four times.

#### Acceptance Criteria

1. Each analyzer SHALL emit `Evidence` items. Each is BULLISH, BEARISH or NEUTRAL and has its significance (0-1), timeframe and source event.
2. **Correlation control:**
   - items with the same source event (the same candles) SHALL count once per direction, at their greatest significance;
   - an item that depends on another counts only its own increment.
3. THE scores SHALL be S_B = Σ w_c·e_c,B and S_S = Σ w_c·e_c,S. Each e_c is the category's capped sum of significance × timeframe weight, divided by its maximum. The weights are §9.4's starting weights:
   - HTF structure 0.25;
   - liquidity 0.25;
   - premium/discount 0.20;
   - PD arrays 0.15;
   - delivery 0.15.

   Temporal and volatility items are contextual and weigh 0.
4. Weights, timeframe weights and thresholds SHALL be settings, frozen as `v1` before the §16 test. A change is a new version and a new try.
5. THE output SHALL call the result a confidence, never a probability (§9.4).

### Requirement 10: The Narrative (§9.1, §9.2)

**User Story:** As the trader, I want the hypothesis as a structured explanation, so that I can read why the engine thinks what it thinks.

#### Acceptance Criteria

1. A `MarketNarrative` SHALL hold:
   - the structure per timeframe;
   - the primary ranges and price's position in them;
   - the ranked objectives;
   - the arrays in play;
   - the delivery state;
   - the supporting and conflicting evidence;
   - the invalidation conditions.
2. ITS text SHALL be built from the record by fixed templates (§9.2), never generated.

### Requirement 11: Multi-Timeframe Reasoning (§11)

**User Story:** As the trader, I want the higher timeframe to outweigh the lower, so that four bearish lower frames don't overturn a bullish daily.

#### Acceptance Criteria

1. THE timeframe weights SHALL be MN1 1.0, W1 0.8, D1 0.6, H4 0.4, H1 0.3 (settings).
2. Lower-timeframe evidence against the held side SHALL be classified as one of three things:
   - a retracement (inside the D1 range, toward an internal objective);
   - internal delivery;
   - a developing reversal (a D1 MSS or a D1 close beyond the protected level).

   Only a developing reversal can move the state (§11.2). There is no majority vote.

### Requirement 12: The State Machine (§10)

**User Story:** As the trader, I want the bias held with hysteresis until it is delivered, invalidated or expired, so that it isn't re-invented every candle.

#### Acceptance Criteria

1. THE states SHALL be UNDETERMINED, BULLISH, BEARISH, NEUTRAL and TRANSITIONAL. The transitions are §10.2's, evaluated at each D1 close only. 12.3's ends add the edges §10.2's diagram leaves out (§10.4 names the ends, not the state after them): a side or TRANSITIONAL → UNDETERMINED when invalidated or expired, and any state → UNDETERMINED on stale data.
2. **Establish:** from UNDETERMINED or NEUTRAL, a side SHALL be set when its score is at least 0.5 and leads the other by at least 0.2. It records:
   - its evidence;
   - its primary objective (the draw);
   - its protected level: the W1 SWING range's opposite extreme, or the D1 one without it;
   - its validity (20 D1 closes).
3. **Hold:** a side SHALL be kept while none of these happen:
   - **delivered:** price trades at its draw → NEUTRAL, the episode concluded;
   - **invalidated:** a D1 candle closes beyond its protected level (a wick is liquidation) → UNDETERMINED;
   - **expired:** 20 D1 closes without either → UNDETERMINED;
   - **challenged:** the HTF categories alone (structure and external liquidity) favour the other side by at least 0.3, or a D1 MSS against it → TRANSITIONAL.
4. **Resolve TRANSITIONAL** within 3 D1 closes:
   - to the other side if 12.2's rule establishes it;
   - back to the side if the challenge fades;
   - else to NEUTRAL.
5. EVERY transition SHALL record its trigger, the previous and new states, the timeframe, the time and the narrative (§10.3).
6. THE state at t SHALL be the same whichever later bars exist, and the same bars SHALL give the same timeline (§19.4).

### Requirement 13: The Contract and Setup Qualification (§12)

**User Story:** As the trader, I want the setup engine to read one stable, versioned contract, so that AlgoMindDIS can change inside without breaking it.

#### Acceptance Criteria

1. `DirectionalBiasOutput` SHALL carry §12's fields with `contract_version` "1.0.0". The direction is BULLISH, BEARISH, NEUTRAL or UNDETERMINED; the state is ACTIVE, TRANSITIONAL, INVALIDATED or EXPIRED.
2. `qualify(setup, bias)` SHALL return one of (§12.1):
   - **ALIGNED:** the setup's direction is the active side;
   - **COUNTERTREND_JUSTIFIED:** against the side, but toward an internal objective inside the D1 range, from an opposing HTF array in its zone, after a sweep;
   - **INSUFFICIENT_CONTEXT:** no active side, or a countertrend setup without that justification;
   - **INVALIDATED_CONTEXT:** the side ended at or before the setup.

   Each comes with its reason.
3. THE thesis-file adapter SHALL write an ACTIVE side, its draw and its protected level in the existing thesis format. The engine's THESIS mode then executes inside it unchanged.

### Requirement 14: Observations, Persistence and Replay (§13, §15)

**User Story:** As the trader, I want the state rebuilt exactly from the bars, so that a restart or a replay gives the same answer.

#### Acceptance Criteria

1. Observations SHALL be computed from closed candles at each D1 close. A repeated or re-sent bar changes nothing (idempotent by construction).
2. THE state after a restart SHALL be rebuilt by replaying the bars. No mutable state is stored that the bars can't rebuild.
3. EACH week's records SHALL be written to `data/algo_mind/dis_v1/<week>.json` (git-ignored), and every transition appended to `transitions.jsonl`.
4. A frame missing or stale (no close for more than 3 days on a weekday) SHALL set `data_quality` and give UNDETERMINED for that market (§13.3).

### Requirement 15: Historical Evaluation (§16): H-AF

**User Story:** As the trader, I want AlgoMindDIS measured over decades before it trades, against the baselines, so that we know whether it adds anything.

#### Acceptance Criteria

1. THE replay SHALL run AlgoMindDIS `v1` at every D1 close of Yahoo's daily history, 1996-2022, for the nine markets, on MN1, W1 and D1, using only closed candles (§16.1). 2023-2024 stays unread.
2. H-AF SHALL be registered in the search log before it runs, with H-AE's rule:
   - **cell 1:** the primary objective reached before invalidation, against matched random starts (distances in ADR);
   - **cell 2:** the weeks opened under an active side closing on it, against drift.

   A cell passes when its Holm-adjusted 97.5% interval over calendar months is above zero and at least 6 of 9 markets are positive. H-AF passes if either cell does, as H-AE did.
3. THE report SHALL add, without gating:
   - §16.2's state quality (transitions a year, time undetermined, days live, false transitions);
   - §16.3's split by market, regime and decade;
   - §16.4's baselines: no filter (drift), and a simple HTF filter (the W1 candle's trend, LE-D15).
4. ONE run is one try. A failed v1 is reported as failed. A v2 is a new registration.

### Requirement 16: Activation (§18 Phases 5-7)

**User Story:** As the trader, I want AlgoMindDIS to watch before it acts, so that it earns the paper agent.

#### Acceptance Criteria

1. THE modes SHALL be DIS_DISABLED, DIS_SHADOW, DIS_ADVISORY and DIS_ENFORCED, read from the settings; the default is DIS_SHADOW.
2. **DIS_SHADOW:**
   - /context shows AlgoMindDIS v1's record beside reader v0's and the trader's call;
   - the qualification of each paper setup is recorded;
   - nothing changes an order.
3. **DIS_ADVISORY** adds the qualification to the Noculus engine chart and the paper logs.
4. **DIS_ENFORCED** SHALL be allowed only for a version that passed H-AF. It writes the thesis file the paper agent trades, in place of reader v0's.

### Requirement 17: Regression Scenarios (§17.4)

**User Story:** As the trader, I want the seven scenarios of §17.4 kept as tests, so that a change that breaks a reading is caught.

#### Acceptance Criteria

1. Hand-made bars for scenarios A-G (bullish and bearish reversal, bullish and bearish continuation, conflicting timeframes, neutral consolidation, news volatility) SHALL give §17.4's expected outcomes, and stay as permanent tests.
