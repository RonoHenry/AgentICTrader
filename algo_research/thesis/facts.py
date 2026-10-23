"""The blind facts at a trading day's open (market-narrative Requirement 16.1-16.2, ND-D3).

Everything the engine and the trader's Fractal + POI indicator see at the 17:00 New York open, from closed candles
only, written for a reasoning model:
- the last candles of W1, D1, H4 and H1;
- the engine's read: price against each timeframe's open, the day profile, the untaken pools and the unfilled PD
  arrays near price (under ``fvg_zone = "gap"``: read from closed candles);
- the indicator's live setups on its H1 and H4 charts (C2 swept C1, the CISD, the C3 and C4 zones, C1's other side);
- each timeframe's phase of delivery (liquidity-engine Requirement 28).

It is blind: no date and no market name (the time is the weekday and the New York clock), and every price is
rescaled so that the open is 1000 and one D1 average true range is 100 (``Rescale``). These months are inside the
models' training data; without this a thesis could be recall.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

import numpy as np

from algo_research.phases import label_phases
from liquidity_engine.models import Candle, Timeframe
from liquidity_engine.utils.time_utils import closed_candles

__all__ = ["Facts", "Rescale", "build_facts", "facts_at"]

NY = ZoneInfo("America/New_York")
SHOWN = {Timeframe.W1: 8, Timeframe.D1: 10, Timeframe.H4: 12, Timeframe.H1: 12}
PHASE_TFS = (Timeframe.W1, Timeframe.D1, Timeframe.H4, Timeframe.H1)
NEAR = 4.0          # pools and arrays within this many D1 ranges of the open
SHOWN_POOLS, SHOWN_ARRAYS = 14, 14


@dataclass(frozen=True)
class Rescale:
    """Prices as the model sees them: the open is 1000 and one D1 average true range is 100."""
    open: float
    atr: float

    def to(self, price: float) -> float:
        return round(1000.0 + 100.0 * (float(price) - self.open) / self.atr, 1)

    def back(self, level: float) -> float:
        return self.open + (float(level) - 1000.0) * self.atr / 100.0


@dataclass(frozen=True)
class Facts:
    text: str
    rescale: Rescale
    weekday: str


def _ny(t: datetime) -> datetime:
    return t.astimezone(NY)


def _clock(t: datetime) -> str:
    return _ny(t).strftime("%a %H:%M")


def _trading_day(t: datetime) -> str:
    """The weekday of the trading day a 17:00 New York open starts (Sunday 17:00 opens Monday's)."""
    return (_ny(t) + timedelta(hours=7)).strftime("%A")


def _atr(candles: Sequence[Candle], n: int = 14) -> float:
    if len(candles) < 2:
        return float("nan")
    last = candles[-(n + 1):]
    tr = [max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close)) for a, b in zip(last, last[1:])]
    return sum(tr) / len(tr)


def _candle_lines(tf: Timeframe, candles: Sequence[Candle], rs: Rescale) -> list[str]:
    shown = candles[-SHOWN[tf]:]
    out = []
    for k, c in enumerate(shown):
        back = len(shown) - k
        when = (f"{back} week(s) back" if tf == Timeframe.W1 else
                f"{_trading_day(c.timestamp)[:3]}" if tf == Timeframe.D1
                else f"opened {_clock(c.timestamp)}")
        out.append(f"  {tf.value} [{when}] O {rs.to(c.open)} H {rs.to(c.high)} L {rs.to(c.low)} C {rs.to(c.close)}")
    return out


def _phases(view: Mapping[Timeframe, Sequence[Candle]]) -> list[str]:
    out = []
    for tf in PHASE_TFS:
        bars = view.get(tf) or []
        if len(bars) < 30:
            continue
        labels = label_phases([b.open for b in bars], [b.high for b in bars], [b.low for b in bars],
                              [b.close for b in bars])
        last = [x or "unclassified" for x in labels[-4:]]
        out.append(f"  {tf.value}: last four closed candles {', '.join(last)}")
    return out


def _live(s, clock: int) -> bool:
    """A setup still in play at the clock: not invalidated, and its C3 or C4 window not yet over. A setup whose C3
    zone is set waits for C4 too, so it lives one C3 length past C3's end."""
    if s.is_invalid:
        return False
    if s.ez_c4_set and s.ez_c4_right_time is not None:
        return clock < int(s.ez_c4_right_time)
    if s.ez_c3_set and s.ez_c3_right_time is not None and s.ez_c3_left_time is not None:
        return clock < int(s.ez_c3_right_time) + (int(s.ez_c3_right_time) - int(s.ez_c3_left_time))
    return True                                          # C2 swept C1 and waits for the CISD


def _setup_lines(chart: str, model, rs: Rescale, clock: int) -> list[str]:
    """The indicator's setups still in play on one chart, newest first."""
    out = []
    for s in reversed(getattr(model, "setups", []) or []):
        if not _live(s, clock):
            continue
        side = "bullish" if s.is_bullish else "bearish"
        stage = ("C4 zone set" if s.ez_c4_set else "C3 zone set" if s.ez_c3_set else
                 "CISD triggered" if s.cisd_triggered else "C2 swept C1, waiting for the CISD")
        parts = [f"  {chart} chart (HTF {model.htf}): {side} setup, {stage}; C2 swept C1's "
                 f"{'low' if s.is_bullish else 'high'} at {rs.to(s.sweep_price)}"]
        for label, value in (("C2's extreme", s.c2_extreme), ("CISD level", s.cisd_level),
                             ("C1's other side (target)", s.liq_c1_price)):
            if value is not None and not (isinstance(value, float) and math.isnan(value)):
                parts.append(f"{label} {rs.to(value)}")
        if s.ez_c3_set:
            parts.append(f"C3 zone {rs.to(min(s.ez_c3_top, s.ez_c3_bot))}-{rs.to(max(s.ez_c3_top, s.ez_c3_bot))}")
        if s.ez_c4_set:
            parts.append(f"C4 zone {rs.to(min(s.ez_c4_top, s.ez_c4_bot))}-{rs.to(max(s.ez_c4_top, s.ez_c4_bot))}")
        out.append("; ".join(parts))
    return out[:4]


def build_facts(view: Mapping[Timeframe, Sequence[Candle]], liquidity_map, pools: Sequence, t: datetime,
                indicator: Mapping[str, object], entry_tf: Timeframe = Timeframe.M15) -> Facts:
    """The blind facts at ``t``, the trading day's open. ``view`` is the engine's as-of view, ``liquidity_map`` its
    analysis at ``t``, ``pools`` its raidable pools, ``indicator`` the Fractal + POI models by chart ("H1", "H4")."""
    closed = closed_candles(view, t)
    d1 = closed.get(Timeframe.D1) or []
    price = view[entry_tf][-1].close
    rs = Rescale(open=price, atr=_atr(d1))
    if not (rs.atr > 0 and math.isfinite(rs.atr)):
        raise ValueError("no D1 range to rescale with")
    weekday = _trading_day(t)
    lines = [
        f"Now: 17:00 New York, the open of {weekday}'s trading day (its D1 candle). Times are New York; candles are "
        "labelled by their open, D1 candles by their trading day.",
        "Prices are rescaled: the current price (the open) is 1000.0 and one D1 average true range is 100 points.",
        "", "CANDLES (closed, oldest first):"]
    for tf in SHOWN:
        if closed.get(tf):
            lines += _candle_lines(tf, closed[tf], rs)
    lines += ["", "PHASE OF DELIVERY (consolidation, expansion, retracement, reversal):"] + _phases(closed)
    lm = liquidity_map
    lines += ["", "THE ENGINE'S READ:"]
    prof = lm.candle_profile
    if prof is not None:
        draw = "none" if prof.draw is None else f"{prof.draw.source} {rs.to(prof.draw.price)}"
        lines.append(f"  Day profile: anticipated {prof.direction.value.lower()}, trend {prof.trend.value.lower()}, "
                     f"draw {draw}")
    near = lambda p: abs(rs.to(p) - 1000.0) <= NEAR * 100  # noqa: E731
    bars = view.get(entry_tf, [])
    opens = [c.timestamp for c in bars]
    untaken = []
    for p in pools:
        if p.known_at > t or not near(p.price):
            continue
        later = bars[bisect_right(opens, p.known_at):]
        above = p.side.value == "BSL"
        if any((c.high > p.price) if above else (c.low < p.price) for c in later):
            continue
        untaken.append(p)
    untaken.sort(key=lambda p: abs(p.price - price))
    lines.append("  Untaken liquidity (side, source, timeframe, level), nearest first:")
    seen = set()
    for p in untaken:
        key = (p.side.value, p.source.value, round(rs.to(p.price)))
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"    {'buy-side' if p.side.value == 'BSL' else 'sell-side'} {p.source.value} {p.timeframe.value} "
                     f"{rs.to(p.price)}")
        if len(seen) >= SHOWN_POOLS:
            break
    arrays = [a for a in lm.pd_arrays if not a.is_filled and a.timeframe.value in ("H1", "H4", "D1", "W1")
              and (near(a.high) or near(a.low)) and a.direction.value != "NEUTRAL"]
    arrays.sort(key=lambda a: min(abs(a.high - price), abs(a.low - price)))
    lines.append("  Unfilled PD arrays H1 and above (type, side, timeframe, low-high), nearest first:")
    for a in arrays[:SHOWN_ARRAYS]:
        lines.append(f"    {a.array_type.value} {a.direction.value.lower()} {a.timeframe.value} "
                     f"{rs.to(a.low)}-{rs.to(a.high)}")
    lines += ["", "THE FRACTAL + POI INDICATOR (setups still in play, newest first):"]
    ny = _ny(t)
    clock = int((ny.replace(tzinfo=None) - datetime(1970, 1, 1)).total_seconds())     # New York wall seconds
    shown = [line for chart, model in indicator.items() for line in _setup_lines(chart, model, rs, clock)]
    lines += shown or ["  none live"]
    return Facts(text="\n".join(lines), rescale=rs, weekday=weekday)


def facts_at(data, cfg, t: datetime, readers: Mapping[str, object], engine=None) -> Facts:
    """The blind facts at ``t`` from the backtester's own pieces: the as-of view the engine reads, its analysis
    under ``fvg_zone = "gap"`` (arrays from closed candles), its raidable pools, and the Fractal + POI readers
    (``FractalPOI`` by chart, stepped to ``t``; they read only candles closed by then, Property 11)."""
    import pandas as pd

    from algo_backtester.signals import _CALENDAR
    from algo_research.replay.timeframes import wall_seconds
    from liquidity_engine import LiquidityMappingEngine
    from liquidity_engine.grader.sequence import SetupSequenceDetector
    from services.market_data.as_of_view import compose_as_of_view

    view = compose_as_of_view(data.closed, data.m1, t, cfg.entry_tf, cfg.candle_counts, _CALENDAR)
    lm = (engine or LiquidityMappingEngine("gap")).analyze(view, data.instrument, t)
    pools = SetupSequenceDetector().pools(view, as_of=t)
    wall = int(wall_seconds(pd.to_datetime([t], utc=True))[0])
    models = {}
    for chart, reader in readers.items():
        reader.at(wall)
        models[chart] = reader.model
    return build_facts(view, lm, pools, t, models, cfg.entry_tf)
