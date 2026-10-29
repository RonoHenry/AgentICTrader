"""Algo Mind's learning ledger (algo-mind Requirement 7.1-7.2): refits are candidates, judged only on later weeks.

Every fit, judgement and adoption is a line of ``data/algo_mind/ledger.jsonl``. A candidate is judged on the weeks
after its training window, against the version in use on the same weeks, by H-Y's rule (the thirds' hit rate minus
each market's drift). It replaces the version in use only when its excess is higher there; with fewer than
``min_calls`` calls from either, the verdict waits.

    python -m algo_mind refit --version v2      # fit a candidate on every permitted week so far
    python -m algo_mind judge --candidate v2    # judge it on the weeks after its window
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from algo_mind.brain import MODELS, load_version
from algo_research.search_state import judge as judge_calls

__all__ = ["LEDGER", "Ledger"]

LEDGER = Path(__file__).resolve().parents[1] / "data" / "algo_mind" / "ledger.jsonl"
FIRST = "v1"


class Ledger:
    def __init__(self, path: Path = LEDGER, models: Path = MODELS) -> None:
        self.path, self.models = Path(path), Path(models)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def log(self, action: str, **fields) -> dict:
        entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "action": action, **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry

    def in_use(self) -> str:
        """The version the brief uses: the last adopted, or v1."""
        adopted = [e["version"] for e in self.entries() if e["action"] == "adopt"]
        return adopted[-1] if adopted else FIRST

    def judge(self, candidate: str, states: pd.DataFrame, min_calls: int = 150) -> dict:
        """Judge ``candidate`` against the version in use on ``states``' weeks after the candidate's training window
        (states with a direction), log it, and adopt it if it does better there."""
        current = self.in_use()
        cand, used = load_version(candidate, self.models), load_version(current, self.models)
        start = pd.Timestamp(cand.meta["train_end"])
        later = states[(states["week"] >= start) & (states["up"] != 0)].reset_index(drop=True)
        result = {"candidate": candidate, "in_use_version": current, "weeks_from": str(start.date()),
                  "weeks": len(later)}
        scores = {}
        for name, brain in (("candidate", cand), ("in_use", used)):
            r = judge_calls(brain.call(later)) if len(later) else {"calls": 0}
            scores[name] = {k: r.get(k) for k in ("calls", "hit", "base", "excess", "lo", "hi", "positive")}
        result.update(scores)
        enough = min(scores["candidate"]["calls"] or 0, scores["in_use"]["calls"] or 0) >= min_calls
        if not enough:
            action = "pending"
        elif scores["candidate"]["excess"] > scores["in_use"]["excess"]:
            action = "adopt"
        else:
            action = "keep"
        self.log("judge", verdict=action, **result)
        result["action"] = action
        if action == "adopt":
            self.log("adopt", version=candidate, replaces=current, weeks_from=str(start.date()))
        return result
