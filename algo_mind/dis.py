"""The directional state, AlgoMindDIS's core (context-engine Requirement 35).

One held side per market: set by a source's turn, with the evidence behind it, its draw and its protected swing,
kept until it is delivered (price trades at the draw's CE) or invalidated (a D1 candle closes beyond the protected
swing; a wick is liquidation), and UNDETERMINED otherwise. A turn on the live side replaces it; one against it is
recorded as ignored (manipulation) and changes nothing. The state at t reads only candles closed by t.

The first source is reader v0's narrative (``algo_research.sequence``, Requirement 33.2, frozen at fe84645), whose
``_turns``, ``_signed`` and ``_end`` run here unchanged. ``daily_market`` gives them the D1 and W1 frames of a long
daily history (the source's dates; weeks Monday to Friday, a weekend day merged into Monday), so they read 28
years (H-AE, ``algo_research.search_narrative``).
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from algo_research import sequence as seq

__all__ = ["DirectionalState", "Span", "DailyMarket", "daily_market", "reader_turns", "states", "state_at",
           "terminal_market", "week_checks"]

SOURCE, VERSION = "reader", "v0-fe84645"
_DAY = pd.Timedelta(days=1)
_HOUR = pd.Timedelta(hours=1)
_CLOSE = pd.Timedelta(hours=17)
_SIDES = {1: "BULLISH", -1: "BEARISH", 0: "NONE"}


@dataclass(frozen=True)
class DirectionalState:
    """One market's side at a time, from one source (Requirement 35.1). Prices on the real side; times ns UTC."""
    market: str
    source: str
    version: str
    as_of: int
    side: int
    state: str                                  # ACTIVE, DELIVERED, INVALIDATED or UNDETERMINED
    since: Optional[int] = None
    draw: Optional[dict] = None
    protected: Optional[float] = None
    evidence: tuple = ()                        # (text, ns)
    ignored: tuple = ()                         # the turns against it so far
    invalidation: str = ""
    ended: Optional[tuple] = None               # (reason, ns) of the side that ended last

    @property
    def direction(self) -> str:
        return _SIDES[self.side]

    def to_json(self) -> dict:
        iso = (lambda t: None if t is None else pd.Timestamp(int(t), tz="UTC").isoformat())
        return {"market": self.market, "source": self.source, "version": self.version, "as_of": iso(self.as_of),
                "side": self.direction, "state": self.state, "since": iso(self.since), "draw": self.draw,
                "protected": self.protected, "evidence": [[e, iso(t)] for e, t in self.evidence],
                "ignored": [{"side": _SIDES[x["side"]], "at": iso(x["t"])} for x in self.ignored],
                "invalidation": self.invalidation,
                "ended": None if self.ended is None else [self.ended[0], iso(self.ended[1])]}


@dataclass
class Span:
    """A side from the turn that set it to its end: ``reason`` delivered, invalidated, replaced or open; ``end`` the
    close that ended it (int64 max while open)."""
    turn: dict
    start: int
    end: int
    reason: str
    ignored: list = field(default_factory=list)


# ── the long daily history as reader v0's frames ───────────────────────────

@dataclass
class DailyMarket:
    """Reader v0's frames (``hist["D1"]``, ``hist["W1"]``) from daily bars, buy side up."""
    hist: dict

    def flipped(self) -> "DailyMarket":
        return DailyMarket({tf: seq._flip(b) for tf, b in self.hist.items()})


def daily_market(days: pd.DataFrame) -> DailyMarket:
    """``days`` (date, open, high, low, close) as D1 and W1 candles: a weekend day merged into the Monday after,
    each day open from its date's 00:00 UTC for a day, weeks Monday to Friday (``monday``)."""
    d = days[["date", "open", "high", "low", "close"]].copy()
    d["date"] = pd.to_datetime(d["date"]).dt.tz_localize(None).dt.normalize()
    weekend = d["date"].dt.dayofweek >= 5
    d.loc[weekend, "date"] += pd.to_timedelta(7 - d.loc[weekend, "date"].dt.dayofweek, unit="D")
    g = d.sort_values("date", kind="stable").groupby("date", sort=True)
    d1 = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                       "close": g["close"].last()}).reset_index()
    t = pd.DatetimeIndex(d1["date"]).tz_localize("UTC").as_unit("ns").asi8
    d1 = d1.assign(t_open=t, t_close=t + _DAY.value)
    monday = d1["date"] - pd.to_timedelta(d1["date"].dt.dayofweek, unit="D")
    w = d1.groupby(monday.to_numpy(), sort=True)
    w1 = pd.DataFrame({"open": w["open"].first(), "high": w["high"].max(), "low": w["low"].min(),
                       "close": w["close"].last(), "t_open": w["t_open"].first(), "t_close": w["t_close"].last(),
                       "date": w["date"].last()})
    w1["monday"] = w1.index
    cols = ["open", "high", "low", "close", "t_open", "t_close", "date"]
    return DailyMarket({"D1": d1[cols].reset_index(drop=True), "W1": w1.reset_index(drop=True)})


def _closes(dates) -> np.ndarray:
    """17:00 New York on each trading date, ns UTC: when its D1 candle closes."""
    return np.array([seq._utc(pd.Timestamp(d) + _CLOSE) for d in dates], dtype=np.int64)


def terminal_market(h1: pd.DataFrame, as_of: int) -> DailyMarket:
    """Reader v0's D1 and W1 frames from the terminal's H1 bars (New York days, as ``sequence`` reads them live),
    only the candles closed by ``as_of``: a forming day or week is left out, so no record changes when it closes."""
    frames = seq.candles(h1[seq._ns(h1["time"]) + _HOUR.value <= as_of], _HOUR)
    d1, w1 = frames["D1"], frames["W1"]
    d1 = d1[_closes(d1["date"]) <= as_of].reset_index(drop=True)
    w1 = w1[_closes(pd.to_datetime(w1["monday"]) + 4 * _DAY) <= as_of].reset_index(drop=True)
    return DailyMarket({"D1": d1, "W1": w1})

def reader_turns(m) -> list[dict]:
    """Reader v0's turns, both sides, on the real prices, in time order. Each reads only the candles closed by its
    own W1 close, so one pass over the history gives the turns a pass at every week would."""
    as_of = int(m.hist["D1"]["t_close"].max())
    turns = [seq._signed(t, 1) for t in seq._turns(m, as_of)] + \
            [seq._signed(t, -1) for t in seq._turns(m.flipped(), as_of)]
    return sorted(turns, key=lambda t: (t["t"], t["side"]))


# ── the state machine ──────────────────────────────────────────────────────

def states(turns: list[dict], d1: pd.DataFrame, until: Optional[int] = None) -> list[Span]:
    """The turns in time order through Requirement 35.2: reader v0's ``narrative`` kept as a timeline."""
    until = int(d1["t_close"].max()) if until is None else until
    out: list[Span] = []
    live: Optional[Span] = None
    for t in sorted(turns, key=lambda x: x["t"]):
        if live is not None:
            end = seq._end(live.turn, d1, t["t"])
            if end is None:
                if t["side"] == live.turn["side"]:
                    live.end, live.reason = t["t"], "replaced"
                    live = Span(t, t["t"], np.iinfo(np.int64).max, "open")
                    out.append(live)
                else:
                    live.ignored.append(t)
                continue
            live.reason, live.end = end
        live = Span(t, t["t"], np.iinfo(np.int64).max, "open")
        out.append(live)
    if live is not None and live.reason == "open":
        end = seq._end(live.turn, d1, until)
        if end is not None:
            live.reason, live.end = end
    return out


def _check(m, k: int, side: int) -> list[tuple[str, bool, str]]:
    """Reader v0's tests of a turn on W1 row ``k`` of ``m`` (buy space; ``side`` names the prices), in
    ``_turns``'s order, up to the first it fails: (test, passed, what the candles show)."""
    w, p = seq._WORDS[side], (lambda x: seq._p(side * x))
    w1, d1 = m.hist["W1"], m.hist["D1"]
    c1, c2 = w1.iloc[k - 1], w1.iloc[k]
    week = f"{pd.Timestamp(c1['monday']):%d %b} week's {w['low']} {p(c1['low'])}"
    if not c2["low"] < c1["low"]:
        return [("soup", False, f"didn't trade {w['under']} the {week}")]
    if not c2["close"] > c1["low"]:
        return [("soup", False, f"traded {w['under']} the {week} but closed {w['under']} it ({p(c2['close'])})")]
    out = [("soup", True, f"took the {week} ({w['low']} {p(c2['low'])}) and closed back {w['above']} it "
                          f"({p(c2['close'])})")]
    monday = pd.Timestamp(c2["monday"])
    nth = (monday.day - 1) // 7 + 1
    if nth > seq.W1_C2_WEEKS:
        return out + [("C2 window", False, f"week {nth} of {monday:%B}: the W1 C2 is the month's first "
                                           f"{seq.W1_C2_WEEKS} weeks")]
    out.append(("C2 window", True, f"week {nth} of {monday:%B}"))
    pools = seq._external_lows(d1, int(c2["t_open"]))
    taken = [(n, x) for n, x in pools if c2["low"] < x]
    name = (lambda n: n if side > 0 else n.replace(" low", " high"))
    span = f"the last {seq.QUARTERS} quarters or {seq.MONTHS} months"
    if not pools:
        return out + [("external pool", False, f"no {w['low']} of {span} was left untaken to take")]
    if not taken:
        near = max(pools, key=lambda q: q[1])
        return out + [("external pool", False, f"took none of the untaken {w['low']}s of {span} (nearest: the "
                                               f"{name(near[0])} {p(near[1])})")]
    out.append(("external pool", True, "took " + ", ".join(f"the {name(n)} {p(x)}" for n, x in taken)))
    days = d1[(d1["t_open"] >= c2["t_open"]) & (d1["t_close"] <= c2["t_close"])]
    shift = None if days.empty else seq.cisd(d1, int(days["low"].idxmin()), int(c2["t_close"]))
    if not shift:
        return out + [("D1 CISD", False, f"no run of {w['down']}-closing D1 candles delivered the {w['low']}")]
    if shift["confirm"] < 0:
        return out + [("D1 CISD", False, f"no D1 close {w['above']} {p(shift['level'])} (the run's open) by the "
                                         f"week's close")]
    at = pd.Timestamp(d1["date"].iloc[shift["confirm"]])
    return out + [("D1 CISD", True, f"a close {w['above']} {p(shift['level'])} on {at:%a %d %b}")]


def week_checks(m: DailyMarket, n: int = 4) -> list[dict]:
    """Why each of the last ``n`` closed W1 candles did or didn't turn the narrative, both sides: reader v0's tests
    up to the first each fails. It explains ``_turns``; the turns themselves come only from there."""
    w1 = m.hist["W1"]
    flipped = m.flipped()
    out = []
    for k in range(max(1, len(w1) - n), len(w1)):
        sides = {}
        for side, mm in ((1, m), (-1, flipped)):
            steps = _check(mm, k, side)
            sides[_SIDES[side]] = {"turn": all(ok for _, ok, _ in steps) and len(steps) == 4,
                                   "steps": [list(s) for s in steps]}
        out.append({"week": f"{pd.Timestamp(w1['monday'].iloc[k]):%Y-%m-%d}", **sides})
    return out


def _evidence(turn: dict) -> tuple:
    w = seq._WORDS[turn["side"]]
    pools = ", ".join(f"the {n} {seq._p(x)}" for n, x in turn["erl"])
    return ((f"W1 {w['+']}soup: C1 week {turn['c1']:%d %b %Y}, C2 week {turn['c2']:%d %b %Y} took {pools} "
             f"({w['low']} {seq._p(turn['low'])})", turn["t"]),
            (f"D1 CISD: a close {w['above']} {seq._p(turn['level'])}", turn["cisd_at"]))


def state_at(timeline: list[Span], t: int, market: str = "", source: str = SOURCE,
             version: str = VERSION) -> DirectionalState:
    """The record live at ``t``: the span started by ``t`` and not ended by it, else UNDETERMINED with the last
    end."""
    starts = [s.start for s in timeline]
    k = bisect_right(starts, t) - 1
    if k < 0:
        return DirectionalState(market, source, version, t, 0, "UNDETERMINED")
    s = timeline[k]
    if s.end <= t and s.reason in ("delivered", "invalidated"):
        return DirectionalState(market, source, version, t, 0, "UNDETERMINED", ended=(s.reason, s.end))
    turn, w = s.turn, seq._WORDS[s.turn["side"]]
    return DirectionalState(
        market, source, version, t, turn["side"], "ACTIVE", since=s.start, draw=turn["draw"], protected=turn["low"],
        evidence=_evidence(turn), ignored=tuple(x for x in s.ignored if x["t"] <= t),
        invalidation=f"a D1 candle closes {w['under']} {seq._p(turn['low'])} (a wick is liquidation)",
        ended=None)
