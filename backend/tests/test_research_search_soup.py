"""
Tests for algo_research/search_soup.py — H-U, the turtle soup after displacement
(docs/research/SEARCH_2018_2024.md). Synthetic bars only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_soup import market_rows, soup, swings, weekly

START = pd.Timestamp("2022-03-07", tz="UTC")
DAY = 86_400 * 10**9

# A swing high at 105 (bar 2), a swing low at 97 (bar 6); C0 (bar 9) raids 105 and closes back below it, C1 (bar 10)
# closes below C0's low, C2 (bar 11) takes C1's low and the pool at 97 and closes back inside, low in the range;
# C3 (bar 12) reaches C1's equilibrium (101.85) without going below C2's low.
OHLC = [(100, 101, 99, 100.5), (100.5, 102, 100, 101.5), (101.5, 105, 101, 104), (104, 104.5, 102, 103),
        (103, 104, 101.5, 102), (102, 103, 100, 101), (101, 101.5, 97, 98), (98, 102, 97.5, 101.5),
        (101.5, 104.5, 101, 104), (104, 105.5, 103, 104.8), (104.8, 105.2, 98.5, 99), (99, 100, 96.5, 98.7),
        (98.7, 102.5, 98, 102)]


def bars(ohlc=OHLC):
    b = pd.DataFrame(ohlc, columns=["open", "high", "low", "close"], dtype=float)
    t = START.value + DAY * np.arange(len(b))
    return b.assign(i0=np.arange(len(b)), i1=np.arange(len(b)), t_open=t, t_close=t + DAY,
                    date=pd.date_range("2022-03-07", periods=len(b), freq="D"))


def edit(k, **kw):
    rows = [list(r) for r in OHLC]
    for i, name in enumerate(("open", "high", "low", "close")):
        if name in kw:
            rows[k][i] = kw[name]
    return bars([tuple(r) for r in rows])


def test_a_swing_is_known_two_candles_later_and_taken_by_the_first_candle_beyond_it():
    b = bars()
    s = swings(b, "high")
    i = list(s["level"]).index(105)
    assert s["known"][i] == b["t_close"][4]                                   # the second candle after bar 2
    assert s["taken"][i] == b["t_open"][9]                                    # C0's high 105.5
    lows = swings(b, "low")
    j = list(lows["level"]).index(97)
    assert lows["known"][j] == b["t_close"][8] and lows["taken"][j] == b["t_open"][11]


def test_the_traders_soup_is_read_with_every_condition():
    r = soup(bars(), bars())
    assert list(r["k"]) == [11]
    row = r.iloc[0]
    assert row["raid"] and row["pool"] and row["discount"] and row["engulf"]
    assert row["eq"] == (105.2 + 98.5) / 2 and row["c1_high"] == 105.2


def test_each_condition_fails_on_its_own():
    def read(b):
        return soup(b, b)

    assert not read(edit(9, close=105.2)).iloc[0]["raid"]                     # C0 closed above the swing high
    assert not read(edit(11, low=97.2)).iloc[0]["pool"]                       # C2 stops short of the pool at 97
    assert not read(edit(11, close=99.9)).iloc[0]["discount"]                 # C2 closes too high in the range
    assert read(edit(10, close=103.5)).empty                                  # C1 didn't close below C0's low
    assert read(edit(11, close=98.2)).empty                                   # C2 closed below C1's low: displaced
    assert read(edit(11, high=105.4)).empty                                   # C2 took C1's high too


def test_a_call_races_the_equilibrium_against_c2s_low_and_the_short_is_its_mirror():
    b = bars()
    hi, lo = b["high"].to_numpy(float), b["low"].to_numpy(float)
    t = market_rows(b, b, hi, lo, "X", "D1", START, START + pd.Timedelta(days=30), 0.1)
    long_ = t[t["side"] > 0].iloc[0]
    assert long_["outcome"] == "held" and bool(long_["within_c3"])
    assert np.isclose(long_["geo"], (98.7 - 96.5) / (101.85 - 96.5))
    assert np.isclose(long_["r_gross"], (1 - long_["geo"]) / long_["geo"])
    assert long_["far_outcome"] == "open"                                     # C1's high 105.2 never comes
    mirror = bars([(200 - o, 200 - l, 200 - h, 200 - c) for o, h, l, c in OHLC])
    m = market_rows(mirror, mirror, mirror["high"].to_numpy(float), mirror["low"].to_numpy(float), "X", "D1",
                    START, START + pd.Timedelta(days=30), 0.1)
    short = m[m["side"] < 0].iloc[0]
    assert short["outcome"] == "held" and np.isclose(short["geo"], long_["geo"])
    assert np.isclose(short["draw"], 200 - 101.85) and np.isclose(short["stop"], 200 - 96.5)


def test_weeks_are_built_from_the_days_with_the_days_as_their_path():
    d1 = pd.DataFrame({"time": pd.date_range("2022-03-07", periods=10, freq="B", tz="UTC"),
                       "open": np.arange(10.0), "high": np.arange(10.0) + 1, "low": np.arange(10.0) - 1,
                       "close": np.arange(10.0) + 0.5})
    weeks, days = weekly(d1)
    assert len(weeks) == 2 and list(weeks["i0"]) == [0, 5] and list(weeks["i1"]) == [4, 9]
    assert weeks["high"][0] == 5 and weeks["low"][1] == 4 and weeks["close"][1] == 9.5
    assert weeks["t_close"][0] == days["t_open"][4] + DAY
