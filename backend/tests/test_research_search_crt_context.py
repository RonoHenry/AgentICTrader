"""
Tests for algo_research/search_crt_context.py — H-O's context of a CRT: the pool C2 took, the gap it reached into,
the H4 trend (docs/research/SEARCH_2018_2024.md).

Synthetic M15 bars only: nothing here reads the snapshot.
"""
from __future__ import annotations

import pandas as pd

from algo_research.search_crt_context import Context

T0 = pd.Timestamp("2022-03-01 22:00", tz="UTC")             # 17:00 New York: a trading day opens


def bars(rows, start=T0):
    """M15 bars from (high, low, close) tuples, one every 15 minutes."""
    return pd.DataFrame([{"time": start + pd.Timedelta(minutes=15 * i), "open": c, "high": h, "low": l, "close": c}
                         for i, (h, l, c) in enumerate(rows)])


def ns(t):
    return int(pd.Timestamp(t).value)


def test_the_previous_days_high_is_taken_by_the_first_bar_through_it():
    day1 = [(105, 100, 102)] + [(103, 100, 101)] * 95                # 96 bars: one trading day, high 105
    day2 = [(104, 101, 102)] * 10 + [(106, 101, 102), (107, 101, 102)] + [(104, 101, 102)] * 10
    m15 = bars(day1 + day2)
    ctx = Context(m15)
    first = m15["time"].iloc[96 + 10]
    assert ("PDH" in [n for k, n in ctx.taken.get(ns(first), []) if k > 0])
    assert "PDH" not in [n for _, n in ctx.taken.get(ns(first + pd.Timedelta(minutes=15)), [])]   # taken once
    tag = ctx.tag(ns(first + pd.Timedelta(minutes=15)), -1, 106, 101, 102)
    assert "PDH" in tag["pools"]


def test_a_gap_counts_while_unfilled_and_when_c2_reaches_into_it():
    # H1 candles: 108-110, then a drop, then 100-103: a bearish H1 gap from 103 (near) to 108 (far).
    # The last hours tag 103.6 (into the gap, not through it) and leave no second gap below.
    hours = [(110, 108, 109)] * 4 + [(108, 103.5, 104)] * 4 + [(103, 100, 101)] * 4 + [(103.6, 99, 100)] * 8
    m15 = bars(hours, start=pd.Timestamp("2022-03-02 00:00", tz="UTC"))
    ctx = Context(m15)
    t2 = ns(m15["time"].iloc[-1] + pd.Timedelta(minutes=15))
    assert ctx.arrays_at(t2, -1, c2_high=104.0, c2_low=100.0, c2_close=101.0) == ["H1 FVG"]
    assert ctx.arrays_at(t2, -1, c2_high=102.5, c2_low=100.0, c2_close=101.0) == []     # short of the near edge
    assert ctx.arrays_at(t2, -1, c2_high=109.0, c2_low=100.0, c2_close=108.5) == []     # closed through it
    assert ctx.arrays_at(t2, 1, c2_high=104.0, c2_low=100.0, c2_close=101.0) == []      # a long needs a bullish gap


def test_the_h4_trend_is_the_side_of_the_last_break():
    def h4(h, l, c):
        return [(h, l, c)] * 16                                    # sixteen M15 bars to an H4 candle
    rows = h4(110, 105, 108) + h4(108, 100, 102) + h4(109, 103, 107) + h4(107, 98, 99) + h4(100, 96, 97)
    m15 = bars(rows, start=pd.Timestamp("2022-03-02 00:00", tz="UTC"))
    ctx = Context(m15)
    # H4 #2 (low 100) is a swing low once #3 closes; #4 closes at 99, below it: down.
    after_break = ns(pd.Timestamp("2022-03-02 16:00", tz="UTC"))
    assert ctx.trend_at(after_break) == -1
    assert ctx.trend_at(ns(pd.Timestamp("2022-03-02 12:00", tz="UTC"))) == 0            # no break yet
