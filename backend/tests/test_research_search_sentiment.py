"""
Tests for algo_research/search_sentiment.py — H-X, candle sentiment (docs/research/SEARCH_2018_2024.md).
The trader's own months (US500, Exness, 2026) and synthetic days.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_sentiment import _base, judge, market_rows, reads
from algo_research.search_side import monthly
from algo_research.search_soup import weekly

# US500 on Exness, June, July and August 2026: open, high, low, close.
MONTHS = pd.DataFrame([(7602.00, 7629.51, 7236.49, 7500.32), (7500.46, 7595.01, 7299.08, 7488.63),
                       (7525.41, 7825.22, 7522.35, 7701.09)], columns=["open", "high", "low", "close"])


def test_the_read_is_the_close_in_the_range_and_the_wicks_not_the_colour():
    r = reads(MONTHS)
    assert list(r["colour"]) == [-1, -1, 1]
    assert list(r["close"]) == [1, 1, 1]                                    # 67%, 64% and 59% of the range
    assert list(r["wicks"]) == [1, 1, -1]                                   # August: 124 above, 3 below
    assert list(r["call"]) == [1, 1, 0]                                     # "still bullish", twice; August mixed
    assert list(r["strong"]) == [1, 0, 0]                                   # June: outer third, wick 9.6x


def test_calls_are_judged_on_the_next_candle_against_the_drift():
    days = pd.DataFrame({"time": pd.date_range("2022-01-03", periods=60, freq="B", tz="UTC")})
    rng = np.random.default_rng(1)
    o = 100 + rng.normal(0, 1, 60).cumsum()
    c = o + rng.normal(0, 1, 60)
    days = days.assign(open=o, close=c, high=np.maximum(o, c) + rng.uniform(0.1, 1, 60),
                       low=np.minimum(o, c) - rng.uniform(0.1, 1, 60))
    weeks, d = weekly(days)
    frames = {"D1": d, "W1": weeks, "MN1": monthly(d)}
    t = market_rows(frames, d["high"].to_numpy(float), d["low"].to_numpy(float), "X", "2022-01-01", "2022-04-01")
    t["up_share"] = _base(t)
    days_t = t[t["frame"] == "D1"]
    assert len(days_t) == 59                                                # the last day has no next candle
    first = days_t.iloc[0]
    assert first["next_dir"] == np.sign(c[1] - o[1])
    r = judge(days_t)
    called = days_t[(days_t["call"] != 0) & (days_t["next_dir"] != 0)]
    assert r["calls"] == len(called)
    hits = (called["next_dir"] == called["call"]).mean()
    assert np.isclose(r["hit"], hits)
    up = (days_t.loc[days_t["next_dir"] != 0, "next_dir"] > 0).mean()
    base = np.where(called["call"] > 0, up, 1 - up).mean()
    assert np.isclose(r["base"], base) and np.isclose(r["excess"], hits - base)
    w = t[t["frame"] == "W1"]
    assert set(w["above"].unique()) <= {-1, 0, 1} and (t[t["frame"] == "MN1"]["above"] == 0).all()
