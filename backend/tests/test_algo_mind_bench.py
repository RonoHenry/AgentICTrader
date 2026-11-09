"""
Tests for algo_mind/bench.py — the bench's markets (algo-mind Requirement 6, task 387).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_mind.bench import random_walk_days


def real(n=2600, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2000-01-03", periods=n)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[100, c[:-1]]
    return pd.DataFrame({"date": dates, "open": o, "close": c, "high": np.maximum(o, c) * 1.004,
                         "low": np.minimum(o, c) * 0.996})


def test_a_bench_market_keeps_the_dates_and_volatility_and_holds_no_lean():
    r = real()
    walk = random_walk_days(r, seed=1)
    assert (walk["date"].to_numpy() == r["date"].to_numpy()).all()
    vol = np.std(np.diff(np.log(walk["close"])))
    assert abs(vol - np.std(np.diff(np.log(r["close"])))) < 0.002
    assert ((walk["high"] >= walk[["open", "close"]].max(axis=1)) & (walk["low"] <= walk[["open", "close"]].min(axis=1))).all()


def weekly_lean(days: pd.DataFrame) -> float:
    """Up-week share when a week opens in its 26-week range's bottom third, minus the share in its top third."""
    w = days.groupby(days["date"] - pd.to_timedelta(days["date"].dt.dayofweek, unit="D")).agg(
        o=("open", "first"), c=("close", "last"), h=("high", "max"), l=("low", "min"))
    top, bottom = w["h"].rolling(26).max().shift(1), w["l"].rolling(26).min().shift(1)
    pos = (w["o"] - bottom) / (top - bottom)
    up = w["c"] > w["o"]
    return float(up[pos < 1 / 3].mean() - up[pos > 2 / 3].mean())


def test_a_planted_lean_shows_in_the_weeks_and_none_without_it():
    r = real(n=8000)
    planted = np.mean([weekly_lean(random_walk_days(r, seed=s, plant=0.10)) for s in range(3)])
    none = np.mean([weekly_lean(random_walk_days(r, seed=s)) for s in range(3)])
    assert planted > 0.12 and abs(none) < 0.06
