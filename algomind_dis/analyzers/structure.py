"""Structure (algomind-dis Requirement 3, §5.1, §7.1): swings, the closes that break them, and the direction.

Swings are the engine's (``measures.swing_highs/swing_lows``, lookback 2). A swing at candle i is known once candle
i + 2 has closed. A candle breaks the latest known swing when it closes beyond it; each swing breaks once. The break
is a BOS when it goes with the structure (or there is none yet) and an MSS when it goes against it. Each event reads
only candles up to its own close, so the events of any earlier cut are the full frame's up to that cut's last close.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import numpy as np

from algomind_dis.records import StructureEvent, make_id
from liquidity_engine.context.frame_state import Candles
from liquidity_engine.context.measures import swing_highs, swing_lows

__all__ = ["LOOKBACK", "Swing", "direction", "events", "swings"]

LOOKBACK = 2


@dataclass(frozen=True)
class Swing:
    index: int
    is_high: bool
    price: float
    known_at: int                # the close of the candle that confirms it


def swings(c: Candles) -> List[Swing]:
    """The frame's confirmed swings, in time order."""
    out = [Swing(i, True, float(c.h[i]), int(c.end[i + LOOKBACK])) for i in swing_highs(c.h, LOOKBACK)]
    out += [Swing(i, False, float(c.l[i]), int(c.end[i + LOOKBACK])) for i in swing_lows(c.l, LOOKBACK)]
    return sorted(out, key=lambda s: (s.index, not s.is_high))


def events(market: str, c: Candles) -> tuple[StructureEvent, ...]:
    """Every BOS and MSS of the frame, in time order."""
    s = swings(c)
    highs = [x for x in s if x.is_high]
    lows = [x for x in s if not x.is_high]
    out: List[StructureEvent] = []
    trend = "NEUTRAL"
    hi = lo = 0                                  # the next swing of each side to become known
    high = low = None                            # the latest known, unbroken swing of each side
    for k in range(len(c)):
        while hi < len(highs) and highs[hi].index + LOOKBACK < k:
            high, hi = highs[hi], hi + 1
        while lo < len(lows) and lows[lo].index + LOOKBACK < k:
            low, lo = lows[lo], lo + 1
        close = float(c.c[k])
        for swing, side, beyond in ((high, "BULLISH", lambda x: close > x), (low, "BEARISH", lambda x: close < x)):
            if swing is None or not beyond(swing.price):
                continue
            kind = "MSS" if trend not in ("NEUTRAL", side) else "BOS"
            out.append(StructureEvent(make_id(market, c.tf, kind, side, int(c.t[swing.index]), int(c.end[k])),
                                      c.tf, kind, side, swing.price, int(c.end[k]), int(c.t[swing.index])))
            trend = side
            if side == "BULLISH":
                high = None
            else:
                low = None
    return tuple(out)


def direction(ev: Sequence[StructureEvent], t: int) -> str:
    """The structural direction at ``t``: the latest event's, NEUTRAL before the first."""
    at = np.array([e.at for e in ev], dtype=np.int64)
    k = int(np.searchsorted(at, t, "right"))
    return ev[k - 1].direction if k else "NEUTRAL"
