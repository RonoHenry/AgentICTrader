"""
Tests for algo_research/sweep_m1.py — the M1 sweep model without a bias at 2R (the Noculus "Sweep M1" layer).

Synthetic M1 only: nothing here reads the snapshot. A flat market at 100 with one M5 swing low at 99 (minutes 5-9),
swept at minute 20 by a down-close run that opened at 100, checks the pool, the CISD, the 20-minute window, the
entry, the stop, the 2R exit, the mirror, the short side and the 16:00-18:00 New York gap.
"""
from __future__ import annotations

import pandas as pd
import pytest

from algo_research.sweep_m1 import TARGET, session_trades, signals

T0 = pd.Timestamp("2022-03-01 14:00", tz="UTC")            # 09:00 New York


def m1(overrides: dict, n: int = 40, spread: float = 0.0, start=T0, flip: bool = False) -> pd.DataFrame:
    """``n`` flat bars at 100, with (open, high, low, close) overrides by minute; ``flip`` mirrors them around 100."""
    rows = []
    for i in range(n):
        o, h, l, c = overrides.get(i, (100.0, 100.0, 100.0, 100.0))
        if flip:
            o, h, l, c = 200 - o, 200 - l, 200 - h, 200 - c
        rows.append({"time": start + pd.Timedelta(minutes=i), "open": o, "high": h, "low": l, "close": c,
                     "spread": spread})
    return pd.DataFrame(rows)


SWING = {7: (100, 100, 99.0, 100)}                         # M5 #1's low: a swing once M5 #2 closes (minute 15)
RUN = {19: (100, 100, 99.7, 99.7), 20: (99.7, 99.7, 98.8, 98.9)}   # the down-closes into the sweep, opened at 100
LONG = {**SWING, **RUN, 21: (98.9, 99.5, 98.85, 99.4), 22: (99.4, 100.2, 99.3, 100.1),   # the CISD: 100.1 > 100
        23: (100.1, 100.2, 100.0, 100.1), 24: (100.1, 102.8, 100.0, 102.5)}               # 2R = 102.7


def test_a_sweep_of_the_m5_swing_then_a_close_through_the_runs_open_is_a_long():
    [s] = [x for x in signals(m1(LONG)) if x["side"] > 0]
    assert (s["sweep"], s["extreme_i"], s["cisd"], s["entry"]) == (20, 20, 22, 23)
    assert s["extreme"] == 98.8 and s["level"] == 100.0
    assert s["pools"] == [(99.0, int((T0 + pd.Timedelta(minutes=5)).value))]


def test_the_trade_enters_at_the_next_open_stops_at_the_extreme_and_takes_2r():
    [tr] = [x for x in session_trades(m1(LONG)) if x["side"] > 0]
    assert tr["entry"] == T0 + pd.Timedelta(minutes=23)
    assert (tr["fill"], tr["stop"]) == pytest.approx((100.1, 98.8))
    assert tr["net"] == pytest.approx(TARGET) and [leg["kind"] for leg in tr["legs"]] == ["target"]
    assert tr["legs"][0]["price"] == pytest.approx(100.1 + 2 * 1.3)
    assert tr["mirror"] == pytest.approx(-1.0)              # the short at 100.1 with a 1.3 stop: 102.8 took it


@pytest.mark.parametrize("minute, fires", [(40, True), (41, False)])
def test_the_cisd_must_come_within_20_minutes_of_the_extreme(minute, fires):
    bars = {**SWING, **RUN, 21: (98.9, 99.5, 98.85, 99.4), minute: (99.9, 100.6, 99.8, 100.5)}
    longs = [x for x in signals(m1(bars, n=50)) if x["side"] > 0]
    assert [x["cisd"] for x in longs] == ([minute] if fires else [])


def test_a_new_extreme_restarts_the_window_and_moves_the_stop():
    held = {i: (99.0, 99.0, 99.0, 99.0) for i in range(36, 50)}                          # under 99.4, above 98.5
    bars = {**SWING, **RUN, 21: (98.9, 99.5, 98.85, 99.4), 35: (99.4, 99.4, 98.5, 98.6),    # 15 minutes on: lower
            **held, 50: (99.0, 100.6, 98.9, 100.5)}                                       # 30 after the first
    [s] = [x for x in signals(m1(bars, n=60)) if x["side"] > 0]
    assert (s["extreme_i"], s["extreme"], s["cisd"]) == (35, 98.5, 50)
    assert s["level"] == 99.4                                # the run into 98.5 is that bar alone
    assert [px for px, _ in s["pools"]] == [99.0, 98.8]      # and it took M5 #4's swing (known at minute 30)


def test_the_short_is_the_mirror():
    [tr] = [x for x in session_trades(m1(LONG, flip=True)) if x["side"] < 0]
    assert (tr["fill"], tr["stop"]) == pytest.approx((99.9, 101.2))
    assert tr["net"] == pytest.approx(TARGET) and tr["pools"][0]["price"] == 101.0


def test_no_entry_from_16_to_18_new_york():
    # 20:30 UTC is 15:30 New York in March: the entry opens at 15:53; ten minutes later it would open at 16:03.
    assert [x["side"] for x in session_trades(m1(LONG, start=pd.Timestamp("2022-03-01 20:30", tz="UTC")))] == [1]
    assert session_trades(m1(LONG, start=pd.Timestamp("2022-03-01 20:40", tz="UTC"))) == []


def test_a_risk_under_two_spreads_is_skipped():
    # The buy pays the spread s, so the risk is 1.3 + s: taken while that is at least 2s.
    assert [x["side"] for x in session_trades(m1(LONG, spread=1.2)) if x["side"] > 0] == [1]   # 2.5 >= 2.4
    assert [x for x in session_trades(m1(LONG, spread=1.4)) if x["side"] > 0] == []            # 2.7 < 2.8
