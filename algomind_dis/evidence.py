"""Evidence and synthesis (algomind-dis Requirements 9, 11, §9.3, §9.4, §11).

**The items** (v1), each BULLISH, BEARISH or NEUTRAL with a significance in [0, 1]:
- STRUCTURE: each frame's structural direction (1.0), from its latest break.
- LIQUIDITY: each pool swept in the last three candles whose sweeping candle closed back: toward the other side,
  at its type's weight (external 1.0, temporal 0.8, internal 0.6; equal highs or lows +0.25, capped at 1).
- PREMIUM_DISCOUNT: each frame's SWING range zone: deep discount 1.0 and discount 0.5 bullish; premium 0.5 and
  deep premium 1.0 bearish (§5.3: location, weighed only here).
- PD_ARRAY: each array that counts (Requirement 6.3): 0.5, +0.25 if a displacement made it, +0.25 after a sweep.
- DELIVERY: each frame's delivery: 1.0 delivering, 0.5 transitional, toward its side.
- TEMPORAL and VOLATILITY: neutral context, weight 0 (§8).

**Correlation control (§9.3):** an item's source is the candle that caused it (the breaking close, the CISD close,
the sweeping candle, the array's retest), or the range for a location. Items with the same source and direction
are one movement and count once, through the most significant (ties: the weightiest category and frame). Then each
frame counts once per category and side, at its greatest significance.

**The scores (§9.4):** e_c is the frames' weighted significance over the frames' weights (so in [0, 1]), and
S = Σ w_c e_c. Only the scored frames (MN1, W1, D1) count; lower frames are classified (``classify_lower``) and
never scored (§11.2). The result is a confidence, never a probability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import numpy as np

from algomind_dis.analyzers.arrays import counts
from algomind_dis.records import Evidence, make_id
from algomind_dis.settings import V1, Settings

__all__ = ["SCORED", "Scores", "classify_lower", "counted", "gather", "htf_scores", "scores"]

SCORED = ("MN1", "W1", "D1")
_ZONES = {"DEEP_DISCOUNT": ("BULLISH", 1.0), "DISCOUNT": ("BULLISH", 0.5), "PREMIUM": ("BEARISH", 0.5),
          "DEEP_PREMIUM": ("BEARISH", 1.0)}
_OTHER = {"BULLISH": "BEARISH", "BEARISH": "BULLISH"}


def _p(x: float) -> str:
    return f"{x:.6g}"


def _candle(tf: str, end: Optional[int]) -> Optional[str]:
    return None if end is None else make_id(tf, "candle", int(end))


def _retest(a, c) -> int:
    """The close of the latest candle that traded into the array (the current one if price is in it)."""
    if a.location == "INSIDE":
        return int(c.end[-1])
    after = c.t >= a.formed_at
    touched = (c.l <= a.high) if a.direction == "BULLISH" else (c.h >= a.low)
    k = np.flatnonzero(after & touched)
    return int(c.end[k[-1]]) if len(k) else int(c.end[-1])


def gather(obs, s: Settings = V1) -> list[Evidence]:
    """Every evidence item of an observation (``algomind_dis.observe``)."""
    items: list[Evidence] = []

    def add(category, direction, tf, source, sig, at, text, depends=(), scope=""):
        items.append(Evidence(make_id(category, direction, tf, source, round(sig, 9), text), category, direction,
                              tf, source, float(sig), int(at), True, tuple(depends), text, scope))

    for tf, ctx in obs.contexts.items():
        if ctx.structural_direction != "NEUTRAL" and ctx.events:
            ev = ctx.events[-1]
            add("STRUCTURE", ctx.structural_direction, tf, _candle(tf, ev.at), 1.0, ev.at,
                f"{tf} structure {ctx.structural_direction.lower()}: its last {ev.kind} closed beyond {_p(ev.level)}",
                (ev.id,))
        for r, pos in zip(ctx.ranges, ctx.positions):
            if r.kind == "SWING" and pos.zone in _ZONES:
                side, sig = _ZONES[pos.zone]
                add("PREMIUM_DISCOUNT", side, tf, make_id(tf, "range", r.id), sig, r.established_at,
                    f"price at {pos.position:.0%} of the {tf} range {_p(r.low)}-{_p(r.high)}: "
                    f"{pos.zone.lower().replace('_', ' ')}", (r.id,))
        c = obs.frames[tf]
        for a in ctx.arrays:
            if counts(a, c, s):
                sig = 0.5 + 0.25 * a.displacement + 0.25 * a.after_sweep
                at = _retest(a, c)
                add("PD_ARRAY", a.direction, tf, _candle(tf, at), sig, at,
                    f"{tf} {a.direction.lower()} {a.kind} {_p(a.low)}-{_p(a.high)} in {a.zone.lower().replace('_', ' ')}"
                    f", price {a.location.lower()} it" + (", displaced" if a.displacement else "")
                    + (", after a sweep" if a.after_sweep else ""), (a.id,))
        d = ctx.delivery
        if d is not None and d.direction in _OTHER and d.since is not None:
            sig = 0.5 if d.state == "TRANSITIONAL" else 1.0
            add("DELIVERY", d.direction, tf, _candle(tf, d.since), sig, d.since,
                f"{tf} {d.state.lower().replace('_', ' ')}: " + "; ".join(d.evidence))
    for o in obs.objectives:
        if o.status == "SWEPT" and o.closed_back:
            sig = min(1.0, s.type_weights[o.kind] + (s.equal_bonus if o.source.startswith("EQUAL") else 0.0))
            add("LIQUIDITY", _OTHER[o.side], o.tf, _candle("D1", o.swept_at), sig, o.swept_at,
                f"{o.tf} {o.source} {_p(o.price)} ({o.kind.lower()}) swept and closed back", (o.id,),
                "EXTERNAL" if o.kind == "EXTERNAL" else "")
    tc, vc = obs.time, obs.volatility
    add("TEMPORAL", "NEUTRAL", "D1", None, 0.0, obs.t,
        f"{tc.weekday} {tc.day}, week {tc.week_of_month} of the month"
        + (f"; scheduled: {', '.join(tc.scheduled)}" if tc.scheduled else ""))
    add("VOLATILITY", "NEUTRAL", "D1", None, 0.0, obs.t,
        f"the last D1 range {vc.last_ratio:.2f} ADR (ADR {_p(vc.adr)})" + (", expanding" if vc.expanding else "")
        + (f", phase {vc.phase}" if vc.phase else ""))
    return items


def counted(items: Sequence[Evidence], frames: Sequence[str] = SCORED, s: Settings = V1) -> list[Evidence]:
    """The items that count: scored categories and frames, one per source and direction (the weightiest), then one
    per category, frame and side (the most significant)."""
    use = [e for e in items if e.category in s.category_weights and e.tf in frames and e.direction in _OTHER]

    def rank(e: Evidence) -> tuple[float, float]:
        """The greatest significance (Requirement 9.2), then the weightiest category and frame."""
        return e.significance, s.category_weights[e.category] * s.timeframe_weights.get(e.tf, 0.0)

    best: dict = {}
    for e in use:
        key = (e.source_event, e.direction) if e.source_event is not None else (e.id, e.direction)
        if key not in best or rank(e) > rank(best[key]):
            best[key] = e
    top: dict = {}
    for e in best.values():
        key = (e.category, e.tf, e.direction)
        if key not in top or e.significance > top[key].significance:
            top[key] = e
    return sorted(top.values(), key=lambda e: (list(s.category_weights).index(e.category), frames.index(e.tf),
                                                e.direction))


@dataclass(frozen=True)
class Scores:
    bullish: float
    bearish: float
    by_category: Mapping[str, tuple[float, float]]

    def lead(self, side: str) -> float:
        return (self.bullish - self.bearish) if side == "BULLISH" else (self.bearish - self.bullish)


def _category(items: Sequence[Evidence], frames: Sequence[str], s: Settings) -> tuple[float, float]:
    total = sum(s.timeframe_weights.get(tf, 0.0) for tf in frames)
    if not total:
        return 0.0, 0.0
    up = sum(e.significance * s.timeframe_weights[e.tf] for e in items if e.direction == "BULLISH")
    down = sum(e.significance * s.timeframe_weights[e.tf] for e in items if e.direction == "BEARISH")
    return up / total, down / total


def scores(items: Sequence[Evidence], frames: Sequence[str] = SCORED, s: Settings = V1) -> Scores:
    use = counted(items, frames, s)
    by = {c: _category([e for e in use if e.category == c], frames, s) for c in s.category_weights}
    return Scores(sum(s.category_weights[c] * by[c][0] for c in by), sum(s.category_weights[c] * by[c][1] for c in by),
                  by)


def htf_scores(items: Sequence[Evidence], frames: Sequence[str] = SCORED, s: Settings = V1) -> tuple[float, float]:
    """The challenge's scores (Requirement 12.3): structure and external liquidity alone, over their weights."""
    use = [e for e in counted(items, frames, s)
           if e.category == "STRUCTURE" or (e.category == "LIQUIDITY" and e.scope == "EXTERNAL")]
    ws, wl = s.category_weights["STRUCTURE"], s.category_weights["LIQUIDITY"]
    st = _category([e for e in use if e.category == "STRUCTURE"], frames, s)
    lq = _category([e for e in use if e.category == "LIQUIDITY"], frames, s)
    return (ws * st[0] + wl * lq[0]) / (ws + wl), (ws * st[1] + wl * lq[1]) / (ws + wl)


def classify_lower(direction: str, *, side: str, price: float, protected: float, d1_range: tuple[float, float],
                   d1_mss_against: bool, d1_close: float) -> str:
    """§11.2: lower-frame evidence against the held side is a RETRACEMENT (price inside the D1 range), INTERNAL
    DELIVERY (price beyond the range, the D1 close not), or a DEVELOPING_REVERSAL (a D1 MSS against the side, or a
    D1 close beyond its protected level). Only a developing reversal can move the state."""
    if direction == side:
        return "WITH_THE_SIDE"
    beyond = (d1_close < protected) if side == "BULLISH" else (d1_close > protected)
    if d1_mss_against or beyond:
        return "DEVELOPING_REVERSAL"
    low, high = d1_range
    return "RETRACEMENT" if low <= price <= high else "INTERNAL_DELIVERY"
