"""The state machine (thesis-engine Requirement 5, design.md "The State Machine").

One machine per market. The thesis is the outer state; the stages live inside it, so its end ends them all. Two pure
steps change the state: ``on_close`` at each execution-frame close (the level frames that closed at the same instant
are already in the book, TE-D2) and ``on_fill`` at each event of the market's own order. Each returns the new state
with what changed and why; nothing else changes a state.

At each close, in order: the thesis (an end, or a newer one going live), the trading day (the day's budget resets,
SPENT returns to THESIS while the thesis has entries left), then the level, the window and the hand.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from thesis_engine.book import Book
from thesis_engine.clock import in_window, stale, trading_day
from thesis_engine.levels import levels
from thesis_engine.records import Hand, Intent, Level, Skip, Thesis, Transition, make_id
from thesis_engine.settings import V1, Settings
from thesis_engine.thesis import end

__all__ = ["STATES", "TABLE", "Ctx", "State", "on_close", "on_fill"]

STATES = ("FLAT", "THESIS", "AT_LEVEL", "ARMED", "IN_TRADE", "SPENT")
#: Every transition the machine may make (Requirement 5.2); "any → FLAT" is the thesis's end.
TABLE = frozenset({
    ("FLAT", "THESIS"), ("THESIS", "AT_LEVEL"), ("AT_LEVEL", "THESIS"), ("AT_LEVEL", "ARMED"),
    ("ARMED", "AT_LEVEL"), ("ARMED", "THESIS"), ("ARMED", "IN_TRADE"),
    ("IN_TRADE", "SPENT"), ("IN_TRADE", "THESIS"), ("IN_TRADE", "AT_LEVEL"), ("SPENT", "THESIS"),
    *((s, "FLAT") for s in STATES if s != "FLAT"),
})


@dataclass(frozen=True)
class State:
    name: str = "FLAT"
    thesis: Optional[Thesis] = None
    level: Optional[Level] = None
    hand: Optional[Hand] = None
    order_id: Optional[str] = None             # the market's open order, whatever the state
    entries_day: int = 0
    entries_thesis: int = 0
    day: Optional[int] = None
    next_thesis: int = 0                       # the next of the market's theses to go live
    d1_seen: int = 0                           # D1 candles closed by the last step


@dataclass
class Ctx:
    """What the steps read: the book, the market's theses in time order, the settings and the typical spread, and
    the execution frame's calendar flags. It holds no state: the levels it caches are a function of the book."""
    market: str
    book: Book
    theses: Sequence[Thesis]
    typical_spread: float
    s: Settings = V1
    window: np.ndarray = field(init=False)
    day: np.ndarray = field(init=False)
    stale: np.ndarray = field(init=False)
    _levels: Dict[tuple, List[Level]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        e = self.book.e
        self.theses = sorted(self.theses, key=lambda x: (x.since, x.id))
        self.window = in_window(e.t, self.s) if len(e) else np.zeros(0, bool)
        self.day = trading_day(e.t, self.market, self.s) if len(e) else np.zeros(0, np.int64)
        self.stale = stale(e, self.market, self.s)

    def levels(self, th: Thesis, t: int, price: float) -> List[Level]:
        frames = self.book.frames
        key = (th.id, *(frames[tf].n(t) for tf in (*self.s.level_frames, "D1", "W1")))
        if key not in self._levels:
            self._levels = {key: levels(th, self.book, t, price, self.s)}      # one thesis at a time
        found = self._levels[key]
        return sorted(found, key=lambda x: (-x.score, min(abs(price - x.low), abs(price - x.high)), x.array_id))


def _p(x: float) -> str:
    return f"{x:.6g}"


class _Out:
    """What one step records."""

    def __init__(self, ctx: Ctx, t: int) -> None:
        self.ctx, self.t = ctx, t
        self.transitions: List[Transition] = []
        self.intents: List[Intent] = []
        self.skips: List[Skip] = []
        self.notes: List[dict] = []

    def move(self, st: State, to: str, reason: str, frame: str, **changes) -> State:
        if (st.name, to) not in TABLE:
            raise AssertionError(f"not a transition of the table: {st.name} -> {to}")
        new = replace(st, name=to, **changes)
        th = new.thesis or st.thesis
        lv = new.level or st.level
        self.transitions.append(Transition(self.ctx.market, self.t, st.name, to, reason, frame,
                                           th.id if th else None, lv.array_id if lv else None,
                                           None, new.order_id))
        return new

    def note(self, kind: str, **fields) -> None:
        self.notes.append({"note": kind, "market": self.ctx.market, "t": self.t, **fields})


def on_close(st: State, ctx: Ctx, m: int) -> Tuple[State, _Out]:
    """The step at the close of execution-frame candle ``m``."""
    book, s = ctx.book, ctx.s
    e = book.e
    t = int(e.end[m])
    out = _Out(ctx, t)
    d1_now = book.frames["D1"].n(t)

    if st.thesis is not None:                                                    # 1. the thesis
        ended = end(st.thesis, book, m, t, st.d1_seen, d1_now)
        if ended is not None:
            kind, why = ended
            st = out.move(st, "FLAT", f"{kind.lower()}: {why}", "D1" if kind == "INVALIDATED" else s.e_frame,
                          thesis=None, level=None, hand=None, entries_thesis=0)
            out.note("thesis_end", end=kind, why=why)
    while st.next_thesis < len(ctx.theses) and ctx.theses[st.next_thesis].since <= t:
        th = ctx.theses[st.next_thesis]
        st = replace(st, next_thesis=st.next_thesis + 1)
        if th.until <= t:
            out.note("thesis_missed", thesis_id=th.id)
            continue
        if st.thesis is not None:
            st = out.move(st, "FLAT", "replaced: a newer thesis went live", "W1",
                          thesis=None, level=None, hand=None, entries_thesis=0)
            out.note("thesis_end", end="REPLACED", why="a newer thesis went live")
        st = out.move(st, "THESIS", f"{th.source}, {th.side.lower()}: draw {_p(th.draw)}, protected {_p(th.protected)}"
                      + (f" ({th.note})" if th.note else ""), "W1", thesis=th, level=None, hand=None,
                      entries_thesis=0)

    day = int(ctx.day[m])                                                        # 2. the trading day
    if st.day != day:
        st = replace(st, day=day, entries_day=0)
        if st.name == "SPENT" and st.thesis is not None and st.entries_thesis < s.per_thesis:
            st = out.move(st, "THESIS", f"a new day: {s.per_thesis - st.entries_thesis} of {s.per_thesis} entries left",
                          s.e_frame)

    if st.name in ("THESIS", "AT_LEVEL", "ARMED") and st.order_id is None:      # 3. level, window, hand
        st = _stage(st, ctx, m, out)
    return replace(st, d1_seen=d1_now), out


def _stage(st: State, ctx: Ctx, m: int, out: _Out) -> State:
    book, s, th = ctx.book, ctx.s, st.thesis
    e = book.e
    t, price, bull = int(e.end[m]), float(e.c[m]), th.bullish

    if st.name in ("AT_LEVEL", "ARMED"):
        lv = st.level
        frame = book.frames[lv.tf]
        n = frame.n(t)
        if lv.end < n:
            k = lv.end
            st = out.move(st, "THESIS", f"a {lv.tf} close {_p(frame.c.c[k])} through the level's far edge "
                          f"{_p(lv.low if bull else lv.high)}", lv.tf, level=None, hand=None)
        else:
            reach = frame.average_range(n)
            away = price > lv.high + reach if bull else price < lv.low - reach
            if np.isfinite(reach) and away:
                st = out.move(st, "THESIS", f"price {_p(price)} left the level by more than one {lv.tf} average range",
                              s.e_frame, level=None, hand=None)

    if st.name == "THESIS":
        hit = [lv for lv in ctx.levels(th, t, price) if e.l[m] <= lv.high and e.h[m] >= lv.low]
        if hit:
            st = out.move(st, "AT_LEVEL", f"at {hit[0].describe()}", s.e_frame, level=hit[0])

    if st.name == "AT_LEVEL" and ctx.window[m] and not ctx.stale[m]:
        opened = m == 0 or not ctx.window[m - 1]
        st = out.move(st, "ARMED", "the window opened" if opened else "at the level inside the window", s.e_frame)

    if st.name != "ARMED":
        return st
    hand = st.hand
    if hand is None:
        if not ctx.window[m] or ctx.stale[m]:
            return out.move(st, "AT_LEVEL", "the window closed without a hand" if not ctx.window[m]
                            else "the data went stale", s.e_frame)
        return replace(st, hand=_sweep(st, ctx, m, out))
    extreme = min(hand.extreme, float(e.l[m])) if bull else max(hand.extreme, float(e.h[m]))
    hand = replace(hand, extreme=extreme)
    run = book.cisd(m, bull, hand.swept)
    if run is not None and m - hand.swept <= s.hand_candles:
        return _order(st, ctx, m, hand, run, out)
    if m - hand.swept >= s.hand_candles:
        out.note("hand_failed", why=f"no CISD within {s.hand_candles} {s.e_frame} candles of the sweep",
                 pool=hand.pool)
        st = replace(st, hand=None)
        if not ctx.window[m]:
            return out.move(st, "AT_LEVEL", "the window closed without a hand", s.e_frame)
        return st
    return replace(st, hand=hand)


def _sweep(st: State, ctx: Ctx, m: int, out: _Out) -> Optional[Hand]:
    """A pool at the level that E candle m traded beyond (Requirement 8.1), as the start of a hand."""
    book, s, lv, bull = ctx.book, ctx.s, st.level, st.thesis.bullish
    e = book.e
    band = s.pool_band_adr * book.adr(int(e.end[m]))
    lo, hi = (lv.low - band, lv.high) if bull else (lv.low, lv.high + band)
    pools = [(f"the {s.e_frame} swing {'low' if bull else 'high'} {_p(p)}", p) for _, p in book.e_pools_taken(m, bull)]
    h1 = book.h1_pool_taken(m, bull)
    if h1 is not None:
        pools.append((f"the previous H1 {'low' if bull else 'high'} {_p(h1)}", h1))
    pools = [(name, p) for name, p in pools if lo <= p <= hi]
    if not pools:
        return None
    name, price = min(pools, key=lambda x: x[1]) if bull else max(pools, key=lambda x: x[1])
    out.note("sweep", pool=name, price=price, level_id=lv.array_id)
    return Hand(name, float(price), m, float(e.l[m] if bull else e.h[m]))


def _order(st: State, ctx: Ctx, m: int, hand: Hand, run: Tuple[int, int], out: _Out) -> State:
    """The hand completed (Requirement 8.4): an order, or a skip with its reason (Requirement 9)."""
    book, s, th = ctx.book, ctx.s, st.thesis
    e = book.e
    t, spread, bull = int(e.end[m]), ctx.typical_spread, th.bullish
    close = float(e.c[m])
    entry = close + spread if bull else close                       # a buy pays the ask; a sell takes the bid
    stop = hand.extreme if bull else hand.extreme + spread          # a short's stop triggers on the ask
    risk = entry - stop if bull else stop - entry
    reward = th.draw - entry if bull else entry - th.draw
    intent = Intent(ctx.market, th.id, st.level.array_id, th.side, "MARKET", entry, stop, th.draw, t)
    why = (f"{s.e_frame} took {hand.pool}, then closed {_p(close)} {'above' if bull else 'below'} the run's open "
           f"{_p(float(e.o[run[0]]))} (CISD)")
    skip = None
    if risk <= 0 or risk < s.min_stop_spreads * spread:
        skip = ("STOP_TOO_SMALL", f"risk {_p(risk)} is " + (f"{risk / spread:.1f} spreads" if spread else "no spread")
                + f", under {s.min_stop_spreads:g}")
    elif reward < s.min_rr * risk:
        skip = ("TARGET_TOO_CLOSE", f"the draw is {reward / risk:.2f}R away, under {s.min_rr:g}R")
    elif st.entries_day >= s.per_day or st.entries_thesis >= s.per_thesis:
        skip = ("BUDGET", f"{st.entries_day} today, {st.entries_thesis} on the thesis")
    if skip is not None:
        out.skips.append(Skip(intent, *skip))
        out.note("skip", reason=skip[0], detail=skip[1], hand=why)
        return replace(st, hand=None)
    order_id = make_id(ctx.market, t, th.id, "order")
    out.intents.append(intent)
    return out.move(st, "IN_TRADE", f"{why}: {'buy' if bull else 'sell'} at market, stop {_p(stop)}, "
                    f"target {_p(th.draw)} ({reward / risk:.1f}R)", s.e_frame, hand=None, order_id=order_id)


def on_fill(st: State, ctx: Ctx, kind: str, t: int, price: Optional[float], r: Optional[float] = None
            ) -> Tuple[State, _Out]:
    """The step at an event of the market's open order: FILLED, REJECTED, or its close (SL, TP, TIME, END)."""
    s = ctx.s
    out = _Out(ctx, t)
    if kind == "FILLED":
        return replace(st, entries_day=st.entries_day + 1, entries_thesis=st.entries_thesis + 1), out
    st = replace(st, order_id=None)
    if st.name != "IN_TRADE":
        return st, out                                                # the thesis ended while the order was open
    if kind == "REJECTED":
        return out.move(st, "AT_LEVEL", "rejected: the open was beyond the stop or the target", s.e_frame), out
    what = {"SL": "stopped", "TP": "the draw traded", "TIME": "time: closed", "END": "the data ended"}.get(kind, kind)
    reason = f"{what} at {_p(price)}" + (f" ({r:+.2f}R)" if r is not None else "")
    spent = st.entries_day >= s.per_day or st.entries_thesis >= s.per_thesis
    return out.move(st, "SPENT" if spent else "THESIS", reason, s.e_frame), out
