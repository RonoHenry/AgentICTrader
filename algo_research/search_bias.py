"""The 2018-2024 search: H-Q, the two-candle read on every frame (docs/research/SEARCH_2018_2024.md).

The trader's candle guide, read at each close of H1, H4, D1 and W1 in New York time (the day 17:00-17:00, H4 from
17:00, the week from Sunday 17:00), built from M1 with the rollover minutes (16:55-17:05) left out:

- **Expansion:** C2 closes beyond one side of C1. The call is that side.
- **Reversal (aim for the range's other end):** C2 takes one side of C1, not the other, and closes back inside. The
  call is the other side.
- **Seek and destroy** (both sides taken, closed inside) and **consolidation** (inside) make no call.

The draw is C2's extreme on the call's side, the invalidation its other extreme. From C2's close, the M1 path says
which is reached first (a bar reaching both is failed), against a driftless walk's chance from the close. A call is
at a gap when C2's wick reached into an unfilled fair value gap of its side, on its frame or the one above, and C2
closed short of the gap's far edge.

Pass: for a cell (a frame, with every call or only those at a gap), the excess over geometry above zero, its
trading-date interval at 99.375% (Holm, eight cells) above zero, and positive in 6 of the 9 markets.

    python -m algo_research.search_bias --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_crt import M1_SNAPSHOTS, NY, WINDOWS, _interval
from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT

__all__ = ["FRAMES", "calls", "drop_rollover", "first_touch", "frames", "gaps", "market_calls"]

FRAMES = ("H1", "H4", "D1", "W1")
ABOVE = {"H1": "H4", "H4": "D1", "D1": "W1"}
GAP_FRAMES = {"H1": ("H1", "H4"), "H4": ("H4", "D1"), "D1": ("D1", "W1"), "W1": ("W1",)}
CALLS_FROM = "2021-09-01"
ROLLOVER = ("16:55", "17:05")
LEVEL = 1 - 0.05 / 8
MIN_RISK_SPREADS = 2.0
_SHIFT = pd.Timedelta(hours=7)                     # New York + 7 h puts the 17:00 open at midnight
_MINUTE = 60 * 10**9
_NEVER = np.iinfo(np.int64).max


def _ns(times) -> np.ndarray:
    return pd.DatetimeIndex(times).as_unit("ns").asi8


def drop_rollover(m1: pd.DataFrame) -> pd.DataFrame:
    """``m1`` without the minutes 16:55-17:05 New York, where the bid dips as the spread widens."""
    clock = m1["time"].dt.tz_convert(NY).dt.strftime("%H:%M")
    return m1[~((clock >= ROLLOVER[0]) & (clock < ROLLOVER[1]))].reset_index(drop=True)


def frames(m1: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """The H1, H4, D1 and W1 candles of ``m1`` in New York time: open, high, low, close, the first and last M1 rows
    (``i0``, ``i1``), when they open and close (``t_open``, ``t_close``: ns, UTC) and the trading date they close on."""
    local = m1["time"].dt.tz_convert(NY).dt.tz_localize(None)
    shifted = local + _SHIFT
    date = shifted.dt.normalize()
    keys = {"H1": m1["time"].dt.floor("h").dt.tz_localize(None), "H4": shifted.dt.floor("4h"), "D1": date,
            "W1": date - pd.to_timedelta(date.dt.dayofweek, unit="D")}
    base = pd.DataFrame({"open": m1["open"].to_numpy(float), "high": m1["high"].to_numpy(float),
                         "low": m1["low"].to_numpy(float), "close": m1["close"].to_numpy(float),
                         "row": np.arange(len(m1)), "t": _ns(m1["time"]), "date": date.to_numpy()})
    out = {}
    for tf, key in keys.items():
        g = base.groupby(key.to_numpy(), sort=True)
        bars = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                             "close": g["close"].last(), "i0": g["row"].first(), "i1": g["row"].last(),
                             "t_open": g["t"].first(), "t_close": g["t"].last() + _MINUTE, "date": g["date"].last()})
        out[tf] = bars.rename_axis("start").reset_index()
    return out


def calls(bars: pd.DataFrame) -> pd.DataFrame:
    """The read at each candle's close against the one before: ``side`` (+1 bullish, -1 bearish, 0 none) and
    ``case`` (expansion, reversal, seek and destroy, consolidation), with C1's high and low."""
    h1, l1 = bars["high"].shift(1), bars["low"].shift(1)
    h2, l2, c2 = bars["high"], bars["low"], bars["close"]
    up, down = c2 > h1, c2 < l1
    took_high, took_low = h2 > h1, l2 < l1
    side = np.select([up, down, took_high & ~took_low, took_low & ~took_high], [1, -1, -1, 1], 0)
    case = np.select([up | down, took_high ^ took_low, took_high & took_low],
                     ["expansion", "reversal", "seek and destroy"], "consolidation")
    return pd.DataFrame({"side": side, "case": case, "c1_high": h1, "c1_low": l1}, index=bars.index)


def gaps(bars: pd.DataFrame) -> pd.DataFrame:
    """The fair value gaps of closed candles: side (+1 bullish), near and far edges, when the third candle closed
    (``formed``) and when a candle first closed beyond the far edge (``filled``; never is int64 max)."""
    h, l, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    tc = bars["t_close"].to_numpy(np.int64)
    rows = []
    for i in range(2, len(bars)):
        if l[i] > h[i - 2]:
            rows.append((1, l[i], h[i - 2], i))
        if h[i] < l[i - 2]:
            rows.append((-1, h[i], l[i - 2], i))
    out = pd.DataFrame(rows, columns=["side", "near", "far", "i"])
    filled = np.full(len(out), _NEVER, dtype=np.int64)
    for k, (s, far, i) in enumerate(zip(out["side"], out["far"], out["i"])):
        beyond = c[i + 1:] < far if s > 0 else c[i + 1:] > far
        if beyond.any():
            filled[k] = tc[i + 1 + int(np.argmax(beyond))]
    return out.assign(formed=tc[out["i"].to_numpy(int)] if len(out) else np.array([], np.int64), filled=filled)


def first_touch(hi: np.ndarray, lo: np.ndarray, start: int, above: float, below: float) -> tuple[int, int]:
    """From row ``start``, the first row whose high reaches ``above`` and the first whose low reaches ``below``, read
    in growing chunks up to the first chunk reaching either (-1: not in it). (-1, -1) when the path ends first."""
    n, a, w = len(hi), start, 256
    while a < n:
        b = min(n, a + w)
        up, down = hi[a:b] >= above, lo[a:b] <= below
        if up.any() or down.any():
            return (a + int(np.argmax(up)) if up.any() else -1, a + int(np.argmax(down)) if down.any() else -1)
        a, w = b, 2 * w
    return -1, -1


def _outcome(side: int, i_up: int, i_down: int) -> tuple[str, int]:
    """held, failed or open for a race to the ``side``'s level (above for +1), and the row that settled it."""
    i_draw, i_inval = (i_up, i_down) if side > 0 else (i_down, i_up)
    if i_draw < 0 and i_inval < 0:
        return "open", -1
    if i_draw >= 0 and (i_inval < 0 or i_draw < i_inval):
        return "held", i_draw
    return "failed", i_inval


def _at_gap(g: pd.DataFrame, side: int, t_open: int, high: float, low: float, close: float) -> bool:
    live = (g["side"].to_numpy() == side) & (g["formed"].to_numpy() <= t_open) & (g["filled"].to_numpy() > t_open)
    near, far = g["near"].to_numpy(float), g["far"].to_numpy(float)
    reached = (low <= near) & (close > far) if side > 0 else (high >= near) & (close < far)
    return bool((live & reached).any())


def market_calls(m1: pd.DataFrame, market: str, since, until, spread: float) -> pd.DataFrame:
    """Every call H-Q makes in one market from ``since`` to ``until`` (closes), on ``m1`` (the rollover dropped),
    with its outcome, geometry and the companions' columns."""
    since, until = _ns([pd.Timestamp(since)])[0], _ns([pd.Timestamp(until)])[0]
    hi, lo = m1["high"].to_numpy(float), m1["low"].to_numpy(float)
    f = frames(m1)
    read = {tf: calls(f[tf]) for tf in FRAMES}
    gap = {tf: gaps(f[tf]) for tf in FRAMES}
    rows = []
    for tf in FRAMES:
        bars, r = f[tf], read[tf]
        gap_tables = [gap[x] for x in GAP_FRAMES[tf]]
        above = f.get(ABOVE.get(tf, ""))
        above_close = above["t_close"].to_numpy(np.int64) if above is not None else None
        for k in np.nonzero(r["side"].to_numpy() != 0)[0]:
            b, s = bars.iloc[k], int(r["side"].iat[k])
            if not since <= b.t_close <= until or b.high <= b.low:
                continue
            p = float(b.close)
            outcome, i_set = _outcome(s, *first_touch(hi, lo, int(b.i1) + 1, b.high, b.low))
            ambiguous = outcome == "failed" and i_set >= 0 and hi[i_set] >= b.high and lo[i_set] <= b.low
            next_end = int(bars["i1"].iat[k + 1]) if k + 1 < len(bars) else len(hi) - 1
            geo = (p - b.low) / (b.high - b.low) if s > 0 else (b.high - p) / (b.high - b.low)
            risk = p - b.low if s > 0 else b.high - p
            row = {"market": market, "frame": tf, "close_at": pd.Timestamp(int(b.t_close), tz="UTC"),
                   "date": pd.Timestamp(b.date), "side": s, "case": r["case"].iat[k], "close": p,
                   "c2_high": float(b.high), "c2_low": float(b.low), "outcome": outcome, "geo": geo,
                   "ambiguous": bool(ambiguous), "held_next": outcome == "held" and i_set <= next_end,
                   "failed_next": outcome == "failed" and i_set <= next_end,
                   "at_gap": any(_at_gap(g, s, int(b.t_open), b.high, b.low, p) for g in gap_tables),
                   "risk_spreads": risk / spread if spread > 0 else np.inf,
                   "r_gross": ((1 - geo) / geo if outcome == "held" else -1.0) if geo > 0 else np.nan,
                   "cost_r": spread / risk if risk > 0 else np.nan}
            if above is not None:
                j = int(np.searchsorted(above_close, b.t_close, side="right")) - 1
                row["above"] = int(read[ABOVE[tf]]["side"].iat[j]) * s if j >= 1 else 0
            if row["case"] == "reversal":                         # C1's other extreme: the range's far end
                far = float(r["c1_high"].iat[k]) if s > 0 else float(r["c1_low"].iat[k])
                up, down = (far, b.low) if s > 0 else (b.high, far)
                row["far_outcome"] = _outcome(s, *first_touch(hi, lo, int(b.i1) + 1, up, down))[0]
                row["far_geo"] = (p - b.low) / (far - b.low) if s > 0 else (b.high - p) / (b.high - far)
            rows.append(row)
    return pd.DataFrame(rows)


# ── judging ────────────────────────────────────────────────────────────────

def _excess(t: pd.DataFrame, outcome: str = "outcome", geo: str = "geo") -> tuple[float, int]:
    g = t[t[outcome].isin(("held", "failed"))]
    return (float(((g[outcome] == "held") - g[geo]).mean()) if len(g) else np.nan), len(g)


def judge(t: pd.DataFrame) -> dict:
    """The pass rule's numbers for the calls ``t``, and the companions."""
    g = t[t["outcome"].isin(("held", "failed"))]
    held = (g["outcome"] == "held").to_numpy(float)
    gap = held - g["geo"].to_numpy(float)
    dates = g["date"].to_numpy()
    months = g["date"].dt.to_period("M").astype(str).to_numpy()
    lo, hi = _interval(dates, gap, LEVEL) if len(g) else (np.nan, np.nan)
    mlo, mhi = _interval(months, gap, 0.95) if len(g) else (np.nan, np.nan)
    per = {m: _excess(x) for m, x in t.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    excess = float(gap.mean()) if len(g) else np.nan
    traded = g[g["risk_spreads"] >= MIN_RISK_SPREADS]
    return {"calls": len(t), "resolved": len(g), "open": int((t["outcome"] == "open").sum()),
            "ambiguous": int(g["ambiguous"].sum()), "held": float(held.mean()) if len(g) else np.nan,
            "geo": float(g["geo"].mean()) if len(g) else np.nan, "excess": excess, "lo": lo, "hi": hi,
            "month_lo": mlo, "month_hi": mhi, "per_market": per, "positive": positive,
            "passes": bool(excess > 0 and lo > 0 and positive >= MIN_MARKETS),
            "r_gross": float(traded["r_gross"].mean()), "r_net": float((traded["r_gross"] - traded["cost_r"]).mean()),
            "risk_spreads": float(g["risk_spreads"].median()) if len(g) else np.nan, "traded": len(traded)}


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def render(window: str, t: pd.DataFrame, candles: dict[str, int]) -> str:
    since, until = CALLS_FROM, WINDOWS[window][1]
    lines = [f"Window `{window}`: calls at closes {since} to {until}, outcomes on M1 before {until}.", "",
             f"| Frame | Calls | Resolved (open) | Held | Geometry | Excess (pts) | {100 * LEVEL:.3f}% dates | 95% months "
             f"| Markets > 0 | R gross / net (risk, spreads) | Passes |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    results = {}
    for tf in FRAMES:
        for label, mask in (("", None), (" at a gap", "at_gap")):
            part = t[t["frame"] == tf]
            part = part[part[mask]] if mask else part
            if part.empty:
                lines.append(f"| {tf}{label} | 0 | | | | | | | | | |")
                continue
            r = results[tf + label] = judge(part)
            lines.append(f"| {tf}{label} | {r['calls']:,} | {r['resolved']:,} ({r['open']}) | {r['held']:.1%} | "
                         f"{r['geo']:.1%} | {_pts(r['excess'])} | [{_pts(r['lo'])}, {_pts(r['hi'])}] | "
                         f"[{_pts(r['month_lo'])}, {_pts(r['month_hi'])}] | {r['positive']}/9 | "
                         f"{r['r_gross']:+.3f} / {r['r_net']:+.3f} ({r['risk_spreads']:.1f}) | "
                         f"{'yes' if r['passes'] else 'no'} |")
    lines += ["", "Companions, excess over geometry in points (resolved calls):", "",
              "| Frame | No call | Expansion | Reversal | Bullish | Bearish | Next candle: draw / invalidation | "
              "Reversal to C1's far end | Frame above with / against / none | Ambiguous |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for tf in FRAMES:
        part = t[t["frame"] == tf]
        if part.empty:
            continue
        cells = [f"{1 - len(part) / candles[tf]:.0%}" if candles.get(tf) else "–"]
        for col, value in (("case", "expansion"), ("case", "reversal"), ("side", 1), ("side", -1)):
            x, n = _excess(part[part[col] == value])
            cells.append(f"{_pts(x)} ({n:,})")
        cells.append(f"{part['held_next'].mean():.0%} / {part['failed_next'].mean():.0%}")
        rev = part[part["case"] == "reversal"]
        x, n = _excess(rev, "far_outcome", "far_geo") if "far_outcome" in rev else (np.nan, 0)
        cells.append(f"{_pts(x)} ({n:,})")
        if "above" in part and part["above"].notna().any():
            cells.append(" / ".join(f"{_pts(_excess(part[part['above'] == v])[0])} ({_excess(part[part['above'] == v])[1]:,})"
                                    for v in (1, -1, 0)))
        else:
            cells.append("–")
        cells.append(f"{int(part['ambiguous'].sum()):,}")
        lines.append(f"| {tf} | " + " | ".join(cells) + " |")
    lines += [""] + [f"Excess per market, {name}: " + ", ".join(f"{m} {_pts(v)} ({n:,})" for m, (v, n) in r["per_market"].items())
                     for name, r in results.items()]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(M1_SNAPSHOTS), required=True)
    args = parser.parse_args()
    start, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    since = pd.Timestamp(CALLS_FROM, tz="UTC")
    parts, candles = [], {tf: 0 for tf in FRAMES}
    for market in MARKETS:
        m1 = pd.read_parquet(M1_SNAPSHOTS[args.window] / f"{market}_M1.parquet")
        m1 = drop_rollover(m1[(m1["time"] >= start) & (m1["time"] < until)].reset_index(drop=True))
        t = market_calls(m1, market, since, until, float(m1["spread"].median()))
        for tf, bars in frames(m1).items():
            candles[tf] += int(((bars["t_close"] >= _ns([since])[0]) & (bars["t_close"] <= _ns([until])[0])).sum())
        parts.append(t)
        print(f"{market}: " + ", ".join(f"{tf} {int((t['frame'] == tf).sum()):,}" for tf in FRAMES), flush=True)
    t = pd.concat(parts, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_parquet(OUT / f"bias_{args.window}.parquet")
    print(render(args.window, t, candles))


if __name__ == "__main__":
    main()
