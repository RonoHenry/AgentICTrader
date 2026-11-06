"""H-AI, V3's conversion test (thesis-engine Requirement 18; docs/research/SEARCH_2018_2024.md, registered 2026-11-06
in 3ef61a3 before V3's code existed).

V3 on H-AG's data, markets, arms and theses, one market at a time. Its sides are hindsight, so it is not a try: it
measures whether the dynamic execution frame turns a right weekly side into R better than V1 did.

- **Pass:** H-AH's three checks: ORACLE's net R a trade above zero with its 95% interval (resampling market-weeks)
  above zero, positive in at least 6 of the 8 markets, and the break-even weekly hit rate counted a week below V1's
  (58.3%).
- **Beside it, not judged:** V1 and V2 from H-AH's run, the funnel by the pool's frame and the execution frame, the
  market and limit entries, the limits filled and expired, each market, and buys and sells.

    python -m thesis_engine hai
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List

import pandas as pd

from agent.broker_profiles import load_profile
from thesis_engine import VERSION
from thesis_engine.hag import ARMS, MARKETS, SEED, SINCE, SNAPSHOT, _f, _trades
from thesis_engine.hah import OUT as HAH, _funnel_v2, _pct, judge, robust
from thesis_engine.replay import Journal, prepare, run
from thesis_engine.settings import MINUTES, V1, V3
from thesis_engine.thesis import research_theses

__all__ = ["by_frame", "main", "render"]

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "research" / "thesis_engine" / "hai"
REPORT = REPO / "docs" / "research" / "THESIS_ENGINE_HAI.md"


def by_frame(j: Journal) -> Counter:
    """The hands by the pool's frame and the execution frame: sweeps, takeovers, CISDs without displacement, skips
    and orders (market or limit)."""
    out: Counter = Counter()
    for r in j.of("note"):
        if r["note"] == "sweep":
            out[f"sweeps: {r['pool_tf']} pool, {r['frame']} child"] += 1
            out["takeovers"] += r["took_over"] is not None
        elif r["note"] == "no_displacement":
            out[f"no displacement: {r['frame']}"] += 1
        elif r["note"] == "skip":
            out[f"skips: {r['hand'].split(' ')[0]} {r['reason'].lower()}"] += 1
        elif r["note"] == "hand":
            out[f"orders: {r['frame']} {r['kind'].lower()}"] += 1
    return out


def _hands(j: Journal) -> Dict[str, dict]:
    return {r["order_id"]: r for r in j.of("note") if r["note"] == "hand"}


def render(r: dict, hah: dict, robustness: dict, trades: pd.DataFrame, funnels: Dict[str, Counter],
           frames: Dict[str, Counter], seconds: float) -> str:
    v1_week = hah["v1_week"]
    runs = {"V3": r, "V2": hah["runs"]["V2"], "V1": hah["runs"]["V1"]}
    lines = [
        "# H-AI: the Thesis Engine V3's conversion test",
        "",
        f"Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-06, 3ef61a3) before V3's code existed. Machine "
        f"{VERSION}, settings v3; `mt5-m1-develop`, {len(MARKETS)} markets, H-AG's theses from the week of 4 October "
        "2021. Not a try: its sides are hindsight. The development data favours V3: it was designed after V2's results "
        "on these data and a review of five weeks chosen from V2's trades.",
        "",
        f"**Verdict: H-AI {'PASSES' if r['passes'] else 'FAILS'}.**",
        "",
        *[f"- {'✓' if ok else '✗'} {name}" for name, ok in r["checks"].items()],
        "",
        f"Break-even weekly hit rate: {_pct(r['break_even']['per_week'])} a week, the registered measure (V1 "
        f"{_pct(v1_week)}, V2 {_pct(hah['runs']['V2']['break_even']['per_week'])}); "
        f"{_pct(r['break_even']['per_trade'])} a trade.",
        "",
        "## The arms",
        "",
        "| Run | Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | "
        "Markets > 0 | Buys | Sells | Median stop (spreads) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, x in runs.items():
        for arm in ARMS:
            a = x["arms"].get(arm, {})
            if not a.get("trades"):
                lines.append(f"| {name} | {arm} | 0 | | | | | | | | | | | |")
                continue
            lines.append(f"| {name} | {arm} | {a['trades']} | {a['weeks']} | {_f(a['net'])} | [{a['ci'][0]:+.3f}, "
                         f"{a['ci'][1]:+.3f}] | {_f(a['gross'])} | {a['total']:+.1f} | {_f(a['per_week'])} | "
                         f"{a['win']:.0%} | {a['markets_positive']}/{len(MARKETS)} | {_f(a['buys'])} | "
                         f"{_f(a['sells'])} | {a['stop_spreads_median']:.1f} |")
    lines += ["", "## ORACLE's robustness", "",
              "| Run | Without the ten best | Median | Win | 2021 | 2022 | Exits (count, mean R) |",
              "|---|---|---|---|---|---|---|"]
    for name, x in (("V3", robustness), ("V2", hah["robustness"]["V2"]), ("V1", hah["robustness"]["V1"])):
        if not x:
            continue
        exits = ", ".join(f"{k} {n} ({m:+.2f})" for k, (n, m) in sorted(x["exits"].items()))
        lines.append(f"| {name} | {_f(x['without the ten best'])} | {_f(x['median'])} | {x['win']:.0%} | "
                     f"{_f(x['2021'])} | {_f(x['2022'])} | {exits} |")
    o = trades[trades["arm"] == "ORACLE"] if len(trades) else trades
    lines += ["", "## ORACLE by execution frame and entry", "", "| Frame | Pool | Entry | Trades | Net R a trade | Win |",
              "|---|---|---|---|---|---|"]
    if len(o):
        g = o.groupby(["frame", "pool_tf", "entry_kind"])["net_r"].agg(["count", "mean", lambda s: (s > 0).mean()])
        order = sorted(g.index, key=lambda ix: (-MINUTES[ix[0]], -MINUTES[ix[1]], ix[2]))
        for ix in order:
            n, m, w = g.loc[ix]
            lines.append(f"| {ix[0]} | {ix[1]} | {ix[2].lower()} | {int(n)} | {m:+.3f} | {w:.0%} |")
    cols = [("V3", "ORACLE"), ("V3", "MIRROR"), ("V2", "ORACLE"), ("V1", "ORACLE")]
    lines += ["", "## By market (net R a trade)", "", "| Market | " + " | ".join(f"{n} {a}" for n, a in cols) + " |",
              "|---|" + "---|" * len(cols)]
    for mkt in MARKETS:
        lines.append(f"| {mkt} | " + " | ".join(_f(runs[n]["arms"].get(a, {}).get("by_market", {}).get(mkt))
                                                for n, a in cols) + " |")
    keys = sorted({k for f in funnels.values() for k in f})
    lines += ["", "## The funnel (all markets)", "", "| | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(str(funnels[a].get(k, 0)) for a in ARMS) + " |")
    keys = sorted({k for f in frames.values() for k in f})
    lines += ["", "## The hands by frame (all markets)", "", "| | " + " | ".join(ARMS) + " |",
              "|---|" + "---|" * len(ARMS)]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(str(frames[a].get(k, 0)) for a in ARMS) + " |")
    lines += ["", f"Run time {seconds / 60:.1f} minutes.", ""]
    return "\n".join(lines)


def main() -> None:
    specs = load_profile("exness-standard-swapfree").specs()
    hah = json.loads((HAH / "result.json").read_text(encoding="utf-8"))
    rows: List[dict] = []
    funnels: Dict[str, Counter] = {arm: Counter() for arm in ARMS}
    frames: Dict[str, Counter] = {arm: Counter() for arm in ARMS}
    weeks: Dict[str, int] = Counter()
    t0 = time.time()
    for market in MARKETS:
        mk = prepare(market, pd.read_parquet(SNAPSHOT / f"{market}_M1.parquet"), V3)
        for arm in ARMS:
            theses, refused = research_theses(market, mk.book, arm, seed=SEED, s=V1, since_from=SINCE)
            weeks[arm] += len(theses)
            j = run(mk, theses, V3, slippage=specs[market].stop_slippage)
            j.write(OUT / arm / f"{market}.jsonl")
            hands = _hands(j)
            for t in _trades(j, market, arm):
                h = hands.get(t["order_id"], {})
                rows.append({**t, "frame": h.get("frame"), "pool_tf": h.get("pool_tf"), "entry_kind": h.get("kind")})
            funnels[arm].update(_funnel_v2(j))
            funnels[arm].update({f"refused: {k}": v for k, v in refused.items()})
            frames[arm].update(by_frame(j))
        print(f"{market}: done ({time.time() - t0:.0f}s)", flush=True)
    for arm in ARMS:                                   # the same theses as H-AG's and H-AH's
        assert weeks[arm] == hah["runs"]["V1"]["arms"][arm]["weeks"], (arm, weeks[arm])
    trades = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(OUT / "trades.parquet")
    r = judge(trades, weeks, hah["v1_week"])
    robustness = robust(trades)
    (OUT / "result.json").write_text(json.dumps({"verdict": r["passes"], "v1_week": hah["v1_week"], "V3": r,
                                                 "robustness": robustness}, indent=1, default=str), encoding="utf-8")
    REPORT.write_text(render(r, hah, robustness, trades, funnels, frames, time.time() - t0), encoding="utf-8")
    print(f"H-AI {'PASSES' if r['passes'] else 'FAILS'}: " + json.dumps(r["checks"]))
    for arm in ARMS:
        x = r["arms"].get(arm, {})
        if x.get("trades"):
            print(f"  V3 {arm}: {x['trades']} trades, net {x['net']:+.3f} [{x['ci'][0]:+.3f}, {x['ci'][1]:+.3f}], "
                  f"a week {x['per_week']:+.3f}, markets > 0: {x['markets_positive']}")
    print(f"  V3 break-even: {r['break_even']}")
