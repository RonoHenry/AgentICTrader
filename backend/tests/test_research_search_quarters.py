"""
Tests for algo_research/search_quarters.py — H-P, the quarterly theory's false move traded into Q3
(docs/research/SEARCH_2018_2024.md). Synthetic M1 bars only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_quarters import false_moves, quarter_sets

OPEN = pd.Timestamp("2022-03-01 18:00", tz="America/New_York").tz_convert("UTC")    # the day's Q1 opens


def day_of(prices_by_quarter):
    """A day of M1: 360 bars per day quarter, each quarter's bars at one (high, low, close)."""
    rows = []
    for q, (h, l, c) in enumerate(prices_by_quarter):
        for k in range(360):
            rows.append({"time": OPEN + pd.Timedelta(minutes=360 * q + k), "open": c, "high": h, "low": l, "close": c})
    return pd.DataFrame(rows)


def test_day_quarters_are_six_hours_from_18_00_new_york():
    m1 = day_of([(101, 99, 100)] * 4)
    sets = quarter_sets(m1, "day")
    assert list(sets["quarter"]) == [0, 1, 2, 3] and sets["i"].tolist() == [0, 360, 720, 1080]
    sessions = quarter_sets(m1, "session")
    assert len(sessions) == 16 and sessions["i"].iloc[1] == 90                      # four 90-minute quarters each


def test_a_false_move_up_is_sold_at_q3s_open():
    m1 = day_of([(101, 99, 100), (102, 99.5, 100.5), (101, 98, 99), (100, 97, 98)])   # Q2 takes Q1's high only
    f = false_moves(quarter_sets(m1, "day"))
    assert len(f) == 1 and f["side"].iloc[0] == -1 and f["e"].iloc[0] == 720 and f["q2_high"].iloc[0] == 102
    both = day_of([(101, 99, 100), (102, 98, 100), (101, 98, 99), (100, 97, 98)])     # takes both sides: none
    assert false_moves(quarter_sets(both, "day")).empty
    beyond = day_of([(101, 99, 100), (102, 99.5, 101.5), (103, 101, 102), (104, 102, 103)])   # closes above: none
    assert false_moves(quarter_sets(beyond, "day")).empty
    assert np.isfinite(f["q2_close"].iloc[0])
