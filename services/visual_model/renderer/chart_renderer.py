"""
Deterministic OHLCV -> PNG rendering for a single timeframe.

Given the same candles and annotations, always produces byte-identical PNG
output (Property 1: Chart Rendering Determinism) - required both for the
Redis cache key (Requirement 5.5) and for Phase 4's future AlgoRAG visual
similarity to be meaningful. No price axis labels, no volume bars: the model
should perceive shape/pattern, not memorise price levels (Requirement 1.3).

Pure function - no network, file-system, or database access anywhere in this
module (Requirement 1.5).

**Validates: Requirements 1.1-1.6 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING, Callable, List, Optional

from PIL import Image, ImageDraw, ImageFont

from pd_array_engine.models import Candle, Timeframe
from services.visual_model.config import settings
from services.visual_model.renderer.styles import (
    BACKGROUND_COLOR,
    BEARISH_COLOR,
    BEARISH_WICK_COLOR,
    BODY_WIDTH_RATIO,
    BULLISH_COLOR,
    BULLISH_WICK_COLOR,
    CANVAS_MARGIN_PX,
    GOLD_COLOR,
)

if TYPE_CHECKING:  # pragma: no cover - type-checking only, avoids a runtime
    # dependency on annotation_renderer.py existing at import time.
    from services.visual_model.renderer.annotation_renderer import ICTAnnotations


def _price_range(candles: List[Candle]) -> tuple:
    price_max = max(c.high for c in candles)
    price_min = min(c.low for c in candles)
    if price_max == price_min:
        price_max += 1e-6
        price_min -= 1e-6
    return price_min, price_max


def _make_price_to_y(price_min: float, price_max: float, size_px: int) -> Callable[[float], float]:
    plot_height = size_px - 2 * CANVAS_MARGIN_PX
    price_range = price_max - price_min

    def price_to_y(price: float) -> float:
        return CANVAS_MARGIN_PX + (price_max - price) / price_range * plot_height

    return price_to_y


def _draw_candles(
    draw: ImageDraw.ImageDraw,
    candles: List[Candle],
    price_to_y: Callable[[float], float],
    size_px: int,
    highlight_index: Optional[int],
) -> None:
    n = len(candles)
    candle_width = size_px / n
    body_half_width = candle_width * BODY_WIDTH_RATIO / 2

    for i, candle in enumerate(candles):
        x_center = i * candle_width + candle_width / 2
        bullish = candle.is_bullish or not candle.is_bearish
        body_color = BULLISH_COLOR if bullish else BEARISH_COLOR
        wick_color = BULLISH_WICK_COLOR if bullish else BEARISH_WICK_COLOR

        y_high = price_to_y(candle.high)
        y_low = price_to_y(candle.low)
        draw.line([(x_center, y_high), (x_center, y_low)], fill=wick_color, width=1)

        y_open = price_to_y(candle.open)
        y_close = price_to_y(candle.close)
        top = min(y_open, y_close)
        bottom = max(y_open, y_close)
        if bottom - top < 1:
            bottom = top + 1
        left = x_center - body_half_width
        right = x_center + body_half_width
        draw.rectangle([left, top, right, bottom], fill=body_color)

        if highlight_index is not None and i == highlight_index:
            draw.rectangle(
                [left - 2, top - 2, right + 2, bottom + 2],
                outline=GOLD_COLOR,
                width=2,
            )


def _draw_watermark(draw: ImageDraw.ImageDraw, label: str, size_px: int) -> None:
    font = ImageFont.load_default()
    text_color = tuple(int(c * 0.5) for c in (255, 255, 255))
    draw.text((size_px - 40, size_px - 18), label, fill=text_color, font=font)


def render_single_timeframe(
    candles: List[Candle],
    timeframe: Timeframe,
    annotations: Optional["ICTAnnotations"] = None,
    highlight_index: Optional[int] = None,
) -> bytes:
    """Render exactly `settings.lookback_candles` candles into a square PNG."""
    if len(candles) != settings.lookback_candles:
        raise ValueError(
            f"render_single_timeframe requires exactly {settings.lookback_candles} "
            f"candles, got {len(candles)}"
        )

    size_px = settings.single_tf_size_px
    img = Image.new("RGB", (size_px, size_px), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    price_min, price_max = _price_range(candles)
    price_to_y = _make_price_to_y(price_min, price_max, size_px)

    _draw_candles(draw, candles, price_to_y, size_px, highlight_index)

    if annotations is not None:
        from services.visual_model.renderer.annotation_renderer import apply_annotations

        apply_annotations(draw, annotations, candles, price_to_y, size_px)

    tf_label = timeframe.value if hasattr(timeframe, "value") else str(timeframe)
    _draw_watermark(draw, tf_label, size_px)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
