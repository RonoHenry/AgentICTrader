"""
Tests for the Thesis Engine's V2 (thesis-engine Requirement 15; task 419): the trader's pools, a displacement, a limit
at the CISD run's mean threshold with its expiry, and the stack as a gate. V1 stays byte for byte as it was.
"""
from __future__ import annotations

import hashlib
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from liquidity_engine.context.measures import average_range
from tests.thesis_engine_walks import mirrored, walk_m1
from thesis_engine.clock import trading_day
from thesis_engine.records import Thesis
from thesis_engine.replay import _limit_expiry, prepare, run
from thesis_engine.settings import V1, V2
from thesis_engine.thesis import research_theses

#: V1's journal on this walk with the week's real side, recorded before V2 existed (commit dc5d45e's code).
V1_WALK_21 = "ead552c81db4ae0de20e9929902549d1f49df74f"


@pytest.fixture(scope="module")
def walked():
    mk = prepare("EURUSD", walk_m1(14, seed=8, step=0.0003))
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE", s=V2)
    return mk, theses, run(mk, theses, V2)


def test_v1_is_unchanged():
    mk = prepare("EURUSD", walk_m1(10, seed=21))
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    assert hashlib.sha1("\n".join(run(mk, theses, V1).lines()).encode()).hexdigest() == V1_WALK_21


def test_v2_trades(walked):
    _, _, j = walked
    assert j.of("intent") and j.of("trade"), Counter(r["note"] for r in j.of("note"))


def test_only_the_traders_pools_are_swept(walked):
    _, _, j = walked
    pools = [r["pool"] for r in j.of("note") if r["note"] == "sweep"]
    assert pools and not any("M5 swing" in p for p in pools)
    assert {p.split(" ")[1] for p in pools} <= {"previous", "Asia", "H1"}


def test_every_entry_displaces(walked):
    mk, _, j = walked
    e = mk.book.e
    for intent in j.of("intent"):
        m = int(np.searchsorted(e.end, intent["at"], "left"))
        assert abs(e.c[m] - e.o[m]) >= 1.5 * average_range(e.h, e.l, m, 20) - 1e-12


def test_entries_are_limits_at_the_runs_mt_and_expire(walked):
    mk, _, j = walked
    e = mk.book.e
    for intent in j.of("intent"):
        assert intent["kind"] == "LIMIT"
        m = int(np.searchsorted(e.end, intent["at"], "left"))
        first, last = mk.book.cisd(m, intent["side"] == "BULLISH", 0)
        assert intent["entry"] == pytest.approx(mk.book.run_mt(first, last))
    events = Counter(r["event"] for r in j.of("fill"))
    assert events["FILLED"] == len(j.of("trade"))
    expired = [r for r in j.of("transition") if r["reason"] == "the limit expired unfilled"]
    assert len(expired) == events["EXPIRED"] and all(r["frm"] == "IN_TRADE" and r["to"] == "AT_LEVEL" for r in expired)


def test_a_limit_expires_at_the_windows_end_an_hour_on_or_the_theses_end():
    ny = lambda s: int(pd.Timestamp(s, tz="America/New_York").tz_convert("UTC").value)   # noqa: E731
    week = ny("2022-01-07 17:00")
    assert _limit_expiry(ny("2022-01-05 03:00"), week, V2) == ny("2022-01-05 12:00")
    assert _limit_expiry(ny("2022-01-05 11:30"), week, V2) == ny("2022-01-05 12:30")
    assert _limit_expiry(ny("2022-01-05 03:00"), ny("2022-01-05 09:00"), V2) == ny("2022-01-05 09:00")


def test_the_budget_counts_fills_only(walked):
    _, _, j = walked
    fills = [r for r in j.of("fill") if r["event"] == "FILLED"]
    days = Counter(int(trading_day(r["t"], "EURUSD")[0]) for r in fills)
    assert max(days.values(), default=0) <= 1


def test_the_stack_is_a_gate(walked):
    _, _, j = walked
    levels = [r for r in j.of("note") if r["note"] == "level"]
    assert levels
    for lv in levels:
        frames = lv["reasons"][0].split(" ")[0].split("+")
        assert len(frames) >= 2 or lv["tf"] == "D1", lv


def test_the_mirror():
    m1 = walk_m1(14, seed=8, step=0.00018, spread=0.0)
    up, down = prepare("EURUSD", m1), prepare("EURUSD", mirrored(m1))
    theses, _ = research_theses("EURUSD", up.book, "ORACLE", s=V2)
    flipped = [Thesis(th.market, "BEARISH" if th.bullish else "BULLISH", -th.draw, -th.protected, th.since, th.until,
                      th.source) for th in theses]
    a, b = run(up, theses, V2), run(down, flipped, V2)
    moves = lambda jj: [(r["t"], r["frm"], r["to"]) for r in jj.of("transition")]          # noqa: E731
    assert a.of("intent") and moves(a) == moves(b)
    assert [round(t["net_r"], 9) for t in a.of("trade")] == [round(t["net_r"], 9) for t in b.of("trade")]
