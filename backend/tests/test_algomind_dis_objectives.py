"""
Tests for AlgoMindDIS's liquidity objectives and PD array context (algomind-dis Requirements 5, 6; task 401).
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from algomind_dis.analyzers.arrays import arrays, counts, reacting
from algomind_dis.analyzers.objectives import objectives, primary_objective, ranked
from algomind_dis.analyzers.ranges import ranges, swing_range
from liquidity_engine.context.frame_state import Candles, _arrays
from tests.test_algomind_dis_structure import DAY, MID, bars, cut


def test_objectives_are_typed_statused_and_ranked_by_significance_not_distance():
    d1 = bars(MID)                                            # D1 swing range 6-17; last close 6.6; ADR 2.0
    obs = objectives("TEST", {"D1": d1}, float(d1.c[-1]), {"D1": ranges("TEST", d1)})
    by = {(o.source, o.price): o for o in obs}
    assert by[("RANGE_HIGH", 17.0)].kind == "EXTERNAL" and by[("SWING_HIGH", 17.0)].kind == "EXTERNAL"
    assert by[("PDH", 8.0)].kind == "TEMPORAL" and by[("PDL", 6.0)].kind == "TEMPORAL"
    assert by[("SWING_LOW", 8.0)].kind == "INTERNAL"          # inside the range
    assert by[("SWING_LOW", 8.0)].status == "SWEPT" and by[("SWING_LOW", 8.0)].swept_at == d1.end[24]
    assert not by[("SWING_LOW", 8.0)].closed_back             # candle 24 closed beyond it
    assert ("SWING_HIGH", 15.0) not in by                     # taken at candle 15, long ago: consumed
    assert by[("PDL", 6.0)].status == "APPROACHING" and by[("PDH", 8.0)].status == "IDENTIFIED"
    assert by[("RANGE_HIGH", 17.0)].significance == pytest.approx(0.6)      # D1 0.6 x external 1.0
    assert by[("PDH", 8.0)].significance == pytest.approx(0.48)             # D1 0.6 x temporal 0.8
    assert by[("SWING_LOW", 8.0)].significance == pytest.approx(0.36)       # D1 0.6 x internal 0.6
    above = ranked(obs, "BULLISH")
    assert [o.price for o in above] == [17.0, 17.0, 8.0]      # the nearer PDH ranks last: less significant
    assert primary_objective(obs, "BULLISH").price == 17.0
    assert primary_objective(obs, "BEARISH").price == 6.0     # the swept low is never a primary objective


def test_relative_equal_highs_are_raised():
    mid = [10, 11, 12, 14, 12, 11, 12, 13.95, 12, 11, 10, 9, 10]   # two peaks 0.05 apart, the second lower
    d1 = bars(mid)
    obs = objectives("TEST", {"D1": d1}, float(d1.c[-1]), {"D1": ranges("TEST", d1)})
    eq = [o for o in obs if o.source == "EQUAL_HIGHS"]
    assert sorted(o.price for o in eq) == [14.95, 15.0]
    assert all(o.kind == "EXTERNAL" and o.significance == pytest.approx(0.6 + 0.25) for o in eq)


#: A sell-side sweep (candle 8 under the swing low of candle 4), a displacement (9), a bullish FVG 16.0-17.0
#: (candles 8-10), price back into it (12) and closing above it.
OHLC = [(20, 20.5, 19, 19.2), (19.2, 19.4, 18, 18.2), (18.2, 18.4, 17, 17.3), (17.3, 17.6, 16, 16.4),
        (16.4, 16.6, 15.0, 15.4), (15.4, 16.8, 15.2, 16.5), (16.5, 17.0, 16.0, 16.2), (16.2, 16.4, 15.5, 15.8),
        (15.8, 16.0, 14.6, 15.9), (15.9, 18.6, 15.8, 18.5), (18.5, 19.2, 17.0, 19.0), (19.0, 20.5, 18.2, 18.4),
        (18.4, 18.5, 16.8, 17.2)]


def ohlc(rows) -> Candles:
    a = np.asarray(rows, float)
    t = np.arange(len(a), dtype=np.int64) * DAY
    return Candles("D1", t, t + DAY, a[:, 0], a[:, 1], a[:, 2], a[:, 3])


def test_an_array_is_judged_in_its_context():
    c = ohlc(OHLC)
    rng = swing_range("TEST", c)
    assert (rng.low, rng.high) == (14.6, 20.5)
    found = arrays("TEST", c, 17.2, rng, "BULLISH")
    gap = next(a for a in found if (a.kind, a.direction, a.low, a.high) == ("FVG", "BULLISH", 16.0, 17.0))
    assert gap.formed_at == c.end[10] and gap.location == "ABOVE" and gap.range_id == rng.id
    assert gap.zone == "DISCOUNT"                             # its near edge 17.0 at 41% of 14.6-20.5
    assert gap.displacement and gap.after_sweep and gap.aligned and gap.mitigated and gap.valid
    assert reacting(gap, c) and counts(gap, c)
    assert not counts(dataclasses.replace(gap, zone="PREMIUM"), c)          # a bullish array in premium: no
    assert not next(a for a in arrays("TEST", c, 17.2, rng, "BEARISH") if a.id == gap.id).aligned
    later = ohlc(OHLC + [(17.2, 17.4, 15.3, 15.5)])           # a close under its far edge ends it
    gone = next(a for a in arrays("TEST", later, 15.5, swing_range("TEST", later), "BULLISH") if a.id == gap.id)
    assert not gone.valid and gone.invalidated_at == later.end[13] and not counts(gone, later)
    raw = _arrays(later)                                       # the replay passes the full frame's arrays once
    assert arrays("TEST", c, 17.2, rng, "BULLISH", raw=raw) == found


def test_mirrored_bars_give_the_mirrored_array():
    c = ohlc(OHLC)
    m = Candles("D1", c.t, c.end, -c.o, -c.l, -c.h, -c.c)
    found = arrays("TEST", m, -17.2, swing_range("TEST", m), "BEARISH")
    gap = next(a for a in found if (a.kind, a.direction, a.low, a.high) == ("FVG", "BEARISH", -17.0, -16.0))
    assert gap.zone == "PREMIUM" and gap.location == "BELOW" and gap.displacement and gap.after_sweep
    assert counts(gap, m)
