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

from liquidity_engine.context.blocks import BULL, delivery_blocks
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
    parts = [pd.read_parquet(p, columns=["time", "open", "high", "low", "close"]) for p in paths if p.exists()]
    m1 = pd.concat(parts, ignore_index=True)
    m1["time"] = pd.to_datetime(m1["time"], utc=True)
    return m1.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)


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


def side_rows(market: str, fr: dict[str, F], T: np.ndarray, H: np.ndarray, L: np.ndarray, side: str) -> list[dict]:
    """Every swing low of every current frame on prices already turned for ``side`` (``high``: upside down)."""
    up, down = Passage(H), Passage(-L)
    last_t = int(T[-1]) if len(T) else 0
    levels = {tf: anchor_levels(fr[tf]) for tf in ("M30", "H1", "H4", "D1", "W1", "MN1", "Q")}
    rows = []
    for cur in CURRENT:
        f, a_tf = fr[cur], TRIADS[cur][0]
        a = fr[a_tf]
        a2_tf = UP2.get(a_tf)
        dur_a = int(np.median(a.end - a.t)) if len(a.t) else 0
        dur_a2 = int(np.median(fr[a2_tf].end - fr[a2_tf].t)) if a2_tf else 0
        rng = f.h - f.l
        atr = pd.Series(rng).rolling(ATR_N).mean().shift(1).to_numpy()
        a_rng = pd.Series(a.h - a.l).rolling(ATR_N).mean().shift(1).to_numpy()
        above = [tf for tf in LADDER[LADDER.index(cur) + 1:]]
        n = len(f.t)
        sh = np.zeros(n, dtype=bool)                          # swing highs of the current frame
        sh[1:-1] = (f.h[1:-1] > f.h[:-2]) & (f.h[1:-1] > f.h[2:])
        sh_idx = np.flatnonzero(sh)
        for k in range(2, n - 1):
            if not (f.l[k] < f.l[k - 1] and f.l[k] < f.l[k + 1]) or not np.isfinite(atr[k]):
                continue
            ext = f.l[k]
            ia, ib = np.searchsorted(T, [f.t[k], f.end[k]])
            if ib <= ia:
                continue
            ie = ia + int(np.argmin(L[ia:ib]))
            t_ext = int(T[ie])
            known = int(f.end[k + 1])
            s = int(np.searchsorted(T, known, "left"))
            if s >= len(T):
                continue
            close = float(f.c[k + 1])
            i = int(a.at(np.array([t_ext]))[0])
            if i < 1:
                continue
            tol = TOL * atr[k]
            row = {"market": market, "group": GROUP.get(market, "?"), "side": side, "tf": cur, "anchor": a_tf,
                   "t_ext": t_ext, "known": known, "extreme": ext, "close": close, "atr": atr[k],
                   "below_open": bool(ext < a.o[i]), "phase": (t_ext - a.t[i]) / max(1, a.end[i] - a.t[i]),
                   "pd": (ext - a.l[i - 1]) / (a.h[i - 1] - a.l[i - 1]) if a.h[i - 1] > a.l[i - 1] else np.nan}
            kinds = levels[a_tf].near(t_ext, ext, tol, LOOKBACK * dur_a + dur_a)
            row["stack"] = int(len(kinds))
            row["stack_kinds"] = int(len(set(kinds)))
            for kk in ("open", "close", "ob", "breaker", "fvg", "ifvg", "wick"):
                row[f"lv_{kk}"] = int((kinds == kk).sum())
            row["stack2"] = int(len(levels[a2_tf].near(t_ext, ext, tol, LOOKBACK * dur_a2 + dur_a2))) if a2_tf else 0
            below, w = [], []
            for r, tf in enumerate(above):                   # the opens above, nearest first
                g = fr[tf]
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
            # the objectives
            j0 = sh_idx[sh_idx <= k - 2]
            leg = float(f.h[j0[-1]:k].max()) if len(j0) else np.nan
            objs = {"anchor": float(a.h[i - 1]), "leg": leg, "crt": float(f.h[k - 1])}
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
            # PO3: the anchor closes beyond its open
            tau = (a.end[i] - known) / max(1, a.end[i] - a.t[i])
            if tau > 0 and a.end[i] <= last_t and np.isfinite(a_rng[i]) and a_rng[i] > 0:
                row["po3"] = bool(a.c[i] > a.o[i])
                row["geo_po3"] = _phi((close - a.o[i]) / (a_rng[i] / 1.596 * math.sqrt(tau)))
                row["anchor_low"] = bool(a.l[i] >= ext - 1e-9)
            rows.append(row)
    return rows


def market_rows(market: str) -> pd.DataFrame:
    m1 = load_m1(market)
    fr = build_frames(m1, market)
    T = m1["time"].to_numpy("datetime64[ns]").astype(np.int64)
    H, L = m1["high"].to_numpy(float), m1["low"].to_numpy(float)
    rows = side_rows(market, fr, T, H, L, "low")
    mir = {tf: f.mirror() for tf, f in fr.items()}
    hi = side_rows(market, mir, T, -L, -H, "high")
    for r in hi:                                              # back to real prices
        for k in ("extreme", "close"):
            r[k] = -r[k]
    return pd.DataFrame(rows + hi)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m algo_research.atlas.anchor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--markets", default="")
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    markets = args.markets.split(",") if args.markets else [*FOCUS, *ASSETS, *CRYPTO]
    t0 = time.time()
    for m in markets:
        df = market_rows(m)
        df.to_parquet(OUT / f"{m}.parquet", index=False)
        print(f"{m}: {len(df)} swings ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
