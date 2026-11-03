"""One market at one D1 close: every analyzer's records (algomind-dis Requirements 3-8, §5.1).

``observe`` takes the closed frames at t (``Frames.at``) and gives each frame's ``TimeframeContext`` (its structure,
ranges and positions, objectives, the arrays in play and its delivery), the objectives of every frame, and the time
and volatility context. Nothing reads past the frames' last close.

The replay computes what is prefix-stable once per frame (``prepare``: the structure events, the arrays, the
delivery sequences and the phase labels, each dated) and passes it in; each close reads the parts complete by then.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, Mapping, Optional

import numpy as np

from algo_research.phases import label_phases
from algomind_dis.analyzers.arrays import arrays, reacting
from algomind_dis.analyzers.context import TimeContext, VolatilityContext, time_context, volatility_context
from algomind_dis.analyzers.delivery import Seq, delivery, sequences
from algomind_dis.analyzers.objectives import objectives
from algomind_dis.analyzers.ranges import position, ranges
from algomind_dis.analyzers.structure import direction, events
from algomind_dis.records import LiquidityObjective, StructureEvent, TimeframeContext
from algomind_dis.settings import V1, Settings
from liquidity_engine.context.frame_state import Candles, _Array, _arrays

__all__ = ["Observation", "Prepared", "observe", "prepare"]

#: The structure events a context keeps (the latest).
KEEP_EVENTS = 3


@dataclass(frozen=True)
class Prepared:
    """One frame's prefix-stable reads over its full history."""
    events: tuple[StructureEvent, ...]
    arrays: list[_Array]
    seqs: list[Seq]
    labels: np.ndarray


def prepare(market: str, full: Mapping[str, Candles], s: Settings = V1) -> dict[str, Prepared]:
    return {tf: Prepared(events(market, c), _arrays(c), sequences(c, s), label_phases(c.o, c.h, c.l, c.c))
            for tf, c in full.items() if len(c)}


@dataclass(frozen=True)
class Observation:
    market: str
    t: int
    price: float
    contexts: Mapping[str, TimeframeContext]
    objectives: tuple[LiquidityObjective, ...]
    time: TimeContext
    volatility: VolatilityContext
    frames: Mapping[str, Candles] = field(compare=False, repr=False)


def observe(market: str, frames: Mapping[str, Candles], s: Settings = V1,
            prepared: Optional[Mapping[str, Prepared]] = None,
            calendar: Optional[Callable[[datetime], Iterable[str]]] = None) -> Observation:
    frames = {tf: c for tf, c in frames.items() if len(c)}
    d1 = frames["D1"]
    t, price = int(d1.end[-1]), float(d1.c[-1])
    by_tf = {tf: ranges(market, c, s) for tf, c in frames.items()}
    found = {}
    for tf, c in frames.items():
        p = prepared.get(tf) if prepared else None
        found[tf] = tuple(e for e in p.events if e.at <= t) if p else events(market, c)
    w1 = direction(found["W1"], t) if "W1" in found else "NEUTRAL"
    objs = objectives(market, frames, price, by_tf, s, path=d1)
    contexts = {}
    for tf, c in frames.items():
        p = prepared.get(tf) if prepared else None
        rng = next((r for r in by_tf[tf] if r.kind == "SWING"), None)
        arr = arrays(market, c, price, rng, w1, s, raw=p.arrays if p else None)
        dl = delivery(c, s, seqs=p.seqs if p else None, labels=p.labels if p else None)
        contexts[tf] = TimeframeContext(
            tf, direction(found[tf], t), price, by_tf[tf], tuple(position(r, price, s) for r in by_tf[tf]),
            tuple(o for o in objs if o.tf == tf), tuple(a for a in arr if reacting(a, c, s)), dl,
            found[tf][-KEEP_EVENTS:])
    labels = prepared["D1"].labels if prepared and "D1" in prepared else None
    return Observation(market, t, price, contexts, objs, time_context(d1, calendar),
                       volatility_context(d1, s, labels), frames)
