"""
Tests for the trader's order blocks and breakers on arrays (liquidity_engine/context/blocks.py; the trader's answers
of 2026-10-28 and 2026-11-03), and their use by AlgoMindDIS v2.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from liquidity_engine.context.blocks import delivery_blocks
from liquidity_engine.context.measures import bearish_breakers
from liquidity_engine.detectors.internal import PDArrayDetector
from liquidity_engine.models import BiasDirection, Candle, PDArrayType, Timeframe

T0 = datetime(2022, 1, 3, tzinfo=timezone.utc)


def candles(rows) -> list[Candle]:
    return [Candle(timestamp=T0 + timedelta(days=i), open=o, high=h, low=l, close=c, timeframe=Timeframe.D1,
                   instrument="TEST") for i, (o, h, l, c) in enumerate(rows)]


def walk(seed: int, n: int):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    o = np.r_[100.0, c[:-1]] + rng.normal(0, 0.2, n)
    doji = rng.random(n) < 0.05
    c[doji] = o[doji]                                              # dojis: neither end nor join a run
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.5, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.5, n))
    return o, h, l, c


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_the_array_rule_is_the_engines_cisd_rule(seed):
    o, h, l, c = walk(seed, 400)
    cs = candles(zip(o, h, l, c))
    obs, breakers, _ = PDArrayDetector(ob_rule="cisd")._detect_delivery_changes(cs, Timeframe.D1, [])
    mine = delivery_blocks(o, h, l, c)
    when = lambda i: T0 + timedelta(days=int(i))                                         # noqa: E731
    got_obs = sorted((b.direction, round(b.low, 9), round(b.high, 9), when(b.formed), b.high_probability,
                      None if b.ended is None else when(b.ended)) for b in mine if b.kind == "OB")
    want_obs = sorted((a.direction, round(a.low, 9), round(a.high, 9), a.formed_at, bool(a.high_probability),
                       a.filled_at) for a in obs)
    assert got_obs == want_obs and len(got_obs) > 10
    got_br = sorted((b.direction, round(b.low, 9), round(b.high, 9), when(b.formed),
                     None if b.ended is None else when(b.ended)) for b in mine if b.kind == "BREAKER")
    want_br = sorted((a.direction, round(a.low, 9), round(a.high, 9), a.formed_at, a.filled_at) for a in breakers)
    assert got_br == want_br and len(got_br) > 5


#: GBPUSD D1 (the broker's, New York days), 1 to 16 June 2022, then flat closes under 1.235 to a close of 1.19207
#: under the 14 June low on 6 July. The engine's rule calls 14 June alone a bullish order block (the last down candle
#: before a 1.5 ATR up candle) and the 6 July close a bearish breaker over its wicks, 1.19336-1.22075. By the
#: trader's rule the down run of 8-14 June opened at 1.25877 and no close got back above it: no change of delivery,
#: so no order block there, and nothing to fail into a breaker.
JUNE = [(1.26008, 1.26163, 1.24581, 1.24842), (1.24840, 1.25861, 1.24688, 1.25751), (1.25741, 1.25894, 1.24851, 1.24882),
        (1.24856, 1.25771, 1.24763, 1.25276), (1.25263, 1.25990, 1.24299, 1.25888), (1.25877, 1.25969, 1.25129, 1.25341),
        (1.25330, 1.25580, 1.24867, 1.24899), (1.24881, 1.25171, 1.23007, 1.23146), (1.23142, 1.23166, 1.21069, 1.21303),
        (1.21286, 1.22075, 1.19336, 1.19954), (1.19943, 1.22045, 1.19857, 1.21731), (1.21709, 1.24063, 1.20410, 1.23497)]
DRIFT = [(1.2280, 1.2330, 1.2180, 1.2240), (1.2240, 1.2300, 1.2150, 1.2190), (1.2190, 1.2280, 1.2120, 1.2250),
         (1.2250, 1.2320, 1.2160, 1.2200), (1.2200, 1.2260, 1.2080, 1.2120), (1.2120, 1.2200, 1.2010, 1.2060),
         (1.2060, 1.2170, 1.2000, 1.2140), (1.2140, 1.2190, 1.2040, 1.2080), (1.2080, 1.2120, 1.1970, 1.2010),
         (1.2010, 1.2090, 1.1950, 1.2030), (1.2030, 1.2060, 1.1900, 1.19207)]


def test_the_june_2022_breaker_is_the_engines_and_not_the_traders():
    a = np.array(JUNE + DRIFT)
    o, h, l, c = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
    engine = [(round(lo, 5), round(hi, 5)) for _k, lo, hi in bearish_breakers(o, h, l, c)]
    assert (1.19336, 1.22075) in engine
    mine = delivery_blocks(o, h, l, c)
    assert not any(b.kind == "BREAKER" and abs(b.low - 1.19954) < 1e-9 for b in mine)
    assert not any(b.kind == "OB" and b.direction == BiasDirection.BULLISH and b.first == 5 for b in mine)
    assert max(c[11:-1]) < o[5]                                    # no close back above the run's first open


def test_a_breaker_ends_on_a_close_back_through_it():
    rows = [(10, 10.5, 9.0, 9.2), (9.2, 9.4, 8.5, 8.6),          # a down run, open 10
            (8.6, 10.6, 8.5, 10.4),                               # closes above 10: a bullish OB over the bodies 8.6-10
            (10.4, 10.5, 9.8, 10.0), (10.0, 10.1, 8.0, 8.2),      # closes under 8.6: the OB becomes a bearish breaker
            (8.2, 9.5, 8.1, 9.4), (9.4, 10.3, 9.3, 10.2)]         # closes back above 10: the breaker ends
    o, h, l, c = (np.array([r[i] for r in rows]) for i in range(4))
    b = delivery_blocks(o, h, l, c)
    ob = next(x for x in b if x.kind == "OB" and x.direction == BiasDirection.BULLISH)
    br = next(x for x in b if x.kind == "BREAKER")
    assert (ob.low, ob.high, ob.formed, ob.ended, ob.level, ob.mt) == (8.6, 10.0, 2, 4, 10.0, 9.3)
    assert (br.direction, br.low, br.high, br.formed, br.ended) == (BiasDirection.BEARISH, 8.6, 10.0, 4, 6)
    _, breakers, _ = PDArrayDetector(ob_rule="cisd")._detect_delivery_changes(candles(rows), Timeframe.D1, [])
    assert breakers[0].is_filled and breakers[0].filled_at == T0 + timedelta(days=6)


def test_algomind_dis_v2_reads_the_traders_blocks_and_v1_is_unchanged():
    from algomind_dis.analyzers.arrays import raw_arrays
    from algomind_dis.settings import V1, V2, Settings
    from liquidity_engine.context.frame_state import Candles, _arrays
    assert Settings() == V1 and V1.array_rule == "engine" and (V2.version, V2.array_rule) == ("v2", "cisd")
    a = np.array(JUNE + DRIFT)
    t = np.arange(len(a), dtype=np.int64) * 86_400 * 10**9
    c = Candles("D1", t, t + 86_400 * 10**9, a[:, 0], a[:, 1], a[:, 2], a[:, 3])
    assert raw_arrays(c, V1) == _arrays(c)
    v2 = raw_arrays(c, V2)
    assert not any(x.kind == "BREAKER" and abs(x.low - 1.19336) < 1e-9 for x in v2)
    assert {x.kind for x in v2} <= {"OB", "BREAKER", "FVG"}
