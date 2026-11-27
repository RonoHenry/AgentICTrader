"""
Tests for the Thesis Engine's state machine and replay (thesis-engine Requirements 5-11, Properties 1, 2, 5-8;
tasks 412-413), on random-walk markets with the hindsight side.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from thesis_engine.clock import trading_day
from thesis_engine.machine import TABLE
from thesis_engine.records import Thesis
from thesis_engine.replay import prepare, run
from thesis_engine.thesis import research_theses
from tests.thesis_engine_walks import mirrored, walk_m1


@pytest.fixture(scope="module")
def walked():
    mk = prepare("EURUSD", walk_m1(10, seed=21))
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    return mk, theses, run(mk, theses)


def test_the_machine_runs_through_its_stages(walked):
    _, theses, j = walked
    moves = Counter((r["frm"], r["to"]) for r in j.of("transition"))
    assert theses and moves[("FLAT", "THESIS")] >= len(theses) - 1
    for stage in (("THESIS", "AT_LEVEL"), ("AT_LEVEL", "ARMED"), ("ARMED", "IN_TRADE")):
        assert moves[stage] > 0, f"no {stage} in {dict(moves)}"
    assert j.of("trade")


def test_every_transition_is_a_row_of_the_table(walked):
    _, _, j = walked
    assert {(r["frm"], r["to"]) for r in j.of("transition")} <= TABLE


def test_the_side_is_the_theses_and_never_both(walked):
    mk, theses, j = walked
    side = {th.id: th.side for th in theses}
    assert j.of("intent")
    for intent in j.of("intent"):
        assert intent["side"] == side[intent["thesis_id"]]
    trades = sorted(j.of("trade"), key=lambda x: x["placed_at"])
    for a, b in zip(trades, trades[1:]):
        assert b["placed_at"] >= a["closed_at"]                   # one position at a time, so never both sides


def test_the_budget_holds(walked):
    mk, _, j = walked
    fills = [r for r in j.of("fill") if r["event"] == "FILLED"]
    days = Counter(int(trading_day(r["t"], "EURUSD")[0]) for r in fills)
    assert max(days.values(), default=0) <= 1
    by_order = {r["order_id"]: r["thesis_id"] for r in j.of("trade")}
    per_thesis = Counter(by_order[r["order_id"]] for r in fills if r["order_id"] in by_order)
    assert max(per_thesis.values(), default=0) <= 2


def test_a_stop_without_a_gap_is_minus_one_r(walked):
    _, _, j = walked
    stops = [t for t in j.of("trade") if t["reason"] == "SL"]
    assert stops and all(abs(t["net_r"] + 1) < 1e-9 for t in stops if t["exit"] == t["stop"])


def test_the_same_bars_and_theses_give_the_same_journal(walked):
    mk, theses, j = walked
    assert run(mk, theses).lines() == j.lines()


def test_only_the_past(walked):
    mk, theses, j = walked
    cut = int(mk.book.frames["D1"].c.end[40])
    m1 = walk_m1(10, seed=21)
    short = prepare("EURUSD", m1[m1["time"].astype("int64") < cut])
    k = run(short, theses)
    before = lambda jj: [(r["t"], r["frm"], r["to"], r["reason"]) for r in jj.of("transition")    # noqa: E731
                         if r["t"] < cut and "data ended" not in r["reason"]]
    assert before(j) and before(k) == before(j)


def test_the_mirror():
    m1 = walk_m1(8, seed=33, spread=0.0)
    up = prepare("EURUSD", m1)
    down = prepare("EURUSD", mirrored(m1))
    theses, _ = research_theses("EURUSD", up.book, "ORACLE")
    flipped = [Thesis(th.market, "BEARISH" if th.bullish else "BULLISH", -th.draw, -th.protected, th.since, th.until,
                      th.source) for th in theses]
    a, b = run(up, theses), run(down, flipped)
    moves = lambda jj: [(r["t"], r["frm"], r["to"]) for r in jj.of("transition")]          # noqa: E731
    assert a.of("trade") and moves(a) == moves(b)
    assert [round(t["net_r"], 9) for t in a.of("trade")] == [round(t["net_r"], 9) for t in b.of("trade")]
