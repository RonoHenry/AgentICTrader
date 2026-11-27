"""AlgoMindDIS v1's sides as a THESIS file the Thesis Engine reads (algomind-dis task 436; 2026-11-07, the trader:
"please load them", AlgoMindDIS's trades on Noculus).

v1 runs at every D1 close of the broker's daily bars (``mt5-2018-2026``, extended with whole UTC days from the
latest M1 snapshot). Each New York trading date gets the state at the last D1 close before the date opens (17:00 New
York the day before), so nothing is read before it was known. An ACTIVE side writes ``{side, draw, protected,
since}``; any other state writes nothing, and the Thesis Engine stays FLAT that day. ``since`` is the D1 close that
set the side. The file is git-ignored data; the same bars give the same file.

    python -m algomind_dis.theses                 # data/research/theses/algomind_dis_v1.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from algomind_dis.frames import from_daily
from algomind_dis.settings import V1, Settings
from algomind_dis.state import run as timeline

__all__ = ["MARKETS", "PATH", "daily_bars", "entries", "write"]

REPO = Path(__file__).resolve().parents[1]
SNAPSHOTS = REPO / "data" / "research" / "snapshots"
PATH = REPO / "data" / "research" / "theses" / "algomind_dis_v1.json"
DAILY = SNAPSHOTS / "mt5-2018-2026"
LATEST_M1 = SNAPSHOTS / "mt5-m1-2026-11"
#: The Thesis Engine's markets (thesis_engine.hag.MARKETS).
MARKETS = ("XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")
#: The first trading date written: Noculus's earliest period starts 2021-08-16.
FIRST = "2021-08-16"
_NY = "America/New_York"
_SIDES = ("BULLISH", "BEARISH")


def _utc_days(frame: pd.DataFrame) -> pd.Series:
    return frame["time"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()


def daily_bars(market: str, daily: Path = DAILY, m1: Optional[Path] = LATEST_M1) -> pd.DataFrame:
    """The broker's D1 (date, open, high, low, close), then whole UTC days of the M1 snapshot after its last."""
    d1 = pd.read_parquet(daily / f"{market}_D1.parquet")
    d1 = d1.assign(date=_utc_days(d1))[["date", "open", "high", "low", "close"]]
    path = None if m1 is None else m1 / f"{market}_M1.parquet"
    if path is None or not path.exists():
        return d1.reset_index(drop=True)
    bars = pd.read_parquet(path, columns=["time", "open", "high", "low", "close"])
    bars = bars.assign(date=_utc_days(bars))
    g = bars[bars["date"] > d1["date"].max()].groupby("date")
    ext = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last()}).reset_index()
    ext = ext[ext["date"] < bars["date"].max()]                       # the last day may still be forming
    return pd.concat([d1, ext], ignore_index=True)


def _opens(days: pd.DatetimeIndex) -> np.ndarray:
    """Each trading date's open: 17:00 New York the calendar day before, ns UTC."""
    eve = (days - pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=17)
    return eve.tz_localize(_NY).tz_convert("UTC").as_unit("ns").asi8


def entries(rows: pd.DataFrame, first: str, last: str) -> dict:
    """``{trading date: {side, draw, protected, since}}`` from a v1 timeline's rows, for weekdays ``first``..``last``."""
    days = pd.bdate_range(first, last)
    t = rows["t"].to_numpy(np.int64)
    k = np.searchsorted(t, _opens(days), "right") - 1
    out = {}
    for day, i in zip(days, k):
        if i < 0:
            continue
        r = rows.iloc[int(i)]
        if r["state"] in _SIDES and pd.notna(r["draw"]) and pd.notna(r["protected"]) and pd.notna(r["since"]):
            out[day.date().isoformat()] = {"side": r["state"], "draw": float(r["draw"]),
                                           "protected": float(r["protected"]),
                                           "since": pd.Timestamp(int(r["since"]), tz="UTC").isoformat()}
    return out


def write(path: Path = PATH, markets=MARKETS, first: str = FIRST, s: Settings = V1, log=print,
          bars: Optional[Mapping[str, pd.DataFrame]] = None) -> dict:
    """Run v1 for each market and write the file; returns it."""
    out = {}
    for market in markets:
        days = daily_bars(market) if bars is None else bars[market]
        rows = timeline(market, from_daily(market, days), s).rows
        last = (pd.Timestamp(days["date"].max()) + pd.Timedelta(days=1)).date().isoformat()
        out[market] = entries(rows, first, last)
        log(f"{market}: {len(out[market])} trading dates with a side ({first} to {last})")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": s.version, **out}, indent=1), encoding="utf-8")
    return out


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(prog="python -m algomind_dis.theses", description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=PATH)
    args = p.parse_args(argv)
    write(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
