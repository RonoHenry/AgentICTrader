"""
Tests for the Thesis Engine's V3 (thesis-engine Requirement 17; task 422): the execution frames from M1, each pool's
child frame with the M30 and M15 swings as pools, a larger pool taking a waiting hand over, the CISD and its
displacement on the child, and the entry at market near the run's MT or as a limit at it. V1 and V2 stay byte for
byte as they were.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import replace

import numpy as np
import pytest

from liquidity_engine.context.measures import swing_highs, swing_lows
from tests.thesis_engine_walks import mirrored, walk_m1
from thesis_engine.clock import clean, frames, trading_day
from thesis_engine.records import Thesis
from thesis_engine.replay import prepare, run
from thesis_engine.settings import MINUTES, V1, V2, V3
from thesis_engine.thesis import research_theses

#: V1's and V2's journals with the week's real side, recorded before V3 existed (commit 3ef61a3's code).
V1_WALK_21 = "ead552c81db4ae0de20e9929902549d1f49df74f"
V2_WALK_8 = "f5ef12697c2c0d31a20312e15fb8eba89397204c"
MIN = 60 * 10**9


def _sha(j) -> str:
    return hashlib.sha1("\n".join(j.lines()).encode()).hexdigest()


@pytest.fixture(scope="module")
def walked():
    mk = prepare("EURUSD", walk_m1(14, seed=8, step=0.0003), V3)
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE", s=V3)
    return mk, theses, run(mk, theses, V3)


def test_v1_and_v2_are_unchanged():
    mk = prepare("EURUSD", walk_m1(10, seed=21))
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    assert _sha(run(mk, theses, V1)) == V1_WALK_21
    mk = prepare("EURUSD", walk_m1(14, seed=8, step=0.0003))
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    assert _sha(run(mk, theses, V2)) == V2_WALK_8


def test_the_execution_frames_come_from_m1():
    bars, _ = clean(walk_m1(1, seed=3))
    fr = frames(bars, "EURUSD", V3)
    assert set(fr) == {"W1", "D1", "H4", "H1", "M30", "M20", "M15", "M10", "M5", "M3", "M1"}
    m1 = fr["M1"]
    for tf in ("M30", "M20", "M15", "M10", "M3"):
        c, n = fr[tf], MINUTES[tf] * MIN
        assert (c.t % n == 0).all() and (c.end - c.t == n).all()
        for k in (0, len(c) // 2, len(c) - 1):
            inside = (m1.t >= c.t[k]) & (m1.end <= c.end[k])
            assert c.o[k] == m1.o[inside][0] and c.c[k] == m1.c[inside][-1]
            assert c.h[k] == m1.h[inside].max() and c.l[k] == m1.l[inside].min()
    assert set(frames(bars, "EURUSD", V2)) == {"W1", "D1", "H4", "H1", "M5"}


def test_each_pool_has_its_child_frame():
    assert {tf: V3.child(tf) for tf in ("D1", "ASIA", "H4", "H1", "M30", "M15")} == {
        "D1": "M30", "ASIA": "M30", "H4": "M20", "H1": "M5", "M30": "M3", "M15": "M1"}


def test_m30_and_m15_swings_are_taken_at_the_minute(walked):
    mk, _, _ = walked
    book, e = mk.book, mk.book.e
    for tf in ("M30", "M15"):
        c = book.x[tf]
        for lows in (True, False):
            x = c.l if lows else c.h
            at = {}
            for i in (swing_lows if lows else swing_highs)(x, 2):
                at.setdefault(float(x[i]), []).append(i)
            takers = book._swing_takers[tf][lows]
            assert takers
            for m, prices in takers.items():
                for p in prices:
                    i = max(i for i in at[p] if c.end[i + 2] <= e.t[m])         # the swing it was, known by then
                    a = int(np.searchsorted(e.t, c.end[i + 2], "left"))
                    assert (e.l[m] < p) if lows else (e.h[m] > p)
                    assert (e.l[a:m] >= p).all() if lows else (e.h[a:m] <= p).all()


def test_each_hand_runs_on_its_pools_child_and_a_larger_pool_takes_it_over(walked):
    _, _, j = walked
    sweeps = [r for r in j.of("note") if r["note"] == "sweep"]
    assert sweeps and all(r["frame"] == V3.child(r["pool_tf"]) for r in sweeps)
    assert len({r["frame"] for r in sweeps}) >= 3
    over = [(a, b) for a, b in zip(sweeps, sweeps[1:]) if b["took_over"] is not None]
    assert over
    for before, after in over:
        assert after["took_over"] == before["pool"] and MINUTES[after["pool_tf"]] > MINUTES[before["pool_tf"]]


def test_the_cisd_and_its_displacement_are_on_the_child(walked):
    mk, theses, j = walked
    book = mk.book
    hands = [r for r in j.of("note") if r["note"] == "hand"]
    assert hands
    side = {th.id: th.bullish for th in theses}
    for r, intent in zip(hands, j.of("intent")):
        tf, k, k0, bull = r["frame"], r["k"], r["k0"], side[intent["thesis_id"]]
        x = book.x[tf]
        first, last = book.x_cisd(tf, k, bull, k0)
        assert last >= k0 - 1 and 0 <= k - k0 <= 12
        assert (x.c[k] > x.o[first]) if bull else (x.c[k] < x.o[first])
        assert abs(x.c[k] - x.o[k]) >= 1.5 * book.x_reach(tf, k) - 1e-12


def test_the_entry_is_at_market_near_the_mt_and_a_limit_away_from_it(walked):
    mk, theses, j = walked
    hands = [r for r in j.of("note") if r["note"] == "hand"]
    for r, intent in zip(hands, j.of("intent")):
        assert intent["kind"] == r["kind"] == ("MARKET" if r["away"] <= V3.near_mt else "LIMIT")
    for near, kind in ((99.0, "MARKET"), (0.0, "LIMIT")):
        jj = run(mk, theses, replace(V3, near_mt=near))
        assert jj.of("intent") and {i["kind"] for i in jj.of("intent")} == {kind}
        for r, intent in zip([r for r in jj.of("note") if r["note"] == "hand"], jj.of("intent")):
            x, book = mk.book.x[r["frame"]], mk.book
            if kind == "LIMIT":
                first, last = book.x_cisd(r["frame"], r["k"], intent["side"] == "BULLISH", r["k0"])
                assert intent["entry"] == pytest.approx(book.x_run_mt(r["frame"], first, last))
            else:
                buy = intent["side"] == "BULLISH"
                assert intent["entry"] == pytest.approx(x.c[r["k"]] + (mk.typical_spread if buy else 0.0))


def test_the_runner_counts_the_hands_by_frame(walked):
    from thesis_engine.hai import by_frame
    _, _, j = walked
    got, notes = by_frame(j), j.of("note")
    assert sum(v for k, v in got.items() if k.startswith("sweeps: ")) == sum(r["note"] == "sweep" for r in notes)
    assert sum(v for k, v in got.items() if k.startswith("orders: ")) == len(j.of("intent")) > 0
    assert got["takeovers"] == sum(r["note"] == "sweep" and r["took_over"] is not None for r in notes) > 0


def test_the_budget_counts_fills_only(walked):
    _, _, j = walked
    fills = [r for r in j.of("fill") if r["event"] == "FILLED"]
    days = Counter(int(trading_day(r["t"], "EURUSD")[0]) for r in fills)
    assert max(days.values(), default=0) <= 1


def test_the_mirror():
    m1 = walk_m1(14, seed=8, step=0.0003, spread=0.0)
    up, down = prepare("EURUSD", m1, V3), prepare("EURUSD", mirrored(m1), V3)
    theses, _ = research_theses("EURUSD", up.book, "ORACLE", s=V3)
    flipped = [Thesis(th.market, "BEARISH" if th.bullish else "BULLISH", -th.draw, -th.protected, th.since, th.until,
                      th.source) for th in theses]
    a, b = run(up, theses, V3), run(down, flipped, V3)
    moves = lambda jj: [(r["t"], r["frm"], r["to"]) for r in jj.of("transition")]          # noqa: E731
    assert a.of("intent") and moves(a) == moves(b)
    assert [round(t["net_r"], 9) for t in a.of("trade")] == [round(t["net_r"], 9) for t in b.of("trade")]
