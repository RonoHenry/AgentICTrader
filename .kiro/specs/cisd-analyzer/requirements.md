# Requirements Document — CISD Analyzer

## Introduction

The CISD Analyzer implements the TTrades reversal sequence methodology as a timeframe-agnostic
detector of Change in State of Delivery signals. It lives at
`backend/trader/agents/cisd.py` and fills the currently empty placeholder module.

The detector recognises a three-step confirmation sequence — Turtle Soup sweep → imbalance
(FVG or IFVG) → CISD validating Order Block — and returns a structured `CISDResult` that
encodes how far through the sequence price has progressed. Because price is fractal, the same
sequence appears on every timeframe; the analyzer is deliberately timeframe-agnostic. Callers
pass whatever candle list they hold and the detector does not need to know or care which
timeframe those candles belong to.

**Two calling contexts share a single implementation:**

1. **HTF direction validation** — `ZoneFeatureExtractor` calls `CISDAnalyzer.scan()` with H1,
   H4, or D1 candles to confirm a program flip and update `htf_trend_bias`. This replaces the
   current simplistic `_detect_choch()` implementation.

2. **LTF entry gate** — `decide_node` calls `CISDAnalyzer.scan()` with M1/M5/M15 candles as
   an additional confluence gate before committing to a trade.

The `sequence_step` output (0–3) is also consumed by the confluence scorer as a graded feature,
so partial sequences contribute signal rather than binary pass/fail.

**Alignment:** This spec implements Requirement 6 of `.kiro/specs/liquidity-engine/requirements.md`
at the component level. BRD traceability: BR-ML03, BR-AG01.

---

## Glossary

- **CISDAnalyzer**: The detector class. Stateless `scan()` method; caller owns any persistent state.
- **CISDResult**: The output dataclass returned by every `scan()` call.
- **FVGZone**: A dataclass representing a detected Fair Value Gap stored in the rolling history buffer.
- **Turtle Soup**: A false breakout where a candle wick pierces a prior swing high or swing low but the candle body closes back inside the range. Signals a stop hunt and the start of a potential reversal.
- **Sweep**: The Turtle Soup event that starts the sequence. BULLISH sweep = sweep of a swing LOW (price seeks long-side liquidity before reversing up). BEARISH sweep = sweep of a swing HIGH.
- **Swing High**: A candle whose high is strictly greater than the highs of both its immediate left and right neighbours (1-candle fractal).
- **Swing Low**: A candle whose low is strictly less than the lows of both its immediate left and right neighbours (1-candle fractal).
- **FVG**: Fair Value Gap — a 3-candle imbalance where `candles[i-2].high < candles[i].low` (bullish) or `candles[i-2].low > candles[i].high` (bearish). Price has not yet traded through the gap.
- **IFVG**: Inverse Fair Value Gap — a previously formed FVG that has been traded into (partially or fully filled) and now acts as an opposing array. Requires a rolling `fvg_history` buffer to detect.
- **Imbalance**: Either an FVG or IFVG forming in the displacement move away from the sweep. Both are valid; they are tracked separately.
- **Displacement Move**: The impulsive directional candle or candle sequence that moves away from the sweep level and creates the FVG or IFVG.
- **Order Block (OB)**: The last opposing candle before the displacement move. For a bullish displacement, the OB is the last bearish (down-close) candle before the move. For a bearish displacement, the OB is the last bullish (up-close) candle.
- **CISD Validating OB**: The confirmation event — a candle that closes back into the OB body. This is the program flip signal.
- **sequence_step**: An integer 0–3 encoding how far through the three-step sequence price has progressed: 0 = nothing, 1 = sweep only, 2 = sweep + imbalance, 3 = full CISD confirmed.
- **candles_elapsed**: The number of candles since the sweep candle was detected. Used to expire stale partial sequences.
- **max_sequence_candles**: Constructor parameter controlling how many candles a partial sequence may persist before it is discarded and the detector resets to step 0.
- **Program Flip**: A confirmed change from a buy program to a sell program (or vice versa), evidenced by the full three-step CISD sequence.

---

## Requirements

### Requirement 1: CISDResult Output Dataclass

**User Story:** As a calling module (ZoneFeatureExtractor or decide_node), I want a structured
dataclass returned from every `scan()` call, so that I can route on `confirmed`, consume
`sequence_step` as a graded feature, and access individual field values without parsing strings.

#### Acceptance Criteria

1. THE `CISDResult` SHALL be a Python `@dataclass` with the following fields and types:
   `confirmed: bool`, `direction: str`, `sequence_step: int`, `sweep_level: Optional[float]`,
   `sweep_direction: Optional[str]`, `imbalance_type: Optional[str]`,
   `imbalance_high: Optional[float]`, `imbalance_low: Optional[float]`,
   `ob_high: Optional[float]`, `ob_low: Optional[float]`, `candles_elapsed: int`.
2. THE `CISDResult.direction` field SHALL only ever contain the string values `"BULLISH"`,
   `"BEARISH"`, or `"NONE"`.
3. THE `CISDResult.sequence_step` field SHALL only ever contain integer values in the set
   `{0, 1, 2, 3}`.
4. THE `CISDResult.sweep_direction` field SHALL only ever contain `"BULLISH"`, `"BEARISH"`,
   or `None`.
5. THE `CISDResult.imbalance_type` field SHALL only ever contain `"FVG"`, `"IFVG"`, or `None`.
6. THE `CISDResult.candles_elapsed` field SHALL be a non-negative integer for every returned
   `CISDResult`.

---

### Requirement 2: FVGZone Buffer Dataclass

**User Story:** As the CISDAnalyzer, I want a typed container for FVG zones stored in the
rolling history buffer, so that IFVG detection can query prior imbalances without relying on
untyped dicts.

#### Acceptance Criteria

1. THE `FVGZone` SHALL be a Python `@dataclass` with at minimum the following fields:
   `high: float`, `low: float`, `direction: str`, `is_filled: bool`,
   `candle_index: int`.
2. THE `FVGZone.direction` field SHALL only ever contain `"BULLISH"` or `"BEARISH"`.
3. FOR ALL `FVGZone` instances, `FVGZone.high` SHALL be strictly greater than `FVGZone.low`.

---

### Requirement 3: CISDAnalyzer Class Interface

**User Story:** As a Python module importing this analyzer, I want a clean, type-annotated
class interface with a stateless `scan()` method and a helper for FVG history management, so
that I can call it identically from both `ZoneFeatureExtractor` and `decide_node` regardless
of timeframe.

#### Acceptance Criteria

1. THE `CISDAnalyzer` class SHALL be importable from `backend.trader.agents.cisd`.
2. THE `CISDAnalyzer.__init__` SHALL accept a single keyword argument
   `max_sequence_candles: int = 20` and store it as an instance attribute.
3. THE `CISDAnalyzer.scan` SHALL accept `candles: List[Dict[str, Any]]` as its first positional
   argument and `fvg_history: Optional[List] = None` as a keyword argument.
4. THE `CISDAnalyzer.scan` SHALL return a `CISDResult` for every valid invocation.
5. THE `CISDAnalyzer.update_fvg_history` SHALL accept `candles: List[Dict[str, Any]]` and
   return a `List` of `FVGZone` objects representing the updated history for the caller to persist.
6. THE `CISDAnalyzer.scan` SHALL treat `candles` as read-only — it SHALL NOT mutate any
   candle dictionary in the input list.
7. WHEN `candles` is an empty list, THE `CISDAnalyzer.scan` SHALL return a `CISDResult` with
   `confirmed=False`, `direction="NONE"`, `sequence_step=0`, and `candles_elapsed=0`.
8. WHEN `candles` contains fewer than 3 elements, THE `CISDAnalyzer.scan` SHALL return a
   `CISDResult` with `confirmed=False`, `direction="NONE"`, and `sequence_step=0`.

---

### Requirement 4: Step 1 — Turtle Soup Sweep Detection

**User Story:** As the sequence detector, I want to identify the Turtle Soup false breakout
that starts the reversal sequence, so that the downstream steps have an anchored sweep level
and direction to work with.

#### Acceptance Criteria

1. WHEN a candle's wick pierces a prior Swing Low AND that candle's close is strictly above
   the Swing Low level, THE `CISDAnalyzer` SHALL record a BULLISH sweep event with
   `sweep_direction = "BULLISH"` and `sweep_level` equal to the Swing Low price.
2. WHEN a candle's wick pierces a prior Swing High AND that candle's close is strictly below
   the Swing High level, THE `CISDAnalyzer` SHALL record a BEARISH sweep event with
   `sweep_direction = "BEARISH"` and `sweep_level` equal to the Swing High price.
3. WHEN a sweep is detected, THE `CISDAnalyzer` SHALL record the index of the sweep candle
   as `sweep_candle_index` for use in imbalance and OB detection.
4. THE sweep candle `low` SHALL be strictly less than `sweep_level` for a BULLISH sweep, and
   the sweep candle `high` SHALL be strictly greater than `sweep_level` for a BEARISH sweep.
5. WHEN no prior Swing High or Swing Low is found in the provided candle window, THE
   `CISDAnalyzer` SHALL return a `CISDResult` with `sequence_step=0` and `confirmed=False`.
6. WHEN multiple swing points exist, THE `CISDAnalyzer` SHALL use the most recent Swing High
   or Swing Low as the sweep reference level.

---

### Requirement 5: Swing Point Detection

**User Story:** As the sweep detector, I want a consistent 1-candle fractal definition of
swing highs and lows so that sweep detection is deterministic and reproducible.

#### Acceptance Criteria

1. THE `CISDAnalyzer` SHALL define a Swing High as a candle at index `i` where
   `candles[i].high > candles[i-1].high` AND `candles[i].high > candles[i+1].high`.
2. THE `CISDAnalyzer` SHALL define a Swing Low as a candle at index `i` where
   `candles[i].low < candles[i-1].low` AND `candles[i].low < candles[i+1].low`.
3. WHEN searching for the most recent swing point, THE `CISDAnalyzer` SHALL search backwards
   from the current candle index and return the first matching fractal encountered.
4. THE `CISDAnalyzer` SHALL require at least 3 candles in the window before any swing point
   can be identified; WHEN fewer than 3 candles are present, THE `CISDAnalyzer` SHALL treat
   no swing point as found.

---

### Requirement 6: Step 2 — Imbalance Detection (FVG Path)

**User Story:** As the sequence detector at step 2, I want to detect a Fair Value Gap forming
in the displacement move away from the sweep, so that I have structural confirmation that
institutional order flow is present.

#### Acceptance Criteria

1. WHEN `candles[i-2].high < candles[i].low` (a gap exists between the third-prior candle's
   high and the current candle's low), THE `CISDAnalyzer` SHALL detect a bullish FVG with
   `imbalance_type = "FVG"`, `imbalance_low = candles[i-2].high`, and
   `imbalance_high = candles[i].low`.
2. WHEN `candles[i-2].low > candles[i].high` (a gap exists between the third-prior candle's
   low and the current candle's high), THE `CISDAnalyzer` SHALL detect a bearish FVG with
   `imbalance_type = "FVG"`, `imbalance_high = candles[i-2].low`, and
   `imbalance_low = candles[i].high`.
3. THE detected FVG SHALL form in the displacement move away from the sweep — specifically,
   the FVG SHALL appear at a candle index strictly after `sweep_candle_index`.
4. FOR ALL detected FVG imbalances, `imbalance_high` SHALL be strictly greater than
   `imbalance_low`.
5. WHEN a bullish FVG is detected, the FVG direction SHALL align with the sweep direction
   (BULLISH sweep → BULLISH FVG); misaligned FVGs SHALL be ignored.

---

### Requirement 7: Step 2 — Imbalance Detection (IFVG Path)

**User Story:** As the sequence detector at step 2, I want to detect an Inverse Fair Value
Gap from the rolling FVG history as an alternative path to step 2, so that setups where
price trades into a previously formed imbalance are correctly identified.

#### Acceptance Criteria

1. WHEN `fvg_history` is provided and a candle in the displacement move trades into a
   previously recorded `FVGZone` (price overlaps with the zone's `high`/`low` range),
   THE `CISDAnalyzer` SHALL detect an IFVG with `imbalance_type = "IFVG"`.
2. WHEN an IFVG is detected, THE `CISDAnalyzer` SHALL set `imbalance_high` and
   `imbalance_low` to the `high` and `low` of the originating `FVGZone`.
3. THE IFVG detection SHALL only consider `FVGZone` objects whose direction opposes the
   current sweep direction (a BULLISH sweep looks for a prior BEARISH FVG that is inverting).
4. WHEN both an FVG and an IFVG are detected in the same displacement move, THE
   `CISDAnalyzer` SHALL prefer the FVG and set `imbalance_type = "FVG"`.
5. WHEN no `fvg_history` is provided or `fvg_history` is an empty list, THE
   `CISDAnalyzer` SHALL proceed with FVG-only detection for step 2.

---

### Requirement 8: Step 3 — CISD Validating Order Block Detection

**User Story:** As the sequence detector at step 3, I want to identify the Order Block formed
by the displacement candle and detect when price closes back into it, so that the full program
flip is confirmed.

#### Acceptance Criteria

1. THE `CISDAnalyzer` SHALL identify the Order Block as the last opposing candle immediately
   before the displacement move: for a BULLISH sequence the OB is the last down-close candle
   before the bullish displacement; for a BEARISH sequence the OB is the last up-close candle
   before the bearish displacement.
2. THE `CISDAnalyzer` SHALL define "closing into the OB" as a candle whose `close` price is
   within the OB body range — i.e., `ob_low <= candle.close <= ob_high` for a bullish sequence,
   or `ob_low <= candle.close <= ob_high` for a bearish sequence.
3. WHEN a candle closes into the OB body after steps 1 and 2 have been satisfied, THE
   `CISDAnalyzer` SHALL set `confirmed = True`, `sequence_step = 3`, and populate `ob_high`
   and `ob_low` with the OB candle's body boundaries.
4. FOR ALL confirmed CISD results, `ob_high` SHALL be strictly greater than `ob_low`.
5. FOR ALL confirmed CISD results, THE `CISDAnalyzer` SHALL set `direction` to match
   `sweep_direction` (BULLISH sweep produces a BULLISH CISD confirmation).
6. THE OB candle index SHALL be strictly less than the displacement candle index; THE
   `CISDAnalyzer` SHALL not identify a candle as both the OB and a displacement candle.

---

### Requirement 9: Sequence Step and Confirmation Invariants

**User Story:** As the confluence scorer and downstream consumers, I want the `sequence_step`
and `confirmed` fields to be structurally consistent at all times, so that I can rely on them
without defensive null-checks or consistency guards.

#### Acceptance Criteria

1. WHEN `confirmed = True`, THE `CISDAnalyzer` SHALL always set `sequence_step = 3`.
2. WHEN `sequence_step = 3`, THE `CISDAnalyzer` SHALL always set `confirmed = True`.
3. WHEN `confirmed = True`, THE `CISDResult.direction` SHALL never equal `"NONE"`.
4. WHEN `sequence_step < 2`, THE `CISDResult.imbalance_type` SHALL be `None`.
5. WHEN `sequence_step < 2`, THE `CISDResult.imbalance_high` and `imbalance_low` SHALL
   both be `None`.
6. WHEN `sequence_step < 3`, THE `CISDResult.ob_high` and `ob_low` SHALL both be `None`.
7. WHEN `sequence_step = 0`, THE `CISDResult.sweep_level` and `sweep_direction` SHALL
   both be `None`.

---

### Requirement 10: Sweep Level Bounds

**User Story:** As the test suite, I want the `sweep_level` to always sit within the price
range of the sweep candle, so that I can cross-reference it against candle data without
floating-point surprises.

#### Acceptance Criteria

1. FOR ALL `CISDResult` objects where `sweep_level` is not `None`, `sweep_level` SHALL be
   greater than or equal to the `low` of the sweep candle AND less than or equal to the
   `high` of the sweep candle.
2. FOR ALL `CISDResult` objects where `sweep_direction = "BULLISH"`, `sweep_level` SHALL
   correspond to a Swing Low price found in the candle window that precedes the sweep candle.
3. FOR ALL `CISDResult` objects where `sweep_direction = "BEARISH"`, `sweep_level` SHALL
   correspond to a Swing High price found in the candle window that precedes the sweep candle.

---

### Requirement 11: Sequence Expiry

**User Story:** As the detector managing state across a sequence, I want partial sequences
that have not completed within `max_sequence_candles` to expire and reset, so that stale,
no-longer-valid setups do not persist and trigger false confirmations on unrelated candles.

#### Acceptance Criteria

1. WHEN a sweep has been detected (sequence_step = 1) and `candles_elapsed` exceeds
   `max_sequence_candles`, THE `CISDAnalyzer` SHALL reset the sequence and return a
   `CISDResult` with `sequence_step = 0` and `confirmed = False`.
2. WHEN an imbalance has been detected (sequence_step = 2) and `candles_elapsed` exceeds
   `max_sequence_candles`, THE `CISDAnalyzer` SHALL reset the sequence and return a
   `CISDResult` with `sequence_step = 0` and `confirmed = False`.
3. THE `candles_elapsed` counter SHALL start at 0 on the sweep candle and increment by 1
   for each subsequent candle scanned.
4. WHEN the sequence is reset due to expiry, all partial sequence fields (`sweep_level`,
   `sweep_direction`, `imbalance_type`, etc.) SHALL be returned as `None`.
5. THE `max_sequence_candles` parameter SHALL accept any positive integer value; THE
   `CISDAnalyzer` SHALL use the value provided at construction time for all subsequent
   `scan()` calls.

---

### Requirement 12: FVG History Management

**User Story:** As the caller (ZoneFeatureExtractor or decide_node), I want a dedicated
method to build and update the FVG history buffer from a candle list, so that IFVG detection
has the rolling context it needs without requiring the caller to implement FVG detection logic.

#### Acceptance Criteria

1. THE `CISDAnalyzer.update_fvg_history` SHALL scan the provided candles and return a list
   of `FVGZone` objects for every fresh 3-candle imbalance detected.
2. FOR ALL `FVGZone` objects returned by `update_fvg_history`, `FVGZone.high` SHALL be
   strictly greater than `FVGZone.low`.
3. THE `update_fvg_history` method SHALL NOT mutate the input candles list.
4. WHEN the same candles are passed to `update_fvg_history` more than once, THE returned
   list SHALL contain the same `FVGZone` objects (idempotent detection — no duplicates from
   repeated calls on the same window).
5. WHEN no FVGs are present in the provided candles, THE method SHALL return an empty list.

---

### Requirement 13: Timeframe Agnosticism

**User Story:** As a caller on any timeframe (M1 through D1), I want the analyzer to accept
any candle list without requiring timeframe metadata, so that the same code path handles both
HTF bias validation and LTF entry gating.

#### Acceptance Criteria

1. THE `CISDAnalyzer.scan` SHALL NOT require or inspect any timeframe field on the input
   candle dictionaries.
2. THE `CISDAnalyzer.scan` SHALL NOT require any minimum number of candles beyond the
   structural minimums needed for swing detection (3 candles) and FVG detection (3 candles).
3. THE `CISDAnalyzer.scan` output for identical candle data SHALL be identical regardless of
   the timeframe label a caller would assign to those candles.

---

### Requirement 14: Integration — ZoneFeatureExtractor HTF Bias

**User Story:** As ZoneFeatureExtractor, I want to call CISDAnalyzer.scan() with HTF candles
and use the result to derive `htf_trend_bias`, so that HTF bias reflects a confirmed program
flip rather than a single candle direction.

#### Acceptance Criteria

1. WHEN `CISDResult.confirmed = True` and `direction = "BULLISH"`, THE `ZoneFeatureExtractor`
   SHALL set `htf_trend_bias = "BULLISH"`.
2. WHEN `CISDResult.confirmed = True` and `direction = "BEARISH"`, THE `ZoneFeatureExtractor`
   SHALL set `htf_trend_bias = "BEARISH"`.
3. WHEN `CISDResult.confirmed = False` (any `sequence_step`), THE `ZoneFeatureExtractor`
   SHALL fall back to the existing single-candle `_derive_htf_trend_bias()` method to retain
   backward-compatible behaviour.
4. THE `ZoneFeatureExtractor` SHALL pass the fvg_history it maintains between calls into
   `CISDAnalyzer.scan(fvg_history=...)` so that IFVG detection has full context.

---

### Requirement 15: Integration — decide_node LTF Entry Gate

**User Story:** As decide_node, I want to call CISDAnalyzer.scan() with LTF candles and use
`sequence_step` as an additional confluence gate, so that entries with only partial structure
confirmation are treated more conservatively.

#### Acceptance Criteria

1. WHEN `CISDResult.sequence_step = 3` (full CISD confirmed), THE `decide_node` SHALL treat
   the CISD gate as fully passed and apply no confidence penalty.
2. WHEN `CISDResult.sequence_step = 2` (sweep + imbalance, no OB close), THE `decide_node`
   SHALL treat the CISD gate as partially passed and apply a configurable confidence
   reduction.
3. WHEN `CISDResult.sequence_step <= 1`, THE `decide_node` SHALL treat the CISD gate as
   failed; the gate failure SHALL be surfaced in `decision_reason`.
4. THE `CISDResult.sequence_step` value SHALL be recorded on `AgentState` so that it is
   available for logging and the learn_node retraining sample.

---

## Correctness Properties

*A property is a characteristic or behaviour that should hold true across all valid executions
of the system — essentially, a formal statement about what the system should do.*

---

### Property 1: sequence_step and confirmed are consistent (Invariant)

For any candle list and any `fvg_history`, calling `CISDAnalyzer.scan()` SHALL produce a
`CISDResult` where:
- `confirmed = True` if and only if `sequence_step = 3`
- `confirmed = False` if and only if `sequence_step < 3`

**Validates: Requirements 9.1, 9.2**

---

### Property 2: confirmed implies direction is not "NONE" (Invariant)

For any `CISDResult` where `confirmed = True`, `direction` SHALL never equal `"NONE"`.

**Validates: Requirement 9.3**

---

### Property 3: imbalance_type is None below step 2 (Invariant)

For any `CISDResult` where `sequence_step < 2`, both `imbalance_type` and `imbalance_high`
and `imbalance_low` SHALL be `None`.

**Validates: Requirements 9.4, 9.5**

---

### Property 4: ob_high > ob_low when confirmed (Invariant)

For any `CISDResult` where `sequence_step = 3`, `ob_high` SHALL be strictly greater than
`ob_low`. Neither SHALL be `None`.

**Validates: Requirements 8.4, 9.6**

---

### Property 5: sweep_level within sweep candle range (Bounds)

For any `CISDResult` where `sweep_level` is not `None`, `sweep_level` SHALL be greater than
or equal to `candles[sweep_candle_index].low` AND less than or equal to
`candles[sweep_candle_index].high`.

**Validates: Requirement 10.1**

---

### Property 6: No sweep → step 0 and not confirmed (Invariant)

For any candle list where no Turtle Soup sweep is detectable, `CISDAnalyzer.scan()` SHALL
return `sequence_step = 0` and `confirmed = False`.

**Validates: Requirements 4.5, 9.7**

---

### Property 7: Partial sequences expire after max_sequence_candles (State / Expiry)

For any partial sequence (step 1 or step 2) and any `max_sequence_candles = N`, after
scanning `N + 1` candles from the sweep candle without completing the sequence, THE result
SHALL have `sequence_step = 0`, `confirmed = False`, and all partial fields SHALL be `None`.

**Validates: Requirements 11.1, 11.2, 11.4**

---

### Property 8: scan() never mutates input candles (Immutability)

For any candle list, after calling `CISDAnalyzer.scan()`, every candle dictionary in the
input list SHALL have the same key-value pairs as before the call.

**Validates: Requirement 3.6**

---

### Property 9: update_fvg_history is idempotent (Idempotence)

For any candle list `C`, calling `update_fvg_history(C)` once and then again on the same
window SHALL return lists with the same set of `FVGZone` objects (no duplicates from repeated
calls on the same window).

**Validates: Requirement 12.4**

---

### Property 10: FVGZone high > low (Invariant)

For any `FVGZone` returned by `update_fvg_history`, `FVGZone.high` SHALL be strictly greater
than `FVGZone.low`.

**Validates: Requirements 2.3, 12.2**

---

### Property 11: imbalance_high > imbalance_low when step >= 2 (Invariant)

For any `CISDResult` where `sequence_step >= 2` and `imbalance_high` is not `None`,
`imbalance_high` SHALL be strictly greater than `imbalance_low`.

**Validates: Requirements 6.4, 7.2**
