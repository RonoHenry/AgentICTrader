# Implementation Plan: 

**spec**: Liquidity Engine

## Overview

Pure-Python analytical package that encodes the complete ICT/TTrades multi-timeframe Price Action
methodology into a deterministic, stateless computation pipeline. Tasks are numbered starting from
**144** to continue the platform task sequence. Every task follows the strict **RED → GREEN →
REFACTOR** TDD cycle. Sub-tasks are ordered: **(a) RED** — write failing tests, **(b) GREEN** —
write minimal implementation, **(c) REFACTOR** — clean up and confirm GREEN.

Tests live in `backend/tests/` following the platform convention. Property-based tests use
`hypothesis`. The package lives at `liquidity_engine/` in the workspace root.

> **This spec is parked for post-v1 implementation (after task 143 ships).**

**Revision note**: Tasks 146 and 152 are new, and tasks 144, 145, 148, 155, 157, 158 were updated
in place. This followed a review of the TTrades reference material (`docs/references/`) against
the original spec, which surfaced three gaps (swing structure hierarchy, wick-based candle typing,
the Candle 1–4 Fractal Model + Equilibrium) and one ambiguity (Breaker confirmation timing) — see
`requirements.md` Requirements 15–17 and the amended Requirement 4.15. SMT (Smart Money Divergence)
was surfaced by the same review and deliberately **excluded** — see `requirements.md` → Non-Goals.
All other tasks are unchanged in content; numbers shifted to keep the sequence contiguous.

---

## Tasks

- [x] 144. Create `liquidity_engine/` package scaffold and `models.py`
  - **144a. RED — Write failing tests** (`backend/tests/test_liquidity_models.py`)
    - `test_candle_valid_construction` — Candle constructs without error given valid OHLCV
    - `test_candle_high_lt_low_raises` — ValueError when high < low
    - `test_candle_high_lt_open_raises` — ValueError when high < open
    - `test_candle_high_lt_close_raises` — ValueError when high < close
    - `test_candle_is_bullish_true` — is_bullish returns True iff close > open
    - `test_candle_is_bearish_true` — is_bearish returns True iff close < open
    - `test_candle_body_size` — body_size == abs(close - open)
    - `test_candle_total_range` — total_range == high - low
    - `test_candle_upper_wick` — upper_wick == high - max(open, close)
    - `test_candle_lower_wick` — lower_wick == min(open, close) - low
    - `test_candle_timestamp_must_be_aware` — naive datetime rejected
    - `test_htf_bias_fields` — HTFBias instantiates with all required fields
    - `test_liquidity_level_fields` — LiquidityLevel has UUID level_id, formed_at aware datetime, touch_count >= 0
    - `test_pdarray_high_gt_low` — PDArray raises on construction when high <= low
    - `test_pdarray_structure_confirmed_defaults_false` — PDArray.structure_confirmed defaults to False for every array_type
    - `test_setup_grade_detail_fields` — SetupGradeDetail instantiates with all 8 boolean conditions
    - `test_liquidity_map_fields` — LiquidityMap instantiates with required fields
    - `test_swing_point_fields` — SwingPoint has UUID swing_id, tier, is_high, price, formed_at aware datetime, broken defaults False
    - `test_swing_point_derived_from_optional` — derived_from_swing_id defaults to None; settable for INTERMEDIATE_TERM/LONG_TERM tiers
    - `test_structure_event_fields` — StructureEvent instantiates with event_type, tier, timeframe, direction, broken_swing_id, confirmed_at aware datetime
    - `test_swing_structure_result_defaults` — SwingStructureResult's six swing-point lists and events default to empty lists; latest_event defaults to None
    - `test_candle_type_enum_values` — CandleType has EXPANSION, REVERSAL, REVERSAL_EXPANSION
    - `test_closure_type_enum_values` — ClosureType has CONTINUATION, REVERSAL
    - `test_fractal_candle_step_closure_type_optional` — FractalCandleStep.closure_type is Optional, defaults to None
    - `test_fractal_model_result_fields` — FractalModelResult instantiates with key_level, steps, range_high, range_low, equilibrium, price_above_equilibrium
    - **PBT — `property_candle_ohlc_invariant`** (`@given` valid/invalid OHLCV floats)
      - **Property 22: Candle OHLC Invariant** — high < low, high < open, or high < close always raises ValueError
      - **Validates: Requirements 11.1, 11.2, 11.3**
    - Confirm all tests FAIL (RED)
  - **144b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/__init__.py` — exports `LiquidityMappingEngine`, `LiquidityMap`
    - Create `liquidity_engine/models.py` — all Pydantic v2 enums and data models:
      - Enums: `Timeframe`, `BiasDirection`, `PDArrayType`, `LiquidityType`, `LiquiditySource`, `CRTPhase`, `PricePhase`, `SetupGrade`, `KillzoneWindow`, `SwingTier`, `StructureEventType`, `CandleType`, `ClosureType`
      - Models: `Candle`, `HTFBias`, `LiquidityLevel`, `PDArray` (incl. `structure_confirmed: bool = False`), `CRTPhaseResult`, `CISDResult`, `CISDCascadeStatus`, `OTEZone`, `UnicornPattern`, `SetupGradeDetail`, `SwingPoint`, `StructureEvent`, `SwingStructureResult`, `FractalCandleStep`, `FractalModelResult`, `LiquidityMap`
      - All `field_validator` decorators with `@classmethod` (Pydantic v2)
      - All computed properties on `Candle` (`is_bullish`, `is_bearish`, `body_size`, `total_range`, `upper_wick`, `lower_wick`)
      - `LiquidityMap.swing_structure: Dict[str, SwingStructureResult] = {}` and `LiquidityMap.fractal_model: Optional[FractalModelResult] = None` fields
      - `LiquidityMap` convenience methods: `get_bias()`, `get_arrays_by_type()`, `get_arrays_in_range()`
      - Stub `LiquidityMap.to_agent_context()` returning `""`
    - Create `liquidity_engine/detectors/__init__.py`
    - Create `liquidity_engine/ipda/__init__.py`
    - Create `liquidity_engine/ote/__init__.py`
    - Create `liquidity_engine/unicorn/__init__.py`
    - Create `liquidity_engine/grader/__init__.py`
    - Create `liquidity_engine/fractal/__init__.py`
    - Create `liquidity_engine/utils/__init__.py`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 14.3, 14.4, 14.5, 15.1, 15.4, 16.7, 17.7_
  - **144c. REFACTOR** — add `model_config = ConfigDict(frozen=True)` on `Candle`; confirm GREEN

- [x] 145. Implement `liquidity_engine/utils/time_utils.py` and `candle_utils.py`
  - **145a. RED — Write failing tests** (`backend/tests/test_liquidity_utils.py`)
    - `test_to_est_from_utc` — UTC datetime correctly offset to EST (UTC-5) / EDT (UTC-4)
    - `test_to_utc_from_est` — EST/EDT correctly converted back to UTC
    - `test_killzone_london_start_end` — 02:00–05:00 EST correctly identified
    - `test_killzone_ny_am_start_end` — 07:00–10:00 EST correctly identified
    - `test_killzone_ny_pm_start_end` — 13:30–16:00 EST correctly identified
    - `test_get_killzone_returns_correct_window` — all three killzone windows + NONE
    - `test_is_in_killzone_true_false` — boundary timestamps tested
    - `test_dst_transition_march` — spring-forward handled correctly (UTC-4)
    - `test_dst_transition_november` — fall-back handled correctly (UTC-5)
    - `test_swing_high_detected` — local maximum identified after n-candle confirmation
    - `test_swing_low_detected` — local minimum identified
    - `test_no_swing_flat_candles` — flat sequence returns no swings
    - `test_atr_calculation` — ATR over n periods matches manual calculation
    - `test_classify_candle_type_expansion` — wick_ratio <= 0.25 → CandleType.EXPANSION
    - `test_classify_candle_type_reversal` — wick_ratio >= 0.5 → CandleType.REVERSAL
    - `test_classify_candle_type_reversal_expansion` — 0.25 < wick_ratio < 0.5 → CandleType.REVERSAL_EXPANSION
    - `test_classify_candle_type_zero_range_is_expansion` — total_range == 0 → CandleType.EXPANSION
    - `test_classify_candle_type_thresholds_are_named_constants` — EXPANSION_WICK_RATIO_MAX and REVERSAL_WICK_RATIO_MIN are module-level constants, not inline literals
    - **PBT — `property_candle_type_classification_total`** (`@given` valid Candle instances)
      - **Property 24 (design.md) / 26 (requirements.md): Candle Type Classification Is Total and Exclusive**
      - **Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5**
    - Confirm all tests FAIL (RED)
  - **145b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/utils/time_utils.py`:
      - `to_est(dt: datetime) -> datetime` using `zoneinfo.ZoneInfo("America/New_York")`
      - `to_utc(dt: datetime) -> datetime`
      - `get_killzone(dt: datetime) -> KillzoneWindow` — London / NY AM / NY PM / NONE
      - `is_in_killzone(dt: datetime) -> bool`
    - Create `liquidity_engine/utils/candle_utils.py`:
      - `find_swing_highs(candles, lookback=2) -> List[int]` — indices of swing highs
      - `find_swing_lows(candles, lookback=2) -> List[int]` — indices of swing lows
      - `calculate_atr(candles, period=14) -> float`
      - `EXPANSION_WICK_RATIO_MAX: float = 0.25`, `REVERSAL_WICK_RATIO_MIN: float = 0.5` — named constants
      - `classify_candle_type(candle: Candle) -> CandleType`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 3.7, 9.9, 14.1, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_
  - **145c. REFACTOR** — extract `KILLZONE_WINDOWS` dict constant; confirm GREEN

- [x] 146. Implement `liquidity_engine/detectors/structure.py` — `SwingStructureClassifier`
  - **146a. RED — Write failing tests** (`backend/tests/test_liquidity_swing_structure.py`)
    - `test_seeds_short_term_highs_from_swing_indices` — every `find_swing_highs` index becomes an `STH` `SwingPoint`
    - `test_seeds_short_term_lows_from_swing_indices` — every `find_swing_lows` index becomes an `STL` `SwingPoint`
    - `test_ith_promoted_when_adjacent_stl_broken` — an STH is promoted to ITH once the STL preceding it is broken
    - `test_itl_promoted_when_adjacent_sth_broken` — an STL is promoted to ITL once the STH preceding it is broken
    - `test_lth_promoted_when_adjacent_itl_broken` — an ITH is promoted to LTH once the ITL preceding it is broken
    - `test_ltl_promoted_when_adjacent_ith_broken` — an ITL is promoted to LTL once the ITH preceding it is broken
    - `test_promoted_swing_has_derived_from_swing_id` — every promoted SwingPoint's `derived_from_swing_id` points at the lower-tier SwingPoint
    - `test_no_promotion_without_broken_lower_tier` — an STH/STL with an unbroken adjacent low/high stays SHORT_TERM
    - `test_bos_emitted_on_same_direction_break` — closing beyond the most recent same-tier swing in the trend direction emits BOS
    - `test_choch_emitted_on_opposite_direction_break` — closing beyond the most recent same-tier swing against the trend emits CHOCH
    - `test_structure_event_never_both_bos_and_choch` — a single break produces exactly one StructureEvent, never two
    - `test_latest_event_reflects_most_recent_break` — `SwingStructureResult.latest_event` is the chronologically last StructureEvent
    - `test_classify_is_deterministic` — identical candle input twice → identical SwingStructureResult
    - `test_swing_structure_result_per_timeframe` — one SwingStructureResult per timeframe key in candles_by_tf
    - `test_no_swings_on_flat_candles` — flat candle sequence produces empty swing lists and no events
    - **PBT — `property_swing_tier_promotion_requires_broken_lower_tier`** (`@given` candle lists)
      - **Property 22 (design.md) / 24 (requirements.md): Swing Tier Promotion Requires a Broken Lower Tier**
      - **Validates: Requirements 15.2, 15.3, 15.4**
    - **PBT — `property_bos_choch_mutual_exclusivity`** (`@given` candle lists)
      - **Property 23 (design.md) / 25 (requirements.md): BOS/CHoCH Mutual Exclusivity**
      - **Validates: Requirements 15.5, 15.6, 15.7**
    - Confirm all tests FAIL (RED)
  - **146b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/detectors/structure.py`:
      - `SwingStructureClassifier.classify(candles_by_tf) -> Dict[Timeframe, SwingStructureResult]`
      - `SwingStructureClassifier._promote_tier(swings, candles) -> List[SwingPoint]`
      - `SwingStructureClassifier._classify_structure_events(swings, candles) -> List[StructureEvent]`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9_
  - **146c. REFACTOR** — extract `_break_confirmed(swing, candles)` helper shared by promotion and event classification; confirm GREEN

- [x] 147. Implement `liquidity_engine/detectors/external.py` — `LiquidityLevelDetector`
  - **147a. RED — Write failing tests** (`backend/tests/test_liquidity_external_detector.py`)
    - `test_pwh_detected_as_bsl` — PWH from W1 candles returned as BSL level
    - `test_pwl_detected_as_ssl` — PWL from W1 candles returned as SSL level
    - `test_pdh_detected_as_bsl` — PDH from D1 candles returned as BSL
    - `test_pdl_detected_as_ssl` — PDL from D1 candles returned as SSL
    - `test_pmh_detected_as_bsl` — PMH from MN1 candles returned as BSL
    - `test_pml_detected_as_ssl` — PML from MN1 candles returned as SSL
    - `test_equal_highs_within_tolerance` — two swing highs within 0.1% classified as EQH (BSL)
    - `test_equal_lows_within_tolerance` — two swing lows within 0.1% classified as EQL (SSL)
    - `test_equal_highs_outside_tolerance_not_classified` — swing highs > 0.1% apart not merged
    - `test_session_high_london` — session high detected for London window candles
    - `test_session_low_london` — session low detected for London window candles
    - `test_session_high_ny_am` — NY AM session high detected
    - `test_session_low_ny_pm` — NY PM session low detected
    - `test_strength_score_range` — every returned LiquidityLevel has strength_score in [0.0, 1.0]
    - `test_level_id_is_uuid` — level_id is valid UUID string
    - `test_formed_at_is_aware` — formed_at is timezone-aware UTC datetime
    - `test_touch_count_nonnegative` — touch_count >= 0 on all returned levels
    - **PBT — `property_equal_highs_tolerance_invariant`** (`@given` candle lists)
      - **Property 20 (design.md): Equal Highs/Lows Satisfy Tolerance Invariant**
      - **Validates: Requirement 3.6**
    - **PBT — `property_strength_scores_in_range`** (`@given` candle lists)
      - **Property 19 (design.md): Strength Scores in Valid Range** (LiquidityLevel)
      - **Validates: Requirements 3.8**
    - Confirm all tests FAIL (RED)
  - **147b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/detectors/external.py`:
      - `LiquidityLevelDetector.detect(candles_by_tf, timestamp) -> List[LiquidityLevel]`
      - `_detect_previous_highs_lows(candles_by_tf) -> List[LiquidityLevel]`
      - `_detect_equal_highs_lows(candles, tolerance_pct=0.001) -> List[LiquidityLevel]`
      - `_detect_session_highs_lows(candles, timestamp) -> List[LiquidityLevel]`
      - `_score_level(level, candles) -> float` — touches + timeframe weight + recency
    - Create `liquidity_engine/detectors/institutional.py` (session + trendline stubs for post-v1)
    - Confirm all tests PASS (GREEN)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_
  - **147c. REFACTOR** — extract `_TIMEFRAME_WEIGHT` constant map; confirm GREEN

- [x] 148. Implement `liquidity_engine/detectors/internal.py` — `PDArrayDetector`
  - **148a. RED — Write failing tests** (`backend/tests/test_liquidity_internal_detector.py`)
    - `test_bullish_fvg_detected` — gap between candles[i-2].low and candles[i].high → FVG BULLISH
    - `test_bearish_fvg_detected` — gap between candles[i-2].high and candles[i].low → FVG BEARISH
    - `test_fvg_high_gt_low` — all detected FVGs satisfy high > low
    - `test_fvg_filled_when_price_fills_gap` — is_filled=True, filled_at populated after gap filled
    - `test_bearish_ob_detected` — last up-close candle before bearish expansion detected as OB BEARISH
    - `test_bullish_ob_detected` — last down-close candle before bullish expansion detected as OB BULLISH
    - `test_ob_high_gt_low` — all OBs satisfy high > low
    - `test_breaker_block_from_violated_ob` — violated OB tagged as BREAKER with source_ob_id set
    - `test_breaker_structure_confirmed_true_after_opposing_structure_event` — a BREAKER's `structure_confirmed` is True when `structure_events` contains a same-tier BOS/CHoCH on the opposing side, formed after the OB violation
    - `test_breaker_structure_confirmed_false_without_structure_event` — a BREAKER's `structure_confirmed` stays False when no qualifying StructureEvent is passed in
    - `test_breaker_classification_unaffected_by_structure_confirmed` — the BREAKER is still tagged at the moment of violation regardless of whether structure_confirmed later becomes True — classification timing does not change
    - `test_ifvg_from_filled_fvg` — IFVG created from filled FVG with opposing direction
    - `test_bpr_from_overlapping_fvgs` — overlapping bull + bear FVG tagged as BPR, both IDs populated
    - `test_cisd_level_is_first_candle_open` — CISD_LEVEL.cisd_sequence_open == open of first candle in sequence
    - `test_pdarray_timeframe_populated` — every returned PDArray has timeframe field set
    - `test_strength_score_in_range` — all PDArrays have strength_score in [0.0, 1.0]
    - **PBT — `property_all_pdarray_high_gt_low`** (`@given` candle lists)
      - **Property 6 / 7 / 8 (design.md): FVG High > Low / OB High > Low / All PDArray High > Low**
      - **Validates: Requirements 4.3, 4.6, 4.12**
    - **PBT — `property_pdarray_strength_scores_in_range`** (`@given` candle lists)
      - **Property 19 (design.md): Strength Scores in Valid Range** (PDArray)
      - **Validates: Requirement 4.11**
    - **PBT — `property_structure_confirmed_breaker_requires_event`** (`@given` OB/StructureEvent pairs)
      - **Property 26 (design.md) / 28 (requirements.md): Structure-Confirmed Breaker Requires a Corresponding Structure Event**
      - **Validates: Requirements 4.15**
    - Confirm all tests FAIL (RED)
  - **148b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/detectors/internal.py`:
      - `PDArrayDetector.detect(candles_by_tf, swing_structure) -> List[PDArray]`
      - `_detect_fvg(candles, tf) -> List[PDArray]`
      - `_detect_order_blocks(candles, tf) -> List[PDArray]`
      - `_detect_breaker_blocks(candles, ob_list, structure_events) -> List[PDArray]` — sets `structure_confirmed` per Requirement 4.15
      - `_detect_ifvg(candles, fvg_list) -> List[PDArray]`
      - `_detect_bpr(fvg_list) -> List[PDArray]`
      - `_detect_cisd_levels(candles, tf) -> List[PDArray]`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 4.14, 4.15_
  - **148c. REFACTOR** — consolidate `_assign_strength_score()` helper; confirm GREEN

- [x] 149. Checkpoint — run full test suite; ensure tasks 144–148 are all GREEN
  - Run `pytest backend/tests/test_liquidity_models.py backend/tests/test_liquidity_utils.py backend/tests/test_liquidity_swing_structure.py backend/tests/test_liquidity_external_detector.py backend/tests/test_liquidity_internal_detector.py -v`
  - All tests must pass. Ask the user if any failures arise.

- [x] 150. Implement `liquidity_engine/ipda/cisd.py` — `CISDDetector`
  - **150a. RED — Write failing tests** (`backend/tests/test_liquidity_cisd.py`)
    - `test_bearish_cisd_detected` — series of up-close candles followed by close below first-candle open → CISD BEARISH confirmed
    - `test_bullish_cisd_detected` — series of down-close candles followed by close above first-candle open → CISD BULLISH confirmed
    - `test_cisd_not_confirmed_without_swing_prerequisite` — has_swing_prerequisite=False → confirmed=False
    - `test_cisd_level_equals_first_candle_open` — CISDResult.level == open of first candle in sequence
    - `test_cisd_sequence_start_time_populated` — sequence_start_time matches first candle timestamp
    - `test_cisd_violation_candle_time_populated` — violation_candle_time matches the breaking candle timestamp
    - `test_cisd_direction_bearish_for_bearish_cisd` — direction == BEARISH
    - `test_cisd_direction_bullish_for_bullish_cisd` — direction == BULLISH
    - `test_swing_prerequisite_3_candle_check` — 3-candle swing verified before confirming
    - `test_no_cisd_on_single_candle` — single candle returns confirmed=False
    - Confirm all tests FAIL (RED)
  - **150b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/ipda/cisd.py`:
      - `CISDDetector.detect(candles) -> Optional[CISDResult]`
      - `_has_swing_point_prerequisite(candles) -> bool` — validates 3-candle swing
    - Confirm all tests PASS (GREEN)
    - _Requirements: 6.1, 6.2, 6.3, 6.6_
  - **150c. REFACTOR** — extract `_find_sequence_open()` helper; confirm GREEN

- [x] 151. Implement `liquidity_engine/ipda/classifier.py` — `IPDAClassifier`
  - **151a. RED — Write failing tests** (`backend/tests/test_liquidity_ipda_classifier.py`)
    - `test_c1_accumulation_tight_range` — ATR-relative tight candle series classified as C1_ACCUMULATION
    - `test_c2_manipulation_within_c1_range` — candle closing within C1 range + confirmed lower-TF CISD → C2_MANIPULATION
    - `test_c2_within_c1_field_true` — CRTPhaseResult.c2_within_c1 == True for C2
    - `test_c2_confirmation_tf_cisd_true` — CRTPhaseResult.confirmation_tf_cisd == True for C2
    - `test_c3_distribution_strong_directional_candle` — strong directional candle away from C2 → C3_DISTRIBUTION
    - `test_c4_continuation_follow_through` — follow-through candle in C3 direction → C4_CONTINUATION
    - `test_unknown_when_no_conditions_met` — random candles return UNKNOWN
    - `test_confidence_in_range` — CRTPhaseResult.confidence in [0.0, 1.0]
    - `test_c1_range_populated` — c1_range_high and c1_range_low set for C1+ phases
    - `test_cisd_cascade_mn1_maps_to_d1` — cascade map: MN1 → D1
    - `test_cisd_cascade_w1_maps_to_h4` — W1 → H4
    - `test_cisd_cascade_d1_maps_to_h1` — D1 → H1
    - `test_cisd_cascade_h4_maps_to_m15` — H4 → M15
    - `test_cisd_cascade_m30_maps_to_m3` — M30 → M3
    - `test_cisd_cascade_m15_maps_to_m1` — M15 → M1
    - `test_cascade_valid_when_both_cisds_confirmed` — cascade_valid=True iff both trigger + confirmation confirmed
    - `test_cascade_invalid_when_trigger_unconfirmed` — trigger.confirmed=False → cascade_valid=False
    - `test_cascade_invalid_when_confirmation_unconfirmed` — confirmation.confirmed=False → cascade_valid=False
    - `test_cascade_invalid_when_timeframe_absent` — missing timeframe data → cascade_valid=False
    - `test_crt_phases_keyed_by_timeframe_value` — LiquidityMap.crt_phases keyed by Timeframe.value string
    - **PBT — `property_cisd_cascade_valid_iff_both_confirmed`** (`@given` CISD result pairs)
      - **Property 17 (design.md): CISD Cascade Validity Requires Both CISDs**
      - **Validates: Requirement 6.4**
    - Confirm all tests FAIL (RED)
  - **151b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/ipda/classifier.py`:
      - `IPDAClassifier.classify_crt_phase(candles, tf) -> CRTPhaseResult`
      - `IPDAClassifier.validate_cisd_cascade(candles_by_tf, trigger_tf) -> CISDCascadeStatus`
      - `CISD_CASCADE` dict constant with all 6 timeframe mappings
    - Confirm all tests PASS (GREEN)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.4, 6.5, 6.7, 6.8_
  - **151c. REFACTOR** — extract `_classify_phase()` pure function; confirm GREEN

- [x] 152. Implement `liquidity_engine/fractal/candle_model.py` — `FractalModelTracker`
  - **152a. RED — Write failing tests** (`backend/tests/test_liquidity_fractal_model.py`)
    - `test_step_one_has_no_closure_type` — the first candle in the sequence gets `closure_type = None`
    - `test_continuation_closure_when_extending_range` — Step N closing beyond Step N-1's extreme in the developing direction → ClosureType.CONTINUATION
    - `test_reversal_closure_when_closing_back_within_prior_range` — Step N closing back within Step N-1's range on the opposite side of Step N-1's open → ClosureType.REVERSAL
    - `test_range_high_only_expands` — range_high never decreases as steps accumulate
    - `test_range_low_only_contracts_downward` — range_low never increases as steps accumulate
    - `test_equilibrium_equals_range_midpoint` — equilibrium == (range_high + range_low) / 2 after every step
    - `test_price_above_equilibrium_true` — latest close > equilibrium → price_above_equilibrium=True
    - `test_price_above_equilibrium_false` — latest close <= equilibrium → price_above_equilibrium=False
    - `test_key_level_immutable_across_steps` — key_level passed at call time is unchanged in the result regardless of step count
    - `test_returns_none_on_insufficient_candles` — empty or single-candle input with no way to seed a sequence returns None rather than a degenerate result
    - `test_track_is_deterministic` — identical candles + key_level twice → identical FractalModelResult
    - **PBT — `property_fractal_model_range_and_equilibrium_correctness`** (`@given` candle sequences + key_level)
      - **Property 25 (design.md) / 27 (requirements.md): Fractal Model Range and Equilibrium Correctness**
      - **Validates: Requirements 17.3, 17.4**
    - Confirm all tests FAIL (RED)
  - **152b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/fractal/candle_model.py`:
      - `FractalModelTracker.track(candles, key_level) -> Optional[FractalModelResult]`
      - `FractalModelTracker._classify_closure(prior, current) -> ClosureType`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8_
  - **152c. REFACTOR** — extract `_update_range(step, range_high, range_low)` helper; confirm GREEN

- [x] 153. Implement `liquidity_engine/ote/calculator.py` — `OTECalculator`
  - **153a. RED — Write failing tests** (`backend/tests/test_liquidity_ote.py`)
    - `test_fib_62_computed_correctly` — fib_62 == swing_high - 0.62 * (swing_high - swing_low)
    - `test_fib_705_computed_correctly` — fib_705 == swing_high - 0.705 * (swing_high - swing_low)
    - `test_fib_79_computed_correctly` — fib_79 == swing_high - 0.79 * (swing_high - swing_low)
    - `test_golden_level_equals_fib705` — OTEZone.golden_level == OTEZone.fib_705
    - `test_ote_low_lt_ote_high_bullish` — bullish setup: ote_low < ote_high
    - `test_ote_low_lt_ote_high_bearish` — bearish setup: ote_low < ote_high
    - `test_bullish_ote_anchors_from_high_to_low` — discount retracement zone correct
    - `test_bearish_ote_anchors_from_low_to_high` — premium retracement zone correct
    - `test_price_in_ote_true` — price inside [ote_low, ote_high] → price_in_ote=True
    - `test_price_in_ote_false` — price outside → price_in_ote=False
    - `test_price_in_ote_at_boundary` — price exactly at ote_low or ote_high → True
    - `test_find_displacement_leg_identifies_fvg_leg` — most recent impulsive move with FVG returned
    - **PBT — `property_ote_zone_structural_ordering`** (`@given` valid swing_high/swing_low pairs)
      - **Property 7 (design.md): OTE Zone Structural Ordering** — fib_62 < fib_705 < fib_79
      - **Validates: Requirement 7.4**
    - **PBT — `property_ote_low_lt_ote_high`** (`@given` valid swing pairs + BiasDirection)
      - **Property 8 (design.md): OTE Zone Low Less Than High** — ote_low < ote_high
      - **Validates: Requirements 7.5, 10.4**
    - **PBT — `property_golden_level_equals_fib705`** (`@given` valid swing pairs)
      - **Property 9 (design.md): OTE Golden Level Equals fib_705**
      - **Validates: Requirement 7.6**
    - **PBT — `property_price_in_ote_flag_correctness`** (`@given` OTEZone + current_price)
      - **Property 10 (design.md): OTE Price-In-Zone Flag Correctness**
      - **Validates: Requirements 7.9, 7.10**
    - Confirm all tests FAIL (RED)
  - **153b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/ote/calculator.py`:
      - `OTECalculator.FIBONACCI_LEVELS`, `OTE_LOW`, `OTE_HIGH`, `GOLDEN_LEVEL` constants
      - `OTECalculator.calculate(swing_high, swing_low, direction) -> OTEZone`
      - `OTECalculator.find_displacement_leg(candles, direction) -> Optional[tuple[float, float]]`
      - `OTECalculator.price_in_ote(price, ote_zone) -> bool`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11_
  - **153c. REFACTOR** — extract `_fib_level(swing_high, swing_low, pct, direction)` helper; confirm GREEN

- [x] 154. Implement `liquidity_engine/unicorn/detector.py` — `UnicornDetector`
  - **154a. RED — Write failing tests** (`backend/tests/test_liquidity_unicorn.py`)
    - `test_bullish_unicorn_detected` — bullish BREAKER + bullish FVG overlapping → UnicornPattern returned
    - `test_bearish_unicorn_detected` — bearish BREAKER + bearish FVG overlapping → UnicornPattern returned
    - `test_unicorn_overlap_low_lt_overlap_high` — overlap_low < overlap_high always
    - `test_overlap_high_is_min_of_highs` — overlap_high == min(breaker.high, fvg.high)
    - `test_overlap_low_is_max_of_lows` — overlap_low == max(breaker.low, fvg.low)
    - `test_no_unicorn_when_no_overlap` — non-overlapping pairs return None
    - `test_most_recent_unicorn_returned` — when multiple qualifying pairs, most recent formed_at wins
    - `test_unicorn_returns_none_on_empty_arrays` — empty pd_arrays list → None
    - `test_unicorn_strength_score_is_combined` — strength_score derived from breaker + FVG scores
    - `test_cross_direction_not_matched` — bullish breaker + bearish FVG not matched
    - `test_near_touch_within_tolerance` — near-overlap within 0.1% tolerance still qualifies
    - **PBT — `property_unicorn_overlap_well_formed`** (`@given` valid PDArray pairs)
      - **Property 11 (design.md): UNICORN Overlap Well-Formed** — overlap_low < overlap_high
      - **Validates: Requirements 8.3, 10.5**
    - **PBT — `property_unicorn_returns_most_recent`** (`@given` list of qualifying pairs with distinct timestamps)
      - **Property 12 (design.md): UNICORN Returns Most Recent**
      - **Validates: Requirement 8.5**
    - Confirm all tests FAIL (RED)
  - **154b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/unicorn/detector.py`:
      - `UnicornDetector.detect(pd_arrays, overlap_tolerance_pct=0.001) -> Optional[UnicornPattern]`
      - `UnicornDetector._arrays_overlap(a, b, tolerance_pct) -> bool`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_
  - **154c. REFACTOR** — extract `_compute_overlap()` pure function; confirm GREEN

- [x] 155. Implement `liquidity_engine/grader/setup_grader.py` — `SetupGrader`
  - **155a. RED — Write failing tests** (`backend/tests/test_liquidity_grader.py`)
    - `test_aplus_grade_all_8_conditions_true` — all 8 True → SetupGrade.A_PLUS
    - `test_a_grade_7_conditions_true` — exactly 7 True → SetupGrade.A
    - `test_b_grade_sweep_cisd_fvg_only` — sweep + CISD + FVG only (no Breaker/UNICORN) → SetupGrade.B
    - `test_no_trade_fewer_than_6_conditions` — 5 conditions met → SetupGrade.NO_TRADE
    - `test_no_trade_when_htf_bias_false` — htf_bias_confirmed=False → NO_TRADE regardless of other conditions
    - `test_no_trade_when_no_draw_on_liquidity` — draw_on_liquidity_identified=False → NO_TRADE
    - `test_conditions_met_count_correct` — conditions_met == count of True boolean fields
    - `test_grade_reason_nonempty` — grade_reason is non-empty string for every grade
    - `test_check_htf_bias_true` — D1 and W1 both non-NEUTRAL → True
    - `test_check_htf_bias_false_when_neutral` — either D1 or W1 NEUTRAL → False
    - `test_check_draw_on_liquidity_true` — draw_on_liquidity not None → True
    - `test_check_liquidity_sweep_true` — sweep_detected=True → True
    - `test_check_time_window_london` — timestamp in London killzone → True
    - `test_check_time_window_ny_am` — timestamp in NY AM killzone → True
    - `test_check_time_window_ny_pm` — timestamp in NY PM killzone → True
    - `test_check_time_window_off_hours` — timestamp outside all killzones → False
    - `test_suggested_entry_golden_level_when_ote` — entry_array_is_ote=True → suggested_entry == golden_level
    - `test_suggested_entry_array_midpoint_when_not_ote` — entry_array_is_ote=False → midpoint of entry array
    - `test_suggested_stop_below_array_low_bullish` — bullish: stop below PDArray.low
    - `test_suggested_stop_above_array_high_bearish` — bearish: stop above PDArray.high
    - `test_grade_reason_mentions_structure_confirmed_when_true` — entry_array.structure_confirmed=True → grade_reason references it
    - `test_conditions_met_unaffected_by_structure_confirmed` — structure_confirmed True or False never changes conditions_met or the assigned grade — it is informational only
    - `test_grade_reason_may_reference_equilibrium` — when fractal_model is present, grade_reason may reference price_above_equilibrium without altering the grade
    - **PBT — `property_setup_grade_conditions_met_accuracy`** (`@given` boolean 8-tuples)
      - **Property 15 (design.md): Setup Grade conditions_met Accuracy**
      - **Validates: Requirements 9.2, 10.6**
    - **PBT — `property_aplus_requires_all_8_conditions`** (`@given` boolean 8-tuples)
      - **Property 16 (design.md): A+ Grade Requires All 8 Conditions**
      - **Validates: Requirement 9.1**
    - **PBT — `property_no_trade_when_conditions_below_threshold`** (`@given` boolean 8-tuples satisfying threshold)
      - **Property 17 (design.md): NO_TRADE Grade When Conditions Below Threshold**
      - **Validates: Requirement 9.5**
    - Confirm all tests FAIL (RED)
  - **155b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/grader/setup_grader.py`:
      - `SetupGrader.grade(liquidity_map, timestamp) -> SetupGrade`
      - `SetupGrader._check_htf_bias(lm) -> bool`
      - `SetupGrader._check_draw_on_liquidity(lm) -> bool`
      - `SetupGrader._check_liquidity_sweep(lm) -> bool`
      - `SetupGrader._check_displacement(lm) -> bool`
      - `SetupGrader._check_cisd(lm) -> bool`
      - `SetupGrader._check_entry_pd_array(lm) -> bool`
      - `SetupGrader._check_stop_placement(lm) -> bool`
      - `SetupGrader._check_time_window(lm, ts) -> bool`
      - `SetupGrader._build_grade_reason(lm, detail) -> str` — includes structure_confirmed / equilibrium context when present, without influencing `conditions_met`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13_
  - **155c. REFACTOR** — extract `_build_grade_reason()` helper; confirm GREEN

- [x] 156. Checkpoint — run grader + upstream test suite; ensure tasks 150–155 are all GREEN
  - Run `pytest backend/tests/test_liquidity_cisd.py backend/tests/test_liquidity_ipda_classifier.py backend/tests/test_liquidity_fractal_model.py backend/tests/test_liquidity_ote.py backend/tests/test_liquidity_unicorn.py backend/tests/test_liquidity_grader.py -v`
  - All tests must pass. Ask the user if any failures arise.

- [x] 157. Implement `liquidity_engine/engine.py` — `LiquidityMappingEngine`
  - **157a. RED — Write failing tests** (`backend/tests/test_liquidity_engine.py`)
    - `test_analyze_returns_liquidity_map` — valid candles_by_tf → LiquidityMap returned
    - `test_analyze_requires_d1_timeframe` — missing D1 raises ValueError
    - `test_analyze_requires_w1_timeframe` — missing W1 raises ValueError
    - `test_analyzed_at_matches_timestamp_arg` — LiquidityMap.analyzed_at == timestamp argument
    - `test_analyzed_at_is_timezone_aware` — analyzed_at has tzinfo set
    - `test_htf_bias_contains_d1` — htf_bias["D1"] present after analyze()
    - `test_htf_bias_contains_w1` — htf_bias["W1"] present after analyze()
    - `test_does_not_mutate_input` — input candles unchanged after analyze()
    - `test_sub_components_called_in_order` — (use mock to verify call sequence) HTFBiasClassifier → LiquidityLevelDetector → SwingStructureClassifier → PDArrayDetector → FractalModelTracker → IPDAClassifier → OTECalculator → UnicornDetector → SetupGrader
    - `test_swing_structure_populated_per_timeframe` — LiquidityMap.swing_structure has an entry for every timeframe in candles_by_tf
    - `test_pd_array_detector_receives_swing_structure` — PDArrayDetector.detect() is called with the SwingStructureClassifier output, not an empty dict
    - `test_fractal_model_populated_when_key_level_available` — fractal_model is set when a draw_on_liquidity or HTF reference_open is available to seed key_level
    - `test_fractal_model_none_when_insufficient_data` — fractal_model is None when there isn't enough candle data to seed a sequence, matching FractalModelTracker's own contract
    - `test_draw_on_liquidity_bsl_when_bullish_bias` — BULLISH D1+W1 → draw target is BSL
    - `test_draw_on_liquidity_ssl_when_bearish_bias` — BEARISH D1+W1 → draw target is SSL
    - `test_draw_on_liquidity_none_when_no_unswept_levels` — no unswept levels → None
    - `test_sweep_detected_true_when_price_through_level` — price trades through draw level → sweep_detected=True
    - `test_sweep_detected_false_when_price_not_through` — sweep_detected=False otherwise
    - `test_draw_on_liquidity_level_id_in_liquidity_levels` — draw_on_liquidity.level_id in levels list
    - `test_get_arrays_in_range_excludes_filled` — get_arrays_in_range returns only unfilled arrays
    - `test_get_arrays_in_range_price_overlap` — price overlap filter correct
    - **PBT — `property_engine_determinism`** (`@given` valid candles_by_tf, instrument, timestamp)
      - **Property 1 (design.md): Engine Determinism (Statelessness)** — identical inputs → identical LiquidityMap outputs
      - **Validates: Requirements 1.2, 14.1**
    - **PBT — `property_input_immutability`** (`@given` valid candles_by_tf)
      - **Property 2 (design.md): Input Immutability** — candle fields unchanged after analyze()
      - **Validates: Requirement 1.3**
    - **PBT — `property_d1_w1_bias_always_present`** (`@given` valid candles_by_tf with D1+W1)
      - **Property 5 (design.md): D1 and W1 Bias Always Present**
      - **Validates: Requirements 2.6, 10.2**
    - **PBT — `property_draw_on_liquidity_reference_integrity`** (`@given` valid candles_by_tf)
      - **Property 18 (design.md): draw_on_liquidity Reference Integrity**
      - **Validates: Requirement 10.3**
    - Confirm all tests FAIL (RED)
  - **157b. GREEN — Write minimal implementation**
    - Create `liquidity_engine/engine.py`:
      - `LiquidityMappingEngine.analyze(candles_by_tf, instrument, timestamp) -> LiquidityMap`
      - `_classify_htf_bias(candles_by_tf) -> Dict[Timeframe, HTFBias]`
        - Uses `HTFBiasClassifier` (inline or in `detectors/external.py`)
        - D1: NY midnight (00:00 EST) open; W1: Sunday 18:00 EST open; MN1: first calendar month open
      - `_detect_liquidity_levels(candles_by_tf) -> List[LiquidityLevel]`
      - `_classify_swing_structure(candles_by_tf) -> Dict[Timeframe, SwingStructureResult]`
      - `_detect_pd_arrays(candles_by_tf, swing_structure) -> List[PDArray]`
      - `_track_fractal_model(candles, key_level) -> Optional[FractalModelResult]`
      - `_classify_crt_phases(candles_by_tf) -> Dict[Timeframe, CRTPhaseResult]`
      - `_validate_cisd_cascade(candles_by_tf) -> CISDCascadeStatus`
      - `_find_draw_on_liquidity(bias, levels) -> Optional[LiquidityLevel]`
      - `_detect_sweep(candles_by_tf, draw) -> bool`
      - Wire: HTFBiasClassifier → LiquidityLevelDetector → SwingStructureClassifier → PDArrayDetector → FractalModelTracker → IPDAClassifier → OTECalculator → UnicornDetector → SetupGrader (per amended Requirement 1.5)
    - Update `liquidity_engine/__init__.py` to export `LiquidityMappingEngine` and `LiquidityMap`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 15.9, 17.7_
  - **157c. REFACTOR** — ensure no sub-component holds mutable state between calls; confirm GREEN

- [x] 158. Implement `LiquidityMap.to_agent_context()` and `HTFBiasClassifier`
  - **158a. RED — Write failing tests** (`backend/tests/test_liquidity_context.py`)
    - `test_to_agent_context_nonempty` — valid LiquidityMap → non-empty string
    - `test_to_agent_context_contains_all_htf_biases` — every htf_bias key+direction in output
    - `test_to_agent_context_contains_grade` — SetupGrade value present in output
    - `test_to_agent_context_contains_conditions_met` — conditions_met count present
    - `test_to_agent_context_contains_draw_target_when_set` — draw_on_liquidity price + source present
    - `test_to_agent_context_omits_draw_target_when_none` — no spurious draw line when None
    - `test_to_agent_context_answers_three_questions` — output references "come from", "now", "go"
    - `test_to_agent_context_mentions_latest_structure_event_when_present` — the most recent BOS/CHoCH across timeframes is referenced when `swing_structure` has one
    - `test_to_agent_context_mentions_equilibrium_when_fractal_model_present` — price_above_equilibrium is referenced when `fractal_model` is not None
    - `test_to_agent_context_omits_structure_and_equilibrium_lines_when_absent` — no spurious lines when swing_structure has no events / fractal_model is None
    - `test_htf_bias_bullish_when_price_above_open` — current_price > reference_open → BULLISH
    - `test_htf_bias_bearish_when_price_below_open` — current_price < reference_open → BEARISH
    - `test_htf_bias_neutral_within_tolerance` — within 0.01% → NEUTRAL
    - `test_htf_bias_distance_from_open` — distance_from_open == current_price - reference_open
    - `test_htf_bias_distance_pct` — distance_pct == distance_from_open / reference_open
    - `test_d1_uses_ny_midnight_open` — D1 reference_open == 00:00 EST candle open
    - `test_w1_uses_sunday_1800_est_open` — W1 reference_open == Sunday 18:00 EST open
    - `test_mn1_uses_first_candle_of_month` — MN1 reference_open == first calendar month candle open
    - **PBT — `property_htf_bias_direction_correctness`** (`@given` price/open pairs outside neutral band)
      - **Property 3 (design.md): HTF Bias Direction Correctness**
      - **Validates: Requirements 2.1, 2.2**
    - **PBT — `property_htf_bias_neutral_band`** (`@given` price within 0.01% of open)
      - **Property 4 (design.md): HTF Bias Neutral Band**
      - **Validates: Requirement 2.3**
    - **PBT — `property_to_agent_context_nonempty_and_complete`** (`@given` valid LiquidityMap)
      - **Property 21 (design.md): to_agent_context Non-Empty and Complete**
      - **Validates: Requirements 10.7, 10.8, 10.9**
    - Confirm all tests FAIL (RED)
  - **158b. GREEN — Write minimal implementation**
    - Implement `LiquidityMap.to_agent_context()` in `liquidity_engine/models.py` following the 3-question narrative template:
      1. "Where has price come from?" — HTF context, PD arrays swept/respected, most recent BOS/CHoCH
      2. "Where is it now?" — current time window, price vs daily/weekly open, CRT phase, price vs. Fractal Model equilibrium
      3. "Where is it likely to go?" — draw-on-liquidity target, OTE zone, setup grade
    - Implement `HTFBiasClassifier` in `liquidity_engine/engine.py` or a dedicated `detectors/bias.py`:
      - `classify(candles_by_tf, current_price) -> Dict[Timeframe, HTFBias]`
      - `_get_reference_open(tf, candles, timestamp) -> float`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 10.7, 10.8, 10.9, 10.10, 14.8_
  - **158c. REFACTOR** — format `to_agent_context()` output as structured Markdown sections; confirm GREEN

- [x] 159. Checkpoint — full engine integration test; ensure tasks 157–158 GREEN
  - Run `pytest backend/tests/test_liquidity_engine.py backend/tests/test_liquidity_context.py -v`
  - Run `pytest backend/tests/ -k "liquidity" --cov=liquidity_engine --cov-report=term-missing`
  - Coverage must be ≥ 90%. Ask the user if below threshold.
  - **Result: 244 passed, 97% coverage across `liquidity_engine/`** (only `detectors/institutional.py`,
    a deliberate post-v1 stub, is uncovered).

- [x] 160. Integrate `LiquidityMappingEngine` with `agent/nodes/observe_node.py` and `AgentState`
  - **160a. RED — Write failing tests** (`backend/tests/test_observe_node_liquidity.py`)
    - `test_observe_node_stores_liquidity_map` — when message includes candles_by_tf, observe_node populates AgentState.liquidity_map
    - `test_observe_node_liquidity_map_is_liquidity_map_type` — AgentState.liquidity_map is LiquidityMap instance
    - `test_observe_node_liquidity_map_none_when_no_candles` — no candles_by_tf in message → liquidity_map=None
    - `test_observe_node_liquidity_map_respected_on_stale_rejection` — stale setup → liquidity_map not set
    - `test_agent_state_has_liquidity_map_field` — AgentState model has liquidity_map: Optional[LiquidityMap]
    - Confirm all tests FAIL (RED)
  - **160b. GREEN — Write minimal implementation**
    - Update `agent/state.py`: add `liquidity_map: Optional["LiquidityMap"] = None` field with forward ref
    - Update `agent/nodes/observe_node.py`:
      - Accept optional `candles_by_tf: Dict[str, List[dict]]` in message
      - Deserialise candles to `Dict[Timeframe, List[Candle]]`
      - Call `LiquidityMappingEngine().analyze(candles_by_tf, instrument, timestamp)`
      - Store result on `state.liquidity_map`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_
  - **160c. REFACTOR** — `liquidity_engine` has no dependency on `agent/*` (verified: none of its
    modules import from `agent`), so there is no actual cycle to guard against. Used a plain
    top-level `from liquidity_engine.models import LiquidityMap` in `agent/state.py` instead of a
    `TYPE_CHECKING`-only import, which would otherwise leave Pydantic v2 unable to resolve the
    forward reference at schema-build time without an explicit `model_rebuild()`. Confirmed GREEN.

- [x] 161. Final checkpoint — complete liquidity engine test suite and coverage gate
  - Run full backend test suite: `pytest backend/tests/ -v --tb=short`
  - Run coverage: `pytest backend/tests/ -k "liquidity" --cov=liquidity_engine --cov-report=term-missing`
  - Assert ≥ 90% line coverage across the `liquidity_engine/` package (_Requirement 14.7_)
  - Assert zero regressions in existing passing tests
  - Ask the user if any failures arise before proceeding
  - **Note**: 7 pre-existing test modules (`test_auth_service.py`, `test_calendar_ingestion.py`,
    `test_candle_builder.py`, `test_kafka_producer.py`, `test_notification_service.py`,
    `test_shadow_period.py`, `test_timescaledb_writer.py`) fail to collect for reasons unrelated to
    this spec (external service/DB dependencies). Not touched by tasks 157–162; run with
    `--continue-on-collection-errors` to get a full picture around them.

- [x]* 162. Optional: Implement `services/liquidity/` FastAPI + Kafka microservice wrapper
  - **162a. RED — Write failing tests** (`backend/tests/test_liquidity_service.py`)
    - `test_health_endpoint_returns_200`
    - `test_analyze_endpoint_accepts_candles_by_tf_and_returns_liquidity_map`
    - `test_analyze_endpoint_validates_required_timeframes`
    - `test_kafka_consumer_calls_engine_on_market_candles_message`
    - `test_kafka_consumer_publishes_liquidity_map_to_liquidity_analyzed_topic`
    - Confirm all tests FAIL (RED)
  - **162b. GREEN — Write minimal implementation**
    - Create `services/liquidity/__init__.py`
    - Create `services/liquidity/main.py` — FastAPI app with:
      - `GET /health`
      - `POST /analyze` — deserialise candles_by_tf, call `LiquidityMappingEngine.analyze()`, return `LiquidityMap.model_dump()`
    - Create `services/liquidity/kafka_consumer.py` — consume `market.candles` → analyze → publish to `liquidity.analyzed`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 12.1, 12.3, 12.4, 14.1, 14.2_
  - **162c. REFACTOR** — confirm GREEN

---

## Update 2026-10: Setup Sequence, Protected-Swing Stop, Counter-Trend Cap (tasks 227–233)

Requirements 13.4, 13.5, 18 and 19; design section "Update 2026-10"; decisions LE-D1 to LE-D8.
- Numbered after algo-backtester task 226.
- Each task that changes engine output regenerates, in its own commit:
  - the engine-window fixtures (`UPDATE_ENGINE_WINDOWS=1 pytest tests/test_liquidity_engine_perf.py`);
  - the golden journal (`UPDATE_GOLDEN=1 pytest tests/test_backtest_golden.py`).

- [x] 227. Spec update 2026-10
  - requirements.md: 1.5, 9.5, 9.8, 9.12, 13.4 and 13.5 amended. New Requirements 18 and 19, Properties 29–34, decisions LE-D1 to LE-D8, and the deferred list.
  - design.md: section "Update 2026-10".
  - The user decided the rules on 2026-10-02 and answered the open questions on 2026-10-07: the sweep is a gate; all pools can be raided; no fixed raid window; SD targets at 2–2.5 SD.

- [x] 228. Mark swept levels; draw on liquidity from untouched pools (Req 13.5, Property 34)
  - **Done 2026-10-07, committed with task 230.** `_mark_swept_levels` uses bisect per timeframe and stops at the earliest breach.
  - **Lands together with task 230 (one commit).** On its own it leaves the old sweep check (the draw on liquidity already traded through) unable ever to fire. The golden week then has no orders at all until 230 replaces that check.
  - **228a. RED** (`backend/tests/test_liquidity_engine.py`)
    - `test_level_marked_swept_when_later_bar_trades_beyond`
    - `test_level_not_swept_by_bars_of_its_own_period`
    - `test_swept_at_is_earliest_breaching_bar`
    - `test_draw_on_liquidity_never_swept`
    - `test_property_swept_iff_breached` (Property 34)
  - **228b. GREEN**
    - `LiquidityMappingEngine._mark_swept_levels`, run before `_find_draw_on_liquidity`.
    - `UPDATE_ENGINE_WINDOWS` added to `test_liquidity_engine_perf.py`. Re-baseline the fixtures and the golden journal.
  - **228c. REFACTOR**

- [x] 229. `SetupSequenceDetector` (`liquidity_engine/grader/sequence.py`; Req 18.1–18.8, Properties 32, 33)
  - **Done 2026-10-07.**
    - The detector and models are in. The engine records `setup_sequence` between `UnicornDetector` and `SetupGrader`; grading doesn't use it yet, and the golden journal is unchanged.
    - `TIMEFRAME_WEIGHT` in `detectors/external.py` is now public: it weights raids too.
    - The engine-window fixtures were re-baselined for the new field (`UPDATE_ENGINE_WINDOWS`, added to `test_liquidity_engine_perf.py`).
    - About 1 in 6 random walks yields a sequence, so properties 32 and 33 are exercised.
    - **Cost:** +5 to 15 ms per `analyze()` on the four fixture windows (54–88 ms with the detector, against 49–73 ms without). Most of it is the CISD pass over each prefix.
  - **229a. RED** (`backend/tests/test_liquidity_sequence.py`, synthetic candles)
    - `test_raid_reclaim_cisd_then_array_forms_bullish_sequence`
    - `test_bearish_sequence_mirrors`
    - `test_no_sequence_without_reclaim`
    - `test_no_sequence_without_cisd_after_raid`
    - `test_no_sequence_when_array_formed_before_raid`
    - `test_no_sequence_when_protected_swing_broken`
    - `test_pool_taken_before_raid_bar_is_not_raided`
    - `test_swing_is_not_a_pool_until_confirmed` (no lookahead)
    - `test_htf_swing_and_previous_day_low_are_pools`
    - `test_protected_swing_is_extreme_from_raid_to_array`
    - `test_most_recent_raid_wins_then_pool_weight`
    - `test_selection_order_across_arrays`
    - `test_property_no_lookahead` (Property 33)
    - `test_property_raid_integrity` (Property 32)
  - **229b. GREEN**
    - Models: `LiquiditySource.SWING_HIGH` / `SWING_LOW`, `LiquidityPool`, `LiquidityRaid`, `ProtectedSwing`, `SetupSequence`, `LiquidityMap.setup_sequence`.
    - The detector.
    - The engine sets `setup_sequence`; grading is unchanged in this task.
    - Re-baseline the engine-window fixtures (new field). The golden journal is unchanged.
  - **229c. REFACTOR**

- [x] 230. Grade from the setup sequence (Req 9.5, 9.8, 13.4, 18.9–18.16; Properties 29–31)
  - **Done 2026-10-07, together with 228.**
    - **Code:**
      - The grader takes the entry array from the sequence and gates on it.
      - It records the wick and body stops (10% buffer of the protected bar's range) and caps counter-trend setups at B, recorded as `SetupGradeDetail.counter_trend`.
      - The grade reason names the raid, the protected swing, the gate and the cap.
      - The engine sets `sweep_detected = setup_sequence is not None` and projects SD from the setup leg. `_detect_sweep` is removed.
    - **Tests:**
      - `full_liquidity_map` builds a sequence on the strongest entry array unless one is given. The old target-side sweep and array-edge stop tests are rewritten.
      - Property 31 was too strict: a protected bar without range gets no buffer, and wick = body gives equal stops. It now reads ≤, and is strict when the bar has a range.
    - **Re-baselined:**
      - the engine-window fixtures;
      - the golden journal;
      - the pinned runner message (`EURUSD_M5_message.json`, refreshed by `UPDATE_GOLDEN=1`; it encoded the old grader).
    - **Golden week:** 7 orders, against the baseline's sub-spread ones.
      - Stops are 13–79 pips (were 0.6–3.5), and R:R runs 3.3–11 (was always 5.0).
      - A stopped trade costs about −1.005R net (spread about 0.005R).
      - Two counter-trend shorts were capped at B.
  - **230a. RED** (`test_liquidity_grader.py`, `test_liquidity_engine.py`)
    - `test_no_trade_without_setup_sequence`
    - `test_entry_array_is_the_sequence_array`
    - `test_sweep_condition_follows_setup_sequence`
    - `test_stop_behind_protected_swing_wick_with_buffer`
    - `test_body_stop_recorded`
    - `test_stop_placement_valid_requires_stop_beyond_array`
    - `test_counter_trend_capped_at_b`
    - `test_aligned_setup_not_capped`
    - `test_grade_reason_names_raid_and_protected_swing`
    - `test_grade_reason_names_gate_and_cap`
    - `test_sd_projection_anchored_on_setup_leg`
    - `test_sd_projection_none_without_sequence`
    - `test_property_sweep_gate` (Property 29)
    - `test_property_counter_trend_cap` (Property 30)
    - `test_property_protected_swing_ordering` (Property 31)
    - Rewrite the tests built on superseded 9.12 and 13.4.
  - **230b. GREEN** — grader and engine as designed. Re-baseline the fixtures and the golden journal.
  - **230c. REFACTOR**

- [x] 231. Order derivation and report (Req 19)
  - **Done 2026-10-07.**
    - **Code:**
      - `build_order_intent` trades the sequence's direction and takes the stop from `cfg.stop_mode`. A stop not beyond the entry is `NoTrade` `INVALID_STOP`, journaled as its own decision so task 233 can count it.
      - A tradeable grade without a sequence raises: the grader never produces one.
      - `TradeContext` records the raid and the protected swing.
    - **Report:**
      - The M15 chart draws the raided pool (a dotted line from where it formed to the raid) and rings the protected swing's wick.
      - Their labels stack on the entry side, clear of the position tool's labels.
      - A window starts 8 bars before the raid when that is earlier than its usual start.
      - Checked in headless Chrome on the golden week: a SHORT TP and a LONG stop-out.
    - **Re-baselined:**
      - the golden journal: 8 EXECUTE, 17 RR_BELOW_MIN, no INVALID_STOP;
      - the pinned runner message: TP1 is now 2.0 SD, R:R 5.92 (was 7.07).
  - **231a. RED**
    - In `test_backtest_order_intent.py`:
      - `test_stop_mode_wick_uses_suggested_stop`
      - `test_stop_mode_body_uses_body_stop`
      - `test_direction_from_setup_sequence`
      - `test_invalid_stop_is_no_trade`
      - `test_default_tp_levels`
    - Strategy config: `stop_mode` is validated and in the fingerprint; `--variant stop_body` loads from `base.toml`.
    - `test_backtest_signals.py`: `test_trade_context_records_raid_and_protected_swing`.
  - **231b. GREEN**
    - `StrategyConfig.stop_mode` and the `tp_levels` default (2.0, 2.5).
    - `build_order_intent`, and `NoTradeReason` `INVALID_STOP`.
    - `TradeContext.swept_level` / `protected_swing`, and the report draws both.
    - `[variants.stop_body]` in `config/backtests/base.toml`.
    - Re-baseline the golden journal.
  - **231c. REFACTOR** — check the chart in headless Chrome.

- [x] 232. Checkpoint
  - **Done 2026-10-07.**
    - **Suite:** root 844 + 1 flaky, backend 1892. The only failures are the 27 task-39 RED tests and `test_mocked_ensure_collection_completes_under_5ms`, an algorag wall-clock assert that passes 3/3 alone.
    - **Speed:** `analyze()` takes 39–42 ms per M15 window and 45–57 ms per M5 window (median of 30, engine-window fixtures).
      - `SetupSequenceDetector` is 3.5–5.8 ms of that, about 10%.
      - Well within Requirement 1.7's 500 ms. Task 199's 33 ms was per Phase A close on stored data; task 233's run times give the like-for-like figure.
    - **Live impact:** the paper-trader image (built 2026-10-06) bakes in the code. It keeps trading the old grader until the image is rebuilt and the container restarted, which needs the user's OK.
  - Full suite green, apart from the task-39 RED tests.
  - Measure `analyze()` per M15 close on the engine-window fixtures, against task 199's 33 ms.
  - **Live impact:** the paper-trader container runs the new grader only after a restart, which needs the user's OK.

- [x] 233. Measure against the baseline **(user review)**
  - **Done 2026-10-08.** Write-up: `docs/backtests/SETUP_SEQUENCE.md`.
    - **Result:** both runs fail the pass mark (1 of 5):
      - WICK `ec4876ba87a1`: −0.16R (CI −0.33 to +0.01), PF 0.79, DD 100R;
      - BODY `475491a89d91`: −0.01R (CI −0.20 to +0.18), PF 0.98, DD 44R;
      - baseline: −0.54R, PF 0.45, DD 117R.
    - **Fixed:** costs 1.14R → 0.07/0.14R; fills 15% → 55%; no sub-spread stops in WICK.
    - **Where it loses:** R:R 10+ (3% hit rate in both runs) and counter-trend setups.
    - **Alignment:** only today's D1 candle separates results; BOS/CHoCH structure alignment doesn't.
    - **Gaps:** BODY needs a minimum stop (10 sub-spread trades, −19R); swap isn't modelled.
    - **Next variants proposed** in the write-up.
    - **User review of the two reports:** requested 2026-10-08.
  - Run `config/backtests/base.toml` (stop `WICK`) and `--variant stop_body` on study `baseline-2026q3`. Compare each with the baseline run `5d241691c701`.
  - Write `docs/backtests/SETUP_SEQUENCE.md` with:
    - the pass-mark table per run;
    - counts: gated, `RR_BELOW_MIN`, `INVALID_STOP`, never filled;
    - stops against the spread;
    - observations.
  - The user reviews trades in `report.html`.

---

## Update 2026-10b: Candle Anticipation (tasks 234–243)

Requirements 20–25; design section "Update 2026-10b"; decisions LE-D9 to LE-D15.
- Numbered after task 233.
- Each task that changes engine output regenerates, in its own commit, the engine-window fixtures and the golden journal (as in tasks 227–233).
- Tasks 238 and 240 also change algo-backtester code (the journal decisions, the fill model and the instrument specs). They are tracked here because this update's measurement depends on them.

- [x] 234. Spec update 2026-10b
  - requirements.md: Requirements 20–25, Properties 35–39, decisions LE-D9 to LE-D15, deferred list.
  - design.md: section "Update 2026-10b", with the hindsight diagnostic and the market-timing statistics.
  - The user described the method on 2026-10-08:
    - anticipate how the next candle forms; a bullish candle makes its false move lower first;
    - two objectives: liquidity and inefficiencies; nearest is realistic, further only when trending;
    - time anchors: the 01:00, 05:00 and 09:00 H4 candles, New York time, the 17:00 open blended with midnight;
    - the Asian range raid;
    - H1, M30 and M15 liquidity.
  - LE-D15 (the trend definition) confirmed by the user on 2026-10-08.
  - LE-D16 added the same day: swap belongs to the account. The user may run swap and swap-free accounts at once.

- [x] 235. Intraday timeframes and Asian pools (Req 20; Property 39)
  - **Done 2026-10-08.**
    - `context_tfs` adds H1, M30 and M15; `timeframes` lists each once.
    - The M30 window is 100 bars, not 200: about 50 hours, M15's span. The golden week has no native M30 for a longer warm-up. Req 20.1 amended.
    - Asian pools come from the current day's 20:00–23:00 New York H1 bars, known at midnight. The engine passes the analysis time to `SetupSequenceDetector`.
    - **Golden journal:** the same decisions (8 EXECUTE, 17 RR_BELOW_MIN); reasons now name H1 raids. The engine windows are unchanged (they have no H1).
    - **Speed (235c):** per M15 close on the golden week, 35 ms went to 109 ms with the new timeframes. Output-preserving speedups bring it to about 60 ms (old timeframes: 26 ms):
      - cached uuid5 ids;
      - bisect starts for the break, fill and violation scans;
      - faster swing finders;
      - unicorn pairs grouped by timeframe;
      - raids sorted once.
  - **235a. RED**
    - `test_backtest_strategy_config.py`: the defaults include H1, M30 and M15 with their counts; `timeframes` has no duplicates.
    - `test_liquidity_sequence.py`:
      - Asian pools come from the 20:00–23:00 New York H1 bars, known at 00:00;
      - there are none before 00:00 (Property 39);
      - none when the session has no bars;
      - an `ASIA_LOW` raid can start a bullish sequence.
  - **235b. GREEN** — the config defaults, the `LiquiditySource` values and the pools.
    - Re-baseline the engine windows and the golden journal.
  - **235c. REFACTOR** — measure `analyze()` per M15 close with the extra timeframes.

- [ ] 236. CandleProfileAnalyzer: frame, objectives, trend, anticipation (Req 21; Properties 35, 36)
  - **236a. RED** (`test_liquidity_profile.py`):
    - **Frame:** `frame_open` and `midnight_open`.
    - **Objectives:**
      - untaken pools and unfilled FVGs only, from bars before the open;
      - the nearest objective on each side, with ties going to the higher timeframe.
    - **Trend:** the W1 closure rule.
    - **Direction:**
      - trending: the trend, with the W1 objective as the draw;
      - not trending: toward the nearer objective;
      - `NEUTRAL` with no objective.
    - **Properties:** 35 (no lookahead: equal at every `t` in the candle) and 36 (ordering) with Hypothesis.
  - **236b. GREEN** — `liquidity_engine/profile/`, the models, and `LiquidityMap.candle_profile`.
    - The engine calls the analyzer after `SetupSequenceDetector`.
  - **236c. REFACTOR**

- [ ] 237. False move, manipulation window, weekday (Req 22)
  - **237a. RED**
    - `false_move_taken`, `asia_raided` and the candle's low and high so far;
    - `in_window` and `raid_in_window` at the window's edges (01:00 and 13:00 New York, DST on both sides);
    - `weekday` on the 17:00 boundary (Sunday 17:00 is Monday).
  - **237b. GREEN**
  - **237c. REFACTOR**

- [ ] 238. Order policy and variants (Req 23; Properties 37, 38)
  - **238a. RED** (`test_backtest_order_intent.py`, `test_backtest_strategy_config.py`, `test_backtest_simulation.py`):
    - **Reasons:** each `NoTrade` reason and the order of the checks.
    - **Targets:** `NEAREST` takes the nearer of SD 2.0 and the draw, and falls back to SD when the draw doesn't lie beyond the entry.
    - **Minimum stop:** `STOP_TOO_TIGHT` with `typical_spread`; `ValueError` without it.
    - **Config:** the new fields are validated and in the fingerprint.
    - **Journal:** each reason gets its own decision.
    - **Properties:** 37 and 38 with Hypothesis.
  - **238b. GREEN**
    - The `StrategyConfig` fields, `build_order_intent`, `NoTradeReason`, and `simulation._decide`.
    - Phase A and the live runner pass `typical_spread`.
    - The `anticipation`, `anticipation_body` and `anticipation_poi` variants in `config/backtests/base.toml`.
  - **238c. REFACTOR**

- [ ] 239. Recording and report (Req 24)
  - **239a. RED** — `TradeContext.candle_profile`, and the report script draws the frame open and the draw.
  - **239b. GREEN**
  - **239c. REFACTOR** — check the chart in headless Chrome.

- [ ] 240. Swap in the cost model (Req 25.1; algo-backtester code)
  - **240a. RED**
    - **Export:** the exporter reads the swap fields; old spec files load with zero swap.
    - **Fill model:** swap is charged per rollover held through, triple on the rollover day, converted to account currency; `cost_r_swap` is in the journal.
    - **Modes:** an unsupported `swap_mode` raises.
    - **Accounts:** a profile with `swap_free = true` loads zero swap (LE-D16).
  - **240b. GREEN**
    - Re-export `config/instruments/exness-standard.toml` from the MT5 terminal, logged in to the swap account (MT5 must be open).
    - Add `config/brokers/exness-standard-swapfree.toml`.
  - **240c. REFACTOR** — re-price `ec4876ba87a1` and `475491a89d91` with swap from the Phase A cache, and note the difference.

- [ ] 241. Checkpoint
  - **Suite:** the full suite is green apart from the task-39 RED tests.
  - **Speed:** `analyze()` time against task 232.
  - **Live impact:** the paper trader's configuration (entry timeframe, instruments) differs from the backtest. Aligning it is a separate decision for the user, and needs a container rebuild.

- [ ] 242. Measure candle anticipation **(user review)**
  - Run `base.toml` (the new reference) and the `anticipation`, `anticipation_body` and `anticipation_poi` variants on study `baseline-2026q3`.
  - Compare each with the reference, `ec4876ba87a1` and `475491a89d91`.
  - Write `docs/backtests/CANDLE_ANTICIPATION.md` with:
    - the pass-mark table;
    - `NoTrade` counts per reason;
    - the breakdowns by weekday and by `midnight_open` side;
    - stops against the spread;
    - swap's share of costs, and each run's result without swap (the swap-free account, LE-D16).
  - The hold-out stays unused. The user reviews the trades in `report.html`.

- [ ] 243. Decide the next step with the user
  - **If a variant passes:** ablations (one rule removed at a time), then the hold-out `--final` run once the user agrees the version is final.
  - **If none passes:** use the breakdowns to choose between the deferred items (lower frames, trade management, premium/discount, the economic calendar).

---

## Task Dependency Graph

The Liquidity Engine tasks follow a strict dependency hierarchy from foundational models to advanced analytics. Dependencies are denoted as `prerequisite → dependent`.

```json
{
  "waves": [
    {
      "name": "Foundation",
      "tasks": ["144", "145"],
      "description": "Core models, utilities, and package structure"
    },
    {
      "name": "Detection Layer",
      "tasks": ["146", "147", "148"],
      "description": "Swing structure, external liquidity, and PD array detection",
      "dependencies": ["Foundation"]
    },
    {
      "name": "Checkpoint 1", 
      "tasks": ["149"],
      "description": "Validate foundation and detection layers",
      "dependencies": ["Foundation", "Detection Layer"]
    },
    {
      "name": "Analytics Layer",
      "tasks": ["150", "151", "152", "153", "154"],
      "description": "CISD, IPDA, fractal model, OTE, and UNICORN analytics",
      "dependencies": ["Foundation"]
    },
    {
      "name": "Grading Layer",
      "tasks": ["155"],
      "description": "Setup quality grading based on all detection outputs",
      "dependencies": ["Detection Layer", "Analytics Layer"]
    },
    {
      "name": "Checkpoint 2",
      "tasks": ["156"], 
      "description": "Validate analytics and grading layers",
      "dependencies": ["Analytics Layer", "Grading Layer"]
    },
    {
      "name": "Engine Integration",
      "tasks": ["157", "158"],
      "description": "Main engine and agent context integration",
      "dependencies": ["Detection Layer", "Analytics Layer", "Grading Layer"]
    },
    {
      "name": "Final Integration",
      "tasks": ["159", "160", "161"],
      "description": "Complete integration with agent system",
      "dependencies": ["Engine Integration"]
    },
    {
      "name": "Optional Service",
      "tasks": ["162"],
      "description": "Optional FastAPI microservice wrapper",
      "dependencies": ["Final Integration"]
    },
    {
      "name": "Setup Sequence Update (2026-10)",
      "tasks": ["227", "228", "229", "230", "231", "232", "233"],
      "description": "Opposite-side raid sequence, protected-swing stop, counter-trend cap; measured against the algo-backtester baseline",
      "dependencies": ["Final Integration"]
    },
    {
      "name": "Candle Anticipation Update (2026-10b)",
      "tasks": ["234", "235", "236", "237", "238", "239", "240", "241", "242", "243"],
      "description": "Power of 3 candle profile: anticipated D1 direction from W1 and the nearest objectives, false move, manipulation window, Asian and intraday pools, swap and minimum stop; measured against the setup-sequence runs",
      "dependencies": ["Setup Sequence Update (2026-10)"]
    }
  ]
}
```

### Core Foundation Layer
```
144 (Models & Scaffold) → 145 (Utils)
```

### Detection Layer  
```
144 (Models) + 145 (Utils) → 146 (Swing Structure)
144 (Models) + 145 (Utils) → 147 (External Liquidity)
144 (Models) + 145 (Utils) + 146 (Swing Structure) → 148 (Internal Arrays)
```

### Checkpoint 1
```
144 + 145 + 146 + 147 + 148 → 149 (Checkpoint)
```

### Analysis Layer
```
144 (Models) + 145 (Utils) → 150 (CISD Detector)
144 (Models) + 145 (Utils) + 150 (CISD) → 151 (IPDA Classifier)
144 (Models) + 145 (Utils) → 152 (Fractal Model)
144 (Models) + 145 (Utils) → 153 (OTE Calculator)
144 (Models) + 145 (Utils) + 148 (PD Arrays) → 154 (Unicorn Detector)
```

### Grading Layer
```
144 (Models) + 147 (External) + 148 (Internal) + 151 (IPDA) + 153 (OTE) + 154 (Unicorn) → 155 (Setup Grader)
```

### Checkpoint 2
```
150 + 151 + 152 + 153 + 154 + 155 → 156 (Checkpoint)
```

### Engine Integration Layer
```
All Detection & Analysis Tasks (144-155) → 157 (Main Engine)
144 (Models) + 157 (Engine) → 158 (Agent Context & HTF Bias)
```

### Final Integration
```
157 + 158 → 159 (Engine Checkpoint)
144 (Models) + 159 (Complete Engine) → 160 (Agent Integration)
160 → 161 (Final Checkpoint)
161 → 162 (Optional Service)
```

### Dependency Summary by Phase

**Phase 1 - Foundation (Tasks 144-149)**
- 144: Base models and package structure (no dependencies)
- 145: Time and candle utilities (requires 144)
- 146: Swing structure classification (requires 144 + 145)
- 147: External liquidity detection (requires 144 + 145)
- 148: Internal PD array detection (requires 144 + 145 + 146)
- 149: Checkpoint for foundation layer

**Phase 2 - Analytics (Tasks 150-156)**
- 150: CISD detection (requires 144 + 145)
- 151: IPDA classification (requires 144 + 145 + 150)
- 152: Fractal model tracking (requires 144 + 145)
- 153: OTE calculations (requires 144 + 145)
- 154: UNICORN pattern detection (requires 144 + 145 + 148)
- 155: Setup grading (requires all detection tasks 147, 148, 151, 153, 154)
- 156: Checkpoint for analytics layer

**Phase 3 - Engine (Tasks 157-162)**
- 157: Main liquidity engine (requires all tasks 144-155)
- 158: Agent context formatting (requires 144 + 157)
- 159: Engine integration checkpoint
- 160: Agent node integration (requires complete engine)
- 161: Final validation checkpoint
- 162: Optional microservice wrapper

### Critical Path
The longest dependency chain is:
`144 → 145 → 146 → 148 → 154 → 155 → 157 → 158 → 159 → 160 → 161`

### Parallel Execution Opportunities
Tasks that can run in parallel after their prerequisites:
- **After 144+145**: Tasks 146, 147, 150, 152, 153 can run in parallel
- **After 148**: Task 154 can start while other analysis tasks continue
- **After 150**: Task 151 can start
- **After all detection tasks**: Task 155 depends on multiple outputs

### Testing Dependencies
Each checkpoint task has specific test dependencies:
- Task 149: Tests for tasks 144-148
- Task 156: Tests for tasks 150-155  
- Task 159: Tests for tasks 157-158
- Task 161: Full integration tests

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery.
- Every implementation task follows RED → GREEN → REFACTOR. No production code without a failing test first.
- Hypothesis PBT tasks (`property_*`) run with `@settings(max_examples=100)` minimum.
- Tests in `backend/tests/` — all file names prefixed `test_liquidity_`.
- The `liquidity_engine/` package must have zero I/O side effects: no file reads, no DB calls, no network calls during `analyze()` (_Requirement 14.1_).
- The package must use only dependencies already in `requirements.txt` — Pydantic v2 and stdlib only (_Requirement 14.2_).
- `SwingStructureClassifier` (task 146) and `FractalModelTracker` (task 152) are new components added after cross-checking this spec against the TTrades reference decks (`Basic-/Advanced-Market-Structure`, `Candle-2-/Candle-2-Closure-/Candle-3-Closure-TTrades`). They are additive: no existing detector's classification timing changes, only new fields (`structure_confirmed` on `PDArray`) and new `LiquidityMap` sections (`swing_structure`, `fractal_model`).
- SMT (Smart Money Divergence) was identified during that same review and deliberately excluded — see `requirements.md` → Non-Goals. Do not add it ad hoc to any task above; it requires a multi-instrument signature change and belongs in its own follow-on spec.
- After task 161 passes, the engine is production-ready for integration into the main observe_node loop.
