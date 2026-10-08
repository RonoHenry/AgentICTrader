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

from agent.strategy_config import BiasMode, PendingExpiry, StopMode, StrategyConfig, TargetMode, TimeWindow
from liquidity_engine.models import SetupGrade, Timeframe as TF


def test_defaults_equal_current_runner_constants():
    # Today's values in scripts/run_live_agent.py (_CANDLE_COUNT,
    # _GRADE_TO_CONFIDENCE, --min-rr, _TP1/_TP2_SD_LEVEL, CONTEXT_TIMEFRAMES,
    # ENTRY_TIMEFRAME). Changing a default changes live behaviour. tp_levels
    # and stop_mode follow the setup-sequence update (liquidity-engine Req 19).
    cfg = StrategyConfig()

    assert cfg.entry_tf is TF.M15
    # H1, M30 and M15 liquidity is analysed too (liquidity-engine Req 20.1, LE-D13).
    assert cfg.context_tfs == (TF.H12, TF.H8, TF.H6, TF.H4, TF.H3, TF.H1, TF.M30, TF.M15)
    assert dict(cfg.candle_counts) == {
        TF.M1: 300, TF.M3: 300, TF.M5: 300, TF.M15: 200, TF.M30: 100, TF.H1: 200,
        TF.H3: 150, TF.H4: 150, TF.H6: 120, TF.H8: 100, TF.H12: 90,
        TF.D1: 90, TF.W1: 30,
    }
    assert cfg.min_rr == 3.0
    assert dict(cfg.grade_confidence) == {SetupGrade.A_PLUS: 0.90, SetupGrade.A: 0.80, SetupGrade.B: 0.70}
    assert cfg.tp_levels == (2.0, 2.5)
    assert cfg.stop_mode is StopMode.WICK
    # The candle anticipation rules are all off by default (liquidity-engine Req 23, 25.2).
    assert (cfg.bias_mode, cfg.require_false_move, cfg.time_window, cfg.require_htf_poi, cfg.target_mode,
            cfg.min_stop_spreads) == (BiasMode.OPEN, False, TimeWindow.ANY, False, TargetMode.SD, 0.0)


def test_timeframes_list_each_once():
    # The entry timeframe is also a context timeframe by default: it is fetched and analysed once.
    assert StrategyConfig().timeframes == (TF.D1, TF.W1, TF.H12, TF.H8, TF.H6, TF.H4, TF.H3, TF.H1, TF.M30, TF.M15)
    assert StrategyConfig(entry_tf="M5").timeframes[-2:] == (TF.M15, TF.M5)


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
    ({"min_rr": -1}, "min_rr"),
    ({"tp_levels": (4.0, 2.5)}, "tp_levels"),           # TP1 before TP2
    ({"tp_levels": ()}, "tp_levels"),
    ({"stop_mode": "MIDPOINT"}, "stop_mode"),           # WICK or BODY
    ({"bias_mode": "STRUCTURE"}, "bias_mode"),          # OPEN or PROFILE
    ({"time_window": "LONDON"}, "time_window"),         # ANY or MANIPULATION
    ({"target_mode": "FAR"}, "target_mode"),            # SD or NEAREST
    ({"min_stop_spreads": -1.0}, "min_stop_spreads"),
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
    "stop_mode": StopMode.BODY,
    "bias_mode": BiasMode.PROFILE,
    "require_false_move": True,
    "time_window": TimeWindow.MANIPULATION,
    "require_htf_poi": True,
    "target_mode": TargetMode.NEAREST,
    "min_stop_spreads": 2.0,
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


def test_pickles_for_worker_processes():
    # Phase A sends the config to one process per instrument (task 199).
    import pickle

    cfg = StrategyConfig(entry_tf="M5", min_rr=4.0)
    clone = pickle.loads(pickle.dumps(cfg))
    assert clone == cfg and clone.fingerprint() == cfg.fingerprint()
    with pytest.raises(TypeError):
        clone.candle_counts[TF.M5] = 1  # still read-only
