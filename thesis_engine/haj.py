"""H-AJ, V4's test on a year no version was shaped on (thesis-engine Requirement 20; docs/research/SEARCH_2018_2024.md,
registered 2026-11-06 in 959c2cc before V4's code existed).

- **Judged:** the eight traded focus markets in ``focus-2025-2026h1``, its bars from 1 January 2025, theses from the
  week of 6 July 2025 to the last complete week (3 July 2026); V4 and V1 with the same arms. Pass: V4's ORACLE net R
  a trade above zero with its 95% interval (resampling market-weeks) above zero, positive in at least 6 of the 8
  markets, and V4's break-even weekly hit rate counted a week below V1's on the same year.
- **Reported, not judged:** V4 on the development window (H-AG's arms, data and theses), the funnel by frame, each
  market, and buys and sells.

    python -m thesis_engine haj
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from agent.broker_profiles import load_profile
from thesis_engine import VERSION
from thesis_engine.hag import ARMS, MARKETS, SEED, SINCE, SNAPSHOT, _f, _trades, judge as measure
from thesis_engine.hah import _funnel_v2, _pct, judge, robust
from thesis_engine.replay import Journal, prepare, run
from thesis_engine.settings import V1, V4, Settings
from thesis_engine.thesis import research_theses

__all__ = ["by_frame", "main"]

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "research" / "thesis_engine" / "haj"
REPORT = REPO / "docs" / "research" / "THESIS_ENGINE_HAJ.md"
YEAR = REPO / "data" / "research" / "snapshots" / "focus-2025-2026h1"
YEAR_BARS_FROM = pd.Timestamp("2025-01-01", tz="UTC")             # nothing of 2023-2024 is read
YEAR_SINCE = pd.Timestamp("2025-07-06", tz="UTC").value           # theses from the week of 6 July 2025
RESEARCH = REPO / "data" / "research" / "thesis_engine"


def by_frame(j: Journal) -> Counter:
    """V4's hands by frame: sweeps by the pool's frame, setups, pull-backs, failures, expiries, CISDs without
    displacement, skips and entries."""
    out: Counter = Counter()
    for r in j.of("note"):
        what = r["note"]
        if what == "sweep":
            out[f"sweeps: {r['pool_tf']} pool, {r['frame']} setup"] += 1
            out["takeovers"] += r["took_over"] is not None
        elif what == "setup":
            out[f"setups: {r['frame']}"] += 1
        elif what == "pullback":
            out[f"pull-backs: {r['frame']}"] += 1
        elif what == "setup_failed":
            out[f"failed beyond the sweep: {r['frame']}"] += 1
        elif what == "setup_expired":
            out[f"expired, {'after' if r['touched'] else 'with no'} pull-back: {r['frame']}"] += 1
        elif what == "no_displacement":
            out[f"no displacement: {r['frame']}"] += 1
        elif what == "skip":
            out[f"skips: {r['reason'].lower()}"] += 1
        elif what == "hand":
            out[f"entries: {r['frame']} setup, {r['refine']} CISD"] += 1
    return out


def _window(name: str, folder: Path, bars_from: Optional[pd.Timestamp], since: int,
            versions: Tuple[Tuple[str, Settings], ...]) -> Tuple[Dict[str, pd.DataFrame], Dict[str, int], dict, dict]:
    """Each version's four arms over one window, one market at a time: trades, the market-weeks each arm held a
    thesis, the funnels and V4's hands by frame."""
    specs = load_profile("exness-standard-swapfree").specs()
    rows: Dict[str, List[dict]] = {v: [] for v, _ in versions}
    funnels = {v: {arm: Counter() for arm in ARMS} for v, _ in versions}
    frames = {arm: Counter() for arm in ARMS}
    weeks: Dict[str, int] = Counter()
    t0 = time.time()
    for market in MARKETS:
        m1 = pd.read_parquet(folder / f"{market}_M1.parquet")
        if bars_from is not None:
            m1 = m1[m1["time"] >= bars_from].reset_index(drop=True)
        m1 = m1[["time", "open", "high", "low", "close", "spread"]]
        ids: Dict[str, List[str]] = {}
        for v, s in versions:                                         # one prepared market in memory at a time
            mk = prepare(market, m1, s)
            for arm in ARMS:
                theses, refused = research_theses(market, mk.book, arm, seed=SEED, s=V1, since_from=since)
                if arm in ids:
                    assert ids[arm] == [th.id for th in theses], (market, arm, v)       # the same theses
                else:
                    ids[arm] = [th.id for th in theses]
                    weeks[arm] += len(theses)
                j = run(mk, theses, s, slippage=specs[market].stop_slippage)
                j.write(OUT / name / v / arm / f"{market}.jsonl")
                hands = {r["order_id"]: r for r in j.of("note") if r["note"] == "hand"}
                for t in _trades(j, market, arm):
                    h = hands.get(t["order_id"], {})
                    rows[v].append({**t, "frame": h.get("frame"), "refine": h.get("refine")})
                funnels[v][arm].update(_funnel_v2(j))
                funnels[v][arm].update({f"refused: {k}": n for k, n in refused.items()})
                if v == "V4":
                    frames[arm].update(by_frame(j))
            del mk
        print(f"{name} {market}: done ({time.time() - t0:.0f}s)", flush=True)
    return {v: pd.DataFrame(r) for v, r in rows.items()}, weeks, funnels, frames


def _arms_table(runs: Dict[str, dict]) -> List[str]:
    lines = ["| Run | Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | "
             "Markets > 0 | Buys | Sells | Median stop (spreads) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
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
    return lines


def _counts(title: str, table: Dict[str, Counter]) -> List[str]:
    keys = sorted({k for c in table.values() for k in c})
    lines = ["", title, "", "| | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    return lines + [f"| {k} | " + " | ".join(str(table[a].get(k, 0)) for a in ARMS) + " |" for k in keys]


def render(r: dict, v1: dict, dev: dict, older: Dict[str, dict], robustness: dict, trades: pd.DataFrame,
           funnels: dict, frames: dict, dev_frames: dict, seconds: float) -> str:
    bar = v1["break_even"]["per_week"]
    lines = [
        "# H-AJ: the Thesis Engine V4's test on a year no version was shaped on",
        "",
        f"Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-06, 959c2cc) before V4's code existed. Machine "
        f"{VERSION}, settings v4. Judged on `focus-2025-2026h1`: {len(MARKETS)} markets, bars from 1 January 2025, "
        "theses from the week of 6 July 2025 to the week closing 3 July 2026, against V1 on the same year. Not a "
        "try: its sides are hindsight. 2021-22 is reported, not judged: V4 was shaped by H-AI's results there.",
        "",
        f"**Verdict: H-AJ {'PASSES' if r['passes'] else 'FAILS'}.**",
        "",
        *[f"- {'✓' if ok else '✗'} {name}" for name, ok in r["checks"].items()],
        "",
        f"Break-even weekly hit rate on the judged year: V4 {_pct(r['break_even']['per_week'])} a week (the "
        f"registered measure), V1 {_pct(bar)}; a trade: V4 {_pct(r['break_even']['per_trade'])}, V1 "
        f"{_pct(v1['break_even']['per_trade'])}.",
        "",
        "## The judged year (July 2025 to June 2026)",
        "",
        *_arms_table({"V4": r, "V1": v1}),
        "",
        "## By market on the judged year (net R a trade)",
        "",
        "| Market | V4 ORACLE | V4 MIRROR | V1 ORACLE | V1 MIRROR |",
        "|---|---|---|---|---|",
    ]
    runs = {"V4": r, "V1": v1}
    for mkt in MARKETS:
        lines.append(f"| {mkt} | " + " | ".join(_f(runs[n]["arms"].get(a, {}).get("by_market", {}).get(mkt))
                                                for n, a in (("V4", "ORACLE"), ("V4", "MIRROR"), ("V1", "ORACLE"),
                                                             ("V1", "MIRROR"))) + " |")
    o = trades[trades["arm"] == "ORACLE"] if len(trades) else trades
    lines += ["", "## V4's ORACLE by setup frame on the judged year", "",
              "| Setup | Refining CISD | Trades | Net R a trade | Win |", "|---|---|---|---|---|"]
    if len(o):
        for (frame, refine), g in o.groupby(["frame", "refine"]):
            lines.append(f"| {frame} | {refine} | {len(g)} | {g['net_r'].mean():+.3f} | {(g['net_r'] > 0).mean():.0%} |")
    if robustness:
        exits = ", ".join(f"{k} {n} ({m:+.2f})" for k, (n, m) in sorted(robustness["exits"].items()))
        lines += ["", f"V4's ORACLE without its ten best trades: {_f(robustness['without the ten best'])}; median "
                  f"{_f(robustness['median'])}; win {robustness['win']:.0%}; exits {exits}."]
    lines += _counts("## V4's hands by frame on the judged year", frames)
    lines += _counts("## V4's funnel on the judged year", funnels["V4"])
    lines += _counts("## V1's funnel on the judged year", funnels["V1"])
    lines += ["", "## The development window, 2021-22 (reported, not judged)", "",
              "V4 on H-AG's arms, data and theses; V1, V2 and V3 from their own registered runs.", "",
              *_arms_table({"V4": dev, **older})]
    lines += _counts("## V4's hands by frame on 2021-22", dev_frames)
    lines += ["", f"Run time {seconds / 60:.1f} minutes.", ""]
    return "\n".join(lines)


def main() -> None:
    t0 = time.time()
    year, weeks, funnels, frames = _window("year", YEAR, YEAR_BARS_FROM, YEAR_SINCE, (("V4", V4), ("V1", V1)))
    dev, dev_weeks, _, dev_frames = _window("develop", SNAPSHOT, None, SINCE, (("V4", V4),))
    v1 = measure(year["V1"], weeks)
    bar = v1["break_even"]["per_week"]
    r = judge(year["V4"], weeks, bar if bar is not None else 1.0)
    d = judge(dev["V4"], dev_weeks, bar if bar is not None else 1.0)
    older: Dict[str, dict] = {}
    for name, path, key in (("V3", RESEARCH / "hai" / "result.json", "V3"), ("V2", RESEARCH / "hah" / "result.json", "V2"),
                            ("V1", RESEARCH / "hah" / "result.json", "V1")):
        if path.exists():
            got = json.loads(path.read_text(encoding="utf-8"))
            older[name] = got[key] if key in got else got["runs"][key]
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat([year["V4"].assign(run="V4", window="year"), year["V1"].assign(run="V1", window="year"),
               dev["V4"].assign(run="V4", window="develop")], ignore_index=True).to_parquet(OUT / "trades.parquet")
    robustness = robust(year["V4"])
    (OUT / "result.json").write_text(json.dumps({"verdict": r["passes"], "v1_week": bar, "V4": r, "V1": v1,
                                                 "V4_develop": d, "robustness": robustness}, indent=1, default=str),
                                     encoding="utf-8")
    REPORT.write_text(render(r, v1, d, older, robustness, year["V4"], funnels, frames, dev_frames, time.time() - t0),
                      encoding="utf-8")
    print(f"H-AJ {'PASSES' if r['passes'] else 'FAILS'}: " + json.dumps(r["checks"]))
    for name, x in (("V4 year", r), ("V1 year", v1), ("V4 develop", d)):
        for arm in ARMS:
            a = x["arms"].get(arm, {})
            if a.get("trades"):
                print(f"  {name} {arm}: {a['trades']} trades, net {a['net']:+.3f} [{a['ci'][0]:+.3f}, {a['ci'][1]:+.3f}],"
                      f" a week {a['per_week']:+.3f}, markets > 0: {a['markets_positive']}")
        print(f"  {name} break-even: {x['break_even']}")
