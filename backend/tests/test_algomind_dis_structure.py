"""
Tests for AlgoMindDIS's structure, ranges and premium/discount (algomind-dis Requirements 3, 4; task 400).

Hand-made bars: a rise to a swing high (candle 4), a fall to a swing low (candle 9), a rise through the high (a
break up at candle 15) to a new swing high (16), then a fall through the low (a break down at candle 24).
"""
from __future__ import annotations

import numpy as np
import pytest

from algomind_dis.analyzers.ranges import (displacement_range, position, previous_range, primary, ranges,
                                           swing_range, zone)
from algomind_dis.analyzers.structure import direction, events, swings
from liquidity_engine.context.frame_state import Candles

DAY = 86_400 * 10**9
MID = [10, 11, 12, 13, 14, 13, 12, 11, 10, 9, 10, 11, 12, 13, 14, 15, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7]


def bars(mid, tf="D1", body=0.4, wick=1.0) -> Candles:
    m = np.asarray(mid, float)
    up = np.r_[True, np.diff(m) >= 0]
    o = np.where(up, m - body, m + body)
    c = np.where(up, m + body, m - body)
    t = np.arange(len(m), dtype=np.int64) * DAY
    return Candles(tf, t, t + DAY, o, m + wick, m - wick, c)


def cut(c: Candles, n: int) -> Candles:
    return Candles(c.tf, c.t[:n], c.end[:n], c.o[:n], c.h[:n], c.l[:n], c.c[:n])


def flip(c: Candles) -> Candles:
    return Candles(c.tf, c.t, c.end, -c.o, -c.l, -c.h, -c.c)


def test_swings_are_known_only_from_their_confirming_close():
    c = bars(MID)
    s = swings(c)
    assert [(x.index, x.is_high, x.known_at) for x in s] == [(4, True, c.end[6]), (9, False, c.end[11]),
                                                             (16, True, c.end[18])]
    assert swings(cut(c, 6)) == []                            # candle 4's high is unconfirmed until candle 6 closes


def test_a_bos_and_an_mss_fire_at_their_closes_and_only_there():
    c = bars(MID)
    ev = events("TEST", c)
    assert [(e.kind, e.direction, e.level, e.at) for e in ev] == [
        ("BOS", "BULLISH", 15.0, c.end[15]),                  # the first break, from no structure
        ("MSS", "BEARISH", 8.0, c.end[24])]                   # against the bullish structure
    assert direction(ev, c.end[23]) == "BULLISH" and direction(ev, c.end[24]) == "BEARISH"
    assert direction(ev, c.end[14]) == "NEUTRAL"
    for n in range(1, len(MID) + 1):                          # each close sees the same events as the full frame
        assert events("TEST", cut(c, n)) == tuple(e for e in ev if e.at <= c.end[n - 1])


def test_the_three_ranges_carry_their_origin_and_invalidation():
    c = bars(MID)
    r = swing_range("TEST", c)
    assert (r.kind, r.low, r.high) == ("SWING", 6.0, 17.0)    # anchored on candles 9 and 16, stretched to the fall
    assert r.established_at == c.end[18] and not r.valid and r.invalidated_at == c.end[24]
    assert "close" in r.invalidation
    p = previous_range("TEST", c)
    assert (p.kind, p.low, p.high, p.valid) == ("PREVIOUS", 6.0, 8.0, True)
    assert swing_range("TEST", cut(c, 8)) is None             # no confirmed swing low yet
    flat = [10 + 0.01 * (k % 2) for k in range(21)]
    d = bars(flat + [11, 11.2, 11.1, 10.95, 10.4], body=0.05, wick=0.1)
    d = Candles(d.tf, d.t, d.end, d.o.copy(), d.h.copy(), d.l.copy(), d.c.copy())
    d.o[21], d.c[21], d.h[21], d.l[21] = 10.0, 11.0, 11.05, 9.98      # the displacement: a body of 1.0 against 0.05
    x = displacement_range("TEST", d)
    assert (x.kind, x.low, x.high) == ("DISPLACEMENT", pytest.approx(9.9), pytest.approx(11.3))   # its run's low
    assert x.established_at == d.end[21] and x.valid
    assert {r.kind for r in ranges("TEST", d)} == {"PREVIOUS", "DISPLACEMENT"}   # no swing low: no swing range
    d.o[25], d.h[25], d.l[25], d.c[25] = 9.95, 10.0, 9.8, 9.85  # a small close under its origin ends it
    x = displacement_range("TEST", d)
    assert x.established_at == d.end[21] and not x.valid and x.invalidated_at == d.end[25]


def test_the_zones_bounds():
    got = [zone(p) for p in (0.1, 0.25, 0.449, 0.45, 0.55, 0.551, 0.75, 0.751)]
    assert got == ["DEEP_DISCOUNT", "DISCOUNT", "DISCOUNT", "EQUILIBRIUM", "EQUILIBRIUM", "PREMIUM", "PREMIUM",
                   "DEEP_PREMIUM"]
    r = swing_range("TEST", bars(MID))
    pp = position(r, 6.6)
    assert pp.zone == "DEEP_DISCOUNT" and pp.position == pytest.approx(0.6 / 11) and pp.range_id == r.id


def test_mirrored_bars_give_the_mirrored_reading():
    c = bars(MID)
    ev, mv = events("TEST", c), events("TEST", flip(c))
    assert [(e.kind, e.direction, e.level) for e in mv] == [
        (e.kind, {"BULLISH": "BEARISH", "BEARISH": "BULLISH"}[e.direction], -e.level) for e in ev]
    r, m = swing_range("TEST", c), swing_range("TEST", flip(c))
    assert (m.low, m.high, m.valid) == (-r.high, -r.low, r.valid)
    assert zone(position(m, -6.6).position) == "DEEP_PREMIUM"


def test_the_primary_range_for_each_question():
    d1, w1 = bars(MID), bars(MID, tf="W1")
    by_tf = {"W1": ranges("TEST", w1), "D1": ranges("TEST", d1)}
    assert (primary(by_tf, "SIDE").tf, primary(by_tf, "SIDE").kind) == ("W1", "SWING")
    assert (primary(by_tf, "LOCATION").tf, primary(by_tf, "LOCATION").kind) == ("D1", "SWING")
    short = {"W1": (), "D1": ranges("TEST", cut(d1, 8))}       # no D1 swing range yet: the previous candle
    assert primary(short, "LOCATION").kind == "PREVIOUS" and primary(short, "SIDE") is None
