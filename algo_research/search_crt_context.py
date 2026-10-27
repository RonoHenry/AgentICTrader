"""The 2018-2024 search: H-O, H-N's CRTs kept at liquidity or a PD array, with the H4 trend
(docs/research/SEARCH_2018_2024.md).

Each CRT's context at C2, read from M15 bars (the broker's, or built from a session's M1). H1 and H4 are UTC hours
built from them; the server is UTC+0.

- **Pools.** A pool is taken by C2 when C2 is the first M15 bar to trade through it after it formed:
  - the previous trading day's high or low, during the next trading day;
  - the day's Asian (20:00-00:00 New York) and London (02:00-05:00) session highs and lows, from the session's end
    to the day's close;
  - an H1 three-candle swing high or low, for 48 hours from the close that confirms it.

  A short needs a high taken, a long a low.
- **PD arrays:** an H1 or H4 fair value gap of the trade's side, from closed candles, formed within 10 days and not
  closed through (an M15 close beyond its far edge) before C2. C2's wick reaches its near edge and C2 closes short of
  its far edge.
- **The H4 trend:** the side of the last H4 break of structure, an H4 close beyond the latest three-candle swing
  high (up) or low (down), on H4 candles closed by C3's open. None yet is no trend.

H-O keeps H-N's trades with a pool or an array, and the trend; its pass rule is H-N's.

    python -m algo_research.search_crt_context --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_crt import NY, TARGETS, WINDOWS, crt_signals, judge
from algo_research.search_d1 import MARKETS, OUT, SNAPSHOT

__all__ = ["Context", "WARMUP", "tag_trades"]

WARMUP = pd.Timedelta(days=30)
SWING_LIFE = pd.Timedelta(hours=48)
FVG_LIFE = pd.Timedelta(days=10)
SESSIONS = (("Asia", "20:00", "24:00"), ("London", "02:00", "05:00"))
_M15 = pd.Timedelta(minutes=15)
_NS = {"1h": 3_600 * 10**9, "4h": 4 * 3_600 * 10**9}


def _bins(m15: pd.DataFrame, freq: str) -> pd.DataFrame:
    """UTC bars of ``freq`` from M15: open time, high, low, close."""
    return m15.groupby(m15["time"].dt.floor(freq), sort=True).agg(
        high=("high", "max"), low=("low", "min"), close=("close", "last")).reset_index()


def _ns(times) -> np.ndarray:
    return pd.DatetimeIndex(times).as_unit("ns").asi8


class Context:
    """The pools, gaps and H4 trend over a stretch of M15, ready to tag CRTs."""

    def __init__(self, m15: pd.DataFrame) -> None:
        m15 = m15.sort_values("time").reset_index(drop=True)
        self.t = _ns(m15["time"])
        self.h, self.l, self.c = (m15[k].to_numpy(float) for k in ("high", "low", "close"))
        self.taken: dict[int, list[tuple[int, str]]] = {}          # M15 open (ns) -> [(+1 high / -1 low, name)]
        for kind, level, start, end, name in self._pools(m15):
            i0, i1 = np.searchsorted(self.t, [start, end], side="left")
            through = self.h[i0:i1] > level if kind > 0 else self.l[i0:i1] < level
            if through.any():
                self.taken.setdefault(int(self.t[i0 + int(np.argmax(through))]), []).append((kind, name))
        self._gaps(m15)
        self._trend(m15)

    # ── pools ────────────────────────────────────────────────────────────────
    def _pools(self, m15: pd.DataFrame):
        local = m15["time"].dt.tz_convert(NY).dt.tz_localize(None)
        day = (local - pd.Timedelta(hours=17)).dt.normalize()
        clock = local.dt.strftime("%H:%M")
        t_ns = self.t
        days = pd.DataFrame({"day": day, "t": t_ns, "h": self.h, "l": self.l}).groupby("day", sort=True).agg(
            start=("t", "first"), last=("t", "last"), high=("h", "max"), low=("l", "min"))
        span = 15 * 60 * 10**9
        rows = list(days.itertuples())
        for prev, cur in zip(rows, rows[1:]):                      # the previous day's extremes, through the next day
            yield 1, prev.high, cur.start, cur.last + span, "PDH"
            yield -1, prev.low, cur.start, cur.last + span, "PDL"
        ends = {r.Index: r.last + span for r in rows}
        for name, a, b in SESSIONS:
            inside = (clock >= a) & (clock < b) if b != "24:00" else (clock >= a)
            frame = pd.DataFrame({"day": day[inside], "t": t_ns[inside.to_numpy()], "h": self.h[inside.to_numpy()],
                                  "l": self.l[inside.to_numpy()]})
            for d, g in frame.groupby("day", sort=True):
                done = int(g["t"].iloc[-1]) + span                  # the session's end
                yield 1, float(g["h"].max()), done, ends[d], f"{name} high"
                yield -1, float(g["l"].min()), done, ends[d], f"{name} low"
        h1 = _bins(m15, "1h")
        hh, ll, ht = h1["high"].to_numpy(float), h1["low"].to_numpy(float), _ns(h1["time"])
        life = int(SWING_LIFE.value)
        for j in range(1, len(h1) - 1):
            confirm = int(ht[j + 1]) + _NS["1h"]
            if hh[j] > hh[j - 1] and hh[j] > hh[j + 1]:
                yield 1, hh[j], confirm, confirm + life, "H1 swing high"
            if ll[j] < ll[j - 1] and ll[j] < ll[j + 1]:
                yield -1, ll[j], confirm, confirm + life, "H1 swing low"

    # ── fair value gaps ──────────────────────────────────────────────────────
    def _gaps(self, m15: pd.DataFrame) -> None:
        rows = []
        life = int(FVG_LIFE.value)
        for tf, freq in (("H1", "1h"), ("H4", "4h")):
            b = _bins(m15, freq)
            h, l, t = b["high"].to_numpy(float), b["low"].to_numpy(float), _ns(b["time"])
            for i in range(2, len(b)):
                formed = int(t[i]) + _NS[freq]
                if l[i] > h[i - 2]:      # bullish: price comes down to its top (near), its far edge the first's high
                    rows.append((1, l[i], h[i - 2], formed, tf))
                if h[i] < l[i - 2]:      # bearish: price comes up to its bottom (near), its far edge the first's low
                    rows.append((-1, h[i], l[i - 2], formed, tf))
        side = np.array([r[0] for r in rows], dtype=int)
        near = np.array([r[1] for r in rows], dtype=float)
        far = np.array([r[2] for r in rows], dtype=float)
        formed = np.array([r[3] for r in rows], dtype=np.int64)
        filled = np.full(len(rows), np.iinfo(np.int64).max, dtype=np.int64)
        for k in range(len(rows)):
            i0, i1 = np.searchsorted(self.t, [formed[k], formed[k] + life], side="left")
            beyond = self.c[i0:i1] < far[k] if side[k] > 0 else self.c[i0:i1] > far[k]
            if beyond.any():
                filled[k] = self.t[i0 + int(np.argmax(beyond))]
        order = np.argsort(formed, kind="stable")
        self.g_side, self.g_near, self.g_far, self.g_formed, self.g_filled = (
            side[order], near[order], far[order], formed[order], filled[order])
        self.g_tf = np.array([rows[k][4] for k in order], dtype=object) if rows else np.array([], dtype=object)

    def arrays_at(self, t2: int, side: int, c2_high: float, c2_low: float, c2_close: float) -> list[str]:
        """The gaps of ``side`` that C2 (opening at ``t2``) reached into and closed short of."""
        lo = np.searchsorted(self.g_formed, t2 - int(FVG_LIFE.value), side="left")
        hi = np.searchsorted(self.g_formed, t2, side="right")
        s, near, far, filled = (a[lo:hi] for a in (self.g_side, self.g_near, self.g_far, self.g_filled))
        if side > 0:
            hit = (s > 0) & (filled >= t2) & (c2_low <= near) & (c2_close > far)
        else:
            hit = (s < 0) & (filled >= t2) & (c2_high >= near) & (c2_close < far)
        return sorted({f"{tf} FVG" for tf in self.g_tf[lo:hi][hit]})

    # ── the H4 trend ─────────────────────────────────────────────────────────
    def _trend(self, m15: pd.DataFrame) -> None:
        b = _bins(m15, "4h")
        h, l, c = (b[k].to_numpy(float) for k in ("high", "low", "close"))
        trend = np.zeros(len(b), dtype=int)
        swing_high = swing_low = None
        state = 0
        for i in range(len(b)):
            if swing_high is not None and c[i] > swing_high:
                state, swing_high = 1, None
            if swing_low is not None and c[i] < swing_low:
                state, swing_low = -1, None
            if i >= 2:                                             # bar i confirms a swing at i - 1
                if h[i - 1] > h[i - 2] and h[i - 1] > h[i]:
                    swing_high = h[i - 1]
                if l[i - 1] < l[i - 2] and l[i - 1] < l[i]:
                    swing_low = l[i - 1]
            trend[i] = state
        self.h4_end, self.h4_trend = _ns(b["time"]) + _NS["4h"], trend

    def trend_at(self, c3: int) -> int:
        i = int(np.searchsorted(self.h4_end, c3, side="right")) - 1
        return int(self.h4_trend[i]) if i >= 0 else 0

    # ── one CRT ──────────────────────────────────────────────────────────────
    def tag(self, c3: int, side: int, c2_high: float, c2_low: float, c2_close: float) -> dict:
        t2 = c3 - int(_M15.value)
        pools = sorted({name for kind, name in self.taken.get(t2, []) if kind == (-1 if side > 0 else 1)})
        arrays = self.arrays_at(t2, side, c2_high, c2_low, c2_close)
        trend = self.trend_at(c3)
        return {"pools": pools, "arrays": arrays, "trend": trend,
                "kept": bool((pools or arrays) and trend == side)}


def tag_trades(ctx: Context, m15: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    """H-N's trades ``t`` of one market, with each CRT's pools, arrays, H4 trend and whether H-O keeps it."""
    s = crt_signals(m15)
    s = s.assign(c3_ns=_ns(s["c3"]))
    t = t.assign(c3_ns=_ns(t["c3"])).merge(s[["c3_ns", "side", "c2_high", "c2_low", "c2_close"]], on=["c3_ns", "side"],
                                             how="left")
    tags = [ctx.tag(int(r.c3_ns), int(r.side), r.c2_high, r.c2_low, r.c2_close) for r in t.itertuples(index=False)]
    return t.assign(pool=[bool(x["pools"]) for x in tags], array=[bool(x["arrays"]) for x in tags],
                    with_trend=[x["trend"] == side for x, side in zip(tags, t["side"])],
                    pools=[", ".join(x["pools"]) for x in tags], arrays=[", ".join(x["arrays"]) for x in tags],
                    kept=[x["kept"] for x in tags]).drop(columns=["c3_ns"])


def _row(name: str, part: pd.DataFrame, total: int) -> str:
    if part.empty:
        return f"| {name} | 0 | | | | | |"
    r = judge(part)
    cells = " | ".join(f"{r[k]['net']:+.3f} [{r[k]['lo']:+.3f}, {r[k]['hi']:+.3f}]" for k in TARGETS)
    k5 = r[TARGETS[-1]]
    return (f"| {name} | {len(part):,} ({len(part) / total:.0%}) | {cells} | {k5['minus_mirror']:+.3f} | "
            f"{k5['positive']}/9 | {'yes' if any(r[k]['passes'] for k in TARGETS) else 'no'} |")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=["develop"], required=True)
    args = parser.parse_args()
    since, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    trades = pd.read_parquet(OUT / f"crt_{args.window}.parquet")             # H-N's own trades
    parts = []
    for market in MARKETS:
        m15 = pd.read_parquet(SNAPSHOT / f"{market}_M15.parquet")
        m15 = m15[(m15["time"] >= since - WARMUP) & (m15["time"] < until)].reset_index(drop=True)
        tagged = tag_trades(Context(m15), m15, trades[trades["market"] == market].reset_index(drop=True))
        parts.append(tagged)
        print(f"{market}: {len(tagged):,} trades, kept {int(tagged['kept'].sum()):,}", flush=True)
    t = pd.concat(parts, ignore_index=True)
    t.to_parquet(OUT / f"crt_context_{args.window}.parquet")
    total = len(t)
    head = " | ".join(f"{k:g}R{' + partial' if k > 3 else ''} net [98.3%]" for k in TARGETS)
    print(f"\n| Trades | n (share) | {head} | 5R trade - mirror | Markets > 0 (5R) | Passes |")
    print("|---|---|" + "---|" * len(TARGETS) + "---|---|---|")
    print(_row("**H-O: (pool or array) and the trend**", t[t["kept"]], total))
    for name, mask in (("pool", t["pool"]), ("array", t["array"]), ("with the H4 trend", t["with_trend"]),
                       ("pool or array", t["pool"] | t["array"]), ("pool and the trend", t["pool"] & t["with_trend"]),
                       ("array and the trend", t["array"] & t["with_trend"]), ("all of H-N", t["net_3"].notna())):
        print(_row(name, t[mask.to_numpy(bool)], total))
    kept = t[t["kept"]]
    print("\nH-O per market, 5R + partial: " + ", ".join(
        f"{m} {g['net_5'].mean():+.3f} ({len(g):,})" for m, g in kept.groupby("market")))
    print("pools taken by kept trades: " + ", ".join(f"{k} {v:,}" for k, v in
          kept["pools"].str.split(", ").explode().replace("", np.nan).dropna().value_counts().items()))


if __name__ == "__main__":
    main()
