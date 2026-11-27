"""Export the nine markets' long daily history from Yahoo Finance into a research snapshot (H-Y, the 2018-2024 search).

The broker's terminal holds D1 only from 2018, too few weeks to learn a weekly state from. Yahoo's chart endpoint
gives decades of daily bars. Requests stop at ``--end`` (default 2023-01-01, exclusive), so the search's test window
is never downloaded. The raw JSON goes to ``data/research/external/<name>``; the bars, one parquet per market, to
``data/research/snapshots/yahoo-daily-to-2022`` with a manifest. Both are git-ignored. The cleaning (Yahoo's FX
close, the flat early years) is ``algo_research.search_state.load``'s, so the snapshot keeps Yahoo's own bars.

    python scripts/export_yahoo_history.py [--end 2023-01-01]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from algo_mind.sources import SYMBOLS, bars, fetch  # noqa: E402  (the live senses use the same fetch and bars)

FIRST = "1980-01-01"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--end", default="2023-01-01", help="exclusive; the test window starts here")
    parser.add_argument("--name", default=None, help="default: yahoo-daily-to-2022 (nine), yahoo-broad-to-2022")
    parser.add_argument("--universe", choices=["nine", "broad"], default="nine",
                        help="broad: the markets beyond the nine (algo_research/universe.py, H-AA)")
    args = parser.parse_args()
    symbols = SYMBOLS
    if args.universe == "broad":
        from algo_research.universe import BROAD as symbols
    name = args.name or ("yahoo-broad-to-2022" if args.universe == "broad" else "yahoo-daily-to-2022")
    now = datetime.now(timezone.utc)
    raw = REPO / "data" / "research" / "external" / f"yahoo-{args.universe}-{now:%Y-%m-%d}"
    out = REPO / "data" / "research" / "snapshots" / name
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    start = datetime.fromisoformat(FIRST).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    manifest = {"source": "Yahoo Finance chart API v8, interval 1d", "period": [FIRST, f"{args.end} exclusive"],
                "fetched": now.isoformat(timespec="seconds"), "markets": {}}
    for market, symbol in symbols.items():
        try:
            data = fetch(symbol, start, end)
        except Exception as e:                       # a symbol Yahoo doesn't serve is left out, and said so
            print(market, symbol, "failed:", e, flush=True)
            continue
        (raw / f"{market}.json").write_text(json.dumps(data), encoding="utf-8")
        frame = bars(data, args.end)
        frame.to_parquet(out / f"{market}_D1.parquet", index=False)
        manifest["markets"][market] = {"symbol": symbol, "rows": len(frame), "first": str(frame["date"].iloc[0].date()),
                                       "last": str(frame["date"].iloc[-1].date())}
        print(market, symbol, len(frame), flush=True)
        time.sleep(1.0)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
