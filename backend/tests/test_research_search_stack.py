"""
Tests for algo_research/search_stack.py — ICT's confluences stacked, H-M (docs/research/SEARCH_2018_2024.md).

Synthetic bars only: nothing here reads the snapshot. On the wave of the chain's tests, each vote is the reader it
names, unchanged; the score is their sum; the call needs seven net votes and a range on every frame; SMT votes by
date and abstains without a partner; and later bars change nothing (Property 2).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algo_research.atlas.arrays import build_arrays
from algo_research.search_chain import chain_rows
from algo_research.search_d1 import d1_frame
from algo_research.search_stack import NET, VOTES, stack_votes
from algo_research.trend import SIGNALS, trend_signals
from liquidity_engine.models import Timeframe
from tests.test_research_search_chain import bars_on


@pytest.fixture(scope="module")
def wave():
    b = bars_on(pd.bdate_range("2019-01-01", periods=420, tz="UTC"), seed=4)
    return b, stack_votes(b)


def test_votes_are_the_readers_own(wave):
    b, v = wave
    rows = chain_rows(b)
    for name in ("own-MN1", "own-W1", "own-D1", "H-K", "profile"):
        assert (v[name].to_numpy() == rows[name].fillna(0).to_numpy()).all(), name
    zones = rows["zones"].dropna().str.split("/")
    w1 = zones.str[1].map({"DISCOUNT": 1, "PREMIUM": -1}).fillna(0)
    assert (v.loc[w1.index, "zone-W1"].to_numpy() == w1.to_numpy()).all()
    frame = d1_frame("X", b)
    signals = trend_signals(frame.bars[Timeframe.D1].reset_index(drop=True), build_arrays(frame, (Timeframe.D1,)))
    for name in SIGNALS:
        assert (v[name].iloc[:len(signals)].to_numpy() == signals[name].to_numpy()).all(), name
    assert v["po3"].iloc[-1] == 0                                    # the last bar isn't closed by the path's end


def test_call_needs_net_seven_and_every_range(wave):
    _, v = wave
    assert (v["score"] == v[list(VOTES)].sum(axis=1)).all()
    called = v["H-M"] != 0
    assert called.any() and (v.loc[called, "score"].abs() >= NET).all() and v.loc[called, "ranged"].all()
    assert (np.sign(v.loc[called, "score"]) == v.loc[called, "H-M"]).all()
    strong = v["ranged"] & (v["score"].abs() >= NET)
    assert (called == strong).all()


def test_smt_votes_by_date_and_abstains_without_a_partner(wave):
    b, v = wave
    assert (v["smt"] == 0).all()
    day = pd.DatetimeIndex(b["time"]).normalize()
    smt = pd.Series([1, -1], index=day[[200, 300]])
    with_smt = stack_votes(b, smt=smt)
    assert with_smt["smt"].iloc[200] == 1 and with_smt["smt"].iloc[300] == -1 and with_smt["smt"].abs().sum() == 2


def test_votes_read_only_the_past(wave):
    """Property 2: the bars after a close change nothing read at it (the last bar's PO3 and trend signals wait for
    its close, so the cut's last row is left out)."""
    b, v = wave
    cut = 333
    part = stack_votes(b.iloc[:cut].reset_index(drop=True))
    pd.testing.assert_frame_equal(part.iloc[:cut - 1], v.iloc[:cut - 1], check_dtype=False)
