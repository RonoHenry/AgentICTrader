"""
Tests for H-AF's replay (algomind-dis Requirement 15; task 406), on a random walk: no market data is read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algomind_dis.replay import market_tables, report


def walk(seed: int, start: str, n: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, periods=n)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[100.0, c[:-1]]
    spread = np.abs(rng.normal(0, 0.006, n)) * c
    return pd.DataFrame({"date": days, "open": o, "high": np.maximum(o, c) + spread,
                         "low": np.minimum(o, c) - spread, "close": c})


def test_the_replay_scores_establishments_and_weeks_with_h_aes_scorer():
    t = market_tables("WALK", walk(3, "1994-06-01", 1100))
    calls, weeks = t["calls"], t["weeks"]
    states = t["states"]
    assert len(calls) and calls["t"].min() >= pd.Timestamp("1996-01-01")
    established = states[states["state"].isin(["BULLISH", "BEARISH"]) & (states["since"] == states["t"])]
    in_window = established[pd.to_datetime(established["t"], unit="ns") >= calls["t"].min()]
    assert len(calls) == len(in_window)                              # one call per establishment, none per fade
    assert set(calls["outcome"]) <= {"held", "failed", "open", "no draw"}
    resolved = calls[calls["outcome"].isin(["held", "failed"])]
    assert resolved["control"].between(0, 1).all() and (resolved["n_control"] > 0).all()
    assert set(weeks["side"]) <= {-1, 0, 1} and weeks["t"].min() >= pd.Timestamp("1996-01-01")
    live = weeks[weeks["side"] != 0]
    assert (live["hit"] == np.where(live["side"] > 0, live["up"], live["down"])).all()
    assert set(weeks["htf"]) <= {-1, 0, 1}
    text, passes = report(t)
    assert text.startswith("**H-AF ") and isinstance(passes, bool)
