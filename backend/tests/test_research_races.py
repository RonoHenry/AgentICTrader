"""
Tests for algo_research/races.py — races priced with the backtester's own rules.

Task 250 (.kiro/specs/algo-research/tasks.md). Known cases on hand-made bars;
Property 5 against stepping the shared FillModel; Property 6 on driftless paths.
Validates: Requirements 7.1-7.4 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.brokers.fill_model import Bar, FillModel, SimOrder
from agent.instruments import CommissionSpec, load_specs
from algo_research.config import REPO_ROOT
from algo_research.frame import InstrumentFrame, frame_from_arrays
from algo_research.races import RaceCosts, run_races

UTC = timezone.utc
T0 = datetime(2026, 1, 13, 14, 0, tzinfo=UTC)          # a Tuesday, 09:00 New York
MIN = timedelta(minutes=1)


def bars_frame(rows, spread=0.0002, slippage=0.0001) -> InstrumentFrame:
    """M1 bars from T0, one per minute: rows of (open, high, low, close[, spread])."""
    times = pd.DatetimeIndex([T0 + i * MIN for i in range(len(rows))])
    o, h, l, c = (np.array([r[k] for r in rows], dtype=float) for k in range(4))
    spreads = np.array([r[4] if len(r) > 4 else spread for r in rows], dtype=float)
    return frame_from_arrays("EURUSD", times, o, h, l, c, spread=spreads, typical_spread=0.0, stop_slippage=slippage)


def race(frame, direction, stop, target, t=T0, limit=None, costs=None) -> pd.Series:
    orders = pd.DataFrame({"t": [pd.Timestamp(t)], "direction": [direction], "stop": [stop], "target": [target],
                           "limit": [pd.Timestamp(limit or t + timedelta(hours=6))]})
    return run_races(frame, orders, costs).iloc[0]


FLAT = (1.1000, 1.1005, 1.0995, 1.1000)


# ── known cases ─────────────────────────────────────────────────────────────

def test_long_to_target():
    frame = bars_frame([FLAT, (1.1000, 1.1030, 1.0998, 1.1025), FLAT])
    r = race(frame, "LONG", stop=1.0980, target=1.1020)
    assert r["outcome"] == "TARGET" and not r["ambiguous"]
    assert (r["entry"], r["entry_bid"]) == (pytest.approx(1.1002), 1.1000)        # the ask open, then the bid
    assert r["entry_time"] == pd.Timestamp(T0) and r["exit_time"] == pd.Timestamp(T0 + MIN)
    assert (r["exit"], r["exit_bid"]) == (1.1020, 1.1020)
    risk = 1.1002 - 1.0980
    assert r["gross_r"] == pytest.approx((1.1020 - 1.1000) / risk)
    assert r["net_r"] == pytest.approx((1.1020 - 1.1002) / risk)
    assert r["mfe_r"] == pytest.approx((1.1020 - 1.1002) / risk)                  # capped at the target
    assert r["mae_r"] == pytest.approx((1.0995 - 1.1002) / risk)
    assert r["score"] == 1.0 and r["holding_minutes"] == 1


def test_long_to_stop_with_slippage():
    frame = bars_frame([FLAT, (1.1000, 1.1003, 1.0970, 1.0975)])
    r = race(frame, "LONG", stop=1.0980, target=1.1050)
    assert r["outcome"] == "STOP"
    assert (r["exit"], r["exit_bid"]) == (pytest.approx(1.0979), 1.0980)          # worsened by the slippage
    assert r["net_r"] == pytest.approx((1.0979 - 1.1002) / (1.1002 - 1.0980))
    assert r["score"] == 0.0


def test_short_to_target_and_stop_on_the_ask():
    # SHORT fills at the bid open; its stop and target trigger on the ask (bid + spread).
    frame = bars_frame([FLAT, (1.1000, 1.1001, 1.0975, 1.0980)])
    r = race(frame, "SHORT", stop=1.1030, target=1.0980)
    assert r["outcome"] == "TARGET"                                              # ask low 1.0977 <= 1.0980
    assert (r["entry"], r["entry_bid"], r["exit"], r["exit_bid"]) == (1.1000, 1.1000, 1.0980, pytest.approx(1.0978))
    frame = bars_frame([FLAT, (1.1000, 1.1029, 1.0999, 1.1020)])
    r = race(frame, "SHORT", stop=1.1030, target=1.0900)
    assert r["outcome"] == "STOP"                                                # ask high 1.1031 >= 1.1030
    assert r["exit"] == pytest.approx(1.1031)                                    # stop + slippage


def test_gap_through_the_stop_exits_at_the_open():
    frame = bars_frame([FLAT, (1.0960, 1.0965, 1.0950, 1.0955)])
    r = race(frame, "LONG", stop=1.0980, target=1.1050)
    assert r["outcome"] == "STOP"
    assert (r["exit_bid"], r["exit"]) == (1.0960, pytest.approx(1.0959))


def test_bar_reaching_both_is_a_stop_and_ambiguous():
    frame = bars_frame([FLAT, (1.1000, 1.1060, 1.0970, 1.1000)])
    r = race(frame, "LONG", stop=1.0980, target=1.1050)
    assert r["outcome"] == "STOP" and r["ambiguous"]


def test_rejected_when_the_entry_open_is_beyond_a_level():
    frame = bars_frame([FLAT, FLAT])
    assert race(frame, "LONG", stop=1.1005, target=1.1050)["outcome"] == "REJECTED"     # ask open 1.1002 <= stop
    assert race(frame, "LONG", stop=1.0950, target=1.1001)["outcome"] == "REJECTED"     # ask open beyond the target
    assert race(frame, "SHORT", stop=1.0999, target=1.0950)["outcome"] == "REJECTED"
    r = race(frame, "LONG", stop=1.0950, target=1.1001)
    assert np.isnan(r["net_r"]) and np.isnan(r["score"])
    # No bar before the limit: nothing to fill on.
    assert race(frame, "LONG", stop=1.09, target=1.2, t=T0 + 10 * MIN)["outcome"] == "REJECTED"


def test_timeout_at_the_last_close_on_the_closing_side():
    frame = bars_frame([FLAT, (1.1000, 1.1010, 1.0990, 1.1008), (1.1008, 1.1012, 1.1001, 1.1010), FLAT])
    r = race(frame, "LONG", stop=1.0950, target=1.1100, limit=T0 + 3 * MIN)            # bars 0-2
    assert r["outcome"] == "TIMEOUT"
    assert (r["exit_bid"], r["exit"]) == (1.1010, 1.1010) and r["exit_time"] == pd.Timestamp(T0 + 3 * MIN)
    assert r["score"] == pytest.approx((1.1010 - 1.0950) / (1.1100 - 1.0950))       # its coin flip at the exit
    r = race(frame, "SHORT", stop=1.1100, target=1.0950, limit=T0 + 3 * MIN)
    assert (r["exit_bid"], r["exit"]) == (1.1010, pytest.approx(1.1012))            # bought back at the ask
    assert r["score"] == pytest.approx((1.1100 - 1.1012) / (1.1100 - 1.0950))


def test_coin_flip_on_the_closing_side_at_entry():
    frame = bars_frame([FLAT, FLAT])
    assert race(frame, "LONG", stop=1.0980, target=1.1040, limit=T0 + MIN)["p_coin"] == pytest.approx(
        (1.1000 - 1.0980) / (1.1040 - 1.0980))
    assert race(frame, "SHORT", stop=1.1040, target=1.0980, limit=T0 + MIN)["p_coin"] == pytest.approx(
        (1.1040 - 1.1002) / (1.1040 - 1.0980))


def test_commission_in_r():
    spec = load_specs(REPO_ROOT / "config" / "instruments" / "exness-standard.toml")["EURUSD"]
    spec = replace(spec, commission=CommissionSpec(kind="PER_LOT_PER_SIDE", value=3.5))
    costs = RaceCosts.from_spec(spec, "USD")
    frame = bars_frame([FLAT, (1.1000, 1.1030, 1.0998, 1.1025)])
    r = race(frame, "LONG", stop=1.0980, target=1.1020, costs=costs)
    risk_money = (1.1002 - 1.0980) * 100_000                                      # per lot
    assert r["commission_r"] == pytest.approx(7.0 / risk_money)
    assert r["net_r"] == pytest.approx((1.1020 - 1.1002) / (1.1002 - 1.0980) - 7.0 / risk_money)
    assert costs.stop_slippage == spec.stop_slippage


def test_races_at_several_times_keep_their_index():
    frame = bars_frame([FLAT] * 10)
    orders = pd.DataFrame({"t": [pd.Timestamp(T0 + 2 * MIN), pd.Timestamp(T0)], "direction": ["LONG", "SHORT"],
                           "stop": [1.09, 1.11], "target": [1.11, 1.09],
                           "limit": [pd.Timestamp(T0 + 5 * MIN)] * 2}, index=[7, 3])
    out = run_races(frame, orders)
    assert list(out.index) == [7, 3]
    assert list(out["entry_time"]) == [pd.Timestamp(T0 + 2 * MIN), pd.Timestamp(T0)]


# ── Property 5: races equal the fill model ─────────────────────────────────

@st.composite
def paths_and_races(draw):
    n = draw(st.integers(2, 30))
    price, rows = 1.1, []
    for _ in range(n):
        gap = draw(st.sampled_from([0.0, 0.0, 0.0, draw(st.floats(-0.003, 0.003))]))
        o = price + gap
        c = o + draw(st.floats(-0.002, 0.002))
        h = max(o, c) + draw(st.floats(0, 0.002))
        lo = min(o, c) - draw(st.floats(0, 0.002))
        rows.append((o, h, lo, c, draw(st.sampled_from([0.0, 0.0001, 0.0003, 0.001]))))
        price = c
    start = draw(st.integers(0, n - 1))
    direction = draw(st.sampled_from(["LONG", "SHORT"]))
    near = rows[start][0]
    stop_gap, target_gap = draw(st.floats(-0.0005, 0.004)), draw(st.floats(-0.0005, 0.006))
    sign = 1 if direction == "LONG" else -1
    stop, target = near - sign * stop_gap, near + sign * target_gap
    t = T0 + start * MIN + draw(st.sampled_from([timedelta(0), timedelta(seconds=30)]))
    limit = T0 + draw(st.integers(start, n + 2)) * MIN
    return rows, direction, stop, target, t, limit


def step_fill_model(rows, direction, stop, target, t, limit, slippage):
    model = FillModel(slippage)
    order = SimOrder(order_id="r", setup_id="", instrument="EURUSD", direction=direction, kind="MARKET",
                     entry=0.0, stop=stop, target=target, placed_at=t)
    last = None
    for i, (o, h, lo, c, sp) in enumerate(rows):
        ts = T0 + i * MIN
        if ts < t or ts >= limit:
            continue
        bar = Bar(timestamp=ts, open=o, high=h, low=lo, close=c, spread=sp)
        model.step(order, bar)
        last = bar
        if order.status == "CLOSED":
            break
    if order.exit_reason == "INVALID_STOPS" or order.fill is None:
        return "REJECTED", None, None, order
    if order.exit_reason == "SL":
        return "STOP", order.closed_at, order.exit, order
    if order.exit_reason == "TP":
        return "TARGET", order.closed_at, order.exit, order
    exit_price = last.close if direction == "LONG" else last.close + last.spread
    return "TIMEOUT", last.timestamp + MIN, exit_price, order


@settings(max_examples=100, deadline=None)
@given(paths_and_races())
def test_property_5_races_equal_the_fill_model(case):
    rows, direction, stop, target, t, limit = case
    frame = bars_frame([r[:4] + (r[4],) for r in rows], slippage=0.0001)
    got = race(frame, direction, stop, target, t=t, limit=limit)
    outcome, exit_time, exit_price, order = step_fill_model(rows, direction, stop, target, t, limit, 0.0001)
    assert got["outcome"] == outcome
    if outcome == "REJECTED":
        return
    assert got["exit_time"] == pd.Timestamp(exit_time)
    assert got["exit"] == pytest.approx(exit_price, abs=1e-12)
    assert got["entry"] == pytest.approx(order.fill, abs=1e-12)
    assert got["entry_bid"] == pytest.approx(order.ideal_fill, abs=1e-12)
    if outcome in ("STOP", "TARGET"):
        assert got["exit_bid"] == pytest.approx(order.ideal_exit, abs=1e-12)
        sign, risk = (1 if direction == "LONG" else -1), abs(order.fill - stop)
        assert got["mae_r"] == pytest.approx(sign * (order.mae_price - order.fill) / risk, abs=1e-9)
        assert got["mfe_r"] == pytest.approx(sign * (order.mfe_price - order.fill) / risk, abs=1e-9)


# ── Property 6: coin-flip consistency ──────────────────────────────────────

def test_property_6_driftless_win_rate_matches_the_coin_flip():
    # One long driftless walk, cut into independent windows: one race per window, to its end.
    rng = np.random.default_rng(20261009)
    n_races, n_bars, spread = 3000, 600, 0.00002
    closes = 1.1 + np.cumsum(rng.normal(0, 0.00005, n_races * n_bars))
    opens = np.concatenate([[1.1], closes[:-1]])
    frame = bars_frame(list(zip(opens, np.maximum(opens, closes), np.minimum(opens, closes), closes)),
                       spread=spread, slippage=0.0)
    starts = np.arange(n_races) * n_bars
    directions = np.where(starts % 2 == 0, "LONG", "SHORT")
    sign = np.where(directions == "LONG", 1, -1)
    closing = opens[starts] + np.where(directions == "LONG", 0.0, spread)   # the price the position closes at
    stop = closing - sign * rng.uniform(0.0003, 0.0012, n_races)
    target = closing + sign * rng.uniform(0.0003, 0.0024, n_races)
    orders = pd.DataFrame({"t": pd.DatetimeIndex([T0 + int(i) * MIN for i in starts]), "direction": directions,
                           "stop": stop, "target": target,
                           "limit": pd.DatetimeIndex([T0 + int(i + n_bars) * MIN for i in starts])})
    races = run_races(frame, orders)
    races = races[races["outcome"] != "REJECTED"]
    diff = (races["score"] - races["p_coin"]).to_numpy()
    se = diff.std(ddof=1) / np.sqrt(len(diff))
    assert len(diff) > 2900
    assert abs(diff.mean()) < 3 * se, (diff.mean(), se)
    assert (races["outcome"] == "TIMEOUT").mean() < 0.5
