"""The context page's server side (context-engine Requirement 32.4): the trader's weekly calls on Noculus.

``GET /api/context?week=YYYY-MM-DD`` gives the week (by default the next to open), the nine markets with their last
price when the broker's terminal answers, and each market's call. ``POST /api/context/call`` keeps a call
(``agent.context_calls``), which rewrites the engine's thesis file. ``GET /api/context/scorecard`` scores every
called week on the terminal's M15 bars and the paper agents' records (Requirement 32.6).
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from agent.context_calls import (CALLS_FILE, PAPER_FILES, THESIS_FILE, Call, ContextBook, paper_r, score_call,
                                 week_close, week_monday, week_open)

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["BREAK_EVEN", "MARKETS", "ContextApp", "default_week"]

#: The markets the trader calls each week (2026-10-29: "all nine").
MARKETS = ("DXY", "XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")


def default_week(now: datetime) -> date:
    """The next week to open: the coming one at the weekend, the following one during a trading week."""
    monday = week_monday(now)
    return monday if now < week_open(monday) else monday + timedelta(days=7)


def _row(call: Call) -> dict:
    return {**asdict(call), "late": call.late, "since": call.since}


#: The hit rate on the week's close that one weekly side needs to clear the costs (2026-10-29: H-N's trades with
#: the week's own side, stops of ten spreads or more: 60% at 3R, 57% at 5R).
BREAK_EVEN = (0.57, 0.60)


class ContextApp:
    """The calls journal and thesis file, and a quote for each market (None without a terminal)."""

    def __init__(self, calls: Path = CALLS_FILE, theses: Path = THESIS_FILE,
                 quote: Optional[Callable[[str], Optional[float]]] = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 bars: Optional[Callable[[str, datetime, datetime], "pd.DataFrame"]] = None,
                 paper: Optional[dict[str, Path]] = None) -> None:
        self.calls_path, self.theses_path, self.quote, self.clock = Path(calls), Path(theses), quote, clock
        self.bars, self.paper = bars, dict(PAPER_FILES if paper is None else paper)

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

    def scorecard(self, q: Optional[dict] = None) -> dict:
        """Every called week and market, scored (Requirement 32.6), with the totals against BREAK_EVEN."""
        if self.bars is None:
            raise LookupError("the scorecard needs the broker's terminal: this server has none")
        now = self.clock()
        weeks: dict[str, list] = {}
        for call in sorted(self.book().calls(), key=lambda c: (c.week, MARKETS.index(c.instrument))):
            if call.opens > now:
                continue                                        # not opened yet: nothing to score
            monday = date.fromisoformat(call.week)
            start, end = week_open(monday), week_close(monday)
            try:
                bars = self.bars(call.instrument, start, min(end, now))
            except Exception as exc:                            # one market's bars failing leaves the rest
                weeks.setdefault(call.week, []).append({"call": _row(call), "error": str(exc)})
                continue
            agents = {name: dict(zip(("n", "r"), paper_r(path, call.instrument, start, end)))
                      for name, path in self.paper.items()}
            weeks.setdefault(call.week, []).append({"call": _row(call), **score_call(call, bars, now),
                                                    "agents": agents})
        rows = [r for rs in weeks.values() for r in rs if "error" not in r and r["call"]["side"] != "NONE"]
        final = [r for r in rows if r["final"] and r["hit"] is not None]
        totals = {"calls": len(rows), "final": len(final), "hits": sum(r["hit"] for r in final),
                  "hit_rate": (sum(r["hit"] for r in final) / len(final)) if final else None,
                  "delivered": sum(r["outcome"] == "delivered" for r in rows),
                  "invalidated": sum(r["outcome"] == "invalidated" for r in rows),
                  "break_even": BREAK_EVEN,
                  "agents": {name: {"n": sum(r["agents"][name]["n"] for r in rows),
                                    "r": round(sum(r["agents"][name]["r"] for r in rows), 3)} for name in self.paper}}
        return {"weeks": [{"week": w, "rows": rs} for w, rs in sorted(weeks.items(), reverse=True)],
                "totals": totals, "now": now.isoformat(timespec="seconds")}
