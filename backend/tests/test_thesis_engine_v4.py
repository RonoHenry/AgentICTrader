"""
Tests for the Thesis Engine's V4 (thesis-engine Requirement 19; task 426): setups only on M30 and M15 by the pool's
size, the setup placing no order, the pull-back into its order block and the M3 or M1 CISD that enters at market, the
stop at the setup's sweep, and the setup's failure and expiry. V1, V2 and V3 stay byte for byte as they were.
"""
from __future__ import annotations

import hashlib
from collections import Counter

import numpy as np
import pytest

from tests.thesis_engine_walks import mirrored, walk_m1
from thesis_engine.clock import trading_day
from thesis_engine.records import Thesis
from thesis_engine.replay import prepare, run
from thesis_engine.settings import V1, V2, V3, V4
from thesis_engine.thesis import research_theses

#: The older versions' journals with the week's real side, recorded before V4 existed (commit 959c2cc's code).
V1_WALK_21 = "ead552c81db4ae0de20e9929902549d1f49df74f"
V2_WALK_8 = "f5ef12697c2c0d31a20312e15fb8eba89397204c"
V3_WALK_8 = "bb655f219864c96709b1d8913f9af71ec537bcf6"
SETUP_FRAME = {"D1": "M30", "ASIA": "M30", "H4": "M30", "H1": "M15"}
SPREAD = 0.00003


def _sha(j) -> str:
    return hashlib.sha1("\n".join(j.lines()).encode()).hexdigest()


@pytest.fixture(scope="module")
def walked():
    mk = prepare("EURUSD", walk_m1(20, seed=3, step=0.0003, spread=SPREAD), V4)
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE", s=V4)
    return mk, theses, run(mk, theses, V4)


def _notes(j, what):
    return [r for r in j.of("note") if r["note"] == what]


def test_v1_v2_and_v3_are_unchanged():
    mk = prepare("EURUSD", walk_m1(10, seed=21))
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    assert _sha(run(mk, theses, V1)) == V1_WALK_21
    m1 = walk_m1(14, seed=8, step=0.0003)
    mk = prepare("EURUSD", m1)
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    assert _sha(run(mk, theses, V2)) == V2_WALK_8
    mk = prepare("EURUSD", m1, V3)
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    assert _sha(run(mk, theses, V3)) == V3_WALK_8


def test_setups_live_on_m30_and_m15_by_the_pools_size(walked):
    mk, _, j = walked
    assert {"M30", "M15", "M3", "M1"} <= set(mk.book.x)
    sweeps = _notes(j, "sweep")
    assert sweeps and all(r["pool_tf"] in SETUP_FRAME for r in sweeps)               # no M30 or M15 swing pools
    assert all(r["frame"] == SETUP_FRAME[r["pool_tf"]] for r in sweeps)
    setups = _notes(j, "setup")
    assert {r["frame"] for r in setups} == {"M30", "M15"}
    assert all(r["refine"] == {"M30": "M3", "M15": "M1"}[r["frame"]] for r in setups)


def test_a_setup_places_no_order_and_each_entry_follows_a_setup_and_its_pull_back(walked):
    _, _, j = walked
    setups, intents = _notes(j, "setup"), j.of("intent")
    assert intents and len(setups) > len(intents)
    placed = {i["at"] for i in intents}
    assert not any(r["t"] in placed for r in setups)
    for i in intents:
        before = [r for r in j.of("note") if r["t"] <= i["at"] and r["note"] in ("setup", "pullback")]
        assert [r["note"] for r in before[-2:]] == ["setup", "pullback"]


def test_the_refined_entry_is_a_market_order_on_the_lower_frames_cisd_inside_the_order_block(walked):
    mk, theses, j = walked
    book, e = mk.book, mk.book.e
    side = {th.id: th.bullish for th in theses}
    for h, i in zip(_notes(j, "hand"), j.of("intent")):
        bull = side[i["thesis_id"]]
        setup = [r for r in _notes(j, "setup") if r["t"] <= i["at"]][-1]
        pull = [r for r in _notes(j, "pullback") if r["t"] <= i["at"]][-1]
        assert i["kind"] == "MARKET" and h["refine"] == setup["refine"] and h["frame"] == setup["frame"]
        m = int(np.searchsorted(e.end, pull["t"], "left"))
        assert (e.l[m] <= setup["zone_high"]) if bull else (e.h[m] >= setup["zone_low"])     # back in the block
        x, k = book.x[h["refine"]], h["k"]
        touched = book.x_at(h["refine"], m)
        first, last = book.x_cisd(h["refine"], k, bull, touched)
        assert k >= touched and last >= touched - 1
        assert (x.c[k] > x.o[first]) if bull else (x.c[k] < x.o[first])
        assert i["entry"] == pytest.approx(x.c[k] + (SPREAD if bull else 0.0))
        assert i["stop"] == pytest.approx(setup["extreme"] + (0.0 if bull else SPREAD))   # beyond the setup's sweep


def test_a_setup_fails_beyond_its_sweep_and_expires_with_its_time(walked):
    mk, theses, j = walked
    e = mk.book.e
    failed, expired = _notes(j, "setup_failed"), _notes(j, "setup_expired")
    assert failed and expired
    setups = _notes(j, "setup")
    bull = {th.id: th.bullish for th in theses}
    moves = j.of("transition")
    for r in failed:
        setup = [s for s in setups if s["t"] < r["t"]][-1]
        th = [mv for mv in moves if mv["t"] <= r["t"] and mv["thesis_id"]][-1]["thesis_id"]
        m = int(np.searchsorted(e.end, r["t"], "left"))
        assert (e.l[m] < setup["extreme"]) if bull[th] else (e.h[m] > setup["extreme"])
    for r in expired:
        setup = [s for s in setups if s["t"] < r["t"]][-1]
        assert r["t"] >= setup["until"]


def test_the_runner_counts_the_hands_by_frame(walked):
    from thesis_engine.haj import by_frame
    _, _, j = walked
    got = by_frame(j)
    assert sum(v for k, v in got.items() if k.startswith("setups: ")) == len(_notes(j, "setup")) > 0
    assert sum(v for k, v in got.items() if k.startswith("entries: ")) == len(j.of("intent")) > 0
    assert sum(v for k, v in got.items() if k.startswith("expired")) == len(_notes(j, "setup_expired")) > 0


def test_the_budget_counts_fills_only(walked):
    _, _, j = walked
    fills = [r for r in j.of("fill") if r["event"] == "FILLED"]
    days = Counter(int(trading_day(r["t"], "EURUSD")[0]) for r in fills)
    assert fills and max(days.values()) <= 1


def test_the_mirror():
    m1 = walk_m1(20, seed=3, step=0.0003, spread=0.0)
    up, down = prepare("EURUSD", m1, V4), prepare("EURUSD", mirrored(m1), V4)
    theses, _ = research_theses("EURUSD", up.book, "ORACLE", s=V4)
    flipped = [Thesis(th.market, "BEARISH" if th.bullish else "BULLISH", -th.draw, -th.protected, th.since, th.until,
                      th.source) for th in theses]
    a, b = run(up, theses, V4), run(down, flipped, V4)
    moves = lambda jj: [(r["t"], r["frm"], r["to"]) for r in jj.of("transition")]          # noqa: E731
    assert a.of("intent") and moves(a) == moves(b)
    assert [round(t["net_r"], 9) for t in a.of("trade")] == [round(t["net_r"], 9) for t in b.of("trade")]
