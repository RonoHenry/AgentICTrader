"""The context page's server side (context-engine Requirement 32.4): the trader's weekly calls on Noculus.

``GET /api/context?week=YYYY-MM-DD`` gives the week (by default the next to open), the nine markets with their last
price when the broker's terminal answers, and each market's call. ``POST /api/context/call`` keeps a call
(``agent.context_calls``), which rewrites the engine's thesis file. ``GET /api/context/scorecard`` scores every
called week on the terminal's M15 bars and the paper agents' records (Requirement 32.6).

Algo Mind (algo-mind Requirements 4.2-4.3, 5.1): the view carries the week's brief beside the trader's calls,
``POST /api/context/brief`` makes the brief again, saving a call rewrites the agreement's thesis file, and the
scorecard scores the brain's calls and the agreement as it scores the trader's.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

import json

from agent.context_calls import (CALLS_FILE, PAPER_FILES, THESIS_FILE, Call, ContextBook, paper_r, score_call,
                                 week_close, week_monday, week_move, week_open)

__all__ = ["BREAK_EVEN", "MARKETS", "ContextApp", "coherence", "default_week"]

#: The markets the trader calls each week (2026-10-29: "all nine").
MARKETS = ("DXY", "XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")
REPO = Path(__file__).resolve().parents[2]
BRIEFS = REPO / "data" / "algo_mind" / "briefs"
AGREE_THESES = REPO / "data" / "research" / "theses" / "agree_theses.json"


def coherence(calls: dict) -> list:
    """Calls on markets that usually move apart, called the same way, or that usually move together, called apart
    (``calls``: market -> side)."""
    notes = []
    dxy = calls.get("DXY")
    for fx in ("EURUSD", "GBPUSD", "XAUUSD"):
        if dxy in ("BULLISH", "BEARISH") and calls.get(fx) == dxy:
            notes.append(f"DXY and {fx} both {dxy.lower()}: they usually move apart")
    us = {m: calls.get(m) for m in ("US100", "US500", "US30") if calls.get(m) in ("BULLISH", "BEARISH")}
    if len(set(us.values())) > 1:
        notes.append("the US indices are called apart: " + ", ".join(f"{m} {v.lower()}" for m, v in us.items()))
    return notes


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
                 paper: Optional[dict[str, Path]] = None, briefs: Path = BRIEFS, agree: Path = AGREE_THESES,
                 brief_writer: Optional[Callable[[date, ContextBook], Path]] = None) -> None:
        self.calls_path, self.theses_path, self.quote, self.clock = Path(calls), Path(theses), quote, clock
        self.bars, self.paper = bars, dict(PAPER_FILES if paper is None else paper)
        self.briefs, self.agree, self.brief_writer = Path(briefs), Path(agree), brief_writer

    def book(self) -> ContextBook:
        return ContextBook(self.calls_path, self.theses_path)

    def _price(self, instrument: str) -> Optional[float]:
        if self.quote is None:
            return None
        try:
            return self.quote(instrument)
        except Exception:                                       # the page works without the terminal
            return None

    def brief(self, week: str) -> Optional[dict]:
        """Algo Mind's brief for the week of ``week`` (its Monday), or None."""
        path = self.briefs / f"{week}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _brain(self, week: str) -> Optional[dict]:
        b = self.brief(week)
        if b is None:
            return None
        rows = {r["market"]: {"call": r.get("call"), "p": r.get("p"), "provisional": r.get("provisional"),
                              "share_up": (r.get("analogs") or {}).get("share_up")} for r in b["rows"]}
        return {"version": b["version"], "made_at": b["made_at"], "rows": rows,
                "provisional": any(bool(r["provisional"]) for r in rows.values()),
                "notes": coherence({m: r["call"] for m, r in rows.items()})}

    def view(self, q: dict) -> dict:
        now = self.clock()
        default = default_week(now)
        monday = date.fromisoformat(q["week"]) if q.get("week") else default
        if monday.weekday() != 0:
            raise ValueError(f"week: a Monday, not {monday}")
        book = self.book()
        calls = book.week(monday)
        called = sorted({c.week for c in book.calls()} | {default.isoformat(), monday.isoformat()})
        brain = self._brain(monday.isoformat())
        return {"week": monday.isoformat(), "opens": week_open(monday).isoformat(), "default": default.isoformat(),
                "open": now >= week_open(monday), "now": now.isoformat(timespec="seconds"), "weeks": called,
                "brain": brain, "notes": coherence({m: c.side for m, c in calls.items()}),
                "rows": [{"instrument": m, "price": self._price(m),
                          "call": _row(calls[m]) if m in calls else None,
                          "brain": brain["rows"].get(m) if brain else None} for m in MARKETS]}

    def run_brain(self, body: dict) -> dict:
        """Make the week's brief again (Algo Mind), then the view."""
        monday = date.fromisoformat(str(body.get("week", "")))
        if monday.weekday() != 0:
            raise ValueError(f"week: a Monday, not {monday}")
        writer = self.brief_writer
        if writer is None:
            from algo_mind.brief import write_brief

            def writer(m, book):
                return write_brief(pd.Timestamp(m), book=book)
        writer(monday, self.book())
        return self.view({"week": monday.isoformat()})

    def _write_agree(self, book: ContextBook) -> None:
        from algo_mind.brief import write_agree_theses
        write_agree_theses(book, self.briefs, self.agree)

    def call(self, body: dict) -> dict:
        instrument = str(body.get("instrument", "")).upper()
        if instrument not in MARKETS:
            raise ValueError(f"instrument: one of {', '.join(MARKETS)}")
        num = (lambda v: None if v in (None, "") else float(v))
        call = Call(instrument, str(body.get("week", "")), str(body.get("side", "")), num(body.get("draw")),
                    num(body.get("protected")), str(body.get("note", "")).strip(),
                    self.clock().isoformat(timespec="seconds"))
        book = self.book()
        book.put(call)
        self._write_agree(book)
        return {"call": _row(call)}

    def scorecard(self, q: Optional[dict] = None) -> dict:
        """Every opened week with the trader's calls or the brain's brief, each market scored (Requirement 32.6;
        algo-mind 4.3), with the totals against BREAK_EVEN for the trader, the brain and the two agreeing."""
        if self.bars is None:
            raise LookupError("the scorecard needs the broker's terminal: this server has none")
        now = self.clock()
        by_week: dict = {}
        for call in self.book().calls():
            by_week.setdefault(call.week, {})[call.instrument] = call
        briefs = {p.stem: self.brief(p.stem) for p in sorted(self.briefs.glob("????-??-??.json"))}
        weeks: dict = {}
        for week in sorted(set(by_week) | set(briefs)):
            monday = date.fromisoformat(week)
            start, end = week_open(monday), week_close(monday)
            if start > now:
                continue                                        # not opened yet: nothing to score
            calls = by_week.get(week, {})
            brain = {r["market"]: r for r in (briefs.get(week) or {"rows": []})["rows"]}
            for market in MARKETS:
                call, b = calls.get(market), brain.get(market)
                brain_side = (b or {}).get("call")
                if call is None and brain_side not in ("BULLISH", "BEARISH"):
                    continue
                row = {"market": market, "call": _row(call) if call else None}
                try:
                    bars = self.bars(market, start, min(end, now))
                except Exception as exc:                        # one market's bars failing leaves the rest
                    weeks.setdefault(week, []).append({**row, "error": str(exc)})
                    continue
                if call:
                    row.update(score_call(call, bars, now))
                else:
                    row.update({**week_move(bars, monday, now), "hit": None, "outcome": None, "at": None,
                                "walk": None})
                row["agents"] = {name: dict(zip(("n", "r"), paper_r(path, market, start, end)))
                                 for name, path in self.paper.items()}
                side = {"BULLISH": 1, "BEARISH": -1}.get(brain_side or "")
                moved = row["week_open"] is not None and row["week_close"] != row["week_open"]
                row["brain"] = None if b is None else {
                    "call": brain_side, "p": b.get("p"), "provisional": b.get("provisional"),
                    "hit": ((row["week_close"] - row["week_open"]) * side > 0) if side and moved else None}
                weeks.setdefault(week, []).append(row)
        rows = [r for rs in weeks.values() for r in rs if "error" not in r]
        trader = [r for r in rows if r["call"] and r["call"]["side"] != "NONE"]
        final = [r for r in trader if r["final"] and r["hit"] is not None]

        def rate(picked: list) -> dict:
            done = [r for r in picked if r["final"] and r["brain"]["hit"] is not None]
            hits = sum(r["brain"]["hit"] for r in done)
            return {"calls": len(picked), "final": len(done), "hits": hits,
                    "hit_rate": hits / len(done) if done else None}

        brain_called = [r for r in rows if r["brain"] and r["brain"]["call"] in ("BULLISH", "BEARISH")]
        agreeing = [r for r in brain_called if r["call"] and r["call"]["side"] == r["brain"]["call"]]
        totals = {"calls": len(trader), "final": len(final), "hits": sum(r["hit"] for r in final),
                  "hit_rate": (sum(r["hit"] for r in final) / len(final)) if final else None,
                  "delivered": sum(r["outcome"] == "delivered" for r in trader),
                  "invalidated": sum(r["outcome"] == "invalidated" for r in trader),
                  "break_even": BREAK_EVEN, "brain": rate(brain_called), "agree": rate(agreeing),
                  "agents": {name: {"n": sum(r["agents"][name]["n"] for r in trader),
                                    "r": round(sum(r["agents"][name]["r"] for r in trader), 3)}
                             for name in self.paper}}
        return {"weeks": [{"week": w, "rows": rs} for w, rs in sorted(weeks.items(), reverse=True)],
                "totals": totals, "now": now.isoformat(timespec="seconds")}
