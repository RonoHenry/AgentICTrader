"""
Setup sequence detection: raid -> change in state of delivery -> PD array.

Requirement 18 (.kiro/specs/liquidity-engine, update 2026-10). Price runs
between liquidity pools and inefficiencies. A setup is a raid on resting
liquidity against the coming move (the manipulation), a change in state of
delivery after it, and a PD array formed by that displacement. Its stop goes
behind the protected swing, the extreme the displacement started from.

Per entry timeframe, for every unfilled entry-eligible PD array:

1. Pools: swing highs and lows (lookback 2) on every timeframe, known from
   the open of the bar after the confirming bar; the previous day, week
   and month high and low, known from the current period's open; and the
   current day's Asian range (20:00 to 00:00 New York, from H1), known from
   midnight New York (Requirement 20.2). Every pool gates alike; its
   timeframe weight only breaks ties (decision LE-D2).
2. Raid: the first bar of the entry timeframe, from known_at on, that trades
   beyond the pool. A pool that a bar of another timeframe traded beyond and
   closed before that bar opened was already taken: it has no raid.
3. A bullish array has a sequence when a sell-side raid came at or before the
   bar it formed on, a bar closed back above the pool from the raid on, a
   confirmed bullish CISD came after the raid, and nothing has traded below
   the protected swing (the lowest low from the raid to the array) since.
   Bearish arrays mirror this. The most recent qualifying raid is used.
4. Among arrays: the most recent raid, then the heavier pool, the stronger
   array, the later array, the array id.

Pure and stateless: it reads only the candles and arrays passed in, and
nothing about a bar is used before that bar has closed.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple

from liquidity_engine.detectors.external import TIMEFRAME_WEIGHT
from liquidity_engine.grader.setup_grader import _ENTRY_ELIGIBLE_TIMEFRAMES
from liquidity_engine.ipda.cisd import CISDDetector
from liquidity_engine.models import (
    BiasDirection,
    Candle,
    LiquidityPool,
    LiquidityRaid,
    LiquiditySource,
    LiquidityType,
    PDArray,
    ProtectedSwing,
    SetupSequence,
    Timeframe,
)
from liquidity_engine.utils.candle_utils import find_swing_highs, find_swing_lows
from liquidity_engine.utils.time_utils import ny_time_in_day, trading_day_open

__all__ = ["ASIA_SESSION", "SWING_LOOKBACK", "SetupSequenceDetector", "asian_pools"]

#: Bars on each side that confirm a swing point (the equal-highs/lows detector's default).
SWING_LOOKBACK = 2

#: The Asian session in New York wall time, [start, end): the H1 bars from 20:00 to 23:00.
ASIA_SESSION = (time(20, 0), time(0, 0))

_PREVIOUS_PERIOD: Dict[Timeframe, Tuple[LiquiditySource, LiquiditySource]] = {
    Timeframe.D1: (LiquiditySource.PDH, LiquiditySource.PDL),
    Timeframe.W1: (LiquiditySource.PWH, LiquiditySource.PWL),
    Timeframe.MN1: (LiquiditySource.PMH, LiquiditySource.PML),
}

_Raid = Tuple[LiquidityPool, int, int]          # the pool, the raid bar, the reclaim bar (indices on the entry timeframe)


class SetupSequenceDetector:
    """Finds the setup sequence the grader trades (Requirement 18)."""

    def pools(
        self, candles_by_tf: Dict[Timeframe, List[Candle]], as_of: Optional[datetime] = None
    ) -> List[LiquidityPool]:
        """Every raidable pool in the window, each with the moment it became known (18.1, 18.2).
        The Asian range needs the time of the analysis, ``as_of`` (20.2): without it there is none."""
        pools: List[LiquidityPool] = []
        known = SWING_LOOKBACK + 1                  # the bar after the one that confirms a swing
        for tf, candles in candles_by_tf.items():
            for i in find_swing_highs(candles, SWING_LOOKBACK):
                if i + known < len(candles):
                    pools.append(_pool(LiquidityType.BSL, LiquiditySource.SWING_HIGH, tf, candles[i].high,
                                       candles[i], candles[i + known]))
            for i in find_swing_lows(candles, SWING_LOOKBACK):
                if i + known < len(candles):
                    pools.append(_pool(LiquidityType.SSL, LiquiditySource.SWING_LOW, tf, candles[i].low,
                                       candles[i], candles[i + known]))
            sources = _PREVIOUS_PERIOD.get(tf)
            if sources is not None and len(candles) >= 2:
                previous, current = candles[-2], candles[-1]
                pools.append(_pool(LiquidityType.BSL, sources[0], tf, previous.high, previous, current))
                pools.append(_pool(LiquidityType.SSL, sources[1], tf, previous.low, previous, current))
        if as_of is not None:
            pools += asian_pools(candles_by_tf.get(Timeframe.H1, []), as_of)
        return pools

    def detect(
        self, candles_by_tf: Dict[Timeframe, List[Candle]], pd_arrays: List[PDArray],
        as_of: Optional[datetime] = None,
    ) -> Optional[SetupSequence]:
        arrays_by_tf: Dict[Timeframe, List[PDArray]] = {}
        for array in pd_arrays:
            if (not array.is_filled and array.timeframe in _ENTRY_ELIGIBLE_TIMEFRAMES
                    and array.direction != BiasDirection.NEUTRAL and candles_by_tf.get(array.timeframe)):
                arrays_by_tf.setdefault(array.timeframe, []).append(array)
        if not arrays_by_tf:
            return None

        pools = self.pools(candles_by_tf, as_of)
        best: Optional[Tuple[tuple, SetupSequence]] = None
        for tf, arrays in arrays_by_tf.items():
            window = _EntryWindow(tf, candles_by_tf, pools)
            for array in arrays:
                found = window.sequence_for(array)
                if found is None:
                    continue
                sequence, weight = found
                key = (sequence.raid.raided_at, weight, array.strength_score, array.formed_at, array.array_id)
                if best is None or key > best[0]:
                    best = (key, sequence)
        return None if best is None else best[1]


class _EntryWindow:
    """One entry timeframe's bars with what its arrays need: every pool's
    raid, the CISD violations, and suffix extremes for the intact checks."""

    def __init__(self, tf: Timeframe, candles_by_tf: Dict[Timeframe, List[Candle]], pools: List[LiquidityPool]):
        self.candles = candles = candles_by_tf[tf]
        self.opens = [c.timestamp for c in candles]
        n = len(candles)
        self.suffix_low = [math.inf] * (n + 1)
        self.suffix_high = [-math.inf] * (n + 1)
        for i in range(n - 1, -1, -1):
            self.suffix_low[i] = min(candles[i].low, self.suffix_low[i + 1])
            self.suffix_high[i] = max(candles[i].high, self.suffix_high[i + 1])

        # Bars whose close completes a confirmed CISD, per direction. CISDDetector judges the
        # last bar of what it is given, so each prefix is offered in turn.
        detector = CISDDetector()
        self.cisd: Dict[BiasDirection, List[int]] = {BiasDirection.BULLISH: [], BiasDirection.BEARISH: []}
        for k in range(1, n):
            result = detector.detect(candles[: k + 1])
            if result is not None and result.confirmed:
                self.cisd[result.direction].append(k)

        self.others = {other: (bars, [c.timestamp for c in bars])
                       for other, bars in candles_by_tf.items() if other != tf and bars}
        self.raids: Dict[LiquidityType, List[_Raid]] = {LiquidityType.SSL: [], LiquidityType.BSL: []}
        for pool in pools:
            raid = self._raid(pool)
            if raid is not None:
                self.raids[pool.side].append(raid)
        # Most recent raid first; on one bar the heavier, then the deeper pool. Sorted
        # once here (stably), so each array's candidates keep this order.
        for side, raids in self.raids.items():
            raids.sort(key=lambda r: _recency(r, bullish=side == LiquidityType.SSL), reverse=True)

    def _raid(self, pool: LiquidityPool) -> Optional[_Raid]:
        sell_side = pool.side == LiquidityType.SSL
        start = bisect_left(self.opens, pool.known_at)
        untouched = self.suffix_low[start] >= pool.price if sell_side else self.suffix_high[start] <= pool.price
        if untouched:
            return None
        raid = next(i for i in range(start, len(self.candles)) if _beyond(self.candles[i], pool, sell_side))
        if self._taken_earlier(pool, sell_side, self.opens[raid]):
            return None
        price = pool.price
        reclaim = next((k for k in range(raid, len(self.candles))
                        if (self.candles[k].close > price if sell_side else self.candles[k].close < price)), None)
        return None if reclaim is None else (pool, raid, reclaim)

    def _taken_earlier(self, pool: LiquidityPool, sell_side: bool, raid_open) -> bool:
        """Whether a bar of another timeframe, opened at or after known_at and
        closed by the raid bar's open (its successor opened by then), already
        traded beyond the pool."""
        for bars, opens in self.others.values():
            first = bisect_left(opens, pool.known_at)
            end = bisect_right(opens, raid_open) - 1
            for j in range(first, end):
                if _beyond(bars[j], pool, sell_side):
                    return True
        return False

    def sequence_for(self, array: PDArray) -> Optional[Tuple[SetupSequence, float]]:
        bullish = array.direction == BiasDirection.BULLISH
        formed = bisect_right(self.opens, array.formed_at) - 1          # the bar the array formed on
        if formed < 0:
            return None
        side = LiquidityType.SSL if bullish else LiquidityType.BSL
        cisd = self.cisd[array.direction]

        for pool, raid, reclaim in (r for r in self.raids[side] if r[1] <= formed):
            after = bisect_right(cisd, raid)                             # the first CISD after the raid bar
            if after == len(cisd):
                continue
            bars = range(raid, formed + 1)
            p = (min(bars, key=lambda i: self.candles[i].low) if bullish
                 else max(bars, key=lambda i: self.candles[i].high))     # earliest extreme
            bar = self.candles[p]
            intact = self.suffix_low[p + 1] >= bar.low if bullish else self.suffix_high[p + 1] <= bar.high
            if not intact:
                continue
            swing = ProtectedSwing(
                candle_at=bar.timestamp,
                wick=bar.low if bullish else bar.high,
                body=min(bar.open, bar.close) if bullish else max(bar.open, bar.close),
                candle_range=bar.high - bar.low,
            )
            sequence = SetupSequence(
                entry_array_id=array.array_id,
                direction=array.direction,
                raid=LiquidityRaid(pool=pool, raided_at=self.opens[raid], reclaimed_at=self.opens[reclaim]),
                cisd_at=self.opens[cisd[after]],
                protected_swing=swing,
                leg_extreme=self.suffix_high[raid] if bullish else self.suffix_low[raid],
            )
            return sequence, _weight(pool)
        return None


def asian_pools(h1: List[Candle], as_of: datetime) -> List[LiquidityPool]:
    """The Asian high and low of the trading day containing ``as_of``, known from
    its midnight New York; none before then, or when the session has no H1 bar."""
    day_open = trading_day_open(as_of)
    start, midnight = (ny_time_in_day(day_open, at) for at in ASIA_SESSION)
    if as_of < midnight:
        return []
    session = h1[bisect_left(h1, start, key=_open_time): bisect_left(h1, midnight, key=_open_time)]
    if not session:
        return []
    high = max(session, key=lambda c: c.high)          # the earliest bar on a tie
    low = min(session, key=lambda c: c.low)
    return [
        LiquidityPool(side=LiquidityType.BSL, source=LiquiditySource.ASIA_HIGH, timeframe=Timeframe.H1,
                      price=high.high, formed_at=high.timestamp, known_at=midnight),
        LiquidityPool(side=LiquidityType.SSL, source=LiquiditySource.ASIA_LOW, timeframe=Timeframe.H1,
                      price=low.low, formed_at=low.timestamp, known_at=midnight),
    ]


def _open_time(candle: Candle) -> datetime:
    return candle.timestamp


def _pool(side: LiquidityType, source: LiquiditySource, tf: Timeframe, price: float,
          formed: Candle, known: Candle) -> LiquidityPool:
    return LiquidityPool(side=side, source=source, timeframe=tf, price=price,
                         formed_at=formed.timestamp, known_at=known.timestamp)


def _beyond(candle: Candle, pool: LiquidityPool, sell_side: bool) -> bool:
    return candle.low < pool.price if sell_side else candle.high > pool.price


def _recency(raid: _Raid, bullish: bool) -> tuple:
    pool = raid[0]
    return raid[1], _weight(pool), -pool.price if bullish else pool.price


def _weight(pool: LiquidityPool) -> float:
    return TIMEFRAME_WEIGHT.get(pool.timeframe, 0.5)
