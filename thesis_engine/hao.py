"""H-AO: Volume Profile as a filter and as an entry on V1 (thesis-engine Requirements 25-26; docs/research/
SEARCH_2018_2024.md, registered 2026-11-09 in f3efe2d before this code). Not a try: the sides are hindsight.

The measure is H-AN's break-even weekly side ``p = -M / (O - M)``.
- **tune:** V1 and nine single-change variants, each with ORACLE, MIRROR and RANDOM, on the three windows already read.
  The registered rule picks: p below V1's in all three windows with ORACLE's net R a week above zero; pooled p at
  least 2 points under V1's; pooled ORACLE trades at least a quarter of V1's; EPOC's pooled p below MT's (MT is a
  control, never picked); then the lowest pooled p.
- **confirm:** the pick and V1 once on July to November 2026, H-AN's window and pass. It spends the hold-out, so it
  runs only on the trader's go.

    python -m thesis_engine.hao tune [--workers 3]
    python -m thesis_engine.hao confirm
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from agent.broker_profiles import load_profile
from thesis_engine import VERSION
from thesis_engine.hag import MARKETS, SEED, _trades
from thesis_engine.han import (ARMS, CONFIRM_SEED, HOLD_WEEKS, HOLDOUT, MIN_GAIN, WINDOWS, _rows, _weekly, paired, pick as
                               han_pick, power, table as han_table)
from thesis_engine.replay import Journal, prepare, run
from thesis_engine.settings import V1, Settings
from thesis_engine.thesis import research_theses

__all__ = ["CONTROLS", "VARIANTS", "confirm", "pick", "table", "tune", "windows"]

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "research" / "thesis_engine" / "hao"
HAN_TUNE = REPO / "data" / "research" / "thesis_engine" / "han" / "tune.json"
REPORT = REPO / "docs" / "research" / "THESIS_ENGINE_HAO.md"
MIN_KEPT = 0.25                       # pooled ORACLE trades, as a share of V1's
KEPT = "keeps a quarter of V1's ORACLE trades"
#: The registered variants: V1 with one change each (SEARCH_2018_2024.md, H-AO).
VARIANTS: Dict[str, Settings] = {
    "V1": V1,
    "POC_W": replace(V1, version="v1-poc-w", volume_gate="POC", volume_anchor="W1"),
    "VA_W": replace(V1, version="v1-va-w", volume_gate="VA", volume_anchor="W1"),
    "NEAR_W": replace(V1, version="v1-near-w", volume_gate="NEAR", volume_anchor="W1"),
    "PATH_W": replace(V1, version="v1-path-w", volume_gate="PATH", volume_anchor="W1"),
    "POC_D": replace(V1, version="v1-poc-d", volume_gate="POC", volume_anchor="D1"),
    "VA_D": replace(V1, version="v1-va-d", volume_gate="VA", volume_anchor="D1"),
    "NEAR_D": replace(V1, version="v1-near-d", volume_gate="NEAR", volume_anchor="D1"),
    "EPOC": replace(V1, version="v1-epoc", entry="LIMIT_POC"),
    "MT": replace(V1, version="v1-mt", entry="LIMIT_MT"),
}
CONTROLS = ("MT",)


def _funnel(j: Journal, window: str, market: str, arm: str, variant: str) -> dict:
    events = Counter(r["event"] for r in j.of("fill"))
    intents = j.of("intent")
    return {"window": window, "market": market, "arm": arm, "variant": variant, "orders": len(intents),
            "limits": sum(1 for r in intents if r["kind"] == "LIMIT"), "filled": events["FILLED"],
            "expired": events["EXPIRED"], "cancelled": events["CANCELLED"],
            "volume_skips": sum(1 for r in j.of("skip") if r["reason"] == "VOLUME")}


def _market(job) -> Tuple[list, list, list]:
    """One market of one window: every variant with every arm on the same prepared bars and theses."""
    name, folder, bars_from, since, until, market, names = job
    specs = load_profile("exness-standard-swapfree").specs()
    m1 = pd.read_parquet(folder / f"{market}_M1.parquet")
    if bars_from is not None:
        m1 = m1[m1["time"] >= bars_from].reset_index(drop=True)
    volume = next(c for c in ("tick_volume", "volume") if c in m1)
    m1 = m1[["time", "open", "high", "low", "close", "spread", volume]]
    mk = prepare(market, m1, V1)                         # no variant changes the book
    rows, held, funnel = [], [], []
    for arm in ARMS:
        theses, _ = research_theses(market, mk.book, arm, seed=SEED, s=V1, since_from=since)
        if until is not None:
            theses = [th for th in theses if th.since < until]
        held += [{"window": name, "market": market, "arm": arm, "week": int(th.since)} for th in theses]
        for v in names:
            j = run(mk, theses, VARIANTS[v], slippage=specs[market].stop_slippage)
            rows += [{**t, "window": name, "variant": v} for t in _trades(j, market, arm)]
            funnel.append(_funnel(j, name, market, arm, v))
    return rows, held, funnel


def windows(spec: Dict[str, tuple], names, workers: int = 1, log=print) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    jobs = [(w, *spec[w], m, tuple(names)) for w in spec for m in MARKETS]
    rows, held, funnel, t0 = [], [], [], time.time()
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = zip(jobs, ex.map(_market, jobs))
            for job, (r, h, f) in results:
                rows += r
                held += h
                funnel += f
                log(f"{job[0]} {job[5]}: {len(r)} trades ({time.time() - t0:.0f}s)")
    else:
        for job in jobs:
            r, h, f = _market(job)
            rows += r
            held += h
            funnel += f
            log(f"{job[0]} {job[5]}: {len(r)} trades ({time.time() - t0:.0f}s)")
    return pd.DataFrame(rows), pd.DataFrame(held), pd.DataFrame(funnel)


def table(trades: pd.DataFrame, held: pd.DataFrame) -> pd.DataFrame:
    return han_table(trades, held, VARIANTS)


def pick(tab: pd.DataFrame) -> Tuple[Optional[str], dict]:
    """The registered rule: H-AN's, with a floor on the trades kept, EPOC below MT, and MT never picked."""
    _, why = han_pick(tab)
    pooled = tab[tab["window"] == "pooled"].set_index("variant")
    base = float(pooled.loc["V1", "ORACLE_trades"])
    for v, x in why.items():
        kept = float(pooled.loc[v, "ORACLE_trades"]) >= MIN_KEPT * base
        beats = v != "EPOC" or "MT" not in pooled.index or float(pooled.loc[v, "p_week"]) < float(pooled.loc["MT", "p_week"])
        x[KEPT] = bool(kept)
        x["below MT pooled (EPOC only)"] = bool(beats)
        x["qualifies"] = bool(x["qualifies"] and kept and beats and v not in CONTROLS)
    ok = [v for v, x in why.items() if x["qualifies"]]
    return (min(ok, key=lambda v: float(pooled.loc[v, "p_week"])) if ok else None), why


def _reproduces_han(tab: pd.DataFrame) -> Optional[bool]:
    """Whether V1 here equals V1 in H-AN's table: None when that table isn't on disk."""
    if not HAN_TUNE.exists():
        return None
    old = {r["window"]: r for r in json.loads(HAN_TUNE.read_text(encoding="utf-8"))["table"] if r["variant"] == "V1"}
    fields = ("p_week", "ORACLE_week", "MIRROR_week", "RANDOM_week", "ORACLE_trades", "MIRROR_trades")
    new = tab[tab["variant"] == "V1"]
    return all(np.isclose(float(r[f]), float(old[r["window"]][f]), atol=1e-9) for _, r in new.iterrows() for f in fields)


def _funnel_lines(funnel: pd.DataFrame) -> list:
    lines = ["| Variant | Arm | Orders | Limits | Filled | Expired | Cancelled | VOLUME skips |", "|---|---|---|---|---|---|---|---|"]
    g = funnel.groupby(["variant", "arm"])[["orders", "limits", "filled", "expired", "cancelled", "volume_skips"]].sum()
    for v in VARIANTS:
        for arm in ("ORACLE", "MIRROR"):
            if (v, arm) in g.index:
                r = g.loc[(v, arm)]
                lines.append(f"| {v} | {arm} | {r.orders} | {r.limits} | {r.filled} | {r.expired} | {r.cancelled} | "
                             f"{r.volume_skips} |")
    return lines


def tune(workers: int = 1, log=print) -> dict:
    t0 = time.time()
    trades, held, funnel = windows(WINDOWS, tuple(VARIANTS), workers, log)
    OUT.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(OUT / "tune_trades.parquet")
    held.to_parquet(OUT / "tune_held.parquet")
    funnel.to_parquet(OUT / "tune_funnel.parquet")
    tab = table(trades, held)
    chosen, why = pick(tab)
    same = _reproduces_han(tab)
    result = {"machine": VERSION, "pick": chosen, "why": why, "v1_reproduces_han": same,
              "minutes": round((time.time() - t0) / 60, 1), "table": tab.to_dict("records")}
    if chosen is not None:
        result["power"] = power(_weekly(trades, held, ("V1", chosen)), chosen, HOLD_WEEKS * len(MARKETS),
                                np.random.default_rng(CONFIRM_SEED))
    (OUT / "tune.json").write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    lines = ["# H-AO: Volume Profile as a filter and as an entry on V1", "",
             "Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-09, f3efe2d) before its code. "
             f"Machine {VERSION}. Not a try: the sides are hindsight. The volume is tick volume.", "",
             "## The tuning (2021-22, 2023-24, July 2025 to June 2026)", "",
             f"V1 reproduces H-AN's table: {'yes' if same else 'unknown' if same is None else 'NO'}.", "",
             f"**The pick: {chosen or 'none'}.**", ""]
    for v, x in why.items():
        lines.append(f"- {v}: below V1 in every window {'yes' if x['below V1 in every window'] else 'no'}; ORACLE "
                     f"above zero a week {'yes' if x['ORACLE above zero a week in every window'] else 'no'}; pooled "
                     f"{x['pooled gain (points)']:+.1f} points under V1; keeps a quarter of V1's trades "
                     f"{'yes' if x[KEPT] else 'no'}; "
                     f"{'qualifies' if x['qualifies'] else 'does not qualify'}")
    if chosen is not None:
        pw = result["power"]
        lines += ["", f"**The confirmation's power, stated before it runs:** over {pw['market-weeks a window']} "
                  f"market-weeks the pick's p is {pw['mean difference (points)']:+.1f} points from V1's with a "
                  f"spread of {pw['spread (points)']:.1f}; a window shows it below by more than 1.645 spreads "
                  f"{pw['power']:.0%} of the time."]
    else:
        lines += ["", "No variant qualifies: H-AO fails at the tuning stage and July to November 2026 stays unspent."]
    lines += ["", "## Every variant", "", *_rows(tab), "", "## Orders (all windows)", "", *_funnel_lines(funnel), "",
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
        raise SystemExit("H-AO's confirmation has run once; it is not run again")
    chosen = json.loads((OUT / "tune.json").read_text(encoding="utf-8"))["pick"]
    if chosen is None:
        raise SystemExit("no variant qualified at the tuning stage: July to November 2026 stays unspent")
    name, *spec = HOLDOUT
    trades, held, funnel = windows({name: tuple(spec)}, ("V1", chosen), workers, log)
    trades.to_parquet(OUT / "confirm_trades.parquet")
    held.to_parquet(OUT / "confirm_held.parquet")
    tab = table(trades, held)
    tab = tab[tab["window"] == name]
    p = tab.set_index("variant")
    weekly = _weekly(trades, held, ("V1", chosen))
    pr = paired(weekly, chosen)
    checks = {"the pick's p is below V1's": bool(p.loc[chosen, "p_week"] < p.loc["V1", "p_week"]),
              "the paired difference's 90% interval is below zero": bool(pr["hi"] < 0),
              "the pick's ORACLE is above zero a week": bool(p.loc[chosen, "ORACLE_week"] > 0)}
    result = {"pick": chosen, "checks": checks, "passes": all(checks.values()), "paired": pr,
              "table": tab.to_dict("records"), "market_weeks": int(len(weekly))}
    done.write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    lines = ["", "## The confirmation (July to October 2026, run once)", "",
             f"**H-AO {'PASSES' if result['passes'] else 'FAILS'}** ({chosen} against V1).", "",
             *[f"- {'✓' if ok else '✗'} {k}" for k, ok in checks.items()], "",
             f"The pick's p minus V1's: {100 * pr['difference']:+.1f} points, 90% interval "
             f"[{100 * pr['lo']:+.1f}, {100 * pr['hi']:+.1f}] over {result['market_weeks']} market-weeks.", "",
             *_rows(tab), ""]
    with REPORT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return result


def main(argv: Optional[list] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m thesis_engine.hao", description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=("tune", "confirm"))
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args(argv)
    r = (tune if args.step == "tune" else confirm)(args.workers)
    print(json.dumps({k: v for k, v in r.items() if k != "table"}, indent=1, default=float))


if __name__ == "__main__":
    main()
