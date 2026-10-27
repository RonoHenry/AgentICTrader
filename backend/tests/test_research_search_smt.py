"""
Tests for algo_research/search_smt.py — SMT divergence at a major array, H-L (context-engine Requirement 29;
docs/research/SEARCH_2018_2024.md).

Task 367 (.kiro/specs/context-engine/tasks.md). Synthetic bars only: nothing here reads the snapshot. Hand-made days
check the divergence (both legs, the dollar index inverse) and the one-call-per-day rule; hand-made bars check each
gate; a wave checks the W1 extreme against the frame state and that later bars change nothing (Property 2).
Validates: Requirements 29.1-29.2 (.kiro/specs/context-engine/requirements.md); Property 2
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_chain import Ladder
from algo_research.search_smt import arm_calls, market_days, smt_legs
from liquidity_engine.context.frame_state import frame_state

DATES = pd.DatetimeIndex(["2021-03-01", "2021-03-02", "2021-03-03"], tz="UTC")


def day_flags(took_low, took_high, **gates):
    n = len(took_low)
    frame = pd.DataFrame({"date": DATES[:n], "took_low": took_low, "took_high": took_high})
    for g in ("a_bull", "a_bear", "b_bull", "b_bear", "c_bull", "c_bear"):
        frame[g] = gates.get(g, [False] * n)
    return frame


def legs_of(days):
    return sorted((r.market, r.date.strftime("%m-%d"), r.side, bool(r.swept)) for r in smt_legs(days).itertuples())


def test_divergence_calls_both_legs():
    days = {"EURUSD": day_flags([True, True, False], [False, False, True]),
            "GBPUSD": day_flags([False, True, False], [False, False, True])}
    assert legs_of(days) == [("EURUSD", "03-01", 1, True), ("GBPUSD", "03-01", 1, False)]   # both took on 03-02


def test_dollar_index_is_inverse():
    days = {"EURUSD": day_flags([True, True], [False, False]), "DXY": day_flags([False, False], [False, True])}
    # 03-01: the euro took its low, the dollar didn't take its high -> bullish euro, bearish dollar.
    # 03-02: the euro took its low and the dollar its high: they agree, no divergence.
    assert legs_of(days) == [("DXY", "03-01", -1, False), ("EURUSD", "03-01", 1, True)]


def test_one_call_per_market_and_day():
    legs = pd.DataFrame({"market": ["DXY", "DXY", "EURUSD"], "date": [DATES[0]] * 3, "side": [1, -1, 1],
                         "swept": [True, False, True], "gate_a": True, "gate_b": False, "gate_c": False})
    calls = arm_calls(legs, legs["gate_a"])
    assert calls.values.tolist() == [["EURUSD", DATES[0], 1]]                # the dollar called both ways: dropped


def bars(rows, start="2021-01-04"):
    days = pd.bdate_range(start, periods=len(rows), tz="UTC")
    prices = {k: [r[i] for r in rows] for i, k in enumerate(("open", "high", "low", "close"))}
    return pd.DataFrame({"time": days, **prices})


FLAT = (100.0, 100.5, 99.5, 100.0)


def test_gate_a_first_touch_of_an_unfilled_block():
    rows = [FLAT] * 16 + [(100.0, 100.2, 98.8, 99.0), (99.0, 105.0, 98.9, 104.8)]   # a down day, then a 1.5-ATR rally
    rows += [(104.8, 105.5, 103.5, 105.0), (105.0, 105.2, 99.8, 100.2), (100.2, 100.4, 99.0, 99.5)]
    flags = market_days(bars(rows))
    assert flags["a_bull"].tolist().index(True) == 19 and flags["a_bull"].sum() == 1   # first back into 98.8-100.2


def test_gate_b_major_pools():
    rows = [FLAT] * 25 + [(100.0, 100.3, 99.0, 99.2)]                         # below the 20-day low of 99.5
    flags = market_days(bars(rows))
    assert flags["b_bull"].iloc[-1] and not flags["b_bull"].iloc[:-1].any()
    swing = [FLAT] * 3 + [(100.0, 100.1, 98.0, 99.0), (99.0, 99.6, 98.6, 99.4), (99.4, 99.7, 98.8, 99.5)]
    swing += [(99.5, 99.8, 98.7, 99.6), (99.6, 99.9, 97.9, 98.5)]           # the swing low at 98.0, taken
    flags = market_days(bars(swing))
    assert flags["b_bull"].iloc[-1] and not flags["b_bull"].iloc[4:-1].any()


def wave(n=320, seed=2):
    days = pd.bdate_range("2019-01-01", periods=n, tz="UTC")
    rng = np.random.default_rng(seed)
    c = 100 + 8 * np.sin(2 * np.pi * np.arange(n) / 90) + np.cumsum(rng.normal(0, 0.5, n))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"time": days, "open": o, "high": np.maximum(o, c) + rng.random(n) * 0.4,
                         "low": np.minimum(o, c) - rng.random(n) * 0.4, "close": c})


def test_gate_c_is_the_w1_ranges_outer_quarter():
    b = wave()
    flags = market_days(b)
    ladder = Ladder(b)
    assert flags["c_bull"].sum() > 10 and flags["c_bear"].sum() > 10 and not (flags["c_bull"] & flags["c_bear"]).any()
    for d in range(60, len(b), 17):
        _days, weeks, _m, forming, _mf = ladder.at(d)
        s = frame_state(weeks, float(b["close"].iloc[d]), forming=forming)
        if s.position is not None:
            assert flags["c_bull"].iloc[d] == (s.position <= 0.25) and flags["c_bear"].iloc[d] == (s.position >= 0.75)


def test_days_read_only_the_past():
    """Property 2: the bars after a day change none of its flags."""
    b = wave()
    full = market_days(b)
    for cut in (150, 247):
        pd.testing.assert_frame_equal(market_days(b.iloc[:cut].reset_index(drop=True)), full.iloc[:cut])
