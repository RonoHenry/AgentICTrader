"""The indicator's liquidity suite (algo-backtester Requirement 21.2), in its order on each candle:
1. the sessions (Asia, London, New York): a box, and a high and a low that run on until price touches them;
2. the true day open (TDO), from New York midnight;
3. the previous day's, week's and month's high and low, purged when price trades through them;
4. BSL and SSL: the swing highs and lows of up to three higher timeframes, the newest few per side;
5. relevant swings (off by default): chart pivots within the last few HTF candles;
6. the purged registry, which keeps the last purged levels grey with a ✕;
7. reconciliation (off by default): of levels closer than ATR x a multiple, only one is shown.

Ported from the Pine ``f_lq_*``, ``f_prev_level``, ``f_bsl_ssl_v2`` and ``f_rc_*`` functions. A Pine line's
right edge that moves with every candle is ``live`` here, and is drawn to the clock's candle.
"""
from __future__ import annotations

import copy
import math
from typing import Optional

import numpy as np

from algo_research.fractal_poi.chart import Chart, Now, box, hexa, label, line
from algo_research.fractal_poi.frames import bsl_auto, in_seconds, starts
from algo_research.fractal_poi.settings import FractalSettings

__all__ = ["Liquidity"]

NA = float("nan")
PURGED = hexa("787b86")                       # color.gray
TDO = hexa("4c9f51")
COLORS = {"PD": hexa("2962ff"), "PW": hexa("9c27b0"), "PM": hexa("880e4f"), 1: hexa("2962ff"), 2: hexa("089981"),
          3: hexa("1a237e")}
SWING = hexa("787b86")
_ORPHANS = 60                                 # swing lines Pine leaves behind once crossed (its own cap is 500)


class _Obj:
    """A line or label the suite keeps between candles."""
    __slots__ = ("x1", "y1", "x2", "y2", "live", "off", "c", "s", "w", "t", "st")

    def __init__(self, x1, y1, x2=None, y2=None, c=None, s="solid", w=1, t=None, st="left", live=False, off=0):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2 if y2 is not None else y1
        self.c, self.s, self.w, self.t, self.st, self.live, self.off = c, s, w, t, st, live, off


class _Mini:
    """f_bsl_mini: a timeframe's previous and forming candle (high, low, and when the extremes printed)."""

    def __init__(self, tf: str, times: np.ndarray) -> None:
        self.tf = tf
        self.starts = starts(times, tf)
        self.ready = False

    def __deepcopy__(self, memo):                         # a checkpoint shares the candle boundaries
        twin = copy.copy(self)
        memo[id(self)] = twin
        return twin

    def changed(self, i: int) -> bool:
        return i > 0 and self.starts[i] != self.starts[i - 1]

    def step(self, i: int, o: float, h: float, l: float, t: int) -> None:
        if not self.ready:
            self.h0 = self.h1 = h
            self.l0 = self.l1 = l
            self.o0 = self.o1 = o
            self.t0 = self.t1 = t
            self.h0bar = self.l0bar = self.h1bar = self.l1bar = t
            self.ready = True
        self.prev_h1, self.prev_l1, self.prev_h1bar, self.prev_l1bar = self.h1, self.l1, self.h1bar, self.l1bar
        before = (self.o0, self.h0, self.l0, self.t0, self.h0bar, self.l0bar)
        change = self.changed(i)
        if change:
            self.t0, self.o0, self.h0, self.l0 = t, o, h, l
        if h >= self.h0:
            self.h0, self.h0bar = h, t
        if l <= self.l0:
            self.l0, self.l0bar = l, t
        if change:
            self.o1, self.h1, self.l1, self.t1, self.h1bar, self.l1bar = before


class _Atr:
    """ta.atr: Wilder's average true range."""

    def __init__(self, n: int) -> None:
        self.n, self.value, self.trs, self.prev_close = n, NA, [], NA

    def step(self, h: float, l: float, c: float) -> None:
        tr = h - l if math.isnan(self.prev_close) else max(h - l, abs(h - self.prev_close), abs(l - self.prev_close))
        self.prev_close = c
        if math.isnan(self.value):
            self.trs.append(tr)
            if len(self.trs) == self.n:
                self.value = sum(self.trs) / self.n
        else:
            self.value = (self.value * (self.n - 1) + tr) / self.n


class _Session:
    """One session of a kind: its box, its high and low lines and labels, and whether each is still untouched."""

    def __init__(self, t: int, i_time: int, h: float, l: float) -> None:
        self.box = [t, t, h, l]                                    # left, right, top, bottom
        self.hi = _Obj(i_time, h, i_time)
        self.lo = _Obj(i_time, l, i_time)
        self.hi_valid = self.lo_valid = True
        self.hi_lbl = [t, h]                                       # x, y
        self.lo_lbl = [t, l]
        self.hi_lbl_live = self.lo_lbl_live = False


class _Kind:
    def __init__(self, name: str, window: tuple[int, int], color: str, hi: str, lo: str) -> None:
        self.name, self.window, self.color, self.hi_txt, self.lo_txt = name, window, color, hi, lo
        self.sessions: list[_Session] = []
        self.created, self.created_day = False, None

    def inside(self, t: int) -> bool:
        minute = (t % 86400) // 60
        a, b = self.window
        return (a <= minute < b) if a < b else (minute >= a or minute < b) if b != 0 else minute >= a


class _Prev:
    """f_prev_level: one previous-period high or low."""

    def __init__(self, kind: str, high: bool, text: str) -> None:
        self.kind, self.high, self.text = kind, high, text
        self.lv, self.lv_time, self.touched = NA, None, False
        self.ln: Optional[_Obj] = None


class _BslSide:
    def __init__(self) -> None:
        self.lines: list[dict] = []                               # newest first: obj, trig, time


class _Bsl:
    """f_bsl_ssl_v2 for one timeframe: the swing highs (BSL) and lows (SSL) of its candles."""

    def __init__(self, n: int, mini: _Mini, enabled: bool) -> None:
        self.n, self.mini, self.enabled, self.ready = n, mini, enabled, False
        self.bsl, self.ssl = _BslSide(), _BslSide()
        self.bsl_temp: Optional[_Obj] = None
        self.ssl_temp: Optional[_Obj] = None
        self.sayh = self.sayl = 0


class Liquidity:
    """The liquidity suite over one chart, read candle by candle."""

    def __init__(self, chart: Chart, s: FractalSettings) -> None:
        self.ch, self.s = chart, s
        sec = chart.sec
        self.intraday = sec < (in_seconds(s.lq_hide_above_tf) or 0)
        self.kinds = [_Kind(*x) for x in s.sessions()] if s.lq_show_sessions else []
        self.tdo: Optional[_Obj] = None
        self.tdo_label: Optional[_Obj] = None
        self.minis = {tf: _Mini(tf, chart.time) for tf in ("1D", "1W", "1M")}
        self.prev = [(_Prev("PD", True, "PDH"), s.lq_show_pd), (_Prev("PD", False, "PDL"), s.lq_show_pd),
                     (_Prev("PW", True, "PWH"), s.lq_show_pw), (_Prev("PW", False, "PWL"), s.lq_show_pw),
                     (_Prev("PM", True, "PMH"), s.lq_show_pm), (_Prev("PM", False, "PML"), s.lq_show_pm)]
        htf1 = bsl_auto(chart.tf) if s.lq_htf1_mode == "Auto" else s.lq_htf1_manual
        self.bsl_tfs = [htf1, s.lq_htf2_manual, s.lq_htf3_manual]
        self.bsl_minis = [_Mini(tf, chart.time) for tf in self.bsl_tfs]
        self.bsls = [_Bsl(n + 1, m, on) for n, (m, on) in
                     enumerate(zip(self.bsl_minis, (s.lq_show_htf1, s.lq_show_htf2, s.lq_show_htf3)))]
        self.prg: list[dict] = []                                  # the purged registry, oldest first
        self.atr = _Atr(s.lq_atr_len)
        # Relevant swings
        self.swing_starts = starts(chart.time, bsl_auto(chart.tf)) if s.lq_show_swings else None
        self.swing_changes: list[int] = []
        self.swing_atr = _Atr(s.lq_swing_atr_len)
        self.sw = {True: [], False: []}                            # highs, lows: dicts price, bar, time, obj, lbl
        self.orphans: list[_Obj] = []
        self.pos = -1

    _STATE = ("kinds", "tdo", "tdo_label", "minis", "prev", "bsl_minis", "bsls", "prg", "atr", "swing_changes",
              "swing_atr", "sw", "orphans", "pos")

    def state(self) -> dict:
        return copy.deepcopy({k: getattr(self, k) for k in self._STATE})

    def restore(self, state: dict) -> None:
        for k, v in copy.deepcopy(state).items():                 # one deepcopy: each BSL keeps its own mini
            setattr(self, k, v)

    # ── the purged registry ──────────────────────────────────────────────────
    def _trim(self) -> None:
        del self.prg[:max(0, len(self.prg) - self.s.lq_max_purged)]

    def _touch(self, i: int, price: float, prio: int, crtime: int) -> None:
        """f_touch_mark: a ✕ where a session high or low or a swing was touched."""
        self.prg.append({"ln": None, "x": int(self.ch.time[i]), "price": price, "prio": prio, "time": crtime})
        self._trim()

    def _purge(self, i: int, obj: _Obj, level: float, prio: int, crtime: int) -> None:
        """f_purge_level: the level greys out, ends at this candle and gets its ✕ (or goes, if purged levels are
        deleted)."""
        if self.s.lq_del_purged:
            return
        t = int(self.ch.time[i])
        obj.c, obj.s, obj.x2, obj.live, obj.off = PURGED, "dotted", t, False, 0
        self.prg.append({"ln": obj, "x": t, "price": level, "prio": prio, "time": crtime})
        self._trim()

    # ── reading a candle ─────────────────────────────────────────────────────
    def step(self, i: int) -> None:
        ch, s = self.ch, self.s
        o, h, l, c, t = ch.o[i], ch.h[i], ch.l[i], ch.c[i], int(ch.time[i])
        self.pos = i
        self.atr.step(h, l, c)
        if self.intraday:
            for kind in self.kinds:
                self._session(i, kind)
        self._true_open(i)
        for m in self.minis.values():
            m.step(i, o, h, l, t)
        for p, on in self.prev:
            self._prev_level(i, p, on)
        for m in self.bsl_minis:
            m.step(i, o, h, l, t)
        for b in self.bsls:
            self._bsl(i, b)
        if s.lq_show_swings:
            self._swings(i)

    def _session(self, i: int, k: _Kind) -> None:
        ch, s = self.ch, self.s
        h, l, t = ch.h[i], ch.l[i], int(ch.time[i])
        inside = k.inside(t)
        day = (t // 86400)
        if k.created and day != k.created_day:
            k.created = False
        if inside and (not k.created or not k.sessions):
            k.sessions.insert(0, _Session(t, t, h, l))
            del k.sessions[s.lq_max_sessions:]
            k.created, k.created_day = True, day
        if inside and k.sessions:                                  # f_lq_adjust_in_kz
            z = k.sessions[0]
            z.box[1], z.box[2], z.box[3] = t, max(z.box[2], h), min(z.box[3], l)
            z.hi.x2 = t
            if h > z.hi.y1:
                z.hi.x1 = z.hi.x2 = t
                z.hi.y1 = z.hi.y2 = h
            z.lo.x2 = t
            if l < z.lo.y1:
                z.lo.x1 = z.lo.x2 = t
                z.lo.y1 = z.lo.y2 = l
            if h > z.hi_lbl[1]:
                z.hi_lbl = [t, h]
            if l < z.lo_lbl[1]:
                z.lo_lbl = [t, l]
            z.hi.live = z.lo.live = True
            z.hi_lbl_live = z.lo_lbl_live = False
        if not inside and k.sessions:                              # f_lq_adjust_out_kz
            z = k.sessions[0]
            back3 = int(ch.time[max(0, i - 3)])
            if z.hi_valid:
                z.hi.x2, z.hi_lbl[0], z.hi.live, z.hi_lbl_live = t, t, True, True
                if h >= z.hi.y1:
                    z.hi_valid, z.hi.live, z.hi_lbl_live = False, False, False
                    self._touch(i, z.hi.y1, 2, z.box[0])
                    z.hi_lbl[0] = back3
            if z.lo_valid:
                z.lo.x2, z.lo_lbl[0], z.lo.live, z.lo_lbl_live = t, t, True, True
                if l <= z.lo.y1:
                    z.lo_valid, z.lo.live, z.lo_lbl_live = False, False, False
                    self._touch(i, z.lo.y1, 2, z.box[0])
                    z.lo_lbl[0] = back3
        for n, z in enumerate(k.sessions):                         # only the newest moves
            if n:
                z.hi.live = z.lo.live = z.hi_lbl_live = z.lo_lbl_live = False

    def _true_open(self, i: int) -> None:
        ch = self.ch
        if not self.intraday:
            self.tdo = self.tdo_label = None
            return
        t = int(ch.time[i])
        midnight = (t % 86400) < 60
        was = i > 0 and (int(ch.time[i - 1]) % 86400) < 60
        if midnight and not was:
            self.tdo = _Obj(t, ch.o[i], t, c=TDO, live=True)
            self.tdo_label = _Obj(t, ch.o[i], t="TDO", c=TDO, st="down", live=True)
        if self.tdo is not None:
            self.tdo.x2 = t
            self.tdo_label.x1 = t

    def _prev_level(self, i: int, p: _Prev, on: bool) -> None:
        if not on:
            return
        ch, m = self.ch, self.minis[{"PD": "1D", "PW": "1W", "PM": "1M"}[p.kind]]
        t = int(ch.time[i])
        h1, l1 = m.h1, m.l1
        if math.isnan(h1) or math.isnan(l1):
            return
        if m.changed(i):
            p.lv, p.lv_time = (h1, m.h1bar) if p.high else (l1, m.l1bar)
            p.touched = False
            p.ln = _Obj(p.lv_time, p.lv, t, c=COLORS[p.kind], live=True, t=p.text)
        elif p.ln is not None:
            p.ln.x2 = t
            if not p.touched and ((ch.h[i] >= p.lv) if p.high else (ch.l[i] <= p.lv)):
                p.touched = True
                self._purge(i, p.ln, p.lv, 1, p.lv_time)
                p.ln = None

    def _bsl(self, i: int, b: _Bsl) -> None:
        if not b.enabled:
            return
        ch, m, sec = self.ch, b.mini, self.ch.sec
        h, l, t = ch.h[i], ch.l[i], int(ch.time[i])
        if not b.ready:
            b.h2 = b.h3 = b.h4 = h
            b.l2 = b.l3 = b.l4 = l
            b.h2bar = b.l2bar = t
            b.ready = True
        color = COLORS[b.n]
        if m.changed(i):
            b.h4, b.l4 = b.h3, b.l3
            b.h3, b.l3 = b.h2, b.l2
            b.h2, b.l2 = m.prev_h1, m.prev_l1
            b.h2bar, b.l2bar = m.prev_h1bar, m.prev_l1bar
            b.sayh = b.sayl = 0
            b.bsl_temp = b.ssl_temp = None
        h0, l0, h1, l1 = m.h0, m.l0, m.h1, m.l1
        faint = color.split("@")[0] + "@0.4"
        if (h1 > b.h2 and h1 > h0) or (h1 == b.h2 and h1 > h0 and b.h2 > b.h3):
            b.bsl_temp = _Obj(m.h1bar, h1, t, c=faint, s="dashed")
        if (l1 < b.l2 and l1 < l0) or (l1 == b.l2 and l1 < l0 and b.l2 < b.l3):
            b.ssl_temp = _Obj(m.l1bar, l1, t, c=faint, s="dashed")
        if ((b.h2 > b.h3 and b.h2 > h1) or (b.h2 == b.h3 and b.h2 > h1 and b.h3 > b.h4)) and b.sayh == 0:
            b.bsl.lines.insert(0, {"obj": _Obj(b.h2bar, b.h2, t + 4 * sec, c=color, live=True, off=4, t="BSL"),
                                   "time": b.h2bar})
            b.sayh = 1
        if ((b.l2 < b.l3 and b.l2 < l1) or (b.l2 == b.l3 and b.l2 < l1 and b.l3 < b.l4)) and b.sayl == 0:
            b.ssl.lines.insert(0, {"obj": _Obj(b.l2bar, b.l2, t + 4 * sec, c=color, live=True, off=4, t="SSL"),
                                   "time": b.l2bar})
            b.sayl = 1
        prev_h = ch.h[i - 1] if i > 0 else NA
        prev_l = ch.l[i - 1] if i > 0 else NA
        prio = 6 - b.n                                                 # HTF1 5, HTF2 4, HTF3 3
        for n in range(len(b.bsl.lines) - 1, -1, -1):
            x = b.bsl.lines[n]
            top = x["obj"].y1
            if h < top:
                x["obj"].x2 = t + 4 * sec
            if h >= top and prev_h < top:
                self._purge(i, x["obj"], top, prio, x["time"])
                del b.bsl.lines[n]
        for n in range(len(b.ssl.lines) - 1, -1, -1):
            x = b.ssl.lines[n]
            bot = x["obj"].y1
            if l > bot:
                x["obj"].x2 = t + 4 * sec
            if l <= bot and prev_l > bot:
                self._purge(i, x["obj"], bot, prio, x["time"])
                del b.ssl.lines[n]
        del b.bsl.lines[self.s.lq_max_bsl_lines:]
        del b.ssl.lines[self.s.lq_max_bsl_lines:]

    def _swings(self, i: int) -> None:
        ch, s = self.ch, self.s
        h, l, t = ch.h[i], ch.l[i], int(ch.time[i])
        self.swing_atr.step(h, l, ch.c[i])
        if i > 0 and self.swing_starts[i] != self.swing_starts[i - 1]:
            self.swing_changes.append(i)
        window = s.lq_swing_window
        win_start = self.swing_changes[-window] if len(self.swing_changes) >= window else None
        n = s.lq_swing_len
        p = i - n
        if p - n >= 0:
            for high in (True, False):
                vals = ch.h if high else ch.l
                v = vals[p]
                around = np.r_[vals[p - n:p], vals[p + 1:i + 1]]
                if (v > around).all() if high else (v < around).all():
                    lbl = None if s.lq_swing_label == "Hide" else s.lq_swing_label
                    self.sw[high].append({"price": float(v), "bar": p, "time": int(ch.time[p]),
                                          "obj": _Obj(int(ch.time[p]), float(v), t, c=SWING, s="dotted", t=lbl)})
        if win_start is not None:
            for high in (True, False):
                self.sw[high] = [x for x in self.sw[high] if x["bar"] >= win_start]
        thresh = self.swing_atr.value * s.lq_atr_mult if not math.isnan(self.swing_atr.value) else NA
        prev_h = ch.h[i - 1] if i > 0 else NA
        prev_l = ch.l[i - 1] if i > 0 else NA
        for high in (True, False):
            levels = self.sw[high]
            keep = [True] * len(levels)
            if thresh > 0 and len(levels) > 1:
                for a in range(len(levels) - 1):
                    if not keep[a]:
                        continue
                    pa = levels[a]["price"]
                    for b in range(a + 1, len(levels)):
                        if keep[b] and abs(pa - levels[b]["price"]) <= thresh:
                            if (pa >= levels[b]["price"]) if high else (pa <= levels[b]["price"]):
                                keep[b] = False
                            else:
                                keep[a] = False
                                break
            kept = sum(keep)
            while kept > s.lq_swing_max_levels:
                worst = None
                for a, x in enumerate(levels):
                    if keep[a] and (worst is None or ((x["price"] < levels[worst]["price"]) if high
                                                      else (x["price"] > levels[worst]["price"]))):
                        worst = a
                if worst is not None:
                    keep[worst] = False
                kept -= 1
            for x in levels:
                x["obj"].live = False
            for a in range(len(levels) - 1, -1, -1):
                if not keep[a]:
                    continue
                x = levels[a]
                crossed = (h >= x["price"] and prev_h < x["price"]) if high else (l <= x["price"] and prev_l > x["price"])
                if crossed:
                    self.orphans.append(x["obj"])
                    del self.orphans[:-_ORPHANS]
                    del levels[a]
                    self._touch(i, x["price"], 6, x["time"])
                else:
                    x["obj"].x2, x["obj"].live = t, True

    # ── drawing ──────────────────────────────────────────────────────────────
    def _registered(self) -> list[tuple]:
        """The levels Pine registers for reconciliation on this candle, in its order: (kind, ref, price, prio,
        time, purged)."""
        out = []
        for k in self.kinds:
            if not k.sessions:
                continue
            inside = k.inside(int(self.ch.time[self.pos])) if self.pos >= 0 else False
            for n, z in enumerate(k.sessions):
                if n == 0 and inside:
                    continue
                if z.hi_valid:
                    out.append(("obj", z.hi, z.hi.y1, 2, z.box[0], False))
                if z.lo_valid:
                    out.append(("obj", z.lo, z.lo.y1, 2, z.box[0], False))
        for p, on in self.prev:
            if on and p.ln is not None:
                out.append(("obj", p.ln, p.lv, 1, p.lv_time, False))
        for b in self.bsls:
            if b.enabled:
                for x in b.bsl.lines + b.ssl.lines:
                    out.append(("obj", x["obj"], x["obj"].y1, 6 - b.n, x["time"], False))
        for high in (True, False):
            for x in reversed(self.sw[high]):
                if x["obj"].live:
                    out.append(("obj", x["obj"], x["price"], 6, x["time"], False))
        for x in self.prg:
            out.append(("prg", x, x["price"], x["prio"], x["time"], True))
        return out

    def _hidden(self) -> set[int]:
        """f_rc_reconcile: which registered levels the relevance filter hides (ids of their objects)."""
        reg = self._registered()
        hidden = [False] * len(reg)
        if len(reg) > 1 and not math.isnan(self.atr.value):
            thresh = self.atr.value * self.s.lq_atr_mult
            for a in range(len(reg) - 1):
                if hidden[a]:
                    continue
                _, _, pa, pri_a, tim_a, prg_a = reg[a]
                for b in range(a + 1, len(reg)):
                    if hidden[b] or abs(pa - reg[b][2]) > thresh:
                        continue
                    _, _, _, pri_b, tim_b, prg_b = reg[b]
                    if prg_a != prg_b:
                        hide_a = prg_a
                    elif prg_a:
                        hide_a = False if tim_a < tim_b else True if tim_b < tim_a else pri_a > pri_b
                    elif (pri_a == 6) != (pri_b == 6):
                        hide_a = pri_a == 6
                    else:
                        hide_a = False if tim_a < tim_b else True if tim_b < tim_a else pri_a > pri_b
                    if hide_a:
                        hidden[a] = True
                        break
                    hidden[b] = True
        return {id(r[1]) for r, h in zip(reg, hidden) if h}

    def draw(self, pos: int, now: Now, d: FractalSettings) -> list[dict]:
        out: list[dict] = []
        hidden = self._hidden() if d.lq_mark_relevant else set()
        sec = self.ch.sec

        def x2_of(o: _Obj):
            return now.time + o.off * sec if o.live else o.x2

        def put(o: _Obj, layer: str, text: Optional[str] = None, style: str = "left", label_x=None):
            if id(o) in hidden:
                return
            out.append(line(layer, o.x1, o.y1, x2_of(o), o.y2, o.c, o.s, o.w))
            if text:
                out.append(label(layer, label_x if label_x is not None else x2_of(o), o.y1, text, o.c, style, "small"))

        for k in self.kinds:
            color = hexa(k.color)
            fill = hexa(k.color, d.lq_box_transp) if d.lq_draw_style in ("Box", "Both") else None
            for z in k.sessions:
                if fill:
                    out.append(box("sessions", z.box[0], z.box[2], z.box[1], z.box[3], fill, fill))
                if d.lq_draw_style in ("Lines", "Both"):
                    for o in (z.hi, z.lo):
                        if id(o) not in hidden:
                            out.append(line("sessions", o.x1, o.y1, now.time if o.live else o.x2, o.y1, color))
                if d.lq_session_labels:
                    for lbl, live, text, style in ((z.hi_lbl, z.hi_lbl_live, k.hi_txt, "down"),
                                                   (z.lo_lbl, z.lo_lbl_live, k.lo_txt, "up")):
                        out.append(label("sessions", now.time if live else lbl[0], lbl[1], text, color, style, "small"))
        if d.lq_use_true_open and self.tdo is not None:
            out.append(line("tdo", self.tdo.x1, self.tdo.y1, now.time, self.tdo.y1, TDO))
            if d.lq_tdo_show_label:
                out.append(label("tdo", now.time, self.tdo.y1, "TDO", TDO, "down", "small"))
        for p, on in self.prev:
            if on and p.ln is not None:
                put(p.ln, p.kind.lower(), p.text)
        for b in self.bsls:
            if not b.enabled:
                continue
            layer = f"bsl{b.n}"
            for temp in (b.bsl_temp, b.ssl_temp):
                if temp is not None:
                    out.append(line(layer, temp.x1, temp.y1, temp.x2, temp.y1, temp.c, temp.s))
            for x in b.bsl.lines + b.ssl.lines:
                put(x["obj"], layer, x["obj"].t)
        for o in self.orphans:
            out.append(line("swings", o.x1, o.y1, o.x2, o.y1, o.c, o.s))
        for high in (True, False):
            for x in self.sw[high]:
                o = x["obj"]
                if id(o) in hidden:
                    continue
                out.append(line("swings", o.x1, o.y1, now.time if o.live else o.x2, o.y1, o.c, o.s))
                if o.t:
                    out.append(label("swings", now.time if o.live else o.x2, o.y1, o.t, o.c, "left", "tiny"))
        for x in self.prg:
            if id(x) in hidden:
                continue
            if x["ln"] is not None:
                o = x["ln"]
                out.append(line("purged", o.x1, o.y1, o.x2, o.y1, PURGED, "dotted"))
            if d.lq_purge_cross:
                out.append(label("purged", x["x"], x["price"], "✕", PURGED, "left", "tiny"))
        return out
