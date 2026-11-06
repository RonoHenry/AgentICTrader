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

from liquidity_engine.context.measures import average_range
from thesis_engine.book import Book
from thesis_engine.clock import in_window, limit_expiry, stale, trading_day
from thesis_engine.levels import levels, rank
from thesis_engine.records import Hand, Intent, Level, Skip, Thesis, Transition, make_id, to_json
from thesis_engine.settings import MINUTES, V1, Settings
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
        return sorted(found, key=lambda x: rank(x, price, self.s))


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

    def note(self, what: str, /, **fields) -> None:
        self.notes.append({**fields, "note": what, "market": self.ctx.market, "t": self.t})


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
            out.note("level", **to_json(hit[0]))                     # its geometry, for the chart

    if st.name == "AT_LEVEL" and ctx.window[m] and not ctx.stale[m]:
        opened = m == 0 or not ctx.window[m - 1]
        st = out.move(st, "ARMED", "the window opened" if opened else "at the level inside the window", s.e_frame)

    if st.name != "ARMED":
        return st
    if s.exec_child == "POOL":                                       # V3: the hand on its pool's child frame
        return _hand_on_child(st, ctx, m, out)
    hand = st.hand
    if hand is None:
        if not ctx.window[m] or ctx.stale[m]:
            return out.move(st, "AT_LEVEL", "the window closed without a hand" if not ctx.window[m]
                            else "the data went stale", s.e_frame)
        return replace(st, hand=_sweep(st, ctx, m, out))
    extreme = min(hand.extreme, float(e.l[m])) if bull else max(hand.extreme, float(e.h[m]))
    hand = replace(hand, extreme=extreme)
    run = book.cisd(m, bull, hand.swept)
    if run is not None and s.displacement_body > 0:              # V2: the close through must displace
        reach = average_range(e.h, e.l, m, 20)
        if not abs(float(e.c[m]) - float(e.o[m])) >= s.displacement_body * reach:
            out.note("no_displacement", pool=hand.pool, body=abs(float(e.c[m]) - float(e.o[m])), reach=reach)
            run = None
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
    if s.hand_pools == "TRADER":                                     # V2: the trader's liquidity
        pools = book.trader_pools_taken(m, bull)
    else:
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


def _hand_on_child(st: State, ctx: Ctx, m: int, out: _Out) -> State:
    """V3 (Requirement 17): the hand waits on its pool's child frame and reads each child candle at its close; a
    sweep of a larger frame's pool takes a waiting hand over, the extreme carried."""
    book, s, bull = ctx.book, ctx.s, st.thesis.bullish
    e = book.e
    hand = st.hand
    if hand is not None and hand.rframe:                            # V4: a setup waits for its refined entry
        return _refine(st, ctx, m, out)
    if hand is None and (not ctx.window[m] or ctx.stale[m]):
        return out.move(st, "AT_LEVEL", "the window closed without a hand" if not ctx.window[m]
                        else "the data went stale", s.e_frame)
    if hand is None or (ctx.window[m] and not ctx.stale[m]):
        taken = _pool_swept(st, ctx, m, out, hand)
        if taken is not None:
            hand = taken
    if hand is None:
        return st
    hand = replace(hand, extreme=min(hand.extreme, float(e.l[m])) if bull else max(hand.extreme, float(e.h[m])))
    x = book.x[hand.frame]
    for k in range(hand.seen + 1, book.x_closed(hand.frame, int(e.end[m]))):
        hand = replace(hand, seen=k)
        run = book.x_cisd(hand.frame, k, bull, hand.k0)
        if run is not None and s.displacement_body > 0:
            reach, body = book.x_reach(hand.frame, k), abs(float(x.c[k]) - float(x.o[k]))
            if not body >= s.displacement_body * reach:
                out.note("no_displacement", pool=hand.pool, frame=hand.frame, body=body, reach=reach)
                run = None
        if run is not None and k - hand.k0 <= s.hand_candles:
            if s.entry == "REFINED":                                # V4: the setup; the entry comes lower down
                return _setup(st, ctx, m, hand, k, run, out)
            return _order(st, ctx, k, hand, run, out, x=x, tf=hand.frame, t=int(e.end[m]))
        if k - hand.k0 >= s.hand_candles:
            out.note("hand_failed", why=f"no CISD within {s.hand_candles} {hand.frame} candles of the sweep",
                     pool=hand.pool, frame=hand.frame)
            st = replace(st, hand=None)
            if not ctx.window[m]:
                return out.move(st, "AT_LEVEL", "the window closed without a hand", s.e_frame)
            return st
    return replace(st, hand=hand)


def _setup(st: State, ctx: Ctx, m: int, hand: Hand, k: int, run: Tuple[int, int], out: _Out) -> State:
    """V4 (Requirement 19.4): the setup frame's CISD confirms the setup and places no order. Its order block is the
    CISD run's bodies; the machine now waits for price to come back into it, until the window's end or an hour on."""
    book, s = ctx.book, ctx.s
    x = book.x[hand.frame]
    first, last = run
    lo = float(np.minimum(x.o[first:last + 1], x.c[first:last + 1]).min())
    hi = float(np.maximum(x.o[first:last + 1], x.c[first:last + 1]).max())
    t = int(book.e.end[m])
    until = limit_expiry(t, st.thesis.until, s)
    rframe = dict(s.refine)[hand.frame]
    out.note("setup", pool=hand.pool, pool_tf=hand.pool_tf, frame=hand.frame, k=k, zone_low=lo, zone_high=hi,
             extreme=hand.extreme, until=until, refine=rframe)
    return replace(st, hand=replace(hand, rframe=rframe, zone_lo=lo, zone_hi=hi, until=until))


def _refine(st: State, ctx: Ctx, m: int, out: _Out) -> State:
    """V4 (Requirements 19.5, 19.6): the setup waits for price to trade back into its order block, then enters on the
    refining frame's first CISD back the thesis's way, from the run into the pull-back. It fails if price trades
    beyond the sweep's extreme first, and expires when its time runs out."""
    book, s, bull = ctx.book, ctx.s, st.thesis.bullish
    e = book.e
    hand, t = st.hand, int(e.end[m])
    beyond = e.l[m] < hand.extreme if bull else e.h[m] > hand.extreme
    if beyond or t >= hand.until:
        if beyond:
            out.note("setup_failed", pool=hand.pool, frame=hand.frame,
                     why=f"price traded beyond the sweep's extreme {_p(hand.extreme)}")
        else:
            out.note("setup_expired", pool=hand.pool, frame=hand.frame, touched=hand.touched >= 0)
        st = replace(st, hand=None)
        if not ctx.window[m] or ctx.stale[m]:
            return out.move(st, "AT_LEVEL", "the setup ended without its entry; the window closed" if not ctx.window[m]
                            else "the setup ended without its entry; the data went stale", s.e_frame)
        return replace(st, hand=_pool_swept(st, ctx, m, out, None) if beyond else None)
    if hand.touched < 0:
        inside = e.l[m] <= hand.zone_hi if bull else e.h[m] >= hand.zone_lo
        if not inside:
            return st
        k = book.x_at(hand.rframe, m)
        hand = replace(hand, touched=k, rseen=k - 1)
        out.note("pullback", pool=hand.pool, frame=hand.frame, refine=hand.rframe, price=float(e.c[m]))
    rx = book.x[hand.rframe]
    for k in range(hand.rseen + 1, book.x_closed(hand.rframe, t)):
        hand = replace(hand, rseen=k)
        run = book.x_cisd(hand.rframe, k, bull, hand.touched)
        if run is not None:
            return _order(replace(st, hand=hand), ctx, k, hand, run, out, x=rx, tf=hand.rframe, t=t)
    return replace(st, hand=hand)


def _pool_swept(st: State, ctx: Ctx, m: int, out: _Out, hand: Optional[Hand]) -> Optional[Hand]:
    """V3: the pools at the level that E candle m takes (Requirement 17.3). The largest frame's, then the deepest,
    starts a hand on its child frame, or takes over a waiting hand of a smaller frame's pool."""
    book, s, lv, bull = ctx.book, ctx.s, st.level, st.thesis.bullish
    e = book.e
    band = s.pool_band_adr * book.adr(int(e.end[m]))
    lo, hi = (lv.low - band, lv.high) if bull else (lv.low, lv.high + band)
    pools = [(name, p, tf) for name, p, tf in book.pools_taken(m, bull) if lo <= p <= hi]
    if hand is not None:
        pools = [x for x in pools if MINUTES[x[2]] > MINUTES[hand.pool_tf]]
    if not pools:
        return None
    big = max(MINUTES[tf] for _, _, tf in pools)
    pools = [x for x in pools if MINUTES[x[2]] == big]
    name, price, tf = min(pools, key=lambda x: x[1]) if bull else max(pools, key=lambda x: x[1])
    frame = s.child(tf)
    k0 = book.x_at(frame, m)
    bar = float(e.l[m] if bull else e.h[m])
    extreme = bar if hand is None else (min(hand.extreme, bar) if bull else max(hand.extreme, bar))
    out.note("sweep", pool=name, price=price, level_id=lv.array_id, pool_tf=tf, frame=frame,
             took_over=hand.pool if hand is not None else None)
    return Hand(name, float(price), m, extreme, frame=frame, pool_tf=tf, k0=k0, seen=k0 - 1)


def _order(st: State, ctx: Ctx, m: int, hand: Hand, run: Tuple[int, int], out: _Out, x=None, tf: str = "",
           t: Optional[int] = None) -> State:
    """The hand completed (Requirement 8.4): an order, or a skip with its reason (Requirement 9). V3 passes the child
    frame's candles ``x`` (m indexes them) and the step's time."""
    book, s, th = ctx.book, ctx.s, st.thesis
    e = book.e if x is None else x
    tf = tf or s.e_frame
    t = int(e.end[m]) if t is None else t
    spread, bull = ctx.typical_spread, th.bullish
    close = float(e.c[m])
    limit = s.entry == "LIMIT_MT"
    away = None
    if s.entry == "NEAR_MT":                                        # V3: at market near the MT, else a limit at it
        mt, reach = book.x_run_mt(tf, *run), book.x_reach(tf, m)
        away = abs(close - mt) / reach if reach > 0 else float("inf")
        limit = not away <= s.near_mt
        entry = mt if limit else (close + spread if bull else close)
    elif limit:                                                     # V2: a limit at the run's mean threshold
        entry = book.run_mt(*run)
    else:
        entry = close + spread if bull else close                   # a buy pays the ask; a sell takes the bid
    stop = hand.extreme if bull else hand.extreme + spread          # a short's stop triggers on the ask
    risk = entry - stop if bull else stop - entry
    reward = th.draw - entry if bull else entry - th.draw
    intent = Intent(ctx.market, th.id, st.level.array_id, th.side, "LIMIT" if limit else "MARKET", entry, stop,
                    th.draw, t)
    if hand.rframe:                                                 # V4: the setup above, the entry refined below
        why = (f"{hand.frame} took {hand.pool} (the setup); price came back into its order block "
               f"{_p(hand.zone_lo)}-{_p(hand.zone_hi)} and {tf} closed {_p(close)} {'above' if bull else 'below'} "
               f"the open of the run into it {_p(float(e.o[run[0]]))} (CISD)")
    else:
        why = (f"{tf} took {hand.pool}, then closed {_p(close)} {'above' if bull else 'below'} the run's open "
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
    how = f"limit at the run's MT {_p(entry)}" if limit else "at market"
    if away is not None:                                            # V3: how far the close ran from the MT
        how += f" ({away:.1f} {tf} average ranges from the run's MT)"
        out.note("hand", pool=hand.pool, pool_tf=hand.pool_tf, frame=tf, k=m, k0=hand.k0,
                 kind="LIMIT" if limit else "MARKET", away=away, order_id=order_id)
    elif hand.rframe:                                               # V4: the setup's frame and the refining one
        out.note("hand", pool=hand.pool, pool_tf=hand.pool_tf, frame=hand.frame, refine=tf, k=m, k0=hand.k0,
                 kind="MARKET", away=None, zone_low=hand.zone_lo, zone_high=hand.zone_hi, order_id=order_id)
    return out.move(st, "IN_TRADE", f"{why}: {'buy' if bull else 'sell'} {how}, stop {_p(stop)}, "
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
    if kind in ("REJECTED", "EXPIRED"):
        return out.move(st, "AT_LEVEL", "rejected: the open was beyond the stop or the target" if kind == "REJECTED"
                        else "the limit expired unfilled", s.e_frame), out
    what = {"SL": "stopped", "TP": "the draw traded", "TIME": "time: closed", "END": "the data ended"}.get(kind, kind)
    reason = f"{what} at {_p(price)}" + (f" ({r:+.2f}R)" if r is not None else "")
    spent = st.entries_day >= s.per_day or st.entries_thesis >= s.per_thesis
    return out.move(st, "SPENT" if spent else "THESIS", reason, s.e_frame), out
