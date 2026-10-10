"""
Tests for algo_research/features/volatility.py — each instrument's normal range
per session from the previous 20 trading dates, and whether today runs hotter
or colder; and the ``h4_range`` race geometry.

Task 272 (.kiro/specs/algo-research/tasks.md). Flat simulated markets whose
bar ranges are set by formula, so every median is known exactly.
Validates: Requirements 21.1, 21.2, 21.4 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algo_research.frame import build_grid, frame_from_arrays
from tests.research_fixtures import fx_minutes

BASE = 1.1
DAYS = 30


def ranged_frame(range_of):
    """Flat M1 bars at BASE, each with high - low = range_of(trading-date index, New York minute)."""
    times = fx_minutes(date(2026, 1, 4), DAYS)
    local = times.tz_convert("America/New_York")
    day = (local.tz_localize(None) + pd.Timedelta(hours=7)).normalize()
    index = pd.Series(day).rank(method="dense").to_numpy().astype(int) - 1
    minute = (local.hour * 60 + local.minute).to_numpy()
    r = np.array([range_of(d, m) for d, m in zip(index, minute)])
    o = np.full(len(times), BASE)
    return frame_from_arrays("EURUSD", times, o, o + r / 2, o - r / 2, o, spread=np.full(len(times), 0.0001),
                             typical_spread=0.0001, stop_slippage=0.0)


def grid(frame):
    dates = sorted(set(frame.m1["trading_date"]))
    return build_grid(frame, {"explore": (pd.Timestamp(dates[0]).date(), pd.Timestamp(dates[-1]).date())})


def day_index(features: pd.DataFrame) -> np.ndarray:
    return pd.Series(features["trading_date"]).rank(method="dense").to_numpy().astype(int) - 1


def h4_offset(features: pd.DataFrame) -> np.ndarray:
    start = (17 * 60 + 240 * features["h4_index"].to_numpy().astype(int)) % 1440
    return ((features["ny_minute"].to_numpy().astype(int) - start) % 1440) // 15


def by_date(d, m):                                     # every bar of date d has range (d + 1) pips
    return 0.0001 * (d + 1) if d != 25 else 0.01       # date 25 is a spike


def test_norms_are_medians_of_the_previous_20_dates_only():
    from algo_research.features.volatility import VOLATILITY_COLUMNS, volatility_features

    frame = ranged_frame(by_date)
    g = grid(frame)
    v = volatility_features(frame, g)
    assert list(v.columns) == list(VOLATILITY_COLUMNS) and v.index.equals(g.index)
    d, k = day_index(g), h4_offset(g)
    mid = (g["ny_minute"].to_numpy() == 9 * 60 + 30)                 # 09:30: the 09:00 H4's 2nd bar has closed
    for i in np.flatnonzero(mid):
        if d[i] < 20:
            assert v.iloc[i].isna().all(), d[i]                      # fewer than 20 earlier dates: null
            continue
        prior = [by_date(j, 0) for j in range(d[i] - 20, d[i])]
        want = float(np.median(prior))
        for name in ("slot_range_norm", "h4_range_norm", "h4_range_so_far_norm"):
            assert v[name].iloc[i] == pytest.approx(want), (d[i], name)
        assert v["h4_range_ratio"].iloc[i] == pytest.approx(by_date(d[i], 0) / want)
    spike = np.flatnonzero(mid & (d == 25))[0]
    assert v["h4_range_norm"].iloc[spike] == pytest.approx(np.median([by_date(j, 0) for j in range(5, 25)]))
    assert v["h4_range_ratio"].iloc[spike] > 5                        # today runs far hotter than normal


def by_position(d, m):                                 # the k-th M15 bar of every H4 has range k pips
    start = (m - 17 * 60) % 240
    return 0.0001 * (start // 15 + 1)


def test_so_far_norm_is_time_matched_within_the_h4():
    from algo_research.features.volatility import volatility_features

    frame = ranged_frame(by_position)
    g = grid(frame)
    v = volatility_features(frame, g)
    d, k = day_index(g), h4_offset(g)
    late = (d >= 20) & (k >= 1)
    assert late.any()
    assert np.allclose(v["h4_range_so_far_norm"].to_numpy()[late], 0.0001 * k[late])
    assert np.allclose(v["h4_range_norm"].to_numpy()[late], 0.0016)
    assert np.allclose(v["h4_range_ratio"].to_numpy()[late], 1.0)    # normal for the time of the H4, not 16 bars' worth
    at_open = (d >= 20) & (k == 0)                                   # no bar of the H4 has closed yet
    assert v.loc[at_open, ["h4_range_so_far_norm", "h4_range_ratio"]].isna().all().all()
    assert v.loc[at_open, "h4_range_norm"].notna().all()


def test_volatility_uses_only_the_past():
    # Property 1: the row at t is the same from data cut off at t.
    from algo_research.features.volatility import VOLATILITY_COLUMNS, volatility_features
    from tests.test_research_features import _truncated

    frame = ranged_frame(by_date)
    g = grid(frame)
    full = volatility_features(frame, g)
    rows = np.flatnonzero(day_index(g) >= 19)[::97]
    for i in rows:
        t = g["t"].iloc[i]
        short = _truncated(frame, t.to_pydatetime())
        sg = g[g["t"] <= t]
        again = volatility_features(short, sg)
        for name in VOLATILITY_COLUMNS:
            a, b = full[name].iloc[i], again.loc[g.index[i], name]
            assert (pd.isna(a) and pd.isna(b)) or a == pytest.approx(b), (t, name, a, b)


def test_volatility_columns_are_features():
    from algo_research.events import FEATURE_NAMES
    from algo_research.features.volatility import VOLATILITY_COLUMNS

    assert set(VOLATILITY_COLUMNS) <= FEATURE_NAMES
    for name, doc in VOLATILITY_COLUMNS.items():
        assert doc.definition and doc.unit, name
