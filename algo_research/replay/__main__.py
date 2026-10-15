"""python -m algo_research.replay: the charts (update 2026-10-15). You: the blind replay on the research snapshot's
exploration slice; Engine: the engine watch. Both modes are served by ``charts.serve``."""
from __future__ import annotations

import argparse
from pathlib import Path

from algo_research.config import REPO_ROOT

JOURNAL_DIR = REPO_ROOT / "data" / "journal" / "blind"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m algo_research.replay",
                                     description="The charts: read days you don't remember (You), or watch the engine work (Engine).")
    parser.add_argument("--instrument", default="XAUUSD", help="the first tab (default XAUUSD)")
    parser.add_argument("--port", type=int, default=8765, help="default 8765")
    parser.add_argument("--root", type=Path, default=JOURNAL_DIR, help=f"where reads are kept (default {JOURNAL_DIR})")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config" / "backtests" / "base.toml",
                        help="the engine's run configuration, for the Engine mode (default config/backtests/base.toml)")
    parser.add_argument("--picks", type=Path, default=None, help="where your picks go (default data/journal/watch_picks.jsonl)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the page")
    args = parser.parse_args(argv)
    from algo_research.replay.charts import serve
    return serve(args.config, args.port, not args.no_browser, args.instrument.upper(), args.root, args.picks)


if __name__ == "__main__":
    raise SystemExit(main())
