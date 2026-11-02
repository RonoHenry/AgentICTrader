"""The directional state in shadow on the context page (context-engine Requirement 35.3-35.4, task 395).

For each market and week, from the broker's terminal (``data/algo_mind/dis/<week>.json``):
- reader v0's record at the week's open, the side the week is scored on;
- the record at the last D1 close since, as a side can end or start inside the week;
- why each of the last four W1 candles did or didn't turn the narrative, on both sides;
- the reader's read of each trading date opened so far: the narrative, the D1 setup, C3's execution, and its
  verdict (ORDER, or NO TRADE and the first rule that refused).

Nothing in the engine reads it (35.4). Each record reads only candles closed by its time, so the same bars give
the same file whenever it is made.

    python -m algo_mind shadow --week 2026-11-02
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from agent.context_calls import trading_dates, week_close, week_open
from algo_mind.dis import SOURCE, VERSION, reader_turns, state_at, states, terminal_market, week_checks
from algo_research import sequence as seq
from liquidity_engine.models import Timeframe

__all__ = ["HISTORY", "MARKETS", "SHADOWS", "read_market", "write_shadow"]

REPO = Path(__file__).resolve().parents[1]
SHADOWS = REPO / "data" / "algo_mind" / "dis"
#: The context page's markets (algo_research.replay.context.MARKETS).
MARKETS = ("DXY", "XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")
#: The H1 each market is read with: a side set two years ago still needs its year of external lows before it.
HISTORY = timedelta(days=1100)
_SPANS = 3


def _ns(t: datetime) -> int:
    return int(pd.Timestamp(t).value)


def _iso(t: Optional[int]) -> Optional[str]:
    return None if t is None or t >= np.iinfo(np.int64).max else pd.Timestamp(int(t), tz="UTC").isoformat()


def last_close(t: datetime) -> datetime:
    """The last 17:00 New York (a D1 close) at or before ``t``."""
    ny = pd.Timestamp(t).tz_convert(seq.NY)
    day = ny.normalize() + pd.Timedelta(hours=17)
    return (day if day <= ny else day - pd.Timedelta(days=1)).tz_convert("UTC").to_pydatetime()


def _spans(timeline: list, upto: int) -> list[dict]:
    """The last few sides set by ``upto``: each one's side, start, end and why, its draw and protected swing."""
    out = []
    for s in [x for x in timeline if x.start <= upto][-_SPANS:]:
        ended = s.end <= upto and s.reason != "open"
        out.append({"side": {1: "BULLISH", -1: "BEARISH"}[s.turn["side"]], "since": _iso(s.start),
                    "end": _iso(s.end) if ended else None, "reason": s.reason if ended else "live",
                    "draw": s.turn["draw"], "protected": s.turn["low"],
                    "ignored": sum(1 for x in s.ignored if x["t"] <= upto)})
    return out


def read_market(market: str, h1: pd.DataFrame, m1: pd.DataFrame, monday: date, now: datetime) -> dict:
    """One market's shadow for the week of ``monday`` as of ``now`` (H1 and M1 closed by then, times UTC)."""
    opens, closes = week_open(monday), week_close(monday)
    upto = last_close(min(now, closes))
    m = terminal_market(h1, _ns(upto))
    timeline = states(reader_turns(m), m.hist["D1"])
    at_open, latest = (state_at(timeline, _ns(t), market=market) for t in (opens, upto))
    reads = []
    for day in trading_dates(monday):
        d = pd.Timestamp(day)
        if seq._utc(d - pd.Timedelta(hours=7)) > _ns(now):
            break                                               # not opened yet: it opens at 17:00 New York the eve
        r = seq.read_day(market, h1, m1, d.date())
        reads.append({"day": day, "side": {1: "BULLISH", -1: "BEARISH", 0: "NONE"}[r.side],
                      "steps": [list(x) for x in r.lines], "verdict": r.verdict,
                      "order": r.verdict.startswith("ORDER"),
                      "so_far": seq._utc(d + pd.Timedelta(hours=17)) > _ns(now)})
    return {"market": market, "open": at_open.to_json(), "now": latest.to_json(), "as_of": upto.isoformat(),
            "spans": _spans(timeline, _ns(upto)), "weeks": week_checks(m), "reads": reads,
            "history": {"h1": len(h1), "from": h1["time"].iloc[0].isoformat() if len(h1) else None}}


def write_shadow(monday: date, rates: Callable[[str, Timeframe, datetime, datetime], pd.DataFrame],
                 now: Optional[datetime] = None, markets: tuple[str, ...] = MARKETS,
                 folder: Path = SHADOWS) -> Path:
    """Every market's shadow for the week of ``monday`` from ``rates`` (the terminal), as ``<folder>/<week>.json``."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for market in markets:
        try:
            # bars to now: the records stop at the week's close, the reads' paths run on after it
            h1 = _closed(rates(market, Timeframe.H1, min(now, week_close(monday)) - HISTORY, now),
                         timedelta(hours=1), now)
            m1 = _closed(rates(market, Timeframe.M1, week_open(monday) - timedelta(days=5), now),
                         timedelta(minutes=1), now)
            if h1.empty:
                raise LookupError("the broker gives no H1 bars for it")
            rows.append(read_market(market, h1, m1, monday, now))
        except Exception as exc:                                # one market failing leaves the rest
            rows.append({"market": market, "error": str(exc)})
    out = {"week": monday.isoformat(), "source": SOURCE, "version": VERSION,
           "made_at": now.isoformat(timespec="seconds"), "rows": rows}
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{monday.isoformat()}.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return path


def _closed(frame: Optional[pd.DataFrame], step: timedelta, now: datetime) -> pd.DataFrame:
    """The bars of ``frame`` closed by ``now``, in time order."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    f = frame.assign(time=pd.to_datetime(frame["time"], utc=True))
    f = f[f["time"] + step <= pd.Timestamp(now)]
    return f.drop_duplicates("time").sort_values("time").reset_index(drop=True)[["time", "open", "high", "low",
                                                                                  "close"]]
