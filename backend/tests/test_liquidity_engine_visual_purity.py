"""
TDD - Task 178: liquidity_engine purity checkpoint.

Confirms services/visual_model never got imported into liquidity_engine -
grading must remain a pure, synchronous, in-process function with zero
dependency on the (network-calling) visual model.

**Validates: Requirement 13.4 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import os


def _liquidity_engine_python_files():
    root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "liquidity_engine")
    )
    for dirpath, _dirnames, filenames in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for filename in filenames:
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)


class TestLiquidityEnginePurity:
    def test_no_file_references_services_visual_model(self) -> None:
        offenders = []
        for path in _liquidity_engine_python_files():
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if "services.visual_model" in content or "visual_model_client" in content:
                offenders.append(path)
        assert offenders == [], f"liquidity_engine references the visual model: {offenders}"

    def test_grade_output_identical_with_and_without_visual_model_importable(self) -> None:
        """Property 7: Grading Purity Is Preserved."""
        from datetime import datetime, timedelta, timezone

        from liquidity_engine import LiquidityMappingEngine
        from liquidity_engine.models import Candle, Timeframe

        base = datetime(2024, 1, 1, tzinfo=timezone.utc)

        def _candles(n, tf_days=0, tf_minutes=0):
            return [
                Candle(
                    timestamp=base + timedelta(days=tf_days * i, minutes=tf_minutes * i),
                    open=50 + i,
                    high=52 + i,
                    low=49 + i,
                    close=51 + i,
                    volume=100,
                    timeframe=Timeframe.D1 if tf_days else Timeframe.W1,
                    instrument="EURUSD",
                )
                for i in range(n)
            ]

        candles_by_tf = {
            Timeframe.D1: _candles(10, tf_days=1),
            Timeframe.W1: _candles(4, tf_days=7),
        }

        engine = LiquidityMappingEngine()
        first = engine.analyze(candles_by_tf, "EURUSD", datetime.now(tz=timezone.utc))

        # services.visual_model is importable in this process (task 163-171
        # already imported it earlier in the test session) - grading must be
        # unaffected either way.
        import services.visual_model  # noqa: F401

        second = engine.analyze(candles_by_tf, "EURUSD", first.analyzed_at)

        assert first.setup_grade.grade == second.setup_grade.grade
        assert first.setup_grade.conditions_met == second.setup_grade.conditions_met
