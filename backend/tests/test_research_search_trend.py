"""
Tests for algo_research/search_trend.py — H-R, setups with the displacement trend
(docs/research/SEARCH_2018_2024.md). Synthetic candles only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_trend import trend_at, trend_breaks


def bars(rows):
    """Closed candles (high, low, close), each closing at t = 1, 2, 3 ..."""
    return pd.DataFrame([{"high": h, "low": l, "close": c, "t_close": k + 1} for k, (h, l, c) in enumerate(rows)])


SWING = [(10.0, 9.0, 9.5), (11.0, 9.5, 10.5), (10.5, 9.6, 9.8)]      # a swing high at 11, known at the third close


def test_a_close_through_a_swing_high_that_leaves_a_gap_turns_the_trend_up():
    up = bars(SWING + [(11.6, 10.4, 11.5), (12.5, 11.2, 12.4)])      # closes above 11; low 11.2 > 10.5: a gap
    b = trend_breaks(up)
    assert list(zip(b["known"], b["side"])) == [(5, 1)]             # known at the gap's third close
    assert trend_at(b, np.array([4, 5, 9])).tolist() == [0, 1, 1]


def test_a_close_through_without_a_gap_is_a_failure_to_displace():
    flat = bars(SWING + [(11.4, 10.0, 11.2), (11.3, 10.2, 10.6)])    # above 11, but no low above 10.5 / 11.4
    assert trend_breaks(flat).empty
    plain = trend_breaks(flat, displacement=False)
    assert list(zip(plain["known"], plain["side"])) == [(4, 1)]      # every close through counts without the gap


def test_a_bearish_displacement_break_turns_it_down():
    down = bars([(10.5, 9.5, 10.0), (10.0, 9.0, 9.2), (10.2, 9.4, 9.9),  # a swing low at 9, known at the third close
                 (9.6, 8.4, 8.5), (8.8, 7.5, 7.6)])                   # closes below 9; high 8.8 < 9.4: a gap
    b = trend_breaks(down)
    assert list(zip(b["known"], b["side"])) == [(5, -1)]
    assert trend_at(pd.DataFrame(columns=["known", "side"]), np.array([5])).tolist() == [0]
