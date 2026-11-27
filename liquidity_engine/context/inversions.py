"""Inverted fair value gaps on arrays (thesis-engine Requirement 3.5): the detection the array layer lacked.

A fair value gap is the gap only (``measures.bearish_fvgs``, mirrored for bullish ones), as AlgoMindDIS V2 reads it.
When a candle closes beyond the gap's far edge (below a bullish gap's low, above a bearish gap's high) the gap
fails, and from that close it is an **inverted FVG** of the other side over the same prices: a failed support
becomes resistance, and the mirror. What ends an inverted FVG is read like any array's end: a later close beyond
its own far edge (``algomind_dis.analyzers.arrays.array_table``'s breach).

Each one is dated by the close that inverted it and reads only candles up to that close, so a cut of the frame
holds exactly the inversions made by its last candle. Nothing existing calls this module: every existing output is
unchanged.
"""
from __future__ import annotations

from typing import List

import numpy as np

from liquidity_engine.context.frame_state import Candles, _Array
from liquidity_engine.context.measures import bearish_fvgs, mirror
from liquidity_engine.models import BiasDirection

__all__ = ["inverted_fvgs"]


def _first_close(c: np.ndarray, start: int, below: float | None = None, above: float | None = None) -> int | None:
    later = c[start:]
    hit = np.flatnonzero(later < below) if below is not None else np.flatnonzero(later > above)
    return start + int(hit[0]) if len(hit) else None


def inverted_fvgs(c: Candles) -> List[_Array]:
    """The frame's inverted FVGs, in the order their gaps formed."""
    n = len(c)
    gaps = [(k, BiasDirection.BEARISH, lo, hi) for k, lo, hi in bearish_fvgs(c.h, c.l, 0, n)]
    _, mh, ml, _ = mirror(c.o, c.h, c.l, c.c)
    gaps += [(k, BiasDirection.BULLISH, -hi, -lo) for k, lo, hi in bearish_fvgs(mh, ml, 0, n)]
    out: List[_Array] = []
    for k, direction, lo, hi in sorted(gaps, key=lambda g: (g[0], g[1].value)):
        bullish = direction == BiasDirection.BULLISH
        b = _first_close(c.c, k + 1, below=lo) if bullish else _first_close(c.c, k + 1, above=hi)
        if b is not None:
            flipped = BiasDirection.BEARISH if bullish else BiasDirection.BULLISH
            out.append(_Array(flipped, "IFVG", c.tf, float(lo), float(hi), int(c.end[b])))
    return out
