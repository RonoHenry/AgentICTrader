"""
Tests for AlgoMindDIS v3, the draw first, and H-AM's runner (algomind-dis Requirement 18; task 434). No market data
is read: the picks are built from hand-made objectives, the replay runs on a random walk.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algo_research.search_narrative import control_share
from algomind_dis.draw import Close, Draw, Machine, end_of, pick, protected
from algomind_dis.ham import Control, market_tables, report
from algomind_dis.records import LiquidityObjective

_TFW = {"MN1": 1.0, "W1": 0.8, "D1": 0.6}
_KW = {"EXTERNAL": 1.0, "TEMPORAL": 0.8, "INTERNAL": 0.6}


def obj(price, side, tf="W1", kind="EXTERNAL", source=None, status="IDENTIFIED", equal=False):
    source = source or ("SWING_HIGH" if side == "BULLISH" else "SWING_LOW")
    if equal:
        source = "EQUAL_HIGHS" if side == "BULLISH" else "EQUAL_LOWS"
    sig = _TFW[tf] * _KW[kind] + (0.25 if equal else 0.0)
    return LiquidityObjective(f"{tf}-{source}-{price}", "T", tf, float(price), kind, source, side, None, status,
                              float(sig), 0, None, False)


def at(objs, c=100.0, w1="NEUTRAL", hi=None, lo=None, week=(None, None), adr=1.0, t=0):
    return Close(t, c + 0.2 if hi is None else hi, c - 0.2 if lo is None else lo, c, adr, w1, week[0], week[1],
                 tuple(objs))


SUPPORT = [obj(99.0, "BEARISH", "D1", "INTERNAL"), obj(101.0, "BULLISH", "D1", "INTERNAL")]


def test_a_takes_the_most_significant_reachable_draw_then_the_nearest():
    x = at([obj(103, "BULLISH", "MN1"), obj(102, "BULLISH", "MN1"), obj(98, "BEARISH", "W1"),
            obj(100.3, "BULLISH", "MN1", equal=True),                     # 0.3 ADR: too near
            obj(106, "BULLISH", "MN1", equal=True),                       # 6 ADR: too far
            obj(101.5, "BULLISH", "MN1", equal=True, status="SWEPT"),     # not live
            obj(98.5, "BEARISH", "D1", "INTERNAL"), *SUPPORT])
    d = pick("A", x)
    assert (d.side, d.price, d.protected, d.protected_from) == ("BULLISH", 102.0, 99.0, "D1 SWING_LOW")
    assert (d.tf, d.kind, d.equal) == ("MN1", "EXTERNAL", False)


def test_a_tie_across_the_sides_is_no_pick_and_so_is_nearest():
    x = at([obj(102, "BULLISH", "MN1"), obj(98, "BEARISH", "MN1"), *SUPPORT])
    assert pick("A", x) is None
    assert pick("NEAREST", at([obj(102, "BULLISH", "MN1"), obj(98, "BEARISH", "W1"), *SUPPORT])) is None
    # not a tie when one side is nearer
    assert pick("A", at([obj(102, "BULLISH", "MN1"), obj(97, "BEARISH", "MN1"), *SUPPORT])).price == 102.0


def test_b_takes_the_w1_structures_side_only():
    objs = [obj(102, "BULLISH", "MN1"), obj(97, "BEARISH", "MN1", equal=True), *SUPPORT]
    assert pick("A", at(objs)).price == 97.0                          # the equal lows are the strongest
    b = pick("B", at(objs, w1="BULLISH"))
    assert (b.side, b.price) == ("BULLISH", 102.0)
    assert pick("B", at(objs, w1="NEUTRAL")) is None
    assert pick("B", at([obj(102, "BULLISH", "MN1"), obj(101, "BULLISH", "D1")], w1="BEARISH")) is None


def test_nearest_ignores_significance():
    x = at([obj(100.8, "BULLISH", "D1", "INTERNAL"), obj(98, "BEARISH", "MN1", equal=True),
            obj(99.0, "BEARISH", "D1"), obj(102.0, "BULLISH", "D1")])
    assert pick("NEAREST", x).price == 100.8


def test_the_protected_level_is_a_near_d1_swing_else_last_weeks_extreme_else_no_pick():
    draw = obj(102, "BULLISH", "MN1")
    no_d1 = [draw, obj(99, "BEARISH", "D1", "INTERNAL", source="FVG"), obj(99, "BEARISH", "W1"),
             obj(99.6, "BEARISH", "D1")]                                # FVG and W1 don't protect; 0.4 ADR is too near
    assert protected(at(no_d1, week=(101.0, 98.0)), "BULLISH") == (98.0, "previous week")
    assert pick("A", at(no_d1, week=(101.0, 98.0))).protected == 98.0
    assert pick("A", at(no_d1, week=(101.0, 99.8))) is None             # last week's low only 0.2 ADR away
    eq = no_d1 + [obj(98.7, "BEARISH", "D1", equal=True), obj(98.9, "BEARISH", "D1", source="RANGE_LOW")]
    assert protected(at(eq, week=(101.0, 98.0)), "BULLISH") == (98.9, "D1 RANGE_LOW")
    assert protected(at([obj(97, "BEARISH", "MN1"), obj(101.2, "BULLISH", "D1")]), "BEARISH") == \
        (101.2, "D1 SWING_HIGH")


def _draw(side="BULLISH", rule="A"):
    price, prot = (102.0, 99.0) if side == "BULLISH" else (98.0, 101.0)
    return Draw(rule, side, price, prot, 0, 1.0, 100.0, "MN1", "EXTERNAL", "SWING_HIGH", 1.0, "D1 SWING_LOW")


def test_a_held_draw_ends_in_the_registered_order():
    d = _draw()
    assert end_of(d, 1, at([], c=98.9, hi=102.5, lo=98.5)) == "invalidated"      # beats delivered on the same day
    assert end_of(d, 1, at([], c=101.0, hi=102.0, lo=100.5)) == "delivered"
    assert end_of(d, 1, at([], c=100.3, hi=101.6, lo=100.0)) == "rejected"       # within 0.5 ADR, the far quarter
    assert end_of(d, 1, at([], c=101.5, hi=101.6, lo=100.0)) is None             # near, but closed at its top
    assert end_of(d, 1, at([], c=100.1, hi=101.4, lo=100.0)) is None             # 0.6 ADR short: not near
    assert end_of(d, 19, at([], c=100.5)) is None
    assert end_of(d, 20, at([], c=100.5)) == "expired"
    assert end_of(_draw(rule="B"), 3, at([], c=100.5, w1="BEARISH")) == "structure turned"
    assert end_of(_draw(rule="B"), 3, at([], c=100.5, w1="BULLISH")) is None
    assert end_of(d, 3, at([], c=100.5, w1="BEARISH")) is None                   # A ignores structure
    s = _draw("BEARISH")
    assert end_of(s, 1, at([], c=99.9, hi=100.0, lo=98.4)) == "rejected"
    assert end_of(s, 1, at([], c=101.1, hi=101.2, lo=97.9)) == "invalidated"
    assert end_of(s, 1, at([], c=99.0, hi=99.5, lo=98.0)) == "delivered"


def test_a_refuted_draw_is_never_picked_again_and_a_delivered_one_can_be():
    objs = [obj(102, "BULLISH", "MN1"), obj(103, "BULLISH", "W1"), obj(99, "BEARISH", "D1"),
            obj(97, "BEARISH", "D1", "INTERNAL")]
    m = Machine("A")
    ended, new = m.step(at(objs))
    assert ended is None and (new.price, new.protected) == (102.0, 99.0)
    assert m.step(at(objs, c=100.5)) == (None, None)                             # held
    ended, new = m.step(at(objs, c=98.9, hi=99.5, lo=98.6))                      # closes below 99
    assert ended == "invalidated" and ("BULLISH", 102.0) in m.refuted
    assert new is not None and new.price == 103.0                                # picked again at the same close
    m = Machine("A")
    m.step(at(objs))
    ended, _ = m.step(at(objs, c=101.0, hi=102.0, lo=100.5))
    assert ended == "delivered" and not m.refuted


def test_the_ladders_give_control_share_exactly():
    rng = np.random.default_rng(11)
    n = 1500
    cl = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[100.0, cl[:-1]]
    spread = np.abs(rng.normal(0, 0.006, n)) * cl
    hi, lo = np.maximum(o, cl) + spread, np.minimum(o, cl) - spread
    starts = np.arange(30, n)                                         # the last races stay open
    closes, adrs = cl[starts - 1], pd.Series(hi - lo).rolling(20).mean().to_numpy()[starts - 1]
    ctl = Control(hi, lo, cl, starts, closes, adrs, cap=6.0)
    for _ in range(40):
        side, a, b = int(rng.choice([1, -1])), float(rng.uniform(0.5, 5)), float(rng.uniform(0.5, 5))
        assert ctl.share(side, a, b) == control_share(hi, lo, cl, starts, closes, adrs, side, a, b)
    with pytest.raises(ValueError):
        ctl.share(1, 7.0, 1.0)


def walk(seed: int, start: str, n: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, periods=n)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[100.0, c[:-1]]
    spread = np.abs(rng.normal(0, 0.006, n)) * c
    return pd.DataFrame({"date": days, "open": o, "high": np.maximum(o, c) + spread,
                         "low": np.minimum(o, c) - spread, "close": c})


def test_the_replay_scores_every_pick_and_week_with_h_aes_scorer():
    t = market_tables("WALK", walk(5, "1994-06-01", 750), verify=3)
    calls, weeks, picks, closes = t["calls"], t["weeks"], t["picks"], t["closes"]
    assert len(calls) and set(calls["rule"]) <= {"A", "B", "NEAREST"}
    assert calls["t"].min() >= pd.Timestamp("1996-01-01")
    assert set(calls["outcome"]) <= {"held", "failed", "open"}
    resolved = calls[calls["outcome"].isin(["held", "failed"])]
    assert resolved["control"].between(0, 1).all() and (resolved["n_control"] > 0).all()
    assert calls["a"].between(0.5 - 1e-9, 5 + 1e-9).all() and calls["b"].between(0.5 - 1e-9, 5 + 1e-9).all()
    assert int(t["info"]["verified"].iloc[0]) > 0
    # B's side is always the W1 structure's, at its pick and at every week it holds
    b = picks[picks["rule"] == "B"].merge(closes[["t", "w1"]], on="t")
    assert (b["side"] == b["w1"]).all()
    bw = weeks[(weeks["rule"] == "B") & (weeks["side"] != 0)]
    assert (bw["side"] == bw["w1_side"]).all()
    # no rule picks a refuted draw again
    for r, g in picks.groupby("rule"):
        gone = set()
        for p in g.sort_values("t").itertuples():
            assert (p.side, p.draw) not in gone
            if p.ended not in ("delivered", "open"):
                gone.add((p.side, p.draw))
    live = weeks[weeks["side"] != 0]
    assert (live["hit"] == np.where(live["side"] > 0, live["up"], live["down"])).all()
    assert set(weeks["rule"]) == {"W1", "A", "B", "NEAREST"}
    text, passes = report(t)
    assert text.startswith("**H-AM ") and isinstance(passes, bool)
