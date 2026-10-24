"""ICT's IPDA data ranges as objectives (context-engine Requirement 27, task 365).

ICT teaches that the interbank price delivery algorithm refers back 20, 40 and 60 trading days: the highs and lows
of those ranges are the liquidity it reaches for. Here they are pools for the chain's frames (``frame_state``'s
``levels``), read from a market's closed D1 candles (CE-D17). The forward-looking ranges and the quarterly shifts
are not modelled.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np

from liquidity_engine.context.frame_state import Candles, Objective
from liquidity_engine.models import BiasDirection

__all__ = ["IPDA_LOOKBACKS", "ipda_ranges"]

#: Trading days looked back.
IPDA_LOOKBACKS = (20, 40, 60)


def ipda_ranges(d1: Candles, lookbacks: Sequence[int] = IPDA_LOOKBACKS) -> List[Objective]:
    """The highest high and lowest low of the last n closed D1 candles, for each n with that many candles. A candle
    that leads more than one range is listed once, under its longest range; on a tie the latest candle leads."""
    n = len(d1)
    found: Dict[Tuple[BiasDirection, int], int] = {}
    for back in sorted(lookbacks):
        if n < back:
            continue
        lo = n - back
        top = lo + back - 1 - int(np.argmax(d1.h[lo:][::-1]))
        bottom = lo + back - 1 - int(np.argmin(d1.l[lo:][::-1]))
        found[(BiasDirection.BULLISH, top)] = back
        found[(BiasDirection.BEARISH, bottom)] = back
    out = []
    for (direction, i), back in found.items():
        high = direction == BiasDirection.BULLISH
        out.append(Objective("POOL", f"IPDA{back}_{'HIGH' if high else 'LOW'}", d1.tf,
                             float(d1.h[i] if high else d1.l[i]), direction, int(d1.end[i])))
    return out
