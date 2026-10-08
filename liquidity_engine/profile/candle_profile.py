"""
Candle profile: how the frame candle is anticipated to form.

Requirement 21 (.kiro/specs/liquidity-engine, update 2026-10b). The user's
method (decisions LE-D9, LE-D10, LE-D15): ask how the next candle will form.
Price has two objectives, liquidity beyond swing highs and lows and
inefficiencies to rebalance; the nearer one is the realistic draw, unless
the market is trending, when the trend's weekly objective counts.

At the D1 candle containing t (opening 17:00 New York, the strategy calendar):

1. Frame: the candle's open, and the open of its first bar at or after
   midnight New York (recorded only).
2. Objectives, from H4, D1 and W1 bars that closed by the frame open:
   swing highs and lows (lookback 2), the previous day and week high and
   low, and FVGs at their near edge. An objective counts while untaken: no
   later closed bar traded beyond it (a pool) or into it (an FVG). Pools
   above price and bearish FVGs (price rises into them) are objectives
   above; their mirrors are objectives below.
3. Trend: the last closed W1 candle closed above the previous one's high
   (bullish) or below its low (bearish); otherwise not trending.
4. Direction: trending, the trend's, drawn to its nearest untaken W1
   objective, else its nearest objective; not trending, toward the nearer
   objective. NEUTRAL when that side has none.
5. So far (Requirement 22), from the candle's bars up to t: whether it made
   its false move (beyond the open against the direction) and raided the
   Asian range on that side, its low and high, whether t and the setup's
   raid fall in the manipulation window (01:00 to 13:00 New York: the 01:00,
   05:00 and 09:00 H4 candles), and the trading weekday.

Pure and stateless. The anticipation reads only bars that closed by the
frame open, and the frame bar's open, so it is the same at every t in the
candle (Property 35).
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from liquidity_engine.detectors.external import TIMEFRAME_WEIGHT
from liquidity_engine.grader.sequence import asian_pools
from liquidity_engine.models import (
    BiasDirection, Candle, CandleProfile, LiquiditySource, Objective, SetupSequence, Timeframe,
)
from liquidity_engine.utils.candle_utils import find_swing_highs, find_swing_lows
from liquidity_engine.utils.time_utils import ny_time_in_day, to_est, trading_day_open, trading_week_open

__all__ = ["MANIPULATION_WINDOW", "CandleProfileAnalyzer", "nearest_objectives"]

#: Bars on each side that confirm a swing, as for the setup sequence's pools.
SWING_LOOKBACK = 2

#: New York wall time [start, end): the candle's 01:00, 05:00 and 09:00 H4 candles (LE-D11).
MANIPULATION_WINDOW = (time(1, 0), time(13, 0))

_OBJECTIVE_TIMEFRAMES = (Timeframe.H4, Timeframe.D1, Timeframe.W1)
_PREVIOUS_PERIOD = {Timeframe.D1: ("PDH", "PDL"), Timeframe.W1: ("PWH", "PWL")}
_FINEST_FIRST = (
    Timeframe.M1, Timeframe.M3, Timeframe.M5, Timeframe.M15, Timeframe.M30, Timeframe.H1,
    Timeframe.H3, Timeframe.H4, Timeframe.H6, Timeframe.H8, Timeframe.H12, Timeframe.D1,
)
_KIND_ORDER = {"POOL": 0, "FVG": 1}


class CandleProfileAnalyzer:
    """Anticipates the D1 candle containing t (Requirement 21)."""

    def analyze(
        self,
        candles_by_tf: Dict[Timeframe, List[Candle]],
        t: datetime,
        setup_sequence: Optional[SetupSequence] = None,
    ) -> Optional[CandleProfile]:
        open_time = trading_day_open(t)
        days = candles_by_tf.get(Timeframe.D1) or []
        weeks = _closed_by(candles_by_tf.get(Timeframe.W1) or [], trading_week_open(open_time))
        if not days or days[-1].timestamp != open_time or len(weeks) < 2:
            return None

        frame_open = days[-1].open
        objectives = self.objectives(candles_by_tf, open_time)
        above, below = nearest_objectives(objectives, frame_open)
        trend = _trend(weeks[-2], weeks[-1])
        direction, draw = _anticipate(trend, objectives, above, below, frame_open)

        finest = _finest(candles_by_tf)
        candle = finest[bisect_left(finest, open_time, key=_open_time):] or [days[-1]]   # its bars up to t
        low = min(candle, key=lambda c: c.low)                  # the earliest bar on a tie
        high = max(candle, key=lambda c: c.high)
        window_start, window_end = (ny_time_in_day(open_time, at) for at in MANIPULATION_WINDOW)
        raided_at = setup_sequence.raid.raided_at if setup_sequence is not None else None
        return CandleProfile(
            frame_tf=Timeframe.D1,
            open_time=open_time,
            frame_open=frame_open,
            midnight_open=_midnight_open(finest, open_time),
            trend=trend,
            direction=direction,
            draw=draw,
            draw_above=above,
            draw_below=below,
            false_move_taken=_false_move_taken(direction, frame_open, low.low, high.high),
            asia_raided=_asia_raided(direction, candles_by_tf.get(Timeframe.H1) or [], candle, t),
            candle_low=low.low,
            candle_low_at=low.timestamp,
            candle_high=high.high,
            candle_high_at=high.timestamp,
            in_window=window_start <= t < window_end,
            raid_in_window=raided_at is not None and window_start <= raided_at < window_end,
            weekday=(to_est(open_time).date() + timedelta(days=1)).weekday(),
        )

    def objectives(self, candles_by_tf: Dict[Timeframe, List[Candle]], open_time: datetime) -> List[Objective]:
        """Every untaken objective from the H4, D1 and W1 bars that closed by ``open_time`` (21.3)."""
        week_open = trading_week_open(open_time)
        cut = {}
        for tf in _OBJECTIVE_TIMEFRAMES:
            bars = _closed_by(candles_by_tf.get(tf) or [], week_open if tf == Timeframe.W1 else open_time)
            if bars:
                cut[tf] = bars

        found: List[Objective] = []
        for tf, bars in cut.items():
            for i in find_swing_highs(bars, SWING_LOOKBACK):
                found.append(_objective("POOL", "SWING_HIGH", tf, bars[i].high, BiasDirection.BULLISH, bars[i]))
            for i in find_swing_lows(bars, SWING_LOOKBACK):
                found.append(_objective("POOL", "SWING_LOW", tf, bars[i].low, BiasDirection.BEARISH, bars[i]))
            names = _PREVIOUS_PERIOD.get(tf)
            if names is not None:
                previous = bars[-1]
                found.append(_objective("POOL", names[0], tf, previous.high, BiasDirection.BULLISH, previous))
                found.append(_objective("POOL", names[1], tf, previous.low, BiasDirection.BEARISH, previous))
            # PDArrayDetector's FVG rule, at the near edge: a bearish gap's bottom
            # (price rises into it), a bullish gap's top (price falls into it).
            for k in range(2, len(bars)):
                c0, c2 = bars[k - 2], bars[k]
                if c2.low > c0.high:
                    found.append(_objective("FVG", "FVG", tf, c2.low, BiasDirection.BEARISH, c2))
                elif c0.low > c2.high:
                    found.append(_objective("FVG", "FVG", tf, c2.high, BiasDirection.BULLISH, c2))

        later = _LaterExtremes(cut)
        return [o for o in found if later.untaken(o)]


def nearest_objectives(
    objectives: Sequence[Objective], frame_open: float
) -> Tuple[Optional[Objective], Optional[Objective]]:
    """The nearest objective above ``frame_open`` and the nearest below; ties go to the
    higher timeframe, then pools before FVGs. Each objective counts on its own side only."""
    def tie_break(o: Objective) -> tuple:
        return -TIMEFRAME_WEIGHT.get(o.timeframe, 0.0), _KIND_ORDER[o.kind], o.source

    above = min((o for o in objectives if o.direction == BiasDirection.BULLISH and o.price > frame_open),
                key=lambda o: (o.price, *tie_break(o)), default=None)
    below = min((o for o in objectives if o.direction == BiasDirection.BEARISH and o.price < frame_open),
                key=lambda o: (-o.price, *tie_break(o)), default=None)
    return above, below


def _anticipate(
    trend: BiasDirection, objectives: List[Objective], above: Optional[Objective], below: Optional[Objective],
    frame_open: float,
) -> Tuple[BiasDirection, Optional[Objective]]:
    """Requirement 21.5: the anticipated direction and its draw."""
    if trend != BiasDirection.NEUTRAL:
        bullish = trend == BiasDirection.BULLISH
        weekly = nearest_objectives([o for o in objectives if o.timeframe == Timeframe.W1], frame_open)
        draw = (weekly[0] or above) if bullish else (weekly[1] or below)
        return (trend, draw) if draw is not None else (BiasDirection.NEUTRAL, None)
    up = above.price - frame_open if above is not None else math.inf
    down = frame_open - below.price if below is not None else math.inf
    if up < down:
        return BiasDirection.BULLISH, above
    if down < up:
        return BiasDirection.BEARISH, below
    return BiasDirection.NEUTRAL, None          # nothing either side, or equally near


def _trend(previous: Candle, last: Candle) -> BiasDirection:
    """LE-D15: the last closed week closed beyond the previous week's range."""
    if last.close > previous.high:
        return BiasDirection.BULLISH
    if last.close < previous.low:
        return BiasDirection.BEARISH
    return BiasDirection.NEUTRAL


def _false_move_taken(direction: BiasDirection, frame_open: float, low: float, high: float) -> bool:
    """A bullish candle's false move trades below its open; a bearish one's above it."""
    if direction == BiasDirection.BULLISH:
        return low < frame_open
    if direction == BiasDirection.BEARISH:
        return high > frame_open
    return False


def _asia_raided(direction: BiasDirection, h1: List[Candle], candle: List[Candle], t: datetime) -> bool:
    """Whether a bar of the candle, from midnight New York on, traded beyond the Asian
    pool on the false-move side: its low for a bullish candle, its high for a bearish one."""
    if direction == BiasDirection.NEUTRAL:
        return False
    source = LiquiditySource.ASIA_LOW if direction == BiasDirection.BULLISH else LiquiditySource.ASIA_HIGH
    pool = next((p for p in asian_pools(h1, t) if p.source == source), None)
    if pool is None:
        return False
    after = candle[bisect_left(candle, pool.known_at, key=_open_time):]
    if direction == BiasDirection.BULLISH:
        return any(c.low < pool.price for c in after)
    return any(c.high > pool.price for c in after)


def _finest(candles_by_tf: Dict[Timeframe, List[Candle]]) -> List[Candle]:
    return next((candles_by_tf[tf] for tf in _FINEST_FIRST if candles_by_tf.get(tf)), [])


def _midnight_open(finest: List[Candle], open_time: datetime) -> Optional[float]:
    """The open of the finest timeframe's first bar at or after midnight New York in the candle."""
    midnight = ny_time_in_day(open_time, time(0, 0))
    i = bisect_left(finest, midnight, key=_open_time)
    if i == len(finest) or trading_day_open(finest[i].timestamp) != open_time:
        return None
    return finest[i].open


def _objective(kind: str, source: str, tf: Timeframe, price: float, direction: BiasDirection,
               bar: Candle) -> Objective:
    return Objective(kind=kind, source=source, timeframe=tf, price=price, direction=direction,
                     formed_at=bar.timestamp)


def _closed_by(bars: List[Candle], boundary: datetime) -> List[Candle]:
    """The bars (oldest first) that opened before ``boundary``, a boundary of their timeframe."""
    return bars[: bisect_left(bars, boundary, key=_open_time)]


def _open_time(candle: Candle) -> datetime:
    return candle.timestamp


class _LaterExtremes:
    """Per timeframe, the highest high and lowest low from each bar on, to ask
    whether any bar after an objective formed traded beyond it."""

    def __init__(self, cut: Dict[Timeframe, List[Candle]]):
        self.series = []
        for bars in cut.values():
            highs, lows = [-math.inf] * (len(bars) + 1), [math.inf] * (len(bars) + 1)
            for i in range(len(bars) - 1, -1, -1):
                highs[i] = max(bars[i].high, highs[i + 1])
                lows[i] = min(bars[i].low, lows[i + 1])
            self.series.append(([b.timestamp for b in bars], highs, lows))

    def untaken(self, objective: Objective) -> bool:
        for opens, highs, lows in self.series:
            k = bisect_right(opens, objective.formed_at)
            if objective.direction == BiasDirection.BULLISH and highs[k] > objective.price:
                return False
            if objective.direction == BiasDirection.BEARISH and lows[k] < objective.price:
                return False
        return True
