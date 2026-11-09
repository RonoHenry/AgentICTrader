"""H-AN: V1's management tuned to lower the bar (thesis-engine Requirements 23-24; docs/research/SEARCH_2018_2024.md,
registered 2026-11-09 in ae0e5a9 before this code). Not a try: the sides are hindsight.

The bar is the break-even weekly side ``p = -M / (O - M)``: O and M are ORACLE's and MIRROR's net R a thesis-week.
- **tune:** V1 and ten single-change variants, each with ORACLE, MIRROR and RANDOM, on the three windows already read
  (H-AG's, H-AL's and H-AJ's). The registered rule picks:
  - p below V1's in all three windows, with ORACLE's net R a week above zero;
  - pooled p at least 2 points under V1's;
  - the lowest pooled p.

  The power of the confirmation is stated before it runs: the share of 17-week windows, drawn from the tuning's
  market-weeks, where the pick's p is below V1's by more than 1.645 of the spread.
- **confirm:** the pick and V1 once on July to November 2026 (``mt5-m1-2026-11``, theses from the week of 6 July 2026
  to the week of 26 October 2026). It passes when the pick's p is below V1's, the paired difference's 90% interval
  (market-weeks, 10,000, seed 20261109) is below zero, and the pick's ORACLE is above zero a week.

    python -m thesis_engine.han tune [--workers 3]
    python -m thesis_engine.han confirm
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from agent.broker_profiles import load_profile
from thesis_engine import VERSION
from thesis_engine.hag import MARKETS, SEED, SINCE, SNAPSHOT, _trades
from thesis_engine.haj import YEAR, YEAR_BARS_FROM, YEAR_SINCE
from thesis_engine.hal import TEST, TEST_SINCE
from thesis_engine.replay import prepare, run
from thesis_engine.settings import V1, Settings
from thesis_engine.thesis import research_theses

__all__ = ["VARIANTS", "WINDOWS", "bar", "confirm", "pick", "power", "table", "tune"]

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "research" / "thesis_engine" / "han"
REPORT = REPO / "docs" / "research" / "THESIS_ENGINE_HAN.md"
ARMS = ("ORACLE", "MIRROR", "RANDOM")
#: The registered variants: V1 with one change each (SEARCH_2018_2024.md, H-AN).
VARIANTS: Dict[str, Settings] = {
    "V1": V1,
    "BE1": replace(V1, version="v1-be1", partial_r=1.0),
    "BE2": replace(V1, version="v1-be2", partial_r=2.0),
    "P2": replace(V1, version="v1-p2", partial_r=2.0, partial_fraction=1 / 3),
    "P3": replace(V1, version="v1-p3", partial_r=3.0, partial_fraction=1 / 3),
    "CAP3": replace(V1, version="v1-cap3", target_cap_r=3.0),
    "CAP5": replace(V1, version="v1-cap5", target_cap_r=5.0),
    "ONE": replace(V1, version="v1-one", per_thesis=1),
    "DAY": replace(V1, version="v1-day", check_at="DAY_END"),
    "DAY1R": replace(V1, version="v1-day1r", check_at="DAY_END", check_r=1.0),
    "STALL4": replace(V1, version="v1-stall4", check_at="HOURS", check_hours=4.0, check_r=1.0),
}
#: name: (M1 folder, bars from, theses from, theses before)
WINDOWS: Dict[str, Tuple[Path, Optional[pd.Timestamp], int, Optional[int]]] = {
    "2021-22": (SNAPSHOT, None, SINCE, None),
    "2023-24": (TEST, None, TEST_SINCE, None),
    "2025-26": (YEAR, YEAR_BARS_FROM, YEAR_SINCE, None),
}
HOLDOUT = ("Jul-Oct 2026", REPO / "data" / "research" / "snapshots" / "mt5-m1-2026-11", None,
           pd.Timestamp("2026-07-05", tz="UTC").value, pd.Timestamp("2026-11-01", tz="UTC").value)
MIN_GAIN = 0.02                       # pooled p at least 2 points under V1's
HOLD_WEEKS = 17                       # the confirmation's weeks, for the power
LEVEL = 0.90                          # the paired difference's two-sided interval (one-sided 95%)
CONFIRM_SEED, RESAMPLES = 20261109, 10_000


# ── one window ─────────────────────────────────────────────────────────────

def _market(job) -> Tuple[list, list]:
    """One market of one window: every variant with every arm on the same prepared bars and theses."""
    name, folder, bars_from, since, until, market, names = job
    specs = load_profile("exness-standard-swapfree").specs()
    m1 = pd.read_parquet(folder / f"{market}_M1.parquet")
    if bars_from is not None:
        m1 = m1[m1["time"] >= bars_from].reset_index(drop=True)
    m1 = m1[["time", "open", "high", "low", "close", "spread"]]
    mk = prepare(market, m1, V1)                         # management never changes the book
    rows, held = [], []
    for arm in ARMS:
        theses, _ = research_theses(market, mk.book, arm, seed=SEED, s=V1, since_from=since)
        if until is not None:
            theses = [th for th in theses if th.since < until]
        held += [{"window": name, "market": market, "arm": arm, "week": int(th.since)} for th in theses]
        for v in names:
            j = run(mk, theses, VARIANTS[v], slippage=specs[market].stop_slippage)
            rows += [{**t, "window": name, "variant": v} for t in _trades(j, market, arm)]
    return rows, held


def windows(spec: Dict[str, tuple], names, workers: int = 1, log=print) -> Tuple[pd.DataFrame, pd.DataFrame]:
    jobs = [(w, *spec[w], m, tuple(names)) for w in spec for m in MARKETS]
    rows, held, t0 = [], [], time.time()
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for job, (r, h) in zip(jobs, ex.map(_market, jobs)):
                rows += r
                held += h
                log(f"{job[0]} {job[5]}: {len(r)} trades ({time.time() - t0:.0f}s)")
    else:
        for job in jobs:
            r, h = _market(job)
            rows += r
            held += h
            log(f"{job[0]} {job[5]}: {len(r)} trades ({time.time() - t0:.0f}s)")
    return pd.DataFrame(rows), pd.DataFrame(held)


# ── the measures ───────────────────────────────────────────────────────────

def bar(o: float, m: float) -> float:
    """The break-even weekly side: -M / (O - M); 1.0 when the right side earns no more than the wrong one."""
    return float(-m / (o - m)) if o > m else 1.0


def table(trades: pd.DataFrame, held: pd.DataFrame, variants=None) -> pd.DataFrame:
    """One row per window (and "pooled") and variant: each arm's R a week and a trade, the bar a week and a trade."""
    out = []
    present = set(trades["variant"])
    names = [*sorted(held["window"].unique())]
    variants = VARIANTS if variants is None else variants
    for w in names + (["pooled"] if len(names) > 1 else []):
        h = held if w == "pooled" else held[held["window"] == w]
        tw = trades if w == "pooled" else trades[trades["window"] == w]
        weeks = h.groupby("arm").size()
        for v in [v for v in variants if v in present]:
            t = tw[tw["variant"] == v]
            row = {"window": w, "variant": v}
            for arm in ARMS:
                x = t[t["arm"] == arm]
                n = int(weeks.get(arm, 0))
                row.update({f"{arm}_trades": len(x), f"{arm}_week": x["net_r"].sum() / n if n else np.nan,
                            f"{arm}_trade": x["net_r"].mean() if len(x) else np.nan,
                            f"{arm}_win": (x["net_r"] > 0).mean() if len(x) else np.nan,
                            f"{arm}_trades_week": len(x) / n if n else np.nan})
            row["p_week"] = bar(row["ORACLE_week"], row["MIRROR_week"])
            row["p_trade"] = bar(row["ORACLE_trade"], row["MIRROR_trade"])
            out.append(row)
    return pd.DataFrame(out)


def pick(tab: pd.DataFrame) -> Tuple[Optional[str], dict]:
    """The registered rule: below V1 in every window with ORACLE above zero a week, pooled at least 2 points
    under V1's, then the lowest pooled p."""
    p = tab.pivot(index="variant", columns="window", values="p_week")
    o = tab.pivot(index="variant", columns="window", values="ORACLE_week")
    wins = [w for w in p.columns if w != "pooled"]
    why = {}
    for v in p.index:
        if v == "V1":
            continue
        below = all(p.loc[v, w] < p.loc["V1", w] for w in wins)
        positive = all(o.loc[v, w] > 0 for w in wins)
        gain = p.loc["V1", "pooled"] - p.loc[v, "pooled"]
        why[v] = {"below V1 in every window": bool(below), "ORACLE above zero a week in every window": bool(positive),
                  "pooled gain (points)": round(100 * float(gain), 2), "qualifies": bool(below and positive
                                                                                     and gain >= MIN_GAIN)}
    ok = [v for v, x in why.items() if x["qualifies"]]
    return (min(ok, key=lambda v: p.loc[v, "pooled"]) if ok else None), why


def _weekly(trades: pd.DataFrame, held: pd.DataFrame, variants) -> pd.DataFrame:
    """Per market-week: each variant's ORACLE and MIRROR net R, and whether each arm held a thesis."""
    keys = ["window", "market", "week"]
    trades = trades.assign(week=trades["week"].astype("int64"))
    held = held.assign(week=held["week"].astype("int64"))
    h = held[held["arm"].isin(["ORACLE", "MIRROR"])].assign(n=1).pivot_table(
        index=keys, columns="arm", values="n", aggfunc="sum", fill_value=0)
    out = pd.DataFrame({"nO": h.get("ORACLE", 0), "nM": h.get("MIRROR", 0)})
    for v in variants:
        t = trades[(trades["variant"] == v) & trades["arm"].isin(["ORACLE", "MIRROR"])]
        s = t.groupby([*keys, "arm"])["net_r"].sum().unstack("arm")
        out[f"{v}_O"] = s.get("ORACLE", pd.Series(dtype=float)).reindex(out.index).fillna(0.0)
        out[f"{v}_M"] = s.get("MIRROR", pd.Series(dtype=float)).reindex(out.index).fillna(0.0)
    return out.reset_index()


def _bars(w: np.ndarray, mw: pd.DataFrame, v: str) -> np.ndarray:
    """The bar of variant ``v`` under each resample's weights ``w`` (resamples x market-weeks)."""
    n_o, n_m = w @ mw["nO"].to_numpy(float), w @ mw["nM"].to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        o, m = (w @ mw[f"{v}_O"].to_numpy(float)) / n_o, (w @ mw[f"{v}_M"].to_numpy(float)) / n_m
    return np.where(o > m, -m / (o - m), 1.0)


def power(mw: pd.DataFrame, v: str, size: int, rng: np.random.Generator, draws: int = 2000) -> dict:
    """How often a ``size``-market-week window shows ``v`` below V1 by more than 1.645 of the difference's spread."""
    idx = rng.integers(0, len(mw), size=(draws, size))
    w = np.zeros((draws, len(mw)))
    np.add.at(w, (np.repeat(np.arange(draws), size), idx.ravel()), 1.0)
    d = _bars(w, mw, v) - _bars(w, mw, "V1")
    return {"market-weeks a window": size, "mean difference (points)": round(100 * float(d.mean()), 2),
            "spread (points)": round(100 * float(d.std()), 2), "power": round(float((d < -1.645 * d.std()).mean()), 3)}


def paired(mw: pd.DataFrame, v: str) -> dict:
    """The pick's bar minus V1's, and its interval resampling market-weeks (LEVEL, two-sided)."""
    rng = np.random.default_rng(CONFIRM_SEED)
    w = rng.multinomial(len(mw), np.full(len(mw), 1 / len(mw)), size=RESAMPLES).astype(float)
    d = _bars(w, mw, v) - _bars(w, mw, "V1")
    tail = 100 * (1 - LEVEL) / 2
    lo, hi = np.percentile(d, [tail, 100 - tail])
    one = np.ones((1, len(mw)))
    return {"difference": float((_bars(one, mw, v) - _bars(one, mw, "V1"))[0]), "lo": float(lo), "hi": float(hi)}


# ── the two steps ──────────────────────────────────────────────────────────

def _pct(x) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:.1f}%"


def _r(x) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{x:+.2f}"


def _rows(tab: pd.DataFrame) -> list:
    lines = ["| Window | Variant | p a week | p a trade | ORACLE R a week | MIRROR R a week | RANDOM R a week | "
             "ORACLE R a trade | ORACLE win | trades a week (O / M) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in tab.itertuples():
        lines.append(f"| {r.window} | {r.variant} | {_pct(r.p_week)} | {_pct(r.p_trade)} | {_r(r.ORACLE_week)} | "
                     f"{_r(r.MIRROR_week)} | {_r(r.RANDOM_week)} | {_r(r.ORACLE_trade)} | {_pct(r.ORACLE_win)} | "
                     f"{r.ORACLE_trades_week:.2f} / {r.MIRROR_trades_week:.2f} |")
    return lines


def tune(workers: int = 1, log=print) -> dict:
    t0 = time.time()
    trades, held = windows(WINDOWS, tuple(VARIANTS), workers, log)
    OUT.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(OUT / "tune_trades.parquet")
    held.to_parquet(OUT / "tune_held.parquet")
    tab = table(trades, held)
    chosen, why = pick(tab)
    result = {"machine": VERSION, "pick": chosen, "why": why, "minutes": round((time.time() - t0) / 60, 1),
              "table": tab.to_dict("records")}
    if chosen is not None:
        result["power"] = power(_weekly(trades, held, ("V1", chosen)), chosen, HOLD_WEEKS * len(MARKETS),
                                np.random.default_rng(CONFIRM_SEED))
    (OUT / "tune.json").write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    lines = ["# H-AN: V1's management tuned to lower the bar", "",
             "Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-09, ae0e5a9) before its code. "
             f"Machine {VERSION}. Not a try: the sides are hindsight.", "",
             "## The tuning (2021-22, 2023-24, July 2025 to June 2026)", "",
             f"**The pick: {chosen or 'none'}.**", ""]
    for v, x in why.items():
        lines.append(f"- {v}: below V1 in every window {'yes' if x['below V1 in every window'] else 'no'}; ORACLE "
                     f"above zero a week {'yes' if x['ORACLE above zero a week in every window'] else 'no'}; "
                     f"pooled {x['pooled gain (points)']:+.1f} points under V1; "
                     f"{'qualifies' if x['qualifies'] else 'does not qualify'}")
    if chosen is not None:
        pw = result["power"]
        lines += ["", f"**The confirmation's power, stated before it runs:** over {pw['market-weeks a window']} "
                  f"market-weeks the pick's p is {pw['mean difference (points)']:+.1f} points from V1's with a "
                  f"spread of {pw['spread (points)']:.1f}; a window shows it below by more than 1.645 spreads "
                  f"{pw['power']:.0%} of the time."]
    else:
        lines += ["", "No variant qualifies: H-AN fails at the tuning stage and July to November 2026 stays unspent."]
    lines += ["", "## Every variant", "", *_rows(tab), "",
              "## Exits (all windows, ORACLE / MIRROR)", "", "| Variant | ORACLE | MIRROR |", "|---|---|---|"]
    for v in VARIANTS:
        ex = {arm: trades[(trades["variant"] == v) & (trades["arm"] == arm)]["reason"].value_counts().to_dict()
              for arm in ("ORACLE", "MIRROR")}
        lines.append(f"| {v} | {ex['ORACLE']} | {ex['MIRROR']} |")
    lines += ["", f"Run time {result['minutes']} minutes.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return result


def confirm(workers: int = 1, log=print) -> dict:
    done = OUT / "confirm.json"
    if done.exists():
        raise SystemExit("H-AN's confirmation has run once; it is not run again")
    tuned = json.loads((OUT / "tune.json").read_text(encoding="utf-8"))
    chosen = tuned["pick"]
    if chosen is None:
        raise SystemExit("no variant qualified at the tuning stage: July to November 2026 stays unspent")
    name, *spec = HOLDOUT
    trades, held = windows({name: tuple(spec)}, ("V1", chosen), workers, log)
    trades.to_parquet(OUT / "confirm_trades.parquet")
    held.to_parquet(OUT / "confirm_held.parquet")
    tab = table(trades, held)
    tab = tab[tab["window"] == name]
    p = tab.set_index("variant")
    pr = paired(_weekly(trades, held, ("V1", chosen)), chosen)
    checks = {"the pick's p is below V1's": bool(p.loc[chosen, "p_week"] < p.loc["V1", "p_week"]),
              "the paired difference's 90% interval is below zero": bool(pr["hi"] < 0),
              "the pick's ORACLE is above zero a week": bool(p.loc[chosen, "ORACLE_week"] > 0)}
    result = {"pick": chosen, "checks": checks, "passes": all(checks.values()), "paired": pr,
              "table": tab.to_dict("records"), "market_weeks": int(len(_weekly(trades, held, ("V1",))))}
    done.write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    lines = ["", "## The confirmation (July to October 2026, run once)", "",
             f"**H-AN {'PASSES' if result['passes'] else 'FAILS'}** ({chosen} against V1).", "",
             *[f"- {'✓' if ok else '✗'} {k}" for k, ok in checks.items()], "",
             f"The pick's p minus V1's: {100 * pr['difference']:+.1f} points, 90% interval "
             f"[{100 * pr['lo']:+.1f}, {100 * pr['hi']:+.1f}] over {result['market_weeks']} market-weeks.", "",
             *_rows(tab), ""]
    with REPORT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return result


def main(argv: Optional[list] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m thesis_engine.han", description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=("tune", "confirm"))
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args(argv)
    r = (tune if args.step == "tune" else confirm)(args.workers)
    print(json.dumps({k: v for k, v in r.items() if k != "table"}, indent=1, default=float))


if __name__ == "__main__":
    main()
