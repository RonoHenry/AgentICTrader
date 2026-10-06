"""
Tests for agent/strategy_config.py — the strategy settings live trading and
AlgoBacktester share.

Task 188 (.kiro/specs/algo-backtester/tasks.md).
Validates: Requirements 1.6 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from agent.strategy_config import PendingExpiry, StrategyConfig
from liquidity_engine.models import SetupGrade, Timeframe as TF


def test_defaults_equal_current_runner_constants():
    # Today's values in scripts/run_live_agent.py (_CANDLE_COUNT,
    # _GRADE_TO_CONFIDENCE, --min-rr, _TP1/_TP2_SD_LEVEL, CONTEXT_TIMEFRAMES,
    # ENTRY_TIMEFRAME). Changing a default changes live behaviour.
    cfg = StrategyConfig()

    assert cfg.entry_tf is TF.M15
    assert cfg.context_tfs == (TF.H12, TF.H8, TF.H6, TF.H4, TF.H3)
    assert dict(cfg.candle_counts) == {
        TF.M1: 300, TF.M3: 300, TF.M5: 300, TF.M15: 200,
        TF.H3: 150, TF.H4: 150, TF.H6: 120, TF.H8: 100, TF.H12: 90,
        TF.D1: 90, TF.W1: 30,
    }
    assert cfg.min_rr == 3.0
    assert dict(cfg.grade_confidence) == {SetupGrade.A_PLUS: 0.90, SetupGrade.A: 0.80, SetupGrade.B: 0.70}
    assert cfg.tp_levels == (2.5, 4.0)


def test_pending_expiry_default_killzone_end_with_3h_fallback():
    cfg = StrategyConfig()
    assert cfg.pending_expiry is PendingExpiry.KILLZONE_END
    assert cfg.fallback_ttl == timedelta(hours=3)

    # The run config's [strategy] table feeds the model directly.
    fixed = StrategyConfig(pending_expiry="FIXED_TTL", fallback_ttl_minutes=90)
    assert fixed.pending_expiry is PendingExpiry.FIXED_TTL
    assert fixed.fallback_ttl == timedelta(minutes=90)


def test_entry_tf_and_window_sizes_accept_string_values():
    cfg = StrategyConfig(entry_tf="M5", candle_counts={**{tf.value: n for tf, n in StrategyConfig().candle_counts.items()}, "M5": 400})
    assert cfg.entry_tf is TF.M5
    assert cfg.candle_counts[TF.M5] == 400


@pytest.mark.parametrize("overrides, message", [
    ({"entry_tf": "H1"}, "entry_tf"),                   # entries come from M15 and below
    ({"min_rr": 0}, "min_rr"),
    ({"tp_levels": (4.0, 2.5)}, "tp_levels"),           # TP1 before TP2
    ({"tp_levels": ()}, "tp_levels"),
    ({"grade_confidence": {"A+": 1.5, "A": 0.8, "B": 0.7}}, "grade_confidence"),
    ({"grade_confidence": {"A+": 0.9, "A": 0.8, "B": 0.7, "NO_TRADE": 0.1}}, "NO_TRADE"),
    ({"fallback_ttl_minutes": 0}, "fallback_ttl_minutes"),
    ({"candle_counts": {"M15": 200}}, "candle_counts"),  # no window for H4, D1, W1, ...
    ({"candle_counts": {**{tf.value: n for tf, n in StrategyConfig().candle_counts.items()}, "M15": 0}},
     "greater than 0"),
])
def test_invalid_settings_rejected(overrides, message):
    with pytest.raises(ValidationError, match=message):
        StrategyConfig(**overrides)


def test_unknown_field_rejected():
    # A typo in the run config's [strategy] table must not be silently ignored.
    with pytest.raises(ValidationError, match="min_r"):
        StrategyConfig(min_r=5.0)


# One changed value per field. Adding a field without a row here fails the
# coverage assert below, so the fingerprint test always covers every field.
_CHANGED = {
    "entry_tf": TF.M5,
    "context_tfs": (TF.H12, TF.H8, TF.H6, TF.H4),
    "candle_counts": {**{tf: n for tf, n in StrategyConfig().candle_counts.items()}, TF.W1: 31},
    "min_rr": 5.0,
    "grade_confidence": {SetupGrade.A_PLUS: 0.95, SetupGrade.A: 0.80, SetupGrade.B: 0.70},
    "tp_levels": (2.5, 4.5),
    "pending_expiry": PendingExpiry.FIXED_TTL,
    "fallback_ttl_minutes": 181,
}


def test_fingerprint_stable_and_changes_on_any_field():
    assert set(_CHANGED) == set(StrategyConfig.model_fields)

    base = StrategyConfig()
    # Stable: equal settings give equal fingerprints, whatever order the
    # mappings were built in, and it is the sha256 of the canonical JSON.
    reordered = StrategyConfig(
        candle_counts=dict(reversed(list(base.candle_counts.items()))),
        grade_confidence=dict(reversed(list(base.grade_confidence.items()))),
    )
    assert reordered.fingerprint() == base.fingerprint()
    canonical = json.dumps(base.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    assert base.fingerprint() == hashlib.sha256(canonical.encode()).hexdigest()

    for field, value in _CHANGED.items():
        assert StrategyConfig(**{field: value}).fingerprint() != base.fingerprint(), field


def test_frozen():
    cfg = StrategyConfig()
    with pytest.raises(ValidationError):
        cfg.min_rr = 5.0
    # The mappings are read-only too, so the fingerprint can't drift after construction.
    with pytest.raises(TypeError):
        cfg.candle_counts[TF.M15] = 500
    with pytest.raises(TypeError):
        cfg.grade_confidence[SetupGrade.B] = 0.5
