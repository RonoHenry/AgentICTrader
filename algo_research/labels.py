"""Labels: what happened after t, kept apart from what was known at t.

The label table has the feature table's rows (Requirement 6). Nothing in
algo_research/features/, frame.py, events.py or filters.py imports this
module (a test checks the imports), so no condition can read the future. A
hypothesis reads labels only in its measure.

Two kinds:

- **Forward labels** read only M1 bars opening at or after t (Property 2),
  plus the row's own features as reference points (its close, its levels,
  its ATR). They answer "what happens next":
  - ``rem_close``: the close of the candle's last M1 bar before the D1 close
    (17:00 New York); ``rem_move`` = rem_close - close, also in ATR;
  - ``fwd_1h_close``, ``fwd_4h_close``: the close of the last M1 bar ending by
    t + h (past the D1 close if need be; null past the end of the data), and
    the moves in ATR;
  - for each level (PDH, PDL, PWH, PWL, the Asian high and low) known at t:
    whether an M1 bar opening at or after t, before the D1 close, trades
    beyond it, and the close of the first that does.
- **Candle labels** describe the whole D1 candle, bars before t included:
  its direction, its final high and low, and the H4 candle and the daily
  quarter (Quarterly Theory, update 2026-10c) each formed in.
  Asked at 09:00, "did the day close up?" partly restates what has already
  happened, so hypothesis validation accepts candle labels only with the
  ``daily`` event (Req 6.2); direction questions use ``rem_move``.

Validates: Requirements 6.1-6.4, 17.1, 18.2 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from algo_research.frame import InstrumentFrame, daily_quarter, ny_instant

__all__ = ["CANDLE_LABELS", "DRAW_LABELS", "DRAW_LEVELS", "FORWARD_LABELS", "LABEL_COLUMNS", "LEVELS",
           "LEVEL_PRICE", "Label", "build_labels", "candle_labels", "draw_labels", "forward_labels"]


@dataclass(frozen=True)
class Label:
    definition: str
    unit: str


#: Feature levels whose later trading is labelled; the first three are above price when untaken.
LEVELS = ("pdh", "pdl", "pwh", "pwl", "asia_high", "asia_low")
_ABOVE = frozenset({"pdh", "pwh", "asia_high"})

FORWARD_LABELS: dict[str, Label] = {
    "rem_close": Label("close of the candle's last M1 bar before the D1 close (17:00 New York)", "price"),
    "rem_move": Label("rem_close - close: the move still to come in the candle", "price"),
    "rem_move_atr": Label("rem_move / atr_d1", "ATR"),
    "fwd_1h_close": Label("close of the last M1 bar ending by t + 1 h; null past the data", "price"),
    "fwd_1h_atr": Label("(fwd_1h_close - close) / atr_d1", "ATR"),
    "fwd_4h_close": Label("close of the last M1 bar ending by t + 4 h; null past the data", "price"),
    "fwd_4h_atr": Label("(fwd_4h_close - close) / atr_d1", "ATR"),
}
for _level in LEVELS:
    _side = "high > " if _level in _ABOVE else "low < "
    FORWARD_LABELS[f"{_level}_hit_after"] = Label(
        f"an M1 bar opening at or after t, before the D1 close, has {_side}{_level}; null when {_level} "
        f"isn't known at t", "bool")
    FORWARD_LABELS[f"{_level}_hit_at"] = Label(f"close of the first such bar", "UTC time")

#: The engine's draws (update 2026-10e): labelled once the anticipation is joined (draw_labels).
DRAW_LEVELS = ("ant_draw_above", "ant_draw_below")
#: A level's price column in the feature table.
LEVEL_PRICE = {**{level: level for level in LEVELS}, **{level: f"{level}_price" for level in DRAW_LEVELS}}

DRAW_LABELS: dict[str, Label] = {}
for _level in DRAW_LEVELS:
    _side = "high > " if _level == "ant_draw_above" else "low < "
    DRAW_LABELS[f"{_level}_hit_after"] = Label(
        f"an M1 bar opening at or after t, before the D1 close, has {_side}{_level}_price; null when the draw "
        f"isn't known at t", "bool")
    DRAW_LABELS[f"{_level}_hit_at"] = Label("close of the first such bar", "UTC time")

CANDLE_LABELS: dict[str, Label] = {
    "day_dir": Label("sign of the candle's final close - its open (d1_open)", "-1, 0, 1"),
    "day_high_final": Label("the candle's high", "price"),
    "day_low_final": Label("the candle's low", "price"),
    "day_high_h4": Label("h4_index of the M1 bar that made the high, the earliest on a tie", "0-5"),
    "day_low_h4": Label("h4_index of the M1 bar that made the low, the earliest on a tie", "0-5"),
    "day_high_q": Label("daily quarter (New York) of the M1 bar that made the high, the earliest on a tie: "
                        "0 = 17:00-00:00, 1 = 00:00-06:00, 2 = 06:00-12:00, 3 = 12:00-17:00", "0-3"),
    "day_low_q": Label("daily quarter (New York) of the M1 bar that made the low, the earliest on a tie", "0-3"),
}

LABEL_COLUMNS: dict[str, Label] = {**FORWARD_LABELS, **DRAW_LABELS, **CANDLE_LABELS}

_MINUTE = 60 * 1_000_000_000
_HOUR = 60 * _MINUTE
_NAT = np.iinfo(np.int64).min


def build_labels(frame: InstrumentFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Forward and candle labels for ``features``' rows (one instrument), same index.
    The draws' labels come later, from the joined anticipation (draw_labels)."""
    forward = forward_labels(frame, features)
    days = candle_labels(frame)
    candle = features[["trading_date"]].merge(days, on="trading_date", how="left", validate="many_to_one")
    candle.index = features.index
    return pd.concat([forward, candle[list(CANDLE_LABELS)]], axis=1)[[*FORWARD_LABELS, *CANDLE_LABELS]]


def forward_labels(frame: InstrumentFrame, features: pd.DataFrame) -> pd.DataFrame:
    a = frame.arrays
    mt, high, low, close_m1 = a["time"], a["high"], a["low"], a["close"]
    n = len(mt)
    out = pd.DataFrame(index=features.index)
    if n == 0 or features.empty:
        for name in FORWARD_LABELS:
            out[name] = np.nan
        return out

    gt = pd.DatetimeIndex(features["t"]).as_unit("ns").asi8
    k = np.searchsorted(mt, gt, "left")                                   # the first bar opening at or after t
    dates = pd.DatetimeIndex(features["trading_date"])
    e = np.searchsorted(mt, ny_instant(dates + pd.Timedelta(days=1), 17 * 60).as_unit("ns").asi8, "left")
    close = features["close"].to_numpy(dtype=float)
    atr = features["atr_d1"].to_numpy(dtype=float)

    rem = np.where(e > k, close_m1[np.clip(e - 1, 0, n - 1)], np.nan)
    out["rem_close"] = rem
    out["rem_move"] = rem - close
    out["rem_move_atr"] = (rem - close) / atr
    last_close = mt[-1] + _MINUTE
    for hours in (1, 4):
        horizon = gt + hours * _HOUR
        end = np.searchsorted(mt, horizon, "left")                        # bars ending by t + h
        ok = (end > k) & ((end < n) | (last_close >= horizon))
        value = np.where(ok, close_m1[np.clip(end - 1, 0, n - 1)], np.nan)
        out[f"fwd_{hours}h_close"] = value
        out[f"fwd_{hours}h_atr"] = (value - close) / atr

    m1_dates = frame.m1["trading_date"].to_numpy(dtype="datetime64[ns]")
    for level in LEVELS:
        hit_after, hit_at = _level_hits(features, level, m1_dates, high if level in _ABOVE else low,
                                        level in _ABOVE, mt, k, e)
        out[f"{level}_hit_after"] = hit_after
        out[f"{level}_hit_at"] = hit_at
    return out[list(FORWARD_LABELS)]


def draw_labels(frame: InstrumentFrame, features: pd.DataFrame) -> pd.DataFrame:
    """``DRAW_LABELS`` for ``features``' rows of one instrument (the anticipation joined), same index:
    whether, and when, each engine draw trades after t, before the D1 close (Req 18.2)."""
    out = pd.DataFrame(index=features.index)
    a = frame.arrays
    mt, high, low = a["time"], a["high"], a["low"]
    if len(mt) == 0 or features.empty:
        for name in DRAW_LABELS:
            out[name] = np.nan
        return out
    k = np.searchsorted(mt, pd.DatetimeIndex(features["t"]).as_unit("ns").asi8, "left")
    dates = pd.DatetimeIndex(features["trading_date"])
    e = np.searchsorted(mt, ny_instant(dates + pd.Timedelta(days=1), 17 * 60).as_unit("ns").asi8, "left")
    m1_dates = frame.m1["trading_date"].to_numpy(dtype="datetime64[ns]")
    for level in DRAW_LEVELS:
        above = level == "ant_draw_above"
        hit_after, hit_at = _level_hits(features, LEVEL_PRICE[level], m1_dates, high if above else low, above,
                                        mt, k, e)
        out[f"{level}_hit_after"] = hit_after
        out[f"{level}_hit_at"] = hit_at
    return out[list(DRAW_LABELS)]


def _level_hits(features: pd.DataFrame, column: str, m1_dates: np.ndarray, prices: np.ndarray, above: bool,
                mt: np.ndarray, k: np.ndarray, e: np.ndarray) -> tuple[pd.Series, pd.DatetimeIndex]:
    """Whether, and when, a bar in [k, e) trades beyond each row's level (its price ``column``)."""
    n = len(mt)
    values = features[column].to_numpy(dtype=float)
    known = ~np.isnan(values)
    # The level is the same on every row of a candle where it is known; spread it over the candle's bars.
    per_date = pd.Series(values[known], index=features["trading_date"].to_numpy(dtype="datetime64[ns]")[known])
    per_date = per_date.groupby(level=0).first()
    bar_level = per_date.reindex(m1_dates).to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        beyond = prices > bar_level if above else prices < bar_level
    # next_hit[i]: the first index >= i where a bar is beyond its candle's level (n if none).
    marks = np.where(beyond, np.arange(n), n)
    next_hit = np.minimum.accumulate(marks[::-1])[::-1]
    first = np.where(k < n, next_hit[np.clip(k, 0, n - 1)], n)
    hit = known & (first < e)
    hit_after = pd.array(np.where(known, hit, False), dtype="boolean")
    hit_after[~known] = pd.NA
    at = np.where(hit, mt[np.clip(first, 0, n - 1)] + _MINUTE, _NAT)
    return pd.Series(hit_after, index=features.index), pd.DatetimeIndex(at.astype("datetime64[ns]")).tz_localize("UTC")


def candle_labels(frame: InstrumentFrame) -> pd.DataFrame:
    """One row per trading date of the M1 bars: the whole candle's facts."""
    m1 = frame.m1
    if m1.empty:
        return pd.DataFrame(columns=["trading_date", *CANDLE_LABELS])
    grouped = m1.groupby("trading_date", sort=True)
    days = pd.DataFrame({
        "open": grouped["open"].first(), "close": grouped["close"].last(),
        "day_high_final": grouped["high"].max(), "day_low_final": grouped["low"].min(),
    })
    h4, quarter = m1["h4_index"].to_numpy(), daily_quarter(m1["ny_minute"].to_numpy())
    high_at, low_at = grouped["high"].idxmax().to_numpy(), grouped["low"].idxmin().to_numpy()   # the first occurrence
    days["day_high_h4"], days["day_low_h4"] = h4[high_at], h4[low_at]
    days["day_high_q"], days["day_low_q"] = quarter[high_at], quarter[low_at]
    days["day_dir"] = np.sign(days["close"] - days["open"])
    return days.reset_index()[["trading_date", *CANDLE_LABELS]]
