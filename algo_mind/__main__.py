"""Algo Mind's commands (.kiro/specs/algo-mind/).

    python -m algo_mind fit [--version v1]          # the brain on every week before 2023-01-01
    python -m algo_mind brief --week 2026-11-02     # the week's brief and the thesis files
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from algo_mind.brain import FIT_END, MODELS, fit_version
from algo_research.search_d1 import MARKETS
from algo_research.search_state import load, state_table

ROOT = Path(__file__).resolve().parents[1] / "data" / "algo_mind"
HISTORY = ROOT / "states_to_2022.parquet"


def history_states(refresh: bool = False) -> pd.DataFrame:
    """Every market's weekly states from Yahoo's history (the senses on the fitted weeks), cached."""
    if HISTORY.exists() and not refresh:
        return pd.read_parquet(HISTORY)
    table = pd.concat([state_table(m, load(m)) for m in MARKETS], ignore_index=True)
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(HISTORY, index=False)
    return table


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m algo_mind", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    fit = sub.add_parser("fit", help="fit a version of the brain on every week before 2023-01-01")
    fit.add_argument("--version", default="v1")
    fit.add_argument("--refresh", action="store_true", help="rebuild the cached states")
    brief = sub.add_parser("brief", help="the week's brief and thesis files")
    brief.add_argument("--week", required=True, help="the week's Monday, YYYY-MM-DD")
    brief.add_argument("--version", default="v1")
    args = parser.parse_args()
    if args.command == "fit":
        table = history_states(args.refresh)
        brain = fit_version(table, FIT_END, args.version, MODELS)
        m = brain.meta
        print(f"{m['version']}: {m['weeks']:,} weeks {m['train_start']} to {m['train_end']} (exclusive), "
              f"{len(m['markets'])} markets; thirds at {brain.lo:.4f} / {brain.hi:.4f}; commit {m['commit']}")
    elif args.command == "brief":
        from algo_mind.brief import write_brief
        print(write_brief(pd.Timestamp(args.week), args.version))


if __name__ == "__main__":
    main()
