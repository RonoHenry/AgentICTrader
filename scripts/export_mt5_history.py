"""Export the MT5 terminal's bar history for the trader's focus markets into a research snapshot (read-only).

The terminal (Exness, server time UTC+0) holds D1 back to 2018 for the focus markets, years that no research has
read yet. Its intraday history starts on 16 July 2021: before that the server answers H4, H1 and M15 requests with
the D1 bars, one per day, which are dropped here. Each market and timeframe becomes one parquet of UTC bar opens with
open, high, low, close, tick volume and the spread in price units; a manifest records the symbols, spans, row counts
and each market's first intraday date.

    python scripts/export_mt5_history.py [--name mt5-2018-2026] [--start 2018-01-01]
    python scripts/export_mt5_history.py --name mt5-m1-develop --timeframes M1 --start 2021-07-16 --end 2023-01-01
    python scripts/export_mt5_history.py --list-symbols USDJPY,JP225,USOIL     # what the server calls them
    python scripts/export_mt5_history.py --name mt5-m1-assets --timeframes M1 --start 2021-01-01 \\
        --symbols USDJPY=USDJPYm,...                                             # H-AS's markets

A symbol the server doesn't carry is skipped and listed under ``unavailable`` in the manifest.

Requests go a month at a time, so the terminal's bar limit never truncates M1. ``--end`` keeps a window unread
(the 2018-2024 search's test years stay out of a development export).

Nothing is sent to the terminal but history requests.

A second broker (2026-11-20): ``--terminal`` picks the terminal64.exe to read, when more than one MT5 is installed.
``--server-time`` says how its clock relates to UTC:
- ``utc``: Exness, the default;
- ``ny7``: New York time + 7 hours, the usual UTC+2/UTC+3 server whose day ends at 17:00 New York;
- ``+H`` or ``-H``: a fixed offset in hours.
Bars are converted to UTC. The live offset, the last tick's server time less UTC now, goes in the manifest as a check.

    python scripts/export_mt5_history.py --terminal "C:\\Program Files\\<Broker> MetaTrader 5\\terminal64.exe" \\
        --server-time ny7 --list-symbols OIL,JP225,NIKKEI
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
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
    parser.add_argument("--end", default=None, help="exclusive, UTC; default now")
    parser.add_argument("--timeframes", default=",".join(TIMEFRAMES))
    parser.add_argument("--symbols", default="", help="NAME=SYMBOL,... instead of the focus markets (H-AS)")
    parser.add_argument("--list-symbols", default="", help="print the terminal's symbols containing these, then stop")
    parser.add_argument("--terminal", default=None, help="the terminal64.exe to read (default: MT5's own choice)")
    parser.add_argument("--server-time", default="utc", help="utc (Exness), ny7 (New York + 7 h) or a fixed +H/-H")
    args = parser.parse_args()
    ok = mt5.initialize(path=args.terminal) if args.terminal else mt5.initialize()
    if not ok:
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    print("terminal:", mt5.terminal_info().path, "| server:", mt5.account_info().server,
          "| maxbars:", mt5.terminal_info().maxbars, flush=True)
    if args.list_symbols:
        names = [s.name for s in mt5.symbols_get()]
        for key in args.list_symbols.split(","):
            hits = [n for n in names if key.upper() in n.upper()]
            print(key, hits)
            for n in hits[:3]:
                tick = mt5.symbol_info_tick(n) if mt5.symbol_select(n, True) else None
                if tick is not None and tick.time:
                    print("  ", n, "live offset (h):", _live_offset(tick.time))
        mt5.shutdown()
        return
    symbols = dict(x.split("=", 1) for x in args.symbols.split(",") if x) if args.symbols else SYMBOLS
    out = REPO / "data" / "research" / "snapshots" / args.name
    out.mkdir(parents=True, exist_ok=True)
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) if args.end else now
    manifest = {"source": f"{mt5.account_info().server} ({mt5.terminal_info().name})",
                "server_utc_offset": 0 if args.server_time == "utc" else args.server_time,
                "converted_to_utc": True, "live_offsets_h": {},
                "exported_at": now.isoformat(timespec="seconds"), "until": end.isoformat(), "markets": {},
                "unavailable": []}
    # Server-clock requests: ask for a little more on both sides, then cut in UTC.
    pad = timedelta(hours=0 if args.server_time == "utc" else 12)
    for instrument, symbol in symbols.items():
        if not mt5.symbol_select(symbol, True) or mt5.symbol_info(symbol) is None:
            manifest["unavailable"].append({"instrument": instrument, "symbol": symbol})
            print(instrument, symbol, "unavailable on this server", flush=True)
            continue
        point = mt5.symbol_info(symbol).point
        manifest["markets"][instrument] = {"symbol": symbol, "point": point, "timeframes": {}}
        tick = mt5.symbol_info_tick(symbol)
        if tick is not None and tick.time:
            manifest["live_offsets_h"][instrument] = _live_offset(tick.time)
        for tf in args.timeframes.split(","):
            frame = _rates(mt5, symbol, getattr(mt5, f"TIMEFRAME_{tf}"), start - pad, end + pad)
            if frame is None:
                continue
            bars = pd.DataFrame({"time": _to_utc(frame["time"], args.server_time),
                                 **{k: frame[k].astype(float) for k in ("open", "high", "low", "close")},
                                 "tick_volume": frame["tick_volume"].astype("int64"),
                                 "spread": frame["spread"].astype(float) * point})
            bars = bars[bars["time"].notna() & (bars["time"] >= start) & (bars["time"] < end)]
            bars = bars.sort_values("time").drop_duplicates("time").reset_index(drop=True)
            if bars.empty:
                continue
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


def _live_offset(server_epoch: int) -> float:
    """The server clock less UTC now, in hours (rounded to a half hour); right only while the market is quoting."""
    return round((server_epoch - datetime.now(timezone.utc).timestamp()) / 1800) / 2


def _to_utc(server_epoch: pd.Series, server_time: str) -> pd.Series:
    """Server-clock bar opens (seconds, written as if UTC) to UTC timestamps."""
    naive = pd.to_datetime(server_epoch, unit="s")
    if server_time == "utc":
        return naive.dt.tz_localize("UTC")
    if server_time == "ny7":                              # server = New York + 7 h; Sunday-morning DST hours are closed
        ny = (naive - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT",
                                                             nonexistent="shift_forward")
        return ny.dt.tz_convert("UTC")
    return (naive - pd.Timedelta(hours=float(server_time))).dt.tz_localize("UTC")


def _rates(mt5, symbol: str, timeframe: int, start: datetime, end: datetime):
    """[start, end) a month at a time, joined; None when the server has nothing."""
    parts, cursor = [], start
    while cursor < end:
        upto = min(cursor + timedelta(days=31), end)
        rates = mt5.copy_rates_range(symbol, timeframe, cursor, upto)
        if rates is not None and len(rates):
            parts.append(pd.DataFrame(rates))
        cursor = upto
    if not parts:
        return None
    frame = pd.concat(parts, ignore_index=True).drop_duplicates("time")
    return frame[frame["time"] < int(end.timestamp())].reset_index(drop=True)


if __name__ == "__main__":
    main()
