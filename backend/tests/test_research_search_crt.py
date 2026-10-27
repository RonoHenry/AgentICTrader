"""
Tests for algo_research/search_crt.py — the trader's M15 CRT entered at market on M1, managed with the partial, H-N
(docs/research/SEARCH_2018_2024.md).

Synthetic bars only: nothing here reads the snapshot. Hand-made M15 bars check which C2 is a CRT; hand-made M1 paths
check the entry, the stop, the targets, the partial and break-even, the day's close and the mirror's risk.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algo_research.search_crt import _Path, crt_signals, race, trades

T0 = pd.Timestamp("2022-03-01 14:00", tz="UTC")            # 09:00 New York


def m15(rows):
    return pd.DataFrame([{"time": T0 + pd.Timedelta(minutes=15 * i), "open": o, "high": h, "low": l, "close": c}
                         for i, (o, h, l, c) in enumerate(rows)])


def m1(prices, spread=0.0, start=T0):
    """Bars from (open, high, low, close) tuples, one a minute."""
    return pd.DataFrame([{"time": start + pd.Timedelta(minutes=i), "open": o, "high": h, "low": l, "close": c,
                          "spread": spread} for i, (o, h, l, c) in enumerate(prices)])


def test_a_crt_sweeps_one_side_and_closes_back_inside():
    bars = m15([(100, 102, 98, 101),        # C1
                (101, 103, 99, 101.5),      # sweeps the high, closes inside: a short
                (101, 101.2, 97, 100),      # sweeps C2's low, closes inside: a long
                (100, 104, 96, 100),        # takes both sides: none
                (100, 105, 99, 104.5)])     # closes beyond the high: none
    s = crt_signals(bars)
    assert list(zip(s["c3"], s["side"])) == [(T0 + pd.Timedelta(minutes=30), -1), (T0 + pd.Timedelta(minutes=45), 1)]
    assert (s["c2_high"].iloc[0], s["c2_low"].iloc[1]) == (103, 97)


def test_a_long_reaches_3r_and_the_stop_wins_a_bar_that_does_both():
    # Enter at 100 (no spread), stop 99: 1R = 1. Bar 2 reaches 103 (3R).
    path = _Path(m1([(100, 100.5, 99.5, 100), (100, 101, 99.8, 100.8), (101, 103.2, 100.5, 103)]))
    r = race(path, 1, 0, 99.0)
    assert r["net_3"] == pytest.approx(3.0) and r["reached_3r"]
    both = _Path(m1([(100, 100.5, 99.5, 100), (100, 103.5, 98.9, 100)]))   # 3R and the stop on one bar
    assert race(both, 1, 0, 99.0)["net_3"] == pytest.approx(-1.0)


def test_the_partial_then_break_even_or_the_target():
    # A third off at 103, then back to the fill: 1/3 x 3R + 2/3 x 0.
    back = _Path(m1([(100, 100.5, 99.5, 100), (101, 103.1, 100.5, 102), (102, 102.5, 99.9, 100)]))
    r = race(back, 1, 0, 99.0)
    assert r["net_4"] == pytest.approx(1.0) and r["net_5"] == pytest.approx(1.0)
    # Or on to 5R: 1/3 x 3 + 2/3 x 5.
    on = _Path(m1([(100, 100.5, 99.5, 100), (101, 103.1, 100.5, 102), (102, 105.2, 101, 105)]))
    assert race(on, 1, 0, 99.0)["net_5"] == pytest.approx(1 / 3 * 3 + 2 / 3 * 5)
    assert race(on, 1, 0, 99.0)["net_4"] == pytest.approx(1 / 3 * 3 + 2 / 3 * 4)


def test_a_short_pays_the_spread_and_stops_on_the_bid_through_the_high():
    # Sell at the bid 100 with a spread of 0.1; C2's high 101, so the stop exits at the ask 101.1: 1R = 1.1.
    path = _Path(m1([(100, 100.5, 99.8, 100), (100, 101.05, 99.9, 101)], spread=0.1))
    r = race(path, -1, 0, 101.0)
    assert r["risk"] == pytest.approx(1.1) and r["net_3"] == pytest.approx(-1.0)   # the bid at 101.05 took 101
    target = _Path(m1([(100, 100.5, 99.8, 100), (99, 99.2, 96.6, 96.8)], spread=0.1))
    assert race(target, -1, 0, 101.0)["net_3"] == pytest.approx(3.0)              # the ask at 96.7 reached 96.7


def test_whats_open_exits_at_the_trading_days_close():
    # 16:57-16:59 New York (20:57 UTC in March): the day ends at the 16:59 bar's close.
    late = m1([(100, 100.2, 99.8, 100), (100, 100.6, 99.9, 100.5), (100.5, 100.6, 100.4, 100.5),
               (100.5, 102, 100.4, 101.8)], start=pd.Timestamp("2022-03-01 21:57", tz="UTC"))
    r = race(_Path(late), 1, 0, 99.0)
    assert r["net_3"] == pytest.approx(0.5)            # 100.5 at 16:59; the 17:00 bar is the next day


def test_skips_tight_risk_and_the_rollover():
    assert race(_Path(m1([(100, 100.1, 99.95, 100)] * 3, spread=0.05)), 1, 0, 99.95) is None   # risk 0.1 = 2 spreads
    bars = m15([(100, 102, 98, 101), (101, 103, 99, 101.5)])
    rollover = bars.assign(time=bars["time"] + pd.Timedelta(hours=6, minutes=30))   # C3 at 16:00 New York
    path = m1([(101, 101.5, 100, 101)] * 60, start=rollover["time"].iloc[1] + pd.Timedelta(minutes=15))
    assert trades(rollover, path, "EURUSD").empty


def test_the_mirror_takes_the_other_side_at_the_same_risk():
    bars = m15([(100, 102, 98, 101), (101, 103, 99, 101.5)])                       # a short at C3, stop 103
    path = m1([(101.5, 101.6, 101.4, 101.5)] + [(101.5, 101.7, 101.3, 101.5)] * 30,
              spread=0.1, start=T0 + pd.Timedelta(minutes=30))
    t = trades(bars, path, "EURUSD")
    row = t.iloc[0]
    assert row["side"] == -1 and row["risk"] == pytest.approx(103.1 - 101.5)
    assert np.isfinite(row["mirror_net_3"])
