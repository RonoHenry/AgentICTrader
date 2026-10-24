"""A frame's state (context-engine Requirement 3).

Model A's parts (update 2026-10-15): the dealing range and price's zone in it (step 1, premium/discount), and the
frame's bearish points of interest (step 2): untouched order blocks, breakers and fair value gaps whose near edge is
in premium, and the untaken liquidity above price (swing highs, equal highs, previous candles' highs). Written for
shorts; longs read the mirrored bars.

The whole state for the context chain (task 277, ``frame_state``): the range and zone, the untaken objectives
above and below from the frame and the frames above it, the trend (LE-D15 at any frame), the frame's own direction
(CE-D4) and a point of interest for each direction, each with a reason.

Read from the frame's closed candles only; the forming candle's extremes stretch the range. Nothing here reads a
clock: times are compared with each other, never with a constant (Property 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from liquidity_engine.context.measures import (bearish_breakers, bearish_fvgs, bearish_order_blocks, mirror,
                                               swing_highs, swing_lows)
from liquidity_engine.detectors.external import TIMEFRAME_WEIGHT
from liquidity_engine.models import BiasDirection, Timeframe

__all__ = ["ArrayPOI", "Candidate", "Candles", "DealingRange", "FrameState", "Objective", "POI", "PREMIUM_FROM",
           "DISCOUNT_BELOW", "bearish_candidates", "bearish_pois", "dealing_range", "frame_state", "select_pois"]

#: CE-D2: equilibrium is within 5% either side of the middle.
PREMIUM_FROM, DISCOUNT_BELOW = 0.55, 0.45
#: MA-D2: liquidity and equal highs are read within 0.1 of the frame's average range.
LIQUIDITY_BAND = 0.1


@dataclass(frozen=True)
class DealingRange:
    low: float
    high: float
    low_at: int                  # the frame index of the swing low and swing high it is anchored on
    high_at: int

    def position(self, price: float) -> float:
        return (price - self.low) / (self.high - self.low) if self.high > self.low else 0.5

    def zone(self, price: float) -> str:
        p = self.position(price)
        return "PREMIUM" if p > PREMIUM_FROM else "DISCOUNT" if p < DISCOUNT_BELOW else "EQUILIBRIUM"

    @property
    def premium_floor(self) -> float:
        return self.low + PREMIUM_FROM * (self.high - self.low)

    @property
    def anchors(self) -> Tuple[int, int]:
        return self.low_at, self.high_at

    def reason(self) -> str:
        return f"range {self.low:.5g}-{self.high:.5g}"


def dealing_range(h, l, n_closed: int, forming_high: Optional[float] = None,
                  forming_low: Optional[float] = None, lookback: int = 2) -> Optional[DealingRange]:
    """From the last confirmed swing low to the last confirmed swing high among the closed candles, each
    stretched to any later extreme beyond it, the forming candle's included (CE-D2). None without a swing on
    either side."""
    h, l = np.asarray(h[:n_closed], float), np.asarray(l[:n_closed], float)
    highs, lows = swing_highs(h, lookback), swing_lows(l, lookback)
    if not highs or not lows:
        return None
    i_h, i_l = highs[-1], lows[-1]
    high = float(h[i_h:].max())
    low = float(l[i_l:].min())
    if forming_high is not None:
        high = max(high, forming_high)
    if forming_low is not None:
        low = min(low, forming_low)
    return DealingRange(low, high, i_l, i_h)


@dataclass(frozen=True)
class POI:
    kind: str                    # OB, BREAKER, FVG, SWING_HIGH, EQUAL_HIGHS, or a previous candle's high (PDH, PWH...)
    low: float
    high: float
    formed: int                  # the frame index it formed at (-1 for a level read from another frame)
    label: str

    def reason(self) -> str:
        return f"{self.label} {self.low:.5g}-{self.high:.5g}"


def _untouched(h: np.ndarray, start: int, end: int, level: float) -> bool:
    """No candle in [start, end) traded up to ``level``."""
    return start >= end or float(h[start:end].max()) < level


@dataclass(frozen=True)
class Candidate:
    """A POI as the closed candles leave it; whether it is in premium and above price is read at the time."""
    poi: POI
    level: Optional[float] = None     # liquidity: the level itself, which the forming candle may take


def bearish_candidates(o, h, l, c, n_closed: int, avg_range: float, levels: Iterable[Tuple[str, float]] = (),
                       tf: str = "") -> List[Candidate]:
    """The frame's bearish POIs as of its closed candles (MA-D2), price aside:
    - order blocks, breakers and fair value gaps not traded into since they formed;
    - untaken swing highs and equal highs, each as its level +/- 0.1 average ranges;
    - ``levels``: previous candles' highs of this frame and the frames above, (label, price)."""
    o, h, l, c = (np.asarray(x[:n_closed], float) for x in (o, h, l, c))
    n, band = n_closed, LIQUIDITY_BAND * avg_range
    out: List[Candidate] = []
    for j, i, low, high in bearish_order_blocks(o, h, l, c, n):
        if _untouched(h, i + 1, n, low):
            out.append(Candidate(POI("OB", low, high, j, f"{tf} bearish OB")))
    for k, low, high in bearish_breakers(o, h, l, c, n):
        if _untouched(h, k + 1, n, low):
            out.append(Candidate(POI("BREAKER", low, high, k, f"{tf} bearish breaker")))
    for k, low, high in bearish_fvgs(h, l, 0, n):
        if _untouched(h, k + 1, n, low):
            out.append(Candidate(POI("FVG", low, high, k, f"{tf} bearish FVG")))
    untaken = [s for s in swing_highs(h) if _untouched(h, s + 1, n, h[s] + 1e-12)]
    for s in untaken:
        out.append(Candidate(POI("SWING_HIGH", h[s] - band, h[s] + band, s, f"{tf} swing high"), float(h[s])))
    peaks = sorted(untaken, key=lambda s: h[s])
    for a, b in zip(peaks, peaks[1:]):
        if h[b] - h[a] <= band:
            out.append(Candidate(POI("EQUAL_HIGHS", h[a] - band, h[b] + band, max(a, b), f"{tf} equal highs"), float(h[a])))
    for label, level in levels:
        if level is not None and np.isfinite(level):
            out.append(Candidate(POI(label, level - band, level + band, -1, label), float(level)))
    return out


def select_pois(candidates: Sequence[Candidate], rng: DealingRange, price: float,
                forming_high: Optional[float] = None) -> List[POI]:
    """The candidates that are POIs now: near edge in premium, above ``price``, and, for liquidity, not yet taken
    by the forming candle. Nearest first, each zone once."""
    taken_by = forming_high if forming_high is not None else -np.inf
    floor = rng.premium_floor
    keep = {}
    for cand in candidates:
        p = cand.poi
        if p.low >= floor and p.high > price and (cand.level is None or cand.level > taken_by):
            keep.setdefault((p.kind, round(p.low, 10), round(p.high, 10)), p)
    return sorted(keep.values(), key=lambda p: (p.low, p.high))


def bearish_pois(o, h, l, c, n_closed: int, price: float, rng: DealingRange, avg_range: float,
                 levels: Iterable[Tuple[str, float]] = (), forming_high: Optional[float] = None,
                 tf: str = "") -> List[POI]:
    """``bearish_candidates`` selected at ``price``: the frame's bearish POIs above price, nearest first."""
    return select_pois(bearish_candidates(o, h, l, c, n_closed, avg_range, levels, tf), rng, price, forming_high)


# ── the whole state, for the context chain (task 277) ──────────────────────

BULL, BEAR, NEUTRAL = BiasDirection.BULLISH, BiasDirection.BEARISH, BiasDirection.NEUTRAL

#: The previous candle's high and low, named as the candle profile names them.
_PREVIOUS = {"MN1": ("PMH", "PML"), "W1": ("PWH", "PWL"), "D1": ("PDH", "PDL")}
_KIND_ORDER = {"POOL": 0, "FVG": 1, "POI": 2}
_ARRAY_ORDER = {"FVG": 0, "OB": 1, "BREAKER": 2}


@dataclass(frozen=True)
class Candles:
    """A frame's closed candles, oldest first: each one's open and close time (seconds) and prices."""
    tf: str
    t: np.ndarray
    end: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray

    def __len__(self) -> int:
        return len(self.t)


@dataclass(frozen=True)
class Objective:
    """An untaken pool, or an unfilled gap at its near edge (Requirement 3.1). BULLISH lies above price, reached by
    rising; BEARISH below. ``formed_at`` is the close of the candle that made it."""
    kind: str                    # POOL or FVG; a chain's draw toward a parent's POI is kind POI
    source: str                  # SWING_HIGH, SWING_LOW, PDH, PWL, FVG, ASIA_HIGH, IPDA20_HIGH ...
    tf: str
    price: float
    direction: BiasDirection
    formed_at: int

    def reason(self) -> str:
        return f"{self.tf} {self.source} {self.price:.5g}"


@dataclass(frozen=True)
class ArrayPOI:
    """A point of interest (Requirement 3.1): an order block, breaker or gap where a retracement should end. A
    BULLISH one supports price from below. ``reached_at`` is the open of the first bar that traded into it once
    the dealing range had formed."""
    direction: BiasDirection
    kind: str                    # FVG, OB or BREAKER
    tf: str
    low: float
    high: float
    formed_at: int
    reached_at: Optional[int]

    @property
    def near(self) -> float:
        return self.high if self.direction == BULL else self.low

    def reason(self) -> str:
        state = "unreached" if self.reached_at is None else "reached"
        return f"{self.tf} {self.direction.value.lower()} {self.kind} {self.low:.5g}-{self.high:.5g}, {state}"


@dataclass(frozen=True)
class FrameState:
    """Where a frame stands at a price (Requirement 3.1). ``above`` and ``below`` are nearest first."""
    tf: str
    price: float
    range: Optional[DealingRange]
    range_formed_at: Optional[int]
    position: Optional[float]
    zone: Optional[str]
    above: Tuple[Objective, ...]
    below: Tuple[Objective, ...]
    trend: BiasDirection
    own: BiasDirection
    own_draw: Optional[Objective]
    pois: Mapping[BiasDirection, Optional[ArrayPOI]] = field(default_factory=dict)
    reasons: Mapping[str, str] = field(default_factory=dict)

    def poi(self, direction: BiasDirection) -> Optional[ArrayPOI]:
        return self.pois.get(direction)

    def nearest(self, direction: BiasDirection, tf: Optional[str] = None) -> Optional[Objective]:
        """The nearest objective on ``direction``'s side, of timeframe ``tf`` if given."""
        side = self.above if direction == BULL else self.below if direction == BEAR else ()
        return next((x for x in side if tf is None or x.tf == tf), None)

    def nearer(self) -> Tuple[BiasDirection, Optional[Objective]]:
        """Toward the nearer of the nearest objectives above and below; NEUTRAL with neither, or on a tie."""
        up = self.above[0].price - self.price if self.above else np.inf
        down = self.price - self.below[0].price if self.below else np.inf
        if up < down:
            return BULL, self.above[0]
        if down < up:
            return BEAR, self.below[0]
        return NEUTRAL, None


def _weight(tf: str) -> float:
    try:
        return TIMEFRAME_WEIGHT.get(Timeframe(tf), 0.0)
    except ValueError:
        return 0.0


def _tie(x: Objective) -> tuple:
    """Equally near objectives: the higher timeframe first, then pools before gaps (``nearest_objectives``)."""
    return -_weight(x.tf), _KIND_ORDER[x.kind], x.source


def _objectives(c: Candles, previous: bool) -> List[Objective]:
    """A source's pools and gaps, by the candle profile's rules at any frame: swing highs and lows (lookback 2),
    the previous candle's high and low when ``previous``, and gaps at their near edge."""
    out: List[Objective] = []
    for i in swing_highs(c.h):
        out.append(Objective("POOL", "SWING_HIGH", c.tf, float(c.h[i]), BULL, int(c.end[i])))
    for i in swing_lows(c.l):
        out.append(Objective("POOL", "SWING_LOW", c.tf, float(c.l[i]), BEAR, int(c.end[i])))
    if previous and len(c):
        high, low = _PREVIOUS.get(c.tf, (f"P{c.tf}H", f"P{c.tf}L"))
        out.append(Objective("POOL", high, c.tf, float(c.h[-1]), BULL, int(c.end[-1])))
        out.append(Objective("POOL", low, c.tf, float(c.l[-1]), BEAR, int(c.end[-1])))
    for k in range(2, len(c)):
        if c.l[k] > c.h[k - 2]:                  # a gap up: price falls back into it from above
            out.append(Objective("FVG", "FVG", c.tf, float(c.l[k]), BEAR, int(c.end[k])))
        elif c.l[k - 2] > c.h[k]:                # a gap down: price rises back into it
            out.append(Objective("FVG", "FVG", c.tf, float(c.h[k]), BULL, int(c.end[k])))
    return out


class _Later:
    """Per source, the highest high and lowest low from each candle on: whether a candle that opened at or after
    a time traded strictly beyond a price."""

    def __init__(self, sources: Iterable[Candles]):
        self.series = []
        for s in sources:
            if len(s):
                hi = np.r_[np.maximum.accumulate(s.h[::-1])[::-1], -np.inf]
                lo = np.r_[np.minimum.accumulate(s.l[::-1])[::-1], np.inf]
                self.series.append((s.t, hi, lo))

    def taken(self, x: Objective) -> bool:
        for t, hi, lo in self.series:
            k = int(np.searchsorted(t, x.formed_at, "left"))
            if (x.direction == BULL and hi[k] > x.price) or (x.direction == BEAR and lo[k] < x.price):
                return True
        return False


@dataclass(frozen=True)
class _Array:
    direction: BiasDirection
    kind: str
    tf: str
    low: float
    high: float
    formed_at: int               # the close of the candle that completes it

    @property
    def edge(self) -> float:
        return self.high if self.direction == BULL else self.low


def _arrays(c: Candles) -> List[_Array]:
    """A frame's order blocks, breakers and gaps, both ways (the engine's rules; gaps as the gap only)."""
    out: List[_Array] = []
    for direction, bars in ((BEAR, (c.o, c.h, c.l, c.c)), (BULL, mirror(c.o, c.h, c.l, c.c))):
        o, h, l, cl = bars
        zone = (lambda lo, hi: (lo, hi)) if direction == BEAR else (lambda lo, hi: (-hi, -lo))
        for _j, i, lo, hi in bearish_order_blocks(o, h, l, cl):
            out.append(_Array(direction, "OB", c.tf, *zone(lo, hi), int(c.end[i])))
        for k, lo, hi in bearish_breakers(o, h, l, cl):
            out.append(_Array(direction, "BREAKER", c.tf, *zone(lo, hi), int(c.end[k])))
        for k, lo, hi in bearish_fvgs(h, l, 0, len(c)):
            out.append(_Array(direction, "FVG", c.tf, *zone(lo, hi), int(c.end[k])))
    return out


def _first_touch(bars: Candles, direction: BiasDirection, edge: float, since: int,
                 until: Optional[int] = None) -> Optional[int]:
    """The open of the first bar opening in [since, until) that traded into a zone whose near edge is ``edge``."""
    a = int(np.searchsorted(bars.t, since, "left"))
    b = len(bars) if until is None else int(np.searchsorted(bars.t, until, "left"))
    if a >= b:
        return None
    k = np.flatnonzero(bars.l[a:b] <= edge if direction == BULL else bars.h[a:b] >= edge)
    return int(bars.t[a + k[0]]) if len(k) else None


def _poi(direction: BiasDirection, arrays: Sequence[_Array], price: float, rng: DealingRange, formed: int,
         touch: Candles) -> Optional[ArrayPOI]:
    """The nearest array of ``direction`` on the far side of price whose near edge is in the matching zone, and
    that wasn't traded into between its forming and the dealing range's (CE-D2). Reached once a bar trades into
    it after both."""
    width = rng.high - rng.low
    found = []
    for a in arrays:
        if a.direction != direction:
            continue
        if direction == BULL and not (a.high <= rng.low + DISCOUNT_BELOW * width and a.low < price):
            continue
        if direction == BEAR and not (a.low >= rng.low + PREMIUM_FROM * width and a.high > price):
            continue
        if a.formed_at < formed and _first_touch(touch, direction, a.edge, a.formed_at, formed) is not None:
            continue                                     # spent before this range formed
        found.append(a)
    if not found:
        return None
    sign = -1 if direction == BULL else 1                # nearest: the highest support, the lowest resistance
    a = min(found, key=lambda x: (sign * x.edge, -_weight(x.tf), _ARRAY_ORDER[x.kind], -x.formed_at))
    return ArrayPOI(direction, a.kind, a.tf, a.low, a.high, a.formed_at,
                    _first_touch(touch, direction, a.edge, max(a.formed_at, formed)))


def _trend(c: Candles) -> Tuple[BiasDirection, str]:
    """LE-D15 at any frame: the last closed candle closed beyond the previous candle's range."""
    if len(c) < 2:
        return NEUTRAL, "fewer than two closed candles: not trending"
    close, high, low = float(c.c[-1]), float(c.h[-2]), float(c.l[-2])
    if close > high:
        return BULL, f"closed {close:.5g} above the previous high {high:.5g}"
    if close < low:
        return BEAR, f"closed {close:.5g} below the previous low {low:.5g}"
    return NEUTRAL, f"closed {close:.5g} inside the previous range {low:.5g}-{high:.5g}: not trending"


def frame_state(frame: Candles, price: float, parents: Sequence[Candles] = (), lower: Sequence[Candles] = (),
                path: Optional[Candles] = None, forming: Optional[Tuple[float, float]] = None,
                levels: Sequence[Objective] = (), asia: Optional[Tuple[float, float, int]] = None) -> FrameState:
    """The frame's state at ``price`` (Requirement 3.1).

    - ``frame``: its closed candles; ``forming``: the forming candle's (high, low) so far, which stretch the range.
    - ``parents``: the frames above, closed candles; their pools, previous candle and gaps are objectives and their
      arrays POI candidates. ``lower``: frames below whose pools and gaps also count (the candle profile reads H4).
    - ``path``: the finest closed bars to t. Every source decides whether an objective was taken; POIs are timed on
      ``path``, or on the frame's own candles without one.
    - ``levels``: more objectives (the IPDA ranges); ``asia``: (low, high, formed at), read at D1 and below.
    """
    rng = dealing_range(frame.h, frame.l, len(frame), *(forming or (None, None)))
    reasons: Dict[str, str] = {}
    if rng is None:
        formed, position, zone = None, None, None
        reasons["range"] = "UNRANGED: no confirmed swing on a side"
        reasons["zone"] = "no zone without a range"
    else:
        formed = int(frame.end[max(rng.anchors)])
        position, zone = rng.position(price), rng.zone(price)
        reasons["range"] = (f"{rng.reason()} from the swings at candles {rng.low_at} and {rng.high_at} "
                            f"of {len(frame)}")
        reasons["zone"] = f"price {price:.5g} at {position:.0%}: {zone}"

    found = _objectives(frame, previous=True)
    for p in parents:
        found += _objectives(p, previous=True)
    for x in lower:
        found += _objectives(x, previous=False)
    found += list(levels)
    if asia is not None and _weight(frame.tf) <= _weight("D1"):
        low, high, at = asia
        found += [Objective("POOL", "ASIA_HIGH", frame.tf, float(high), BULL, int(at)),
                  Objective("POOL", "ASIA_LOW", frame.tf, float(low), BEAR, int(at))]
    later = _Later([frame, *parents, *lower, *([path] if path is not None else [])])
    live = [x for x in found if not later.taken(x)]
    above = tuple(sorted((x for x in live if x.direction == BULL and x.price > price),
                         key=lambda x: (x.price, *_tie(x))))
    below = tuple(sorted((x for x in live if x.direction == BEAR and x.price < price),
                         key=lambda x: (-x.price, *_tie(x))))
    reasons["objectives"] = (f"{len(above)} above (nearest {above[0].reason() if above else 'none'}), "
                             f"{len(below)} below (nearest {below[0].reason() if below else 'none'})")

    trend, reasons["trend"] = _trend(frame)
    state = FrameState(frame.tf, float(price), rng, formed, position, zone, above, below, trend, NEUTRAL, None)
    if trend != NEUTRAL:
        draw = state.nearest(trend)
        own = trend if draw is not None else NEUTRAL
        reasons["own"] = (f"trending {trend.value}, toward {draw.reason()}" if draw is not None else
                          f"trending {trend.value} with nothing on that side: NEUTRAL")
    else:
        own, draw = state.nearer()
        reasons["own"] = (f"not trending, toward the nearer {draw.reason()}" if draw is not None else
                          "not trending, and neither side nearer: NEUTRAL")

    pois: Dict[BiasDirection, Optional[ArrayPOI]] = {BULL: None, BEAR: None}
    if rng is not None:
        arrays = _arrays(frame) + [a for p in parents for a in _arrays(p)]
        touch = path if path is not None else frame
        pois = {d: _poi(d, arrays, price, rng, formed, touch) for d in (BULL, BEAR)}
    for d, key in ((BULL, "poi_bullish"), (BEAR, "poi_bearish")):
        reasons[key] = pois[d].reason() if pois[d] is not None else (
            "none: no range" if rng is None else f"none: no {d.value.lower()} array in its zone")
    return FrameState(frame.tf, float(price), rng, formed, position, zone, above, below, trend, own, draw, pois,
                      reasons)
