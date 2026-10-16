"""Swings and what they delivered (algo-research update 2026-10g, Requirement 24).

The user (2026-10-16): "Price cannot reverse or retrace without a swing point, and a swing point can only be
formed by three candles." Every swing of a timeframe is found and scored:

- **three** (AR-D28): a bar C2 whose low is below both neighbours' lows, strictly. It is known at C3's close.
- **engulf** (AR-D29, the user's variation): a bar B that trades below the previous bar A's low and closes
  above A's body. Its extreme is B's low, known at B's close.
  - ``engulf_full`` marks a close above A's high too.
  - ``twin`` marks an extreme that is both types.
- Highs are the mirror. They are read on the prices turned upside down, so the code exists once.

The objectives of a swing low (AR-D30) are prices above it, fixed when it is known:

- ``crt``: the high of the bar before the extreme bar (the candle range's other side).
- ``same_tf``: the origin of the leg into the swing, the highest high from T's last three-candle swing high up
  to the bar before the extreme bar.
- ``next_tf``: the most recent three-candle swing high of the next timeframe up that is known, untaken and
  above the extreme when the swing is known.

Each objective's outcome is settled on M1 from the first bar opening at or after the swing is known:
- **held**: a high above the objective;
- **failed**: a low below the extreme;
- **open**: neither, by ``until``. Both sides are strict, so a touch is neither (AR-D33). One M1 bar doing
  both is failed (the stop wins, as in races).

An objective traded beyond after the extreme's own M1 bar but before the swing is known is held at once.
``geo_<objective>`` is the geometry (AR-D33): the chance that a driftless random walk from the confirming close
(C3's, or the engulfing bar's) reaches the objective before the extreme, (close - extreme) / (objective -
extreme), clipped to [0, 1]. It is 1 for an objective held at once.
``excursion`` is the farthest high before the extreme is taken, in T's average range: the mean high minus low
of the 20 bars before the extreme bar (measures.rolling_average_range).

    build_swings(frame, Timeframe.H1, until=end)   # one row per swing, both sides, both types

Validates: Requirement 24 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from algo_research.frame import InstrumentFrame
from liquidity_engine.context.measures import mirror, rolling_average_range
from liquidity_engine.models import Timeframe

__all__ = ["COLUMNS", "NEXT_TF", "OBJECTIVES", "SWING_TIMEFRAMES", "build_swings", "find_swings"]

#: The timeframes swings are read on (AR-D31); W1 is counted, not judged.
SWING_TIMEFRAMES = (Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1)
NEXT_TF = {Timeframe.M15: Timeframe.H1, Timeframe.H1: Timeframe.H4, Timeframe.H4: Timeframe.D1,
           Timeframe.D1: Timeframe.W1}
OBJECTIVES = ("crt", "same_tf", "next_tf")
COLUMNS = (["tf", "side", "type", "extreme", "extreme_bar", "extreme_time", "known_at", "engulf_full", "twin",
            "avg_range", "excursion"]
           + [f"{field}_{o}" for o in OBJECTIVES for field in ("obj", "out", "at_once", "resolved", "bars", "geo")])

_MINUTE = 60 * 1_000_000_000
_WINDOW = 64


# ── finding swings ─────────────────────────────────────────────────────────

def _lows(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> pd.DataFrame:
    """The swing lows of bars (three-candle and engulfing), oldest first: i, type, extreme, engulf_full, twin."""
    n = len(l)
    k = np.arange(1, n - 1)
    three = k[(l[k] < l[k - 1]) & (l[k] < l[k + 1])]
    j = np.arange(1, n)
    engulf = j[(l[j] < l[j - 1]) & (c[j] > np.maximum(o[j - 1], c[j - 1]))]
    three_set, engulf_set = set(three.tolist()), set(engulf.tolist())
    table = pd.DataFrame({
        "i": np.concatenate([three, engulf]).astype(np.int64),
        "type": np.array(["three"] * len(three) + ["engulf"] * len(engulf), dtype=object),
        "extreme": np.concatenate([l[three], l[engulf]]),
        "engulf_full": np.concatenate([np.zeros(len(three), bool), c[engulf] > h[engulf - 1]]),
        "twin": np.array([i in engulf_set for i in three.tolist()] + [i in three_set for i in engulf.tolist()],
                         dtype=bool),
    })
    return table.sort_values(["i", "type"], ascending=[True, False], kind="stable").reset_index(drop=True)


def _ohlc(bars: pd.DataFrame):
    return tuple(bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))


def find_swings(bars: pd.DataFrame) -> pd.DataFrame:
    """Every swing of one timeframe's bars: i (the extreme bar), side, type, extreme, engulf_full, twin."""
    o, h, l, c = _ohlc(bars)
    lows = _lows(o, h, l, c).assign(side="low")
    highs = _lows(*mirror(o, h, l, c)).assign(side="high")
    highs["extreme"] = -highs["extreme"]
    return pd.concat([lows, highs], ignore_index=True)[["i", "side", "type", "extreme", "engulf_full", "twin"]]


# ── scoring ────────────────────────────────────────────────────────────────

def _ns(times) -> np.ndarray:
    index = pd.DatetimeIndex(times)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    return index.tz_localize(None).to_numpy("datetime64[ns]").view(np.int64)


def _first(values: np.ndarray, start: int, stop: int, level: float, below: bool) -> int:
    """The first index in [start, stop) whose value is below ``level`` (or at or above it); -1 if none."""
    window = _WINDOW
    while start < stop:
        segment = values[start:min(stop, start + window)]
        hits = segment < level if below else segment >= level
        if hits.any():
            return start + int(np.argmax(hits))
        start += window
        window *= 2
    return -1


def _three_highs(h: np.ndarray) -> np.ndarray:
    k = np.arange(1, len(h) - 1)
    return k[(h[k] > h[k - 1]) & (h[k] > h[k + 1])]


def _next_tf_highs(next_bars: Optional[tuple], m1_t: np.ndarray, m1_h: np.ndarray, end: int):
    """The next timeframe's three-candle swing highs: price, known time, and the open time of the first M1 bar
    that traded above it after it was known (int64 max if none)."""
    if next_bars is None:
        return np.empty(0), np.empty(0, np.int64), np.empty(0, np.int64)
    nh, close_times = next_bars
    peaks = _three_highs(nh)
    price, known = nh[peaks], close_times[peaks + 1]
    taken = np.full(len(peaks), np.iinfo(np.int64).max, dtype=np.int64)
    for n, (p, k) in enumerate(zip(price, known)):
        # Taken means traded above it; a high at the level only touches it.
        above = _first(m1_h, int(np.searchsorted(m1_t, k, "left")), end, np.nextafter(float(p), np.inf), below=False)
        if above >= 0:
            taken[n] = m1_t[above]
    return price, known, taken


def _score_lows(bars: tuple, times: np.ndarray, close_times: np.ndarray, m1: tuple, next_bars: Optional[tuple],
                since: int, until: int) -> pd.DataFrame:
    """Swing lows of oriented prices (highs come in mirrored), scored against their objectives."""
    o, h, l, c = bars
    m1_t, m1_h, m1_l = m1
    end = int(np.searchsorted(m1_t, until, "left"))                       # outcomes read M1 before ``until``
    swings = _lows(o, h, l, c)
    i = swings["i"].to_numpy()
    known_idx = np.where(swings["type"].to_numpy() == "three", i + 1, i)
    keep = known_idx < len(close_times)
    swings, i, known_idx = swings[keep].reset_index(drop=True), i[keep], known_idx[keep]
    known_at = close_times[known_idx]
    keep = (known_at >= since) & (known_at <= until)
    swings, i, known_idx, known_at = swings[keep].reset_index(drop=True), i[keep], known_idx[keep], known_at[keep]
    n = len(swings)
    extreme = swings["extreme"].to_numpy()
    avg = rolling_average_range(h, l)[i] if n else np.empty(0)
    highs = _three_highs(h)
    peak_price, peak_known, peak_taken = _next_tf_highs(next_bars, m1_t, m1_h, end)

    out = {"extreme_time": np.zeros(n, np.int64), "excursion": np.full(n, np.nan)}
    objectives = {o_: np.full(n, np.nan) for o_ in OBJECTIVES}
    results = {o_: (np.full(n, None, dtype=object), np.zeros(n, bool), np.full(n, np.iinfo(np.int64).min, np.int64),
                    np.full(n, np.nan), np.full(n, np.nan)) for o_ in OBJECTIVES}
    for s in range(n):
        bar = i[s]
        lo = int(np.searchsorted(m1_t, times[bar], "left"))
        hi = int(np.searchsorted(m1_t, close_times[bar], "left"))
        e_idx = lo + int(np.argmin(m1_l[lo:hi])) if hi > lo else lo
        out["extreme_time"][s] = m1_t[e_idx] if e_idx < len(m1_t) else times[bar]
        start = int(np.searchsorted(m1_t, known_at[s], "left"))
        taken = _first(m1_l, start, end, extreme[s], below=True)
        stop = taken if taken >= 0 else end
        before = m1_h[e_idx + 1:stop]
        out["excursion"][s] = (before.max() - extreme[s]) / avg[s] if before.size and avg[s] > 0 else 0.0

        objectives["crt"][s] = h[bar - 1]
        pos = int(np.searchsorted(highs, bar, "left")) - 1
        if pos >= 0:
            objectives["same_tf"][s] = h[highs[pos]:bar].max()
        if len(peak_price):
            ok = (peak_known <= known_at[s]) & (peak_taken >= known_at[s]) & (peak_price > extreme[s])
            if ok.any():
                objectives["next_tf"][s] = peak_price[np.flatnonzero(ok)[-1]]

        early = m1_h[e_idx + 1:start]
        for name in OBJECTIVES:
            target = objectives[name][s]
            if np.isnan(target) or target <= extreme[s]:
                objectives[name][s] = np.nan
                continue
            outcome, at_once, resolved, bars_to, geo = results[name]
            if early.size and early.max() > target:
                outcome[s], at_once[s], resolved[s], bars_to[s], geo[s] = "held", True, known_at[s], 0, 1.0
                continue
            geo[s] = min(1.0, max(0.0, (c[known_idx[s]] - extreme[s]) / (target - extreme[s])))
            beyond = np.nextafter(target, np.inf)                           # strict: a touch is not held
            reach = _first(m1_h, start, stop + 1 if taken >= 0 else end, beyond, below=False)
            if reach >= 0 and (taken < 0 or reach < taken):
                outcome[s], resolved[s] = "held", m1_t[reach] + _MINUTE
            elif taken >= 0:
                outcome[s], resolved[s] = "failed", m1_t[taken] + _MINUTE
            else:
                outcome[s] = "open"
                continue
            bars_to[s] = int(np.searchsorted(close_times, resolved[s] - _MINUTE, "right")) - known_idx[s]

    table = pd.DataFrame({
        "type": swings["type"], "extreme": extreme, "extreme_bar": times[i], "extreme_time": out["extreme_time"],
        "known_at": known_at, "engulf_full": swings["engulf_full"], "twin": swings["twin"], "avg_range": avg,
        "excursion": out["excursion"],
    })
    for name in OBJECTIVES:
        outcome, at_once, resolved, bars_to, geo = results[name]
        table[f"obj_{name}"], table[f"out_{name}"], table[f"at_once_{name}"] = objectives[name], outcome, at_once
        table[f"resolved_{name}"], table[f"bars_{name}"], table[f"geo_{name}"] = resolved, bars_to, geo
    return table


def _times(values: np.ndarray) -> pd.Series:
    out = pd.Series(values, dtype=np.int64)
    out = out.where(out != np.iinfo(np.int64).min)
    return pd.to_datetime(out, utc=True)


def build_swings(frame: InstrumentFrame, tf: Timeframe, since=None, until=None) -> pd.DataFrame:
    """Every swing of ``tf`` known in [since, until], both sides and types, scored against its objectives on the
    M1 bars before ``until`` (default: all of the frame)."""
    bars = frame.bars[tf]
    columns = COLUMNS
    if bars.empty:
        return pd.DataFrame(columns=columns)
    times, close_times = _ns(bars["time"]), _ns(bars["close_time"])
    m1_t = frame.arrays["time"]
    since_ns = _ns([since])[0] if since is not None else np.iinfo(np.int64).min
    until_ns = _ns([until])[0] if until is not None else (int(m1_t[-1]) + _MINUTE if len(m1_t) else 0)
    nxt = frame.bars.get(NEXT_TF.get(tf)) if tf in NEXT_TF else None
    parts = []
    for side in ("low", "high"):
        sign = 1.0 if side == "low" else -1.0
        o, h, l, c = _ohlc(bars) if side == "low" else mirror(*_ohlc(bars))
        m1 = ((m1_t, frame.arrays["high"], frame.arrays["low"]) if side == "low"
              else (m1_t, -frame.arrays["low"], -frame.arrays["high"]))
        next_bars = None
        if nxt is not None and not nxt.empty:
            nh = nxt["high"].to_numpy(float) if side == "low" else -nxt["low"].to_numpy(float)
            next_bars = (nh, _ns(nxt["close_time"]))
        part = _score_lows((o, h, l, c), times, close_times, m1, next_bars, since_ns, until_ns)
        for col in ["extreme"] + [f"obj_{o_}" for o_ in OBJECTIVES]:
            part[col] = sign * part[col]
        part.insert(0, "side", side)
        parts.append(part)
    table = pd.concat(parts, ignore_index=True)
    table.insert(0, "tf", tf.value)
    for col in ["extreme_bar", "extreme_time", "known_at"] + [f"resolved_{o_}" for o_ in OBJECTIVES]:
        table[col] = _times(table[col].to_numpy(np.int64))
    return table.sort_values(["known_at", "side"], kind="stable").reset_index(drop=True)[columns]
