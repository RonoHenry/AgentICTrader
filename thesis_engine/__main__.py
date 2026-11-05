"""``python -m thesis_engine replay MARKET --snapshot NAME --source ORACLE`` | ``python -m thesis_engine hag``."""
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
        raise SystemExit("the development window is read only by H-AG (python -m thesis_engine hag)")
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
    args = p.parse_args()
    _replay(args) if args.cmd == "replay" else hag()


if __name__ == "__main__":
    main()
