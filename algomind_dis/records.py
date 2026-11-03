"""AlgoMindDIS's records (algomind-dis Requirement 2): every judgment kept with its origin, so any decision can be
traced (§2.6, §19.7).

Records are frozen dataclasses. Times are UTC nanoseconds (as ``algo_mind.dis`` and ``algo_research.sequence``);
only the contract's output (``DirectionalBiasOutput``) carries ISO strings. Ids come from content (``make_id``), so
the same bars always give the same ids (Requirement 2.3). ``to_json`` and ``from_json`` round-trip every record.
Directions are "BULLISH", "BEARISH" or "NEUTRAL"; an objective's side is the way price moves to reach it.
"""
from __future__ import annotations

import hashlib
import types
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Dict, Optional, Tuple, Union, get_args, get_origin, get_type_hints

import numpy as np

__all__ = ["ArrayContext", "DealingRange", "DeliveryState", "DirectionalBiasOutput", "Evidence", "LiquidityObjective",
           "MarketNarrative", "PricePosition", "StructureEvent", "TimeframeContext", "Transition", "from_json",
           "make_id", "to_json"]


def make_id(*parts) -> str:
    """A content id: the same parts always give the same 16 hex characters."""
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class DealingRange:
    """§5.2: a structurally meaningful interval. ``kind`` is SWING, PREVIOUS or DISPLACEMENT."""
    id: str
    market: str
    tf: str
    kind: str
    high: float
    low: float
    origin: str                          # what made it, in words
    established_at: int
    valid: bool
    invalidated_at: Optional[int]
    invalidation: str                    # the condition that ends it, in words

    @property
    def equilibrium(self) -> float:
        return (self.high + self.low) / 2

    def position(self, price: float) -> float:
        return (price - self.low) / (self.high - self.low) if self.high > self.low else 0.5


@dataclass(frozen=True)
class PricePosition:
    """§5.3: price's place in a range. Location, never a direction."""
    range_id: str
    tf: str
    position: float
    zone: str                            # DEEP_DISCOUNT, DISCOUNT, EQUILIBRIUM, PREMIUM, DEEP_PREMIUM
    equilibrium: float
    price: float


@dataclass(frozen=True)
class LiquidityObjective:
    """§5.4: a pool or gap that could draw price. ``side`` BULLISH lies above, reached by rising."""
    id: str
    market: str
    tf: str
    price: float
    kind: str                            # EXTERNAL, INTERNAL, TEMPORAL
    source: str                          # SWING_HIGH, PWL, EQUAL_HIGHS, FVG ...
    side: str
    range_id: Optional[str]
    status: str                          # IDENTIFIED, APPROACHING, SWEPT, INVALIDATED
    significance: float
    formed_at: int
    swept_at: Optional[int]
    closed_back: bool                    # the sweeping candle closed back inside


@dataclass(frozen=True)
class ArrayContext:
    """§6.2: one PD array and its nine evaluations."""
    id: str
    market: str
    tf: str
    kind: str                            # FVG, OB, BREAKER
    direction: str
    low: float
    high: float
    formed_at: int
    location: str                        # price ABOVE, INSIDE or BELOW it
    range_id: Optional[str]
    zone: Optional[str]                  # its near edge's zone in its parent range
    displacement: bool
    after_sweep: bool
    aligned: bool                        # with the W1 structural direction
    mitigated: bool
    valid: bool
    invalidated_at: Optional[int]


@dataclass(frozen=True)
class StructureEvent:
    """§7.1: a close beyond a swing. BOS with the structure, MSS against it."""
    id: str
    tf: str
    kind: str
    direction: str
    level: float
    at: int                              # the close that broke it
    swing_at: int                        # the swing's candle


@dataclass(frozen=True)
class DeliveryState:
    """§7.2: BULLISH_DELIVERY, BEARISH_DELIVERY, CONSOLIDATION, TRANSITIONAL or UNCONFIRMED."""
    tf: str
    state: str
    since: Optional[int]
    evidence: Tuple[str, ...]


@dataclass(frozen=True)
class TimeframeContext:
    """§5.1: one timeframe's structure, location, objectives, arrays and delivery, kept apart."""
    tf: str
    structural_direction: str
    price: float
    ranges: Tuple[DealingRange, ...]
    positions: Tuple[PricePosition, ...]
    objectives: Tuple[LiquidityObjective, ...]
    arrays: Tuple[ArrayContext, ...]
    delivery: Optional[DeliveryState]
    events: Tuple[StructureEvent, ...]


@dataclass(frozen=True)
class Evidence:
    """§9.3: one observation's directional weight, with its provenance."""
    id: str
    category: str                        # STRUCTURE, LIQUIDITY, PREMIUM_DISCOUNT, PD_ARRAY, DELIVERY, TEMPORAL, VOLATILITY
    direction: str
    tf: str
    source_event: Optional[str]          # observations of the same candles share it (correlation control)
    significance: float
    at: int
    valid: bool
    depends_on: Tuple[str, ...]
    text: str


@dataclass(frozen=True)
class MarketNarrative:
    """§9.1: the hypothesis as a structured explanation."""
    id: str
    market: str
    at: int
    primary_tf: str
    hypothesis: str
    delivery_state: str
    primary_objective: Optional[str]
    supporting: Tuple[Evidence, ...]
    conflicting: Tuple[Evidence, ...]
    invalidation: Tuple[str, ...]
    confidence: float
    status: str
    text: str


@dataclass(frozen=True)
class Transition:
    """§10.3: a state change and why."""
    market: str
    at: int
    previous: str
    new: str
    trigger: str
    tf: str
    narrative_id: Optional[str]


@dataclass(frozen=True)
class DirectionalBiasOutput:
    """§12: the contract the setup engine reads (``contract_version``)."""
    instrument: str
    bias_id: str
    version: str
    contract_version: str
    primary_direction: str               # BULLISH, BEARISH, NEUTRAL, UNDETERMINED
    state: str                           # ACTIVE, TRANSITIONAL, INVALIDATED, EXPIRED
    confidence_score: float
    analysis_timestamp: str
    timeframe_contexts: Dict[str, TimeframeContext]
    primary_dealing_range: Optional[DealingRange]
    premium_discount_context: Dict[str, PricePosition]
    liquidity_objectives: Tuple[LiquidityObjective, ...]
    supporting_evidence: Tuple[Evidence, ...]
    conflicting_evidence: Tuple[Evidence, ...]
    delivery_state: str
    invalidation_conditions: Tuple[str, ...]
    valid_until: Optional[str]
    narrative_id: Optional[str]
    data_quality: str


def to_json(x: Any) -> Any:
    """A record (or anything holding records) as plain JSON values."""
    if is_dataclass(x) and not isinstance(x, type):
        return {f.name: to_json(getattr(x, f.name)) for f in fields(x)}
    if isinstance(x, (tuple, list)):
        return [to_json(v) for v in x]
    if isinstance(x, dict):
        return {str(k): to_json(v) for k, v in x.items()}
    if isinstance(x, np.generic):
        return x.item()
    return x


def from_json(tp: Any, data: Any) -> Any:
    """``data`` (from ``to_json``) back as ``tp``."""
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(tp) if a is not type(None)]
        return None if data is None else from_json(args[0], data)
    if is_dataclass(tp):
        hints = get_type_hints(tp)
        return tp(**{f.name: from_json(hints[f.name], data[f.name]) for f in fields(tp)})
    if origin is tuple:
        return tuple(from_json(get_args(tp)[0], v) for v in data)
    if origin is dict:
        value = get_args(tp)[1]
        return {k: from_json(value, v) for k, v in data.items()}
    if tp is float:
        return float(data)
    if tp is int:
        return int(data)
    return data
