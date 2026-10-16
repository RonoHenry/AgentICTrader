"""Arrays as the user reads them (algo-research update 2026-10g, Requirement 23).

One table per instrument, one row per array, oldest first:

    tf, kind (FVG / OB), direction (+1 bullish, -1 bearish), low, high, mid, formed_at, flipped_at

- **FVG** (AR-D27, the user's definition): three closed candles C1, C2, C3 of one timeframe.
  - It is bullish when C3's low is above C1's high: the gap runs from C1's high to C3's low.
  - It is bearish when C1's low is above C3's high.
  - ``mid`` is the CE, and ``formed_at`` is C3's close.
  - Trading into the gap doesn't end it. ``flipped_at`` is the first close of a bar of its timeframe beyond
    the far edge; from then on it reads as an IFVG facing the other way.
- **Order block:** the engine's rule (``measures.bearish_order_blocks``, and its mirror for the bullish side).
  - It is the last opposite candle before a displacement of at least 1.5 ATR, formed at the displacement's
    close.
  - ``mid`` is the MT, the midpoint of the order-block candle's body.
  - ``flipped_at`` is the first close beyond it; from then on it reads as a breaker.

Every value is read from bars closed by the time it carries. So the arrays known at t are the same whether or
not later bars exist (Property 1).

    table = build_arrays(frame)            # every timeframe of an InstrumentFrame
    state_at(table, t)                     # the arrays formed by t: name (FVG / IFVG / OB / BRK) and facing

Validates: Requirement 23 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from algo_research.frame import InstrumentFrame
from liquidity_engine.context.measures import bearish_order_blocks, mirror
from liquidity_engine.models import Timeframe

__all__ = ["ARRAY_TIMEFRAMES", "COLUMNS", "build_arrays", "fvgs", "order_blocks", "state_at"]

#: The timeframes arrays are read on (AR-D31).
ARRAY_TIMEFRAMES = (Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1)
COLUMNS = ["tf", "kind", "direction", "low", "high", "mid", "formed_at", "flipped_at"]

_WINDOW = 64            # the first look ahead for a flip; doubled until found or the bars run out


def _times(values) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(np.asarray(values, dtype="datetime64[ns]")).tz_localize("UTC")


def _table(tf: Timeframe, kind: str, direction, low, high, mid, formed_at, flipped_at) -> pd.DataFrame:
    n = len(low)
    return pd.DataFrame({
        "tf": np.full(n, tf.value, dtype=object), "kind": np.full(n, kind, dtype=object),
        "direction": np.asarray(direction, dtype=np.int64), "low": np.asarray(low, dtype=float),
        "high": np.asarray(high, dtype=float), "mid": np.asarray(mid, dtype=float),
        "formed_at": _times(formed_at), "flipped_at": _times(flipped_at),
    }, columns=COLUMNS)


def _first_close_beyond(close: np.ndarray, start: int, level: float, below: bool) -> int:
    """The first index >= ``start`` whose close is below (or above) ``level``; -1 if none."""
    window = _WINDOW
    while start < len(close):
        segment = close[start:start + window]
        hits = segment < level if below else segment > level
        if hits.any():
            return start + int(np.argmax(hits))
        start += window
        window *= 2
    return -1


def _flips(close: np.ndarray, close_time: np.ndarray, starts, levels, below) -> np.ndarray:
    out = np.full(len(starts), np.datetime64("NaT"), dtype="datetime64[ns]")
    for n, (start, level, is_below) in enumerate(zip(starts, levels, below)):
        j = _first_close_beyond(close, int(start), float(level), bool(is_below))
        if j >= 0:
            out[n] = close_time[j]
    return out


def _arrays_of(bars: pd.DataFrame):
    o, h, l, c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    close_time = pd.DatetimeIndex(bars["close_time"]).tz_convert("UTC").tz_localize(None).to_numpy("datetime64[ns]")
    return o, h, l, c, close_time


def fvgs(bars: pd.DataFrame, tf: Timeframe) -> pd.DataFrame:
    """The FVGs of one timeframe's closed bars (columns time, close_time, open, high, low, close)."""
    _, h, l, c, close_time = _arrays_of(bars)
    k = np.arange(2, len(h))
    bull, bear = k[l[k] > h[k - 2]], k[h[k] < l[k - 2]]
    third = np.concatenate([bull, bear])
    direction = np.concatenate([np.ones(len(bull), np.int64), -np.ones(len(bear), np.int64)])
    low = np.concatenate([h[bull - 2], h[bear]])
    high = np.concatenate([l[bull], l[bear - 2]])
    order = np.lexsort((-direction, third))                     # oldest first; bullish before bearish
    third, direction, low, high = third[order], direction[order], low[order], high[order]
    # The far edge: the low of a bullish gap, the high of a bearish one.
    flipped = _flips(c, close_time, third + 1, np.where(direction == 1, low, high), direction == 1)
    return _table(tf, "FVG", direction, low, high, (low + high) / 2, close_time[third], flipped)


def order_blocks(bars: pd.DataFrame, tf: Timeframe) -> pd.DataFrame:
    """The order blocks of one timeframe's closed bars, by the engine's rule, each with its MT."""
    o, h, l, c, close_time = _arrays_of(bars)
    rows = [(ob, expansion, -1, low, high) for ob, expansion, low, high in bearish_order_blocks(o, h, l, c)]
    mo, mh, ml, mc = mirror(o, h, l, c)
    rows += [(ob, expansion, 1, -mhigh, -mlow) for ob, expansion, mlow, mhigh in bearish_order_blocks(mo, mh, ml, mc)]
    rows.sort(key=lambda r: (r[1], -r[2]))                      # by the displacement's close; bullish first
    if not rows:
        return _table(tf, "OB", [], [], [], [], [], [])
    ob, expansion, direction, low, high = (np.array(col) for col in zip(*rows))
    # A bearish block flips when a close goes above it, a bullish one when a close goes below it.
    flipped = _flips(c, close_time, expansion + 1, np.where(direction == 1, low, high), direction == 1)
    return _table(tf, "OB", direction, low, high, (o[ob] + c[ob]) / 2, close_time[expansion], flipped)


def build_arrays(frame: InstrumentFrame, timeframes: Iterable[Timeframe] = ARRAY_TIMEFRAMES) -> pd.DataFrame:
    """Every FVG and order block of the frame's calendar bars, on each of ``timeframes``, oldest first."""
    parts = []
    for tf in timeframes:
        bars = frame.bars.get(tf)
        if bars is None or bars.empty:
            continue
        parts += [fvgs(bars, tf), order_blocks(bars, tf)]
    if not parts:
        return _table(Timeframe.H1, "FVG", [], [], [], [], [], [])
    return pd.concat(parts, ignore_index=True).sort_values("formed_at", kind="stable").reset_index(drop=True)


def state_at(table: pd.DataFrame, t) -> pd.DataFrame:
    """The arrays formed by ``t``, with their state at ``t``: ``name`` FVG, IFVG, OB or BRK, and ``facing``,
    the direction they now support (an inverted array faces the other way)."""
    t = pd.Timestamp(t)
    known = table[table["formed_at"] <= t].copy()
    flipped = (known["flipped_at"].notna() & (known["flipped_at"] <= t)).to_numpy()
    is_fvg = (known["kind"] == "FVG").to_numpy()
    known["name"] = np.where(is_fvg, np.where(flipped, "IFVG", "FVG"), np.where(flipped, "BRK", "OB"))
    known["facing"] = np.where(flipped, -known["direction"].to_numpy(), known["direction"].to_numpy())
    return known.reset_index(drop=True)
