"""The broad universe for H-AA and H-AB (docs/research/SEARCH_2018_2024.md): markets beyond the nine, from Yahoo's
daily history to 2023-01-01, so the brain learns from more of the world's weeks than nine markets hold.

Each market's orientation to the dollar (``USD_SIDE``: +1 rises with it, -1 falls) and whether it is an equity index
(``EQUITY``) set the flow features' signs (``search_state3``). ``load_broad`` cleans the bars as ``search_state.load``
does: Yahoo's FX close is the day's open, so an FX day closes at the next day's open; and each market starts where its
bars have real opens, highs and lows.

    python scripts/export_yahoo_history.py --universe broad
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_state import YAHOO, load
from algo_research.snapshot import SNAPSHOTS_DIR

__all__ = ["BROAD", "BROAD_ROOT", "EQUITY", "USD_SIDE", "first_clean", "load_broad", "orientation"]

BROAD_ROOT = SNAPSHOTS_DIR / "yahoo-broad-to-2022"
#: Yahoo's symbol for each added market (FX "=X", continuous futures "=F").
BROAD = {
    "USDJPY": "USDJPY=X", "AUDUSD": "AUDUSD=X", "NZDUSD": "NZDUSD=X", "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X",
    "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X", "EURGBP": "EURGBP=X", "AUDJPY": "AUDJPY=X", "EURCHF": "EURCHF=X",
    "USDSEK": "USDSEK=X", "USDNOK": "USDNOK=X",
    "JP225": "^N225", "HK50": "^HSI", "FRA40": "^FCHI", "EU50": "^STOXX50E", "AUS200": "^AXJO", "CA60": "^GSPTSE",
    "US2000": "^RUT", "CH20": "^SSMI", "NL25": "^AEX", "ES35": "^IBEX", "KR200": "^KS11", "BR60": "^BVSP",
    "XAGUSD": "SI=F", "WTI": "CL=F", "COPPER": "HG=F", "NATGAS": "NG=F", "XPTUSD": "PL=F", "CORN": "ZC=F",
    "WHEAT": "ZW=F", "SOY": "ZS=F", "UST10": "ZN=F", "UST30": "ZB=F", "BTCUSD": "BTC-USD",
}
NINE_EQUITY = ("US100", "US500", "US30", "GER40", "UK100")
EQUITY = NINE_EQUITY + ("JP225", "HK50", "FRA40", "EU50", "AUS200", "CA60", "US2000", "CH20", "NL25", "ES35", "KR200",
                        "BR60")
USD_SIDE = {"DXY": 1, "USDJPY": 1, "USDCAD": 1, "USDCHF": 1, "USDSEK": 1, "USDNOK": 1,
            "EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "NZDUSD": -1, "XAUUSD": -1, "XAGUSD": -1, "XPTUSD": -1}


def orientation(market: str) -> tuple[float, float]:
    """(the market's side against the dollar, 1 if an equity index)."""
    return float(USD_SIDE.get(market, 0)), float(market in EQUITY)


def first_clean(d: pd.DataFrame, window: int = 250, share: float = 0.95) -> pd.Timestamp:
    """The first date from which every trailing ``window`` of days has real bars: a high above the low and an open
    away from the close on at least ``share`` of them (Yahoo's early years often carry the close in all four)."""
    ok = ((d["high"] > d["low"]) & (d["open"] != d["close"])).astype(float)
    good = ok.rolling(window, min_periods=window).mean() >= share
    bad_after = (~good).to_numpy()[::-1].cumsum()[::-1] > 0        # a failing window at or after this row
    idx = np.nonzero(~bad_after)[0]
    if not len(idx):
        return pd.Timestamp("2100-01-01")
    return pd.Timestamp(d["date"].iat[max(idx[0] - window + 1, 0)])


def load_broad(market: str) -> pd.DataFrame:
    """A market's cleaned daily bars: the nine from H-Y's snapshot, the added ones from the broad snapshot."""
    if market not in BROAD:
        return load(market, YAHOO)
    d = pd.read_parquet(BROAD_ROOT / f"{market}_D1.parquet")[["date", "open", "high", "low", "close"]]
    if BROAD[market].endswith("=X"):
        d = d.assign(close=d["open"].shift(-1)).dropna(subset=["close"])
        d = d.assign(high=d[["high", "open", "close"]].max(axis=1), low=d[["low", "open", "close"]].min(axis=1))
    d = d.sort_values("date").reset_index(drop=True)
    d = d[d["date"] >= first_clean(d)]
    return d[d["high"] > d["low"]].reset_index(drop=True)
