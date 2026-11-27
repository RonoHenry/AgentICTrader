"""
Tests for AlgoMindDIS v4, the week as it unfolds (algomind_dis/unfold.py; algomind-dis Requirement 19; task 446), and
H-AP's runner (thesis_engine/hap.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algomind_dis.unfold import (MAX_ADR, MIN_ADR, Event, _ended_by, events, gap_candle, mirror_geometry, reachable_draw,
                                 reads, withdrawn_at)
from thesis_engine.book import Book
from thesis_engine.clock import clean, frames
from thesis_engine.hap import judge, market_run, thesis_of
from thesis_engine.replay import prepare
from thesis_engine.settings import V1
from tests.thesis_engine_walks import mirrored, walk_m1

WEEKS = 26


def book_of(m1: pd.DataFrame) -> Book:
    bars, _ = clean(m1)
    return Book("EURUSD", frames(bars, "EURUSD"))


@pytest.fixture(scope="module")
def m1() -> pd.DataFrame:
    return walk_m1(WEEKS, seed=7, step=0.00022)


@pytest.fixture(scope="module")
def book(m1) -> Book:
    return book_of(m1)


@pytest.fixture(scope="module")
def evs(book) -> list[Event]:
    return events(book)


# ── the pure pieces ───────────────────────────────────────────────────────────


def test_the_gap_candle_is_the_first_that_completes_an_fvg():
    h = np.array([10.0, 10.0, 12.0, 14.0])
    l = np.array([9.0, 9.0, 10.5, 11.0])
    assert gap_candle(h, l, 1, 2, True) == 2                 # l[2] 10.5 above h[0] 10.0
    assert gap_candle(h, l, 1, 1, True) == 2                 # through + 1 is the last it may read
    assert gap_candle(h, l, 1, 0, True) is None
    assert gap_candle(-l, -h, 1, 2, False) == 2              # the mirror


def test_the_gap_candle_needs_a_gap():
    h, l = np.array([10.0, 10.0, 10.2]), np.array([9.0, 9.0, 9.8])
    assert gap_candle(h, l, 1, 2, True) is None


def test_the_withdrawal_is_the_second_close_after_the_commit_above_the_protected_level():
    low, high = np.array([9.0, 10.5, 11.0, 12.0]), np.array([9.5, 10.8, 11.5, 12.5])
    ends = np.array([150, 100, 300, 400], dtype=np.int64)
    # the first array lies below the protected level (10.0) and the second ended before the commit (200)
    assert withdrawn_at(low, high, ends, True, 10.0, 200, 1000) == 400
    assert withdrawn_at(low, high, ends, True, 10.0, 200, 350) is None            # only one by the week's close
    assert withdrawn_at(low, high, ends, True, 10.0, 50, 1000) == 300             # the array above it counts from 50
    assert withdrawn_at(-high, -low, ends, False, -10.0, 200, 1000) == 400        # the mirror


class _Frame:
    def __init__(self, h, l, untaken):
        self.c = type("C", (), {"h": np.array(h, float), "l": np.array(l, float)})
        self._u = np.array(untaken, float)

    def n(self, t):
        return len(self.c.h)

    def untaken(self, n, lows):
        return self._u


class _Book:
    def __init__(self, week_high, swings, adr=1.0):
        self.frames = {"W1": _Frame([week_high], [0.0], []), "D1": _Frame([100.0], [0.0], swings)}
        self._adr = adr

    def adr(self, t):
        return self._adr


def test_the_draw_is_the_nearest_reachable_pool():
    book = _Book(week_high=103.0, swings=[100.4, 102.0, 108.0])
    assert reachable_draw(book, "BULLISH", 0, 100.0) == 102.0    # 100.4 is under half an ADR away


def test_the_draw_is_refused_past_five_adr_or_with_no_pool():
    assert reachable_draw(_Book(week_high=106.0, swings=[]), "BULLISH", 0, 100.0) is None
    assert reachable_draw(_Book(week_high=100.1, swings=[]), "BULLISH", 0, 100.0) is None
    assert MIN_ADR == 0.5 and MAX_ADR == 5.0


# ── the rule on a market ──────────────────────────────────────────────────────


def test_a_walk_has_events_of_both_sides(evs):
    assert {e.side for e in evs} == {"BULLISH", "BEARISH"}


def test_the_commit_waits_for_the_fvg_and_the_cisd(book, evs):
    h1 = book.frames["H1"].c
    for e in evs:
        bullish = e.side == "BULLISH"
        g = gap_candle(h1.h, h1.l, e.last, e.through, bullish)
        assert g is not None and e.commit == max(e.through, g) and e.t == int(h1.end[e.commit])
        assert e.price == h1.c[e.commit]
        assert e.price > max(e.pools) if bullish else e.price < min(e.pools)
        assert e.own == (h1.l[e.first:e.commit + 1].min() if bullish else h1.h[e.first:e.commit + 1].max())


def test_nothing_later_is_read(m1, book, evs):
    cut = m1.iloc[:(WEEKS - 8) * 5 * 1440]
    shorter = book_of(cut)
    last = int(shorter.frames["H1"].c.end[-1])
    key = lambda x: [(e.side, e.t, round(e.own, 9), round(e.other, 9), e.pools, e.array_id) for e in x]        # noqa: E731
    assert key(events(shorter)) == key([e for e in evs if e.t <= last])
    assert any(e.t <= last for e in evs)


def test_a_mirrored_market_gives_mirrored_events(m1, evs):
    flipped = events(book_of(mirrored(m1)))
    other = {"BULLISH": "BEARISH", "BEARISH": "BULLISH"}
    assert sorted((e.t, other[e.side], round(-e.own, 9)) for e in flipped) == sorted((e.t, e.side, round(e.own, 9)) for e in evs)


def test_one_side_at_a_time_inside_its_week(book, evs):
    rr, _ = reads(book, evs)
    w1 = book.frames["W1"].c
    assert rr
    for a, b in zip(rr, rr[1:]):
        assert _ended_by(book, a) <= b.since           # delivered, invalidated, withdrawn or replaced by then
        assert a.since < b.since
    for r in rr:
        w = int(np.searchsorted(w1.t, r.since, "right")) - 1
        assert r.since < r.until <= int(w1.end[w])
        bullish = r.side == "BULLISH"
        assert (r.protected < r.event.price < r.draw) if bullish else (r.draw < r.event.price < r.protected)
        assert r.reason in ("EXPIRED", "WITHDRAWN")
        adr = book.adr(r.since)
        assert MIN_ADR * adr <= abs(r.draw - r.event.price) <= MAX_ADR * adr + 1e-12


def test_the_withdrawal_only_shortens_a_read(book, evs):
    held, _ = reads(book, evs)
    free, _ = reads(book, evs, withdraw=False)
    free_by_since = {r.since: r for r in free}
    withdrawn = [r for r in held if r.reason == "WITHDRAWN"]
    assert withdrawn
    for r in held:
        if r.since in free_by_since:
            assert r.until <= free_by_since[r.since].until


def test_the_mirror_read_is_the_other_side_at_the_same_commit(book, evs):
    rr, _ = reads(book, evs)
    seen = 0
    for r in rr:
        g = mirror_geometry(book, r)
        if g is None:
            continue
        side, draw, protected = g
        seen += 1
        assert side != r.side and protected == r.event.other
        assert (draw > r.event.price) == (side == "BULLISH")
        th = thesis_of("EURUSD", book, r, "MIRROR", "MIRROR")
        assert (th.side, th.since, th.until, th.until_reason) == (side, r.since, r.until, r.reason)
    assert seen


def test_v1_is_untouched_and_one_market_runs_end_to_end(m1):
    mk = prepare("EURUSD", m1, V1)
    assert V1.version == "v1"
    since = int(mk.book.frames["W1"].c.t[5])
    out = market_run(mk, since, 0.0, companions=False)
    assert out["events"] > 0 and out["reads"] > 0 and {"UNFOLD", "MIRROR"} <= set(out["ends"])
    trades = pd.DataFrame(out["trades"])
    if not trades.empty:
        assert set(trades["arm"]) <= {"UNFOLD", "MIRROR", "RANDOM"}
        v = judge(trades)
        assert v["trades"] == int((trades["arm"] == "UNFOLD").sum()) and len(v["checks"]) == 3


def test_the_companions_run_and_v1_sides_take_the_nearest_pool_geometry(m1, tmp_path, monkeypatch):
    import json

    import thesis_engine.hap as hap

    mk = prepare("EURUSD", m1, V1)
    w1 = mk.book.frames["W1"].c
    opens = pd.Timestamp(int(w1.t[10]), tz="UTC")
    monday = (opens.tz_convert("America/New_York") + pd.Timedelta(hours=7)).date()
    entry = {"side": "BULLISH", "draw": 99.0, "protected": 0.0001, "since": opens.isoformat()}
    path = tmp_path / "sides.json"
    path.write_text(json.dumps({"EURUSD": {monday.isoformat(): entry, (monday + pd.Timedelta(days=1)).isoformat(): entry}}))
    monkeypatch.setattr(hap, "DIS_FILE", path)
    theses, refused = hap.v1_geometry("EURUSD", mk, 0)
    assert len(theses) + sum(refused.values()) == 1
    for th in theses:
        assert th.source == "V1_GEOMETRY" and th.draw != 99.0 and th.protected != 0.0001
    out = market_run(mk, int(w1.t[5]), 0.0, companions=True)
    assert out["reads"] > 0 and "NO_WITHDRAW" in out["ends"]


def test_the_judgement_is_the_registered_three():
    trades = pd.DataFrame({"arm": ["UNFOLD"] * 80, "market": (["A", "B", "C", "D", "E", "F", "G", "H"] * 10),
                           "week": list(range(80)), "net_r": [2.0] * 40 + [-0.5] * 40, "direction": ["LONG"] * 80,
                           "reason": ["TP"] * 80})
    v = judge(trades)
    assert v["passes"] and v["markets_positive"] == 8 and v["ci"][0] > 0
    assert not judge(trades.assign(net_r=[-1.0] * 80))["passes"]
    spike = trades.assign(net_r=[100.0] * 5 + [-0.5] * 75)
    assert not judge(spike)["checks"]["positive without its 5 best trades"]
