"""The indicator's HTF fair value gaps (algo-backtester Requirement 21.2): its only PD array.

The indicator's rules:
- **Timeframe.** One HTF per chart, chosen automatically (M1 shows M15 gaps, M5 shows H1, M15 shows H4, H1 shows
  D1) or set by hand.
- **The gap.** At each new HTF candle, the indicator reads the last three closed ones. A gap is bullish when C3's
  low is above C1's high (the zone runs from C1's high to C3's low), and bearish when C3's high is below C1's low.
  That is the trader's own FVG (AR-D27), on closed candles only.
- **Drawing.** The box runs from C1's open to the clock, labelled "FVG+4H" or "FVG-4H".
- **Invalidation.** An HTF close beyond the far edge (below the bottom of a bullish gap, above the top of a
  bearish one) deletes it. Nothing becomes an inversion here.
- **How many.** Only the newest ``fvg_max_fvgs`` (3) are kept.

Ported from the Pine "FVG Engine" block and ``fvg_detect``.
"""
from __future__ import annotations

import copy
from typing import Optional

from algo_research.fractal_poi.chart import Chart, Now, box, hexa, label, line
from algo_research.fractal_poi.frames import fvg_auto, fvg_label, starts
from algo_research.fractal_poi.settings import FractalSettings

__all__ = ["Imbalance"]

FILL = hexa("808080", 90)
MID = hexa("787b86", 75)
TEXT = hexa("787b86")


class Imbalance:
    def __init__(self, chart: Chart, s: FractalSettings) -> None:
        self.ch, self.s = chart, s
        self.htf = fvg_auto(chart.tf) if s.fvg_auto_mode else s.fvg_manual_htf
        self.starts = starts(chart.time, self.htf)
        self.forming: Optional[list] = None          # start, open, high, low, close
        self.closed: list[list] = []                 # the last three closed HTF candles, oldest first
        self.fvgs: list[dict] = []                   # oldest first: top, bottom, bull, start

    _STATE = ("forming", "closed", "fvgs")

    def state(self) -> dict:
        return copy.deepcopy({k: getattr(self, k) for k in self._STATE})

    def restore(self, state: dict) -> None:
        for k, v in copy.deepcopy(state).items():
            setattr(self, k, v)

    def step(self, i: int) -> None:
        ch, s = self.ch, self.s
        new = self.forming is None or self.starts[i] != self.forming[0]
        if new and self.forming is not None:
            self.closed.append(self.forming)
            del self.closed[:-3]
            if len(self.closed) == 3:
                c1, c3 = self.closed[0], self.closed[2]
                found = None
                if c3[2] < c1[3] and s.fvg_show_bear:
                    found = {"top": c1[3], "bottom": c3[2], "bull": False, "start": int(c1[0])}
                elif c3[3] > c1[2] and s.fvg_show_bull:
                    found = {"top": c3[3], "bottom": c1[2], "bull": True, "start": int(c1[0])}
                if found and not any(f["bull"] == found["bull"] and f["top"] == found["top"]
                                     and f["bottom"] == found["bottom"] for f in self.fvgs):
                    self.fvgs.append(found)
            close = self.closed[-1][4]
            self.fvgs = [f for f in self.fvgs if not ((close < f["bottom"]) if f["bull"] else (close > f["top"]))]
            del self.fvgs[:max(0, len(self.fvgs) - s.fvg_max_fvgs)]
        if new:
            self.forming = [int(self.starts[i]), ch.o[i], ch.h[i], ch.l[i], ch.c[i]]
        else:
            f = self.forming
            f[2], f[3], f[4] = max(f[2], ch.h[i]), min(f[3], ch.l[i]), ch.c[i]

    def draw(self, pos: int, now: Now, d: FractalSettings) -> list[dict]:
        if not d.fvg_show:
            return []
        out, tf = [], fvg_label(self.htf)
        for f in self.fvgs:
            mid = (f["top"] + f["bottom"]) / 2
            if d.fvg_show_boxes:
                out.append(box("fvg", f["start"], f["top"], now.time, f["bottom"], FILL, None))
                if d.fvg_show_midline:
                    out.append(line("fvg", f["start"], mid, now.time, mid, MID, "dotted"))
            if d.fvg_show_labels:
                out.append(label("fvg", now.time, mid, f"FVG{'+' if f['bull'] else '-'}{tf}", TEXT, "right", "small"))
        return out
