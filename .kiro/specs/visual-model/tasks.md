# Implementation Plan:

**spec**: Visual Model (ICT Chart Perception Layer)

## Overview

`services/visual_model/` — a new FastAPI microservice giving the agent a second, VLM-based read on graded setups, plus five small edits to the existing `agent/` package to wire it in. Tasks are numbered starting from **163**, continuing the platform task sequence from where `.kiro/specs/liquidity-engine/tasks.md` left off (144–162). Every implementation task follows the strict **RED → GREEN → REFACTOR** TDD cycle used throughout this platform. Sub-tasks are ordered: **(a) RED** — write failing tests, **(b) GREEN** — write minimal implementation, **(c) REFACTOR** — clean up and confirm GREEN.

New service tests live in `services/visual_model/tests/`. Edits to existing `agent/` files are tested in `backend/tests/` following the platform convention (matching where `agent/nodes/*` tests already live). The real Claude vision API and the real Anthropic SDK are never called in any test in this plan — `vlm_reasoner` is always exercised against a mocked client.

**Companion documents**: `design.md` (architecture, components, data models), `requirements.md` (acceptance criteria and correctness properties referenced below).

---

## Tasks

- [x] 163. Scaffold `services/visual_model/` package and `VisualAnalysis` schemas
  - **163a. RED — Write failing tests** (`services/visual_model/tests/test_schemas.py`)
    - `test_visual_analysis_valid_construction` — full `VisualAnalysis` instantiates given all sections
    - `test_crt_phase_literal_rejects_reversal` — `CRTPhaseLiteral` has no `REVERSAL`/`RETRACEMENT` value; constructing with one raises
    - `test_crt_phase_literal_five_values` — exactly `{C1_ACCUMULATION, C2_MANIPULATION, C3_DISTRIBUTION, C4_CONTINUATION, UNKNOWN}`
    - `test_structure_section_uses_choch_not_mss` — `StructureSection` has `h1_choch_visible`/`h1_choch_description` fields; no `mss` field exists anywhere on the model
    - `test_score_fields_reject_out_of_range` — `structure_clarity_score`/`coherence_score`/`overall_score`/`visual_dominance` > 10.0 or < 0.0 raise `ValidationError`
    - `test_visual_analysis_response_defaults` — `VisualAnalysisResponse(analysis=None, visual_modifier=0.0, hard_block_reason=None)` defaults `degraded=False`
    - Confirm all tests FAIL (RED)
  - **163b. GREEN — Write minimal implementation**
    - Create `services/visual_model/__init__.py`, `config.py`, `requirements.txt`
    - Create `schemas/__init__.py`, `schemas/visual_analysis.py` — `CRTPhaseLiteral`, `StructureSection`, `DealingRangeSection`, `CRTSection`, `DisplacementCandle`, `OrderBlockRead`, `IFVGRead`, `CISDSection`, `M5PrecisionSection`, `FractalSection`, `QualitySection`, `VisualInsightsSection`, `VisualAnalysis` (all Pydantic v2, `Field(ge=0.0, le=10.0)` on score fields)
    - Create `schemas/chart_input.py` — `ChartAnalysisRequest`
    - Create `api/__init__.py`, `api/schemas.py` — `VisualAnalysisResponse`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  - **163c. REFACTOR** — extract shared `Literal` types to avoid duplication between `schemas/visual_analysis.py` and `api/schemas.py`; confirm GREEN

- [x] 164. Implement `renderer/chart_renderer.py` — single-timeframe rendering
  - **164a. RED — Write failing tests** (`services/visual_model/tests/test_renderer.py`)
    - `test_render_single_timeframe_returns_512x512_png` — output dimensions and format
    - `test_render_requires_exactly_60_candles` — raises on candle count mismatch
    - `test_render_uses_dark_background_and_candle_colours` — pixel-sample assertions against `#0a0a0f`/`#00e676`/`#ff3d57`
    - `test_render_no_price_labels_or_volume` — structural assertion (no axis-label render call made)
    - `test_render_highlight_index_draws_gold_border`
    - **PBT — `property_render_determinism`** (`@given` random valid 60-candle sequences)
      - **Property 1: Chart Rendering Determinism** — two renders of identical input are byte-identical
      - **Validates: Requirements 1.6**
    - Confirm all tests FAIL (RED)
  - **164b. GREEN — Write minimal implementation**
    - Create `renderer/__init__.py`, `renderer/styles.py` (colour/size constants), `renderer/chart_renderer.py` — `render_single_timeframe()`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - **164c. REFACTOR** — confirm no network/file/db calls anywhere in the render path (grep-based check in test suite); confirm GREEN

- [x] 165. Implement `renderer/multi_tf_renderer.py` and `renderer/annotation_renderer.py`
  - **165a. RED — Write failing tests** (`services/visual_model/tests/test_renderer.py`, extended)
    - `test_grid_layout_h4_top_left_h1_top_right_m15_bottom_left_m5_bottom_right`
    - `test_grid_raises_valueerror_on_missing_timeframe`
    - `test_grid_1024x1024_output`
    - `test_annotations_derive_from_liquidity_map_not_redetected` — mock `LiquidityMap`, assert no independent PDArray/CISD detection logic runs
    - `test_ob_zone_rendered_as_semi_transparent_rect`
    - `test_fvg_dotted_ifvg_hatched_distinct_styles`
    - `test_bsl_ssl_distinct_dashed_line_colours`
    - `test_cisd_candle_gold_border_at_violation_time`
    - **PBT — `property_grid_render_determinism`**
      - **Property 1: Chart Rendering Determinism** (grid variant)
      - **Validates: Requirements 2.4**
    - Confirm all tests FAIL (RED)
  - **165b. GREEN — Write minimal implementation**
    - Create `renderer/multi_tf_renderer.py` — `render_multi_timeframe_grid()`
    - Create `renderer/annotation_renderer.py` — `build_annotations()`, `ICTAnnotations` dataclass
    - Confirm all tests PASS (GREEN)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_
  - **165c. REFACTOR** — confirm GREEN

- [x] 166. Checkpoint — run full renderer test suite; ensure tasks 164–165 are GREEN

- [x] 167. Implement `perception/prompt_builder.py`
  - **167a. RED — Write failing tests** (`services/visual_model/tests/test_prompt_builder.py`)
    - `test_system_prompt_injects_instrument_timestamp_session_killzone`
    - `test_user_prompt_asks_about_bos_and_choch` — string contains "BOS", "CHoCH"; does NOT contain "MSS"
    - `test_user_prompt_crt_phase_options_are_five_values` — asserts the five `CRTPhaseLiteral` values appear as the offered classification options; asserts `REVERSAL`/`RETRACEMENT`/`AMD` do not appear
    - `test_user_prompt_requests_json_only_no_preamble`
    - `test_user_prompt_instructs_visual_only_no_inference`
    - Confirm all tests FAIL (RED)
  - **167b. GREEN — Write minimal implementation**
    - Create `perception/__init__.py`, `perception/prompt_builder.py` — `build_system_prompt()`, `build_user_prompt()`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - **167c. REFACTOR** — confirm GREEN

- [x] 168. Implement `perception/vlm_reasoner.py`
  - **168a. RED — Write failing tests** (`services/visual_model/tests/test_vlm_reasoner.py`, Anthropic client mocked throughout)
    - `test_analyse_returns_parsed_visual_analysis_on_valid_json`
    - `test_analyse_retries_once_on_invalid_json`
    - `test_analyse_raises_vlm_analysis_error_after_second_invalid_json`
    - `test_configured_model_is_a_real_current_model_id` — asserts `VISION_MODEL_PRIMARY`/`VISION_MODEL_FALLBACK` are non-empty strings matching the currently-supported Claude model id pattern, not a placeholder/fictional id
    - `test_cache_hit_skips_second_vlm_call` — same `(chart_png, instrument, timestamp)` within TTL calls mocked client exactly once
    - `test_cache_miss_on_different_chart_hash`
    - `test_redis_unavailable_falls_back_to_direct_call` — mocked Redis raising ConnectionError still returns a valid result
    - `test_logs_token_counts_and_model_per_call`
    - Confirm all tests FAIL (RED)
  - **168b. GREEN — Write minimal implementation**
    - Create `perception/vlm_reasoner.py` — `VISION_MODEL_PRIMARY`, `VISION_MODEL_FALLBACK` constants (mirroring `services/nlp/llm_service.py`'s `CLAUDE_MODEL` pattern), `VLMReasoner`, `VLMAnalysisError`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_
  - **168c. REFACTOR** — confirm GREEN

- [x] 169. Implement `fusion/visual_modifier.py`
  - **169a. RED — Write failing tests** (`services/visual_model/tests/test_visual_modifier.py`)
    - `test_visual_composite_formula` — weighted 0.5/0.3/0.2 combination
    - `test_modifier_formula_and_clamping`
    - **PBT — `property_modifier_bounds`** (`@given` random valid `VisualAnalysis`)
      - **Property 2: Visual Modifier Bounds** — modifier always in `[-0.15, 0.15]`
      - **Validates: Requirement 7.6**
    - `test_direction_conflict_returns_hard_block_reason`
    - `test_no_direction_conflict_when_visual_direction_none`
    - `test_c2_manipulation_returns_hard_block_reason`
    - `test_no_hard_block_when_neither_condition_met_returns_zero_none`
    - `test_never_raises_on_any_structurally_valid_input` — fuzz-style test over the full `VisualAnalysis` field space
    - Confirm all tests FAIL (RED)
  - **169b. GREEN — Write minimal implementation**
    - Create `fusion/__init__.py`, `fusion/visual_modifier.py` — `compute_visual_modifier()`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
  - **169c. REFACTOR** — confirm GREEN

- [x] 170. Implement `api/router.py`, `main.py`, and degraded-mode handling
  - **170a. RED — Write failing tests** (`services/visual_model/tests/test_router.py`, FastAPI `TestClient`, VLM/renderer mocked)
    - `test_post_visual_analyse_happy_path_returns_200_with_modifier`
    - `test_post_visual_analyse_render_valueerror_returns_degraded_200` — missing timeframe in request
    - `test_post_visual_analyse_vlm_analysis_error_returns_degraded_200`
    - `test_post_visual_analyse_never_returns_5xx_on_internal_failure`
    - `test_post_visual_render_returns_base64_png`
    - `test_get_visual_health_reports_model_and_cache_status`
    - `test_analyse_endpoint_completes_under_8s_with_mocked_vlm_latency`
    - Confirm all tests FAIL (RED)
  - **170b. GREEN — Write minimal implementation**
    - Create `api/router.py` — `POST /visual/analyse`, `POST /visual/render`, `GET /visual/health`; wraps renderer + `VLMReasoner` + `compute_visual_modifier()`; catches all internal exceptions into `degraded=True` responses
    - Create `main.py` — FastAPI app assembly
    - Confirm all tests PASS (GREEN)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - **170c. REFACTOR** — confirm GREEN

- [x] 171. Implement `training/data_pipeline.py`
  - **171a. RED — Write failing tests** (`services/visual_model/tests/test_data_pipeline.py`, S3 client mocked)
    - `test_store_training_sample_uploads_png_and_metadata`
    - `test_store_training_sample_runs_after_response_sent` — asserts call ordering in `api/router.py`'s handler (fire-and-forget, not awaited inline)
    - `test_store_training_sample_never_called_on_degraded_response`
    - `test_data_pipeline_has_no_embedding_or_training_calls` — static assertion: module imports no ML/embedding libraries
    - Confirm all tests FAIL (RED)
  - **171b. GREEN — Write minimal implementation**
    - Create `training/__init__.py`, `training/data_pipeline.py` — `store_training_sample()`
    - Wire fire-and-forget call into `api/router.py`'s `/visual/analyse` handler (background task, after response construction)
    - Confirm all tests PASS (GREEN)
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
  - **171c. REFACTOR** — confirm GREEN

- [x] 172. Checkpoint — run full `services/visual_model/` test suite; ensure tasks 163–171 are GREEN; confirm zero real network/API calls anywhere in the suite

- [x] 173. Extend `AgentState` with candle window and visual-analysis fields
  - **173a. RED — Write failing tests** (`backend/tests/test_agent_state_visual_fields.py`)
    - `test_agent_state_candles_by_tf_optional_defaults_none`
    - `test_agent_state_visual_analysis_optional_defaults_none`
    - `test_agent_state_visual_modifier_optional_defaults_none`
    - `test_agent_state_visual_hard_block_reason_optional_defaults_none`
    - `test_agent_state_visual_narrative_optional_defaults_none`
    - `test_agent_state_construction_unaffected_for_existing_callers` — an `AgentState` built with only the pre-existing required fields still constructs without error (regression guard)
    - Confirm all tests FAIL (RED)
  - **173b. GREEN — Write minimal implementation**
    - Edit `agent/state.py` — add `candles_by_tf: Optional[Dict[str, List[Candle]]] = None`, `visual_analysis: Optional[VisualAnalysis] = None`, `visual_modifier: Optional[float] = None`, `visual_hard_block_reason: Optional[str] = None`, `visual_narrative: Optional[str] = None`
    - Confirm all tests PASS (GREEN)
    - _Requirements: 8.5_
  - **173c. REFACTOR** — confirm GREEN

- [x] 174. Update `observe_node.py` to retain `candles_by_tf` on state
  - **174a. RED — Write failing tests** (`backend/tests/test_observe_node.py`, extended)
    - `test_observe_node_stores_candles_by_tf_on_state_when_present`
    - `test_observe_node_candles_by_tf_none_when_message_lacks_candle_data`
    - `test_observe_node_liquidity_map_computation_unchanged` — regression: existing `_build_liquidity_map` behaviour and timing untouched
    - Confirm all tests FAIL (RED)
  - **174b. GREEN — Write minimal implementation**
    - Edit `agent/nodes/observe_node.py` — after `_build_liquidity_map()` parses `candles_by_tf`, also assign it to `state.candles_by_tf` instead of letting it fall out of scope
    - Confirm all tests PASS (GREEN)
    - _Requirements: 13.5_
  - **174c. REFACTOR** — confirm GREEN

- [ ] 175. Update `analyse_node.py` — grade-gated visual-model call and confidence fusion
  - **175a. RED — Write failing tests** (`backend/tests/test_analyse_node.py`, extended; `visual_model_client` mocked)
    - `test_analyse_node_calls_visual_client_when_grade_b_or_better`
    - `test_analyse_node_skips_visual_client_when_grade_no_trade`
    - `test_analyse_node_skips_visual_client_when_setup_grade_none`
    - `test_analyse_node_skips_visual_client_when_candles_by_tf_none`
    - `test_analyse_node_folds_visual_modifier_into_final_confidence`
    - `test_analyse_node_stores_visual_fields_on_state`
    - **PBT — `property_final_confidence_clamped`** (`@given` random valid bonus/modifier combinations)
      - **Property 3: final_confidence Remains Clamped**
      - **Validates: Requirement 8.4**
    - **PBT — `property_visual_gate_only_on_graded_setups`**
      - **Property 9: Visual Model Only Runs on Graded Setups**
      - **Validates: Requirement 8.2**
    - Confirm all tests FAIL (RED)
  - **175b. GREEN — Write minimal implementation**
    - Edit `agent/nodes/analyse_node.py` — add `visual_model_client` call gated on `setup_grade.grade in {B, A, A_PLUS}` and `candles_by_tf is not None`; compute `final_confidence` including `visual_modifier`
    - Create `agent/visual_model_client.py` (or extend an existing HTTP client module) — thin async wrapper around `POST /visual/analyse`, catching connection errors into a degraded local result (never raises to the caller)
    - Confirm all tests PASS (GREEN)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 12.1_
  - **175c. REFACTOR** — confirm GREEN

- [ ] 176. Update `decide_node.py` — visual hard-block gate
  - **176a. RED — Write failing tests** (`backend/tests/test_decide_node.py`, extended)
    - `test_decide_node_skips_on_visual_hard_block_reason_regardless_of_confidence`
    - `test_decide_node_hard_block_check_after_calendar_before_threshold` — ordering assertion
    - `test_decide_node_unaffected_when_hard_block_reason_none`
    - `test_decide_node_unaffected_when_visual_analysis_none` — visual model never called / degraded
    - **PBT — `property_direction_conflict_always_blocks`**
      - **Property 4: Direction Conflict Always Blocks**
      - **Validates: Requirements 7.3, 9.2**
    - **PBT — `property_manipulation_always_blocks`**
      - **Property 5: Active Manipulation Always Blocks**
      - **Validates: Requirements 7.4, 9.2**
    - Confirm all tests FAIL (RED)
  - **176b. GREEN — Write minimal implementation**
    - Edit `agent/nodes/decide_node.py` — insert `visual_hard_block_reason` check after the existing `calendar_clear` gate and before the confidence-threshold gate
    - Confirm all tests PASS (GREEN)
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - **176c. REFACTOR** — confirm GREEN

- [ ] 177. Checkpoint — full agent integration test; ensure tasks 173–176 are GREEN
  - Run the complete `observe → analyse → decide` path with a mocked `visual_model_client` in three modes: (1) visual model healthy and agrees, (2) visual model healthy and hard-blocks, (3) visual model unreachable — assert decision/final_confidence for each
  - **PBT — `property_absent_visual_model_invisible`**
    - **Property 11: Absent Visual Model Is Behaviourally Invisible**
    - **Validates: Requirement 12.3**

- [ ] 178. Checkpoint — confirm `liquidity_engine` purity is unaffected by this spec
  - Grep-based test asserting no file under `liquidity_engine/` imports from or references `services/visual_model` or `agent.visual_model_client`
  - **PBT — `property_grading_purity_preserved`**
    - **Property 7: Grading Purity Is Preserved**
    - **Validates: Requirement 13.4**
  - Re-run the full `liquidity_engine` test suite from `.kiro/specs/liquidity-engine/tasks.md` unmodified and confirm it is still 100% GREEN

- [ ] 179. Dockerfile and service wiring
  - **179a. GREEN — Write implementation** (infrastructure task, no new business logic — RED/GREEN split not applicable)
    - Create `services/visual_model/Dockerfile`, mirroring `services/liquidity/Dockerfile`'s pattern
    - Add `visual-model` service entry to `docker/docker-compose.yml`
    - Document the `ANTHROPIC_API_KEY`, `REDIS_URL`, and S3 bucket environment variables the service requires
  - **179b. REFACTOR** — confirm the service builds and `GET /visual/health` responds inside the compose network

- [ ] 180. Final checkpoint — complete visual-model test suite and coverage gate
  - Run every test created in tasks 163–179
  - Confirm all 12 Correctness Properties from `requirements.md` have at least one passing property-based test exercising them
  - Confirm `services/visual_model/` achieves the same minimum line-coverage bar the platform convention applies elsewhere (see `.kiro/specs/liquidity-engine/requirements.md` Requirement 14.7 for the precedent — 90%)

---

## Task Dependency Graph

The Visual Model tasks follow a strict dependency hierarchy from schemas to rendering/perception/fusion, into the API layer, then into agent wiring and deployment. Dependencies are denoted as `prerequisite → dependent`.

```json
{
  "waves": [
    {
      "name": "Schema Foundation",
      "tasks": ["163"],
      "description": "Package scaffold and VisualAnalysis/response schemas"
    },
    {
      "name": "Rendering Layer",
      "tasks": ["164", "165"],
      "description": "Single-timeframe and multi-timeframe/annotated chart rendering",
      "dependencies": ["Schema Foundation"]
    },
    {
      "name": "Renderer Checkpoint",
      "tasks": ["166"],
      "description": "Validate the rendering layer",
      "dependencies": ["Rendering Layer"]
    },
    {
      "name": "Perception Layer",
      "tasks": ["167", "168"],
      "description": "VLM prompt construction and reasoning client with caching/retries",
      "dependencies": ["Schema Foundation"]
    },
    {
      "name": "Fusion Layer",
      "tasks": ["169"],
      "description": "Visual modifier and hard-block formula",
      "dependencies": ["Schema Foundation"]
    },
    {
      "name": "API & Degraded-Mode Layer",
      "tasks": ["170"],
      "description": "FastAPI router, app assembly, and degraded-mode handling",
      "dependencies": ["Renderer Checkpoint", "Perception Layer", "Fusion Layer"]
    },
    {
      "name": "Training Data Pipeline",
      "tasks": ["171"],
      "description": "Fire-and-forget training sample capture",
      "dependencies": ["API & Degraded-Mode Layer"]
    },
    {
      "name": "Service Checkpoint",
      "tasks": ["172"],
      "description": "Validate the complete services/visual_model/ test suite",
      "dependencies": ["Renderer Checkpoint", "Perception Layer", "Fusion Layer", "API & Degraded-Mode Layer", "Training Data Pipeline"]
    },
    {
      "name": "Agent State Extension",
      "tasks": ["173"],
      "description": "Optional candle-window and visual-analysis fields on AgentState"
    },
    {
      "name": "Observe Node Wiring",
      "tasks": ["174"],
      "description": "Retain candles_by_tf on state",
      "dependencies": ["Agent State Extension"]
    },
    {
      "name": "Analyse Node Integration",
      "tasks": ["175"],
      "description": "Grade-gated visual-model call and confidence fusion",
      "dependencies": ["Agent State Extension", "Observe Node Wiring", "Service Checkpoint"]
    },
    {
      "name": "Decide Node Gate",
      "tasks": ["176"],
      "description": "Visual hard-block gate",
      "dependencies": ["Analyse Node Integration"]
    },
    {
      "name": "Agent Integration Checkpoint",
      "tasks": ["177"],
      "description": "Full observe → analyse → decide integration test",
      "dependencies": ["Decide Node Gate"]
    },
    {
      "name": "Purity Checkpoint",
      "tasks": ["178"],
      "description": "Confirm liquidity_engine purity is unaffected",
      "dependencies": ["Analyse Node Integration"]
    },
    {
      "name": "Deployment",
      "tasks": ["179"],
      "description": "Dockerfile and service wiring",
      "dependencies": ["Service Checkpoint"]
    },
    {
      "name": "Final Checkpoint",
      "tasks": ["180"],
      "description": "Complete suite and coverage gate",
      "dependencies": ["Agent Integration Checkpoint", "Purity Checkpoint", "Deployment"]
    }
  ]
}
```

### Schema Foundation
```
163 (Schemas & Scaffold) → everything below
```

### Rendering Layer
```
163 (Schemas) → 164 (Single-TF Renderer)
163 (Schemas) + 164 (Single-TF Renderer) → 165 (Multi-TF Renderer + Annotations)
164 (Single-TF Renderer) + 165 (Multi-TF Renderer) → 166 (Renderer Checkpoint)
```

### Perception Layer
```
163 (Schemas) → 167 (Prompt Builder)
163 (Schemas) + 167 (Prompt Builder) → 168 (VLM Reasoner)
```

### Fusion Layer
```
163 (Schemas) → 169 (Visual Modifier)
```

### API & Degraded-Mode Layer
```
166 (Renderer Checkpoint) + 168 (VLM Reasoner) + 169 (Visual Modifier) → 170 (Router & Degraded Mode)
170 (Router) → 171 (Training Data Pipeline)
166 + 168 + 169 + 170 + 171 → 172 (Service Checkpoint)
```

### Agent Integration Layer
```
173 (AgentState Fields) → 174 (Observe Node)
173 (AgentState Fields) + 174 (Observe Node) + 172 (Service Checkpoint) → 175 (Analyse Node + visual_model_client)
175 (Analyse Node) → 176 (Decide Node Gate)
176 (Decide Node) → 177 (Agent Integration Checkpoint)
175 (Analyse Node) → 178 (Liquidity Engine Purity Checkpoint)
```

### Deployment Layer
```
172 (Service Checkpoint) → 179 (Dockerfile & Compose Wiring)
```

### Final Checkpoint
```
177 (Agent Integration Checkpoint) + 178 (Purity Checkpoint) + 179 (Dockerization) → 180 (Final Checkpoint)
```

### Dependency Summary by Phase

**Phase 1 — Service Foundation (Tasks 163–166)**
- 163: Package scaffold and `VisualAnalysis` schemas (no dependencies)
- 164: Single-timeframe chart renderer (requires 163)
- 165: Multi-timeframe grid renderer and ICT annotations (requires 163 + 164)
- 166: Checkpoint for the rendering layer (requires 164 + 165)

**Phase 2 — Reasoning & Fusion (Tasks 167–172)**
- 167: VLM prompt builder (requires 163)
- 168: VLM reasoner with caching and retries (requires 163 + 167)
- 169: Visual modifier fusion formula (requires 163)
- 170: FastAPI router, degraded-mode handling (requires 166 + 168 + 169)
- 171: Training data pipeline (requires 170)
- 172: Checkpoint for the full service (requires 166 + 168 + 169 + 170 + 171)

**Phase 3 — Agent Wiring (Tasks 173–178)**
- 173: `AgentState` field extension (no dependencies; can run in parallel with Phase 1–2)
- 174: `observe_node` `candles_by_tf` wiring (requires 173)
- 175: `analyse_node` visual-model call and confidence fusion (requires 173 + 174 + 172)
- 176: `decide_node` hard-block gate (requires 175)
- 177: Agent integration checkpoint (requires 176)
- 178: `liquidity_engine` purity checkpoint (requires 175)

**Phase 4 — Deployment & Final Validation (Tasks 179–180)**
- 179: Dockerfile and docker-compose wiring (requires 172)
- 180: Final checkpoint — full suite and coverage gate (requires 177 + 178 + 179)

### Critical Path
Two chains tie for longest, both nine tasks, merging at the Service Checkpoint:
```
163 → 164 → 165 → 166 → 172 → 175 → 176 → 177 → 180
163 → 167 → 168 → 170 → 172 → 175 → 176 → 177 → 180
```

### Parallel Execution Opportunities
- **After 163**: Tasks 164, 167, and 169 can start in parallel — rendering, prompt building, and the fusion formula only need the schemas
- **Task 173** (`AgentState` extension) has no dependency on `services/visual_model/` at all and can proceed in parallel with all of Phase 1–2
- **After 172**: Task 179 (Dockerization) can proceed independently of Task 175 (`analyse_node` integration) — both only need the Service Checkpoint
- **After 175**: Tasks 176 (`decide_node` gate) and 178 (purity checkpoint) can run in parallel

### Testing Dependencies
- Task 166: renderer test suite covers tasks 164–165
- Task 172: full `services/visual_model/` suite covers tasks 163–171
- Task 177: agent integration tests cover tasks 173–176 (three-mode mocked `visual_model_client`)
- Task 178: grep-based purity check plus a full re-run of the `.kiro/specs/liquidity-engine/tasks.md` suite
- Task 180: aggregate run of every test from tasks 163–179, plus the 12 correctness-property confirmation and the coverage gate
