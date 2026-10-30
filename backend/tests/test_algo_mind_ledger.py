"""
Tests for algo_mind/ledger.py — learning without fooling itself (algo-mind Requirement 7.1-7.2, task 388).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_mind.brain import fit_version
from algo_mind.ledger import Ledger
from algo_research.search_state import FEATURES


def table(n=2400, seed=0, lean=0.8):
    rng = np.random.default_rng(seed)
    t = pd.DataFrame(rng.normal(size=(n, len(FEATURES))), columns=list(FEATURES))
    t["market"] = np.where(np.arange(n) % 2, "AAA", "BBB")
    t["week"] = pd.Timestamp("2000-01-03") + pd.to_timedelta((np.arange(n) // 2) * 7, unit="D")
    t["up"] = np.where(rng.normal(size=n) + lean * t["W1_body"] > 0, 1.0, -1.0)
    return t


def test_the_version_in_use_is_v1_until_a_candidate_wins_on_later_weeks(tmp_path):
    t = table()
    models = tmp_path / "models"
    ledger = Ledger(tmp_path / "ledger.jsonl", models)
    assert ledger.in_use() == "v1"
    fit_version(t.assign(up=np.where(np.random.default_rng(9).normal(size=len(t)) > 0, 1.0, -1.0)),
                end=pd.Timestamp("2010-01-01"), version="v1", root=models)        # v1 learned nothing
    ledger.log("fit", version="v1", train_end="2010-01-01")
    fit_version(t, end=pd.Timestamp("2015-01-01"), version="v2", root=models)     # v2 learned the lean
    ledger.log("fit", version="v2", train_end="2015-01-01")
    verdict = ledger.judge("v2", t, min_calls=100)
    assert verdict["action"] == "adopt" and verdict["weeks_from"] == "2015-01-01"
    assert verdict["candidate"]["excess"] > verdict["in_use"]["excess"]
    assert ledger.in_use() == "v2"
    entries = ledger.entries()
    assert [e["action"] for e in entries] == ["fit", "fit", "judge", "adopt"]
    assert entries[2]["candidate_version"] == "v2" and entries[2]["verdict"] == "adopt"
    assert ledger.candidates() == ["v1"]                     # v2 in use: v1 rides beside it


def test_a_candidate_that_doesnt_win_or_hasnt_enough_weeks_is_not_adopted(tmp_path):
    t = table(seed=1)
    models = tmp_path / "models"
    ledger = Ledger(tmp_path / "ledger.jsonl", models)
    fit_version(t, end=pd.Timestamp("2010-01-01"), version="v1", root=models)
    noise = t.assign(up=np.where(np.random.default_rng(5).normal(size=len(t)) > 0, 1.0, -1.0))
    fit_version(noise, end=pd.Timestamp("2015-01-01"), version="v2", root=models)
    assert ledger.judge("v2", t, min_calls=100)["action"] == "keep" and ledger.in_use() == "v1"
    fit_version(t, end=pd.Timestamp("2022-12-01"), version="v3", root=models)
    assert ledger.judge("v3", t, min_calls=100)["action"] == "pending" and ledger.in_use() == "v1"
