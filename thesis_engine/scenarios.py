"""The trader's own trades as scenarios (thesis-engine Requirement 12.2, task 414).

Each scenario is a call the trader held (side, draw, protected level, from when to when) and, when they took one,
their trade. The calls are kept in the trader's journal space (``data/journal/thesis_engine/scenarios.json``,
git-ignored like the rest of their journal), not in the repository. A scenario runs the V1 machine on that one thesis
over a snapshot's M1, and the report sets the engine's path beside the trader's trade. They are checks that the
engine reads like the trader, not evidence: the trades were picked after the fact.

    python -m thesis_engine scenarios [--snapshot mt5-m1-2026-11]
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from thesis_engine.records import Thesis
from thesis_engine.replay import Journal, Market, prepare, run
from thesis_engine.settings import V1, Settings

__all__ = ["FILE", "Scenario", "Trade", "for_market", "load", "main", "render", "run_one"]

REPO = Path(__file__).resolve().parents[1]
FILE = REPO / "data" / "journal" / "thesis_engine" / "scenarios.json"
REPORT = REPO / "data" / "research" / "thesis_engine" / "scenarios.md"
NY = "America/New_York"


def _ns(ny: str) -> int:
    return int(pd.Timestamp(ny).tz_localize(NY).tz_convert("UTC").value)


def _ny(ns: Optional[int]) -> str:
    return "-" if ns is None else pd.Timestamp(int(ns), tz="UTC").tz_convert(NY).strftime("%a %d %b %H:%M")


@dataclass(frozen=True)
class Trade:
    side: str                    # LONG or SHORT
    entry: float
    stop: float
    target: float
    at: Optional[str] = None     # New York wall time, when the notes give it

    @property
    def r(self) -> float:
        """The target in R."""
        return (self.target - self.entry) / (self.entry - self.stop) if self.side == "LONG" else \
            (self.entry - self.target) / (self.stop - self.entry)


@dataclass(frozen=True)
class Scenario:
    name: str
    market: str
    side: str
    draw: float
    protected: float
    since: str                   # New York wall time
    until: str
    trade: Optional[Trade]
    notes: str
    confirmed: bool = False      # the trader has confirmed the call as read from their notes

    def thesis(self) -> Thesis:
        return Thesis(self.market, self.side, self.draw, self.protected, _ns(self.since), _ns(self.until), "SCENARIO",
                      note=self.name)


def load(path: Path = FILE) -> List[Scenario]:
    if not Path(path).exists():
        return []
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Scenario(**{**r, "trade": Trade(**r["trade"]) if r.get("trade") else None}) for r in rows]


def save(scenarios: Sequence[Scenario], path: Path = FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(s) for s in scenarios], indent=1), encoding="utf-8")
    return path


def for_market(market: str, path: Path = FILE) -> List[Scenario]:
    return [s for s in load(path) if s.market == market.upper()]


def run_one(sc: Scenario, mk: Market, s: Settings = V1, slippage: float = 0.0) -> dict:
    """The machine on the scenario's one thesis, and what it did beside the trader's trade."""
    j: Journal = run(mk, [sc.thesis()], s, slippage)
    moves = [(r["t"], r["frm"], r["to"], r["reason"]) for r in j.of("transition")]
    trades = j.of("trade")
    skips = Counter(r["reason"] for r in j.of("skip"))
    ended = next((r for r in j.of("note") if r["note"] == "thesis_end"), None)
    first = lambda state: next((t for t, _, to, _ in moves if to == state), None)          # noqa: E731
    out = {"name": sc.name, "market": sc.market, "side": sc.side, "draw": sc.draw, "protected": sc.protected,
           "since": sc.since, "until": sc.until, "confirmed": sc.confirmed, "notes": sc.notes,
           "trade": asdict(sc.trade) if sc.trade else None, "trade_r": sc.trade.r if sc.trade else None,
           "moves": moves, "trades": trades, "skips": dict(skips), "sweeps": sum(1 for r in j.of("note")
                                                                                 if r["note"] == "sweep"),
           "at_level": first("AT_LEVEL"), "armed": first("ARMED"),
           "levels": [r for r in j.of("note") if r["note"] == "level"],
           "ended": (ended["end"], ended["t"]) if ended else None, "typical_spread": mk.typical_spread}
    if sc.trade and sc.trade.at and trades:
        at = _ns(sc.trade.at)
        nearest = min(trades, key=lambda t: abs((t["filled_at"] or t["placed_at"]) - at))
        out["nearest"] = {"minutes": ((nearest["filled_at"] or nearest["placed_at"]) - at) / 60e9,
                          "price": nearest["fill"] - sc.trade.entry, "stop_ratio": nearest["risk"] /
                          abs(sc.trade.entry - sc.trade.stop)}
    return out


def render(results: Sequence[dict]) -> str:
    lines = ["# The trader's trades as scenarios", "",
             "The V1 machine on each call, read from the trader's notes (unconfirmed calls are marked). Checks that "
             "the engine reads like the trader, not evidence: the trades were picked after the fact.", ""]
    for r in results:
        t = r["trade"]
        lines += [f"## {r['name']}{'' if r['confirmed'] else ' (call unconfirmed)'}", "",
                  f"- **The call:** {r['side'].lower()}, draw {r['draw']:g}, protected {r['protected']:g}, "
                  f"from {r['since']} to {r['until']} New York.",
                  f"- **From the notes:** {r['notes']}",
                  f"- **Your trade:** " + (f"{t['side'].lower()} {t['entry']:g}, stop {t['stop']:g}, target "
                                           f"{t['target']:g} ({r['trade_r']:.1f}R){', at ' + t['at'] if t['at'] else ''}"
                                           if t else "none (a read)"),
                  f"- **The engine:** reached a level {_ny(r['at_level'])}, armed {_ny(r['armed'])}; "
                  f"{r['sweeps']} sweeps; skips {r['skips'] or 'none'}; the thesis ended "
                  + (f"{r['ended'][0].lower()} {_ny(r['ended'][1])}" if r["ended"] else "open") + "."]
        for tr in r["trades"]:
            lines.append(f"  - trade: {tr['direction'].lower()} {tr['fill']:.6g} at {_ny(tr['filled_at'])}, stop "
                         f"{tr['stop']:.6g} ({tr['risk_spreads']:.0f} spreads), {tr['reason']} at {_ny(tr['closed_at'])}"
                         f", {tr['net_r']:+.2f}R")
        if "nearest" in r:
            n = r["nearest"]
            lines.append(f"- **Beside yours:** its nearest entry was {n['minutes']:+.0f} minutes from yours, "
                         f"{n['price']:+.6g} in price, with a stop {n['stop_ratio']:.1f}x yours.")
        lines += ["", "| New York | From | To | Why |", "|---|---|---|---|"]
        lines += [f"| {_ny(t)} | {a} | {b} | {why} |" for t, a, b, why in r["moves"]]
        lines.append("")
    return "\n".join(lines)


def main(snapshot: str = "mt5-m1-2026-11") -> None:
    from agent.broker_profiles import load_profile
    specs = load_profile("exness-standard-swapfree").specs()
    folder = REPO / "data" / "research" / "snapshots" / snapshot
    markets: Dict[str, Market] = {}
    results = []
    for sc in load():
        if sc.market not in markets:
            markets[sc.market] = prepare(sc.market, pd.read_parquet(folder / f"{sc.market}_M1.parquet"))
        results.append(run_one(sc, markets[sc.market], slippage=specs[sc.market].stop_slippage))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(results), encoding="utf-8")
    for r in results:
        made = ", ".join(f"{t['direction'].lower()} {t['net_r']:+.2f}R" for t in r["trades"]) or "no trade"
        print(f"{r['name']}: {made}; skips {r['skips'] or '-'}; ended {r['ended'][0] if r['ended'] else 'open'}")
    print(f"report: {REPORT}")
