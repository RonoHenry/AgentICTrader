"""
Tests for the Thesis Engine's V5 (thesis-engine Requirement 21; task 430): V1 in ICT's London window, 02:00-04:00 New
York, a hand completing only inside it. V1 to V4 stay byte for byte as they were.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import replace

import pandas as pd
import pytest

from tests.thesis_engine_walks import mirrored, walk_m1
from thesis_engine.clock import trading_day
from thesis_engine.records import Thesis
from thesis_engine.replay import prepare, run
from thesis_engine.settings import V1, V2, V3, V4, V5
from thesis_engine.thesis import research_theses

#: The older versions' journals with the week's real side, recorded before V5 existed (commit 4100a4e's code).
V1_WALK_21 = "ead552c81db4ae0de20e9929902549d1f49df74f"
V2_WALK_8 = "f5ef12697c2c0d31a20312e15fb8eba89397204c"
V3_WALK_8 = "bb655f219864c96709b1d8913f9af71ec537bcf6"
V4_WALK_3 = "f806378f40d8f0995f6c54723440f1054ffbe6bd"
FIVE = 5 * 60 * 10**9


def _sha(j) -> str:
    return hashlib.sha1("\n".join(j.lines()).encode()).hexdigest()


def _opens_in_window(t_close: int) -> bool:
    """Whether the M5 candle closing at ``t_close`` opened between 02:00 and 04:00 New York."""
    local = pd.Timestamp(t_close - FIVE, tz="UTC").tz_convert("America/New_York")
    return 2 <= local.hour + local.minute / 60 < 4


@pytest.fixture(scope="module")
def walked():
    mk = prepare("EURUSD", walk_m1(14, seed=8, step=0.0003, spread=0.00003), V5)
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE", s=V5)
    return mk, theses, run(mk, theses, V5)


def test_v1_to_v4_are_unchanged():
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
    mk = prepare("EURUSD", walk_m1(20, seed=3, step=0.0003, spread=0.00003), V4)
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    assert _sha(run(mk, theses, V4)) == V4_WALK_3


def test_v5_arms_sweeps_and_enters_only_in_the_london_window(walked):
    _, _, j = walked
    armed = [r for r in j.of("transition") if r["to"] == "ARMED"]
    sweeps = [r for r in j.of("note") if r["note"] == "sweep"]
    intents = j.of("intent")
    assert armed and sweeps and len(intents) >= 5
    assert all(_opens_in_window(r["t"]) for r in armed + sweeps)
    assert all(_opens_in_window(i["at"]) for i in intents)


def test_a_hand_still_waiting_when_the_window_closes_ends(walked):
    _, _, j = walked
    ended = [r for r in j.of("note") if r["note"] == "hand_failed" and r["why"] == "the window closed before the CISD"]
    assert ended
    for r in ended:
        local = pd.Timestamp(r["t"] - FIVE, tz="UTC").tz_convert("America/New_York")
        assert (local.hour, local.minute) == (4, 0)                    # the first candle after the window
    moves = {r["t"]: r for r in j.of("transition")}
    assert all(moves[r["t"]]["to"] == "AT_LEVEL" for r in ended)


def test_the_rest_is_v1(walked):
    mk, theses, j = walked
    assert V5.window == (2, 4) and V5.entry_in_window
    assert {k: v for k, v in vars(V5).items() if k not in ("version", "window", "entry_in_window")} == \
        {k: v for k, v in vars(V1).items() if k not in ("version", "window", "entry_in_window")}
    assert {i["kind"] for i in j.of("intent")} == {"MARKET"}


def test_the_budget_counts_fills_only(walked):
    _, _, j = walked
    fills = [r for r in j.of("fill") if r["event"] == "FILLED"]
    days = Counter(int(trading_day(r["t"], "EURUSD")[0]) for r in fills)
    assert fills and max(days.values()) <= 1


def _mirror(m1, s):
    up, down = prepare("EURUSD", m1, s), prepare("EURUSD", mirrored(m1), s)
    theses, _ = research_theses("EURUSD", up.book, "ORACLE", s=s)
    flipped = [Thesis(th.market, "BEARISH" if th.bullish else "BULLISH", -th.draw, -th.protected, th.since, th.until,
                      th.source) for th in theses]
    a, b = run(up, theses, s), run(down, flipped, s)
    moves = lambda jj: [(r["t"], r["frm"], r["to"]) for r in jj.of("transition")]          # noqa: E731
    return a, b, moves(a) == moves(b)


def test_the_mirror():
    # Where no two levels tie: V5 keeps V1's tie-break by the array's content id, which a mirror doesn't keep
    # (V1's own mirror test uses such a walk too).
    a, b, same = _mirror(walk_m1(20, seed=5, step=0.0003, spread=0.0), V5)
    assert a.of("intent") and same
    assert [round(t["net_r"], 9) for t in a.of("trade")] == [round(t["net_r"], 9) for t in b.of("trade")]


def test_v1s_tie_break_is_the_only_asymmetry():
    m1 = walk_m1(14, seed=8, step=0.0003, spread=0.0)
    assert not _mirror(m1, V5)[2]
    assert _mirror(m1, replace(V5, level_tiebreak="FRAME"))[2]
