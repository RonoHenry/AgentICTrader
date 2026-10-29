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
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SYMBOLS = {"DXY": "DX-Y.NYB", "XAUUSD": "GC=F", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "US100": "^NDX",
           "US500": "^GSPC", "US30": "^DJI", "GER40": "^GDAXI", "UK100": "^FTSE"}
FIRST = "1980-01-01"


def fetch(symbol: str, start: datetime, end: datetime) -> dict:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?period1={int(start.timestamp())}&period2={int(end.timestamp())}&interval=1d&events=history")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def bars(data: dict, end: str) -> pd.DataFrame:
    """Yahoo's daily bars as time (UTC), date (the exchange's own day), open, high, low and close, before ``end``."""
    res = data["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    t = pd.to_datetime(res["timestamp"], unit="s", utc=True)
    frame = pd.DataFrame({"time": t, "date": t.tz_convert(res["meta"]["exchangeTimezoneName"]).normalize()
                          .tz_localize(None), **{k: q[k] for k in ("open", "high", "low", "close")}})
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    return frame[frame["date"] < end].drop_duplicates("date", keep="last").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--end", default="2023-01-01", help="exclusive; the test window starts here")
    parser.add_argument("--name", default="yahoo-daily-to-2022")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    raw = REPO / "data" / "research" / "external" / f"yahoo-{now:%Y-%m-%d}"
    out = REPO / "data" / "research" / "snapshots" / args.name
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    start = datetime.fromisoformat(FIRST).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    manifest = {"source": "Yahoo Finance chart API v8, interval 1d", "period": [FIRST, f"{args.end} exclusive"],
                "fetched": now.isoformat(timespec="seconds"), "markets": {}}
    for market, symbol in SYMBOLS.items():
        data = fetch(symbol, start, end)
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
