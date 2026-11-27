"""
Tests for the Thesis Engine's book (thesis-engine Requirement 3, Property 4; task 411): what AlgoMindDIS's analyzers
see, read as of each close, plus the execution frame's pools and runs.
"""
from __future__ import annotations

import numpy as np
import pytest

from algomind_dis.analyzers.ranges import swing_range
from liquidity_engine.context.blocks import runs
from thesis_engine.book import NEVER, Book, Frame
from thesis_engine.clock import clean, frames
from tests.thesis_engine_walks import walk_m1


@pytest.fixture(scope="module")
def market():
    m1, _ = clean(walk_m1(6, seed=11))
    fr = frames(m1, "EURUSD")
    return fr, Book("EURUSD", fr)


def key(rows):
    return sorted((r.kind, r.side, round(r.low, 9), round(r.high, 9), r.formed_at, r.high_probability) for r in rows)


@pytest.mark.parametrize("tf", ["H1", "H4", "D1"])
def test_the_book_at_a_cut_equals_the_analyzers_run_on_the_cut(market, tf):
    fr, book = market
    full = book.frames[tf]
    rng = np.random.default_rng(3)
    compared = 0
    for n in sorted(set(rng.integers(5, len(full.c), 6).tolist())):
        alone = Frame("EURUSD", full.cut(n))
        for side in ("BULLISH", "BEARISH"):
            live = key(full.live(n, side))
            assert live == key(r for r in alone.rows if r.end == NEVER and r.side == side)
            compared += len(live)
        a, b = full.range(n), swing_range("EURUSD", full.cut(n))
        assert (a is None) == (b is None)
        if a is not None:
            assert (a.high, a.low, a.valid) == (b.high, b.low, b.valid)
    assert compared > 0


def test_the_book_holds_the_traders_blocks_gaps_and_inversions(market):
    _, book = market
    kinds = {r.kind for tf in ("H1", "H4") for r in book.frames[tf].rows}
    assert {"OB", "BREAKER", "FVG", "IFVG"} <= kinds


def test_the_pools_a_candle_takes(market):
    _, book = market
    e = book.e
    lb = book.s.e_swing_lookback
    for m in range(10, len(e), 97):
        for bullish in (True, False):
            x = e.l if bullish else e.h
            expected = []
            for i in range(lb, m - lb):
                window = x[i - lb:i + lb + 1]
                swing = (x[i] < np.delete(window, lb).min()) if bullish else (x[i] > np.delete(window, lb).max())
                if not swing:
                    continue
                untaken = (x[i + 1:m] >= x[i]).all() if bullish else (x[i + 1:m] <= x[i]).all()
                taken = x[m] < x[i] if bullish else x[m] > x[i]
                if untaken and taken:
                    expected.append(i)
            assert [i for i, _ in book.e_pools_taken(m, bullish)] == expected


def test_the_cisd_closes_through_a_run_that_ended_at_or_after_the_sweep(market):
    _, book = market
    e = book.e
    found = runs(e.o, e.c, True)
    first, last, through = found[len(found) // 2]
    assert book.cisd(through, True, last) == (first, last)
    assert book.cisd(through, True, last + 1) is None
    assert book.cisd(through + 1, True, 0) in (None, *[(f, l) for f, l, th in found if th == through + 1])


def test_the_previous_h1_pool(market):
    _, book = market
    e, h1 = book.e, book.h1
    for m in range(30, len(e), 53):
        k = int(np.searchsorted(h1.end, e.t[m], "right")) - 1
        start = int(np.searchsorted(e.t, h1.end[k], "left"))
        expect = h1.l[k] if (e.l[start:m] >= h1.l[k]).all() and e.l[m] < h1.l[k] else None
        assert book.h1_pool_taken(m, True) == expect
