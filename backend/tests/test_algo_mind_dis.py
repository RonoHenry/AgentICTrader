"""
Tests for algo_mind/dis.py and algo_research/search_narrative.py — the directional state (context-engine
Requirement 35, task 394) and H-AE.

The worked example is the trader's GBPUSD narrative of October 2026 on the Exness fixture, its H1 bars rebuilt as
daily candles: the long history's D1 and W1 must give reader v0's side. The rest pin the state machine on hand-made
turns, its use of the past only, and H-AE's race and control.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algo_mind.dis import DirectionalState, daily_market, reader_turns, state_at, states
from algo_research.search_narrative import control_share, race
from algo_research.sequence import candles

FIXTURES = Path(__file__).parent / "fixtures" / "research" / "sequence"
DAY = 86_400 * 10**9


def _gbpusd_days() -> pd.DataFrame:
    h1 = pd.read_csv(FIXTURES / "GBPUSDm_H1_2026-01-01_2026-10-30.csv.gz")
    h1["time"] = pd.to_datetime(h1["time"], utc=True)
    d1 = candles(h1, pd.Timedelta(hours=1))["D1"]
    return pd.DataFrame({"date": pd.to_datetime(d1["date"]), "open": d1["open"], "high": d1["high"],
                         "low": d1["low"], "close": d1["close"]})


@pytest.fixture(scope="module")
def gbpusd():
    return _gbpusd_days()


def _ns(day: str) -> int:
    return int(pd.Timestamp(day, tz="UTC").value)


def test_the_daily_history_gives_the_readers_gbpusd_narrative_of_october_2026(gbpusd):
    m = daily_market(gbpusd)
    timeline = states(reader_turns(m), m.hist["D1"])
    s = state_at(timeline, _ns("2026-10-26"), market="GBPUSD")
    assert isinstance(s, DirectionalState)
    assert (s.direction, s.state) == ("BULLISH", "ACTIVE")
    assert s.since == _ns("2026-10-17")                               # the C2 week's close (12-16 Oct)
    assert any("2026 Q2 low" in e for e, _ in s.evidence)
    assert s.draw["name"].startswith("W1 gap 07 Sep-21 Sep")
    assert s.protected == pytest.approx(1.31364, abs=2e-4)
    assert "closes under" in s.invalidation
    assert s.to_json()["side"] == "BULLISH"


def test_the_state_on_a_day_doesnt_change_when_later_bars_are_cut(gbpusd):
    t = _ns("2026-10-20")
    full = daily_market(gbpusd)
    cut = daily_market(gbpusd[gbpusd["date"] < pd.Timestamp("2026-10-20")])
    a = state_at(states(reader_turns(full), full.hist["D1"]), t)
    b = state_at(states(reader_turns(cut), cut.hist["D1"]), t)
    assert (a.side, a.state, a.since, a.protected) == (b.side, b.state, b.since, b.protected)
    assert a.draw == b.draw


def _d1(rows) -> pd.DataFrame:
    """Daily candles from (high, low, close), day i opening at i days."""
    return pd.DataFrame([{"open": c, "high": h, "low": lo, "close": c, "t_open": i * DAY, "t_close": (i + 1) * DAY}
                         for i, (h, lo, c) in enumerate(rows)])


def _turn(t_day: int, side: int, low: float, ce: float) -> dict:
    return {"t": t_day * DAY, "side": side, "low": low, "erl": [("test low", low)], "c1": pd.Timestamp("2000-01-03"),
            "c2": pd.Timestamp("2000-01-10"), "cisd_at": t_day * DAY, "level": low,
            "draw": {"name": "test gap", "near": ce, "far": ce, "ce": ce}}


def test_a_side_is_replaced_on_its_side_ignores_the_other_and_waits_after_its_end():
    flat = [(101, 99, 100)] * 10
    d1 = _d1(flat + [(106, 100, 105)] + flat)                         # day 10 reaches 105
    turns = [_turn(2, 1, 95, 110), _turn(4, 1, 97, 105), _turn(6, -1, 103, 90), _turn(15, -1, 103, 90)]
    timeline = states(turns, d1)
    assert [x.reason for x in timeline] == ["replaced", "delivered", "open"]
    assert timeline[1].ignored and timeline[1].ignored[0]["side"] == -1
    assert state_at(timeline, 3 * DAY).protected == 95
    live = state_at(timeline, 7 * DAY)
    assert (live.side, live.protected, len(live.ignored)) == (1, 97, 1)
    after = state_at(timeline, 12 * DAY)
    assert (after.direction, after.state, after.ended[0]) == ("NONE", "UNDETERMINED", "delivered")
    assert state_at(timeline, 16 * DAY).side == -1
    assert state_at(timeline, 1 * DAY).state == "UNDETERMINED"


def test_a_side_is_invalidated_by_a_close_beyond_its_protected_swing_not_a_wick():
    d1 = _d1([(101, 99, 100)] * 3 + [(101, 94, 100)] + [(101, 93, 94)] + [(101, 99, 100)] * 3)
    timeline = states([_turn(1, 1, 95, 110)], d1)
    assert timeline[0].reason == "invalidated" and timeline[0].end == 5 * DAY


def test_the_race_counts_a_day_that_both_delivers_and_invalidates_as_failed():
    hi = np.array([101, 111, 101.0])
    lo = np.array([99, 90, 99.0])
    cl = np.array([100, 94, 100.0])
    assert race(hi, lo, cl, 0, 1, 110, 95) == ("failed", 1)
    assert race(hi, lo, cl, 0, -1, 90, 105) == ("held", 1)        # the low reaches 90; no close above 105
    assert race(hi[:1], lo[:1], cl[:1], 0, 1, 110, 95) == ("open", -1)


def test_the_control_puts_the_calls_distances_in_each_starts_average_range():
    # two starts with the same path shape, the second twice the size: the same race in average ranges
    hi = np.array([101, 103, 101, 202, 206, 202.0])
    lo = np.array([99, 99, 99, 198, 198, 198.0])
    cl = np.array([100, 102, 100, 200, 204, 200.0])
    share, n = control_share(hi, lo, cl, np.array([1, 4]), np.array([100.0, 200.0]), np.array([1.0, 2.0]),
                             side=1, a=2.5, b=5.0)
    assert (share, n) == (1.0, 2)                                     # +2.5 and +5 reached on both
    share, n = control_share(hi, lo, cl, np.array([4]), np.array([200.0]), np.array([2.0]), side=1, a=3.5, b=5.0)
    assert n == 0                                                     # +7 never reached, no close under 190: open
