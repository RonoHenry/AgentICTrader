"""H-AU, V6 and V7 against V1 (thesis-engine Requirement 28; docs/research/SEARCH_2018_2024.md, registered 2026-11-23
before V6's and V7's first run and before any 2018-2020 intraday bar was obtained).

The trader's backtest diary (26 October to 4 November 2026) showed V1 spending its one entry of the day on a small M5
sweep before the session's real manipulation, and their own entries coming after a raid of the Asia range, London's
extreme or the previous day's. Two single changes, frozen in ``settings.py``:
- **V6:** two entries a trading day (two a thesis, as V1);
- **V7:** V1's hand orders only once the trading day has raided the previous day's low (a buy) or high (a sell).

- ``explore``: V6 and V7 on the three windows already read (2021-22, 2023-24, July 2025 to June 2026) beside V1's
  registered runs there. Reported, never judged.
- ``judge``: V6, V7 and V1 on 2018-2020 intraday M1 for the eight traded focus markets (``m1-2018-2020``), which no
  version has read: the Exness server holds no intraday history before 16 July 2021. Theses from the week of 1 April
  2018 to the last complete week of 2020; the bars before warm the frames up.
  - Each of V6 and V7 passes with its ORACLE net R a trade above zero and its **97.5%** interval above zero (two
    versions judged together, Holm-style, as the protocol asks), positive in at least 6 of the 8 markets, and its
    break-even weekly hit rate counted a week below V1's on the same window.
  - V1 is reported by H-AG's own rule.

    python -m thesis_engine hau explore
    python -m thesis_engine hau judge
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from thesis_engine import VERSION
from thesis_engine.hag import ARMS, MARKETS, MIN_MARKETS, RESAMPLES, SEED, SINCE, SNAPSHOT, _f, judge as measure
from thesis_engine.hah import _pct
from thesis_engine.haj import YEAR, YEAR_BARS_FROM, YEAR_SINCE, _arms_table, _counts, _window
from thesis_engine.hal import TEST, TEST_SINCE
from thesis_engine.settings import V1, V6, V7

__all__ = ["judge_version", "main"]

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "research" / "thesis_engine" / "hau"
REPORT = REPO / "docs" / "research" / "THESIS_ENGINE_HAU.md"
WINDOW = REPO / "data" / "research" / "snapshots" / "m1-2018-2020"
WINDOW_SINCE = pd.Timestamp("2018-04-01", tz="UTC").value            # theses from the week of 1 April 2018
LEVEL = 1 - 0.05 / 2                                                   # two versions judged together (Holm-style)
RESEARCH = REPO / "data" / "research" / "thesis_engine"


def _interval(t: pd.DataFrame, level: float) -> tuple:
    """The ``level`` interval of the mean net R a trade, resampling market-weeks (H-AG's resampling, its seed)."""
    rng = np.random.default_rng(SEED)
    keys = (t["market"] + "|" + t["week"].astype(str)).to_numpy()
    uniq, inv = np.unique(keys, return_inverse=True)
    values = t["net_r"].to_numpy(float)
    sums = np.bincount(inv, weights=values, minlength=len(uniq))
    counts = np.bincount(inv, minlength=len(uniq)).astype(float)
    pick = rng.integers(0, len(uniq), size=(RESAMPLES, len(uniq)))
    means = sums[pick].sum(axis=1) / np.maximum(counts[pick].sum(axis=1), 1)
    tail = (1 - level) / 2 * 100
    return float(np.percentile(means, tail)), float(np.percentile(means, 100 - tail))


def judge_version(trades: pd.DataFrame, weeks: Dict[str, int], v1_week: float) -> dict:
    """H-AG's measures, and H-AU's verdict for one version against V1's weekly break-even on the same window."""
    r = measure(trades, weeks)
    o, p = r["arms"].get("ORACLE", {}), r["break_even"]["per_week"]
    ci = _interval(trades[trades["arm"] == "ORACLE"], LEVEL) if o.get("trades") else (None, None)
    r["ci_judged"] = ci
    r["checks"] = {
        f"ORACLE net R > 0 with its {LEVEL:.1%} interval above 0": bool(o.get("trades") and o["net"] > 0 and ci[0] > 0),
        f"positive in at least {MIN_MARKETS} of {len(MARKETS)} markets":
            bool(o.get("trades") and o["markets_positive"] >= MIN_MARKETS),
        f"break-even weekly hit rate, a week, below V1's {_pct(v1_week)}": bool(p is not None and p < v1_week)}
    r["passes"] = all(r["checks"].values())
    return r


def _window_rows(runs: Dict[str, dict]) -> list:
    return [f"| {name} | {_pct(x['break_even']['per_week'])} | {_pct(x['break_even']['per_trade'])} | "
            f"{x['arms'].get('ORACLE', {}).get('trades', 0)} | {_f(x['arms'].get('ORACLE', {}).get('net'))} | "
            f"{x['arms'].get('ORACLE', {}).get('markets_positive', '-')} |" for name, x in runs.items()]


def explore() -> None:
    """V6 and V7 on the three read windows, beside V1 there. Reported, never judged."""
    t0 = time.time()
    windows = {"2021-22": (SNAPSHOT, None, SINCE), "2023-24": (TEST, None, TEST_SINCE),
               "2025-26": (YEAR, YEAR_BARS_FROM, YEAR_SINCE)}
    results: Dict[str, Dict[str, dict]] = {}
    funnels = {}
    for name, (folder, bars_from, since) in windows.items():
        runs, weeks, fun, _ = _window(f"explore-{name}", folder, bars_from, since, (("V1", V1), ("V6", V6), ("V7", V7)),
                                      OUT)
        results[name] = {v: measure(runs[v], weeks) for v in runs}
        funnels[name] = fun
        for v, x in results[name].items():
            print(f"{name} {v}: break-even a week {_pct(x['break_even']['per_week'])}, ORACLE "
                  f"{x['arms']['ORACLE'].get('trades', 0)} trades {_f(x['arms']['ORACLE'].get('net'))}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "explore.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    lines = ["# H-AU explore: V6 and V7 on the windows already read (reported, never judged)", "",
             f"Machine {VERSION}. Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-23). These windows "
             "shaped V1 and its earlier versions, so nothing here is evidence; the judged run is on 2018-2020.", ""]
    for name, runs in results.items():
        lines += [f"## {name}", "", "| Version | Break-even a week | A trade | ORACLE trades | ORACLE net R | Markets > 0 |",
                  "|---|---|---|---|---|---|", *_window_rows(runs), "", *_arms_table(runs), ""]
        for v in ("V6", "V7"):
            lines += _counts(f"### {v}'s funnel, {name}", funnels[name][v])
        lines.append("")
    lines.append(f"Run time {(time.time() - t0) / 60:.1f} minutes.")
    (OUT / "explore.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {OUT / 'explore.md'}")


def judge() -> None:
    """The registered run on 2018-2020, once."""
    if not (WINDOW / "XAUUSD_M1.parquet").exists():
        raise SystemExit(f"{WINDOW} is missing: export the eight markets' M1 for 2018-01-01 to 2021-01-01 first "
                         "(see H-AU's registration for the sources)")
    if (OUT / "result.json").exists():
        raise SystemExit("H-AU has run: its result is in data/research/thesis_engine/hau/result.json")
    t0 = time.time()
    runs, weeks, funnels, _ = _window("judge", WINDOW, None, WINDOW_SINCE, (("V6", V6), ("V7", V7), ("V1", V1)), OUT)
    v1 = measure(runs["V1"], weeks)
    bar = v1["break_even"]["per_week"]
    v6 = judge_version(runs["V6"], weeks, bar if bar is not None else 0.0)
    v7 = judge_version(runs["V7"], weeks, bar if bar is not None else 0.0)
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat([runs[v].assign(run=v) for v in runs], ignore_index=True).to_parquet(OUT / "trades.parquet")
    (OUT / "result.json").write_text(json.dumps({"V6": v6, "V7": v7, "V1": v1, "level": LEVEL,
                                                 "manifest": json.loads((WINDOW / "manifest.json").read_text())},
                                                indent=1, default=str), encoding="utf-8")
    lines = ["# H-AU: V6 and V7 judged on 2018-2020", "",
             f"Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-23) before the window's bars were obtained. "
             f"Machine {VERSION}. `m1-2018-2020`: {len(MARKETS)} markets, theses from the week of 1 April 2018. Not a "
             "try: its sides are hindsight.", ""]
    for name, r in (("V6 (two entries a day)", v6), ("V7 (the previous day's raid)", v7)):
        lines += [f"**{name}: {'PASSES' if r['passes'] else 'FAILS'}**", "",
                  *[f"- {'✓' if ok else '✗'} {c}" for c, ok in r["checks"].items()], ""]
    lines += [f"**V1 by H-AG's own rule: {'PASSES' if v1['passes'] else 'FAILS'}**", "",
              *[f"- {'✓' if ok else '✗'} {c}" for c, ok in v1["checks"].items()], "",
              "| Version | Break-even a week | A trade | ORACLE trades | ORACLE net R | Markets > 0 |",
              "|---|---|---|---|---|---|", *_window_rows({"V6": v6, "V7": v7, "V1": v1}), "",
              *_arms_table({"V6": v6, "V7": v7, "V1": v1}), "", "## By market (ORACLE net R a trade)", "",
              "| Market | V6 | V7 | V1 |", "|---|---|---|---|"]
    for mkt in MARKETS:
        lines.append(f"| {mkt} | " + " | ".join(_f(r["arms"].get("ORACLE", {}).get("by_market", {}).get(mkt))
                                                for r in (v6, v7, v1)) + " |")
    for v in ("V6", "V7", "V1"):
        lines += _counts(f"## {v}'s funnel", funnels[v])
    lines += ["", f"Run time {(time.time() - t0) / 60:.1f} minutes.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    for name, r in (("V6", v6), ("V7", v7), ("V1", v1)):
        print(f"{name} {'PASSES' if r['passes'] else 'FAILS'}: {json.dumps(r['checks'])}")
    print(f"report: {REPORT}")


def main(which: str) -> None:
    {"explore": explore, "judge": judge}[which]()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "explore")
