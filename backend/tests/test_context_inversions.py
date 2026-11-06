"""
Tests for inverted fair value gaps on arrays (liquidity_engine/context/inversions.py; thesis-engine Requirement 3.5).
"""
from __future__ import annotations

import numpy as np

from liquidity_engine.context.frame_state import Candles
from liquidity_engine.context.inversions import inverted_fvgs
from liquidity_engine.models import BiasDirection


def frame(rows) -> Candles:
    o, h, l, c = (np.array(x, dtype=float) for x in zip(*rows))
    t = np.arange(len(rows), dtype=np.int64) * 10
    return Candles("H1", t, t + 10, o, h, l, c)


def test_a_bullish_gap_closed_through_becomes_a_bearish_inverted_gap_at_that_close():
    rows = [(10, 11, 9.5, 10.8), (10.8, 13, 10.7, 12.9), (12.9, 14, 12, 13.8),   # gap 11-12 above candle one
            (13.8, 14, 12.5, 12.6), (12.6, 12.7, 10.5, 10.6)]                       # closes under 11
    out = inverted_fvgs(frame(rows))
    assert len(out) == 1
    a = out[0]
    assert (a.kind, a.direction, a.low, a.high, a.formed_at) == ("IFVG", BiasDirection.BEARISH, 11.0, 12.0, 50)


def test_the_mirror_and_no_inversion_without_a_close_through():
    rows = [(10, 10.5, 9, 9.2), (9.2, 9.3, 7, 7.1), (7.1, 8, 6, 6.2),               # gap 8-9 under candle one
            (6.2, 9.6, 6.1, 9.4)]                                                     # closes above 9
    out = inverted_fvgs(frame(rows))
    assert [(a.direction, a.low, a.high, a.formed_at) for a in out] == [(BiasDirection.BULLISH, 8.0, 9.0, 40)]
    wick_only = rows[:3] + [(6.2, 9.6, 6.1, 8.5)]                                   # a wick through is not an end
    assert inverted_fvgs(frame(wick_only)) == []


def test_each_inversion_reads_only_candles_up_to_its_close():
    rng = np.random.default_rng(7)
    c = 100 + np.cumsum(rng.normal(0, 1, 300))
    o = np.r_[100.0, c[:-1]]
    h = np.maximum(o, c) + rng.random(300)
    l = np.minimum(o, c) - rng.random(300)
    full = inverted_fvgs(frame(list(zip(o, h, l, c))))
    for n in (50, 120, 233):
        cut = inverted_fvgs(frame(list(zip(o[:n], h[:n], l[:n], c[:n]))))
        assert sorted((a.formed_at, a.low, a.high) for a in cut) == \
            sorted((a.formed_at, a.low, a.high) for a in full if a.formed_at <= n * 10)
