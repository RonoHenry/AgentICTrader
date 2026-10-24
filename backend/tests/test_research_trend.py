"""The trader's trend (context-engine Requirement 20, task 355): five signals per closed candle of a frame."""
from __future__ import annotations

import numpy as np
import pytest
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


# ── a trend call, scored (Requirement 23, task 357) ─────────────────────────
from algo_research.trend import call_outcome  # noqa: E402

H, T = 3600, 100 * 3600                     # hourly candles; the call at the 100th hour's open


def _calls_bars(rows):
    """Hourly candles closing by T, the last one ending at T."""
    n = len(rows)
    o, h, l, c = (np.array(x, dtype=float) for x in zip(*rows))
    return pd.DataFrame({"time": T - (n - np.arange(n)) * H, "open": o, "high": h, "low": l, "close": c})


def _minutes(path):
    """Minutes from T, each (open, high, low)."""
    o, h, l = (np.array(x, dtype=float) for x in zip(*path))
    return {"time": T + 60 * np.arange(len(path)), "open": o, "high": h, "low": l}


QUIET = [(100, 100.5, 99.5, 100)] * 20                  # an average range of 1.0
FALL = [(100, 100.2, 99.8)] * 10 + [(99.8, 99.9, 98.9)] + [(99, 99.2, 98.5)] * 200      # one range down at minute 10


def test_a_call_s_next_move_is_one_average_range_either_way_within_three_candles():
    bars, m1 = _calls_bars(QUIET), _minutes(FALL)
    assert call_outcome(-1, T, H, bars, m1, T + 3 * H)["next"] == "RIGHT"
    assert call_outcome(1, T, H, bars, m1, T + 3 * H)["next"] == "WRONG"
    assert call_outcome(-1, T, H, bars, m1, T + 5 * 60)["next"] == "PENDING"        # the clock is before the move
    assert call_outcome(-1, T, H, bars, m1, T)["next"] == "PENDING"                  # made at the clock itself
    flat = _minutes([(100, 100.2, 99.8)] * 240)
    assert call_outcome(-1, T, H, bars, flat, T + 4 * H)["next"] == "UNRESOLVED"     # three candles, no range
    both = _minutes([(100, 101.2, 98.8)] + [(100, 100.2, 99.8)] * 10)               # one minute reaches both
    assert call_outcome(-1, T, H, bars, both, T + H)["next"] == "WRONG"
    assert call_outcome(1, T, H, bars, both, T + H)["next"] == "WRONG"


def test_a_call_s_continuation_is_its_side_s_last_swing_taken_first_beside_geometry():
    swings = QUIET[:15] + [(100, 101, 99.6, 100.5), (100.5, 102, 100, 101), (101, 101.5, 99, 99.5),
                           (99.5, 99.8, 98, 98.5), (98.5, 100, 98.4, 99.8)]       # swing high 102, swing low 98
    bars = _calls_bars(swings)
    down = _minutes([(100, 100.2, 99.8)] * 5 + [(99, 99.1, 97.9)] + [(98, 98.2, 97.8)] * 5)
    out = call_outcome(-1, T, H, bars, down, T + H)
    assert out["cont"] == "RIGHT" and out["geometry"] == pytest.approx(0.5)        # (102 - 100) / (102 - 98)
    up = call_outcome(1, T, H, bars, down, T + H)
    assert up["cont"] == "WRONG" and up["geometry"] == pytest.approx(0.5)
    assert call_outcome(-1, T, H, bars, down, T + 3 * 60)["cont"] == "PENDING"     # read only before the clock


# ── ranked swings and breaks (Requirement 24, task 359) ─────────────────────
from algo_research.trend import break_state, compare_state, ranked_highs  # noqa: E402


def _zigzag(peaks):
    """Highs that rise to each value in ``peaks`` and fall back between them: one STH per peak."""
    h = []
    for p in peaks:
        h += [90.0, p]
    return np.array(h + [90.0])


def test_an_ith_is_an_sth_higher_than_its_neighbours_known_once_the_next_sth_is():
    h = _zigzag([100, 105, 102, 108, 104, 103])
    ranks = ranked_highs(h)
    sth, sth_known = ranks["STH"]
    assert list(h[sth]) == [100, 105, 102, 108, 104, 103] and list(sth_known) == list(sth + 1)
    ith, ith_known = ranks["ITH"]
    assert list(h[ith]) == [105, 108]                        # each higher than the STH on either side
    assert list(ith_known) == [sth_known[2], sth_known[4]]   # known once the next, lower STH has formed
    lth, _ = ranks["LTH"]
    assert len(lth) == 0                                     # needs an ITH on either side


def test_a_break_is_a_close_beyond_the_swing_and_a_wick_through_it_is_a_sweep():
    o = np.array([100, 101, 104, 103, 102, 103, 103.5, 105, 106], dtype=float)
    h = np.array([101, 103, 105, 104, 103, 105.5, 104.5, 107, 107.5], dtype=float)
    l = np.array([99, 100, 103, 102, 101, 102.5, 103, 104.8, 105.5], dtype=float)
    c = np.array([100.5, 102.5, 104, 102.5, 102.8, 103.5, 104, 106.5, 107], dtype=float)
    # The STH is candle 2 (105), known at candle 3's close. Candle 5 trades to 105.5 and closes back at 103.5: a
    # sweep. Candle 7 closes at 106.5, above it: the bullish break.
    s = break_state(o, h, l, c, "STH")
    assert list(s[:7]) == [0] * 7 and s[7] == 1 and s[8] == 1
    # With the FVG rule the breaking candle must leave a gap: candle 8's low 105.5 is above candle 6's high 104.5,
    # so the break holds, known at candle 8's close.
    f = break_state(o, h, l, c, "STH", fvg=True)
    assert list(f[:8]) == [0] * 8 and f[8] == 1


def test_compare_state_on_sth_is_task_355_s_structure():
    rng = np.random.default_rng(5)
    walk = rng.normal(0, 1, 400).cumsum() + 100
    h, l = walk + rng.uniform(0.1, 1, 400), walk - rng.uniform(0.1, 1, 400)
    o, c = walk, walk + rng.normal(0, 0.3, 400)
    rows = [(a, max(a, b, x), min(a, b, y), b) for a, b, x, y in zip(o, c, h, l)]
    hh, ll = np.array([r[1] for r in rows]), np.array([r[2] for r in rows])
    assert list(compare_state(hh, ll, "STH")) == list(trend_signals(bars(rows))["structure"])
