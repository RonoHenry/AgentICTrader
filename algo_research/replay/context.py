"""The context page's server side (context-engine Requirement 32.4): the trader's weekly calls on Noculus.

``GET /api/context?week=YYYY-MM-DD`` gives the week (by default the next to open), the nine markets with their last
price when the broker's terminal answers, and each market's call. ``POST /api/context/call`` keeps a call
(``agent.context_calls``), which rewrites the engine's thesis file.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from agent.context_calls import CALLS_FILE, THESIS_FILE, Call, ContextBook, week_monday, week_open

__all__ = ["MARKETS", "ContextApp", "default_week"]

#: The markets the trader calls each week (2026-10-29: "all nine").
MARKETS = ("DXY", "XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")


def default_week(now: datetime) -> date:
    """The next week to open: the coming one at the weekend, the following one during a trading week."""
    monday = week_monday(now)
    return monday if now < week_open(monday) else monday + timedelta(days=7)


def _row(call: Call) -> dict:
    return {**asdict(call), "late": call.late, "since": call.since}


class ContextApp:
    """The calls journal and thesis file, and a quote for each market (None without a terminal)."""

    def __init__(self, calls: Path = CALLS_FILE, theses: Path = THESIS_FILE,
                 quote: Optional[Callable[[str], Optional[float]]] = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.calls_path, self.theses_path, self.quote, self.clock = Path(calls), Path(theses), quote, clock

    def book(self) -> ContextBook:
        return ContextBook(self.calls_path, self.theses_path)

    def _price(self, instrument: str) -> Optional[float]:
        if self.quote is None:
            return None
        try:
            return self.quote(instrument)
        except Exception:                                       # the page works without the terminal
            return None

    def view(self, q: dict) -> dict:
        now = self.clock()
        default = default_week(now)
        monday = date.fromisoformat(q["week"]) if q.get("week") else default
        if monday.weekday() != 0:
            raise ValueError(f"week: a Monday, not {monday}")
        book = self.book()
        calls = book.week(monday)
        called = sorted({c.week for c in book.calls()} | {default.isoformat(), monday.isoformat()})
        return {"week": monday.isoformat(), "opens": week_open(monday).isoformat(), "default": default.isoformat(),
                "open": now >= week_open(monday), "now": now.isoformat(timespec="seconds"), "weeks": called,
                "rows": [{"instrument": m, "price": self._price(m),
                          "call": _row(calls[m]) if m in calls else None} for m in MARKETS]}

    def call(self, body: dict) -> dict:
        instrument = str(body.get("instrument", "")).upper()
        if instrument not in MARKETS:
            raise ValueError(f"instrument: one of {', '.join(MARKETS)}")
        num = (lambda v: None if v in (None, "") else float(v))
        call = Call(instrument, str(body.get("week", "")), str(body.get("side", "")), num(body.get("draw")),
                    num(body.get("protected")), str(body.get("note", "")).strip(),
                    self.clock().isoformat(timespec="seconds"))
        self.book().put(call)
        return {"call": _row(call)}
