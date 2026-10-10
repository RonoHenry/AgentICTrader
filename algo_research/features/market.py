"""Market features: what a trader reads off the chart at each M15 close t.

One row per decision time (frame.build_grid) with the columns of
``COLUMNS``, each documented with its definition, unit and the moment it
becomes known (Requirement 3). Prices are bid, as stored.

Known at t means: computed only from M1 bars that closed at or before t
(opened before t) and calendar bars whose period ended by t (Property 1). A
value that isn't known yet, or lacks the history it needs, is null, never a
guess (Req 2.4). The engine's definitions are used where it has one, and are
checked against it (Property 4): the Asian range (LE-D12, asian_pools), the
W1 trend (LE-D15), the killzone and the manipulation window.

How it's computed, per instrument, without a loop over rows:
- ``k``, the number of M1 bars closed by each t, by ``searchsorted``; a bar
  index below k is known;
- running values (the day's extremes so far) as cumulative max/min within
  each trading date, read at bar k - 1;
- "taken" and "raided" times as the first M1 index per trading date (or
  week) beyond the level, known once that index is below k;
- previous candles by ``searchsorted`` on the calendar bars' close times.

Update 2026-10c adds the candle ranges of the user's Fractal + POI indicator:
for H1, H4 and D1, C2 (the last candle closed by t) and C1 (the bar before it,
so Monday's first H4 follows Friday's last), and whether C2 swept one side of
C1 and closed back inside (``crt_<tf>_side``).

Validates: Requirements 2.4, 3.1-3.4, 15.1 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from algo_research.frame import InstrumentFrame, calendar_columns, ny_instant, period_bounds
from liquidity_engine.models import Timeframe

__all__ = ["COLUMNS", "CRT_TIMEFRAMES", "Column", "market_features"]


@dataclass(frozen=True)
class Column:
    definition: str
    unit: str
    known_at: str


COLUMNS: dict[str, Column] = {
    "t": Column("the M15 close: the decision time", "UTC time", "t"),
    "instrument": Column("the instrument", "name", "t"),
    "trading_date": Column("New York date of the D1 candle containing t (opens 17:00 the day before)", "date", "t"),
    "weekday": Column("weekday of trading_date", "0 = Monday", "t"),
    "ny_minute": Column("New York wall time of t", "minutes after 00:00", "t"),
    "h4_index": Column("the H4 candle containing t: 17:00, 21:00, 01:00, 05:00, 09:00, 13:00 New York", "0-5", "t"),
    "in_window": Column("01:00 <= New York time < 13:00, the manipulation window (LE-D11)", "bool", "t"),
    "killzone": Column("get_killzone(t): LONDON, NY_AM, NY_PM or NONE", "name", "t"),
    "slice": Column("the research slice of trading_date: explore or confirm", "name", "t"),
    "close": Column("close of the M15 bar ending at t", "price", "t"),
    "d1_open": Column("open of the D1 candle's first M1 bar", "price", "that bar's close"),
    "midnight_open": Column("open of the candle's first M1 bar at or after 00:00 New York", "price",
                            "that bar's close"),
    "h4_open": Column("open of the first M1 bar of the H4 candle containing t", "price", "that bar's close"),
    "side_d1_open": Column("sign of close - d1_open", "-1, 0, 1", "t"),
    "side_midnight_open": Column("sign of close - midnight_open", "-1, 0, 1", "t"),
    "side_h4_open": Column("sign of close - h4_open", "-1, 0, 1", "t"),
    "day_high": Column("highest M1 high of the candle so far", "price", "t"),
    "day_low": Column("lowest M1 low of the candle so far", "price", "t"),
    "day_high_at": Column("open time of the M1 bar that made day_high, the earliest on a tie", "UTC time", "t"),
    "day_low_at": Column("open time of the M1 bar that made day_low, the earliest on a tie", "UTC time", "t"),
    "post_midnight_high": Column("highest M1 high of the candle from 00:00 New York", "price", "t"),
    "post_midnight_low": Column("lowest M1 low of the candle from 00:00 New York", "price", "t"),
    "prev_h4_dir": Column("sign of close - open of the last closed H4 candle", "-1, 0, 1", "its close"),
    "prev_day_dir": Column("sign of close - open of the last closed D1 candle", "-1, 0, 1", "its close"),
    "prev_week_dir": Column("sign of close - open of the last closed W1 candle", "-1, 0, 1", "its close"),
    "asia_high": Column("highest high of the candle's 20:00-23:00 New York H1 bars (asian_pools, LE-D12)", "price",
                        "00:00 New York"),
    "asia_low": Column("lowest low of the candle's 20:00-23:00 New York H1 bars (asian_pools, LE-D12)", "price",
                       "00:00 New York"),
    "asia_high_raided_at": Column("close of the first M1 bar from 00:00 New York with high > asia_high",
                                  "UTC time", "that bar's close"),
    "asia_low_raided_at": Column("close of the first M1 bar from 00:00 New York with low < asia_low",
                                 "UTC time", "that bar's close"),
    "pdh": Column("high of the last closed D1 candle", "price", "17:00 New York"),
    "pdl": Column("low of the last closed D1 candle", "price", "17:00 New York"),
    "pwh": Column("high of the last closed W1 candle", "price", "the W1 open"),
    "pwl": Column("low of the last closed W1 candle", "price", "the W1 open"),
    "pdh_taken_at": Column("close of the candle's first M1 bar with high > pdh", "UTC time", "that bar's close"),
    "pdl_taken_at": Column("close of the candle's first M1 bar with low < pdl", "UTC time", "that bar's close"),
    "pwh_taken_at": Column("close of the W1 candle's first M1 bar with high > pwh", "UTC time", "that bar's close"),
    "pwl_taken_at": Column("close of the W1 candle's first M1 bar with low < pwl", "UTC time", "that bar's close"),
    "w1_trend": Column("UP when the last closed W1 closed above the previous W1's high, DOWN below its low, "
                       "else NEUTRAL (LE-D15)", "name", "the W1 close"),
    "atr_d1": Column("calculate_atr over the last 15 closed D1 candles: 14 true ranges", "price", "17:00 New York"),
    "atr_m15": Column("calculate_atr over the last 15 closed M15 bars: 14 true ranges", "price", "t"),
    "typical_spread": Column("the spec's default_spread", "price", "always"),
    "spread_to_atr": Column("typical_spread / atr_d1", "ratio", "17:00 New York"),
}

#: Candle-range timeframes (update 2026-10c, Requirement 15): C2 is the last candle closed by t, C1 the one before.
CRT_TIMEFRAMES = {"h1": Timeframe.H1, "h4": Timeframe.H4, "d1": Timeframe.D1}
for _name, _tf in CRT_TIMEFRAMES.items():
    _c2 = f"the last {_tf.value} candle closed by t (C2)"
    COLUMNS[f"crt_{_name}_at"] = Column(f"close time of {_c2}", "UTC time", "its close")
    COLUMNS[f"crt_{_name}_c1_high"] = Column(f"high of the {_tf.value} candle before C2 (C1); null without one",
                                             "price", "C2's close")
    COLUMNS[f"crt_{_name}_c1_low"] = Column(f"low of the {_tf.value} candle before C2 (C1); null without one",
                                            "price", "C2's close")
    COLUMNS[f"crt_{_name}_c2_high"] = Column(f"high of {_c2}", "price", "its close")
    COLUMNS[f"crt_{_name}_c2_low"] = Column(f"low of {_c2}", "price", "its close")
    COLUMNS[f"crt_{_name}_side"] = Column(
        "+1 when C2's low < C1's low, its high <= C1's high and its close > C1's low (C1's low swept, closed "
        "back inside); -1 mirrored; else 0. Null without C1", "-1, 0, 1", "C2's close")

_MINUTE = 60 * 1_000_000_000
_NAT = np.iinfo(np.int64).min
_ATR_PERIOD = 14


def market_features(frame: InstrumentFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """The market feature columns for ``grid``'s rows (one instrument)."""
    a = frame.arrays
    mt, o, h, l = a["time"], a["open"], a["high"], a["low"]
    n = len(mt)
    out = grid.copy()
    if out.empty:
        return pd.DataFrame({name: pd.Series(dtype=object) for name in COLUMNS})

    t_index = pd.DatetimeIndex(grid["t"])
    gt = _ns(t_index)
    k = np.searchsorted(mt + _MINUTE, gt, "right")             # M1 bars [0, k) closed by t
    last = np.clip(k - 1, 0, max(n - 1, 0))
    out["close"] = a["close"][last]

    # ── per trading date: the candle's bars ──────────────────────────────
    dates_row = pd.DatetimeIndex(grid["trading_date"])
    day_open_row = _ns(ny_instant(dates_row, 17 * 60))
    midnight_row = _ns(ny_instant(dates_row, 0))
    first_d1 = np.searchsorted(mt, day_open_row, "left")
    first_mid = np.searchsorted(mt, midnight_row, "left")
    first_h4 = np.searchsorted(mt, _ns(period_bounds(t_index, Timeframe.H4)[0]), "left")
    known_d1, known_mid, known_h4 = first_d1 < k, first_mid < k, first_h4 < k

    out["d1_open"] = _take(o, first_d1, known_d1)
    out["midnight_open"] = _take(o, first_mid, known_mid)
    out["h4_open"] = _take(o, first_h4, known_h4)
    for name, base in (("side_d1_open", "d1_open"), ("side_midnight_open", "midnight_open"),
                       ("side_h4_open", "h4_open")):
        out[name] = np.sign(out["close"].to_numpy() - out[base].to_numpy())

    m1_dates = frame.m1["trading_date"].to_numpy(dtype="datetime64[ns]")
    seg = m1_dates.astype(np.int64)
    run_high, high_at = _running(h, seg, maximum=True)
    run_low, low_at = _running(l, seg, maximum=False)
    out["day_high"] = _take(run_high, last, known_d1)
    out["day_low"] = _take(run_low, last, known_d1)
    high_bar, low_bar = _take_int(high_at, last, known_d1), _take_int(low_at, last, known_d1)
    out["day_high_at"] = _times(_take_int(mt, high_bar, high_bar != _NAT))
    out["day_low_at"] = _times(_take_int(mt, low_bar, low_bar != _NAT))

    # Per unique trading date of the M1 bars: its open, its midnight and its week.
    u_dates, inverse = np.unique(m1_dates, return_inverse=True)
    u_index = pd.DatetimeIndex(u_dates)
    u_midnight = _ns(ny_instant(u_index, 0)) if len(u_dates) else np.array([], dtype=np.int64)
    u_open = _ns(ny_instant(u_index, 17 * 60)) if len(u_dates) else np.array([], dtype=np.int64)
    after_midnight = mt >= u_midnight[inverse] if n else np.zeros(0, dtype=bool)
    pm_high, _ = _running(np.where(after_midnight, h, -np.inf), seg, maximum=True)
    pm_low, _ = _running(np.where(after_midnight, l, np.inf), seg, maximum=False)
    out["post_midnight_high"] = _take(pm_high, last, known_mid)
    out["post_midnight_low"] = _take(pm_low, last, known_mid)

    # ── previous candles ─────────────────────────────────────────────────
    h4, d1, w1 = (frame.bars[tf] for tf in (Timeframe.H4, Timeframe.D1, Timeframe.W1))
    j_h4, j_d1, j_w1 = (_last_closed(b, gt) for b in (h4, d1, w1))
    out["prev_h4_dir"] = _direction(h4, j_h4)
    out["prev_day_dir"] = _direction(d1, j_d1)
    out["prev_week_dir"] = _direction(w1, j_w1)

    # ── the Asian range (LE-D12) and its raids ───────────────────────────
    asia_high_u, asia_low_u = _asia_range(frame.bars[Timeframe.H1], u_dates)
    row_u = np.searchsorted(u_dates, dates_row.to_numpy(dtype="datetime64[ns]"))
    has_u = (row_u < len(u_dates)) & (u_dates[np.clip(row_u, 0, max(len(u_dates) - 1, 0))] == dates_row.to_numpy(
        dtype="datetime64[ns]")) if len(u_dates) else np.zeros(len(gt), dtype=bool)
    row_u = np.clip(row_u, 0, max(len(u_dates) - 1, 0))
    asia_known = has_u & (gt >= midnight_row)
    out["asia_high"] = _take(asia_high_u, row_u, asia_known)
    out["asia_low"] = _take(asia_low_u, row_u, asia_known)
    with np.errstate(invalid="ignore"):
        high_raid = after_midnight & (h > asia_high_u[inverse])
        low_raid = after_midnight & (l < asia_low_u[inverse])
    out["asia_high_raided_at"] = _taken_at(mt, _first_by_key(high_raid, seg, dates_row), k)
    out["asia_low_raided_at"] = _taken_at(mt, _first_by_key(low_raid, seg, dates_row), k)

    # ── previous day and week levels, and when they were taken ───────────
    out["pdh"] = _take(d1["high"].to_numpy(), j_d1, j_d1 >= 0)
    out["pdl"] = _take(d1["low"].to_numpy(), j_d1, j_d1 >= 0)
    out["pwh"] = _take(w1["high"].to_numpy(), j_w1, j_w1 >= 0)
    out["pwl"] = _take(w1["low"].to_numpy(), j_w1, j_w1 >= 0)

    j_day = _last_closed(d1, u_open)                         # the previous candle of each M1 bar's candle
    pdh_u, pdl_u = _take(d1["high"].to_numpy(), j_day, j_day >= 0), _take(d1["low"].to_numpy(), j_day, j_day >= 0)
    u_week = _ns(period_bounds(pd.DatetimeIndex(u_open, tz="UTC"), Timeframe.W1)[0]) if len(u_dates) else u_open
    j_week = _last_closed(w1, u_week)
    pwh_u, pwl_u = _take(w1["high"].to_numpy(), j_week, j_week >= 0), _take(w1["low"].to_numpy(), j_week, j_week >= 0)
    week_m1 = u_week[inverse] if n else np.zeros(0, dtype=np.int64)
    week_row = _ns(period_bounds(pd.DatetimeIndex(day_open_row, tz="UTC"), Timeframe.W1)[0])
    with np.errstate(invalid="ignore"):
        out["pdh_taken_at"] = _taken_at(mt, _first_by_key(h > pdh_u[inverse], seg, dates_row), k)
        out["pdl_taken_at"] = _taken_at(mt, _first_by_key(l < pdl_u[inverse], seg, dates_row), k)
        out["pwh_taken_at"] = _taken_at(mt, _first_by_key(h > pwh_u[inverse], week_m1, week_row), k)
        out["pwl_taken_at"] = _taken_at(mt, _first_by_key(l < pwl_u[inverse], week_m1, week_row), k)

    out["w1_trend"] = _w1_trend(w1, j_w1)
    out["atr_d1"] = _atr(d1, j_d1 + 1)
    out["atr_m15"] = _atr(frame.bars[Timeframe.M15], _last_closed(frame.bars[Timeframe.M15], gt) + 1)
    out["typical_spread"] = frame.typical_spread
    out["spread_to_atr"] = frame.typical_spread / out["atr_d1"].to_numpy()

    # ── candle ranges: C1 and C2 (update 2026-10c) ───────────────────────
    for name, tf in CRT_TIMEFRAMES.items():
        _candle_range(out, name, frame.bars[tf], gt)
    return out[list(COLUMNS)]


def _candle_range(out: pd.DataFrame, name: str, bars: pd.DataFrame, gt: np.ndarray) -> None:
    """The crt_<name>_* columns: C2, the last bar closed by each t, and C1, the bar before it."""
    j = _last_closed(bars, gt)
    has_c2, has_c1 = j >= 0, j >= 1
    high, low, close = (bars[c].to_numpy(dtype=float) for c in ("high", "low", "close"))
    closes = _ns(bars["close_time"]) if len(bars) else np.array([], dtype=np.int64)
    c1_high, c1_low = _take(high, j - 1, has_c1), _take(low, j - 1, has_c1)
    c2_high, c2_low, c2_close = _take(high, j, has_c2), _take(low, j, has_c2), _take(close, j, has_c2)
    with np.errstate(invalid="ignore"):
        low_swept, high_swept = c2_low < c1_low, c2_high > c1_high
        side = np.where(low_swept & ~high_swept & (c2_close > c1_low), 1.0,
                        np.where(high_swept & ~low_swept & (c2_close < c1_high), -1.0, 0.0))
    out[f"crt_{name}_at"] = _times(_take_int(closes, j, has_c2))
    out[f"crt_{name}_c1_high"], out[f"crt_{name}_c1_low"] = c1_high, c1_low
    out[f"crt_{name}_c2_high"], out[f"crt_{name}_c2_low"] = c2_high, c2_low
    out[f"crt_{name}_side"] = np.where(has_c1, side, np.nan)


# ── helpers ────────────────────────────────────────────────────────────────

def _ns(times) -> np.ndarray:
    return pd.DatetimeIndex(times).as_unit("ns").asi8 if not isinstance(times, np.ndarray) else times


def _take(values: np.ndarray, index: np.ndarray, known: np.ndarray) -> np.ndarray:
    if len(values) == 0:
        return np.full(len(index), np.nan)
    return np.where(known, values[np.clip(index, 0, len(values) - 1)], np.nan)


def _take_int(values: np.ndarray, index: np.ndarray, known: np.ndarray) -> np.ndarray:
    if len(values) == 0:
        return np.full(len(index), _NAT, dtype=np.int64)
    ok = known & (index != _NAT)
    return np.where(ok, values[np.clip(index, 0, len(values) - 1)], _NAT)


def _times(ns: np.ndarray) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(ns.astype("datetime64[ns]")).tz_localize("UTC")


def _running(values: np.ndarray, seg: np.ndarray, maximum: bool) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative max (min) within each segment, and the index of the bar that
    set it: the earliest on a tie."""
    if len(values) == 0:
        return values.astype(float), np.zeros(0, dtype=np.int64)
    series = pd.Series(values)
    grouped = series.groupby(seg, sort=False)
    run = (grouped.cummax() if maximum else grouped.cummin()).to_numpy()
    previous = pd.Series(run).groupby(seg, sort=False).shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        new = np.isnan(previous) | (values > previous if maximum else values < previous)
    marks = pd.Series(np.where(new, np.arange(len(values)), np.nan))
    at = marks.groupby(seg, sort=False).ffill().to_numpy()
    return run, np.where(np.isnan(at), _NAT, at).astype(np.int64)


def _last_closed(bars: pd.DataFrame, instants: np.ndarray) -> np.ndarray:
    """Index of the last bar whose period ended by each instant; -1 if none."""
    closes = _ns(bars["close_time"]) if len(bars) else np.array([], dtype=np.int64)
    return np.searchsorted(closes, instants, "right") - 1


def _direction(bars: pd.DataFrame, j: np.ndarray) -> np.ndarray:
    if len(bars) == 0:
        return np.full(len(j), np.nan)
    return _take(np.sign(bars["close"].to_numpy() - bars["open"].to_numpy()), j, j >= 0)


def _asia_range(h1: pd.DataFrame, dates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per trading date: the highest high and lowest low of its H1 bars opening
    20:00-23:00 New York (asian_pools); NaN when it has none."""
    high, low = np.full(len(dates), np.nan), np.full(len(dates), np.nan)
    if len(h1) == 0 or len(dates) == 0:
        return high, low
    cal = calendar_columns(pd.DatetimeIndex(h1["time"]))
    session = (cal["ny_minute"].to_numpy() >= 20 * 60)
    bars = pd.DataFrame({"date": cal["trading_date"].to_numpy(dtype="datetime64[ns]")[session],
                         "high": h1["high"].to_numpy()[session], "low": h1["low"].to_numpy()[session]})
    agg = bars.groupby("date").agg(high=("high", "max"), low=("low", "min"))
    where = np.searchsorted(dates, agg.index.to_numpy(dtype="datetime64[ns]"))
    found = (where < len(dates)) & (dates[np.clip(where, 0, len(dates) - 1)] == agg.index.to_numpy(
        dtype="datetime64[ns]"))
    high[where[found]] = agg["high"].to_numpy()[found]
    low[where[found]] = agg["low"].to_numpy()[found]
    return high, low


def _first_by_key(mask: np.ndarray, keys: np.ndarray, row_keys) -> np.ndarray:
    """For each row, the first M1 index whose key equals the row's key and where
    ``mask`` holds; _NAT when none."""
    row_keys = _ns(row_keys) if not isinstance(row_keys, np.ndarray) else row_keys
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return np.full(len(row_keys), _NAT, dtype=np.int64)
    unique, first = np.unique(keys[idx], return_index=True)
    loc = np.clip(np.searchsorted(unique, row_keys), 0, len(unique) - 1)
    return np.where(unique[loc] == row_keys, idx[first[loc]], _NAT)


def _taken_at(mt: np.ndarray, first: np.ndarray, k: np.ndarray) -> pd.DatetimeIndex:
    """The close of the first bar beyond, once it has closed by t."""
    known = (first != _NAT) & (first < k)
    return _times(np.where(known, mt[np.clip(first, 0, len(mt) - 1)] + _MINUTE, _NAT))


def _w1_trend(w1: pd.DataFrame, j: np.ndarray) -> np.ndarray:
    trend = np.full(len(j), None, dtype=object)
    ok = j >= 1
    if not ok.any():
        return trend
    close, high, low = (w1[name].to_numpy() for name in ("close", "high", "low"))
    last, prev = j[ok], j[ok] - 1
    trend[ok] = np.where(close[last] > high[prev], "UP", np.where(close[last] < low[prev], "DOWN", "NEUTRAL"))
    return trend


def _atr(bars: pd.DataFrame, count: np.ndarray) -> np.ndarray:
    """calculate_atr(bars[:count], 14) for each count, null below 15 bars. The
    same true ranges summed in the same order, so the values are identical."""
    out = np.full(len(count), np.nan)
    if len(bars) < _ATR_PERIOD + 1:
        return out
    high, low, close = (bars[name].to_numpy() for name in ("high", "low", "close"))
    tr = np.maximum(np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1])), np.abs(low[1:] - close[:-1]))
    true_ranges = [float("nan"), *tr.tolist()]                # true_ranges[i] belongs to bar i
    for m in np.unique(count[count >= _ATR_PERIOD + 1]):
        window = true_ranges[m - _ATR_PERIOD: m]
        out[count == m] = sum(window) / len(window)
    return out
