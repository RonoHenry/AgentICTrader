"""Candle frames, the trading calendar and the decision grid.

Per instrument, ``frame_from_data()`` turns the backtester's InstrumentData
into pandas frames (Requirement 2):

- ``m1``: every M1 bar, bid OHLC, with ``spread`` priced as ``fill_bars()``
  prices it (the larger of the recorded spread and the spec's typical spread,
  algo-backtester D10), and the calendar columns of its open time;
- ``bars``: the strategy-calendar bars the engine sees (M15, H1, H4, D1, W1),
  each with its close time.

The calendar columns are vectorised with the strategy calendar's own rule,
"New York wall time + 7 h" (StrategyCalendar, an MT5 ny_close server clock):

- ``trading_date``: the date of that wall time, so 17:00 New York is midnight
  of the next date and Sunday 17:00 belongs to Monday;
- ``h4_index``: its hour // 4, so 17:00 → 0, 21:00 → 1, 01:00 → 2, 05:00 → 3,
  09:00 → 4 and 13:00 → 5;
- ``weekday`` of the trading date (0 = Monday), ``ny_minute`` (minutes since
  00:00 New York), ``in_window`` (01:00 ≤ New York time < 13:00, LE-D11) and
  ``killzone`` (``get_killzone``).

Property 3 checks them against StrategyCalendar at random instants, on both
sides of each DST change. (In the hour New York repeats when DST ends, the
calendar stretches one M15 period; FX and gold are closed then.)

The decision grid (``build_grid``) is the close of every M15 bar of the
calendar that holds M1 bars, within the research slices: the moments Phase A
evaluates the engine (AR-D2). A row belongs to the D1 candle containing its
t, as in the engine: the row at 17:00 New York, the close of the old candle's
last M15 bar, is the first instant of the new candle.

``frame_from_arrays()`` builds the same frames from plain arrays, with the
calendar bars aggregated here; the self-check's simulated markets use it.

Validates: Requirements 2.1-2.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from algo_backtester.data import InstrumentData
from liquidity_engine.models import Candle, KillzoneWindow, Timeframe
from liquidity_engine.utils.time_utils import KILLZONE_WINDOWS
from services.market_data.as_of_view import aggregate
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = [
    "BAR_TIMEFRAMES",
    "InstrumentFrame",
    "aggregate_frame",
    "build_grid",
    "calendar_columns",
    "frame_from_arrays",
    "frame_from_data",
]

#: The calendar bars research reads: the entry timeframe, the Asian range's, and the opens and levels'.
BAR_TIMEFRAMES = (Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1)

_NY = "America/New_York"
_SHIFT = pd.Timedelta(hours=7)          # the ny_close server clock: New York wall time + 7 h
_ONE_HOUR = pd.Timedelta(hours=1)
_CALENDAR = StrategyCalendar()
_WINDOW = (60, 13 * 60)                 # LE-D11: [01:00, 13:00) New York, in minutes
_INTRADAY = {Timeframe.M15: "15min", Timeframe.H1: "1h"}


def _killzone_by_minute() -> np.ndarray:
    """get_killzone's answer for each New York minute of the day: its windows
    are wall-clock times with both ends inclusive."""
    names = np.full(1440, KillzoneWindow.NONE.value, dtype=object)
    for window, (start, end) in KILLZONE_WINDOWS.items():
        names[start.hour * 60 + start.minute: end.hour * 60 + end.minute + 1] = window.value
    return names


_KILLZONE = _killzone_by_minute()


def _server_wall(times: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """The ny_close server's wall clock (naive) at each UTC instant."""
    return times.tz_convert(_NY).tz_localize(None) + _SHIFT


def _from_server_wall(wall: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """UTC instants of server wall times: a repeated wall time maps to its first
    occurrence and a skipped one an hour on, as MT5ServerClock.to_utc does."""
    first = np.ones(len(wall), dtype=bool)
    return (wall - _SHIFT).tz_localize(_NY, ambiguous=first, nonexistent=_ONE_HOUR).tz_convert("UTC")


def calendar_columns(times: pd.DatetimeIndex) -> pd.DataFrame:
    """Calendar columns at UTC instants ``times`` (Req 2.2)."""
    times = pd.DatetimeIndex(times)
    times = times.tz_localize("UTC") if times.tz is None else times.tz_convert("UTC")
    local = times.tz_convert(_NY)
    wall = local.tz_localize(None) + _SHIFT
    ny_minute = (local.hour * 60 + local.minute).to_numpy()
    trading_date = wall.normalize()
    return pd.DataFrame({
        "trading_date": trading_date,
        "weekday": trading_date.weekday.to_numpy().astype(np.int8),
        "ny_minute": ny_minute.astype(np.int16),
        "h4_index": (wall.hour // 4).to_numpy().astype(np.int8),
        "in_window": (ny_minute >= _WINDOW[0]) & (ny_minute < _WINDOW[1]),
        "killzone": _KILLZONE[ny_minute],
    })


# ── calendar bars ──────────────────────────────────────────────────────────

def _period_start_wall(wall: pd.DatetimeIndex, tf: Timeframe) -> pd.DatetimeIndex:
    if tf in _INTRADAY:
        return wall.floor(_INTRADAY[tf])
    day = wall.normalize()
    if tf == Timeframe.H4:
        return day + pd.to_timedelta((wall.hour // 4) * 4, unit="h")
    if tf == Timeframe.D1:
        return day
    if tf == Timeframe.W1:
        return day - pd.to_timedelta((day.dayofweek + 1) % 7, unit="D")     # back to the server's Sunday
    raise ValueError(f"unsupported timeframe {tf}")


_LENGTH = {Timeframe.M15: pd.Timedelta(minutes=15), Timeframe.H1: pd.Timedelta(hours=1),
           Timeframe.H4: pd.Timedelta(hours=4), Timeframe.D1: pd.Timedelta(days=1),
           Timeframe.W1: pd.Timedelta(days=7)}


def close_times(open_times: pd.DatetimeIndex, tf: Timeframe) -> pd.DatetimeIndex:
    """The calendar close (the next period's start) of ``tf`` periods opening at ``open_times``."""
    start_wall = _period_start_wall(_server_wall(pd.DatetimeIndex(open_times)), tf)
    return _from_server_wall(start_wall + _LENGTH[tf])


def period_bounds(times: pd.DatetimeIndex, tf: Timeframe) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """UTC [start, end) of the ``tf`` period containing each instant."""
    start_wall = _period_start_wall(_server_wall(pd.DatetimeIndex(times)), tf)
    return _from_server_wall(start_wall), _from_server_wall(start_wall + _LENGTH[tf])


def ny_instant(trading_dates, ny_minute: int) -> pd.DatetimeIndex:
    """The UTC instant of New York wall time ``ny_minute`` (minutes after 00:00)
    within each trading date: 17:00 and later fall on the eve, earlier times on
    the date itself (00:00 is the candle's midnight)."""
    wall = pd.DatetimeIndex(trading_dates) + pd.Timedelta(minutes=(ny_minute + 7 * 60) % 1440)
    return _from_server_wall(wall)


def aggregate_frame(m1: pd.DataFrame, tf: Timeframe, as_of: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Closed ``tf`` bars from M1 (columns time, open, high, low, close), as
    services.market_data.as_of_view.aggregate builds them: a period is kept only
    when it has ended by ``as_of`` (default: the last M1 bar's close)."""
    if m1.empty:
        return pd.DataFrame(columns=["time", "close_time", "open", "high", "low", "close"])
    times = pd.DatetimeIndex(m1["time"])
    start_wall = _period_start_wall(_server_wall(times), tf)
    grouped = m1.groupby(start_wall.to_numpy(), sort=True)
    bars = pd.DataFrame({"open": grouped["open"].first(), "high": grouped["high"].max(),
                         "low": grouped["low"].min(), "close": grouped["close"].last()})
    walls = pd.DatetimeIndex(bars.index)
    bars.insert(0, "close_time", _from_server_wall(walls + _LENGTH[tf]))
    bars.insert(0, "time", _from_server_wall(walls))
    cutoff = as_of if as_of is not None else times[-1] + pd.Timedelta(minutes=1)
    return bars[bars["close_time"] <= cutoff].reset_index(drop=True)


def _bars_from_candles(candles: list[Candle], tf: Timeframe) -> pd.DataFrame:
    times = pd.DatetimeIndex([c.timestamp for c in candles], tz="UTC") if candles else pd.DatetimeIndex([], tz="UTC")
    return pd.DataFrame({
        "time": times,
        "close_time": close_times(times, tf),
        "open": np.array([c.open for c in candles], dtype=float),
        "high": np.array([c.high for c in candles], dtype=float),
        "low": np.array([c.low for c in candles], dtype=float),
        "close": np.array([c.close for c in candles], dtype=float),
    })


# ── frames ─────────────────────────────────────────────────────────────────

@dataclass
class InstrumentFrame:
    instrument: str
    typical_spread: float                  # the spec's default_spread, price units
    stop_slippage: float
    m1: pd.DataFrame                       # time, open, high, low, close, spread + calendar columns
    bars: dict[Timeframe, pd.DataFrame]    # time, close_time, open, high, low, close; closed bars only
    arrays: dict[str, np.ndarray] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        m1 = self.m1
        self.arrays = {
            "time": m1["time"].to_numpy(dtype="datetime64[ns]").astype(np.int64),
            **{name: m1[name].to_numpy(dtype=float) for name in ("open", "high", "low", "close", "spread")},
        }


def _m1_frame(times: pd.DatetimeIndex, o, h, l, c, spread) -> pd.DataFrame:
    frame = pd.DataFrame({"time": times, "open": o, "high": h, "low": l, "close": c, "spread": spread})
    cal = calendar_columns(times)
    for name in ("trading_date", "h4_index", "ny_minute"):
        frame[name] = cal[name].to_numpy()
    return frame


def frame_from_data(data: InstrumentData, typical_spread: float, stop_slippage: float) -> InstrumentFrame:
    """Frames from the backtester's InstrumentData: its M1, and its calendar bars
    (built from M1, or native in the warm-up). A timeframe the strategy didn't
    load is aggregated from the M1, as load_instrument would."""
    m1 = data.m1
    times = pd.DatetimeIndex([b.timestamp for b in m1], tz="UTC") if m1 else pd.DatetimeIndex([], tz="UTC")
    recorded = np.array([np.nan if b.spread is None else b.spread for b in m1], dtype=float)
    # fill_bars: max(b.spread or 0.0, default_spread)
    spread = np.maximum(np.nan_to_num(recorded, nan=0.0), typical_spread)
    frame = _m1_frame(times, *(np.array([getattr(b, f) for b in m1], dtype=float)
                               for f in ("open", "high", "low", "close")), spread)
    end = m1[-1].timestamp + pd.Timedelta(minutes=1) if m1 else None
    bars = {}
    for tf in BAR_TIMEFRAMES:
        candles = data.closed.get(tf)
        if candles is None:
            candles = aggregate(m1, tf, _CALENDAR, as_of=end)[1:] if m1 else []
        bars[tf] = _bars_from_candles(candles, tf)
    return InstrumentFrame(data.instrument, typical_spread, stop_slippage, frame, bars)


def frame_from_arrays(instrument: str, times: pd.DatetimeIndex, o: np.ndarray, h: np.ndarray, l: np.ndarray,
                      c: np.ndarray, *, spread: np.ndarray, typical_spread: float,
                      stop_slippage: float) -> InstrumentFrame:
    """Frames from plain M1 arrays (bid prices; ``spread`` already priced), with
    every calendar bar aggregated from them. For simulated markets."""
    times = pd.DatetimeIndex(times)
    times = times.tz_localize("UTC") if times.tz is None else times.tz_convert("UTC")
    frame = _m1_frame(times, o, h, l, c, np.maximum(spread, typical_spread))
    bars = {tf: aggregate_frame(frame, tf) for tf in BAR_TIMEFRAMES}
    return InstrumentFrame(instrument, typical_spread, stop_slippage, frame, bars)


# ── the decision grid ──────────────────────────────────────────────────────

def build_grid(frame: InstrumentFrame, slices: Mapping[str, tuple[date, date]]) -> pd.DataFrame:
    """One row per M15 close t whose bar holds M1 bars and whose trading date is
    in a slice: t, instrument, the calendar columns at t and the slice."""
    m15 = frame.bars[Timeframe.M15]
    m1_times = frame.arrays["time"]
    opens = m15["time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    closes = m15["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    has_m1 = np.searchsorted(m1_times, closes, "left") > np.searchsorted(m1_times, opens, "left")
    t = pd.DatetimeIndex(m15["close_time"][has_m1])
    grid = calendar_columns(t)
    grid.insert(0, "instrument", frame.instrument)
    grid.insert(0, "t", t)
    names = np.full(len(grid), None, dtype=object)
    dates = grid["trading_date"].to_numpy()
    for name, (first, end) in slices.items():
        names[(dates >= np.datetime64(first)) & (dates < np.datetime64(end))] = name
    grid["slice"] = names
    return grid[grid["slice"].notna()].reset_index(drop=True)


def slices_of(cfg) -> dict[str, tuple[date, date]]:
    """The slices of a ResearchConfig, as build_grid takes them."""
    return {"explore": cfg.slices.explore, "confirm": cfg.slices.confirm}
