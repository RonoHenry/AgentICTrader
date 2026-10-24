"""The context chain and the confluence stack, read for the trader's chart (Noculus's Chain layer, 2026-10-24).

The trader wants to see the chain's reads on the candles, to judge whether its definitions read price the way they
do. This serves, for any closed D1 candle, exactly what H-K and H-M read at its close (``search_chain``,
``search_stack``):
- each frame's dealing range, zone, trend, own direction and draw, and its POI each way, with their reasons;
- the chain's links (``PD_POI``) and the candle profile's (``PROFILE``);
- the thirteen votes, their score and the stack's call.

SMT abstains on the chart: a session loads one market, and the vote needs its partner.

The chart's D1 candles open at 17:00 New York. Each is read as the research reads a day bar: labelled with its
trading date at 00:00 UTC (``trading_days``). Times go back out as New York wall-clock seconds, the chart's own.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from algo_research.atlas.arrays import build_arrays
from algo_research.search_chain import SIDE, Ladder, armed_call, frame_states
from algo_research.search_d1 import d1_frame
from algo_research.search_stack import NET, VOTES
from algo_research.trend import SIGNALS, trend_signals
from liquidity_engine.context.chain import ChainRule, chain
from liquidity_engine.context.frame_state import ArrayPOI, FrameState, Objective
from liquidity_engine.context.ipda import ipda_ranges
from liquidity_engine.models import BiasDirection, Timeframe

__all__ = ["ChainView", "trading_days"]

#: A trading date's 00:00 UTC label against its candle's 17:00 New York open, in wall seconds.
_OPEN_BEFORE_LABEL = 7 * 3600
_ZONE = {"DISCOUNT": 1, "PREMIUM": -1}


def trading_days(rows: pd.DataFrame) -> pd.DataFrame:
    """The chart's D1 candles (``time`` = the 17:00 New York open, wall seconds) as research day bars: ``time`` the
    trading date at 00:00 UTC, and ``open_wall`` the candle's open on the chart."""
    opens = np.asarray(rows["time"], dtype=np.int64)
    return pd.DataFrame({"time": pd.to_datetime(opens + _OPEN_BEFORE_LABEL, unit="s", utc=True),
                         "open_wall": opens, **{k: rows[k].to_numpy(float) for k in ("open", "high", "low", "close")}})


def _wall(t: Optional[int]) -> Optional[int]:
    return None if t is None else int(t) - _OPEN_BEFORE_LABEL


def _objective(x: Optional[Objective]) -> Optional[dict]:
    if x is None:
        return None
    return {"price": x.price, "source": x.source, "tf": x.tf, "kind": x.kind, "formed": _wall(x.formed_at)}


def _poi(p: Optional[ArrayPOI]) -> Optional[dict]:
    if p is None:
        return None
    return {"low": p.low, "high": p.high, "near": p.near, "kind": p.kind, "tf": p.tf, "formed": _wall(p.formed_at),
            "reached": _wall(p.reached_at)}


def _frame(s: FrameState) -> dict:
    return {"tf": s.tf, "range": None if s.range is None else [s.range.low, s.range.high],
            "position": s.position, "zone": s.zone, "trend": s.trend.value, "own": s.own.value,
            "draw": _objective(s.own_draw), "poi_bull": _poi(s.poi(BiasDirection.BULLISH)),
            "poi_bear": _poi(s.poi(BiasDirection.BEARISH)), "reasons": dict(s.reasons)}


def _link(x) -> dict:
    return {"tf": x.tf, "context": x.context.value, "case": x.case, "draw": _objective(x.draw), "reason": x.reason}


class ChainView:
    """The chain and the stack at each D1 close of one market's ``days`` (``trading_days``), from the days to it
    only."""

    def __init__(self, days: pd.DataFrame, market: str = "X"):
        self.days = days.reset_index(drop=True)
        self.ladder = Ladder(self.days)
        frame = d1_frame(market, self.days)
        d1 = frame.bars[Timeframe.D1].reset_index(drop=True)
        signals = trend_signals(d1, build_arrays(frame, (Timeframe.D1,))) if len(d1) else None
        pad = len(self.days) - (len(signals) if signals is not None else 0)
        self.signals = {k: np.r_[signals[k].to_numpy(int) if signals is not None else [], np.zeros(pad, int)]
                        for k in SIGNALS}

    def at(self, i: int) -> dict:
        """What H-K and H-M read at day i's close, ready for the page."""
        days, weeks, months, w_forming, m_forming = self.ladder.at(i)
        votes = {name: 0 for name in VOTES}
        for k in SIGNALS:
            votes[k] = int(self.signals[k][i])
        out = {"i": int(i), "open": int(self.days["open_wall"].iloc[i]), "frames": [], "links": [], "profile": None}
        ranged = False
        if len(weeks) >= 2 and len(months) >= 2:
            states = frame_states(days, weeks, months, w_forming, m_forming, ipda_ranges(days))
            ranged = all(s.range is not None for s in states)
            main, profile = chain(states), chain(states, ChainRule.PROFILE)
            for s in states:
                votes[f"own-{s.tf}"] = SIDE[s.own] if s.own_draw is not None and ranged else 0
            votes["H-K"] = armed_call(main, states)
            votes["profile"] = armed_call(profile, states)
            votes["zone-W1"] = _ZONE.get(str(states[1].zone), 0)
            votes["zone-D1"] = _ZONE.get(str(states[2].zone), 0)
            out["frames"] = [_frame(s) for s in states]
            out["links"] = [_link(x) for x in main.links]
            out["profile"] = _link(profile.bias)
            out["unarmed"] = main.unarmed_reason
        score = int(sum(votes.values()))
        out.update(votes=votes, score=score, ranged=ranged,
                   call=int(np.sign(score)) if ranged and abs(score) >= NET else 0, chain_call=votes["H-K"])
        return out
