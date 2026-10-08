"""
Candle-level utilities: swing point detection, ATR, and wick-based candle typing.

Stateless functions only; no I/O, no shared mutable state.
"""
from __future__ import annotations

import math
from typing import List

from liquidity_engine.models import Candle, CandleType

# Named thresholds (Requirement 16.6) — first-pass defaults calibrated
# qualitatively against the TTrades reference material, not backtest-derived.
EXPANSION_WICK_RATIO_MAX: float = 0.25
REVERSAL_WICK_RATIO_MIN: float = 0.5


def find_swing_highs(candles: List[Candle], lookback: int = 2) -> List[int]:
    """Indices of local maxima confirmed by `lookback` candles on both sides."""
    highs = [c.high for c in candles]
    return [i for i in range(lookback, len(highs) - lookback)
            if highs[i] > max(highs[i - lookback:i], default=-math.inf)
            and highs[i] > max(highs[i + 1:i + lookback + 1], default=-math.inf)]


def find_swing_lows(candles: List[Candle], lookback: int = 2) -> List[int]:
    """Indices of local minima confirmed by `lookback` candles on both sides."""
    lows = [c.low for c in candles]
    return [i for i in range(lookback, len(lows) - lookback)
            if lows[i] < min(lows[i - lookback:i], default=math.inf)
            and lows[i] < min(lows[i + 1:i + lookback + 1], default=math.inf)]


def calculate_atr(candles: List[Candle], period: int = 14) -> float:
    """Average True Range over the most recent `period` candles."""
    if len(candles) < 2:
        return 0.0
    true_ranges: List[float] = []
    for i in range(1, len(candles)):
        candle = candles[i]
        prev_close = candles[i - 1].close
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - prev_close),
                abs(candle.low - prev_close),
            )
        )
    window = true_ranges[-period:]
    return sum(window) / len(window)


def atr_series(candles: List[Candle], period: int = 14) -> List[float]:
    """ATR as seen at each index, in one pass instead of one pass per candle.

    ``series[i] == calculate_atr(candles[:i], period=min(period, i))`` exactly
    for every i >= 2: the same true ranges summed in the same order, so
    downstream threshold decisions are byte-for-byte unchanged. Indices 0 and
    1 have no prior true range and are 0.0. Building a prefix-sum shortcut
    instead would drift by float error and could flip a borderline decision.
    """
    n = len(candles)
    true_ranges = [0.0] * n
    for i in range(1, n):
        candle, prev_close = candles[i], candles[i - 1].close
        true_ranges[i] = max(
            candle.high - candle.low,
            abs(candle.high - prev_close),
            abs(candle.low - prev_close),
        )
    series = [0.0] * n
    for i in range(2, n):
        window = true_ranges[max(1, i - min(period, i)):i]
        series[i] = sum(window) / len(window)
    return series


def classify_candle_type(candle: Candle) -> CandleType:
    """Classify a candle as EXPANSION, REVERSAL, or REVERSAL_EXPANSION by wick ratio."""
    total_range = candle.total_range
    if total_range == 0:
        return CandleType.EXPANSION
    wick_ratio = max(candle.upper_wick, candle.lower_wick) / total_range
    if wick_ratio <= EXPANSION_WICK_RATIO_MAX:
        return CandleType.EXPANSION
    if wick_ratio >= REVERSAL_WICK_RATIO_MIN:
        return CandleType.REVERSAL
    return CandleType.REVERSAL_EXPANSION
