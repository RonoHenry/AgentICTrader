# Requirements Document

**Spec**: PD Array Engine

## Introduction

The PD Array Engine is a pure-Python analytical package that encodes the complete ICT/TTrades multi-timeframe Price Action methodology into a deterministic, stateless computation pipeline. It consumes `Dict[Timeframe, List[Candle]]` — multi-timeframe OHLCV candle data — and produces a single structured output object, `LiquidityMap`, containing every analytical result the methodology requires.

The engine is called once per candle close from `agent/nodes/observe_node.py`. Its output is stored on `AgentState.liquidity_map` and injected into the LLM reasoning prompt via `LiquidityMap.to_agent_context()`. It replaces `backend/trader/agents/power_of_3.py`, `backend/trader/analysis/patterns.py`, and the stub `backend/trader/agents/pd_array/` directory.

This spec is **parked for post-v1 implementation** (after task 143 ships). It is written to be complete enough for any developer to implement without further clarification.

**BRD traceability**: BR-ML01, BR-ML03, BR-ML04, SO-01, BR-AG01.

---

## Glossary

- **LiquidityMappingEngine**: The top-level orchestrator class. Entry point for all analysis.
- **LiquidityMap**: The primary output object produced by a single `analyze()` call.
- **Candle**: A single OHLCV bar (open, high, low, close, volume, timestamp, timeframe, instrument).
- **Timeframe**: An enumeration of supported candle periods: M1, M3, M5, M15, M30, H1, H4, D1, W1, MN1.
- **BiasDirection**: BULLISH, BEARISH, or NEUTRAL — the directional bias for a given context.
- **HTFBias**: The higher-timeframe directional bias for one timeframe, relative to that timeframe's candle open.
- **BSL**: Buy-Side Liquidity — stop orders resting above swing highs; targeted in bearish sequences.
- **SSL**: Sell-Side Liquidity — stop orders resting below swing lows; targeted in bullish sequences.
- **LiquidityLevel**: An identified external liquidity pool (PWH, PWL, PDH, PDL, PMH, PML, EQH, EQL, session highs/lows).
- **PDArray**: Price Delivery Array — an institutional footprint or imbalance in price (FVG, OB, Breaker, IFVG, BPR, CISD_LEVEL).
- **FVG**: Fair Value Gap — a 3-candle imbalance where price has not yet traded through the gap.
- **IFVG**: Inverse Fair Value Gap — a previously filled FVG that now acts as an opposing array.
- **OB**: Order Block — the last opposing candle before a significant expansion move.
- **Breaker**: A violated Order Block that has flipped polarity and acts as an opposing array.
- **BPR**: Balanced Price Range — overlapping bullish FVG and bearish FVG at the same price level.
- **CISD_LEVEL**: Change in State of Delivery level — the open of the first candle in a violated delivery sequence.
- **CRT**: Candle Range Theory — the 4-phase candle delivery model (C1/C2/C3/C4).
- **C1 (Accumulation)**: Range-building phase with ATR-relative tight candles.
- **C2 (Manipulation)**: Candle closing within C1's range, confirmed by lower-timeframe CISD.
- **C3 (Distribution/Expansion)**: Strong directional candle away from C2.
- **C4 (Continuation)**: Follow-through candle in the C3 direction.
- **CISD**: Change in State of Delivery — a sequence reversal signal confirmed when price closes beyond the first candle's open.
- **CISD Cascade**: Cross-timeframe CISD validation using the defined trigger→confirmation hierarchy.
- **IPDA**: Interbank Price Delivery Algorithm — the institutional framework underlying price delivery.
- **OTE Zone**: Optimal Trade Entry — the 0.62–0.79 Fibonacci retracement of the most recent displacement leg.
- **UNICORN Pattern**: A Breaker Block and FVG overlapping at the same price level.
- **Draw-on-Liquidity**: The primary price target identified from HTF bias and nearest unswept liquidity level.
- **SetupGrade**: The final output grade: A+, A, B, or NO_TRADE.
- **SetupGradeDetail**: The full 8-condition breakdown that produces the SetupGrade.
- **Killzone**: A high-probability trading session window: London (02:00–05:00 EST), NY AM (07:00–10:00 EST), NY PM (13:30–16:00 EST).
- **PWH / PWL**: Previous Week High / Previous Week Low.
- **PDH / PDL**: Previous Day High / Previous Day Low.
- **PMH / PML**: Previous Month High / Previous Month Low.
- **EQH / EQL**: Equal Highs / Equal Lows — two or more swing points within tolerance of each other.
- **displacement_leg**: The most recent impulsive directional move that created a FVG; used as the anchor for OTE calculation.
- **observe_node**: The `agent/nodes/observe_node.py` LangGraph node that calls the engine per candle close.
- **AgentState**: The Pydantic v2 state model passed through every node of the agent loop.
- **tolerance_pct**: The percentage tolerance (default 0.1%, i.e. 0.001) used to classify equal highs/lows.
- **strength_score**: A float in [0.0, 1.0] representing the relative significance of a level or array.

---

## Non-Goals (Deferred)

The following concepts appear in the TTrades reference material (`docs/references/`) but are explicitly **out of scope** for this version of the engine. They are recorded here so they are not silently forgotten and are not re-litigated mid-implementation.

- **SMT (Smart Money Divergence)**: Cross-instrument correlation divergence (e.g., a correlated pair failing to confirm a sweep) used as continuation confluence in "Breaker Continuations." `LiquidityMappingEngine.analyze()` is single-instrument by design (Requirement 1.1 takes one `instrument: str`). Supporting SMT requires either a signature change to accept multiple correlated instruments' candle data, or a separate cross-instrument service that computes divergence and passes it in as an auxiliary input to `SetupGrader`. Revisit as its own follow-on spec once the single-instrument engine (this spec) is validated in production — do not bolt it on ad hoc during this implementation.

---

## Requirements

### Requirement 1: Core Engine Pipeline

**User Story:** As the observe_node, I want to call a single deterministic function with multi-timeframe candle data, so that I receive a complete LiquidityMap containing all analytical outputs required by the trading methodology.

#### Acceptance Criteria

1. WHEN `LiquidityMappingEngine.analyze(candles_by_tf, instrument, timestamp)` is called with valid candle data containing at least D1 and W1 timeframes, THE Engine SHALL return a fully populated `LiquidityMap` object.
2. THE `LiquidityMappingEngine` SHALL be stateless — for any two identical `candles_by_tf` inputs, THE Engine SHALL produce identical `LiquidityMap` outputs.
3. THE `LiquidityMappingEngine` SHALL never mutate the input `candles_by_tf` dictionary or any `Candle` objects within it.
4. WHEN `candles_by_tf` is missing the D1 or W1 timeframe, THE Engine SHALL raise a `ValueError` with a descriptive message before executing any sub-component.
5. THE `LiquidityMappingEngine` SHALL invoke sub-components in the following dependency order: `HTFBiasClassifier` → `LiquidityLevelDetector` → `SwingStructureClassifier` → `PDArrayDetector` → `FractalModelTracker` → `IPDAClassifier` → `OTECalculator` → `UnicornDetector` → `SetupGrader`. `SwingStructureClassifier` SHALL run before `PDArrayDetector` because Breaker `structure_confirmed` (Requirement 4.15) depends on `StructureEvent` output. `FractalModelTracker` SHALL run after `PDArrayDetector` because its `key_level` argument is typically sourced from a detected `LiquidityLevel` or `HTFBias.reference_open`.
6. WHEN `analyze()` completes successfully, THE Engine SHALL return a `LiquidityMap` where `analyzed_at` is a timezone-aware `datetime` matching the `timestamp` argument.
7. THE `LiquidityMappingEngine.analyze()` SHALL complete execution within 500ms for any standard multi-timeframe candle input covering up to 1,000 candles per timeframe.

---

### Requirement 2: HTF Bias Classification

**User Story:** As the methodology engine, I want to classify directional bias for each higher timeframe by comparing current price to that timeframe's candle open, so that the agent can determine whether to hunt longs or shorts on the next lower timeframe.

#### Acceptance Criteria

1. WHEN `current_price` is strictly greater than `reference_open` for a given timeframe, THE `HTFBiasClassifier` SHALL set `HTFBias.direction` to `BiasDirection.BULLISH` for that timeframe.
2. WHEN `current_price` is strictly less than `reference_open` for a given timeframe, THE `HTFBiasClassifier` SHALL set `HTFBias.direction` to `BiasDirection.BEARISH` for that timeframe.
3. WHEN `current_price` is within 0.01% of `reference_open` (i.e., `abs(current_price - reference_open) / reference_open <= 0.0001`), THE `HTFBiasClassifier` SHALL set `HTFBias.direction` to `BiasDirection.NEUTRAL`.
4. FOR THE D1 timeframe, THE `HTFBiasClassifier` SHALL use the NY midnight (00:00 EST) candle open as the primary `reference_open`.
5. FOR THE W1 timeframe, THE `HTFBiasClassifier` SHALL use the Sunday 18:00 EST candle open as the `reference_open`.
6. FOR THE MN1 timeframe, THE `HTFBiasClassifier` SHALL use the first candle open of the calendar month as the `reference_open`.
7. THE `LiquidityMap.htf_bias` dictionary SHALL contain at least one entry for `D1` and at least one entry for `W1` after every successful `analyze()` call.
8. THE `HTFBias.distance_from_open` SHALL equal `current_price - reference_open` (signed float) for every returned `HTFBias` object.
9. THE `HTFBias.distance_pct` SHALL equal `distance_from_open / reference_open` for every returned `HTFBias` object.

---

### Requirement 3: Liquidity Level Detection

**User Story:** As the trading methodology, I want to identify all external liquidity pools where stop orders rest, so that the engine can identify draw-on-liquidity targets and detect sweeps.

#### Acceptance Criteria

1. THE `LiquidityLevelDetector` SHALL detect the Previous Week High (PWH) as a `BSL` level and the Previous Week Low (PWL) as a `SSL` level from the W1 candle series.
2. THE `LiquidityLevelDetector` SHALL detect the Previous Day High (PDH) as a `BSL` level and the Previous Day Low (PDL) as a `SSL` level from the D1 candle series.
3. THE `LiquidityLevelDetector` SHALL detect the Previous Month High (PMH) as a `BSL` level and the Previous Month Low (PML) as a `SSL` level from the MN1 candle series.
4. WHEN two or more swing points in a candle series are within `tolerance_pct` (default 0.1%) of each other on the high side, THE `LiquidityLevelDetector` SHALL classify them as Equal Highs (`EQH`, type `BSL`).
5. WHEN two or more swing points in a candle series are within `tolerance_pct` (default 0.1%) of each other on the low side, THE `LiquidityLevelDetector` SHALL classify them as Equal Lows (`EQL`, type `SSL`).
6. FOR ALL detected `EQH` or `EQL` levels, THE `LiquidityLevelDetector` SHALL ensure the constituent swing points are within `tolerance_pct` of each other (i.e., `abs(level_a - level_b) / level_a <= tolerance_pct`).
7. THE `LiquidityLevelDetector` SHALL detect session highs and lows for the London (02:00–05:00 EST), NY AM (07:00–10:00 EST), and NY PM (13:30–16:00 EST) sessions from intraday candle data.
8. THE `LiquidityLevelDetector` SHALL assign a `strength_score` in the range [0.0, 1.0] to every `LiquidityLevel`, computed from the number of touches, timeframe significance, and recency.
9. FOR ALL returned `LiquidityLevel` objects, THE `LiquidityLevelDetector` SHALL populate `level_id` with a UUID, `formed_at` with a timezone-aware UTC `datetime`, and `touch_count` with a non-negative integer.

---

### Requirement 4: PD Array Detection

**User Story:** As the methodology engine, I want to detect all Price Delivery Arrays (imbalances and institutional footprints) across all timeframes, so that the agent can identify high-probability entry zones and structure for trade execution.

#### Acceptance Criteria

1. WHEN a 3-candle bullish imbalance exists — a gap between `candles[i-2].low` and `candles[i].high` — THE `PDArrayDetector` SHALL detect a `FVG` with `direction = BULLISH`, `low = candles[i-2].low`, and `high = candles[i].high`.
2. WHEN a 3-candle bearish imbalance exists — a gap between `candles[i-2].high` and `candles[i].low` — THE `PDArrayDetector` SHALL detect a `FVG` with `direction = BEARISH`, `high = candles[i-2].high`, and `low = candles[i].low`.
3. FOR ALL detected `FVG` PDArrays, THE `PDArrayDetector` SHALL ensure `PDArray.high > PDArray.low`.
4. THE `PDArrayDetector` SHALL detect a bearish Order Block (`OB`) as the last up-close candle before a significant bearish expansion move.
5. THE `PDArrayDetector` SHALL detect a bullish Order Block (`OB`) as the last down-close candle before a significant bullish expansion move.
6. FOR ALL detected `OB` PDArrays, THE `PDArrayDetector` SHALL ensure `PDArray.high > PDArray.low`.
7. THE `PDArrayDetector` SHALL detect a `BREAKER` block when price trades through an existing `OB` in the opposing direction, flipping its polarity; the `source_ob_id` field SHALL reference the originating OB's `array_id`.
8. THE `PDArrayDetector` SHALL detect an `IFVG` from a previously filled `FVG` (where `is_filled = True`); the `IFVG` SHALL have the opposing direction to the original FVG.
9. THE `PDArrayDetector` SHALL detect a `BPR` when a bullish FVG and a bearish FVG overlap at the same price level; the `bpr_bullish_fvg_id` and `bpr_bearish_fvg_id` fields SHALL be populated with the respective FVG `array_id` values.
10. THE `PDArrayDetector` SHALL detect a `CISD_LEVEL` as the open price of the first candle in the violated delivery sequence; this SHALL be stored in the `cisd_sequence_open` field.
11. FOR ALL detected PDArrays of any type, THE `PDArrayDetector` SHALL assign a `strength_score` in the range [0.0, 1.0].
12. FOR ALL detected PDArrays of any type, THE `PDArrayDetector` SHALL ensure `PDArray.high > PDArray.low`.
13. THE `PDArrayDetector` SHALL detect PD arrays across all provided timeframes and SHALL populate the `timeframe` field on each `PDArray` with the timeframe on which it was detected.
14. WHEN a `FVG` has been fully filled (price has traded through the entire gap), THE `PDArrayDetector` SHALL set `is_filled = True` and `filled_at` to the timestamp of the filling candle.
15. THE `PDArray.structure_confirmed` field SHALL default to `False` for every PDArray of any type. FOR a `BREAKER` specifically, THE `PDArrayDetector` SHALL set `structure_confirmed = True` only WHEN, after the initiating OB violation, price subsequently forms a same-tier `StructureEvent` (BOS or CHoCH, per Requirement 15) on the opposing side of the original OB — i.e. a liquidity sweep beyond the OB's range followed by a structural break back through the swing point that preceded it. Requirement 4.7 (the BREAKER classification itself) is unaffected by this criterion — a `BREAKER` is still tagged the moment price violates the OB; `structure_confirmed` is an additive confirmation flag layered on top, not a gate on classification timing. (Source: `Breaker-Blocks-TTrades-PDF.pdf`, pp. 3–13, which shows Breaker confirmation as a two-step sequence — sweep, then structural break back — rather than a single violation.)

---

### Requirement 5: CRT Phase Classification

**User Story:** As the methodology engine, I want to classify the Candle Range Theory phase (C1/C2/C3/C4) for each timeframe, so that the agent understands the current candle delivery context and can confirm manipulation before expecting expansion.

#### Acceptance Criteria

1. THE `IPDAClassifier` SHALL classify `C1_ACCUMULATION` when a series of candles exhibits an ATR-relative tight range (range significantly below the lookback ATR average).
2. THE `IPDAClassifier` SHALL classify `C2_MANIPULATION` when a candle closes within the C1 accumulation range AND the lower-timeframe CISD is confirmed; the `CRTPhaseResult.c2_within_c1` field SHALL be `True` and `confirmation_tf_cisd` SHALL be `True`.
3. THE `IPDAClassifier` SHALL classify `C3_DISTRIBUTION` when a strong directional candle moves away from the C2 manipulation close in the direction consistent with HTF bias.
4. THE `IPDAClassifier` SHALL classify `C4_CONTINUATION` when follow-through candles extend in the C3 direction.
5. WHEN the candle sequence does not satisfy any of the C1–C4 conditions, THE `IPDAClassifier` SHALL classify `UNKNOWN`.
6. THE `CRTPhaseResult.confidence` SHALL be a float in [0.0, 1.0] for every classification result.
7. THE `CRTPhaseResult` SHALL be populated with `c1_range_high` and `c1_range_low` when C1 or later phases are detected.
8. THE `IPDAClassifier` SHALL produce one `CRTPhaseResult` per timeframe present in `candles_by_tf`, stored in `LiquidityMap.crt_phases` keyed by `Timeframe.value`.

---

### Requirement 6: CISD Detection and Cascade Validation

**User Story:** As the methodology engine, I want to detect Change in State of Delivery signals and validate their cross-timeframe cascade, so that the agent can confirm genuine institutional reversals before committing to a trade direction.

#### Acceptance Criteria

1. THE `CISDDetector` SHALL detect a bearish CISD when a series of up-close candles is followed by a candle that closes below the `open` of the first candle in the series.
2. THE `CISDDetector` SHALL detect a bullish CISD when a series of down-close candles is followed by a candle that closes above the `open` of the first candle in the series.
3. WHEN the 3-candle swing point prerequisite is absent, THE `CISDDetector` SHALL set `CISDResult.has_swing_prerequisite = False` and SHALL NOT confirm the CISD (`confirmed = False`).
4. THE `IPDAClassifier.validate_cisd_cascade()` SHALL set `CISDCascadeStatus.cascade_valid = True` IF AND ONLY IF both `trigger_cisd.confirmed = True` AND `confirmation_cisd.confirmed = True`.
5. THE `IPDAClassifier.validate_cisd_cascade()` SHALL use the following confirmation timeframe mapping: `MN1 → D1`, `W1 → H4`, `D1 → H1`, `H4 → M15`, `M30 → M3`, `M15 → M1`.
6. WHEN a CISD is confirmed, THE `CISDResult` SHALL populate `direction`, `level` (the open of the first candle in the sequence), `sequence_start_time`, and `violation_candle_time`.
7. THE `CISDCascadeStatus.cascade_chain` SHALL contain the ordered list of `CISDResult` objects from the trigger timeframe down to the confirmation timeframe.
8. IF either the trigger or confirmation timeframe data is absent from `candles_by_tf`, THE `IPDAClassifier.validate_cisd_cascade()` SHALL return a `CISDCascadeStatus` with `cascade_valid = False`.

---

### Requirement 7: OTE Zone Calculation

**User Story:** As the methodology engine, I want to compute the Optimal Trade Entry Fibonacci zone from the most recent displacement leg, so that the agent can identify the highest-probability price range for trade entry.

#### Acceptance Criteria

1. THE `OTECalculator` SHALL compute `fib_62` as the 62% Fibonacci retracement of the displacement leg (`swing_high - swing_low`).
2. THE `OTECalculator` SHALL compute `fib_705` as the 70.5% Fibonacci retracement of the displacement leg.
3. THE `OTECalculator` SHALL compute `fib_79` as the 79% Fibonacci retracement of the displacement leg.
4. FOR ALL calculated `OTEZone` objects, THE `OTECalculator` SHALL ensure `fib_62 < fib_705 < fib_79`.
5. FOR ALL calculated `OTEZone` objects, THE `OTECalculator` SHALL ensure `ote_low < ote_high`.
6. THE `OTEZone.golden_level` SHALL equal `fib_705` for every computed zone.
7. FOR bullish setups, THE `OTECalculator` SHALL anchor from `swing_high` to `swing_low` (retracement into discount); `ote_low = fib_79` and `ote_high = fib_62` relative to the swing range.
8. FOR bearish setups, THE `OTECalculator` SHALL anchor from `swing_low` to `swing_high` (retracement into premium); `ote_low = fib_62` and `ote_high = fib_79` relative to the swing range.
9. WHEN `current_price` is within `[ote_low, ote_high]`, THE `OTECalculator` SHALL set `OTEZone.price_in_ote = True`.
10. WHEN `current_price` is outside `[ote_low, ote_high]`, THE `OTECalculator` SHALL set `OTEZone.price_in_ote = False`.
11. THE `OTECalculator.find_displacement_leg()` SHALL identify the most recent impulsive directional move that created a FVG as the displacement leg anchor.

---

### Requirement 8: UNICORN Pattern Detection

**User Story:** As the methodology engine, I want to detect the UNICORN pattern — a Breaker Block and FVG overlapping at the same price level — so that the agent can identify the highest-conviction entry arrays.

#### Acceptance Criteria

1. THE `UnicornDetector` SHALL detect a bullish UNICORN when a bullish `BREAKER` PDArray and a bullish `FVG` PDArray have overlapping price ranges on the same timeframe.
2. THE `UnicornDetector` SHALL detect a bearish UNICORN when a bearish `BREAKER` PDArray and a bearish `FVG` PDArray have overlapping price ranges on the same timeframe.
3. FOR ALL detected `UnicornPattern` objects, THE `UnicornDetector` SHALL ensure `overlap_low < overlap_high`.
4. THE `UnicornPattern.overlap_high` SHALL equal the minimum of the two arrays' high values, and `overlap_low` SHALL equal the maximum of the two arrays' low values.
5. WHEN multiple qualifying Breaker+FVG pairs exist, THE `UnicornDetector` SHALL return the `UnicornPattern` with the most recent `formed_at` timestamp.
6. WHEN no qualifying Breaker+FVG pair exists, THE `UnicornDetector` SHALL return `None`.
7. THE `UnicornPattern.strength_score` SHALL be computed as the combined `strength_score` of the constituent Breaker Block and FVG (e.g., average or sum clamped to [0.0, 1.0]).
8. WHEN evaluating overlap, THE `UnicornDetector` SHALL apply an `overlap_tolerance_pct` (default 0.1%) to account for near-touches.

---

### Requirement 9: Setup Grading

**User Story:** As the agent, I want a deterministic 8-condition setup grade (A+/A/B/NO_TRADE) so that I can make a consistent, explainable decision about whether and how to act on a detected setup.

#### Acceptance Criteria

1. THE `SetupGrader` SHALL assign grade `A+` IF AND ONLY IF all 8 boolean conditions in `SetupGradeDetail` are `True`.
2. THE `SetupGradeDetail.conditions_met` SHALL equal the count of `True` values among the 8 boolean condition fields (`htf_bias_confirmed`, `draw_on_liquidity_identified`, `liquidity_sweep_confirmed`, `displacement_present`, `cisd_confirmed`, `entry_pd_array_present`, `stop_placement_valid`, `time_window_aligned`).
3. THE `SetupGrader` SHALL assign grade `A` WHEN exactly 7 of the 8 conditions are `True`.
4. THE `SetupGrader` SHALL assign grade `B` WHEN `liquidity_sweep_confirmed = True` AND `cisd_confirmed = True` AND `entry_pd_array_present = True` AND the entry array is `FVG` type only (no Breaker or UNICORN present), regardless of other conditions.
5. THE `SetupGrader` SHALL assign grade `NO_TRADE` WHEN fewer than 6 of the 8 conditions are `True`, OR `htf_bias_confirmed = False`, OR `draw_on_liquidity_identified = False`.
6. THE `SetupGrader._check_htf_bias()` SHALL return `True` WHEN at least D1 and W1 bias entries are present in `LiquidityMap.htf_bias` AND neither is `NEUTRAL`.
7. THE `SetupGrader._check_draw_on_liquidity()` SHALL return `True` WHEN `LiquidityMap.draw_on_liquidity` is not `None`.
8. THE `SetupGrader._check_liquidity_sweep()` SHALL return `True` WHEN `LiquidityMap.sweep_detected = True`.
9. THE `SetupGrader._check_time_window()` SHALL return `True` WHEN the `timestamp` falls within a London, NY AM, or NY PM killzone window.
10. THE `SetupGradeDetail.grade_reason` SHALL be a non-empty string providing a human-readable explanation of the assigned grade for every grading output.
11. THE `SetupGradeDetail.suggested_entry` SHALL be set to the `golden_level` of the OTE zone when `entry_array_is_ote = True`, otherwise to the midpoint of the entry PD array.
12. THE `SetupGradeDetail.suggested_stop` SHALL be placed beyond the far boundary of the entry PD array (below `PDArray.low` for bullish entries, above `PDArray.high` for bearish entries).
13. WHEN the `entry_array` has `structure_confirmed = True` (see Requirement 4.15), THE `SetupGrader` SHALL record this in `grade_reason` as corroborating evidence; `structure_confirmed` SHALL NOT alter the 8-condition boolean gate or the `conditions_met` count — it is informational strength context only, not a 9th condition.

---

### Requirement 10: LiquidityMap Structural Integrity

**User Story:** As the agent and LLM prompt engine, I want the LiquidityMap to maintain strict structural invariants so that downstream consumers never encounter invalid or contradictory data.

#### Acceptance Criteria

1. THE `LiquidityMap.analyzed_at` SHALL be a timezone-aware `datetime` object for every returned `LiquidityMap`.
2. THE `LiquidityMap.htf_bias` SHALL contain at least the `D1` and `W1` keys for every returned `LiquidityMap`.
3. WHEN `LiquidityMap.draw_on_liquidity` is not `None`, THE `LiquidityMap` SHALL ensure `draw_on_liquidity.level_id` matches the `level_id` of a member of `LiquidityMap.liquidity_levels`.
4. WHEN `LiquidityMap.ote_zone` is not `None`, THE `LiquidityMap` SHALL ensure `ote_zone.ote_low < ote_zone.ote_high`.
5. WHEN `LiquidityMap.unicorn` is not `None`, THE `LiquidityMap` SHALL ensure `unicorn.overlap_low < unicorn.overlap_high`.
6. THE `LiquidityMap.setup_grade.conditions_met` SHALL equal the sum of the 8 boolean condition fields in `SetupGradeDetail` for every returned `LiquidityMap`.
7. THE `LiquidityMap.to_agent_context()` SHALL return a non-empty string for any valid `LiquidityMap` input.
8. THE `LiquidityMap.to_agent_context()` output SHALL include the HTF bias direction for every timeframe entry in `htf_bias`.
9. THE `LiquidityMap.to_agent_context()` output SHALL include the setup grade value and `conditions_met` count.
10. THE `LiquidityMap.to_agent_context()` output SHALL include the draw-on-liquidity target price and source when `draw_on_liquidity` is not `None`.
11. THE `LiquidityMap.get_arrays_in_range(price_low, price_high)` SHALL return only PDArrays where `is_filled = False` AND `PDArray.low <= price_high` AND `PDArray.high >= price_low`.

---

### Requirement 11: Candle Data Integrity

**User Story:** As the data pipeline, I want the Candle model to enforce OHLC integrity at construction time so that all downstream analytical components receive structurally valid candle data.

#### Acceptance Criteria

1. THE `Candle` model SHALL raise a `ValueError` at construction time WHEN `high < low`.
2. THE `Candle` model SHALL raise a `ValueError` at construction time WHEN `high < open`.
3. THE `Candle` model SHALL raise a `ValueError` at construction time WHEN `high < close`.
4. THE `Candle.is_bullish` property SHALL return `True` IF AND ONLY IF `close > open`.
5. THE `Candle.is_bearish` property SHALL return `True` IF AND ONLY IF `close < open`.
6. THE `Candle.body_size` property SHALL return `abs(close - open)`.
7. THE `Candle.total_range` property SHALL return `high - low`.
8. THE `Candle.upper_wick` property SHALL return `high - max(open, close)`.
9. THE `Candle.lower_wick` property SHALL return `min(open, close) - low`.
10. THE `Candle.timestamp` SHALL be a timezone-aware UTC `datetime`.

---

### Requirement 12: Integration with AgentState and observe_node

**User Story:** As the agent loop, I want the PD Array Engine to integrate cleanly with `observe_node.py` and `AgentState`, so that every candle close triggers a complete analysis that is immediately available for the analyse and decide nodes.

#### Acceptance Criteria

1. WHEN `observe_node` calls `LiquidityMappingEngine.analyze()`, THE Engine SHALL complete and return a `LiquidityMap` within 500ms.
2. WHEN `LiquidityMappingEngine.analyze()` returns successfully, THE `observe_node` SHALL store the result on `AgentState.liquidity_map`.
3. THE `LiquidityMappingEngine` SHALL accept a `Dict[Timeframe, List[Candle]]` as its primary input without requiring any external I/O, database connections, or network calls.
4. THE `pd_array_engine` package SHALL export `LiquidityMappingEngine` and `LiquidityMap` from its `__init__.py`.
5. THE `LiquidityMappingEngine` SHALL replace the analytical responsibilities of `backend/trader/agents/power_of_3.py`, `backend/trader/analysis/patterns.py`, and the stub `backend/trader/agents/pd_array/` directory without breaking any existing passing tests in the test suite.

---

### Requirement 13: Draw-on-Liquidity and Sweep Detection

**User Story:** As the methodology engine, I want to identify the primary price target and detect when that target has been swept, so that the agent can determine whether the market is still seeking its objective or has completed the delivery.

#### Acceptance Criteria

1. THE `LiquidityMappingEngine._find_draw_on_liquidity()` SHALL select the nearest unswept `LiquidityLevel` in the direction consistent with the dominant HTF bias as the `draw_on_liquidity` target.
2. WHEN `htf_bias` indicates `BULLISH` on D1 and W1, THE Engine SHALL prefer `BSL` (Buy-Side Liquidity) levels as the `draw_on_liquidity` target.
3. WHEN `htf_bias` indicates `BEARISH` on D1 and W1, THE Engine SHALL prefer `SSL` (Sell-Side Liquidity) levels as the `draw_on_liquidity` target.
4. THE `LiquidityMappingEngine._detect_sweep()` SHALL set `LiquidityMap.sweep_detected = True` WHEN price has traded through the `draw_on_liquidity` level's price in the current analysis window.
5. WHEN a sweep is detected, THE `LiquidityLevel.swept` field on the swept level SHALL be set to `True` and `swept_at` SHALL be populated with the timestamp of the sweeping candle.
6. WHEN no unswept `LiquidityLevel` exists in the bias direction, THE Engine SHALL set `draw_on_liquidity = None`.

---

### Requirement 14: Non-Functional Requirements

**User Story:** As the platform engineering team, I want the PD Array Engine to meet strict non-functional standards so that it integrates reliably into the production agent loop and remains maintainable.

#### Acceptance Criteria

1. THE `pd_array_engine` package SHALL be pure Python with no I/O side effects — no file reads, database calls, network calls, or global state mutations during `analyze()`.
2. THE `pd_array_engine` package SHALL use only dependencies already present in `requirements.txt` (Pydantic v2, standard library).
3. THE `pd_array_engine` package layout SHALL match the directory structure defined in the design document exactly: `pd_array_engine/__init__.py`, `models.py`, `engine.py`, `detectors/`, `ipda/`, `ote/`, `unicorn/`, `grader/`, `utils/`.
4. ALL Pydantic models in `pd_array_engine/models.py` SHALL use Pydantic v2 syntax (`model_config`, `field_validator` with `@classmethod`).
5. ALL price values in all models SHALL be `float`. ALL timestamps SHALL be timezone-aware `datetime` objects stored in UTC.
6. THE `LiquidityMappingEngine` SHALL be fully covered by property-based tests using the `hypothesis` library with a minimum of 100 examples per property.
7. THE `pd_array_engine` package SHALL achieve a minimum of 90% line coverage as measured by `pytest-cov`.
8. THE `LiquidityMap.to_agent_context()` output format SHALL follow the structured template defined in the design document, answering: (1) where price has come from, (2) where it is now, and (3) where it is likely to go.

---

### Requirement 15: Swing Structure Hierarchy and BOS/CHoCH Detection

**User Story:** As the methodology engine, I want to classify swing points into a nested Short-Term / Intermediate-Term / Long-Term hierarchy and detect Break of Structure (BOS) and Change of Character (CHoCH) events, so that the agent has a tiered, faithful reading of market structure rather than a flat list of local extrema.

**Source**: `Basic-Market-Structure-TTrades-PDF.pdf` (bullish/bearish trend HH/HL/LH/LL sequencing) and `Advanced-Market-Structure-TTrades-PDF.pdf` (STH/STL → ITH/ITL → LTH/LTL nesting).

#### Acceptance Criteria

1. THE `SwingStructureClassifier` SHALL classify every local extremum produced by `find_swing_highs`/`find_swing_lows` as a Short-Term High (`STH`) or Short-Term Low (`STL`) — `SwingTier.SHORT_TERM`.
2. WHEN price closes beyond the `STL` immediately preceding an `STH` (or beyond the `STH` immediately preceding an `STL`), THE `SwingStructureClassifier` SHALL promote that `STH`/`STL` to Intermediate-Term (`ITH`/`ITL`) — `SwingTier.INTERMEDIATE_TERM`.
3. WHEN price closes beyond the `ITL` immediately preceding an `ITH` (or beyond the `ITH` immediately preceding an `ITL`), THE `SwingStructureClassifier` SHALL promote that `ITH`/`ITL` to Long-Term (`LTH`/`LTL`) — `SwingTier.LONG_TERM`.
4. EVERY `SwingPoint` promoted to `INTERMEDIATE_TERM` or `LONG_TERM` SHALL retain a reference to the lower-tier `SwingPoint` it was derived from (`derived_from_swing_id`).
5. THE `SwingStructureClassifier` SHALL emit a `StructureEvent` of type `BOS` WHEN price closes beyond the most recent same-tier swing point in the direction consistent with the prevailing trend at that tier (continuation).
6. THE `SwingStructureClassifier` SHALL emit a `StructureEvent` of type `CHOCH` WHEN price closes beyond the most recent same-tier swing point in the direction opposite the prevailing trend at that tier (first sign of reversal).
7. FOR ANY given swing point break, THE `SwingStructureClassifier` SHALL classify the resulting `StructureEvent` as exactly one of `BOS` or `CHOCH`, never both, and never neither.
8. THE `SwingStructureClassifier.classify(candles, tf) -> SwingStructureResult` SHALL be pure and stateless — identical candle input SHALL always produce an identical `SwingStructureResult`.
9. THE `LiquidityMap.swing_structure` dictionary SHALL contain one `SwingStructureResult` per timeframe present in `candles_by_tf`, keyed by `Timeframe.value`.

---

### Requirement 16: Candle Type Classification (Wick-Based)

**User Story:** As the methodology engine, I want to classify each candle as an Expansion, Reversal, or Reversal-Expansion candle based on its wick-to-range ratio, so that the agent can read individual candles for manipulation/rejection signals independently of multi-candle pattern detection.

**Source**: `Candle-2-TTrades-PDF.pdf` ("Wick Size", "Reversal Candle", "Reversal Expansion Candle", "Two Types").

#### Acceptance Criteria

1. THE `classify_candle_type(candle)` utility SHALL compute `wick_ratio = max(candle.upper_wick, candle.lower_wick) / candle.total_range` for any candle where `total_range > 0`.
2. WHEN `wick_ratio <= 0.25`, THE utility SHALL classify the candle as `CandleType.EXPANSION` (small opposing wick; strong directional close near an extreme).
3. WHEN `wick_ratio >= 0.5`, THE utility SHALL classify the candle as `CandleType.REVERSAL` (large opposing wick; rejection before close).
4. WHEN `0.25 < wick_ratio < 0.5`, THE utility SHALL classify the candle as `CandleType.REVERSAL_EXPANSION` (a directional body with a moderate rejection wick).
5. WHEN `candle.total_range == 0`, THE utility SHALL classify the candle as `CandleType.EXPANSION` (a doji/zero-range candle carries no rejection wick to speak of).
6. THE `classify_candle_type()` thresholds (0.25 / 0.5) ARE first-pass defaults calibrated qualitatively against the TTrades reference material, not derived from a backtest; THE implementation SHALL expose them as named constants (not magic numbers) so they can be recalibrated without touching call sites.
7. `classify_candle_type()` SHALL NOT be added as a `Candle` property or field — `Candle` remains a pure OHLC geometry model; candle typing is a derived, interpretive classification and SHALL live in `utils/candle_utils.py` as a stateless function.

---

### Requirement 17: Fractal Model Candle Sequence and Equilibrium

**User Story:** As the methodology engine, I want to track the candle-by-candle continuation/reversal closure sequence relative to an HTF Key Level and compute the Equilibrium of the developing range, so that the agent has the granular, single-candle-resolution view of delivery that CISD and OTE operate above.

**Source**: `Candle-2-TTrades-PDF.pdf`, `Candle-2-Closure-TTrades-PDF.pdf`, `Candle-3-Closure-TTrades.pdf` (the "Fractal Model — Candle Closures" series: Candle 1/2/3/4 relative to an HTF Key Level, Continuation vs. Reversal Closure, and the 0.5 Equilibrium of the developing range).

#### Acceptance Criteria

1. THE `FractalModelTracker.track(candles, key_level) -> FractalModelResult` SHALL treat the first candle in `candles` as Step 1 (the reference candle) with `closure_type = None` (there is no prior candle to compare against).
2. FOR every subsequent candle (Step N, N >= 2), THE `FractalModelTracker` SHALL classify `closure_type = ClosureType.CONTINUATION` WHEN Step N's close extends beyond Step N-1's extreme in the direction of the developing sequence, and `closure_type = ClosureType.REVERSAL` WHEN Step N's close falls back within Step N-1's range on the opposing side of Step N-1's open.
3. THE `FractalModelResult.range_high` and `range_low` SHALL be updated to encompass the high/low of every step processed so far — these values SHALL only expand (never contract) as new steps are added.
4. THE `FractalModelResult.equilibrium` SHALL always equal `(range_high + range_low) / 2`.
5. THE `FractalModelResult.price_above_equilibrium` SHALL be `True` WHEN the latest step's close is greater than `equilibrium`, and `False` otherwise.
6. THE `FractalModelResult.key_level` SHALL be immutable for the lifetime of a single `track()` call and SHALL be the value passed in by the caller (an HTF Key Level — typically an `HTFBias.reference_open` or a `LiquidityLevel.price`).
7. `LiquidityMap.fractal_model` SHALL be `Optional[FractalModelResult]`, set to `None` when insufficient candle data is available to seed a sequence.
8. `FractalModelTracker` SHALL be pure and stateless per Requirement 14.1 (no I/O, no shared mutable state between calls).

---

## Correctness Properties

*A property is a characteristic or behaviour that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Engine Determinism (Statelessness)

*For any* valid `candles_by_tf` dictionary and instrument/timestamp combination, calling `LiquidityMappingEngine.analyze()` twice with identical inputs SHALL produce two `LiquidityMap` objects that are equal in all fields.

**Validates: Requirements 1.2, 14.1**

---

### Property 2: Input Immutability

*For any* valid `candles_by_tf` input, after calling `LiquidityMappingEngine.analyze()`, every `Candle` object in the input dictionary SHALL have the same field values as before the call.

**Validates: Requirements 1.3**

---

### Property 3: HTF Bias Direction Correctness

*For any* timeframe and any `(current_price, reference_open)` pair where `current_price != reference_open` and the difference exceeds the 0.01% tolerance, `HTFBiasClassifier.classify()` SHALL return `BULLISH` when `current_price > reference_open` and `BEARISH` when `current_price < reference_open`.

**Validates: Requirements 2.1, 2.2**

---

### Property 4: HTF Bias Neutral Band

*For any* `current_price` within 0.01% of `reference_open`, `HTFBiasClassifier.classify()` SHALL return `NEUTRAL`.

**Validates: Requirement 2.3**

---

### Property 5: D1 and W1 Bias Always Present

*For any* valid multi-timeframe candle input that includes D1 and W1 candle series, `LiquidityMap.htf_bias` SHALL contain entries for both `"D1"` and `"W1"`.

**Validates: Requirements 2.6, 10.2**

---

### Property 6: FVG High Greater Than Low

*For any* candle sequence, all `PDArray` objects with `array_type = FVG` returned by `PDArrayDetector.detect()` SHALL satisfy `PDArray.high > PDArray.low`.

**Validates: Requirements 4.3, 4.12**

---

### Property 7: OB High Greater Than Low

*For any* candle sequence, all `PDArray` objects with `array_type = OB` returned by `PDArrayDetector.detect()` SHALL satisfy `PDArray.high > PDArray.low`.

**Validates: Requirements 4.6, 4.12**

---

### Property 8: All PDArray High Greater Than Low

*For any* candle sequence, every `PDArray` of any type returned by `PDArrayDetector.detect()` SHALL satisfy `PDArray.high > PDArray.low`.

**Validates: Requirements 4.3, 4.6, 4.12**

---

### Property 9: OTE Zone Structural Ordering

*For any* displacement leg with a non-zero range, the `OTEZone` returned by `OTECalculator.calculate()` SHALL satisfy `fib_62 < fib_705 < fib_79`.

**Validates: Requirement 7.4**

---

### Property 10: OTE Zone Low Less Than High

*For any* displacement leg with a non-zero range, the `OTEZone` returned by `OTECalculator.calculate()` SHALL satisfy `ote_low < ote_high`.

**Validates: Requirements 7.5, 10.4**

---

### Property 11: OTE Golden Level Equals fib_705

*For any* computed `OTEZone`, `golden_level` SHALL equal `fib_705`.

**Validates: Requirement 7.6**

---

### Property 12: OTE Price-In-Zone Flag Correctness

*For any* `OTEZone` and any `current_price`, `price_in_ote` SHALL be `True` if and only if `ote_low <= current_price <= ote_high`.

**Validates: Requirements 7.9, 7.10**

---

### Property 13: UNICORN Overlap Well-Formed

*For any* detected `UnicornPattern`, `overlap_low < overlap_high` SHALL always hold.

**Validates: Requirements 8.3, 10.5**

---

### Property 14: UNICORN Returns Most Recent

*For any* list of qualifying Breaker+FVG pairs with distinct `formed_at` timestamps, `UnicornDetector.detect()` SHALL return the pair with the maximum `formed_at` value.

**Validates: Requirement 8.5**

---

### Property 15: Setup Grade conditions_met Accuracy

*For any* `SetupGradeDetail` object, `conditions_met` SHALL equal the sum of the 8 boolean condition fields: `htf_bias_confirmed + draw_on_liquidity_identified + liquidity_sweep_confirmed + displacement_present + cisd_confirmed + entry_pd_array_present + stop_placement_valid + time_window_aligned`.

**Validates: Requirements 9.2, 10.6**

---

### Property 16: A+ Grade Requires All 8 Conditions

*For any* `LiquidityMap`, the `SetupGrader` SHALL assign grade `A+` if and only if all 8 boolean conditions in `SetupGradeDetail` are `True` (i.e., `conditions_met == 8`). No `LiquidityMap` with `conditions_met < 8` SHALL receive grade `A+`.

**Validates: Requirement 9.1**

---

### Property 17: NO_TRADE Grade When Conditions Below Threshold

*For any* `LiquidityMap` where `conditions_met < 6`, OR where `htf_bias_confirmed = False`, OR where `draw_on_liquidity_identified = False`, THE `SetupGrader` SHALL assign grade `NO_TRADE`.

**Validates: Requirement 9.5**

---

### Property 18: draw_on_liquidity Reference Integrity

*For any* `LiquidityMap` where `draw_on_liquidity` is not `None`, `draw_on_liquidity.level_id` SHALL appear as the `level_id` of at least one member of `LiquidityMap.liquidity_levels`.

**Validates: Requirement 10.3**

---

### Property 19: CISD Cascade Validity Requires Both CISDs

*For any* call to `IPDAClassifier.validate_cisd_cascade()`, `CISDCascadeStatus.cascade_valid` SHALL be `True` if and only if both `trigger_cisd.confirmed = True` AND `confirmation_cisd.confirmed = True`. A cascade SHALL NOT be valid if either is unconfirmed.

**Validates: Requirement 6.4**

---

### Property 20: Equal Highs/Lows Satisfy Tolerance Invariant

*For any* set of candles and any `tolerance_pct`, every `LiquidityLevel` with source `EQH` or `EQL` returned by `LiquidityLevelDetector.detect()` SHALL have constituent swing points satisfying `abs(level_a - level_b) / level_a <= tolerance_pct`.

**Validates: Requirement 3.6**

---

### Property 21: Strength Scores in Valid Range

*For any* candle input, every `LiquidityLevel` and every `PDArray` returned by their respective detectors SHALL have `strength_score` in [0.0, 1.0].

**Validates: Requirements 3.8, 4.11**

---

### Property 22: Candle OHLC Invariant

*For any* valid `Candle` construction attempt, attempting to create a `Candle` with `high < low`, `high < open`, or `high < close` SHALL always raise a `ValueError`.

**Validates: Requirements 11.1, 11.2, 11.3**

---

### Property 23: to_agent_context Non-Empty and Complete

*For any* valid `LiquidityMap`, `to_agent_context()` SHALL return a non-empty string that contains: (a) every timeframe key and bias direction from `htf_bias`, (b) the `grade` value and `conditions_met` count from `setup_grade`.

**Validates: Requirements 10.7, 10.8, 10.9**

---

### Property 24: Swing Tier Promotion Requires a Broken Lower Tier

*For any* `SwingPoint` with `tier = INTERMEDIATE_TERM` or `tier = LONG_TERM`, `derived_from_swing_id` SHALL reference a `SwingPoint` one tier below (`SHORT_TERM` → `INTERMEDIATE_TERM`, `INTERMEDIATE_TERM` → `LONG_TERM`) that has `broken = True`. No swing point SHALL be promoted without a broken lower-tier swing point beneath it.

**Validates: Requirement 15.2, 15.3, 15.4**

---

### Property 25: BOS/CHoCH Mutual Exclusivity

*For any* `StructureEvent` emitted by `SwingStructureClassifier`, `event_type` SHALL be exactly one of `BOS` or `CHOCH` — never both, never neither — and `CHOCH` events SHALL always have a `direction` opposite the prevailing trend direction at the time of formation.

**Validates: Requirement 15.5, 15.6, 15.7**

---

### Property 26: Candle Type Classification Is Total and Exclusive

*For any* valid `Candle`, `classify_candle_type(candle)` SHALL return exactly one of `CandleType.EXPANSION`, `CandleType.REVERSAL`, or `CandleType.REVERSAL_EXPANSION` — the function SHALL never raise and SHALL never return `None` for a structurally valid candle.

**Validates: Requirement 16.1–16.5**

---

### Property 27: Fractal Model Range and Equilibrium Correctness

*For any* sequence of candles passed incrementally to `FractalModelTracker.track()`, `range_high` SHALL be monotonically non-decreasing and `range_low` SHALL be monotonically non-increasing as steps accumulate, and `equilibrium` SHALL equal `(range_high + range_low) / 2` after every step.

**Validates: Requirement 17.3, 17.4**

---

### Property 28: Structure-Confirmed Breaker Requires a Corresponding Structure Event

*For any* `PDArray` with `array_type = BREAKER` and `structure_confirmed = True`, THERE SHALL exist a `StructureEvent` (of type `BOS` or `CHOCH`) on the opposing side of the originating OB, formed at or after the OB's violation timestamp.

**Validates: Requirement 4.15**

---
