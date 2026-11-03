"""AlgoMindDIS on the Noculus engine chart (algomind-dis Requirement 16.3, task 407): what the chart draws.

The chart's D1 candles are trading dates (the 17:00 New York close); ``frames.from_daily`` dates them at 00:00 UTC,
so a time here in UTC ns is the chart's New York wall time seven hours earlier (``to_wall``). ``ChartView`` keeps one
market's timeline and its prepared reads, and gives:
- ``rows``: the state at each D1 close in a window, for the strip;
- ``transitions``: each change, with its trigger;
- ``detail``: everything at one close, for the lines, boxes and the card: the side with its draw and protected
  level, the scores by category, the counted evidence both ways, each frame's structure, range and delivery, the
  best objectives and the arrays in play, and the narrative's text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from algomind_dis.analyzers.arrays import counts
from algomind_dis.analyzers.objectives import ranked
from algomind_dis.evidence import SCORED, counted, gather, htf_scores, scores
from algomind_dis.frames import Frames
from algomind_dis.narrative import draw_text, narrative
from algomind_dis.observe import observe, prepare
from algomind_dis.settings import V1, V2, Settings
from algomind_dis.state import Timeline, run

__all__ = ["ChartView", "HAF", "to_wall"]

_SHIFT = 7 * 3600
#: What H-AF found (search log, 2026-11-03), shown beside the layer.
HAF = ("v1 was tested 1996-2022 (H-AF, failed): its sides reached their draw 12.4% of the time, random starts at the "
       "same distances 12.4%; weeks under a side closed on it 52.8% against 49.9% drift. v1 read the engine's arrays; "
       "v2 reads yours (the CISD run's bodies, breakers ended by a close back through) and is untested. Shown to "
       "watch, not to trade.")


def to_wall(t: Optional[int]) -> Optional[int]:
    """A UTC-date time (ns) as the chart's New York wall seconds."""
    return None if t is None or (isinstance(t, float) and not np.isfinite(t)) else int(t) // 10**9 - _SHIFT


def _num(x) -> Optional[float]:
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else float(x)


@dataclass
class ChartView:
    market: str
    frames: Frames
    s: Settings = V1
    prepared: dict = field(init=False)
    timeline: Timeline = field(init=False)
    _detail: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.prepared = prepare(self.market, self.frames.full, self.s)
        self.timeline = run(self.market, self.frames, self.s, prepared=self.prepared)

    def _walls(self) -> np.ndarray:
        return (self.timeline.rows["t"].to_numpy(np.int64) // 10**9 - _SHIFT) if len(self.timeline.rows) else \
            np.array([], dtype=np.int64)

    def rows(self, since: int, clock: int) -> list[dict]:
        r = self.timeline.rows
        w = self._walls()
        keep = (w <= clock) & (w >= since)
        out = []
        for i in np.flatnonzero(keep):
            x = r.iloc[i]
            out.append({"open": int(w[i]) - 86400, "close": int(w[i]), "state": x["state"], "side": x["side"],
                        "draw": _num(x["draw"]), "protected": _num(x["protected"]),
                        "bullish": round(float(x["bullish"]), 3), "bearish": round(float(x["bearish"]), 3)})
        return out

    def transitions(self, since: int, clock: int) -> list[dict]:
        return [{"close": to_wall(tr.at), "previous": tr.previous, "new": tr.new, "trigger": tr.trigger}
                for tr in self.timeline.transitions if since <= to_wall(tr.at) <= clock]

    def index_at(self, clock: int) -> Optional[int]:
        w = self._walls()
        k = int(np.searchsorted(w, clock, "right")) - 1
        return k if k >= 0 else None

    def detail(self, k: int) -> dict:
        if k in self._detail:
            return self._detail[k]
        row = self.timeline.rows.iloc[k]
        t = int(row["t"])
        obs = observe(self.market, self.frames.at(t), self.s, self.prepared)
        items = gather(obs, self.s)
        sc = scores(items, SCORED, self.s)
        htf = htf_scores(items, SCORED, self.s)
        state = row["state"]
        sided = state in ("BULLISH", "BEARISH", "TRANSITIONAL")
        hyp = row["side"] if sided else state
        n = narrative(obs, items, sc, hyp, _num(row["protected"]), "ACTIVE" if state in ("BULLISH", "BEARISH")
                      else state, self.s)
        use = counted(items, s=self.s)

        def ev(e) -> dict:
            return {"category": e.category, "direction": e.direction, "tf": e.tf, "significance": e.significance,
                    "text": e.text}

        frames = {}
        for tf, ctx in obs.contexts.items():
            swing = next(((r, p) for r, p in zip(ctx.ranges, ctx.positions) if r.kind == "SWING"), None)
            frames[tf] = {"structure": ctx.structural_direction, "delivery": ctx.delivery.state if ctx.delivery else None,
                          "range": None if swing is None else {"low": swing[0].low, "high": swing[0].high,
                                                               "eq": swing[0].equilibrium, "zone": swing[1].zone,
                                                               "position": swing[1].position, "valid": swing[0].valid}}
        arrays = [{"tf": a.tf, "kind": a.kind, "direction": a.direction, "low": a.low, "high": a.high,
                   "formed": to_wall(a.formed_at), "zone": a.zone, "counts": counts(a, obs.frames[a.tf], self.s),
                   "displaced": a.displacement, "after_sweep": a.after_sweep}
                  for c in obs.contexts.values() for a in c.arrays]

        def best(side: str) -> list[dict]:
            return [{"tf": o.tf, "source": o.source, "price": o.price, "kind": o.kind, "status": o.status,
                     "significance": round(o.significance, 3), "text": draw_text(o)} for o in ranked(obs.objectives, side)[:3]]

        out = {"close": to_wall(t), "version": self.s.version, "state": state, "side": row["side"],
               "since": to_wall(row["since"]) if row["since"] is not None and np.isfinite(row["since"]) else None,
               "draw": _num(row["draw"]), "protected": _num(row["protected"]), "closes": int(row["closes"]),
               "bullish": sc.bullish, "bearish": sc.bearish, "htf": list(htf),
               "categories": {c: list(v) for c, v in sc.by_category.items()},
               "weights": dict(self.s.category_weights),
               "bar": {"score": self.s.establish_score, "lead": self.s.establish_lead,
                       "challenge": self.s.challenge_lead},
               "supporting": [ev(e) for e in use if sided and e.direction == row["side"]],
               "conflicting": [ev(e) for e in use if sided and e.direction != row["side"]],
               "evidence": [ev(e) for e in use], "frames": frames, "arrays": arrays,
               "objectives": {"BULLISH": best("BULLISH"), "BEARISH": best("BEARISH")},
               "draw_text": n.primary_objective, "narrative": n.text, "time": obs.time.weekday,
               "volatility": {"adr": obs.volatility.adr, "ratio": obs.volatility.last_ratio,
                              "phase": obs.volatility.phase}}
        self._detail[k] = out
        return out
