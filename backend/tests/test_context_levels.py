"""
Tests for liquidity_engine/context/levels.py — where the engine waits (context-engine Requirement 34).

On hand-made D1 and W1 candles with a swing low and a swing high (the D1 range 100-110, the W1 range 96-124), a
level is an unfilled H4, D1 or W1 array of its side, at most a D1 average range tall, whose CE sits in discount
(premium for a sell) of either range; overlapping arrays stack on it, and the score counts the frames, the ranges
and the liquidity resting at the level. The
window is Q2 and Q3, 00:00-12:00 New York.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from liquidity_engine.context.levels import in_window, levels
from liquidity_engine.models import (BiasDirection, Candle, LiquidityLevel, LiquiditySource, LiquidityType,
                                     PDArrayType, Timeframe)
from tests.test_liquidity_grader import make_pdarray

AS_OF = datetime(2026, 1, 14, 14, 0, tzinfo=timezone.utc)         # Wednesday 09:00 New York
BULL, BEAR = BiasDirection.BULLISH, BiasDirection.BEARISH
#: Each candle's high and low as fractions of the range: a swing low at the third, a swing high at the seventh.
SHAPE = [(0.4, 0.2), (0.3, 0.1), (0.2, 0.0), (0.4, 0.1), (0.6, 0.3), (0.8, 0.5), (1.0, 0.7), (0.9, 0.6), (0.7, 0.4),
         (0.6, 0.3)]
FORMING = (0.55, 0.35)


def ranged_view(d1=(100.0, 110.0), w1=(96.0, 124.0), as_of=AS_OF, instrument="X") -> dict[Timeframe, list[Candle]]:
    """D1 and W1 candles closed before ``as_of`` whose dealing ranges are ``d1`` and ``w1``, each with its forming
    candle inside the range. The D1's ten closed candles span 0.27 of its range on average."""
    def candles(tf, opens, low, high):
        size = high - low
        out = []
        for t, (h, l) in zip(opens, SHAPE + [FORMING]):
            hi, lo = low + h * size, low + l * size
            out.append(Candle(timestamp=t, open=lo, high=hi, low=lo, close=hi, volume=1, timeframe=tf,
                              instrument=instrument))
        return out
    days = pd.bdate_range(end=as_of.date() - timedelta(days=1), periods=len(SHAPE)).append(
        pd.DatetimeIndex([pd.Timestamp(as_of.date())]))
    d1_opens = [datetime(d.year, d.month, d.day, 22, tzinfo=timezone.utc) - timedelta(days=1) for d in days]
    sunday = as_of.date() - timedelta(days=(as_of.weekday() + 1) % 7)
    w1_opens = [datetime(sunday.year, sunday.month, sunday.day, 22, tzinfo=timezone.utc) - timedelta(weeks=n)
                for n in range(len(SHAPE), -1, -1)]
    return {Timeframe.D1: candles(Timeframe.D1, d1_opens, *d1), Timeframe.W1: candles(Timeframe.W1, w1_opens, *w1)}


def _array(kind=PDArrayType.FVG, direction=BULL, low=101.0, high=102.5, tf=Timeframe.H4, filled=False, **update):
    a = make_pdarray(kind, direction, high, low, is_filled=filled, tf=tf)
    return a.model_copy(update=update) if update else a


def _pool(price, side=LiquidityType.SSL, source=LiquiditySource.PDL, swept=False):
    return LiquidityLevel(level_id=f"{source.value}-{price}", liquidity_type=side, source=source, price=price,
                          timeframe=Timeframe.D1, formed_at=AS_OF - timedelta(days=1), strength_score=0.5,
                          touch_count=1, swept=swept)


ARRAYS = [
    _array(),                                                                       # H4 FVG in discount of both
    _array(PDArrayType.OB, low=102.0, high=103.5, tf=Timeframe.D1),                 # overlaps it: stacked
    _array(low=106.0, high=107.0),                                                  # D1 premium, W1 discount
    _array(low=111.0, high=112.0),                                                  # premium of both: no level
    _array(PDArrayType.OB, low=99.0, high=103.0, tf=Timeframe.W1),                  # 4.0 tall, over the 2.7 ADR
    _array(low=101.2, high=101.6, tf=Timeframe.H1),                                 # H1 and M15 arrays: no level
    _array(low=101.2, high=101.6, tf=Timeframe.M15),
    _array(low=104.0, high=104.5, filled=True),                                     # filled: no level
    _array(PDArrayType.CISD_LEVEL, low=103.6, high=103.9),                          # not an array a level holds
    _array(direction=BEAR, low=108.5, high=109.5, tf=Timeframe.D1),                 # a sell level, D1 premium only
    _array(PDArrayType.OB, BEAR, low=109.0, high=109.4, formed_at=AS_OF + timedelta(hours=1)),   # not yet formed
]
POOLS = [_pool(100.8), _pool(100.5), _pool(101.5, swept=True),
         _pool(109.7, LiquidityType.BSL, LiquiditySource.PDH), _pool(109.9, LiquidityType.BSL, LiquiditySource.PWH)]


@pytest.fixture(scope="module")
def found():
    return levels(ARRAYS, ranged_view(), AS_OF, POOLS)


def test_a_level_is_an_htf_array_of_its_side_in_discount_or_premium_of_the_d1_or_w1_range(found):
    got = [(x.side, x.low, x.high, x.arrays, x.discount) for x in found]
    assert got == [
        (BULL, 106.0, 107.0, ("H4 FVG",), ("W1",)),
        (BULL, 102.0, 103.5, ("D1 OB", "H4 FVG"), ("W1", "D1")),          # each array its own level, the other stacked
        (BULL, 101.0, 102.5, ("H4 FVG", "D1 OB"), ("W1", "D1")),
        (BEAR, 108.5, 109.5, ("D1 FVG",), ("D1",)),
    ]


def test_the_score_counts_its_frames_ranges_and_the_liquidity_resting_at_it(found):
    by_low = {x.low: x for x in found}
    # The D1 average range is 2.7, so liquidity within 0.27 beyond the level counts: 100.8 does, 100.5 doesn't, and
    # a swept level never does.
    assert by_low[101.0].pools == ("PDL 100.8",) and by_low[101.0].score == 2 + 2 + 1
    assert by_low[102.0].pools == () and by_low[102.0].score == 2 + 2
    assert by_low[106.0].score == 1 + 1
    assert by_low[108.5].pools == ("PDH 109.7",) and by_low[108.5].score == 1 + 1 + 1
    assert "H4 FVG + D1 OB" in by_low[101.0].reason()


def test_liquidity_is_at_a_level_inside_it_or_just_beyond_it(found):
    buy, sell = {x.low: x for x in found}[101.0], {x.low: x for x in found}[108.5]
    assert buy.holds(102.0) and not buy.holds(100.9)
    assert buy.at(100.8) and buy.at(102.0) and not buy.at(100.6) and not buy.at(102.6)     # the band is below a buy
    assert sell.at(109.7) and not sell.at(108.3)                                            # and above a sell


def test_without_a_range_nothing_is_a_level():
    flat = {tf: candles[:2] for tf, candles in ranged_view().items()}        # no swing on either side yet
    assert levels(ARRAYS, flat, AS_OF, POOLS) == []


@pytest.mark.parametrize("utc, live", [
    (datetime(2026, 1, 14, 5, 0), True),        # 00:00 New York (EST)
    (datetime(2026, 1, 14, 8, 0), True),        # 03:00, London
    (datetime(2026, 1, 14, 16, 59), True),      # 11:59
    (datetime(2026, 1, 14, 17, 0), False),      # 12:00: Q4 begins
    (datetime(2026, 1, 14, 4, 59), False),      # 23:59, Asia (Q1)
    (datetime(2026, 7, 14, 4, 0), True),        # 00:00 New York in summer (EDT)
])
def test_the_window_is_q2_and_q3_new_york(utc, live):
    assert in_window(utc.replace(tzinfo=timezone.utc)) is live
