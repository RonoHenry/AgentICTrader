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

__all__ = ["CALLS_FILE", "SIDES", "THESIS_FILE", "Call", "ContextBook", "thesis_table", "trading_dates",
           "week_monday", "week_open"]

REPO = Path(__file__).resolve().parents[1]
CALLS_FILE = REPO / "data" / "journal" / "context" / "calls.json"
THESIS_FILE = REPO / "data" / "research" / "theses" / "context_theses.json"
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
