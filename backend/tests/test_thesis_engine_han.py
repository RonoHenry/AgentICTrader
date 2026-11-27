"""
Tests for H-AN's runner (thesis-engine Requirement 24; task 438): the bar, the registered pick, and one window end to
end on a random walk. No market data is read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tests.thesis_engine_walks import walk_m1
from thesis_engine import han


def test_the_bar_is_the_side_accuracy_that_breaks_even():
    assert han.bar(1.0, -1.0) == 0.5
    assert abs(han.bar(0.68, -0.80) - 0.80 / 1.48) < 1e-12
    assert han.bar(-0.2, -0.1) == 1.0                         # the right side earns no more than the wrong one


def _tab(rows):
    return pd.DataFrame([{"window": w, "variant": v, "p_week": p, "ORACLE_week": o} for w, v, p, o in rows])


def test_the_pick_needs_every_window_a_positive_oracle_and_two_points_pooled():
    rows = []
    for w, base in (("a", 0.58), ("b", 0.50), ("c", 0.59), ("pooled", 0.56)):
        rows += [(w, "V1", base, 0.7),
                 (w, "GOOD", base - 0.05, 0.6),                 # below everywhere, 5 points pooled
                 (w, "BETTER", base - 0.06, 0.5),
                 (w, "SMALL", base - 0.01, 0.6),                # below everywhere, but 1 point pooled
                 (w, "ONE_WINDOW", base + (0.02 if w == "b" else -0.08), 0.6),
                 (w, "NEGATIVE", base - 0.1, -0.1 if w == "a" else 0.4)]
    chosen, why = han.pick(_tab(rows))
    assert chosen == "BETTER"
    assert why["GOOD"]["qualifies"] and not why["SMALL"]["qualifies"]
    assert not why["ONE_WINDOW"]["qualifies"] and not why["NEGATIVE"]["qualifies"]
    none, _ = han.pick(_tab([r for r in rows if r[1] in ("V1", "SMALL")]))
    assert none is None


def test_one_window_end_to_end(tmp_path, monkeypatch):
    walk_m1(14, seed=5, step=0.0003, spread=0.00003).to_parquet(tmp_path / "EURUSD_M1.parquet")
    monkeypatch.setattr(han, "MARKETS", ("EURUSD",))
    trades, held = han.windows({"walk": (tmp_path, None, 0, None)}, ("V1", "DAY", "ONE"))
    assert set(trades["variant"]) == {"V1", "DAY", "ONE"} and set(held["arm"]) == set(han.ARMS)
    assert (trades[trades["variant"] == "DAY"]["reason"] == "CHECK").any()
    tab = han.table(trades, held)
    assert set(tab["window"]) == {"walk"} and (tab["p_week"] <= 1).all()      # below 0: pays at any side
    v1 = tab.set_index("variant").loc["V1"]
    weeks = held[held["arm"] == "ORACLE"].shape[0]
    assert np.isclose(v1["ORACLE_week"], trades[(trades["variant"] == "V1") & (trades["arm"] == "ORACLE")]
                      ["net_r"].sum() / weeks)
    mw = han._weekly(trades, held, ("V1", "DAY"))
    assert np.isclose(mw["V1_O"].sum(), trades[(trades["variant"] == "V1") & (trades["arm"] == "ORACLE")]
                      ["net_r"].sum())
    one = np.ones((1, len(mw)))
    assert np.isclose(han._bars(one, mw, "V1")[0], v1["p_week"])
    pr = han.paired(mw, "DAY")
    assert pr["lo"] <= pr["hi"]
    pw = han.power(mw, "DAY", 20, np.random.default_rng(0), draws=200)
    assert 0 <= pw["power"] <= 1
