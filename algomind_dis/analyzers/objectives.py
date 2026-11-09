"""Liquidity objectives (algomind-dis Requirement 5, §5.4): the pools and gaps that could draw price, typed, with
their status, ranked by significance rather than distance.

The pools and gaps are the engine's (``frame_state._objectives``: swing highs and lows, the previous candle's high
and low, gaps at their near edge), plus each frame's SWING range high and low. Their type:
- **EXTERNAL:** a range's high or low, and swings at or beyond their frame's SWING range;
- **INTERNAL:** swings inside the range, and gaps;
- **TEMPORAL:** the previous candle's high and low (PDH/PDL, PWH/PWL, PMH/PML).

Two untaken swings of a side within a tenth of their frame's average range of each other are relative equal highs
or lows (``EQUAL_HIGHS``, ``EQUAL_LOWS``). An objective is followed on the finest frame given (``path``, D1 by
default) from the close of the candle that made it: a pool is SWEPT by the first candle trading beyond it, a gap
MITIGATED by the first trading into its near edge. One taken more than ``sweep_window`` candles ago is consumed and
no longer listed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import numpy as np

from algomind_dis.records import DealingRange, LiquidityObjective, make_id
from algomind_dis.settings import V1, Settings
from liquidity_engine.context.frame_state import LIQUIDITY_BAND, Candles, Objective, _objectives
from liquidity_engine.context.measures import average_range
from liquidity_engine.models import BiasDirection

__all__ = ["LIVE", "ObjectiveTable", "adr", "objective_table", "objectives", "primary_objective", "ranked"]

LIVE = ("IDENTIFIED", "APPROACHING")
_TEMPORAL = {"PDH", "PDL", "PWH", "PWL", "PMH", "PML"}
_BULL = BiasDirection.BULLISH


def adr(d1: Candles, s: Settings = V1) -> float:
    """The mean D1 range of the last ``adr_days`` closed days."""
    return average_range(d1.h, d1.l, len(d1), s.adr_days)


def _kind(x: Objective, rng: Optional[DealingRange]) -> str:
    if x.source in _TEMPORAL or x.source in (f"P{x.tf}H", f"P{x.tf}L"):     # frame_state's previous-candle names
        return "TEMPORAL"
    if x.source in ("RANGE_HIGH", "RANGE_LOW"):
        return "EXTERNAL"
    if x.kind == "FVG" or rng is None:
        return "INTERNAL"
    if x.direction == _BULL:
        return "EXTERNAL" if x.price >= rng.high else "INTERNAL"
    return "EXTERNAL" if x.price <= rng.low else "INTERNAL"


def _range_extremes(c: Candles, rng: DealingRange) -> list[Objective]:
    hi = int(np.flatnonzero(c.h == rng.high)[-1])
    lo = int(np.flatnonzero(c.l == rng.low)[-1])
    return [Objective("POOL", "RANGE_HIGH", c.tf, float(rng.high), _BULL, int(c.end[hi])),
            Objective("POOL", "RANGE_LOW", c.tf, float(rng.low), BiasDirection.BEARISH, int(c.end[lo]))]


def _taken(path: Candles, x: Objective) -> Optional[int]:
    """The index on ``path`` of the first candle opening at or after ``x`` was made that took it."""
    a = int(np.searchsorted(path.t, x.formed_at, "left"))
    if x.kind == "FVG":
        hit = path.h[a:] >= x.price if x.direction == _BULL else path.l[a:] <= x.price
    else:
        hit = path.h[a:] > x.price if x.direction == _BULL else path.l[a:] < x.price
    k = np.flatnonzero(hit)
    return a + int(k[0]) if len(k) else None


def _equal(found: list[Objective], c: Candles) -> set[int]:
    """Indices into ``found`` of the frame's untaken swings within a tenth of its average range of another."""
    band = LIQUIDITY_BAND * average_range(c.h, c.l, len(c))
    out: set[int] = set()
    for source in ("SWING_HIGH", "SWING_LOW"):
        idx = [i for i, x in enumerate(found) if x.source == source]
        for a in idx:
            for b in idx:
                if a < b and abs(found[a].price - found[b].price) <= band:
                    out |= {a, b}
    return out


@dataclass(frozen=True)
class ObjectiveTable:
    """A frame's swing and gap objectives over its full history (the replay's): each one's index in the frame when
    it is known, and the index on the full D1 path of the candle that first took it (-1: never)."""
    groups: tuple                                   # (objectives, known, taken) for highs, lows and gaps


def objective_table(c: Candles, path: Candles) -> ObjectiveTable:
    found = _objectives(c, previous=False)
    groups = []
    for source in ("SWING_HIGH", "SWING_LOW", "FVG"):
        xs = [x for x in found if x.source == source]
        at = np.searchsorted(c.end, np.array([x.formed_at for x in xs], dtype=np.int64), "left")
        known = at + (0 if source == "FVG" else 2)               # a swing is known two candles on (lookback 2)
        taken = [_taken(path, x) for x in xs]
        groups.append((xs, known.astype(np.int64), np.array([-1 if k is None else k for k in taken], np.int64)))
    return ObjectiveTable(tuple(groups))


def _found(c: Candles, path: Candles, table: Optional[ObjectiveTable]) -> tuple[list, list]:
    """``frame_state._objectives(c, previous=True)`` and each one's taken index on ``path``; from the table, the
    entries known by the cut's last candle, in the same order."""
    if table is None:
        found = list(_objectives(c, previous=True))
        return found, [_taken(path, x) for x in found]
    n, m = len(c), len(path)
    (hx, hk, ht), (lx, lk, lt), (gx, gk, gt) = table.groups
    last = Candles(c.tf, c.t[-1:], c.end[-1:], c.o[-1:], c.h[-1:], c.l[-1:], c.c[-1:])
    previous = list(_objectives(last, previous=True))           # one candle: only its high and low
    found: list = []
    taken: list = []
    for xs, known, tk in ((hx, hk, ht), (lx, lk, lt)):
        k = int(np.searchsorted(known, n - 1, "right"))
        found += xs[:k]
        taken += [int(v) if 0 <= v < m else None for v in tk[:k]]
    found += previous
    taken += [_taken(path, x) for x in previous]
    k = int(np.searchsorted(gk, n - 1, "right"))
    found += gx[:k]
    taken += [int(v) if 0 <= v < m else None for v in gt[:k]]
    return found, taken


def objectives(market: str, frames: Mapping[str, Candles], price: float,
               ranges_by_tf: Mapping[str, Sequence[DealingRange]], s: Settings = V1,
               path: Optional[Candles] = None,
               tables: Optional[Mapping[str, ObjectiveTable]] = None) -> tuple[LiquidityObjective, ...]:
    """Every frame's live objectives, and those swept or mitigated in the last ``sweep_window`` candles of ``path``.
    The replay passes each frame's ``objective_table``; the result is the same."""
    d1 = frames["D1"]
    path = d1 if path is None else path
    daily = adr(d1, s)
    recent = len(path) - s.sweep_window
    out: list[LiquidityObjective] = []
    for tf, c in frames.items():
        if not len(c):
            continue
        rng = next((r for r in ranges_by_tf.get(tf, ()) if r.kind == "SWING"), None)
        found, taken = _found(c, path, tables.get(tf) if tables else None)
        if rng is not None:
            extremes = _range_extremes(c, rng)
            found += extremes
            taken += [_taken(path, x) for x in extremes]
        live = [x if k is None else None for x, k in zip(found, taken)]
        equal = _equal([x for x in live if x is not None], c)
        live_idx = [i for i, x in enumerate(live) if x is not None]
        equal_idx = {live_idx[j] for j in equal}
        tfw = s.timeframe_weights.get(tf, 0.0)
        for i, (x, k) in enumerate(zip(found, taken)):
            if k is not None and k < recent:
                continue                                    # consumed
            source = x.source
            if i in equal_idx:
                source = "EQUAL_HIGHS" if x.source == "SWING_HIGH" else "EQUAL_LOWS"
            kind = _kind(x, rng)
            significance = tfw * s.type_weights[kind] + (s.equal_bonus if i in equal_idx else 0.0)
            if k is None:
                near = np.isfinite(daily) and abs(price - x.price) <= s.approaching_adr * daily
                status, swept_at, back = ("APPROACHING" if near else "IDENTIFIED"), None, False
            else:
                status = "MITIGATED" if x.kind == "FVG" else "SWEPT"
                swept_at = int(path.end[k])
                back = bool(path.c[k] < x.price) if x.direction == _BULL else bool(path.c[k] > x.price)
            out.append(LiquidityObjective(make_id(market, tf, source, x.formed_at, x.price), market, tf,
                                          float(x.price), kind, source, x.direction.value,
                                          rng.id if rng is not None else None, status, float(significance),
                                          int(x.formed_at), swept_at, back))
    return tuple(out)


def ranked(objs: Sequence[LiquidityObjective], side: str) -> list[LiquidityObjective]:
    """``side``'s live objectives, most significant first, then nearest (the lowest above, the highest below)."""
    sign = 1 if side == "BULLISH" else -1
    return sorted((o for o in objs if o.side == side and o.status in LIVE),
                  key=lambda o: (-o.significance, sign * o.price, o.source))


def primary_objective(objs: Sequence[LiquidityObjective], side: str) -> Optional[LiquidityObjective]:
    r = ranked(objs, side)
    return r[0] if r else None
