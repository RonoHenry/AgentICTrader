"""
Tests for liquidity_engine.profile.candle_profile.CandleProfileAnalyzer.

Task 236 (.kiro/specs/liquidity-engine/tasks.md). At each D1 open (17:00 New
York) the analyzer anticipates how the candle will form, from bars that
closed by that open only (decisions LE-D9, LE-D10, LE-D15):
- objectives: untaken H4/D1/W1 swing pools, the previous day and week high
  and low, and unfilled H4/D1/W1 FVGs at their near edge;
- trend: the last closed W1 candle closed beyond the previous one's range;
- direction: the trend when trending (drawn to a W1 objective), otherwise
  toward the nearer objective.

Task 237 adds what the candle has done so far: its false move, the Asian
raid on that side, its low and high, the manipulation window (01:00 to
13:00 New York) and the trading weekday (Requirement 22).

The hand-built context: the trading day Wednesday 2024-01-10 (EST) opens
Tuesday 17:00 New York = 22:00 UTC. Its week opened Saturday 17:00 New York
(2024-01-06 22:00 UTC), the label the strategy calendar gives W1 bars.
Validates: Requirements 21.1-21.6, 22.1-22.3; Properties 35, 36
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from liquidity_engine.models import (
    BiasDirection, Candle, LiquidityPool, LiquidityRaid, LiquiditySource, LiquidityType, Objective,
    ProtectedSwing, SetupSequence, Timeframe,
)
from liquidity_engine.profile.candle_profile import CandleProfileAnalyzer, nearest_objectives
from services.market_data.as_of_view import aggregate
from services.market_data.strategy_calendar import StrategyCalendar

UTC = timezone.utc
CAL = StrategyCalendar()
OPEN = datetime(2024, 1, 9, 22, tzinfo=UTC)          # Tuesday 17:00 EST: Wednesday's D1 candle
WEEK = datetime(2024, 1, 6, 22, tzinfo=UTC)          # Saturday 17:00 EST: the current W1 period
MIDNIGHT = datetime(2024, 1, 10, 5, tzinfo=UTC)      # 00:00 EST
H4, D1 = timedelta(hours=4), timedelta(days=1)
FLAT = (1.1000, 1.1010, 1.0990, 1.1000)


def bars(rows, tf: Timeframe, start: datetime, step: timedelta) -> List[Candle]:
    return [Candle(timestamp=start + step * i, open=o, high=h, low=lo, close=c, timeframe=tf, instrument="EURUSD")
            for i, (o, h, lo, c) in enumerate(rows)]


def context(last_w=(1.1000, 1.1150, 1.0850, 1.1000), prev_w=(1.1000, 1.1200, 1.0800, 1.1000),
            week_d1=((1.1000, 1.1060, 1.0960, 1.1000), (1.1000, 1.1040, 1.0980, 1.1000)),
            frame_open=1.1000, m15_rows=((1.1000, 1.1005, 1.0995, 1.1000),) * 4,
            t: Optional[datetime] = None, open_time: datetime = OPEN,
            h1: List[Candle] = ()) -> Dict[Timeframe, List[Candle]]:
    """Two closed weeks, this week's closed days (Monday, Tuesday), six flat H4 bars of Tuesday,
    and the forming D1/W1/H4 bars from the frame open, built from M15 bars that closed by t."""
    OPEN, WEEK = open_time, CAL.period_start(open_time, Timeframe.W1)  # noqa: N806 (the module's by default)
    m15 = bars(m15_rows, Timeframe.M15, OPEN, timedelta(minutes=15))
    m15[0] = m15[0].model_copy(update={"open": frame_open, "high": max(frame_open, m15[0].high),
                                       "low": min(frame_open, m15[0].low)})
    t = t or m15[-1].timestamp + timedelta(minutes=15)
    m15 = [b for b in m15 if b.timestamp + timedelta(minutes=15) <= t]
    day_bars = bars(week_d1, Timeframe.D1, OPEN - D1 * len(week_d1), D1)
    h4 = bars([FLAT] * 6, Timeframe.H4, OPEN - D1, H4)
    weeks = bars([prev_w, last_w], Timeframe.W1, WEEK - timedelta(weeks=2), timedelta(weeks=1))
    forming = (lambda tf, start, before: [combine(before + m15, tf, start)] if before + m15 else [])
    return {
        Timeframe.W1: weeks + forming(Timeframe.W1, WEEK, day_bars),
        Timeframe.D1: day_bars + forming(Timeframe.D1, OPEN, []),
        Timeframe.H4: h4 + forming(Timeframe.H4, OPEN, []),
        Timeframe.M15: m15,
        **({Timeframe.H1: [b for b in h1 if b.timestamp + timedelta(hours=1) <= t]} if h1 else {}),
    }


def combine(group: List[Candle], tf: Timeframe, start: datetime) -> Candle:
    return Candle(timestamp=start, open=group[0].open, high=max(b.high for b in group),
                  low=min(b.low for b in group), close=group[-1].close, timeframe=tf, instrument="EURUSD")


def profile(sequence: Optional[SetupSequence] = None, **kwargs):
    candles = context(**kwargs)
    t = kwargs.get("t") or candles[Timeframe.M15][-1].timestamp + timedelta(minutes=15)
    return CandleProfileAnalyzer().analyze(candles, t, sequence)


def summary(objective: Optional[Objective]):
    return None if objective is None else (objective.source, objective.timeframe, objective.price)


# ── the frame ──────────────────────────────────────────────────────────────

def test_frame_open_is_the_17_00_open():
    p = profile(frame_open=1.1003)
    assert (p.frame_tf, p.open_time, p.frame_open) == (Timeframe.D1, OPEN, 1.1003)


def test_midnight_open_recorded_from_midnight_on():
    assert profile().midnight_open is None                       # 18:00 New York
    rows = [(1.1000, 1.1005, 1.0995, 1.1000)] * 28 + [(1.1012, 1.1020, 1.1010, 1.1015)] * 2
    p = profile(m15_rows=rows)                                    # bar 28 opens at 00:00 New York
    assert p.midnight_open == 1.1012


def test_none_without_two_closed_weeks_or_a_frame_bar():
    candles = context()
    t = candles[Timeframe.M15][-1].timestamp + timedelta(minutes=15)
    short = {**candles, Timeframe.W1: candles[Timeframe.W1][1:]}          # one closed week
    assert CandleProfileAnalyzer().analyze(short, t) is None
    no_frame = {**candles, Timeframe.D1: candles[Timeframe.D1][:-1]}      # no D1 bar at the open
    assert CandleProfileAnalyzer().analyze(no_frame, t) is None


# ── objectives ─────────────────────────────────────────────────────────────

H4_ROWS = [
    FLAT, FLAT,
    (1.1015, 1.1020, 1.1015, 1.1018),      # 2  bullish FVG 1.1010-1.1015 over bars 0-2; bar 3 trades into it
    (1.1000, 1.1060, 1.0990, 1.1000),      # 3  swing high 1.1060, taken by bar 8
    FLAT,
    (1.1000, 1.1010, 1.0950, 1.1000),      # 5  swing low 1.0950, untaken
    FLAT, FLAT,
    (1.1000, 1.1070, 1.0990, 1.1000),      # 8  swing high 1.1070, untaken
    (1.1000, 1.1010, 1.0990, 1.0995),      # 9
    (1.0995, 1.0995, 1.0975, 1.0980),      # 10
    (1.0980, 1.0985, 1.0970, 1.0975),      # 11 bearish FVG 1.0985-1.0990 over bars 9-11, unfilled
]


def h4_objectives(extra_after_open=()):
    start = OPEN - H4 * len(H4_ROWS)
    h4 = bars(H4_ROWS, Timeframe.H4, start, H4) + bars(extra_after_open, Timeframe.H4, OPEN, H4)
    found = CandleProfileAnalyzer().objectives({Timeframe.H4: h4}, OPEN)
    return {(o.kind, o.source, o.price, o.direction, o.formed_at) for o in found}, start


def test_untaken_pools_and_unfilled_fvgs_only():
    found, start = h4_objectives()
    assert found == {
        ("POOL", "SWING_LOW", 1.0950, BiasDirection.BEARISH, start + 5 * H4),
        ("POOL", "SWING_HIGH", 1.1070, BiasDirection.BULLISH, start + 8 * H4),
        ("FVG", "FVG", 1.0985, BiasDirection.BULLISH, start + 11 * H4),   # near edge: the gap's bottom, above
    }


def test_bars_from_the_open_on_are_ignored():
    # A bar after the open that takes every high and fills every gap changes nothing.
    assert h4_objectives(extra_after_open=[(1.0975, 1.1500, 1.0500, 1.1000)])[0] == h4_objectives()[0]


def test_previous_day_and_week_are_pools():
    found = CandleProfileAnalyzer().objectives(context(), OPEN)
    by_source = {(o.source, o.timeframe): o.price for o in found}
    assert by_source[("PDH", Timeframe.D1)] == 1.1040 and by_source[("PDL", Timeframe.D1)] == 1.0980
    assert by_source[("PWH", Timeframe.W1)] == 1.1150 and by_source[("PWL", Timeframe.W1)] == 1.0850


def objective(price, direction, tf=Timeframe.H4, source="SWING_HIGH", kind="POOL"):
    return Objective(kind=kind, source=source, timeframe=tf, price=price, direction=direction, formed_at=OPEN - D1)


def test_nearest_objective_each_side_with_ties_to_the_higher_timeframe():
    up, down = BiasDirection.BULLISH, BiasDirection.BEARISH
    objectives = [
        objective(1.1040, up), objective(1.1040, up, Timeframe.D1, "PDH"), objective(1.1080, up, Timeframe.W1, "PWH"),
        objective(1.0950, down, source="SWING_LOW"), objective(1.0970, down, Timeframe.D1, "PDL"),
        objective(1.1020, down, source="SWING_LOW"),       # a sell-side pool above the open: not an objective
    ]
    above, below = nearest_objectives(objectives, 1.1000)
    assert summary(above) == ("PDH", Timeframe.D1, 1.1040)
    assert summary(below) == ("PDL", Timeframe.D1, 1.0970)
    assert nearest_objectives([], 1.1000) == (None, None)


# ── trend and direction ────────────────────────────────────────────────────

def test_not_trending_goes_to_the_nearer_objective():
    p = profile()                                            # last week inside the previous one
    assert p.trend == BiasDirection.NEUTRAL
    assert summary(p.draw_above) == ("PDH", Timeframe.D1, 1.1040)
    assert summary(p.draw_below) == ("PDL", Timeframe.D1, 1.0980)
    assert p.direction == BiasDirection.BEARISH and summary(p.draw) == ("PDL", Timeframe.D1, 1.0980)


def test_trending_follows_the_trend_to_a_weekly_objective():
    p = profile(last_w=(1.1000, 1.1250, 1.0850, 1.1210))    # closed above the previous week's 1.1200 high
    assert p.trend == BiasDirection.BULLISH
    assert p.direction == BiasDirection.BULLISH and summary(p.draw) == ("PWH", Timeframe.W1, 1.1250)

    p = profile(last_w=(1.1000, 1.1150, 1.0750, 1.0790))    # closed below the previous week's 1.0800 low
    assert p.trend == BiasDirection.BEARISH
    assert p.direction == BiasDirection.BEARISH and summary(p.draw) == ("PWL", Timeframe.W1, 1.0750)


def test_trending_without_a_weekly_objective_takes_the_nearest():
    # Monday traded above last week's high: PWH is taken, so the draw is the nearest objective above.
    p = profile(last_w=(1.1000, 1.1250, 1.0850, 1.1210),
                week_d1=((1.1000, 1.1300, 1.0960, 1.1000), (1.1000, 1.1040, 1.0980, 1.1000)))
    assert p.direction == BiasDirection.BULLISH and summary(p.draw) == ("PDH", Timeframe.D1, 1.1040)


def test_neutral_when_the_chosen_side_has_no_objective():
    p = profile(last_w=(1.1000, 1.1250, 1.0850, 1.1210), frame_open=1.2000)   # opened above every objective
    assert p.draw_above is None and p.direction == BiasDirection.NEUTRAL and p.draw is None


# ── properties ─────────────────────────────────────────────────────────────

# Six to eight weeks of H4 bars, drawn from a seed: lists that long trip Hypothesis's size check.
steps = st.builds(lambda seed, weeks: [(r.uniform(-0.004, 0.004), r.uniform(0, 0.003), r.uniform(0, 0.003))
                                       for r in [random.Random(seed)] for _ in range(6 * 7 * weeks)],
                  st.integers(0, 2**32), st.integers(6, 8))
FIRST = datetime(2023, 11, 11, 22, tzinfo=UTC)              # a Saturday 17:00 EST (after the DST change): a W1 boundary


def walk(moves, start=FIRST, price=1.1000) -> List[Candle]:
    rows = []
    for move, up, down in moves:
        close = round(price + move, 5)
        rows.append((price, round(max(price, close) + up, 5), round(min(price, close) - down, 5), close))
        price = close
    return bars(rows, Timeframe.H4, start, H4)


def view(h4: List[Candle], t: datetime) -> Dict[Timeframe, List[Candle]]:
    """What the engine sees at t: H4 bars closed by t, and D1/W1 closed bars plus the forming one."""
    known = [b for b in h4 if b.timestamp + H4 <= t]
    out = {Timeframe.H4: known}
    for tf in (Timeframe.D1, Timeframe.W1):
        start = CAL.period_start(t, tf)
        current = [b for b in known if b.timestamp >= start]
        out[tf] = aggregate(known, tf, CAL, as_of=start) + ([combine(current, tf, start)] if current else [])
    return out


def anticipation(p):
    return None if p is None else (p.trend, p.direction, p.draw, p.draw_above, p.draw_below, p.frame_open)


@settings(max_examples=40, deadline=None)
@given(steps, st.integers(1, 5), st.integers(1, 5), st.lists(st.floats(-0.01, 0.01), min_size=6, max_size=6))
def test_property_35_anticipation_without_lookahead(moves, i, j, later):
    """The anticipation is the same at every t within the candle, whatever happens after the open."""
    h4 = walk(moves)
    open_time = CAL.period_start(h4[-1].timestamp, Timeframe.D1) - D1     # a candle with six H4 bars after it
    first_after = next(k for k, b in enumerate(h4) if b.timestamp >= open_time)
    analyzer = CandleProfileAnalyzer()
    p_i = analyzer.analyze(view(h4, open_time + H4 * i), open_time + H4 * i)
    p_j = analyzer.analyze(view(h4, open_time + H4 * j), open_time + H4 * j)
    assert anticipation(p_i) == anticipation(p_j)

    # Different bars after the first one of the candle: the same anticipation.
    rewritten = h4[:first_after + 1] + walk([(m, 0.001, 0.001) for m in later], h4[first_after].timestamp + H4,
                                            h4[first_after].close)
    t = open_time + H4 * 5
    assert anticipation(analyzer.analyze(view(rewritten, t), t)) == anticipation(analyzer.analyze(view(h4, t), t))


@settings(max_examples=40, deadline=None)
@given(steps, st.integers(1, 5))
def test_property_36_draw_ordering(moves, i):
    h4 = walk(moves)
    open_time = CAL.period_start(h4[-1].timestamp, Timeframe.D1) - D1
    t = open_time + H4 * i
    p = CandleProfileAnalyzer().analyze(view(h4, t), t)
    if p is None:
        return
    if p.draw_above is not None:
        assert p.draw_above.price > p.frame_open and p.draw_above.direction == BiasDirection.BULLISH
    if p.draw_below is not None:
        assert p.draw_below.price < p.frame_open and p.draw_below.direction == BiasDirection.BEARISH
    if p.direction == BiasDirection.BULLISH:
        assert p.draw is not None and p.draw.price > p.frame_open
    elif p.direction == BiasDirection.BEARISH:
        assert p.draw is not None and p.draw.price < p.frame_open
    else:
        assert p.draw is None


# ── false move, manipulation window, weekday (Requirement 22, task 237) ────

BULL = {"last_w": (1.1000, 1.1250, 1.0850, 1.1210)}          # trending up: anticipates a bullish candle
BEAR = {"last_w": (1.1000, 1.1150, 1.0750, 1.0790)}          # trending down
QUIET = (1.1002, 1.1008, 1.1001, 1.1004)                     # above the 1.1000 open all day
M15 = timedelta(minutes=15)


def day(**changes) -> list:
    """95 M15 rows, to 16:45 New York: the candle bar the last one closes in; changes["i40"] replaces bar 40."""
    rows = [QUIET] * 95
    for key, row in changes.items():
        rows[int(key[1:])] = row
    return rows


def asia(open_time: datetime = OPEN) -> List[Candle]:
    """The Asian session, 20:00-23:00 New York: high 1.1012, low 1.0992."""
    return bars([(1.1003, 1.1012, 1.0992, 1.1004)] * 4, Timeframe.H1, open_time + timedelta(hours=3),
                timedelta(hours=1))


def test_false_move_is_a_trade_beyond_the_open_against_the_direction():
    assert profile(m15_rows=day(), **BULL).false_move_taken is False                 # never below the open
    dipped = profile(m15_rows=day(i10=(1.1002, 1.1004, 1.0997, 1.1003)), **BULL)
    assert dipped.direction == BiasDirection.BULLISH and dipped.false_move_taken is True
    assert profile(m15_rows=day(), **BEAR).false_move_taken is True                  # traded above the open
    below = (1.0998, 1.0999, 1.0992, 1.0996)
    assert profile(m15_rows=[below] * 95, frame_open=1.0999, **BEAR).false_move_taken is False
    neutral = profile(m15_rows=day(i10=(1.1002, 1.1004, 1.0997, 1.1003)), frame_open=1.2000, **BULL)
    assert neutral.direction == BiasDirection.NEUTRAL and neutral.false_move_taken is False


def test_asia_raid_on_the_false_move_side_after_midnight():
    raid = profile(m15_rows=day(i40=(1.1002, 1.1004, 1.0990, 1.1003)), h1=asia(), **BULL)   # 03:00 New York
    assert raid.asia_raided is True
    shallow = profile(m15_rows=day(i40=(1.1002, 1.1004, 1.0995, 1.1003)), h1=asia(), **BULL)
    assert shallow.false_move_taken is True and shallow.asia_raided is False      # below the open, not the Asian low
    early = profile(m15_rows=day(i40=(1.1002, 1.1004, 1.0990, 1.1003)), h1=asia(), t=OPEN + 26 * M15, **BULL)
    assert early.asia_raided is False                                              # 23:30 New York: no Asian pools yet
    above = profile(m15_rows=day(i40=(1.1002, 1.1015, 1.1001, 1.1003)), h1=asia(), **BEAR)
    assert above.asia_raided is True                                               # bearish: the Asian high
    assert profile(m15_rows=day(i40=(1.1002, 1.1004, 1.0990, 1.1003)), **BULL).asia_raided is False   # no H1


def test_candle_low_and_high_so_far():
    rows = day(i10=(1.1002, 1.1004, 1.0997, 1.1003), i50=(1.1004, 1.1030, 1.1003, 1.1010))
    p = profile(m15_rows=rows, t=OPEN + 60 * M15, **BULL)
    assert (p.candle_low, p.candle_low_at, p.candle_high, p.candle_high_at) == (
        1.0997, OPEN + 10 * M15, 1.1030, OPEN + 50 * M15)
    earlier = profile(m15_rows=rows, t=OPEN + 40 * M15, **BULL)
    assert (earlier.candle_high, earlier.candle_high_at) == (1.1008, OPEN)       # the first bar to reach it


def sequence(raided_at: datetime) -> SetupSequence:
    pool = LiquidityPool(side=LiquidityType.SSL, source=LiquiditySource.ASIA_LOW, timeframe=Timeframe.H1,
                         price=1.0992, formed_at=raided_at - timedelta(hours=2), known_at=raided_at - M15)
    return SetupSequence(
        entry_array_id="fvg", direction=BiasDirection.BULLISH,
        raid=LiquidityRaid(pool=pool, raided_at=raided_at, reclaimed_at=raided_at), cisd_at=raided_at + M15,
        protected_swing=ProtectedSwing(candle_at=raided_at, wick=1.0990, body=1.0995, candle_range=0.001),
        leg_extreme=1.1050)


@pytest.mark.parametrize("open_time", [OPEN, datetime(2024, 7, 9, 21, tzinfo=UTC)], ids=["EST", "EDT"])
def test_manipulation_window_edges(open_time):
    one, thirteen = open_time + timedelta(hours=8), open_time + timedelta(hours=20)     # 01:00 and 13:00 New York

    def window(t, raided_at=None):
        p = profile(m15_rows=day(), open_time=open_time, t=t, sequence=raided_at and sequence(raided_at), **BULL)
        return p.in_window, p.raid_in_window

    assert window(one - timedelta(minutes=1)) == (False, False)
    assert window(one, raided_at=one) == (True, True)
    assert window(one + M15, raided_at=one - M15) == (True, False)            # raid bar opened at 00:45
    assert window(thirteen - timedelta(minutes=1), raided_at=thirteen - M15) == (True, True)
    assert window(thirteen, raided_at=thirteen) == (False, False)
    assert window(one + M15, raided_at=one - timedelta(days=1)) == (True, False)   # yesterday's window


@pytest.mark.parametrize("open_time, weekday", [
    (datetime(2024, 1, 7, 22, tzinfo=UTC), 0),       # Sunday 17:00 opens Monday
    (OPEN, 2),                                        # Tuesday 17:00 opens Wednesday
    (datetime(2024, 1, 11, 22, tzinfo=UTC), 4),      # Thursday 17:00 opens Friday
])
def test_weekday_is_the_trading_day(open_time, weekday):
    assert profile(open_time=open_time).weekday == weekday
