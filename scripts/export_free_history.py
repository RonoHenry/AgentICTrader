"""Export free M1 history into a research snapshot, with no broker account (read-only).

Two sources, for the markets the Exness demo can't give whole (2026-11-20):
- ``binance``: Binance spot klines from data.binance.vision, monthly files and then daily ones for the current month.
  BTCUSD, ETHUSD and XRPUSD as BTCUSDT, ETHUSDT and XRPUSDT. Spread 0: the cost is the taker fee, which is not in
  the bars and is set by whatever uses them. Tick volume is the number of trades.
- ``dukascopy``: Dukascopy's bid and ask minute candles, one file per side and day. USOIL as LIGHTCMDUSD (WTI) and
  JP225 as JPNIDXJPY. The bars are the bid; the spread is the ask close less the bid close (never below 0). The
  flat zero-volume bars Dukascopy fills closed hours with are dropped. Tick volume is its volume x 1000 (its own units).

Times are UTC. The snapshot has the MT5 export's layout (``<NAME>_M1.parquet`` with time, open, high, low, close,
tick_volume and spread in price units, plus ``manifest.json``), so the research runners read it unchanged.

Downloads are cached under ``data/research/downloads/<source>/`` and reused, so an interrupted export resumes. Dukascopy
answers 503 when asked too fast; requests are paced and retried with a growing wait.

    python scripts/export_free_history.py binance --name binance-m1-crypto --start 2021-01-01
    python scripts/export_free_history.py dukascopy --name dukascopy-m1-assets --start 2021-01-01
"""
from __future__ import annotations

import argparse
import io
import json
import lzma
import struct
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SNAPSHOTS = REPO / "data" / "research" / "snapshots"
CACHE = REPO / "data" / "research" / "downloads"
UA = {"User-Agent": "Mozilla/5.0 (research data client)"}

BINANCE = {"BTCUSD": ("BTCUSDT", 0.01), "ETHUSD": ("ETHUSDT", 0.01), "XRPUSD": ("XRPUSDT", 0.0001)}
DUKASCOPY = {"USOIL": ("LIGHTCMDUSD", 1000.0), "JP225": ("JPNIDXJPY", 1000.0)}
COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread"]


def fetch(url: str, tries: int = 30, pace: float = 0.0) -> bytes | None:
    """The body, b"" for an empty file, None for 404. Retries 503s and timeouts with a growing wait."""
    wait = 2.0
    for k in range(tries):
        if pace:
            time.sleep(pace)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e.code
        except Exception as e:  # timeouts, resets
            err = type(e).__name__
        print(f"  retry {k + 1} after {err}: {url}", flush=True)
        time.sleep(wait)
        wait = min(wait * 2, 300.0)
    raise SystemExit(f"gave up on {url}")


def cached(path: Path, url: str, pace: float = 0.0) -> bytes | None:
    """The cached body; a ``.none`` marker records a 404 so it isn't asked again."""
    none = path.with_suffix(path.suffix + ".none")
    if path.exists():
        return path.read_bytes()
    if none.exists():
        return None
    body = fetch(url, pace=pace)
    path.parent.mkdir(parents=True, exist_ok=True)
    if body is None:
        none.write_bytes(b"")
    else:
        path.write_bytes(body)
    return body


# --- Binance ------------------------------------------------------------------------------------------------------

def binance_frame(body: bytes) -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(body))
    raw = pd.read_csv(z.open(z.namelist()[0]), header=None, usecols=range(9))
    if not str(raw.iloc[0, 0]).strip().isdigit():                     # a header row, in some files
        raw = raw.iloc[1:].astype(float)
    t = raw[0].astype(np.int64)
    t = np.where(t > 10**14, t // 1000, t)                              # microseconds from 2025, milliseconds before
    return pd.DataFrame({"time": pd.to_datetime(t, unit="ms", utc=True),
                         "open": raw[1].astype(float), "high": raw[2].astype(float), "low": raw[3].astype(float),
                         "close": raw[4].astype(float), "tick_volume": raw[8].astype(np.int64), "spread": 0.0})


def binance(symbol: str, start: date, end: date) -> pd.DataFrame:
    base = "https://data.binance.vision/data/spot"
    parts, month = [], date(start.year, start.month, 1)
    this_month = date(end.year, end.month, 1)
    while month < this_month:
        tag = f"{month:%Y-%m}"
        body = cached(CACHE / "binance" / symbol / f"{symbol}-1m-{tag}.zip",
                      f"{base}/monthly/klines/{symbol}/1m/{symbol}-1m-{tag}.zip")
        if body:
            parts.append(binance_frame(body))
        print(f"{symbol} {tag}", flush=True)
        month = (month + timedelta(days=32)).replace(day=1)
    day = this_month
    while day < end:                                                    # the current month, day by day
        tag = f"{day:%Y-%m-%d}"
        body = cached(CACHE / "binance" / symbol / f"{symbol}-1m-{tag}.zip",
                      f"{base}/daily/klines/{symbol}/1m/{symbol}-1m-{tag}.zip")
        if body:
            parts.append(binance_frame(body))
        day += timedelta(days=1)
    return pd.concat(parts, ignore_index=True)


# --- Dukascopy ----------------------------------------------------------------------------------------------------

def dukascopy_day(body: bytes | None, day: date, scale: float) -> pd.DataFrame:
    if not body:
        return pd.DataFrame(columns=["t", "o", "c", "l", "h", "v"])
    raw = lzma.decompress(body)
    rec = np.array(list(struct.iter_unpack(">5If", raw[: len(raw) // 24 * 24])), dtype=float)
    t0 = pd.Timestamp(day, tz="UTC")
    return pd.DataFrame({"t": t0 + pd.to_timedelta(rec[:, 0], unit="s"), "o": rec[:, 1] / scale,
                         "c": rec[:, 2] / scale, "l": rec[:, 3] / scale, "h": rec[:, 4] / scale, "v": rec[:, 5]})


def dukascopy(instrument: str, scale: float, start: date, end: date, pace: float) -> pd.DataFrame:
    parts, day = [], start
    while day < end:
        if day.weekday() != 5:                                          # Saturdays carry only flat fillers
            sides = {}
            for side in ("BID", "ASK"):
                url = (f"https://datafeed.dukascopy.com/datafeed/{instrument}/{day.year}/{day.month - 1:02d}/"
                       f"{day.day:02d}/{side}_candles_min_1.bi5")
                body = cached(CACHE / "dukascopy" / instrument / f"{day:%Y-%m-%d}_{side}.bi5", url, pace)
                sides[side] = dukascopy_day(body, day, scale)
            b, a = sides["BID"], sides["ASK"]
            if len(b):
                m = b.merge(a[["t", "c"]].rename(columns={"c": "ask_c"}), on="t", how="left")
                m = m[m["v"] > 0]
                parts.append(pd.DataFrame({"time": m["t"], "open": m["o"], "high": m["h"], "low": m["l"],
                                           "close": m["c"], "tick_volume": np.round(m["v"] * 1000).astype(np.int64),
                                           "spread": (m["ask_c"] - m["c"]).clip(lower=0).fillna(0.0)}))
        if day.day == 1:
            print(f"{instrument} {day:%Y-%m}", flush=True)
        day += timedelta(days=1)
    return pd.concat(parts, ignore_index=True)


# --- the snapshot -------------------------------------------------------------------------------------------------

def write(name: str, source: str, frames: dict, points: dict, symbols: dict, notes: str) -> None:
    out = SNAPSHOTS / name
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    manifest = {"source": source, "server_utc_offset": 0, "exported_at": now.isoformat(timespec="seconds"),
                "until": now.isoformat(), "notes": notes, "unavailable": [], "markets": {}}
    for inst, df in frames.items():
        df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)[COLUMNS]
        df.to_parquet(out / f"{inst}_M1.parquet", index=False)
        gaps = df["time"].diff().dt.total_seconds().div(86400)
        big = [(str(df["time"][i - 1])[:10], str(df["time"][i])[:10], round(float(gaps[i]), 1))
               for i in gaps[gaps > 3.5].index]
        manifest["markets"][inst] = {
            "symbol": symbols[inst], "point": points[inst],
            "timeframes": {"M1": {"first": df["time"].iloc[0].isoformat(), "last": df["time"].iloc[-1].isoformat(),
                                  "rows": int(len(df))}},
            "intraday_from": df["time"].iloc[0].date().isoformat(), "gaps_over_3_5_days": big}
        print(inst, len(df), "rows", df["time"].iloc[0], "->", df["time"].iloc[-1], "| gaps > 3.5 days:", big,
              "| median spread", float(df["spread"].median()), flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print("wrote", out, flush=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python scripts/export_free_history.py")
    ap.add_argument("source", choices=("binance", "dukascopy"))
    ap.add_argument("--name", required=True)
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default=None, help="exclusive, UTC date; default today")
    ap.add_argument("--markets", default="", help="a subset, comma separated")
    ap.add_argument("--pace", type=float, default=0.5, help="seconds between Dukascopy requests")
    args = ap.parse_args(argv)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date()
    table = BINANCE if args.source == "binance" else DUKASCOPY
    markets = [m for m in (args.markets.split(",") if args.markets else table)]
    frames, points, symbols = {}, {}, {}
    for inst in markets:
        sym, x = table[inst]
        if args.source == "binance":
            frames[inst], points[inst] = binance(sym, start, end), x
        else:
            frames[inst], points[inst] = dukascopy(sym, x, start, end, args.pace), 1.0 / x
        symbols[inst] = sym
    if args.source == "binance":
        write(args.name, "Binance spot klines (data.binance.vision)", frames, points, symbols,
              "spread 0: the taker fee is the cost and is not in the bars; tick_volume = trades")
    else:
        write(args.name, "Dukascopy bid/ask minute candles (datafeed.dukascopy.com)", frames, points, symbols,
              "bars are the bid; spread = ask close - bid close; flat zero-volume bars dropped; "
              "tick_volume = Dukascopy volume x 1000")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
