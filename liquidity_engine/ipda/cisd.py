"""
Change in State of Delivery (CISD) detection.

A CISD fires when a run of same-direction candle closes is violated by a
candle closing beyond the *first* candle's open in the opposite direction —
the classic "delivery sequence" reversal signal. Confirmation additionally
requires a 3-candle swing point somewhere in the run (Requirement 6.3):
price cannot reverse without first printing a genuine swing.
"""
from __future__ import annotations

from typing import List, Optional

from liquidity_engine.models import BiasDirection, Candle, CISDResult
from liquidity_engine.utils.candle_utils import find_swing_highs, find_swing_lows


class CISDDetector:
    """Detects a Change in State of Delivery in a single candle series."""

    def detect(self, candles: List[Candle]) -> Optional[CISDResult]:
        if len(candles) < 2:
            return None

        run_end = len(candles) - 2
        if candles[run_end].is_bullish:
            want_bullish = True
        elif candles[run_end].is_bearish:
            want_bullish = False
        else:
            return None

        run_start = run_end
        while run_start > 0 and (
            (want_bullish and candles[run_start - 1].is_bullish)
            or (not want_bullish and candles[run_start - 1].is_bearish)
        ):
            run_start -= 1

        violator = candles[-1]
        first_open = self._find_sequence_open(candles, run_start)

        if want_bullish and violator.close < first_open:
            direction = BiasDirection.BEARISH
        elif not want_bullish and violator.close > first_open:
            direction = BiasDirection.BULLISH
        else:
            return None  # run continues or is inconclusive — no CISD yet

        sequence_candles = candles[run_start:]
        has_prerequisite = self._has_swing_point_prerequisite(sequence_candles)

        return CISDResult(
            direction=direction,
            level=first_open,
            sequence_start_time=candles[run_start].timestamp,
            violation_candle_time=violator.timestamp,
            confirmed=has_prerequisite,
            has_swing_prerequisite=has_prerequisite,
        )

    def _find_sequence_open(self, candles: List[Candle], run_start: int) -> float:
        return candles[run_start].open

    def _has_swing_point_prerequisite(self, candles: List[Candle]) -> bool:
        """A genuine 3-candle swing (high or low) must exist within `candles`."""
        if len(candles) < 3:
            return False
        return bool(find_swing_highs(candles, lookback=1)) or bool(find_swing_lows(candles, lookback=1))
