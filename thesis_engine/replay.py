"""The replay (thesis-engine Requirements 10, 11): the machine over a market's M1 bars, through the shared fill model.

The loop is the design's: for each execution-frame close, the market's open order first meets the M1 bars before it
(``agent.brokers.fill_model.FillModel``, the paper broker's and the backtester's), then the machine steps at the
close. An order placed at a close acts from the next bar. Each bar's spread is the recorded one or the window's
median, whichever is larger (H-N's rule); stops slip by the instrument's ``stop_slippage``; the Exness Standard
swap-free account charges no commission and no swap.

A position still open when its thesis's ``until`` comes is closed at the close of the last bar before it (TIME), so
nothing is carried through a weekend; one still open when the bars end is closed at the last bar (END).

The journal is JSON lines with sorted keys: the same bars and theses give the same bytes (Property 2).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from agent.brokers.fill_model import Bar, FillModel, SimOrder
from liquidity_engine.context.frame_state import Candles
from thesis_engine import VERSION
from thesis_engine.book import Book
from thesis_engine.clock import clean, frames, limit_expiry
from thesis_engine.machine import Ctx, State, on_close, on_fill
from thesis_engine.records import Thesis, to_json
from thesis_engine.settings import V1, Settings

__all__ = ["Market", "Journal", "prepare", "run"]


@dataclass
class Market:
    """One market's bars, frames and book, built once and shared by every run on them."""
    name: str
    t: np.ndarray                    # M1 bar opens, UTC ns
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    spread: np.ndarray               # the spread each bar pays
    typical_spread: float
    frames: Dict[str, Candles]
    book: Book
    dropped: Dict[str, int]


def prepare(name: str, m1: pd.DataFrame, s: Settings = V1) -> Market:
    bars, dropped = clean(m1)
    typical = float(bars["spread"].median())
    fr = frames(bars, name, s)
    return Market(name, bars["time"].to_numpy("datetime64[ns]").astype(np.int64),
                  *(bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close")),
                  np.maximum(bars["spread"].to_numpy(dtype=float), typical), typical, fr, Book(name, fr, s), dropped)


@dataclass
class Journal:
    market: str
    records: List[dict] = field(default_factory=list)

    def add(self, kind: str, rec: dict) -> None:
        self.records.append({**rec, "record": kind})

    def of(self, kind: str) -> List[dict]:
        return [r for r in self.records if r["record"] == kind]

    def lines(self) -> List[str]:
        return [json.dumps(r, sort_keys=True, default=float) for r in self.records]

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines()) + "\n", encoding="utf-8")
        return path


def _dt(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)


def _ns(dt: datetime) -> int:
    return int(round(dt.timestamp() * 1e9))


def _r(order: SimOrder, spread_at_entry: float, stop: float) -> tuple[float, float, float]:
    """Net R on the prices paid, gross R on bid prices, and the risk (Requirement 11.2, H-N's measures). ``stop`` is
    the planned one: a partial moves the order's own to the fill, and its share exits at the partial's price."""
    long_ = order.direction == "LONG"
    risk = order.fill - stop if long_ else stop - order.fill
    moved = (order.exit - order.fill) if long_ else (order.fill - order.exit)
    ideal = (order.ideal_exit - order.ideal_fill) if long_ else (order.ideal_fill - order.ideal_exit)
    f = order.partial_fraction if order.partial_at is not None else 0.0
    if f:
        part = (order.partial_price - order.fill) if long_ else (order.fill - order.partial_price)
        ideal_part = ((order.partial_ideal_exit - order.ideal_fill) if long_
                      else (order.ideal_fill - order.partial_ideal_exit))
        moved, ideal = (1 - f) * moved + f * part, (1 - f) * ideal + f * ideal_part
    stop_bid = stop if long_ else stop - spread_at_entry
    ideal_risk = order.ideal_fill - stop_bid if long_ else stop_bid - order.ideal_fill
    return float(moved / risk), float(ideal / ideal_risk), float(risk)


def _close_at(order: SimOrder, bar: Bar, reason: str) -> None:
    """Close an open position at ``bar``'s close: the bid for a long, the ask for a short."""
    long_ = order.direction == "LONG"
    order.status, order.closed_at, order.exit_reason = "CLOSED", bar.timestamp, reason
    order.ideal_exit = bar.close
    order.exit = bar.close if long_ else bar.close + bar.spread


def _limit_expiry(at: int, until: int, s: Settings) -> int:
    """V2's limit expiry (Requirement 15.4): ``clock.limit_expiry``."""
    return limit_expiry(at, until, s)


def day_end(t: int, hour: int) -> int:
    """The end of the trading day holding ``t`` (ns): the next ``hour``:00 New York after it."""
    local = pd.Timestamp(t, tz="UTC").tz_convert("America/New_York")
    day = local.date()
    end = pd.Timestamp(day.year, day.month, day.day, hour).tz_localize("America/New_York")
    if end <= local:
        day += timedelta(days=1)
        end = pd.Timestamp(day.year, day.month, day.day, hour).tz_localize("America/New_York")
    return int(end.tz_convert("UTC").value)


def check_time(filled: int, market: str, s: Settings) -> Optional[int]:
    """When a position filled at ``filled`` meets its check (Requirement 23.4); None without one."""
    if s.check_at == "DAY_END":
        return day_end(filled, s.day_open_hour(market))
    if s.check_at == "HOURS":
        return filled + int(round(s.check_hours * 3600 * 1e9))
    if s.check_at:
        raise ValueError(f"unknown check {s.check_at!r}")
    return None


def _has_been(order: SimOrder, stop: float, r: float) -> bool:
    """Whether the position's best closing-side price since its fill has been ``r`` times the planned risk beyond
    the fill (``r`` 0: never, so the check always closes)."""
    if r <= 0:
        return False
    long_ = order.direction == "LONG"
    risk = order.fill - stop if long_ else stop - order.fill
    best = (order.mfe_price - order.fill) if long_ else (order.fill - order.mfe_price)
    return risk > 0 and best >= r * risk


def _journal_step(j: Journal, out) -> None:
    for tr in out.transitions:
        j.add("transition", to_json(tr))
    for sk in out.skips:
        j.add("skip", {"t": sk.intent.at, "reason": sk.reason, "detail": sk.detail, "intent": to_json(sk.intent)})
    for note in out.notes:
        j.add("note", note)


def run(mk: Market, theses: Sequence[Thesis], s: Settings = V1, slippage: float = 0.0,
        until: Optional[int] = None, partial: Optional[Tuple[float, float]] = None) -> Journal:
    """The machine over ``mk``'s bars with ``theses``. ``until`` cuts the run (ns): nothing after it is read.
    ``partial`` (R, fraction) takes that share of every position off at that many R and moves the rest's stop to the
    fill: the companion H-AH reports. With it None, the settings' own (``partial_r``, Requirement 23.2) apply."""
    if partial is None and s.partial_r > 0:
        partial = (s.partial_r, s.partial_fraction)
    j = Journal(mk.name)
    j.add("run", {"version": VERSION, "settings": s.version, "market": mk.name, "theses": len(theses),
                  "typical_spread": mk.typical_spread, "dropped": mk.dropped})
    for th in sorted(theses, key=lambda x: x.since):
        j.add("thesis", {**to_json(th), "id": th.id})
    ctx = Ctx(mk.name, mk.book, theses, mk.typical_spread, s)
    e = mk.book.e
    fm = FillModel(slippage)
    st = State()
    order: Optional[SimOrder] = None
    order_until, order_spread, order_stop = 0, 0.0, 0.0
    order_check: Optional[int] = None              # Requirement 23.4: set at the fill, None once passed
    thesis_until = {th.id: th.until for th in theses}
    bi = 0
    prev: Optional[Bar] = None                     # the last bar the open order met
    n_e = len(e) if until is None else int(np.searchsorted(e.end, until, "right"))
    last_bar = len(mk.t) if until is None else int(np.searchsorted(mk.t, until, "left"))

    def bar(i: int) -> Bar:
        return Bar(_dt(int(mk.t[i])), float(mk.o[i]), float(mk.h[i]), float(mk.l[i]), float(mk.c[i]),
                   float(mk.spread[i]))

    def finish(i_bar: Bar) -> None:
        nonlocal st, order
        net, gross, risk = _r(order, order_spread, order_stop)
        rec = {"order_id": order.order_id, "thesis_id": order.setup_id, "direction": order.direction,
               "placed_at": _ns(order.placed_at), "filled_at": _ns(order.filled_at) if order.filled_at else None,
               "closed_at": _ns(order.closed_at), "fill": order.fill, "stop": order_stop, "target": order.target,
               "exit": order.exit, "reason": order.exit_reason, "ideal_fill": order.ideal_fill,
               "ideal_exit": order.ideal_exit, "mae": order.mae_price, "mfe": order.mfe_price, "net_r": net,
               "gross_r": gross, "risk": risk,
               "risk_spreads": risk / mk.typical_spread if mk.typical_spread else float("inf")}
        if partial is not None:
            taken = order.partial_at is not None
            rec.update({"partial_at": _ns(order.partial_at) if taken else None,
                        "partial_price": order.partial_price if taken else None})
        j.add("trade", rec)
        st, out = on_fill(st, ctx, order.exit_reason, _ns(order.closed_at), order.exit, net)
        _journal_step(j, out)
        order = None

    def walk(to: int) -> None:
        """The open order through bars [bi, to)."""
        nonlocal st, order, bi, prev, order_check
        for i in range(bi, to):
            if order is None:
                break
            b = bar(i)
            if order.status == "OPEN" and mk.t[i] >= order_until and prev is not None:
                _close_at(order, prev, "TIME")
                finish(prev)
                break
            if order.status == "OPEN" and order_check is not None and mk.t[i] >= order_check and prev is not None:
                if not _has_been(order, order_stop, s.check_r):
                    _close_at(order, prev, "CHECK")
                    finish(prev)
                    break
                order_check = None
            for ev in fm.step(order, b):
                j.add("fill", {"order_id": ev.order_id, "event": ev.kind, "t": _ns(ev.at), "price": ev.price})
                if ev.kind == "FILLED":
                    order_check = check_time(_ns(ev.at), mk.name, s)
                if ev.kind in ("FILLED", "REJECTED", "EXPIRED"):
                    st, out = on_fill(st, ctx, ev.kind, _ns(ev.at), ev.price)
                    _journal_step(j, out)
            if order.status == "CLOSED":
                if order.exit_reason in ("INVALID_STOPS", "EXPIRED"):
                    order = None
                else:
                    finish(b)
                break
            if order.status == "OPEN" and mk.t[i] + 60_000_000_000 >= order_until:
                _close_at(order, b, "TIME")
                finish(b)
                break
            prev = b
        bi = to

    for m in range(n_e):
        t = int(e.end[m])
        k = int(np.searchsorted(mk.t, t, "left"))
        if order is not None:
            walk(min(k, last_bar))
        bi = max(bi, k)
        st, out = on_close(st, ctx, m)
        _journal_step(j, out)
        if order is not None and order.status == "PENDING" and (st.thesis is None or st.thesis.id != order.setup_id):
            j.add("fill", {"order_id": order.order_id, "event": "CANCELLED", "t": t, "price": None})
            st, out = on_fill(st, ctx, "CANCELLED", t, None)            # its thesis ended before it filled
            _journal_step(j, out)
            order = None
        for intent in out.intents:
            order_until, order_spread, order_stop = thesis_until[intent.thesis_id], mk.typical_spread, intent.stop
            order_check = None
            order = SimOrder(st.order_id, intent.thesis_id, mk.name, "LONG" if intent.side == "BULLISH" else "SHORT",
                             intent.kind, intent.entry, intent.stop, intent.target, _dt(t),
                             expires_at=_dt(_limit_expiry(t, order_until, s)) if intent.kind == "LIMIT" else None,
                             **({"partial_r": partial[0], "partial_fraction": partial[1]} if partial else {}))
            j.add("intent", {**to_json(intent), "order_id": st.order_id})
    if order is not None:
        walk(last_bar)
    if order is not None and order.status == "OPEN" and last_bar > 0:
        b = bar(last_bar - 1)
        _close_at(order, b, "END")
        finish(b)
    j.add("end", {"state": st.name})
    return j
