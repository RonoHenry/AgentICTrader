"""Which higher timeframe a chart reads, and where every timeframe's candles start (algo-backtester Requirement 21).

The trader's Pine v6 indicator, "Fractal + POI" (``backend/FractalPOI.md``), picks its higher timeframe (HTF) from
the chart's own by a "Fractal" mode, and builds that HTF's candles from the chart's. These are the same choices,
on the charts' own clock (``algo_research.replay.timeframes``): New York wall seconds, with the trading day
opening at 17:00. So Noculus starts every candle where a TradingView FX chart does: H4 at 17:00, 21:00, 01:00 and
so on, D1 at 17:00, and W1 on Sunday at 17:00.

Pine names timeframes as strings:
- "1" to "720" are minutes;
- "1D", "1W" and "1M" (and multiples such as "4D", "15W", "3M") are days, weeks and months;
- the Quarterly mode adds three session clocks. SESSION_MICRO is about 22.5 minutes, SESSION_90 is 90 minutes and
  SESSION_6H is six hours, all counted from 18:00 New York.

Noculus' timeframes (M1 to MN1) map onto these strings one to one (``PERIOD``).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from algo_research.replay.timeframes import DAY, DAY_OPEN, bucket

__all__ = ["PERIOD", "QUARTERLY", "bsl_auto", "fractal_htf", "fvg_auto", "fvg_label", "htf2_auto", "htf_name",
           "in_seconds", "ltf_name", "period_end", "starts", "valid_htf"]

#: Noculus' chart timeframes as Pine's ``timeframe.period`` names them.
PERIOD = {"M1": "1", "M2": "2", "M3": "3", "M4": "4", "M5": "5", "M10": "10", "M15": "15", "M20": "20", "M30": "30",
          "M45": "45", "H1": "60", "H3": "180", "H4": "240", "H6": "360", "H7": "420", "H8": "480", "H12": "720",
          "D1": "1D", "W1": "1W", "MN1": "1M"}
#: The Quarterly Theory clocks: their nominal length in seconds, as the indicator uses it for time arithmetic.
QUARTERLY = {"SESSION_MICRO": 1350, "SESSION_90": 5400, "SESSION_6H": 21600}
_MONTH = 2_628_003                    # TradingView's timeframe.in_seconds("1M")
_WEEK = 7 * DAY
#: Fractal modes with a fixed HTF, whatever the chart (the indicator's "1m-15m" and the like).
_FIXED = {"1s-1m": "1", "15s-5m": "5", "1m-15m": "15", "3m-30m": "30", "5m-1H": "60", "15m-4H": "240",
          "1H-1D": "1D", "4H-1W": "1W", "1D-1M": "1M"}
MODES = ("Automatic", "Intraday", "Scalp", "Swing", "Quarterly", "Custom", *_FIXED)


def _norm(tf: str) -> str:
    return {"D": "1D", "W": "1W", "M": "1M"}.get(tf, tf)


def in_seconds(tf: str) -> Optional[int]:
    """``timeframe.in_seconds(tf)``; None for "" (no timeframe) or a name Pine wouldn't take."""
    tf = _norm(str(tf or ""))
    if tf in QUARTERLY:
        return QUARTERLY[tf]
    if not tf:
        return None
    unit, n = tf[-1], tf[:-1]
    if unit in "SDWM" and not tf.isdigit():
        if not n.isdigit():
            return None
        return int(n) * {"S": 1, "D": DAY, "W": _WEEK, "M": _MONTH}[unit]
    return int(tf) * 60 if tf.isdigit() else None


# ── the Fractal modes (getHigherTF, getIntradayHTF, getScalpHTF, getSwingHTF, getQuarterlyHTF) ────────────
def _higher(period: str) -> str:
    return {"1S": "1", "15S": "5", "1": "15", "3": "30", "5": "60", "15": "240", "30": "240", "60": "1D", "120": "1D",
            "240": "1W", "1D": "1M", "1W": "3M", "1M": "12M"}.get(period, "")


def _intraday(s: int) -> str:
    fixed = {60: "15", 180: "30", 300: "60", 900: "240", 1800: "240", 3600: "1D", 7200: "1D", 14400: "1D", 86400: "1W"}
    return fixed.get(s) or ("60" if s < 3600 else "1D")


def _scalp(s: int) -> str:
    return "5" if s <= 60 else "15" if s <= 300 else "60" if s <= 900 else "240" if s <= 3600 else "1D"


def _swing(s: int, period: str) -> str:
    fixed = {300: "60", 900: "240", 1800: "240", 3600: "1D", 7200: "1D", 14400: "1W", 86400: "1W"}
    if s in fixed:
        return fixed[s]
    if period == "1W":
        return "1M"
    return "240" if s < 3600 else "1D"


def _quarterly(period: str) -> str:
    return {"1": "SESSION_MICRO", "3": "SESSION_90", "5": "SESSION_90", "15": "SESSION_6H",
            "30": "SESSION_6H"}.get(period) or _higher(period)


def fractal_htf(mode: str, tf: str, custom_htf: str = "60") -> str:
    """The HTF the indicator reads on a Noculus chart of ``tf`` in Fractal mode ``mode`` ("" when there is none)."""
    period = PERIOD[tf]
    s = in_seconds(period)
    if mode in _FIXED:
        return _FIXED[mode]
    return {"Automatic": lambda: _higher(period), "Intraday": lambda: _intraday(s), "Scalp": lambda: _scalp(s),
            "Swing": lambda: _swing(s, period), "Quarterly": lambda: _quarterly(period),
            "Custom": lambda: _norm(custom_htf)}.get(mode, lambda: _higher(period))()


def htf2_auto(tf: str) -> str:
    """getAutoHTF2: the preview timeframe one step above HTF1."""
    period = PERIOD[tf]
    s = in_seconds(period)
    fixed = {60: "240", 120: "240", 180: "90", 300: "240", 900: "1D", 1800: "240", 3600: "1W", 14400: "1M", 86400: "3M"}
    if s in fixed:
        return fixed[s]
    if period in ("1W", "1M"):
        return "12M"
    return "240" if s < 3600 else "1W"


def fvg_auto(tf: str) -> str:
    """fvg_get_htf_period: the HTF whose fair value gaps the chart shows."""
    s = in_seconds(PERIOD[tf])
    for limit, htf in ((15, "5"), (60, "15"), (180, "30"), (300, "60"), (600, "150"), (900, "240"), (1800, "1D"),
                       (2700, "720"), (3600, "1D"), (7200, "2D"), (14400, "1W"), (21600, "4D"), (43200, "1W"),
                       (86400, "15D"), (259200, "45D"), (604800, "15W"), (2592000, "15M")):
        if s <= limit:
            return htf
    return "45M"


def bsl_auto(tf: str) -> str:
    """lq_f_bsl_auto_tf: the HTF whose swing highs and lows are the suite's BSL and SSL (and the swings' window)."""
    s = in_seconds(PERIOD[tf])
    return ("15" if s <= 60 else "30" if s <= 180 else "60" if s <= 300 else "240" if s <= 1800 else
            "1D" if s <= 3600 else "1W" if s <= 14400 else "1M")


def valid_htf(htf: str, tf: str) -> bool:
    """ValidTimeframe: the HTF must be a whole multiple of the chart's timeframe (or a day or more, and longer)."""
    if htf in QUARTERLY:
        return True
    n2, n1 = in_seconds(htf), in_seconds(PERIOD[tf])
    if n2 is None:
        return False
    if n2 >= DAY and n2 > n1:
        return True
    return n1 < n2 and n2 % n1 == 0


def htf_name(htf: str) -> str:
    """HTFName: "Micro Cycle", "Quarterly", "Sessions", "15m", "4H"; a day or more keeps its own name ("1D")."""
    if htf in QUARTERLY:
        return {"SESSION_MICRO": "Micro Cycle", "SESSION_90": "Quarterly", "SESSION_6H": "Sessions"}[htf]
    s = in_seconds(htf)
    if s is None:
        return htf
    if s < 60:
        return f"{s}s"
    if s // 60 < 60:
        return f"{s // 60}m"
    if s // 3600 < 24:
        return f"{s // 3600}H"
    return _norm(htf)


def ltf_name(tf: str) -> str:
    s = in_seconds(PERIOD[tf])
    return f"{s}s" if s < 60 else f"{s // 60}m" if s < 3600 else f"{s // 3600}H" if s < DAY else PERIOD[tf]


def fvg_label(htf: str) -> str:
    """fvg_format_tf: the FVG labels' timeframe, "15M" (minutes), "4H", "1D", "1W"."""
    s = in_seconds(htf) or 0
    if s < 60:
        return f"{s}S"
    for size, unit, top in ((60, "M", 60), (3600, "H", 24), (DAY, "D", 7), (_WEEK, "W", 4), (2_592_000, "M", 12)):
        if s / size < top:
            return f"{round(s / size)}{unit}"
    return f"{round(s / 31_536_000)}Y"


# ── candle boundaries ─────────────────────────────────────────────────────────────────────────────────────
def _day_open(wall: np.ndarray) -> np.ndarray:
    return ((wall - DAY_OPEN) // DAY) * DAY + DAY_OPEN


def _trading_dates(wall: np.ndarray) -> np.ndarray:
    """Each wall second's trading date (the day after the eve whose 17:00 opened it), as datetime64[D]."""
    return ((wall - DAY_OPEN) // DAY + 1).astype("datetime64[D]")


def _eve(dates: np.ndarray) -> np.ndarray:
    """The 17:00 open, in wall seconds, of the trading dates given."""
    return (dates.astype("datetime64[D]").astype(np.int64) - 1) * DAY + DAY_OPEN


def _months(wall: np.ndarray) -> np.ndarray:
    """Each wall second's trading month as a count of months since 1970-01."""
    return _trading_dates(wall).astype("datetime64[M]").astype(np.int64)


def _month_open(months: np.ndarray) -> np.ndarray:
    return _eve(np.asarray(months, dtype=np.int64).astype("datetime64[M]").astype("datetime64[D]"))


_MICRO_GAP = (21 * 60 + 45, 24 * 60)   # SESSION_MICRO lists no session from 21:45 to midnight (see starts)


def starts(wall, tf: str) -> np.ndarray:
    """The start (wall seconds) of the ``tf`` candle each wall second falls in.

    - **Minutes:** counted from each trading day's 17:00 open, as the charts' own buckets are. A length that doesn't
      divide the day (150 minutes) restarts at the open.
    - **Days, weeks, months:** "1D" is the trading day, "1W" opens on Sunday at 17:00, and "1M" holds a calendar
      month's trading dates. Multiples count from 1970: trading days (weekdays) for "nD", weeks for "nW", and
      months for "nM", so "3M" is the quarter and "12M" the year.
    - **SESSION_6H and SESSION_90:** six-hour and 90-minute blocks from 18:00 New York. Both divide the day, so
      they are plain wall-clock buckets.
    - **SESSION_MICRO:** each 90-minute block split at 0, 22, 45 and 67 minutes. The indicator lists these sessions
      from 18:00 to 21:45 and from 00:00 to 18:00, and none from 21:45 to midnight. So, as there, the 21:22 candle
      runs on to midnight.
    """
    wall = np.asarray(wall, dtype=np.int64)
    tf = _norm(tf)
    if tf == "SESSION_6H":
        return (wall // 21600) * 21600
    if tf == "SESSION_90":
        return (wall // 5400) * 5400
    if tf == "SESSION_MICRO":
        minute = (wall % DAY) // 60
        block = minute // 90 * 90
        off = minute - block
        sub = np.where(off >= 67, 67, np.where(off >= 45, 45, np.where(off >= 22, 22, 0)))
        out = (wall // DAY) * DAY + (block + sub) * 60
        gap = (minute >= _MICRO_GAP[0]) & (minute < _MICRO_GAP[1])
        if gap.any():                     # no session: the candle before carries on
            out = out.astype(float)
            out[gap] = np.nan
            filled = np.maximum.accumulate(np.where(np.isnan(out), -np.inf, out))
            out = np.where(np.isfinite(filled), filled, (wall // DAY) * DAY + (21 * 60 + 22) * 60).astype(np.int64)
        return out
    if tf.isdigit():
        size = int(tf) * 60
        day_open = _day_open(wall)
        return day_open + ((wall - day_open) // size) * size
    n, unit = int(tf[:-1]), tf[-1]
    if unit == "D":
        if n == 1:
            return _day_open(wall)
        ordinal = np.busday_count(np.datetime64("1970-01-01"), _trading_dates(wall))
        first = np.busday_offset(np.datetime64("1970-01-01"), (ordinal // n) * n, roll="forward")
        return _eve(first)
    if unit == "W":
        weeks = bucket(wall, "W1")
        if n == 1:
            return weeks
        index = (weeks - bucket(np.array([3 * DAY + DAY_OPEN]), "W1")[0]) // _WEEK
        return weeks - (index % n) * _WEEK
    if unit == "M":
        months = _months(wall)
        return _month_open((months // n) * n)
    raise ValueError(f"tf: not a timeframe the indicator uses: {tf!r}")


def period_end(start: int, tf: str) -> int:
    """When the ``tf`` candle that starts at ``start`` closes: ``time_close(tf)`` in wall seconds.

    A minute candle ends at its length or at the next 17:00 open, whichever comes first. The Quarterly clocks
    use the nominal length, as the indicator does in its time arithmetic.
    """
    tf = _norm(tf)
    if tf in QUARTERLY:
        return int(start) + QUARTERLY[tf]
    if tf.isdigit():
        day_open = int(_day_open(np.array([start]))[0])
        return min(int(start) + int(tf) * 60, day_open + DAY)
    n, unit = int(tf[:-1]), tf[-1]
    if unit == "D":
        if n == 1:
            return int(start) + DAY
        first = _trading_dates(np.array([start]))
        nxt = np.busday_offset(first, n, roll="forward")
        return int(_eve(nxt)[0])
    if unit == "W":
        return int(start) + n * _WEEK
    if unit == "M":
        months = _months(np.array([start]))
        return int(_month_open(months + n)[0])
    raise ValueError(f"tf: not a timeframe the indicator uses: {tf!r}")
