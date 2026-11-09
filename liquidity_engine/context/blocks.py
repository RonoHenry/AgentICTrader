"""The trader's order blocks and breakers, on arrays (liquidity-engine Requirement 31; the trader's answers of
2026-10-28 and 2026-11-03; ``FindCISDLevel`` in their Fractal + POI script, ``backend/FractalPOI.md``).

The same rule as ``PDArrayDetector._detect_delivery_changes`` (``ob_rule = "cisd"``), for the array layer:

- **An order block is a change in the state of delivery.** For a bullish one: a run of down-closing candles (a doji,
  close equal to open, neither ends nor joins the run), confirmed when a later candle closes above the open of the
  run's first candle (the CISD level). Only the latest run waits for its close through; a new run replaces one still
  waiting. The zone is the run's bodies; its MT is their midpoint; the last candle is the sniper entry.
- **High probability** (a grade, not the definition): the run took the latest three-candle swing before it, and the
  move away left a fair value gap.
- **A close through the bodies ends the order block** and inverts it: from that close it is a **breaker** of the
  other side over the same bodies. No sweep is needed (2026-10-28).
- **A close back through the breaker ends it** (2026-11-03): above its top for a bearish breaker.

Every block is dated by indices: the candle that confirmed it and the one that ended it. Each reads only candles up
to its own index, so a cut of the frame holds exactly the blocks confirmed by its last candle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from liquidity_engine.models import BiasDirection

__all__ = ["Block", "delivery_blocks", "runs"]

BULL, BEAR = BiasDirection.BULLISH, BiasDirection.BEARISH


@dataclass(frozen=True)
class Block:
    kind: str                    # OB or BREAKER
    direction: BiasDirection     # BULLISH supports price from below; BEARISH resists from above
    low: float                   # the run's bodies
    high: float
    first: int                   # the run's first and last candles
    last: int
    formed: int                  # the close that made it: the CISD close (OB), the close through the bodies (BREAKER)
    level: float                 # the CISD level: the open of the run's first candle
    high_probability: bool
    ended: Optional[int]         # the close that ended it: through the bodies (OB), back through (BREAKER)

    @property
    def mt(self) -> float:
        """The mean threshold: the midpoint of the bodies."""
        return (self.low + self.high) / 2


def runs(o: Sequence[float], c: Sequence[float], bullish: bool) -> List[tuple[int, int, int]]:
    """(first, last, through) for each run of closes against a ``bullish`` block (down closes for a bullish one),
    dojis skipped, that a later candle closed through (``_closed_through_runs`` on arrays)."""
    out: List[tuple[int, int, int]] = []
    run: Optional[list] = None
    last_against = False
    for i in range(len(c)):
        if run is not None and not run[2] and i > run[1]:
            level = o[run[0]]
            if (c[i] > level) if bullish else (c[i] < level):
                out.append((run[0], run[1], i))
                run[2] = True
        up, down = c[i] > o[i], c[i] < o[i]
        against = down if bullish else up
        if against:
            if run is not None and last_against and not run[2]:
                run[1] = i
            else:
                run = [i, i, False]
        if up or down:
            last_against = against
    return out


def _took_swing(h, l, first: int, last: int, bullish: bool) -> bool:
    for s in range(first - 2, 0, -1):
        if bullish and l[s] < l[s - 1] and l[s] < l[s + 1]:
            return min(l[first:last + 1]) < l[s]
        if not bullish and h[s] > h[s - 1] and h[s] > h[s + 1]:
            return max(h[first:last + 1]) > h[s]
    return False


def _left_gap(h, l, last: int, through: int, bullish: bool) -> bool:
    for k in range(max(2, last + 1), min(len(h), through + 2)):
        if (l[k] > h[k - 2]) if bullish else (h[k] < l[k - 2]):
            return True
    return False


def _first_close(c: np.ndarray, start: int, above: Optional[float] = None, below: Optional[float] = None) -> Optional[int]:
    tail = c[start:]
    hit = (tail > above) if above is not None else (tail < below)
    k = np.flatnonzero(hit)
    return start + int(k[0]) if len(k) else None


def delivery_blocks(o, h, l, c) -> List[Block]:
    """Every order block of the frame, both sides, and the breaker each one became, in the order they were made."""
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    out: List[Block] = []
    for bullish in (True, False):
        side, other = (BULL, BEAR) if bullish else (BEAR, BULL)
        for first, last, through in runs(o, c, bullish):
            bodies_o, bodies_c = o[first:last + 1], c[first:last + 1]
            top = float(max(bodies_o.max(), bodies_c.max()))
            bottom = float(min(bodies_o.min(), bodies_c.min()))
            grade = _took_swing(h, l, first, last, bullish) and _left_gap(h, l, last, through, bullish)
            inverted = _first_close(c, through + 1, below=bottom) if bullish else _first_close(c, through + 1,
                                                                                                above=top)
            out.append(Block("OB", side, bottom, top, first, last, through, float(o[first]), grade, inverted))
            if inverted is not None:
                back = _first_close(c, inverted + 1, above=top) if bullish else _first_close(c, inverted + 1,
                                                                                              below=bottom)
                out.append(Block("BREAKER", other, bottom, top, first, last, inverted, float(o[first]), grade, back))
    return sorted(out, key=lambda b: (b.formed, b.kind != "OB", b.direction != BULL))
