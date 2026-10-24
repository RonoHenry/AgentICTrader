"""The 2018-2024 search's D1 path (docs/research/SEARCH_2018_2024.md, Amendment 1)."""
import numpy as np
import pandas as pd

from algo_research.search_d1 import d1_frame, merge_sundays
from liquidity_engine.models import Timeframe


def _server_days(days, ohlc):
    return pd.DataFrame({"time": pd.DatetimeIndex(days, tz="UTC"),
                         **{k: np.array([row[n] for row in ohlc], float) for n, k in enumerate(("open", "high", "low", "close"))}})


def test_sunday_merges_into_monday():
    bars = _server_days(["2020-03-06", "2020-03-08", "2020-03-09", "2020-03-10"],
                        [(1.0, 1.2, 0.9, 1.1), (1.1, 1.15, 1.05, 1.12), (1.12, 1.3, 1.0, 1.25), (1.25, 1.26, 1.2, 1.21)])
    merged = merge_sundays(bars)
    assert list(merged["time"].dt.strftime("%a %d")) == ["Fri 06", "Mon 09", "Tue 10"]
    monday = merged.iloc[1]
    assert (monday["open"], monday["high"], monday["low"], monday["close"]) == (1.1, 1.3, 1.0, 1.25)


def test_the_frame_reads_the_bars_as_its_days_and_weeks():
    days = pd.bdate_range("2020-03-02", "2020-03-20", tz="UTC")
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 1, len(days)))
    opens = np.r_[100.0, close[:-1]]
    bars = pd.DataFrame({"time": days, "open": opens, "high": np.maximum(opens, close) + 0.5,
                         "low": np.minimum(opens, close) - 0.5, "close": close})
    frame = d1_frame("TEST", bars)
    d1 = frame.bars[Timeframe.D1]
    assert len(d1) == len(bars) - 1                              # the last day isn't closed by the path's end
    assert np.allclose(d1[["open", "high", "low", "close"]].to_numpy(), bars.iloc[:-1, 1:].to_numpy())
    w1 = frame.bars[Timeframe.W1]
    first_week = bars.iloc[:5]
    assert (w1["high"].iloc[0], w1["low"].iloc[0]) == (first_week["high"].max(), first_week["low"].min())
