"""
Tests for algo_research/search_state.py — H-Y, the learned combination of time and price at the weekly open
(docs/research/SEARCH_2018_2024.md). Synthetic bars only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_state import FEATURES, _Frame, build_frames, fit_and_call, judge, load, state_table


def days(n=900, seed=0, start="2000-01-03"):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n)
    o = 100 + rng.normal(0, 1, n).cumsum()
    c = o + rng.normal(0, 0.8, n)
    return pd.DataFrame({"date": dates, "open": o, "high": np.maximum(o, c) + rng.uniform(0.1, 1, n),
                         "low": np.minimum(o, c) - rng.uniform(0.1, 1, n), "close": c})


def test_an_fx_day_closes_at_the_next_days_open_and_the_flat_years_are_cut(tmp_path):
    d = days(10)
    d.assign(time=d["date"]).to_parquet(tmp_path / "EURUSD_D1.parquet")
    fx = load("EURUSD", tmp_path)
    assert len(fx) == 9 and np.allclose(fx["close"], d["open"].iloc[1:].to_numpy())
    assert (fx["high"] >= fx[["open", "close"]].max(axis=1)).all() and (fx["low"] <= fx[["open", "close"]].min(axis=1)).all()
    flat = days(10, start="1989-12-25")
    flat.loc[2, "high"] = flat.loc[2, "low"]
    flat.assign(time=flat["date"]).to_parquet(tmp_path / "DXY_D1.parquet")
    dxy = load("DXY", tmp_path)
    assert dxy["date"].min() >= pd.Timestamp("1990-01-01") and (dxy["high"] > dxy["low"]).all()


def test_a_frame_reads_shape_liquidity_and_gaps_at_a_price():
    bars = pd.DataFrame([(10, 11, 9, 10.5), (10.5, 13, 10, 12.8), (12.8, 13.5, 12.5, 13), (13, 14, 12.9, 13.6),
                         (13.6, 13.7, 12.6, 12.7), (12.7, 12.9, 11.8, 12.0), (12.0, 12.6, 11.9, 12.5)] * 4,
                        columns=["open", "high", "low", "close"], dtype=float)
    bars["last"] = pd.bdate_range("2020-01-06", periods=len(bars))
    f = _Frame(bars, "D1")
    k = len(bars) - 1                                       # (12.0, 12.6, 11.9, 12.5) after (12.7, 12.9, 11.8, 12.0)
    r = f.read(k, 12.5)
    assert np.isclose(r["pos"], (12.5 - 11.9) / 0.7) and r["expansion"] == 0
    assert r["turtle"] == 0                                 # inside the candle before it
    assert r["swing_up"] > 0 and r["swing_dn"] > 0
    assert r["prev_up"] == (12.6 - 12.5) / f.mean[k]
    r2 = f.read(k - 1, 12.0)                                # (12.7, 12.9, 11.8, 12.0) closed below 12.6: expansion
    assert r2["expansion"] == -1


def test_the_state_table_reads_only_closed_candles_and_calls_the_thirds():
    t = state_table("X", days(1400, seed=3))
    assert set(FEATURES) <= set(t.columns) and t["week"].is_monotonic_increasing
    assert t[list(FEATURES)].notna().all().all()
    frames = build_frames(days(1400, seed=3))
    w1 = frames["W1"]
    row = t.iloc[10]
    prev = w1[w1["last"] < row["week"]].iloc[-1]             # the last week closed before this one opened
    assert np.isclose(row["W1_pos"], (prev["close"] - prev["low"]) / (prev["high"] - prev["low"]))
    fit, judged = t.iloc[:150], t.iloc[150:]
    f, c, _ = fit_and_call(fit.assign(market="X"), judged.assign(market="X"), "logit")   # 150 weeks: no GBM leaf
    calls = f["call"].value_counts()
    assert abs(calls.get(1, 0) - len(f) / 3) <= len(f) * 0.05 and abs(calls.get(-1, 0) - len(f) / 3) <= len(f) * 0.05
    r = judge(c)
    assert r["calls"] == int(((c["call"] != 0) & (c["up"] != 0)).sum())


def test_one_sides_calls_are_judged_against_the_drift_of_every_week():
    t = pd.DataFrame({"market": "X", "week": pd.date_range("2020-01-06", periods=8, freq="W-MON"),
                      "up": [1, 1, 1, 1, 1, 1, -1, -1], "call": [1, 1, 1, 0, 0, 0, -1, 1]})
    up = judge(t, side=1)                                   # 3 of 4 up calls right; 6 of 8 weeks went up
    assert up["calls"] == 4 and np.isclose(up["hit"], 0.75) and np.isclose(up["base"], 0.75)
    down = judge(t, side=-1)                                # 1 of 1 right; 2 of 8 weeks went down
    assert down["calls"] == 1 and np.isclose(down["excess"], 1 - 0.25)
