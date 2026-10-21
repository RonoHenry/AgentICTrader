"""
Arrays from closed candles under the gap (liquidity-engine Req 26.6, task 343).

The as-of view ends every timeframe above the entry one with its in-progress candle. Under ``fvg_zone = "gap"``
(the trader's reading) the PD arrays are read from closed candles only, so a gap whose third candle is still
forming isn't one yet, and an in-progress candle's running price is not a close that inverts a gap. The
strategy calendar decides what has closed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import BiasDirection, Candle, PDArrayType, Timeframe
from liquidity_engine.utils.time_utils import closed_candles

NY = ZoneInfo("America/New_York")


def ny(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2025, 4, day, hour, minute, tzinfo=NY).astimezone(timezone.utc)


def bar(tf: Timeframe, at: datetime, o: float, h: float, lo: float, c: float) -> Candle:
    return Candle(timestamp=at, open=o, high=h, low=lo, close=c, volume=1, timeframe=tf, instrument="TEST")


def test_closed_candles_follow_the_strategy_calendar():
    d1 = bar(Timeframe.D1, ny(10, 17), 100, 101, 99, 100)                     # Thursday 17:00 to Friday 17:00
    h4 = bar(Timeframe.H4, ny(11, 9), 100, 101, 99, 100)                      # 09:00 to 13:00
    m15 = bar(Timeframe.M15, ny(11, 12, 45), 100, 101, 99, 100)
    view = {Timeframe.D1: [d1], Timeframe.H4: [h4], Timeframe.M15: [m15]}
    at_one = closed_candles(view, ny(11, 13))
    assert at_one[Timeframe.H4] == [h4] and at_one[Timeframe.M15] == [m15] and at_one[Timeframe.D1] == []
    early = closed_candles(view, ny(11, 12, 59))
    assert early[Timeframe.H4] == [] and early[Timeframe.M15] == []
    assert closed_candles(view, ny(11, 17))[Timeframe.D1] == [d1]
    week = bar(Timeframe.W1, datetime(2025, 4, 5, 17, tzinfo=NY).astimezone(timezone.utc), 100, 101, 99, 100)
    assert closed_candles({Timeframe.W1: [week]}, ny(11, 16))[Timeframe.W1] == []     # the week is still open
    assert closed_candles({Timeframe.W1: [week]}, ny(13, 18))[Timeframe.W1] == [week]
    month = bar(Timeframe.MN1, datetime(2025, 3, 31, 17, tzinfo=NY).astimezone(timezone.utc), 100, 101, 99, 100)
    assert closed_candles({Timeframe.MN1: [month]}, ny(29, 12))[Timeframe.MN1] == []
    assert closed_candles({Timeframe.MN1: [month]}, ny(30, 17))[Timeframe.MN1] == [month]


def _view(h1: list[Candle], t: datetime) -> dict[Timeframe, list[Candle]]:
    """An as-of view at ``t`` (11:30 New York, Monday 14 April 2025): closed D1/W1, the given H1 bars (the last
    one in progress), and closed M15 bars up to ``t``."""
    m15 = []
    price = 100.0
    at = t - timedelta(minutes=15 * 40)
    while at < t:
        m15.append(bar(Timeframe.M15, at, price, price + 0.2, price - 0.2, price))
        at += timedelta(minutes=15)
    return {
        Timeframe.W1: [bar(Timeframe.W1, datetime(2025, 4, 5, 17, tzinfo=NY).astimezone(timezone.utc), 95, 106, 94, 100),
                       bar(Timeframe.W1, datetime(2025, 4, 12, 17, tzinfo=NY).astimezone(timezone.utc), 100, 104, 99, 100)],
        Timeframe.D1: [bar(Timeframe.D1, ny(10, 17), 98, 105, 97, 99),
                       bar(Timeframe.D1, ny(13, 17), 99, 104, 98, 100)],
        Timeframe.H1: h1,
        Timeframe.M15: m15,
    }


T = ny(14, 11, 30)


def _arrays(zone: str, h1: list[Candle]):
    return LiquidityMappingEngine(zone).analyze(_view(h1, T), "TEST", T).pd_arrays


def test_a_gap_whose_third_candle_is_still_forming_is_not_one_yet():
    h1 = [bar(Timeframe.H1, ny(14, 8), 99.0, 99.5, 98.5, 99.2),
          bar(Timeframe.H1, ny(14, 9), 99.2, 100.0, 99.0, 99.8),              # C1: high 100
          bar(Timeframe.H1, ny(14, 10), 99.8, 103.0, 99.7, 102.8),             # C2: the displacement
          bar(Timeframe.H1, ny(14, 11), 102.8, 103.5, 101.0, 103.2)]           # C3, in progress: low 101 > 100
    forming = ny(14, 11)
    gap_fvgs = [a for a in _arrays("gap", h1) if a.timeframe == Timeframe.H1 and a.array_type == PDArrayType.FVG]
    assert all(a.formed_at != forming for a in gap_fvgs)
    candle_fvgs = [a for a in _arrays("candles", h1) if a.timeframe == Timeframe.H1 and a.array_type == PDArrayType.FVG]
    assert any(a.formed_at == forming for a in candle_fvgs)                   # the old reading, unchanged


def test_an_in_progress_candle_does_not_invert_a_gap():
    h1 = [bar(Timeframe.H1, ny(14, 7), 99.0, 99.5, 98.5, 99.2),
          bar(Timeframe.H1, ny(14, 8), 99.2, 100.0, 99.0, 99.8),              # C1: high 100
          bar(Timeframe.H1, ny(14, 9), 99.8, 103.0, 99.7, 102.8),
          bar(Timeframe.H1, ny(14, 10), 102.8, 103.5, 101.0, 103.2),           # C3: the gap 100-101, closed
          bar(Timeframe.H1, ny(14, 11), 103.2, 103.3, 98.0, 99.0)]             # in progress, "closing" below 100
    arrays = [a for a in _arrays("gap", h1) if a.timeframe == Timeframe.H1]
    gap = [a for a in arrays if a.array_type == PDArrayType.FVG and a.direction == BiasDirection.BULLISH
           and a.formed_at == ny(14, 10)]
    assert gap and gap[0].low == 100.0 and gap[0].high == 101.0 and not gap[0].is_filled
    assert not [a for a in arrays if a.array_type == PDArrayType.IFVG and a.low == 100.0 and a.high == 101.0]


def test_the_entry_timeframe_reads_the_same_under_both():
    h1 = [bar(Timeframe.H1, ny(14, 9), 99.2, 100.0, 99.0, 99.8)]
    zones = {zone: sorted((a.formed_at, a.array_type.value, a.direction.value)
                          for a in _arrays(zone, h1) if a.timeframe == Timeframe.M15
                          and a.array_type in (PDArrayType.OB, PDArrayType.BREAKER))
             for zone in ("candles", "gap")}
    assert zones["candles"] == zones["gap"]
