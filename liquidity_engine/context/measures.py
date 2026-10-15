"""Frame-relative measures for Model A (context-engine update 2026-10-15).

Pure functions over a frame's arrays (open, high, low, close, oldest first). Every size is read in the frame's
own average range (MA-D8), so the same call means the same thing on M1 and on D1. Nothing here reads a clock.

Model A is read for shorts; a long is the same reading of the mirrored bars (``mirror``), so every function
here is written once, for the bearish side.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from liquidity_engine.detectors.internal import OB_EXPANSION_ATR_MULTIPLE

__all__ = ["AVERAGE_RANGE_CANDLES", "average_range", "bearish_breakers", "bearish_cisd", "bearish_fvgs",
           "bearish_order_blocks", "equal_highs", "mirror", "rolling_average_range", "swing_highs", "swing_lows",
           "tight_range"]

#: MA-D8: a frame's average range is the mean high minus low of its last 20 closed candles.
AVERAGE_RANGE_CANDLES = 20


def mirror(o, h, l, c) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The bars upside down: a long read as a short. Highs become lows, so every bearish rule reads bullish."""
    return -np.asarray(o, float), -np.asarray(l, float), -np.asarray(h, float), -np.asarray(c, float)


def average_range(h, l, end: int, n: int = AVERAGE_RANGE_CANDLES) -> float:
    """The mean high minus low of the ``n`` candles before index ``end``; NaN without any."""
    lo = max(0, end - n)
    return float(np.mean(np.asarray(h[lo:end]) - np.asarray(l[lo:end]))) if end > lo else float("nan")


def rolling_average_range(h, l, n: int = AVERAGE_RANGE_CANDLES) -> np.ndarray:
    """``average_range(h, l, i)`` for every i at once: element i reads the candles before i."""
    r = np.asarray(h, float) - np.asarray(l, float)
    csum = np.concatenate([[0.0], np.cumsum(r)])
    i = np.arange(len(r))
    lo = np.maximum(0, i - n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(i > lo, (csum[i] - csum[lo]) / (i - lo), np.nan)


def swing_highs(h, lookback: int = 2) -> List[int]:
    """Indices of highs above the ``lookback`` highs on each side (``find_swing_highs`` on arrays)."""
    h = [float(x) for x in h]
    return [i for i in range(lookback, len(h) - lookback)
            if h[i] > max(h[i - lookback:i]) and h[i] > max(h[i + 1:i + lookback + 1])]


def swing_lows(l, lookback: int = 2) -> List[int]:
    l = [float(x) for x in l]
    return [i for i in range(lookback, len(l) - lookback)
            if l[i] < min(l[i - lookback:i]) and l[i] < min(l[i + 1:i + lookback + 1])]


def bearish_fvgs(h, l, lo: int, hi: int) -> List[Tuple[int, float, float]]:
    """Bearish fair value gaps formed by candles k in [lo + 2, hi): the gap itself, from candle k's high up to
    candle k-2's low (the engine's FVG spans the three candles; this is the gap only). As (k, bottom, top)."""
    return [(k, float(h[k]), float(l[k - 2])) for k in range(max(lo + 2, 2), hi) if l[k - 2] > h[k]]


def bearish_cisd(o, h, l, c, j: int) -> bool:
    """Whether candle j confirms a bearish change in state of delivery, as ``CISDDetector`` reads ``candles[:j+1]``:
    the candles before j close up in a run, j closes below the run's first open, and the run with j holds a
    3-candle swing."""
    if j < 1 or not c[j - 1] > o[j - 1]:
        return False
    r = j - 1
    while r > 0 and c[r - 1] > o[r - 1]:
        r -= 1
    if not c[j] < o[r]:
        return False
    seq_h, seq_l = h[r:j + 1], l[r:j + 1]
    return len(seq_h) >= 3 and (bool(swing_highs(seq_h, 1)) or bool(swing_lows(seq_l, 1)))


def _true_ranges(h, l, c) -> List[float]:
    """``atr_series``'s true ranges, as plain floats (index 0 has none)."""
    tr = [0.0] * len(h)
    for i in range(1, len(h)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return tr


def bearish_order_blocks(o, h, l, c, hi: Optional[int] = None) -> List[Tuple[int, int, float, float]]:
    """The engine's bearish order blocks (``PDArrayDetector._detect_order_blocks``) among candles [0, hi): a
    bearish candle of at least 1.5 ATR, and the last bullish candle before it. As (ob index, expansion index,
    low, high). The ATR is summed as ``atr_series`` sums it, so borderline candles decide alike."""
    hi = len(h) if hi is None else hi
    o, h, l, c = ([float(x) for x in a[:hi]] for a in (o, h, l, c))
    tr = _true_ranges(h, l, c)
    out = []
    last_bull = -1                                       # the last bullish candle before i
    for i in range(hi):
        if i >= 2 and c[i] < o[i]:
            lo = max(1, i - min(14, i))
            atr = sum(tr[lo:i]) / (i - lo)
            if atr > 0 and h[i] - l[i] >= OB_EXPANSION_ATR_MULTIPLE * atr and last_bull >= 0 and h[last_bull] > l[last_bull]:
                out.append((last_bull, i, l[last_bull], h[last_bull]))
        if c[i] > o[i]:
            last_bull = i
    return out


def bearish_breakers(o, h, l, c, hi: Optional[int] = None) -> List[Tuple[int, float, float]]:
    """The engine's bearish breakers among candles [0, hi): a bullish order block (read on the mirrored bars)
    that a later candle closes below. As (violation index, low, high)."""
    mo, mh, ml, mc = mirror(o, h, l, c)
    out = []
    for j, _i, mlow, mhigh in bearish_order_blocks(mo, mh, ml, mc, hi):
        low, high = -mhigh, -mlow                          # the bullish block, back the right way up
        end = len(c) if hi is None else hi
        for k in range(j + 1, end):
            if c[k] < low:
                out.append((k, low, high))
                break
    return out


def equal_highs(h, lo: int, hi: int, tolerance: float, below: float) -> Optional[Tuple[float, float]]:
    """Two peaks among candles [lo, hi) within ``tolerance`` of each other and under ``below``: inducement as
    relative equal highs. A peak is higher than the candle before and not lower than the one after, so a flat top
    counts once. Their range, or None."""
    seg = np.asarray(h[max(0, lo - 1):hi], float)
    first = 1 if lo >= 1 else 0
    peaks = sorted(float(seg[i]) for i in range(max(first, 1), len(seg) - 1)   # a peak, or a flat top's first candle
                   if seg[i] > seg[i - 1] and seg[i] >= seg[i + 1] and seg[i] < below)
    for a, b in zip(peaks, peaks[1:]):
        if b - a <= tolerance:
            return a, b
    return None


def tight_range(h, l, lo: int, hi: int, width: float, candles: int = 6) -> bool:
    """At least ``candles`` consecutive candles in [lo, hi) inside a range narrower than ``width``."""
    for s in range(lo, hi - candles + 1):
        if max(h[s:s + candles]) - min(l[s:s + candles]) < width:
            return True
    return False
