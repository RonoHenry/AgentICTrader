"""Algo Mind's live senses (algo-mind Requirement 1): Yahoo's daily bars from 2025-01-01, cleaned as for training, and
the state of a week at its open, even before it opens.

The test window (2023-2024) is never requested (AM-D2). A day not closed at the run is left out. An FX day's close is
the next day's open (Yahoo's FX close is the day's open); the last closed FX day, with no next day yet, closes at the
symbol's last price. A week read before its open is read at the last close, with no gap, and marked provisional
when its Friday isn't in the bars.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from algo_research.search_state import FEATURES, FRAMES, FX, _Frame, build_frames, week_state

__all__ = ["LIVE", "LIVE_FROM", "SYMBOLS", "bars", "fetch", "fetch_live", "live_days", "live_macro", "state_at"]

REPO = Path(__file__).resolve().parents[1]
LIVE = REPO / "data" / "algo_mind" / "live"
LIVE_FROM = datetime(2025, 1, 1, tzinfo=timezone.utc)
SYMBOLS = {"DXY": "DX-Y.NYB", "XAUUSD": "GC=F", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "US100": "^NDX",
           "US500": "^GSPC", "US30": "^DJI", "GER40": "^GDAXI", "UK100": "^FTSE"}


def fetch(symbol: str, start: datetime, end: datetime) -> dict:
    """Yahoo's chart endpoint, daily, from ``start`` to ``end``."""
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
    # the local wall time, then its day: a midnight skipped by a clock change (Brazil's) can't break it
    frame = pd.DataFrame({"time": t, "date": t.tz_convert(res["meta"]["exchangeTimezoneName"]).tz_localize(None)
                          .normalize(), **{k: q[k] for k in ("open", "high", "low", "close")}})
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    return frame[frame["date"] < end].drop_duplicates("date", keep="last").reset_index(drop=True)


def fetch_live(market: str, now: Optional[datetime] = None, root: Path = LIVE) -> dict:
    """The market's bars from 2025-01-01 to ``now``, kept as raw JSON under ``root``."""
    now = now or datetime.now(timezone.utc)
    data = fetch(SYMBOLS[market], LIVE_FROM, now)
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{market}.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def live_macro(now: Optional[datetime] = None, root: Path = LIVE, fetcher=None) -> Path:
    """The macro and risk series (H-Z: the 10-year yield, the 3-month bill, the VIX) from 2025-01-01, their days
    closed before today, kept as parquet in ``root`` the way ``search_state2.macro_table`` reads them."""
    from algo_research.search_state2 import MACRO_SYMBOLS

    now = now or datetime.now(timezone.utc)
    fetcher = fetcher or fetch
    root.mkdir(parents=True, exist_ok=True)
    for name, symbol in MACRO_SYMBOLS.items():
        d = bars(fetcher(symbol, LIVE_FROM, now), now.date().isoformat())
        d.to_parquet(root / f"{name}_D1.parquet", index=False)
    return root


def live_days(data: dict, market: str, today: date) -> pd.DataFrame:
    """The days closed before ``today``, cleaned as for training (``search_state.load``)."""
    every = bars(data, "2100-01-01")
    d = every[every["date"] < pd.Timestamp(today)].reset_index(drop=True)[["date", "open", "high", "low", "close"]]
    if market in FX and len(d):
        nxt = every["open"].shift(-1)[: len(d)].to_numpy()
        last = data["chart"]["result"][0]["meta"].get("regularMarketPrice")
        if pd.isna(nxt[-1]) and last is not None:
            nxt[-1] = float(last)                              # no day after it yet: the last price
        d = d.assign(close=nxt).dropna(subset=["close"])
        d = d.assign(high=d[["high", "open", "close"]].max(axis=1), low=d[["low", "open", "close"]].min(axis=1))
    return d[d["high"] > d["low"]].reset_index(drop=True)


def state_at(market: str, days: pd.DataFrame, monday: pd.Timestamp,
             price: Optional[float] = None) -> tuple[Optional[dict], bool]:
    """The state at the open of the week of ``monday`` from ``days`` (read only before it), at ``price``, and
    whether it is provisional (its Friday missing). Without ``price``: the week's open once it has opened (its first
    day in ``days``), else the last close. A month still running at ``monday`` is not a closed candle, as in
    training."""
    monday = pd.Timestamp(monday).normalize()
    opened = days[(days["date"] >= monday) & (days["date"] < monday + timedelta(days=7))]
    if price is None and len(opened):
        price = float(opened["open"].iat[0])
    before = days[days["date"] < monday].reset_index(drop=True)
    if before.empty:
        return None, True
    fr = build_frames(before)
    fr["MN1"] = fr["MN1"][fr["MN1"]["first"].dt.to_period("M") != monday.to_period("M")].reset_index(drop=True)
    frames = {tf: _Frame(fr[tf], tf) for tf in FRAMES}
    weeks = fr["W1"]
    prev_close, prev_last = float(weeks["close"].iat[-1]), pd.Timestamp(weeks["last"].iat[-1])
    row = week_state(market, frames, monday, prev_close if price is None else float(price), prev_close, prev_last,
                     monday + timedelta(days=4))
    provisional = pd.Timestamp(before["date"].iat[-1]) < monday - timedelta(days=3)
    if row is not None:
        row = {k: row[k] for k in ("market", "week", "open", *FEATURES)}
    return row, bool(provisional)
