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
from algomind_dis.analyzers.arrays import ArrayTable, array_table, arrays, in_play, raw_arrays, reacting
from algomind_dis.analyzers.context import TimeContext, VolatilityContext, time_context, volatility_context
from algomind_dis.analyzers.delivery import Seq, delivery, sequences
from algomind_dis.analyzers.objectives import ObjectiveTable, objective_table, objectives
from algomind_dis.analyzers.ranges import displacements, position, ranges
from algomind_dis.analyzers.structure import LOOKBACK, direction, events
from algomind_dis.records import LiquidityObjective, StructureEvent, TimeframeContext
from algomind_dis.settings import V1, Settings
from liquidity_engine.context.frame_state import Candles, _Array, _arrays
from liquidity_engine.context.measures import swing_highs, swing_lows

__all__ = ["Observation", "Prepared", "observe", "prepare"]

#: The structure events a context keeps (the latest).
KEEP_EVENTS = 3


@dataclass(frozen=True)
class Prepared:
    """One frame's prefix-stable reads over its full history: each item is dated or indexed, so a cut reads the
    ones complete by its last candle and gets what reading the cut afresh gives."""
    events: tuple[StructureEvent, ...]
    arrays: list[_Array]
    seqs: list[Seq]
    labels: np.ndarray
    swing_idx: tuple[np.ndarray, np.ndarray]
    disp: np.ndarray
    objectives: ObjectiveTable
    array_table: ArrayTable


def prepare(market: str, full: Mapping[str, Candles], s: Settings = V1) -> dict[str, Prepared]:
    path = full["D1"]
    out = {}
    for tf, c in full.items():
        if not len(c):
            continue
        idx = (np.array(swing_highs(c.h, LOOKBACK), dtype=np.int64),
               np.array(swing_lows(c.l, LOOKBACK), dtype=np.int64))
        out[tf] = Prepared(events(market, c), raw_arrays(c, s), sequences(c, s), label_phases(c.o, c.h, c.l, c.c), idx,
                           displacements(c, s), objective_table(c, path), array_table(c, s))
    return out


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
    def hint(tf: str) -> Optional[Prepared]:
        return prepared.get(tf) if prepared else None

    by_tf = {tf: ranges(market, c, s, hint(tf).swing_idx if hint(tf) else None, hint(tf).disp if hint(tf) else None)
             for tf, c in frames.items()}
    found = {}
    for tf, c in frames.items():
        p = prepared.get(tf) if prepared else None
        found[tf] = tuple(e for e in p.events if e.at <= t) if p else events(market, c)
    w1 = direction(found["W1"], t) if "W1" in found else "NEUTRAL"
    objs = objectives(market, frames, price, by_tf, s, path=d1,
                      tables={tf: p.objectives for tf, p in prepared.items()} if prepared else None)
    contexts = {}
    for tf, c in frames.items():
        p = prepared.get(tf) if prepared else None
        rng = next((r for r in by_tf[tf] if r.kind == "SWING"), None)
        if p is not None:
            play = in_play(market, c, price, rng, w1, p.array_table, s)
        else:
            play = tuple(a for a in arrays(market, c, price, rng, w1, s) if reacting(a, c, s))
        dl = delivery(c, s, seqs=p.seqs if p else None, labels=p.labels if p else None,
                      disp=p.disp if p else None)
        contexts[tf] = TimeframeContext(
            tf, direction(found[tf], t), price, by_tf[tf], tuple(position(r, price, s) for r in by_tf[tf]),
            tuple(o for o in objs if o.tf == tf), play, dl,
            found[tf][-KEEP_EVENTS:])
    labels = prepared["D1"].labels if prepared and "D1" in prepared else None
    return Observation(market, t, price, contexts, objs, time_context(d1, calendar),
                       volatility_context(d1, s, labels), frames)
