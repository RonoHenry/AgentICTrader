"""
Optimal Trade Entry (OTE) Fibonacci zone calculation.

Computes the 62%-79% retracement zone of the most recent displacement leg,
anchored per direction: bullish setups retrace from the swing high down
toward the swing low (discount), bearish setups retrace from the swing low up
toward the swing high (premium) — Requirements 7.7/7.8. The retracement
formula is therefore direction-dependent: `fib_X` is always measured *from
the leg's origin toward its destination*, which is what makes `ote_low <
ote_high` hold unconditionally (Property 10/Requirement 7.5, the invariant
every other consumer of `OTEZone` relies on). Note this means the "fib_62 <
fib_705 < fib_79" ordering (Property 9) only holds for bearish zones — for
bullish zones the correct, ote_low<ote_high-preserving order is the reverse
(fib_79 < fib_705 < fib_62), since retracement measured down from a high
must *decrease* as the retracement percentage increases.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from pd_array_engine.models import BiasDirection, Candle, OTEZone


class OTECalculator:
    """Calculates the OTE Fibonacci zone from a displacement leg."""

    FIBONACCI_LEVELS: List[float] = [0.0, 0.5, 0.62, 0.705, 0.79, 1.0]
    OTE_LOW: float = 0.62
    OTE_HIGH: float = 0.79
    GOLDEN_LEVEL: float = 0.705

    def calculate(self, swing_high: float, swing_low: float, direction: BiasDirection) -> OTEZone:
        fib_62 = self._fib_level(swing_high, swing_low, self.OTE_LOW, direction)
        fib_705 = self._fib_level(swing_high, swing_low, self.GOLDEN_LEVEL, direction)
        fib_79 = self._fib_level(swing_high, swing_low, self.OTE_HIGH, direction)

        if direction == BiasDirection.BEARISH:
            ote_low, ote_high = fib_62, fib_79
        else:
            ote_low, ote_high = fib_79, fib_62

        return OTEZone(
            fib_62=fib_62,
            fib_705=fib_705,
            fib_79=fib_79,
            ote_low=ote_low,
            ote_high=ote_high,
            golden_level=fib_705,
            price_in_ote=False,
            displacement_leg_high=swing_high,
            displacement_leg_low=swing_low,
        )

    def _fib_level(
        self, swing_high: float, swing_low: float, pct: float, direction: BiasDirection
    ) -> float:
        leg_range = swing_high - swing_low
        if direction == BiasDirection.BEARISH:
            return swing_low + pct * leg_range  # anchor low -> high (premium)
        return swing_high - pct * leg_range  # anchor high -> low (discount)

    def find_displacement_leg(
        self, candles: List[Candle], direction: BiasDirection
    ) -> Optional[Tuple[float, float]]:
        for i in range(len(candles) - 1, 1, -1):
            c0, c2 = candles[i - 2], candles[i]
            is_bullish_gap = c2.low > c0.high
            is_bearish_gap = c0.low > c2.high
            if (direction == BiasDirection.BULLISH and is_bullish_gap) or (
                direction == BiasDirection.BEARISH and is_bearish_gap
            ):
                leg_candles = candles[i - 2 : i + 1]
                return max(c.high for c in leg_candles), min(c.low for c in leg_candles)
        return None

    def price_in_ote(self, price: float, ote_zone: OTEZone) -> bool:
        return ote_zone.ote_low <= price <= ote_zone.ote_high
