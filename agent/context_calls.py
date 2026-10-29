"""The trader's weekly context (context-engine Requirement 32).

Once a week the trader calls each market: the side, the draw and the protected swing. The calls are kept in a local
journal (``data/journal/context/calls.json``, git-ignored, every version kept) and written to the engine's thesis
file (``data/research/theses/context_theses.json``), one entry per trading date of the week. Under
``bias_mode = THESIS`` the engine then orders only the call's side (``agent.order_intent``), until the draw trades or
a D1 candle closes beyond the protected swing.

    book = ContextBook()
    book.put(Call("US500", "2026-11-02", "BULLISH", draw=7850.8, protected=7616.3, made_at=now))
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

__all__ = ["CALLS_FILE", "PAPER_FILES", "SIDES", "THESIS_FILE", "Call", "ContextBook", "paper_r", "score_call",
           "thesis_table", "trading_dates", "week_close", "week_monday", "week_move", "week_open"]

REPO = Path(__file__).resolve().parents[1]
CALLS_FILE = REPO / "data" / "journal" / "context" / "calls.json"
THESIS_FILE = REPO / "data" / "research" / "theses" / "context_theses.json"
#: The paper agents the scorecard compares (Requirement 32.6): the context agent and the two controls.
PAPER_FILES = {"context": REPO / "data" / "paper_trades_fresh_near_gap_context.json",
               "partial": REPO / "data" / "paper_trades_fresh_near_gap_partial.json",
               "control": REPO / "data" / "paper_trades_fresh_near_gap.json"}
SIDES = ("BULLISH", "BEARISH", "NONE")
_NY = ZoneInfo("America/New_York")


def week_monday(t: datetime) -> date:
    """The Monday of the trading week holding ``t``. The week opens on Sunday at 17:00 New York and closes on Friday at
    17:00; a weekend time belongs to the week ahead."""
    d = (t.astimezone(_NY) + timedelta(hours=7)).date()             # the trading date: 17:00 opens the next one
    return d + timedelta(days=7 - d.weekday()) if d.weekday() >= 5 else d - timedelta(days=d.weekday())


def week_open(monday: date) -> datetime:
    """When the week of ``monday`` opens: the Sunday before, at 17:00 New York (in UTC)."""
    return datetime.combine(monday - timedelta(days=1), time(17), _NY).astimezone(timezone.utc)


def week_close(monday: date) -> datetime:
    """When the week of ``monday`` closes: Friday at 17:00 New York (clocks change on Sundays before the open)."""
    return week_open(monday) + timedelta(days=5)


def trading_dates(monday: date) -> list[str]:
    return [(monday + timedelta(days=k)).isoformat() for k in range(5)]


@dataclass(frozen=True)
class Call:
    """One market's context for one week: its side, the draw and the protected swing (Requirement 32.1)."""
    instrument: str
    week: str                                   # the week's Monday, ISO
    side: str
    draw: Optional[float] = None
    protected: Optional[float] = None
    note: str = ""
    made_at: str = ""                           # UTC, ISO; empty means now

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument", self.instrument.strip().upper())
        object.__setattr__(self, "side", self.side.strip().upper())
        if not self.made_at:
            object.__setattr__(self, "made_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if not self.instrument:
            raise ValueError("instrument: required")
        if date.fromisoformat(self.week).weekday() != 0:
            raise ValueError(f"week: a Monday, not {self.week}")
        if self.side not in SIDES:
            raise ValueError(f"side: one of {', '.join(SIDES)}")
        if self.side == "NONE":
            object.__setattr__(self, "draw", None)
            object.__setattr__(self, "protected", None)
            return
        for name in ("draw", "protected"):
            value = getattr(self, name)
            if value is None or not math.isfinite(float(value)):
                raise ValueError(f"{name}: a price is required for a {self.side} call")
            object.__setattr__(self, name, float(value))
        if (self.protected >= self.draw) if self.side == "BULLISH" else (self.protected <= self.draw):
            where = "below" if self.side == "BULLISH" else "above"
            raise ValueError(f"protected: a {self.side} call's protected swing is {where} its draw")

    @property
    def opens(self) -> datetime:
        return week_open(date.fromisoformat(self.week))

    @property
    def late(self) -> bool:
        """Made after its week opened (kept, and counted from its own time)."""
        return datetime.fromisoformat(self.made_at) > self.opens

    @property
    def since(self) -> str:
        """When the context starts: the later of the week's open and the call."""
        return max(self.opens, datetime.fromisoformat(self.made_at)).astimezone(timezone.utc).isoformat()


def thesis_table(calls: Iterable[Call]) -> dict:
    """The thesis file (Requirement 32.2): {instrument: {trading date: {side, draw, protected, since}}}, for every
    call with a side."""
    table: dict = {}
    for call in calls:
        if call.side == "NONE":
            continue
        entry = {"side": call.side, "draw": call.draw, "protected": call.protected, "since": call.since}
        for day in trading_dates(date.fromisoformat(call.week)):
            table.setdefault(call.instrument, {})[day] = entry
    return table


def week_move(bars, monday: date, now: datetime) -> dict:
    """A week's open and close on ``bars`` (the last close so far while it runs), and whether it has ended."""
    import pandas as pd

    opens, closes = week_open(monday), week_close(monday)
    t = pd.to_datetime(bars["time"], utc=True) if len(bars) else pd.Series([], dtype="datetime64[ns, UTC]")
    week = bars[(t >= opens) & (t < closes)]
    return {"final": now >= closes, "week_open": float(week["open"].iloc[0]) if len(week) else None,
            "week_close": float(week["close"].iloc[-1]) if len(week) else None}


def score_call(call: Call, bars, now: datetime) -> dict:
    """One call scored on its week's bars (Requirement 32.6): ``bars`` is a DataFrame of ``time`` (UTC), open, high,
    low and close covering the week. It gives:
    - the week's open and its close (the last close so far while the week runs), and whether it closed on the call's
      side;
    - the context's outcome from ``since``: delivered (the draw traded), invalidated (a New York D1 close beyond the
      protected swing) or open, the first of them and when;
    - a random walk's chance of reaching the draw before the protected swing from the price at ``since``."""
    import pandas as pd

    opens, closes = call.opens, week_close(date.fromisoformat(call.week))
    t = pd.to_datetime(bars["time"], utc=True) if len(bars) else pd.Series([], dtype="datetime64[ns, UTC]")
    week = bars[(t >= opens) & (t < closes)]
    out = {"final": now >= closes, "week_open": None, "week_close": None, "hit": None, "outcome": None, "at": None,
           "start_price": None, "walk": None}
    if week.empty:
        return out
    out["week_open"], out["week_close"] = float(week["open"].iloc[0]), float(week["close"].iloc[-1])
    if call.side == "NONE":
        return out
    s = 1 if call.side == "BULLISH" else -1
    out["hit"] = (out["week_close"] - out["week_open"]) * s > 0
    since = datetime.fromisoformat(call.since)
    tw = t[week.index]
    path = week[tw >= since]
    if path.empty:
        return out
    p0 = float(path["open"].iloc[0])
    out["start_price"] = p0
    span = (call.draw - call.protected) * s
    out["walk"] = min(1.0, max(0.0, (p0 - call.protected) * s / span))
    reached = path[(path["high"] >= call.draw) if s > 0 else (path["low"] <= call.draw)]
    delivered = pd.Timestamp(t[reached.index[0]]) if len(reached) else None
    day = (t[path.index].dt.tz_convert(_NY) + pd.Timedelta(hours=7)).dt.date
    invalidated = None
    for d, bars_of_day in path.groupby(day.to_numpy(), sort=True):
        end = datetime.combine(d, time(17), _NY).astimezone(timezone.utc)
        c = float(bars_of_day["close"].iloc[-1])
        if end <= now and (c - call.protected) * s < 0:
            invalidated = pd.Timestamp(end)
            break
    if delivered is not None and (invalidated is None or delivered < invalidated):
        out["outcome"], out["at"] = "delivered", delivered.isoformat()
    elif invalidated is not None:
        out["outcome"], out["at"] = "invalidated", invalidated.isoformat()
    else:
        out["outcome"] = "expired" if out["final"] else "open"
    return out


def paper_r(path: Path, instrument: str, start: datetime, end: datetime) -> tuple[int, float]:
    """A paper agent's filled trades in ``instrument`` placed in [start, end): how many, and their R net."""
    p = Path(path)
    if not p.exists():
        return 0, 0.0
    picked = [t for t in json.loads(p.read_text(encoding="utf-8"))
              if t.get("instrument") == instrument and t.get("filled_at") and t.get("net_r") is not None
              and start <= datetime.fromisoformat(t["placed_at"]) < end]
    return len(picked), round(sum(float(t["net_r"]) for t in picked), 3)


def _write(path: Path, data) -> None:
    """``data`` as JSON at ``path``, through a temporary file, so a reader never sees half of it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


class ContextBook:
    """The calls journal (every version, in the order made) and the thesis file written from the latest ones."""

    def __init__(self, path: Path = CALLS_FILE, theses: Path = THESIS_FILE) -> None:
        self.path, self.theses = Path(path), Path(theses)
        rows = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []
        self._calls = [Call(**row) for row in rows]

    def calls(self) -> list[Call]:
        """The latest call for each market and week."""
        latest = {(c.instrument, c.week): c for c in self._calls}
        return list(latest.values())

    def history(self, instrument: str, week: str) -> list[Call]:
        return [c for c in self._calls if (c.instrument, c.week) == (instrument.upper(), week)]

    def week(self, monday: date) -> dict[str, Call]:
        return {c.instrument: c for c in self.calls() if c.week == monday.isoformat()}

    def put(self, call: Call) -> Call:
        """Keep ``call`` (a later one for the same market and week replaces it) and rewrite the thesis file."""
        self._calls.append(call)
        _write(self.path, [asdict(c) for c in self._calls])
        self.write_theses()
        return call

    def write_theses(self) -> Path:
        _write(self.theses, thesis_table(self.calls()))
        return self.theses
