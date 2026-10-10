"""
Tests for liquidity_engine.grader.sequence.SetupSequenceDetector.

Task 229 (.kiro/specs/liquidity-engine/tasks.md). A setup is the sequence
raid -> change in state of delivery -> PD array: an opposite-side liquidity
pool is raided and reclaimed, a CISD follows, a PD array forms after the raid,
and the protected swing the raid made stays intact (Requirement 18.1-18.8).

The fixture is one bullish M15 sequence, checked by hand:
- bar 2 is a swing low at 100.0, known from bar 5's open (confirmed by bar 4);
- bar 7 trades to 99.6 and closes back at 100.1: the raid, reclaimed on the same bar;
- bar 8 closes at 101.0, above 100.9, the open of the bearish run 5-7: a bullish CISD;
- bars 8-10 leave a bullish FVG 101.1-101.6, formed at bar 10;
- nothing trades below 99.6 afterwards, so the protected swing (bar 7) holds.
The bearish fixture is its mirror image around 101.
Validates: Requirements 18.1-18.8; Properties 32, 33
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from liquidity_engine.detectors.internal import PDArrayDetector
from liquidity_engine.grader.sequence import SetupSequenceDetector
from liquidity_engine.models import (
    BiasDirection,
    Candle,
    LiquiditySource,
    LiquidityType,
    PDArray,
    PDArrayType,
    Timeframe,
)

UTC = timezone.utc
M15_START = datetime(2024, 1, 2, 6, 0, tzinfo=UTC)

BULLISH_ROWS = [                       # open, high, low, close
    (101.0, 101.5, 100.6, 101.2),      # 0
    (101.2, 101.4, 100.4, 100.8),      # 1
    (100.8, 101.0, 100.0, 100.5),      # 2  swing low 100.0
    (100.5, 100.9, 100.3, 100.7),      # 3
    (100.7, 101.1, 100.5, 100.9),      # 4  confirms bar 2 (and is a swing high at 101.1)
    (100.9, 101.0, 100.6, 100.7),      # 5  bar 2's pool is known from here; bearish run starts
    (100.7, 100.8, 100.2, 100.3),      # 6
    (100.3, 100.4, 99.6, 100.1),       # 7  raid of 100.0, closes back above it
    (100.1, 101.1, 100.0, 101.0),      # 8  bullish CISD: close 101.0 > 100.9
    (101.0, 101.8, 100.9, 101.7),      # 9
    (101.7, 102.2, 101.6, 102.1),      # 10 bullish FVG 101.1-101.6 (bar 8 high, bar 10 low)
    (102.1, 102.3, 101.9, 102.0),      # 11 leg high 102.3
    (102.0, 102.1, 101.7, 101.8),      # 12 retrace; the FVG stays unfilled
]


def m15(i: int) -> datetime:
    return M15_START + timedelta(minutes=15 * i)


def series(rows, tf: Timeframe = Timeframe.M15, start: datetime = M15_START, step: timedelta = None) -> List[Candle]:
    step = step or timedelta(minutes=15)
    return [Candle(timestamp=start + step * i, open=o, high=h, low=lo, close=c, timeframe=tf, instrument="EURUSD")
            for i, (o, h, lo, c) in enumerate(rows)]


def mirror(rows) -> list:
    return [(202 - o, 202 - lo, 202 - h, 202 - c) for o, h, lo, c in rows]


def array(array_id: str, direction: BiasDirection, low: float, high: float, formed: int,
          kind: PDArrayType = PDArrayType.FVG, strength: float = 0.5) -> PDArray:
    return PDArray(array_id=array_id, array_type=kind, direction=direction, timeframe=Timeframe.M15,
                   high=high, low=low, formed_at=m15(formed), strength_score=strength)


BULLISH_FVG = array("fvg", BiasDirection.BULLISH, 101.1, 101.6, 10)
BEARISH_FVG = array("fvg", BiasDirection.BEARISH, 202 - 101.6, 202 - 101.1, 10)


def with_rows(changes: Dict[int, tuple], rows=BULLISH_ROWS) -> list:
    return [changes.get(i, row) for i, row in enumerate(rows)]


def detect(rows=BULLISH_ROWS, arrays=(BULLISH_FVG,), **other_tfs):
    candles_by_tf = {Timeframe.M15: series(rows), **{Timeframe[k]: v for k, v in other_tfs.items()}}
    return SetupSequenceDetector().detect(candles_by_tf, list(arrays))


def day_bars(prev_low: float, prev_high: float = 103.0) -> List[Candle]:
    """D1: the previous day (Jan 1) and the current one (Jan 2), whose bar spans the M15 bars."""
    return series([(101.0, prev_high, prev_low, 101.0), (101.0, 102.3, 99.6, 101.8)], Timeframe.D1,
                  datetime(2024, 1, 1, tzinfo=UTC), timedelta(days=1))


# ── the sequence ───────────────────────────────────────────────────────────

def test_raid_reclaim_cisd_then_array_forms_bullish_sequence():
    seq = detect()
    assert seq is not None and seq.entry_array_id == "fvg" and seq.direction == BiasDirection.BULLISH
    pool = seq.raid.pool
    assert (pool.side, pool.source, pool.timeframe, pool.price) == (
        LiquidityType.SSL, LiquiditySource.SWING_LOW, Timeframe.M15, 100.0)
    assert (pool.formed_at, pool.known_at) == (m15(2), m15(5))
    assert (seq.raid.raided_at, seq.raid.reclaimed_at, seq.cisd_at) == (m15(7), m15(7), m15(8))
    swing = seq.protected_swing
    assert swing.candle_at == m15(7) and (swing.wick, swing.body) == (99.6, 100.1)
    assert swing.candle_range == pytest.approx(0.8)
    assert seq.leg_extreme == 102.3


def test_bearish_sequence_mirrors():
    seq = detect(mirror(BULLISH_ROWS), (BEARISH_FVG,))
    assert seq is not None and seq.direction == BiasDirection.BEARISH
    assert (seq.raid.pool.side, seq.raid.pool.source, seq.raid.pool.price) == (
        LiquidityType.BSL, LiquiditySource.SWING_HIGH, 102.0)
    assert (seq.raid.raided_at, seq.cisd_at) == (m15(7), m15(8))
    assert (seq.protected_swing.wick, seq.protected_swing.body) == (202 - 99.6, 202 - 100.1)
    assert seq.leg_extreme == 202 - 102.3


def test_no_sequence_without_reclaim():
    # Price gaps through an old swing low at 103.0 and never closes back above it: a breakdown,
    # not a sweep, even though a CISD and a bullish FVG follow lower down.
    rows = [
        (104.0, 104.5, 103.6, 104.2), (104.2, 104.4, 103.4, 103.8), (103.8, 104.0, 103.0, 103.5),
        (103.5, 103.9, 103.3, 103.7), (103.7, 104.1, 103.5, 103.9), (103.9, 104.0, 103.6, 103.7),
        (103.7, 103.8, 100.2, 100.3),      # 6 raid of 103.0, closes far below
        (100.3, 100.6, 100.1, 100.5),      # 7
        (100.5, 100.55, 100.0, 100.1),     # 8 bearish run 8-9
        (100.1, 100.2, 99.6, 99.8),        # 9
        (99.8, 100.7, 99.7, 100.6),        # 10 bullish CISD: close 100.6 > 100.5
        (100.6, 101.2, 100.5, 101.1),
        (101.1, 101.5, 100.9, 101.4),      # 12 bullish FVG 100.7-100.9
        (101.4, 101.6, 101.0, 101.2),
    ]
    assert detect(rows, (array("fvg", BiasDirection.BULLISH, 100.7, 100.9, 12),)) is None


def test_no_sequence_without_cisd_after_raid():
    no_cisd = with_rows({8: (100.1, 101.1, 100.0, 100.85)})      # closes below the run's 100.9 open
    assert detect(no_cisd) is None


def test_no_sequence_when_array_formed_before_raid():
    assert detect(arrays=(array("old", BiasDirection.BULLISH, 100.3, 100.5, 3),)) is None


def test_no_sequence_when_protected_swing_broken():
    broken = with_rows({12: (102.0, 102.1, 99.5, 101.8)})        # trades below the 99.6 protected low
    assert detect(broken) is None


def test_no_sequence_for_array_against_the_raid_side():
    # A bearish array needs a BSL raid; the only BSL pool (101.1) is never reclaimed.
    assert detect(arrays=(array("bear", BiasDirection.BEARISH, 101.9, 102.2, 11),)) is None


# ── pools and raids ────────────────────────────────────────────────────────

def test_pools_known_from_the_bar_after_confirmation():
    pools = SetupSequenceDetector().pools({Timeframe.M15: series(BULLISH_ROWS)})
    lows = {(p.price, p.formed_at, p.known_at) for p in pools if p.side == LiquidityType.SSL}
    # Bar 2 (confirmed by bar 4) is known from bar 5; bar 7 (confirmed by bar 9) from bar 10.
    assert lows == {(100.0, m15(2), m15(5)), (99.6, m15(7), m15(10))}
    # Bar 11's high would need bar 13 to confirm it, and bar 14 to be known: not a pool yet.
    assert {p.price for p in pools if p.side == LiquidityType.BSL} == {101.1}


def test_htf_swing_and_previous_day_low_are_pools():
    h1 = series([(101.0, 101.5, 100.9, 101.2), (101.2, 101.3, 100.7, 100.8), (100.8, 101.0, 100.5, 100.9),
                 (100.9, 101.4, 100.8, 101.3), (101.3, 101.6, 101.0, 101.5), (101.5, 101.7, 101.2, 101.6)],
                Timeframe.H1, datetime(2024, 1, 1, 18, tzinfo=UTC), timedelta(hours=1))
    pools = SetupSequenceDetector().pools({Timeframe.M15: series(BULLISH_ROWS), Timeframe.H1: h1,
                                           Timeframe.D1: day_bars(prev_low=99.9)})
    by_source = {(p.source, p.timeframe): p for p in pools}
    pdl = by_source[(LiquiditySource.PDL, Timeframe.D1)]
    assert (pdl.price, pdl.formed_at, pdl.known_at) == (99.9, datetime(2024, 1, 1, tzinfo=UTC),
                                                         datetime(2024, 1, 2, tzinfo=UTC))
    h1_low = by_source[(LiquiditySource.SWING_LOW, Timeframe.H1)]
    assert (h1_low.price, h1_low.known_at) == (100.5, datetime(2024, 1, 1, 23, tzinfo=UTC))
    assert by_source[(LiquiditySource.PDH, Timeframe.D1)].side == LiquidityType.BSL


def test_same_bar_raid_prefers_the_higher_timeframe_pool():
    seq = detect(D1=day_bars(prev_low=99.9))          # bar 7 takes both the M15 swing (100.0) and the PDL (99.9)
    assert (seq.raid.pool.source, seq.raid.pool.timeframe, seq.raid.raided_at) == (
        LiquiditySource.PDL, Timeframe.D1, m15(7))


def test_pool_taken_before_raid_bar_is_not_raided():
    # An H1 bar that closed before bar 7 already traded below the PDL: it was taken, not raided at bar 7.
    h1 = series([(100.5, 100.8, 99.8, 100.4), (100.4, 100.9, 100.3, 100.8)], Timeframe.H1,
                datetime(2024, 1, 2, 2, tzinfo=UTC), timedelta(hours=1))
    seq = detect(D1=day_bars(prev_low=99.9), H1=h1)
    assert seq.raid.pool.source == LiquiditySource.SWING_LOW


def test_most_recent_raid_beats_pool_weight():
    # The previous week's low (100.25, W1) is raided at bar 2 and reclaimed; the M15 swing low
    # is raided later, at bar 7. Both lead to the FVG: the more recent raid wins.
    w1 = series([(101.0, 103.0, 100.25, 101.0), (101.0, 102.3, 99.6, 101.8)], Timeframe.W1,
                datetime(2023, 12, 25, tzinfo=UTC), timedelta(weeks=1))
    seq = detect(W1=w1)
    assert (seq.raid.pool.source, seq.raid.raided_at) == (LiquiditySource.SWING_LOW, m15(7))


def test_protected_swing_is_extreme_from_raid_to_array():
    deeper = with_rows({9: (101.0, 101.8, 99.5, 101.7)})          # bar 9 dips below the raid bar's low
    swing = detect(deeper).protected_swing
    assert (swing.candle_at, swing.wick, swing.body) == (m15(9), 99.5, 101.0)


# ── choosing among arrays ──────────────────────────────────────────────────

def test_selection_order_across_arrays():
    ob = array("ob", BiasDirection.BULLISH, 99.6, 100.4, 7, PDArrayType.OB, strength=0.7)
    assert detect(arrays=(BULLISH_FVG, ob)).entry_array_id == "ob"           # same raid: stronger array
    twin = array("fvg-2", BiasDirection.BULLISH, 101.0, 101.5, 9)
    assert detect(arrays=(twin, BULLISH_FVG)).entry_array_id == "fvg"        # same strength: formed later
    filled = BULLISH_FVG.model_copy(update={"is_filled": True})
    assert detect(arrays=(filled,)) is None                                  # filled arrays aren't entries
    h1_array = BULLISH_FVG.model_copy(update={"timeframe": Timeframe.H1})
    assert detect(arrays=(h1_array,)) is None                                # nor are arrays above M15


# ── properties ─────────────────────────────────────────────────────────────

walks = st.lists(st.tuples(st.floats(-1.0, 1.0), st.floats(0.0, 0.6), st.floats(0.0, 0.6)), min_size=20, max_size=60)


def walk(steps) -> List[Candle]:
    rows, price = [], 100.0
    for move, up, down in steps:
        close = round(price + move, 4)
        rows.append((price, round(max(price, close) + up, 4), round(min(price, close) - down, 4), close))
        price = close
    return series(rows)


@settings(max_examples=60, deadline=None)
@given(walks)
def test_property_raid_integrity(steps):
    """Property 32: the raided pool was known and intact up to the raid, and the array formed after it."""
    candles = walk(steps)
    arrays = PDArrayDetector().detect({Timeframe.M15: candles}, {})
    seq = SetupSequenceDetector().detect({Timeframe.M15: candles}, arrays)
    if seq is None:
        return
    pool, raid = seq.raid.pool, seq.raid
    assert raid.raided_at >= pool.known_at
    beyond = (lambda c: c.low < pool.price) if pool.side == LiquidityType.SSL else (lambda c: c.high > pool.price)
    assert not any(beyond(c) for c in candles if pool.known_at <= c.timestamp < raid.raided_at)
    assert beyond(next(c for c in candles if c.timestamp == raid.raided_at))
    entry = next(a for a in arrays if a.array_id == seq.entry_array_id)
    assert entry.formed_at >= raid.raided_at and not entry.is_filled
    assert raid.raided_at <= raid.reclaimed_at and raid.raided_at < seq.cisd_at


@settings(max_examples=60, deadline=None)
@given(walks, st.integers(5, 60))
def test_property_no_lookahead(steps, cut):
    """Property 33: what is known by a bar doesn't depend on later bars, and a sequence found on a
    prefix uses only that prefix."""
    full = walk(steps)
    prefix = full[:cut]
    detector = SetupSequenceDetector()
    last_open = prefix[-1].timestamp

    def key(p):
        return p.timeframe.value, p.formed_at, p.side.value, p.price

    known_by_then = sorted((p for p in detector.pools({Timeframe.M15: full}) if p.known_at <= last_open), key=key)
    assert sorted(detector.pools({Timeframe.M15: prefix}), key=key) == known_by_then
    seq = detector.detect({Timeframe.M15: prefix}, PDArrayDetector().detect({Timeframe.M15: prefix}, {}))
    if seq is not None:
        assert max(seq.raid.raided_at, seq.raid.reclaimed_at, seq.cisd_at, seq.protected_swing.candle_at) <= last_open


# ── Asian range pools (Requirement 20.2, task 235) ─────────────────────────
#
# Trading day Tuesday 2024-01-09 (EST): opens Monday 17:00 New York = 22:00 UTC.
# The Asian session, 20:00-00:00 New York, is the H1 bars at 01:00-04:00 UTC;
# its pools are known from midnight New York, 05:00 UTC. In July (EDT) every
# New York time is an hour earlier in UTC.

def asia_day(day_open: datetime, drop_session: bool = False) -> List[Candle]:
    """24 H1 bars from the day's open. Bars 3-6 are the Asian session: high 101.4 (bar 4), low 99.9 (bar 5).
    Bar 1 (18:00 New York) is wider still, outside the session."""
    rows = [(100.5, 100.8, 100.2, 100.5)] * 24
    rows[1] = (100.5, 102.0, 99.0, 100.5)
    rows[3:7] = [(100.5, 101.0, 100.3, 100.6), (100.6, 101.4, 100.4, 101.0),
                 (101.0, 101.1, 99.9, 100.2), (100.2, 100.7, 100.1, 100.5)]
    bars = series(rows, Timeframe.H1, day_open, timedelta(hours=1))
    return [b for i, b in enumerate(bars) if not (drop_session and 3 <= i <= 6)]


WINTER_OPEN = datetime(2024, 1, 8, 22, tzinfo=UTC)       # 17:00 EST
SUMMER_OPEN = datetime(2024, 7, 8, 21, tzinfo=UTC)       # 17:00 EDT


def closed_by(bars: List[Candle], as_of: datetime) -> List[Candle]:
    return [b for b in bars if b.timestamp + timedelta(hours=1) <= as_of]


def asia_pools(bars: List[Candle], as_of):
    pools = SetupSequenceDetector().pools({Timeframe.H1: bars}, as_of=as_of)
    return {p.source: p for p in pools if p.source in (LiquiditySource.ASIA_HIGH, LiquiditySource.ASIA_LOW)}


def test_asian_pools_from_the_session_h1_bars():
    as_of = WINTER_OPEN + timedelta(hours=8)                      # 01:00 New York
    pools = asia_pools(closed_by(asia_day(WINTER_OPEN), as_of), as_of)
    high, low = pools[LiquiditySource.ASIA_HIGH], pools[LiquiditySource.ASIA_LOW]
    midnight = datetime(2024, 1, 9, 5, tzinfo=UTC)
    assert (high.side, high.timeframe, high.price, high.formed_at, high.known_at) == (
        LiquidityType.BSL, Timeframe.H1, 101.4, datetime(2024, 1, 9, 2, tzinfo=UTC), midnight)
    assert (low.side, low.timeframe, low.price, low.formed_at, low.known_at) == (
        LiquidityType.SSL, Timeframe.H1, 99.9, datetime(2024, 1, 9, 3, tzinfo=UTC), midnight)


def test_no_asian_pools_before_midnight_or_without_a_time():
    bars = asia_day(WINTER_OPEN)
    before = WINTER_OPEN + timedelta(hours=6, minutes=30)         # 23:30 New York
    assert asia_pools(closed_by(bars, before), before) == {}
    assert asia_pools(closed_by(bars, WINTER_OPEN + timedelta(hours=8)), None) == {}


def test_no_asian_pools_without_session_bars():
    as_of = WINTER_OPEN + timedelta(hours=8)
    assert asia_pools(closed_by(asia_day(WINTER_OPEN, drop_session=True), as_of), as_of) == {}


def test_asian_pools_belong_to_the_current_day_only():
    # 17:30 New York: a new trading day, whose session hasn't happened yet.
    as_of = WINTER_OPEN + timedelta(hours=24, minutes=30)
    assert asia_pools(closed_by(asia_day(WINTER_OPEN), as_of), as_of) == {}


def test_asia_low_raid_starts_a_bullish_sequence():
    # BULLISH_ROWS from midnight New York: bar 7 trades to 99.6, through the M15 swing low (100.0)
    # and the Asian low (99.9). On the same bar the heavier pool wins: the H1 Asian low.
    start = datetime(2024, 1, 9, 5, tzinfo=UTC)
    m15_bars = series(BULLISH_ROWS, start=start)
    session = [b for b in asia_day(WINTER_OPEN) if datetime(2024, 1, 9, 1, tzinfo=UTC) <= b.timestamp < start]
    fvg = BULLISH_FVG.model_copy(update={"formed_at": start + timedelta(minutes=150)})
    seq = SetupSequenceDetector().detect({Timeframe.M15: m15_bars, Timeframe.H1: session}, [fvg],
                                         as_of=start + timedelta(minutes=195))
    assert seq is not None and seq.direction == BiasDirection.BULLISH
    assert (seq.raid.pool.source, seq.raid.pool.price, seq.raid.raided_at) == (
        LiquiditySource.ASIA_LOW, 99.9, start + timedelta(minutes=105))


@settings(max_examples=80, deadline=None)
@given(st.sampled_from([WINTER_OPEN, SUMMER_OPEN]), st.integers(0, 24 * 60 - 1))
def test_property_asian_pools_after_the_session(day_open, minutes):
    """Property 39: before midnight New York the day has no Asian pool; from then on both are
    known, from midnight."""
    as_of = day_open + timedelta(minutes=minutes)
    midnight = day_open + timedelta(hours=7)
    pools = asia_pools(closed_by(asia_day(day_open), as_of), as_of)
    if as_of < midnight:
        assert pools == {}
    else:
        assert set(pools) == {LiquiditySource.ASIA_HIGH, LiquiditySource.ASIA_LOW}
        assert {p.known_at for p in pools.values()} == {midnight}
        assert (pools[LiquiditySource.ASIA_HIGH].price, pools[LiquiditySource.ASIA_LOW].price) == (101.4, 99.9)
