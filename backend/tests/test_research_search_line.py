"""
Tests for algo_research/search_line.py — H-T, the line chart's trend (docs/research/SEARCH_2018_2024.md).
Synthetic closes only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_line import line_breaks, line_structure
from algo_research.search_trend import trend_at


def closes(values):
    """Closed candles whose wicks are far from the closes: only the closes may matter. Candle k closes at t = k + 1."""
    return pd.DataFrame([{"high": c + 5, "low": c - 5, "close": c, "t_close": k + 1} for k, c in enumerate(values)])


def test_a_close_above_the_last_closing_swing_high_turns_the_line_up():
    b = line_breaks(closes([10, 12, 11, 11.5, 12.5]))       # the closing swing high 12, known at 11; broken by 12.5
    assert list(zip(b["known"], b["side"])) == [(5, 1)]
    assert trend_at(b, np.array([4, 5])).tolist() == [0, 1]


def test_wicks_never_make_or_break_a_swing():
    b = line_breaks(closes([10, 12, 11, 11.9, 11.95]))      # wicks reach 16.95, but no close above 12
    assert b.empty


def test_a_close_below_the_last_closing_swing_low_turns_it_down_and_a_swing_counts_once():
    b = line_breaks(closes([12, 10, 11, 9.5, 9.0]))         # the closing swing low 10, known at 11; broken by 9.5
    assert list(zip(b["known"], b["side"])) == [(4, -1)]


def test_the_structure_needs_both_highs_and_lows_rising():
    up = line_structure(closes([10, 12, 11, 13, 12, 14, 13]))   # highs 12, 13; lows 11, 12: up from the second low
    assert up["side"].iloc[-1] == 1
    mixed = line_structure(closes([10, 12, 11, 13, 10, 14, 9]))  # highs rise, lows fall: none
    assert mixed["side"].iloc[-1] == 0
