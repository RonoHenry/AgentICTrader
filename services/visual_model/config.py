"""
Configuration constants for the Visual Model service.

Usage:
    from services.visual_model.config import settings
    settings.vision_model_primary
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class VisualModelSettings:
    # -- VLM models (mirrors services/nlp/llm_service.py's CLAUDE_MODEL constant pattern) --
    vision_model_primary: str = field(
        default_factory=lambda: os.getenv("VISION_MODEL_PRIMARY", "claude-opus-5")
    )
    vision_model_fallback: str = field(
        default_factory=lambda: os.getenv("VISION_MODEL_FALLBACK", "claude-sonnet-5")
    )

    # -- Rendering --
    lookback_candles: int = 60
    single_tf_size_px: int = 512
    grid_size_px: int = 1024
    render_timeframes: tuple = ("H4", "H1", "M15", "M5")

    # -- Fusion --
    visual_modifier_min: float = -0.15
    visual_modifier_max: float = 0.15
    quality_weight: float = 0.5
    fractal_weight: float = 0.3
    structure_weight: float = 0.2

    # -- Caching --
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    cache_ttl_seconds: int = 60

    # -- Storage (training data pipeline) --
    s3_bucket_charts: str = field(
        default_factory=lambda: os.getenv("S3_BUCKET_CHARTS", "agentict-charts")
    )

    # -- API --
    analyse_timeout_seconds: float = 8.0


settings = VisualModelSettings()
