"""
TDD - Task 168: VLM visual reasoner - model invocation, retry, caching.

RED phase: the real Anthropic client is never constructed or called in this
suite - every test injects a mock `client` directly into VLMReasoner.

**Validates: Requirements 5.1-5.7 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.visual_model.perception.vlm_reasoner import (
    VISION_MODEL_FALLBACK,
    VISION_MODEL_PRIMARY,
    VLMAnalysisError,
    VLMReasoner,
)
from services.visual_model.schemas.visual_analysis import VisualAnalysis

_VALID_ANALYSIS_JSON = json.dumps(
    {
        "instrument": "XAUUSD",
        "analysis_timestamp": "2026-08-15T08:33:00+00:00",
        "structure": {
            "h4_direction": "BEARISH",
            "h4_bos_visible": True,
            "h4_bos_description": "Clean break below the prior swing low.",
            "h1_direction": "BEARISH",
            "h1_choch_visible": True,
            "h1_choch_description": "CHoCH confirmed on the retest.",
            "structure_clarity_score": 8.0,
        },
        "dealing_range": {
            "range_visible": True,
            "price_position": "PREMIUM",
            "bsl_pools_visible": True,
            "bsl_description": "Equal highs.",
            "ssl_pools_visible": False,
            "ssl_description": "None visible.",
            "liquidity_sweep_confirmed": True,
            "sweep_description": "Wick swept and closed back inside.",
        },
        "crt": {
            "h4_phase": "C3_DISTRIBUTION",
            "h4_phase_description": "Strong expansion.",
            "h1_phase": "C3_DISTRIBUTION",
            "h1_phase_description": "Follow-through.",
            "m15_phase": "C4_CONTINUATION",
            "m15_phase_description": "Continuation candles.",
            "manipulation_complete": True,
            "manipulation_evidence": "Sweep rejected and closed back inside.",
        },
        "cisd": {
            "detected": True,
            "direction": "BEARISH",
            "displacement_candle": {
                "visual_dominance": 9.0,
                "body_appears_large": True,
                "wicks_minimal": True,
                "closes_beyond_structure": True,
                "description": "Dominant displacement candle.",
            },
            "order_block": {
                "identifiable": True,
                "ambiguity": "UNAMBIGUOUS",
                "description": "Single clear OB candle.",
            },
            "ifvg": {
                "visible": True,
                "gap_obvious": True,
                "ce_approximate": "midpoint of the gap",
                "description": "Clear gap.",
            },
        },
        "m5_precision": {
            "ob_visible_at_ce": True,
            "ob_ifvg_confluence": True,
            "m5_cisd_nested": True,
            "description": "M5 OB aligns with M15 IFVG CE.",
        },
        "fractal": {
            "coherence_score": 8.0,
            "amd_phases_aligned": True,
            "perceived_depth": 3,
            "description": "Consistent story across timeframes.",
        },
        "quality": {
            "overall_score": 8.5,
            "strongest_element": "Displacement candle dominance.",
            "biggest_weakness": "SSL pool unclear.",
            "take_this_trade": True,
            "conviction_level": "HIGH",
        },
        "visual_insights": {
            "what_numbers_miss": "Visual dominance of the candle.",
            "visual_warnings": "None significant.",
            "narrative": "Clean bearish CISD.",
        },
    }
)


def _mock_message(text: str, input_tokens: int = 500, output_tokens: int = 300) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _mock_anthropic_client(responses) -> MagicMock:
    """responses: a single text or a list of texts returned on successive calls."""
    client = MagicMock()
    if isinstance(responses, list):
        client.messages.create.side_effect = [_mock_message(r) for r in responses]
    else:
        client.messages.create.return_value = _mock_message(responses)
    return client


class TestModelConfiguration:
    def test_configured_model_is_a_real_current_model_id(self) -> None:
        known_current_models = {
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-fable-5",
            "claude-haiku-4-5-20251001",
        }
        assert VISION_MODEL_PRIMARY in known_current_models
        assert VISION_MODEL_FALLBACK in known_current_models
        # The original draft's fictional model ids must never resurface.
        assert VISION_MODEL_PRIMARY != "claude-opus-4-6"
        assert VISION_MODEL_FALLBACK != "claude-sonnet-4-6"


class TestAnalyse:
    @pytest.mark.asyncio
    async def test_analyse_returns_parsed_visual_analysis_on_valid_json(self) -> None:
        client = _mock_anthropic_client(_VALID_ANALYSIS_JSON)
        reasoner = VLMReasoner(client=client, redis_client=None)
        result = await reasoner.analyse(
            chart_png=b"fake-png-bytes",
            instrument="XAUUSD",
            timestamp=datetime(2026, 8, 15, 8, 33, tzinfo=timezone.utc),
            session="NY_AM",
            kill_zone="ACTIVE",
        )
        assert isinstance(result, VisualAnalysis)
        assert result.cisd.direction == "BEARISH"
        client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyse_retries_once_on_invalid_json(self) -> None:
        client = _mock_anthropic_client(["not valid json", _VALID_ANALYSIS_JSON])
        reasoner = VLMReasoner(client=client, redis_client=None)
        result = await reasoner.analyse(
            chart_png=b"fake-png-bytes",
            instrument="XAUUSD",
            timestamp=datetime(2026, 8, 15, 8, 33, tzinfo=timezone.utc),
            session="NY_AM",
            kill_zone="ACTIVE",
        )
        assert isinstance(result, VisualAnalysis)
        assert client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_analyse_raises_vlm_analysis_error_after_second_invalid_json(self) -> None:
        client = _mock_anthropic_client(["not valid json", "still not valid json"])
        reasoner = VLMReasoner(client=client, redis_client=None)
        with pytest.raises(VLMAnalysisError):
            await reasoner.analyse(
                chart_png=b"fake-png-bytes",
                instrument="XAUUSD",
                timestamp=datetime(2026, 8, 15, 8, 33, tzinfo=timezone.utc),
                session="NY_AM",
                kill_zone="ACTIVE",
            )
        assert client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_logs_token_counts_and_model_per_call(self, caplog) -> None:
        client = _mock_anthropic_client(_VALID_ANALYSIS_JSON)
        reasoner = VLMReasoner(client=client, redis_client=None, vision_model="claude-opus-5")
        with caplog.at_level("INFO"):
            await reasoner.analyse(
                chart_png=b"fake-png-bytes",
                instrument="XAUUSD",
                timestamp=datetime(2026, 8, 15, 8, 33, tzinfo=timezone.utc),
                session="NY_AM",
                kill_zone="ACTIVE",
            )
        joined = " ".join(record.message for record in caplog.records)
        assert "claude-opus-5" in joined
        assert "500" in joined
        assert "300" in joined


class TestCaching:
    def _redis_stub(self):
        store: dict = {}

        redis = MagicMock()
        redis.get = AsyncMock(side_effect=lambda key: store.get(key))

        async def _set(key, value, ex=None):
            store[key] = value

        redis.set = AsyncMock(side_effect=_set)
        return redis

    @pytest.mark.asyncio
    async def test_cache_hit_skips_second_vlm_call(self) -> None:
        """Property 8: Cache Key Uniqueness (identical-triple half)."""
        client = _mock_anthropic_client(_VALID_ANALYSIS_JSON)
        redis = self._redis_stub()
        reasoner = VLMReasoner(client=client, redis_client=redis)
        kwargs = dict(
            chart_png=b"same-bytes",
            instrument="XAUUSD",
            timestamp=datetime(2026, 8, 15, 8, 33, tzinfo=timezone.utc),
            session="NY_AM",
            kill_zone="ACTIVE",
        )
        await reasoner.analyse(**kwargs)
        await reasoner.analyse(**kwargs)
        client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_on_different_chart_hash(self) -> None:
        """Property 8: Cache Key Uniqueness (distinct-triple half)."""
        client = _mock_anthropic_client([_VALID_ANALYSIS_JSON, _VALID_ANALYSIS_JSON])
        redis = self._redis_stub()
        reasoner = VLMReasoner(client=client, redis_client=redis)
        common = dict(
            instrument="XAUUSD",
            timestamp=datetime(2026, 8, 15, 8, 33, tzinfo=timezone.utc),
            session="NY_AM",
            kill_zone="ACTIVE",
        )
        await reasoner.analyse(chart_png=b"chart-one", **common)
        await reasoner.analyse(chart_png=b"chart-two", **common)
        assert client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_back_to_direct_call(self) -> None:
        client = _mock_anthropic_client(_VALID_ANALYSIS_JSON)
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=ConnectionError("redis down"))
        redis.set = AsyncMock(side_effect=ConnectionError("redis down"))
        reasoner = VLMReasoner(client=client, redis_client=redis)
        result = await reasoner.analyse(
            chart_png=b"fake-png-bytes",
            instrument="XAUUSD",
            timestamp=datetime(2026, 8, 15, 8, 33, tzinfo=timezone.utc),
            session="NY_AM",
            kill_zone="ACTIVE",
        )
        assert isinstance(result, VisualAnalysis)
