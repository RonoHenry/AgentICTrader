"""The Model A reader (context-engine Requirement 13, update 2026-10-15).

One frame set (F, the context; C, the CRT candles; E, execution) and one direction, read in Model A's order:

    FRAMED      a C candle (C1) closes with price in F's premium and a bearish POI above
    ARMED       price within one F average range of the POI
    MANIPULATED the next C candle (C2) trades above C1's high and into the POI (inducement and time recorded)
    REJECTED    C2 closes back at or under C1's high
    DISPLACED   on E after C2's high: a bearish CISD, a body of 1.5 E average ranges and a bearish FVG in the leg;
                the new range runs from C2's high to the leg's low (MA-D5)
    IN_OTE      in C3, price retraces into 0.62-0.79 of the new range
    ENTERED     the sell limit at 0.705 fills
    then TP1 (C1's low), the SD levels of the new range, STOPPED (above C2's high) or HORIZON

and its invalidations: POI_FAILED, NO_REJECTION, NO_MANIPULATION, MISSED, RETRACE_INVALID, EXPIRED. (REFRAMED
can't occur: before MANIPULATED an instance lives one C candle, and C candles nest inside F's.)

Volatility and time (Requirement 18, update 2026-10-15b): each instance records the phase of the day C2 opened in,
how much of the average daily range (ADR) the day had used by C2's close, the setup's size and TP1's reach in ADR.
A variant can gate on each (``MODEL_A_VT``: early phases, 70% of the ADR, 0.35 ADR, TP1 within reach) and measure
E's sizes against the same time of day over the previous 20 days instead of the last 20 candles.
Sizes are read in each frame's own average range and durations in its own candles, so one reader serves every
frame set (Property 1). It is written for shorts; ``side="LONG"`` reads the mirrored bars and mirrors the prices
back. Bars are New York wall-clock seconds; C and F candles are aggregated from the same M1 bars on the 17:00 New
York calendar, and the reader goes through E bars in order, reading only candles that have closed (Property 2).

    reader = ModelAReader(MODEL_SETS["model_d1"], wall, o, h, l, c, side="SHORT")
    instances = reader.run(start_wall, end_wall)       # one dict per instance
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from liquidity_engine.context.frame_state import (POI, Candidate, DealingRange, bearish_candidates, dealing_range,
                                                  select_pois)
from liquidity_engine.context.measures import (average_range, bearish_cisd, equal_highs, mirror,
                                               rolling_average_range, tight_range)

__all__ = ["DAY_PHASES", "EARLY", "FrameSet", "MODEL_A_VT", "MODEL_SETS", "UNIVERSAL_SETS", "ModelAReader", "Variant",
           "day_phase", "in_time_window"]


@dataclass(frozen=True)
class FrameSet:
    name: str
    f: str            # context: premium/discount and the POI
    c: str            # the CRT candles: C1, C2, C3
    e: str            # execution: inducement, displacement, the new range, the entry


#: MA-D1: the trader's sets, and their variants.
MODEL_SETS = {
    "model_d1": FrameSet("model_d1", "D1", "H1", "M5"),
    "model_h4": FrameSet("model_h4", "H4", "M15", "M1"),
    "model_h4_m30": FrameSet("model_h4_m30", "H4", "M30", "M1"),
    "model_h4_m3": FrameSet("model_h4_m3", "H4", "M15", "M3"),
}
#: Requirement 16.4: the universality check, report-only.
UNIVERSAL_SETS = {
    "w1_d1_h4": FrameSet("w1_d1_h4", "W1", "D1", "H4"),
    "d1_h4_m15": FrameSet("d1_h4_m15", "D1", "H4", "M15"),
    "h1_m15_m1": FrameSet("h1_m15_m1", "H1", "M15", "M1"),
}
_SIZE = {"M1": 0, "M2": 0, "M3": 0, "M4": 0, "M5": 0, "M10": 0, "M15": 0, "M20": 0, "M30": 0, "M45": 0,
         "H1": 1, "H3": 1, "H4": 2, "H6": 2, "H7": 2, "H8": 2, "H12": 2, "D1": 3, "W1": 4, "MN1": 5}
_PREVIOUS = {"D1": "PDH", "W1": "PWH", "MN1": "PMH"}
_DAY, _DAY_OPEN = 86400, 61200                          # trading days open at 17:00 New York
#: F's state is read from its last 600 closed candles: on D1 the whole history, on H4 about four months, on H1
#: about a month. Older arrays and swings are far from price, and reading all of them at every F close is slow.
CONTEXT_CANDLES = 600


@dataclass(frozen=True)
class Variant:
    leg_end: str = "CISD"             # MA-D5: CISD (the lowest low to the displacement) or SWING (on to a swing low)
    entry: float = 0.705              # MA-D6
    ote: Tuple[float, float] = (0.62, 0.79)
    displacement_body: float = 1.5    # MA-D4, in E average ranges
    cisd: str = "RUN"                 # MA-D4: RUN, a close below the open of the up-close run into C2's high, any
                                      # time after; NEXT, the engine's CISDDetector (the very next candle breaks it)
    stop_buffer: float = 0.1          # Requirement 14.1, in E average ranges
    horizon_f_candles: int = 1        # MA-D11: to the close of the F candle the entry filled in
    poi_mode: str = "MODEL"           # MODEL, or the baselines CRT (no F) and RANDOM_POI (Requirement 16.3)
    seed: int = 0
    # Requirement 18: volatility and time
    size_basis: str = "ROLLING"       # MA-D14: E's sizes against its last 20 candles (ROLLING), or against its candles at
                                      # the same time of day over the previous 20 trading days (SEASONAL)
    phases: Optional[Tuple[str, ...]] = None    # MA-D13: the phases of the day C2 may open in; None: any
    max_adr_used: Optional[float] = None        # MA-D15: the day's range by C2's close, in ADR (RANGE_SPENT beyond)
    max_size_adr: Optional[float] = None        # MA-D16: C2's extreme to C1's opposite extreme, in ADR (TOO_LARGE)
    room: bool = False                          # MA-D17: C1's opposite extreme within one ADR of the day's extreme
                                                # on C2's side (NO_ROOM otherwise)

    def name(self) -> str:
        extra = "+time" if self.phases else ""
        if self.size_basis == "SEASONAL" or self.max_adr_used or self.max_size_adr or self.room:
            extra += "+vol"
        return f"{self.poi_mode.lower()}/{self.leg_end.lower()}/{self.cisd.lower()}{extra}"


def _wall(t: int) -> datetime:
    return datetime.fromtimestamp(int(t), tz=timezone.utc)


#: MA-D13: the phases of the trading day, New York wall hours.
DAY_PHASES = (("ASIA", 20.0, 24.0), ("MIDNIGHT", 0.0, 2.0), ("LONDON", 2.0, 5.0), ("PRE_NY", 5.0, 7.0),
              ("NY_AM", 7.0, 10.0), ("NY_MID", 10.0, 13.5), ("NY_PM", 13.5, 16.0), ("CLOSE", 16.0, 20.0))
_WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
#: The early part of the cycle: 20:00 to 07:00 New York for intraday C candles; Monday to Wednesday for D1; weeks
#: 1-2 of the month for W1 (the record of 2026-10-15: Model A's context helps there and hurts later).
EARLY = ("ASIA", "MIDNIGHT", "LONDON", "PRE_NY", "MON", "TUE", "WED", "WEEK1", "WEEK2")


def day_phase(tf: str, wall_open: int) -> str:
    """The phase of its cycle a C candle opening at ``wall_open`` belongs to: the phase of the day for intraday
    candles, the trading date's weekday for D1, the week of the month for W1."""
    if _SIZE.get(tf, 0) >= _SIZE["W1"]:
        return f"WEEK{min(5, (_wall(int(wall_open) + 7 * 3600).day - 1) // 7 + 1)}"
    if _SIZE.get(tf, 0) >= _SIZE["D1"]:
        return _WEEKDAYS[_wall(int(wall_open) + 7 * 3600).weekday()]
    hour = (int(wall_open) % 86400) / 3600.0
    return next(name for name, a, b in DAY_PHASES if a <= hour < b)


#: Model A with volatility and time (Requirement 18): the early phases, sizes against the same hour, 70% of the ADR,
#: setups up to 0.35 ADR, C1's opposite extreme within reach.
MODEL_A_VT = Variant(size_basis="SEASONAL", phases=EARLY, max_adr_used=0.7, max_size_adr=0.35, room=True)


def in_time_window(tf: str, wall_open: int) -> bool:
    """MA-D9, the trader's windows, for a C2 candle opening at ``wall_open`` (New York wall seconds)."""
    t = _wall(wall_open)
    if tf == "H1":
        return t.hour in (2, 3, 7, 8)
    if tf in ("M15", "M30"):
        return t.minute in (45, 0)
    if tf == "H4":
        return t.hour in (1, 5, 9)
    if tf == "D1":
        return _wall(int(wall_open) + 7 * 3600).weekday() <= 2          # its trading date: Monday to Wednesday
    if tf == "W1":
        return _wall(int(wall_open) + 7 * 3600).day <= 14               # weeks 1-2 of the month
    return False


@dataclass
class _FContext:
    """F as its closed candles leave it: the dealing range's anchors, the POI candidates, the average range."""
    base: Optional[DealingRange]
    candidates: List[Candidate]
    favg: float


@dataclass
class _Instance:
    c1: Tuple[int, float, float, float, float]          # (open, o, h, l, c), in the reader's (short) prices
    poi: POI
    favg: float
    zone_position: float
    anchors: Tuple[int, int]
    f_range: Tuple[float, float] = (np.nan, np.nan)      # F's dealing range at FRAMED (low, high)
    events: List[Tuple[str, int, str]] = field(default_factory=list)
    stage: str = "C2"                                    # C2, C3, TRADE
    c2_open: Optional[int] = None
    c2_high: float = -np.inf
    armed: bool = False
    manipulated: bool = False
    leg_start: int = -1
    leg_low: float = np.inf
    leg_low_at: int = -1
    cisd: bool = False
    cisd_level: float = np.inf                           # the open of the up-close run into C2's high
    max_body: float = 0.0
    fvg: bool = False
    displaced: bool = False
    e_avg: float = np.nan                                # E's average range at the displacement
    rejected: bool = False
    range_low: Optional[float] = None
    order: Optional[dict] = None
    in_ote: bool = False
    entered: bool = False
    fill: float = np.nan
    horizon_end: Optional[int] = None
    hits: Dict[str, int] = field(default_factory=dict)
    exit_price: Optional[float] = None
    best: float = np.nan
    ended: Optional[Tuple[str, int, str]] = None
    inducement: Optional[str] = None
    time_sync: Optional[bool] = None
    phase: Optional[str] = None
    adr: float = np.nan                                  # the day's ADR (the previous 20 trading days' mean range)
    adr_used: float = np.nan                             # the day's range by C2's close, in ADR
    size_adr: float = np.nan                             # C2's extreme to C1's opposite extreme, in ADR
    target_reach: float = np.nan                         # the day's extreme on C2's side to C1's opposite extreme, in ADR

    def event(self, state: str, t: int, reason: str = "") -> None:
        self.events.append((state, int(t), reason))

    def end(self, state: str, t: int, reason: str = "") -> None:
        self.ended = (state, int(t), reason)
        self.event(state, t, reason)


class ModelAReader:
    def __init__(self, frames: FrameSet, wall, o, h, l, c, side: str = "SHORT", variant: Variant = Variant(),
                 extra_pois: Optional[Callable[[int, str], List[POI]]] = None) -> None:
        from algo_research.replay.timeframes import aggregate, bucket, seconds_of
        self.frames, self.side, self.variant = frames, side.upper(), variant
        self.sign = 1.0 if self.side == "SHORT" else -1.0
        wall = np.asarray(wall, dtype=np.int64)
        o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
        if self.side == "LONG":
            o, h, l, c = mirror(o, h, l, c)
        self.higher = [tf for tf in ("D1", "W1", "MN1") if _SIZE[tf] > _SIZE[frames.f]]
        self.bars = {}
        for tf in {frames.f, frames.c, frames.e, *self.higher}:
            b = aggregate(wall, o, h, l, c, tf)
            self.bars[tf] = (b["time"].to_numpy(np.int64),) + tuple(b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.seconds, self.bucket = seconds_of, bucket
        self.extra_pois = extra_pois                    # nesting (Requirement 15): (t, side) -> a higher reader's POIs
        self._rng = np.random.default_rng(variant.seed)

    # ── the run ──────────────────────────────────────────────────────────
    def run(self, start: int, end: int) -> List[dict]:
        fs = self.frames
        et, eo, eh, el, ec = self.bars[fs.e]
        ct, co, ch, cl, cc = self.bars[fs.c]
        ft, fo, fh, fl, fc = self.bars[fs.f]
        c_sec, e_sec = self.seconds(fs.c), self.seconds(fs.e)
        e_avg = self._sizes(et, eh, el, e_sec)
        day_of = (et - _DAY_OPEN) // _DAY
        adr_of = self._adr(day_of, eh, el)
        self._day = [None, -np.inf, np.inf]                  # the trading day, its high and low so far (closed E bars)
        self._adr_of = adr_of
        c_of, f_of = self.bucket(et, fs.c), self.bucket(et, fs.f)
        c_index = {int(t): i for i, t in enumerate(ct)}
        f_index = {int(t): i for i, t in enumerate(ft)}
        first = int(np.searchsorted(et, start, side="left"))
        last = int(np.searchsorted(et, end, side="left"))
        # warm up from the opening of the largest frame's candle that holds the start, so forming extremes are whole
        top = (self.higher or [fs.f])[-1]
        warm = int(np.searchsorted(et, self.bucket(et[first:first + 1], top)[0], side="left")) if first < len(et) else first
        higher_of = {tf: self.bucket(et, tf) for tf in self.higher}

        out: List[dict] = []
        inst: Optional[_Instance] = None
        ctx: Optional[_FContext] = None
        forming_hi, forming_lo = -np.inf, np.inf
        higher_hi = {tf: -np.inf for tf in self.higher}
        cur_c = cur_f = None
        cur_higher = {tf: None for tf in self.higher}
        for i in range(warm, last):
            cb, fb, live = int(c_of[i]), int(f_of[i]), i >= first
            if cur_f is None:
                ctx = self._context(f_index.get(fb, 0), cur_higher, higher_hi, et[i])
            if cur_c is not None and cb != cur_c:
                k = c_index[cur_c]
                if inst is not None:
                    self._c_closed(inst, k, ct, cc, c_sec)
                    if inst.ended is not None:
                        out.append(self._export(inst)); inst = None
                if fb != cur_f:                              # F closed too: a new context
                    ctx = self._context(f_index[cur_f] + 1, cur_higher, higher_hi, et[i])
                    forming_hi, forming_lo = -np.inf, np.inf
                if inst is None and live:
                    inst = self._frame(k, ct, co, ch, cl, cc, c_sec, ctx, forming_hi, forming_lo)
            for tf in self.higher:
                hb = int(higher_of[tf][i])
                if hb != cur_higher[tf]:
                    cur_higher[tf], higher_hi[tf] = hb, -np.inf
            cur_c, cur_f = cb, fb
            if inst is not None and live:
                self._e_bar(inst, i, et, eo, eh, el, ec, e_sec, e_avg, fb)
                if inst.ended is not None:
                    out.append(self._export(inst)); inst = None
            forming_hi, forming_lo = max(forming_hi, eh[i]), min(forming_lo, el[i])
            for tf in self.higher:
                higher_hi[tf] = max(higher_hi[tf], eh[i])
            d = int(day_of[i])
            if d != self._day[0]:
                self._day = [d, -np.inf, np.inf]
            self._day[1], self._day[2] = max(self._day[1], eh[i]), min(self._day[2], el[i])
        if inst is not None:
            inst.end("UNFINISHED", int(et[last - 1]) + e_sec if last else int(end), "the data ended")
            out.append(self._export(inst))
        return out

    # ── volatility: E's sizes and the day's ADR ─────────────────────────
    def _sizes(self, et, eh, el, e_sec) -> np.ndarray:
        """E's average range for each E candle (MA-D8, MA-D14): over its last 20 candles, or, SEASONAL, over its
        candles in the same slot of the day (15 minutes, or the candle itself when longer) on the previous 20
        trading days. The seasonal size falls back to the rolling one where the history is short."""
        rolling = rolling_average_range(eh, el)
        if self.variant.size_basis != "SEASONAL":
            return rolling
        import pandas as pd
        day = (et - _DAY_OPEN) // _DAY
        slot = ((et - _DAY_OPEN) % _DAY) // max(900, e_sec)
        frame = pd.DataFrame({"day": day, "slot": slot, "r": np.asarray(eh) - np.asarray(el)})
        table = frame.groupby(["day", "slot"])["r"].mean().unstack("slot").sort_index()
        normal = table.shift(1).rolling(20, min_periods=5).mean()            # the 20 trading days before, per slot
        seasonal = normal.stack().reindex(pd.MultiIndex.from_arrays([day, slot])).to_numpy()
        return np.where(np.isfinite(seasonal), seasonal, rolling)

    @staticmethod
    def _adr(day_of, eh, el) -> dict:
        """Each trading day's ADR: the mean range of the 20 trading days before it (at least 10)."""
        import pandas as pd
        frame = pd.DataFrame({"day": day_of, "h": eh, "l": el}).groupby("day").agg(h=("h", "max"), l=("l", "min"))
        adr = (frame["h"] - frame["l"]).shift(1).rolling(20, min_periods=10).mean()
        return {int(k): float(v) for k, v in adr.items()}

    # ── F: the context ───────────────────────────────────────────────────
    def _context(self, n: int, cur_higher, higher_hi, now) -> _FContext:
        """F as its first ``n`` (closed) candles leave it."""
        ft, fo, fh, fl, fc = self.bars[self.frames.f]
        if n < 5:
            return _FContext(None, [], np.nan)
        favg = average_range(fh, fl, n)
        lo = max(0, n - CONTEXT_CANDLES)
        levels = [(f"previous {self.frames.f} high", float(fh[n - 1]))]
        for tf in self.higher:                               # the frames above: their previous candle's high
            bt = self.bars[tf][0]
            hb = cur_higher.get(tf)
            idx = int(np.searchsorted(bt, hb if hb is not None else now, side="left"))
            if idx >= 1:
                levels.append((_PREVIOUS[tf], float(self.bars[tf][2][idx - 1])))
        cands = bearish_candidates(fo[lo:n], fh[lo:n], fl[lo:n], fc[lo:n], n - lo, favg, levels, self.frames.f)
        return _FContext(dealing_range(fh[lo:n], fl[lo:n], n - lo), cands, favg)

    def _frame(self, k, ct, co, ch, cl, cc, c_sec, ctx, forming_hi, forming_lo) -> Optional[_Instance]:
        """A C candle has closed: C1 of a new instance, if price is in F's premium with a POI above."""
        c1 = (int(ct[k]), float(co[k]), float(ch[k]), float(cl[k]), float(cc[k]))
        t = int(ct[k]) + c_sec
        phase = day_phase(self.frames.c, t)                  # C2 opens as C1 closes
        if self.variant.phases is not None and phase not in self.variant.phases:
            return None
        if self.variant.poi_mode == "CRT":                   # the baseline: no F; C1's high is the only "POI"
            inst = _Instance(c1, POI("C1_HIGH", c1[2], np.inf, -1, "C1's high"), ctx.favg if ctx else np.nan,
                             np.nan, (-1, -1))
            inst.phase = phase
            inst.armed = True
            inst.event("FRAMED", t, "CRT baseline: no context")
            inst.event("ARMED", t, "")
            return inst
        if ctx is None or ctx.base is None:
            return None
        rng = DealingRange(min(ctx.base.low, forming_lo), max(ctx.base.high, forming_hi), *ctx.base.anchors)
        price = c1[4]
        if rng.zone(price) != "PREMIUM":
            return None
        pois = select_pois(ctx.candidates, rng, price, forming_hi)
        if self.variant.poi_mode == "RANDOM_POI":
            moved = []
            for p in pois:
                d = self._rng.uniform(0.5, 2.0) * ctx.favg * self._rng.choice((-1.0, 1.0))
                moved.append(POI(p.kind, p.low + d, p.high + d, p.formed, p.label + " (moved)"))
            pois = sorted((p for p in moved if p.high > price), key=lambda p: (p.low, p.high))
        if self.extra_pois is not None:
            pois = sorted([*pois, *self.extra_pois(t, self.side)], key=lambda p: (p.low, p.high))
        reachable = [p for p in pois if p.high > c1[2]]
        if not reachable:
            return None
        poi = min(reachable, key=lambda p: (max(p.low, c1[2]), p.high))
        inst = _Instance(c1, poi, ctx.favg, rng.position(price), rng.anchors, (rng.low, rng.high))
        inst.phase = phase
        inst.event("FRAMED", t, f"{rng.reason()}, price at {rng.position(price):.0%}; POI {poi.reason()}")
        if c1[2] >= poi.low - ctx.favg:
            inst.armed = True
            inst.event("ARMED", t, "C1 within one F average range of the POI")
        return inst

    # ── C: C2's close and C3's ───────────────────────────────────────────
    def _c_closed(self, inst: _Instance, k, ct, cc, c_sec) -> None:
        t = int(ct[k]) + c_sec
        if inst.stage == "C2":
            close, c1_high = float(cc[k]), inst.c1[2]
            if not inst.manipulated:
                inst.end("NO_MANIPULATION", t, "C2 closed without running C1's high into the POI")
            elif close > inst.poi.high:
                inst.end("POI_FAILED", t, f"C2 closed {close:.5g} through the POI")
            elif close > c1_high:
                inst.end("NO_REJECTION", t, f"C2 closed {close:.5g} above C1's high {c1_high:.5g}")
            elif self._spent(inst, t):
                pass                                             # ended RANGE_SPENT, TOO_LARGE or NO_ROOM
            else:
                inst.rejected = True
                inst.event("REJECTED", t, f"C2 closed {close:.5g} back under C1's high {c1_high:.5g}")
                inst.stage = "C3"
                self._order(inst)
        elif inst.stage == "C3":
            if inst.entered:
                inst.stage = "TRADE"
            else:
                inst.end("EXPIRED", t, "C3 closed without a fill" if inst.displaced else "C3 closed without displacement")

    def _spent(self, inst: _Instance, t: int) -> bool:
        """Requirement 18 at C2's close: the day's range used, the setup's size and C1's opposite extreme's reach,
        in ADR, recorded; with the variant's limits, the first one exceeded ends the instance."""
        v, (day, hi, lo) = self.variant, self._day
        adr = self._adr_of.get(day, np.nan) if day is not None else np.nan
        inst.adr = adr
        if not (np.isfinite(adr) and adr > 0):
            return False                                     # too little history: recorded as unknown, never gated
        inst.adr_used = (hi - lo) / adr
        inst.size_adr = (inst.c2_high - inst.c1[3]) / adr
        inst.target_reach = (max(hi, inst.c2_high) - inst.c1[3]) / adr
        if v.max_adr_used is not None and inst.adr_used > v.max_adr_used:
            inst.end("RANGE_SPENT", t, f"the day had used {inst.adr_used:.0%} of its ADR by C2's close")
        elif v.max_size_adr is not None and inst.size_adr > v.max_size_adr:
            inst.end("TOO_LARGE", t, f"the setup spans {inst.size_adr:.2f} ADR")
        elif v.room and inst.target_reach > 1.0:
            inst.end("NO_ROOM", t, f"C1's opposite extreme is {inst.target_reach:.2f} ADR from the day's extreme")
        return inst.ended is not None

    # ── E: inside the candles ────────────────────────────────────────────
    def _e_bar(self, inst: _Instance, i, et, eo, eh, el, ec, e_sec, e_avg, fb) -> None:
        t_end, v = int(et[i]) + e_sec, self.variant
        if inst.entered:
            self._manage(inst, i, et, eh, el, ec, e_sec)
            return
        if inst.stage == "C2":
            if inst.c2_open is None:
                inst.c2_open = int(et[i])
            if not inst.armed and eh[i] >= inst.poi.low - inst.favg:
                inst.armed = True
                inst.event("ARMED", t_end, "price within one F average range of the POI")
            if eh[i] > inst.c2_high:                         # a new high in C2: the leg starts again from it
                inst.c2_high = float(eh[i])
                inst.leg_start, inst.leg_low, inst.leg_low_at = i, float(el[i]), i
                inst.cisd, inst.max_body, inst.fvg = False, 0.0, False
                r = i if ec[i] > eo[i] else i - 1            # the up-close run that made the high
                if r >= 0 and ec[r] > eo[r]:
                    while r > 0 and ec[r - 1] > eo[r - 1]:
                        r -= 1
                    inst.cisd_level = float(eo[r])
                else:
                    inst.cisd_level = float(eo[i])
                if inst.displaced:                           # an earlier displacement wasn't the one
                    inst.displaced, inst.range_low = False, None
                    inst.events = [e for e in inst.events if e[0] != "DISPLACED"]
                if not inst.manipulated and inst.c2_high > inst.c1[2] and inst.c2_high >= inst.poi.low:
                    inst.manipulated = True
                    inst.time_sync = in_time_window(self.frames.c, inst.c2_open)
                    inst.inducement = self._inducement(inst, i, et, eh, el, e_avg)
                    inst.event("MANIPULATED", t_end, f"C2 ran C1's high {inst.c1[2]:.5g} to {inst.c2_high:.5g}, into the "
                               f"POI{'; in the time window' if inst.time_sync else ''}")
                return
        elif inst.order is None and eh[i] > inst.c2_high:   # C3: a higher high before the order is live
            inst.end("RETRACE_INVALID", t_end, f"price took C2's high {inst.c2_high:.5g} before the entry")
            return
        if not inst.manipulated:
            return
        if not inst.displaced:                               # the leg down from C2's high
            inst.cisd = inst.cisd or (ec[i] < inst.cisd_level if v.cisd == "RUN" else bearish_cisd(eo, eh, el, ec, i))
            inst.max_body = max(inst.max_body, float(eo[i] - ec[i]))
            inst.fvg = inst.fvg or (i - 2 >= inst.leg_start and el[i - 2] > eh[i])
            if el[i] < inst.leg_low:
                inst.leg_low, inst.leg_low_at = float(el[i]), i
            avg = e_avg[i]
            if inst.cisd and inst.fvg and np.isfinite(avg) and inst.max_body >= v.displacement_body * avg:
                inst.displaced, inst.e_avg = True, float(avg)
                if v.leg_end == "CISD":
                    inst.range_low = inst.leg_low
                inst.event("DISPLACED", t_end, f"CISD, a body of {inst.max_body / avg:.1f} E average ranges, an FVG")
                self._order(inst)
            return
        if inst.range_low is None:                           # SWING: the leg runs on to the first confirmed swing low
            if el[i] < inst.leg_low:
                inst.leg_low, inst.leg_low_at = float(el[i]), i
            if i >= inst.leg_low_at + 2:                     # two candles closed after the low without undercutting it
                inst.range_low = inst.leg_low
                self._order(inst)
            return
        if inst.order is not None:
            o = inst.order
            if eh[i] >= o["ote_low"] and not inst.in_ote:
                inst.in_ote = True
                inst.event("IN_OTE", t_end, f"price in the OTE {o['ote_low']:.5g}-{o['ote_high']:.5g}")
            if eh[i] >= o["entry"]:
                inst.entered = True
                inst.fill = max(o["entry"], float(eo[i]))       # a gap above the entry fills at the open
                inst.best = inst.fill
                inst.horizon_end = int(fb) + v.horizon_f_candles * self.seconds(self.frames.f)
                inst.event("ENTERED", t_end, f"sell limit {o['entry']:.5g} filled at {inst.fill:.5g}")
                self._manage(inst, i, et, eh, el, ec, e_sec, fill_bar=True)
                return
        if el[i] < inst.range_low and not inst.in_ote:
            inst.end("MISSED", t_end, f"price broke the new range's low {inst.range_low:.5g} before the OTE")

    def _order(self, inst: _Instance) -> None:
        """The order lives once C2 has rejected and the new range is fixed (Requirement 14.1)."""
        if inst.order is not None or not inst.rejected or not inst.displaced or inst.range_low is None:
            return
        v, hi, lo = self.variant, inst.c2_high, inst.range_low
        size = hi - lo
        if size <= 0:
            return
        entry = lo + v.entry * size
        inst.order = {"entry": entry, "stop": hi + v.stop_buffer * (inst.e_avg if np.isfinite(inst.e_avg) else 0.0),
                      "ote_low": lo + v.ote[0] * size, "ote_high": lo + v.ote[1] * size,
                      "tp1": inst.c1[3] if inst.c1[3] < entry else lo - size,
                      "sd1": lo - size, "sd2": lo - 2 * size, "sd25": lo - 2.5 * size, "high": hi, "low": lo}

    def _manage(self, inst: _Instance, i, et, eh, el, ec, e_sec, fill_bar: bool = False) -> None:
        """After the fill: the stop, TP1 and the SD levels, first touch wins; within a bar the stop goes first."""
        o, t_end = inst.order, int(et[i]) + e_sec
        if not fill_bar and inst.horizon_end is not None and int(et[i]) >= inst.horizon_end:
            inst.exit_price = float(ec[i - 1])
            inst.end("HORIZON", int(et[i]), f"the F candle closed; out at {inst.exit_price:.5g}")
            return
        if eh[i] >= o["stop"]:
            inst.end("STOPPED", t_end, f"price reached the stop {o['stop']:.5g}")
            return
        inst.best = min(inst.best, float(el[i]))
        for key, name in (("tp1", "TP1"), ("sd1", "SD_1"), ("sd2", "SD_2"), ("sd25", "SD_2.5")):
            if key not in inst.hits and el[i] <= o[key]:
                inst.hits[key] = t_end
                inst.event(name, t_end, f"price reached {o[key]:.5g}")
        if "sd25" in inst.hits:
            inst.end("TARGETS_DONE", t_end, "-2.5 SD reached")

    def _inducement(self, inst: _Instance, i, et, eh, el, e_avg) -> Optional[str]:
        """MA-D3, on the E candles from C1's open up to the manipulation, under the POI."""
        lo = int(np.searchsorted(et, inst.c1[0], side="left"))
        avg = e_avg[i]
        if not np.isfinite(avg) or i - lo < 3:
            return None
        if equal_highs(eh, lo, i, 0.1 * avg, inst.poi.low) is not None:
            return "EQUAL_HIGHS"
        if tight_range(eh, el, lo, i, avg):
            return "TIGHT_RANGE"
        return None

    # ── out ──────────────────────────────────────────────────────────────
    def _export(self, inst: _Instance) -> dict:
        s, o = self.sign, inst.order or {}
        p = lambda x: None if x is None or not np.isfinite(x) else float(s * x)  # noqa: E731
        risk = (o["stop"] - inst.fill) if inst.entered else None
        r = lambda price: None if not risk or price is None else float((inst.fill - price) / risk)  # noqa: E731
        end = inst.ended[0] if inst.ended else None
        exit_r = r(inst.exit_price) if inst.exit_price is not None else None

        def result(target: str) -> Optional[float]:     # holding to ``target``: hit, stopped, or out at the horizon
            if not inst.entered:
                return None
            if target in inst.hits:
                return r(o[target])
            return -1.0 if end == "STOPPED" else exit_r
        states: Dict[str, int] = {}
        for name, t, _ in inst.events:
            states.setdefault(name, t)
        poi_lo, poi_hi = inst.poi.low, inst.poi.high          # near and far edge: mirrored prices flip them back
        return {
            "set": self.frames.name, "f": self.frames.f, "c": self.frames.c, "e": self.frames.e, "side": self.side,
            "variant": self.variant.name(), "leg_end": self.variant.leg_end, "poi_mode": self.variant.poi_mode,
            "c1_open": inst.c1[0], "c1_extreme": p(inst.c1[2]), "c1_opposite": p(inst.c1[3]),
            "poi_kind": inst.poi.kind, "poi_label": inst.poi.label, "poi_near": p(poi_lo), "poi_far": p(poi_hi),
            "zone_position": inst.zone_position, "favg": inst.favg, "states": states, "events": list(inst.events),
            "f_range": sorted(p(x) for x in inst.f_range) if np.all(np.isfinite(inst.f_range)) else None,
            "end": end, "end_at": inst.ended[1] if inst.ended else None, "end_reason": inst.ended[2] if inst.ended else "",
            "time_sync": inst.time_sync, "inducement": inst.inducement, "phase": inst.phase,
            "adr": float(inst.adr) if np.isfinite(inst.adr) else None,
            "adr_used": float(inst.adr_used) if np.isfinite(inst.adr_used) else None,
            "size_adr": float(inst.size_adr) if np.isfinite(inst.size_adr) else None,
            "target_reach": float(inst.target_reach) if np.isfinite(inst.target_reach) else None,
            "c2_extreme": p(inst.c2_high) if inst.manipulated else None,
            "range_end": p(o.get("low")), "entry": p(o.get("entry")), "stop": p(o.get("stop")), "tp1": p(o.get("tp1")),
            "sd1": p(o.get("sd1")), "sd2": p(o.get("sd2")), "sd25": p(o.get("sd25")),
            "ote_near": p(o.get("ote_low")), "ote_far": p(o.get("ote_high")),
            "fill": p(inst.fill) if inst.entered else None, "hits": dict(inst.hits),
            "mfe_r": r(inst.best) if inst.entered else None, "r_tp1": result("tp1"), "r_sd2": result("sd2"),
        }
