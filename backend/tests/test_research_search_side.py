"""
Tests for algo_research/search_side.py — H-V, the side from the frames above, and manipulation against it
(docs/research/SEARCH_2018_2024.md, with its amendment). Synthetic bars only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_side import MODES, classify, market_rows, sides
from algo_research.search_soup import weekly

# Four weeks of days. Week 2 takes week 1's low (98 < 99), not its high, and closes back inside: a W1 turtle soup
# buy (draw 102, protected 98). Day 11 reaches 102 (delivered) and makes 103. Day 13 is a D1 turtle soup sell,
# which flips W1 short: protected 103 (the high since delivery), draw 98 (where the long began). Day 16 reaches 98
# (delivered); day 17 is a D1 turtle soup buy, which flips W1 long again (protected 97, draw 103).
DAYS = [(100, 101, 99.5, 100.5), (100.5, 101, 99, 100), (100, 102, 99.8, 101.5), (101.5, 101.8, 100.5, 101),
        (101, 101.5, 100.5, 101),
        (101, 101.2, 99.5, 100), (100, 100.2, 98, 98.6), (98.6, 100, 98.4, 99.8), (99.8, 100.8, 99.5, 100.6),
        (100.6, 101, 100.2, 100.5),
        (100.5, 101.5, 100.3, 101.2), (101.2, 103, 101, 102.6), (102.6, 102.8, 101.8, 102.2),
        (102.2, 102.9, 101.9, 102.0), (102, 102.1, 101.3, 101.5),
        (101.5, 101.6, 99, 99.2), (99.2, 99.5, 97.5, 97.8), (97.8, 98.5, 97, 98), (98, 98.4, 97.4, 97.9),
        (97.9, 98.2, 97.2, 97.6)]


def build():
    d1 = pd.DataFrame(DAYS, columns=["open", "high", "low", "close"], dtype=float)
    d1.insert(0, "time", pd.date_range("2022-03-07", periods=len(DAYS), freq="B", tz="UTC"))
    weeks, days = weekly(d1)
    hi, lo, known = days["high"].to_numpy(float), days["low"].to_numpy(float), days["t_close"].to_numpy(np.int64)
    return weeks, days, hi, lo, known


def test_a_delivered_side_flips_on_the_frame_below_with_the_high_since_delivery_protected():
    weeks, days, hi, lo, known = build()
    s = sides(weeks, hi, lo, known, days)
    tc = days["t_close"].to_numpy(np.int64)
    assert list(s["kind"]) == ["set", "flip", "flip"] and list(s["side"]) == [1, -1, 1]
    assert s["start"][0] == weeks["t_close"][1] and s["end"][0] == tc[11]         # delivered on day 11
    assert s["start"][1] == tc[13] and s["end"][1] == tc[16]                      # flipped by day 13, delivered day 16
    assert s["start"][2] == tc[17] and s["end"][2] == np.iinfo(np.int64).max     # flipped back by day 17, live


def test_the_modes_without_the_flip_keep_only_the_turtle_soup():
    weeks, days, hi, lo, known = build()
    for mode in ("noflip", "first"):
        s = sides(weeks, hi, lo, known, days, mode)
        assert list(s["kind"]) == ["set"] and s["end"][0] == days["t_close"][11]
    r = sides(weeks, hi, lo, known, days, "replace")
    assert len(r) == 1 and r["end"][0] == np.iinfo(np.int64).max                 # no delivery in this mode


def test_the_highest_live_frame_above_decides():
    weeks, days, hi, lo, known = build()
    w1 = sides(weeks, hi, lo, known, days)
    tc = days["t_close"].to_numpy(np.int64)
    assert classify(1, int(tc[14]), {"W1": w1}) == ("against", "W1")              # W1 short, a long against it
    assert classify(-1, int(tc[14]), {"W1": w1}) == ("with", "W1")
    assert classify(1, int(tc[3]), {"W1": w1}) == ("none", "")                    # before any side
    short_d1 = pd.DataFrame({"start": [int(tc[0])], "end": [np.iinfo(np.int64).max], "side": [-1], "kind": ["set"]})
    assert classify(1, int(tc[9]) + 1, {"D1": short_d1, "W1": w1}) == ("with", "W1")   # W1 outranks D1


def test_the_turtle_soup_that_flips_the_frame_above_reads_with_it():
    weeks, days, hi, lo, known = build()
    tables = {mode: {"D1": sides(days, hi, lo, known, None, mode), "W1": sides(weeks, hi, lo, known, days, mode)}
              for mode in MODES}
    t = market_rows(days, tables, hi, lo, "X", "D1", "2022-03-07", "2022-04-30", 0.01)
    tc = days["t_close"].to_numpy(np.int64)
    at = {int(pd.Timestamp(r).value): r2 for r, r2 in zip(t["close_at"], t.to_dict("records"))}
    sell, buy = at[int(tc[13])], at[int(tc[17])]
    assert (sell["side"], sell["class"], sell["decider"], sell["outcome"]) == (-1, "with", "W1", "held")
    assert (buy["side"], buy["class"], buy["decider"]) == (1, "with", "W1")
    assert sell["class_noflip"] == "none"                                         # without the flip, W1 is waiting
