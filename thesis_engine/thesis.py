"""The thesis (thesis-engine Requirement 4): its ends, its sources and the completion rule.

- **Ends,** checked at each E close in AlgoMindDIS's order (§10.4): INVALIDATED by a D1 candle closing after
  ``since`` beyond the protected level (a wick is liquidation), DELIVERED by an E candle after ``since`` trading at or
  beyond the draw, then ``until`` (EXPIRED, or WITHDRAWN for a source that stopped holding it).
- **CALL:** the trader's /context calls (``agent.context_calls``), live from the call's ``since`` to the week's close.
- **FILE:** a thesis file in the THESIS-mode format; consecutive trading dates with the same entry are one thesis,
  withdrawn at the close of its last date.
- **ORACLE, MIRROR, RANDOM, W1TREND** (research only, never on paper): the week's real side (its New York W1 close
  against its open), the opposite, a seeded coin flip, or the last W1 candle's LE-D15 trend at the week's open, each
  completed by the nearest-pool rule (Requirement 4.4, TE-D10) and live for the week.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from agent.context_calls import CALLS_FILE, ContextBook, week_close
from liquidity_engine.context.frame_state import _trend
from liquidity_engine.models import BiasDirection
from thesis_engine.book import Book
from thesis_engine.clock import NY
from thesis_engine.records import Thesis
from thesis_engine.settings import V1, Settings

__all__ = ["RESEARCH", "call_theses", "complete", "end", "file_theses", "research_theses"]

RESEARCH = ("ORACLE", "MIRROR", "RANDOM", "W1TREND")


def _p(x: float) -> str:
    return f"{x:.6g}"


def end(th: Thesis, book: Book, m: int, t: int, d1_from: int, d1_to: int) -> Optional[Tuple[str, str]]:
    """The thesis's end at the close of E candle ``m`` (time ``t``), given the D1 candles [d1_from, d1_to) that
    closed since the last step: (INVALIDATED | DELIVERED | EXPIRED | WITHDRAWN, why), or None."""
    d1 = book.frames["D1"].c
    for i in range(d1_from, d1_to):
        if d1.end[i] > th.since and (d1.c[i] < th.protected if th.bullish else d1.c[i] > th.protected):
            return "INVALIDATED", (f"a D1 close {_p(d1.c[i])} beyond the protected level {_p(th.protected)}")
    e = book.e
    if e.t[m] >= th.since and (e.h[m] >= th.draw if th.bullish else e.l[m] <= th.draw):
        return "DELIVERED", f"the draw {_p(th.draw)} traded"
    if t >= th.until:
        return th.until_reason, ("the source stopped holding it" if th.until_reason == "WITHDRAWN"
                                 else "its time ran out")
    return None


def complete(side: str, book: Book, since: int, open_price: float, prev_high: float, prev_low: float,
             s: Settings = V1) -> Tuple[Optional[float], Optional[float], str]:
    """The completion rule (Requirement 4.4) at a week's open: (draw, protected, why), or (None, None, why)."""
    bullish = side == "BULLISH"
    d1 = book.frames["D1"]
    n = d1.n(since)
    adr = book.adr(since)
    if not np.isfinite(adr) or adr <= 0:
        return None, None, "no ADR yet"
    near, far = s.completion_min_adr * adr, s.completion_max_adr * adr
    beyond = (lambda x: x >= open_price + near) if bullish else (lambda x: x <= open_price - near)
    draws = [x for x in (prev_high if bullish else prev_low, *d1.untaken(n, lows=not bullish)) if beyond(x)]
    against = [x for x in d1.untaken(n, lows=bullish)
               if (x <= open_price - near if bullish else x >= open_price + near)]
    draw = (min(draws) if bullish else max(draws)) if draws else None
    if against:
        protected = max(against) if bullish else min(against)
    else:
        fallback = prev_low if bullish else prev_high
        protected = fallback if (fallback < open_price if bullish else fallback > open_price) else None
    if draw is None or protected is None:
        return None, None, "no " + ("draw" if draw is None else "protected level")
    if abs(draw - open_price) > far or abs(open_price - protected) > far:
        return None, None, f"more than {s.completion_max_adr:g} ADR away"
    return float(draw), float(protected), "completed"


def research_theses(market: str, book: Book, kind: str, seed: int = 0, s: Settings = V1,
                    since_from: Optional[int] = None) -> Tuple[List[Thesis], Dict[str, int]]:
    """One thesis a week for ``kind`` in RESEARCH, and the weeks refused by reason."""
    if kind not in RESEARCH:
        raise ValueError(f"kind: one of {', '.join(RESEARCH)}")
    w1 = book.frames["W1"].c
    rng = random.Random(f"{market}|{seed}")
    out, refused = [], {}
    for w in range(1, len(w1)):
        since, until = int(w1.t[w]), int(w1.end[w])
        flip = rng.random() < 0.5                                # drawn every week, so RANDOM is the same per seed
        if since_from is not None and since < since_from:
            continue
        real = "BULLISH" if w1.c[w] > w1.o[w] else "BEARISH" if w1.c[w] < w1.o[w] else None
        if kind == "ORACLE":
            side = real
        elif kind == "MIRROR":
            side = None if real is None else ("BEARISH" if real == "BULLISH" else "BULLISH")
        elif kind == "RANDOM":
            side = "BULLISH" if flip else "BEARISH"
        else:
            trend, _ = _trend(book.frames["W1"].cut(w))
            side = None if trend == BiasDirection.NEUTRAL else trend.value
        if side is None:
            refused["no side"] = refused.get("no side", 0) + 1
            continue
        draw, protected, why = complete(side, book, since, float(w1.o[w]), float(w1.h[w - 1]), float(w1.l[w - 1]), s)
        if draw is None:
            refused[why] = refused.get(why, 0) + 1
            continue
        out.append(Thesis(market, side, draw, protected, since, until, kind,
                          note=f"week of {pd.Timestamp(since, tz='UTC').tz_convert(NY):%Y-%m-%d}"))
    return out, refused


def _ns(iso: str) -> int:
    return int(pd.Timestamp(datetime.fromisoformat(iso)).tz_convert("UTC").value)


def call_theses(market: str, path: Path = CALLS_FILE) -> List[Thesis]:
    """The trader's latest call for each week of ``market`` with a side, live from its ``since`` to the week's
    close."""
    out = []
    for call in ContextBook(path).calls():
        if call.instrument != market.upper() or call.side == "NONE":
            continue
        until = int(pd.Timestamp(week_close(date.fromisoformat(call.week))).tz_convert("UTC").value)
        out.append(Thesis(market.upper(), call.side, call.draw, call.protected, _ns(call.since), until, "CALL",
                          note=call.note))
    return sorted(out, key=lambda x: x.since)


def file_theses(market: str, path: Path, s: Settings = V1) -> List[Thesis]:
    """A THESIS-mode file's entries for ``market`` (``{instrument: {date: {side, draw, protected, since}}}``),
    consecutive dates with the same entry joined into one thesis, withdrawn at the close of its last date."""
    days = json.loads(Path(path).read_text(encoding="utf-8")).get(market.upper(), {})
    hour = s.day_open_hour(market)
    out: List[Thesis] = []
    run: Optional[Tuple[dict, str, str]] = None
    for day in sorted(days):
        entry = days[day]
        if not isinstance(entry, dict) or entry.get("side") not in ("BULLISH", "BEARISH"):
            run = _close_run(out, market, run, hour)
            continue
        key = {k: entry.get(k) for k in ("side", "draw", "protected", "since")}
        consecutive = run is not None and run[0] == key and \
            np.busday_count(date.fromisoformat(run[2]), date.fromisoformat(day)) <= 1
        run = (key, run[1], day) if consecutive else (_close_run(out, market, run, hour) or (key, day, day))
    _close_run(out, market, run, hour)
    return out


def _close_run(out: List[Thesis], market: str, run, hour: int):
    if run is not None:
        key, _, last = run
        until = int(pd.Timestamp(f"{last} {hour:02d}:00").tz_localize(NY).tz_convert("UTC").value)
        out.append(Thesis(market.upper(), key["side"], float(key["draw"]), float(key["protected"]), _ns(key["since"]),
                          until, "FILE", until_reason="WITHDRAWN"))
    return None
