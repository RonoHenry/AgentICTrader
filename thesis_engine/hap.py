"""H-AP: AlgoMindDIS v4, the week as it unfolds, through the Thesis Engine at V1 (algomind-dis Requirement 19;
docs/research/SEARCH_2018_2024.md, registered 2026-11-09 in 3bf3e87 before this code). Try 32.

- **dev:** one run on 2021-22. UNFOLD, MIRROR and RANDOM on the same commits, with NO_WITHDRAW and V1_GEOMETRY reported
  beside them, not judged.
- **test:** one run on 2023-24, only after a pass, judged by the same rule.

    python -m thesis_engine.hap dev
    python -m thesis_engine.hap test
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from agent.broker_profiles import load_profile
from algomind_dis.unfold import Read, events, mirror_geometry, reads
from thesis_engine import VERSION
from thesis_engine.hag import MARKETS, SINCE, SNAPSHOT, _interval
from thesis_engine.hal import TEST, TEST_SINCE
from thesis_engine.records import Thesis
from thesis_engine.replay import Journal, Market, prepare, run
from thesis_engine.settings import V1
from thesis_engine.thesis import complete, file_theses

__all__ = ["ARMS", "judge", "main", "market_run", "thesis_of", "v1_geometry"]

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "research" / "thesis_engine" / "hap"
REPORT = REPO / "docs" / "research" / "THESIS_ENGINE_HAP.md"
DIS_FILE = REPO / "data" / "research" / "theses" / "algomind_dis_v1.json"
ARMS = ("UNFOLD", "MIRROR", "RANDOM")
COMPANIONS = ("NO_WITHDRAW", "V1_GEOMETRY")
SEED = 20261109
MIN_MARKETS, DROP_BEST = 6, 5


def thesis_of(market: str, book, r: Read, kind: str, source: str) -> Optional[Thesis]:
    """A read as a thesis, on its own side (UNFOLD) or the other (MIRROR); None when the other side has no draw."""
    if kind == "UNFOLD":
        side, draw, protected = r.side, r.draw, r.protected
    else:
        g = mirror_geometry(book, r)
        if g is None:
            return None
        side, draw, protected = g
    return Thesis(market, side, draw, protected, r.since, r.until, source, until_reason=r.reason)


def _arm(market: str, book, rr: Sequence[Read], arm: str) -> tuple[List[Thesis], int]:
    coin = random.Random(f"{market}|{SEED}")
    out, refused = [], 0
    for r in rr:
        flip = coin.random() < 0.5                     # drawn for every read, so RANDOM is the same per seed
        kind = arm if arm in ("UNFOLD", "MIRROR") else ("UNFOLD" if flip else "MIRROR")
        th = thesis_of(market, book, r, kind, arm)
        if th is None:
            refused += 1
        else:
            out.append(th)
    return out, refused


def v1_geometry(market: str, mk: Market, since_from: int) -> tuple[List[Thesis], Counter]:
    """AlgoMindDIS v1's sides, each completed by the nearest-pool rule at its start (reported, not judged)."""
    book, refused, out = mk.book, Counter(), []
    w1, e = book.frames["W1"], book.e
    for th in file_theses(market, DIS_FILE, V1):
        if th.until <= since_from or th.since >= int(mk.t[-1]):
            continue
        m, k = w1.n(th.since), int(np.searchsorted(e.end, th.since, "right")) - 1
        if m < 1 or k < 0:
            refused["no history"] += 1
            continue
        draw, protected, why = complete(th.side, book, th.since, float(e.c[k]), float(w1.c.h[m - 1]), float(w1.c.l[m - 1]), V1)
        if draw is None:
            refused[why] += 1
            continue
        out.append(replace(th, draw=draw, protected=protected, source="V1_GEOMETRY"))
    return out, refused


def _trades(j: Journal, market: str, arm: str, w1) -> List[dict]:
    since = {th["id"]: th["since"] for th in j.of("thesis")}
    rows = []
    for t in j.of("trade"):
        week = int(w1.t[int(np.searchsorted(w1.t, since[t["thesis_id"]], "right")) - 1])
        rows.append({**t, "market": market, "arm": arm, "week": week})
    return rows


def market_run(mk: Market, since_from: int, slippage: float, companions: bool) -> dict:
    """One market: its events, reads, every arm's journal, and the measures reported beside the judgement."""
    market, book = mk.name, mk.book
    w1 = book.frames["W1"].c
    evs = [e for e in events(book) if e.t >= since_from]
    rr, refused = reads(book, evs)
    theses: Dict[str, List[Thesis]] = {}
    no_draw: Dict[str, int] = {}
    for arm in ARMS:
        theses[arm], no_draw[arm] = _arm(market, book, rr, arm)
    rows, ends = [], {}
    if companions:
        flat, _ = reads(book, evs, withdraw=False)
        theses["NO_WITHDRAW"] = [t for t in (thesis_of(market, book, r, "UNFOLD", "NO_WITHDRAW") for r in flat) if t]
        theses["V1_GEOMETRY"], _ = v1_geometry(market, mk, since_from)
    for arm, ths in theses.items():
        if not ths:
            continue
        j = run(mk, ths, V1, slippage=slippage)
        rows += _trades(j, market, arm, w1)
        ends[arm] = dict(Counter(r["end"] for r in j.of("note") if r["note"] == "thesis_end"))
    adr = np.array([book.adr(r.since) for r in rr]) if rr else np.array([])
    measures = []
    for r in rr:
        w = int(np.searchsorted(w1.t, r.since, "right")) - 1
        a = book.adr(r.since)
        measures.append({"market": market, "side": r.side, "since": r.since, "week": int(w1.t[w]),
                         "hours_in": (r.since - int(w1.t[w])) / 3.6e12, "reason": r.reason,
                         "draw_adr": abs(r.draw - r.event.price) / a, "protected_adr": abs(r.event.price - r.protected) / a,
                         "right_to_close": bool((w1.c[w] > r.event.price) == (r.side == "BULLISH"))})
    return {"market": market, "trades": rows, "measures": measures, "events": len(evs), "refused": dict(refused),
            "reads": len(rr), "no_draw": no_draw, "ends": ends, "weeks": len(np.unique(w1.t[w1.t >= since_from])),
            "typical_adr": float(np.nanmedian(adr)) if len(adr) else float("nan")}


def judge(trades: pd.DataFrame, arm: str = "UNFOLD") -> dict:
    """H-AP's three checks on ``arm``'s trades."""
    t = trades[trades["arm"] == arm]
    if t.empty:
        return {"trades": 0, "checks": {}, "passes": False}
    net = t["net_r"].to_numpy(float)
    keys = (t["market"] + "|" + t["week"].astype(str)).to_numpy()
    lo, hi = _interval(keys, net, np.random.default_rng(SEED))
    by_market = t.groupby("market")["net_r"].mean()
    rest = np.sort(net)[:-DROP_BEST] if len(net) > DROP_BEST else np.array([])
    without = float(rest.mean()) if len(rest) else float("nan")
    checks = {"net R a trade above zero, with its 95% market-week interval above zero": bool(net.mean() > 0 and lo > 0),
              f"positive in at least {MIN_MARKETS} of {len(MARKETS)} markets": bool((by_market > 0).sum() >= MIN_MARKETS),
              f"positive without its {DROP_BEST} best trades": bool(without > 0)}
    return {"trades": int(len(t)), "net": float(net.mean()), "ci": (lo, hi), "total": float(net.sum()),
            "win": float((net > 0).mean()), "without_best": without, "markets_positive": int((by_market > 0).sum()),
            "by_market": by_market.round(3).to_dict(), "exits": t["reason"].value_counts().to_dict(),
            "buys": float(t.loc[t["direction"] == "LONG", "net_r"].mean()) if (t["direction"] == "LONG").any() else None,
            "sells": float(t.loc[t["direction"] == "SHORT", "net_r"].mean()) if (t["direction"] == "SHORT").any() else None,
            "checks": checks, "passes": all(checks.values())}


def _window(name: str, folder: Path, since_from: int, companions: bool, log=print) -> dict:
    specs = load_profile("exness-standard-swapfree").specs()
    rows, measures, per_market, t0 = [], [], {}, time.time()
    for market in MARKETS:
        mk = prepare(market, pd.read_parquet(folder / f"{market}_M1.parquet"), V1)
        out = market_run(mk, since_from, specs[market].stop_slippage, companions)
        rows += out.pop("trades")
        measures += out.pop("measures")
        per_market[market] = out
        log(f"{name} {market}: {out['events']} events, {out['reads']} reads ({time.time() - t0:.0f}s)")
    trades, ms = pd.DataFrame(rows), pd.DataFrame(measures)
    OUT.mkdir(parents=True, exist_ok=True)
    if not trades.empty:
        trades.to_parquet(OUT / f"{name}_trades.parquet")
    if not ms.empty:
        ms.to_parquet(OUT / f"{name}_reads.parquet")
    arms = {a: judge(trades, a) if not trades.empty else {"trades": 0, "passes": False, "checks": {}}
            for a in (*ARMS, *(COMPANIONS if companions else ()))}
    u, m = arms["UNFOLD"].get("net"), arms["MIRROR"].get("net")
    breakeven = -m / (u - m) if u is not None and m is not None and u > m else None
    summary = {"events": sum(x["events"] for x in per_market.values()), "reads": sum(x["reads"] for x in per_market.values()),
               "refused": dict(sum((Counter(x["refused"]) for x in per_market.values()), Counter())),
               "market_weeks": sum(x["weeks"] for x in per_market.values())}
    if not ms.empty:
        summary.update({"market_weeks_with_a_side": int(ms.groupby(["market", "week"]).ngroups), "hours_in_median": float(ms.hours_in.median()),
                        "draw_adr_median": float(ms.draw_adr.median()), "protected_adr_median": float(ms.protected_adr.median()),
                        "right_to_close": float(ms.right_to_close.mean()), "bullish_share": float((ms.side == "BULLISH").mean()),
                        "withdrawn_share": float((ms.reason == "WITHDRAWN").mean())})
    return {"window": name, "machine": VERSION, "arms": arms, "breakeven_side": breakeven, "summary": summary,
            "per_market": per_market, "minutes": round((time.time() - t0) / 60, 1)}


def _f(x, d: int = 3) -> str:
    return "–" if x is None else f"{x:+.{d}f}" if isinstance(x, float) else str(x)


def render(r: dict) -> List[str]:
    a, s = r["arms"], r["summary"]
    u = a["UNFOLD"]
    lines = [f"## {r['window']}", "", f"**H-AP {'PASSES' if u.get('passes') else 'FAILS'} on {r['window']}.**", ""]
    lines += [f"- {'✓' if ok else '✗'} {k}" for k, ok in u.get("checks", {}).items()]
    lines += ["", "| Arm | Trades | Net R a trade | 95% (market-weeks) | Total R | Win | Without its 5 best | Markets > 0 | Buys | Sells |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for arm, x in a.items():
        if not x.get("trades"):
            lines.append(f"| {arm} | 0 | | | | | | | | |")
            continue
        lines.append(f"| {arm} | {x['trades']} | {_f(x['net'])} | [{x['ci'][0]:+.3f}, {x['ci'][1]:+.3f}] | {x['total']:+.1f} | "
                     f"{x['win']:.0%} | {_f(x['without_best'])} | {x['markets_positive']}/{len(MARKETS)} | {_f(x['buys'])} | {_f(x['sells'])} |")
    lines += ["", f"Break-even side, a trade: {_f(r['breakeven_side'])}.", "", "**The funnel and the reads.**", ""]
    lines += [f"- {k}: {v if not isinstance(v, float) else round(v, 3)}" for k, v in s.items()]
    lines += ["", "**By market (UNFOLD: events, reads, net R a trade).**", "", "| Market | Events | Reads | Net R | Exits by arm |", "|---|---|---|---|---|"]
    for m, x in r["per_market"].items():
        lines.append(f"| {m} | {x['events']} | {x['reads']} | {_f(u.get('by_market', {}).get(m))} | {x['ends'].get('UNFOLD', {})} |")
    lines += ["", f"Run time {r['minutes']} minutes.", ""]
    return lines


def dev(log=print) -> dict:
    done = OUT / "dev.json"
    if done.exists():
        raise SystemExit("H-AP's development run has run once; it is not run again")
    r = _window("2021-22", SNAPSHOT, SINCE, True, log)
    done.write_text(json.dumps(r, indent=1, default=float), encoding="utf-8")
    head = ["# H-AP: AlgoMindDIS v4, the week as it unfolds", "",
            "Registered in `docs/research/SEARCH_2018_2024.md` (2026-11-09, 3bf3e87) before its code. Try 32. The Thesis Engine runs at V1.", ""]
    REPORT.write_text("\n".join(head + render(r)), encoding="utf-8")
    return r


def test(log=print) -> dict:
    done, before = OUT / "test.json", OUT / "dev.json"
    if done.exists():
        raise SystemExit("H-AP's test run has run once; it is not run again")
    if not before.exists() or not json.loads(before.read_text(encoding="utf-8"))["arms"]["UNFOLD"].get("passes"):
        raise SystemExit("H-AP did not pass development: 2023-24 stays unread by v4")
    r = _window("2023-24", TEST, TEST_SINCE, False, log)
    done.write_text(json.dumps(r, indent=1, default=float), encoding="utf-8")
    with REPORT.open("a", encoding="utf-8") as f:
        f.write("\n".join(render(r)))
    return r


def main(argv: Optional[list] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m thesis_engine.hap", description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=("dev", "test"))
    args = ap.parse_args(argv)
    r = (dev if args.step == "dev" else test)()
    print(json.dumps({k: v for k, v in r.items() if k != "per_market"}, indent=1, default=float))


if __name__ == "__main__":
    main()
