"""The book (thesis-engine Requirement 3): what AlgoMindDIS's analyzers see, as of each close.

The book detects nothing (TE-D15). Each level frame's arrays are AlgoMindDIS's ``array_table`` at V2 (the trader's
order blocks and breakers, the FVGs as the gap), with the inverted FVGs the array layer now has
(``liquidity_engine.context.inversions``); each is dated by the candle that completed it and ended by the first close
beyond its far edge, as the table reads it. Swings are the analyzers' (``algomind_dis.analyzers.structure``, lookback
2), ranges are their SWING ranges (``ranges.swing_range``), and the execution frame's swings and down-close runs come
from the functions they use (``measures``, ``blocks.runs``). Everything is computed once over the full frame and read
as of a cut: each item reads only candles up to its own index, so the book at t equals the analyzers run on the
candles closed by t (Requirement 3.4, Property 4).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from algomind_dis.analyzers.arrays import array_table
from algomind_dis.analyzers.ranges import swing_range
from algomind_dis.analyzers.structure import LOOKBACK
from algomind_dis.records import DealingRange, make_id
from liquidity_engine.context.blocks import delivery_blocks, runs
from liquidity_engine.context.frame_state import Candles
from liquidity_engine.context.inversions import inverted_fvgs
from liquidity_engine.context.measures import average_range, swing_highs, swing_lows
from thesis_engine.settings import V1, Settings

__all__ = ["NEVER", "ArrayRow", "Book", "Frame", "next_beyond"]

NEVER = np.iinfo(np.int64).max


@dataclass(frozen=True)
class ArrayRow:
    id: str
    tf: str
    kind: str
    side: str
    low: float
    high: float
    k: int                       # the index of the candle that completed it
    formed_at: int
    end: int                     # the index of the first close beyond its far edge (NEVER: none)
    high_probability: bool


def next_beyond(x: np.ndarray, lower: bool) -> np.ndarray:
    """For each i, the first j > i with x[j] < x[i] (``lower``) or x[j] > x[i]; NEVER when there is none."""
    n = len(x)
    out = np.full(n, NEVER, dtype=np.int64)
    stack: List[int] = []
    for j in range(n):
        v = x[j]
        while stack and ((v < x[stack[-1]]) if lower else (v > x[stack[-1]])):
            out[stack.pop()] = j
        stack.append(j)
    return out


def _first_close(c: np.ndarray, start: int, below: Optional[float], above: Optional[float]) -> int:
    later = c[start:]
    hit = np.flatnonzero(later < below) if below is not None else np.flatnonzero(later > above)
    return start + int(hit[0]) if len(hit) else NEVER


class Frame:
    """One level frame's arrays, swings and ranges over its full history, read as of any cut."""

    def __init__(self, market: str, c: Candles, s: Settings = V1) -> None:
        self.market, self.c, self.s = market, c, s
        self.highs = np.array(swing_highs(c.h, LOOKBACK), dtype=np.int64)
        self.lows = np.array(swing_lows(c.l, LOOKBACK), dtype=np.int64)
        self.low_taken = next_beyond(c.l, lower=True)[self.lows] if len(self.lows) else np.array([], np.int64)
        self.high_taken = next_beyond(c.h, lower=False)[self.highs] if len(self.highs) else np.array([], np.int64)
        self.rows = self._rows()
        self._k = np.array([r.k for r in self.rows], dtype=np.int64)
        self._end = np.array([r.end for r in self.rows], dtype=np.int64)
        self._bull = np.array([r.side == "BULLISH" for r in self.rows], dtype=bool)
        self._ranges: Dict[int, Optional[DealingRange]] = {}

    def _rows(self) -> List[ArrayRow]:
        c, tf = self.c, self.c.tf
        if not len(c):
            return []
        hp = {(b.kind, b.direction.value, float(b.low), float(b.high), int(c.end[b.formed])): b.high_probability
              for b in delivery_blocks(c.o, c.h, c.l, c.c)}
        table = array_table(c, self.s.dis)
        rows = []
        for i, a in enumerate(table.raw):
            side = a.direction.value
            key = (a.kind, side, float(a.low), float(a.high), int(a.formed_at))
            rows.append(ArrayRow(make_id(self.market, tf, a.kind, side, a.formed_at, a.low, a.high), tf, a.kind, side,
                                 float(a.low), float(a.high), int(table.k[i]), int(a.formed_at), int(table.breach[i]),
                                 bool(hp.get(key, False))))
        for a in inverted_fvgs(c):                 # the array layer's inverted FVGs, ended as the table ends arrays
            k = int(np.searchsorted(c.end, a.formed_at, "left"))
            bullish = a.direction.value == "BULLISH"
            end = _first_close(c.c, k + 1, below=a.low if bullish else None, above=None if bullish else a.high)
            rows.append(ArrayRow(make_id(self.market, tf, a.kind, a.direction.value, a.formed_at, a.low, a.high), tf,
                                 a.kind, a.direction.value, float(a.low), float(a.high), k, int(a.formed_at), end,
                                 False))
        return rows

    def n(self, t: int) -> int:
        """The number of candles closed by ``t``."""
        return int(np.searchsorted(self.c.end, t, "right"))

    def cut(self, n: int) -> Candles:
        c = self.c
        return Candles(c.tf, c.t[:n], c.end[:n], c.o[:n], c.h[:n], c.l[:n], c.c[:n])

    def live(self, n: int, side: str) -> List[ArrayRow]:
        """The side's arrays completed by candle n - 1 and not ended by it."""
        if not self.rows:
            return []
        mask = (self._k <= n - 1) & (self._end >= n) & (self._bull == (side == "BULLISH"))
        return [self.rows[i] for i in np.flatnonzero(mask)]

    def ended(self, row: ArrayRow, n: int) -> bool:
        return row.end < n

    def range(self, n: int) -> Optional[DealingRange]:
        """The SWING dealing range as of the cut (AlgoMindDIS's ``swing_range``)."""
        if n not in self._ranges:
            self._ranges[n] = swing_range(self.market, self.cut(n), (self.highs, self.lows)) if n > 0 else None
        return self._ranges[n]

    def average_range(self, n: int) -> float:
        return average_range(self.c.h, self.c.l, n)

    def untaken(self, n: int, lows: bool) -> np.ndarray:
        """The prices of the swings known by the cut (confirmed by candle n - 1) and not traded beyond by it."""
        idx, taken = (self.lows, self.low_taken) if lows else (self.highs, self.high_taken)
        if not len(idx):
            return np.array([])
        mask = (idx + LOOKBACK <= n - 1) & (taken >= n)
        return (self.c.l if lows else self.c.h)[idx[mask]]


class Book:
    """The level frames, D1 and W1 for the ranges and the ADR, and the execution frame's pools and runs."""

    def __init__(self, market: str, frames: Dict[str, Candles], s: Settings = V1) -> None:
        self.market, self.s = market, s
        self.frames = {tf: Frame(market, frames[tf], s) for tf in dict.fromkeys((*s.level_frames, "D1", "W1"))}
        self.h1 = frames["H1"]
        e = self.e = frames[s.e_frame]
        lb = s.e_swing_lookback
        self._e_pools: Dict[bool, Dict[int, List[int]]] = {}
        for lows in (True, False):
            idx = np.array((swing_lows if lows else swing_highs)(e.l if lows else e.h, lb), dtype=np.int64)
            taken = next_beyond(e.l if lows else e.h, lower=lows)[idx] if len(idx) else np.array([], np.int64)
            by_taker: Dict[int, List[int]] = {}
            for i, j in zip(idx.tolist(), taken.tolist()):
                if j != NEVER:
                    by_taker.setdefault(j, []).append(i)
            self._e_pools[lows] = by_taker
        self._runs = {bullish: {through: (first, last) for first, last, through in runs(e.o, e.c, bullish)}
                      for bullish in (True, False)}
        # The trading day's Asia range (V2's pools): its candles from the day's open to 00:00 New York, read once
        # midnight has passed.
        from thesis_engine.clock import NY, trading_day
        self._h0 = s.day_open_hour(market)
        self._e_hour = np.asarray(pd.DatetimeIndex(pd.to_datetime(e.t, utc=True)).tz_convert(NY).hour) if len(e)             else np.zeros(0, dtype=int)
        self._e_day = trading_day(e.t, market, s) if len(e) else np.zeros(0, dtype=np.int64)
        self._asia: Dict[int, Tuple[float, float, int]] = {}
        night = self._e_hour >= self._h0
        if night.any():
            g = pd.DataFrame({"d": self._e_day[night], "l": e.l[night], "h": e.h[night]}).groupby("d").agg(
                l=("l", "min"), h=("h", "max"))
            for d, row in g.iterrows():
                midnight = int(pd.Timestamp(int(d)).tz_localize(NY).tz_convert("UTC").value)
                self._asia[int(d)] = (float(row["l"]), float(row["h"]), midnight)

    def n(self, tf: str, t: int) -> int:
        return self.frames[tf].n(t) if tf in self.frames else int(np.searchsorted(self.h1.end, t, "right"))

    def adr(self, t: int) -> float:
        d1 = self.frames["D1"].c
        return average_range(d1.h, d1.l, self.frames["D1"].n(t), self.s.adr_days)

    def e_pools_taken(self, m: int, bullish: bool) -> List[Tuple[int, float]]:
        """The E swings (a bullish hand's lows, a bearish one's highs) known before candle m and first traded
        beyond by it: (swing index, price)."""
        lb = self.s.e_swing_lookback
        prices = self.e.l if bullish else self.e.h
        return [(i, float(prices[i])) for i in self._e_pools[bullish].get(m, []) if i + lb <= m - 1]

    def h1_pool_taken(self, m: int, bullish: bool) -> Optional[float]:
        """The previous H1 candle's low (a bearish hand: its high), when E candle m is the first since that H1 close
        to trade beyond it."""
        e, h1 = self.e, self.h1
        k = int(np.searchsorted(h1.end, e.t[m], "right")) - 1      # the last H1 closed when candle m opened
        if k < 0:
            return None
        price = float(h1.l[k] if bullish else h1.h[k])
        start = int(np.searchsorted(e.t, h1.end[k], "left"))
        before = (e.l if bullish else e.h)[start:m]
        untaken = (before >= price).all() if bullish else (before <= price).all()
        now = e.l[m] < price if bullish else e.h[m] > price
        return price if untaken and now else None

    def _first_beyond(self, m: int, price: float, since: int, bullish: bool) -> bool:
        """Whether E candle m is the first since ``since`` (UTC ns) to trade beyond ``price``."""
        e = self.e
        start = int(np.searchsorted(e.t, since, "left"))
        if start > m:
            return False
        before = (e.l if bullish else e.h)[start:m]
        untaken = bool((before >= price).all()) if bullish else bool((before <= price).all())
        return untaken and bool(e.l[m] < price if bullish else e.h[m] > price)

    def trader_pools_taken(self, m: int, bullish: bool) -> List[Tuple[str, float]]:
        """V2's pools (Requirement 15.2) that E candle m is the first to trade beyond since each became known: the
        previous D1, H4 and H1 extremes, the trading day's Asia range (from 00:00 New York) and the untaken H1 swings
        (a bullish hand's lows; a bearish one's highs)."""
        t, side, out = int(self.e.t[m]), ("low" if bullish else "high"), []
        for tf, name in (("D1", "previous day's"), ("H4", "previous H4"), ("H1", "previous H1")):
            c = self.frames[tf].c
            k = int(np.searchsorted(c.end, t, "right")) - 1
            if k >= 0:
                price = float(c.l[k] if bullish else c.h[k])
                if self._first_beyond(m, price, int(c.end[k]), bullish):
                    out.append((f"the {name} {side} {price:.6g}", price))
        if len(self._e_hour) and self._e_hour[m] < self._h0:
            asia = self._asia.get(int(self._e_day[m]))
            if asia is not None:
                price = asia[0] if bullish else asia[1]
                if self._first_beyond(m, price, asia[2], bullish):
                    out.append((f"the Asia {side} {price:.6g}", price))
        h1 = self.frames["H1"]
        n = h1.n(t)
        if n:
            for price in sorted(set(float(x) for x in h1.untaken(n, lows=bullish))):
                if self._first_beyond(m, price, int(h1.c.end[n - 1]), bullish):
                    out.append((f"the H1 swing {side} {price:.6g}", price))
        return out

    def run_mt(self, first: int, last: int) -> float:
        """The mean threshold of E candles first..last's bodies (the trader's order block)."""
        e = self.e
        lo = float(np.minimum(e.o[first:last + 1], e.c[first:last + 1]).min())
        hi = float(np.maximum(e.o[first:last + 1], e.c[first:last + 1]).max())
        return (lo + hi) / 2

    def cisd(self, m: int, bullish: bool, swept: int) -> Optional[Tuple[int, int]]:
        """The run E candle m closes through (a bullish CISD: above the open of a down-close run's first candle),
        when that run ended at or after the sweep: (first, last)."""
        run = self._runs[bullish].get(m)
        return run if run is not None and run[1] >= swept else None
