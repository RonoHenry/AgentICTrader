"""Strategy settings shared by the live runner and AlgoBacktester.

These used to be constants scattered through scripts/run_live_agent.py. Live
trading and the backtester read them from one frozen model, so a backtest
runs the settings the agent trades with (.kiro/specs/algo-backtester,
task 188). A run config's [strategy] table maps onto the fields directly:

    [strategy]
    entry_tf = "M15"
    min_rr = 3.0
    pending_expiry = "KILLZONE_END"
    fallback_ttl_minutes = 180

Grader parameters stay in liquidity_engine; a run manifest records them
through the engine code fingerprint, and these through fingerprint().

Validates: Requirements 1.6 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import timedelta
from enum import Enum
from types import MappingProxyType
from typing import Annotated, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, PositiveInt, field_validator, model_validator

from liquidity_engine.models import SetupGrade, Timeframe

__all__ = ["ENTRY_TIMEFRAMES", "PendingExpiry", "StrategyConfig"]

# Entries come from M15 and below; higher timeframes are bias and context
# only (liquidity_engine.grader.setup_grader._ENTRY_ELIGIBLE_TIMEFRAMES).
ENTRY_TIMEFRAMES = (Timeframe.M1, Timeframe.M3, Timeframe.M5, Timeframe.M15)
TRADEABLE_GRADES = (SetupGrade.A_PLUS, SetupGrade.A, SetupGrade.B)


class PendingExpiry(str, Enum):
    """When an unfilled pending order is cancelled."""
    KILLZONE_END = "KILLZONE_END"  # end of the killzone it was placed in; fallback_ttl outside every killzone
    FIXED_TTL = "FIXED_TTL"        # fallback_ttl after placement, always


K = TypeVar("K")
V = TypeVar("V")
# A read-only mapping, so a config's fingerprint can't drift after it is built.
ReadOnlyMapping = Annotated[
    Mapping[K, V],
    AfterValidator(lambda m: MappingProxyType(dict(m))),
    PlainSerializer(dict, return_type=dict[K, V]),
]


class StrategyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)

    entry_tf: Timeframe = Timeframe.M15
    # Analysed alongside D1 and W1 (which the engine requires) for bias and
    # CRT-phase context. HTFBiasClassifier computes a bias for every timeframe
    # it is given, so these let H4 (or H12/H8/H6/H3) inform intraday bias
    # distinctly from D1/W1's swing bias. Entries never come from them.
    context_tfs: tuple[Timeframe, ...] = (Timeframe.H12, Timeframe.H8, Timeframe.H6, Timeframe.H4, Timeframe.H3)
    # Bars per timeframe handed to the engine.
    candle_counts: ReadOnlyMapping[Timeframe, PositiveInt] = {
        Timeframe.M1: 300,
        Timeframe.M3: 300,
        Timeframe.M5: 300,
        Timeframe.M15: 200,
        Timeframe.H3: 150,
        Timeframe.H4: 150,
        Timeframe.H6: 120,
        Timeframe.H8: 100,
        Timeframe.H12: 90,
        Timeframe.D1: 90,
        Timeframe.W1: 30,
    }
    min_rr: float = Field(default=3.0, ge=0)  # 0 acts on every graded setup (debugging)
    grade_confidence: ReadOnlyMapping[SetupGrade, float] = {
        SetupGrade.A_PLUS: 0.90,
        SetupGrade.A: 0.80,
        SetupGrade.B: 0.70,
    }
    # Standard Deviation projection levels for TP1 and TP2. TTrades' reference
    # material labels 2.5 as "Target" on its projection chart, with 4.0 as a
    # further runner target (liquidity_engine.projections.standard_deviation).
    tp_levels: tuple[float, ...] = (2.5, 4.0)
    pending_expiry: PendingExpiry = PendingExpiry.KILLZONE_END
    fallback_ttl_minutes: PositiveInt = 180

    @property
    def fallback_ttl(self) -> timedelta:
        return timedelta(minutes=self.fallback_ttl_minutes)

    @property
    def timeframes(self) -> tuple[Timeframe, ...]:
        """Every timeframe handed to the engine, in the order the runner fetches them."""
        return (Timeframe.D1, Timeframe.W1, *self.context_tfs, self.entry_tf)

    def __reduce__(self):
        # Read-only mappings don't pickle; rebuild from plain values instead
        # (AlgoBacktester sends the config to one process per instrument).
        return type(self).model_validate, (self.model_dump(),)

    def fingerprint(self) -> str:
        """sha256 of the canonical JSON: equal settings, equal fingerprint."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @field_validator("entry_tf")
    @classmethod
    def _entry_tf_m15_or_below(cls, tf: Timeframe) -> Timeframe:
        if tf not in ENTRY_TIMEFRAMES:
            raise ValueError(
                f"entry_tf must be one of {', '.join(t.value for t in ENTRY_TIMEFRAMES)} "
                f"(entries come from M15 and below), not {tf.value}"
            )
        return tf

    @field_validator("tp_levels")
    @classmethod
    def _tp_levels_increasing(cls, levels: tuple[float, ...]) -> tuple[float, ...]:
        if not 1 <= len(levels) <= 2:
            raise ValueError(f"tp_levels needs one or two levels (TP1, optional TP2), got {len(levels)}")
        if levels[0] <= 0 or list(levels) != sorted(set(levels)):
            raise ValueError(f"tp_levels must be positive and increasing (TP1 before TP2), got {levels}")
        return levels

    @field_validator("grade_confidence")
    @classmethod
    def _confidence_per_tradeable_grade(cls, confidence: Mapping[SetupGrade, float]) -> Mapping[SetupGrade, float]:
        extra = [g.value for g in confidence if g not in TRADEABLE_GRADES]
        if extra:
            raise ValueError(f"grade_confidence: {', '.join(extra)} is not a tradeable grade")
        missing = [g.value for g in TRADEABLE_GRADES if g not in confidence]
        if missing:
            raise ValueError(f"grade_confidence has no value for {', '.join(missing)}")
        bad = {g.value: c for g, c in confidence.items() if not 0 < c <= 1}
        if bad:
            raise ValueError(f"grade_confidence values must be in (0, 1], got {bad}")
        return confidence

    @model_validator(mode="after")
    def _window_for_every_timeframe(self) -> StrategyConfig:
        missing = [tf.value for tf in self.timeframes if tf not in self.candle_counts]
        if missing:
            raise ValueError(f"candle_counts has no window size for {', '.join(missing)}")
        return self
