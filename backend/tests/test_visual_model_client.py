"""
TDD - Task 175: agent/visual_model_client.py - thin synchronous HTTP client.

RED phase: never raises to the caller - connection/timeout failures degrade
to a neutral VisualAnalysisResponse, matching services/visual_model's own
degraded-mode contract (Requirement 12.1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from agent.visual_model_client import VisualModelClient
from liquidity_engine.models import Candle, Timeframe
from services.visual_model.api.schemas import VisualAnalysisResponse


def _make_candles(n: int, timeframe: Timeframe) -> list:
    from datetime import timedelta

    base_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(
            timestamp=base_ts + timedelta(minutes=15 * i),
            open=2000.0 + i,
            high=2001.0 + i,
            low=1999.0 + i,
            close=2000.5 + i,
            volume=100,
            timeframe=timeframe,
            instrument="XAUUSD",
        )
        for i in range(n)
    ]


class TestVisualModelClientDegradesOnFailure:
    def test_connection_error_returns_degraded_response(self) -> None:
        import httpx

        client = VisualModelClient(base_url="http://unreachable-host:9999")
        with patch(
            "httpx.Client.post",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            result = client.analyse(
                candles_by_tf={Timeframe.M15: _make_candles(5, Timeframe.M15)},
                liquidity_map=None,
                instrument="XAUUSD",
                timestamp=datetime.now(timezone.utc),
            )
        assert isinstance(result, VisualAnalysisResponse)
        assert result.degraded is True
        assert result.analysis is None
        assert result.visual_modifier == 0.0

    def test_never_raises_on_unexpected_exception(self) -> None:
        client = VisualModelClient(base_url="http://fake-host:9999")
        with patch("httpx.Client.post", side_effect=RuntimeError("boom")):
            result = client.analyse(
                candles_by_tf={Timeframe.M15: _make_candles(5, Timeframe.M15)},
                liquidity_map=None,
                instrument="XAUUSD",
                timestamp=datetime.now(timezone.utc),
            )
        assert result.degraded is True

    def test_successful_response_is_parsed(self) -> None:
        client = VisualModelClient(base_url="http://fake-host:9999")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "analysis": None,
            "visual_modifier": 0.08,
            "hard_block_reason": None,
            "degraded": False,
        }
        mock_response.raise_for_status.return_value = None
        with patch("httpx.Client.post", return_value=mock_response):
            result = client.analyse(
                candles_by_tf={Timeframe.M15: _make_candles(5, Timeframe.M15)},
                liquidity_map=None,
                instrument="XAUUSD",
                timestamp=datetime.now(timezone.utc),
            )
        assert result.degraded is False
        assert result.visual_modifier == 0.08
