"""
Standard Deviation Projection — target levels beyond a displacement leg.

Same anchor mechanism as OTE (liquidity_engine/ote/calculator.py): "Anchored
from swing high to swing low," direction-dependent 0%/100% assignment. Where
OTE stops at the 0-1 retracement range to find an entry, this projects
*beyond* the 0% anchor by whole-leg multiples to find continuation targets —
the same leg, extended rather than subdivided.
"""
from __future__ import annotations

from typing import List

from liquidity_engine.models import BiasDirection, SDProjection

#: TTrades' standard deviation levels (charted as 1/-1, 2/-2, 2.5/-2.5,
#: 4/-4, 4.5/-4.5 — stored as positive multiples, see SDProjection docstring).
DEFAULT_LEVELS: List[float] = [1.0, 2.0, 2.5, 4.0, 4.5]


class StandardDeviationCalculator:
    """Projects target levels beyond a displacement leg, direction-aware."""

    def project(
        self,
        swing_high: float,
        swing_low: float,
        direction: BiasDirection,
        levels: List[float] = DEFAULT_LEVELS,
    ) -> SDProjection:
        # Same anchor assignment as OTECalculator._fib_level: bearish
        # measures low->high (0% at the low), bullish measures high->low
        # (0% at the high) — see that module's docstring for why.
        if direction == BiasDirection.BEARISH:
            anchor_0, anchor_1 = swing_low, swing_high
        else:
            anchor_0, anchor_1 = swing_high, swing_low

        leg_range = anchor_0 - anchor_1
        targets = {level: anchor_0 + level * leg_range for level in levels}

        return SDProjection(anchor_0=anchor_0, anchor_1=anchor_1, targets=targets)


__all__ = ["StandardDeviationCalculator", "DEFAULT_LEVELS"]
