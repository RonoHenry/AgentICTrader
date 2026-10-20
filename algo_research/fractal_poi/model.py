"""The indicator's model (algo-backtester Requirement 21.2): HTF candles, the C1/C2 sweep, CISD and IC-CISD, the C3
and C4 entry zones, the SD projections, formation liquidity and SMT.

A port of the Pine methods ``Monitor``, ``Update`` and ``DrawAll`` (with ``DrawSetups`` and ``DrawHTF2``), one
statement for one, in the indicator's order. The names are Pine's, so the two can be read side by side.

**Reading.** ``step(i)`` reads chart candle ``i`` once it has closed: the indicator's "Calculate on Close". Its
order per candle is:
1. the SMT trackers;
2. ``Monitor`` (the setups), against the HTF candles as they stood before this candle;
3. ``Update`` (this candle into the forming HTF candle);
4. the HTF2 preview.

**Drawing.** ``draw(pos, now, s)`` draws what the indicator would show on its last bar, given the candles read
so far (``pos``) and the clock's candle (``now``).

Pine's ``na`` is NaN for prices, so a comparison with it is false there and here; for bar indexes it is None.
The model keeps what Pine keeps:
- the last ``max_display`` HTF candles, newest first;
- the setups that completed, newest first, capped at (HTF candles + history) x 2;
- at most one live bearish and one live bullish setup.

Validates: Requirements 21.2, 21.3 and 22.1 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import copy
import math
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from algo_research.fractal_poi.chart import Chart, Now, box, label, line, rgb
from algo_research.fractal_poi.frames import QUARTERLY, htf_name, in_seconds, ltf_name, period_end, starts, valid_htf
from algo_research.fractal_poi.settings import FractalSettings

__all__ = ["Model", "Setup"]

NA = float("nan")


def isna(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


# The indicator's default colours.
BLACK = rgb(0, 0, 0)
BULL_BODY = rgb(0x6b, 0xa5, 0x83)
CISD_BULL, CISD_BEAR = rgb(41, 98, 255), rgb(242, 54, 69)
ZONE_BULL, ZONE_BEAR = rgb(41, 98, 255, 94), rgb(242, 54, 69, 94)
EARLY = rgb(120, 123, 134)
PROJ = rgb(0, 0, 0, 80)
SMT = rgb(156, 39, 176)
VT, HL, TRACE = rgb(0, 0, 0, 70), rgb(0, 0, 0, 70), rgb(0, 0, 0, 50)
RED, GRAY = rgb(0xf2, 0x36, 0x45), rgb(0x78, 0x7b, 0x86)


class Candle:
    __slots__ = ("o", "c", "h", "l", "o_time", "c_time", "o_idx", "c_idx", "h_idx", "l_idx", "dow", "left", "right",
                 "wick")

    def __init__(self, o, h, l, c, t, i, dow=""):
        self.o, self.h, self.l, self.c = o, h, l, c
        self.o_time, self.c_time = t, None
        self.o_idx = self.c_idx = self.h_idx = self.l_idx = i
        self.dow = dow
        self.left = self.right = self.wick = None


class ICCisd:
    __slots__ = ("level", "start_idx", "end_idx", "extreme_price", "extreme_idx", "taken")

    def __init__(self, level, start_idx, end_idx, extreme_price, extreme_idx):
        self.level, self.start_idx, self.end_idx = level, start_idx, end_idx
        self.extreme_price, self.extreme_idx, self.taken = extreme_price, extreme_idx, False


class Setup:
    """Pine's ``Setup``: a C1 swept by C2, through CISD, C3 and C4."""
    _FLOATS = ("sweep_price", "c2_y", "c2_extreme", "cisd_level", "tracked_extreme", "ic_level", "ic_extreme",
               "ic_last_extreme", "proj_anchor_1", "proj_anchor_0", "liq_c1_price", "liq_c0_price", "c2_mid", "c3_open",
               "ez_c3_top", "ez_c3_bot", "c3_mid", "c3_extreme", "c4_open", "ez_c4_top", "ez_c4_bot", "smt_y1", "smt_y2")
    _INTS = ("sweep_ltf_idx", "sweep_bar_idx", "swept_candle_idx", "htf_candle_idx", "ltf_end_idx", "htf_count", "c2_x",
             "cisd_start_idx", "cisd_end_idx", "extreme_bar_idx", "ic_start_idx", "ic_extreme_idx", "proj_start_idx",
             "proj_end_idx", "liq_c1_start_idx", "liq_c0_start_idx", "liq_end_time", "liq_c1_mitigated_idx",
             "liq_c0_mitigated_idx", "ez_c3_left_time", "ez_c3_right_time", "ez_c4_invalid_time", "ez_c4_left_time",
             "ez_c4_right_time", "smt_x1", "smt_x2")
    _BOOLS = ("is_bullish", "is_confirmed", "is_post_c2", "has_cisd", "cisd_triggered", "ic_active", "ic_pending",
              "ic_seen_same_side", "is_invalid", "ez_c3_set", "ez_c4_set", "ez_c4_invalid", "has_smt")
    __slots__ = _FLOATS + _INTS + _BOOLS + ("ic_list", "smt_symbol", "uid")

    def __init__(self, is_bullish: bool, uid: int) -> None:
        for name in self._FLOATS:
            setattr(self, name, NA)
        for name in self._INTS:
            setattr(self, name, None)
        for name in self._BOOLS:
            setattr(self, name, False)
        self.is_bullish, self.ic_list, self.smt_symbol, self.uid = is_bullish, None, "", uid


class Tracker:
    """SMT_Tracker: the running high and low of the current HTF candle, and the previous one's."""
    __slots__ = ("h", "l", "h_idx", "l_idx", "prev_h", "prev_l", "prev_h_idx", "prev_l_idx")

    def __init__(self) -> None:
        self.h = self.l = self.prev_h = self.prev_l = NA
        self.h_idx = self.l_idx = self.prev_h_idx = self.prev_l_idx = None


class Partner:
    """A correlated symbol for SMT: its name and its chart candles' highs and lows on this chart's candles."""

    def __init__(self, name: str, high: np.ndarray, low: np.ndarray, inverse: bool) -> None:
        self.name, self.high, self.low, self.inverse = name, high, low, inverse


def _weekday_letter(t: int) -> str:
    trading = datetime.fromtimestamp((t - 17 * 3600) // 86400 * 86400 + 86400, timezone.utc)
    return "MTWTFSS"[trading.weekday()]


def _fmt(t: int, pattern: str) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).strftime(pattern)


class Model:
    """The HTF candle set and its setups over one chart, read candle by candle."""

    def __init__(self, chart: Chart, s: FractalSettings, symbol: str, partners: tuple[Partner, ...] = (),
                 events: Optional[list] = None) -> None:
        from algo_research.fractal_poi.frames import fractal_htf, htf2_auto
        self.ch, self.s, self.symbol = chart, s, symbol
        self.htf = fractal_htf(s.fractal_mode, chart.tf, s.custom_htf)
        self.valid = valid_htf(self.htf, chart.tf)
        self.quarterly = self.htf in QUARTERLY
        self.starts = starts(chart.time, self.htf) if self.valid else None
        self.htf2 = s.htf2_custom if s.htf2_mode == "Custom" else htf2_auto(chart.tf)
        self.htf2_valid = valid_htf(self.htf2, chart.tf)
        self.starts2 = starts(chart.time, self.htf2) if self.htf2_valid else None
        self.partners = partners
        self.events = events if events is not None else []
        self.candles: list[Candle] = []
        self.setups: list[Setup] = []
        self.live = {False: None, True: None}                   # bearish, bullish
        self.curr, self.trk = Tracker(), [Tracker(), Tracker()]
        self.htf2_candles: list[Candle] = []
        self._uid = 0

    # ── state, for checkpoints ───────────────────────────────────────────────
    _STATE = ("candles", "setups", "live", "curr", "trk", "htf2_candles", "_uid")

    def state(self) -> dict:
        return copy.deepcopy({k: getattr(self, k) for k in self._STATE})

    def restore(self, state: dict) -> None:
        for k, v in copy.deepcopy(state).items():
            setattr(self, k, v)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _new_setup(self, bull: bool) -> Setup:
        self._uid += 1
        return Setup(bull, self._uid)

    def _time_close_htf(self, i: int) -> int:
        return period_end(int(self.starts[i]), self.htf)

    def _liq_end(self, i: int) -> int:
        t = int(self.ch.time[i])
        if self.quarterly:
            return t + QUARTERLY[self.htf]
        return self._time_close_htf(i) + in_seconds(self.htf)

    def _event(self, i: int, bull: bool, name: str, kind: str) -> None:
        self.events.append({"t": int(self.ch.end[i]), "kind": kind, "dir": "bull" if bull else "bear",
                            "text": f"{'Bullish' if bull else 'Bearish'} {name} ({ltf_name(self.ch.tf)}-{htf_name(self.htf)})"})

    def find_cisd(self, i: int, extreme_idx: int, bias: int) -> tuple[float, Optional[int]]:
        """FindCISDLevel: from the extreme back, the open of the first candle of the run of ``bias`` candles that
        made it (dojis skipped)."""
        o, c = self.ch.o, self.ch.c
        price, idx, found = NA, None, False
        offset = i - extreme_idx
        for k in range(offset, min(offset + 500, i) + 1):
            j = i - k
            att = 1 if c[j] > o[j] else -1 if c[j] < o[j] else 0
            if att == 0:
                continue
            if not found:
                if att == bias:
                    found, price, idx = True, o[j], j
            else:
                if att != bias:
                    break
                price, idx = o[j], j
        return price, idx

    def _body_range(self, i: int, cisd_start: Optional[int], extreme: Optional[int]) -> tuple[float, float, float]:
        """GetCisdBodyRange: the bodies' high and low from the CISD candle to the extreme (500 candles at most)."""
        hi = lo = NA
        if cisd_start is not None and extreme is not None:
            off_a, off_b = i - extreme, i - cisd_start
            lo_off, hi_off = max(0, min(off_a, off_b)), min(max(off_a, off_b), 500)
            for k in range(lo_off, hi_off + 1):
                j = i - k
                bt, bb = max(self.ch.o[j], self.ch.c[j]), min(self.ch.o[j], self.ch.c[j])
                hi = bt if isna(hi) else max(hi, bt)
                lo = bb if isna(lo) else min(lo, bb)
        mid = (hi + lo) / 2.0 if not (isna(hi) or isna(lo)) else NA
        return lo, hi, mid

    def _try_ez_c3(self, i: int, s: Setup) -> None:
        if (not s.ez_c3_set and not s.is_invalid and s.is_post_c2 and s.cisd_triggered and not isna(s.c2_mid)
                and not isna(s.c3_open) and s.cisd_start_idx is not None and s.extreme_bar_idx is not None):
            lo, hi, mid = self._body_range(i, s.cisd_start_idx, s.extreme_bar_idx)
            if not (isna(lo) or isna(hi) or isna(mid)):
                c2m = s.c2_mid
                inside = lo <= c2m <= hi
                y2 = mid if inside else s.c3_open
                s.ez_c3_top, s.ez_c3_bot, s.ez_c3_set = max(c2m, y2), min(c2m, y2), True

    def _try_ez_c4(self, s: Setup, c3_h: float, c3_l: float, c4_open: float, left: int, right: int) -> None:
        if not s.is_invalid and not (isna(c3_h) or isna(c3_l) or isna(c4_open)):
            c3m = (c3_h + c3_l) / 2.0
            s.c3_mid, s.c3_extreme, s.c4_open = c3m, (c3_l if s.is_bullish else c3_h), c4_open
            s.ez_c4_left_time, s.ez_c4_right_time = left, right
            if not s.ez_c4_set:
                s.ez_c4_top, s.ez_c4_bot = max(c3m, c4_open), min(c3m, c4_open)
                s.ez_c4_set, s.ez_c4_invalid = True, False

    def _projection(self, i: int, s: Setup) -> None:
        """The SD projection's anchors: "1" at the swing (or its body), "0" at the CISD candle's far end."""
        ch, j, e = self.ch, s.cisd_start_idx, s.extreme_bar_idx
        s.proj_start_idx, s.proj_end_idx = j, e + 1
        if self.s.proj_type == "Wick":
            s.proj_anchor_1 = s.tracked_extreme
            s.proj_anchor_0 = ch.h[j] if s.is_bullish else ch.l[j]
        elif s.is_bullish:
            s.proj_anchor_1, s.proj_anchor_0 = min(ch.o[e], ch.c[e]), max(ch.o[j], ch.c[j])
        else:
            s.proj_anchor_1, s.proj_anchor_0 = max(ch.o[e], ch.c[e]), min(ch.o[j], ch.c[j])

    # ── IC-CISD ──────────────────────────────────────────────────────────────
    def _ic_hard_stop(self, i: int, s: Setup) -> bool:
        return s.is_invalid or s.ez_c4_invalid or (s.ez_c4_right_time is not None and self.ch.time[i] >= s.ez_c4_right_time)

    @staticmethod
    def _ic_clear(s: Setup) -> None:
        s.ic_pending, s.ic_level, s.ic_start_idx, s.ic_extreme, s.ic_extreme_idx = False, NA, None, NA, None
        s.ic_seen_same_side = False

    def _ic_stop(self, s: Setup) -> None:
        s.ic_active = False
        self._ic_clear(s)

    def _ic_reset(self, s: Setup) -> None:
        self._ic_stop(s)
        s.ic_last_extreme = NA
        s.ic_list = []

    def _ic_track(self, i: int, s: Setup) -> None:
        if s.is_bullish:
            if isna(s.ic_extreme) or self.ch.l[i] < s.ic_extreme:
                s.ic_extreme, s.ic_extreme_idx = self.ch.l[i], i
        elif isna(s.ic_extreme) or self.ch.h[i] > s.ic_extreme:
            s.ic_extreme, s.ic_extreme_idx = self.ch.h[i], i

    def _ic_swing(self, i: int, s: Setup, end_idx: int) -> tuple[float, Optional[int]]:
        """ICFindSwing: the most extreme three-candle swing between the pending candle and ``end_idx``."""
        best, best_idx = NA, None
        start = s.ic_start_idx
        if start is not None and end_idx > start:
            h, l = self.ch.h, self.ch.l
            for m in range(start, end_idx):
                if m < 1 or m + 1 > i:
                    continue
                if s.is_bullish:
                    if l[m] < l[m - 1] and l[m] < l[m + 1] and (isna(best) or l[m] < best):
                        best, best_idx = l[m], m
                elif h[m] > h[m - 1] and h[m] > h[m + 1] and (isna(best) or h[m] > best):
                    best, best_idx = h[m], m
        return best, best_idx

    def _ic_mark_taken(self, i: int, s: Setup) -> None:
        if self._ic_hard_stop(i, s) or not s.ic_list:
            return
        for ic in s.ic_list:
            if not ic.taken and not isna(ic.extreme_price):
                if (self.ch.l[i] < ic.extreme_price) if s.is_bullish else (self.ch.h[i] > ic.extreme_price):
                    ic.taken = True

    def _ic_update(self, i: int, s: Setup) -> None:
        """ICUpdate: after the main CISD, each opposite candle's open is a level; a body close through it, with a
        swing made since, confirms an IC-CISD. It stops at the setup's or C4's invalidation, or C4's close."""
        ch = self.ch
        self._ic_mark_taken(i, s)
        if self._ic_hard_stop(i, s):
            self._ic_stop(s)
        elif s.cisd_end_idx is None:
            if not s.is_invalid and (s.ic_active or s.ic_pending):
                self._ic_reset(s)
            else:
                self._ic_stop(s)
        elif i <= s.cisd_end_idx:
            if s.ic_active or s.ic_pending:
                self._ic_clear(s)
                s.ic_active = False
        else:
            if not s.ic_active:
                s.ic_active = True
                if s.ic_list is None:
                    s.ic_list = []
                self._ic_clear(s)
            opp = (ch.c[i] < ch.o[i]) if s.is_bullish else (ch.c[i] > ch.o[i])
            if s.ic_pending:
                if i > s.ic_start_idx:
                    broke = (ch.c[i] > s.ic_level) if s.is_bullish else (ch.c[i] < s.ic_level)
                    sw_px, sw_idx = self._ic_swing(i, s, i)
                    if broke:
                        if not isna(sw_px) and sw_idx is not None:
                            s.ic_list.append(ICCisd(s.ic_level, s.ic_start_idx, i, sw_px, sw_idx))
                            s.ic_last_extreme = sw_px
                            self._ic_clear(s)
                            self._event(i, s.is_bullish, "IC-CISD", "ic")
                        else:
                            new_ext = (ch.l[i] < s.ic_extreme) if s.is_bullish else (ch.h[i] > s.ic_extreme)
                            if new_ext:
                                self._ic_track(i, s)
                            else:
                                self._ic_clear(s)
                    else:
                        self._ic_track(i, s)
                else:
                    self._ic_track(i, s)
            elif opp:
                s.ic_pending, s.ic_level, s.ic_start_idx = True, ch.o[i], i
                s.ic_extreme = ch.l[i] if s.is_bullish else ch.h[i]
                s.ic_extreme_idx, s.ic_seen_same_side = i, False

    # ── SMT ──────────────────────────────────────────────────────────────────
    def _smt_trackers(self, i: int, is_new: bool) -> None:
        h, l = self.ch.h[i], self.ch.l[i]
        tracked = [(self.curr, h, l)] + [(t, p.high[i], p.low[i]) for t, p in zip(self.trk, self.partners)]
        if is_new:
            for t, ph, pl in tracked:
                t.prev_h, t.prev_l, t.prev_h_idx, t.prev_l_idx = t.h, t.l, t.h_idx, t.l_idx
                t.h, t.l, t.h_idx, t.l_idx = ph, pl, i, i
        for n, (t, ph, pl) in enumerate(tracked):
            if n == 0 or not isna(ph):
                if ph > t.h or isna(t.h):
                    t.h, t.h_idx = ph, i
            if n == 0 or not isna(pl):
                if pl < t.l or isna(t.l):
                    t.l, t.l_idx = pl, i

    def _smt(self, bearish: bool) -> tuple[bool, str]:
        """CheckSMTDivergence, at a setup's sweep: the chart takes the HTF candle's extreme and a partner doesn't
        (or, inverted, the partner doesn't make the mirror one)."""
        c = self.curr
        curr_hh, curr_ll = c.h > c.prev_h, c.l < c.prev_l
        curr_lh = c.h < c.prev_h if not isna(c.prev_h) else False
        curr_hl = c.l > c.prev_l if not isna(c.prev_l) else False
        names = []
        for n, (t, p) in enumerate(zip(self.trk, self.partners)):
            if n == 1 and not self.s.smt_sym2_enable:
                continue
            if isna(t.prev_h) or isna(t.h) or isna(c.prev_h):
                continue
            comp_hh, comp_lh = t.h > t.prev_h, t.h < t.prev_h
            comp_ll = t.l < t.prev_l if not isna(t.prev_l) else False
            comp_hl = t.l > t.prev_l if not isna(t.prev_l) else False
            if bearish:
                curr_leads = (curr_hh and comp_hl) if p.inverse else (curr_hh and comp_lh)
                comp_leads = (comp_ll and curr_lh) if p.inverse else (comp_hh and curr_lh)
            else:
                curr_leads = (curr_ll and comp_lh) if p.inverse else (curr_ll and comp_hl)
                comp_leads = (comp_hh and curr_hl) if p.inverse else (comp_ll and curr_hl)
            if curr_leads or comp_leads:
                names.append(p.name)
        return bool(names), "/".join(names)

    # ── reading a candle ─────────────────────────────────────────────────────
    def step(self, i: int) -> None:
        is_new = self.valid and (i == 0 or self.starts[i] != self.starts[i - 1])
        self._smt_trackers(i, is_new if self.valid else False)
        if self.valid:
            self._monitor(i, is_new)
            self._update(i)
        if self.htf2_valid and self.s.htf2_show:
            ch = self.ch
            if i == 0 or self.starts2[i] != self.starts2[i - 1]:
                self.htf2_candles.insert(0, Candle(ch.o[i], ch.h[i], ch.l[i], ch.c[i], int(ch.time[i]), i))
                del self.htf2_candles[self.s.htf2_count:]
            elif self.htf2_candles:
                k = self.htf2_candles[0]
                k.h, k.l, k.c = max(k.h, ch.h[i]), min(k.l, ch.l[i]), ch.c[i]

    def _update(self, i: int) -> None:
        if self.candles:
            k, ch = self.candles[0], self.ch
            if ch.h[i] > k.h:
                k.h, k.h_idx = ch.h[i], i
            if ch.l[i] < k.l:
                k.l, k.l_idx = ch.l[i], i
            k.c, k.c_idx = ch.c[i], i

    def _dow(self, t: int) -> str:
        htf = self.htf
        if htf == "1D":
            return _weekday_letter(t)
        if htf == "1W":
            return _fmt(t, "%b ") + str(int(_fmt(t, "%d")))
        if htf == "1M":
            return _fmt(t, "%b")
        if htf == "3M":
            return f"Q{(int(_fmt(t, '%m')) - 1) // 3 + 1}"
        if htf == "12M":
            return ""
        return _fmt(t, "%H:%M")

    def _monitor(self, i: int, is_new: bool) -> None:
        ch, cs = self.ch, self
        o, h, l, c, t = ch.o[i], ch.h[i], ch.l[i], ch.c[i], int(ch.time[i])
        prev_close = ch.c[i - 1] if i > 0 else NA
        if is_new:
            for bull in (False, True):
                s = cs.live[bull]
                if s is not None and s.sweep_bar_idx != i and not s.is_post_c2:
                    if not ((prev_close > s.sweep_price) if bull else (prev_close < s.sweep_price)):
                        cs.live[bull] = None
        prev_idx = 0 if is_new else 1
        if len(cs.candles) > prev_idx:
            prev = cs.candles[prev_idx]
            high_breached, low_breached = h > prev.h, l < prev.l
            high_sweep_confirmed = high_breached and c < prev.h
            low_sweep_confirmed = low_breached and c > prev.l
            # ===== MITIGATION + C4 INVALIDATION =====
            for s in cs.setups:
                self._ic_mark_taken(i, s)
                if s.cisd_triggered and s.liq_end_time is not None and t < s.liq_end_time:
                    if s.is_bullish:
                        if not isna(s.liq_c1_price) and s.liq_c1_mitigated_idx is None and h >= s.liq_c1_price:
                            s.liq_c1_mitigated_idx = i
                        if not isna(s.liq_c0_price) and s.liq_c0_mitigated_idx is None and h >= s.liq_c0_price:
                            s.liq_c0_mitigated_idx = i
                        if (not s.ez_c4_invalid and not isna(s.c3_extreme) and s.ez_c4_left_time is not None
                                and s.ez_c4_right_time is not None and t < s.ez_c4_right_time and l < s.c3_extreme):
                            s.ez_c4_invalid, s.ez_c4_invalid_time = True, int(ch.end[i])
                    else:
                        if not isna(s.liq_c1_price) and s.liq_c1_mitigated_idx is None and l <= s.liq_c1_price:
                            s.liq_c1_mitigated_idx = i
                        if not isna(s.liq_c0_price) and s.liq_c0_mitigated_idx is None and l <= s.liq_c0_price:
                            s.liq_c0_mitigated_idx = i
                        if (not s.ez_c4_invalid and not isna(s.c3_extreme) and s.ez_c4_left_time is not None
                                and s.ez_c4_right_time is not None and t < s.ez_c4_right_time and h > s.c3_extreme):
                            s.ez_c4_invalid, s.ez_c4_invalid_time = True, int(ch.end[i])
                    self._ic_update(i, s)
            for bull in (False, True):
                self._track(i, bull, is_new, prev, low_breached if bull else high_breached,
                            low_sweep_confirmed if bull else high_sweep_confirmed)
        if is_new:
            for bull in (False, True):
                self._close_htf(i, bull, prev_close)
            k = Candle(o, h, l, c, t, i, self._dow(t))
            cs.candles.insert(0, k)
            if len(cs.candles) > 1:
                cs.candles[1].c_time = t
            if len(cs.candles) > 2 and self.s.sweep_show:
                max_setups = (self.s.max_display + self.s.sweep_history) * 2
                del cs.setups[max_setups:]
            if len(cs.candles) > self.s.max_display:
                cs.candles.pop()

    def _track(self, i: int, bull: bool, is_new: bool, prev: Candle, breached: bool, sweep_confirmed: bool) -> None:
        """BEARISH TRACKING (and its mirror, BULLISH TRACKING)."""
        ch, cs = self.ch, self
        h, l, c = ch.h[i], ch.l[i], ch.c[i]
        far = (lambda a, b: a < b) if bull else (lambda a, b: a > b)          # beyond, on the swept side
        back = (lambda x, level: x > level) if bull else (lambda x, level: x < level)   # back inside / through CISD
        ext = l if bull else h
        live = cs.live[bull]
        if live is None:
            if not breached:
                return
            s = self._new_setup(bull)
            s.sweep_price = prev.l if bull else prev.h
            s.sweep_ltf_idx = prev.l_idx if bull else prev.h_idx
            s.sweep_bar_idx, s.swept_candle_idx = i, prev.o_idx
            s.htf_candle_idx = i if is_new else cs.candles[0].o_idx
            s.ltf_end_idx, s.c2_x, s.c2_y, s.htf_count = i + 50, i, ext, 1
            if is_new:
                s.tracked_extreme, s.extreme_bar_idx = ext, i
            else:
                first = cs.candles[0]
                first_ext = first.l if bull else first.h
                if far(ext, first_ext):
                    s.tracked_extreme, s.extreme_bar_idx = ext, i
                else:
                    s.tracked_extreme, s.extreme_bar_idx = first_ext, (first.l_idx if bull else first.h_idx)
            price, idx = self.find_cisd(i, s.extreme_bar_idx, -1 if bull else 1)
            if not isna(price):
                s.cisd_level, s.cisd_start_idx, s.has_cisd = price, idx, True
            if sweep_confirmed:
                s.is_confirmed = True
            s.liq_c1_price = prev.h if bull else prev.l
            s.liq_c1_start_idx = prev.h_idx if bull else prev.l_idx
            c0_idx = 1 if is_new else 2
            if len(cs.candles) > c0_idx:
                c0 = cs.candles[c0_idx]
                if (c0.h > prev.h) if bull else (c0.l < prev.l):
                    s.liq_c0_price = c0.h if bull else c0.l
                    s.liq_c0_start_idx = c0.h_idx if bull else c0.l_idx
            has_smt, names = self._smt(bearish=not bull)
            if has_smt:
                s.has_smt, s.smt_symbol = True, names
                s.smt_x1, s.smt_y1 = (prev.l_idx, prev.l) if bull else (prev.h_idx, prev.h)
                s.smt_x2, s.smt_y2 = s.extreme_bar_idx, s.tracked_extreme
                self._event(i, bull, "SMT", "smt")
            cs.live[bull] = s
            return
        s = live
        if not s.is_post_c2:
            s.is_confirmed = back(c, s.sweep_price)
            if far(ext, s.tracked_extreme):
                s.tracked_extreme, s.extreme_bar_idx, s.c2_x, s.c2_y = ext, i, i, ext
                if s.has_smt:
                    s.smt_x2, s.smt_y2 = i, ext
                price, idx = self.find_cisd(i, i, -1 if bull else 1)
                if not isna(price):
                    s.cisd_level, s.cisd_start_idx, s.has_cisd = price, idx, True
                    s.cisd_triggered, s.cisd_end_idx = False, None
                    self._ic_reset(s)
            if s.has_cisd and s.cisd_end_idx is None and back(c, s.cisd_level):
                s.cisd_end_idx = i
            if s.is_confirmed and s.has_cisd and not s.cisd_triggered and s.cisd_end_idx is not None:
                s.cisd_triggered = True
                self._projection(i, s)
                self._event(i, bull, "C1 Sweep + CISD (potential)", "potential")
            self._mitigate(i, s)
            self._ic_update(i, s)
            return
        replaced = False
        if far(ext, s.c2_extreme):
            if s.cisd_triggered:
                s.is_invalid = True
                self._ic_stop(s)
                cs.setups.insert(0, s)
            old_c2 = cs.candles[1]
            ns = self._new_setup(bull)
            ns.sweep_price = s.c2_extreme
            ns.sweep_ltf_idx = old_c2.l_idx if bull else old_c2.h_idx
            ns.sweep_bar_idx, ns.swept_candle_idx = i, s.htf_candle_idx
            ns.htf_candle_idx = cs.candles[0].o_idx
            ns.ltf_end_idx, ns.c2_x, ns.c2_y, ns.htf_count = i + 50, i, ext, 1
            ns.tracked_extreme, ns.extreme_bar_idx = ext, i
            price, idx = self.find_cisd(i, i, -1 if bull else 1)
            if not isna(price):
                ns.cisd_level, ns.cisd_start_idx, ns.has_cisd = price, idx, True
            ns.liq_c1_price = old_c2.h if bull else old_c2.l
            ns.liq_c1_start_idx = old_c2.h_idx if bull else old_c2.l_idx
            if back(c, ns.sweep_price):
                ns.is_confirmed = True
            cs.live[bull] = ns
            replaced = True
        if not replaced:
            self._mitigate(i, s)
            if s.has_cisd and not s.cisd_triggered and back(c, s.cisd_level):
                s.cisd_triggered, s.cisd_end_idx = True, i
                self._projection(i, s)
                s.liq_end_time = self._liq_end(i)
                self._try_ez_c3(i, s)
                self._event(i, bull, "C2 + CISD", "c2_cisd")
            self._ic_update(i, s)

    def _mitigate(self, i: int, s: Setup) -> None:
        """The live setup's formation liquidity, taken."""
        h, l = self.ch.h[i], self.ch.l[i]
        if s.is_bullish:
            if not isna(s.liq_c1_price) and s.liq_c1_mitigated_idx is None and h >= s.liq_c1_price:
                s.liq_c1_mitigated_idx = i
            if not isna(s.liq_c0_price) and s.liq_c0_mitigated_idx is None and h >= s.liq_c0_price:
                s.liq_c0_mitigated_idx = i
        else:
            if not isna(s.liq_c1_price) and s.liq_c1_mitigated_idx is None and l <= s.liq_c1_price:
                s.liq_c1_mitigated_idx = i
            if not isna(s.liq_c0_price) and s.liq_c0_mitigated_idx is None and l <= s.liq_c0_price:
                s.liq_c0_mitigated_idx = i

    def _close_htf(self, i: int, bull: bool, prev_close: float) -> None:
        """At a new HTF candle: C2 closes back inside C1 (or the setup goes), and after C3 the setup is kept."""
        ch, cs = self.ch, self
        s = cs.live[bull]
        if s is None or s.sweep_bar_idx == i:
            return
        s.htf_count += 1
        first = cs.candles[0]
        if not s.is_post_c2:
            if (prev_close > s.sweep_price) if bull else (prev_close < s.sweep_price):
                s.is_post_c2 = s.is_confirmed = True
                s.ltf_end_idx = i
                s.c2_extreme = first.l if bull else first.h
                s.c2_mid = (first.h + first.l) / 2.0
                s.c3_open, s.ez_c3_left_time = ch.o[i], int(ch.time[i])
                self._try_ez_c3(i, s)
                self._event(i, bull, "C2", "c2")
                if s.cisd_triggered:
                    self._event(i, bull, "C2 + CISD", "c2_cisd")
            else:
                cs.live[bull] = None
        elif s.htf_count >= 2:
            if s.cisd_triggered:
                if isna(s.proj_anchor_0) and s.has_cisd:
                    self._projection(i, s)
                s.liq_end_time = self._liq_end(i)
                t = int(ch.time[i])
                s.ez_c3_right_time = t
                right = t + QUARTERLY[self.htf] if self.quarterly else self._time_close_htf(i)
                self._try_ez_c4(s, first.h, first.l, ch.o[i], t, right)
                cs.setups.insert(0, s)
            cs.live[bull] = None

    # ── drawing (DrawAll, DrawSetups, DrawHTF2) ──────────────────────────────
    def draw(self, pos: int, now: Now, d: FractalSettings) -> list[dict]:
        if not self.valid:
            return []
        out: list[dict] = []
        X = lambda idx: self.ch.x(idx, pos, now)                                     # noqa: E731
        T = lambda idx: int(self.ch.time[idx]) if idx <= pos else X(idx)             # noqa: E731
        width, size = d.width, len(self.candles)
        for n, k in enumerate(self.candles):                                         # CalculatePositions
            buffer = d.offset + (width + 1) * (size - n - 1)
            k.left, k.right, k.wick = now.idx + buffer, now.idx + width + buffer, now.idx + width / 2 + buffer
        for n, k in enumerate(self.candles):                                         # DrawVTHLLines
            if d.vt_show:
                out.append(line("vt", k.o_time, k.h, k.o_time, k.l, VT, "solid", 1, extend="both"))
            if d.hl_show and n != 0 and k.c_time:
                out.append(line("hl", k.o_time, k.h, k.c_time, k.h, HL, "dotted"))
                out.append(line("hl", k.o_time, k.l, k.c_time, k.l, HL, "dotted"))
        if not d.hide_candles:
            for k in self.candles:                                                   # DrawCandles
                bull = k.c > k.o
                top, bot = max(k.o, k.c), min(k.o, k.c)
                out.append(box("candles", X(k.left), top, X(k.right), bot, BULL_BODY if bull else BLACK, BLACK))
                out.append(line("candles", X(k.wick), k.h, X(k.wick), top, BLACK))
                out.append(line("candles", X(k.wick), bot, X(k.wick), k.l, BLACK))
                if d.daily_name and k.dow:
                    if d.dow_position in ("Both", "Top"):
                        out.append(label("dow", X(k.wick), k.h, k.dow, BLACK, "down", "small"))
                    if d.dow_position in ("Both", "Bottom"):
                        out.append(label("dow", X(k.wick), k.l, k.dow, BLACK, "up", "small"))
            if size and d.htf_label_show:                                            # DrawLabels
                top = max(k.h for k in self.candles)
                bottom = min(k.l for k in self.candles)
                left = now.idx + d.offset + (width + 1) * (size - 1) / 2
                text = htf_name(self.htf)
                if d.htf_timer_show:
                    text += "\n\n(" + self.remaining(now) + ")"
                if d.label_position in ("Both", "Top"):
                    out.append(label("htf_label", X(left), top, text, BLACK, "down", "large"))
                if d.label_position in ("Both", "Bottom"):
                    out.append(label("htf_label", X(left), bottom, text, BLACK, "up", "large"))
            if d.trace_show and self.candles:                                        # DrawTrace
                k = self.candles[0]
                out.append(line("trace", T(k.o_idx), k.o, X(k.left), k.o, TRACE))
        if not d.hide_setups:
            out += self._draw_setups(pos, now, d, X, T)
        if d.htf2_show and self.htf2_valid and self.htf2_candles:
            out += self._draw_htf2(now, d, X)
        return out

    def htf_end(self, now: Now) -> int:
        """When the HTF candle holding the clock's candle closes."""
        return period_end(int(starts(np.array([now.time]), self.htf)[0]), self.htf)

    def remaining(self, now: Now) -> str:
        """The forming HTF candle's time left at the clock, as the indicator's timer writes it."""
        if not self.candles:
            return "n/a"
        left = max(0, self.htf_end(now) - now.clock)
        days, rest = divmod(left, 86400)
        hours, rest = divmod(rest, 3600)
        minutes, seconds = divmod(rest, 60)
        out = f"{seconds:02d}"
        if minutes or hours or days:
            out = f"{minutes:02d}:" + out
        if hours or days:
            out = f"{hours:02d}:" + out
        if days:
            out = f"{days}D " + out
        return out

    def _bias_ok(self, bull: bool, d: FractalSettings) -> bool:
        return d.bias == "Neutral" or (d.bias == "Bullish" and bull) or (d.bias == "Bearish" and not bull)

    def _zone_right(self, locked: Optional[int], now: Now) -> int:
        """EntryZoneRight: a zone runs to the clock's candle's close until its own end."""
        if locked is None:
            return now.end
        return locked if now.time >= locked else min(now.end, locked)

    def _draw_setups(self, pos: int, now: Now, d: FractalSettings, X, T) -> list[dict]:
        out: list[dict] = []
        visible_htf = {k.o_idx for k in self.candles}
        non_visible = total = 0
        for s in self.setups:
            if not s.is_confirmed or not self._bias_ok(s.is_bullish, d):
                continue
            draw = False
            if d.sweep_visible_only:
                if s.htf_candle_idx in visible_htf:
                    draw = True
                elif non_visible < d.sweep_history:
                    draw, non_visible = True, non_visible + 1
            elif total < d.sweep_history:
                draw, total = True, total + 1
            if draw:
                out += self._draw_one(s, False, pos, now, d, X, T)
        for bull in (False, True):
            s = self.live[bull]
            if s is None or not self._bias_ok(bull, d):
                continue
            if d.sweep_live:
                if not (s.is_confirmed or s.is_post_c2):
                    continue
            elif not (s.is_post_c2 and s.cisd_triggered):
                continue
            out += self._draw_one(s, True, pos, now, d, X, T)
        return out

    def _draw_one(self, s: Setup, live: bool, pos: int, now: Now, d: FractalSettings, X, T) -> list[dict]:
        out: list[dict] = []
        bull, tag = s.is_bullish, {"setup": s.uid, "live": live}
        up_down = "up" if bull else "down"

        def add(item: dict) -> None:
            item.update(tag)
            out.append(item)

        if not s.is_invalid and d.liq_show and s.cisd_triggered and not isna(s.liq_c1_price) \
                and (live or s.liq_end_time is not None):
            for price, start, mitigated in ((s.liq_c1_price, s.liq_c1_start_idx, s.liq_c1_mitigated_idx),
                                            (s.liq_c0_price, s.liq_c0_start_idx, s.liq_c0_mitigated_idx)):
                if isna(price):
                    continue
                if mitigated is not None:
                    end = T(mitigated)
                elif live or now.time < s.liq_end_time:
                    end = now.time
                else:
                    end = s.liq_end_time
                add(line("liq", T(start), price, end, price, BLACK, "dotted"))
        if not s.is_invalid and d.proj_show and s.cisd_triggered and not (isna(s.proj_anchor_1) or isna(s.proj_anchor_0)):
            rng = s.proj_anchor_1 - s.proj_anchor_0
            for dev in d.deviations():
                price = s.proj_anchor_0 - abs(rng) * dev if bull else s.proj_anchor_0 + rng * dev
                add(line("proj", X(s.proj_start_idx), price, X(s.proj_end_idx), price, PROJ))
                if d.proj_label_show:
                    add(label("proj", X(s.proj_start_idx), price, f"{dev:g}", PROJ, "right", "small"))
        if d.show_c2_lbl and (not live or (s.is_post_c2 and s.cisd_triggered)):
            add(label("c2", X(s.c2_x), s.c2_y, "xC2" if s.is_invalid else "C2", RED if s.is_invalid else BLACK,
                      up_down, "small"))
        if not s.is_invalid and d.sweep_show:
            end = s.ltf_end_idx if (not live or s.is_post_c2) else now.idx
            add(line("sweep", X(s.sweep_ltf_idx), s.sweep_price, X(end), s.sweep_price, BLACK))
        if not s.is_invalid and not d.hide_candles:
            x1 = next((k.wick for k in self.candles if k.o_idx == s.swept_candle_idx), None)
            x2 = next((k.right for k in self.candles if k.o_idx == s.htf_candle_idx), None)
            if x1 is not None and x2 is not None and d.sweep_show:
                add(line("sweep", X(x1), s.sweep_price, X(x2), s.sweep_price, BLACK))
        if live and not s.is_invalid and d.early_cisd_show and s.has_cisd and not s.cisd_triggered:
            early_end = now.idx if s.cisd_end_idx is None else s.cisd_end_idx
            add(line("early", X(s.cisd_start_idx), s.cisd_level, X(early_end), s.cisd_level, EARLY, "dotted", 2))
            if d.show_c2_lbl:
                add(label("early", X(early_end), s.cisd_level, "+CISD" if bull else "-CISD", EARLY, up_down, "small"))
        if d.cisd_show and s.cisd_triggered and s.has_cisd:
            add(line("cisd", X(s.cisd_start_idx), s.cisd_level, X(s.cisd_end_idx + 1), s.cisd_level,
                     CISD_BULL if bull else CISD_BEAR, "solid", 2))
        if d.ic_cisd_show and s.cisd_triggered and s.ic_list:
            for ic in s.ic_list:
                color = GRAY if ic.taken else (CISD_BULL if bull else CISD_BEAR)
                add(line("ic", X(ic.start_idx), ic.level, X(ic.end_idx), ic.level, color, "solid", 2))
                add(label("ic", X(ic.extreme_idx), ic.extreme_price, "●", color, up_down, "tiny"))
        if not s.is_invalid and d.smt_show and s.has_smt and s.smt_x1 is not None and s.smt_x2 is not None:
            add(line("smt", X(s.smt_x1), s.smt_y1, X(s.smt_x2), s.smt_y2, SMT))
            if d.smt_label_show:
                mid = round((s.smt_x1 + s.smt_x2) / 2)
                add(label("smt", X(mid), (s.smt_y1 + s.smt_y2) / 2, s.smt_symbol, SMT, up_down, "small"))
        chart_eq = d.prev_eq_show and d.drawings_type in ("On Chart", "Both")
        htf_eq = d.prev_eq_show and d.drawings_type in ("HTF candle", "Both")
        if not s.is_invalid and s.is_confirmed and chart_eq:
            if not isna(s.c2_mid) and s.ez_c3_left_time is not None:
                right = self._zone_right(s.ez_c3_right_time, now)
                if right > s.ez_c3_left_time:
                    add(line("eq", s.ez_c3_left_time, s.c2_mid, right, s.c2_mid, BLACK, "dotted"))
            if not isna(s.c3_mid) and s.ez_c4_left_time is not None:
                right = s.ez_c4_invalid_time if (s.ez_c4_invalid and s.ez_c4_invalid_time is not None) \
                    else self._zone_right(s.ez_c4_right_time, now)
                if right > s.ez_c4_left_time:
                    add(line("eq", s.ez_c4_left_time, s.c3_mid, right, s.c3_mid, RED if s.ez_c4_invalid else BLACK,
                             "dotted"))
        if not s.is_invalid and s.is_confirmed and htf_eq and not d.hide_candles:
            c2_i = next((n for n, k in enumerate(self.candles) if k.o_idx == s.htf_candle_idx), -1)
            if not isna(s.c2_mid) and c2_i > 0:
                x1, x2 = self.candles[c2_i].wick, self.candles[c2_i - 1].right + 2
                if x2 > x1:
                    add(line("eq", X(x1), s.c2_mid, X(x2), s.c2_mid, BLACK, "dotted"))
            if not isna(s.c3_mid) and c2_i > 1:
                x1, x2 = self.candles[c2_i - 1].wick, self.candles[c2_i - 2].right + 2
                if x2 > x1:
                    add(line("eq", X(x1), s.c3_mid, X(x2), s.c3_mid, RED if s.ez_c4_invalid else BLACK, "dotted"))
        if not s.is_invalid and d.entry_zone_show and s.ez_c3_set and s.ez_c3_left_time is not None:
            add(box("zone", s.ez_c3_left_time, s.ez_c3_top, self._zone_right(s.ez_c3_right_time, now), s.ez_c3_bot,
                    ZONE_BULL if bull else ZONE_BEAR))
            if d.show_c3_lbl:
                add(label("zone", s.ez_c3_left_time + self.ch.sec, s.ez_c3_bot if bull else s.ez_c3_top, "C3", BLACK,
                          up_down, "small"))
        if not live and not s.is_invalid and d.entry_zone_show and s.ez_c4_set and s.ez_c4_left_time is not None:
            if not s.ez_c4_invalid:
                add(box("zone", s.ez_c4_left_time, s.ez_c4_top, self._zone_right(s.ez_c4_right_time, now), s.ez_c4_bot,
                        ZONE_BULL if bull else ZONE_BEAR))
            if d.show_c4_lbl:
                add(label("zone", s.ez_c4_left_time + self.ch.sec, s.ez_c4_bot if bull else s.ez_c4_top,
                          "xC4" if s.ez_c4_invalid else "C4", RED if s.ez_c4_invalid else BLACK, up_down, "small"))
        return out

    def _draw_htf2(self, now: Now, d: FractalSettings, X) -> list[dict]:
        out: list[dict] = []
        width, n2 = d.width, len(self.htf2_candles)
        base = now.idx + d.offset + (width + 1) * (len(self.candles) - 1) + width + d.htf2_gap
        for n, k in enumerate(self.htf2_candles):
            buffer = (width + 1) * (n2 - n - 1)
            left, right, wick = base + buffer, base + width + buffer, base + width / 2 + buffer
            bull = k.c > k.o
            top, bot = max(k.o, k.c), min(k.o, k.c)
            out.append(box("htf2", X(left), top, X(right), bot, BULL_BODY if bull else BLACK, BLACK))
            out.append(line("htf2", X(wick), k.h, X(wick), top, BLACK))
            out.append(line("htf2", X(wick), bot, X(wick), k.l, BLACK))
        if d.htf2_label_show:
            top, bot = max(k.h for k in self.htf2_candles), min(k.l for k in self.htf2_candles)
            x = X(base + (width + 1) * (n2 - 1) / 2)
            text = htf_name(self.htf2)
            if d.htf2_timer_show:
                start = int(starts(np.array([now.time]), self.htf2)[0])
                text += f"\n\n({_clock(max(0, period_end(start, self.htf2) - now.clock))})"
            if d.htf2_label_position in ("Both", "Top"):
                out.append(label("htf2", x, top, text, BLACK, "down", "large"))
            if d.htf2_label_position in ("Both", "Bottom"):
                out.append(label("htf2", x, bot, text, BLACK, "up", "large"))
        return out


def _clock(left: int) -> str:
    days, rest = divmod(int(left), 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    out = f"{seconds:02d}"
    if minutes or hours or days:
        out = f"{minutes:02d}:" + out
    if hours or days:
        out = f"{hours:02d}:" + out
    return f"{days}D " + out if days else out
