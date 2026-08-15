"""
Claude vision call, retry-on-invalid-JSON, and Redis caching.

Mirrors services/nlp/llm_service.py's conventions: an optional Anthropic
import guarded by a try/except (graceful degradation if the package is not
installed), a module-level model-name constant, and a synchronous
`client.messages.create()` call wrapped in an `async def` method.

**Validates: Requirements 5.1-5.7 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from typing import Optional

from pydantic import ValidationError

from services.visual_model.config import settings
from services.visual_model.perception.prompt_builder import (
    build_system_prompt,
    build_user_prompt,
)
from services.visual_model.schemas.visual_analysis import VisualAnalysis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Anthropic import - graceful degradation if not installed
# ---------------------------------------------------------------------------
try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ANTHROPIC_AVAILABLE = False
    anthropic = None  # type: ignore[assignment]

# Real, currently-supported Claude models - never a placeholder/fictional id
# such as the original draft's "claude-opus-4-6".
VISION_MODEL_PRIMARY = settings.vision_model_primary
VISION_MODEL_FALLBACK = settings.vision_model_fallback

_RETRY_SUFFIX = (
    "\n\nYour last response was not valid JSON. Return ONLY the JSON object, "
    "with no preamble or explanation."
)


class VLMAnalysisError(Exception):
    """Raised when the VLM fails to return parseable JSON after one retry."""


class VLMReasoner:
    def __init__(
        self,
        anthropic_api_key: str = "",
        vision_model: str = VISION_MODEL_PRIMARY,
        redis_client: Optional[object] = None,
        client: Optional[object] = None,
        max_tokens: int = 4096,
    ) -> None:
        self._vision_model = vision_model
        self._redis = redis_client
        self._max_tokens = max_tokens
        self._client: Optional[object] = client

        if self._client is None and _ANTHROPIC_AVAILABLE and anthropic_api_key:
            try:
                self._client = anthropic.Anthropic(api_key=anthropic_api_key)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to initialise Anthropic client: %s", exc)
                self._client = None

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    @property
    def has_cache(self) -> bool:
        return self._redis is not None

    async def analyse(
        self,
        chart_png: bytes,
        instrument: str,
        timestamp: datetime,
        session: str,
        kill_zone: str,
    ) -> VisualAnalysis:
        if self._client is None:
            raise VLMAnalysisError("Anthropic client is not configured")

        cache_key = self._cache_key(chart_png, instrument, timestamp)
        cached_json = await self._get_cached(cache_key)
        if cached_json is not None:
            return VisualAnalysis.model_validate_json(cached_json)

        raw_text = self._call_vlm(chart_png, instrument, timestamp, session, kill_zone)
        analysis = self._parse_with_one_retry(
            raw_text, chart_png, instrument, timestamp, session, kill_zone
        )

        await self._set_cached(cache_key, analysis.model_dump_json())
        return analysis

    # ------------------------------------------------------------------
    # VLM call
    # ------------------------------------------------------------------

    def _call_vlm(
        self,
        chart_png: bytes,
        instrument: str,
        timestamp: datetime,
        session: str,
        kill_zone: str,
        retry: bool = False,
    ) -> str:
        system_prompt = build_system_prompt(
            instrument=instrument,
            timestamp=timestamp.isoformat(),
            session=session,
            kill_zone=kill_zone,
        )
        user_prompt = build_user_prompt()
        if retry:
            user_prompt += _RETRY_SUFFIX

        image_b64 = base64.b64encode(chart_png).decode("utf-8")
        message = self._client.messages.create(  # type: ignore[union-attr]
            model=self._vision_model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ],
        )

        usage = getattr(message, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        logger.info(
            "vlm_reasoner call: model=%s input_tokens=%s output_tokens=%s",
            self._vision_model,
            input_tokens,
            output_tokens,
        )

        return message.content[0].text

    def _parse_with_one_retry(
        self,
        raw_text: str,
        chart_png: bytes,
        instrument: str,
        timestamp: datetime,
        session: str,
        kill_zone: str,
    ) -> VisualAnalysis:
        try:
            return VisualAnalysis.model_validate_json(raw_text)
        except (ValidationError, json.JSONDecodeError, ValueError):
            retry_text = self._call_vlm(
                chart_png, instrument, timestamp, session, kill_zone, retry=True
            )
            try:
                return VisualAnalysis.model_validate_json(retry_text)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                raise VLMAnalysisError(
                    "VLM returned invalid JSON after one retry"
                ) from exc

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(chart_png: bytes, instrument: str, timestamp: datetime) -> str:
        import hashlib

        digest = hashlib.sha256(chart_png).hexdigest()
        return f"visual_model:analysis:{digest}:{instrument}:{timestamp.isoformat()}"

    async def _get_cached(self, key: str) -> Optional[str]:
        if self._redis is None:
            return None
        try:
            return await self._redis.get(key)
        except Exception as exc:
            logger.warning("Redis cache unavailable, calling VLM directly: %s", exc)
            return None

    async def _set_cached(self, key: str, value: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, value, ex=settings.cache_ttl_seconds)
        except Exception as exc:
            logger.warning("Failed to write VLM cache: %s", exc)
