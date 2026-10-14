"""python -m algo_research.replay: the blind replay on the research snapshot's exploration slice."""
from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

import pandas as pd

from algo_research.config import REPO_ROOT, load_research_config
from algo_research.replay.bars import ReplayBars
from algo_research.replay.journal import Journal
from algo_research.replay.server import ReplayApp, make_server
from algo_research.snapshot import SNAPSHOTS_DIR

JOURNAL_DIR = REPO_ROOT / "data" / "journal" / "blind"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m algo_research.replay",
                                     description="Read days you don't remember, as of their open; be scored.")
    parser.add_argument("--instrument", default="XAUUSD", help="default XAUUSD")
    parser.add_argument("--port", type=int, default=8765, help="default 8765")
    parser.add_argument("--root", type=Path, default=JOURNAL_DIR, help=f"where reads are kept (default {JOURNAL_DIR})")
    parser.add_argument("--no-browser", action="store_true", help="don't open the page")
    args = parser.parse_args(argv)

    cfg = load_research_config()
    instrument = args.instrument.upper()
    path = SNAPSHOTS_DIR / cfg.snapshot / f"{instrument}_M1.parquet"
    if not path.exists():
        print(f"no snapshot file {path}")
        return 1
    print(f"loading {instrument} from snapshot {cfg.snapshot}...")
    bars = ReplayBars(pd.read_parquet(path, columns=["time", "open", "high", "low", "close"]), instrument)
    first, end = cfg.slices.explore
    journal = Journal(args.root, bars, bars.trading_dates(first, end))
    server = make_server(ReplayApp(journal), port=args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"blind replay at {url} ({journal.remaining()} {instrument} days left in the exploration slice). "
          f"Reads go to {args.root / instrument}. Ctrl+C stops.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
