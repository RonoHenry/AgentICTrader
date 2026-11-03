"""PD array context (algomind-dis Requirement 6, §6): each of the engine's arrays judged in its context, so that an
array alone never sets a bias.

The arrays are the engine's (``frame_state._arrays``: FVGs as the gap, order blocks and breakers, both ways), each
dated by the close of the candle that completes it. Each gets §6.2's evaluations:
- price's location against it;
- its parent SWING range and the zone of its near edge;
- whether a displacement candle (``ranges.displacements``) of its direction is among the three candles that made it;
- whether a sweep came within ``sweep_window`` candles before it: a candle trading beyond the latest known swing on
  the other side (under a swing low, for a bullish array);
- whether it agrees with the W1 structural direction;
- mitigation (a later candle traded into its near edge) and invalidation (a later close beyond its far edge).

Listed: the valid arrays, and those invalidated in the last ``sweep_window`` candles. The replay passes the full
frame's arrays once (``raw``); each array is dated, so the ones formed by a cut's last close are the cut's own.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from algomind_dis.analyzers.ranges import displacements, zone
from algomind_dis.analyzers.structure import LOOKBACK, swings
from algomind_dis.records import ArrayContext, DealingRange, make_id
from algomind_dis.settings import V1, Settings
from liquidity_engine.context.frame_state import Candles, _Array, _arrays
from liquidity_engine.models import BiasDirection

__all__ = ["arrays", "counts", "reacting"]

_SIDE_ZONES = {"BULLISH": ("DISCOUNT", "DEEP_DISCOUNT"), "BEARISH": ("PREMIUM", "DEEP_PREMIUM")}


def _swept(c: Candles) -> tuple[np.ndarray, np.ndarray]:
    """Per candle: whether it traded under the latest swing low known before it, and over the latest swing high."""
    n = len(c)
    low_level = np.full(n, np.nan)
    high_level = np.full(n, np.nan)
    for s in swings(c):
        first = s.index + LOOKBACK + 1                           # known once candle index + 2 has closed
        (high_level if s.is_high else low_level)[first:] = s.price
    with np.errstate(invalid="ignore"):
        return c.l < low_level, c.h > high_level


def arrays(market: str, c: Candles, price: float, rng: Optional[DealingRange], w1_direction: str,
           s: Settings = V1, raw: Optional[Sequence[_Array]] = None) -> tuple[ArrayContext, ...]:
    n = len(c)
    if not n:
        return ()
    last = int(c.end[-1])
    found = [a for a in (_arrays(c) if raw is None else raw) if a.formed_at <= last]
    disp = displacements(c, s)
    under, over = _swept(c)
    out = []
    for a in found:
        k = int(np.searchsorted(c.end, a.formed_at, "left"))
        bullish = a.direction == BiasDirection.BULLISH
        sign = 1 if bullish else -1
        later = slice(k + 1, n)
        breach = np.flatnonzero(c.c[later] < a.low if bullish else c.c[later] > a.high)
        if len(breach) and k + 1 + int(breach[0]) < n - s.sweep_window:
            continue                                             # failed long ago
        invalidated = int(c.end[k + 1 + int(breach[0])]) if len(breach) else None
        near = a.high if bullish else a.low
        mitigated = bool(len(np.flatnonzero(c.l[later] <= near if bullish else c.h[later] >= near)))
        location = "ABOVE" if price > a.high else "BELOW" if price < a.low else "INSIDE"
        made = slice(max(0, k - 2), k + 1)
        before = slice(max(0, k - s.sweep_window), k + 1)
        out.append(ArrayContext(
            make_id(market, c.tf, a.kind, a.direction.value, a.formed_at, a.low, a.high), market, c.tf, a.kind,
            a.direction.value, float(a.low), float(a.high), int(a.formed_at), location,
            rng.id if rng is not None else None, zone(rng.position(near), s) if rng is not None else None,
            bool((disp[made] == sign).any()), bool((under if bullish else over)[before].any()),
            a.direction.value == w1_direction, mitigated, invalidated is None, invalidated))
    return tuple(out)


def reacting(a: ArrayContext, c: Candles, s: Settings = V1) -> bool:
    """Price is in the array, or traded into it in the last ``sweep_window`` candles and closed on its side."""
    if a.location == "INSIDE":
        return True
    recent = slice(max(0, len(c) - s.sweep_window), len(c))
    after = c.t[recent] >= a.formed_at
    if a.direction == "BULLISH":
        touched = (c.l[recent] <= a.high) & after
        return bool(touched.any()) and a.location == "ABOVE"
    touched = (c.h[recent] >= a.low) & after
    return bool(touched.any()) and a.location == "BELOW"


def counts(a: ArrayContext, c: Candles, s: Settings = V1) -> bool:
    """Requirement 6.3: directional evidence only when valid, in its side's zone, and price in it or just off it."""
    return a.valid and a.zone in _SIDE_ZONES[a.direction] and reacting(a, c, s)
