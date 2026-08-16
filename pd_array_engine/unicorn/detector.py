"""
UNICORN pattern detection — a Breaker Block and FVG overlapping at the same
price level, the highest-conviction PD array confluence in the methodology.
Pure and stateless.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from pd_array_engine.models import PDArray, PDArrayType, UnicornPattern


class UnicornDetector:
    """Detects the UNICORN pattern (Breaker + FVG overlap) across PD arrays."""

    def detect(
        self, pd_arrays: List[PDArray], overlap_tolerance_pct: float = 0.001
    ) -> Optional[UnicornPattern]:
        breakers = [a for a in pd_arrays if a.array_type == PDArrayType.BREAKER]
        fvgs = [a for a in pd_arrays if a.array_type == PDArrayType.FVG]

        candidates: List[UnicornPattern] = []
        for breaker in breakers:
            for fvg in fvgs:
                if breaker.direction != fvg.direction or breaker.timeframe != fvg.timeframe:
                    continue
                if not self._arrays_overlap(breaker, fvg, overlap_tolerance_pct):
                    continue
                overlap_low, overlap_high = self._compute_overlap(breaker, fvg, overlap_tolerance_pct)
                strength_score = max(0.0, min(1.0, (breaker.strength_score + fvg.strength_score) / 2))
                candidates.append(
                    UnicornPattern(
                        breaker_array_id=breaker.array_id,
                        fvg_array_id=fvg.array_id,
                        overlap_high=overlap_high,
                        overlap_low=overlap_low,
                        direction=breaker.direction,
                        formed_at=max(breaker.formed_at, fvg.formed_at),
                        strength_score=strength_score,
                    )
                )

        if not candidates:
            return None
        return max(candidates, key=lambda pattern: pattern.formed_at)

    def _arrays_overlap(self, a: PDArray, b: PDArray, tolerance_pct: float) -> bool:
        tolerance = self._tolerance(a, tolerance_pct)
        return (a.low - tolerance) <= (b.high + tolerance) and (b.low - tolerance) <= (a.high + tolerance)

    def _compute_overlap(self, a: PDArray, b: PDArray, tolerance_pct: float) -> Tuple[float, float]:
        overlap_low = max(a.low, b.low)
        overlap_high = min(a.high, b.high)
        if overlap_low < overlap_high:
            return overlap_low, overlap_high
        # A near-touch (no literal overlap) that still passed `_arrays_overlap`'s
        # tolerance check — widen by the same tolerance so overlap_low < overlap_high
        # still holds (Property 13/Requirement 8.3 must never be violated).
        tolerance = self._tolerance(a, tolerance_pct)
        return overlap_low - tolerance, overlap_high + tolerance

    def _tolerance(self, a: PDArray, tolerance_pct: float) -> float:
        reference = (a.high + a.low) / 2
        return abs(reference) * tolerance_pct
