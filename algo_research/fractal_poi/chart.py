"""The chart the indicator runs on, and what it draws (algo-backtester Requirements 21 and 22).

``Chart`` holds the chart timeframe's candles over the loaded window, aggregated from M1 exactly as Noculus
aggregates them (``algo_research.replay.timeframes.aggregate``), with each candle's close time. The indicator
reads them one by one. A candle is read once it has closed by the clock, and never before.

What the indicator draws is plain data, Pine's three objects:
- ``box``: x1, y1, x2, y2, a fill and an optional border;
- ``line``: two points, a colour, a style (solid, dashed, dotted), a width, and ``extend`` "both" for a vertical
  line across the pane;
- ``label``: a point and its text. Its style is Pine's: "down" sits above the point, "up" below it, "left" to
  its right, "right" to its left.

Every x is a time in New York wall seconds, the chart's own axis. A position Pine counts in bars ahead of the
last one (the HTF candles drawn to the right of price) is that many chart candles past the clock's candle, so
the page places it where TradingView would. Every item carries ``l``, its layer, which the drawing inputs show
or hide.

Colours are ``"#rrggbb@alpha"``, or ``"ink@alpha"`` for the indicator's black, which the page paints in the
theme's foreground so it reads on a dark chart too.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

import numpy as np

from algo_research.fractal_poi.frames import PERIOD, period_end
from algo_research.replay.timeframes import aggregate, bucket, seconds_of

__all__ = ["Chart", "Now", "box", "label", "line", "rgb"]


def rgb(r: int, g: int, b: int, transp: float = 0) -> str:
    """``color.rgb(r, g, b, transp)`` / ``color.new``: transparency 0 (solid) to 100 (invisible)."""
    alpha = round(max(0.0, min(1.0, 1 - transp / 100)), 3)
    return f"ink@{alpha}" if (r, g, b) == (0, 0, 0) else f"#{r:02x}{g:02x}{b:02x}@{alpha}"


def hexa(code: str, transp: float = 0) -> str:
    code = code.lstrip("#")
    return rgb(int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16), transp)


def box(layer: str, x1: float, y1: float, x2: float, y2: float, fill: str, border: Optional[str] = None) -> dict:
    return {"k": "box", "l": layer, "x1": _x(x1), "y1": float(y1), "x2": _x(x2), "y2": float(y2), "fill": fill,
            "border": border}


def line(layer: str, x1: float, y1: float, x2: float, y2: float, color: str, style: str = "solid", width: int = 1,
         extend: Optional[str] = None) -> dict:
    out = {"k": "line", "l": layer, "x1": _x(x1), "y1": float(y1), "x2": _x(x2), "y2": float(y2), "c": color,
           "s": style.lower(), "w": int(width)}
    if extend:
        out["ext"] = extend
    return out


def label(layer: str, x: float, y: float, text: str, color: str, style: str = "down", size: str = "small") -> dict:
    return {"k": "label", "l": layer, "x": _x(x), "y": float(y), "t": str(text), "c": color, "st": style,
            "sz": size.lower()}


def _x(x: float) -> float:
    x = float(x)
    return int(x) if x.is_integer() else round(x, 1)


class Now(NamedTuple):
    """The clock's candle: the chart's last candle at the clock (forming, or just closed), as Pine's last bar."""
    idx: int          # its index among the chart's candles
    time: int         # its open, wall seconds
    end: int          # its close
    clock: int        # the replay clock itself


class Chart:
    """One instrument's candles of one chart timeframe over the loaded window, with their close times."""

    def __init__(self, wall: np.ndarray, o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, tf: str) -> None:
        self.tf, self.period, self.sec = tf, PERIOD[tf], seconds_of(tf)
        self.m1_wall = np.asarray(wall, dtype=np.int64)
        bars = aggregate(self.m1_wall, o, h, l, c, tf)
        self.time = bars["time"].to_numpy(dtype=np.int64)
        self.o, self.h, self.l, self.c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
        self.end = np.array([period_end(int(t), self.period) for t in self.time], dtype=np.int64)
        self.n = len(self.time)

    def closed_by(self, clock: int) -> int:
        """The index of the last candle closed by ``clock`` (-1 before the first)."""
        return int(np.searchsorted(self.end, int(clock), side="right")) - 1

    def now(self, clock: int) -> Optional[Now]:
        """The candle the chart shows last at ``clock``: the one holding the last M1 bar closed by then."""
        k = int(np.searchsorted(self.m1_wall, int(clock) - 60, side="right")) - 1
        if k < 0:
            return None
        start = int(bucket(self.m1_wall[k:k + 1], self.tf)[0])
        idx = int(np.searchsorted(self.time, start, side="left"))
        return Now(idx, start, period_end(start, self.period), int(clock))

    def x(self, idx: float, pos: int, now: Now) -> float:
        """The time of candle ``idx`` (fractions allowed): its own open once it is read, else counted in chart
        candles from the clock's candle, so a candle not yet read never lends its time."""
        if idx <= pos and float(idx).is_integer():
            return int(self.time[int(idx)])
        if idx == now.idx:
            return now.time
        return now.time + (idx - now.idx) * self.sec
