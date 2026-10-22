"""The phase of price delivery (liquidity-engine update 2026-10-22, Requirement 28).

ICT's Interbank Price Delivery Algorithm cycles through four phases: consolidation, expansion, retracement and
reversal, and "a price move is always going to start from consolidation to expansion" (the trader, 2026-10-22).
This reads them candle by candle, from closed candles only, with the engine's own CRT thresholds (LE-D23):

- **consolidation:** the last ``LOOKBACK`` candles span at most ``TIGHT_RATIO`` average true ranges, the ATR taken
  over the ``ATR_PERIOD`` candles before them. Its box is their high and low.
- **expansion:** the first close outside the box. The leg runs from the box's opposite extreme, manipulation
  wicks included, and every candle that makes a new extreme in the leg is expansion too.
- **retracement:** after an expansion, a candle that makes no new extreme in the leg and closes on the leg's side
  of its origin.
- **reversal:** a close beyond the leg's origin. The leg then runs the other way, from the old leg's extreme.

A wick beyond the box that closes back inside is the consolidation's manipulation: the stop run on its liquidity.

    label_phases(o, h, l, c)        -> one label per candle ("" before the first consolidation)
    episodes(o, h, l, c, t)         -> one row per consolidation that ended in an expansion

Each label reads only its candle and the ones before it. The episodes' outcome columns (``travel_atr``,
``delivered``) look ahead on purpose: they are what the research measures the reads known before the break against.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

__all__ = ["ATR_PERIOD", "EXPANSION_RATIO", "LOOKBACK", "TIGHT_RATIO", "episodes", "label_phases"]

#: The engine's CRT thresholds (liquidity_engine/ipda/classifier.py: _C1_LOOKBACK, _C1_TIGHT_RATIO,
#: _C3_EXPANSION_RATIO) and its ATR period.
LOOKBACK, TIGHT_RATIO, EXPANSION_RATIO, ATR_PERIOD = 8, 2.0, 1.5, 14
#: Candles after the break over which the expansion's travel and delivery are measured.
OUTCOME_CANDLES = 2 * LOOKBACK

CONSOLIDATION, EXPANSION, RETRACEMENT, REVERSAL = "consolidation", "expansion", "retracement", "reversal"


def _true_ranges(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    prev = np.r_[c[0], c[:-1]]
    return np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))


def _read(o, h, l, c):
    """The labels, and each consolidation episode as the reader saw it (no look-ahead)."""
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    n = len(c)
    tr = _true_ranges(h, l, c)
    labels = np.full(n, "", dtype=object)
    found: list[dict] = []
    state, box, leg, previous = None, None, None, 0
    first = LOOKBACK + ATR_PERIOD - 1                        # the first candle with a full window and ATR before it
    for i in range(n):
        window = slice(i - LOOKBACK + 1, i + 1)
        atr = float(tr[i - LOOKBACK - ATR_PERIOD + 1: i - LOOKBACK + 1].mean()) if i >= first else np.nan
        is_tight = i >= first and atr > 0 and h[window].max() - l[window].min() <= TIGHT_RATIO * atr

        if state == CONSOLIDATION:
            if c[i] > box["high"] or c[i] < box["low"]:
                d = 1 if c[i] > box["high"] else -1
                origin = box["wick_low"] if d == 1 else box["wick_high"]
                found.append({**box, "direction": d, "broken": i, "origin": origin,
                              "break_range_atr": (h[i] - l[i]) / box["atr"], "previous": previous})
                state, previous = EXPANSION, d
                leg = {"dir": d, "origin": origin, "extreme": h[i] if d == 1 else l[i]}
                labels[i] = EXPANSION
                continue
            if h[i] > box["high"] or l[i] < box["low"]:          # a wick beyond the box, closed back inside
                side = "high" if h[i] > box["high"] else "low"
                if box["manipulation"] is None:
                    box["manipulation"], box["manipulated"] = side, i
                box["last_manipulation"] = side
            box["wick_high"], box["wick_low"] = max(box["wick_high"], h[i]), min(box["wick_low"], l[i])
            labels[i] = CONSOLIDATION
            continue

        if state in (EXPANSION, RETRACEMENT, REVERSAL):
            d = leg["dir"]
            if (c[i] < leg["origin"]) if d == 1 else (c[i] > leg["origin"]):
                leg = {"dir": -d, "origin": leg["extreme"], "extreme": l[i] if d == 1 else h[i]}
                state = labels[i] = REVERSAL
                previous = -d
                continue
            new_extreme = h[i] > leg["extreme"] if d == 1 else l[i] < leg["extreme"]
            if new_extreme:
                leg["extreme"] = h[i] if d == 1 else l[i]
                state = labels[i] = EXPANSION
                continue
            if not is_tight:
                state = labels[i] = RETRACEMENT
                continue

        if is_tight:
            box = {"start": i - LOOKBACK + 1, "detected": i, "high": float(h[window].max()),
                   "low": float(l[window].min()), "atr": atr, "manipulation": None, "manipulated": None,
                   "last_manipulation": None}
            box["wick_high"], box["wick_low"] = box["high"], box["low"]
            state = labels[i] = CONSOLIDATION
    return labels, found


def label_phases(o: Sequence[float], h: Sequence[float], l: Sequence[float], c: Sequence[float]) -> np.ndarray:
    """Each candle's phase: consolidation, expansion, retracement or reversal ("" before the first consolidation)."""
    return _read(o, h, l, c)[0]


def episodes(o: Sequence[float], h: Sequence[float], l: Sequence[float], c: Sequence[float],
             t: Optional[Sequence] = None) -> pd.DataFrame:
    """One row per consolidation that ended in an expansion: its box, its first and last manipulation, the side and
    candle of the close that broke it, the leg's origin, the previous expansion's side, and the outcome over the
    next ``OUTCOME_CANDLES`` candles (look-ahead, for research): ``travel_atr``, how far price went beyond the box
    on the break's side, in the box's ATR; ``delivered``, the first side to travel ``EXPANSION_RATIO`` ATRs
    beyond the box (+1 up, -1 down, 0 neither)."""
    h_, l_ = np.asarray(h, dtype=float), np.asarray(l, dtype=float)
    t = np.arange(len(h_)) if t is None else np.asarray(t)
    rows = []
    for ep in _read(o, h, l, c)[1]:
        b = ep["broken"]
        ahead = slice(b, min(len(h_), b + OUTCOME_CANDLES))
        up_travel, down_travel = h_[ahead] - ep["high"], ep["low"] - l_[ahead]
        travel = (up_travel.max() if ep["direction"] == 1 else down_travel.max()) / ep["atr"]
        need = EXPANSION_RATIO * ep["atr"]
        up_at = np.flatnonzero(up_travel >= need)
        down_at = np.flatnonzero(down_travel >= need)
        delivered = 0
        if len(up_at) or len(down_at):
            first_up = up_at[0] if len(up_at) else np.inf
            first_down = down_at[0] if len(down_at) else np.inf
            delivered = 1 if first_up < first_down else -1 if first_down < first_up else 0
        rows.append({"start": t[ep["start"]], "detected": t[ep["detected"]], "broken_at": t[b],
                     "box_high": ep["high"], "box_low": ep["low"], "atr": ep["atr"],
                     "manipulation": ep["manipulation"],
                     "manipulated_at": None if ep["manipulated"] is None else t[ep["manipulated"]],
                     "last_manipulation": ep["last_manipulation"], "direction": ep["direction"],
                     "origin": ep["origin"], "break_range_atr": ep["break_range_atr"], "previous": ep["previous"],
                     "travel_atr": float(travel), "delivered": delivered})
    return pd.DataFrame(rows)
