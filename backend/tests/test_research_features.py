"""
Tests for algo_research/features/market.py and features/cache.py — the market
features known at each M15 close, and their cache.

Task 247 (.kiro/specs/algo-research/tasks.md). Hand-made M1 paths
(tests/research_fixtures.py) state the prices each test reasons about; the
backtester's task 186 fixture week checks engine parity and Property 1 on
real data.
Validates: Requirements 2.4, 3.1-3.5 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algo_research.features.cache import ParquetCache, cache_key, code_fingerprint
from algo_research.features.market import COLUMNS, market_features
from algo_research.frame import BAR_TIMEFRAMES, InstrumentFrame, build_grid, frame_from_data
from liquidity_engine.grader.sequence import asian_pools
from liquidity_engine.models import Candle, LiquiditySource
from liquidity_engine.models import Timeframe as TF
from liquidity_engine.profile.candle_profile import MANIPULATION_WINDOW
from liquidity_engine.utils.candle_utils import calculate_atr
from liquidity_engine.utils.time_utils import get_killzone, ny_time_in_day, trading_day_open
from services.market_data.as_of_view import aggregate
from services.market_data.strategy_calendar import StrategyCalendar
from tests.research_fixtures import MIN, Path, crt_path, grid_for, ny
from tests.test_backtest_signals import data_for

UTC = timezone.utc
CAL = StrategyCalendar()


def features_of(path: Path, first: date, end: date) -> pd.DataFrame:
    frame = path.frame()
    return market_features(frame, grid_for(frame, first, end)).set_index("t")


def at(features: pd.DataFrame, t: datetime) -> pd.Series:
    return features.loc[pd.Timestamp(t)]


def null(value) -> bool:
    return value is None or value is pd.NaT or (isinstance(value, float) and math.isnan(value))


# ── hand-made frames ────────────────────────────────────────────────────────

def test_opens_and_sides():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 9, 17))
    path.bar(ny(2026, 1, 4, 17), o=1.1010)                 # the Monday candle's first bar
    path.bar(ny(2026, 1, 5, 0), o=1.1050)                  # its first bar at or after midnight
    path.bar(ny(2026, 1, 5, 5), o=1.1020)                  # the 05:00 H4 candle's first bar
    path.bar(ny(2026, 1, 5, 5, 14), c=1.1030)              # the close at 05:15
    f = features_of(path, date(2026, 1, 5), date(2026, 1, 6))

    first = at(f, ny(2026, 1, 4, 17, 15))
    assert first["d1_open"] == 1.1010
    assert null(first["midnight_open"])
    assert null(at(f, ny(2026, 1, 5, 0, 0))["midnight_open"])       # the 00:00 bar hasn't closed at 00:00
    assert at(f, ny(2026, 1, 5, 0, 15))["midnight_open"] == 1.1050
    assert null(at(f, ny(2026, 1, 5, 5, 0))["h4_open"])             # no bar of the 05:00 H4 candle closed yet
    row = at(f, ny(2026, 1, 5, 5, 15))
    assert (row["h4_open"], row["close"]) == (1.1020, 1.1030)
    assert (row["side_d1_open"], row["side_midnight_open"], row["side_h4_open"]) == (1, -1, 1)
    # 17:00 opens the next candle: nothing of it has closed yet.
    assert null(at(f, ny(2026, 1, 4, 17, 0))["d1_open"]) if ny(2026, 1, 4, 17, 0) in f.index else True


def test_day_extremes_so_far_earliest_on_tie():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17))
    path.bar(ny(2026, 1, 5, 2, 0), h=1.1100).bar(ny(2026, 1, 5, 3, 0), h=1.1100)
    path.bar(ny(2026, 1, 5, 3, 30), lo=1.0900)
    f = features_of(path, date(2026, 1, 5), date(2026, 1, 6))
    assert at(f, ny(2026, 1, 5, 2, 0))["day_high"] == pytest.approx(1.1001)
    row = at(f, ny(2026, 1, 5, 4, 0))
    assert (row["day_high"], row["day_high_at"]) == (1.1100, pd.Timestamp(ny(2026, 1, 5, 2, 0)))
    assert (row["day_low"], row["day_low_at"]) == (1.0900, pd.Timestamp(ny(2026, 1, 5, 3, 30)))
    assert at(f, ny(2026, 1, 5, 3, 30))["day_low"] == pytest.approx(1.0999)   # the 03:30 bar closes at 03:31


def asia_path() -> Path:
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17))
    path.bar(ny(2026, 1, 4, 19, 0), h=1.1200)              # before the session: not Asian
    path.bar(ny(2026, 1, 4, 21, 30), h=1.1060)
    path.bar(ny(2026, 1, 4, 22, 10), lo=1.0950)
    path.bar(ny(2026, 1, 5, 2, 7), h=1.1070)               # the first bar beyond the Asian high
    path.bar(ny(2026, 1, 5, 2, 30), h=1.1080)
    path.bar(ny(2026, 1, 5, 3, 20), lo=1.0940)             # and beyond the Asian low
    return path


def test_asia_range_known_at_midnight():
    path = asia_path()
    f = features_of(path, date(2026, 1, 5), date(2026, 1, 6))
    assert null(at(f, ny(2026, 1, 4, 23, 45))["asia_high"])
    row = at(f, ny(2026, 1, 5, 0, 0))
    assert (row["asia_high"], row["asia_low"]) == (1.1060, 1.0950)
    # The engine's definition (LE-D12): asian_pools() over the H1 bars.
    m1 = path.frame().m1
    h1 = [Candle(timestamp=r.time.to_pydatetime(), open=r.open, high=r.high, low=r.low, close=r.close,
                 timeframe=TF.H1, instrument="EURUSD") for r in path.frame().bars[TF.H1].itertuples()]
    pools = {p.source: p.price for p in asian_pools(h1, ny(2026, 1, 5, 0, 0))}
    assert pools == {LiquiditySource.ASIA_HIGH: 1.1060, LiquiditySource.ASIA_LOW: 1.0950}
    assert len(m1) > 0


def test_asia_raided_at_first_m1_beyond():
    f = features_of(asia_path(), date(2026, 1, 5), date(2026, 1, 6))
    assert null(at(f, ny(2026, 1, 5, 2, 0))["asia_high_raided_at"])
    assert at(f, ny(2026, 1, 5, 2, 15))["asia_high_raided_at"] == pd.Timestamp(ny(2026, 1, 5, 2, 8))   # its close
    assert at(f, ny(2026, 1, 5, 2, 45))["asia_high_raided_at"] == pd.Timestamp(ny(2026, 1, 5, 2, 8))   # the first
    assert null(at(f, ny(2026, 1, 5, 3, 15))["asia_low_raided_at"])
    row = at(f, ny(2026, 1, 5, 3, 30))
    assert row["asia_low_raided_at"] == pd.Timestamp(ny(2026, 1, 5, 3, 21))
    # Extremes since midnight: the raid's furthest price so far.
    assert (row["post_midnight_high"], row["post_midnight_low"]) == (1.1080, 1.0940)
    assert null(at(f, ny(2026, 1, 4, 23, 45))["post_midnight_high"])


def test_previous_levels_and_taken_at():
    path = Path(ny(2025, 12, 28, 17), ny(2026, 1, 9, 17))
    path.bar(ny(2025, 12, 30, 10, 0), h=1.1300).bar(ny(2025, 12, 31, 10, 0), lo=1.0700)    # last week's range
    path.bar(ny(2026, 1, 5, 10, 0), h=1.1200).bar(ny(2026, 1, 5, 11, 0), lo=1.0800)        # Monday's range
    path.bar(ny(2026, 1, 6, 3, 0), h=1.1210)                                               # Tuesday takes PDH
    path.bar(ny(2026, 1, 7, 9, 0), h=1.1310)                                               # Wednesday takes PWH
    f = features_of(path, date(2026, 1, 5), date(2026, 1, 9))

    tue = at(f, ny(2026, 1, 5, 17, 0))                       # Tuesday's candle opens: Monday just closed
    assert (tue["pdh"], tue["pdl"]) == (1.1200, 1.0800)
    assert (tue["pwh"], tue["pwl"]) == (1.1300, 1.0700)
    assert null(at(f, ny(2026, 1, 6, 3, 0))["pdh_taken_at"])
    assert at(f, ny(2026, 1, 6, 3, 15))["pdh_taken_at"] == pd.Timestamp(ny(2026, 1, 6, 3, 1))
    assert null(at(f, ny(2026, 1, 6, 3, 15))["pdl_taken_at"])
    assert null(at(f, ny(2026, 1, 7, 9, 0))["pwh_taken_at"])
    wed = at(f, ny(2026, 1, 7, 9, 15))
    assert wed["pwh_taken_at"] == pd.Timestamp(ny(2026, 1, 7, 9, 1))
    assert wed["pdh"] == 1.1210                              # Tuesday's high
    # PWH is the same all week and stays taken; PDH resets with each candle.
    assert at(f, ny(2026, 1, 8, 9, 15))["pwh_taken_at"] == pd.Timestamp(ny(2026, 1, 7, 9, 1))
    assert at(f, ny(2026, 1, 8, 9, 15))["pdh"] == 1.1310


@pytest.mark.parametrize("friday_close, trend", [(1.1050, "UP"), (1.0950, "DOWN"), (1.1000, "NEUTRAL")])
def test_w1_trend_closure_rule(friday_close, trend):
    # LE-D15: the last closed week closed beyond the previous week's range.
    path = Path(ny(2025, 12, 21, 17), ny(2026, 1, 9, 17))     # weeks of Dec 22, Dec 29 and Jan 5
    path.bar(ny(2026, 1, 2, 16, 59), c=friday_close)
    f = features_of(path, date(2025, 12, 22), date(2026, 1, 9))
    assert at(f, ny(2026, 1, 5, 9, 0))["w1_trend"] == trend
    assert null(at(f, ny(2025, 12, 31, 9, 0))["w1_trend"])     # one closed week isn't enough
    assert at(f, ny(2026, 1, 5, 9, 0))["prev_week_dir"] == (1 if friday_close > 1.1 else -1 if friday_close < 1.1 else 0)


def test_null_without_history():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 9, 17))
    f = features_of(path, date(2026, 1, 5), date(2026, 1, 10))
    first = at(f, ny(2026, 1, 4, 17, 15))
    for name in ("pdh", "pdl", "pwh", "pwl", "prev_day_dir", "prev_week_dir", "w1_trend", "atr_d1", "atr_m15",
                 "spread_to_atr", "asia_high", "pdh_taken_at"):
        assert null(first[name]), name
    assert first["typical_spread"] == 0.0001
    # ATR(14) needs 15 closed bars: 14 true ranges.
    assert null(at(f, ny(2026, 1, 4, 20, 30))["atr_m15"])        # 14 closed M15 bars
    assert not null(at(f, ny(2026, 1, 4, 20, 45))["atr_m15"])    # 15


# ── candle ranges: C1 and C2 (Requirement 15, update 2026-10c) ──────────────

def test_crt_side_and_ranges():
    f = features_of(crt_path(), date(2026, 1, 5), date(2026, 1, 6))
    row = at(f, ny(2026, 1, 5, 9, 0))                                # the 05:00 H4 candle (C2) just closed
    assert row["crt_h4_at"] == pd.Timestamp(ny(2026, 1, 5, 9, 0))
    assert (row["crt_h4_c1_high"], row["crt_h4_c1_low"]) == (1.1050, 1.0950)
    assert (row["crt_h4_c2_high"], row["crt_h4_c2_low"]) == (1.1020, 1.0940)
    assert row["crt_h4_side"] == 1                                    # C1's low swept, closed back above it
    later = at(f, ny(2026, 1, 5, 12, 45))                            # the same C2 until the next H4 closes
    assert (later["crt_h4_at"], later["crt_h4_side"]) == (pd.Timestamp(ny(2026, 1, 5, 9, 0)), 1)
    assert at(f, ny(2026, 1, 5, 5, 0))["crt_h4_side"] == 0           # the 01:00 candle swept both sides
    sides = [at(f, ny(2026, 1, 5, h, 0))["crt_h1_side"] for h in range(3, 9)]
    assert sides == [-1, 1, 0, -1, 1, 0]
    assert at(f, ny(2026, 1, 5, 7, 0))["crt_h1_c1_high"] == 1.1020


def test_crt_side_needs_the_close_back_inside():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17), base=1.1000)
    path.bar(ny(2026, 1, 5, 2, 0), h=1.1050).bar(ny(2026, 1, 5, 3, 0), lo=1.0950)
    path.level(ny(2026, 1, 5, 8, 0), ny(2026, 1, 5, 9, 0), 1.0930)     # C2 ends below C1's low
    f = features_of(path, date(2026, 1, 5), date(2026, 1, 6))
    row = at(f, ny(2026, 1, 5, 9, 0))
    assert row["crt_h4_c2_low"] == pytest.approx(1.0929) and row["crt_h4_side"] == 0


def test_crt_c1_is_the_previous_bar_with_data():
    path = Path(ny(2026, 1, 2, 9), ny(2026, 1, 5, 17))                # Friday 09:00 to Monday
    path.bar(ny(2026, 1, 2, 14, 0), h=1.1070)                         # Friday's last H4 candle
    f = features_of(path, date(2026, 1, 5), date(2026, 1, 6))
    first = at(f, ny(2026, 1, 4, 17, 15))                             # Sunday's open: C2 is Friday's last H4
    assert first["crt_h4_at"] == pd.Timestamp(ny(2026, 1, 2, 17, 0))
    assert first["crt_h4_c2_high"] == 1.1070
    row = at(f, ny(2026, 1, 4, 21, 0))                                # Monday's first H4 has closed
    assert row["crt_h4_c1_high"] == 1.1070


def test_crt_null_without_c1():
    f = features_of(crt_path(), date(2026, 1, 5), date(2026, 1, 7))
    for name in ("crt_h4_at", "crt_h4_side", "crt_h4_c1_high", "crt_h4_c2_low"):
        assert null(at(f, ny(2026, 1, 4, 17, 15))[name]), name       # no H4 candle closed yet
    assert null(at(f, ny(2026, 1, 4, 21, 0))["crt_h4_side"])          # C2 but no C1
    assert null(at(f, ny(2026, 1, 5, 17, 15))["crt_d1_side"])         # Monday's D1 has no C1 in the data


def test_columns_are_documented():
    frame = Path(ny(2026, 1, 4, 17), ny(2026, 1, 5, 17)).frame()
    f = market_features(frame, grid_for(frame, date(2026, 1, 5), date(2026, 1, 6)))
    assert list(f.columns) == list(COLUMNS)
    for name, doc in COLUMNS.items():
        assert doc.definition and doc.unit and doc.known_at, name


# ── real data: ATR, engine parity (Property 4), the past only (Property 1) ──

FIXTURE_SLICES = {"explore": (date(2026, 9, 29), date(2026, 10, 3))}


@lru_cache(maxsize=None)
def fixture() -> tuple[InstrumentFrame, pd.DataFrame]:
    frame = frame_from_data(data_for("EURUSD"), typical_spread=0.00008, stop_slippage=0.00002)
    return frame, market_features(frame, build_grid(frame, FIXTURE_SLICES))


def test_atr_matches_calculate_atr():
    data = data_for("EURUSD")
    _, f = fixture()
    for _, row in f.iloc[::37].iterrows():
        t = row["t"].to_pydatetime()
        d1 = [c for c in data.closed[TF.D1] if CAL.period_end(c.timestamp, TF.D1) <= t]
        m15 = [c for c in data.closed[TF.M15] if CAL.period_end(c.timestamp, TF.M15) <= t]
        assert row["atr_d1"] == calculate_atr(d1, 14), t
        assert row["atr_m15"] == calculate_atr(m15, 14), t
        assert row["spread_to_atr"] == 0.00008 / row["atr_d1"]


def test_property_4_engine_parity():
    data = data_for("EURUSD")
    h1 = aggregate(data.m1, TF.H1, CAL)
    _, f = fixture()
    checked = 0
    for _, row in f.iterrows():
        t = row["t"].to_pydatetime()
        pools = {p.source: p.price for p in asian_pools(h1, t)}
        assert pools.get(LiquiditySource.ASIA_HIGH) == (None if null(row["asia_high"]) else row["asia_high"]), t
        assert pools.get(LiquiditySource.ASIA_LOW) == (None if null(row["asia_low"]) else row["asia_low"]), t
        checked += bool(pools)
        assert row["killzone"] == get_killzone(t).value
        start, end = (ny_time_in_day(trading_day_open(t), at_) for at_ in MANIPULATION_WINDOW)
        assert row["in_window"] == (start <= t < end), t
    assert checked > 100


def _truncated(frame: InstrumentFrame, t: datetime) -> InstrumentFrame:
    cut = pd.Timestamp(t)
    m1 = frame.m1[frame.m1["time"] + pd.Timedelta(minutes=1) <= cut].reset_index(drop=True)
    bars = {tf: b[b["close_time"] <= cut].reset_index(drop=True) for tf, b in frame.bars.items()}
    return InstrumentFrame(frame.instrument, frame.typical_spread, frame.stop_slippage, m1, bars)


@settings(max_examples=25, deadline=None)
@given(st.data())
def test_property_1_features_use_only_the_past(data):
    frame, f = fixture()
    i = data.draw(st.integers(0, len(f) - 1))
    t = f["t"].iloc[i].to_pydatetime()
    short = _truncated(frame, t)
    again = market_features(short, build_grid(short, FIXTURE_SLICES))
    row = again[again["t"] == pd.Timestamp(t)]
    assert len(row) == 1, t
    expected, got = f.iloc[i], row.iloc[0]
    for name in COLUMNS:
        a, b = expected[name], got[name]
        assert (null(a) and null(b)) or a == b, (t, name, a, b)


# ── cache ───────────────────────────────────────────────────────────────────

def test_cache_key_changes_with_snapshot_and_code(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    code = code_fingerprint(("pkg/*.py",), root=tmp_path)
    key = cache_key("market", "EURUSD", {"rows": 10, "sha256": "aa"}, code, {"explore": ["2025-01-01", "2025-07-01"]})
    assert key == cache_key("market", "EURUSD", {"rows": 10, "sha256": "aa"}, code,
                            {"explore": ["2025-01-01", "2025-07-01"]})
    assert key != cache_key("market", "EURUSD", {"rows": 10, "sha256": "ab"}, code,
                            {"explore": ["2025-01-01", "2025-07-01"]})
    (tmp_path / "pkg" / "a.py").write_text("x = 2\n", encoding="utf-8")
    changed = code_fingerprint(("pkg/*.py",), root=tmp_path)
    assert changed != code
    assert key != cache_key("market", "EURUSD", {"rows": 10, "sha256": "aa"}, changed,
                            {"explore": ["2025-01-01", "2025-07-01"]})
    # Line endings don't count: Windows and Linux checkouts agree.
    (tmp_path / "pkg" / "a.py").write_bytes(b"x = 2\r\n")
    assert code_fingerprint(("pkg/*.py",), root=tmp_path) == changed


def test_cache_round_trip(tmp_path):
    _, f = fixture()
    cache = ParquetCache(tmp_path)
    assert cache.load("market", "k1") is None
    cache.store("market", "k1", f)
    back = cache.load("market", "k1")
    pd.testing.assert_frame_equal(back, f)


# ── the build command ───────────────────────────────────────────────────────

def test_build_command_builds_and_caches_market_features(tmp_path, capsys):
    from algo_research.cli import main
    from tests.test_research_snapshot import MultiFixtureSource, fixture_root

    root = fixture_root(tmp_path / "repo", profile="exness-standard")     # priced: typical spreads
    dirs = dict(root=root, snapshots_dir=tmp_path / "snapshots", cache_dir=tmp_path / "cache")
    assert main(["snapshot"], source_factory=lambda profile: MultiFixtureSource(), **dirs) == 0
    capsys.readouterr()

    assert main(["build"], **dirs) == 0
    out = capsys.readouterr().out
    assert "EURUSD:" in out and "XAUUSD:" in out and "timings:" in out
    entries = sorted((tmp_path / "cache" / "market").glob("*.parquet"))
    assert len(entries) == 2                                              # one per instrument
    table = pd.read_parquet(entries[0])
    assert list(table.columns) == list(COLUMNS) and len(table) > 100

    assert main(["build"], **dirs) == 0                                   # served from the cache
    out = capsys.readouterr().out
    assert ("from the cache: market:EURUSD, market:XAUUSD, labels:EURUSD, labels:XAUUSD, anticipation:EURUSD, "
            "anticipation:XAUUSD") in out
