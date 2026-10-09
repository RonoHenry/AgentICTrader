"""
Tests for algo_research/features/anticipation.py — the engine's anticipation
of each D1 candle, on every row of the candle.

Task 248 (.kiro/specs/algo-research/tasks.md). Real data: the backtester's task
186 fixture week, with the small engine windows of the Phase A tests.
Validates: Requirements 4.1-4.4 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import math
from datetime import date, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from algo_research.features.anticipation import (
    ANTICIPATION_COLUMNS,
    anticipation_key,
    daily_anticipation,
    join_anticipation,
)
from algo_research.features.market import market_features
from algo_research.frame import build_grid, frame_from_data
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import BiasDirection
from services.market_data.as_of_view import compose_as_of_view
from services.market_data.strategy_calendar import StrategyCalendar
from tests.test_backtest_signals import CFG, data_for

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
CAL = StrategyCalendar()
SLICES = {"explore": (date(2026, 9, 29), date(2026, 10, 3))}
TREND = {"BULLISH": "UP", "BEARISH": "DOWN", "NEUTRAL": "NEUTRAL"}


class SpyEngine:
    def __init__(self, fail_on: date | None = None):
        self.calls = []
        self.fail_on = fail_on
        self.engine = LiquidityMappingEngine()

    def analyze(self, view, instrument, t):
        self.calls.append((instrument, t))
        if self.fail_on is not None and t.astimezone(NY).date() + timedelta(days=1) == self.fail_on:
            raise ValueError("engine blew up")
        return self.engine.analyze(view, instrument, t)


@lru_cache(maxsize=None)
def market(instrument: str = "EURUSD") -> pd.DataFrame:
    frame = frame_from_data(data_for(instrument), typical_spread=0.00008, stop_slippage=0.00002)
    return market_features(frame, build_grid(frame, SLICES))


@lru_cache(maxsize=None)
def built(instrument: str = "EURUSD"):
    spy = SpyEngine()
    daily, errors = daily_anticipation(data_for(instrument), market(instrument), CFG, engine=spy)
    return daily, errors, spy.calls, join_anticipation(market(instrument), daily)


def null(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def test_one_engine_call_per_instrument_day_at_17_15():
    daily, errors, calls, _ = built("EURUSD")
    dates = sorted(market("EURUSD")["trading_date"].dt.date.unique())
    assert [d.date() for d in daily["trading_date"]] == dates
    assert len(calls) == len(dates) and errors == []
    for (_, t), d in zip(calls, dates):
        local = t.astimezone(NY)
        assert (local.hour, local.minute) == (17, 15), t       # the candle's first M15 close with data
        assert local.date() + timedelta(days=1) == d
    # Gold stops 17:00-18:00 New York: its first close with data is later.
    _, _, gold_calls, _ = built("XAUUSD")
    assert all(t.astimezone(NY).hour >= 17 for _, t in gold_calls)


def test_anticipation_on_every_row_from_the_first_close():
    daily, _, _, rows = built("EURUSD")
    assert list(rows.columns[-len(ANTICIPATION_COLUMNS):]) == list(ANTICIPATION_COLUMNS)
    for _, day in daily.iterrows():
        same = rows[rows["trading_date"] == day["trading_date"]]
        before, after = same[same["t"] < day["ant_at"]], same[same["t"] >= day["ant_at"]]
        assert len(after) > 50
        assert after["ant_direction"].nunique() == 1 and after["ant_direction"].iloc[0] == day["ant_direction"]
        assert before["ant_direction"].isna().all()               # known from its first close, not before


def test_anticipation_equals_profile_at_any_t_in_the_candle():
    # Liquidity-engine Property 35: the anticipation is the same at every t in the candle.
    data = data_for("EURUSD")
    _, _, _, rows = built("EURUSD")
    engine = LiquidityMappingEngine()
    known = rows[rows["ant_direction"].notna()]
    for _, row in known.iloc[::23].iterrows():
        t = row["t"].to_pydatetime()
        view = compose_as_of_view(data.closed, data.m1, t, CFG.entry_tf, CFG.candle_counts, CAL)
        profile = engine.analyze(view, "EURUSD", t).candle_profile
        assert profile is not None, t
        assert (row["ant_trend"], row["ant_direction"]) == (profile.trend.value, profile.direction.value), t
        for prefix, objective in (("ant_draw", profile.draw), ("ant_draw_above", profile.draw_above),
                                  ("ant_draw_below", profile.draw_below)):
            if objective is None:
                assert null(row[f"{prefix}_price"]) and null(row[f"{prefix}_source"]), (t, prefix)
            else:
                assert (row[f"{prefix}_price"], row[f"{prefix}_source"], row[f"{prefix}_tf"]) == (
                    objective.price, objective.source, objective.timeframe.value), (t, prefix)


def test_engine_error_leaves_the_day_null_and_counted():
    failing = date(2026, 9, 30)
    daily, errors = daily_anticipation(data_for("EURUSD"), market("EURUSD"), CFG, engine=SpyEngine(fail_on=failing))
    assert len(errors) == 1 and "2026-09-30" in errors[0] and "engine blew up" in errors[0]
    rows = join_anticipation(market("EURUSD"), daily)
    day = rows[rows["trading_date"] == pd.Timestamp(failing)]
    assert len(day) > 0 and day["ant_direction"].isna().all()
    other = rows[rows["trading_date"] == pd.Timestamp(date(2026, 10, 1))]
    assert other["ant_direction"].notna().any()


def test_w1_trend_equals_ant_trend():
    # Property 4: the feature's W1 trend is the engine's (LE-D15) on every trading date.
    for instrument in ("EURUSD", "XAUUSD"):
        _, _, _, rows = built(instrument)
        known = rows[rows["ant_trend"].notna()]
        assert len(known) > 0
        assert (known["w1_trend"] == known["ant_trend"].map(TREND)).all(), instrument


def test_cache_key_includes_engine_fingerprint_and_config():
    base = anticipation_key("EURUSD", "sha", "engine-a", CFG, ["2026-09-29"])
    assert base == anticipation_key("EURUSD", "sha", "engine-a", CFG, ["2026-09-29"])
    assert base != anticipation_key("EURUSD", "sha", "engine-b", CFG, ["2026-09-29"])
    assert base != anticipation_key("EURUSD", "sha2", "engine-a", CFG, ["2026-09-29"])
    assert base != anticipation_key("EURUSD", "sha", "engine-a", CFG.model_copy(update={"min_rr": 4.0}),
                                    ["2026-09-29"])
    assert base != anticipation_key("EURUSD", "sha", "engine-a", CFG, ["2026-09-29", "2026-09-30"])


def test_bias_values_are_the_engines():
    daily, _, _, _ = built("EURUSD")
    assert set(daily["ant_direction"].dropna()) <= {d.value for d in BiasDirection}


def test_build_includes_the_anticipation(tmp_path, capsys):
    from algo_research.cli import main
    from tests.test_research_snapshot import MultiFixtureSource, fixture_root

    root = fixture_root(tmp_path / "repo", profile="exness-standard")
    dirs = dict(root=root, snapshots_dir=tmp_path / "snapshots", cache_dir=tmp_path / "cache")
    assert main(["snapshot"], source_factory=lambda profile: MultiFixtureSource(), **dirs) == 0
    assert main(["build", "--workers", "1"], **dirs) == 0
    out = capsys.readouterr().out
    assert "engine: 0 day(s) without an anticipation" in out
    entries = sorted((tmp_path / "cache" / "anticipation").glob("*.parquet"))
    assert len(entries) == 2
    daily = pd.read_parquet(entries[0])
    assert daily["ant_direction"].notna().all() and daily["error"].isna().all()
