"""The context chain (context-engine Requirement 4, task 278).

A ladder's frame states, highest first, each read in the light of the one above it:
- ``PD_POI`` (CE-D5): a child goes with its parent's context direction, except when price sits in the parent's
  wrong zone (premium for a bullish parent, discount for a bearish one) and the parent has an unreached point of
  interest for its direction. Then the child goes against the parent, toward that POI's near edge: selling short
  term in a long-term bull market. A NEUTRAL parent gives a NEUTRAL child: no trade without context.
- ``PROFILE``: the candle profile at any frame (liquidity-engine Requirement 21). The child follows a trending
  parent to the parent's nearest objective, else goes to its own nearer objective. On W1 -> D1 it is
  ``CandleProfileAnalyzer`` (Property 6).

Every link records its case and a reason. Pure: the states carry everything (Property 2 is theirs).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

from liquidity_engine.context.frame_state import ArrayPOI, FrameState, Objective
from liquidity_engine.models import BiasDirection

__all__ = ["Chain", "ChainRule", "Link", "chain"]

BULL, BEAR, NEUTRAL = BiasDirection.BULLISH, BiasDirection.BEARISH, BiasDirection.NEUTRAL
_OPPOSITE = {BULL: BEAR, BEAR: BULL}
#: The zone a direction's retracement runs from: a bullish frame in premium is due a move down to its POI.
_WRONG_ZONE = {BULL: "PREMIUM", BEAR: "DISCOUNT"}


class ChainRule(str, Enum):
    PD_POI = "PD_POI"
    PROFILE = "PROFILE"


@dataclass(frozen=True)
class Link:
    """One frame of the chain (Requirement 4.4)."""
    tf: str
    own: BiasDirection
    context: BiasDirection
    case: str                    # TOP, WITH_PARENT, TO_PARENT_POI, PARENT_NEUTRAL; PROFILE: PARENT_TREND, OWN_NEARER
    draw: Optional[Objective]
    poi: Optional[ArrayPOI]      # the parent's POI for its direction, as read
    reason: str


@dataclass(frozen=True)
class Chain:
    rule: ChainRule
    links: Tuple[Link, ...]

    @property
    def bias(self) -> Link:
        """The lowest frame's link: the bias frame."""
        return self.links[-1]

    @property
    def armed(self) -> bool:
        return self.unarmed_reason is None

    @property
    def unarmed_reason(self) -> Optional[str]:
        if self.bias.context == NEUTRAL:
            return "CONTEXT_NEUTRAL"
        if self.bias.draw is None:
            return "NO_DRAW"
        return None


def chain(states: Sequence[FrameState], rule: ChainRule = ChainRule.PD_POI) -> Chain:
    """The chain over ``states``, highest frame first (Requirement 4)."""
    top = states[0]
    draw = f", toward {top.own_draw.reason()}" if top.own_draw is not None else ""
    links = [Link(top.tf, top.own, top.own, "TOP", top.own_draw, None,
                  f"{top.tf} top frame: its own direction, {top.own.value}{draw}")]
    for parent, child in zip(states, states[1:]):
        step = _pd_poi(parent, links[-1], child) if rule == ChainRule.PD_POI else _profile(parent, child)
        links.append(step)
    return Chain(rule, tuple(links))


def _pd_poi(parent: FrameState, above: Link, child: FrameState) -> Link:
    d = above.context
    if d == NEUTRAL:
        return Link(child.tf, child.own, NEUTRAL, "PARENT_NEUTRAL", None, None,
                    f"{parent.tf} is NEUTRAL, so {child.tf} is NEUTRAL")
    poi = parent.poi(d)
    against = _OPPOSITE[d]
    ahead = poi is not None and (poi.near < child.price if against == BEAR else poi.near > child.price)
    if poi is not None and poi.reached_at is None and parent.zone == _WRONG_ZONE[d] and ahead:
        draw = Objective("POI", poi.kind, poi.tf, poi.near, against, poi.formed_at)
        return Link(child.tf, child.own, against, "TO_PARENT_POI", draw, poi,
                    f"{parent.tf} {d.value} in its {parent.zone} with its POI {poi.reason()}: {child.tf} "
                    f"{against.value} toward the POI's near edge {poi.near:.5g}")
    target = child.nearest(d)
    why = ("no POI" if poi is None else "its POI reached" if poi.reached_at is not None else
           f"price in its {parent.zone or 'unranged frame'}")
    toward = f"toward {target.reason()}" if target is not None else f"with no {child.tf} objective that way"
    return Link(child.tf, child.own, d, "WITH_PARENT", target, poi,
                f"{parent.tf} {d.value}, {why}: {child.tf} {d.value} {toward}")


def _profile(parent: FrameState, child: FrameState) -> Link:
    trend = parent.trend
    if trend != NEUTRAL:
        draw = child.nearest(trend, tf=parent.tf) or child.nearest(trend)
        if draw is None:
            return Link(child.tf, child.own, NEUTRAL, "PARENT_TREND", None, None,
                        f"{parent.tf} trending {trend.value} with no objective that way: NEUTRAL")
        return Link(child.tf, child.own, trend, "PARENT_TREND", draw, None,
                    f"{parent.tf} trending {trend.value}: {child.tf} toward {draw.reason()}")
    direction, draw = child.nearer()
    toward = f"toward the nearer {draw.reason()}" if draw is not None else "neither side nearer: NEUTRAL"
    return Link(child.tf, child.own, direction, "OWN_NEARER", draw, None,
                f"{parent.tf} not trending: {child.tf} {toward}")
