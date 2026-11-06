"""Algo Mind's memory (algo-mind Requirement 3): the training weeks nearest to a state, and what they did.

The state and the training weeks are z-scored on the training weeks' means and spreads; the nearest are by Euclidean
distance, across markets. Memory explains; it doesn't decide.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_state import FEATURES

__all__ = ["K", "analogs"]

K = 20


def analogs(train: pd.DataFrame, state: dict, k: int = K, features=None) -> dict:
    """The ``k`` training weeks nearest to ``state`` on ``features`` (H-Y's by default): their market, week,
    direction and distance, and the share that closed up."""
    features = list(features or FEATURES)
    x = train[features].to_numpy(float)
    mu, sd = x.mean(axis=0), x.std(axis=0)
    sd[sd == 0] = 1.0
    z = (x - mu) / sd
    s = (np.array([float(state[f]) for f in features]) - mu) / sd
    dist = np.sqrt(((z - s) ** 2).sum(axis=1))
    near = np.argsort(dist, kind="stable")[:k]
    rows = train.iloc[near]
    weeks = [{"market": m, "week": pd.Timestamp(w).date().isoformat(), "up": int(u), "distance": round(float(d), 3)}
             for m, w, u, d in zip(rows["market"], rows["week"], rows["up"], dist[near])]
    return {"k": len(weeks), "share_up": float((rows["up"] > 0).mean()) if len(weeks) else None, "weeks": weeks}
