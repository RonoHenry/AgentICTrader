"""
Tests for algo_research/narrative/ — the candle narrative and its price basis.

Task 290 (.kiro/specs/market-narrative/tasks.md). The narrative describes a
finished candle at any frame: its open, extremes and their times, its
direction, the false move and the expansion, and the child each extreme
formed in. It is hindsight, read only by the autopsy and research labels.
Validates: Requirements 1.1-1.5, 2.1-2.4 (.kiro/specs/market-narrative/requirements.md)
"""
from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algo_research.narrative import (
    NARRATIVE_COLUMNS,
    NarrativeConfig,
    PriceBasis,
    apply_price_basis,
    fill_phase,
    load_narrative_config,
    narrate,
)
from liquidity_engine.models import Timeframe
from services.market_data.strategy_calendar import StrategyCalendar

M15 = timedelta(minutes=15)
CAL = StrategyCalendar()
# Monday 2026-01-12 17:00 New York (EST): the D1 candle of Tuesday 2026-01-13.
TUE = pd.Timestamp("2026-01-12 22:00", tz="UTC")
REPO = Path(__file__).resolve().parents[2]


def candle_bars(start: pd.Timestamp, n: int = 96, level: float = 1.1000, close: float | None = None,
                wicks: tuple = (), step: timedelta = M15) -> pd.DataFrame:
    """n flat bars at ``level``; ``wicks`` = (index, high, low) overrides; the last close set to ``close``."""
    rows = [[start + i * step, level, level, level, level] for i in range(n)]
    for i, high, low in wicks:
        rows[i][2] = max(rows[i][2], high)
        rows[i][3] = min(rows[i][3], low)
    if close is not None:
        rows[-1][4] = close
        rows[-1][2] = max(rows[-1][2], close)
        rows[-1][3] = min(rows[-1][3], close)
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close"])


def at(i: int, start: pd.Timestamp = TUE) -> pd.Timestamp:
    return start + i * M15


def only(narrative: pd.DataFrame) -> pd.Series:
    assert len(narrative) == 1
    return narrative.iloc[0]


# ── Requirement 1: the candle narrative ─────────────────────────────────────

def test_up_day_low_first():
    bars = candle_bars(TUE, close=1.1020, wicks=((40, 1.1000, 1.0980), (70, 1.1050, 1.1000)))
    c = only(narrate(bars, Timeframe.M15, Timeframe.D1))
    assert tuple(narrate(bars, Timeframe.M15, Timeframe.D1).columns) == NARRATIVE_COLUMNS
    assert c.start == TUE and c.end == TUE + timedelta(days=1)
    assert (c.open, c.high, c.low, c.close) == (1.1000, 1.1050, 1.0980, 1.1020)
    assert c.range == pytest.approx(0.0070)
    assert c.t_low == at(40) and c.t_high == at(70)
    assert c.direction == "UP"
    assert (c.false_price, c.t_false, c.exp_price, c.t_exp) == (1.0980, at(40), 1.1050, at(70))
    assert not c.inverted
    assert c.false_move == pytest.approx(0.0020) and c.false_share == pytest.approx(2 / 7)
    assert (c.low_child, c.high_child) == (2, 4)        # the 01:00 and 09:00 New York H4 slots
    assert c.complete


def test_down_day_and_flat_day():
    down = only(narrate(candle_bars(TUE, close=1.0990, wicks=((20, 1.1030, 1.1000), (80, 1.1000, 1.0960))),
                        Timeframe.M15, Timeframe.D1))
    assert down.direction == "DOWN"
    assert (down.false_price, down.t_false, down.exp_price, down.t_exp) == (1.1030, at(20), 1.0960, at(80))
    assert down.false_move == pytest.approx(0.0030) and not down.inverted

    flat = only(narrate(candle_bars(TUE, wicks=((20, 1.1030, 1.0970),)), Timeframe.M15, Timeframe.D1))
    assert flat.direction == "FLAT"
    assert math.isnan(flat.false_price) and math.isnan(flat.exp_price) and math.isnan(flat.false_share)
    assert pd.isna(flat.t_false) and pd.isna(flat.t_exp) and not flat.inverted


def test_inverted_day():
    c = only(narrate(candle_bars(TUE, close=1.1010, wicks=((20, 1.1050, 1.1000), (60, 1.1000, 1.0980))),
                     Timeframe.M15, Timeframe.D1))
    assert c.direction == "UP" and c.t_exp == at(20) and c.t_false == at(60) and c.inverted


def test_ties_take_the_first_bar():
    c = only(narrate(candle_bars(TUE, close=1.1010, wicks=((30, 1.1040, 1.1000), (50, 1.1040, 1.1000),
                                                           (10, 1.1000, 1.0990), (11, 1.1000, 1.0990))),
                     Timeframe.M15, Timeframe.D1))
    assert c.t_high == at(30) and c.t_low == at(10)


def test_incomplete_edges():
    two_days = pd.concat([candle_bars(TUE, close=1.1010), candle_bars(TUE + timedelta(days=1), level=1.1010)],
                         ignore_index=True)
    assert narrate(two_days, Timeframe.M15, Timeframe.D1).complete.tolist() == [True, True]
    late_start = two_days.iloc[10:].reset_index(drop=True)
    assert narrate(late_start, Timeframe.M15, Timeframe.D1).complete.tolist() == [False, True]
    early_end = two_days.iloc[:-5].reset_index(drop=True)
    assert narrate(early_end, Timeframe.M15, Timeframe.D1).complete.tolist() == [True, False]


def test_week_child_index_from_sunday():
    h1 = timedelta(hours=1)
    monday = pd.Timestamp("2026-01-11 22:00", tz="UTC")                  # Sunday 17:00 New York
    week = candle_bars(monday, n=120, close=1.1020, step=h1,
                       wicks=((0, 1.1000, 1.0950), (60, 1.1080, 1.1000)))   # Monday's first hour; Wednesday
    c = only(narrate(week, Timeframe.H1, Timeframe.W1))
    assert c.start == CAL.period_start(monday.to_pydatetime(), Timeframe.W1)
    assert (c.low_child, c.high_child) == (1, 3)        # 0 is the server's Sunday, empty for FX

    no_monday = week.iloc[24:].reset_index(drop=True)                    # a holiday: Monday has no bars
    c = only(narrate(no_monday, Timeframe.H1, Timeframe.W1))
    assert c.high_child == 3 and c.low_child == 2 and not c.complete


def test_refuses_bars_not_finer_than_frame():
    h4 = candle_bars(TUE, n=6, step=timedelta(hours=4))
    with pytest.raises(ValueError, match="H4"):
        narrate(h4, Timeframe.H4, Timeframe.H4)
    with pytest.raises(ValueError, match="D1"):
        narrate(candle_bars(TUE, n=2, step=timedelta(days=1)), Timeframe.D1, Timeframe.H4)


def test_empty_bars_give_an_empty_narrative():
    empty = candle_bars(TUE, n=0)
    out = narrate(empty, Timeframe.M15, Timeframe.D1)
    assert len(out) == 0 and tuple(out.columns) == NARRATIVE_COLUMNS


def test_fill_phase_cases():
    up = only(narrate(candle_bars(TUE, close=1.1020, wicks=((40, 1.1000, 1.0980), (70, 1.1050, 1.1000))),
                      Timeframe.M15, Timeframe.D1))
    assert fill_phase(up, at(10)) == "BEFORE_FALSE_EXTREME"
    assert fill_phase(up, at(40)) == "AT_FALSE_EXTREME"
    assert fill_phase(up, at(41)) == "IN_EXPANSION"
    assert fill_phase(up, at(70)) == "IN_EXPANSION"
    assert fill_phase(up, at(71)) == "AFTER_EXPANSION"

    inverted = only(narrate(candle_bars(TUE, close=1.1010, wicks=((20, 1.1050, 1.1000), (60, 1.1000, 1.0980))),
                            Timeframe.M15, Timeframe.D1))
    assert fill_phase(inverted, at(70)) == "INVERTED"
    flat = only(narrate(candle_bars(TUE), Timeframe.M15, Timeframe.D1))
    assert fill_phase(flat, at(10)) == "UNKNOWN"
    partial = narrate(candle_bars(TUE, close=1.1020).iloc[5:].reset_index(drop=True), Timeframe.M15, Timeframe.D1)
    assert fill_phase(only(partial), at(10)) == "UNKNOWN"
    assert fill_phase(None, at(10)) == "UNKNOWN"


# ── Requirement 2: the price basis ─────────────────────────────────────────

def rollover_bars(day: str, utc_offset: int) -> pd.DataFrame:
    """16:00-17:45 New York M15 bars; the 17:00 and 17:15 bars dip like a blown-out bid."""
    start = pd.Timestamp(f"{day} 16:00", tz="UTC") + timedelta(hours=-utc_offset)
    rows = []
    for i in range(8):
        price = 1.1000 + i * 0.0001
        low = 1.0950 if i in (4, 5) else price
        rows.append([start + i * M15, price, price + 0.0002, low, price + 0.0001])
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close"])


@pytest.mark.parametrize("day,offset", [("2026-01-13", -5), ("2026-07-14", -4)])
def test_rollover_window_flattens_fx(day, offset):
    bars = rollover_bars(day, offset)
    out = apply_price_basis(bars, "EURUSD", PriceBasis())
    last_clean = bars.close.iloc[3]                                   # the 16:45 bar's close
    for i in (4, 5):                                                  # 17:00 and 17:15 New York
        assert out.loc[i, ["open", "high", "low", "close"]].tolist() == [last_clean] * 4
    for i in (0, 1, 2, 3, 6, 7):
        assert out.loc[i, ["open", "high", "low", "close"]].tolist() == bars.loc[i, ["open", "high", "low", "close"]].tolist()
    assert bars.low.iloc[4] == 1.0950                                 # the input is not changed


def test_rollover_window_minutes():
    bars = rollover_bars("2026-01-13", -5)
    out = apply_price_basis(bars, "GBPUSD", PriceBasis(minutes=15))
    assert out.low.iloc[4] == bars.close.iloc[3] and out.low.iloc[5] == 1.0950


def test_rollover_window_drops_leading_bars():
    bars = rollover_bars("2026-01-13", -5).iloc[4:].reset_index(drop=True)   # starts at 17:00 New York
    out = apply_price_basis(bars, "USDJPY", PriceBasis())
    assert out.time.tolist() == bars.time.iloc[2:].tolist()


def test_gold_untouched_and_basis_none():
    bars = rollover_bars("2026-01-13", -5)
    pd.testing.assert_frame_equal(apply_price_basis(bars, "XAUUSD", PriceBasis()), bars)
    pd.testing.assert_frame_equal(apply_price_basis(bars, "EURUSD", PriceBasis(rule="NONE")), bars)


# ── configuration ───────────────────────────────────────────────────────────

def test_config_defaults_and_toml(tmp_path):
    cfg = NarrativeConfig()
    assert cfg.frames == (Timeframe.W1, Timeframe.D1, Timeframe.H4) and cfg.bias_frame == Timeframe.D1
    assert cfg.direction_rule == "CLOSE_VS_OPEN" and cfg.resamples == 2000
    assert cfg.price_basis == PriceBasis("ROLLOVER_WINDOW", 30, ("EURUSD", "GBPUSD", "USDJPY"))
    assert load_narrative_config() == cfg                             # config/research/narrative.toml
    assert (REPO / "config" / "research" / "narrative.toml").is_file()

    path = tmp_path / "n.toml"
    path.write_text('frames = ["D1", "H4"]\nbias_frame = "H4"\n[price_basis]\nrule = "NONE"\n', encoding="utf-8")
    custom = load_narrative_config(path)
    assert custom.frames == (Timeframe.D1, Timeframe.H4) and custom.bias_frame == Timeframe.H4
    assert custom.price_basis.rule == "NONE" and custom.price_basis.minutes == 30


@pytest.mark.parametrize("text,key", [
    ('colour = "red"\n', "colour"),
    ('[price_basis]\nwindow = 30\n', "window"),
    ('[price_basis]\nrule = "SPREAD"\n', "rule"),
    ('[price_basis]\nminutes = 0\n', "minutes"),
    ('[price_basis]\nminutes = 61\n', "minutes"),
    ('direction_rule = "DRAW_DELIVERED"\n', "direction_rule"),
    ('frames = ["D1", "H4"]\nbias_frame = "W1"\n', "bias_frame"),
    ('frames = ["D2"]\n', "frames"),
])
def test_config_rejects_unknown_keys_and_values(tmp_path, text, key):
    path = tmp_path / "bad.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=key):
        load_narrative_config(path)


# ── Properties ──────────────────────────────────────────────────────────────

def walk(steps: list[int], start: pd.Timestamp = TUE) -> pd.DataFrame:
    """M15 bars from integer tick steps: each bar's open is the last close, its wick one step out."""
    rows, price = [], 10_000
    for i, (move, wick) in enumerate(zip(steps[0::2], steps[1::2])):
        close = price + move
        rows.append([start + i * M15, price / 1e4, (max(price, close) + abs(wick)) / 1e4,
                     (min(price, close) - abs(wick) // 2) / 1e4, close / 1e4])
        price = close
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close"])


def to_h1(m15: pd.DataFrame) -> pd.DataFrame:
    key = [CAL.period_start(t.to_pydatetime(), Timeframe.H1) for t in m15.time]
    g = m15.assign(key=key).groupby("key", sort=True)
    out = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last()})
    return out.rename_axis("time").reset_index().assign(time=lambda d: pd.to_datetime(d.time, utc=True))


_steps = st.lists(st.integers(-8, 8), min_size=2 * 96 * 2, max_size=2 * 96 * 2)


@settings(max_examples=100, deadline=None)
@given(_steps, st.sampled_from([Timeframe.D1, Timeframe.H4]))
def test_property_1_resolution_invariance(steps, frame):
    """Property 1: narrating from M15 or from the same bars as H1 tells the same story."""
    m15 = walk(steps)
    fine, coarse = narrate(m15, Timeframe.M15, frame), narrate(to_h1(m15), Timeframe.H1, frame)
    assert len(fine) == len(coarse)
    for a, b in zip(fine.itertuples(), coarse.itertuples()):
        assert (a.open, a.high, a.low, a.close, a.direction) == (b.open, b.high, b.low, b.close, b.direction)
        assert (a.high_child, a.low_child) == (b.high_child, b.low_child)
        floor = lambda t: CAL.period_start(t.to_pydatetime(), Timeframe.H1)  # noqa: E731
        assert b.t_high == floor(a.t_high) and b.t_low == floor(a.t_low)
        if a.direction != "FLAT" and floor(a.t_false) != floor(a.t_exp):
            assert a.inverted == b.inverted


@settings(max_examples=100, deadline=None)
@given(st.lists(st.integers(-8, 8), min_size=2 * 96 * 3, max_size=2 * 96 * 3), st.integers(0, 2**31 - 1))
def test_property_2_locality(steps, seed):
    """Property 2: under price basis NONE, bars outside a candle don't change its narrative."""
    bars = walk(steps)
    middle = narrate(bars, Timeframe.M15, Timeframe.D1).iloc[1]
    outside = (bars.time < middle.start) | (bars.time >= middle.end)
    noise = np.random.default_rng(seed).normal(0, 0.001, outside.sum())
    moved = bars.copy()
    for name in ("open", "high", "low", "close"):
        moved.loc[outside, name] = moved.loc[outside, name] + noise
    moved.loc[outside, "high"] = moved.loc[outside, ["open", "high", "low", "close"]].max(axis=1)
    moved.loc[outside, "low"] = moved.loc[outside, ["open", "high", "low", "close"]].min(axis=1)
    again = narrate(moved, Timeframe.M15, Timeframe.D1).iloc[1]
    pd.testing.assert_series_equal(middle, again)
