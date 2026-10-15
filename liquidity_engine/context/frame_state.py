"""A frame's state for Model A (context-engine Requirement 3, the parts Model A reads; update 2026-10-15).

The dealing range and price's zone in it (step 1, premium/discount), and the frame's bearish points of interest
(step 2): untouched order blocks, breakers and fair value gaps whose near edge is in premium, and the untaken
liquidity above price (swing highs, equal highs, previous candles' highs). Read from the frame's closed candles
only; the forming candle's extremes stretch the range. Written for shorts; longs read the mirrored bars.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from liquidity_engine.context.measures import (bearish_breakers, bearish_fvgs, bearish_order_blocks, swing_highs,
                                               swing_lows)

__all__ = ["Candidate", "DealingRange", "POI", "PREMIUM_FROM", "DISCOUNT_BELOW", "bearish_candidates", "bearish_pois",
           "dealing_range", "select_pois"]

#: CE-D2: equilibrium is within 5% either side of the middle.
PREMIUM_FROM, DISCOUNT_BELOW = 0.55, 0.45
#: MA-D2: liquidity and equal highs are read within 0.1 of the frame's average range.
LIQUIDITY_BAND = 0.1


@dataclass(frozen=True)
class DealingRange:
    low: float
    high: float
    low_at: int                  # the frame index of the swing low and swing high it is anchored on
    high_at: int

    def position(self, price: float) -> float:
        return (price - self.low) / (self.high - self.low) if self.high > self.low else 0.5

    def zone(self, price: float) -> str:
        p = self.position(price)
        return "PREMIUM" if p > PREMIUM_FROM else "DISCOUNT" if p < DISCOUNT_BELOW else "EQUILIBRIUM"

    @property
    def premium_floor(self) -> float:
        return self.low + PREMIUM_FROM * (self.high - self.low)

    @property
    def anchors(self) -> Tuple[int, int]:
        return self.low_at, self.high_at

    def reason(self) -> str:
        return f"range {self.low:.5g}-{self.high:.5g}"


def dealing_range(h, l, n_closed: int, forming_high: Optional[float] = None,
                  forming_low: Optional[float] = None, lookback: int = 2) -> Optional[DealingRange]:
    """From the last confirmed swing low to the last confirmed swing high among the closed candles, each
    stretched to any later extreme beyond it, the forming candle's included (CE-D2). None without a swing on
    either side."""
    h, l = np.asarray(h[:n_closed], float), np.asarray(l[:n_closed], float)
    highs, lows = swing_highs(h, lookback), swing_lows(l, lookback)
    if not highs or not lows:
        return None
    i_h, i_l = highs[-1], lows[-1]
    high = float(h[i_h:].max())
    low = float(l[i_l:].min())
    if forming_high is not None:
        high = max(high, forming_high)
    if forming_low is not None:
        low = min(low, forming_low)
    return DealingRange(low, high, i_l, i_h)


@dataclass(frozen=True)
class POI:
    kind: str                    # OB, BREAKER, FVG, SWING_HIGH, EQUAL_HIGHS, or a previous candle's high (PDH, PWH...)
    low: float
    high: float
    formed: int                  # the frame index it formed at (-1 for a level read from another frame)
    label: str

    def reason(self) -> str:
        return f"{self.label} {self.low:.5g}-{self.high:.5g}"


def _untouched(h: np.ndarray, start: int, end: int, level: float) -> bool:
    """No candle in [start, end) traded up to ``level``."""
    return start >= end or float(h[start:end].max()) < level


@dataclass(frozen=True)
class Candidate:
    """A POI as the closed candles leave it; whether it is in premium and above price is read at the time."""
    poi: POI
    level: Optional[float] = None     # liquidity: the level itself, which the forming candle may take


def bearish_candidates(o, h, l, c, n_closed: int, avg_range: float, levels: Iterable[Tuple[str, float]] = (),
                       tf: str = "") -> List[Candidate]:
    """The frame's bearish POIs as of its closed candles (MA-D2), price aside:
    - order blocks, breakers and fair value gaps not traded into since they formed;
    - untaken swing highs and equal highs, each as its level +/- 0.1 average ranges;
    - ``levels``: previous candles' highs of this frame and the frames above, (label, price)."""
    o, h, l, c = (np.asarray(x[:n_closed], float) for x in (o, h, l, c))
    n, band = n_closed, LIQUIDITY_BAND * avg_range
    out: List[Candidate] = []
    for j, i, low, high in bearish_order_blocks(o, h, l, c, n):
        if _untouched(h, i + 1, n, low):
            out.append(Candidate(POI("OB", low, high, j, f"{tf} bearish OB")))
    for k, low, high in bearish_breakers(o, h, l, c, n):
        if _untouched(h, k + 1, n, low):
            out.append(Candidate(POI("BREAKER", low, high, k, f"{tf} bearish breaker")))
    for k, low, high in bearish_fvgs(h, l, 0, n):
        if _untouched(h, k + 1, n, low):
            out.append(Candidate(POI("FVG", low, high, k, f"{tf} bearish FVG")))
    untaken = [s for s in swing_highs(h) if _untouched(h, s + 1, n, h[s] + 1e-12)]
    for s in untaken:
        out.append(Candidate(POI("SWING_HIGH", h[s] - band, h[s] + band, s, f"{tf} swing high"), float(h[s])))
    peaks = sorted(untaken, key=lambda s: h[s])
    for a, b in zip(peaks, peaks[1:]):
        if h[b] - h[a] <= band:
            out.append(Candidate(POI("EQUAL_HIGHS", h[a] - band, h[b] + band, max(a, b), f"{tf} equal highs"), float(h[a])))
    for label, level in levels:
        if level is not None and np.isfinite(level):
            out.append(Candidate(POI(label, level - band, level + band, -1, label), float(level)))
    return out


def select_pois(candidates: Sequence[Candidate], rng: DealingRange, price: float,
                forming_high: Optional[float] = None) -> List[POI]:
    """The candidates that are POIs now: near edge in premium, above ``price``, and, for liquidity, not yet taken
    by the forming candle. Nearest first, each zone once."""
    taken_by = forming_high if forming_high is not None else -np.inf
    floor = rng.premium_floor
    keep = {}
    for cand in candidates:
        p = cand.poi
        if p.low >= floor and p.high > price and (cand.level is None or cand.level > taken_by):
            keep.setdefault((p.kind, round(p.low, 10), round(p.high, 10)), p)
    return sorted(keep.values(), key=lambda p: (p.low, p.high))


def bearish_pois(o, h, l, c, n_closed: int, price: float, rng: DealingRange, avg_range: float,
                 levels: Iterable[Tuple[str, float]] = (), forming_high: Optional[float] = None,
                 tf: str = "") -> List[POI]:
    """``bearish_candidates`` selected at ``price``: the frame's bearish POIs above price, nearest first."""
    return select_pois(bearish_candidates(o, h, l, c, n_closed, avg_range, levels, tf), rng, price, forming_high)
