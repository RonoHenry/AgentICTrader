"""The trader's trend (context-engine update 2026-10-23, Requirement 20).

The trader reads a trend fractally, mostly on the parent timeframe from H1 up. A bearish one shows:
1. lower highs and lower lows;
2. consecutive bearish closes;
3. buy-side liquidity swept, with price failing to displace higher;
4. bearish arrays respected while bullish arrays are traded through;
5. bearish PO3 in the down-close candles.

The bullish trend is the mirror. Each closed candle of a frame gets the five signals, each -1 (bearish), +1
(bullish) or 0, read from that frame's closed candles only (MA-D18, MA-D19):

- **structure:** the last two three-candle swing highs and lows known by the candle's close. Lower high and lower
  low is -1, higher high and higher low +1. A swing at k is known at k+1's close.
- **closes:** the candle closed down and at least two of the last three did: -1 (the mirror +1).
- **liquidity:** the most recent sweep that failed. A candle trading above an untaken three-candle swing high and
  closing back below the highest one it took is a failed buy-side sweep (-1), active until a later close above its
  wick. A failed sell-side sweep is the mirror (+1).
- **arrays:** over the last ``ARRAY_WINDOW`` candles, bearish evidence (bearish arrays traded into and not closed
  beyond, and bullish arrays closed through) against bullish evidence (the mirror). The arrays are the frame's
  FVGs and order blocks (``algo_research.atlas.arrays``). Each array counts once per candle.
- **po3:** among the last three candles, bearish PO3s against bullish ones. A bearish PO3 is a down close whose high
  is at least ``PO3_WICK`` of its range above the open and whose close is within ``PO3_CLOSE`` of its range from
  the low.

The trend is their sum: -1 at -3 or below, +1 at +3 or above, otherwise 0 (MA-D20). No value reads a candle after
the one it labels (Property 2).

    signals = trend_signals(frame.bars[Timeframe.H1], arrays_of_h1)      # one row per closed candle

A trend call (the trader's, on Noculus, Requirement 23) is scored by ``call_outcome`` from the minutes before the
replay clock only, the way task 356 scored the reader: the next move, one average range each way, and continuation,
the call's side's last swing taken first, beside the chance a driftless walk has of the same.

Validates: Requirements 20, 23 (.kiro/specs/context-engine/requirements.md)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

__all__ = ["ARRAY_WINDOW", "COLUMNS", "PO3_CLOSE", "PO3_WICK", "SIGNALS", "TREND_AT", "call_outcome", "swing_highs",
           "swing_lows", "trend_signals"]

ARRAY_WINDOW = 20
PO3_WICK, PO3_CLOSE = 0.2, 0.3
TREND_AT = 3
SIGNALS = ("structure", "closes", "liquidity", "arrays", "po3")
COLUMNS = SIGNALS + ("score", "trend")


def _ns(values) -> np.ndarray:
    index = pd.DatetimeIndex(values)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    return index.tz_localize(None).to_numpy("datetime64[ns]").view(np.int64)


def _swing_highs(h: np.ndarray) -> np.ndarray:
    k = np.arange(1, len(h) - 1)
    return k[(h[k] > h[k - 1]) & (h[k] > h[k + 1])]


def _swing_lows(l: np.ndarray) -> np.ndarray:
    k = np.arange(1, len(l) - 1)
    return k[(l[k] < l[k - 1]) & (l[k] < l[k + 1])]


def _structure(h: np.ndarray, l: np.ndarray) -> np.ndarray:
    n = len(h)
    out = np.zeros(n, dtype=np.int64)
    highs, lows = _swing_highs(h), _swing_lows(l)
    for i in range(n):
        known_h = highs[: np.searchsorted(highs + 1, i, "right")]           # swings whose third candle closed
        known_l = lows[: np.searchsorted(lows + 1, i, "right")]
        if len(known_h) < 2 or len(known_l) < 2:
            continue
        lower_high, higher_high = h[known_h[-1]] < h[known_h[-2]], h[known_h[-1]] > h[known_h[-2]]
        lower_low, higher_low = l[known_l[-1]] < l[known_l[-2]], l[known_l[-1]] > l[known_l[-2]]
        out[i] = -1 if (lower_high and lower_low) else 1 if (higher_high and higher_low) else 0
    return out


def _closes(o: np.ndarray, c: np.ndarray) -> np.ndarray:
    d = np.sign(c - o)
    out = np.zeros(len(c), dtype=np.int64)
    for i in range(len(c)):
        last = d[max(0, i - 2): i + 1]
        if d[i] < 0 and (last < 0).sum() >= 2:
            out[i] = -1
        elif d[i] > 0 and (last > 0).sum() >= 2:
            out[i] = 1
    return out


def _liquidity(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    n = len(c)
    out = np.zeros(n, dtype=np.int64)
    highs, lows = set(_swing_highs(h).tolist()), set(_swing_lows(l).tolist())
    untaken_h: list[float] = []
    untaken_l: list[float] = []
    active: Optional[tuple[int, float, int]] = None            # (side, wick, candle): -1 failed buy-side sweep
    for j in range(n):
        if active is not None and active[2] < j:                # a later close beyond the sweep's wick ends it
            if (active[0] == -1 and c[j] > active[1]) or (active[0] == 1 and c[j] < active[1]):
                active = None
        taken = [lv for lv in untaken_h if h[j] > lv]
        if taken:
            untaken_h = [lv for lv in untaken_h if lv >= h[j]]
            if c[j] < max(taken):
                active = (-1, h[j], j)
        taken = [lv for lv in untaken_l if l[j] < lv]
        if taken:
            untaken_l = [lv for lv in untaken_l if lv <= l[j]]
            if c[j] > min(taken):
                active = (1, l[j], j)
        out[j] = 0 if active is None else active[0]
        if j - 1 in highs:                                      # the swing at j-1 is known at j's close
            untaken_h.append(h[j - 1])
        if j - 1 in lows:
            untaken_l.append(l[j - 1])
    return out


def _intervals(starts: np.ndarray, length: int, end: int) -> list[tuple[int, int]]:
    """The union of [s, s + length - 1] for each start, cut at ``end`` (exclusive), as merged intervals."""
    merged: list[tuple[int, int]] = []
    for s in starts:
        a, b = int(s), min(int(s) + length - 1, end - 1)
        if a > b:
            continue
        if merged and a <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def _arrays(bars: pd.DataFrame, arrays: Optional[pd.DataFrame]) -> np.ndarray:
    n = len(bars)
    out = np.zeros(n, dtype=np.int64)
    if arrays is None or arrays.empty or n == 0:
        return out
    h, l = bars["high"].to_numpy(float), bars["low"].to_numpy(float)
    close = _ns(bars["close_time"])
    bear, bull = np.zeros(n + 1), np.zeros(n + 1)            # difference arrays: evidence counts per candle
    formed = np.searchsorted(close, _ns(arrays["formed_at"]), "left")
    flipped_at = pd.DatetimeIndex(arrays["flipped_at"])
    has_flip = ~flipped_at.isna()
    flip = np.full(len(arrays), n, dtype=np.int64)
    if has_flip.any():
        flip[has_flip] = np.searchsorted(close, _ns(flipped_at[has_flip]), "left")
    for k, (direction, low, high) in enumerate(zip(arrays["direction"], arrays["low"], arrays["high"])):
        start, stop = int(formed[k]) + 1, min(int(flip[k]), n)
        if start < stop:
            seg = l[start:stop] <= high if direction > 0 else h[start:stop] >= low
            for a, b in _intervals(start + np.flatnonzero(seg), ARRAY_WINDOW, stop):
                side = bull if direction > 0 else bear              # respected: evidence for its own side
                side[a] += 1
                side[b + 1] -= 1
        if flip[k] < n:
            a, b = int(flip[k]), min(int(flip[k]) + ARRAY_WINDOW - 1, n - 1)
            side = bear if direction > 0 else bull                  # traded through: evidence for the other side
            side[a] += 1
            side[b + 1] -= 1
    return np.sign(np.cumsum(bull)[:n] - np.cumsum(bear)[:n]).astype(np.int64)


def _po3(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    rng = h - l
    with np.errstate(invalid="ignore", divide="ignore"):
        bear = (c < o) & (h - o >= PO3_WICK * rng) & (c - l <= PO3_CLOSE * rng) & (rng > 0)
        bull = (c > o) & (o - l >= PO3_WICK * rng) & (h - c <= PO3_CLOSE * rng) & (rng > 0)
    out = np.zeros(len(c), dtype=np.int64)
    for i in range(len(c)):
        a = max(0, i - 2)
        out[i] = int(np.sign(bull[a: i + 1].sum() - bear[a: i + 1].sum()))
    return out


def trend_signals(bars: pd.DataFrame, arrays: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """The five signals, their sum and the trend for each closed candle of one frame. ``bars`` holds the frame's
    candles (open, high, low, close, close_time), oldest first; ``arrays`` its FVGs and order blocks (kind,
    direction, low, high, formed_at, flipped_at), or None."""
    o, h, l, c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    out = pd.DataFrame({
        "structure": _structure(h, l),
        "closes": _closes(o, c),
        "liquidity": _liquidity(h, l, c),
        "arrays": _arrays(bars.reset_index(drop=True), arrays),
        "po3": _po3(o, h, l, c),
    })
    out["score"] = out[list(SIGNALS)].sum(axis=1)
    out["trend"] = np.where(out["score"] <= -TREND_AT, -1, np.where(out["score"] >= TREND_AT, 1, 0))
    return out[list(COLUMNS)]


swing_highs, swing_lows = _swing_highs, _swing_lows
NEXT_CANDLES, ATR_CANDLES = 3, 14


def _first_beyond(values: np.ndarray, level: float, above: bool) -> int:
    hit = np.flatnonzero(values >= level if above else values <= level)
    return int(hit[0]) if len(hit) else -1


def _first_strictly(values: np.ndarray, level: float, above: bool) -> int:
    hit = np.flatnonzero(values > level if above else values < level)
    return int(hit[0]) if len(hit) else -1


def _race(up: int, down: int, side: int) -> Optional[str]:
    """RIGHT when the call's side came first, WRONG when the other did or both came in one minute; None if neither."""
    if up < 0 and down < 0:
        return None
    if up >= 0 and down >= 0 and up == down:
        return "WRONG"
    first_up = down < 0 or (up >= 0 and up < down)
    return "RIGHT" if first_up == (side > 0) else "WRONG"


def call_outcome(side: int, t: int, size: int, bars: pd.DataFrame, m1: dict, clock: int) -> dict:
    """How a trend call made at ``t`` (wall seconds) on a frame of ``size`` seconds stood at ``clock``.

    ``side`` is -1 bearish or +1 bullish. ``bars`` holds the frame's candles (``time`` their open in wall seconds;
    open, high, low, close), ``m1`` the minutes (``time`` each minute's open in wall seconds; open, high, low).
    Only the candles closed by ``t`` and the minutes opening before ``clock`` are read.

    - ``next``: one average range (the last ``ATR_CANDLES`` closed candles) each way from the first open at or after
      ``t``, within ``NEXT_CANDLES`` candles: RIGHT, WRONG, PENDING while the window is still open, or UNRESOLVED.
    - ``cont``: price beyond the last three-candle swing on the call's side before the one on the other side: RIGHT,
      WRONG or PENDING; None when the price is not between them. ``geometry`` is a driftless walk's chance of the
      same from the first open.
    """
    times = np.asarray(bars["time"], dtype=np.int64)
    closed = int(np.count_nonzero(times + size <= t))
    h, l = (np.asarray(bars[k], dtype=float)[:closed] for k in ("high", "low"))
    mt = np.asarray(m1["time"], dtype=np.int64)
    a, b = int(np.searchsorted(mt, t, "left")), int(np.searchsorted(mt, clock, "left"))
    out = {"next": None, "cont": None, "geometry": None, "atr": None, "ref": None}
    if closed < ATR_CANDLES:
        return out
    if a >= b:                                                              # no minute since the call, yet
        out["next"] = "PENDING"
        return out
    mo, mh, ml = (np.asarray(m1[k], dtype=float) for k in ("open", "high", "low"))
    ref = float(mo[a])
    atr = float(np.mean(h[-ATR_CANDLES:] - l[-ATR_CANDLES:]))
    out.update(atr=atr, ref=ref)
    window_end = t + NEXT_CANDLES * size
    stop = min(b, int(np.searchsorted(mt, window_end, "left")))
    race = _race(_first_beyond(mh[a:stop], ref + atr, True), _first_beyond(ml[a:stop], ref - atr, False), side)
    out["next"] = race or ("PENDING" if clock < window_end else "UNRESOLVED")
    highs = swing_highs(h)
    lows = swing_lows(l)
    highs, lows = highs[highs + 1 < closed], lows[lows + 1 < closed]       # known: their third candle closed by t
    if len(highs) and len(lows):
        top, bottom = float(h[highs[-1]]), float(l[lows[-1]])
        if bottom < ref < top:
            race = _race(_first_strictly(mh[a:b], top, True), _first_strictly(ml[a:b], bottom, False), side)
            out["cont"] = race or "PENDING"
            out["geometry"] = (top - ref) / (top - bottom) if side < 0 else (ref - bottom) / (top - bottom)
    return out
