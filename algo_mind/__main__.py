"""Algo Mind's commands (.kiro/specs/algo-mind/).

    python -m algo_mind fit [--version v1]          # the brain on every week before 2023-01-01
    python -m algo_mind brief --week 2026-11-02     # the week's brief and the thesis files
    python -m algo_mind refit --version v2          # a candidate on every permitted week so far
    python -m algo_mind judge --candidate v2        # judged on the weeks after its window
    python -m algo_mind bench --runs 20 [--plant 0.05]
    python -m algo_mind third-look
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from algo_mind.brain import FIT_END, MODELS, fit_version
from algo_research.search_d1 import MARKETS
from algo_research.search_state import load, state_table

ROOT = Path(__file__).resolve().parents[1] / "data" / "algo_mind"
HISTORY = ROOT / "states_to_2022.parquet"
HISTORY2 = ROOT / "states2_to_2022.parquet"


def history_states(refresh: bool = False) -> pd.DataFrame:
    """Every market's weekly states from Yahoo's history (the senses on the fitted weeks), cached."""
    if HISTORY.exists() and not refresh:
        return pd.read_parquet(HISTORY)
    table = pd.concat([state_table(m, load(m)) for m in MARKETS], ignore_index=True)
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(HISTORY, index=False)
    return table


def history_states2(refresh: bool = False) -> pd.DataFrame:
    """Every market's widened weekly states (H-Z) from Yahoo's history, cached."""
    from algo_research.search_state2 import macro_table, state_table2, widen
    if HISTORY2.exists() and not refresh:
        return pd.read_parquet(HISTORY2)
    table = widen({m: state_table2(m, load(m)) for m in MARKETS}, macro_table())
    HISTORY2.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(HISTORY2, index=False)
    return table


def live_states2(now=None) -> pd.DataFrame:
    """Every market's whole weeks read by the live senses since 2025, widened, with their outcomes."""
    from datetime import datetime, timezone

    from algo_mind.sources import LIVE, fetch_live, live_days, live_macro
    from algo_research.search_state2 import macro_table, state_table2, widen
    now = now or datetime.now(timezone.utc)
    tables = {}
    for m in MARKETS:
        t = state_table2(m, live_days(fetch_live(m, now), m, now.date()))
        tables[m] = t[t["week"] + pd.Timedelta(days=5) <= pd.Timestamp(now.date())]
    live_macro(now, LIVE)
    return widen(tables, macro_table(LIVE))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m algo_mind", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    fit = sub.add_parser("fit", help="fit a version of the brain on every week before 2023-01-01")
    fit.add_argument("--version", default="v1")
    fit.add_argument("--refresh", action="store_true", help="rebuild the cached states")
    fit.add_argument("--widened", action="store_true", help="H-Z's widened state (structure, intermarket, macro)")
    brief = sub.add_parser("brief", help="the week's brief and thesis files")
    brief.add_argument("--week", required=True, help="the week's Monday, YYYY-MM-DD")
    brief.add_argument("--version", default=None, help="default: the version in use (the ledger's)")
    refit = sub.add_parser("refit", help="fit a candidate on every permitted week so far (the ledger logs it)")
    refit.add_argument("--version", required=True)
    judge = sub.add_parser("judge", help="judge a candidate on the weeks after its window against the version in use")
    judge.add_argument("--candidate", required=True)
    judge.add_argument("--min-calls", type=int, default=150)
    bench = sub.add_parser("bench", help="the fit and judgment on random walks (false alarms, or power with --plant)")
    bench.add_argument("--runs", type=int, default=20)
    bench.add_argument("--plant", type=float, default=0.0, help="a planted lean in probability, e.g. 0.05")
    bench.add_argument("--workers", type=int, default=4)
    look = sub.add_parser("third-look", help="the brain's calls on the readable weeks since 2025 (information)")
    look.add_argument("--version", default="v1")
    args = parser.parse_args()
    if args.command == "bench":
        from algo_mind.bench import H_Y_EXCESS, bench as run_bench
        out = run_bench(args.runs, args.plant, args.workers)
        out.to_csv(ROOT / f"bench_plant{args.plant:g}_runs{args.runs}.csv", index=False)
        print(out.to_string(index=False))
        print(f"\nplant {args.plant:g}: mean excess {100 * out['excess'].mean():+.2f} pts (sd {100 * out['excess'].std():.2f}); "
              f"at or above H-Y's +{100 * H_Y_EXCESS:.1f}: {(out['excess'] >= H_Y_EXCESS).mean():.0%}; "
              f"passing H-Y's rule: {out['passes'].mean():.0%} of {len(out)} runs")
        return
    if args.command in ("refit", "judge"):
        from algo_mind.ledger import Ledger
        ledger = Ledger()
        states = pd.concat([history_states2(), live_states2()], ignore_index=True)
        if args.command == "refit":
            end = states["week"].max() + pd.Timedelta(days=7)
            brain = fit_version(states, end, args.version, MODELS)
            ledger.log("fit", version=args.version, train_end=brain.meta["train_end"], weeks=brain.meta["weeks"])
            print(f"candidate {args.version}: {brain.meta['weeks']:,} weeks to {brain.meta['train_end']}; "
                  f"judge it once weeks after that have closed")
        else:
            v = ledger.judge(args.candidate, states, args.min_calls)
            print(json.dumps(v, indent=1, default=str))
        return
    if args.command == "third-look":
        import numpy as np

        from algo_mind.brain import load_version
        from algo_research.search_state import judge as judge_calls
        t = live_states2()
        called = load_version(args.version).call(t)
        called = called.assign(every=np.where(called["p"] >= 0.5, 1, -1))
        r = {"weeks": len(t), "first": str(t["week"].min().date()), "last": str(t["week"].max().date()),
             "thirds": judge_calls(called), "every": judge_calls(called, "every")}
        for name in ("thirds", "every"):
            x = r[name]
            print(f"{name}: {x['calls']} calls, hit {x['hit']:.1%} vs drift {x['base']:.1%}, excess "
                  f"{100 * x['excess']:+.1f} pts [{100 * x['lo']:+.1f}, {100 * x['hi']:+.1f}], {x['positive']}/9 markets"
                  if x.get("calls") else f"{name}: no calls")
        print(f"{r['weeks']} weeks, {r['first']} to {r['last']}")
        return
    if args.command == "fit":
        from algo_mind.ledger import Ledger
        if args.widened:
            from algo_research.search_state2 import FEATURES as WIDE
            brain = fit_version(history_states2(args.refresh), FIT_END, args.version, MODELS, WIDE)
        else:
            brain = fit_version(history_states(args.refresh), FIT_END, args.version, MODELS)
        m = brain.meta
        Ledger().log("fit", version=m["version"], train_end=m["train_end"], weeks=m["weeks"],
                     features=len(m["features"]))
        print(f"{m['version']}: {m['weeks']:,} weeks {m['train_start']} to {m['train_end']} (exclusive), "
              f"{len(m['markets'])} markets; thirds at {brain.lo:.4f} / {brain.hi:.4f}; commit {m['commit']}")
    elif args.command == "brief":
        from agent.context_calls import ContextBook
        from algo_mind.brief import write_brief
        path = write_brief(pd.Timestamp(args.week), args.version, book=ContextBook())   # None: the version in use
        brief = json.loads(path.read_text(encoding="utf-8"))
        print(f"Week of {brief['week']}, brain {brief['version']} (thirds {brief['thresholds'][0]:.4f} / "
              f"{brief['thresholds'][1]:.4f}), made {brief['made_at']}:")
        for r in brief["rows"]:
            memory = r.get("analogs") or {}
            share = memory.get("share_up")
            print(f"  {r['market']:7} {r['call']:8} p={r['p'] if r['p'] is not None else '–'}"
                  f"  analogs up {'–' if share is None else f'{share:.0%}'}"
                  f"  last day {r.get('last_day')}{'  PROVISIONAL' if r['provisional'] else ''}")
        print(path)


if __name__ == "__main__":
    main()
