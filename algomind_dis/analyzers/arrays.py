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

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from algomind_dis.analyzers.ranges import displacements, zone
from algomind_dis.analyzers.structure import LOOKBACK, swings
from algomind_dis.records import ArrayContext, DealingRange, make_id
from algomind_dis.settings import V1, Settings
from liquidity_engine.context.blocks import delivery_blocks
from liquidity_engine.context.frame_state import Candles, _Array, _arrays
from liquidity_engine.context.measures import bearish_fvgs, mirror
from liquidity_engine.models import BiasDirection

__all__ = ["ArrayTable", "array_table", "arrays", "counts", "in_play", "raw_arrays", "reacting"]

_SIDE_ZONES = {"BULLISH": ("DISCOUNT", "DEEP_DISCOUNT"), "BEARISH": ("PREMIUM", "DEEP_PREMIUM")}


def raw_arrays(c: Candles, s: Settings = V1) -> list:
    """The frame's arrays by ``s.array_rule``: the engine's (``frame_state._arrays``), or the trader's order blocks
    and breakers (``blocks.delivery_blocks``, each dated by the close that made it) with the fair value gaps as their
    script draws them (the gap between candle one's high and candle three's low)."""
    if s.array_rule == "engine":
        return _arrays(c)
    out = [_Array(b.direction, b.kind, c.tf, b.low, b.high, int(c.end[b.formed]))
           for b in delivery_blocks(c.o, c.h, c.l, c.c)]
    for k, lo, hi in bearish_fvgs(c.h, c.l, 0, len(c)):
        out.append(_Array(BiasDirection.BEARISH, "FVG", c.tf, lo, hi, int(c.end[k])))
    mo, mh, ml, mc = mirror(c.o, c.h, c.l, c.c)
    for k, lo, hi in bearish_fvgs(mh, ml, 0, len(c)):
        out.append(_Array(BiasDirection.BULLISH, "FVG", c.tf, -hi, -lo, int(c.end[k])))
    return out


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
    found = [a for a in (raw_arrays(c, s) if raw is None else raw) if a.formed_at <= last]
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


_NEVER = np.iinfo(np.int64).max


@dataclass(frozen=True)
class ArrayTable:
    """A frame's arrays over its full history (the replay's): each one's forming index, the first later close
    beyond its far edge and the first later trade into its near edge (``_NEVER``: none), and its two
    formation-time flags. Each reads only candles up to its own index, so a cut reads its entries below n."""
    raw: list
    k: np.ndarray
    low: np.ndarray
    high: np.ndarray
    bullish: np.ndarray
    formed: np.ndarray
    breach: np.ndarray
    touch: np.ndarray
    displaced: np.ndarray
    swept: np.ndarray


def array_table(c: Candles, s: Settings = V1) -> ArrayTable:
    raw = raw_arrays(c, s)
    n = len(c)
    disp = displacements(c, s)
    under, over = _swept(c)
    rows = []
    for a in raw:
        k = int(np.searchsorted(c.end, a.formed_at, "left"))
        bullish = a.direction == BiasDirection.BULLISH
        later = slice(k + 1, n)
        b = np.flatnonzero(c.c[later] < a.low if bullish else c.c[later] > a.high)
        near = a.high if bullish else a.low
        t = np.flatnonzero(c.l[later] <= near if bullish else c.h[later] >= near)
        sign = 1 if bullish else -1
        rows.append((k, a.low, a.high, bullish, a.formed_at, k + 1 + int(b[0]) if len(b) else _NEVER,
                     k + 1 + int(t[0]) if len(t) else _NEVER, bool((disp[max(0, k - 2):k + 1] == sign).any()),
                     bool((under if bullish else over)[max(0, k - s.sweep_window):k + 1].any())))
    cols = list(zip(*rows)) if rows else [()] * 9
    types = (np.int64, float, float, bool, np.int64, np.int64, np.int64, bool, bool)
    return ArrayTable(raw, *(np.array(col, dtype=dt) for col, dt in zip(cols, types)))


def in_play(market: str, c: Candles, price: float, rng: Optional[DealingRange], w1_direction: str,
            table: ArrayTable, s: Settings = V1) -> tuple[ArrayContext, ...]:
    """``tuple(a for a in arrays(...) if reacting(a, c))``, read from the table (the replay's)."""
    n = len(c)
    if not n or not len(table.k):
        return ()
    keep = (table.k <= n - 1) & ~((table.breach < n) & (table.breach < n - s.sweep_window))
    inside = (table.low <= price) & (price <= table.high)
    above, below = price > table.high, price < table.low
    j = np.arange(max(0, n - s.sweep_window), n)
    after = c.t[j][None, :] >= table.formed[:, None]
    hit = np.where(table.bullish[:, None], c.l[j][None, :] <= table.high[:, None],
                   c.h[j][None, :] >= table.low[:, None])
    touched = (after & hit).any(axis=1)
    play = inside | (touched & np.where(table.bullish, above, below))
    out = []
    for i in np.flatnonzero(keep & play):
        a = table.raw[i]
        near = a.high if table.bullish[i] else a.low
        breach = int(table.breach[i])
        out.append(ArrayContext(
            make_id(market, c.tf, a.kind, a.direction.value, a.formed_at, a.low, a.high), market, c.tf, a.kind,
            a.direction.value, float(a.low), float(a.high), int(a.formed_at),
            "INSIDE" if inside[i] else "ABOVE" if above[i] else "BELOW", rng.id if rng is not None else None,
            zone(rng.position(near), s) if rng is not None else None, bool(table.displaced[i]),
            bool(table.swept[i]), a.direction.value == w1_direction, bool(table.touch[i] < n), breach >= n,
            int(c.end[breach]) if breach < n else None))
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
