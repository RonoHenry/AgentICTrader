"""Export the MT5 terminal's bar history for the trader's focus markets into a research snapshot (read-only).

The terminal (Exness, server time UTC+0) holds D1 back to 2018 for the focus markets, years that no research has
read yet. Its intraday history starts on 16 July 2021: before that the server answers H4, H1 and M15 requests with
the D1 bars, one per day, which are dropped here. Each market and timeframe becomes one parquet of UTC bar opens with
open, high, low, close, tick volume and the spread in price units; a manifest records the symbols, spans, row counts
and each market's first intraday date.

    python scripts/export_mt5_history.py [--name mt5-2018-2026] [--start 2018-01-01]

Nothing is sent to the terminal but history requests.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SYMBOLS = {"DXY": "DXYm", "XAUUSD": "XAUUSDm", "EURUSD": "EURUSDm", "GBPUSD": "GBPUSDm", "US100": "USTECm",
           "US500": "US500m", "US30": "US30m", "GER40": "DE30m", "UK100": "UK100m"}
TIMEFRAMES = ("D1", "H4", "H1", "M15")


def main() -> None:
    import MetaTrader5 as mt5

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="mt5-2018-2026")
    parser.add_argument("--start", default="2018-01-01")
    args = parser.parse_args()
    out = REPO / "data" / "research" / "snapshots" / args.name
    out.mkdir(parents=True, exist_ok=True)
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    manifest = {"source": f"{mt5.account_info().server} ({mt5.terminal_info().name})", "server_utc_offset": 0,
                "exported_at": end.isoformat(timespec="seconds"), "markets": {}}
    for instrument, symbol in SYMBOLS.items():
        mt5.symbol_select(symbol, True)
        point = mt5.symbol_info(symbol).point
        manifest["markets"][instrument] = {"symbol": symbol, "point": point, "timeframes": {}}
        for tf in TIMEFRAMES:
            rates = mt5.copy_rates_range(symbol, getattr(mt5, f"TIMEFRAME_{tf}"), start, end)
            if rates is None or not len(rates):
                continue
            frame = pd.DataFrame(rates)
            bars = pd.DataFrame({"time": pd.to_datetime(frame["time"], unit="s", utc=True),
                                 **{k: frame[k].astype(float) for k in ("open", "high", "low", "close")},
                                 "tick_volume": frame["tick_volume"].astype("int64"),
                                 "spread": frame["spread"].astype(float) * point})
            if tf != "D1":
                # Stand-in D1 bars come one per day; the intraday history starts on the first day with more.
                per_day = bars.groupby(bars["time"].dt.normalize()).size()
                first = per_day[per_day > 1].index[0]
                bars = bars[bars["time"] >= first].reset_index(drop=True)
                manifest["markets"][instrument]["intraday_from"] = first.date().isoformat()
            bars.to_parquet(out / f"{instrument}_{tf}.parquet", index=False)
            manifest["markets"][instrument]["timeframes"][tf] = {
                "first": bars["time"].iloc[0].isoformat(), "last": bars["time"].iloc[-1].isoformat(), "rows": len(bars)}
        print(instrument, {tf: v["rows"] for tf, v in manifest["markets"][instrument]["timeframes"].items()}, flush=True)
    mt5.shutdown()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
