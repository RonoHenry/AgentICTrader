"""The Thesis Engine's records (thesis-engine design.md, "Data Models").

Pools, arrays, ranges and structure are AlgoMindDIS's records and arrays as they are (Requirement 3); these are the
records the engine adds. Times are UTC nanoseconds; ids are content hashes (``algomind_dis.records.make_id``), so the
same content always has the same id. ``to_json`` / ``from_json`` are AlgoMindDIS's.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from algomind_dis.records import from_json, make_id, to_json

__all__ = ["SIDES", "Hand", "Intent", "Level", "Skip", "Thesis", "Transition", "from_json", "make_id", "to_json"]

SIDES = ("BULLISH", "BEARISH")


@dataclass(frozen=True)
class Thesis:
    """One side for one market, with its draw and its protected level, live from ``since`` to ``until``
    (Requirement 4.1). ``until_reason`` names what ``until`` passing is: EXPIRED, or WITHDRAWN for a source that
    stopped holding it (a thesis file's dates)."""
    market: str
    side: str
    draw: float
    protected: float
    since: int
    until: int
    source: str
    note: str = ""
    until_reason: str = "EXPIRED"

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ValueError(f"side: one of {', '.join(SIDES)}, not {self.side!r}")
        for name in ("draw", "protected"):
            if not math.isfinite(float(getattr(self, name))):
                raise ValueError(f"{name}: a price is required")
        if (self.protected >= self.draw) if self.side == "BULLISH" else (self.protected <= self.draw):
            where = "below" if self.side == "BULLISH" else "above"
            raise ValueError(f"protected: a {self.side} thesis's protected level is {where} its draw")
        if self.until <= self.since:
            raise ValueError("until: after since")

    @property
    def bullish(self) -> bool:
        return self.side == "BULLISH"

    @property
    def id(self) -> str:
        return make_id(self.market, self.side, self.draw, self.protected, self.since, self.until, self.source)


@dataclass(frozen=True)
class Level:
    """Where the engine waits (Requirement 6): one live array of the thesis's side, and what lines up there."""
    array_id: str
    tf: str
    kind: str
    side: str
    low: float
    high: float
    formed_at: int
    end: int                   # its frame's index of the first close beyond its far edge (book.NEVER: none)
    score: int
    reasons: tuple

    @property
    def ce(self) -> float:
        return (self.low + self.high) / 2

    def describe(self) -> str:
        return f"the {self.tf} {self.side.lower()} {self.kind} {self.low:.6g}-{self.high:.6g} (score {self.score})"


@dataclass(frozen=True)
class Hand:
    """A sweep at the level, waiting for the E frame's CISD (Requirement 8)."""
    pool: str                  # what was taken, in words
    pool_price: float
    swept: int                 # the E candle's index
    extreme: float             # the sweep's extreme so far
    frame: str = ""            # V3: the child frame the CISD is read on
    pool_tf: str = ""          # V3: the pool's frame
    k0: int = -1               # V3: the child candle that holds the sweep
    seen: int = -1             # V3: the last child candle read
    rframe: str = ""           # V4: once the setup is confirmed, the refining frame
    zone_lo: float = 0.0       # V4: the setup's order block (its CISD run's bodies)
    zone_hi: float = 0.0
    until: int = 0             # V4: when the setup stops waiting for its entry
    touched: int = -1          # V4: the refining candle in which price came back into the order block
    rseen: int = -1            # V4: the last refining candle read


@dataclass(frozen=True)
class Intent:
    market: str
    thesis_id: str
    level_id: str
    side: str
    kind: str                  # MARKET
    entry: float               # the expected price: the CISD close, plus the spread for a buy
    stop: float
    target: float
    at: int                    # placed at: the CISD candle's close


@dataclass(frozen=True)
class Skip:
    intent: Intent
    reason: str                # STOP_TOO_SMALL | TARGET_TOO_CLOSE | BUDGET
    detail: str


@dataclass(frozen=True)
class Transition:
    market: str
    t: int
    frm: str
    to: str
    reason: str
    frame: str
    thesis_id: Optional[str] = None
    level_id: Optional[str] = None
    pool: Optional[str] = None
    order_id: Optional[str] = None
