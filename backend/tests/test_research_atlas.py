"""
Tests for algo_research/atlas/ — the turn atlas (algo-research update 2026-10g).

Task 320 (.kiro/specs/algo-research/tasks.md): arrays as the user reads them. Hand-made bars state exactly the
highs, lows and closes each rule reasons about.
Validates: Requirement 23 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algo_research.atlas.arrays import build_arrays, fvgs, order_blocks, state_at
from liquidity_engine.context.measures import bearish_order_blocks, mirror
from liquidity_engine.models import Timeframe as TF

HOUR = pd.Timedelta(hours=1)
T0 = pd.Timestamp("2025-01-06 00:00", tz="UTC")


def bars(rows) -> pd.DataFrame:
    """H1 bars from (open, high, low, close) rows, one hour apart."""
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    time = pd.DatetimeIndex([T0 + i * HOUR for i in range(len(rows))])
    return pd.DataFrame({"time": time, "close_time": time + HOUR, "open": o, "high": h, "low": l, "close": c})


def close_of(b: pd.DataFrame, i: int) -> pd.Timestamp:
    return b["close_time"].iloc[i]


# ── FVG (23.1, 23.2) ────────────────────────────────────────────────────────

BULL = [(1.00, 1.02, 0.99, 1.01), (1.01, 1.06, 1.01, 1.05), (1.05, 1.08, 1.04, 1.07)]


def test_a_bullish_fvg_is_the_gap_with_its_ce_formed_at_c3s_close():
    b = bars(BULL)
    table = fvgs(b, TF.H1)
    assert len(table) == 1
    row = table.iloc[0]
    assert (row["kind"], row["direction"], row["tf"]) == ("FVG", 1, "H1")
    assert (row["low"], row["high"]) == pytest.approx((1.02, 1.04))           # C1's high to C3's low
    assert row["mid"] == pytest.approx(1.03)                                   # the CE
    assert row["formed_at"] == close_of(b, 2)
    assert pd.isna(row["flipped_at"])


def test_a_bearish_fvg_is_the_gap_between_c3s_high_and_c1s_low():
    b = bars([(1.07, 1.08, 1.05, 1.06), (1.06, 1.06, 1.01, 1.02), (1.02, 1.03, 1.00, 1.01)])
    row = fvgs(b, TF.H1).iloc[0]
    assert (row["direction"], row["low"], row["high"], row["mid"]) == pytest.approx((-1, 1.03, 1.05, 1.04))


def test_three_candles_without_a_gap_leave_no_fvg():
    touching = [(1.00, 1.02, 0.99, 1.01), (1.01, 1.06, 1.01, 1.05), (1.05, 1.08, 1.02, 1.07)]   # C3 low = C1 high
    assert fvgs(bars(touching), TF.H1).empty


def test_an_fvg_survives_a_wick_and_a_close_inside_and_flips_on_a_close_beyond_its_far_edge():
    b = bars(BULL + [(1.07, 1.07, 1.025, 1.05),          # a wick into the gap
                     (1.05, 1.05, 1.01, 1.03),           # a wick through the far edge, closing inside
                     (1.03, 1.03, 1.00, 1.015)])         # a close below the far edge (1.02): inverted
    table = fvgs(b, TF.H1)
    row = table.iloc[0]
    assert row["flipped_at"] == close_of(b, 5)
    before = state_at(table, close_of(b, 4)).iloc[0]
    after = state_at(table, close_of(b, 5)).iloc[0]
    assert (before["name"], before["facing"]) == ("FVG", 1)
    assert (after["name"], after["facing"]) == ("IFVG", -1)                   # it now faces the other way
    assert state_at(table, close_of(b, 1)).empty                               # not formed yet


# ── order blocks and breakers (23.3) ────────────────────────────────────────

def _ob_bars():
    quiet = [(1.000, 1.002, 0.998, 1.001)] * 15                              # a small ATR
    return bars(quiet + [(1.000, 1.004, 0.999, 1.003),                         # the last bullish candle (the OB)
                         (1.003, 1.003, 0.985, 0.986),                         # a bearish displacement > 1.5 ATR
                         (0.986, 0.990, 0.984, 0.989),
                         (0.989, 1.006, 0.989, 1.005)])                        # closes above the OB: a breaker


def test_order_blocks_follow_the_engines_rule_with_the_body_midpoint_as_mt():
    b = _ob_bars()
    table = order_blocks(b, TF.H1)
    bear = table[table["direction"] == -1]
    o, h, l, c = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    expected = bearish_order_blocks(o, h, l, c)
    assert [(r.low, r.high) for r in bear.itertuples()] == [(lo, hi) for _, _, lo, hi in expected]
    row = bear.iloc[0]
    assert row["kind"] == "OB" and row["mid"] == pytest.approx((1.000 + 1.003) / 2)   # the body's midpoint
    assert row["formed_at"] == close_of(b, 16)                                 # the displacement's close
    assert row["flipped_at"] == close_of(b, 18)
    assert state_at(table, close_of(b, 18)).query("direction == -1").iloc[0]["name"] == "BRK"
    mo, mh, ml, mc = mirror(o, h, l, c)                                        # the bullish side is the mirror
    assert len(table[table["direction"] == 1]) == len(bearish_order_blocks(mo, mh, ml, mc))


# ── every timeframe, and nothing from the future (23.4, Property 1) ─────────

def _walk(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 1.1 + np.cumsum(rng.normal(0, 0.001, n))
    open_ = np.r_[1.1, close[:-1]]
    return bars(list(zip(open_, np.maximum(open_, close) + rng.random(n) * 0.0008,
                         np.minimum(open_, close) - rng.random(n) * 0.0008, close)))


@pytest.mark.parametrize("cut", [40, 117, 250])
def test_property_1_arrays_known_at_t_never_read_a_later_bar(cut):
    b = _walk(300, 11)
    t = close_of(b, cut - 1)
    for build in (fvgs, order_blocks):
        full, past = build(b, TF.H1), build(b.iloc[:cut], TF.H1)
        known = full[full["formed_at"] <= t].reset_index(drop=True)
        assert known[["kind", "direction", "low", "high", "mid", "formed_at"]].equals(
            past[["kind", "direction", "low", "high", "mid", "formed_at"]].reset_index(drop=True))
        flipped = known["flipped_at"].where(known["flipped_at"] <= t)
        assert flipped.equals(past["flipped_at"].reset_index(drop=True))


def test_build_arrays_covers_every_timeframe_of_the_frame():
    from tests.test_research_frame import fixture_frame

    frame = fixture_frame("EURUSD")
    table = build_arrays(frame)
    assert set(table["tf"]) <= {"M15", "H1", "H4", "D1", "W1"} and {"M15", "H1"} <= set(table["tf"])
    assert set(table["kind"]) == {"FVG", "OB"}
    assert (table["low"] < table["high"]).all()


# ══ Task 321: swings and what they delivered (Requirement 24) ═══════════════

from zoneinfo import ZoneInfo  # noqa: E402

from algo_research.atlas.swings import build_swings, find_swings  # noqa: E402
from algo_research.frame import frame_from_arrays  # noqa: E402

MINUTE = pd.Timedelta(minutes=1)
START = pd.Timestamp("2025-01-07 01:00", tz=ZoneInfo("America/New_York")).tz_convert("UTC")   # an H4 boundary


def hourly_frame(rows, orders=None, spikes=None, mirrored=False, start=None):
    """A frame whose H1 bars are ``rows`` (open, high, low, close), built minute by minute: an hour opens, reaches
    its first extreme at :20 and its second at :40, and closes at :59. A bearish hour makes its high first ("hl"),
    a bullish one its low first ("lh"), unless ``orders`` says otherwise. ``spikes`` {hour: (minute, high, low)}
    widens one M1 bar. ``mirrored`` turns the prices upside down."""
    start = START if start is None else pd.Timestamp(start).tz_convert("UTC")
    times, o, h, l, c = [], [], [], [], []
    for n, (op, hi, lo, cl) in enumerate(rows):
        order = (orders or {}).get(n) or ("hl" if cl < op else "lh")
        x1, x2 = (hi, lo) if order == "hl" else (lo, hi)
        path = [(op, op)] * 20 + [(op, x1)] + [(x1, x1)] * 19 + [(x1, x2)] + [(x2, x2)] * 18 + [(x2, cl)]
        for m, (a, b) in enumerate(path):
            times.append(start + n * HOUR + m * MINUTE)
            o.append(a), c.append(b), h.append(max(a, b)), l.append(min(a, b))
            if spikes and n in spikes and spikes[n][0] == m:
                h[-1], l[-1] = max(h[-1], spikes[n][1]), min(l[-1], spikes[n][2])
    o, h, l, c = (np.array(x) for x in (o, h, l, c))
    if mirrored:
        o, h, l, c = -o, -l, -h, -c
    return frame_from_arrays("TEST", pd.DatetimeIndex(times), o, h, l, c, spread=np.zeros(len(o)),
                             typical_spread=0.0, stop_slippage=0.0)


def test_three_candle_swings_need_both_neighbours_strictly_and_an_outside_bar_is_both():
    b = bars([(1.000, 1.010, 0.990, 1.005), (1.005, 1.008, 0.980, 0.985), (0.985, 1.020, 0.985, 1.015),
              (1.015, 1.018, 1.000, 1.005), (1.005, 1.018, 0.995, 1.000), (1.000, 1.010, 0.990, 1.008),
              (1.008, 1.030, 0.970, 1.000), (1.000, 1.020, 0.980, 1.010)])
    found = find_swings(b)
    three = found[found["type"] == "three"]
    assert sorted(zip(three["i"], three["side"])) == [(1, "low"), (2, "high"), (6, "high"), (6, "low")]
    # bar 4 ties bar 3's high, so it isn't a swing high. Bar 5 sweeps bar 4's low and closes above its body.
    engulf = found[found["type"] == "engulf"]
    assert list(zip(engulf["i"], engulf["side"], engulf["engulf_full"], engulf["twin"])) == [(5, "low", False, False)]


def test_an_engulfing_swing_sweeps_and_closes_above_the_previous_body():
    full = bars([(1.010, 1.012, 1.000, 1.002), (1.002, 1.014, 0.995, 1.013), (1.013, 1.020, 1.005, 1.018)])
    row = find_swings(full).query("type == 'engulf'").iloc[0]
    assert (row["i"], row["side"], row["extreme"], row["engulf_full"], row["twin"]) == (1, "low", 0.995, True, True)
    body_only = bars([(1.010, 1.012, 1.000, 1.002), (1.002, 1.011, 0.995, 1.011), (1.011, 1.013, 0.990, 1.000)])
    row = find_swings(body_only).query("type == 'engulf'").iloc[0]
    assert (row["engulf_full"], row["twin"]) == (False, False)          # the next bar went lower: no three-candle twin


LEG = [(1.100, 1.102, 1.098, 1.101), (1.101, 1.110, 1.100, 1.108), (1.108, 1.109, 1.095, 1.096),
       (1.096, 1.097, 1.090, 1.092), (1.092, 1.099, 1.093, 1.098)]          # a swing high at 1, a swing low at 3


def _low(frame):
    return build_swings(frame, TF.H1).query("side == 'low' and type == 'three'").iloc[0]


def test_a_swing_low_held_against_its_crt_and_leg_objectives():
    frame = hourly_frame(LEG + [(1.098, 1.112, 1.097, 1.111)])
    row = _low(frame)
    assert row["extreme"] == pytest.approx(1.090)
    assert row["known_at"] == START + 5 * HOUR                             # C3's close
    assert (row["obj_crt"], row["obj_same_tf"]) == pytest.approx((1.109, 1.110))   # C1's high; the leg's origin
    assert (row["out_crt"], row["out_same_tf"]) == ("held", "held")
    assert row["resolved_same_tf"] == START + 5 * HOUR + 40 * MINUTE + MINUTE    # the M1 bar that reached it
    assert row["bars_same_tf"] == 1
    assert not row["at_once_crt"]
    assert pd.isna(row["obj_next_tf"]) and row["out_next_tf"] is None    # no H4 swing high yet
    assert row["avg_range"] == pytest.approx((0.004 + 0.010 + 0.014) / 3)
    assert row["excursion"] == pytest.approx((1.112 - 1.090) / row["avg_range"])


def test_a_swing_low_failed_and_one_left_open():
    failed = _low(hourly_frame(LEG + [(1.098, 1.099, 1.089, 1.090)]))
    assert (failed["out_crt"], failed["out_same_tf"]) == ("failed", "failed")
    open_ = _low(hourly_frame(LEG + [(1.098, 1.105, 1.095, 1.100)]))
    assert (open_["out_crt"], open_["out_same_tf"]) == ("open", "open")


def test_a_bar_that_does_both_is_settled_on_m1_and_one_m1_bar_doing_both_fails():
    both = (1.098, 1.112, 1.089, 1.100)
    assert _low(hourly_frame(LEG + [both], orders={5: "lh"}))["out_same_tf"] == "failed"   # the low came first
    assert _low(hourly_frame(LEG + [both], orders={5: "hl"}))["out_same_tf"] == "held"     # the high came first
    one_bar = hourly_frame(LEG + [(1.098, 1.100, 1.095, 1.099)], spikes={5: (10, 1.112, 1.089)})
    assert _low(one_bar)["out_same_tf"] == "failed"


def test_an_objective_reached_before_the_swing_is_known_is_held_at_once():
    high = build_swings(hourly_frame(LEG + [(1.098, 1.112, 1.097, 1.111)]), TF.H1).query(
        "side == 'high' and type == 'three'").iloc[0]
    assert high["extreme"] == pytest.approx(1.110) and high["obj_crt"] == pytest.approx(1.098)
    assert (high["out_crt"], high["at_once_crt"], high["bars_crt"]) == ("held", True, 0)   # 1.095 at hour 2's :40
    assert high["resolved_crt"] == high["known_at"]


def test_the_next_timeframes_untaken_swing_is_the_third_objective():
    rows = ([(1.100, 1.105, 1.099, 1.102)] * 4
            + [(1.102, 1.110, 1.101, 1.109), (1.109, 1.120, 1.108, 1.115), (1.115, 1.116, 1.105, 1.106),
               (1.106, 1.108, 1.100, 1.104)]                                  # H4 bar 1: the H4 swing high, 1.120
            + [(1.104, 1.110, 1.098, 1.100), (1.100, 1.102, 1.096, 1.097), (1.097, 1.099, 1.094, 1.095),
               (1.095, 1.097, 1.093, 1.094)]
            + [(1.094, 1.096, 1.091, 1.092), (1.092, 1.093, 1.085, 1.087), (1.087, 1.095, 1.088, 1.094),
               (1.094, 1.121, 1.093, 1.120)])
    low = build_swings(hourly_frame(rows), TF.H1).query("side == 'low' and type == 'three'")
    row = low[low["extreme"] == 1.085].iloc[0]
    assert row["obj_next_tf"] == pytest.approx(1.120) and row["out_next_tf"] == "held"
    assert row["obj_same_tf"] == pytest.approx(1.110)                    # from the H1 swing high at hour 8


def test_swing_highs_are_swing_lows_read_upside_down():
    rows = LEG + [(1.098, 1.112, 1.097, 1.111)]
    lows = build_swings(hourly_frame(rows), TF.H1).query("side == 'low'").reset_index(drop=True)
    highs = build_swings(hourly_frame(rows, mirrored=True), TF.H1).query("side == 'high'").reset_index(drop=True)
    assert len(lows) == len(highs) > 0
    for col in ("extreme", "obj_crt", "obj_same_tf"):
        assert highs[col].to_numpy() == pytest.approx(-lows[col].to_numpy(), nan_ok=True)
    for col in ("type", "known_at", "out_crt", "out_same_tf", "at_once_crt"):
        assert list(highs[col]) == list(lows[col])
    assert highs["excursion"].to_numpy() == pytest.approx(lows["excursion"].to_numpy())


def test_property_1_objectives_are_known_when_the_swing_is():
    frame = hourly_frame(LEG + [(1.098, 1.112, 1.097, 1.111)])
    full = _low(frame)
    t = full["known_at"]
    early = frame.m1["time"] < t
    cut = frame_from_arrays("TEST", pd.DatetimeIndex(frame.m1["time"][early]),
                            *(frame.m1[k][early].to_numpy() for k in ("open", "high", "low", "close")),
                            spread=np.zeros(int(early.sum())), typical_spread=0.0, stop_slippage=0.0)
    past = _low(cut)
    for col in ("extreme", "obj_crt", "obj_same_tf", "avg_range", "at_once_crt", "known_at"):
        assert past[col] == full[col]
    assert past["out_same_tf"] == "open"                                   # its outcome lies after t


# ══ Task 322: the context at a swing (Requirement 25) ═══════════════════════

from algo_research.atlas.context import CONTEXT_COLUMNS, build_context, facing_depths, pd_zone  # noqa: E402
from algo_research.frame import calendar_columns  # noqa: E402


def _arrays_table(rows):
    """Arrays from (tf, kind, direction, low, high, formed_at, flipped_at) rows; mid is the midpoint."""
    tf, kind, direction, low, high, formed, flipped = zip(*rows)
    return pd.DataFrame({"tf": tf, "kind": kind, "direction": direction, "low": low, "high": high,
                         "mid": [(a + b) / 2 for a, b in zip(low, high)],
                         "formed_at": pd.to_datetime(list(formed), utc=True),
                         "flipped_at": pd.to_datetime(list(flipped), utc=True)})


def test_the_depth_of_a_supporting_array_and_which_arrays_count():
    opened = T0 + 10 * HOUR
    arrays = _arrays_table([
        ("H4", "FVG", 1, 1.104, 1.115, T0, None),                         # supports a low
        ("H4", "OB", -1, 1.104, 1.115, T0, None),                         # resistance: the other way
        ("H1", "FVG", 1, 1.104, 1.115, opened + HOUR, None),              # formed after the bar opened
        ("D1", "FVG", -1, 1.100, 1.109, T0, T0 + 5 * HOUR),               # a bearish gap closed through: an IFVG
    ])
    assert facing_depths(arrays, opened, 1.112, 1.116) == {("H4", "FVG"): "edge"}
    assert facing_depths(arrays, opened, 1.108, 1.116) == {("H4", "FVG"): "mid", ("D1", "IFVG"): "edge"}
    assert facing_depths(arrays, opened, 1.102, 1.116) == {("H4", "FVG"): "through", ("D1", "IFVG"): "mid"}
    assert facing_depths(arrays, opened, 1.125, 1.130) == {}                # the bar never reached them
    # A swing high reads the same arrays upside down: the bearish OB is its resistance.
    assert facing_depths(arrays, opened, 1.112, 1.100, side="high") == {("H4", "OB"): "mid"}


def _path_a(x):
    """An H4 bullish FVG [1.104, 1.115] formed at hour 12; an H1 swing low at hour 13 reaching ``x``. Hour 10
    makes its own swing low at the FVG's top, inside the H4 bar that forms it."""
    up = [(1.100, 1.104, 1.099, 1.102)] * 4
    leg = [(1.102, 1.108, 1.101, 1.107), (1.107, 1.113, 1.106, 1.112), (1.112, 1.118, 1.111, 1.117),
           (1.117, 1.122, 1.116, 1.121)]
    top = [(1.121, 1.125, 1.118, 1.120), (1.120, 1.124, 1.117, 1.122), (1.122, 1.125, 1.115, 1.118),
           (1.118, 1.121, 1.116, 1.119)]
    dip = [(1.119, 1.120, 1.114, 1.115), (1.115, 1.116, x, 1.113), (1.113, 1.118, x + 0.002, 1.117),
           (1.117, 1.120, 1.116, 1.119)]
    return hourly_frame(up + leg + top + dip)


def _context(frame, tf=TF.H1, extra=()):
    swings = build_swings(frame, tf)
    every = pd.concat([swings, *(build_swings(frame, t) for t in extra)], ignore_index=True)
    return build_context(frame, swings, build_arrays(frame), every)


@pytest.mark.parametrize("x, depth", [(1.112, "edge"), (1.108, "mid"), (1.102, "through")])
def test_an_h1_swing_low_into_an_h4_fvg_records_how_deep_it_went(x, depth):
    table = _context(_path_a(x))
    lows = table[(table["side"] == "low") & (table["type"] == "three")].set_index("extreme")
    assert lows.loc[x, "arr_H4_FVG"] == depth
    assert lows.loc[x, "arr_htf_any"] and lows.loc[x, "arr_any"]
    assert lows.loc[1.115, "arr_H4_FVG"] is None                            # the FVG formed after its bar opened
    assert list(table.columns[-len(CONTEXT_COLUMNS):]) == CONTEXT_COLUMNS


def _path_b():
    """Two trading dates from Monday 17:00 New York, flat at 1.1000 (H1 lows 1.0995) except:
    Tuesday's Asian low 1.0990 (22:00) and Tuesday's low 1.0985 (08:00); Wednesday's Asian low 1.0988 (22:00),
    equal lows 1.0990 (02:00) and 1.09905 (05:00), then 1.0980 at 09:00 Wednesday."""
    rows = [(1.1000, 1.1005, 1.0995, 1.1000)] * 48
    for hour, low in ((5, 1.0990), (15, 1.0985), (29, 1.0988), (33, 1.0990), (36, 1.09905), (40, 1.0980)):
        rows[hour] = (1.1000, 1.1005, low, 1.1000)
    return hourly_frame(rows, start=pd.Timestamp("2025-01-06 17:00", tz=ZoneInfo("America/New_York")))


def test_the_liquidity_a_swing_took():
    table = _context(_path_b())
    lows = table[(table["side"] == "low") & (table["type"] == "three")].set_index("extreme")
    wednesday = lows.loc[1.0980]
    assert (wednesday["liq_pd"], wednesday["liq_asia"], wednesday["liq_london"], wednesday["liq_equal"]) == (
        True, True, True, True)
    assert not wednesday["liq_pw"]                                         # no previous week in the data
    tuesday = lows.loc[1.0985]
    assert tuesday["liq_asia"] and not tuesday["liq_pd"] and not tuesday["liq_equal"]
    # 1.0990 twice: hour 5 is inside Tuesday's Asian session; hour 33 stays above Wednesday's Asian low.
    assert not lows.loc[[1.0990], "liq_asia"].any()


def _path_c():
    """An H4 swing low (1.095) and high (1.110) at H4 bar 1; an H1 swing low at hour 13 takes the low."""
    rows = [(1.102, 1.103, 1.101, 1.102)] * 16
    rows[1], rows[5], rows[6] = (1.102, 1.103, 1.100, 1.102), (1.102, 1.103, 1.095, 1.102), (1.102, 1.110, 1.101, 1.102)
    rows[9], rows[10] = (1.102, 1.103, 1.098, 1.102), (1.102, 1.104, 1.101, 1.102)
    rows[12], rows[13], rows[14] = (1.102, 1.103, 1.097, 1.102), (1.102, 1.103, 1.094, 1.102), (1.102, 1.103, 1.096, 1.102)
    return hourly_frame(rows)


def test_an_untaken_higher_timeframe_swing_and_the_dealing_range():
    table = _context(_path_c(), extra=(TF.H4,))
    row = table[(table["side"] == "low") & (table["type"] == "three") & (table["extreme"] == 1.094)].iloc[0]
    assert row["liq_htf_swing"]
    assert row["pd"] == pytest.approx((1.094 - 1.095) / (1.110 - 1.095))  # below the H4 range's low
    assert (row["pd_zone"], row["pd_aligned"]) == ("beyond", True)


def test_dealing_range_zones_read_for_the_swings_side():
    assert [pd_zone("low", v) for v in (-0.1, 0.2, 0.8)] == ["beyond", "discount", "premium"]
    assert [pd_zone("high", v) for v in (1.2, 0.8, 0.2)] == ["beyond", "premium", "discount"]
    assert pd_zone("low", float("nan")) is None


def test_time_and_anatomy_of_a_swing():
    table = _context(hourly_frame(LEG + [(1.098, 1.112, 1.097, 1.111)]))
    row = table[(table["side"] == "low") & (table["type"] == "three")].iloc[0]
    cal = calendar_columns(pd.DatetimeIndex([row["extreme_time"]]))
    assert (row["ny_hour"], row["session"], row["weekday"]) == (4, "london", 1)    # 04:40 New York, Tuesday
    assert (row["killzone"], row["h4_index"]) == (cal["killzone"].iloc[0], cal["h4_index"].iloc[0])
    assert not row["turtle_soup"]                                          # C2 closed below C1's low
    assert row["wick_share"] == pytest.approx((1.092 - 1.090) / (1.097 - 1.090))
    assert row["displacement"] == pytest.approx(0.006 / row["avg_range"])
    assert row["closes_beyond"] and not row["own_fvg"]                     # C3 closed above C2's high
    soup = _context(hourly_frame([(1.100, 1.102, 1.098, 1.101)] * 3 + [
        (1.100, 1.102, 1.098, 1.101), (1.101, 1.102, 1.096, 1.100), (1.100, 1.106, 1.099, 1.105)]))
    assert soup[(soup["side"] == "low") & (soup["type"] == "three")].iloc[0]["turtle_soup"]


def test_property_1_context_is_known_when_the_swing_is():
    frame = _path_a(1.108)
    full = _context(frame)
    row = full[(full["side"] == "low") & (full["type"] == "three") & (full["extreme"] == 1.108)].iloc[0]
    early = frame.m1["time"] < row["known_at"]
    cut = frame_from_arrays("TEST", pd.DatetimeIndex(frame.m1["time"][early]),
                            *(frame.m1[k][early].to_numpy() for k in ("open", "high", "low", "close")),
                            spread=np.zeros(int(early.sum())), typical_spread=0.0, stop_slippage=0.0)
    past = _context(cut)
    again = past[(past["side"] == "low") & (past["type"] == "three") & (past["extreme"] == 1.108)].iloc[0]
    for col in CONTEXT_COLUMNS:
        assert (again[col] == row[col]) or (pd.isna(again[col]) and pd.isna(row[col])), col
