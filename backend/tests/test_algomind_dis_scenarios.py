"""
The specification's regression scenarios (§17.4; algomind-dis Requirement 17, task 405).

Daily bars are built from straight legs with seeded wicks and noise (a candle opening exactly at the last close
would tie the swing highs, which real bars don't), then a scripted tail. Each scenario checks what its reads must
show at its key close: the delivery, the sweep, the zones, the structure and which side the evidence leads. The
state is checked where v1's rules make it unambiguous. B and D are A and C mirrored (prices negated).

v1's bar to hold a side (a score of 0.5 leading by 0.2, the specification's starting values) is not reached by
these single-market textbook cases: C, with every frame's structure bullish, scores 0.33 against 0.19. So A-D check
the reads and which side leads, not the state.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algomind_dis.evidence import SCORED, classify_lower, counted, gather, scores
from algomind_dis.frames import from_daily
from algomind_dis.observe import observe, prepare
from algomind_dis.state import run
from liquidity_engine.context.frame_state import Candles


def legs(spec, start=100.0, saw=1.2, period=8, wick=0.3, seed=5, day0="2016-01-04"):
    path, x = [], start
    for days, target in spec:
        step = (target - x) / days
        for _ in range(days):
            x += step
            path.append(x + (saw if (len(path) // (period // 2)) % 2 else -saw))
    rng = np.random.default_rng(seed)
    c = np.array(path) + rng.normal(0, 0.15 * wick, len(path))
    o = np.r_[start, c[:-1]] + rng.normal(0, 0.1 * wick, len(path))
    return pd.DataFrame({"date": pd.bdate_range(day0, periods=len(c)), "open": o,
                         "high": np.maximum(o, c) + wick * rng.uniform(0.3, 1.5, len(c)),
                         "low": np.minimum(o, c) - wick * rng.uniform(0.3, 1.5, len(c)), "close": c})


def tail(df, rows):
    dates = pd.bdate_range(df["date"].iloc[-1] + pd.offsets.BDay(1), periods=len(rows))
    t = pd.DataFrame(rows, columns=["open", "high", "low", "close"]).assign(date=dates)
    return pd.concat([df, t[["date", "open", "high", "low", "close"]]], ignore_index=True)


def mirror(df):
    return df.assign(open=-df["open"], high=-df["low"], low=-df["high"], close=-df["close"])


def reversal(df):
    """A sweep of the lows closing back, a displacement through the run's open, a gap, and its retest."""
    x = float(df["close"].iloc[-1])
    low = float(df["low"].iloc[-12:].min())
    return tail(df, [(x, x + 0.4, low - 2.5, x + 0.3),               # under the recent lows, closing back
                     (x + 0.3, x + 9.5, x, x + 9.2),                  # the displacement
                     (x + 9.2, x + 11.0, x + 2.4, x + 10.5),          # a gap over the sweep day's high, in the
                     (x + 10.5, x + 10.6, x + 2.2, x + 9.9),          # leg's discount; a wick back into it
                     (x + 9.9, x + 10.4, x + 9.5, x + 10.2)])         # and the leg's high confirmed


def read(df, name="S"):
    f = from_daily(name, df)
    obs = observe(name, f.at(int(f.closes("D1")[-1])), prepared=prepare(name, f.full))
    items = gather(obs)
    return obs, items, scores(items, SCORED)


def scenario_a():
    """A bullish reversal: a long decline into deep discount, then the reversal sequence."""
    return reversal(legs([(90, 70), (30, 80), (90, 55), (30, 64), (90, 42), (25, 47), (40, 40)]))


def scenario_c():
    """A bullish continuation: a rising market, a pullback into its discount, the same sequence."""
    return reversal(legs([(90, 130), (30, 118), (90, 150), (30, 137), (90, 172), (45, 150)]))


def test_a_bullish_reversal_reads_bullish_delivery_from_deep_discount():
    df = scenario_a()
    early, early_items, _ = read(df.iloc[:-2])                             # two closes after the sweep
    assert early.contexts["D1"].delivery.state == "BULLISH_DELIVERY"
    assert any(e.category == "LIQUIDITY" and e.direction == "BULLISH" for e in early_items)
    obs, items, sc = read(df)                                              # after the gap's retest
    assert obs.contexts["D1"].delivery.state == "BULLISH_DELIVERY"
    assert obs.contexts["MN1"].structural_direction == "BEARISH"           # the month still falls
    use = counted(items)
    assert any(e.category == "PREMIUM_DISCOUNT" and e.direction == "BULLISH" for e in use)
    assert any(e.category == "PD_ARRAY" and e.direction == "BULLISH" for e in use)
    assert sc.by_category["DELIVERY"][1] == 0.0
    assert sc.bullish > sc.bearish


def test_b_the_bearish_reversal_is_a_mirrored():
    a = read(scenario_a())
    b = read(mirror(scenario_a()))
    assert b[0].contexts["D1"].delivery.state == "BEARISH_DELIVERY"
    assert (b[2].bullish, b[2].bearish) == pytest.approx((a[2].bearish, a[2].bullish))


def test_c_a_bullish_continuation_leads_bullish_with_the_higher_frames():
    obs, items, sc = read(scenario_c())
    assert {tf: c.structural_direction for tf, c in obs.contexts.items()} == {"MN1": "BULLISH", "W1": "BULLISH",
                                                                               "D1": "BULLISH"}
    assert obs.contexts["D1"].delivery.state == "BULLISH_DELIVERY"
    assert sc.bullish > sc.bearish and sc.by_category["STRUCTURE"][0] > sc.by_category["STRUCTURE"][1]


def test_d_the_bearish_continuation_is_c_mirrored():
    c, d = read(scenario_c()), read(mirror(scenario_c()))
    assert d[0].contexts["MN1"].structural_direction == "BEARISH"
    assert (d[2].bullish, d[2].bearish) == pytest.approx((c[2].bearish, c[2].bullish))


def test_e_bearish_lower_frames_inside_a_bullish_daily_change_nothing():
    df = scenario_c()
    f = from_daily("E", df)
    frames = f.at(int(f.closes("D1")[-1]))
    d1 = frames["D1"]
    t0 = int(d1.end[-1]) - 86_400 * 10**9
    t = t0 + np.arange(24, dtype=np.int64) * 3_600 * 10**9                  # the last day as falling hours
    x = float(d1.h[-1]) - 0.2 * np.arange(24)
    h1 = Candles("H1", t, t + 3_600 * 10**9, x, x + 0.05, x - 0.25, x - 0.2)
    base = gather(observe("E", frames))
    lower = gather(observe("E", {**frames, "H1": h1}))
    assert scores(lower, SCORED) == scores(base, SCORED)                     # lower frames aren't scored
    assert classify_lower("BEARISH", side="BULLISH", price=float(d1.c[-1]), protected=float(d1.l[-30:].min()),
                          d1_range=(float(d1.l[-30:].min()), float(d1.h[-30:].max())), d1_mss_against=False,
                          d1_close=float(d1.c[-1])) == "RETRACEMENT"


def scenario_f():
    """A neutral consolidation: a trend, then four months inside a tight box."""
    base = legs([(90, 130), (30, 120)])
    rng = np.random.default_rng(9)
    x = float(base["close"].iloc[-1])
    rows = []
    for _ in range(80):
        o = x + rng.normal(0, 0.05)
        c = x + rng.normal(0, 0.05)
        rows.append((o, max(o, c) + 0.08, min(o, c) - 0.08, c))
    return tail(base, rows)


def test_f_a_neutral_consolidation_holds_no_side_and_reads_consolidation():
    df = scenario_f()
    tl = run("F", from_daily("F", df))
    box = tl.rows.iloc[-60:]
    assert not box["state"].isin(["BULLISH", "BEARISH"]).any()
    obs, _, _ = read(df, "F")
    assert obs.contexts["D1"].delivery.state == "CONSOLIDATION"


def test_g_a_news_spike_is_volatility_not_a_side():
    df = scenario_f()
    x = float(df["close"].iloc[-1])
    df = tail(df, [(x, x + 4.0, x - 0.1, x + 3.6)])                         # the release
    f = from_daily("G", df)
    frames = f.at(int(f.closes("D1")[-1]))
    obs = observe("G", frames, calendar=lambda when: ["USD Non-Farm Payrolls 08:30"])
    items = gather(obs)
    news = [e for e in items if e.category == "TEMPORAL"]
    assert news and news[0].direction == "NEUTRAL" and "Non-Farm" in news[0].text
    assert obs.volatility.expanding
    tl = run("G", f)
    assert tl.rows["state"].iloc[-1] not in ("BULLISH", "BEARISH")          # one candle is not enough
