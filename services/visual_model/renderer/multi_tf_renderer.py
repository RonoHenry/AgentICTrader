"""
Composes four single-timeframe renders into the 2x2 grid the VLM prompt
describes: H4 top-left, H1 top-right, M15 bottom-left, M5 bottom-right.

**Validates: Requirements 2.1-2.4 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from PIL import Image

from pd_array_engine.models import Candle, Timeframe
from services.visual_model.config import settings
from services.visual_model.renderer.chart_renderer import render_single_timeframe
from services.visual_model.renderer.styles import BACKGROUND_COLOR

if TYPE_CHECKING:  # pragma: no cover
    from services.visual_model.renderer.annotation_renderer import ICTAnnotations

# Fixed grid layout - matches the VLM prompt's description of the image
# (perception/prompt_builder.py). Changing this mapping means changing the
# prompt too.
_GRID_TIMEFRAMES = (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)


def render_multi_timeframe_grid(
    instrument: str,
    timestamp: datetime,
    candles_by_tf: Dict[Timeframe, List[Candle]],
    annotations_by_tf: Optional[Dict[Timeframe, "ICTAnnotations"]] = None,
) -> bytes:
    missing = [tf for tf in _GRID_TIMEFRAMES if tf not in candles_by_tf]
    if missing:
        raise ValueError(
            "render_multi_timeframe_grid requires H4, H1, M15, and M5 - "
            f"missing: {[tf.value for tf in missing]}"
        )

    annotations_by_tf = annotations_by_tf or {}
    quadrant_px = settings.single_tf_size_px

    positions = {
        Timeframe.H4: (0, 0),
        Timeframe.H1: (quadrant_px, 0),
        Timeframe.M15: (0, quadrant_px),
        Timeframe.M5: (quadrant_px, quadrant_px),
    }

    grid_img = Image.new("RGB", (settings.grid_size_px, settings.grid_size_px), BACKGROUND_COLOR)

    for tf, (x, y) in positions.items():
        quadrant_png = render_single_timeframe(
            candles_by_tf[tf],
            tf,
            annotations=annotations_by_tf.get(tf),
        )
        quadrant_img = Image.open(io.BytesIO(quadrant_png)).convert("RGB")
        grid_img.paste(quadrant_img, (x, y))

    buf = io.BytesIO()
    grid_img.save(buf, format="PNG")
    return buf.getvalue()
