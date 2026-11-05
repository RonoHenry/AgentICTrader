"""Levels: where the engine waits (thesis-engine Requirement 6, TE-D5).

A level for a bullish thesis (bearish is the mirror) is a live bullish array of a level frame from the book (an FVG
or an inverted FVG's gap, an order block's bodies, a breaker) that is:
- between the thesis's protected level and its draw;
- in discount: its CE below the equilibrium of the D1 or the W1 SWING range (context-engine Requirement 34's rule);
- at most ``level_max_adr`` ADR tall.

Its score counts what lines up there: the level frames with an array of the side overlapping it, the ranges it is in
discount of, untaken sell-side swing liquidity of a level frame inside it or within ``pool_band_adr`` ADR under it,
and a high-probability block. Arrays of the other side are never levels.
"""
from __future__ import annotations

from typing import List

import numpy as np

from thesis_engine.book import Book
from thesis_engine.records import Level, Thesis
from thesis_engine.settings import V1, Settings

__all__ = ["levels"]


def levels(th: Thesis, book: Book, t: int, price: float, s: Settings = V1) -> List[Level]:
    """The thesis's levels as of ``t``, best first: highest score, then nearest to ``price``."""
    adr = book.adr(t)
    if not np.isfinite(adr) or adr <= 0:
        return []
    bullish = th.bullish
    ranges = [r for r in (book.frames[tf].range(book.frames[tf].n(t)) for tf in ("D1", "W1")) if r is not None]
    found = []
    for tf in s.level_frames:
        frame = book.frames[tf]
        for a in frame.live(frame.n(t), th.side):
            if a.high - a.low > s.level_max_adr * adr:
                continue
            inside = (a.low > th.protected and a.high < th.draw) if bullish else \
                (a.high < th.protected and a.low > th.draw)
            if not inside:
                continue
            ce = (a.low + a.high) / 2
            cheap = tuple(r.tf for r in ranges if (r.position(ce) < 0.5) == bullish)
            if cheap:
                found.append((a, cheap))
    pools = {tf: book.frames[tf].untaken(book.frames[tf].n(t), lows=bullish) for tf in s.level_frames}
    out = []
    for a, cheap in found:
        frames = sorted({b.tf for b, _ in found if b.low <= a.high and b.high >= a.low})
        band = s.pool_band_adr * adr
        lo, hi = (a.low - band, a.high) if bullish else (a.low, a.high + band)
        liquidity = any(((p >= lo) & (p <= hi)).any() for p in pools.values() if len(p))
        reasons = (f"{'+'.join(frames)} arrays", f"{'discount' if bullish else 'premium'} of {'+'.join(cheap)}",
                   *(("resting liquidity",) if liquidity else ()), *(("high probability",) if a.high_probability else ()))
        score = len(frames) + len(cheap) + int(liquidity) + int(a.high_probability)
        out.append(Level(a.id, a.tf, a.kind, a.side, a.low, a.high, a.formed_at, a.end, score, reasons))
    return sorted(out, key=lambda x: (-x.score, min(abs(price - x.low), abs(price - x.high)), x.array_id))
