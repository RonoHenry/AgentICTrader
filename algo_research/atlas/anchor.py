"""The Time Anchor atlas (2026-11-21): every three-candle swing read the way the trader reads one, through the frame
above it (valuation, in time) and scored against a random walk. EXPLORATION, on data the research has already read.

The trader's frame, in their words:
- "Price cannot reverse or retrace without a swing point, and a swing point can only be formed by three candles."
- The Time Anchor: "whenever I am looking at the current time frame, I am putting to consideration the higher time
  frame above it and the one below it": 3M-MN1-W1, MN1-W1-D1, W1-D1-H4, D1-H4-H1, H4-H1-M30, M30-M15-M3.
- Valuation: premium and discount, market structure, price against the key opens; the levels that matter are opens and
  closes, the mean threshold of HTF order blocks, the CE of FVGs and the CE of HTF wicks.
- "All this trace back to how candles form in time (PO3). Higher time frames will hold more weight."

What is read, for a swing low (a high is the same on the prices turned upside down):
- **The swing** on the current frame: C2's low below both neighbours' lows; known at C3's close. Its extreme's M1 bar
  dates it.
- **The anchor** is the higher frame's candle the extreme printed in. At the extreme:
  - ``below_open``: the extreme is below the anchor's open (the manipulation side of a bullish candle);
  - ``phase``: how far through the anchor's time the extreme printed, 0 to 1;
  - ``pd``: the extreme's place in the previous anchor candle's range (0 its low, 1 its high, below 0 under its low);
  - ``stack``: the anchor frame's supporting levels within ``TOL`` average current-frame candles of the extreme,
    all known before it: the anchor's open, the previous anchor's open and close, bullish OB and breaker mean
    thresholds (the trader's CISD-run bodies, ``liquidity_engine.context.blocks``), the CE of bullish FVGs and of
    bearish FVGs closed through upward (IFVGs) not yet closed through, and the CE of large lower wicks
    (wick at least 30% of the range) not yet traded through. Levels older than ``LOOKBACK`` anchor candles are left out.
    ``stack2`` counts the same one frame further up.
  - ``depth``: of the opens above the current frame (M30 up to the quarter), how many in a row, from the nearest up,
    the extreme is below; ``weighted``: the same with each frame weighted by its rank (higher weighs more).
- **The outcomes**, settled strictly on M1 from the first bar at or after the swing is known (a touch is neither;
  one bar doing both is failed), with the geometry of a driftless random walk from C3's close,
  (close - extreme) / (objective - extreme):
  - ``anchor``: the previous anchor candle's high (the opposite side of the higher frame's range);
  - ``leg``: the origin of the leg into the swing (the highest high since the current frame's last swing high);
  - ``crt``: C1's high.
  An objective traded through between the extreme and C3's close is held at once and left out of the rates.
  - ``po3``: the anchor candle closes above its open; its random walk, Phi((close - open) / (sigma sqrt(tau))), with
    tau the share of the anchor's time left at C3's close and sigma its average range over 1.596.

**The trigger** (added 2026-11-21, the trader's execution): the swing's C2 taking C1 is the turtle soup; the trigger is
the lower frame's CISD off the extreme: a run of down-closing lower candles (``blocks.runs``) that includes the
extreme, closed through upward, the close by C3's close (so earlier than the swing is known). No CISD by then, no
trade. Entries, the stop under the extreme, priced on M1 from the trigger's close:
- ``t1``: at market at the CISD close;
- ``t2``: a limit at the 50% of the new range (the extreme to the CISD candle's high), missed when the objective
  prints first; the fill bar can stop it, never take profit.
Each with its random walk from its own entry, its reward:risk, and its cost in R: on MT5 markets 1.5 median spreads
(the spread, and half of it as stop slippage), on Binance 0.1% of the price a side and 1 bp.

    .venv\\Scripts\\python.exe -m algo_research.atlas.anchor build [--markets US30,XAUUSD]
"""
from __future__ import annotations

import argparse
import dataclasses
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from liquidity_engine.context.blocks import BULL, delivery_blocks, runs
from thesis_engine.clock import clean, frames as clock_frames
from thesis_engine.settings import V1

REPO = Path(__file__).resolve().parents[2]
SNAP = REPO / "data" / "research" / "snapshots"
OUT = REPO / "data" / "research" / "atlas" / "anchor"

#: The trader's Time Anchor: the current frame -> (the frame above, the frame below).
TRIADS = {"M15": ("M30", "M3"), "H1": ("H4", "M30"), "H4": ("D1", "H1"), "D1": ("W1", "H4"), "W1": ("MN1", "D1"),
          "MN1": ("Q", "W1")}
CURRENT = ("M15", "H1", "H4", "D1", "W1")
#: The opens read upward for the depth, nearest first.
LADDER = ("M15", "M30", "H1", "H4", "D1", "W1", "MN1", "Q")
UP2 = {"M30": "H1", "H4": "D1", "D1": "W1", "W1": "MN1", "MN1": "Q", "Q": None}
TOL = 0.25            # a level "at" the extreme: within this many average current-frame candles
LOOKBACK = 60         # anchor candles a level stays a candidate
WICK_SHARE = 0.3
ATR_N = 20
SETTINGS = dataclasses.replace(V1, exec_frames=("M30", "M15", "M3"))

FOCUS = ("DXY", "XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")
FOCUS_SNAPS = ("mt5-m1-develop", "mt5-m1-test", "focus-2025-2026h1", "mt5-m1-2026-11")
ASSETS = ("USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "EURCAD", "GBPCAD")
CRYPTO = ("BTCUSD", "ETHUSD", "XRPUSD")
GROUP = {**{m: "focus" for m in FOCUS}, **{m: "fx" for m in ASSETS}, **{m: "crypto" for m in CRYPTO}}


@dataclass
class F:
    """A frame's candles as arrays (UTC ns opens and closes), possibly turned upside down."""
    t: np.ndarray
    end: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray

    def mirror(self) -> "F":
        return F(self.t, self.end, -self.o, -self.l, -self.h, -self.c)

    def at(self, t_ns: np.ndarray) -> np.ndarray:
        """The candle each time is in (-1: none)."""
        i = np.searchsorted(self.t, t_ns, "right") - 1
        ok = (i >= 0) & (t_ns < self.end[np.clip(i, 0, len(self.t) - 1)])
        return np.where(ok, i, -1)


# ── data ─────────────────────────────────────────────────────────────────────
def load_m1(market: str) -> pd.DataFrame:
    """The market's read M1, 2021 to 2026, one bar per minute."""
    if market in FOCUS:
        paths = [SNAP / s / f"{market}_M1.parquet" for s in FOCUS_SNAPS]
    elif market in ASSETS:
        paths = [SNAP / "mt5-m1-assets" / f"{market}_M1.parquet"]
    else:
        paths = [SNAP / "binance-m1-crypto" / f"{market}_M1.parquet"]
    parts = []
    for p in paths:
        if p.exists():
            x = pd.read_parquet(p)
            parts.append(x[[c for c in ("time", "open", "high", "low", "close", "spread") if c in x]])
    m1 = pd.concat(parts, ignore_index=True)
    m1["time"] = pd.to_datetime(m1["time"], utc=True)
    if "spread" not in m1:
        m1["spread"] = 0.0
    return m1.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)


FEE, FEE_SLIP = 0.001, 0.0001           # Binance: a side, and stop slippage, of the price
SPREADS = 1.5                            # MT5: the spread and half of it as stop slippage
TRIG_LOOKBACK = 3                        # the CISD's run ends at most this many lower candles before the extreme's


def cost_of(market: str, m1: pd.DataFrame):
    """The round trip's cost in price at an entry price: (kind, value)."""
    if market in CRYPTO:
        return ("rate", 2 * FEE + FEE_SLIP)
    sp = m1["spread"].to_numpy(float)
    return ("price", SPREADS * float(np.median(sp[sp > 0])) if (sp > 0).any() else 0.0)


def _periods(d1: F, key: np.ndarray) -> F:
    """D1 candles grouped into months or quarters; the first (maybe partial) and the last (maybe forming) dropped."""
    df = pd.DataFrame({"k": key, "t": d1.t, "end": d1.end, "o": d1.o, "h": d1.h, "l": d1.l, "c": d1.c})
    g = df.groupby("k", sort=True).agg(t=("t", "first"), end=("end", "last"), o=("o", "first"), h=("h", "max"),
                                       l=("l", "min"), c=("c", "last")).iloc[1:-1]
    return F(*(g[x].to_numpy(dtype=np.int64 if x in ("t", "end") else float) for x in ("t", "end", "o", "h", "l", "c")))


def build_frames(m1: pd.DataFrame, market: str) -> dict[str, F]:
    bars, _ = clean(m1)
    fr = clock_frames(bars, market, SETTINGS)
    out = {tf: F(c.t.astype(np.int64), c.end.astype(np.int64), c.o, c.h, c.l, c.c) for tf, c in fr.items()}
    for tf in ("D1", "W1"):                                  # the first one may be partial
        f = out[tf]
        out[tf] = F(f.t[1:], f.end[1:], f.o[1:], f.h[1:], f.l[1:], f.c[1:])
    day = pd.to_datetime(out["D1"].end, utc=True).tz_convert("America/New_York")
    out["MN1"] = _periods(out["D1"], (day.year * 100 + day.month).to_numpy())
    out["Q"] = _periods(out["D1"], (day.year * 10 + day.quarter).to_numpy())
    return out


# ── first passage on M1 ──────────────────────────────────────────────────────
class Passage:
    """The first M1 bar at or after ``s`` whose value is above a level, by day blocks."""

    def __init__(self, x: np.ndarray, block: int = 1440) -> None:
        self.x, self.n, self.B = x, len(x), block
        nb = (self.n + block - 1) // block
        pad = np.full(nb * block, -np.inf)
        pad[: self.n] = x
        self.bmax = pad.reshape(nb, block).max(axis=1)

    def first_above(self, s: int, level: float) -> int:
        n, B = self.n, self.B
        if s >= n:
            return n
        e = min(n, (s // B + 1) * B)
        seg = self.x[s:e] > level
        if seg.any():
            return s + int(seg.argmax())
        b = e // B
        if b >= len(self.bmax):
            return n
        hit = self.bmax[b:] > level
        if not hit.any():
            return n
        bb = b + int(hit.argmax())
        return bb * B + int((self.x[bb * B: min(n, (bb + 1) * B)] > level).argmax())


# ── the anchor frame's supporting levels ─────────────────────────────────────
@dataclass
class Levels:
    value: np.ndarray
    since: np.ndarray        # UTC ns from which the level is known
    until: np.ndarray        # UTC ns from which it no longer counts
    kind: np.ndarray

    def near(self, t_ns: int, price: float, tol: float, horizon: int) -> np.ndarray:
        """Kinds of the levels live at ``t_ns`` within ``tol`` of ``price``."""
        a = np.searchsorted(self.since, t_ns - horizon, "left")
        b = np.searchsorted(self.since, t_ns, "right")
        v, u, k = self.value[a:b], self.until[a:b], self.kind[a:b]
        m = (u > t_ns) & (np.abs(v - price) <= tol)
        return k[m]


def _first_close_below(c: np.ndarray, start: int, level: float, stop: int) -> int:
    seg = c[start:stop] < level
    return start + int(seg.argmax()) if seg.any() else stop


def _first_low_below(l: np.ndarray, start: int, level: float, stop: int) -> int:
    seg = l[start:stop] < level
    return start + int(seg.argmax()) if seg.any() else stop


def anchor_levels(f: F) -> Levels:
    """The supporting levels of a frame (for swing lows; turn the frame upside down for highs)."""
    n = len(f.t)
    val, since, until, kind = [], [], [], []
    if n < 3:
        return Levels(*(np.array([], dtype=x) for x in (float, np.int64, np.int64, object)))
    cap = lambda i: f.end[min(n - 1, i + LOOKBACK)] if i + LOOKBACK < n else np.iinfo(np.int64).max  # noqa: E731
    for i in range(1, n):                                    # the anchor's open, the previous open and close
        for v, k in ((f.o[i], "open"), (f.o[i - 1], "open"), (f.c[i - 1], "close")):
            val.append(v), since.append(f.t[i]), until.append(f.end[i]), kind.append(k)
    for b in delivery_blocks(f.o, f.h, f.l, f.c):           # the trader's order blocks and breakers
        if b.direction != BULL:
            continue
        end = f.end[b.ended] if b.ended is not None else np.iinfo(np.int64).max
        val.append(b.mt), since.append(f.end[b.formed]), until.append(min(end, cap(b.formed)))
        kind.append("ob" if b.kind == "OB" else "breaker")
    for k in range(2, n):                                    # FVGs and IFVGs
        if f.l[k] > f.h[k - 2]:                              # bullish: live until a close below its bottom
            stop = min(n, k + 1 + LOOKBACK)
            j = _first_close_below(f.c, k + 1, f.h[k - 2], stop)
            val.append((f.h[k - 2] + f.l[k]) / 2), since.append(f.end[k])
            until.append(f.end[j] if j < n else np.iinfo(np.int64).max), kind.append("fvg")
        elif f.h[k] < f.l[k - 2]:                            # bearish: an IFVG once a close is above its top
            stop = min(n, k + 1 + LOOKBACK)
            seg = f.c[k + 1: stop] > f.l[k - 2]
            if seg.any():
                m = k + 1 + int(seg.argmax())
                j = _first_close_below(f.c, m + 1, f.h[k], min(n, m + 1 + LOOKBACK))
                val.append((f.l[k - 2] + f.h[k]) / 2), since.append(f.end[m])
                until.append(f.end[j] if j < n else np.iinfo(np.int64).max), kind.append("ifvg")
    body_lo = np.minimum(f.o, f.c)
    for j in range(n):                                       # large lower wicks, until traded through
        rng = f.h[j] - f.l[j]
        if rng > 0 and body_lo[j] - f.l[j] >= WICK_SHARE * rng:
            k = _first_low_below(f.l, j + 1, f.l[j], min(n, j + 1 + LOOKBACK))
            val.append((f.l[j] + body_lo[j]) / 2), since.append(f.end[j])
            until.append(f.end[k] if k < n else np.iinfo(np.int64).max), kind.append("wick")
    order = np.argsort(np.asarray(since, dtype=np.int64), kind="stable")
    return Levels(np.asarray(val, float)[order], np.asarray(since, np.int64)[order],
                  np.asarray(until, np.int64)[order], np.asarray(kind, object)[order])


# ── the swings ───────────────────────────────────────────────────────────────
def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _cisds(y: F) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every bullish CISD of a frame: (first, last, through), ordered by the close through."""
    r = runs(y.o, y.c, True)
    if not r:
        return (np.array([], np.int64),) * 3
    a = np.asarray(r, dtype=np.int64)
    return a[:, 0], a[:, 1], a[:, 2]


class _Ctx:
    """What a current frame reads: its anchor, the anchor's levels, the opens above, its swing highs and ranges."""

    def __init__(self, cur: str, fr: dict[str, F], levels: dict[str, Levels]) -> None:
        self.cur, self.f = cur, fr[cur]
        self.a_tf = TRIADS[cur][0]
        self.a = fr[self.a_tf]
        self.a2_tf = UP2.get(self.a_tf)
        self.fr, self.levels = fr, levels
        self.dur_a = int(np.median(self.a.end - self.a.t)) if len(self.a.t) else 0
        self.dur_a2 = int(np.median(fr[self.a2_tf].end - fr[self.a2_tf].t)) if self.a2_tf else 0
        self.atr = pd.Series(self.f.h - self.f.l).rolling(ATR_N).mean().shift(1).to_numpy()
        self.a_rng = pd.Series(self.a.h - self.a.l).rolling(ATR_N).mean().shift(1).to_numpy()
        self.above = list(LADDER[LADDER.index(cur) + 1:])
        n = len(self.f.t)
        sh = np.zeros(n, dtype=bool)
        sh[1:-1] = (self.f.h[1:-1] > self.f.h[:-2]) & (self.f.h[1:-1] > self.f.h[2:])
        self.sh_idx = np.flatnonzero(sh)

    def features(self, row: dict, k: int, ext: float, t_ext: int) -> bool:
        """The anchor's reading of an extreme in current candle ``k`` printed at ``t_ext``, into ``row``; the
        objectives into ``row['_objs']``. False when there is no anchor or range to read it against."""
        f, a = self.f, self.a
        if not np.isfinite(self.atr[k]):
            return False
        i = int(a.at(np.array([t_ext]))[0])
        if i < 1:
            return False
        tol = TOL * self.atr[k]
        row.update(anchor=self.a_tf, atr=self.atr[k], below_open=bool(ext < a.o[i]),
                   phase=(t_ext - a.t[i]) / max(1, a.end[i] - a.t[i]),
                   pd=(ext - a.l[i - 1]) / (a.h[i - 1] - a.l[i - 1]) if a.h[i - 1] > a.l[i - 1] else np.nan)
        kinds = self.levels[self.a_tf].near(t_ext, ext, tol, LOOKBACK * self.dur_a + self.dur_a)
        row["stack"] = int(len(kinds))
        row["stack_kinds"] = int(len(set(kinds)))
        for kk in ("open", "close", "ob", "breaker", "fvg", "ifvg", "wick"):
            row[f"lv_{kk}"] = int((kinds == kk).sum())
        row["stack2"] = (int(len(self.levels[self.a2_tf].near(t_ext, ext, tol, LOOKBACK * self.dur_a2 + self.dur_a2)))
                         if self.a2_tf else 0)
        below, w = [], []
        for r, tf in enumerate(self.above):                  # the opens above, nearest first
            g = self.fr[tf]
            j = int(g.at(np.array([t_ext]))[0])
            below.append(None if j < 0 else bool(ext < g.o[j]))
            w.append(r + 1)
        depth = 0
        for b in below:
            if b is not True:
                break
            depth += 1
        known_b = [(b, wt) for b, wt in zip(below, w) if b is not None]
        row["depth"] = depth
        row["weighted"] = (sum(wt for b, wt in known_b if b) / sum(wt for _, wt in known_b)) if known_b else np.nan
        j0 = self.sh_idx[self.sh_idx <= k - 2]
        row["_objs"] = {"anchor": float(a.h[i - 1]), "leg": float(f.h[j0[-1]:k].max()) if len(j0) else np.nan,
                        "crt": float(f.h[k - 1])}
        row["_i"] = i
        return True

    def po3(self, row: dict, price: float, at: int, last_t: int) -> None:
        a, i = self.a, row["_i"]
        tau = (a.end[i] - at) / max(1, a.end[i] - a.t[i])
        if tau > 0 and a.end[i] <= last_t and np.isfinite(self.a_rng[i]) and self.a_rng[i] > 0:
            row["po3"] = bool(a.c[i] > a.o[i])
            row["geo_po3"] = _phi((price - a.o[i]) / (self.a_rng[i] / 1.596 * math.sqrt(tau)))
            row["anchor_low"] = bool(a.l[i] >= row["extreme"] - 1e-9)


def side_rows(market: str, fr: dict[str, F], T: np.ndarray, H: np.ndarray, L: np.ndarray, side: str,
              cost: tuple = ("price", 0.0)) -> tuple[list[dict], list[dict]]:
    """Every swing low of every current frame, and every trigger (the lower frame's CISD off a low that has taken
    the previous current candle's low and is still the current candle's low), on prices already turned for
    ``side`` (``high``: upside down)."""
    up, down = Passage(H), Passage(-L)
    last_t = int(T[-1]) if len(T) else 0
    levels = {tf: anchor_levels(fr[tf]) for tf in ("M30", "H1", "H4", "D1", "W1", "MN1", "Q")}

    def price_cost(p: float) -> float:
        return cost[1] * abs(p) if cost[0] == "rate" else cost[1]

    swings, triggers = [], []
    for cur in CURRENT:
        ctx = _Ctx(cur, fr, levels)
        f = ctx.f
        n = len(f.t)
        # ── the swings, known at C3's close ──
        for k in range(2, n - 1):
            if not (f.l[k] < f.l[k - 1] and f.l[k] < f.l[k + 1]):
                continue
            ext = f.l[k]
            ia, ib = np.searchsorted(T, [f.t[k], f.end[k]])
            if ib <= ia:
                continue
            ie = ia + int(np.argmin(L[ia:ib]))
            t_ext, known = int(T[ie]), int(f.end[k + 1])
            s = int(np.searchsorted(T, known, "left"))
            if s >= len(T):
                continue
            close = float(f.c[k + 1])
            row = {"market": market, "group": GROUP.get(market, "?"), "side": side, "tf": cur, "t_ext": t_ext,
                   "known": known, "extreme": ext, "close": close}
            if not ctx.features(row, k, ext, t_ext):
                continue
            objs = row.pop("_objs")
            before = H[ie + 1: s].max() if s > ie + 1 else -np.inf
            fail = down.first_above(s, -ext)
            for name, obj in objs.items():
                if not np.isfinite(obj) or obj <= ext:
                    row[f"out_{name}"], row[f"geo_{name}"] = "none", np.nan
                    continue
                if before > obj or close >= obj:
                    row[f"out_{name}"], row[f"geo_{name}"] = "at_once", 1.0
                    continue
                hit = up.first_above(s, obj)
                row[f"out_{name}"] = ("held" if hit < fail else "failed") if min(hit, fail) < len(T) else "open"
                row[f"geo_{name}"] = float(np.clip((close - ext) / (obj - ext), 0, 1))
                row[f"rr_{name}"] = (obj - close) / max(close - ext, 1e-12)
            ctx.po3(row, close, known, last_t)
            row.pop("_i")
            swings.append(row)
        # ── the triggers, known at the lower frame's CISD close; the swing need not form ──
        y = fr[TRIADS[cur][1]]
        first, last, through = _cisds(y)
        seen = set()
        for fi, la, th in zip(first.tolist(), last.tolist(), through.tolist()):
            iy = fi + int(np.argmin(y.l[fi:th + 1]))
            if iy in seen or la < iy - TRIG_LOOKBACK:
                continue
            ext, t1, ce = float(y.l[iy]), int(y.end[th]), float(y.c[th])
            ia, ib = np.searchsorted(T, [y.t[iy], y.end[iy]])
            if ib <= ia or ce <= ext:
                continue
            t_ext = int(T[ia + int(np.argmin(L[ia:ib]))])
            k = int(f.at(np.array([t_ext]))[0])
            if k < 2 or k + 1 >= n or not ext < f.l[k - 1] or t1 > f.end[k + 1]:
                continue                                     # no turtle soup of C1, or too late to be C2's
            ka, s1 = (int(x) for x in np.searchsorted(T, [f.t[k], t1]))
            if s1 >= len(T) or L[ka:s1].min() < ext - 1e-12:
                continue                                     # not the current candle's low at the CISD close
            seen.add(iy)
            row = {"market": market, "group": GROUP.get(market, "?"), "side": side, "tf": cur,
                   "lower": TRIADS[cur][1], "t_ext": t_ext, "known": t1, "extreme": ext, "entry": ce}
            if not ctx.features(row, k, ext, t_ext):
                continue
            objs = row.pop("_objs")
            mid = min(ce, (ext + float(y.h[th])) / 2)
            row.update(mid=mid, risk_t1=ce - ext, risk_t2=mid - ext,
                       became_swing=bool(f.l[k] >= ext - 1e-12 and f.l[k + 1] > ext))
            fail1 = down.first_above(s1, -ext)
            fill = down.first_above(s1, -mid - 1e-12) if mid < ce else s1
            for name, obj in objs.items():
                if not np.isfinite(obj) or obj <= ext:
                    continue
                if obj <= ce:
                    row[f"t1_{name}"] = "at_once"
                    continue
                hit = up.first_above(s1, obj)
                row[f"t1_{name}"] = ("held" if hit < fail1 else "failed") if min(hit, fail1) < len(T) else "open"
                row[f"t1geo_{name}"] = (ce - ext) / (obj - ext)
                row[f"t1rr_{name}"] = (obj - ce) / (ce - ext)
                row[f"t1cost_{name}"] = price_cost(ce) / (ce - ext)
                if fill >= len(T) or hit < fill:
                    row[f"t2_{name}"] = "missed"
                    continue
                fail2 = down.first_above(fill, -ext)
                hit2 = up.first_above(fill + 1, obj) if mid < ce else hit
                row[f"t2_{name}"] = ("held" if hit2 < fail2 else "failed") if min(hit2, fail2) < len(T) else "open"
                row[f"t2geo_{name}"] = (mid - ext) / (obj - ext)
                row[f"t2rr_{name}"] = (obj - mid) / (mid - ext)
                row[f"t2cost_{name}"] = price_cost(mid) / (mid - ext)
            ctx.po3(row, ce, t1, last_t)
            row.pop("_i")
            triggers.append(row)
    return swings, triggers


def market_rows(market: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    m1 = load_m1(market)
    fr = build_frames(m1, market)
    T = m1["time"].to_numpy("datetime64[ns]").astype(np.int64)
    H, L = m1["high"].to_numpy(float), m1["low"].to_numpy(float)
    cost = cost_of(market, m1)
    sw, tr = side_rows(market, fr, T, H, L, "low", cost)
    mir = {tf: f.mirror() for tf, f in fr.items()}
    sw_h, tr_h = side_rows(market, mir, T, -L, -H, "high", cost)
    for r in sw_h + tr_h:                                     # back to real prices
        for k in ("extreme", "close", "entry", "mid"):
            if k in r:
                r[k] = -r[k]
    return pd.DataFrame(sw + sw_h), pd.DataFrame(tr + tr_h)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m algo_research.atlas.anchor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--markets", default="")
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    markets = args.markets.split(",") if args.markets else [*FOCUS, *ASSETS, *CRYPTO]
    t0 = time.time()
    (OUT / "trig").mkdir(parents=True, exist_ok=True)
    for m in markets:
        sw, tr = market_rows(m)
        sw.to_parquet(OUT / f"{m}.parquet", index=False)
        tr.to_parquet(OUT / "trig" / f"{m}.parquet", index=False)
        print(f"{m}: {len(sw)} swings, {len(tr)} triggers ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
