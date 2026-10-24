"""
Tests for liquidity_engine/context/ipda.py — ICT's IPDA data ranges as objectives (context-engine Requirement 27).

Task 365 (.kiro/specs/context-engine/tasks.md). Seventy flat days (highs 101, lows 99) with one extreme planted in
each lookback: a high of 110 and a low of 90 only in the last 60 days, 107 and 93 in the last 40, 104 and 96 in
the last 20.
Validates: Requirements 27.1-27.3 (.kiro/specs/context-engine/requirements.md)
"""
from __future__ import annotations

from liquidity_engine.context.frame_state import frame_state
from liquidity_engine.context.ipda import ipda_ranges
from liquidity_engine.models import BiasDirection
from tests.test_context_frame_state import DAY, T0, candles

BULL, BEAR = BiasDirection.BULLISH, BiasDirection.BEARISH


def days(n=70, highs=None, lows=None):
    highs = {15: 110, 35: 107, 60: 104, **(highs or {})}
    lows = {12: 90, 40: 93, 55: 96, **(lows or {})}
    return candles([(100, highs.get(i, 101), lows.get(i, 99), 100) for i in range(n)])


def levels(objectives):
    return sorted((x.source, x.price, x.direction, (x.formed_at - T0) // DAY - 1) for x in objectives)


def test_ranges_are_the_20_40_60_day_extremes():
    assert levels(ipda_ranges(days())) == sorted([
        ("IPDA60_HIGH", 110, BULL, 15), ("IPDA40_HIGH", 107, BULL, 35), ("IPDA20_HIGH", 104, BULL, 60),
        ("IPDA60_LOW", 90, BEAR, 12), ("IPDA40_LOW", 93, BEAR, 40), ("IPDA20_LOW", 96, BEAR, 55)])
    assert all(x.kind == "POOL" and x.tf == "D1" for x in ipda_ranges(days()))


def test_a_candle_leading_two_ranges_is_listed_once():
    found = levels(ipda_ranges(days(highs={65: 112})))               # the 20-day high is the 60-day high too
    assert [x for x in found if x[2] == BULL] == [("IPDA60_HIGH", 112, BULL, 65)]


def test_no_range_without_its_candles():
    assert {x[0] for x in levels(ipda_ranges(days(30, highs={15: 101, 25: 104}, lows={12: 99, 22: 96})))} == \
        {"IPDA20_HIGH", "IPDA20_LOW"}
    assert ipda_ranges(days(19)) == []


def test_ranges_feed_the_chain_as_objectives():
    d1 = days()
    s = frame_state(d1, 100.0, levels=ipda_ranges(d1))
    assert ("IPDA20_HIGH", 104) in [(x.source, x.price) for x in s.above]
    assert ("IPDA20_LOW", 96) in [(x.source, x.price) for x in s.below]
    assert s.nearest(BULL).price == 101                               # the previous day's high is nearer still
