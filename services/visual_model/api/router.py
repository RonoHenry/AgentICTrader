"""
FastAPI endpoints for the Visual Model service.

Governing principle (see .kiro/specs/visual-model/design.md, Error Handling):
nothing this service does can ever turn a would-be NOTIFY/EXECUTE into a hung
request or an unhandled exception for its caller. Every internal failure
degrades to `degraded=True`, HTTP 200 - never a 5xx.

**Validates: Requirements 10.1-10.5 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from liquidity_engine.models import Timeframe
from services.visual_model.api.schemas import HealthResponse, VisualAnalysisResponse
from services.visual_model.fusion.visual_modifier import compute_visual_modifier
from services.visual_model.perception.vlm_reasoner import VLMAnalysisError, VLMReasoner
from services.visual_model.renderer.annotation_renderer import ICTAnnotations, build_annotations
from services.visual_model.renderer.multi_tf_renderer import render_multi_timeframe_grid
from services.visual_model.schemas.chart_input import ChartAnalysisRequest, ChartRenderRequest
from services.visual_model.training.data_pipeline import store_training_sample

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/visual", tags=["visual"])

_vlm_reasoner_singleton: Optional[VLMReasoner] = None


def get_vlm_reasoner() -> VLMReasoner:
    """FastAPI dependency - overridden in tests via app.dependency_overrides."""
    global _vlm_reasoner_singleton
    if _vlm_reasoner_singleton is None:
        _vlm_reasoner_singleton = VLMReasoner(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "")
        )
    return _vlm_reasoner_singleton


def _degraded_response() -> VisualAnalysisResponse:
    return VisualAnalysisResponse(
        analysis=None, visual_modifier=0.0, hard_block_reason=None, degraded=True
    )


def _build_annotations_by_tf(
    candles_by_tf: Dict[Timeframe, list], liquidity_map
) -> Dict[Timeframe, ICTAnnotations]:
    if liquidity_map is None:
        return {}
    return {tf: build_annotations(liquidity_map, tf) for tf in candles_by_tf.keys()}


@router.post("/analyse", response_model=VisualAnalysisResponse)
async def analyse(
    request: ChartAnalysisRequest,
    background_tasks: BackgroundTasks,
    reasoner: VLMReasoner = Depends(get_vlm_reasoner),
) -> VisualAnalysisResponse:
    try:
        annotations_by_tf = _build_annotations_by_tf(request.candles_by_tf, request.liquidity_map)
        chart_png = render_multi_timeframe_grid(
            instrument=request.instrument,
            timestamp=request.timestamp,
            candles_by_tf=request.candles_by_tf,
            annotations_by_tf=annotations_by_tf,
        )
    except ValueError as exc:
        logger.warning("visual/analyse render failure, returning degraded: %s", exc)
        return _degraded_response()

    try:
        analysis = await reasoner.analyse(
            chart_png=chart_png,
            instrument=request.instrument,
            timestamp=request.timestamp,
            session=request.session or "UNKNOWN",
            kill_zone=request.kill_zone or "INACTIVE",
        )
    except VLMAnalysisError as exc:
        logger.warning("visual/analyse VLM failure, returning degraded: %s", exc)
        return _degraded_response()
    except Exception as exc:  # pragma: no cover - defensive: never let an
        # unmodeled failure (timeout, network error, ...) propagate as a 5xx.
        logger.exception("visual/analyse unexpected failure, returning degraded: %s", exc)
        return _degraded_response()

    modifier, hard_block_reason = compute_visual_modifier(
        analysis, numerical_direction=request.numerical_direction
    )

    # Fire-and-forget: Starlette runs background tasks after the response
    # has already been sent - never awaited inline here (Requirement 11.2).
    background_tasks.add_task(
        store_training_sample,
        chart_png,
        analysis,
        request.instrument,
        request.timestamp,
    )

    return VisualAnalysisResponse(
        analysis=analysis,
        visual_modifier=modifier,
        hard_block_reason=hard_block_reason,
        degraded=False,
    )


@router.post("/render")
async def render(request: ChartRenderRequest) -> dict:
    try:
        annotations_by_tf = _build_annotations_by_tf(request.candles_by_tf, request.liquidity_map)
        chart_png = render_multi_timeframe_grid(
            instrument=request.instrument,
            timestamp=request.timestamp,
            candles_by_tf=request.candles_by_tf,
            annotations_by_tf=annotations_by_tf,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"image_b64": base64.b64encode(chart_png).decode("utf-8")}


@router.get("/health", response_model=HealthResponse)
async def health(reasoner: VLMReasoner = Depends(get_vlm_reasoner)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        vlm_configured=reasoner.is_configured,
        cache_available=reasoner.has_cache,
    )
