"""
Chart annotation overlays sourced from an already-computed LiquidityMap.

This module never re-detects PD arrays, liquidity levels, or CISD events -
it only projects what liquidity_engine already found onto pixel coordinates.
The overlays exist to orient the VLM's attention (e.g. "here's the OB the
numerical engine flagged"), not to hand it the answer - the whole point of
the visual layer is an independent read of the same chart.

**Validates: Requirements 3.1-3.5 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

from PIL import ImageDraw

from liquidity_engine.models import (
    Candle,
    LiquidityLevel,
    LiquidityMap,
    LiquidityType,
    PDArray,
    PDArrayType,
    Timeframe,
)
from services.visual_model.renderer.styles import (
    BSL_COLOR,
    GOLD_COLOR,
    IFVG_HATCH_COLOR,
    OB_BEARISH_FILL,
    OB_BULLISH_FILL,
    SSL_COLOR,
)


@dataclass
class ICTAnnotations:
    """A pure projection of a LiquidityMap's contents for one timeframe -
    holds no detection logic of its own."""

    ob_zones: List[PDArray] = field(default_factory=list)
    fvg_zones: List[PDArray] = field(default_factory=list)
    ifvg_zones: List[PDArray] = field(default_factory=list)
    bsl_levels: List[LiquidityLevel] = field(default_factory=list)
    ssl_levels: List[LiquidityLevel] = field(default_factory=list)
    cisd_violation_time: Optional[datetime] = None


def build_annotations(liquidity_map: LiquidityMap, timeframe: Timeframe) -> ICTAnnotations:
    """Filter LiquidityMap.pd_arrays / liquidity_levels down to one timeframe's
    overlays. Purely a filter - detection already happened in liquidity_engine."""
    arrays = [a for a in liquidity_map.pd_arrays if a.timeframe == timeframe]
    levels = [lv for lv in liquidity_map.liquidity_levels if lv.timeframe == timeframe]

    cisd_violation_time: Optional[datetime] = None
    if liquidity_map.cisd_cascade is not None and liquidity_map.cisd_cascade.cascade_chain:
        cisd_violation_time = liquidity_map.cisd_cascade.cascade_chain[-1].violation_candle_time

    return ICTAnnotations(
        ob_zones=[a for a in arrays if a.array_type == PDArrayType.OB],
        fvg_zones=[a for a in arrays if a.array_type == PDArrayType.FVG],
        ifvg_zones=[a for a in arrays if a.array_type == PDArrayType.IFVG],
        bsl_levels=[lv for lv in levels if lv.liquidity_type == LiquidityType.BSL],
        ssl_levels=[lv for lv in levels if lv.liquidity_type == LiquidityType.SSL],
        cisd_violation_time=cisd_violation_time,
    )


def _nearest_candle_index(candles: List[Candle], ts: datetime) -> Optional[int]:
    if not candles:
        return None
    best_index = 0
    best_delta = abs((candles[0].timestamp - ts).total_seconds())
    for i, candle in enumerate(candles):
        delta = abs((candle.timestamp - ts).total_seconds())
        if delta < best_delta:
            best_delta = delta
            best_index = i
    return best_index


def _draw_zone(
    draw: ImageDraw.ImageDraw,
    zone: PDArray,
    candles: List[Candle],
    price_to_y: Callable[[float], float],
    size_px: int,
    fill: Optional[tuple],
    outline: tuple,
    style: str,
) -> None:
    start_index = _nearest_candle_index(candles, zone.formed_at)
    if start_index is None:
        return
    candle_width = size_px / len(candles)
    x_left = start_index * candle_width
    x_right = float(size_px)
    y_top = price_to_y(zone.high)
    y_bottom = price_to_y(zone.low)

    if fill is not None:
        draw.rectangle([x_left, y_top, x_right, y_bottom], fill=fill)

    if style == "dotted":
        _draw_dotted_rect(draw, x_left, y_top, x_right, y_bottom, outline)
    elif style == "hatched":
        _draw_hatched_rect(draw, x_left, y_top, x_right, y_bottom, outline)
    else:
        draw.rectangle([x_left, y_top, x_right, y_bottom], outline=outline, width=1)


def _draw_dotted_rect(draw, x0, y0, x1, y1, color, dash=4, gap=3) -> None:
    for x in range(int(x0), int(x1), dash + gap):
        draw.line([(x, y0), (min(x + dash, x1), y0)], fill=color, width=1)
        draw.line([(x, y1), (min(x + dash, x1), y1)], fill=color, width=1)
    for y in range(int(y0), int(y1), dash + gap):
        draw.line([(x0, y), (x0, min(y + dash, y1))], fill=color, width=1)
        draw.line([(x1, y), (x1, min(y + dash, y1))], fill=color, width=1)


def _draw_hatched_rect(draw, x0, y0, x1, y1, color, spacing=8) -> None:
    draw.rectangle([x0, y0, x1, y1], outline=color, width=1)
    width = int(x1 - x0)
    height = int(y1 - y0)
    for offset in range(0, width + height, spacing):
        start = (x0 + offset, y0)
        end = (x0, y0 + offset)
        draw.line([start, end], fill=color, width=1)


def apply_annotations(
    draw: ImageDraw.ImageDraw,
    annotations: ICTAnnotations,
    candles: List[Candle],
    price_to_y: Callable[[float], float],
    size_px: int,
) -> None:
    for ob in annotations.ob_zones:
        bearish = ob.direction.value == "BEARISH"
        _draw_zone(
            draw,
            ob,
            candles,
            price_to_y,
            size_px,
            fill=OB_BEARISH_FILL if bearish else OB_BULLISH_FILL,
            outline=OB_BEARISH_FILL if bearish else OB_BULLISH_FILL,
            style="solid",
        )

    for fvg in annotations.fvg_zones:
        _draw_zone(
            draw, fvg, candles, price_to_y, size_px, fill=None, outline=IFVG_HATCH_COLOR, style="dotted"
        )

    for ifvg in annotations.ifvg_zones:
        _draw_zone(
            draw, ifvg, candles, price_to_y, size_px, fill=None, outline=IFVG_HATCH_COLOR, style="hatched"
        )

    for bsl in annotations.bsl_levels:
        y = price_to_y(bsl.price)
        _draw_dashed_hline(draw, y, size_px, BSL_COLOR)

    for ssl in annotations.ssl_levels:
        y = price_to_y(ssl.price)
        _draw_dashed_hline(draw, y, size_px, SSL_COLOR)

    if annotations.cisd_violation_time is not None:
        index = _nearest_candle_index(candles, annotations.cisd_violation_time)
        if index is not None:
            candle_width = size_px / len(candles)
            x_center = index * candle_width + candle_width / 2
            candle = candles[index]
            y_open = price_to_y(candle.open)
            y_close = price_to_y(candle.close)
            top = min(y_open, y_close)
            bottom = max(y_open, y_close)
            half_width = candle_width * 0.4
            draw.rectangle(
                [x_center - half_width - 2, top - 2, x_center + half_width + 2, bottom + 2],
                outline=GOLD_COLOR,
                width=2,
            )


def _draw_dashed_hline(draw: ImageDraw.ImageDraw, y: float, size_px: int, color: tuple, dash=6, gap=4) -> None:
    for x in range(0, size_px, dash + gap):
        draw.line([(x, y), (min(x + dash, size_px), y)], fill=color, width=1)
