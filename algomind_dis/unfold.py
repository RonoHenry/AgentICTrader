"""AlgoMindDIS v4, the week as it unfolds (algomind-dis Requirement 19; H-AP, registered 2026-11-09 in 3bf3e87 before
this code).

Every side source before this called the week from a snapshot. v4 opens each week with no side, sets one from what
price does during the week, and withdraws it when the side's own arrays fail. It reads the Thesis Engine's book (the
analyzers' arrays and swings as of each close) and returns plain records, so ``thesis_engine`` depends on it and not
the other way round.

Frozen with the registration (docs/research/SEARCH_2018_2024.md, "H-AP"). Bullish is written out, bearish is the mirror:

- **An event,** on H1, the child of the D1 pools: a run of down-closing candles ``first..last`` closed through by
  ``through`` (the CISD); a candle of ``first..through`` first traded below a pool of D1 or larger; the move away left
  an FVG at ``g`` in ``last+1..through+1``; the commit is the close of ``max(through, g)``; that close is above every
  pool taken; and the lowest low X of ``first..commit`` lies within ``[a.low - 0.1 ADR, a.high]`` of a bullish H4 or
  D1 array completed before the run's first candle opened and live at the commit.
- **The hold:** the first event sets the side, a later event of the same side changes nothing, an event of the other
  side replaces it, and after a side ends the next event can set a new one.
- **The geometry:** the protected level is X. The draw is the nearest of the last closed W1's high and the untaken D1
  swing highs at least 0.5 ADR above the commit close; over 5 ADR, or none, and the event is refused.
- **The ends:** delivered and invalidated are the Thesis Engine's own; the week's close expires it; the second close
  after the commit beyond the far edge of a bullish H4 or D1 array lying wholly above the protected level withdraws
  it. A close, not a wick, so a sweep against the side stays manipulation.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from liquidity_engine.context.blocks import runs

__all__ = ["ARRAY_FRAMES", "BAND_ADR", "Event", "MAX_ADR", "MIN_ADR", "Read", "WITHDRAW_AFTER", "events", "gap_candle",
           "mirror_geometry", "pools_taken", "reachable_draw", "reads", "withdrawn_at"]

BAND_ADR = 0.1                                   # V1's pool_band_adr
MIN_ADR, MAX_ADR = 0.5, 5.0                      # the Thesis Engine's completion limits
WITHDRAW_AFTER = 2
ARRAY_FRAMES = ("H4", "D1")
_BULL, _BEAR = "BULLISH", "BEARISH"
OTHER = {_BULL: _BEAR, _BEAR: _BULL}


@dataclass(frozen=True)
class Event:
    side: str
    t: int                       # the commit's close, UTC ns
    price: float                 # the commit's close
    own: float                   # X: the reaction's extreme, the side's protected level
    other: float                 # the opposite extreme of first..commit, the mirror's protected level
    first: int                   # the H1 run and its CISD
    last: int
    through: int
    commit: int
    pools: Tuple[float, ...]     # the pools the run took
    array_id: str                # the array it reacted at


@dataclass(frozen=True)
class Read:
    """One held side."""
    event: Event
    side: str
    draw: float
    protected: float
    since: int
    until: int
    reason: str                  # what ``until`` passing is: EXPIRED or WITHDRAWN


def gap_candle(h, l, last: int, through: int, bullish: bool) -> Optional[int]:
    """The candle that completes the first FVG the move away left, in ``last+1..through+1``; None without one."""
    for g in range(max(2, last + 1), min(len(h), through + 2)):
        if (l[g] > h[g - 2]) if bullish else (h[g] < l[g - 2]):
            return g
    return None


def _known_pools(book, n: int, m: int, bullish: bool) -> List[Tuple[float, int]]:
    """(price, the time it was known) for the pools a side's run can take, with ``n`` D1 and ``m`` W1 candles closed."""
    d1, w1 = book.frames["D1"], book.frames["W1"]
    out: List[Tuple[float, int]] = []
    if n > 0:
        known = int(d1.c.end[n - 1])
        out.append((float(d1.c.l[n - 1] if bullish else d1.c.h[n - 1]), known))
        out += [(float(p), known) for p in d1.untaken(n, lows=bullish)]
    if m > 0:
        out.append((float(w1.c.l[m - 1] if bullish else w1.c.h[m - 1]), int(w1.c.end[m - 1])))
    return out


def pools_taken(book, bullish: bool) -> Dict[int, List[float]]:
    """For each H1 candle, the D1-or-larger pools it was first to trade beyond since each was known."""
    h1, d1, w1 = book.frames["H1"].c, book.frames["D1"], book.frames["W1"]
    x = h1.l if bullish else h1.h
    out: Dict[int, List[float]] = {}
    cache: Dict[Tuple[int, int], List[Tuple[float, int]]] = {}
    for j in range(len(h1)):
        at = int(h1.t[j])
        key = (d1.n(at), w1.n(at))
        if key not in cache:
            cache[key] = _known_pools(book, *key, bullish)
        for price, known in cache[key]:
            if not (x[j] < price if bullish else x[j] > price):
                continue
            before = x[int(np.searchsorted(h1.t, known, "left")):j]
            if bool((before >= price).all()) if bullish else bool((before <= price).all()):
                out.setdefault(j, []).append(price)
    return out


def _array_at(book, side: str, x: float, t: int, before: int):
    """A live H4 or D1 array of the side, completed by ``before``, that the reaction's extreme ``x`` is at."""
    adr = book.adr(t)
    if not np.isfinite(adr) or adr <= 0:
        return None
    band = BAND_ADR * adr
    for tf in ARRAY_FRAMES:
        frame = book.frames[tf]
        for a in frame.live(frame.n(t), side):
            if a.formed_at > before:
                continue
            if (a.low - band <= x <= a.high) if side == _BULL else (a.low <= x <= a.high + band):
                return a
    return None


def events(book) -> List[Event]:
    """Every event of the market, in time order. Each reads only candles up to its own commit."""
    h1 = book.frames["H1"].c
    out: List[Event] = []
    for bullish in (True, False):
        side = _BULL if bullish else _BEAR
        taken = pools_taken(book, bullish)
        for first, last, through in runs(h1.o, h1.c, bullish):
            swept = [p for j in range(first, through + 1) for p in taken.get(j, ())]
            if not swept:
                continue
            g = gap_candle(h1.h, h1.l, last, through, bullish)
            if g is None:
                continue
            commit = max(through, g)
            close = float(h1.c[commit])
            if not (close > max(swept) if bullish else close < min(swept)):
                continue
            low, high = float(h1.l[first:commit + 1].min()), float(h1.h[first:commit + 1].max())
            own, other = (low, high) if bullish else (high, low)
            t = int(h1.end[commit])
            array = _array_at(book, side, own, t, int(h1.t[first]))
            if array is None:
                continue
            out.append(Event(side, t, close, own, other, first, last, through, commit, tuple(sorted(set(swept))), array.id))
    return sorted(out, key=lambda e: (e.t, e.side))


def reachable_draw(book, side: str, t: int, price: float) -> Optional[float]:
    """The nearest of the last closed W1's extreme and the untaken D1 swings at least 0.5 ADR beyond ``price`` on
    ``side``; None when there is none, or it is over 5 ADR away."""
    adr = book.adr(t)
    if not np.isfinite(adr) or adr <= 0:
        return None
    bullish = side == _BULL
    d1, w1 = book.frames["D1"], book.frames["W1"]
    n, m = d1.n(t), w1.n(t)
    pools: List[float] = []
    if m > 0:
        pools.append(float(w1.c.h[m - 1] if bullish else w1.c.l[m - 1]))
    if n > 0:
        pools += [float(p) for p in d1.untaken(n, lows=not bullish)]
    ahead = [p for p in pools if (p >= price + MIN_ADR * adr if bullish else p <= price - MIN_ADR * adr)]
    if not ahead:
        return None
    draw = min(ahead) if bullish else max(ahead)
    return draw if abs(draw - price) <= MAX_ADR * adr else None


def mirror_geometry(book, r: Read) -> Optional[Tuple[str, float, float]]:
    """(side, draw, protected) of the opposite side at the same commit; None when it has no draw (H-AP's MIRROR)."""
    side = OTHER[r.side]
    draw = reachable_draw(book, side, r.event.t, r.event.price)
    return None if draw is None else (side, draw, r.event.other)


def withdrawn_at(low: np.ndarray, high: np.ndarray, ends: np.ndarray, bullish: bool, protected: float, since: int,
                 until: int, after: int = WITHDRAW_AFTER) -> Optional[int]:
    """The time of the ``after``-th close in (since, until] beyond the far edge of a side's array lying wholly on the
    draw's side of the protected level; None if there are fewer. ``ends`` holds each array's closing time."""
    lying = low > protected if bullish else high < protected
    hit = np.sort(ends[lying & (ends > since) & (ends <= until)])
    return int(hit[after - 1]) if len(hit) >= after else None


class _Arrays:
    """Each side's H4 and D1 arrays as arrays: low, high and the time of the close that ended each (none: never)."""

    def __init__(self, book) -> None:
        rows: Dict[str, list] = {_BULL: [], _BEAR: []}
        never = np.iinfo(np.int64).max
        for tf in ARRAY_FRAMES:
            frame = book.frames[tf]
            for r in frame.rows:
                ended = int(frame.c.end[r.end]) if r.end < len(frame.c) else never
                rows[r.side].append((r.low, r.high, ended))
        self.tables = {side: (np.array([x[0] for x in v], dtype=float), np.array([x[1] for x in v], dtype=float),
                              np.array([x[2] for x in v], dtype=np.int64)) for side, v in rows.items()}

    def withdrawn(self, side: str, protected: float, since: int, until: int) -> Optional[int]:
        return withdrawn_at(*self.tables[side], side == _BULL, protected, since, until)


def _ended_by(book, r: Read) -> int:
    """When a read stops being held: its ``until``, or the Thesis Engine's invalidation or delivery if earlier."""
    d1, e, bullish, end = book.frames["D1"].c, book.e, r.side == _BULL, r.until
    a, b = int(np.searchsorted(d1.end, r.since, "right")), int(np.searchsorted(d1.end, r.until, "right"))
    hit = np.flatnonzero(d1.c[a:b] < r.protected if bullish else d1.c[a:b] > r.protected)
    if len(hit):
        end = min(end, int(d1.end[a + int(hit[0])]))
    i, j = int(np.searchsorted(e.t, r.since, "left")), int(np.searchsorted(e.end, r.until, "right"))
    hit = np.flatnonzero(e.h[i:j] >= r.draw if bullish else e.l[i:j] <= r.draw)
    if len(hit):
        end = min(end, int(e.end[i + int(hit[0])]))
    return end


def reads(book, evs: Sequence[Event], withdraw: bool = True) -> Tuple[List[Read], Counter]:
    """The sides held through the events, and the events refused by reason. ``withdraw`` False is H-AP's NO_WITHDRAW."""
    w1 = book.frames["W1"].c
    arrays = _Arrays(book)
    out: List[Read] = []
    refused: Counter = Counter()
    held: Optional[Read] = None
    held_end = 0
    for ev in sorted(evs, key=lambda e: (e.t, e.side)):
        w = int(np.searchsorted(w1.t, ev.t, "right")) - 1
        if w < 0 or ev.t >= int(w1.end[w]):                # at the week's close there is no week left to hold
            refused["at the week's close"] += 1
            continue
        if held is not None and ev.t >= held_end:
            held = None
        if held is not None and ev.side == held.side:
            continue
        draw = reachable_draw(book, ev.side, ev.t, ev.price)
        if draw is None:
            refused["no reachable draw"] += 1
            continue
        until, reason = int(w1.end[w]), "EXPIRED"
        if withdraw:
            pulled = arrays.withdrawn(ev.side, ev.own, ev.t, until)
            if pulled is not None and pulled < until:
                until, reason = pulled, "WITHDRAWN"
        if held is not None:                               # replaced by an event of the other side
            out[-1] = replace(held, until=ev.t, reason="WITHDRAWN")
        held = Read(ev, ev.side, draw, ev.own, ev.t, until, reason)
        held_end = _ended_by(book, held)
        out.append(held)
    return out, refused
