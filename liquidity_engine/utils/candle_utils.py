"""
Candle-level utilities: swing point detection, ATR, and wick-based candle typing.

Stateless functions only; no I/O, no shared mutable state.
"""
from __future__ import annotations

from typing import List

from liquidity_engine.models import Candle, CandleType

# Named thresholds (Requirement 16.6) — first-pass defaults calibrated
# qualitatively against the TTrades reference material, not backtest-derived.
EXPANSION_WICK_RATIO_MAX: float = 0.25
REVERSAL_WICK_RATIO_MIN: float = 0.5


def find_swing_highs(candles: List[Candle], lookback: int = 2) -> List[int]:
    """Indices of local maxima confirmed by `lookback` candles on both sides."""
    n = len(candles)
    swings: List[int] = []
    for i in range(lookback, n - lookback):
        pivot = candles[i].high
        if all(pivot > candles[j].high for j in range(i - lookback, i)) and all(
            pivot > candles[j].high for j in range(i + 1, i + lookback + 1)
        ):
            swings.append(i)
    return swings


def find_swing_lows(candles: List[Candle], lookback: int = 2) -> List[int]:
    """Indices of local minima confirmed by `lookback` candles on both sides."""
    n = len(candles)
    swings: List[int] = []
    for i in range(lookback, n - lookback):
        pivot = candles[i].low
        if all(pivot < candles[j].low for j in range(i - lookback, i)) and all(
            pivot < candles[j].low for j in range(i + 1, i + lookback + 1)
        ):
            swings.append(i)
    return swings


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
