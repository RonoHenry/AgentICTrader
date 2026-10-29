"""
Tests for algo_research/search_bias.py — H-Q, the two-candle read on every frame
(docs/research/SEARCH_2018_2024.md). Synthetic M1 bars only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_bias import calls, drop_rollover, first_touch, frames, gaps, market_calls

DAY_OPEN = pd.Timestamp("2022-03-07 17:00", tz="America/New_York").tz_convert("UTC")   # Monday 7 March 2022


def hours(bars):
    """M1 bars, 60 per hour from DAY_OPEN, each hour's bars at one (high, low, close)."""
    rows = []
    for k, (h, l, c) in enumerate(bars):
        for m in range(60):
            rows.append({"time": DAY_OPEN + pd.Timedelta(minutes=60 * k + m), "open": c, "high": h, "low": l,
                         "close": c, "spread": 0.01})
    return pd.DataFrame(rows)


def two(c1, c2):
    return pd.DataFrame([dict(zip(("high", "low", "close"), c)) for c in (c1, c2)])


def test_the_read_names_each_case_of_the_candle_guide():
    cases = {
        "expansion higher": (two((10, 8, 9), (11, 8.5, 10.5)), 1, "expansion"),
        "expansion lower": (two((10, 8, 9), (9.5, 7, 7.5)), -1, "expansion"),
        "aim for the range lows": (two((10, 8, 9), (10.5, 8.5, 9.8)), -1, "reversal"),
        "aim for the range highs": (two((10, 8, 9), (9.5, 7.5, 8.2)), 1, "reversal"),
        "seek and destroy": (two((10, 8, 9), (10.5, 7.5, 9)), 0, "seek and destroy"),
        "consolidation": (two((10, 8, 9), (9.5, 8.5, 9)), 0, "consolidation"),
        "outside, closed above": (two((10, 8, 9), (11, 7.5, 10.5)), 1, "expansion"),
    }
    for name, (bars, side, case) in cases.items():
        r = calls(bars).iloc[1]
        assert (r["side"], r["case"]) == (side, case), name


def test_frames_keep_new_york_time_and_leave_out_the_rollover():
    m1 = hours([(10, 9, 9.5)] * 48)                                         # two trading days from Monday 17:00
    f = frames(drop_rollover(m1))
    starts = f["H4"]["start"].dt.hour.tolist()[:6]
    assert starts == [0, 4, 8, 12, 16, 20]                                  # shifted 7 h: 17, 21, 01, 05, 09, 13 NY
    assert len(f["D1"]) == 2 and f["D1"]["date"].dt.day.tolist() == [8, 9]  # Monday 17:00 opens Tuesday's day
    assert len(f["W1"]) == 1
    clock = m1["time"].dt.tz_convert("America/New_York").dt.strftime("%H:%M")
    dropped = set(clock) - set(drop_rollover(m1)["time"].dt.tz_convert("America/New_York").dt.strftime("%H:%M"))
    assert dropped == {f"16:{m}" for m in range(55, 60)} | {f"17:0{m}" for m in range(5)}


def test_the_race_takes_the_first_level_reached():
    hi = np.array([5, 5, 6, 7, 5], float)
    lo = np.array([4, 4, 4, 3, 3], float)
    assert first_touch(hi, lo, 0, 6, 3) == (2, 3)                           # the high first, then the low
    assert first_touch(hi, lo, 3, 7, 3) == (3, 3)                           # one bar reaches both
    assert first_touch(hi, lo, 0, 9, 1) == (-1, -1)                         # the path ends first


def test_a_gap_is_from_closed_candles_and_filled_by_a_close_beyond_its_far_edge():
    bars = pd.DataFrame({"high": [10, 12, 14, 13, 12], "low": [9, 10.5, 11, 10.5, 9.5],
                         "close": [9.5, 11.5, 13, 11, 9.8], "t_close": [1, 2, 3, 4, 5]})
    g = gaps(bars)
    first = g.iloc[0]                                                       # bar 2's low 11 above bar 0's high 10
    assert (first["side"], first["near"], first["far"], first["formed"]) == (1, 11, 10, 3)
    assert first["filled"] == 5                                             # bar 4 closes at 9.8, below 10


def test_a_call_scores_the_draw_against_geometry_and_flags_a_gap():
    # H1 candles: C1 9-10, C2 sweeps C1's high to 10.5 and closes back at 9.8 (bearish, the low 9.2 is the draw);
    # the next hour trades down to 9.1.
    m1 = hours([(10, 9, 9.5), (10.5, 9.2, 9.8), (9.9, 9.1, 9.3)] + [(9.4, 9.2, 9.3)] * 3)
    t = market_calls(drop_rollover(m1), "X", DAY_OPEN, DAY_OPEN + pd.Timedelta(days=1), 0.01)
    c = t[(t["frame"] == "H1") & (t["close_at"] == DAY_OPEN + pd.Timedelta(hours=2))].iloc[0]
    assert (c["side"], c["case"], c["outcome"]) == (-1, "reversal", "held")
    assert c["geo"] == np.float64((10.5 - 9.8) / (10.5 - 9.2))
    assert bool(c["held_next"]) and not bool(c["at_gap"])
    assert c["far_outcome"] == "open"                                       # C1's low 9 is never reached
