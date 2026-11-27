"""
Tests for algo_mind/brain.py — the brain and its versions (algo-mind Requirement 2, task 382).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from algo_mind.brain import fit_version, load_version
from algo_research.search_state import FEATURES


def table(n=1200, seed=0):
    """Two markets' weekly states: random features, the week's direction leaning on one of them."""
    rng = np.random.default_rng(seed)
    t = pd.DataFrame(rng.normal(size=(n, len(FEATURES))), columns=list(FEATURES))
    t["market"] = np.where(np.arange(n) % 2, "AAA", "BBB")
    t["week"] = pd.Timestamp("2005-01-03") + pd.to_timedelta((np.arange(n) // 2) * 7, unit="D")
    t["up"] = np.where(rng.normal(size=n) + 0.6 * t["W1_body"] > 0, 1.0, -1.0)
    return t


def test_a_version_is_reproducible_and_keeps_its_thirds_and_meta(tmp_path):
    t = table()
    a = fit_version(t, end=pd.Timestamp("2020-01-01"), version="va", root=tmp_path)
    b = fit_version(t, end=pd.Timestamp("2020-01-01"), version="vb", root=tmp_path)
    fit = t[t["week"] < "2020-01-01"]
    assert np.allclose(a.probability(fit), b.probability(fit))
    p = a.probability(fit)
    assert np.isclose(a.lo, np.quantile(p, 1 / 3)) and np.isclose(a.hi, np.quantile(p, 2 / 3))
    calls = a.call(fit)["call"]
    assert abs((calls == 1).mean() - 1 / 3) < 0.03 and abs((calls == -1).mean() - 1 / 3) < 0.03
    meta = json.loads((tmp_path / "va" / "meta.json").read_text(encoding="utf-8"))
    assert meta["train_end"] == "2020-01-01" and meta["weeks"] == len(fit[fit["up"] != 0])
    assert meta["features"] == list(FEATURES) and meta["thresholds"] == [a.lo, a.hi]
    assert {"settings", "commit", "fitted_at"} <= set(meta)


def test_a_loaded_version_predicts_as_the_fitted_one(tmp_path):
    t = table(seed=1)
    fitted = fit_version(t, end=pd.Timestamp("2020-01-01"), version="v1", root=tmp_path)
    loaded = load_version("v1", root=tmp_path)
    later = t[t["week"] >= "2010-01-01"]
    assert np.allclose(fitted.probability(later), loaded.probability(later))
    assert (loaded.train["week"] < "2020-01-01").all() and len(loaded.train) == fitted.meta["weeks"]
    assert loaded.call(later)["call"].isin([1, 0, -1]).all()
