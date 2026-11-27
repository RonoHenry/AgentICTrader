"""
Tests for AlgoMindDIS's state machine and timeline (algomind-dis Requirements 12, 14; task 404).
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from algomind_dis.evidence import SCORED, gather, scores
from algomind_dis.frames import from_daily
from algomind_dis.observe import observe, prepare
from algomind_dis.state import ALLOWED, Held, Inputs, run, step

X = Inputs(t=1, high=101.0, low=99.0, close=100.0, bullish=0.0, bearish=0.0, htf_bullish=0.0, htf_bearish=0.0,
           d1_direction="NEUTRAL", d1_break_at=None, draw_up=110.0, draw_down=90.0, protect_up=95.0,
           protect_down=105.0)


def at(t, **kw):
    return replace(X, t=t, **kw)


def test_a_side_is_established_only_by_score_lead_draw_and_protected_level():
    h, why = step(Held(), at(1, bullish=0.55, bearish=0.30))
    assert (h.state, h.side, h.since, h.draw, h.protected) == ("BULLISH", "BULLISH", 1, 110.0, 95.0)
    assert why.startswith("established")
    assert step(Held(), at(1, bullish=0.55, bearish=0.40))[0].state == "UNDETERMINED"     # leads by 0.15
    assert step(Held(), at(1, bullish=0.45, bearish=0.0))[0].state == "UNDETERMINED"      # under 0.5
    assert step(Held(), at(1, bullish=0.6, bearish=0.1, draw_up=None))[0].state == "UNDETERMINED"
    assert step(Held(), at(1, bullish=0.6, bearish=0.1, protect_up=None))[0].state == "UNDETERMINED"
    assert step(Held("NEUTRAL"), at(1, bearish=0.6))[0].state == "BEARISH"


def test_the_ends_a_close_invalidates_a_wick_doesnt_and_the_draw_delivers():
    held = step(Held(), at(1, bullish=0.6))[0]
    assert step(held, at(2, low=94.0, close=96.0))[0].state == "BULLISH"                # a wick under 95
    h, why = step(held, at(2, low=94.0, close=94.5))
    assert (h.state, h.ended) == ("UNDETERMINED", ("invalidated", 2)) and "94.5" in why
    h, why = step(held, at(2, high=110.0))
    assert (h.state, h.ended) == ("NEUTRAL", ("delivered", 2))
    assert step(held, at(2, high=111.0, close=94.0))[0].ended == ("invalidated", 2)      # both: invalidated
    for k in range(2, 22):                                  # set at close 1: its 20th later close is 21
        held, _ = step(held, at(k))
    assert (held.state, held.ended) == ("UNDETERMINED", ("expired", 21))


def test_a_challenge_resolves_to_the_other_side_back_or_neutral():
    held = step(Held(), at(1, bullish=0.6))[0]
    h, why = step(held, at(2, htf_bearish=0.4))
    assert (h.state, h.side, h.challenger) == ("TRANSITIONAL", "BULLISH", "BEARISH") and "0.40" in why
    assert step(h, at(3, bearish=0.6, bullish=0.2))[0].state == "BEARISH"                # established
    back, why = step(h, at(3))
    assert (back.state, why) == ("BULLISH", "the challenge faded")
    k = h
    for t in (3, 4, 5):
        k, why = step(k, at(t, htf_bearish=0.4))
    assert (k.state, k.ended) == ("NEUTRAL", ("unresolved", 5))
    mss = step(held, at(2, d1_direction="BEARISH", d1_break_at=2))[0]                 # a D1 break against it
    assert mss.state == "TRANSITIONAL"
    assert step(held, at(2, d1_direction="BEARISH", d1_break_at=1))[0].state == "BULLISH"   # older than the side
    stale, why = step(held, at(2, stale=True))
    assert (stale.state, stale.ended, why) == ("UNDETERMINED", ("stale", 2), "the data is stale")


@settings(max_examples=100, deadline=None)
@given(st.lists(st.tuples(st.floats(0, 1), st.floats(0, 1), st.floats(0, 1), st.floats(0, 1),
                          st.sampled_from(["BULLISH", "BEARISH", "NEUTRAL"]), st.floats(80, 120), st.booleans()),
                min_size=1, max_size=60))
def test_only_the_allowed_transitions_happen(seq):
    held = Held()
    for t, (b, s_, hb, hs, d, close, stale) in enumerate(seq, start=1):
        x = at(t, bullish=b, bearish=s_, htf_bullish=hb, htf_bearish=hs, d1_direction=d, d1_break_at=t,
               close=close, high=close + 1, low=close - 1, stale=stale and t % 7 == 0)
        new, why = step(held, x)
        assert new.state == held.state or (held.state, new.state) in ALLOWED, (held.state, new.state)
        assert (why is None) == (new == held or (new.state == held.state and why is None))
        held = new


def _walk(seed: int, n: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2019-01-01", periods=n)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[100.0, c[:-1]]
    spread = np.abs(rng.normal(0, 0.006, n)) * c
    return pd.DataFrame({"date": days, "open": o, "high": np.maximum(o, c) + spread,
                         "low": np.minimum(o, c) - spread, "close": c})


def test_the_timeline_is_the_same_whatever_bars_come_later_and_a_restart_is_a_replay():
    days = _walk(7, 420)
    full = run("WALK", from_daily("WALK", days))
    cut_at = 300
    part = run("WALK", from_daily("WALK", days.iloc[:cut_at]))
    n = len(part.rows)
    shared = full.rows.iloc[:n].reset_index(drop=True)
    last_week_open = part.rows["t"].iloc[-1]
    same = shared["t"] <= last_week_open - 7 * 86_400 * 10**9      # W1/MN1 forming at the cut's end are left out
    cols = ["t", "state", "side", "since", "draw", "protected"]
    pd.testing.assert_frame_equal(shared.loc[same, cols], part.rows.loc[same, cols])
    assert run("WALK", from_daily("WALK", days)).rows.equals(full.rows)          # the same bars, the same timeline
    assert set(full.rows["state"]) <= {"UNDETERMINED", "BULLISH", "BEARISH", "NEUTRAL", "TRANSITIONAL"}
    for tr in full.transitions:
        assert (tr.previous, tr.new) in ALLOWED and tr.trigger


def test_the_replays_prepared_reads_equal_reading_each_close_afresh():
    f = from_daily("WALK", _walk(11, 260))
    prepared = prepare("WALK", f.full)
    for t in f.closes("D1")[150::17]:
        frames = f.at(int(t))
        fast, slow = observe("WALK", frames, prepared=prepared), observe("WALK", frames)
        assert fast == slow
        assert scores(gather(fast), SCORED) == scores(gather(slow), SCORED)
