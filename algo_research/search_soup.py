"""The 2018-2024 search: H-U, the turtle soup after displacement (docs/research/SEARCH_2018_2024.md).

The trader's read, on H1, H4 and D1 in New York time (H-Q's frames, from the window's M1, the rollover left out)
and on W1 from the broker's D1 bars (Amendment 1). A long, read at C2's close with C1 and C0 the two candles before
it (a short is the mirror):

1. **The raid:** C0 or C1 trades above an untaken swing high of the frame, known before C0 opened, and neither
   closes above it (liquidation).
2. **The displacement:** C1 closes below C0's low.
3. **The failure to displace:** C2 trades below C1's low, not above C1's high, and closes back above C1's low.
4. **The pool:** C2's low also takes an untaken swing low below C1's low, of the frame or the frame below (M15 for
   H1, H1 for H4, H4 for D1, D1 for W1), known before C1 opened.
5. **Deep discount:** C2's close is in the bottom quarter of the range from the raid's high to C2's low.

A swing high is a candle whose high is above the highs of the two candles each side, known at the second one's
close. The draw is C1's equilibrium (the midpoint of its high and low), the invalidation C2's low. From C2's close
the path says which is reached first (a bar reaching both is failed), against a driftless walk's chance from the
close.

Pass: for a cell (a frame), the excess over geometry above zero, its trading-date interval at 98.75% (Holm, four
cells) above zero, and positive in 6 of the 9 markets.

    python -m algo_research.search_soup --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_bias import _outcome, drop_rollover, first_touch, frames
from algo_research.search_crt import M1_SNAPSHOTS, WINDOWS, _interval
from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT, SNAPSHOT, merge_sundays

__all__ = ["FRAMES", "judge", "m15", "market_rows", "soup", "swings", "weekly"]

FRAMES = ("H1", "H4", "D1", "W1")
BELOW = {"H1": "M15", "H4": "H1", "D1": "H4", "W1": "D1"}
CALLS_FROM = {"H1": "2021-09-01", "H4": "2021-09-01", "D1": "2021-09-01", "W1": "2018-07-01"}
LEVEL = 1 - 0.05 / len(FRAMES)
SWING = 2
DISCOUNT = 0.25
FIFTH = 0.2
MIN_RISK_SPREADS, COST_FLOOR_SPREADS = 2.0, 10.0
_NEVER = np.iinfo(np.int64).max
_DAY = 86_400 * 10**9
_MINUTE = 60 * 10**9


# ── the frames ─────────────────────────────────────────────────────────────

def m15(m1: pd.DataFrame) -> pd.DataFrame:
    """The M15 candles of ``m1`` in the shape of ``search_bias.frames``' (the frame below H1)."""
    base = pd.DataFrame({"open": m1["open"].to_numpy(float), "high": m1["high"].to_numpy(float),
                         "low": m1["low"].to_numpy(float), "close": m1["close"].to_numpy(float),
                         "row": np.arange(len(m1)), "t": pd.DatetimeIndex(m1["time"]).as_unit("ns").asi8})
    g = base.groupby(m1["time"].dt.floor("15min").to_numpy(), sort=True)
    return pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                         "close": g["close"].last(), "i0": g["row"].first(), "i1": g["row"].last(),
                         "t_open": g["t"].first(), "t_close": g["t"].last() + _MINUTE}).reset_index(drop=True)


def weekly(d1: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The broker's D1 bars (Sundays merged) as the frame below, and their weeks as W1, the D1 rows being the path."""
    time = pd.to_datetime(d1["time"], utc=True)
    t = pd.DatetimeIndex(time).as_unit("ns").asi8
    days = pd.DataFrame({k: d1[k].to_numpy(float) for k in ("open", "high", "low", "close")})
    days = days.assign(i0=np.arange(len(d1)), i1=np.arange(len(d1)), t_open=t, t_close=t + _DAY,
                       date=time.dt.tz_localize(None).dt.normalize().to_numpy())
    week = (time - pd.to_timedelta(time.dt.dayofweek, unit="D")).dt.normalize()
    g = days.groupby(week.to_numpy(), sort=True)
    weeks = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                          "close": g["close"].last(), "i0": g["i0"].first(), "i1": g["i1"].last(),
                          "t_open": g["t_open"].first(), "t_close": g["t_close"].last(), "date": g["date"].last()})
    return weeks.reset_index(drop=True), days


def _flip(bars: pd.DataFrame) -> pd.DataFrame:
    """The bars upside down, so a short reads as a long: highs become lows, every price negated."""
    return bars.assign(open=-bars["open"], close=-bars["close"], high=-bars["low"], low=-bars["high"])


# ── the read ───────────────────────────────────────────────────────────────

def _next_above(x: np.ndarray) -> np.ndarray:
    """For each bar, the first later bar whose value is above its own (-1: none)."""
    out, stack = np.full(len(x), -1), []
    for j, v in enumerate(x):
        while stack and x[stack[-1]] < v:
            out[stack.pop()] = j
        stack.append(j)
    return out


def swings(bars: pd.DataFrame, side: str) -> dict[str, np.ndarray]:
    """The swing highs (``side="high"``) or lows of ``bars``: ``level``, when they are known (the close of the second
    candle after) and ``taken`` (the open of the first later candle beyond them; never is int64 max)."""
    level = bars[side].to_numpy(float)
    v = level if side == "high" else -level
    ok = np.zeros(len(v), bool)
    mid = np.arange(SWING, len(v) - SWING)
    ok[mid] = True
    for k in range(1, SWING + 1):
        ok[mid] &= (v[mid] > v[mid - k]) & (v[mid] > v[mid + k])
    i = np.nonzero(ok)[0]
    nxt = _next_above(v)[i]
    t_open, t_close = bars["t_open"].to_numpy(np.int64), bars["t_close"].to_numpy(np.int64)
    return {"level": level[i], "known": t_close[i + SWING],
            "taken": np.where(nxt >= 0, t_open[np.maximum(nxt, 0)], _NEVER)}


def soup(bars: pd.DataFrame, below: pd.DataFrame) -> pd.DataFrame:
    """Every long whose C1 displaced and whose C2 failed to (conditions 2 and 3), with the raid, the pool and the
    discount (1, 4 and 5) as flags, and the companions known at C2's close (C1 engulfing C0's body, C1 breaking a
    swing low of the frame). ``k`` is C2's row."""
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    t_open, t_close = bars["t_open"].to_numpy(np.int64), bars["t_close"].to_numpy(np.int64)
    highs, own = swings(bars, "high"), swings(bars, "low")
    lows = {k: np.concatenate([own[k], swings(below, "low")[k]]) for k in own}
    rows = []
    for k in range(2, len(bars)):
        c0, c1 = k - 2, k - 1
        if not (c[c1] < l[c0] and l[k] < l[c1] and h[k] <= h[c1] and c[k] > l[c1]):
            continue
        eq = (h[c1] + l[c1]) / 2
        if eq <= c[k]:
            continue
        raided = (highs["known"] <= t_open[c0]) & (highs["taken"] >= t_open[c0]) & (highs["taken"] < t_close[c1])
        raid = bool((raided & (highs["level"] >= max(c[c0], c[c1]))).any())
        pool = bool(((lows["known"] <= t_open[c1]) & (lows["level"] < l[c1]) & (lows["taken"] >= t_open[k])
                     & (lows["taken"] < t_close[k])).any())
        top = max(h[c0], h[c1])
        bos = bool(((own["known"] <= t_open[c1]) & (own["taken"] >= t_open[c1]) & (own["taken"] < t_close[c1])
                    & (own["level"] > c[c1])).any())
        rows.append({"k": k, "raid": raid, "pool": pool, "discount": (c[k] - l[k]) <= DISCOUNT * (top - l[k]),
                     "engulf": min(o[c1], c[c1]) <= min(o[c0], c[c0]) and max(o[c1], c[c1]) >= max(o[c0], c[c0]),
                     "bos": bos, "eq": eq, "c1_high": h[c1]})
    return pd.DataFrame(rows, columns=["k", "raid", "pool", "discount", "engulf", "bos", "eq", "c1_high"])


def market_rows(bars: pd.DataFrame, below: pd.DataFrame, hi: np.ndarray, lo: np.ndarray, market: str, frame: str,
                since, until, spread: float) -> pd.DataFrame:
    """Every call of one frame in one market whose C2 closes in [since, until], long and short, raced on the path
    ``hi``/``lo`` (the rows ``i0``..``i1`` of each candle)."""
    since, until = (pd.DatetimeIndex([pd.Timestamp(x)]).tz_localize(None if pd.Timestamp(x).tz else "UTC")
                    .as_unit("ns").asi8[0] for x in (since, until))
    out = []
    for side in (1, -1):
        b, w = (bars, below) if side > 0 else (_flip(bars), _flip(below))
        phi, plo = (hi, lo) if side > 0 else (-lo, -hi)
        i0, i1 = b["i0"].to_numpy(int), b["i1"].to_numpy(int)
        low, close = b["low"].to_numpy(float), b["close"].to_numpy(float)
        tc = b["t_close"].to_numpy(np.int64)
        for r in soup(b, w).itertuples(index=False):
            k = r.k
            if not since <= tc[k] <= until:
                continue
            p, stop = close[k], low[k]
            start = i1[k] + 1
            outcome, i_set = _outcome(1, *first_touch(phi, plo, start, r.eq, stop))
            far, _ = _outcome(1, *first_touch(phi, plo, start, r.c1_high, stop))
            c2_min = i0[k] + int(np.argmin(plo[i0[k]:i1[k] + 1]))
            c3 = k + 1 if k + 1 < len(b) else None
            c3_min = i0[c3] + int(np.argmin(plo[i0[c3]:i1[c3] + 1])) if c3 is not None else None
            risk = p - stop
            geo = (p - stop) / (r.eq - stop)
            out.append({
                "market": market, "frame": frame, "side": side, "date": pd.Timestamp(b["date"].iat[k]),
                "close_at": pd.Timestamp(int(tc[k]), tz="UTC"), "close": side * p, "draw": side * r.eq,
                "stop": side * stop, "c1_high": side * r.c1_high, "raid": r.raid, "pool": r.pool,
                "discount": r.discount, "engulf": r.engulf, "bos": r.bos, "outcome": outcome, "geo": geo,
                "ambiguous": outcome == "failed" and i_set >= 0 and phi[i_set] >= r.eq and plo[i_set] <= stop,
                "far_outcome": far, "far_geo": (p - stop) / (r.c1_high - stop),
                "within_c3": outcome == "held" and c3 is not None and i_set <= i1[c3],
                "late_c2_low": c2_min - i0[k] >= (1 - FIFTH) * (i1[k] - i0[k]),
                "c3_low_early": float(c3_min - i0[c3] <= FIFTH * (i1[c3] - i0[c3])) if c3 is not None else np.nan,
                "risk_spreads": risk / spread if spread > 0 else np.inf,
                "r_gross": (1 - geo) / geo if outcome == "held" else -1.0,
                "cost_r": spread / risk if risk > 0 else np.nan})
    return pd.DataFrame(out)


# ── judging ────────────────────────────────────────────────────────────────

def _resolved(t: pd.DataFrame, outcome: str = "outcome") -> pd.DataFrame:
    return t[t[outcome].isin(("held", "failed"))]


def _excess(t: pd.DataFrame, outcome: str = "outcome", geo: str = "geo") -> tuple[float, int]:
    g = _resolved(t, outcome)
    return (float(((g[outcome] == "held") - g[geo]).mean()) if len(g) else np.nan), len(g)


def judge(t: pd.DataFrame) -> dict:
    """The pass rule's numbers for the calls ``t``, the month interval and the trade at the call."""
    g = _resolved(t)
    gap = (g["outcome"] == "held").to_numpy(float) - g["geo"].to_numpy(float)
    enough = g["date"].nunique() > 1
    lo, hi = _interval(g["date"].to_numpy(), gap, LEVEL) if enough else (np.nan, np.nan)
    months = g["date"].dt.to_period("M").astype(str).to_numpy()
    mlo, mhi = _interval(months, gap, 0.95) if enough else (np.nan, np.nan)
    per = {m: _excess(x) for m, x in t.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    excess = float(gap.mean()) if len(g) else np.nan
    traded = g[g["risk_spreads"] >= MIN_RISK_SPREADS]
    floor = g[g["risk_spreads"] >= COST_FLOOR_SPREADS]
    return {"calls": len(t), "resolved": len(g), "open": int((t["outcome"] == "open").sum()),
            "ambiguous": int(g["ambiguous"].sum()), "held": float((g["outcome"] == "held").mean()) if len(g) else np.nan,
            "geo": float(g["geo"].mean()) if len(g) else np.nan, "excess": excess, "lo": lo, "hi": hi,
            "month_lo": mlo, "month_hi": mhi, "per_market": per, "positive": positive,
            "passes": bool(excess > 0 and lo > 0 and positive >= MIN_MARKETS),
            "r_gross": float(traded["r_gross"].mean()) if len(traded) else np.nan,
            "r_net": float((traded["r_gross"] - traded["cost_r"]).mean()) if len(traded) else np.nan,
            "r_net_floor": float((floor["r_gross"] - floor["cost_r"]).mean()) if len(floor) else np.nan,
            "floor": len(floor), "risk_spreads": float(g["risk_spreads"].median()) if len(g) else np.nan}


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def _r(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{x:+.3f}"


def _rule(t: pd.DataFrame) -> pd.Series:
    return t["raid"] & t["pool"] & t["discount"]


COMPANIONS = (
    ("C1's high as the draw", lambda t: _rule(t), ("far_outcome", "far_geo")),
    ("without the raid", lambda t: t["pool"] & t["discount"], None),
    ("without the pool", lambda t: t["raid"] & t["discount"], None),
    ("without the discount", lambda t: t["raid"] & t["pool"], None),
    ("all three dropped (H-Q's reversal after a displacement)", lambda t: pd.Series(True, index=t.index), None),
    ("C1 engulfs C0's body", lambda t: _rule(t) & t["engulf"], None),
    ("C1 doesn't engulf", lambda t: _rule(t) & ~t["engulf"], None),
    ("C1 broke a swing low (BOS)", lambda t: _rule(t) & t["bos"], None),
    ("C1 only below C0's low", lambda t: _rule(t) & ~t["bos"], None),
    ("long", lambda t: _rule(t) & (t["side"] > 0), None),
    ("short", lambda t: _rule(t) & (t["side"] < 0), None),
    ("C2's low in its last fifth", lambda t: _rule(t) & t["late_c2_low"], None),
    ("C2's low earlier", lambda t: _rule(t) & ~t["late_c2_low"], None),
)


def render(t: pd.DataFrame) -> str:
    lines = [f"| Frame | Calls | Resolved (open) | Held | Geometry | Excess (pts) | {100 * LEVEL:.2f}% dates | "
             "95% months | Markets > 0 | R gross / net (risk, spreads) | R net, risk >= 10 spreads (n) | Passes |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    results = {}
    for tf in FRAMES:
        part = t[(t["frame"] == tf) & _rule(t)]
        if part.empty:
            lines.append(f"| {tf} | 0 | | | | | | | | | | |")
            continue
        r = results[tf] = judge(part)
        lines.append(f"| {tf} | {r['calls']:,} | {r['resolved']:,} ({r['open']}) | {r['held']:.1%} | {r['geo']:.1%} | "
                     f"{_pts(r['excess'])} | [{_pts(r['lo'])}, {_pts(r['hi'])}] | "
                     f"[{_pts(r['month_lo'])}, {_pts(r['month_hi'])}] | {r['positive']}/9 | "
                     f"{_r(r['r_gross'])} / {_r(r['r_net'])} ({r['risk_spreads']:.1f}) | "
                     f"{_r(r['r_net_floor'])} ({r['floor']:,}) | {'yes' if r['passes'] else 'no'} |")
    lines += ["", "Companions, excess over geometry in points (resolved calls):", "",
              "| Calls | " + " | ".join(FRAMES) + " |", "|---" * (len(FRAMES) + 1) + "|"]
    for name, mask, cols in COMPANIONS:
        cells = []
        for tf in FRAMES:
            part = t[t["frame"] == tf]
            part = part[mask(part).to_numpy(bool)]
            x, n = _excess(part, *cols) if cols else _excess(part)
            cells.append(f"{_pts(x)} ({n:,})")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "| Under the rule | " + " | ".join(FRAMES) + " |", "|---" * (len(FRAMES) + 1) + "|"]
    for name, fn in (
            ("draw reached before C3 closes (of resolved)", lambda g: f"{g['within_c3'].mean():.0%}"),
            ("C3's low in its first fifth: held / failed",
             lambda g: f"{g[g['outcome'] == 'held']['c3_low_early'].mean():.0%} / "
                       f"{g[g['outcome'] == 'failed']['c3_low_early'].mean():.0%}"),
            ("ambiguous (a bar reaching both)", lambda g: f"{int(g['ambiguous'].sum()):,}")):
        cells = []
        for tf in FRAMES:
            g = _resolved(t[(t["frame"] == tf) & _rule(t)])
            cells.append(fn(g) if len(g) else "–")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += [""] + [f"Excess per market, {tf}: " + ", ".join(f"{m} {_pts(v)} ({n:,})"
                                                            for m, (v, n) in r["per_market"].items())
                     for tf, r in results.items()]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(M1_SNAPSHOTS), required=True)
    args = parser.parse_args()
    start, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    parts = []
    for market in MARKETS:
        m1 = pd.read_parquet(M1_SNAPSHOTS[args.window] / f"{market}_M1.parquet")
        m1 = drop_rollover(m1[(m1["time"] >= start) & (m1["time"] < until)].reset_index(drop=True))
        spread = float(m1["spread"].median())
        f = frames(m1)
        f["M15"] = m15(m1)
        hi, lo = m1["high"].to_numpy(float), m1["low"].to_numpy(float)
        for tf in ("H1", "H4", "D1"):
            parts.append(market_rows(f[tf], f[BELOW[tf]], hi, lo, market, tf, CALLS_FROM[tf], until, spread))
        d1 = merge_sundays(pd.read_parquet(SNAPSHOT / f"{market}_D1.parquet"))
        d1 = d1[pd.to_datetime(d1["time"], utc=True) < until].reset_index(drop=True)
        weeks, days = weekly(d1)
        parts.append(market_rows(weeks, days, days["high"].to_numpy(float), days["low"].to_numpy(float), market,
                                 "W1", CALLS_FROM["W1"], until, spread))
        done = pd.concat(parts[-4:], ignore_index=True)
        print(f"{market}: " + ", ".join(f"{tf} {int(((done['frame'] == tf) & _rule(done)).sum()):,}"
                                        for tf in FRAMES), flush=True)
    t = pd.concat(parts, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_parquet(OUT / f"soup_{args.window}.parquet")
    print(render(t))


if __name__ == "__main__":
    main()
