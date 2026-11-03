"""The contract and setup qualification (algomind-dis Requirement 13, §12).

``output`` gives the versioned ``DirectionalBiasOutput`` the setup engine reads. ``qualify`` says how a setup stands
against it (§12.1): ALIGNED, COUNTERTREND_JUSTIFIED, INSUFFICIENT_CONTEXT or INVALIDATED_CONTEXT, with a reason.
``thesis_entry`` writes an active side in the engine's thesis format (``agent.order_intent``'s THESIS mode: side,
draw, protected, since), which is the only way into the setup engine (DIS-D8). Risk stays outside (§12.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import pandas as pd

from algomind_dis import CONTRACT, VERSION
from algomind_dis.analyzers.objectives import ranked
from algomind_dis.analyzers.ranges import primary
from algomind_dis.evidence import Scores, counted
from algomind_dis.records import DirectionalBiasOutput, Evidence, MarketNarrative, make_id
from algomind_dis.settings import V1, Settings

__all__ = ["OUTCOMES", "Qualification", "Setup", "output", "qualify", "thesis_entry"]

OUTCOMES = ("ALIGNED", "COUNTERTREND_JUSTIFIED", "INSUFFICIENT_CONTEXT", "INVALIDATED_CONTEXT")
SIDES = ("BULLISH", "BEARISH")


def _iso(t: Optional[int]) -> Optional[str]:
    return None if t is None else pd.Timestamp(int(t), tz="UTC").isoformat()


def output(obs, held, items: Sequence[Evidence], sc: Scores, narrative: Optional[MarketNarrative] = None,
           data_quality: str = "OK", s: Settings = V1) -> DirectionalBiasOutput:
    """The contract at an observation, from the state machine's ``Held``."""
    sided = held.state in SIDES or held.state == "TRANSITIONAL"
    direction = held.side if sided else held.state
    if held.state == "TRANSITIONAL":
        state = "TRANSITIONAL"
    elif held.state == "UNDETERMINED" and held.ended and held.ended[0] in ("invalidated", "expired"):
        state = held.ended[0].upper()
    else:
        state = "ACTIVE"
    by_tf = {tf: c.ranges for tf, c in obs.contexts.items()}
    rng = primary(by_tf, "SIDE") or primary(by_tf, "LOCATION")
    pd_ctx = {tf: p for tf, c in obs.contexts.items() for r, p in zip(c.ranges, c.positions) if r.kind == "SWING"}
    use = counted(items, s=s)
    objs = tuple(ranked(obs.objectives, direction)[:5]) if sided else \
        tuple(sorted((o for o in obs.objectives if o.status in ("IDENTIFIED", "APPROACHING")),
                     key=lambda o: -o.significance)[:5])
    d1 = obs.contexts["D1"].delivery
    invalidation = ((f"a D1 close {'under' if direction == 'BULLISH' else 'above'} {held.protected:.6g}",)
                    if sided and held.protected is not None else ())
    return DirectionalBiasOutput(
        obs.market, make_id(obs.market, obs.t, held.state, direction, held.since), VERSION, CONTRACT, direction,
        state, float(max(0.0, sc.lead(direction))) if sided else 0.0, _iso(obs.t), dict(obs.contexts), rng, pd_ctx,
        objs, tuple(e for e in use if sided and e.direction == direction),
        tuple(e for e in use if sided and e.direction != direction), d1.state if d1 else "UNCONFIRMED",
        invalidation, None, narrative.id if narrative else None, data_quality)


@dataclass(frozen=True)
class Setup:
    """A setup the engine found: its direction, when, its target, and what supports a countertrend reading."""
    direction: str
    at: int
    target: Optional[float] = None
    at_htf_array: bool = False           # from an opposing W1 or D1 array in its zone
    after_sweep: bool = False


@dataclass(frozen=True)
class Qualification:
    outcome: str
    reason: str


def qualify(setup: Setup, bias: DirectionalBiasOutput) -> Qualification:
    side, state = bias.primary_direction, bias.state
    if state in ("INVALIDATED", "EXPIRED"):
        return Qualification("INVALIDATED_CONTEXT", f"the side ended ({state.lower()}) at or before the setup")
    if side not in SIDES:
        return Qualification("INSUFFICIENT_CONTEXT", f"no active side ({side.lower()})")
    challenged = " (challenged: TRANSITIONAL)" if state == "TRANSITIONAL" else ""
    if setup.direction == side:
        return Qualification("ALIGNED", f"with the {side.lower()} side{challenged}")
    d1 = bias.timeframe_contexts.get("D1")
    rng = next((r for r in d1.ranges if r.kind == "SWING"), None) if d1 else None
    inside = setup.target is not None and rng is not None and rng.low <= setup.target <= rng.high
    if inside and setup.at_htf_array and setup.after_sweep:
        return Qualification("COUNTERTREND_JUSTIFIED",
                             f"against the {side.lower()} side, toward {setup.target:.6g} inside the D1 range, "
                             f"from an opposing higher-timeframe array after a sweep")
    missing = [w for w, ok in (("a target inside the D1 range", inside), ("an opposing HTF array", setup.at_htf_array),
                               ("a sweep", setup.after_sweep)) if not ok]
    return Qualification("INSUFFICIENT_CONTEXT",
                         f"against the {side.lower()} side without {', '.join(missing)}")


def thesis_entry(held, source: str = f"algomind_dis {VERSION}") -> Optional[dict]:
    """An active side as one trading date's thesis entry, or None."""
    if held.state not in SIDES or held.draw is None or held.protected is None or held.since is None:
        return None
    return {"side": held.side, "draw": float(held.draw), "protected": float(held.protected),
            "since": _iso(held.since), "source": source}
