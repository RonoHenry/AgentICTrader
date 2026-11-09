"""The 2018-2024 search: H-AC, the brain's side only when macro moves, walked forward (docs/research/SEARCH_2018_2024.md,
Amendment 2).

H-Z's recipe (the v2 inputs and model) is fitted walk-forward on the nine: on the weeks before 1995, 2000, 2005,
2010, 2015 and 2018-07, each fold calling the weeks to the next cut (the last fold is H-Z's development calls). A
week is macro-active when, at its open, the VIX's one-year percentile is at least 0.67, or the 10-year yield's
four-week change (absolute) is at or above the 67th percentile of the weeks before the fold's cut. The active weeks'
calls, pooled over the folds, are judged by H-Y's measure.

    python -m algo_research.search_regime --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_d1 import MARKETS, OUT
from algo_research.search_state import JUDGE, fit_and_call, judge
from algo_research.search_state2 import FEATURES as V2

__all__ = ["CUTS", "VIX_PCT", "YIELD_Q", "active", "walk_forward"]

CUTS = ("1995-01-01", "2000-01-01", "2005-01-01", "2010-01-01", "2015-01-01", "2018-07-01")
VIX_PCT, YIELD_Q = 0.67, 0.67


def walk_forward(t: pd.DataFrame, features: tuple = V2) -> pd.DataFrame:
    """Each fold's calls on the weeks from its cut to the next (the last to the end of development), with the fold
    and its yield threshold."""
    ends = list(CUTS[1:]) + [str(JUDGE[1].date())]
    parts = []
    for cut, end in zip(CUTS, ends):
        fit = t[t["week"] < cut]
        judged = t[(t["week"] >= cut) & (t["week"] < end)]
        _, calls, _ = fit_and_call(fit, judged, "gbm", features)
        weekly = fit.drop_duplicates("week")["y10_chg4w"].abs()
        parts.append(calls.assign(fold=cut, y_threshold=float(np.quantile(weekly, YIELD_Q))))
    return pd.concat(parts, ignore_index=True)


def active(calls: pd.DataFrame) -> pd.Series:
    return (calls["vix_pct"] >= VIX_PCT) | (calls["y10_chg4w"].abs() >= calls["y_threshold"])


def _row(name: str, r: dict, n: int) -> str:
    if not r.get("calls"):
        return f"| {name} | 0 | | | | | |"
    p = lambda x: f"{100 * x:+.1f}"                                          # noqa: E731
    return (f"| {name} | {r['calls']:,} | {r['hit']:.1%} | {r['base']:.1%} | {p(r['excess'])} | "
            f"[{p(r['lo'])}, {p(r['hi'])}] | {r['positive']}/{n} |")


def main() -> None:
    from algo_research.search_state3 import tables

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=["develop"], required=True)
    parser.parse_args()
    t = tables()
    t = t[t["market"].isin(MARKETS)].reset_index(drop=True)
    calls = walk_forward(t)
    calls["active"] = active(calls)
    calls.to_parquet(OUT / "regime_walk_forward.parquet")
    on, off = calls[calls["active"]], calls[~calls["active"]]
    r_on, r_off, r_all = judge(on), judge(off), judge(calls)
    folds_on = {f: judge(g) for f, g in on.groupby("fold")}
    positive_folds = sum(r.get("calls", 0) and r["excess"] > 0 for r in folds_on.values())
    passes = bool(r_on.get("calls") and r_on["excess"] > 0 and r_on["lo"] > 0 and positive_folds >= 4
                  and r_on["excess"] > r_all["excess"])
    from algo_research.search_state import _scored
    g = _scored(calls)                                        # drift read over every week, for the active calls
    all_drift = float(g.loc[g["active"], "excess"].mean())
    lines = [f"Walk-forward on the nine, {calls['week'].min().date()} to {calls['week'].max().date()}: "
             f"{(calls['up'] != 0).sum():,} weeks, {calls['active'].mean():.0%} of them macro-active.", "",
             "| Calls | n | Hit | Drift | Excess (pts) | 95% weeks | Markets > 0 |", "|---|---|---|---|---|---|---|",
             _row("**H-AC: macro-active weeks, all folds**", r_on, 9),
             _row("calm weeks, all folds", r_off, 9),
             _row("every week, all folds", r_all, 9), "",
             "| Fold | Active: calls, excess [95%] | Calm: calls, excess | All: excess |", "|---|---|---|---|"]
    for f in CUTS:
        a, c, w = (judge(x[x["fold"] == f]) for x in (on, off, calls))
        fmt = lambda r: (f"{r['calls']}, {100 * r['excess']:+.1f} [{100 * r['lo']:+.1f}, {100 * r['hi']:+.1f}]"  # noqa: E731
                         if r.get("calls") else "0")
        lines.append(f"| from {f} | {fmt(a)} | {c.get('calls', 0)}, {100 * c.get('excess', np.nan):+.1f} | "
                     f"{100 * w.get('excess', np.nan):+.1f} |")
    lines += ["", f"H-AC passes: {'yes' if passes else 'no'} (active folds above zero: {positive_folds} of 6; "
                  f"active − all = {100 * (r_on['excess'] - r_all['excess']):+.1f} pts)",
              f"Active calls with drift read over every week: {100 * all_drift:+.1f} pts",
              "Excess per market, active: " + ", ".join(f"{m} {100 * v:+.1f} ({n})"
                                                        for m, (v, n) in r_on["per_market"].items())]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
