"""
Tests for the Thesis Engine's thesis: the record, its ends, the completion rule and the sources (thesis-engine
Requirement 4; task 409).
"""
from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

from agent.context_calls import Call
from thesis_engine.book import Book
from thesis_engine.clock import clean, frames
from thesis_engine.records import Thesis
from thesis_engine.thesis import call_theses, complete, end, file_theses, research_theses
from tests.thesis_engine_walks import walk_m1

NY = "America/New_York"


@pytest.fixture(scope="module")
def book():
    m1, _ = clean(walk_m1(8, seed=5))
    return Book("EURUSD", frames(m1, "EURUSD"))


def test_the_record_checks_its_sides():
    Thesis("EURUSD", "BULLISH", 1.2, 1.1, 0, 10, "CALL")
    with pytest.raises(ValueError):
        Thesis("EURUSD", "BULLISH", 1.1, 1.2, 0, 10, "CALL")
    with pytest.raises(ValueError):
        Thesis("EURUSD", "BEARISH", 1.2, 1.1, 0, 10, "CALL")
    with pytest.raises(ValueError):
        Thesis("EURUSD", "SIDEWAYS", 1.2, 1.1, 0, 10, "CALL")
    assert Thesis("EURUSD", "BULLISH", 1.2, 1.1, 0, 10, "CALL").id == Thesis("EURUSD", "BULLISH", 1.2, 1.1, 0, 10, "CALL").id


def first_end(th, book):
    d1 = book.frames["D1"]
    e = book.e
    seen = d1.n(int(e.end[0]) - 1)
    for m in range(len(e)):
        t = int(e.end[m])
        now = d1.n(t)
        found = end(th, book, m, t, seen, now)
        if found:
            return m, found[0]
        seen = now
    return None, None


def test_each_end_comes_first_when_it_happens_first(book):
    e, d1 = book.e, book.frames["D1"].c
    since = int(d1.end[25])
    m0 = int(np.searchsorted(e.t, since, "left"))
    price = float(e.c[m0])
    span = float(d1.h[10:25].max() - d1.l[10:25].min())
    th = Thesis("EURUSD", "BULLISH", price + span, price - span, since, int(d1.end[-1]), "ORACLE")
    m, kind = first_end(th, book)
    later = slice(m0, None)
    hit_draw = np.flatnonzero(e.h[later] >= th.draw)
    closes = np.flatnonzero((d1.c < th.protected) & (d1.end > since))
    first_draw = m0 + int(hit_draw[0]) if len(hit_draw) else None
    first_close = int(np.searchsorted(e.end, d1.end[closes[0]], "left")) if len(closes) else None
    candidates = [(x, k) for x, k in ((first_close, "INVALIDATED"), (first_draw, "DELIVERED")) if x is not None]
    expected = min(candidates) if candidates else (None, None)
    if expected[0] is None:
        assert kind == "EXPIRED"
    else:
        assert (m, kind) == expected


def test_a_wick_beyond_the_protected_level_is_not_an_end(book):
    d1 = book.frames["D1"].c
    i = int(np.argmax(d1.c - d1.l))                                # a day whose low is far under its close
    th = Thesis("EURUSD", "BULLISH", float(d1.h[i]) + 1, float(d1.c[i] + d1.l[i]) / 2, int(d1.t[i]),
                int(d1.end[i]) + 1, "CALL")
    e = book.e
    m = int(np.searchsorted(e.end, d1.end[i], "left"))
    assert end(th, book, m, int(e.end[m]), i, i + 1) is None


def test_until_expires_or_withdraws(book):
    e = book.e
    t = int(e.end[100])
    for reason in ("EXPIRED", "WITHDRAWN"):
        th = Thesis("EURUSD", "BULLISH", 99.0, -99.0, int(e.t[0]), t, "FILE", until_reason=reason)
        assert end(th, book, 100, t, 0, 0)[0] == reason


def test_the_completion_rule_takes_the_nearest_pools(book):
    w1 = book.frames["W1"].c
    d1 = book.frames["D1"]
    for w in range(3, len(w1)):
        since, open_ = int(w1.t[w]), float(w1.o[w])
        adr = book.adr(since)
        for side in ("BULLISH", "BEARISH"):
            draw, protected, why = complete(side, book, since, open_, float(w1.h[w - 1]), float(w1.l[w - 1]))
            if draw is None:
                assert why.startswith("no ") or "ADR away" in why
                continue
            bull = side == "BULLISH"
            n = d1.n(since)
            pools = [float(w1.h[w - 1] if bull else w1.l[w - 1]), *d1.untaken(n, lows=not bull)]
            beyond = [x for x in pools if (x >= open_ + 0.5 * adr if bull else x <= open_ - 0.5 * adr)]
            assert draw == (min(beyond) if bull else max(beyond))
            assert (draw > open_ > protected) if bull else (draw < open_ < protected)
            assert abs(draw - open_) <= 5 * adr and abs(open_ - protected) <= 5 * adr


def test_the_research_sides(book):
    oracle, _ = research_theses("EURUSD", book, "ORACLE")
    mirror, _ = research_theses("EURUSD", book, "MIRROR")
    w1 = book.frames["W1"].c
    real = {int(t): ("BULLISH" if c > o else "BEARISH") for t, o, c in zip(w1.t, w1.o, w1.c)}
    assert oracle and all(th.side == real[th.since] for th in oracle)
    by_week = {th.since: th.side for th in mirror}
    assert all(by_week[th.since] != th.side for th in oracle if th.since in by_week)
    a, _ = research_theses("EURUSD", book, "RANDOM", seed=1)
    b, _ = research_theses("EURUSD", book, "RANDOM", seed=1)
    assert [x.side for x in a] == [x.side for x in b]
    later, _ = research_theses("EURUSD", book, "RANDOM", seed=1, since_from=int(w1.t[4]))
    assert [x.side for x in later] == [x.side for x in a if x.since >= int(w1.t[4])]
    trend, _ = research_theses("EURUSD", book, "W1TREND")
    assert all(th.source == "W1TREND" for th in trend)


def test_the_traders_calls(tmp_path):
    calls = [Call("EURUSD", "2026-11-02", "BULLISH", 1.20, 1.10, made_at="2026-10-31T10:00:00+00:00"),
             Call("EURUSD", "2026-11-09", "NONE", made_at="2026-11-07T10:00:00+00:00"),
             Call("GBPUSD", "2026-11-02", "BEARISH", 1.20, 1.30, made_at="2026-11-03T10:00:00+00:00")]
    path = tmp_path / "calls.json"
    path.write_text(json.dumps([asdict(c) for c in calls]), encoding="utf-8")
    eur = call_theses("EURUSD", path)
    assert len(eur) == 1 and (eur[0].side, eur[0].draw, eur[0].protected) == ("BULLISH", 1.2, 1.1)
    opens = pd.Timestamp("2026-11-01 17:00", tz=NY).value
    closes = pd.Timestamp("2026-11-06 17:00", tz=NY).value
    assert (eur[0].since, eur[0].until) == (opens, closes)
    gbp = call_theses("GBPUSD", path)
    assert gbp[0].since == pd.Timestamp("2026-11-03T10:00:00+00:00").value          # a late call counts from itself


def test_a_thesis_file_joins_consecutive_dates_and_withdraws_at_the_last_close(tmp_path):
    entry = {"side": "BEARISH", "draw": 1.1, "protected": 1.2, "since": "2026-11-02T22:00:00+00:00"}
    other = {**entry, "draw": 1.05}
    days = {"2026-11-02": entry, "2026-11-03": entry, "2026-11-04": entry, "2026-11-05": other,
            "2026-11-09": entry}
    path = tmp_path / "theses.json"
    path.write_text(json.dumps({"EURUSD": days}), encoding="utf-8")
    out = file_theses("EURUSD", path)
    assert [(x.draw, x.until_reason) for x in out] == [(1.1, "WITHDRAWN"), (1.05, "WITHDRAWN"), (1.1, "WITHDRAWN")]
    assert out[0].until == pd.Timestamp("2026-11-04 17:00", tz=NY).value
    assert out[2].until == pd.Timestamp("2026-11-09 17:00", tz=NY).value
