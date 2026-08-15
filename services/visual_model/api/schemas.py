"""
HTTP request/response models for the Visual Model API.

**Validates: Requirements 10.1, 10.5 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from services.visual_model.schemas.visual_analysis import VisualAnalysis


class VisualAnalysisResponse(BaseModel):
    analysis: Optional[VisualAnalysis]
    visual_modifier: float
    hard_block_reason: Optional[str]
    degraded: bool = False


class HealthResponse(BaseModel):
    status: str
    vlm_configured: bool
    cache_available: bool
