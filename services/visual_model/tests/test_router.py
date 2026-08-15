"""
TDD - Task 170: api/router.py, main.py, degraded-mode handling.

RED phase: /visual/analyse never returns a 5xx on internal failure
(Property 6), always falls back to degraded=True. VLM and Redis are always
mocked; the render path uses real Pillow rendering (fast, deterministic,
no reason to mock it).

**Validates: Requirements 10.1-10.5 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from liquidity_engine.models import Candle, Timeframe
from services.visual_model.api.router import get_vlm_reasoner, router
from services.visual_model.perception.vlm_reasoner import VLMAnalysisError
from services.visual_model.schemas.visual_analysis import (
    CISDSection,
    CRTPhaseLiteral,
    CRTSection,
    DealingRangeSection,
    DisplacementCandle,
    FractalSection,
    IFVGRead,
    M5PrecisionSection,
    OrderBlockRead,
    QualitySection,
    StructureSection,
    VisualAnalysis,
    VisualInsightsSection,
)


def _make_candle(index: int, timeframe: Timeframe, bullish: bool = True) -> Candle:
    base = 2000.0 + index * 0.1
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * index)
    o, c = (base, base + 0.5) if bullish else (base + 0.5, base)
    return Candle(
        timestamp=ts,
        open=o,
        high=max(o, c) + 0.2,
        low=min(o, c) - 0.2,
        close=c,
        volume=100,
        timeframe=timeframe,
        instrument="XAUUSD",
    )


def _candles_by_tf() -> Dict[Timeframe, List[Candle]]:
    return {
        tf: [_make_candle(i, tf, bullish=(i % 2 == 0)) for i in range(60)]
        for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5)
    }


def _valid_analysis() -> VisualAnalysis:
    return VisualAnalysis(
        instrument="XAUUSD",
        analysis_timestamp=datetime.now(timezone.utc),
        structure=StructureSection(
            h4_direction="BEARISH",
            h4_bos_visible=True,
            h4_bos_description="x",
            h1_direction="BEARISH",
            h1_choch_visible=True,
            h1_choch_description="x",
            structure_clarity_score=8.0,
        ),
        dealing_range=DealingRangeSection(
            range_visible=True,
            price_position="PREMIUM",
            bsl_pools_visible=True,
            bsl_description="x",
            ssl_pools_visible=False,
            ssl_description="x",
            liquidity_sweep_confirmed=True,
            sweep_description="x",
        ),
        crt=CRTSection(
            h4_phase=CRTPhaseLiteral.C3_DISTRIBUTION,
            h4_phase_description="x",
            h1_phase=CRTPhaseLiteral.C3_DISTRIBUTION,
            h1_phase_description="x",
            m15_phase=CRTPhaseLiteral.C4_CONTINUATION,
            m15_phase_description="x",
            manipulation_complete=True,
            manipulation_evidence="x",
        ),
        cisd=CISDSection(
            detected=True,
            direction="BEARISH",
            displacement_candle=DisplacementCandle(
                visual_dominance=8.0,
                body_appears_large=True,
                wicks_minimal=True,
                closes_beyond_structure=True,
                description="x",
            ),
            order_block=OrderBlockRead(identifiable=True, ambiguity="UNAMBIGUOUS", description="x"),
            ifvg=IFVGRead(visible=True, gap_obvious=True, ce_approximate="x", description="x"),
        ),
        m5_precision=M5PrecisionSection(
            ob_visible_at_ce=True, ob_ifvg_confluence=True, m5_cisd_nested=True, description="x"
        ),
        fractal=FractalSection(coherence_score=8.0, amd_phases_aligned=True, perceived_depth=3, description="x"),
        quality=QualitySection(
            overall_score=8.5,
            strongest_element="x",
            biggest_weakness="x",
            take_this_trade=True,
            conviction_level="HIGH",
        ),
        visual_insights=VisualInsightsSection(what_numbers_miss="x", visual_warnings="x", narrative="x"),
    )


def _request_payload(candles_by_tf=None) -> dict:
    from services.visual_model.schemas.chart_input import ChartAnalysisRequest

    request = ChartAnalysisRequest(
        instrument="XAUUSD",
        timestamp=datetime.now(timezone.utc),
        candles_by_tf=candles_by_tf if candles_by_tf is not None else _candles_by_tf(),
        session="NY_AM",
        kill_zone="ACTIVE",
        numerical_direction="BEARISH",
    )
    return request.model_dump(mode="json")


@pytest.fixture()
def app_client():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return app


class TestVisualAnalyseHappyPath:
    def test_post_visual_analyse_happy_path_returns_200_with_modifier(self, app_client) -> None:
        mock_reasoner = MagicMock()
        mock_reasoner.analyse = AsyncMock(return_value=_valid_analysis())
        app_client.dependency_overrides[get_vlm_reasoner] = lambda: mock_reasoner
        client = TestClient(app_client)

        response = client.post("/visual/analyse", json=_request_payload())

        assert response.status_code == 200
        body = response.json()
        assert body["degraded"] is False
        assert body["analysis"]["cisd"]["direction"] == "BEARISH"
        assert isinstance(body["visual_modifier"], float)


class TestVisualAnalyseDegradedMode:
    def test_post_visual_analyse_render_valueerror_returns_degraded_200(self, app_client) -> None:
        mock_reasoner = MagicMock()
        mock_reasoner.analyse = AsyncMock(return_value=_valid_analysis())
        app_client.dependency_overrides[get_vlm_reasoner] = lambda: mock_reasoner
        client = TestClient(app_client)

        incomplete = _candles_by_tf()
        del incomplete[Timeframe.M5]
        response = client.post("/visual/analyse", json=_request_payload(incomplete))

        assert response.status_code == 200
        body = response.json()
        assert body["degraded"] is True
        assert body["analysis"] is None
        assert body["visual_modifier"] == 0.0
        assert body["hard_block_reason"] is None

    def test_post_visual_analyse_vlm_analysis_error_returns_degraded_200(self, app_client) -> None:
        mock_reasoner = MagicMock()
        mock_reasoner.analyse = AsyncMock(side_effect=VLMAnalysisError("invalid json twice"))
        app_client.dependency_overrides[get_vlm_reasoner] = lambda: mock_reasoner
        client = TestClient(app_client)

        response = client.post("/visual/analyse", json=_request_payload())

        assert response.status_code == 200
        assert response.json()["degraded"] is True

    def test_post_visual_analyse_never_returns_5xx_on_internal_failure(self, app_client) -> None:
        mock_reasoner = MagicMock()
        mock_reasoner.analyse = AsyncMock(side_effect=RuntimeError("unexpected"))
        app_client.dependency_overrides[get_vlm_reasoner] = lambda: mock_reasoner
        client = TestClient(app_client)

        response = client.post("/visual/analyse", json=_request_payload())

        assert response.status_code < 500
        assert response.json()["degraded"] is True

    def test_analyse_endpoint_completes_under_8s_with_mocked_vlm_latency(self, app_client) -> None:
        mock_reasoner = MagicMock()
        mock_reasoner.analyse = AsyncMock(return_value=_valid_analysis())
        app_client.dependency_overrides[get_vlm_reasoner] = lambda: mock_reasoner
        client = TestClient(app_client)

        start = time.monotonic()
        response = client.post("/visual/analyse", json=_request_payload())
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        assert elapsed < 8.0


class TestVisualRender:
    def test_post_visual_render_returns_base64_png(self, app_client) -> None:
        client = TestClient(app_client)
        payload = {
            "instrument": "XAUUSD",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "candles_by_tf": {
                tf.value: [c.model_dump(mode="json") for c in candles]
                for tf, candles in _candles_by_tf().items()
            },
        }
        response = client.post("/visual/render", json=payload)
        assert response.status_code == 200
        assert "image_b64" in response.json()


class TestVisualHealth:
    def test_get_visual_health_reports_model_and_cache_status(self, app_client) -> None:
        mock_reasoner = MagicMock()
        mock_reasoner.is_configured = True
        mock_reasoner.has_cache = False
        app_client.dependency_overrides[get_vlm_reasoner] = lambda: mock_reasoner
        client = TestClient(app_client)

        response = client.get("/visual/health")

        assert response.status_code == 200
        body = response.json()
        assert body["vlm_configured"] is True
        assert body["cache_available"] is False
