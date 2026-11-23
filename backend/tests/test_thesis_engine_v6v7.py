"""
Tests for the Thesis Engine's V6 and V7 (thesis-engine Requirement 27; task 446): V6 lets V1 enter twice on a
trading day; V7 orders V1's hand only after the day has raided the previous day's extreme on the stop's side. V1 to V5
stay byte for byte as they were.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import fields

import numpy as np
import pandas as pd
import pytest

from tests.thesis_engine_walks import walk_m1
from thesis_engine.clock import trading_day
from thesis_engine.machine import Ctx
from thesis_engine.replay import prepare, run
from thesis_engine.settings import V1, V5, V6, V7
from thesis_engine.thesis import research_theses

#: V1's journal with the week's real side, recorded before V6 and V7 existed (test_thesis_engine_v5.py).
V1_WALK_21 = "ead552c81db4ae0de20e9929902549d1f49df74f"


def _sha(j) -> str:
    return hashlib.sha1("\n".join(j.lines()).encode()).hexdigest()


def _changed(a, b) -> set:
    return {f.name for f in fields(a) if getattr(a, f.name) != getattr(b, f.name)}


def test_v1_is_unchanged():
    mk = prepare("EURUSD", walk_m1(10, seed=21))
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    assert _sha(run(mk, theses, V1)) == V1_WALK_21


def test_each_version_changes_only_its_registered_setting():
    assert _changed(V6, V1) == {"version", "per_day"} and V6.per_day == 2 and V6.per_thesis == V1.per_thesis
    assert _changed(V7, V1) == {"version", "pd_raid"} and V7.pd_raid
    assert not V1.pd_raid and not V5.pd_raid


@pytest.fixture(scope="module")
def market():
    mk = prepare("EURUSD", walk_m1(30, seed=5, step=0.0003, spread=0.00003))
    theses, _ = research_theses("EURUSD", mk.book, "ORACLE")
    return mk, theses


def test_v6_enters_at_most_twice_a_day_and_twice_a_thesis(market):
    mk, theses = market
    j = run(mk, theses, V6)
    fills = [r for r in j.of("fill") if r["event"] == "FILLED"]
    days = Counter(int(trading_day(r["t"], "EURUSD")[0]) for r in fills)
    assert fills and max(days.values()) <= 2
    by_order = {r["order_id"]: r["thesis_id"] for r in j.of("trade")}
    per_thesis = Counter(by_order[r["order_id"]] for r in fills if r["order_id"] in by_order)
    assert max(per_thesis.values()) <= 2
    v1 = run(mk, theses, V1)
    v1_days = Counter(int(trading_day(r["t"], "EURUSD")[0]) for r in v1.of("fill") if r["event"] == "FILLED")
    assert max(v1_days.values()) == 1


def _raided_directly(mk, t: int, bull: bool) -> bool:
    """The same question asked of the M5 candles with pandas, independently of Ctx.pd_raided."""
    e = mk.book.e
    df = pd.DataFrame({"end": e.end, "low": e.l, "high": e.h, "day": trading_day(e.t, "EURUSD")})
    seen = df[df["end"] <= t]
    if seen.empty:
        return False
    today = seen["day"].iloc[-1]
    before = df[df["day"] < today]
    if before.empty:
        return False
    prev = before[before["day"] == before["day"].iloc[-1]]
    now = seen[seen["day"] == today]
    return bool(now["low"].min() < prev["low"].min()) if bull else bool(now["high"].max() > prev["high"].max())


def test_the_raid_reads_only_the_day_so_far_and_the_previous_day(market):
    mk, theses = market
    ctx = Ctx("EURUSD", mk.book, theses, mk.typical_spread, V7)
    rng = np.random.default_rng(7)
    e = mk.book.e
    for m in rng.integers(300, len(e) - 1, size=200):
        t = int(e.end[m])
        for bull in (True, False):
            assert ctx.pd_raided(t, bull) == _raided_directly(mk, t, bull)


def test_v7_orders_only_after_the_raid_and_skips_without_spending(market):
    mk, theses = market
    j = run(mk, theses, V7)
    side = {th.id: th.bullish for th in theses}
    ctx = Ctx("EURUSD", mk.book, theses, mk.typical_spread, V7)
    intents = j.of("intent")
    assert intents
    assert all(ctx.pd_raided(i["at"], side[i["thesis_id"]]) for i in intents)
    skipped = [r for r in j.of("note") if r["note"] == "skip" and r["reason"] == "NO_PD_RAID"]
    assert skipped
    fills = [r for r in j.of("fill") if r["event"] == "FILLED"]
    days = Counter(int(trading_day(r["t"], "EURUSD")[0]) for r in fills)
    assert max(days.values(), default=0) <= 1
