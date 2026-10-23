"""The trader's trend (context-engine Requirement 20, task 355): five signals per closed candle of a frame."""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.trend import trend_signals

T0 = pd.Timestamp("2025-01-06 00:00", tz="UTC")


def bars(rows):
    """Hourly candles from (open, high, low, close) rows."""
    o, h, l, c = (np.array(x, dtype=float) for x in zip(*rows))
    t = pd.date_range(T0, periods=len(rows), freq="1h")
    return pd.DataFrame({"time": t, "close_time": t + pd.Timedelta(hours=1), "open": o, "high": h, "low": l,
                         "close": c})


def flat(n, price=100.0):
    return [(price, price + 0.5, price - 0.5, price)] * n


DOWN = [(100, 101, 99, 100), (101, 105, 100, 104), (103, 104, 101, 102), (101, 102, 98, 99),
        (99, 100.5, 98.8, 100), (100, 103, 99, 102), (101, 102, 97, 98), (97, 98, 96, 97), (97, 99, 96.5, 98),
        (98, 98.5, 97, 97.5)]                                  # swing highs 105, 103, 99; swing lows 98, 96


def test_lower_highs_and_lower_lows_read_bearish_structure():
    # Swing highs at 105 then 103 and swing lows at 98 then 96: lower highs and lower lows.
    down = DOWN
    assert trend_signals(bars(down))["structure"].iloc[-1] == -1
    up = [(200 - o, 200 - l, 200 - h, 200 - c) for o, h, l, c in down]          # the mirror
    assert trend_signals(bars(up))["structure"].iloc[-1] == 1
    mixed = down[:6] + [(101, 106, 100, 105), (105, 105.5, 97, 98), (98, 99, 96, 97), (97, 99, 96.5, 98)]
    assert trend_signals(bars(mixed))["structure"].iloc[-1] == 0                 # a higher high, a lower low


def test_a_down_close_with_two_of_the_last_three_down_is_a_bearish_close():
    s = trend_signals(bars(flat(3) + [(100, 101, 98, 99), (99, 101, 98.5, 100.5), (100.5, 101, 98, 99)]))
    assert list(s["closes"].iloc[-3:]) == [0, 0, -1]          # the last: down, after down and up
    s = trend_signals(bars(flat(3) + [(100, 101, 98, 99), (99, 100, 97, 98), (98, 100, 97.5, 99.5)]))
    assert s["closes"].iloc[-1] == 0                           # the last closed up, against two down


def test_a_failed_sweep_of_buy_side_liquidity_is_bearish_until_a_close_above_its_wick():
    rows = [(100, 101, 99, 100), (100, 103, 99.5, 102), (102, 102.5, 100, 101), (101, 101.5, 100, 100.5),
            (100.5, 104, 100, 102.5),                          # trades above the 103 swing high, closes below it
            (102.5, 103, 101, 101.5), (101.5, 102, 100.5, 101),
            (101, 104.5, 100.8, 104.2)]                        # closes above the sweep's wick (104)
    s = trend_signals(bars(rows))
    assert list(s["liquidity"]) == [0, 0, 0, 0, -1, -1, -1, 0]


def test_arrays_respected_and_traded_through_by_side():
    rows = flat(30)
    b = bars(rows)
    t = b["close_time"]
    arrays = pd.DataFrame({
        "kind": ["FVG", "FVG"], "direction": [1, -1],
        "low": [99.0, 100.2], "high": [99.8, 101.0], "mid": [99.4, 100.6],
        "formed_at": [t.iloc[2], t.iloc[2]],
        "flipped_at": [t.iloc[10], pd.NaT],                   # the bullish one closed through at bar 10
    })
    s = trend_signals(b, arrays)
    # From bar 10 the bullish FVG traded through and the bearish one (touched by every bar's 100.5 high) held.
    assert s["arrays"].iloc[12] == -1
    arrays.loc[0, "flipped_at"] = pd.NaT                      # neither flipped: both respected, a tie
    assert trend_signals(b, arrays)["arrays"].iloc[12] == 0


def test_a_bearish_po3_is_a_down_close_with_a_wick_above_the_open_closing_near_its_low():
    bear = (100, 101, 97, 97.5)          # range 4: 1 above the open (25%), the close 0.5 off the low (12.5%)
    bull = (100, 103, 99, 102.5)         # the mirror: 1 below the open, the close 0.5 off the high
    plain = (100, 100.2, 97, 97.2)       # a down close with no wick above the open: not a PO3
    assert trend_signals(bars(flat(3) + [bear]))["po3"].iloc[-1] == -1
    assert trend_signals(bars(flat(3) + [bull]))["po3"].iloc[-1] == 1
    assert trend_signals(bars(flat(3) + [plain]))["po3"].iloc[-1] == 0
    assert trend_signals(bars(flat(3) + [bear, bull, bear]))["po3"].iloc[-1] == -1     # two of the last three


def test_three_signals_in_agreement_name_the_trend():
    down = DOWN + [(97.5, 98.2, 95.5, 95.7)]                   # a down close, a PO3, after down and up
    s = trend_signals(bars(down))
    last = s.iloc[-1]
    assert (last["structure"], last["closes"], last["po3"]) == (-1, -1, -1)
    assert last["score"] <= -3 and last["trend"] == -1


def test_no_candle_after_the_one_labelled_changes_its_label():
    rng = np.random.default_rng(3)
    steps = rng.normal(0, 1, 300).cumsum() + 100
    rows = [(a, max(a, b) + abs(rng.normal(0, 0.5)), min(a, b) - abs(rng.normal(0, 0.5)), b)
            for a, b in zip(steps[:-1], steps[1:])]
    full = trend_signals(bars(rows))
    for k in (40, 120, 250):
        cut = trend_signals(bars(rows[:k]))
        pd.testing.assert_frame_equal(cut, full.iloc[:k].reset_index(drop=True), check_dtype=False)
