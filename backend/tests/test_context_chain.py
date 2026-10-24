"""
Tests for liquidity_engine/context/chain.py — the context chain (context-engine Requirement 4).

Task 278 (.kiro/specs/context-engine/tasks.md). Each child frame reads its parent:
- `PD_POI` (CE-D5): with the parent, except from the parent's wrong zone toward its unreached POI; a NEUTRAL
  parent gives a NEUTRAL child. The spec's example is the RISE week of task 277's tests: bullish, in premium, with
  an unreached bullish gap at 93-96 below, so the day is bearish, drawn to 96.
- `PROFILE`: the candle profile at any frame. On W1 → D1 it is the engine's `CandleProfileAnalyzer` (Property 6).
Random frame states check that a child only ever follows its parent, heads for the parent's POI, or waits
(Property 3).
Validates: Requirements 4.1-4.6 (.kiro/specs/context-engine/requirements.md); Properties 3, 6
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import numpy as np
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from liquidity_engine.context.chain import ChainRule, chain
from liquidity_engine.context.frame_state import ArrayPOI, Candles, FrameState, Objective, frame_state
from liquidity_engine.models import BiasDirection, Timeframe
from liquidity_engine.profile.candle_profile import CandleProfileAnalyzer
from liquidity_engine.utils.time_utils import trading_week_open
from tests.test_context_frame_state import DAY, FALL, RISE, T0, candles
from tests.test_liquidity_profile import CAL, D1, H4, steps, view, walk

BULL, BEAR, NEUTRAL = BiasDirection.BULLISH, BiasDirection.BEARISH, BiasDirection.NEUTRAL
WEEK = 7 * DAY
BACK = RISE + [(107.5, 107.6, 95.8, 96.5), (96.5, 107.8, 96.3, 107.6)]     # into the gap and out again


def week(rows, price):
    return frame_state(candles(rows, tf="W1", step=WEEK), price)


def day(price, rows=None):
    """A D1 frame after the weeks: three closed days around ``price``."""
    rows = rows or [(price - 1, price + 0.5, price - 1.5, price - 0.2),
                    (price - 0.2, price + 1.2, price - 0.8, price + 0.4),
                    (price + 0.4, price + 0.5, price - 0.7, price)]                 # its high is the nearer
    return frame_state(candles(rows, start=T0 + 10 * WEEK), price)


# ── PD_POI ─────────────────────────────────────────────────────────────────

def test_top_frame_takes_its_own_direction():
    w = week(RISE, 107.5)
    top = chain([w]).links[0]
    assert (top.case, top.context, top.own) == ("TOP", w.own, w.own) and top.draw == w.own_draw
    assert w.own == BULL


def test_to_parent_poi_from_the_wrong_zone():
    w = week(RISE, 107.5)                                   # bullish, premium, the 93-96 gap below unreached
    link = chain([w, day(107.5)]).links[1]
    assert (link.case, link.context) == ("TO_PARENT_POI", BEAR)
    assert (link.draw.kind, link.draw.source, link.draw.tf, link.draw.price) == ("POI", "FVG", "W1", 96)
    assert link.poi == w.poi(BULL)
    assert "POI" in link.reason and "PREMIUM" in link.reason


def test_with_parent_in_the_right_zone():
    w = week(RISE, 107.5)                                   # bullish with an unreached POI below...
    d = day(107.5)
    for zone in ("DISCOUNT", "EQUILIBRIUM"):                # ...but not in premium: no counter-move
        link = chain([replace(w, zone=zone), d]).links[1]
        assert (link.case, link.context, link.draw) == ("WITH_PARENT", BULL, d.nearest(BULL))
    w = week(RISE, 98.0)                                    # read at 98: bearish, from discount, no bearish POI
    assert (w.zone, w.own, w.poi(BEAR)) == ("DISCOUNT", BEAR, None)
    assert chain([w, day(98.0)]).links[1].case == "WITH_PARENT"


def test_with_parent_once_poi_reached():
    w = week(BACK, 107.6)
    assert w.own == BULL and w.zone == "PREMIUM" and w.poi(BULL).reached_at is not None
    d = day(107.6)
    link = chain([w, d]).links[1]
    assert (link.case, link.context, link.draw) == ("WITH_PARENT", BULL, d.nearest(BULL))


def test_neutral_parent_gives_neutral_child():
    inside = FALL[:-1] + [(100, 102.5, 99.5, 101)]          # not trending, 1.5 to either side
    w = frame_state(candles(inside, tf="W1", step=WEEK), 101.0)
    assert w.own == NEUTRAL
    c = chain([w, day(101.0), day(101.0)])
    assert [x.case for x in c.links] == ["TOP", "PARENT_NEUTRAL", "PARENT_NEUTRAL"]
    assert all(x.context == NEUTRAL and x.draw is None for x in c.links)
    assert not c.armed and c.unarmed_reason == "CONTEXT_NEUTRAL"


def test_no_draw_means_not_armed():
    w = week(BACK, 107.6)                                   # bullish, with the parent
    d = replace(day(107.6), above=())                        # nothing above the day
    c = chain([w, d])
    assert c.bias.context == BULL and c.bias.draw is None
    assert not c.armed and c.unarmed_reason == "NO_DRAW"
    assert chain([w, day(107.6)]).armed


def test_poi_reached_and_draw_taken_strictly():
    """A POI is reached by a bar trading to its near edge; a draw is taken only by a bar trading beyond it
    (liquidity-engine Requirement 13.5)."""
    frame = candles(RISE, tf="W1", step=WEEK)
    to_edge = candles([(107.5, 107.7, 96.0, 97.0)], start=T0 + 10 * WEEK)       # touches 96, the gap's top
    assert frame_state(frame, 97.0, path=to_edge).poi(BULL).reached_at == T0 + 10 * WEEK
    short = candles([(107.5, 107.7, 96.01, 97.0)], start=T0 + 10 * WEEK)
    assert frame_state(frame, 97.0, path=short).poi(BULL).reached_at is None

    at_high = candles([(107.5, 110.0, 107.0, 109.0)], start=T0 + 10 * WEEK)      # to 110, the swing high, not past
    held = frame_state(frame, 109.0, path=at_high).above
    assert ("W1", "SWING_HIGH", 110) in [(x.tf, x.source, x.price) for x in held]
    beyond = candles([(107.5, 110.01, 107.0, 109.0)], start=T0 + 10 * WEEK)
    assert ("W1", "SWING_HIGH", 110) not in [(x.tf, x.source, x.price)
                                             for x in frame_state(frame, 109.0, path=beyond).above]


def test_reasons_on_every_link():
    c = chain([week(RISE, 107.5), day(107.5)])
    assert all(link.reason for link in c.links)
    assert c.rule == ChainRule.PD_POI and c.bias is c.links[-1]


# ── PROFILE ────────────────────────────────────────────────────────────────

def test_profile_follows_a_trending_parent_to_its_objective():
    up = FALL[:-1] + [(100, 104, 99.5, 103.5)]              # the week closed above the previous week's high
    w = frame_state(candles(up, tf="W1", step=WEEK), 103.5)
    assert w.trend == BULL
    d = frame_state(candles(RISE[-3:], start=T0 + 10 * WEEK), 103.5, parents=[candles(up, tf="W1", step=WEEK)])
    link = chain([w, d], ChainRule.PROFILE).links[1]
    assert (link.case, link.context) == ("PARENT_TREND", BULL)
    assert link.draw == d.nearest(BULL, tf="W1") and link.draw.tf == "W1"


def test_profile_without_a_trend_goes_to_the_nearer_objective():
    w = week(RISE, 107.5)
    assert w.trend == NEUTRAL
    d = day(107.5)
    link = chain([w, d], ChainRule.PROFILE).links[1]
    assert (link.case, (link.context, link.draw)) == ("OWN_NEARER", d.nearer()) and link.context == BULL


# ── Property 3: a child follows, heads for the parent's POI, or waits ──────

PRICE = 100.0


@st.composite
def states(draw, n):
    out = []
    for k in range(n):
        tf = ("MN1", "W1", "D1", "H4")[k]
        above = tuple(sorted((Objective("POOL", "SWING_HIGH", tf, PRICE + x, BULL, 0)
                              for x in draw(st.lists(st.floats(0.1, 20), max_size=3, unique=True))),
                             key=lambda o: o.price))
        below = tuple(sorted((Objective("POOL", "SWING_LOW", tf, PRICE - x, BEAR, 0)
                              for x in draw(st.lists(st.floats(0.1, 20), max_size=3, unique=True))),
                             key=lambda o: -o.price))
        pois = {}
        for d, sign in ((BULL, -1), (BEAR, 1)):
            if draw(st.booleans()):
                near, depth = draw(st.floats(0.1, 15)), draw(st.floats(0.1, 5))
                lo, hi = sorted((PRICE + sign * near, PRICE + sign * (near + depth)))
                pois[d] = ArrayPOI(d, "FVG", tf, lo, hi, 0, draw(st.sampled_from([None, 5])))
            else:
                pois[d] = None
        own = draw(st.sampled_from([BULL, BEAR, NEUTRAL]))
        zone = draw(st.sampled_from(["PREMIUM", "DISCOUNT", "EQUILIBRIUM", None]))
        trend = draw(st.sampled_from([BULL, BEAR, NEUTRAL]))
        own_draw = above[0] if own == BULL and above else below[0] if own == BEAR and below else None
        out.append(FrameState(tf, PRICE, None, None, None, zone, above, below, trend, own, own_draw, pois, {}))
    return out


@settings(max_examples=300, deadline=None)
@given(st.integers(2, 4).flatmap(states))
def test_property_3_chain_consistency(frames):
    c = chain(frames)
    for parent, (up, link), state in zip(frames, zip(c.links, c.links[1:]), frames[1:]):
        d = up.context
        if d == NEUTRAL:
            assert (link.context, link.case, link.draw) == (NEUTRAL, "PARENT_NEUTRAL", None)
            continue
        poi = parent.poi(d)
        wrong = "PREMIUM" if d == BULL else "DISCOUNT"
        counter = poi is not None and poi.reached_at is None and parent.zone == wrong
        if counter:
            assert link.case == "TO_PARENT_POI" and link.context != d and link.context != NEUTRAL
            assert link.draw.price == poi.near
        else:
            assert (link.case, link.context, link.draw) == ("WITH_PARENT", d, state.nearest(d))
    for link in c.links:
        if link.draw is not None:
            assert (link.draw.price > PRICE) == (link.context == BULL)
            assert link.context != NEUTRAL


@settings(max_examples=150, deadline=None)
@given(st.integers(2, 4).flatmap(states))
def test_property_3_holds_for_profile_draws(frames):
    for link in chain(frames, ChainRule.PROFILE).links:
        if link.draw is not None:
            assert (link.draw.price > PRICE) == (link.context == BULL)
        else:
            assert link.context == NEUTRAL or link.case == "TOP"


# ── Property 6: PROFILE on W1 -> D1 is the engine's candle profile ─────────

def arrays(bars, tf: str, closes_at) -> Candles:
    """Engine candles as a frame's closed candles: each one ends where the next opens, the last at ``closes_at``."""
    t = np.array([int(b.timestamp.timestamp()) for b in bars], np.int64)
    end = np.r_[t[1:], int(closes_at.timestamp())]
    prices = (np.array([getattr(b, k) for b in bars], float) for k in ("open", "high", "low", "close"))
    return Candles(tf, t, end, *prices)


def summary(o):
    if o is None:
        return None
    tf = o.timeframe.value if hasattr(o, "timeframe") else o.tf
    return tf, o.kind, round(o.price, 9)


@settings(max_examples=40, deadline=None)
@given(steps, st.integers(1, 5))
def test_property_6_profile_is_the_candle_profile(moves, i):
    h4 = walk(moves)
    open_time = CAL.period_start(h4[-1].timestamp, Timeframe.D1) - D1
    t = open_time + H4 * i
    v = view(h4, t)
    p = CandleProfileAnalyzer().analyze(v, t)
    assume(p is not None)
    week_open = trading_week_open(open_time)
    weeks = arrays([b for b in v[Timeframe.W1] if b.timestamp < week_open], "W1", week_open)
    days = arrays([b for b in v[Timeframe.D1] if b.timestamp < open_time], "D1", open_time)
    hours = arrays([b for b in v[Timeframe.H4] if b.timestamp < open_time], "H4", open_time)
    w1 = frame_state(weeks, p.frame_open)
    d1 = frame_state(days, p.frame_open, parents=[weeks], lower=[hours])
    link = chain([w1, d1], ChainRule.PROFILE).links[1]
    assert w1.trend == p.trend
    assert summary(d1.nearest(BULL)) == summary(p.draw_above) and summary(d1.nearest(BEAR)) == summary(p.draw_below)
    assert (link.context, summary(link.draw)) == (p.direction, summary(p.draw))


def test_property_6_on_a_trending_week():
    """The hand-built weeks of the profile's own tests: trending up, so drawn to a W1 objective."""
    from tests.test_liquidity_profile import OPEN, context
    v = context(last_w=(1.1000, 1.1250, 1.0850, 1.1210))
    t = v[Timeframe.M15][-1].timestamp + timedelta(minutes=15)
    p = CandleProfileAnalyzer().analyze(v, t)
    week_open = trading_week_open(OPEN)
    weeks = arrays([b for b in v[Timeframe.W1] if b.timestamp < week_open], "W1", week_open)
    days = arrays([b for b in v[Timeframe.D1] if b.timestamp < OPEN], "D1", OPEN)
    hours = arrays([b for b in v[Timeframe.H4] if b.timestamp < OPEN], "H4", OPEN)
    link = chain([frame_state(weeks, p.frame_open), frame_state(days, p.frame_open, parents=[weeks], lower=[hours])],
                 ChainRule.PROFILE).links[1]
    assert p.trend == BULL
    assert (link.context, summary(link.draw)) == (p.direction, summary(p.draw))
