"""Every weight and threshold AlgoMindDIS uses (algomind-dis Requirement 9.4, DIS-D5).

``V1`` is the version registered as H-AF before it ran (docs/research/SEARCH_2018_2024.md, 2026-11-03). The weights
are the specification's §9.4 starting weights: experimental, not validated. Changing any value is a new version and
a new try, never an edit of V1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

__all__ = ["Settings", "V1", "V2"]


@dataclass(frozen=True)
class Settings:
    version: str = "v1"
    #: §9.4: the categories' weights (time and volatility are context and weigh 0).
    category_weights: Dict[str, float] = field(default_factory=lambda: {
        "STRUCTURE": 0.25, "LIQUIDITY": 0.25, "PREMIUM_DISCOUNT": 0.20, "PD_ARRAY": 0.15, "DELIVERY": 0.15})
    #: §11: the higher timeframe outweighs the lower.
    timeframe_weights: Dict[str, float] = field(default_factory=lambda: {
        "MN1": 1.0, "W1": 0.8, "D1": 0.6, "H4": 0.4, "H1": 0.3})
    #: §5.3: the zones' bounds on a range's position (0 its low, 1 its high).
    deep_discount: float = 0.25
    discount: float = 0.45
    premium: float = 0.55
    deep_premium: float = 0.75
    #: §5.4: an objective's significance is its timeframe's weight times its type's, never its distance.
    type_weights: Dict[str, float] = field(default_factory=lambda: {"EXTERNAL": 1.0, "TEMPORAL": 0.8, "INTERNAL": 0.6})
    equal_bonus: float = 0.25
    approaching_adr: float = 0.5
    #: §6.2: a displacement is a body at least this many times the mean body of the candles before it.
    displacement_body: float = 1.5
    body_window: int = 20
    #: §6.2: a sweep counts for an array formed within this many candles after it.
    sweep_window: int = 3
    adr_days: int = 20
    #: §10: the state machine, stepped at each D1 close.
    establish_score: float = 0.5
    establish_lead: float = 0.2
    challenge_lead: float = 0.3
    resolve_closes: int = 3
    validity_closes: int = 20
    #: §13.3: a frame with no close for longer than this on a weekday is stale.
    stale_days: int = 3
    #: Which PD arrays it reads: "engine" (``frame_state._arrays``: the last opposite candle before a 1.5 ATR candle,
    #: wick to wick; v1, as H-AF ran) or "cisd" (the trader's: ``liquidity_engine.context.blocks``, the CISD run's
    #: bodies, a close through inverting it into a breaker, a close back through ending that).
    array_rule: str = "engine"


V1 = Settings()
#: v1 with the trader's order blocks and breakers (2026-11-03). Untested: a test of it is a new registration.
V2 = Settings(version="v2", array_rule="cisd")
