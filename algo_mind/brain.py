"""Algo Mind's brain (algo-mind Requirement 2): H-Y's model, settings unchanged, fitted on every permitted week and
kept as a version.

A version is a folder under ``data/algo_mind/models/<version>/``:
- ``model.pkl``: the fitted model;
- ``meta.json``: the training window and weeks, the features and settings, the thresholds (the 33rd and 67th
  percentiles of its training probabilities) and the code's commit;
- ``train.parquet``: its training weeks (market, week, direction and features), which memory draws its analogs
  from.

    brain = fit_version(table)              # every week before 2023-01-01
    brain = load_version("v1")
    brain.call(states)                      # p (probability of an up week) and call (+1, -1 or 0)
"""
from __future__ import annotations

import json
import pickle
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from algo_research.search_state import FEATURES, MODEL, _weights

__all__ = ["FIT_END", "MODELS", "Brain", "fit_version", "load_version"]

REPO = Path(__file__).resolve().parents[1]
MODELS = REPO / "data" / "algo_mind" / "models"
#: The search's test window starts here: the brain never reads it (AM-D1).
FIT_END = pd.Timestamp("2023-01-01")


@dataclass
class Brain:
    model: object
    lo: float
    hi: float
    meta: dict
    train: pd.DataFrame = field(repr=False)

    def probability(self, states: pd.DataFrame) -> np.ndarray:
        """The probability of an up week for each state."""
        return self.model.predict_proba(states[list(FEATURES)].to_numpy(float))[:, 1]

    def call(self, states: pd.DataFrame) -> pd.DataFrame:
        """``states`` with ``p`` and ``call``: +1 in the training probabilities' top third, -1 in the bottom, 0
        between (Requirement 2.3)."""
        p = self.probability(states)
        return states.assign(p=p, call=np.where(p >= self.hi, 1, np.where(p <= self.lo, -1, 0)))


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def fit_version(table: pd.DataFrame, end: pd.Timestamp = FIT_END, version: str = "v1", root: Path = MODELS) -> Brain:
    """Fit the brain on ``table``'s weeks before ``end`` with a direction, and keep it as ``version``."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    fit = table[(table["week"] < end) & (table["up"] != 0)].reset_index(drop=True)
    x, y = fit[list(FEATURES)].to_numpy(float), (fit["up"] > 0).astype(int).to_numpy()
    model = HistGradientBoostingClassifier(**MODEL)
    model.fit(x, y, sample_weight=_weights(fit))
    p = model.predict_proba(x)[:, 1]
    lo, hi = (float(v) for v in np.quantile(p, [1 / 3, 2 / 3]))
    meta = {"version": version, "train_start": str(fit["week"].min().date()), "train_end": str(pd.Timestamp(end).date()),
            "weeks": len(fit), "markets": sorted(fit["market"].unique()), "features": list(FEATURES),
            "settings": MODEL, "thresholds": [lo, hi], "commit": _commit(),
            "fitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    train = fit[["market", "week", "up", *FEATURES]]
    out = Path(root) / version
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.pkl").write_bytes(pickle.dumps(model))
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    train.to_parquet(out / "train.parquet", index=False)
    return Brain(model, lo, hi, meta, train)


def load_version(version: str = "v1", root: Path = MODELS) -> Brain:
    """A kept version. Its model is a pickle this code wrote; nothing else is loaded this way."""
    folder = Path(root) / version
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    model = pickle.loads((folder / "model.pkl").read_bytes())
    lo, hi = meta["thresholds"]
    return Brain(model, float(lo), float(hi), meta, pd.read_parquet(folder / "train.parquet"))
