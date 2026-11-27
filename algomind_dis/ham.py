"""H-AM: AlgoMindDIS v3, the draw first, over history (algomind-dis Requirement 18; registered 2026-11-07 before
its code, docs/research/SEARCH_2018_2024.md). Try 31.

v3 (``algomind_dis.draw``) runs at every D1 close of Yahoo's daily history for the nine markets (H-AF's data and
day, ``search_state.load`` -> ``frames.from_daily``) to 2022-12-30. Calls and weeks are scored from 1996-01-01 and a
market's 53rd week to 2022-12-31, with H-AE's scorer (``algo_research.search_narrative``):
- **cell 1, the draw (A1, B1):** every pick, raced from the next D1 candle: held when a candle trades at the draw
  before one closes beyond the protected level (a day doing both fails), ignoring the hold's ends. The control is
  ``control_share``: every D1 close of the market in the window as a start, on the call's side, with its draw and
  protected level at the call's distances in 20-day average ranges. Open races are dropped and counted;
- **cell 2, the weekly side (A2, B2):** each week whose open finds a held draw (at the last D1 close before it),
  closed beyond its open on that side, against the market's share of such weeks over the window (drift).

A cell passes when its excess is above zero, its interval over calendar months at 98.75% (Bonferroni for four) is
above zero, and it is positive in at least 6 of 9 markets. H-AM passes if any cell does.

The control is H-AE's, computed faster and exactly (``Control``): from each start, the rows where the high (low)
and the close set a new extreme, so the first row trading at a draw or closing beyond a protected level is a
lookup. Every market checks a sample of its calls against ``control_share`` itself and stops on any difference.

    python -m algomind_dis.ham [--workers 3]     # data/research/search/ham_*_develop.parquet and the report
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from algo_research.search_crt import _interval
from algo_research.search_d1 import MARKETS, MIN_MARKETS
from algo_research.search_narrative import ADR_N, FOLDS, WARM_WEEKS, WINDOW, control_share, race
from algo_research.search_state import load
from algomind_dis.draw import RULES
from algomind_dis.draw import run as draw_run
from algomind_dis.frames import from_daily

__all__ = ["Control", "LEVEL", "OUT", "judge", "market_tables", "report", "run"]

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "search"
LEVEL = 0.9875                                   # Bonferroni for four cells
JUDGED = ("A", "B")
#: Calls per rule and market whose control is recomputed with ``control_share`` and compared.
VERIFY = 12
_SIDE = {"BULLISH": 1, "BEARISH": -1}
_NEVER = np.iinfo(np.int64).max
_DAY = 86_400 * 10**9


# ── the control, exactly and fast ──────────────────────────────────────────

def _ladder(x: np.ndarray, start: int, stop: float, up: bool) -> tuple[np.ndarray, np.ndarray]:
    """The records of the running max (``up``) or min of ``x[start:]``: their values and rows, through the first
    at or beyond ``stop``."""
    n, a, w = len(x), start, 256
    best = -np.inf if up else np.inf
    vals, rows = [], []
    while a < n:
        b = min(n, a + w)
        seg = x[a:b]
        acc = (np.maximum if up else np.minimum).accumulate(np.r_[best, seg])
        new = np.flatnonzero(acc[1:] > acc[:-1]) if up else np.flatnonzero(acc[1:] < acc[:-1])
        v = seg[new]
        reach = v >= stop if up else v <= stop
        if reach.any():
            j = int(np.argmax(reach)) + 1
            vals.append(v[:j])
            rows.append(a + new[:j])
            break
        vals.append(v)
        rows.append(a + new)
        best, a, w = acc[-1], b, 2 * w
    if not vals:
        return np.empty(0), np.empty(0, np.int64)
    return np.concatenate(vals), np.concatenate(rows).astype(np.int64)


def _pad(ladders: list, pad: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    k = max(1, max(len(v) for v, _ in ladders)) if ladders else 1
    vals = np.full((len(ladders), k), pad)
    rows = np.full((len(ladders), k), _NEVER, dtype=np.int64)
    lens = np.zeros(len(ladders), dtype=np.int64)
    for i, (v, r) in enumerate(ladders):
        vals[i, :len(v)], rows[i, :len(r)], lens[i] = v, r, len(v)
    return vals, rows, lens


class Control:
    """``control_share`` for many calls on one market's starts. ``cap``: no call's distance (draw or protected, in
    average ranges) exceeds it."""

    def __init__(self, hi: np.ndarray, lo: np.ndarray, cl: np.ndarray, starts: np.ndarray, closes: np.ndarray,
                 adrs: np.ndarray, cap: float):
        self.closes, self.adrs, self.cap = np.asarray(closes, float), np.asarray(adrs, float), float(cap)
        self._idx = np.arange(len(starts))
        self.ladders = {}
        for side in (1, -1):
            hit = [_ladder(hi if side > 0 else lo, int(st), p + side * cap * adr, up=side > 0)
                   for st, p, adr in zip(starts, self.closes, self.adrs)]
            out = [_ladder(cl, int(st), p - side * cap * adr, up=side < 0)
                   for st, p, adr in zip(starts, self.closes, self.adrs)]
            self.ladders[side] = (_pad(hit, np.inf if side > 0 else -np.inf),
                                  _pad(out, -np.inf if side > 0 else np.inf))

    def _first(self, ladder, k: np.ndarray) -> np.ndarray:
        vals, rows, lens = ladder
        return np.where(k < lens, rows[self._idx, np.minimum(k, vals.shape[1] - 1)], _NEVER)

    def share(self, side: int, a: float, b: float) -> tuple[float, int]:
        if max(a, b) > self.cap:
            raise ValueError(f"a call {a:.3f}/{b:.3f} average ranges away is beyond the ladders' cap {self.cap}")
        draw = self.closes + side * a * self.adrs
        prot = self.closes - side * b * self.adrs
        hit, out = self.ladders[side]
        if side > 0:
            kh, ko = (hit[0] < draw[:, None]).sum(1), (out[0] >= prot[:, None]).sum(1)
        else:
            kh, ko = (hit[0] > draw[:, None]).sum(1), (out[0] <= prot[:, None]).sum(1)
        ih, io = self._first(hit, kh), self._first(out, ko)
        held = int((ih < io).sum())
        n = int(((ih != _NEVER) | (io != _NEVER)).sum())
        return (held / n if n else float("nan")), n


# ── one market ─────────────────────────────────────────────────────────────

def market_tables(market: str, days: Optional[pd.DataFrame] = None, rules=RULES,
                  verify: int = VERIFY) -> dict[str, pd.DataFrame]:
    days = load(market) if days is None else days
    days = days[pd.to_datetime(days["date"]) < WINDOW[1]]
    f = from_daily(market, days)
    tl = draw_run(market, f, rules)
    closes, picks = tl["closes"], tl["picks"]
    d1, w1 = f.full["D1"], f.full["W1"]
    t_open, t_close = d1.t, d1.end
    hi, lo, cl = d1.h, d1.l, d1.c
    adr_rows = pd.Series(hi - lo).rolling(ADR_N).mean().to_numpy()
    first = max(WINDOW[0], pd.Timestamp(int(w1.t[min(WARM_WEEKS, len(w1) - 1)]), tz="UTC").tz_localize(None))
    t0, t1 = int(pd.Timestamp(first, tz="UTC").value), int(pd.Timestamp(WINDOW[1], tz="UTC").value)

    def adr_at(t: int) -> float:
        k = int(np.searchsorted(t_close, t, side="right")) - 1
        return float(adr_rows[k]) if k >= 0 else float("nan")

    in_d1 = (t_open >= t0) & (t_close <= t1)
    c_starts = np.searchsorted(t_open, t_close[in_d1], side="left")
    c_closes = cl[in_d1]
    c_adrs = np.array([adr_at(int(t)) for t in t_close[in_d1]])
    ok = (c_starts < len(cl)) & np.isfinite(c_adrs)
    c_starts, c_closes, c_adrs = c_starts[ok], c_closes[ok], c_adrs[ok]
    r_t = closes["t"].to_numpy(np.int64)

    # cell 1: every pick
    calls = []
    for p in picks.itertuples():
        t = int(p.t)
        if not (t0 <= t < t1):
            continue
        side, adr = _SIDE[p.side], adr_at(t)
        a, b = side * (p.draw - p.close) / adr, side * (p.close - p.protected) / adr
        outcome, _ = race(hi, lo, cl, int(np.searchsorted(t_open, t, side="left")), side, p.draw, p.protected)
        end = np.searchsorted(r_t, int(p.end_t), "left") if np.isfinite(p.end_t) else np.nan
        calls.append({"market": market, "rule": p.rule, "side": side, "t": pd.Timestamp(t, tz="UTC").tz_localize(None),
                      "draw": p.draw, "protected": p.protected, "a": a, "b": b, "outcome": outcome,
                      "held": {"held": 1.0, "failed": 0.0}.get(outcome, np.nan), "control": np.nan, "n_control": 0,
                      "tf": p.tf, "kind": p.kind, "source": p.source, "equal": bool(p.equal),
                      "significance": p.significance, "protected_from": p.protected_from, "ended": p.ended,
                      "live_closes": end - np.searchsorted(r_t, t, "left") if np.isfinite(end) else np.nan})
    calls = pd.DataFrame(calls)
    verified = 0
    if len(calls):
        cap = float(np.ceil(np.nanmax(calls[["a", "b"]].to_numpy())) + 1.0)
        ctl = Control(hi, lo, cl, c_starts, c_closes, c_adrs, cap)
        got = [ctl.share(int(s), float(a), float(b)) for s, a, b in calls[["side", "a", "b"]].itertuples(index=False)]
        calls["control"], calls["n_control"] = [g[0] for g in got], [g[1] for g in got]
        for r, g in calls.groupby("rule"):
            for i in np.unique(np.linspace(0, len(g) - 1, min(verify, len(g))).astype(int)):
                x = g.iloc[i]
                want = control_share(hi, lo, cl, c_starts, c_closes, c_adrs, int(x["side"]), x["a"], x["b"])
                have = (x["control"], x["n_control"])
                same = want[1] == have[1] and (want[0] == have[0] or (np.isnan(want[0]) and np.isnan(have[0])))
                if not same:
                    raise AssertionError(f"{market} {r} {x['t']}: control_share {want} but the ladders {have}")
                verified += 1

    # cell 2: each week's open
    meta = {(p.rule, int(p.t)): p for p in picks.itertuples()}
    weeks = []
    for i in range(len(w1)):
        wo, wc = int(w1.t[i]), int(w1.end[i])
        if not (wo >= t0 and wc <= t1):
            continue
        k = int(np.searchsorted(r_t, wo, side="right")) - 1
        base = {"market": market, "t": pd.Timestamp(wo, tz="UTC").tz_localize(None),
                "up": float(w1.c[i] > w1.o[i]), "down": float(w1.c[i] < w1.o[i])}
        w1_dir = closes["w1"].iloc[k] if k >= 0 else "NEUTRAL"
        weeks.append({**base, "rule": "W1", "side": _SIDE.get(w1_dir, 0)})
        for r in rules:
            side = closes[f"{r}_side"].iloc[k] if k >= 0 else None
            row = {**base, "rule": r, "side": _SIDE.get(side, 0)}
            if side is not None:
                p = meta[(r, int(closes[f"{r}_since"].iloc[k]))]
                row.update(tf=p.tf, kind=p.kind, source=p.source, equal=bool(p.equal), significance=p.significance,
                           w1_side=_SIDE.get(w1_dir, 0))
            weeks.append(row)
    weeks = pd.DataFrame(weeks)
    for col in ("tf", "kind", "source", "equal", "significance", "w1_side"):
        if col not in weeks:
            weeks[col] = np.nan
    if not weeks.empty:
        base = weeks[weeks["rule"] == "W1"]
        up, down = base["up"].mean(), base["down"].mean()
        weeks["expected"] = np.where(weeks["side"] > 0, up, np.where(weeks["side"] < 0, down, np.nan))
        weeks["hit"] = np.where(weeks["side"] > 0, weeks["up"], np.where(weeks["side"] < 0, weeks["down"], np.nan))
    years = (t1 - t0) / (365.25 * _DAY)
    info = pd.DataFrame([{"market": market, "years": years, "verified": verified, "first": first}])
    return {"calls": calls, "weeks": weeks, "picks": picks, "closes": closes.assign(market=market), "info": info}


def _one(market: str) -> dict[str, pd.DataFrame]:
    return market_tables(market)


def run(markets=MARKETS, workers: int = 1, log=print) -> dict[str, pd.DataFrame]:
    parts, t = [], time.time()
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for m, part in zip(markets, ex.map(_one, markets)):
                parts.append(part)
                log(f"{m}: {len(part['calls'])} calls ({time.time() - t:.0f}s)")
    else:
        for m in markets:
            parts.append(market_tables(m))
            log(f"{m}: {len(parts[-1]['calls'])} calls ({time.time() - t:.0f}s)")
    return {k: pd.concat([p[k] for p in parts if not p[k].empty], ignore_index=True) for k in parts[0]}


# ── the judgement ──────────────────────────────────────────────────────────

def judge(t: pd.DataFrame, value: str, base: str, level: float = LEVEL) -> dict:
    """H-AE's judgement at ``level``: the excess of ``value`` over ``base``, its interval over calendar months, the
    markets above zero and the pass."""
    g = t.dropna(subset=[value, base])
    if g.empty:
        return {"n": 0}
    excess = (g[value] - g[base]).to_numpy(float)
    lo, hi = _interval(g["t"].dt.to_period("M").astype(str).to_numpy(), excess, level)
    per = {m: (float((x[value] - x[base]).mean()), len(x)) for m, x in g.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    mean = float(excess.mean())
    return {"n": len(g), "value": float(g[value].mean()), "base": float(g[base].mean()), "excess": mean, "lo": lo,
            "hi": hi, "per_market": per, "positive": positive,
            "passes": bool(mean > 0 and lo > 0 and positive >= MIN_MARKETS)}


def _pts(x) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:+.1f}"


def _row(name: str, r: dict, judged: bool = False) -> str:
    if not r.get("n"):
        return f"| {name} | 0 | – | – | – | – | – |" + (" – |" if judged else "")
    out = (f"| {name} | {r['n']:,} | {r['value']:.1%} | {r['base']:.1%} | {_pts(r['excess'])} | "
           f"[{_pts(r['lo'])}, {_pts(r['hi'])}] | {r['positive']}/{len(r['per_market'])} |")
    return out + (f" {'**yes**' if r['passes'] else 'no'} |" if judged else "")


_HEAD = "| | n | held / hit | control / drift | excess (pts) | 98.75% months | markets > 0 |\n|---|---|---|---|---|---|---|"


def _cells(calls: pd.DataFrame, weeks: pd.DataFrame, rule: str) -> tuple[dict, dict]:
    c = calls[calls["rule"] == rule]
    w = weeks[(weeks["rule"] == rule) & (weeks["side"] != 0)]
    return judge(c, "held", "control"), judge(w, "hit", "expected")


def report(t: dict[str, pd.DataFrame], haf_weeks: Optional[pd.DataFrame] = None) -> tuple[str, bool]:
    calls, weeks, info = t["calls"], t["weeks"], t["info"]
    cells = {}
    for r in JUDGED:
        cells[f"{r}1"], cells[f"{r}2"] = _cells(calls, weeks, r)
    passes = any(c.get("passes") for c in cells.values())
    names = {"A1": "A1: the draw alone, the draw before invalidation vs matched starts",
             "A2": "A2: the draw alone, weeks held vs drift",
             "B1": "B1: the draw with structure, the draw before invalidation vs matched starts",
             "B2": "B2: the draw with structure, weeks held vs drift"}
    out = [f"**H-AM {'passes' if passes else 'fails'}.**", "",
           "| cell | n | held / hit | control / drift | excess (pts) | 98.75% months | markets > 0 | passes |",
           "|---|---|---|---|---|---|---|---|"]
    out += [_row(names[k], v, judged=True) for k, v in cells.items()]
    out += ["", "**Each market** (excess in points, n):", "", "| market | A1 | A2 | B1 | B2 |", "|---|---|---|---|---|"]
    for m in MARKETS:
        line = []
        for k in cells:
            v = cells[k].get("per_market", {}).get(m)
            line.append(f"{_pts(v[0])} ({v[1]})" if v else "–")
        out.append(f"| {m} | " + " | ".join(line) + " |")

    out += ["", "**Beside it, not judged.**", "", "The geometric pick and structure alone:", "", _HEAD]
    c1, c2 = _cells(calls, weeks, "NEAREST")
    out += [_row("NEAREST cell 1", c1), _row("NEAREST cell 2", c2)]
    s = weeks[(weeks["rule"] == "W1") & (weeks["side"] != 0)]
    b_weeks = weeks[(weeks["rule"] == "B") & (weeks["side"] != 0)][["market", "t"]]
    on_b = s.merge(b_weeks, on=["market", "t"])
    off_b = s.merge(b_weeks, on=["market", "t"], how="left", indicator=True)
    off_b = off_b[off_b["_merge"] == "left_only"]
    a = weeks[(weeks["rule"] == "A") & (weeks["side"] != 0)]
    out += [_row("W1 structure alone, all its weeks", judge(s, "hit", "expected")),
            _row("W1 structure on B's weeks", judge(on_b, "hit", "expected")),
            _row("W1 structure on the weeks B holds nothing", judge(off_b, "hit", "expected")),
            _row("A's weeks agreeing with W1 structure", judge(a[a["w1_side"] == a["side"]], "hit", "expected")),
            _row("A's weeks against W1 structure", judge(a[a["w1_side"] == -a["side"]], "hit", "expected")),
            _row("A's weeks with W1 NEUTRAL", judge(a[a["w1_side"] == 0], "hit", "expected"))]
    if haf_weeks is not None and len(haf_weeks):
        v1 = haf_weeks[haf_weeks["side"] != 0][["market", "t", "side", "hit"]].rename(
            columns={"side": "v1_side", "hit": "v1_hit"})
        for r in JUDGED:
            g = weeks[(weeks["rule"] == r) & (weeks["side"] != 0)].merge(v1, on=["market", "t"])
            if len(g):
                out.append(f"- v1 (H-AF) on the {len(g)} weeks both it and {r} hold a side: v1 hit "
                           f"{g['v1_hit'].mean():.1%}, {r} hit {g['hit'].mean():.1%}, the same side "
                           f"{(g['v1_side'] == g['side']).mean():.0%}")

    out += ["", "**By the draw** (cell 1 and cell 2):", "", _HEAD]
    def label(x: pd.Series) -> pd.Series:
        return x.astype(float).round(2).astype(str) if x.name == "significance" else x.astype(str)

    for r in JUDGED:
        c = calls[calls["rule"] == r]
        w = weeks[(weeks["rule"] == r) & (weeks["side"] != 0)]
        for col in ("tf", "kind", "equal", "significance"):
            ck, wk = label(c[col]), label(w[col])
            for v in sorted(set(ck)):
                out.append(_row(f"{r}1 {col} {v}", judge(c[ck == v], "held", "control")))
            for v in sorted(set(wk)):
                out.append(_row(f"{r}2 {col} {v}", judge(w[wk == v], "hit", "expected")))

    out += ["", "**Buys, sells and H-AE's folds:**", "", _HEAD]
    edges = [pd.Timestamp(x) for _, x in FOLDS] + [WINDOW[1]]
    for r in JUDGED:
        c = calls[calls["rule"] == r]
        w = weeks[(weeks["rule"] == r) & (weeks["side"] != 0)]
        for sd, name in ((1, "buys"), (-1, "sells")):
            out += [_row(f"{r}1 {name}", judge(c[c["side"] == sd], "held", "control")),
                    _row(f"{r}2 {name}", judge(w[w["side"] == sd], "hit", "expected"))]
        for (name, _), lo_, hi_ in zip(FOLDS, edges[:-1], edges[1:]):
            out += [_row(f"{r}1 {name}", judge(c[(c["t"] >= lo_) & (c["t"] < hi_)], "held", "control")),
                    _row(f"{r}2 {name}", judge(w[(w["t"] >= lo_) & (w["t"] < hi_)], "hit", "expected"))]

    out += ["", "**The picks:**", ""]
    market_years = float(info["years"].sum())
    n_weeks = (weeks["rule"] == "W1").sum()
    for r in RULES:
        c = calls[calls["rule"] == r]
        w = weeks[(weeks["rule"] == r) & (weeks["side"] != 0)]
        if c.empty:
            out.append(f"- {r}: no picks")
            continue
        out.append(f"- {r}: {len(c):,} picks ({len(c) / market_years:.1f} a market-year), weeks with a side "
                   f"{len(w) / max(n_weeks, 1):.0%}; median draw {c['a'].median():.2f} ADR, protected "
                   f"{c['b'].median():.2f} ADR; protected from {c['protected_from'].str.startswith('D1').mean():.0%} "
                   f"D1 swings; ended {c['ended'].value_counts().to_dict()}; races {c['outcome'].value_counts().to_dict()}"
                   f" (open races dropped); median closes held {c['live_closes'].median():.0f}")
    out.append(f"- The control: {int(info['verified'].sum())} calls recomputed with `control_share`, all identical")
    return "\n".join(out), passes


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(prog="python -m algomind_dis.ham", description=__doc__.splitlines()[0])
    p.add_argument("--markets", default=",".join(MARKETS))
    p.add_argument("--workers", type=int, default=1)
    args = p.parse_args(argv)
    tables = run(tuple(args.markets.split(",")), workers=args.workers)
    OUT.mkdir(parents=True, exist_ok=True)
    for k, v in tables.items():
        v.to_parquet(OUT / f"ham_{k}_develop.parquet", index=False)
    haf = OUT / "haf_weeks_develop.parquet"
    text, _ = report(tables, pd.read_parquet(haf) if haf.exists() else None)
    (OUT / "ham_report_develop.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
