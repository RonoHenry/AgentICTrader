"""
Tests for the Thesis Engine's management settings (thesis-engine Requirement 23; task 438), on random walks: V1 to V5
stay byte for byte the same, and each setting does what H-AN registered.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import replace

import pandas as pd
import pytest

from tests.thesis_engine_walks import walk_m1
from thesis_engine.replay import day_end, prepare, run
from thesis_engine.settings import V1, V5
from thesis_engine.thesis import research_theses

#: V5's journal with the week's real side, recorded before Requirement 23's code (V1 to V4: test_thesis_engine_v5).
V5_WALK_8 = "3a2bb75af9d1c37a4cf1be881ca307d36079f829"
NY = "America/New_York"


def _ns(local: str) -> int:
    return int(pd.Timestamp(local, tz=NY).tz_convert("UTC").value)


def _r(t: dict, price: float) -> float:
    """``price`` in R from the trade's fill, against its planned stop."""
    long_ = t["direction"] == "LONG"
    risk = t["fill"] - t["stop"] if long_ else t["stop"] - t["fill"]
    return ((price - t["fill"]) if long_ else (t["fill"] - price)) / risk


@pytest.fixture(scope="module")
def walked():
    mk = prepare("EURUSD", walk_m1(14, seed=5, step=0.0003, spread=0.00003))
    return mk, {arm: research_theses("EURUSD", mk.book, arm)[0] for arm in ("ORACLE", "MIRROR")}


def _trades(walked, s) -> list[dict]:
    mk, by_arm = walked
    return [t for theses in by_arm.values() for t in run(mk, theses, s).of("trade")]


def test_v5_is_unchanged():
    mk = prepare("EURUSD", walk_m1(14, seed=8, step=0.0003, spread=0.00003), V5)
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE", s=V5)
    assert hashlib.sha1("\n".join(run(mk, theses, V5).lines()).encode()).hexdigest() == V5_WALK_8


def test_the_trading_day_ends_at_the_next_open_hour_in_new_york():
    assert day_end(_ns("2026-03-04 10:00"), 17) == _ns("2026-03-04 17:00")
    assert day_end(_ns("2026-03-04 17:00"), 17) == _ns("2026-03-05 17:00")
    assert day_end(_ns("2026-03-04 17:30"), 18) == _ns("2026-03-04 18:00")
    assert day_end(_ns("2026-03-07 18:00"), 17) == _ns("2026-03-08 17:00")      # the clocks go forward
    assert day_end(_ns("2026-11-01 17:30"), 17) == _ns("2026-11-02 17:00")      # and back
    assert day_end(_ns("2026-11-01 00:30"), 17) == _ns("2026-11-01 17:00")


def test_a_cap_brings_a_far_draw_to_that_many_r(walked):
    mk, by_arm = walked
    capped = 0
    for theses in by_arm.values():
        j = run(mk, theses, replace(V1, version="cap3", target_cap_r=3.0))
        draws = {th["id"]: th["draw"] for th in j.of("thesis")}
        for it in j.of("intent"):
            risk = abs(it["entry"] - it["stop"])
            assert abs(it["target"] - it["entry"]) <= 3.0 * risk * (1 + 1e-9)
            capped += it["target"] != draws[it["thesis_id"]]
        assert all(t["net_r"] <= 3.5 for t in j.of("trade"))
    assert capped > 0


def test_break_even_moves_the_stop_to_the_fill_at_one_r(walked):
    trades = _trades(walked, replace(V1, version="be1", partial_r=1.0))
    reached = [t for t in trades if _r(t, t["mfe"]) >= 1.0]
    assert reached and all(t["partial_at"] is not None for t in reached)
    assert all(t["net_r"] > -0.2 for t in reached)                   # at worst the spread, never the full stop
    assert all(t["net_r"] <= -0.9 or t["reason"] != "SL" for t in trades if t["partial_at"] is None)


def test_a_partial_banks_a_third_at_two_r(walked):
    trades = _trades(walked, replace(V1, version="p2", partial_r=2.0, partial_fraction=1 / 3))
    banked = [t for t in trades if t["partial_at"] is not None]
    assert banked and all(t["net_r"] >= 2 / 3 - 0.1 for t in banked)


def test_the_day_end_check_closes_every_position_by_the_end_of_its_day(walked):
    trades = _trades(walked, replace(V1, version="day", check_at="DAY_END"))
    assert Counter(t["reason"] for t in trades)["CHECK"] > 0
    for t in trades:
        assert t["closed_at"] < day_end(t["filled_at"], 17)


def test_a_stall_check_closes_only_positions_that_never_reached_one_r(walked):
    hours = 3600 * 10**9                                              # the walk decides most positions within hours
    trades = _trades(walked, replace(V1, version="stall1", check_at="HOURS", check_hours=1.0, check_r=1.0))
    checked = [t for t in trades if t["reason"] == "CHECK"]
    assert checked
    for t in checked:
        assert t["closed_at"] < t["filled_at"] + hours and _r(t, t["mfe"]) < 1.0
    for t in trades:                                                  # past the check only after +1R
        if t["closed_at"] >= t["filled_at"] + hours and t["reason"] in ("SL", "TP", "TIME"):
            assert _r(t, t["mfe"]) >= 1.0


def test_one_entry_a_thesis(walked):
    trades = _trades(walked, replace(V1, version="one", per_thesis=1))
    assert trades and max(Counter(t["thesis_id"] for t in trades).values()) == 1
