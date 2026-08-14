"""
Fractal Model — Candle 1-4 continuation/reversal closure sequence.

Tracks each candle relative to the one before it (CONTINUATION when it
extends the developing range beyond the prior candle's extreme, REVERSAL when
it closes back inside the prior candle's range) and computes the Equilibrium
of the accumulating range. This is the single-candle-resolution layer that
sits below CISD and OTE. Pure and stateless.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from liquidity_engine.models import Candle, ClosureType, FractalCandleStep, FractalModelResult


class FractalModelTracker:
    """Tracks the Fractal Model candle sequence and its developing Equilibrium."""

    def track(self, candles: List[Candle], key_level: Optional[float]) -> Optional[FractalModelResult]:
        if key_level is None or len(candles) < 2:
            return None

        steps: List[FractalCandleStep] = [
            FractalCandleStep(step_number=1, candle=candles[0], closure_type=None)
        ]
        range_high, range_low = candles[0].high, candles[0].low

        for n in range(1, len(candles)):
            prior, current = candles[n - 1], candles[n]
            closure_type = self._classify_closure(prior, current)
            steps.append(FractalCandleStep(step_number=n + 1, candle=current, closure_type=closure_type))
            range_high, range_low = self._update_range(current, range_high, range_low)

        equilibrium = (range_high + range_low) / 2
        return FractalModelResult(
            key_level=key_level,
            steps=steps,
            range_high=range_high,
            range_low=range_low,
            equilibrium=equilibrium,
            price_above_equilibrium=candles[-1].close > equilibrium,
        )

    def _classify_closure(self, prior: Candle, current: Candle) -> ClosureType:
        developing_up = prior.close >= prior.open
        if developing_up:
            return ClosureType.CONTINUATION if current.close > prior.high else ClosureType.REVERSAL
        return ClosureType.CONTINUATION if current.close < prior.low else ClosureType.REVERSAL

    def _update_range(self, candle: Candle, range_high: float, range_low: float) -> Tuple[float, float]:
        return max(range_high, candle.high), min(range_low, candle.low)
