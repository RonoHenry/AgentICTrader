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
from algo_mind.sources import LIVE, fetch_live, live_days, live_macro
from algo_research.search_state2 import macro_table, own_state2_at, widen
from algo_research.search_d1 import MARKETS

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


def week_states(monday: pd.Timestamp, now: datetime, fetcher: Callable, macro_fetcher: Optional[Callable] = None,
                live_root: Path = LIVE) -> tuple[dict, dict, dict]:
    """Every market's widened state at the open of the week of ``monday`` (H-Z's: it holds H-Y's too), read from
    the live senses, with whether each is provisional and each market's days."""
    days_by, own, provisional = {}, {}, {}
    for m in MARKETS:
        try:
            days_by[m] = live_days(fetcher(m, now), m, now.date())
        except Exception:                                     # a market the feed can't give is left out
            days_by[m] = pd.DataFrame(columns=["date", "open", "high", "low", "close"])
        row, prov = own_state2_at(m, days_by[m], monday) if len(days_by[m]) else (None, True)
        provisional[m] = prov
        if row is not None:
            own[m] = row
    live_macro(now, live_root, macro_fetcher)
    wide = widen({m: pd.DataFrame([own[m]]) for m in own}, macro_table(live_root)) if own else pd.DataFrame()
    return {r["market"]: r for r in wide.to_dict("records")}, provisional, days_by


def write_brief(monday: pd.Timestamp, version: Optional[str] = None, now: Optional[datetime] = None,
                markets: tuple[str, ...] = MARKETS, fetcher: Callable[[str, datetime], dict] = None,
                root: Optional[Path] = None, name: Optional[str] = None,
                book: Optional[ContextBook] = None, candidates: Optional[tuple] = None,
                macro_fetcher: Optional[Callable] = None) -> Path:
    """The brief for the week of ``monday``: the version in use decides the calls, the candidates' calls ride
    beside them; and the thesis files. ``root`` holds the models, briefs, live bars and thesis files together
    (tests); by default they are Algo Mind's and the research theses' folders."""
    from algo_mind.ledger import Ledger

    now = now or datetime.now(timezone.utc)
    fetcher = fetcher or (lambda m, t: fetch_live(m, t))
    models, briefs = (Path(root) / "models", Path(root) / "briefs") if root else (MODELS, BRIEFS)
    live_root = Path(root) / "live" if root else LIVE
    brain_out = Path(root) / "brain_theses.json" if root else BRAIN_THESES
    ledger = Ledger(Path(root) / "ledger.jsonl", models) if root else Ledger(models=models)
    version = version or ledger.in_use()
    brain = load_version(version, models)
    others = {v: load_version(v, models) for v in (ledger.candidates() if candidates is None else candidates)
              if v != version}
    monday = pd.Timestamp(monday).normalize()
    states, provisional, days_by = week_states(monday, now, fetcher, macro_fetcher, live_root)
    rows = []
    for market in markets:
        state = states.get(market)
        if state is None:
            rows.append({"market": market, "call": "NONE", "p": None, "provisional": True,
                         "note": "not enough history for the state"})
            continue
        frame = pd.DataFrame([state])
        called = brain.call(frame).iloc[0]
        memory = analogs(brain.train, state, features=brain.features)
        days = days_by[market]
        rows.append({"market": market, "p": round(float(called["p"]), 4), "call": SIDES[int(called["call"])],
                     "provisional": provisional[market], "price": float(state["open"]),
                     "last_day": str(pd.Timestamp(days["date"].iat[-1]).date()) if len(days) else None,
                     "analogs": {"k": memory["k"], "share_up": memory["share_up"], "weeks": memory["weeks"][:5]},
                     "state": {f: round(float(state[f]), 4) for f in brain.features},
                     "candidates": {v: {"p": round(float(c["p"]), 4), "call": SIDES[int(c["call"])]}
                                    for v, b in others.items() for c in [b.call(frame).iloc[0]]}})
    brief = {"week": monday.date().isoformat(), "version": version, "thresholds": [brain.lo, brain.hi],
             "candidates": sorted(others), "made_at": now.isoformat(timespec="seconds"), "rows": rows}
    briefs.mkdir(parents=True, exist_ok=True)
    path = briefs / f"{name or monday.date().isoformat()}.json"
    path.write_text(json.dumps(brief, indent=1), encoding="utf-8")
    _write(brain_out, _brain_table(_briefs(briefs)))
    if book is not None:
        write_agree_theses(book, briefs, Path(root) / "agree_theses.json" if root else AGREE_THESES)
    return path
