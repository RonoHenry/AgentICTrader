"""The 2018-2024 search: H-AA, the brain on the world's weeks, with the flows (docs/research/SEARCH_2018_2024.md).

H-Z's widened weekly state, plus what the literature finds direction in, and fitted on 42 markets' weeks instead of
nine (``algo_research/universe.py``):
- **the flows,** calendar facts known before the week opens: a scheduled FOMC statement in the week, the FOMC cycle
  week (Cieslak, Morse and Vissing-Jorgensen 2019), options expiry (monthly, quarterly, the week after), the month's
  last weekday, the month-end rebalancing flow for equity indices (US500's month-to-date return minus the 10-year
  Treasury's; Harvey, Mazzoleni and Melone 2025) and the month-end hedge flow for markets with a side against the
  dollar (Melvin and Prins 2015);
- **the volatility premium:** the VIX's implied month of variance minus US500's realized one (Bollerslev, Tauchen
  and Zhou 2009).

Fitted on every usable market's weeks before 2018-07 and judged on the nine's weeks of 2018-07 to 2022 (H-Z's rows),
by H-Y's rule and against H-Z's v2.

    python -m algo_research.search_state3 --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.fomc import statements
from algo_research.search_d1 import MARKETS, OUT
from algo_research.search_state import FIT_UNTIL, JUDGE, YAHOO, judge, load
from algo_research.search_state2 import FEATURES as V2, macro_table, state_table2, widen
from algo_research.universe import BROAD, load_broad, orientation

__all__ = ["FEATURES", "FLOWS", "VOL", "add_flows", "calendar_flows", "money_flows", "tables", "usable"]

FLOWS = ("fomc_in_week", "fomc_cycle", "fomc_even", "opex_week", "opex_quarter", "after_opex", "month_end_week",
         "reb_flow", "hedge_flow")
VOL = ("vrp",)
FEATURES = V2 + FLOWS + VOL
BOND_DURATION = 7.5
CACHE = OUT / "state3_tables.parquet"


# ── the calendar ───────────────────────────────────────────────────────────

def _third_friday(year: int, month: int) -> pd.Timestamp:
    first = pd.Timestamp(year, month, 1)
    return first + pd.Timedelta(days=(4 - first.dayofweek) % 7 + 14)


def _last_weekday(year: int, month: int) -> pd.Timestamp:
    end = pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)
    return end - pd.Timedelta(days=max(end.dayofweek - 4, 0))


def calendar_flows(mondays: pd.Series) -> pd.DataFrame:
    """The FOMC, options-expiry and month-end facts of each week (Monday to Friday), known before it opens."""
    stmts = statements().to_numpy("datetime64[ns]")
    rows = []
    for m in pd.to_datetime(mondays):
        fri = m + pd.Timedelta(days=4)
        k = int(np.searchsorted(stmts, np.datetime64(m, "ns"), side="left"))   # first statement on or after Monday
        in_week = k < len(stmts) and stmts[k] <= np.datetime64(fri, "ns")
        if in_week:
            cycle = 0.0
        elif k == 0:
            cycle = np.nan                                           # before 1994: no list
        else:
            cycle = float(min(((m - pd.Timestamp(stmts[k - 1])).days + 2) // 7, 7))
        months = {(m.year, m.month), (fri.year, fri.month)}
        opex = [_third_friday(y, mo) for y, mo in months]
        before = m - pd.Timedelta(days=7)
        prev_opex = [_third_friday(y, mo) for y, mo in {(before.year, before.month), (m.year, m.month)}]
        rows.append({"week": m, "fomc_in_week": float(in_week), "fomc_cycle": cycle,
                     "fomc_even": float(cycle % 2 == 0) if np.isfinite(cycle) else np.nan,
                     "opex_week": float(any(m <= d <= fri for d in opex)),
                     "opex_quarter": float(any(m <= d <= fri and d.month % 3 == 0 for d in opex)),
                     "after_opex": float(any(before <= d < m for d in prev_opex)),
                     "month_end_week": float(any(m <= _last_weekday(y, mo) <= fri for y, mo in months))})
    return pd.DataFrame(rows)


def money_flows(root=YAHOO) -> pd.DataFrame:
    """At each week's open (the last close before Monday): US500's month-to-date return, the 10-year Treasury's
    (from ^TNX), and the volatility premium."""
    spx = load("US500", root).set_index("date")["close"]
    tnx = pd.read_parquet(root / "TNX_D1.parquet").set_index("date")["close"].dropna()
    vix = pd.read_parquet(root / "VIX_D1.parquet").set_index("date")["close"].dropna()
    daily = pd.DataFrame({"spx": spx, "tnx": tnx, "vix": vix}).sort_index().ffill()
    month = daily.index.to_period("M")
    prior_end = daily.groupby(month).tail(1).set_index(month.unique()).shift(1)     # the month before's last close
    start = prior_end.reindex(month).set_axis(daily.index)
    rv = (100 * np.log(daily["spx"]).diff()).pow(2).rolling(21, min_periods=21).sum()
    out = pd.DataFrame({"eq_mtd": daily["spx"] / start["spx"] - 1,
                        "bond_mtd": -BOND_DURATION * (daily["tnx"] - start["tnx"]) / 100,
                        "vrp": daily["vix"] ** 2 / 12 - rv}, index=daily.index)
    week = out.index - pd.to_timedelta(out.index.dayofweek, unit="D")
    weekly = out.groupby(week).last()
    weekly.index = weekly.index + pd.Timedelta(days=7)             # the week before's last close, read at this open
    return weekly.rename_axis("week").reset_index()


def add_flows(t: pd.DataFrame, root=YAHOO) -> pd.DataFrame:
    """H-Z's widened table with the flows and the volatility premium."""
    cal = calendar_flows(pd.Series(sorted(t["week"].unique())))
    t = t.merge(cal, on="week", how="left").merge(money_flows(root), on="week", how="left")
    side = t["market"].map(lambda m: orientation(m)[0])
    equity = t["market"].map(lambda m: orientation(m)[1])
    t["reb_flow"] = equity * (t["eq_mtd"] - t["bond_mtd"]).fillna(0)
    t["hedge_flow"] = side * t["eq_mtd"].fillna(0)
    return t.drop(columns=["eq_mtd", "bond_mtd"])


# ── the tables ─────────────────────────────────────────────────────────────

def usable() -> list[str]:
    """The nine and the added markets with enough clean days for a state (14 closed months and a year of weeks)."""
    from algo_research.universe import BROAD_ROOT
    added = [m for m in BROAD if (BROAD_ROOT / f"{m}_D1.parquet").exists() and len(load_broad(m)) >= 400]
    return list(MARKETS) + added


def tables(refresh: bool = False) -> pd.DataFrame:
    """Every usable market's widened weekly states with the flows, cached (the search's development data only)."""
    if CACHE.exists() and not refresh:
        return pd.read_parquet(CACHE)
    own = {}
    for m in usable():
        own[m] = state_table2(m, load_broad(m))
        print(f"{m}: {len(own[m]):,} weeks", flush=True)
    t = add_flows(widen(own, macro_table()))
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_parquet(CACHE, index=False)
    return t


# ── the run ────────────────────────────────────────────────────────────────

def _row(name: str, r: dict, n_markets: int) -> str:
    if not r.get("calls"):
        return f"| {name} | 0 | | | | | | |"
    p = lambda x: f"{100 * x:+.1f}"                                          # noqa: E731
    return (f"| {name} | {r['calls']:,} | {r['hit']:.1%} | {r['base']:.1%} | {p(r['excess'])} | "
            f"[{p(r['lo'])}, {p(r['hi'])}] | {r['positive']}/{n_markets} | {'yes' if r.get('passes') else 'no'} |")


def main() -> None:
    from algo_research.search_state import fit_and_call
    from sklearn.inspection import permutation_importance

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=["develop"], required=True)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    t = tables(args.refresh)
    nine = t["market"].isin(MARKETS)
    fit_all = t[t["week"] < FIT_UNTIL]
    fit_nine = fit_all[fit_all["market"].isin(MARKETS)]
    dev = t[(t["week"] >= JUDGE[0]) & (t["week"] < JUDGE[1])]
    dev_nine, dev_other = dev[dev["market"].isin(MARKETS)], dev[~dev["market"].isin(MARKETS)]
    n_other = dev_other["market"].nunique()
    moved = lambda x: len(x[x["up"] != 0])                                    # noqa: E731
    lines = [f"Markets: {t['market'].nunique()} ({t[~nine]['market'].nunique()} beyond the nine). "
             f"Fitted on {moved(fit_all):,} weeks before {FIT_UNTIL.date()} ({moved(fit_nine):,} of them the nine's); "
             f"judged on the nine's {moved(dev_nine):,} weeks {JUDGE[0].date()} to 2022 and the others' "
             f"{moved(dev_other):,}.", "",
             "| Model | Calls | Hit | Drift | Excess (pts) | 95% weeks | Markets > 0 | H-Y's rule |",
             "|---|---|---|---|---|---|---|---|"]
    _, aa_nine, model = fit_and_call(fit_all, dev_nine, "gbm", FEATURES)
    r_aa = judge(aa_nine)
    _, v2_nine, _ = fit_and_call(fit_nine, dev_nine, "gbm", V2)
    r_v2 = judge(v2_nine)
    passes = r_aa.get("passes") and r_aa["excess"] > r_v2["excess"]
    lines.append(_row("**H-AA: flows + volatility premium, fitted on all markets**", r_aa, 9))
    lines.append(_row("H-Z's v2 (fitted on the nine) on the same rows", r_v2, 9))
    _, b_nine, _ = fit_and_call(fit_all, dev_nine, "gbm", V2)
    lines.append(_row("breadth alone: v2's inputs fitted on all markets", judge(b_nine), 9))
    _, f_nine, _ = fit_and_call(fit_nine, dev_nine, "gbm", FEATURES)
    lines.append(_row("flows alone: H-AA's inputs fitted on the nine", judge(f_nine), 9))
    _, v2_other, _ = fit_and_call(fit_nine, dev_other, "gbm", V2)
    lines.append(_row("transfer: H-Z's v2 on the markets it never saw", judge(v2_other), n_other))
    _, aa_other, _ = fit_and_call(fit_all, dev_other, "gbm", FEATURES)
    lines.append(_row("H-AA on the other markets' development weeks", judge(aa_other), n_other))
    aa_all = pd.concat([aa_nine, aa_other], ignore_index=True)
    lines.append(_row("H-AA on every market's development weeks", judge(aa_all), 9 + n_other))
    for side, name in ((1, "up calls"), (-1, "down calls")):
        lines.append(_row(f"H-AA {name}", judge(aa_nine, side=side), 9))
    lines += ["", f"H-AA passes: {'yes' if passes else 'no'} (H-Y's rule {'met' if r_aa.get('passes') else 'not met'}; "
                  f"H-AA − v2 = {100 * (r_aa['excess'] - r_v2['excess']):+.1f} pts)",
              "Excess per market, H-AA: " + ", ".join(f"{m} {100 * v:+.1f} ({n})"
                                                      for m, (v, n) in r_aa["per_market"].items())]
    by_year = {y: judge(g) for y, g in aa_nine.groupby(aa_nine["week"].dt.year)}
    lines.append("By year, H-AA: " + ", ".join(f"{y} {100 * r['excess']:+.1f} ({r['calls']})"
                                                 for y, r in by_year.items() if r.get("calls")))
    aa_nine.to_parquet(OUT / "state3_develop.parquet")
    aa_all.to_parquet(OUT / "state3_develop_all.parquet")
    mv = aa_nine[aa_nine["up"] != 0]
    imp = permutation_importance(model, mv[list(FEATURES)].to_numpy(float), (mv["up"] > 0).astype(int),
                                 scoring="roc_auc", n_repeats=5, random_state=0)
    order = np.argsort(-imp.importances_mean)[:15]
    lines += ["", "Permutation importance on the nine's judged weeks (ROC AUC lost):",
              ", ".join(f"{FEATURES[i]} {imp.importances_mean[i]:+.4f}" for i in order),
              "The flows: " + ", ".join(f"{f} {imp.importances_mean[FEATURES.index(f)]:+.4f}" for f in FLOWS + VOL)]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
