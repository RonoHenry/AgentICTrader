"""
Tests for algo_research/supply_demand.py — supply and demand zones (algo-research update 2026-10-20).

A zone is a base of small-bodied candles and an explosive leg-out closing beyond it; its proximal line is the
base's body edge, its distal line the far wick; it is fresh until price returns to the proximal line.
"""
from __future__ import annotations

import numpy as np

from algo_research.replay.timeframes import wall_seconds
from algo_research.supply_demand import zone_life, zones
from tests.test_research_fractal_poi import m1_from, w

NORMAL = (99.6, 100.4, 99.4, 100.3)                 # a range of 1.0, a body of 0.7: no base


def _arrays(candles):
    m1 = m1_from(candles, "2026-01-05 18:00", minutes=60)
    return (wall_seconds(m1["time"]), *(m1[k].to_numpy(float) for k in ("open", "high", "low", "close")))


def test_a_base_and_an_explosive_leg_out_make_a_zone_known_at_the_leg_out_s_close():
    candles = [NORMAL] * 21 + [(100.3, 100.5, 99.5, 100.2), (100.2, 103.0, 100.0, 102.9)] + [(102.9, 103.2, 102.6, 103.0)]
    table = zones(*_arrays(candles), "H1")
    z = table.iloc[-1]
    assert (z.kind, z.base_n, z.proximal, z.distal) == ("DEMAND", 1, 100.3, 99.5)   # body edge, the far wick
    assert z.known == w("2026-01-06 17:00") and abs(z.departure - 3.0) < 1e-9   # 18:00 + 23 H1 candles
    supply = zones(*_arrays([NORMAL] * 21 + [(100.3, 100.5, 99.5, 100.2), (100.2, 100.4, 97.0, 97.1)]), "H1")
    assert (supply.iloc[-1].kind, supply.iloc[-1].proximal, supply.iloc[-1].distal) == ("SUPPLY", 100.2, 100.5)


def test_no_base_or_no_explosion_makes_no_zone():
    leg_out_of_a_leg = [NORMAL] * 21 + [(100.3, 101.5, 100.2, 101.4), (101.4, 104.0, 101.3, 103.9)]
    assert zones(*_arrays(leg_out_of_a_leg), "H1").empty
    too_small = [NORMAL] * 21 + [(100.3, 100.5, 99.5, 100.2), (100.2, 101.2, 100.0, 101.1)]   # range 1.2 < 1.5 x 1.0
    assert zones(*_arrays(too_small), "H1").empty


def test_a_zone_is_fresh_until_price_returns_and_broken_by_a_close_beyond_its_far_line():
    candles = ([NORMAL] * 21 + [(100.3, 100.5, 99.5, 100.2), (100.2, 103.0, 100.0, 102.9), (102.9, 103.2, 102.6, 103.0),
               (103.0, 103.1, 100.25, 100.6), (100.6, 100.7, 99.0, 99.2)])
    wall, o, h, l, c = _arrays(candles)
    table = zone_life(zones(wall, o, h, l, c, "H1"), wall, h, l, c)
    assert table.kind.tolist() == ["DEMAND", "SUPPLY"]       # the drop from 103 makes a supply zone of its own
    life = table.iloc[0]
    assert life.first_touch == w("2026-01-06 18:00")         # the candle after the next trades back to 100.3
    assert life.broken == w("2026-01-06 19:00")              # the one after closes 99.2, below 99.5
    assert np.isfinite(life.first_touch) and life.first_touch < life.broken
