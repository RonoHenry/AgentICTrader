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
