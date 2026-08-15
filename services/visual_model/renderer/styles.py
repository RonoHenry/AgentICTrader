"""
Visual constants for chart rendering: colours, sizes, and pre-blended tones.

Wick colours are pre-blended RGB tuples (not RGBA alpha compositing) so a
render's output bytes never depend on the compositing backend's rounding -
required for Property 1 (Chart Rendering Determinism).
"""
from __future__ import annotations

from typing import Tuple

RGB = Tuple[int, int, int]

BACKGROUND_COLOR: RGB = (0x0A, 0x0A, 0x0F)
BULLISH_COLOR: RGB = (0x00, 0xE6, 0x76)
BEARISH_COLOR: RGB = (0xFF, 0x3D, 0x57)
GOLD_COLOR: RGB = (0xFF, 0xD7, 0x00)

BSL_COLOR: RGB = (0xF5, 0xA6, 0x23)
SSL_COLOR: RGB = (0x9D, 0x6E, 0xFF)
CE_COLOR: RGB = (0x00, 0xD4, 0xFF)
IFVG_HATCH_COLOR: RGB = (0xB0, 0xB0, 0xC0)

WICK_OPACITY = 0.6


def _blend(fg: RGB, bg: RGB, alpha: float) -> RGB:
    return tuple(int(round(f * alpha + b * (1 - alpha))) for f, b in zip(fg, bg))


BULLISH_WICK_COLOR: RGB = _blend(BULLISH_COLOR, BACKGROUND_COLOR, WICK_OPACITY)
BEARISH_WICK_COLOR: RGB = _blend(BEARISH_COLOR, BACKGROUND_COLOR, WICK_OPACITY)

OB_BEARISH_FILL: RGB = _blend(BEARISH_COLOR, BACKGROUND_COLOR, 0.13)
OB_BULLISH_FILL: RGB = _blend(BULLISH_COLOR, BACKGROUND_COLOR, 0.13)

CANVAS_MARGIN_PX = 12
BODY_WIDTH_RATIO = 0.6
WATERMARK_OPACITY = 0.35
