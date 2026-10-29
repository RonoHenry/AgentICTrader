"""Algo Mind's weekly brief and the thesis files the execution trades from (algo-mind Requirements 4.1, 5.1).

A brief (``data/algo_mind/briefs/<week>.json``) gives, for each market: the state at the week's open (read at the
last close before it opens, provisional without its Friday), the brain's probability and call, and memory's
analogs. Writing it rewrites:
- the brain's thesis file: its calls for every trading date of every briefed week;
- the agreement's thesis file: the markets where the trader's call and the brain's agree, with the trader's draw
  and protected swing (AM-D8).

    python -m algo_mind brief --week 2026-11-02
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from agent.context_calls import ContextBook, _write, thesis_table, trading_dates
from algo_mind.brain import MODELS, load_version
from algo_mind.memory import analogs
from algo_mind.sources import fetch_live, live_days, state_at
from algo_research.search_d1 import MARKETS
from algo_research.search_state import FEATURES

__all__ = ["AGREE_THESES", "BRAIN_THESES", "BRIEFS", "SIDES", "write_agree_theses", "write_brief"]

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data" / "algo_mind"
BRIEFS = ROOT / "briefs"
BRAIN_THESES = REPO / "data" / "research" / "theses" / "brain_theses.json"
AGREE_THESES = REPO / "data" / "research" / "theses" / "agree_theses.json"
SIDES = {1: "BULLISH", -1: "BEARISH", 0: "NONE"}


def _briefs(folder: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(folder).glob("????-??-??.json"))]


def _brain_table(briefs: list[dict]) -> dict:
    table: dict = {}
    for b in briefs:
        for r in b["rows"]:
            if r.get("call") in ("BULLISH", "BEARISH"):
                for day in trading_dates(date.fromisoformat(b["week"])):
                    table.setdefault(r["market"], {})[day] = {"side": r["call"]}
    return table


def write_agree_theses(book: ContextBook, briefs: Path = BRIEFS, out: Path = AGREE_THESES) -> Path:
    """The trader's calls where the brain's brief for the same week calls the same side (Requirement 5.1)."""
    brain = {(b["week"], r["market"]): r.get("call") for b in _briefs(briefs) for r in b["rows"]}
    agreeing = [c for c in book.calls() if c.side != "NONE" and brain.get((c.week, c.instrument)) == c.side]
    _write(Path(out), thesis_table(agreeing))
    return Path(out)


def write_brief(monday: pd.Timestamp, version: Optional[str] = None, now: Optional[datetime] = None,
                markets: tuple[str, ...] = MARKETS, fetcher: Callable[[str, datetime], dict] = None,
                root: Optional[Path] = None, name: Optional[str] = None,
                book: Optional[ContextBook] = None) -> Path:
    """The brief for the week of ``monday``, and the thesis files. ``root`` holds the models, briefs and thesis
    files together (tests); by default they are Algo Mind's and the research theses' folders."""
    now = now or datetime.now(timezone.utc)
    fetcher = fetcher or (lambda m, t: fetch_live(m, t))
    models, briefs = (Path(root) / "models", Path(root) / "briefs") if root else (MODELS, BRIEFS)
    brain_out = Path(root) / "brain_theses.json" if root else BRAIN_THESES
    if version is None:                                       # the version in use, by the ledger (Requirement 7.2)
        from algo_mind.ledger import Ledger
        version = Ledger(models=models).in_use()
    brain = load_version(version, models)
    monday = pd.Timestamp(monday).normalize()
    rows = []
    for market in markets:
        days = live_days(fetcher(market, now), market, now.date())
        state, provisional = state_at(market, days, monday)
        if state is None:
            rows.append({"market": market, "call": "NONE", "p": None, "provisional": True,
                         "note": "not enough history for the state"})
            continue
        called = brain.call(pd.DataFrame([state])).iloc[0]
        memory = analogs(brain.train, state)
        rows.append({"market": market, "p": round(float(called["p"]), 4), "call": SIDES[int(called["call"])],
                     "provisional": provisional, "price": float(state["open"]),
                     "last_day": str(pd.Timestamp(days["date"].iat[-1]).date()) if len(days) else None,
                     "analogs": {"k": memory["k"], "share_up": memory["share_up"], "weeks": memory["weeks"][:5]},
                     "state": {f: round(float(state[f]), 4) for f in FEATURES}})
    brief = {"week": monday.date().isoformat(), "version": version, "thresholds": [brain.lo, brain.hi],
             "made_at": now.isoformat(timespec="seconds"), "rows": rows}
    briefs.mkdir(parents=True, exist_ok=True)
    path = briefs / f"{name or monday.date().isoformat()}.json"
    path.write_text(json.dumps(brief, indent=1), encoding="utf-8")
    _write(brain_out, _brain_table(_briefs(briefs)))
    if book is not None:
        write_agree_theses(book, briefs, Path(root) / "agree_theses.json" if root else AGREE_THESES)
    return path
