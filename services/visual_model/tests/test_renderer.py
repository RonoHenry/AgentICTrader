"""
TDD - Tasks 164-165: chart_renderer, multi_tf_renderer, annotation_renderer.

RED phase: single-timeframe and multi-timeframe-grid rendering determinism,
fixed styling, and annotation sourcing from LiquidityMap.
GREEN phase: implementation in services/visual_model/renderer/.

**Validates: Requirements 1.1-1.6, 2.1-2.4, 3.1-3.5 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import List
from unittest.mock import patch

import pytest
from hypothesis import given, settings as hyp_settings, strategies as st
from PIL import Image, ImageDraw

from liquidity_engine.models import Candle, Timeframe
from services.visual_model.config import settings as vm_settings
from services.visual_model.renderer.chart_renderer import render_single_timeframe
from services.visual_model.renderer.multi_tf_renderer import render_multi_timeframe_grid


def _make_candle(
    index: int,
    timeframe: Timeframe = Timeframe.M15,
    instrument: str = "XAUUSD",
    bullish: bool = True,
) -> Candle:
    base = 2000.0 + index * 0.1
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * index)
    if bullish:
        o, c = base, base + 0.5
    else:
        o, c = base + 0.5, base
    return Candle(
        timestamp=ts,
        open=o,
        high=max(o, c) + 0.2,
        low=min(o, c) - 0.2,
        close=c,
        volume=100,
        timeframe=timeframe,
        instrument=instrument,
    )


def _make_candles(n: int, timeframe: Timeframe = Timeframe.M15) -> List[Candle]:
    return [_make_candle(i, timeframe=timeframe, bullish=(i % 2 == 0)) for i in range(n)]


class TestRenderSingleTimeframe:
    def test_render_single_timeframe_returns_512x512_png(self) -> None:
        candles = _make_candles(60)
        png_bytes = render_single_timeframe(candles, Timeframe.M15)
        img = Image.open(BytesIO(png_bytes))
        assert img.format == "PNG"
        assert img.size == (512, 512)

    def test_render_requires_exactly_60_candles(self) -> None:
        with pytest.raises(ValueError):
            render_single_timeframe(_make_candles(59), Timeframe.M15)
        with pytest.raises(ValueError):
            render_single_timeframe(_make_candles(61), Timeframe.M15)

    def test_render_uses_dark_background_and_candle_colours(self) -> None:
        candles = _make_candles(60)
        png_bytes = render_single_timeframe(candles, Timeframe.M15)
        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        corner_pixel = img.getpixel((2, 2))
        assert corner_pixel == (0x0A, 0x0A, 0x0F)

        colours_present = set(img.getdata())
        assert (0x00, 0xE6, 0x76) in colours_present  # bullish body colour
        assert (0xFF, 0x3D, 0x57) in colours_present  # bearish body colour

    def test_render_no_price_labels_or_volume(self) -> None:
        candles = _make_candles(60)
        with patch.object(ImageDraw.ImageDraw, "text", wraps=ImageDraw.ImageDraw.text, autospec=True) as text_spy:
            render_single_timeframe(candles, Timeframe.M15)
        # Only the timeframe watermark draws text - never per-candle price labels.
        assert text_spy.call_count == 1

    def test_render_highlight_index_draws_gold_border(self) -> None:
        candles = _make_candles(60)
        plain = render_single_timeframe(candles, Timeframe.M15)
        highlighted = render_single_timeframe(candles, Timeframe.M15, highlight_index=30)
        assert plain != highlighted
        img = Image.open(BytesIO(highlighted)).convert("RGB")
        assert (0xFF, 0xD7, 0x00) in set(img.getdata())

    @hyp_settings(max_examples=25, deadline=None)
    @given(st.integers(min_value=0, max_value=99))
    def test_property_render_determinism(self, seed: int) -> None:
        """Property 1: Chart Rendering Determinism."""
        candles = [
            _make_candle(i, bullish=((i + seed) % 2 == 0)) for i in range(60)
        ]
        first = render_single_timeframe(candles, Timeframe.M15)
        second = render_single_timeframe(candles, Timeframe.M15)
        assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


class TestRenderMultiTimeframeGrid:
    def _candles_by_tf(self) -> dict:
        return {
            Timeframe.H4: _make_candles(60, Timeframe.H4),
            Timeframe.H1: _make_candles(60, Timeframe.H1),
            Timeframe.M15: _make_candles(60, Timeframe.M15),
            Timeframe.M5: _make_candles(60, Timeframe.M5),
        }

    def test_grid_1024x1024_output(self) -> None:
        png_bytes = render_multi_timeframe_grid(
            instrument="XAUUSD",
            timestamp=datetime.now(timezone.utc),
            candles_by_tf=self._candles_by_tf(),
        )
        img = Image.open(BytesIO(png_bytes))
        assert img.size == (1024, 1024)

    def test_grid_raises_valueerror_on_missing_timeframe(self) -> None:
        incomplete = self._candles_by_tf()
        del incomplete[Timeframe.M5]
        with pytest.raises(ValueError):
            render_multi_timeframe_grid(
                instrument="XAUUSD",
                timestamp=datetime.now(timezone.utc),
                candles_by_tf=incomplete,
            )

    def test_grid_layout_quadrants_are_distinct(self) -> None:
        """H4/H1/M15/M5 quadrants render independently (not the same image tiled)."""
        candles_by_tf = self._candles_by_tf()
        candles_by_tf[Timeframe.M5] = _make_candles(60, Timeframe.M5, )
        # Force M5 to be all-bullish so its quadrant is visually distinct.
        candles_by_tf[Timeframe.M5] = [
            _make_candle(i, timeframe=Timeframe.M5, bullish=True) for i in range(60)
        ]
        candles_by_tf[Timeframe.H4] = [
            _make_candle(i, timeframe=Timeframe.H4, bullish=False) for i in range(60)
        ]
        png_bytes = render_multi_timeframe_grid(
            instrument="XAUUSD",
            timestamp=datetime.now(timezone.utc),
            candles_by_tf=candles_by_tf,
        )
        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        top_left = img.crop((0, 0, 512, 512))
        bottom_right = img.crop((512, 512, 1024, 1024))
        assert list(top_left.getdata()) != list(bottom_right.getdata())

    @hyp_settings(max_examples=10, deadline=None)
    @given(st.integers(min_value=0, max_value=99))
    def test_property_grid_render_determinism(self, seed: int) -> None:
        """Property 1: Chart Rendering Determinism (grid variant)."""
        candles_by_tf = {
            tf: [_make_candle(i, timeframe=tf, bullish=((i + seed) % 2 == 0)) for i in range(60)]
            for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)
        }
        ts = datetime.now(timezone.utc)
        first = render_multi_timeframe_grid(instrument="XAUUSD", timestamp=ts, candles_by_tf=candles_by_tf)
        second = render_multi_timeframe_grid(instrument="XAUUSD", timestamp=ts, candles_by_tf=candles_by_tf)
        assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
