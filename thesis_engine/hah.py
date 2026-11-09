"""H-AH, V2's conversion test (thesis-engine Requirement 16; docs/research/SEARCH_2018_2024.md, registered 2026-11-05
and amended before it ran: ties between levels).

V2 on H-AG's data, markets, arms and theses, one market at a time. Its sides are hindsight, so it is not a try: it
measures whether the trader's trigger turns a right weekly side into R better than V1 did.

- **Pass:** ORACLE's net R a trade above zero with its 95% interval (resampling market-weeks) above zero, positive in
  at least 6 of the 8 markets, and the break-even weekly hit rate counted a week, −MIRROR / (ORACLE − MIRROR) on net
  R a market-week, below V1's (H-AG's result: 58.3%).
- **Beside it, not judged:** V1 rerun on the same theses (it must match H-AG's trades), the funnel with the limits
  placed, filled and expired, the companion (a third off at +3R, the rest's stop to the fill), each market, and buys
  and sells.

    python -m thesis_engine hah
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from agent.broker_profiles import load_profile
from thesis_engine import VERSION
from thesis_engine.hag import ARMS, MARKETS, MIN_MARKETS, SEED, SINCE, SNAPSHOT, _f, _funnel, _trades
from thesis_engine.hag import OUT as HAG, judge as hag_judge
from thesis_engine.replay import Journal, prepare, run
from thesis_engine.settings import V1, V2
from thesis_engine.thesis import research_theses

__all__ = ["RUNS", "judge", "main", "render"]

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "research" / "thesis_engine" / "hah"
REPORT = REPO / "docs" / "research" / "THESIS_ENGINE_HAH.md"
PARTIAL = (3.0, 1 / 3)                  # the companion: a third off at +3R, the rest's stop to the fill (TE-D23)
#: The runs: a name, its settings and its partial. V2 is judged; V1 and the companion are reported beside it.
RUNS = (("V2", V2, None), ("V1", V1, None), ("V2 + partial", V2, PARTIAL))
#: What the book reads from its settings: V1 and V2 must agree, so one book serves both.
BOOK_SETTINGS = ("dis", "level_frames", "e_frame", "e_swing_lookback", "adr_days")


def _funnel_v2(j: Journal) -> Dict[str, int]:
    """H-AG's funnel with the limits: expired, or cancelled when their thesis ended first; and the displacements."""
    events = Counter(r["event"] for r in j.of("fill"))
    return {**_funnel(j), "expired": events["EXPIRED"], "cancelled": events["CANCELLED"],
            "partials": events["PARTIAL"],
            "no displacement": sum(1 for r in j.of("note") if r["note"] == "no_displacement")}


def judge(trades: pd.DataFrame, weeks: Dict[str, int], v1_week: float) -> dict:
    """H-AG's measures, and H-AH's verdict: ``v1_week`` is V1's break-even weekly hit rate counted a week."""
    r = hag_judge(trades, weeks)
    o, p = r["arms"].get("ORACLE", {}), r["break_even"]["per_week"]
    r["checks"] = {
        "ORACLE net R > 0 with its interval above 0": bool(o.get("trades") and o["net"] > 0 and o["ci"][0] > 0),
        f"positive in at least {MIN_MARKETS} of {len(MARKETS)} markets":
            bool(o.get("trades") and o["markets_positive"] >= MIN_MARKETS),
        f"break-even weekly hit rate, a week, below V1's {v1_week:.1%}": bool(p is not None and p < v1_week)}
    r["passes"] = all(r["checks"].values())
    return r


def robust(trades: pd.DataFrame) -> dict:
    """ORACLE's trades without the ten best, its median and win rate, each year, and its exits."""
    o = trades[trades["arm"] == "ORACLE"].sort_values("net_r") if len(trades) else trades
    if o.empty:
        return {}
    year = pd.to_datetime(o["week"], utc=True).dt.year

    def mean(mask) -> Optional[float]:
        return float(o.loc[mask, "net_r"].mean()) if mask.any() else None

    return {"without the ten best": float(o["net_r"].iloc[:-10].mean()) if len(o) > 10 else None,
            "median": float(o["net_r"].median()), "win": float((o["net_r"] > 0).mean()),
            "2021": mean(year == 2021), "2022": mean(year == 2022),
            "exits": {k: [int(len(g)), float(g["net_r"].mean())] for k, g in o.groupby("reason")}}


def _same_trades(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    key = lambda t: sorted(zip(t["arm"], t["market"], t["order_id"], t["net_r"].round(9)))      # noqa: E731
    return len(a) == len(b) and key(a) == key(b)


def render(results: Dict[str, dict], robustness: Dict[str, dict], funnels: Dict[str, Dict[str, Counter]],
           v1_matches: bool, v1_week: float, seconds: float) -> str:
    v2 = results["V2"]
    be = {name: r["break_even"] for name, r in results.items()}
    lines = [
        "# H-AH: the Thesis Engine V2's conversion test",
        "",
        f"Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-05) before V2's code existed, and amended before "
        f"it ran (ties between levels). Machine {VERSION}, settings v2; `mt5-m1-develop`, {len(MARKETS)} markets, "
        "H-AG's theses from the week of 4 October 2021. Not a try: its sides are hindsight. The development data "
        "favours V2, because the stack gate came from a look at H-AG's trades.",
        "",
        f"**Verdict: H-AH {'PASSES' if v2['passes'] else 'FAILS'}.**",
        "",
        *[f"- {'✓' if ok else '✗'} {name}" for name, ok in v2["checks"].items()],
        "",
        f"Break-even weekly hit rate: {_pct(be['V2']['per_week'])} a week, the registered measure (V1 "
        f"{_pct(v1_week)}); {_pct(be['V2']['per_trade'])} a trade (V1 {_pct(be['V1']['per_trade'])}).",
        "",
        f"V1, rerun on the same theses, {'matches' if v1_matches else 'DOES NOT match'} H-AG's trades.",
        "",
        "## The arms",
        "",
        "| Run | Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | "
        "Markets > 0 | Buys | Sells | Median stop (spreads) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, r in results.items():
        for arm in ARMS:
            x = r["arms"].get(arm, {})
            if not x.get("trades"):
                lines.append(f"| {name} | {arm} | 0 | | | | | | | | | | | |")
                continue
            lines.append(f"| {name} | {arm} | {x['trades']} | {x['weeks']} | {_f(x['net'])} | [{x['ci'][0]:+.3f}, "
                         f"{x['ci'][1]:+.3f}] | {_f(x['gross'])} | {x['total']:+.1f} | {_f(x['per_week'])} | "
                         f"{x['win']:.0%} | {x['markets_positive']}/{len(MARKETS)} | {_f(x['buys'])} | "
                         f"{_f(x['sells'])} | {x['stop_spreads_median']:.1f} |")
    lines += ["", "## Break-even weekly hit rates", "", "| Run | A week | A trade |", "|---|---|---|",
              *[f"| {name} | {_pct(b['per_week'])} | {_pct(b['per_trade'])} |" for name, b in be.items()],
              "", "## ORACLE's robustness", "",
              "| Run | Without the ten best | Median | Win | 2021 | 2022 | Exits (count, mean R) |",
              "|---|---|---|---|---|---|---|"]
    for name, x in robustness.items():
        if not x:
            continue
        exits = ", ".join(f"{k} {n} ({m:+.2f})" for k, (n, m) in sorted(x["exits"].items()))
        lines.append(f"| {name} | {_f(x['without the ten best'])} | {_f(x['median'])} | {x['win']:.0%} | "
                     f"{_f(x['2021'])} | {_f(x['2022'])} | {exits} |")
    cols = [(name, arm) for name in results for arm in ("ORACLE", "MIRROR")]
    lines += ["", "## By market (net R a trade)", "",
              "| Market | " + " | ".join(f"{n} {a}" for n, a in cols) + " |", "|---|" + "---|" * len(cols)]
    for mkt in MARKETS:
        lines.append(f"| {mkt} | " + " | ".join(_f(results[n]["arms"].get(a, {}).get("by_market", {}).get(mkt))
                                                for n, a in cols) + " |")
    fcols = [("V1", "ORACLE"), ("V2", "ORACLE"), ("V1", "MIRROR"), ("V2", "MIRROR"), ("V2", "RANDOM"),
             ("V2", "W1TREND")]
    keys = sorted({k for n, a in fcols for k in funnels[n][a]})
    lines += ["", "## The funnel (all markets)", "", "| | " + " | ".join(f"{n} {a}" for n, a in fcols) + " |",
              "|---|" + "---|" * len(fcols)]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(str(funnels[n][a].get(k, 0)) for n, a in fcols) + " |")
    lines += ["", f"Run time {seconds / 60:.1f} minutes.", ""]
    return "\n".join(lines)


def _pct(x: Optional[float]) -> str:
    return "–" if x is None else f"{x:.1%}"


def main() -> None:
    assert all(getattr(V1, k) == getattr(V2, k) for k in BOOK_SETTINGS), "V1 and V2 must read the same book"
    specs = load_profile("exness-standard-swapfree").specs()
    v1_week = json.loads((HAG / "result.json").read_text(encoding="utf-8"))["break_even"]["per_week"]
    rows: Dict[str, List[dict]] = {name: [] for name, _, _ in RUNS}
    funnels: Dict[str, Dict[str, Counter]] = {name: {arm: Counter() for arm in ARMS} for name, _, _ in RUNS}
    weeks: Dict[str, int] = Counter()
    t0 = time.time()
    for market in MARKETS:
        mk = prepare(market, pd.read_parquet(SNAPSHOT / f"{market}_M1.parquet"), V2)
        for arm in ARMS:
            theses, refused = research_theses(market, mk.book, arm, seed=SEED, s=V1, since_from=SINCE)
            weeks[arm] += len(theses)
            for name, s, partial in RUNS:
                j = run(mk, theses, s, slippage=specs[market].stop_slippage, partial=partial)
                j.write(OUT / name.replace(" + ", "_").lower() / arm / f"{market}.jsonl")
                rows[name] += _trades(j, market, arm)
                funnels[name][arm].update(_funnel_v2(j))
                funnels[name][arm].update({f"refused: {k}": v for k, v in refused.items()})
        print(f"{market}: done ({time.time() - t0:.0f}s)", flush=True)
    trades = {name: pd.DataFrame(rows[name]) for name in rows}
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat([t.assign(run=name) for name, t in trades.items()], ignore_index=True).to_parquet(OUT / "trades.parquet")
    results = {name: judge(t, weeks, v1_week) for name, t in trades.items()}
    robustness = {name: robust(t) for name, t in trades.items()}
    v1_matches = _same_trades(trades["V1"], pd.read_parquet(HAG / "trades.parquet"))
    (OUT / "result.json").write_text(json.dumps({"verdict": results["V2"]["passes"], "v1_week": v1_week,
                                                 "v1_matches_hag": v1_matches, "runs": results,
                                                 "robustness": robustness}, indent=1, default=str), encoding="utf-8")
    REPORT.write_text(render(results, robustness, funnels, v1_matches, v1_week, time.time() - t0), encoding="utf-8")
    v2 = results["V2"]
    print(f"H-AH {'PASSES' if v2['passes'] else 'FAILS'}: " + json.dumps(v2["checks"]))
    print(f"  V1 rerun matches H-AG: {v1_matches}")
    for name, r in results.items():
        for arm in ARMS:
            x = r["arms"].get(arm, {})
            if x.get("trades"):
                print(f"  {name} {arm}: {x['trades']} trades, net {x['net']:+.3f} [{x['ci'][0]:+.3f}, "
                      f"{x['ci'][1]:+.3f}], a week {x['per_week']:+.3f}, markets > 0: {x['markets_positive']}")
        print(f"  {name} break-even: {r['break_even']}")
