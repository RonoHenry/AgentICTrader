"""Noculus: the trader's marks and trades against the engine's (algo-backtester update 2026-10-16).

The charts app is Noculus (D30), and its Engine mode is the engine watch (``watch.py``). A watch session started
blind withholds the engine's layers until the trader reveals them (D27). Meanwhile the trader marks PD arrays by
their candles and places pseudo trades, at the replay clock. Each blind session keeps its own journal:

    data/journal/noculus/<instrument>/<session>.json     {"session", "marks", "trades", "reveal", "comparison"}

It is local and git-ignored, and written whole through a temporary file after every change.

A mark is read from the candles the trader clicked, on bars that closed by the replay clock (Requirement 18):

- **FVG** — its third candle, C1 two before. Bullish when C3's low is above C1's high: the gap runs from C1's
  high to C3's low, and ``mid`` is the CE. Bearish is the mirror. Three candles without a gap are refused.
  This is ``algo_research.atlas.arrays.fvgs`` read from a click instead of from the bars (AR-D27).
- **IFVG** — the same three candles, plus the first later close of that timeframe beyond the gap's far edge. It
  carries the gap's zone, facing the other way. Before that close it is still an FVG, and the mark is refused.
- **Order block** — the block's own candle: its high to low, ``mid`` the midpoint of its body (the MT). The
  direction is the trader's, and defaults to the opposite of the candle's colour.
- **Breaker** — an order-block candle plus the first later close beyond it, facing the other way.

``formed_at`` is always the close that made the mark: C3's for a gap, the flipping candle's for an inversion.
Nothing is read from a candle that has not closed by the clock, so a mark holds only what the trader could see.

Validates: Requirements 17.4, 18.1-18.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from algo_backtester.config import REPO_ROOT
from algo_research.replay.timeframes import seconds_of

__all__ = ["MARK_TOOLS", "NOCULUS_DIR", "NoculusJournal", "build_mark"]

#: Where the sessions' journals live (local, git-ignored).
NOCULUS_DIR = REPO_ROOT / "data" / "journal" / "noculus"
#: The tools the trader marks with (Requirement 18.1).
MARK_TOOLS = ("FVG", "IFVG", "OB", "BRK")
_KEYS = ("session", "marks", "trades", "reveal", "comparison")


class NoculusJournal:
    """One blind session's journal: its marks, trades, reveal and comparison."""

    def __init__(self, path: Path, session: Optional[dict] = None) -> None:
        self.path = Path(path)
        if self.path.is_file():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"session": dict(session or {}), "marks": [], "trades": [], "reveal": None, "comparison": None}
        for key in _KEYS:
            self.data.setdefault(key, [] if key in ("marks", "trades") else None)

    def save(self) -> None:
        """Write the whole journal through a temporary file, so a crash never leaves half of it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    # ── the trader's marks (Requirement 18) ─────────────────────────────────
    def add_mark(self, mark: dict) -> dict:
        """Keep a mark, numbered in the order it was made."""
        row = {"id": f"m{len(self.data['marks']) + 1}", **mark, "deleted_at": None}
        self.data["marks"].append(row)
        self.save()
        return row

    def delete_mark(self, mark_id: str, clock: int) -> dict:
        """Mark one as deleted, at the clock. It stays in the journal (Requirement 18.3)."""
        for row in self.data["marks"]:
            if row["id"] == mark_id:
                row["deleted_at"] = int(clock)
                self.save()
                return row
        raise KeyError(f"no mark {mark_id} in this session")


def _closed_bars(bars: pd.DataFrame, tf: str, clock: int) -> tuple[np.ndarray, tuple[np.ndarray, ...], int]:
    """The ``tf`` bars closed by ``clock``, and how many of them there are."""
    t = np.asarray(bars["time"], dtype=np.int64)
    n = int(np.count_nonzero(t + seconds_of(tf) <= clock))
    return t, tuple(np.asarray(bars[k], dtype=float) for k in ("open", "high", "low", "close")), n


def _clicked(t: np.ndarray, n: int, tf: str, candle: int) -> int:
    """Where the clicked candle sits among the closed bars, or why it cannot be used."""
    hit = np.flatnonzero(t == candle)
    if not len(hit):
        raise ValueError(f"no {tf} candle starts at {candle}")
    if int(hit[0]) >= n:
        raise ValueError(f"that {tf} candle has not closed by the clock")
    return int(hit[0])


def _beyond(close: np.ndarray, n: int, start: int, level: float, below: bool, tf: str, still: str) -> int:
    """The first closed bar after ``start`` whose close is beyond ``level``, or a refusal."""
    segment = close[start + 1:n]
    hits = segment < level if below else segment > level
    if not hits.any():
        raise ValueError(f"no {tf} close beyond it yet: it is still {still}")
    return start + 1 + int(np.argmax(hits))


def build_mark(bars: pd.DataFrame, *, tool: str, tf: str, clock: int, candle: int,
               direction: Optional[int] = None, note: str = "") -> dict:
    """One mark from the candles clicked on ``tf``, read only from bars closed by ``clock``.

    ``bars`` are that timeframe's bars as the chart draws them (columns time — the bar's start in New York wall
    seconds — open, high, low, close). ``candle`` is the clicked bar's start: C3 for a gap, the block's candle
    for an order block. A mark that would need a candle closing after the clock is refused, with the reason.
    """
    tool, tf, clock, candle = str(tool).upper(), str(tf), int(clock), int(candle)
    if tool not in MARK_TOOLS:
        raise ValueError(f"tool: one of {', '.join(MARK_TOOLS)}")
    size = seconds_of(tf)                                       # also refuses a timeframe the charts don't keep
    t, (o, h, l, c), n = _closed_bars(bars, tf, clock)
    i = _clicked(t, n, tf, candle)
    if tool in ("FVG", "IFVG"):
        if i < 2:
            raise ValueError(f"an FVG needs the two candles before C3: there are none before {candle}")
        if l[i] > h[i - 2]:
            facing, low, high = 1, float(h[i - 2]), float(l[i])
        elif h[i] < l[i - 2]:
            facing, low, high = -1, float(h[i]), float(l[i - 2])
        else:
            raise ValueError(f"those three {tf} candles leave no gap")
        mid, formed, clicked = (low + high) / 2, int(t[i]) + size, [int(t[i - 2]), int(t[i - 1]), int(t[i])]
        if tool == "IFVG":                                      # the gap, read the other way after a close beyond
            j = _beyond(c, n, i, low if facing == 1 else high, facing == 1, tf, "an FVG")
            facing, formed, clicked = -facing, int(t[j]) + size, [*clicked, int(t[j])]
    else:
        facing = int(direction) if direction else (-1 if c[i] > o[i] else 1)   # the opposite of the candle's colour
        low, high = float(l[i]), float(h[i])
        mid, formed, clicked = (float(o[i]) + float(c[i])) / 2, int(t[i]) + size, [int(t[i])]
        if tool == "BRK":
            j = _beyond(c, n, i, low if facing == 1 else high, facing == 1, tf, "an order block")
            facing, formed, clicked = -facing, int(t[j]) + size, [*clicked, int(t[j])]
    return {"tool": tool, "tf": tf, "direction": int(facing), "low": low, "high": high, "mid": mid,
            "formed_at": formed, "candles": clicked, "clock": clock, "note": str(note or "")[:1000]}
