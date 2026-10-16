"""News in the atlas (algo-research update 2026-10i, Requirement 30).

Each swing gains four columns, from an instrument's counting release times only. The schedule is published
before the week it covers, so nothing here reads what wasn't known (AR-D36):

- ``news_made``: a release in the 15 minutes up to the extreme's minute, inclusive. The release printed the
  extreme.
- ``news_ahead``: a release in the 60 minutes after the extreme's minute. The extreme was a run before the
  release.
- ``news_next_bar``: a release in the swing's next bar of its timeframe, after it is known.
- ``news_day``: how many releases fall on the extreme's trading date: "0", "1" or "2+".

    news_columns(swings, releases)        # swings with tf, extreme_time and known_at

Validates: Requirement 30.2 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.frame import calendar_columns

__all__ = ["AHEAD_MINUTES", "MADE_MINUTES", "NEWS_COLUMNS", "news_columns"]

NEWS_COLUMNS = ["news_made", "news_ahead", "news_next_bar", "news_day"]
MADE_MINUTES, AHEAD_MINUTES = 15, 60
_BAR = {"M15": pd.Timedelta(minutes=15), "H1": pd.Timedelta(hours=1), "H4": pd.Timedelta(hours=4),
        "D1": pd.Timedelta(days=1), "W1": pd.Timedelta(days=7)}


def _ns(times) -> np.ndarray:
    index = pd.DatetimeIndex(times)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    return index.tz_localize(None).to_numpy("datetime64[ns]").view(np.int64)


def _any_in(releases: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Whether a release falls in each (lo, hi]."""
    return np.searchsorted(releases, hi, "right") > np.searchsorted(releases, lo, "right")


def news_columns(swings: pd.DataFrame, releases: pd.DatetimeIndex) -> pd.DataFrame:
    """The news columns for ``swings`` (columns tf, extreme_time, known_at), one row each, same index."""
    times = np.sort(_ns(releases)) if len(releases) else np.empty(0, np.int64)
    extreme, known = _ns(swings["extreme_time"]), _ns(swings["known_at"])
    made = pd.Timedelta(minutes=MADE_MINUTES).value
    ahead = pd.Timedelta(minutes=AHEAD_MINUTES).value
    bar = swings["tf"].map(lambda tf: _BAR[tf].value).to_numpy(np.int64)
    if len(times):
        per_day = pd.Series(calendar_columns(pd.DatetimeIndex(times).tz_localize("UTC"))["trading_date"]).value_counts()
    else:
        per_day = pd.Series(dtype=int)
    dates = calendar_columns(pd.DatetimeIndex(extreme).tz_localize("UTC"))["trading_date"]
    counts = dates.map(per_day).fillna(0).astype(int).to_numpy()
    return pd.DataFrame({
        "news_made": _any_in(times, extreme - made, extreme),
        "news_ahead": _any_in(times, extreme, extreme + ahead),
        "news_next_bar": _any_in(times, known, known + bar),
        "news_day": np.where(counts >= 2, "2+", counts.astype(str)),
    }, index=swings.index)[NEWS_COLUMNS]
