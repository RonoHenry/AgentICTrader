# Requirements Document

**Spec**: Visual Model (ICT Chart Perception Layer)

## Introduction

The Visual Model is a new microservice, `services/visual_model/`, that gives the agent a second, independent read on a graded setup by analysing a *rendered chart image* through a Claude vision model, rather than analysing OHLCV numbers. It corroborates or contradicts `pd_array_engine`'s deterministic `SetupGrader` output on things numbers alone struggle to express — whether a displacement candle visually dominates its neighbours, whether an Order Block is ambiguous, whether the chart "looks" clean to a trained eye.

It never replaces `SetupGrader` and never runs inside it. It runs downstream, in `agent/nodes/analyse_node.py`, only for setups that already graded `B` or better, and its output folds into the same `final_confidence` arithmetic `sentiment_bonus`/`calendar_bonus` already contribute to, plus a small set of hard blocks that join `decide_node`'s existing gate stack.

This spec covers **Phase 3 only** — prompt-based reasoning against a general-purpose Claude vision model, zero training data required. Phase 4 (visual embeddings, Visual AlgoRAG) and Phase 5 (fine-tuned ViT) are out of scope; see Non-Goals.

**BRD traceability**: SO-01, SO-03, BR-ML01, BR-ML03, BR-ML04, BR-ML06, BR-AG05.

**Companion document**: `.kiro/specs/visual-model/design.md` (this spec follows the design-first workflow — design.md was authored first; this document translates it into acceptance criteria).

---

## Glossary

Terms already defined in `.kiro/specs/pd-array-engine/requirements.md` are reused as-is and not redefined here: **CISD**, **OB**, **FVG**, **IFVG**, **Breaker**, **BSL/SSL**, **CRT**, **C1/C2/C3/C4**, **BOS**, **CHoCH**, **OTE Zone**, **Killzone**, **SetupGrade**, **SetupGradeDetail**, **HTFBias**, **LiquidityMap**, **Candle**, **Timeframe**, **AgentState**, **observe_node**.

New terms introduced by this spec:

- **VLM**: Vision Language Model — here, a Claude model with vision capability, called via the Anthropic API.
- **Chart Render**: A deterministic PNG produced from `Candle` data, with no price axis labels or volume, so the model perceives shape/pattern rather than memorising price levels.
- **Multi-TF Grid**: The 2×2 chart render composing H4 (top-left), H1 (top-right), M15 (bottom-left), M5 (bottom-right) into one 1024×1024 image — the image actually sent to the VLM.
- **VisualAnalysis**: The structured Pydantic object returned by the VLM reasoner — one section per ICT concept (structure, dealing range, CRT phase, CISD, M5 precision, fractal coherence, quality, visual insights).
- **Visual Modifier**: A float in `[-0.15, 0.15]` derived from `VisualAnalysis`, added to `final_confidence` alongside `sentiment_bonus` and `calendar_bonus`.
- **Hard Block**: A condition detected by the Visual Model that forces `decide_node` to `SKIP` regardless of `final_confidence` — direction conflict or active `C2_MANIPULATION`.
- **Degraded Mode**: The response state (`degraded=True`) `POST /visual/analyse` returns when rendering or the VLM call fails for any reason; the agent proceeds on the numerical score alone.
- **Grade-Gated Invocation**: The rule that the Visual Model is only called for setups already graded `B`, `A`, or `A+` by `SetupGrader` — never for `NO_TRADE`.
- **Training Sample**: A `{chart_png, VisualAnalysis, instrument, timestamp, cisd_id}` record persisted by `training/data_pipeline.py` for later (Phase 4/5) use — collection only, no embedding or training performed by this spec.

---

## Non-Goals (Deferred)

- **AMDX / "X" phase (reversal, retracement)**: `classify_crt_phase()` in `pd_array_engine/ipda/classifier.py` never returns a reversal or retracement phase today — only `C1_ACCUMULATION`/`C2_MANIPULATION`/`C3_DISTRIBUTION`/`C4_CONTINUATION`/`UNKNOWN`. This spec's `VisualAnalysis.crt` section is constrained to that same five-value vocabulary. Formalizing a sixth "X" phase is its own future spec, and would need to land in the numerical classifier first.
- **CLIP-style visual embedder, ViT fine-tuning, Visual AlgoRAG (`visual_algorag/` package)**: Phase 4/5. Requires ≥500 self-generated, VLM-labelled samples before it's worth building — this spec's training pipeline exists to start accumulating that corpus, not to consume it.
- **pgvector**: not used anywhere on this platform (`services/algorag` runs on Qdrant). Not referenced by this spec at all, including in its deferred Phase 4 description.
- **16 instruments / 12 timeframes**: scoped to the 6 instruments actually supported (`EURUSD`, `GBPUSD`, `USDJPY`, `XAUUSD`, `US500`, `US30`) and the 4-timeframe render grid.
- **Modifying `SetupGrader.grade()` or adding a 9th boolean condition to `SetupGradeDetail`**: out of scope. `pd_array_engine` remains pure, synchronous, and untouched.
- **A standalone fusion/decision module independent of `analyse_node`/`decide_node`**: rejected in favour of extending the two existing gate/scoring points.

---

## Requirements

### Requirement 1: Single-Timeframe Chart Rendering

**User Story:** As the Visual Model service, I want to render a single timeframe's candles into a standardised PNG, so that the VLM receives a consistent visual input uncontaminated by price labels or volume that could bias it toward memorising levels instead of reading pattern.

#### Acceptance Criteria

1. THE `chart_renderer.render_single_timeframe()` SHALL accept exactly 60 `Candle` objects for the given timeframe and produce a 512×512 PNG.
2. THE rendered chart SHALL use a dark background (`#0a0a0f`), bullish candle colour `#00e676`, and bearish candle colour `#ff3d57`.
3. THE rendered chart SHALL NOT include price axis labels or volume bars.
4. WHEN `highlight_index` is provided, THE renderer SHALL draw a 2px gold border around the candle at that index.
5. THE `chart_renderer.render_single_timeframe()` SHALL be a pure function with no network, file-system, or database access.
6. FOR any two calls with identical `candles` and `annotations` arguments, THE renderer SHALL produce byte-identical PNG output.

---

### Requirement 2: Multi-Timeframe Grid Rendering

**User Story:** As the Visual Model service, I want to compose four single-timeframe renders into one 2×2 grid, so that the VLM can reason about fractal coherence across H4/H1/M15/M5 in a single call.

#### Acceptance Criteria

1. THE `multi_tf_renderer.render_multi_timeframe_grid()` SHALL produce a 1024×1024 PNG with H4 top-left, H1 top-right, M15 bottom-left, M5 bottom-right.
2. WHEN `candles_by_tf` is missing any of `H4`, `H1`, `M15`, or `M5`, THE renderer SHALL raise `ValueError` before any network call is made.
3. THE renderer SHALL apply a low-opacity timeframe watermark to each quadrant identifying which timeframe it shows.
4. FOR any two calls with identical `candles_by_tf` and `annotations_by_tf` arguments, THE renderer SHALL produce byte-identical PNG output.

---

### Requirement 3: Annotation Overlay Sourced from LiquidityMap

**User Story:** As the Visual Model service, I want chart annotations (OB/FVG/IFVG zones, BSL/SSL levels, the CISD candle) drawn from the already-computed `LiquidityMap`, so that the visual layer orients the VLM's attention without duplicating detection logic or silently diverging from the numerical engine's own output.

#### Acceptance Criteria

1. THE `annotation_renderer.build_annotations()` SHALL derive all overlays from a supplied `LiquidityMap` — it SHALL NOT re-detect PD arrays, liquidity levels, or CISD events independently.
2. THE renderer SHALL draw `PDArrayType.OB` zones as a semi-transparent rectangle bounded by the array's `high`/`low`.
3. THE renderer SHALL draw `PDArrayType.FVG` zones with a dotted border, distinct from `PDArrayType.IFVG` zones (diagonal hatching).
4. THE renderer SHALL draw `LiquidityType.BSL` levels as horizontal dashed lines in one colour and `LiquidityType.SSL` levels in a second, distinct colour.
5. THE renderer SHALL highlight the candle at `CISDResult.violation_candle_time` with a 2px gold border.

---

### Requirement 4: ICT-Specific VLM Prompt Construction

**User Story:** As the Visual Model service, I want a prompt that asks the VLM about the exact ICT vocabulary this codebase already uses, so that its structured output is directly comparable to `pd_array_engine`'s output rather than requiring translation between two different terminologies.

#### Acceptance Criteria

1. THE `prompt_builder.build_user_prompt()` SHALL ask about **BOS** and **CHoCH** on H4 and H1 — it SHALL NOT use the term "MSS" anywhere in the prompt text.
2. THE `prompt_builder.build_user_prompt()` SHALL ask the VLM to classify H4, H1, and M15 phase as exactly one of `C1_ACCUMULATION`, `C2_MANIPULATION`, `C3_DISTRIBUTION`, `C4_CONTINUATION`, or `UNKNOWN` — it SHALL NOT present `REVERSAL`, `RETRACEMENT`, or any AMD-only phase label as a selectable option.
3. THE prompt SHALL request JSON-only output with no preamble or explanation outside the JSON structure, matching the schema in Requirement 6.
4. THE `prompt_builder.build_system_prompt()` SHALL inject `instrument`, `timestamp`, `session`, and `kill_zone` (ACTIVE/INACTIVE) into the system prompt.
5. THE prompt SHALL instruct the VLM to reference only what is visually present in the image and explicitly avoid inferring from outside context.

---

### Requirement 5: VLM Visual Reasoner — Model Invocation, Retry, and Caching

**User Story:** As the Visual Model service, I want a resilient wrapper around the Claude vision call, so that transient model or formatting failures never propagate into the agent loop as a hard error.

#### Acceptance Criteria

1. THE `vlm_reasoner.VLMReasoner` SHALL invoke a currently-available Claude vision-capable model, configured via a named constant (e.g. `VISION_MODEL_PRIMARY`), following the same module-level constant pattern as `services/nlp/llm_service.py`'s `CLAUDE_MODEL`.
2. THE `VLMReasoner` SHALL NOT hardcode a non-existent model identifier; the configured model SHALL be a real, currently available Claude model at time of implementation.
3. WHEN the VLM response fails to parse as valid JSON against the `VisualAnalysis` schema, THE `VLMReasoner` SHALL retry exactly once with an appended instruction to return valid JSON only.
4. WHEN the retry also fails to parse, THE `VLMReasoner` SHALL raise a caught, typed exception (`VLMAnalysisError`) rather than propagating a raw parsing exception.
5. THE `VLMReasoner` SHALL cache successful results in Redis, keyed by a hash of the chart PNG bytes plus `instrument` and `timestamp`, with a 60-second TTL.
6. WHEN Redis is unavailable, THE `VLMReasoner` SHALL proceed to call the VLM directly rather than failing the request.
7. THE `VLMReasoner` SHALL log `input_tokens`, `output_tokens`, and the model name for every call made, whether cached or not.

---

### Requirement 6: Visual Analysis Output Schema

**User Story:** As `analyse_node` and any downstream consumer (Kafka, logging, training pipeline), I want a strictly-typed `VisualAnalysis` object, so that the visual layer's output is as structurally reliable as the numerical engine's.

#### Acceptance Criteria

1. THE `VisualAnalysis` Pydantic model SHALL include a `structure` section with `h4_direction`, `h4_bos_visible`, `h1_direction`, `h1_choch_visible`, and `structure_clarity_score` (0.0–10.0).
2. THE `VisualAnalysis.crt` section SHALL include `h4_phase`, `h1_phase`, `m15_phase` typed as the five-value `CRTPhaseLiteral` enum defined in Requirement 4.2, plus `manipulation_complete: bool`.
3. THE `VisualAnalysis.cisd` section SHALL include `detected: bool`, `direction: Literal["BEARISH","BULLISH","NONE"]`, a `displacement_candle` sub-object (`visual_dominance`, `body_appears_large`, `wicks_minimal`, `closes_beyond_structure`), an `order_block` sub-object (`identifiable`, `ambiguity: Literal["UNAMBIGUOUS","MINOR","SIGNIFICANT"]`), and an `ifvg` sub-object (`visible`, `gap_obvious`, `ce_approximate`).
4. THE `VisualAnalysis.quality` section SHALL include `overall_score` (0.0–10.0), `take_this_trade: bool`, and `conviction_level: Literal["MAXIMUM","HIGH","MEDIUM","LOW","DO_NOT_TAKE"]`.
5. THE `VisualAnalysis.fractal` section SHALL include `coherence_score` (0.0–10.0) and `perceived_depth` (integer, 1–4, corresponding to M15-only through M15+H1+H4+D1).
6. THE `VisualAnalysis.visual_insights` section SHALL include `what_numbers_miss`, `visual_warnings`, and `narrative` — all non-empty strings when `detected = True`.
7. ALL numeric score fields (`structure_clarity_score`, `coherence_score`, `overall_score`, `visual_dominance`) SHALL be constrained to `[0.0, 10.0]` at the schema level (Pydantic field validation), rejecting out-of-range VLM output rather than silently accepting it.

---

### Requirement 7: Visual Modifier and Hard Block Computation

**User Story:** As `analyse_node` and `decide_node`, I want the Visual Model service to hand back a ready-to-use bounded float and an optional block reason, so that neither node needs to replicate ICT-specific scoring logic — they only need to add a number and check a string, exactly as they already do for `sentiment_bonus` and `calendar_clear`.

#### Acceptance Criteria

1. THE `fusion.visual_modifier.compute_visual_modifier()` SHALL compute `visual_composite = quality.overall_score/10 * 0.5 + fractal.coherence_score/10 * 0.3 + structure.structure_clarity_score/10 * 0.2`.
2. THE function SHALL compute `modifier = clamp((visual_composite - 0.5) * 0.30, -0.15, 0.15)`.
3. WHEN `VisualAnalysis.cisd.direction` is not `"NONE"` and differs from the `numerical_direction` argument, THE function SHALL return a non-`None` `hard_block_reason` describing the direction conflict.
4. WHEN `VisualAnalysis.crt.m15_phase == "C2_MANIPULATION"`, THE function SHALL return a non-`None` `hard_block_reason` describing that the lowest timeframe is still in manipulation.
5. THE function SHALL NOT raise for any structurally valid `VisualAnalysis` input — a `VisualAnalysis` that produces no modifier/block condition SHALL return `(0.0, None)`.
6. THE `modifier` return value SHALL always lie within the closed interval `[-0.15, 0.15]`.

---

### Requirement 8: Confidence Fusion Integration (analyse_node)

**User Story:** As the agent's `analyse_node`, I want the visual modifier folded into the same `final_confidence` computation that already applies `sentiment_bonus` and `calendar_bonus`, so that a single, auditable formula produces the final score rather than two competing scoring systems.

#### Acceptance Criteria

1. WHEN `state.liquidity_map.setup_grade.grade` is `B`, `A`, or `A+` AND `state.candles_by_tf` is populated, THE `analyse_node` SHALL call the visual-model client's `/visual/analyse` endpoint.
2. WHEN `state.liquidity_map.setup_grade.grade == NO_TRADE` OR `state.liquidity_map.setup_grade` is `None`, THE `analyse_node` SHALL NOT call the visual-model client.
3. WHEN `state.candles_by_tf` is `None` (message did not carry candle data), THE `analyse_node` SHALL NOT call the visual-model client and SHALL treat `visual_modifier` as `0.0`.
4. THE `analyse_node` SHALL compute `final_confidence = clamp(raw_confidence + sentiment_bonus + calendar_bonus + visual_modifier, 0.0, 1.0)`.
5. THE `analyse_node` SHALL store `visual_analysis`, `visual_modifier`, `visual_hard_block_reason`, and `visual_narrative` on `AgentState` whenever the visual-model client is called, regardless of whether the response is `degraded`.

---

### Requirement 9: Hard Block Gate Integration (decide_node)

**User Story:** As the agent's `decide_node`, I want the visual hard-block check to sit alongside the existing `calendar_clear` gate, so that a visual conflict or an active-manipulation read blocks the trade with the same authority as today's blackout check, before the confidence floor is even evaluated.

#### Acceptance Criteria

1. THE `decide_node` SHALL check `state.visual_hard_block_reason` after the existing `calendar_clear` check and before the confidence-threshold check.
2. WHEN `state.visual_hard_block_reason` is not `None`, THE `decide_node` SHALL set `decision = SKIP` and `decision_reason = state.visual_hard_block_reason`, regardless of `state.final_confidence`.
3. THE hard-block check SHALL NOT alter, bypass, or short-circuit the existing confidence threshold gate (0.65) or the Risk Engine synchronous gate for any setup where `visual_hard_block_reason is None`.
4. WHEN `state.visual_hard_block_reason is None` and `state.visual_analysis is None` (visual model was never called, or was degraded), THE `decide_node` SHALL proceed exactly as it does today — numerical-only decisioning.

---

### Requirement 10: API Endpoints

**User Story:** As the agent's visual-model HTTP client, I want a small, predictable API surface, so that integration is a straightforward request/response call matching the shape already used for the Risk Engine and ML Inference services.

#### Acceptance Criteria

1. THE service SHALL expose `POST /visual/analyse`, accepting `candles_by_tf`, `liquidity_map` (or its relevant fields), `instrument`, and `timestamp`, returning a `VisualAnalysisResponse`.
2. THE service SHALL expose `POST /visual/render`, accepting the same chart inputs, returning a base64-encoded PNG — for dashboard/debugging use, not called by `analyse_node` in normal operation.
3. THE service SHALL expose `GET /visual/health`, returning service status, whether the VLM client is configured, and cache statistics.
4. `POST /visual/analyse` SHALL respond within 8 seconds under normal operation (single VLM call, cache miss).
5. ON any internal failure (render error, VLM error after retry, timeout), `POST /visual/analyse` SHALL return HTTP 200 with `VisualAnalysisResponse(analysis=None, visual_modifier=0.0, hard_block_reason=None, degraded=True)` — it SHALL NOT return an HTTP 5xx for these failure modes.

---

### Requirement 11: Training Data Collection (Self-Generated Only)

**User Story:** As the platform, I want every visual analysis performed on a real setup to be persisted automatically, so that a Phase 4/5 training corpus accumulates from the system's own live activity without manual labelling or any external data source.

#### Acceptance Criteria

1. THE `training.data_pipeline.store_training_sample()` SHALL persist the chart PNG to S3 and record `{s3_key, VisualAnalysis, instrument, timestamp, cisd_id}` for every successful (non-degraded) `/visual/analyse` call.
2. THE storage call SHALL run after the `/visual/analyse` HTTP response has already been sent — it SHALL NOT add latency to the response path.
3. THE `training.data_pipeline` module SHALL NOT compute or store any embedding, and SHALL NOT invoke any model training — those are Phase 4/5, out of scope for this spec.
4. THE only source of training images SHALL be charts rendered from this platform's own OHLCV data at its own detected setups — no externally sourced or scraped images SHALL be ingested by this pipeline.

---

### Requirement 12: Resilience and Degraded-Mode Behaviour

**User Story:** As the platform engineering team, I want the Visual Model to be a strictly additive dependency, so that its failure modes (network, model, formatting) can never stall or break the existing agent loop that operates correctly without it today.

#### Acceptance Criteria

1. WHEN the visual-model service is unreachable (connection refused, DNS failure, timeout), THE `visual_model_client` in `agent/` SHALL catch the exception and treat the call as degraded — `analyse_node` SHALL proceed with `visual_modifier = 0.0` and `visual_hard_block_reason = None`.
2. WHEN `services/visual_model` itself encounters an internal error, IT SHALL return `degraded=True` per Requirement 10.5 rather than raising past its own API boundary.
3. THE `analyse_node` and `decide_node` behaviour when the visual model is fully absent (service down for its entire lifetime) SHALL be identical, field-for-field, to their behaviour before this spec's fields (`visual_analysis`, `visual_modifier`, `visual_hard_block_reason`, `visual_narrative`) existed on `AgentState`.

---

### Requirement 13: Non-Functional Requirements

**User Story:** As the platform engineering team, I want the Visual Model to meet the same engineering standards as the rest of the platform, so that it integrates reliably and remains maintainable.

#### Acceptance Criteria

1. `services/visual_model/` SHALL follow the directory layout defined in `design.md`'s Package Layout section.
2. ALL Pydantic models in `services/visual_model/schemas/` SHALL use Pydantic v2 syntax, consistent with `project-conventions.md`.
3. THE service SHALL target the 6 supported instruments (`EURUSD`, `GBPUSD`, `USDJPY`, `XAUUSD`, `US500`, `US30`) and SHALL NOT assume a larger instrument universe in any hardcoded logic.
4. `pd_array_engine/grader/setup_grader.py`'s `grade()` method SHALL remain unmodified by this spec's implementation — no import of, or call into, `services/visual_model` SHALL appear anywhere in the `pd_array_engine` package.
5. `agent/nodes/observe_node.py` SHALL retain the `candles_by_tf` dict it already parses (currently discarded after building `LiquidityMap`) onto `AgentState.candles_by_tf`, without changing the timing or logic of the existing `LiquidityMappingEngine.analyze()` call.
6. THE Visual Model's Qdrant usage (Phase 4, when built) SHALL target a Qdrant collection, consistent with `services/algorag/config.py`'s existing `QDRANT_COLLECTION` pattern — this requirement exists to prevent a future implementer from reintroducing pgvector.

---

## Correctness Properties

*A property is a characteristic or behaviour that should hold true across all valid executions of a system.*

### Property 1: Chart Rendering Determinism

*For any* `candles_by_tf` input, two calls to `render_multi_timeframe_grid()` with identical arguments SHALL produce byte-identical PNG output.

**Validates: Requirements 1.6, 2.4**

---

### Property 2: Visual Modifier Bounds

*For any* `VisualAnalysis`, `compute_visual_modifier()` SHALL return a `modifier` in `[-0.15, 0.15]`.

**Validates: Requirement 7.6**

---

### Property 3: final_confidence Remains Clamped

*For any* combination of `raw_confidence`, `sentiment_bonus`, `calendar_bonus`, and `visual_modifier`, the `final_confidence` computed in `analyse_node` SHALL lie in `[0.0, 1.0]`.

**Validates: Requirement 8.4**

---

### Property 4: Direction Conflict Always Blocks

*For any* setup where `VisualAnalysis.cisd.direction` is not `"NONE"` and differs from the numerical engine's direction, `decide_node` SHALL set `decision = SKIP` regardless of `final_confidence`.

**Validates: Requirements 7.3, 9.2**

---

### Property 5: Active Manipulation Always Blocks

*For any* setup where `VisualAnalysis.crt.m15_phase == "C2_MANIPULATION"`, `decide_node` SHALL set `decision = SKIP` regardless of `final_confidence`.

**Validates: Requirements 7.4, 9.2**

---

### Property 6: Visual-Model Failure Never Raises Past the API Boundary

*For any* internal failure inside `services/visual_model`, `POST /visual/analyse` SHALL return HTTP 200 with `degraded=True`, never a 5xx.

**Validates: Requirement 10.5**

---

### Property 7: Grading Purity Is Preserved

*For any* `LiquidityMap`, `SetupGrader.grade()`'s output SHALL be identical whether or not `services/visual_model` is running, reachable, or has ever been called.

**Validates: Requirement 13.4**

---

### Property 8: Cache Key Uniqueness

*For any* two distinct `(chart_png, instrument, timestamp)` triples, the Redis cache key SHALL differ; for any identical triple within the 60-second TTL, the Claude API SHALL NOT be called a second time.

**Validates: Requirement 5.5**

---

### Property 9: Visual Model Only Runs on Graded Setups

*For any* `AgentState` where `liquidity_map.setup_grade.grade == NO_TRADE` or `setup_grade` is `None`, `analyse_node` SHALL NOT call the visual-model client.

**Validates: Requirement 8.2**

---

### Property 10: CRT Vocabulary Consistency

*For any* `VisualAnalysis.crt.{h4,h1,m15}_phase`, the value SHALL be one of exactly `{C1_ACCUMULATION, C2_MANIPULATION, C3_DISTRIBUTION, C4_CONTINUATION, UNKNOWN}` — the same five values `classify_crt_phase()` can return.

**Validates: Requirements 4.2, 6.2**

---

### Property 11: Absent Visual Model Is Behaviourally Invisible

*For any* `AgentState` where the visual-model service was never reachable, the resulting `decision`, `decision_reason`, and `final_confidence` SHALL be identical to what `analyse_node`/`decide_node` would have produced before `visual_analysis`/`visual_modifier`/`visual_hard_block_reason` existed on `AgentState`.

**Validates: Requirement 12.3**

---

### Property 12: Training Sample Persistence Never Blocks the Response Path

*For any* successful `/visual/analyse` call, the HTTP response SHALL be sent to the caller before `training.data_pipeline.store_training_sample()` completes.

**Validates: Requirement 11.2**

---

Document: `.kiro/specs/visual-model/requirements.md`
Status: Draft — awaiting tasks.md
