"""H-AF: AlgoMindDIS v1 over history (algomind-dis Requirement 15, §16; registered 2026-11-03 before its code).

The timeline runs from each market's first bar of Yahoo's daily history (H-AE's data and day) to 2022-12-30, and
is scored with H-AE's own scorer (``algo_research.search_narrative``: ``race``, ``control_share``, ``judge``):
- **cell 1, the hypothesis:** each close where a side is established (a new ``since``: from UNDETERMINED, NEUTRAL,
  or the other side out of TRANSITIONAL; a challenge fading back keeps its call). The race from the next day: held
  when a D1 candle trades at the draw before one closes beyond the protected level, against every D1 close of the
  same market in the window as a start at the call's distances in 20-day average ranges;
- **cell 2, the weekly side:** each week whose open finds an ACTIVE side, its close against drift.

Passes if either cell's excess is above zero with its 97.5% interval over calendar months, in 6 of 9 markets.
Reported beside it, never judged: §16.2's state quality, §16.4's baselines (no filter; the last W1 candle's
LE-D15 trend), buys and sells, each market, H-AE's folds, each category alone, agreement with reader v0.

    python -m algomind_dis.replay              # writes data/research/search/haf_*_develop.parquet and the report
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from algo_research.search_d1 import MARKETS
from algo_research.search_narrative import ADR_N, FOLDS, LEVEL, WARM_WEEKS, WINDOW, control_share, judge, race
from algo_research.search_state import load
from algomind_dis.frames import from_daily
from algomind_dis.settings import V1, Settings
from algomind_dis.state import run as timeline

__all__ = ["OUT", "market_tables", "report", "run"]

OUT = Path(__file__).resolve().parents[1] / "data" / "research" / "search"
_DAY = 86_400 * 10**9
_SIDE = {"BULLISH": 1, "BEARISH": -1}
#: §16.2: a challenge that turns to the other side within this many closes counts as a reversal.
CATEGORIES = tuple(V1.category_weights)


def market_tables(market: str, days: Optional[pd.DataFrame] = None, s: Settings = V1) -> dict[str, pd.DataFrame]:
    days = load(market) if days is None else days
    days = days[pd.to_datetime(days["date"]) < WINDOW[1]]
    f = from_daily(market, days)
    tl = timeline(market, f, s)
    rows = tl.rows
    d1 = f.full["D1"]
    t_open, t_close = d1.t, d1.end
    hi, lo, cl = d1.h, d1.l, d1.c
    adr_rows = pd.Series(hi - lo).rolling(ADR_N).mean().to_numpy()
    w1 = f.full["W1"]
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
    close_at = dict(zip(t_close.tolist(), cl.tolist()))

    # cell 1: each establishment
    new = rows[(rows["state"].isin(list(_SIDE))) & (rows["since"] == rows["t"])]
    ends = rows[rows["ended"].notna()]
    calls = []
    for r in new.itertuples():
        t = int(r.t)
        if not (t0 <= t < t1):
            continue
        side = _SIDE[r.side]
        p, adr = close_at.get(t, np.nan), adr_at(t)
        row = {"market": market, "side": side, "t": pd.Timestamp(t, tz="UTC").tz_localize(None),
               "outcome": "no draw", "held": np.nan, "control": np.nan, "n_control": 0, "a": np.nan, "b": np.nan,
               "bullish": r.bullish, "bearish": r.bearish}
        later = ends[ends["t"] > t]
        row["ended"] = later["ended"].iloc[0] if len(later) else "open"
        row["live_days"] = (int(later["t"].iloc[0]) - t) / _DAY if len(later) else np.nan
        if r.draw is None or r.protected is None or not np.isfinite(adr) or not np.isfinite(p):
            calls.append(row)
            continue
        a, b = side * (r.draw - p) / adr, side * (p - r.protected) / adr
        outcome, _ = race(hi, lo, cl, int(np.searchsorted(t_open, t, side="left")), side, r.draw, r.protected)
        share, n = control_share(hi, lo, cl, c_starts, c_closes, c_adrs, side, a, b)
        row.update(outcome=outcome, held={"held": 1.0, "failed": 0.0}.get(outcome, np.nan), control=share,
                   n_control=n, a=a, b=b)
        calls.append(row)

    # cell 2: each week's open, and the baselines
    r_t = rows["t"].to_numpy(np.int64)
    weeks = []
    for i in range(len(w1)):
        wo, wc = int(w1.t[i]), int(w1.end[i])
        if not (wo >= t0 and wc <= t1):
            continue
        k = int(np.searchsorted(r_t, wo, side="right")) - 1
        state = rows["state"].iloc[k] if k >= 0 else "UNDETERMINED"
        cats = {c: (rows[f"{c}_b"].iloc[k] - rows[f"{c}_s"].iloc[k]) if k >= 0 else 0.0 for c in CATEGORIES}
        htf = 0
        if i >= 2:                                           # the last closed W1 candle's LE-D15 trend
            htf = 1 if w1.c[i - 1] > w1.h[i - 2] else -1 if w1.c[i - 1] < w1.l[i - 2] else 0
        weeks.append({"market": market, "t": pd.Timestamp(wo, tz="UTC").tz_localize(None),
                      "side": _SIDE.get(state, 0), "state": state, "htf": htf,
                      "up": float(w1.c[i] > w1.o[i]), "down": float(w1.c[i] < w1.o[i]),
                      **{f"cat_{c}": (1 if v >= s.establish_lead else -1 if v <= -s.establish_lead else 0)
                         for c, v in cats.items()}})
    weeks = pd.DataFrame(weeks)
    if not weeks.empty:
        up, down = weeks["up"].mean(), weeks["down"].mean()
        for col, out in (("side", ""), ("htf", "htf_"), *[(f"cat_{c}", f"cat_{c}_") for c in CATEGORIES]):
            weeks[f"{out}expected"] = np.where(weeks[col] > 0, up, np.where(weeks[col] < 0, down, np.nan))
            weeks[f"{out}hit"] = np.where(weeks[col] > 0, weeks["up"], np.where(weeks[col] < 0, weeks["down"], np.nan))
    states = rows.assign(market=market)[["market", "t", "state", "side", "since", "ended"]]
    trans = pd.DataFrame([{"market": market, "t": tr.at, "previous": tr.previous, "new": tr.new,
                           "trigger": tr.trigger} for tr in tl.transitions])
    return {"calls": pd.DataFrame(calls), "weeks": weeks, "states": states, "transitions": trans}


def run(markets=MARKETS, s: Settings = V1, log=print) -> dict[str, pd.DataFrame]:
    parts = []
    for m in markets:
        t = time.time()
        parts.append(market_tables(m, s=s))
        log(f"{m}: {len(parts[-1]['calls'])} calls, {time.time() - t:.0f}s")
    return {k: pd.concat([p[k] for p in parts if not p[k].empty], ignore_index=True) for k in parts[0]}


def _pts(x: float) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:+.1f}"


def _line(name: str, r: dict) -> str:
    if not r.get("n"):
        return f"| {name} | 0 | – | – | – | – | – |"
    return (f"| {name} | {r['n']:,} | {r['value']:.1%} | {r['base']:.1%} | {_pts(r['excess'])} | "
            f"[{_pts(r['lo'])}, {_pts(r['hi'])}] | {r['positive']}/{len(r['per_market'])} |")


def report(t: dict[str, pd.DataFrame]) -> str:
    calls, weeks, states, trans = t["calls"], t["weeks"], t["states"], t["transitions"]
    c1, c2 = judge(calls, "held", "control"), judge(weeks[weeks["side"] != 0], "hit", "expected")
    passes = bool(c1.get("passes") or c2.get("passes"))
    head = "| | n | value | expected | excess (pts) | 97.5% interval | markets above 0 |\n|---|---|---|---|---|---|---|"
    out = [f"**H-AF {'passes' if passes else 'fails'}.**", "", head,
           _line("Cell 1: the draw before invalidation vs matched starts", c1),
           _line("Cell 2: weeks under an ACTIVE side vs drift", c2), ""]
    out += ["**Each market** (cell 1 held vs control; cell 2 hit vs drift):", "",
            "| market | calls | held | control | weeks | hit | drift |", "|---|---|---|---|---|---|---|"]
    for m in sorted(set(calls["market"]) | set(weeks["market"])):
        c = calls[(calls["market"] == m)].dropna(subset=["held", "control"])
        w = weeks[(weeks["market"] == m) & (weeks["side"] != 0)]
        out.append(f"| {m} | {len(c)} | {c['held'].mean():.1%} | {c['control'].mean():.1%} | {len(w)} | "
                   f"{w['hit'].mean():.1%} | {w['expected'].mean():.1%} |" if len(c) and len(w) else
                   f"| {m} | {len(c)} | – | – | {len(w)} | – | – |")
    out += ["", "**Beside it, not judged.**", ""]
    for name, g in (("buys", calls[calls["side"] > 0]), ("sells", calls[calls["side"] < 0])):
        out.append(f"- Cell 1, {name}: {_line(name, judge(g, 'held', 'control'))}")
    for label, start in FOLDS:
        out.append(f"- Fold {label}: cell 1 {_pts(judge(calls[calls['t'] >= start], 'held', 'control').get('excess'))}")
    years = (states["t"].max() - states["t"].min()) / (365.25 * _DAY) if len(states) else np.nan
    share = states["state"].value_counts(normalize=True)
    live = calls["live_days"].dropna()
    ends = calls["ended"].value_counts().to_dict()
    flips = trans[(trans["previous"] == "TRANSITIONAL") & trans["new"].isin(["BULLISH", "BEARISH"])
                  & trans["trigger"].str.startswith("the challenge established")]
    out += [f"- §16.2 state quality: {len(trans) / max(years, 1e-9) / max(states['market'].nunique(), 1):.1f} "
            f"transitions a market-year; market-days UNDETERMINED {share.get('UNDETERMINED', 0):.0%}, NEUTRAL "
            f"{share.get('NEUTRAL', 0):.0%}, BULLISH {share.get('BULLISH', 0):.0%}, BEARISH "
            f"{share.get('BEARISH', 0):.0%}, TRANSITIONAL {share.get('TRANSITIONAL', 0):.0%}; median days live "
            f"{live.median():.0f}; how calls ended {ends}; challenges turned to the other side {len(flips)}",
            f"- Calls without a draw or protected level: {(calls['outcome'] == 'no draw').sum()}; races open at the "
            f"end: {(calls['outcome'] == 'open').sum()}"]
    htf = weeks[weeks["htf"] != 0]
    out.append(f"- §16.4 the simple HTF filter (last W1 candle's trend), all its weeks: "
               f"{_line('htf', judge(htf, 'htf_hit', 'htf_expected'))}")
    both = weeks[(weeks["side"] != 0) & (weeks["htf"] != 0)]
    out.append(f"- On cell 2's weeks where the filter also has a side: AlgoMindDIS {both['hit'].mean():.1%}, the filter "
               f"{both['htf_hit'].mean():.1%}, agreeing {(both['side'] == both['htf']).mean():.0%} ({len(both)} weeks)"
               if len(both) else "- No week where both have a side")
    for c in CATEGORIES:
        g = weeks[weeks[f"cat_{c}"] != 0]
        out.append(f"- {c} alone (its lead at least {V1.establish_lead}): "
                   f"{_line(c, judge(g, f'cat_{c}_hit', f'cat_{c}_expected'))}")
    return "\n".join(out), passes


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(prog="python -m algomind_dis.replay", description=__doc__.splitlines()[0])
    p.add_argument("--markets", default=",".join(MARKETS))
    args = p.parse_args(argv)
    tables = run(tuple(args.markets.split(",")))
    OUT.mkdir(parents=True, exist_ok=True)
    for k, v in tables.items():
        v.to_parquet(OUT / f"haf_{k}_develop.parquet", index=False)
    text, _ = report(tables)
    (OUT / "haf_report_develop.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
