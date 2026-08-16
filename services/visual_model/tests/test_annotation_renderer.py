"""
TDD - Task 165: annotation_renderer - overlays sourced from LiquidityMap.

RED phase: annotations are always derived from an already-computed
LiquidityMap, never re-detected independently; OB/FVG/IFVG/BSL/SSL/CISD
overlays render with distinct, correct styling.
GREEN phase: services/visual_model/renderer/annotation_renderer.py.

**Validates: Requirements 3.1-3.5 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import List, Optional
from uuid import uuid4

from PIL import Image, ImageDraw

from pd_array_engine.models import (
    BiasDirection,
    Candle,
    CISDCascadeStatus,
    CISDResult,
    LiquidityLevel,
    LiquidityMap,
    LiquidityType,
    LiquiditySource,
    PDArray,
    PDArrayType,
    Timeframe,
)
from services.visual_model.renderer.annotation_renderer import (
    ICTAnnotations,
    apply_annotations,
    build_annotations,
)
from services.visual_model.renderer.chart_renderer import render_single_timeframe
from services.visual_model.renderer.styles import BSL_COLOR, GOLD_COLOR, SSL_COLOR


def _ts(index: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * index)


def _make_candle(index: int, bullish: bool = True) -> Candle:
    base = 2000.0 + index * 0.1
    o, c = (base, base + 0.5) if bullish else (base + 0.5, base)
    return Candle(
        timestamp=_ts(index),
        open=o,
        high=max(o, c) + 0.2,
        low=min(o, c) - 0.2,
        close=c,
        volume=100,
        timeframe=Timeframe.M15,
        instrument="XAUUSD",
    )


def _make_candles(n: int = 60) -> List[Candle]:
    return [_make_candle(i, bullish=(i % 2 == 0)) for i in range(n)]


def _make_pd_array(array_type: PDArrayType, high: float, low: float, formed_at: datetime) -> PDArray:
    return PDArray(
        array_id=str(uuid4()),
        array_type=array_type,
        direction=BiasDirection.BEARISH,
        timeframe=Timeframe.M15,
        high=high,
        low=low,
        formed_at=formed_at,
        strength_score=0.8,
    )


def _make_liquidity_level(liquidity_type: LiquidityType, price: float) -> LiquidityLevel:
    return LiquidityLevel(
        level_id=str(uuid4()),
        liquidity_type=liquidity_type,
        source=LiquiditySource.EQH if liquidity_type == LiquidityType.BSL else LiquiditySource.EQL,
        price=price,
        timeframe=Timeframe.M15,
        formed_at=_ts(0),
        strength_score=0.7,
        touch_count=2,
    )


def _make_liquidity_map(
    pd_arrays: Optional[List[PDArray]] = None,
    liquidity_levels: Optional[List[LiquidityLevel]] = None,
    cisd_cascade: Optional[CISDCascadeStatus] = None,
) -> LiquidityMap:
    return LiquidityMap(
        analyzed_at=_ts(59),
        instrument="XAUUSD",
        htf_bias={},
        liquidity_levels=liquidity_levels or [],
        pd_arrays=pd_arrays or [],
        crt_phases={},
        cisd_cascade=cisd_cascade,
        draw_on_liquidity=None,
        sweep_detected=False,
        ote_zone=None,
        unicorn=None,
        setup_grade=None,
    )


class TestBuildAnnotationsSourcedFromLiquidityMap:
    def test_annotations_derive_from_liquidity_map_not_redetected(self) -> None:
        ob = _make_pd_array(PDArrayType.OB, high=2010.0, low=2005.0, formed_at=_ts(10))
        liquidity_map = _make_liquidity_map(pd_arrays=[ob])
        annotations = build_annotations(liquidity_map, Timeframe.M15)
        assert annotations.ob_zones == [ob]
        # No independent detection logic - the annotations object is a pure
        # projection of what was already on the LiquidityMap.
        assert isinstance(annotations, ICTAnnotations)

    def test_annotations_filter_by_array_type(self) -> None:
        ob = _make_pd_array(PDArrayType.OB, 2010.0, 2005.0, _ts(10))
        fvg = _make_pd_array(PDArrayType.FVG, 2020.0, 2015.0, _ts(20))
        ifvg = _make_pd_array(PDArrayType.IFVG, 2030.0, 2025.0, _ts(30))
        liquidity_map = _make_liquidity_map(pd_arrays=[ob, fvg, ifvg])
        annotations = build_annotations(liquidity_map, Timeframe.M15)
        assert annotations.ob_zones == [ob]
        assert annotations.fvg_zones == [fvg]
        assert annotations.ifvg_zones == [ifvg]

    def test_annotations_filter_bsl_ssl(self) -> None:
        bsl = _make_liquidity_level(LiquidityType.BSL, 2050.0)
        ssl = _make_liquidity_level(LiquidityType.SSL, 1950.0)
        liquidity_map = _make_liquidity_map(liquidity_levels=[bsl, ssl])
        annotations = build_annotations(liquidity_map, Timeframe.M15)
        assert annotations.bsl_levels == [bsl]
        assert annotations.ssl_levels == [ssl]

    def test_annotations_cisd_violation_time_from_cascade(self) -> None:
        cisd_result = CISDResult(
            direction=BiasDirection.BEARISH,
            level=2008.0,
            sequence_start_time=_ts(5),
            violation_candle_time=_ts(10),
            confirmed=True,
            has_swing_prerequisite=True,
        )
        cascade = CISDCascadeStatus(cascade_valid=True, cascade_chain=[cisd_result])
        liquidity_map = _make_liquidity_map(cisd_cascade=cascade)
        annotations = build_annotations(liquidity_map, Timeframe.M15)
        assert annotations.cisd_violation_time == _ts(10)

    def test_annotations_cisd_violation_time_none_when_no_cascade(self) -> None:
        liquidity_map = _make_liquidity_map(cisd_cascade=None)
        annotations = build_annotations(liquidity_map, Timeframe.M15)
        assert annotations.cisd_violation_time is None


class TestApplyAnnotationsRendering:
    def test_ob_zone_rendered_as_semi_transparent_rect(self) -> None:
        candles = _make_candles()
        ob = _make_pd_array(PDArrayType.OB, high=candles[10].high, low=candles[10].low, formed_at=_ts(10))
        annotations = build_annotations(_make_liquidity_map(pd_arrays=[ob]), Timeframe.M15)
        plain = render_single_timeframe(candles, Timeframe.M15)
        annotated = render_single_timeframe(candles, Timeframe.M15, annotations=annotations)
        assert plain != annotated

    def test_fvg_dotted_ifvg_hatched_distinct_styles(self) -> None:
        candles = _make_candles()
        zone_high = candles[25].high
        zone_low = candles[20].low
        fvg = _make_pd_array(PDArrayType.FVG, high=zone_high, low=zone_low, formed_at=_ts(20))
        ifvg = _make_pd_array(PDArrayType.IFVG, high=zone_high, low=zone_low, formed_at=_ts(20))
        fvg_annotations = build_annotations(_make_liquidity_map(pd_arrays=[fvg]), Timeframe.M15)
        ifvg_annotations = build_annotations(_make_liquidity_map(pd_arrays=[ifvg]), Timeframe.M15)
        fvg_png = render_single_timeframe(candles, Timeframe.M15, annotations=fvg_annotations)
        ifvg_png = render_single_timeframe(candles, Timeframe.M15, annotations=ifvg_annotations)
        # Distinct styling (dotted vs hatched) must produce distinct pixels.
        assert fvg_png != ifvg_png

    def test_bsl_ssl_distinct_dashed_line_colours(self) -> None:
        candles = _make_candles()
        price_min = min(c.low for c in candles)
        price_max = max(c.high for c in candles)
        bsl = _make_liquidity_level(LiquidityType.BSL, price_max - 0.05)
        ssl = _make_liquidity_level(LiquidityType.SSL, price_min + 0.05)
        annotations = build_annotations(
            _make_liquidity_map(liquidity_levels=[bsl, ssl]), Timeframe.M15
        )
        png_bytes = render_single_timeframe(candles, Timeframe.M15, annotations=annotations)
        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        colours = set(img.getdata())
        assert BSL_COLOR in colours
        assert SSL_COLOR in colours

    def test_cisd_candle_gold_border_at_violation_time(self) -> None:
        candles = _make_candles()
        cisd_result = CISDResult(
            direction=BiasDirection.BEARISH,
            level=candles[15].open,
            sequence_start_time=_ts(5),
            violation_candle_time=_ts(15),
            confirmed=True,
            has_swing_prerequisite=True,
        )
        cascade = CISDCascadeStatus(cascade_valid=True, cascade_chain=[cisd_result])
        annotations = build_annotations(_make_liquidity_map(cisd_cascade=cascade), Timeframe.M15)
        png_bytes = render_single_timeframe(candles, Timeframe.M15, annotations=annotations)
        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        assert GOLD_COLOR in set(img.getdata())
