"""H-AL, V5's judged run on 2023-2024 (thesis-engine Requirement 22; docs/research/SEARCH_2018_2024.md, registered
2026-11-06 in 4100a4e before V5's code existed and before 2023-2024 was exported).

- **Judged:** M1 for the eight traded focus markets in ``mt5-m1-test`` (exported from the trader's MT5 terminal,
  1 October 2022 to 1 January 2025), theses from the week of 1 January 2023 to the last complete week of 2024; V5 and
  V1 with ORACLE, MIRROR, RANDOM and W1TREND.
  - V5 passes with its ORACLE net R a trade above zero and its 95% interval above zero, positive in at least 6 of the
    8 markets, and its break-even weekly hit rate counted a week below V1's on the same years.
  - V1 is judged by H-AG's own rule, the test-window run its pass was owed: ORACLE above zero with its interval,
    6 of 8 markets, the break-even weekly hit rate a trade at most 60%.
- **Reported, not judged:** V5 on 2021-22 and 2025-26, V1's hands kept 02:00-04:00 on the judged years (H-AK's
  filter), the funnel, each market, and buys and sells.

    python -m thesis_engine hal
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict

import pandas as pd

from thesis_engine import VERSION
from thesis_engine.hag import ARMS, MARKETS, SINCE, SNAPSHOT, _f, judge as measure
from thesis_engine.hah import _pct, judge
from thesis_engine.haj import YEAR, YEAR_BARS_FROM, YEAR_SINCE, _arms_table, _counts, _window
from thesis_engine.settings import V1, V5

__all__ = ["main", "render"]

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "research" / "thesis_engine" / "hal"
REPORT = REPO / "docs" / "research" / "THESIS_ENGINE_HAL.md"
TEST = REPO / "data" / "research" / "snapshots" / "mt5-m1-test"
TEST_SINCE = pd.Timestamp("2023-01-01", tz="UTC").value            # theses from the week of 1 January 2023
RESEARCH = REPO / "data" / "research" / "thesis_engine"


def london(trades: pd.DataFrame) -> pd.DataFrame:
    """H-AK's filter: the hands entered between 02:00 and 04:00 New York."""
    if trades.empty:
        return trades
    local = pd.to_datetime(trades["placed_at"], utc=True).dt.tz_convert("America/New_York")
    hour = local.dt.hour + local.dt.minute / 60
    return trades[(hour >= 2) & (hour < 4)]


def render(v5: dict, v1: dict, filtered: dict, dev: dict, year: dict, older: Dict[str, dict], funnels: dict,
           seconds: float) -> str:
    lines = [
        "# H-AL: the Thesis Engine V5's judged run on 2023-2024",
        "",
        f"Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-06, 4100a4e) before V5's code existed and before "
        f"2023-2024 was exported. Machine {VERSION}. `mt5-m1-test`: {len(MARKETS)} markets, M1 from 1 October 2022, "
        "theses from the week of 1 January 2023 to the last complete week of 2024. Not a try: its sides are hindsight. "
        "The last unread window of 2018-2024.",
        "",
        f"**Verdict: H-AL {'PASSES' if v5['passes'] else 'FAILS'}** (V5, V1 in the 02:00-04:00 New York window).",
        "",
        *[f"- {'✓' if ok else '✗'} {name}" for name, ok in v5["checks"].items()],
        "",
        f"**V1 by H-AG's own rule on the same years: {'PASSES' if v1['passes'] else 'FAILS'}.**",
        "",
        *[f"- {'✓' if ok else '✗'} {name}" for name, ok in v1["checks"].items()],
        "",
        f"Break-even weekly hit rate on 2023-2024, a week: V5 {_pct(v5['break_even']['per_week'])}, V1 "
        f"{_pct(v1['break_even']['per_week'])}, V1's hands kept 02:00-04:00 (H-AK's filter) "
        f"{_pct(filtered['break_even']['per_week'])}. A trade: V5 {_pct(v5['break_even']['per_trade'])}, V1 "
        f"{_pct(v1['break_even']['per_trade'])}.",
        "",
        "## The judged years (2023-2024)",
        "",
        *_arms_table({"V5": v5, "V1": v1, "V1 kept 02:00-04:00": filtered}),
        "",
        "## By market on 2023-2024 (net R a trade)",
        "",
        "| Market | V5 ORACLE | V5 MIRROR | V1 ORACLE | V1 MIRROR |",
        "|---|---|---|---|---|",
    ]
    runs = {"V5": v5, "V1": v1}
    for mkt in MARKETS:
        lines.append(f"| {mkt} | " + " | ".join(_f(runs[n]["arms"].get(a, {}).get("by_market", {}).get(mkt))
                                                for n, a in (("V5", "ORACLE"), ("V5", "MIRROR"), ("V1", "ORACLE"),
                                                             ("V1", "MIRROR"))) + " |")
    lines += _counts("## V5's funnel on 2023-2024", funnels["V5"])
    lines += _counts("## V1's funnel on 2023-2024", funnels["V1"])
    lines += ["", "## V5 on the windows it was chosen on (reported, not judged)", "",
              "2021-22 (H-AG's data and theses) and July 2025 to June 2026 (H-AJ's), V1 from their registered runs.", "",
              *_arms_table({"V5 2021-22": dev, **({"V1 2021-22": older["V1 2021-22"]} if "V1 2021-22" in older else {}),
                            "V5 2025-26": year, **({"V1 2025-26": older["V1 2025-26"]} if "V1 2025-26" in older else {})}),
              "", f"Run time {seconds / 60:.1f} minutes.", ""]
    return "\n".join(lines)


def main() -> None:
    if not (TEST / "XAUUSD_M1.parquet").exists():
        raise SystemExit(f"{TEST} is missing: export it after H-AL's registration (scripts/export_mt5_history.py "
                         "--name mt5-m1-test --timeframes M1 --start 2022-10-01 --end 2025-01-01)")
    t0 = time.time()
    test, weeks, funnels, _ = _window("test", TEST, None, TEST_SINCE, (("V5", V5), ("V1", V1)), OUT)
    dev, dev_weeks, _, _ = _window("develop", SNAPSHOT, None, SINCE, (("V5", V5),), OUT)
    year, year_weeks, _, _ = _window("year", YEAR, YEAR_BARS_FROM, YEAR_SINCE, (("V5", V5),), OUT)
    v1 = measure(test["V1"], weeks)                                   # H-AG's own rule
    bar = v1["break_even"]["per_week"]
    v5 = judge(test["V5"], weeks, bar if bar is not None else 1.0)
    filtered = measure(london(test["V1"]), weeks)
    d, y = measure(dev["V5"], dev_weeks), measure(year["V5"], year_weeks)
    older: Dict[str, dict] = {}
    for name, path, key in (("V1 2021-22", RESEARCH / "hah" / "result.json", None),
                            ("V1 2025-26", RESEARCH / "haj" / "result.json", "V1")):
        if path.exists():
            got = json.loads(path.read_text(encoding="utf-8"))
            older[name] = got["runs"]["V1"] if key is None else got[key]
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat([test["V5"].assign(run="V5", window="test"), test["V1"].assign(run="V1", window="test"),
               dev["V5"].assign(run="V5", window="develop"), year["V5"].assign(run="V5", window="year")],
              ignore_index=True).to_parquet(OUT / "trades.parquet")
    (OUT / "result.json").write_text(json.dumps({"verdict_v5": v5["passes"], "verdict_v1": v1["passes"], "V5": v5,
                                                 "V1": v1, "V1_london": filtered, "V5_develop": d, "V5_year": y},
                                                indent=1, default=str), encoding="utf-8")
    REPORT.write_text(render(v5, v1, filtered, d, y, older, funnels, time.time() - t0), encoding="utf-8")
    print(f"H-AL {'PASSES' if v5['passes'] else 'FAILS'}: " + json.dumps(v5["checks"]))
    print(f"V1 by H-AG's rule {'PASSES' if v1['passes'] else 'FAILS'}: " + json.dumps(v1["checks"]))
    for name, x in (("V5 test", v5), ("V1 test", v1), ("V1 kept 02-04 test", filtered), ("V5 develop", d),
                    ("V5 year", y)):
        for arm in ARMS:
            a = x["arms"].get(arm, {})
            if a.get("trades"):
                print(f"  {name} {arm}: {a['trades']} trades, net {a['net']:+.3f} [{a['ci'][0]:+.3f}, {a['ci'][1]:+.3f}],"
                      f" a week {a['per_week']:+.3f}, markets > 0: {a['markets_positive']}")
        print(f"  {name} break-even: {x['break_even']}")
