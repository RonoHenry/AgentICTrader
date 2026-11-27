"""The narrative (algomind-dis Requirement 10, §9.1, §9.2): the hypothesis as a structured explanation.

``narrative`` builds the record; its text is ``render`` of the record's own fields by fixed templates, never
generated (§21.5: an LLM may only ever rephrase it, outside the decision).
"""
from __future__ import annotations

from typing import Optional, Sequence

import pandas as pd

from algomind_dis.analyzers.objectives import ranked
from algomind_dis.evidence import Scores, counted
from algomind_dis.records import Evidence, MarketNarrative, make_id
from algomind_dis.settings import V1, Settings

__all__ = ["draw_text", "narrative", "render"]


def draw_text(o) -> str:
    return f"{o.tf} {o.source} {o.price:.6g} ({o.kind}, significance {o.significance:.2f})"


def render(n: MarketNarrative) -> str:
    when = pd.Timestamp(n.at, tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"{n.market} at {when}: {n.hypothesis} ({n.status}), confidence {n.confidence:.2f}.",
             f"Delivery on {n.primary_tf}: {n.delivery_state}."]
    if n.primary_objective:
        lines.append(f"The draw: {n.primary_objective}.")
    if n.supporting:
        lines.append("Supporting: " + "; ".join(e.text for e in n.supporting) + ".")
    if n.conflicting:
        lines.append("Against: " + "; ".join(e.text for e in n.conflicting) + ".")
    if n.invalidation:
        lines.append("Proved wrong by " + " or ".join(n.invalidation) + ".")
    return "\n".join(lines)


def narrative(obs, items: Sequence[Evidence], sc: Scores, hypothesis: str, protected: Optional[float],
              status: str, s: Settings = V1) -> MarketNarrative:
    """The narrative of ``hypothesis`` (BULLISH, BEARISH, NEUTRAL or UNDETERMINED) at an observation."""
    sided = hypothesis in ("BULLISH", "BEARISH")
    use = counted(items, s=s)
    supporting = tuple(e for e in use if sided and e.direction == hypothesis)
    conflicting = tuple(e for e in use if sided and e.direction != hypothesis)
    best = ranked(obs.objectives, hypothesis) if sided else []
    invalidation = ((f"a D1 close {'under' if hypothesis == 'BULLISH' else 'above'} {protected:.6g}",)
                    if sided and protected is not None else ())
    d1 = obs.contexts["D1"].delivery
    fields = dict(id=make_id(obs.market, obs.t, hypothesis, status), market=obs.market, at=obs.t, primary_tf="D1",
                  hypothesis=hypothesis, delivery_state=d1.state if d1 else "UNCONFIRMED",
                  primary_objective=draw_text(best[0]) if best else None, supporting=supporting,
                  conflicting=conflicting, invalidation=invalidation,
                  confidence=float(max(0.0, sc.lead(hypothesis))) if sided else 0.0, status=status)
    draft = MarketNarrative(**fields, text="")
    return MarketNarrative(**fields, text=render(draft))
