"""The 2018-2024 search: H-V, the side from the frames above, and manipulation against it
(docs/research/SEARCH_2018_2024.md).

A frame's side is set at a turtle soup's close (H-Q's reversal: C2 takes one side of C1, not the other, and closes
back inside) when the frame has no live side: the side, its draw (C1's far end) and its protected swing (C2's
extreme). It ends when price reaches the draw (delivery) or a candle of that frame closes beyond the protected swing
(invalidation). While it is live, the frame's later turtle soups don't replace it.

Each turtle soup on a child frame (H1, H4 and D1 in New York time from the window's M1; W1 on the broker's D1 bars)
is classed by the deciding side at its C2 close, the side of the highest live frame among its own (an earlier
side) and those above it (H4, D1 from the M1; W1 and MN1 from the broker's D1 bars since 2018): **with** it,
**against** it (manipulation, by the trader's rule) or **none**. Its outcome is H-Q's race to its own draw (C1's far
end) before C2's other extreme, against a driftless walk's chance from the close.

Pass: for a cell (the "with" calls of a child frame), the excess over geometry above zero, its trading-date interval
at 98.75% (Holm, four cells) above zero, positive in 6 of the 9 markets, and the "against" calls below it.

    python -m algo_research.search_side --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_bias import GAP_FRAMES, _at_gap, _outcome, calls, drop_rollover, first_touch, frames, gaps
from algo_research.search_crt import M1_SNAPSHOTS, RESAMPLES, SEED, WINDOWS, _interval
from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT, SNAPSHOT, merge_sundays
from algo_research.search_soup import m15, weekly

__all__ = ["FRAMES", "classify", "judge", "market_rows", "monthly", "sides"]

FRAMES = ("H1", "H4", "D1", "W1")
ORDER = ("H1", "H4", "D1", "W1", "MN1")
CALLS_FROM = {"H1": "2021-09-01", "H4": "2021-09-01", "D1": "2021-09-01", "W1": "2018-07-01"}
LEVEL = 1 - 0.05 / len(FRAMES)
SESSIONS = (("Asia", 18, 2), ("London", 2, 7), ("NY morning", 7, 12), ("NY afternoon", 12, 17))
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
MIN_RISK_SPREADS, COST_FLOOR_SPREADS = 2.0, 10.0
_NEVER = np.iinfo(np.int64).max
_MINUTE = 60 * 10**9


# ── the frames ─────────────────────────────────────────────────────────────

def monthly(days: pd.DataFrame) -> pd.DataFrame:
    """The months of the broker's D1 bars (``search_soup.weekly``'s days), the D1 rows being the path."""
    g = days.groupby(pd.DatetimeIndex(days["date"]).to_period("M"), sort=True)
    return pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                         "close": g["close"].last(), "i0": g["i0"].first(), "i1": g["i1"].last(),
                         "t_open": g["t_open"].first(), "t_close": g["t_close"].last(),
                         "date": g["date"].last()}).reset_index(drop=True)


# ── the sides ──────────────────────────────────────────────────────────────

def _events(bars: pd.DataFrame) -> pd.DataFrame:
    """Every turtle soup of ``bars``: its row, side, draw (C1's far end) and protected swing (C2's extreme)."""
    r = calls(bars)
    k = np.nonzero((r["case"] == "reversal").to_numpy())[0]
    side = r["side"].to_numpy()[k]
    return pd.DataFrame({"k": k, "side": side,
                         "draw": np.where(side > 0, r["c1_high"].to_numpy()[k], r["c1_low"].to_numpy()[k]),
                         "protected": np.where(side > 0, bars["low"].to_numpy()[k], bars["high"].to_numpy()[k])})


MODES = ("rule", "noflip", "nodraw", "replace", "first")


def sides(bars: pd.DataFrame, hi: np.ndarray, lo: np.ndarray, known: np.ndarray, below: pd.DataFrame | None = None,
          mode: str = "rule") -> pd.DataFrame:
    """The frame's sides in order: ``start``, ``end``, ``side`` and ``kind`` ("set" by the frame's turtle soup,
    "flip" by the next frame down's). As amended: a side ends at delivery (read when the path row reaching the draw
    is ``known``), at a close of the frame beyond its protected swing, or at the frame's next turtle soup, which
    replaces it; after a delivery the frame waits to flip. Modes: ``rule`` (as amended), ``noflip`` (no flip),
    ``nodraw`` (a flipped side has no draw), ``replace`` (no delivery, invalidation or flip: each turtle soup lasts
    until the next) and ``first`` (as first registered: no flip, and a live side isn't replaced)."""
    ev = _events(bars)
    tc, close, i1 = bars["t_close"].to_numpy(np.int64), bars["close"].to_numpy(float), bars["i1"].to_numpy(int)
    times = tc[ev["k"].to_numpy()]
    if mode == "replace":
        out = pd.DataFrame({"start": times, "end": np.append(times[1:] + 1, _NEVER) if len(times) else times,
                            "side": ev["side"].to_numpy(), "kind": "set"})
        return out.astype({"start": np.int64, "end": np.int64})
    flips = _events(below) if below is not None and mode not in ("noflip", "first") else _events(bars.iloc[:0])
    b_tc = below["t_close"].to_numpy(np.int64) if below is not None else np.array([], np.int64)
    b_i1 = below["i1"].to_numpy(int) if below is not None else np.array([], int)
    f_times, f_side = b_tc[flips["k"].to_numpy()], flips["side"].to_numpy()
    rows, free, waiting = [], np.iinfo(np.int64).min, None
    while True:
        i = int(np.searchsorted(times, free, side="left"))
        own_t = times[i] if i < len(times) else _NEVER
        flip_t, jf = _NEVER, -1
        if waiting is not None:
            hits = np.nonzero((f_side == -waiting[0]) & (f_times >= free))[0]
            if len(hits):
                jf = int(hits[0])
                flip_t = f_times[jf]
        if own_t == _NEVER and flip_t == _NEVER:
            break
        if own_t <= flip_t:
            k, s, draw, prot = ev.iloc[i]
            k, s = int(k), int(s)
            start, path_from, frame_from, kind = tc[k], i1[k] + 1, k + 1, "set"
        else:
            old, j_del, origin = waiting
            seg = b_i1[int(flips["k"].iat[jf])]
            s, draw = -old, origin
            prot = float(hi[j_del:seg + 1].max()) if old > 0 else float(lo[j_del:seg + 1].min())
            start, path_from, kind = flip_t, seg + 1, "flip"
            frame_from = int(np.searchsorted(tc, start, side="right"))
        later = times[times > start]
        t_next = later[0] if len(later) and mode != "first" else _NEVER
        if kind == "flip" and mode == "nodraw":
            j = -1
        else:
            up, down = first_touch(hi, lo, path_from, draw, -np.inf) if s > 0 else \
                first_touch(hi, lo, path_from, np.inf, draw)
            j = up if s > 0 else down
        beyond = close[frame_from:] < prot if s > 0 else close[frame_from:] > prot
        t_del = known[j] if j >= 0 else _NEVER
        t_inv = tc[frame_from + int(np.argmax(beyond))] if beyond.any() else _NEVER
        end = min(t_del, t_inv, t_next)
        rows.append([start, end, s, kind])
        waiting = (s, j, prot) if j >= 0 and t_del <= min(t_inv, t_next) else None
        if end == _NEVER:
            break
        free = end
    return pd.DataFrame(rows, columns=["start", "end", "side", "kind"]).astype({"start": np.int64, "end": np.int64})


def _live(table: pd.DataFrame, t: int, strict: bool) -> int:
    """The side live at ``t`` (0: none). ``strict``: set before ``t``, not at it (the child's own frame)."""
    if table.empty:
        return 0
    j = int(np.searchsorted(table["start"].to_numpy(), t, side="left" if strict else "right")) - 1
    return int(table["side"].iat[j]) if j >= 0 and table["end"].iat[j] > t else 0


def classify(side: int, t: int, above: dict[str, pd.DataFrame], own: pd.DataFrame | None = None,
             frame: str = "") -> tuple[str, str]:
    """``with``, ``against`` or ``none`` for a turtle soup of ``side`` closing at ``t``, and the deciding frame: the
    highest live frame ``above`` (and the child's ``own`` frame, a side set before ``t``, when it is given)."""
    live = {f: _live(tbl, t, False) for f, tbl in above.items()}
    if own is not None:
        live[frame] = _live(own, t, True)
    for f in reversed(ORDER):
        if live.get(f, 0):
            return ("with" if live[f] == side else "against"), f
    return "none", ""


def _label(side: int, live_side: int) -> str:
    return "none" if live_side == 0 else ("with" if live_side == side else "against")


# ── the calls ──────────────────────────────────────────────────────────────

def market_rows(bars: pd.DataFrame, tables: dict[str, dict[str, pd.DataFrame]], hi: np.ndarray, lo: np.ndarray,
                market: str, frame: str, since, until, spread: float, gap_tables=()) -> pd.DataFrame:
    """Every turtle soup of ``frame`` closing in [since, until], classed and raced on the path ``hi``/``lo``.
    ``tables[mode][frame]`` holds the side tables of the child's own frame and those above it, by mode."""
    since, until = (pd.DatetimeIndex([pd.Timestamp(x)]).tz_localize(None if pd.Timestamp(x).tz else "UTC")
                    .as_unit("ns").asi8[0] for x in (since, until))
    ev = _events(bars)
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    tc, to, i1 = bars["t_close"].to_numpy(np.int64), bars["t_open"].to_numpy(np.int64), bars["i1"].to_numpy(int)
    h1, l1 = np.roll(h, 1), np.roll(l, 1)
    names = [f for f in ORDER[ORDER.index(frame) + 1:] if f in tables["rule"]]
    above = {mode: {f: tables[mode][f] for f in names} for mode in tables}
    rows = []
    for k, s, draw, prot in ev.itertuples(index=False):
        t = tc[k]
        if not since <= t <= until:
            continue
        p = c[k]
        cls, decider = classify(s, t, above["rule"])
        own_cls, _ = classify(s, t, above["rule"], tables["rule"][frame], frame)
        live = {f: _live(above["rule"][f], t, False) for f in names}
        live_all = [v for v in [_live(tables["rule"][frame], t, True), *live.values()] if v]
        variants = {mode: classify(s, t, above[mode])[0] for mode in ("noflip", "nodraw", "replace")}
        variants["first"] = classify(s, t, above["first"], tables["first"][frame], frame)[0]

        def race(level):
            above_, below_ = (level, prot) if s > 0 else (prot, level)
            out, i_set = _outcome(s, *first_touch(hi, lo, i1[k] + 1, above_, below_))
            return out, out == "failed" and i_set >= 0 and hi[i_set] >= above_ and lo[i_set] <= below_

        outcome, ambiguous = race(draw)
        geo = abs(p - prot) / abs(draw - prot)
        c2_draw = h[k] if s > 0 else l[k]
        out_c2, _ = race(c2_draw)
        eq = (h1[k] + l1[k]) / 2
        eq_ok = (eq - p) * s > 0
        out_eq, _ = race(eq) if eq_ok else ("", False)
        risk = abs(p - prot)
        ny = pd.Timestamp(int(t), tz="UTC").tz_convert("America/New_York") - pd.Timedelta(minutes=1)
        date = pd.Timestamp(bars["date"].iat[k])
        rows.append({
            "market": market, "frame": frame, "side": s, "date": date, "close_at": pd.Timestamp(int(t), tz="UTC"),
            "class": cls, "decider": decider, "class_own": own_cls,
            "class_next": _label(s, live[names[0]]) if names else "none",
            "agree": len(set(live_all)) == 1 if live_all else False,
            **{f"class_{mode}": v for mode, v in variants.items()},
            "outcome": outcome, "geo": geo, "ambiguous": ambiguous,
            "out_c2": out_c2, "geo_c2": abs(p - prot) / abs(c2_draw - prot) if c2_draw != prot else np.nan,
            "out_eq": out_eq, "geo_eq": abs(p - prot) / abs(eq - prot) if eq_ok else np.nan,
            "at_gap": any(_at_gap(g, s, int(to[k]), h[k], l[k], p) for g in gap_tables),
            "hour": ny.hour, "weekday": date.dayofweek, "week_of_month": (date.day - 1) // 7 + 1,
            "risk_spreads": risk / spread if spread > 0 else np.inf,
            "r_gross": (1 - geo) / geo if outcome == "held" else -1.0,
            "fade_r": geo / (1 - geo) if outcome == "failed" and not ambiguous and geo < 1 else -1.0,
            "cost_r": spread / risk if risk > 0 else np.nan})
    return pd.DataFrame(rows)


# ── judging ────────────────────────────────────────────────────────────────

def _resolved(t: pd.DataFrame, outcome: str = "outcome") -> pd.DataFrame:
    return t[t[outcome].isin(("held", "failed"))]


def _gaps(t: pd.DataFrame, outcome: str = "outcome", geo: str = "geo") -> pd.DataFrame:
    g = _resolved(t, outcome)
    return g.assign(gap=(g[outcome] == "held").to_numpy(float) - g[geo].to_numpy(float))


def _excess(t: pd.DataFrame, outcome: str = "outcome", geo: str = "geo") -> tuple[float, int]:
    g = _gaps(t, outcome, geo)
    return (float(g["gap"].mean()) if len(g) else np.nan), len(g)


def _diff_interval(a: pd.DataFrame, b: pd.DataFrame, level: float) -> tuple[float, float]:
    """The ``level`` interval of mean(a.gap) - mean(b.gap), resampling trading dates across both."""
    if a.empty or b.empty:
        return np.nan, np.nan
    units, index = np.unique(np.concatenate([a["date"].to_numpy(), b["date"].to_numpy()]), return_inverse=True)
    ia, ib = index[:len(a)], index[len(a):]
    n = len(units)
    sa, ca = np.bincount(ia, a["gap"].to_numpy(), n), np.bincount(ia, minlength=n).astype(float)
    sb, cb = np.bincount(ib, b["gap"].to_numpy(), n), np.bincount(ib, minlength=n).astype(float)
    w = np.random.default_rng(SEED).multinomial(n, np.full(n, 1 / n), size=RESAMPLES).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = (w @ sa) / (w @ ca) - (w @ sb) / (w @ cb)
    tail = 100 * (1 - level) / 2
    lo, hi = np.percentile(draws[np.isfinite(draws)], [tail, 100 - tail])
    return float(lo), float(hi)


def judge(t: pd.DataFrame) -> dict:
    """The pass rule's numbers for one child frame's calls ``t``."""
    w, a, n = (_gaps(t[t["class"] == x]) for x in ("with", "against", "none"))
    enough = w["date"].nunique() > 1
    lo, hi = _interval(w["date"].to_numpy(), w["gap"].to_numpy(), LEVEL) if enough else (np.nan, np.nan)
    months = w["date"].dt.to_period("M").astype(str).to_numpy()
    mlo, mhi = _interval(months, w["gap"].to_numpy(), 0.95) if enough else (np.nan, np.nan)
    per = {m: (float(x["gap"].mean()), len(x)) for m, x in w.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    excess = float(w["gap"].mean()) if len(w) else np.nan
    against = float(a["gap"].mean()) if len(a) else np.nan
    dlo, dhi = _diff_interval(w, a, LEVEL)
    traded = w[w["risk_spreads"] >= MIN_RISK_SPREADS]
    floor = w[w["risk_spreads"] >= COST_FLOOR_SPREADS]
    fade = a[a["risk_spreads"] >= MIN_RISK_SPREADS]
    return {"calls": int((t["class"] == "with").sum()), "resolved": len(w), "held": float((w["outcome"] == "held").mean()),
            "geo": float(w["geo"].mean()), "excess": excess, "lo": lo, "hi": hi, "month_lo": mlo, "month_hi": mhi,
            "per_market": per, "positive": positive, "against": against, "n_against": len(a),
            "none": float(n["gap"].mean()) if len(n) else np.nan, "n_none": len(n),
            "diff": excess - against, "diff_lo": dlo, "diff_hi": dhi,
            "passes": bool(excess > 0 and lo > 0 and positive >= MIN_MARKETS and excess - against > 0),
            "r_gross": float(traded["r_gross"].mean()) if len(traded) else np.nan,
            "r_net": float((traded["r_gross"] - traded["cost_r"]).mean()) if len(traded) else np.nan,
            "r_net_floor": float((floor["r_gross"] - floor["cost_r"]).mean()) if len(floor) else np.nan,
            "floor": len(floor), "risk_spreads": float(w["risk_spreads"].median()) if len(w) else np.nan,
            "fade_r": float(fade["fade_r"].mean()) if len(fade) else np.nan}


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def _r(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{x:+.3f}"


def _session(hour: pd.Series, start: int, end: int) -> pd.Series:
    return (hour >= start) & (hour < end) if start < end else (hour >= start) | (hour < end)


def companions() -> list[tuple[str, callable, tuple]]:
    """(name, the calls it keeps, (outcome, geometry) columns)."""
    rows = [("with", lambda t: t["class"] == "with", ()), ("against", lambda t: t["class"] == "against", ()),
            ("none", lambda t: t["class"] == "none", ())]
    for f in ORDER[1:]:
        for cls in ("with", "against"):
            rows.append((f"{cls}, decided by {f}",
                         lambda t, f=f, cls=cls: (t["class"] == cls) & (t["decider"] == f), ()))
    variants = (("first", "as first registered (own frame, no flip, a live side kept)"),
                ("own", "the child's own frame included"), ("next", "the next frame up only"),
                ("noflip", "sides without the flip"), ("nodraw", "flipped sides with no draw"),
                ("replace", "sides end only when replaced"))
    for col, name in variants:
        for cls in ("with", "against"):
            rows.append((f"{cls}, {name}", lambda t, col=col, cls=cls: t[f"class_{col}"] == cls, ()))
    rows += [("with, every live side agreeing", lambda t: (t["class"] == "with") & t["agree"], ()),
             ("with, live sides mixed", lambda t: (t["class"] == "with") & ~t["agree"], ()),
             ("with, draw at C2's extreme", lambda t: t["class"] == "with", ("out_c2", "geo_c2")),
             ("against, draw at C2's extreme", lambda t: t["class"] == "against", ("out_c2", "geo_c2")),
             ("with, draw at C1's equilibrium", lambda t: t["class"] == "with", ("out_eq", "geo_eq")),
             ("against, draw at C1's equilibrium", lambda t: t["class"] == "against", ("out_eq", "geo_eq")),
             ("with, long", lambda t: (t["class"] == "with") & (t["side"] > 0), ()),
             ("with, short", lambda t: (t["class"] == "with") & (t["side"] < 0), ()),
             ("with, at a gap", lambda t: (t["class"] == "with") & t["at_gap"], ()),
             ("with, not at a gap", lambda t: (t["class"] == "with") & ~t["at_gap"], ())]
    for name, start, end in SESSIONS:
        rows.append((f"with, {name}", lambda t, s=start, e=end: (t["class"] == "with") & _session(t["hour"], s, e)
                     & t["frame"].isin(("H1", "H4")), ()))
    for d, name in enumerate(WEEKDAYS):
        rows.append((f"with, {name}", lambda t, d=d: (t["class"] == "with") & (t["weekday"] == d)
                     & (t["frame"] != "W1"), ()))
    for wk in range(1, 6):
        rows.append((f"with, week {wk} of the month", lambda t, wk=wk: (t["class"] == "with")
                     & (t["week_of_month"] == wk) & (t["frame"] == "W1"), ()))
    return rows


def render(t: pd.DataFrame) -> str:
    lines = [f"| Frame | With: calls (resolved) | Held | Geometry | Excess (pts) | {100 * LEVEL:.2f}% dates | 95% months "
             "| Markets > 0 | Against (n) | None (n) | With − against [98.75%] | R gross / net (risk, spreads) "
             "| R net, risk >= 10 spreads (n) | Fade of against, R gross | Passes |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    results = {}
    for tf in FRAMES:
        part = t[t["frame"] == tf]
        if part.empty or not (part["class"] == "with").any():
            lines.append(f"| {tf} | 0 |" + " |" * 14)
            continue
        r = results[tf] = judge(part)
        lines.append(f"| {tf} | {r['calls']:,} ({r['resolved']:,}) | {r['held']:.1%} | {r['geo']:.1%} | "
                     f"{_pts(r['excess'])} | [{_pts(r['lo'])}, {_pts(r['hi'])}] | "
                     f"[{_pts(r['month_lo'])}, {_pts(r['month_hi'])}] | {r['positive']}/9 | "
                     f"{_pts(r['against'])} ({r['n_against']:,}) | {_pts(r['none'])} ({r['n_none']:,}) | "
                     f"{_pts(r['diff'])} [{_pts(r['diff_lo'])}, {_pts(r['diff_hi'])}] | "
                     f"{_r(r['r_gross'])} / {_r(r['r_net'])} ({r['risk_spreads']:.1f}) | "
                     f"{_r(r['r_net_floor'])} ({r['floor']:,}) | {_r(r['fade_r'])} | {'yes' if r['passes'] else 'no'} |")
    lines += ["", "Companions, excess over geometry in points (resolved calls):", "",
              "| Calls | " + " | ".join(FRAMES) + " |", "|---" * (len(FRAMES) + 1) + "|"]
    for name, mask, cols in companions():
        cells = []
        for tf in FRAMES:
            part = t[t["frame"] == tf]
            keep = mask(part)
            part = part[keep.to_numpy(bool) if isinstance(keep, pd.Series) else np.full(len(part), bool(keep))]
            x, n = _excess(part, *cols)
            cells.append(f"{_pts(x)} ({n:,})" if n else "–")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    shares = ["| Share of turtle soups | " + " | ".join(FRAMES) + " |", "|---" * (len(FRAMES) + 1) + "|"]
    for cls in ("with", "against", "none"):
        shares.append(f"| {cls} | " + " | ".join(f"{(t[t['frame'] == tf]['class'] == cls).mean():.0%}"
                                                  for tf in FRAMES) + " |")
    lines += [""] + shares
    lines += [""] + [f"Excess per market, with, {tf}: " + ", ".join(f"{m} {_pts(v)} ({n:,})"
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
        hi, lo = m1["high"].to_numpy(float), m1["low"].to_numpy(float)
        known = pd.DatetimeIndex(m1["time"]).as_unit("ns").asi8 + _MINUTE
        d1 = merge_sundays(pd.read_parquet(SNAPSHOT / f"{market}_D1.parquet"))
        d1 = d1[pd.to_datetime(d1["time"], utc=True) < until].reset_index(drop=True)
        weeks, days = weekly(d1)
        months = monthly(days)
        dhi, dlo = days["high"].to_numpy(float), days["low"].to_numpy(float)
        dknown = days["t_close"].to_numpy(np.int64)
        f["M15"] = m15(m1)
        tables = {mode: {**{tf: sides(f[tf], hi, lo, known, f[below], mode)
                            for tf, below in (("H1", "M15"), ("H4", "H1"), ("D1", "H4"))},
                         "W1": sides(weeks, dhi, dlo, dknown, days, mode),
                         "MN1": sides(months, dhi, dlo, dknown, weeks, mode)} for mode in MODES}
        g = {tf: gaps(f[tf]) for tf in ("H1", "H4", "D1", "W1")}
        for tf in FRAMES:
            if tf == "W1":
                parts.append(market_rows(weeks, tables, dhi, dlo, market, tf, CALLS_FROM[tf], until, spread))
            else:
                parts.append(market_rows(f[tf], tables, hi, lo, market, tf, CALLS_FROM[tf], until, spread,
                                         [g[x] for x in GAP_FRAMES[tf]]))
        done = pd.concat(parts[-4:], ignore_index=True)
        print(f"{market}: " + ", ".join(f"{tf} {int((done['frame'] == tf).sum()):,} "
                                        f"({int(((done['frame'] == tf) & (done['class'] == 'with')).sum()):,} with)"
                                        for tf in FRAMES), flush=True)
    t = pd.concat(parts, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_parquet(OUT / f"side_{args.window}.parquet")
    print(render(t))


if __name__ == "__main__":
    main()
