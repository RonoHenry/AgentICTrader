"""Dealing ranges and premium/discount (algomind-dis Requirement 4, §5.2, §5.3).

Three ranges per frame, each with its origin and what ends it:
- **SWING:** the engine's ``frame_state.dealing_range``, from the last confirmed swing low to the last confirmed swing
  high, each stretched to any later extreme (CE-D2). Established when its later anchor is confirmed; no longer
  valid once a candle closes beyond an anchor's own price (the range broke, and a new one forms with new swings).
- **PREVIOUS:** the last closed candle's high and low (PDH/PDL, PWH/PWL, PMH/PML), replaced at the next close.
- **DISPLACEMENT:** the leg of the latest displacement candle (a body at least ``displacement_body`` times the mean
  body of up to ``body_window`` candles before it): from the extreme of that candle and the ``sweep_window``
  candles before it, to the furthest price since. No longer valid once a candle closes beyond its origin.

The position is (price − low)/(high − low); the zone is location, never a direction (§5.3).
"""
from __future__ import annotations

from typing import Mapping, Optional, Sequence

import numpy as np

from algomind_dis.analyzers.structure import LOOKBACK
from algomind_dis.records import DealingRange, PricePosition, make_id
from algomind_dis.settings import V1, Settings
from liquidity_engine.context.frame_state import Candles, dealing_range
from liquidity_engine.context.frame_state import DealingRange as _EngineRange

__all__ = ["displacement_range", "displacements", "position", "previous_range", "primary", "ranges", "swing_range",
           "zone"]

_PREVIOUS = {"MN1": "PMH/PML", "W1": "PWH/PWL", "D1": "PDH/PDL"}


def _DR(high: float, low: float, low_at: int, high_at: int) -> _EngineRange:
    return _EngineRange(low, high, low_at, high_at)


def zone(p: float, s: Settings = V1) -> str:
    if p < s.deep_discount:
        return "DEEP_DISCOUNT"
    if p < s.discount:
        return "DISCOUNT"
    if p <= s.premium:
        return "EQUILIBRIUM"
    if p <= s.deep_premium:
        return "PREMIUM"
    return "DEEP_PREMIUM"


def position(r: DealingRange, price: float, s: Settings = V1) -> PricePosition:
    p = r.position(price)
    return PricePosition(r.id, r.tf, float(p), zone(p, s), r.equilibrium, float(price))


def _first_close_beyond(c: Candles, start: int, above: Optional[float], below: Optional[float]) -> Optional[int]:
    """The close time of the first candle from ``start`` closing above ``above`` or below ``below``."""
    closes = c.c[start:]
    hit = np.zeros(len(closes), bool)
    if above is not None:
        hit |= closes > above
    if below is not None:
        hit |= closes < below
    k = np.flatnonzero(hit)
    return int(c.end[start + k[0]]) if len(k) else None


def _dealing_range(c: Candles, swing_idx: Optional[tuple[np.ndarray, np.ndarray]]):
    """``frame_state.dealing_range``; with the full frame's swing indices (the replay's), the same range read from
    the swings confirmed in the cut (index <= n - 3) without detecting them again."""
    if swing_idx is None:
        return dealing_range(c.h, c.l, len(c))
    n = len(c)
    highs, lows = (a[a <= n - 1 - LOOKBACK] for a in swing_idx)
    if not len(highs) or not len(lows):
        return None
    i_h, i_l = int(highs[-1]), int(lows[-1])
    return _DR(float(c.h[i_h:n].max()), float(c.l[i_l:n].min()), i_l, i_h)


def swing_range(market: str, c: Candles,
                swing_idx: Optional[tuple[np.ndarray, np.ndarray]] = None) -> Optional[DealingRange]:
    rng = _dealing_range(c, swing_idx)
    if rng is None:
        return None
    later = max(rng.low_at, rng.high_at)
    established = int(c.end[min(later + LOOKBACK, len(c) - 1)])
    anchor_high, anchor_low = float(c.h[rng.high_at]), float(c.l[rng.low_at])
    broke = _first_close_beyond(c, later + LOOKBACK + 1, anchor_high, anchor_low)
    return DealingRange(make_id(market, c.tf, "SWING", int(c.t[rng.low_at]), int(c.t[rng.high_at])), market, c.tf,
                        "SWING", rng.high, rng.low,
                        f"{c.tf} swings: low {anchor_low:.6g} (candle {rng.low_at}), high {anchor_high:.6g} "
                        f"(candle {rng.high_at})", established, broke is None, broke,
                        f"a {c.tf} close beyond {anchor_low:.6g}-{anchor_high:.6g}")


def previous_range(market: str, c: Candles) -> Optional[DealingRange]:
    if not len(c):
        return None
    name = _PREVIOUS.get(c.tf, f"previous {c.tf}")
    return DealingRange(make_id(market, c.tf, "PREVIOUS", int(c.t[-1])), market, c.tf, "PREVIOUS", float(c.h[-1]),
                        float(c.l[-1]), f"the previous {c.tf} candle ({name})", int(c.end[-1]), True, None,
                        f"replaced at the next {c.tf} close")


def displacements(c: Candles, s: Settings = V1) -> np.ndarray:
    """+1 / −1 for each displacement candle (a body at least ``displacement_body`` times the mean body of up to
    ``body_window`` candles before it, with at least five before), 0 otherwise."""
    body = np.abs(c.c - c.o)
    csum = np.concatenate([[0.0], np.cumsum(body)])
    i = np.arange(len(body))
    lo = np.maximum(0, i - s.body_window)
    n = i - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, (csum[i] - csum[lo]) / np.maximum(n, 1), np.nan)
    big = (n >= 5) & (body >= s.displacement_body * mean) & (body > 0)
    return np.where(big, np.sign(c.c - c.o), 0).astype(int)


def displacement_range(market: str, c: Candles, s: Settings = V1,
                       disp: Optional[np.ndarray] = None) -> Optional[DealingRange]:
    d = displacements(c, s) if disp is None else disp[:len(c)]
    k = np.flatnonzero(d)
    if not len(k):
        return None
    k = int(k[-1])
    first = max(0, k - s.sweep_window)
    if d[k] > 0:
        origin, extreme = float(c.l[first:k + 1].min()), float(c.h[k:].max())
        broke = _first_close_beyond(c, k + 1, None, origin)
        low, high, word = origin, extreme, "under"
    else:
        origin, extreme = float(c.h[first:k + 1].max()), float(c.l[k:].min())
        broke = _first_close_beyond(c, k + 1, origin, None)
        low, high, word = extreme, origin, "above"
    side = "bullish" if d[k] > 0 else "bearish"
    return DealingRange(make_id(market, c.tf, "DISPLACEMENT", int(c.t[k])), market, c.tf, "DISPLACEMENT", high, low,
                        f"the {side} {c.tf} displacement of candle {k}, from {origin:.6g}", int(c.end[k]),
                        broke is None, broke, f"a {c.tf} close {word} {origin:.6g}")


def ranges(market: str, c: Candles, s: Settings = V1, swing_idx=None,
           disp: Optional[np.ndarray] = None) -> tuple[DealingRange, ...]:
    """The frame's ranges that exist: SWING, PREVIOUS, DISPLACEMENT (the replay passes the full frame's swing
    indices and displacements; the result is the same)."""
    return tuple(r for r in (swing_range(market, c, swing_idx), previous_range(market, c),
                             displacement_range(market, c, s, disp)) if r is not None)


def primary(by_tf: Mapping[str, Sequence[DealingRange]], question: str) -> Optional[DealingRange]:
    """The range a question is read against (§5.2's contextual selection): for the SIDE the W1 swing range; for the
    trade's LOCATION the D1 swing range, else the previous D1 candle."""
    def find(tf: str, kind: str) -> Optional[DealingRange]:
        return next((r for r in by_tf.get(tf, ()) if r.kind == kind), None)
    if question == "SIDE":
        return find("W1", "SWING")
    if question == "LOCATION":
        return find("D1", "SWING") or find("D1", "PREVIOUS")
    raise ValueError(f"question: SIDE or LOCATION, not {question}")
