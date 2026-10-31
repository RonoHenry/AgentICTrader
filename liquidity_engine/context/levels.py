"""Where the engine waits (context-engine Requirement 34): the levels price is likely to react from, read before any
trigger is looked for.

The trader's blueprint (2026-10-31): to anticipate a move higher, find what supports it (discount, a PD array,
liquidity and time), then wait at that level for price to show its hand. No move is exactly like the last, so a
level is the characteristics that line up at a price, not a fixed sequence of events. A level to buy from (one to
sell from is the mirror):

- **a PD array:** an unfilled array of the side on H4, D1 or W1 (an FVG, an inverted FVG, an order block, a breaker
  or a balanced price range), at most one D1 average range tall: a zone wider than a day's range is no price to
  wait at;
- **in discount:** its CE under the equilibrium of the D1 or the W1 dealing range (``frame_state.dealing_range``:
  swing to swing, stretched to the extremes since, the forming candle's included).

Each array is its own level; the side's other arrays that overlap it are stacked on it. Its score counts what lines
up there: each frame with an array in it, each range it is in discount of, and liquidity resting inside it or just
under it (an untaken sell-side level within a tenth of the D1 average range below its low).

The gate (``StrategyConfig.require_level``) keeps a setup only when all four line up: its protected wick is inside a
level of its side (the array, in discount), the pool it raided is at that level (the liquidity), and the raid came
in Q2 or Q3, 00:00-12:00 New York (the time).

Read from the candles closed by ``as_of`` and the arrays and levels the engine read then: nothing here reads a clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from liquidity_engine.context.frame_state import LIQUIDITY_BAND, DealingRange, dealing_range
from liquidity_engine.models import (BiasDirection, Candle, LiquidityLevel, LiquidityType, PDArray, PDArrayType,
                                     Timeframe)
from liquidity_engine.utils.time_utils import closed_candles

__all__ = ["LEVEL_TIMEFRAMES", "LEVEL_TYPES", "Level", "WINDOW", "in_window", "levels"]

#: The frames a level's arrays come from, highest first.
LEVEL_TIMEFRAMES = (Timeframe.W1, Timeframe.D1, Timeframe.H4)
LEVEL_TYPES = (PDArrayType.FVG, PDArrayType.IFVG, PDArrayType.OB, PDArrayType.BREAKER, PDArrayType.BPR)
#: The dealing ranges a level's discount (premium) is read on.
RANGE_TIMEFRAMES = (Timeframe.W1, Timeframe.D1)
#: Q2 and Q3 of the day, in minutes after 00:00 New York.
WINDOW = (0, 12 * 60)
ADR_DAYS = 10
#: The tallest array a level holds, in D1 average ranges.
MAX_HEIGHT_ADR = 1.0
_NEW_YORK = ZoneInfo("America/New_York")
_RANK = {tf: i for i, tf in enumerate(LEVEL_TIMEFRAMES)}


@dataclass(frozen=True)
class Level:
    side: BiasDirection           # BULLISH: a level to buy from, in discount; BEARISH: to sell from, in premium
    low: float
    high: float
    arrays: tuple[str, ...]       # its own array first ("D1 IFVG"), then those stacked on it, highest frame first
    discount: tuple[str, ...]     # the ranges it is in discount (premium) of: "W1", "D1"
    pools: tuple[str, ...]        # liquidity resting inside it or just beyond it: "PDL 1.32981"
    band: float                   # how far beyond it liquidity still counts as at it
    formed_at: datetime           # when its array formed

    @property
    def frames(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(a.split()[0] for a in self.arrays))

    @property
    def score(self) -> int:
        return len(self.frames) + len(self.discount) + (1 if self.pools else 0)

    def holds(self, price: float) -> bool:
        return self.low <= price <= self.high

    def at(self, price: float) -> bool:
        """Whether liquidity at ``price`` is at this level: inside it or within the band beyond it."""
        if self.side == BiasDirection.BULLISH:
            return self.low - self.band <= price <= self.high
        return self.low <= price <= self.high + self.band

    def reason(self) -> str:
        zone = "discount" if self.side == BiasDirection.BULLISH else "premium"
        pools = f", {', '.join(self.pools)}" if self.pools else ""
        return (f"{self.side.value} level {self.low:.6g}-{self.high:.6g} ({' + '.join(self.arrays)}; "
                f"{'/'.join(self.discount)} {zone}{pools}; score {self.score})")


def in_window(t: datetime) -> bool:
    """Whether ``t`` falls in the levels' window, Q2 and Q3 (00:00-12:00 New York)."""
    local = (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(_NEW_YORK)
    return WINDOW[0] <= local.hour * 60 + local.minute < WINDOW[1]


def _ranges(view: Mapping[Timeframe, Sequence[Candle]], as_of: datetime) -> dict[Timeframe, DealingRange]:
    closed = closed_candles({tf: view.get(tf, []) for tf in RANGE_TIMEFRAMES}, as_of)
    out = {}
    for tf in RANGE_TIMEFRAMES:
        done = closed[tf]
        forming = list(view.get(tf, []))[len(done):]
        r = dealing_range([c.high for c in done], [c.low for c in done], len(done),
                          max((c.high for c in forming), default=None), min((c.low for c in forming), default=None))
        if r is not None and r.high > r.low:
            out[tf] = r
    return out


def _average_range(view: Mapping[Timeframe, Sequence[Candle]], as_of: datetime) -> float:
    days = closed_candles({Timeframe.D1: view.get(Timeframe.D1, [])}, as_of)[Timeframe.D1][-ADR_DAYS:]
    return sum(c.high - c.low for c in days) / len(days) if days else 0.0


def levels(pd_arrays: Iterable[PDArray], view: Mapping[Timeframe, Sequence[Candle]], as_of: datetime,
           liquidity: Iterable[LiquidityLevel] = ()) -> list[Level]:
    """The levels known at ``as_of``, buy levels first, each side from the top down."""
    ranges = _ranges(view, as_of)
    adr = _average_range(view, as_of)
    band = LIQUIDITY_BAND * adr
    pools = [p for p in liquidity if not p.swept and p.formed_at <= as_of]
    unique = {a.array_id: a for a in pd_arrays}                     # the engine's list can repeat an array
    out = []
    for side in (BiasDirection.BULLISH, BiasDirection.BEARISH):
        buy = side == BiasDirection.BULLISH
        own = [a for a in unique.values() if a.direction == side and not a.is_filled and a.timeframe in _RANK
               and a.array_type in LEVEL_TYPES and a.formed_at <= as_of and a.high - a.low <= MAX_HEIGHT_ADR * adr]
        side_levels = []
        for a in own:
            ce = (a.low + a.high) / 2
            cheap = tuple(tf.value for tf in RANGE_TIMEFRAMES if tf in ranges and (ranges[tf].position(ce) < 0.5) == buy)
            if not cheap:
                continue
            stacked = sorted((b for b in own if b is not a and b.low <= a.high and a.low <= b.high),
                             key=lambda b: (_RANK[b.timeframe], b.array_type.value))
            labels = [f"{a.timeframe.value} {a.array_type.value}"] + [f"{b.timeframe.value} {b.array_type.value}"
                                                                       for b in stacked]
            level = Level(side=side, low=a.low, high=a.high, arrays=tuple(dict.fromkeys(labels)), discount=cheap,
                          pools=(), band=band, formed_at=a.formed_at)
            near = sorted((p for p in pools if p.liquidity_type == (LiquidityType.SSL if buy else LiquidityType.BSL)
                           and level.at(p.price)), key=lambda p: p.price)
            side_levels.append(Level(**{**level.__dict__,
                                        "pools": tuple(dict.fromkeys(f"{p.source.value} {p.price:.6g}" for p in near))}))
        out += sorted(side_levels, key=lambda x: (x.high, x.low), reverse=True)
    return out
