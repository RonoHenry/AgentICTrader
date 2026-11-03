"""The state machine and the timeline (algomind-dis Requirements 12, 14, §10, §13, §15).

One step per D1 close (DIS-D4). The state is UNDETERMINED, BULLISH, BEARISH, NEUTRAL or TRANSITIONAL:
- **Establish** (from UNDETERMINED or NEUTRAL): a side whose score is at least ``establish_score`` and leads by at
  least ``establish_lead``, with a live draw on its side (its most significant objective) and a protected level
  beyond price (the W1 SWING range's far extreme, else the D1 one). Without both it isn't held.
- **Hold** until, on a later close, in this order:
  - **invalidated:** the D1 candle closes beyond the protected level (a wick is liquidation) → UNDETERMINED;
  - **delivered:** the D1 candle trades at the draw → NEUTRAL (the episode concluded);
  - **expired:** its ``validity_closes``-th close → UNDETERMINED;
  - **challenged:** structure and external liquidity alone favour the other side by ``challenge_lead``, or the D1
    structure has broken the other way since it was set → TRANSITIONAL.
- **Resolve TRANSITIONAL** within ``resolve_closes``: to the other side if it establishes, back if the challenge
  fades, else NEUTRAL. The held side's ends still apply meanwhile.
- **Stale data** gives UNDETERMINED (Requirement 14.4).

§10.2's diagram has no edge into UNDETERMINED from a side; the ends above add BULLISH/BEARISH/TRANSITIONAL →
UNDETERMINED, as registered for H-AF (§10.4 names the ends, not the state after them).

The timeline (``run``) folds ``step`` over every D1 close of a market's frames, from its first. The state at t uses
only candles closed by t, so a restart is a replay (§15) and the same bars give the same timeline.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable, Iterable, Optional

import pandas as pd

from algomind_dis.analyzers.objectives import ranked
from algomind_dis.evidence import SCORED, Scores, gather, htf_scores, scores
from algomind_dis.frames import Frames
from algomind_dis.narrative import narrative
from algomind_dis.observe import Observation, observe, prepare
from algomind_dis.records import MarketNarrative, Transition
from algomind_dis.settings import V1, Settings

__all__ = ["ALLOWED", "Held", "Inputs", "Timeline", "inputs_from", "run", "step"]

SIDES = ("BULLISH", "BEARISH")
_OTHER = {"BULLISH": "BEARISH", "BEARISH": "BULLISH"}
#: §10.2's transitions, and the ends that go to UNDETERMINED (see above). Staying put is always allowed.
ALLOWED = {("UNDETERMINED", "BULLISH"), ("UNDETERMINED", "BEARISH"), ("UNDETERMINED", "NEUTRAL"),
           ("BULLISH", "TRANSITIONAL"), ("BEARISH", "TRANSITIONAL"), ("TRANSITIONAL", "BULLISH"),
           ("TRANSITIONAL", "BEARISH"), ("TRANSITIONAL", "NEUTRAL"), ("BULLISH", "NEUTRAL"), ("BEARISH", "NEUTRAL"),
           ("NEUTRAL", "BULLISH"), ("NEUTRAL", "BEARISH"),
           ("BULLISH", "UNDETERMINED"), ("BEARISH", "UNDETERMINED"), ("TRANSITIONAL", "UNDETERMINED"),
           ("NEUTRAL", "UNDETERMINED")}


@dataclass(frozen=True)
class Held:
    state: str = "UNDETERMINED"
    side: Optional[str] = None                   # the held side (in TRANSITIONAL, the side challenged)
    since: Optional[int] = None
    draw: Optional[float] = None
    protected: Optional[float] = None
    closes: int = 0                              # D1 closes since it was set
    challenger: Optional[str] = None
    challenge_closes: int = 0
    ended: Optional[tuple[str, int]] = None      # the last end: (delivered | invalidated | expired | ..., when)


@dataclass(frozen=True)
class Inputs:
    """What one step reads at a D1 close."""
    t: int
    high: float                                  # the D1 candle that closed at t
    low: float
    close: float
    bullish: float                               # S_B, S_S
    bearish: float
    htf_bullish: float                           # structure and external liquidity alone
    htf_bearish: float
    d1_direction: str
    d1_break_at: Optional[int]                   # the latest D1 break's close
    draw_up: Optional[float]                     # the most significant live objective on each side
    draw_down: Optional[float]
    protect_up: Optional[float]                  # a bullish side's protected level; a bearish side's
    protect_down: Optional[float]
    stale: bool = False

    def score(self, side: str) -> float:
        return self.bullish if side == "BULLISH" else self.bearish

    def htf(self, side: str) -> float:
        return self.htf_bullish if side == "BULLISH" else self.htf_bearish


def _establishes(side: str, x: Inputs, s: Settings) -> bool:
    draw, protected = (x.draw_up, x.protect_up) if side == "BULLISH" else (x.draw_down, x.protect_down)
    return (x.score(side) >= s.establish_score and x.score(side) - x.score(_OTHER[side]) >= s.establish_lead
            and draw is not None and protected is not None)


def _set(side: str, x: Inputs) -> Held:
    draw, protected = (x.draw_up, x.protect_up) if side == "BULLISH" else (x.draw_down, x.protect_down)
    return Held(side, side, x.t, draw, protected)


def _p(v: Optional[float]) -> str:
    return "-" if v is None else f"{v:.6g}"


def step(prev: Held, x: Inputs, s: Settings = V1) -> tuple[Held, Optional[str]]:
    """The state after the D1 close at ``x.t``, and why it changed (None when it didn't)."""
    if x.stale:
        if prev.state == "UNDETERMINED":
            return prev, None
        return Held(ended=("stale", x.t)), "the data is stale"
    if prev.state in ("BULLISH", "BEARISH", "TRANSITIONAL"):
        side, other = prev.side, _OTHER[prev.side]
        up = side == "BULLISH"
        if prev.protected is not None and (x.close < prev.protected if up else x.close > prev.protected):
            return (Held(ended=("invalidated", x.t)),
                    f"a D1 close {_p(x.close)} beyond the protected level {_p(prev.protected)}")
        if prev.draw is not None and (x.high >= prev.draw if up else x.low <= prev.draw):
            return Held("NEUTRAL", ended=("delivered", x.t)), f"the draw {_p(prev.draw)} traded"
        closes = prev.closes + 1
        if closes >= s.validity_closes:
            return Held(ended=("expired", x.t)), f"{closes} D1 closes without its draw or its invalidation"
        broke = x.d1_direction == other and x.d1_break_at is not None and prev.since is not None \
            and x.d1_break_at > prev.since
        lead = x.htf(other) - x.htf(side)
        challenged = lead >= s.challenge_lead or broke
        why = (f"structure and external liquidity favour {other.lower()} by {lead:.2f}" if lead >= s.challenge_lead
               else f"the D1 structure broke {other.lower()}")
        if prev.state == "TRANSITIONAL":
            if _establishes(other, x, s):
                return _set(other, x), f"the challenge established {other.lower()}: {x.score(other):.2f} vs " \
                                       f"{x.score(side):.2f}"
            if not challenged:
                return replace(prev, state=side, closes=closes, challenger=None, challenge_closes=0), \
                    "the challenge faded"
            if prev.challenge_closes + 1 >= s.resolve_closes:
                return Held("NEUTRAL", ended=("unresolved", x.t)), \
                    f"the challenge stayed unresolved for {s.resolve_closes} closes"
            return replace(prev, closes=closes, challenge_closes=prev.challenge_closes + 1), None
        if challenged:
            return replace(prev, state="TRANSITIONAL", closes=closes, challenger=other, challenge_closes=0), why
        return replace(prev, closes=closes), None
    for side in SIDES:
        if _establishes(side, x, s):
            return _set(side, x), f"established: {x.score(side):.2f} vs {x.score(_OTHER[side]):.2f}"
    return prev, None


def inputs_from(obs: Observation, sc: Scores, htf: tuple[float, float], stale: bool = False) -> Inputs:
    d1 = obs.frames["D1"]
    close = float(d1.c[-1])

    def extreme(tf: str, low: bool) -> Optional[float]:
        ctx = obs.contexts.get(tf)
        r = next((r for r in ctx.ranges if r.kind == "SWING"), None) if ctx else None
        if r is None:
            return None
        v = r.low if low else r.high
        return v if (v < close if low else v > close) else None

    up, down = ranked(obs.objectives, "BULLISH"), ranked(obs.objectives, "BEARISH")
    ev = obs.contexts["D1"].events
    pu = extreme("W1", True)
    pd_ = extreme("W1", False)
    return Inputs(obs.t, float(d1.h[-1]), float(d1.l[-1]), close, sc.bullish, sc.bearish, htf[0], htf[1],
                  obs.contexts["D1"].structural_direction, ev[-1].at if ev else None,
                  up[0].price if up else None, down[0].price if down else None,
                  pu if pu is not None else extreme("D1", True), pd_ if pd_ is not None else extreme("D1", False),
                  stale)


@dataclass(frozen=True)
class Timeline:
    market: str
    rows: pd.DataFrame                           # one row per D1 close: t, state, side, since, draw, protected, ...
    transitions: tuple[Transition, ...]
    narratives: dict                             # transition time -> the narrative at it


def run(market: str, frames: Frames, s: Settings = V1,
        calendar: Optional[Callable[[datetime], Iterable[str]]] = None, until: Optional[int] = None,
        progress: Optional[Callable[[int, int], None]] = None) -> Timeline:
    prepared = prepare(market, frames.full, s)
    closes = [int(t) for t in frames.closes("D1") if until is None or t <= until]
    held = Held()
    rows, transitions, narratives = [], [], {}
    for i, t in enumerate(closes):
        obs = observe(market, frames.at(t), s, prepared, calendar)
        items = gather(obs, s)
        sc = scores(items, SCORED, s)
        x = inputs_from(obs, sc, htf_scores(items, SCORED, s))
        new, why = step(held, x, s)
        if why is not None:
            hyp = new.side if new.state in SIDES or new.state == "TRANSITIONAL" else new.state
            n: MarketNarrative = narrative(obs, items, sc, hyp, new.protected,
                                           "ACTIVE" if new.state in SIDES else new.state, s)
            narratives[t] = n
            transitions.append(Transition(market, t, held.state, new.state, why, "D1", n.id))
        rows.append({"t": t, "state": new.state, "side": new.side, "since": new.since, "draw": new.draw,
                     "protected": new.protected, "closes": new.closes, "bullish": sc.bullish,
                     "bearish": sc.bearish, "htf_bullish": x.htf_bullish, "htf_bearish": x.htf_bearish,
                     "ended": new.ended[0] if new.ended and new.ended[1] == t else None})
        held = new
        if progress is not None:
            progress(i + 1, len(closes))
    return Timeline(market, pd.DataFrame(rows), tuple(transitions), narratives)
