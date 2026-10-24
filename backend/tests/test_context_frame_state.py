"""
Tests for liquidity_engine/context/frame_state.py — a frame's state (context-engine Requirement 3).

Task 277 (.kiro/specs/context-engine/tasks.md). Two hand-built series, one candle a day:
- FALL: a swing low at 90 and a swing high at 110, then a slide back into discount, closing below the previous
  candle's low (a bearish close);
- RISE: the same range climbed through a bullish gap at 93-96 left in discount, then held in premium; the gap is
  the frame's bullish POI until price trades back into it.
Each field is read off them; a random walk checks that the state reads candles, not the clock (Property 1).
Validates: Requirements 3.1-3.3 (.kiro/specs/context-engine/requirements.md); Property 1
"""
from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from liquidity_engine.context.frame_state import Candles, Objective, frame_state
from liquidity_engine.models import BiasDirection

BULL, BEAR, NEUTRAL = BiasDirection.BULLISH, BiasDirection.BEARISH, BiasDirection.NEUTRAL
DAY = 86_400
T0 = 1_700_000_000

FALL = [(100, 101, 99, 100.5), (100.5, 101, 98, 98.5), (98.5, 99, 90, 91), (91, 95, 91, 94), (94, 100, 93, 99),
        (99, 105, 98, 104), (104, 110, 103, 106), (106, 107, 101, 102), (102, 103, 99, 100), (100, 101, 96, 97)]
RISE = [(100, 101, 99, 100), (100, 100.5, 97, 97.5), (97.5, 98, 90, 91), (91, 93, 90.5, 92.8),
        (92.8, 97, 92.6, 96.5), (96.5, 101, 96, 100.5), (100.5, 106, 100, 105.5), (105.5, 110, 105, 108),
        (108, 109, 106, 107), (107, 108.2, 106.6, 107.5)]


def candles(rows, tf="D1", step=DAY, start=T0) -> Candles:
    o, h, l, c = (np.array([r[k] for r in rows], float) for k in range(4))
    t = start + step * np.arange(len(rows), dtype=np.int64)
    return Candles(tf, t, t + step, o, h, l, c)


def sources(objectives):
    return [(x.tf, x.source, x.price) for x in objectives]


# ── the dealing range and the zone ─────────────────────────────────────────

def test_dealing_range_from_last_confirmed_swings():
    s = frame_state(candles(FALL), 97.0)
    assert (s.range.low, s.range.high) == (90, 110)
    assert s.range.anchors == (2, 6)
    assert s.range_formed_at == T0 + 7 * DAY                       # the close of the later anchor's candle
    assert "90" in s.reasons["range"] and "110" in s.reasons["range"]


def test_range_stretches_past_a_broken_swing_until_a_new_one_confirms():
    rows = FALL + [(97, 112, 96.5, 111)]                            # breaks the 110 high; not a swing yet
    s = frame_state(candles(rows), 111.0)
    assert (s.range.low, s.range.high, s.range.anchors) == (90, 112, (2, 6))
    confirmed = rows + [(111, 111.5, 108, 109), (109, 110, 107, 108)]
    s = frame_state(candles(confirmed), 108.0)
    assert (s.range.low, s.range.high, s.range.anchors) == (96, 112, (9, 10))   # new swings on both sides now
    assert frame_state(candles(FALL), 97.0, forming=(113.0, 95.0)).range.high == 113   # the forming candle


def test_zone_bands():
    c = candles(FALL)                                               # range 90-110
    assert frame_state(c, 97.0).zone == "DISCOUNT" and frame_state(c, 97.0).position == pytest.approx(0.35)
    assert frame_state(c, 99.2).zone == "EQUILIBRIUM"               # 0.46
    assert frame_state(c, 100.8).zone == "EQUILIBRIUM"              # 0.54
    assert frame_state(c, 101.2).zone == "PREMIUM"                  # 0.56
    s = frame_state(candles(FALL[:6]), 104.0)                       # no swing high yet
    assert s.range is None and s.zone is None and s.position is None and "UNRANGED" in s.reasons["range"]


# ── objectives ─────────────────────────────────────────────────────────────

def test_objectives_from_frame_and_parents_untaken_only():
    s = frame_state(candles(FALL), 97.0)
    # all three gaps were traded into; the swings and the previous candle's extremes stand
    assert sources(s.above) == [("D1", "PDH", 101), ("D1", "SWING_HIGH", 110)]
    assert sources(s.below) == [("D1", "PDL", 96), ("D1", "SWING_LOW", 90)]

    parent = candles([(95, 104, 92, 100), (100, 108, 88, 99)], tf="W1", step=7 * DAY, start=T0 - 14 * DAY)
    s = frame_state(candles(FALL), 97.0, parents=[parent])
    assert ("W1", "PWH", 108) not in sources(s.above)               # taken: the D1 high of 110 traded above it
    assert ("W1", "PWL", 88) in sources(s.below)                    # untaken, below the D1 swing low
    assert all(x.formed_at > 0 for x in s.above + s.below)

    r = frame_state(candles(RISE), 107.5)
    assert ("D1", "FVG", 105) in sources(r.below) and ("D1", "FVG", 100) in sources(r.below)   # unfilled gaps
    assert ("D1", "FVG", 96) in sources(r.below)
    assert [x.price for x in r.below] == sorted((x.price for x in r.below), reverse=True)     # nearest first


def test_asian_range_only_at_d1_and_below():
    asia = (96.4, 97.6, T0 + 10 * DAY)
    assert ("D1", "ASIA_LOW", 96.4) in sources(frame_state(candles(FALL), 97.0, asia=asia).below)
    assert ("H4", "ASIA_HIGH", 97.6) in sources(frame_state(candles(FALL, tf="H4"), 97.0, asia=asia).above)
    w1 = frame_state(candles(FALL, tf="W1", step=7 * DAY), 97.0, asia=asia)
    assert "ASIA_LOW" not in [x.source for x in w1.below] and "ASIA_HIGH" not in [x.source for x in w1.above]


def test_levels_are_objectives_on_their_side():
    level = Objective("POOL", "IPDA20_HIGH", "D1", 99.5, BULL, T0 + 10 * DAY)
    s = frame_state(candles(FALL), 97.0, levels=[level])
    assert s.above[0] == level


# ── trend and own direction ────────────────────────────────────────────────

@pytest.mark.parametrize("tf", ["MN1", "W1", "D1", "H1", "M5"])
def test_trend_closure_rule_at_any_frame(tf):
    assert frame_state(candles(FALL, tf=tf), 97.0).trend == BEAR    # closed 97 below the previous low of 99
    up = FALL[:-1] + [(100, 104, 99.5, 103.5)]                      # closed above the previous high of 103
    assert frame_state(candles(up, tf=tf), 103.5).trend == BULL
    inside = FALL[:-1] + [(100, 102.5, 99.5, 101)]
    assert frame_state(candles(inside, tf=tf), 101.0).trend == NEUTRAL
    assert "previous" in frame_state(candles(FALL, tf=tf), 97.0).reasons["trend"]


def test_own_direction_trending_and_not():
    s = frame_state(candles(FALL), 97.0)                            # trending down: the nearest below
    assert (s.own, s.own_draw.source, s.own_draw.price) == (BEAR, "PDL", 96)

    up = FALL[:-1] + [(100, 104, 99.5, 103.5)]                      # trending up, though the PDL is as near
    s = frame_state(candles(up), 103.5)
    assert s.own == BULL and s.own_draw.price > 103.5

    inside = FALL[:-1] + [(100, 102.5, 99.5, 101)]                  # not trending: the nearer side
    s = frame_state(candles(inside), 102.0)
    assert (s.own, s.own_draw.source) == (BULL, "PDH")              # 0.5 up to 102.5, 2.5 down to 99.5
    s = frame_state(candles(inside), 101.0)
    assert s.own == NEUTRAL and s.own_draw is None                  # 1.5 either way
    assert "NEUTRAL" in s.reasons["own"]

    top = FALL[:-1] + [(100, 111, 99.5, 111)]                       # closed on its high, through every high
    s = frame_state(candles(top), 111.0)
    assert s.trend == BULL and s.above == () and s.own == NEUTRAL


# ── points of interest ─────────────────────────────────────────────────────

def test_poi_nearest_unfilled_array_in_zone():
    s = frame_state(candles(RISE), 107.5)                           # premium; the 97-100 gap is above 0.45
    poi = s.poi(BULL)
    assert (poi.kind, poi.tf, poi.low, poi.high, poi.near) == ("FVG", "D1", 93, 96, 96)
    assert poi.formed_at == T0 + 6 * DAY and poi.reached_at is None
    assert s.poi(BEAR) is None
    assert "FVG" in s.reasons["poi_bullish"] and "none" in s.reasons["poi_bearish"]

    back = RISE + [(107.5, 107.6, 95.8, 96.5), (96.5, 107.8, 96.3, 107.6)]  # into the gap and out, no new swing
    s = frame_state(candles(back), 107.6)
    assert s.poi(BULL).reached_at == T0 + 10 * DAY and "reached" in s.reasons["poi_bullish"]

    early = RISE[:6] + [(100.5, 101.5, 95.5, 101.2)] + RISE[6:]    # into it before the swing high: spent
    assert frame_state(candles(early), 107.5).poi(BULL) is None


def test_poi_from_a_parent_frame():
    week = candles(RISE, tf="W1", step=7 * DAY)
    month = candles([(95, 96.5, 94, 96), (96, 99, 95.5, 98.8), (98.8, 100, 98.5, 99.5)], tf="MN1", step=30 * DAY,
                    start=T0 + 42 * DAY - 90 * DAY)                 # its gap 96.5-98.5 forms as the week climbs
    poi = frame_state(week, 107.5, parents=[month]).poi(BULL)
    assert (poi.tf, poi.low, poi.high, poi.reached_at) == ("MN1", 96.5, 98.5, None)
    path = candles([(107.5, 107.7, 98.0, 98.4)], start=T0 + 70 * DAY)   # a day of the forming week trades into it
    assert frame_state(week, 98.4, parents=[month], path=path).poi(BULL).reached_at == T0 + 70 * DAY


def test_reasons_present_for_every_field():
    for s in (frame_state(candles(FALL), 97.0), frame_state(candles(RISE), 107.5)):
        assert set(s.reasons) == {"range", "zone", "objectives", "trend", "own", "poi_bullish", "poi_bearish"}
        assert all(isinstance(v, str) and v for v in s.reasons.values())


# ── Property 1: the state reads candles, not the clock ─────────────────────

def walk(seed, n=80):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    o = np.r_[100.0, c[:-1]]
    h = np.maximum(o, c) + rng.random(n) * 0.8
    l = np.minimum(o, c) - rng.random(n) * 0.8
    return [tuple(x) for x in np.c_[o, h, l, c]]


def plain(s, start, step):
    """The state with its labels and clock removed: times as candle counts from the series' start, and the previous
    candle's high and low under one name (PDH on D1 is PH1H on H1)."""
    at = lambda x: None if x is None else (x - start) / step                             # noqa: E731
    previous = {f"P{name}{side}": f"PREVIOUS_{side}" for name in ("D", "W", "M", s.tf) for side in "HL"}
    obj = lambda x: (x.kind, previous.get(x.source, x.source), x.price, x.direction, at(x.formed_at))  # noqa: E731
    poi = lambda p: None if p is None else (p.kind, p.low, p.high, at(p.formed_at), at(p.reached_at))  # noqa: E731
    return (s.price, s.range, at(s.range_formed_at), s.position, s.zone, [obj(x) for x in s.above],
            [obj(x) for x in s.below], s.trend, s.own, None if s.own_draw is None else obj(s.own_draw),
            poi(s.poi(BULL)), poi(s.poi(BEAR)))


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 10_000), st.sampled_from([("H1", 3600), ("W1", 7 * DAY), ("M5", 300)]))
def test_property_1_frame_invariance(seed, relabel):
    rows = walk(seed)
    price = rows[-1][3]
    a = frame_state(candles(rows, tf="D1"), price)
    tf, step = relabel
    b = frame_state(candles(rows, tf=tf, step=step, start=5_000), price)
    assert plain(a, T0, DAY) == plain(b, 5_000, step)
    assert b.tf == tf and all(x.tf == tf for x in b.above + b.below)
