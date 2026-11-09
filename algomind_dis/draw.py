"""AlgoMindDIS v3, the draw first (algomind-dis Requirement 18; H-AM, registered 2026-11-07 before this code).

The trader (2026-11-07): "Remember Draw on Liquidity derives Directional Bias". v1 picked the side first and its
draw after. v3 names one draw and the side is the way to it. It reads v1's analyzers unchanged (``observe`` with
``V1``): the live objectives of MN1, W1 and D1 with their significance (the timeframe's weight x the type's, +0.25
for equal highs or lows), and the W1 structural direction.

Frozen with the registration (docs/research/SEARCH_2018_2024.md, "H-AM"):
- **The ADR:** v1's (``objectives.adr``, the mean D1 range of the last 20 days) at the pick. Every distance and the
  rejection band of a held draw use the ADR of its pick.
- **Reachable:** a live (IDENTIFIED or APPROACHING) objective beyond the close on its side, 0.5 to 5 ADR away.
- **The pick:**
  - **A, the draw alone:** the most significant reachable objective of both sides, then the nearest. A tie in both
    across the two sides is no pick.
  - **B, the draw with structure:** the W1 structural direction is the side (NEUTRAL: no pick), then the most
    significant reachable objective on it, then the nearest.
  - **NEAREST** (a companion, not judged): the nearest reachable objective of either side; a tie across the sides
    is no pick.
- **Refuted:** a draw that ended any way but delivery is never picked again by its rule (the same side and price).
- **The protected level:** the nearest live D1 swing objective (SWING, EQUAL or RANGE source) beyond the close on
  the other side, 0.5 to 5 ADR away; else the last closed week's opposite extreme within the same limits; else no
  pick (the next candidate is not tried).
- **The hold ends** at a later D1 close, the first of: invalidated (a close beyond the protected level); delivered
  (the candle trades at the draw); rejected (the candle comes within 0.5 ADR of the draw without trading it and
  closes in the quarter of its range farthest from it); expired (the 20th close); for B, the W1 structure no longer
  on the side. Then a new pick at the same close.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd

from algomind_dis.analyzers.objectives import LIVE, adr
from algomind_dis.frames import Frames
from algomind_dis.observe import Observation, observe, prepare
from algomind_dis.records import LiquidityObjective
from algomind_dis.settings import V1, Settings

__all__ = ["Close", "Draw", "Machine", "RULES", "close_of", "end_of", "pick", "protected", "reachable", "run"]

#: A and B are H-AM's; NEAREST is its geometric companion.
RULES = ("A", "B", "NEAREST")
SIDES = ("BULLISH", "BEARISH")
OTHER = {"BULLISH": "BEARISH", "BEARISH": "BULLISH"}
MIN_ADR, MAX_ADR = 0.5, 5.0
REJECT_ADR = 0.5                                 # v1's APPROACHING band
FAR_QUARTER = 0.25
VALIDITY = V1.validity_closes                    # 20
PROTECT_SOURCES = frozenset({"SWING_HIGH", "SWING_LOW", "EQUAL_HIGHS", "EQUAL_LOWS", "RANGE_HIGH", "RANGE_LOW"})
_TF_RANK = {"MN1": 0, "W1": 1, "D1": 2}


@dataclass(frozen=True)
class Close:
    """What a pick reads at one D1 close."""
    t: int
    high: float
    low: float
    close: float
    adr: float
    w1: str                                      # the W1 structural direction
    week_high: Optional[float]                   # the last closed week's
    week_low: Optional[float]
    objectives: tuple[LiquidityObjective, ...]


@dataclass(frozen=True)
class Draw:
    rule: str
    side: str
    price: float
    protected: float
    t: int                                       # the pick's close
    adr: float
    close: float
    tf: str
    kind: str
    source: str
    significance: float
    protected_from: str                          # "D1 <source>" or "previous week"

    @property
    def equal(self) -> bool:
        return self.source.startswith("EQUAL")


def close_of(obs: Observation, s: Settings = V1) -> Close:
    d1, w1 = obs.frames["D1"], obs.frames.get("W1")
    ctx = obs.contexts.get("W1")
    has_week = w1 is not None and len(w1) > 0
    return Close(obs.t, float(d1.h[-1]), float(d1.l[-1]), float(d1.c[-1]), adr(d1, s),
                 ctx.structural_direction if ctx is not None else "NEUTRAL",
                 float(w1.h[-1]) if has_week else None, float(w1.l[-1]) if has_week else None, obs.objectives)


def _distance(price: float, side: str, x: Close) -> float:
    """How far ``price`` lies beyond the close on ``side``, in the close's ADR (negative: on the other side)."""
    return ((price - x.close) if side == "BULLISH" else (x.close - price)) / x.adr


def _within(d: float) -> bool:
    return MIN_ADR <= d <= MAX_ADR


def reachable(x: Close, refuted: Iterable[tuple[str, float]] = ()) -> list[LiquidityObjective]:
    """The live objectives beyond the close on their side, 0.5 to 5 ADR away, that aren't refuted."""
    if not np.isfinite(x.adr) or x.adr <= 0:
        return []
    gone = refuted if isinstance(refuted, (set, frozenset)) else set(refuted)
    return [o for o in x.objectives if o.status in LIVE and o.side in SIDES and (o.side, o.price) not in gone
            and _within(_distance(o.price, o.side, x))]


def protected(x: Close, side: str) -> Optional[tuple[float, str]]:
    """A ``side`` draw's protected level and where it came from, or None."""
    other = OTHER[side]
    found = [o for o in x.objectives if o.tf == "D1" and o.source in PROTECT_SOURCES and o.status in LIVE
             and o.side == other and _within(_distance(o.price, other, x))]
    if found:
        o = min(found, key=lambda o: (_distance(o.price, other, x), o.source))
        return o.price, f"D1 {o.source}"
    week = x.week_low if side == "BULLISH" else x.week_high
    if week is not None and _within(_distance(week, other, x)):
        return week, "previous week"
    return None


def _sig(o: LiquidityObjective) -> float:
    return round(o.significance, 9)


def _best(cands: list[LiquidityObjective], x: Close, key: Callable) -> Optional[LiquidityObjective]:
    """The first by ``key`` (then frame and source, for a stable name); None when the other side ties it."""
    if not cands:
        return None
    full = lambda o: (*key(o), _TF_RANK.get(o.tf, 9), o.source)                # noqa: E731
    top = min(cands, key=full)
    if any(o.side != top.side and key(o) == key(top) for o in cands):
        return None
    return top


def pick(rule: str, x: Close, refuted: Iterable[tuple[str, float]] = ()) -> Optional[Draw]:
    """The rule's draw at this close, with its protected level; None when there is none."""
    cands = reachable(x, refuted)
    dist = lambda o: _distance(o.price, o.side, x)                             # noqa: E731
    if rule == "A":
        top = _best(cands, x, lambda o: (-_sig(o), dist(o)))
    elif rule == "B":
        if x.w1 not in SIDES:
            return None
        top = _best([o for o in cands if o.side == x.w1], x, lambda o: (-_sig(o), dist(o)))
    elif rule == "NEAREST":
        top = _best(cands, x, lambda o: (dist(o),))
    else:
        raise ValueError(f"unknown rule {rule!r}")
    if top is None:
        return None
    prot = protected(x, top.side)
    if prot is None:
        return None
    return Draw(rule, top.side, float(top.price), float(prot[0]), x.t, x.adr, x.close, top.tf, top.kind,
                top.source, float(top.significance), prot[1])


def end_of(d: Draw, closes: int, x: Close) -> Optional[str]:
    """Why a held draw ends at this close (``closes`` counts the closes since its pick, this one included)."""
    up = d.side == "BULLISH"
    if (x.close < d.protected) if up else (x.close > d.protected):
        return "invalidated"
    if (x.high >= d.price) if up else (x.low <= d.price):
        return "delivered"
    near = (x.high >= d.price - REJECT_ADR * d.adr) if up else (x.low <= d.price + REJECT_ADR * d.adr)
    span = x.high - x.low
    far = (x.close <= x.low + FAR_QUARTER * span) if up else (x.close >= x.high - FAR_QUARTER * span)
    if near and far:
        return "rejected"
    if closes >= VALIDITY:
        return "expired"
    if d.rule == "B" and x.w1 != d.side:
        return "structure turned"
    return None


@dataclass
class Machine:
    """One rule's held draw, stepped at each D1 close."""
    rule: str
    held: Optional[Draw] = None
    closes: int = 0
    refuted: set = field(default_factory=set)

    def step(self, x: Close) -> tuple[Optional[str], Optional[Draw]]:
        """(why the held draw ended at this close, the new pick at it)."""
        ended = None
        if self.held is not None:
            self.closes += 1
            ended = end_of(self.held, self.closes, x)
            if ended is None:
                return None, None
            if ended != "delivered":
                self.refuted.add((self.held.side, self.held.price))
            self.held = None
        new = pick(self.rule, x, self.refuted)
        if new is not None:
            self.held, self.closes = new, 0
        return ended, new


def run(market: str, frames: Frames, rules: Iterable[str] = RULES, s: Settings = V1,
        prepared: Optional[dict] = None, until: Optional[int] = None,
        progress: Optional[Callable[[int, int], None]] = None) -> dict[str, pd.DataFrame]:
    """Every rule over every D1 close of the frames, from the first.

    ``closes``: one row per close (its candle, ADR and W1 direction, and each rule's held draw after the step);
    ``picks``: one row per pick, with how and when it ended (``open`` when the bars end first)."""
    rules = tuple(rules)
    prepared = prepare(market, frames.full, s) if prepared is None else prepared
    times = [int(t) for t in frames.closes("D1") if until is None or t <= until]
    machines = {r: Machine(r) for r in rules}
    picks: dict[str, list[dict]] = {r: [] for r in rules}
    rows = []
    for i, t in enumerate(times):
        x = close_of(observe(market, frames.at(t), s, prepared), s)
        row = {"t": t, "high": x.high, "low": x.low, "close": x.close, "adr": x.adr, "w1": x.w1}
        for r, m in machines.items():
            ended, new = m.step(x)
            if ended is not None:
                picks[r][-1].update(ended=ended, end_t=t)
            if new is not None:
                picks[r].append({"market": market, "rule": r, "t": t, "side": new.side, "draw": new.price,
                                 "protected": new.protected, "adr": new.adr, "close": new.close, "tf": new.tf,
                                 "kind": new.kind, "source": new.source, "equal": new.equal,
                                 "significance": new.significance, "protected_from": new.protected_from,
                                 "ended": "open", "end_t": np.nan})
            h = m.held
            row.update({f"{r}_side": h.side if h else None, f"{r}_draw": h.price if h else np.nan,
                        f"{r}_protected": h.protected if h else np.nan, f"{r}_since": h.t if h else np.nan,
                        f"{r}_ended": ended})
        rows.append(row)
        if progress is not None:
            progress(i + 1, len(times))
    cols = ["market", "rule", "t", "side", "draw", "protected", "adr", "close", "tf", "kind", "source", "equal",
            "significance", "protected_from", "ended", "end_t"]
    return {"closes": pd.DataFrame(rows),
            "picks": pd.DataFrame([p for r in rules for p in picks[r]], columns=cols)}
