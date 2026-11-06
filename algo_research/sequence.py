"""The trader's sequence, v0: one market-day read top-down, time first and then price (context-engine Req 33).

Written from the trader's Backtest Diary for GBPUSD, Thursday 29 Oct 2026, and their answers of 31 Oct 2026.
Frozen before their next sample was read, so each later sample tests it blind. New York time throughout (the
trader's charts are on it); the day runs 17:00-17:00 and the rollover minutes (16:55-17:05) are left out, as in the
2018-2024 search. Each step reads only the candles closed when it is taken. A buy read (a sell is the mirror):

- **Turtle soup** on any frame, named by its C1: C2 trades under C1's low and closes back above it. One candle
  alone is not a soup.
- **Valid** once the frame below confirms a CISD: a close above the open of the run of down-closing candles that
  delivered C2's low. An up candle or a doji (a body under a tenth of its range) ends the run.
- **The narrative** (the IRL-ERL cycle): the latest valid W1 soup whose C2 (in the month's first two weeks) took an
  untaken low of the last four quarters or three months (external range liquidity), with a D1 CISD by its close.
  Its draw is the nearest W1 gap above whose CE price hasn't reached (internal range liquidity), else a D1 one. The
  side ends when price reaches the draw's CE (delivered) or a D1 candle closes under C2's low (a wick under it is
  liquidation). A soup against a live side is manipulation, not a turn.
- **The setup:** a D1 soup on the side, its C2 on Monday to Wednesday, its low inside a key level (a D1 or W1 gap of
  the side, an inverted one, or an opening gap of the last ten trading days), with an H4 or H1 CISD by C2's close.
  The next day is C3.
- **C3:** Q1 (18:00-00:00) is the range. In Q2 (00:00-06:00) price takes Q1's low: the Judas swing. An M5 CISD
  before 12:00 confirms it. The buy limit goes at the open of the run's last down candle (the order block) when it
  is in discount of the leg from the Judas low; it is good until 12:00 and its stop is the Judas low.
- **Targets:** the Judas swing's deviations (from the last M5 swing high before the low, to the low), each with the
  pools and gaps within a fifth of a deviation and its distance in average daily ranges. The draw's level is the
  deviation in confluence with the narrative's draw; the trader frames partials on the ones before it.

    python -m algo_research.sequence --symbol GBPUSDm --day 2026-10-29        (bars from the MT5 terminal)
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

from algo_research.search_bias import drop_rollover, gaps

__all__ = ["DEVIATIONS", "Market", "Read", "cisd", "key_zones", "narrative", "opening_gaps", "read_day", "soups"]

NY = "America/New_York"
DOJI = 0.1                      # a candle with a body under a tenth of its range ends a CISD run
DEVIATIONS = (1.0, 2.0, 2.5, 4.0, 4.5)
CONFLUENCE = 0.2                # a pool or gap within a fifth of a deviation of a level
D1_C2_DAYS = (0, 1, 2)          # Model A's D1 C2: Monday to Wednesday
W1_C2_WEEKS = 2                 # Model A's W1 C2: the month's first two weeks
QUARTERS, MONTHS = 4, 3         # the external lows: those of the last four quarters and three months
OPENING_GAP_DAYS = 10
ADR_DAYS = 10
_SHIFT = pd.Timedelta(hours=7)  # New York + 7 h puts the 17:00 open at midnight
_HOUR = pd.Timedelta(hours=1)
_WORDS = {1: {"buy": "buy", "low": "low", "high": "high", "under": "under", "above": "above", "down": "down",
              "discount": "discount", "BULLISH": "BULLISH", "+": "+", "Q1 low": "Q1 low"},
          -1: {"buy": "sell", "low": "high", "high": "low", "under": "above", "above": "under", "down": "up",
               "discount": "premium", "BULLISH": "BEARISH", "+": "-", "Q1 low": "Q1 high"}}


# ── the candles ────────────────────────────────────────────────────────────

def _ns(times) -> np.ndarray:
    return pd.DatetimeIndex(times).as_unit("ns").asi8


def _ny(t: int) -> pd.Timestamp:
    return pd.Timestamp(int(t), tz="UTC").tz_convert(NY).tz_localize(None)


def _utc(wall: pd.Timestamp) -> int:
    return int(pd.Timestamp(wall).tz_localize(NY).tz_convert("UTC").value)


def _flip(bars: pd.DataFrame) -> pd.DataFrame:
    """The mirror image: a sell read is the buy read of the negated prices."""
    out = bars.copy()
    out["open"], out["close"] = -bars["open"], -bars["close"]
    out["high"], out["low"] = -bars["low"], -bars["high"]
    return out


def candles(bars: pd.DataFrame, step: pd.Timedelta) -> dict[str, pd.DataFrame]:
    """The New York candles of ``bars`` (columns time (UTC), open, high, low, close; ``step`` long each, the rollover
    left out): H1, H4 (from 17:00), D1 (17:00-17:00, ``date`` the trading date), W1 (from Sunday 17:00, ``monday``),
    and M5 and M15 when the bars are finer than an hour. ``t_open``/``t_close``: ns, UTC."""
    b = drop_rollover(bars)
    local = b["time"].dt.tz_convert(NY).dt.tz_localize(None)
    trading = (local + _SHIFT).dt.normalize()
    keys = {"H1": b["time"].dt.floor("h"), "H4": (local + _SHIFT).dt.floor("4h"), "D1": trading,
            "W1": trading - pd.to_timedelta(trading.dt.dayofweek, unit="D")}
    if step < _HOUR:
        keys.update(M5=b["time"].dt.floor("5min"), M15=b["time"].dt.floor("15min"))
    base = pd.DataFrame({"open": b["open"].to_numpy(float), "high": b["high"].to_numpy(float),
                         "low": b["low"].to_numpy(float), "close": b["close"].to_numpy(float),
                         "t": _ns(b["time"]), "date": trading.to_numpy()})
    out = {}
    for tf, key in keys.items():
        g = base.groupby(key.to_numpy(), sort=True)
        frame = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                              "close": g["close"].last(), "t_open": g["t"].first(),
                              "t_close": g["t"].last() + step.value, "date": g["date"].last()})
        if tf == "W1":
            frame["monday"] = frame.index
        out[tf] = frame.reset_index(drop=True)
    return out


@dataclass
class Market:
    """One market's bars, buy side up: ``history`` (H1 or finer, at least a year before the day, for the narrative and
    the key levels) and ``m1`` (the days of C2 and C3 and the one after, for the lower frames and the path)."""
    history: pd.DataFrame
    m1: pd.DataFrame
    hist: dict = field(init=False)
    fine: dict = field(init=False)

    def __post_init__(self) -> None:
        step = pd.Timedelta(pd.Series(self.history["time"]).diff().median())
        self.hist = candles(self.history, step)
        self.fine = candles(self.m1, pd.Timedelta(minutes=1))

    def flipped(self) -> "Market":
        return Market(_flip(self.history), _flip(self.m1))


# ── the soup and its CISD ──────────────────────────────────────────────────

def soups(b: pd.DataFrame) -> np.ndarray:
    """The rows (C2) whose candle trades under the low of the candle before (C1) and closes back above it."""
    lo, cl = b["low"].to_numpy(float), b["close"].to_numpy(float)
    k = np.arange(1, len(b))
    return k[(lo[k] < lo[k - 1]) & (cl[k] > lo[k - 1])]


def _down(o, h, l, c, i: int) -> bool:
    return c[i] < o[i] and o[i] - c[i] >= DOJI * (h[i] - l[i])


def cisd(child: pd.DataFrame, k: int, until: int) -> Optional[dict]:
    """The CISD for the low of ``child``'s candle ``k``: the run of down-closing candles that delivered it (candle k
    when it closed down, and those before it back to the first that didn't), its first open the level, and the
    first candle after the run closing above the level by ``until`` (``confirm``: its row, or -1)."""
    o, h, l, c = (child[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    end = k if _down(o, h, l, c, k) else k - 1
    if end < 0 or not _down(o, h, l, c, end):
        return None
    start = end
    while start > 0 and _down(o, h, l, c, start - 1):
        start -= 1
    tc = child["t_close"].to_numpy(np.int64)
    confirm = -1
    for i in range(end + 1, len(child)):
        if tc[i] > until:
            break
        if c[i] > o[start]:
            confirm = i
            break
    return {"start": start, "end": end, "level": float(o[start]), "confirm": confirm}


# ── the key levels ─────────────────────────────────────────────────────────

def opening_gaps(history: pd.DataFrame, before: int, days: int = OPENING_GAP_DAYS) -> list[tuple[str, float, float]]:
    """The opening gaps (NDOG, NWOG on Mondays) of the last ``days`` trading dates opened before ``before``: the
    last close before 16:55 New York and the first open at 18:00 or later."""
    local = history["time"].dt.tz_convert(NY).dt.tz_localize(None)
    clock = local.dt.hour * 60 + local.dt.minute
    t = _ns(history["time"])
    out = []
    for d in pd.DatetimeIndex(sorted(set((local[clock >= 18 * 60] + _SHIFT).dt.normalize()))):
        eve = d - pd.Timedelta(days=3 if d.dayofweek == 0 else 1)
        closes = history[(local >= eve) & (local < eve + pd.Timedelta(hours=16, minutes=55))]
        opens = history[(local >= d - pd.Timedelta(hours=6)) & (local < d) & (t < before)]
        if closes.empty or opens.empty:
            continue
        c, o = float(closes["close"].iloc[-1]), float(opens["open"].iloc[0])
        name = f"{'NWOG' if d.dayofweek == 0 else 'NDOG'} {d:%d %b}"
        out.append((name, min(c, o), max(c, o)))
    return out[-days:]


def _span(first, last, t: int) -> str:
    """'07 Sep-21 Sep' for a gap's first and third candles, with the year on a date outside the year of ``t``."""
    year = _ny(t).year
    days = (pd.Timestamp(first), pd.Timestamp(last))
    return "-".join(f"{x:%d %b}" + ("" if x.year == year else f" {x.year}") for x in days)


def key_zones(m: Market, before: int) -> list[tuple[str, float, float]]:
    """The buy side's key levels known before ``before``: D1 and W1 gaps of the side not closed through, the
    other side's gaps closed through and not closed back (inverted), and the opening gaps; (name, bottom, top)."""
    zones = []
    for tf in ("D1", "W1"):
        b = m.hist[tf][m.hist[tf]["t_close"] <= before].reset_index(drop=True)
        when = b["monday"] if tf == "W1" else b["date"]
        for g in gaps(b).itertuples():
            name = _span(when.iloc[g.i - 2], when.iloc[g.i], before)
            if g.side > 0 and g.filled > before:
                zones.append((f"{tf} +FVG {name}", g.far, g.near))
            elif g.side < 0 and g.filled <= before:
                after = b[b["t_close"] > g.filled]
                if not (after["close"] < g.near).any():
                    zones.append((f"{tf} +IFVG {name}", g.near, g.far))
    return zones + opening_gaps(m.history, before)


def _external_lows(d1: pd.DataFrame, before: int) -> list[tuple[str, float]]:
    """The lows of the last four quarters and three months before ``before`` that no D1 candle has traded under."""
    b = d1[d1["t_close"] <= before]
    if b.empty:
        return []
    dates = pd.DatetimeIndex(b["date"])
    now = pd.Timestamp(_ny(before)) + _SHIFT
    out = []
    for freq, n in (("Q", QUARTERS), ("M", MONTHS)):
        period = dates.to_period(freq)
        for back in range(1, n + 1):
            p = now.to_period(freq) - back
            inside = b[period == p]
            if inside.empty:
                continue
            low = float(inside["low"].min())
            if not (b[period > p]["low"] < low).any():
                out.append((f"{p.year} Q{p.quarter} low" if freq == "Q" else f"{p.strftime('%b %Y')} low", low))
    return out


def _draw(m: Market, w: int, close: float) -> Optional[dict]:
    """The buy draw of the W1 soup at row ``w``: the nearest W1 gap above ``close`` (an inefficiency of the other
    side) whose CE no D1 candle has reached since it formed, else the nearest D1 one."""
    when = m.hist["W1"]["t_close"].iloc[w]
    d1 = m.hist["D1"]
    for tf in ("W1", "D1"):
        b = m.hist[tf][m.hist[tf]["t_close"] <= when].reset_index(drop=True)
        best = None
        for g in gaps(b).itertuples():
            ce = (g.near + g.far) / 2
            seen = d1[(d1["t_open"] >= g.formed) & (d1["t_close"] <= when)]
            if g.side < 0 and g.near > close and not (seen["high"] >= ce).any():
                if best is None or g.near < best["near"]:
                    label = b["monday"] if tf == "W1" else b["date"]
                    best = {"name": f"{tf} gap {_span(label.iloc[g.i - 2], label.iloc[g.i], when)}",
                            "near": float(g.near), "far": float(g.far), "ce": float(ce)}
        if best:
            return best
    return None


# ── the narrative ──────────────────────────────────────────────────────────

def _turns(m: Market, as_of: int) -> list[dict]:
    """The buy turns closed by ``as_of``: valid W1 soups, C2 in the month's first two weeks, its low taking an
    external low, a D1 CISD by its close."""
    w1, d1 = m.hist["W1"], m.hist["D1"]
    out = []
    for k in soups(w1[w1["t_close"] <= as_of]):
        monday = pd.Timestamp(w1["monday"].iloc[k])
        if (monday.day - 1) // 7 + 1 > W1_C2_WEEKS:
            continue
        taken = [(n, x) for n, x in _external_lows(d1, int(w1["t_open"].iloc[k])) if w1["low"].iloc[k] < x]
        if not taken:
            continue
        days = d1[(d1["t_open"] >= w1["t_open"].iloc[k]) & (d1["t_close"] <= w1["t_close"].iloc[k])]
        if days.empty:
            continue
        shift = cisd(d1, int(days["low"].idxmin()), int(w1["t_close"].iloc[k]))
        if not shift or shift["confirm"] < 0:
            continue
        out.append({"t": int(w1["t_close"].iloc[k]), "c1": pd.Timestamp(w1["monday"].iloc[k - 1]), "c2": monday,
                    "low": float(w1["low"].iloc[k]), "erl": taken, "cisd": shift,
                    "cisd_at": int(d1["t_close"].iloc[shift["confirm"]]),
                    "draw": _draw(m, k, float(w1["close"].iloc[k]))})
    return out


def _signed(turn: dict, side: int) -> dict:
    """A turn's prices back on the real side, a sell turn's pools named as the highs they are."""
    erl = [(n if side > 0 else n.replace(" low", " high"), side * x) for n, x in turn["erl"]]
    out = dict(turn, side=side, low=side * turn["low"], erl=erl, level=side * turn["cisd"]["level"])
    if turn["draw"]:
        out["draw"] = dict(turn["draw"], near=side * turn["draw"]["near"], far=side * turn["draw"]["far"],
                           ce=side * turn["draw"]["ce"])
    return out


def _end(turn: dict, d1: pd.DataFrame, until: int) -> Optional[tuple[str, int]]:
    """When a live side ended by ``until``: delivered (the draw's CE reached) or invalidated (a D1 close beyond C2's
    extreme), on the real prices."""
    s = turn["side"]
    after = d1[(d1["t_open"] >= turn["t"]) & (d1["t_close"] <= until)]
    for r in after.itertuples():
        if turn["draw"] and s * (r.high if s > 0 else r.low) >= s * turn["draw"]["ce"]:
            return "delivered", int(r.t_close)
        if s * r.close < s * turn["low"]:
            return "invalidated", int(r.t_close)
    return None


def narrative(m: Market, as_of: int) -> dict:
    """The side at ``as_of``: ``side`` (+1, -1 or 0), the turn that set it, the ``ignored`` soups against it
    (manipulation) and, when it ended, ``ended`` (reason, ns)."""
    flipped = m.flipped()
    turns = sorted([_signed(t, 1) for t in _turns(m, as_of)] + [_signed(t, -1) for t in _turns(flipped, as_of)],
                   key=lambda t: t["t"])
    d1 = m.hist["D1"]
    live, ignored, ended = None, [], None
    for t in turns:
        if live is not None and _end(live, d1, t["t"]) is None:
            if t["side"] == live["side"]:
                live = t
            else:
                ignored.append(t)
            continue
        live, ignored = t, []
    if live is not None:
        ended = _end(live, d1, as_of)
    side = live["side"] if live is not None and ended is None else 0
    return {"side": side, "turn": live, "ignored": ignored, "ended": ended}


# ── the read ───────────────────────────────────────────────────────────────

@dataclass
class Read:
    """One market-day's read: the steps in order and the verdict (ORDER or NO TRADE and why)."""
    symbol: str
    day: date
    side: int = 0
    lines: list = field(default_factory=list)
    verdict: str = ""
    facts: dict = field(default_factory=dict)

    def add(self, step: str, text: str) -> None:
        self.lines.append((step, text))

    def render(self) -> str:
        out = [f"{self.symbol}  {self.day:%a %d %b %Y}  (New York time)"]
        out += [f"  {step:<10} {text}" for step, text in self.lines]
        out.append(f"  {'verdict':<10} {self.verdict}")
        return "\n".join(out)


def _p(x: float) -> str:
    return f"{x:.5f}" if abs(x) < 50 else f"{x:.2f}"


def _when(t: int, fmt: str = "%a %d %b %H:%M") -> str:
    return f"{_ny(t):{fmt}}"


def _setup(m: Market, day: pd.Timestamp, s: int, read: Read) -> Optional[dict]:
    """The D1 soup before C3 = ``day`` (buy space; ``s`` puts prices back on the real side)."""
    w, d1 = _WORDS[s], m.hist["D1"]
    rows = d1.index[pd.DatetimeIndex(d1["date"]) == day]
    if not len(rows) or rows[0] < 2:
        read.verdict = "NO TRADE: no D1 candles before the day"
        return None
    c1, c2 = rows[0] - 2, rows[0] - 1
    lo1, lo2, cl2 = d1["low"].iloc[c1], d1["low"].iloc[c2], d1["close"].iloc[c2]
    d_c1, d_c2 = pd.Timestamp(d1["date"].iloc[c1]), pd.Timestamp(d1["date"].iloc[c2])
    if not (lo2 < lo1 and cl2 > lo1):
        read.verdict = f"NO TRADE: {d_c2:%a} did not take {d_c1:%a}'s {w['low']} and close back inside (no D1 soup)"
        return None
    t2o, t2c = int(d1["t_open"].iloc[c2]), int(d1["t_close"].iloc[c2])
    low_t = _extreme_time(m.m1, t2o, t2c)
    zones = [z for z in key_zones(m, t2o) if z[1] <= lo2 <= z[2]]
    names = ", ".join(f"{n} {_p(s * (lo if s > 0 else hi))}-{_p(s * (hi if s > 0 else lo))}" for n, lo, hi in zones)
    read.add("setup", f"D1 {w['+']}soup: C1 {d_c1:%a %d %b} ({w['low']} {_p(s * lo1)}), C2 {d_c2:%a %d %b} "
                      f"{w['low']} {_p(s * lo2)} at {_when(low_t, '%a %H:%M')}, close {_p(s * cl2)}")
    if d_c2.dayofweek not in D1_C2_DAYS:
        read.verdict = f"NO TRADE: the D1 C2 is a {d_c2:%A} (Model A's window is Monday to Wednesday)"
        return None
    if not zones:
        read.verdict = f"NO TRADE: C2's {w['low']} is not inside a key level"
        return None
    read.add("", f"into {names}")
    shifts = []
    for tf in ("H4", "H1"):
        child = m.fine[tf]
        inside = child[(child["t_open"] >= t2o) & (child["t_close"] <= t2c)]
        if inside.empty:
            continue
        shift = cisd(child, int(inside["low"].idxmin()), t2c)
        if shift and shift["confirm"] >= 0:
            shifts.append(f"{tf} run from {_when(child['t_open'].iloc[shift['start']], '%a %H:%M')} "
                          f"(open {_p(s * shift['level'])}), close beyond it at "
                          f"{_when(child['t_close'].iloc[shift['confirm']], '%a %H:%M')}")
    if not shifts:
        read.verdict = "NO TRADE: no H4 or H1 CISD by C2's close"
        return None
    read.add("", "child CISD: " + "; ".join(shifts))
    return {"c1": c1, "c2": c2, "pdh": float(d1["high"].iloc[c2]), "pdl": float(lo2), "t2c": t2c}


def _extreme_time(m1: pd.DataFrame, t0: int, t1: int) -> int:
    t = _ns(m1["time"])
    inside = m1[(t >= t0) & (t < t1)]
    return int(_ns(inside["time"])[int(np.argmin(inside["low"].to_numpy()))]) if len(inside) else t0


def _levels(m: Market, setup: dict, before: int, draw: Optional[dict]) -> list[tuple[str, float]]:
    """The buy side's pools and gaps above, known before ``before``: the PDH, untaken D1 swing highs, the last four
    W1 highs, D1 and W1 gaps of the other side (their edges and CE) and the narrative's draw."""
    d1 = m.hist["D1"][m.hist["D1"]["t_close"] <= before].reset_index(drop=True)
    out = [("PDH", setup["pdh"])]
    h = d1["high"].to_numpy(float)
    for i in range(max(2, len(d1) - 40), len(d1) - 2):
        if h[i] > h[i - 1] and h[i] > h[i + 1] and h[i] > h[i - 2] and h[i] > h[i + 2] and not (h[i + 1:] > h[i]).any():
            out.append((f"{pd.Timestamp(d1['date'].iloc[i]):%d %b} high", float(h[i])))
    w1 = m.hist["W1"][m.hist["W1"]["t_close"] <= before]
    out += [(f"week {pd.Timestamp(r.monday):%d %b} high", float(r.high)) for r in w1.tail(4).itertuples()]
    for tf in ("D1", "W1"):
        b = m.hist[tf][m.hist[tf]["t_close"] <= before].reset_index(drop=True)
        when = b["monday"] if tf == "W1" else b["date"]
        for g in gaps(b).itertuples():
            if g.side < 0 and g.filled > before:
                name = f"{tf} gap {_span(when.iloc[g.i - 2], when.iloc[g.i], before)}"
                out += [(f"{name} edge", float(g.near)), (f"{name} CE", float((g.near + g.far) / 2)),
                        (f"{name} far edge", float(g.far))]
    if draw:
        out += [(f"draw {draw['name']} edge", draw["near"]), (f"draw {draw['name']} CE", draw["ce"])]
    return out


def _c3(m: Market, day: pd.Timestamp, s: int, setup: dict, draw: Optional[dict], read: Read) -> None:
    """C3's execution (buy space): Q1 range, the Q2 Judas swing, the M5 CISD, the order, its path and the targets."""
    w = _WORDS[s]
    t = _ns(m.m1["time"])
    lo, hi = m.m1["low"].to_numpy(float), m.m1["high"].to_numpy(float)
    q1_0, q2_0 = _utc(day - pd.Timedelta(hours=6)), _utc(day)
    q2_1, q3_1 = _utc(day + pd.Timedelta(hours=6)), _utc(day + pd.Timedelta(hours=12))
    q1 = (t >= q1_0) & (t < q2_0)
    if not q1.any():
        read.verdict = "NO TRADE: no Q1 bars"
        return
    q1_low, q1_high = lo[q1].min(), hi[q1].max()
    i_ql, i_qh = np.flatnonzero(q1)[np.argmin(lo[q1])], np.flatnonzero(q1)[np.argmax(hi[q1])]
    at_low, at_high = (i_ql, i_qh) if s > 0 else (i_qh, i_ql)
    real_low, real_high = sorted((s * q1_low, s * q1_high))
    read.add("Q1", f"18:00-00:00 range {_p(real_low)} ({_when(t[at_low], '%H:%M')}) - {_p(real_high)} "
                   f"({_when(t[at_high], '%H:%M')})")
    q2 = np.flatnonzero((t >= q2_0) & (t < q2_1) & (lo < q1_low))
    if not len(q2):
        read.verdict = f"NO TRADE: Q2 did not take the {w['Q1 low']}"
        return
    sweep = q2[0]
    m5 = m.fine["M5"]
    o5, h5, l5, c5 = (m5[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    t5o, t5c = m5["t_open"].to_numpy(np.int64), m5["t_close"].to_numpy(np.int64)
    first = int(np.searchsorted(t5c, t[sweep], side="right"))
    best, k_low, shift, k_cisd = np.inf, -1, None, -1
    for k in range(first, len(m5)):
        if t5c[k] > q3_1:
            break
        if l5[k] < best:
            best, k_low = l5[k], k
        run = cisd(m5, k_low, int(t5c[k]))
        if run and k > run["end"] and c5[k] > run["level"]:
            shift, k_cisd = run, k
            break
    read.add("Q2", f"the {w['Q1 low']} taken at {_when(t[sweep], '%H:%M')}")
    if shift is None:
        read.verdict = "NO TRADE: no M5 CISD before 12:00"
        return
    low_t = _extreme_time(m.m1, int(t5o[k_low]), int(t5c[k_low]))
    swing = next((i for i in range(k_low - 1, 0, -1) if h5[i] > h5[i - 1] and h5[i] > h5[i + 1]), None)
    j_high = float(h5[swing]) if swing is not None else float(h5[k_low])
    read.add("Judas", f"swing {w['high']} {_p(s * j_high)} ({_when(t5o[swing], '%H:%M') if swing is not None else '-'})"
                      f" to {w['low']} {_p(s * best)} ({_when(low_t, '%H:%M')}), {abs(j_high - best):.5g}")
    read.add("CISD", f"M5 run from {_when(t5o[shift['start']], '%H:%M')} (open {_p(s * shift['level'])}), "
                     f"first close beyond it: the {_when(t5o[k_cisd], '%H:%M')} candle")
    entry, stop = float(o5[shift["end"]]), float(best)
    leg_high = float(h5[k_low:k_cisd + 1].max())
    where = (entry - stop) / (leg_high - stop) if leg_high > stop else 1.0
    if where > 0.5:
        read.verdict = f"NO TRADE: the order block {_p(s * entry)} is not in {w['discount']} ({where:.0%} of the leg)"
        return
    placed = int(t5c[k_cisd])
    read.add("order", f"{w['buy']} limit {_p(s * entry)} (the {_when(t5o[shift['end']], '%H:%M')} candle's open), "
                      f"{where:.0%} up the leg {_p(s * stop)}-{_p(s * leg_high)}; stop {_p(s * stop)}; "
                      f"placed {_when(placed, '%H:%M')}, good until 12:00")
    d1 = m.hist["D1"][m.hist["D1"]["t_close"] <= setup["t2c"]]
    adr = float((d1["high"] - d1["low"]).tail(ADR_DAYS).mean())
    rng = j_high - best
    levels = _levels(m, setup, setup["t2c"], draw)
    risk = entry - stop
    end = _utc(day + pd.Timedelta(hours=17) + pd.Timedelta(days=3 if day.dayofweek == 4 else 1))
    after = np.flatnonzero((t >= placed) & (t < q3_1) & (lo <= entry))
    fill = int(after[0]) if len(after) else -1
    path = np.flatnonzero((t >= (t[fill] if fill >= 0 else placed)) & (t < end))
    stopped = path[lo[path] <= stop] if fill >= 0 else np.array([], int)
    t_stop = int(t[stopped[0]]) if len(stopped) else None
    targets, draw_level = [], None
    for k in DEVIATIONS:
        lvl = j_high + k * rng
        near = [(n, x) for n, x in levels if abs(x - lvl) <= CONFLUENCE * rng]
        reach = path[hi[path] >= lvl] if fill >= 0 else np.array([], int)
        t_hit = int(t[reach[0]]) if len(reach) and (t_stop is None or t[reach[0]] < t_stop) else None
        if draw and any(n.startswith("draw") for n, _ in near) and draw_level is None:
            draw_level = k
        targets.append({"dev": k, "level": lvl, "near": near, "adr": (lvl - best) / adr, "r": (lvl - entry) / risk,
                        "hit": t_hit})
        mark = " (the draw)" if draw_level == k else ""
        names = "; ".join(f"{n} {_p(s * x)}" for n, x in near) or "-"
        read.add("target" if k == DEVIATIONS[0] else "",
                 f"{f'-{k:g}':<4} {_p(s * lvl)}  {(lvl - best) / adr:.1f} ADR, {(lvl - entry) / risk:.1f}R{mark}  "
                 f"[{names}]" + (f"  reached {_when(t_hit, '%a %H:%M')}" if t_hit else ""))
    read.add("ADR", f"{ADR_DAYS}-day {_p(adr)}, from the Judas {w['low']}")
    if fill < 0:
        read.verdict = f"ORDER, not filled by 12:00 ({w['buy']} limit {_p(s * entry)}, stop {_p(s * stop)})"
    else:
        after_fill = f", stopped {_when(t_stop, '%a %H:%M')}" if t_stop else ", stop not reached by the next close"
        read.verdict = (f"ORDER filled {_when(t[fill], '%H:%M')}: {w['buy']} {_p(s * entry)}, "
                        f"stop {_p(s * stop)}{after_fill}")
    read.facts.update(q1=(s * q1_low, s * q1_high), sweep=_ny(t[sweep]), judas=(s * j_high, s * best),
                      judas_high_at=_ny(t5o[swing]) if swing is not None else None, low_at=_ny(low_t),
                      cisd=(_ny(t5o[shift["start"]]), s * shift["level"], _ny(t5o[k_cisd])), entry=s * entry,
                      stop=s * stop, placed=_ny(placed), fill=_ny(t[fill]) if fill >= 0 else None,
                      stopped=_ny(t_stop) if t_stop else None, adr=adr, targets=targets, draw_dev=draw_level)


def read_day(symbol: str, history: pd.DataFrame, m1: pd.DataFrame, day: date) -> Read:
    """The read for C3 = ``day``: the narrative at the eve's 17:00, the D1 soup before it and C3's execution."""
    read = Read(symbol, day)
    real = Market(history, m1)
    d = pd.Timestamp(day)
    d1 = real.hist["D1"]
    rows = d1.index[pd.DatetimeIndex(d1["date"]) == d]
    if not len(rows):
        read.verdict = "NO TRADE: no D1 candle for the day"
        return read
    as_of = int(d1["t_open"].iloc[rows[0]])
    view = narrative(real, as_of)
    turn, s = view["turn"], view["side"]
    if turn is not None:
        w = _WORDS[turn["side"]]
        erl = ", ".join(f"the {n} {_p(x)}" for n, x in turn["erl"])
        read.add("narrative", f"{w['BULLISH']} since {_when(turn['t'])}: W1 {w['+']}soup, C1 week {turn['c1']:%d %b}, "
                              f"C2 week {turn['c2']:%d %b} took {erl} ({w['low']} {_p(turn['low'])}); D1 CISD "
                              f"{_when(turn['cisd_at'], '%a %d %b')} (close beyond {_p(turn['level'])})")
        if turn["draw"]:
            dr = turn["draw"]
            read.add("", f"draw: {dr['name']} {_p(min(dr['near'], dr['far']))}-{_p(max(dr['near'], dr['far']))} "
                         f"(CE {_p(dr['ce'])}); protected {w['low']} {_p(turn['low'])}")
        for t in view["ignored"]:
            read.add("", f"ignored: W1 {_WORDS[t['side']]['+']}soup C2 week {t['c2']:%d %b} against the live side "
                         f"(manipulation)")
        if view["ended"]:
            read.add("", f"ended: {view['ended'][0]} {_when(view['ended'][1], '%a %d %b')}")
    read.side = s
    if s == 0:
        read.verdict = "NO TRADE: no live narrative"
        return read
    m = real if s > 0 else real.flipped()
    setup = _setup(m, d, s, read)
    if setup is None:
        return read
    draw = turn["draw"]
    draw_space = dict(draw, near=s * draw["near"], far=s * draw["far"], ce=s * draw["ce"]) if draw else None
    _c3(m, d, s, setup, draw_space, read)
    return read


# ── bars from the MT5 terminal ─────────────────────────────────────────────

def _mt5_bars(symbol: str, day: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """H1 for the 420 days before ``day`` and M1 from five days before it to four after (history requests only)."""
    import MetaTrader5 as mt5                                                   # noqa: PLC0415 (Windows only)

    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start - timedelta(days=420), start + timedelta(days=4))
        m1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start - timedelta(days=5), start + timedelta(days=4))
    finally:
        mt5.shutdown()
    if h1 is None or m1 is None or not len(h1) or not len(m1):
        raise SystemExit(f"no bars for {symbol}")
    out = []
    for rates in (h1, m1):
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        out.append(df[["time", "open", "high", "low", "close"]])
    return out[0], out[1]


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="The trader's sequence, v0: one market-day's read.")
    parser.add_argument("--symbol", required=True, help="the terminal's symbol, e.g. GBPUSDm")
    parser.add_argument("--day", required=True, type=date.fromisoformat, help="C3, the trading date to read")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    history, m1 = _mt5_bars(args.symbol, args.day)
    print(read_day(args.symbol, history, m1, args.day).render())


if __name__ == "__main__":
    main()
