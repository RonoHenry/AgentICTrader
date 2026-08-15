"""
TDD - Task 167: ICT-specific VLM prompt construction.

RED phase: the prompt must ask about BOS/CHoCH (not MSS) and the five CRT
phase values classify_crt_phase() can return (not AMD's six-value set),
matching liquidity_engine's own vocabulary.
GREEN phase: services/visual_model/perception/prompt_builder.py.

**Validates: Requirements 4.1-4.5 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

from services.visual_model.perception.prompt_builder import (
    build_system_prompt,
    build_user_prompt,
)


class TestSystemPrompt:
    def test_system_prompt_injects_instrument_timestamp_session_killzone(self) -> None:
        prompt = build_system_prompt(
            instrument="XAUUSD",
            timestamp="2026-08-15T08:33:00+00:00",
            session="NY_AM",
            kill_zone="ACTIVE",
        )
        assert "XAUUSD" in prompt
        assert "2026-08-15T08:33:00+00:00" in prompt
        assert "NY_AM" in prompt
        assert "ACTIVE" in prompt


class TestUserPromptVocabulary:
    def test_user_prompt_asks_about_bos_and_choch(self) -> None:
        prompt = build_user_prompt()
        assert "BOS" in prompt
        assert "CHoCH" in prompt
        assert "MSS" not in prompt

    def test_user_prompt_crt_phase_options_are_five_values(self) -> None:
        prompt = build_user_prompt()
        for value in (
            "C1_ACCUMULATION",
            "C2_MANIPULATION",
            "C3_DISTRIBUTION",
            "C4_CONTINUATION",
            "UNKNOWN",
        ):
            assert value in prompt
        assert "REVERSAL" not in prompt
        assert "RETRACEMENT" not in prompt
        assert "AMD" not in prompt

    def test_user_prompt_requests_json_only_no_preamble(self) -> None:
        prompt = build_user_prompt()
        assert "JSON" in prompt
        assert "no preamble" in prompt.lower() or "json only" in prompt.lower()

    def test_user_prompt_instructs_visual_only_no_inference(self) -> None:
        # This instruction is a persistent framing constraint for the whole
        # call, so it lives in the system prompt rather than being repeated
        # in every user-prompt section.
        system_prompt = build_system_prompt(
            instrument="XAUUSD",
            timestamp="2026-08-15T08:33:00+00:00",
            session="NY_AM",
            kill_zone="ACTIVE",
        )
        lowered = system_prompt.lower()
        assert "visual" in lowered
        assert "infer" in lowered or "context" in lowered
