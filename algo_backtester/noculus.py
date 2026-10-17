"""Noculus: the trader's marks and trades against the engine's (algo-backtester update 2026-10-16).

The charts app is Noculus (D30), and its Engine mode is the engine watch (``watch.py``). A watch session started
blind withholds the engine's layers until the trader reveals them (D27). Meanwhile the trader marks PD arrays by
their candles and places pseudo trades, at the replay clock. Each blind session keeps its own journal:

    data/journal/noculus/<instrument>/<session>.json     {"session", "marks", "trades", "reveal", "comparison"}

It is local and git-ignored, and written whole through a temporary file after every change.

Validates: Requirements 17.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from algo_backtester.config import REPO_ROOT

__all__ = ["NOCULUS_DIR", "NoculusJournal"]

#: Where the sessions' journals live (local, git-ignored).
NOCULUS_DIR = REPO_ROOT / "data" / "journal" / "noculus"
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
