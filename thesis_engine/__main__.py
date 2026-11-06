"""``python -m thesis_engine replay MARKET --snapshot NAME --source ORACLE`` | ``hag`` | ``hah`` | ``hai`` |
``haj`` | ``hal`` | ``scenarios`` | ``live``."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from thesis_engine.hag import REPO, main as hag
from thesis_engine.replay import prepare, run
from thesis_engine.thesis import RESEARCH, call_theses, file_theses, research_theses


def _replay(args) -> None:
    snapshot = REPO / "data" / "research" / "snapshots" / args.snapshot
    if args.snapshot == "mt5-m1-develop":
        raise SystemExit("the development window is read only by the registered tests (python -m thesis_engine "
                         "hag | hah | hai | haj | hal)")
    mk = prepare(args.market, pd.read_parquet(snapshot / f"{args.market}_M1.parquet"))
    if args.source in RESEARCH:
        theses, refused = research_theses(args.market, mk.book, args.source)
    elif args.source == "CALL":
        theses, refused = call_theses(args.market), {}
    else:
        theses, refused = file_theses(args.market, Path(args.source)), {}
    j = run(mk, theses)
    out = REPO / "data" / "research" / "thesis_engine" / "replays" / f"{args.market}_{Path(args.source).stem}.jsonl"
    j.write(out)
    trades = j.of("trade")
    print(f"{args.market}: {len(theses)} theses (refused {refused}), {len(trades)} trades, "
          f"net {sum(t['net_r'] for t in trades):+.2f}R; moves {dict(Counter((r['frm'], r['to']) for r in j.of('transition')))}")
    print(f"journal: {out}")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m thesis_engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="the machine over one market's snapshot")
    r.add_argument("market")
    r.add_argument("--snapshot", default="mt5-m1-2026-10")
    r.add_argument("--source", default="ORACLE", help="ORACLE | MIRROR | RANDOM | W1TREND | CALL | a thesis file")
    sub.add_parser("hag", help="H-AG on the development window (registered 2026-11-05)")
    sub.add_parser("hah", help="H-AH, V2 on the development window (registered 2026-11-05)")
    sub.add_parser("hai", help="H-AI, V3 on the development window (registered 2026-11-06)")
    sub.add_parser("haj", help="H-AJ, V4 judged on July 2025 to June 2026 (registered 2026-11-06)")
    sub.add_parser("hal", help="H-AL, V5 and V1 judged on 2023-2024 (registered 2026-11-06)")
    sc = sub.add_parser("scenarios", help="the trader's own trades, each with the call they held")
    sc.add_argument("--snapshot", default="mt5-m1-2026-11")
    lv = sub.add_parser("live", help="on the terminal's live bars with your /context calls, paper only")
    lv.add_argument("--once", action="store_true", help="one cycle, then stop")
    lv.add_argument("--every", type=int, default=300, help="seconds between cycles (default 300)")
    args = p.parse_args()
    if args.cmd == "replay":
        _replay(args)
    elif args.cmd == "live":
        from thesis_engine.live import main as live
        live(args.once, args.every)
    elif args.cmd == "hah":
        from thesis_engine.hah import main as hah
        hah()
    elif args.cmd == "hai":
        from thesis_engine.hai import main as hai
        hai()
    elif args.cmd == "haj":
        from thesis_engine.haj import main as haj
        haj()
    elif args.cmd == "hal":
        from thesis_engine.hal import main as hal
        hal()
    elif args.cmd == "scenarios":
        from thesis_engine.scenarios import main as scenarios
        scenarios(args.snapshot)
    else:
        hag()


if __name__ == "__main__":
    main()
