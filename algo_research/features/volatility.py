"""Session volatility: each instrument's normal range per session, and today against it.

Time works through volatility (update 2026-10e): the day's extremes sit where the
market moves most, and that differs by instrument. These columns hold, per
instrument and from the previous 20 trading dates only, the normal range:

| Column | Definition |
|---|---|
| ``slot_range_norm`` | median ``high - low`` of the M15 bar ending at t (its New York slot), over the previous 20 trading dates that have one |
| ``h4_range_norm`` | median full range of the current H4 candle (by ``h4_index``) over the previous 20 trading dates |
| ``h4_range_so_far_norm`` | median range of the current H4 candle from its open through the same number of M15 bars, over the previous 20 trading dates; null while none of its bars has closed |
| ``h4_range_ratio`` | the current H4 candle's range through t / ``h4_range_so_far_norm``: above 1 runs hotter than normal |

Each M15 bar belongs to the trading date, H4 candle and slot of its open. A
date's norms use only earlier dates, so every value is known at t (Property 1):
the norms from the trading date's start, the ratio from t.

    vol = volatility_features(frame, features)    # same index as features

Validates: Requirements 21.1, 21.4 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.features.market import Column
from algo_research.frame import InstrumentFrame, calendar_columns
from liquidity_engine.models import Timeframe

__all__ = ["LOOKBACK_DATES", "VOLATILITY_COLUMNS", "volatility_features"]

LOOKBACK_DATES = 20                                      # AR-D20

VOLATILITY_COLUMNS: dict[str, Column] = {
    "slot_range_norm": Column("median high - low of the M15 bar ending at t, in its New York slot, over the "
                              "previous 20 trading dates that have one", "price", "the trading date's start"),
    "h4_range_norm": Column("median full range of the current H4 candle (by h4_index) over the previous 20 "
                            "trading dates", "price", "the trading date's start"),
    "h4_range_so_far_norm": Column("median range of the current H4 candle from its open through the same number "
                                   "of M15 bars, over the previous 20 trading dates; null before its first bar "
                                   "closes", "price", "the trading date's start"),
    "h4_range_ratio": Column("the current H4 candle's range through t / h4_range_so_far_norm", "ratio", "t"),
}

_BARS_PER_H4 = 16


def _h4_start(h4_index: np.ndarray) -> np.ndarray:
    """New York minute each H4 candle opens: 17:00, 21:00, 01:00, 05:00, 09:00, 13:00."""
    return (17 * 60 + 240 * np.asarray(h4_index, dtype=int)) % 1440


def volatility_features(frame: InstrumentFrame, features: pd.DataFrame) -> pd.DataFrame:
    """``VOLATILITY_COLUMNS`` for ``features``' rows of one instrument, same index."""
    out = pd.DataFrame({name: np.full(len(features), np.nan) for name in VOLATILITY_COLUMNS}, index=features.index)
    m15 = frame.bars[Timeframe.M15]
    if m15.empty or features.empty:
        return out

    cal = calendar_columns(pd.DatetimeIndex(m15["time"]))                 # by the bar's open
    bars = pd.DataFrame({"date": cal["trading_date"].to_numpy(), "minute": cal["ny_minute"].to_numpy(),
                         "h4": cal["h4_index"].to_numpy(), "high": m15["high"].to_numpy(dtype=float),
                         "low": m15["low"].to_numpy(dtype=float)})
    bars["k"] = (bars["minute"] - _h4_start(bars["h4"])) % 1440 // 15 + 1   # its place in its H4: 1-16
    bars = bars.sort_values(["date", "h4", "k"], kind="stable")
    grouped = bars.groupby(["date", "h4"], sort=False)
    bars["so_far"] = grouped["high"].cummax() - grouped["low"].cummin()

    slot = bars.assign(range=bars["high"] - bars["low"]).pivot_table(
        index="date", columns="minute", values="range", aggfunc="first")
    so_far = bars.pivot_table(index="date", columns=["h4", "k"], values="so_far", aggfunc="first")
    so_far = so_far.reindex(columns=pd.MultiIndex.from_product([range(6), range(1, _BARS_PER_H4 + 1)],
                                                               names=["h4", "k"]))
    for h4 in range(6):                                                    # a missing bar keeps the range so far
        columns = [(h4, k) for k in range(1, _BARS_PER_H4 + 1)]
        so_far[columns] = so_far[columns].ffill(axis=1).to_numpy()
    full = so_far.xs(_BARS_PER_H4, level="k", axis=1)

    rows_date = features["trading_date"].to_numpy(dtype="datetime64[ns]")
    rows_h4 = features["h4_index"].to_numpy(dtype=int)
    rows_k = (features["ny_minute"].to_numpy(dtype=int) - _h4_start(rows_h4)) % 1440 // 15   # bars closed by t
    bar_open = calendar_columns(pd.DatetimeIndex(features["t"]) - pd.Timedelta(minutes=15))  # the bar ending at t

    out["slot_range_norm"] = _lookup(_prior_median(slot), bar_open["trading_date"].to_numpy(dtype="datetime64[ns]"),
                                     bar_open["ny_minute"].to_numpy(dtype=int))
    out["h4_range_norm"] = _lookup(_prior_median(full), rows_date, rows_h4)
    has_bar = rows_k >= 1
    keys = list(zip(rows_h4, np.maximum(rows_k, 1)))
    so_far_norm = _lookup(_prior_median(so_far), rows_date, keys)
    current = _lookup(so_far, rows_date, keys)
    out["h4_range_so_far_norm"] = np.where(has_bar, so_far_norm, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["h4_range_ratio"] = np.where(has_bar, current / so_far_norm, np.nan)
    return out


def _prior_median(table: pd.DataFrame) -> pd.DataFrame:
    """Per column, at each date with a value: the median of its previous LOOKBACK_DATES values
    (dates without one are skipped); null with fewer."""
    out = pd.DataFrame(np.nan, index=table.index, columns=table.columns)
    for column in table.columns:
        values = table[column].dropna()
        out.loc[values.index, column] = values.rolling(LOOKBACK_DATES, min_periods=LOOKBACK_DATES).median().shift(1)
    return out


def _lookup(table: pd.DataFrame, dates: np.ndarray, columns) -> np.ndarray:
    """table.loc[date, column] for each row; NaN where either is missing."""
    stacked = table.stack(list(range(table.columns.nlevels)), future_stack=True)
    index = pd.MultiIndex.from_arrays([pd.DatetimeIndex(dates), *(
        [np.asarray(columns)] if table.columns.nlevels == 1 else [np.array([c[i] for c in columns])
                                                                  for i in range(table.columns.nlevels)])])
    return stacked.reindex(index).to_numpy(dtype=float)
