"""H-AG, the conversion test (thesis-engine Requirement 13; docs/research/SEARCH_2018_2024.md, registered 2026-11-05).

The V1 machine on the development window's M1 (``mt5-m1-develop``), eight traded focus markets, one market at a
time. Its sides are hindsight, so it is not a try: it measures how well the machine turns a right weekly side into R.

- **Arms:** ORACLE (the week's real side), MIRROR (the opposite), RANDOM (a seeded coin flip) and W1TREND (the last
  W1 candle's LE-D15 trend, a simple higher-timeframe side), each completed by the nearest-pool rule.
- **Theses** from the week of 4 October 2021; the bars before warm the frames up. The last complete week is the
  last read.
- **Pass:** ORACLE's net R a trade above zero with its 95% interval (resampling market-weeks) above zero, positive in
  at least 6 of the 8 markets, and the break-even weekly hit rate −MIRROR / (ORACLE − MIRROR) at most 60%.

    python -m thesis_engine hag
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from agent.broker_profiles import load_profile
from thesis_engine import VERSION
from thesis_engine.replay import Journal, prepare, run
from thesis_engine.settings import V1, Settings
from thesis_engine.thesis import research_theses

__all__ = ["ARMS", "MARKETS", "judge", "main", "render"]

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO / "data" / "research" / "snapshots" / "mt5-m1-develop"
OUT = REPO / "data" / "research" / "thesis_engine" / "hag"
REPORT = REPO / "docs" / "research" / "THESIS_ENGINE_HAG.md"
MARKETS = ("XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")
ARMS = ("ORACLE", "MIRROR", "RANDOM", "W1TREND")
SINCE = pd.Timestamp("2021-10-03", tz="UTC").value
RESAMPLES, SEED, MIN_MARKETS, BAR = 10_000, 20261105, 6, 0.60
HN_STACK = 0.17                       # H-N's selection stack with the week's real side (2026-10-30), for comparison


def _trades(j: Journal, market: str, arm: str) -> List[dict]:
    weeks = {th["id"]: th["since"] for th in j.of("thesis")}
    return [{**t, "market": market, "arm": arm, "week": weeks[t["thesis_id"]]} for t in j.of("trade")]


def _funnel(j: Journal) -> Dict[str, int]:
    moves = Counter((r["frm"], r["to"]) for r in j.of("transition"))
    notes = Counter(r["note"] for r in j.of("note"))
    at_level = {r["thesis_id"] for r in j.of("transition") if r["to"] == "AT_LEVEL"}
    armed = {r["thesis_id"] for r in j.of("transition") if r["to"] == "ARMED"}
    return {"theses": len(j.of("thesis")), "theses at a level": len(at_level), "theses armed": len(armed),
            "sweeps": notes["sweep"], "hands failed": notes["hand_failed"], "skips": len(j.of("skip")),
            "orders": len(j.of("intent")), "fills": sum(1 for r in j.of("fill") if r["event"] == "FILLED"),
            "rejected": sum(1 for r in j.of("fill") if r["event"] == "REJECTED"),
            **{f"ends {k.lower()}": v for k, v in Counter(r["end"] for r in j.of("note")
                                                         if r["note"] == "thesis_end").items()},
            **{f"skips {k.lower()}": v for k, v in Counter(r["reason"] for r in j.of("skip")).items()},
            "at level → armed": moves[("AT_LEVEL", "ARMED")]}


def _interval(keys: np.ndarray, values: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    """The 95% interval of the mean a trade, resampling the clusters ``keys`` (market-weeks)."""
    uniq, inv = np.unique(keys, return_inverse=True)
    sums = np.bincount(inv, weights=values, minlength=len(uniq))
    counts = np.bincount(inv, minlength=len(uniq)).astype(float)
    pick = rng.integers(0, len(uniq), size=(RESAMPLES, len(uniq)))
    means = sums[pick].sum(axis=1) / np.maximum(counts[pick].sum(axis=1), 1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def judge(trades: pd.DataFrame, weeks: Dict[str, int]) -> dict:
    """Each arm's measures, and H-AG's verdict. ``weeks``: the market-weeks each arm held a thesis."""
    rng = np.random.default_rng(SEED)
    out: dict = {"arms": {}}
    for arm in ARMS:
        t = trades[trades["arm"] == arm]
        if t.empty:
            out["arms"][arm] = {"trades": 0}
            continue
        keys = (t["market"] + "|" + t["week"].astype(str)).to_numpy()
        lo, hi = _interval(keys, t["net_r"].to_numpy(float), rng)
        by_market = t.groupby("market")["net_r"].mean()
        out["arms"][arm] = {
            "trades": int(len(t)), "net": float(t["net_r"].mean()), "gross": float(t["gross_r"].mean()),
            "ci": (lo, hi), "total": float(t["net_r"].sum()), "win": float((t["net_r"] > 0).mean()),
            "per_week": float(t["net_r"].sum() / max(weeks.get(arm, 0), 1)), "weeks": int(weeks.get(arm, 0)),
            "markets_positive": int((by_market > 0).sum()), "by_market": by_market.round(3).to_dict(),
            "buys": float(t.loc[t["direction"] == "LONG", "net_r"].mean()) if (t["direction"] == "LONG").any() else None,
            "sells": float(t.loc[t["direction"] == "SHORT", "net_r"].mean()) if (t["direction"] == "SHORT").any() else None,
            "stop_spreads_median": float(t["risk_spreads"].median()),
            "exits": t["reason"].value_counts().to_dict()}
    o, m = out["arms"].get("ORACLE", {}), out["arms"].get("MIRROR", {})
    p_trade = p_week = None
    if o.get("trades") and m.get("trades") and o["net"] > m["net"]:
        p_trade = -m["net"] / (o["net"] - m["net"])
    if o.get("trades") and m.get("trades") and o["per_week"] > m["per_week"]:
        p_week = -m["per_week"] / (o["per_week"] - m["per_week"])
    out["break_even"] = {"per_trade": p_trade, "per_week": p_week}
    checks = {"ORACLE net R > 0 with its interval above 0": bool(o.get("trades") and o["ci"][0] > 0 and o["net"] > 0),
              f"positive in at least {MIN_MARKETS} of {len(MARKETS)} markets":
                  bool(o.get("trades") and o["markets_positive"] >= MIN_MARKETS),
              f"break-even weekly hit rate at most {BAR:.0%}": bool(p_trade is not None and p_trade <= BAR)}
    out["checks"], out["passes"] = checks, all(checks.values())
    return out


def _f(x, d=3) -> str:
    return "–" if x is None else f"{x:+.{d}f}" if isinstance(x, float) else str(x)


def render(r: dict, funnels: Dict[str, Counter], dropped: Dict[str, dict], s: Settings, seconds: float) -> str:
    a = r["arms"]
    lines = [
        "# H-AG: the Thesis Engine's conversion test",
        "",
        f"Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-05) before it ran. Machine {VERSION}, settings "
        f"{s.version}; `mt5-m1-develop`, {len(MARKETS)} markets, theses from the week of 4 October 2021. "
        f"Not a try: its sides are hindsight.",
        "",
        f"**Verdict: H-AG {'PASSES' if r['passes'] else 'FAILS'}.**",
        "",
        *[f"- {'✓' if ok else '✗'} {name}" for name, ok in r["checks"].items()],
        "",
        f"Break-even weekly hit rate: {_f(r['break_even']['per_trade'], 3)} a trade (the registered measure), "
        f"{_f(r['break_even']['per_week'], 3)} a week (the trades a week included).",
        "",
        "## The arms",
        "",
        "| Arm | Trades | Weeks | Net R a trade | 95% (market-weeks) | Gross | Total R | R a week | Win | "
        "Markets > 0 | Buys | Sells | Median stop (spreads) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in ARMS:
        x = a.get(arm, {})
        if not x.get("trades"):
            lines.append(f"| {arm} | 0 | | | | | | | | | | | |")
            continue
        lines.append(f"| {arm} | {x['trades']} | {x['weeks']} | {_f(x['net'])} | [{x['ci'][0]:+.3f}, "
                     f"{x['ci'][1]:+.3f}] | {_f(x['gross'])} | {x['total']:+.1f} | {_f(x['per_week'])} | "
                     f"{x['win']:.0%} | {x['markets_positive']}/{len(MARKETS)} | {_f(x['buys'])} | "
                     f"{_f(x['sells'])} | {x['stop_spreads_median']:.1f} |")
    lines += ["", f"For comparison, H-N's selection stack with the week's real side made {HN_STACK:+.2f}R a trade "
              "(2026-10-30, a different trigger and exits).", "", "## By market (net R a trade)", "",
              "| Market | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for mkt in MARKETS:
        lines.append(f"| {mkt} | " + " | ".join(_f(a.get(arm, {}).get("by_market", {}).get(mkt)) for arm in ARMS)
                     + " |")
    lines += ["", "## Exits", "", "| Arm | " + " | ".join(("SL", "TP", "TIME", "END")) + " |", "|---|---|---|---|---|"]
    for arm in ARMS:
        ex = a.get(arm, {}).get("exits", {})
        lines.append(f"| {arm} | " + " | ".join(str(ex.get(k, 0)) for k in ("SL", "TP", "TIME", "END")) + " |")
    keys = sorted({k for f in funnels.values() for k in f})
    lines += ["", "## The funnel (all markets)", "", "| | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(str(funnels.get(arm, Counter()).get(k, 0)) for arm in ARMS) + " |")
    lines += ["", "## The data", "", f"Bars dropped by the clock: {json.dumps(dropped)}.",
              f"Run time {seconds / 60:.1f} minutes.", ""]
    return "\n".join(lines)


def main() -> None:
    s = V1
    specs = load_profile("exness-standard-swapfree").specs()
    rows: List[dict] = []
    funnels: Dict[str, Counter] = {arm: Counter() for arm in ARMS}
    weeks: Dict[str, int] = Counter()
    dropped: Dict[str, dict] = {}
    t0 = time.time()
    for market in MARKETS:
        mk = prepare(market, pd.read_parquet(SNAPSHOT / f"{market}_M1.parquet"), s)
        dropped[market] = mk.dropped
        for arm in ARMS:
            theses, refused = research_theses(market, mk.book, arm, seed=SEED, s=s, since_from=SINCE)
            j = run(mk, theses, s, slippage=specs[market].stop_slippage)
            j.write(OUT / arm / f"{market}.jsonl")
            rows += _trades(j, market, arm)
            funnels[arm].update(_funnel(j))
            funnels[arm].update({f"refused: {k}": v for k, v in refused.items()})
            weeks[arm] += len(theses)
        print(f"{market}: done ({time.time() - t0:.0f}s)", flush=True)
    trades = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(OUT / "trades.parquet")
    r = judge(trades, weeks)
    (OUT / "result.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    REPORT.write_text(render(r, funnels, dropped, s, time.time() - t0), encoding="utf-8")
    print(f"H-AG {'PASSES' if r['passes'] else 'FAILS'}: " + json.dumps(r["checks"]))
    for arm in ARMS:
        x = r["arms"].get(arm, {})
        if x.get("trades"):
            print(f"  {arm}: {x['trades']} trades, net {x['net']:+.3f} [{x['ci'][0]:+.3f}, {x['ci'][1]:+.3f}], "
                  f"markets > 0: {x['markets_positive']}")
    print(f"  break-even: {r['break_even']}")
