"""
Tests for algo_research/labels.py — what happened after t, kept apart from what
was known at t.

Task 249 (.kiro/specs/algo-research/tasks.md). Hand-made M1 paths
(tests/research_fixtures.py), and the backtester's fixture week for Property 2.
Validates: Requirements 6.1-6.4 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import ast
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path as FilePath

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algo_research.features.market import market_features
from algo_research.frame import InstrumentFrame, build_grid, frame_from_data
from algo_research.labels import (
    CANDLE_LABELS,
    DRAW_LABELS,
    DRAW_LEVELS,
    FORWARD_LABELS,
    LABEL_COLUMNS,
    LEVELS,
    build_labels,
    candle_labels,
    forward_labels,
)
from tests.research_fixtures import Path, grid_for, ny
from tests.test_backtest_signals import data_for

REPO = FilePath(__file__).resolve().parents[2]


def labelled(path: Path, first: date, end: date) -> pd.DataFrame:
    frame = path.frame()
    features = market_features(frame, grid_for(frame, first, end))
    labels = build_labels(frame, features)
    assert list(labels.index) == list(features.index)
    return pd.concat([features, labels], axis=1).set_index("t")


def at(table: pd.DataFrame, t) -> pd.Series:
    return table.loc[pd.Timestamp(t)]


def null(value) -> bool:
    return value is None or (not isinstance(value, str) and bool(pd.isna(value)))


def test_label_columns_are_documented():
    # Update 2026-10e (Req 18.2): the engine's draws are labelled too, once the anticipation is joined.
    assert set(LABEL_COLUMNS) == set(FORWARD_LABELS) | set(DRAW_LABELS) | set(CANDLE_LABELS)
    for name, doc in LABEL_COLUMNS.items():
        assert doc.definition and doc.unit, name
    assert {"day_dir", "day_high_final", "day_low_final", "day_high_h4", "day_low_h4", "day_high_q",
            "day_low_q"} == set(CANDLE_LABELS)
    for level in LEVELS:
        assert f"{level}_hit_after" in FORWARD_LABELS and f"{level}_hit_at" in FORWARD_LABELS
    for level in DRAW_LEVELS:
        assert f"{level}_hit_after" in DRAW_LABELS and f"{level}_hit_at" in DRAW_LABELS


@pytest.mark.parametrize("day", [date(2026, 1, 9), date(2026, 3, 9), date(2026, 11, 2)])   # a Friday; both DST changes
def test_rem_move_to_last_m1_before_17_00(day):
    eve = day - timedelta(days=1)
    path = Path(ny(eve.year, eve.month, eve.day, 17) - timedelta(days=3), ny(day.year, day.month, day.day, 17)
                + timedelta(days=1))
    path.bar(ny(day.year, day.month, day.day, 16, 59), c=1.1050)       # the candle's last bar
    path.bar(ny(day.year, day.month, day.day, 17, 0), c=1.2000) if ny(day.year, day.month, day.day, 17) in path.index else None
    table = labelled(path, day, day + timedelta(days=1))
    row = at(table, ny(day.year, day.month, day.day, 9, 0))
    assert row["rem_close"] == 1.1050
    assert row["rem_move"] == pytest.approx(0.0050)
    assert null(row["rem_move_atr"])                                    # no ATR history in this path
    last = at(table, ny(day.year, day.month, day.day, 16, 45))
    assert last["rem_close"] == 1.1050


def test_rem_move_in_atr_units():
    path = Path(ny(2025, 12, 1, 17) - timedelta(days=1), ny(2026, 1, 9, 17))
    path.bar(ny(2026, 1, 8, 16, 59), c=1.1050)
    table = labelled(path, date(2026, 1, 8), date(2026, 1, 9))
    row = at(table, ny(2026, 1, 8, 9, 0))
    assert row["atr_d1"] > 0
    assert row["rem_move_atr"] == pytest.approx(row["rem_move"] / row["atr_d1"])


def test_forward_horizons():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 9, 17))
    path.bar(ny(2026, 1, 7, 9, 59), c=1.1010)                           # closes at 10:00 = t + 1 h
    path.bar(ny(2026, 1, 7, 10, 0), c=1.1020)                           # closes after t + 1 h: not in it
    path.bar(ny(2026, 1, 7, 17, 59), c=1.0990)                          # t + 4 h, past the D1 close
    table = labelled(path, date(2026, 1, 5), date(2026, 1, 10))
    assert at(table, ny(2026, 1, 7, 9, 0))["fwd_1h_close"] == 1.1010
    assert at(table, ny(2026, 1, 7, 9, 0))["fwd_1h_atr"] != at(table, ny(2026, 1, 7, 9, 0))["fwd_1h_atr"]   # NaN: no ATR
    assert at(table, ny(2026, 1, 7, 14, 0))["fwd_4h_close"] == 1.0990
    # Past the end of the data the horizon is unknown, not truncated.
    assert null(at(table, ny(2026, 1, 9, 14, 0))["fwd_4h_close"])
    assert not null(at(table, ny(2026, 1, 9, 14, 0))["fwd_1h_close"])


def test_level_hit_after_strictly_after_t_and_before_the_close():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 9, 17))
    path.bar(ny(2026, 1, 5, 10, 0), h=1.1200)                           # Monday's high: Tuesday's PDH
    path.bar(ny(2026, 1, 6, 3, 0), h=1.1210)                            # Tuesday 03:00 takes it
    path.bar(ny(2026, 1, 6, 9, 0), h=1.1215)                            # and again at 09:00, the bar opening at t
    path.bar(ny(2026, 1, 6, 17, 30), h=1.1300)                          # Wednesday's candle: not Tuesday's
    table = labelled(path, date(2026, 1, 6), date(2026, 1, 8))
    row = at(table, ny(2026, 1, 6, 2, 0))
    assert row["pdh_hit_after"] == True and row["pdh_hit_at"] == pd.Timestamp(ny(2026, 1, 6, 3, 1))   # noqa: E712
    row = at(table, ny(2026, 1, 6, 9, 0))
    assert row["pdh_hit_after"] == True and row["pdh_hit_at"] == pd.Timestamp(ny(2026, 1, 6, 9, 1))   # noqa: E712
    row = at(table, ny(2026, 1, 6, 9, 15))
    assert row["pdh_hit_after"] == False and null(row["pdh_hit_at"])  # noqa: E712  (17:30 is the next candle)
    assert row["pdl_hit_after"] == False                                 # noqa: E712
    # A level not known at t has no label.
    assert null(at(table, ny(2026, 1, 5, 18, 0))["asia_high_hit_after"])


def test_candle_labels():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 9, 17))
    path.bar(ny(2026, 1, 4, 17, 0), o=1.0900)                            # Monday's open
    path.bar(ny(2026, 1, 5, 2, 0), lo=1.0800).bar(ny(2026, 1, 5, 6, 0), lo=1.0800)   # the low, twice
    path.bar(ny(2026, 1, 5, 10, 0), h=1.1200)                            # the high, 09:00 H4
    path.bar(ny(2026, 1, 5, 16, 59), c=1.1100)                           # the close: an up day
    table = labelled(path, date(2026, 1, 5), date(2026, 1, 6))
    for t in (ny(2026, 1, 4, 18, 0), ny(2026, 1, 5, 12, 0)):            # the same on every row of the candle
        row = at(table, t)
        assert row["day_dir"] == 1
        assert (row["day_high_final"], row["day_low_final"]) == (1.1200, 1.0800)
        assert (row["day_high_h4"], row["day_low_h4"]) == (4, 2)         # the earliest low: 02:00, the 01:00 H4


# ── daily quarters (Requirement 17, update 2026-10c) ─────────────────────────

@pytest.mark.parametrize("day", [date(2026, 1, 5), date(2026, 3, 9), date(2026, 11, 2)])   # EST; after both DST changes
@pytest.mark.parametrize("hour, minute, quarter", [
    (17, 0, 0), (23, 59, 0),                     # the eve: 17:00-00:00, the rollover hour included (AR-D14)
    (0, 0, 1), (5, 59, 1), (6, 0, 2), (11, 59, 2), (12, 0, 3), (16, 59, 3)])
def test_daily_quarter_of_the_high_and_low(day, hour, minute, quarter):
    eve = day - timedelta(days=1)
    when = (eve if hour >= 17 else day, hour, minute)
    t = ny(when[0].year, when[0].month, when[0].day, when[1], when[2])
    path = Path(ny(eve.year, eve.month, eve.day, 17), ny(day.year, day.month, day.day, 17))
    path.bar(t, h=1.1200)
    other = ny(day.year, day.month, day.day, 3) if quarter != 1 else ny(day.year, day.month, day.day, 9)
    path.bar(other, lo=1.0800)
    days = candle_labels(path.frame()).set_index("trading_date")
    row = days.loc[pd.Timestamp(day)]
    assert row["day_high_q"] == quarter
    assert row["day_low_q"] == (1 if quarter != 1 else 2)


def test_candle_labels_per_date_frame():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17))
    frame = path.frame()
    days = candle_labels(frame)
    assert [d.date() for d in days["trading_date"]] == [date(2026, 1, 5), date(2026, 1, 6)]
    assert set(CANDLE_LABELS) <= set(days.columns)


# ── separation (Requirement 6.1) ────────────────────────────────────────────

def _imports(path: FilePath) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:   # relative: resolve against the package
                package = path.parent.relative_to(REPO).as_posix().replace("/", ".").split(".")
                base = ".".join(package[: len(package) - node.level + 1] + ([base] if base else []))
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def test_features_events_filters_do_not_import_labels():
    files = [*sorted((REPO / "algo_research" / "features").glob("*.py")), REPO / "algo_research" / "frame.py"]
    files += [p for p in (REPO / "algo_research" / "events.py", REPO / "algo_research" / "filters.py") if p.exists()]
    assert len(files) >= 5
    for path in files:
        leaks = {name for name in _imports(path) if name == "algo_research.labels" or
                 name.startswith("algo_research.labels.")}
        assert not leaks, f"{path.name} imports {leaks}"


# ── Property 2: forward labels use only the future ──────────────────────────

SLICES = {"explore": (date(2026, 9, 29), date(2026, 10, 3))}


@lru_cache(maxsize=None)
def fixture():
    frame = frame_from_data(data_for("EURUSD"), typical_spread=0.00008, stop_slippage=0.00002)
    features = market_features(frame, build_grid(frame, SLICES))
    return frame, features, forward_labels(frame, features)


def _perturbed(frame: InstrumentFrame, t: pd.Timestamp, seed: int) -> InstrumentFrame:
    """Every bar that closed by t gets new prices; times stay."""
    m1 = frame.m1.copy()
    past = (m1["time"] + pd.Timedelta(minutes=1) <= t).to_numpy()
    rng = np.random.default_rng(seed)
    shift = rng.normal(0, 0.001, past.sum())
    for name in ("open", "high", "low", "close"):
        m1.loc[past, name] = m1.loc[past, name].to_numpy() + shift
    m1.loc[past, "high"] += 0.0003
    return InstrumentFrame(frame.instrument, frame.typical_spread, frame.stop_slippage, m1, frame.bars)


@settings(max_examples=100, deadline=None)
@given(st.data())
def test_property_2_forward_labels_use_only_the_future(data):
    frame, features, labels = fixture()
    i = data.draw(st.integers(0, len(features) - 1))
    t = features["t"].iloc[i]
    again = forward_labels(_perturbed(frame, t, data.draw(st.integers(0, 2**31))), features)
    for name in FORWARD_LABELS:
        a, b = labels[name].iloc[i], again[name].iloc[i]
        assert (null(a) and null(b)) or a == b, (t, name, a, b)


def test_build_caches_labels_aligned_with_features(tmp_path):
    from agent.broker_profiles import load_profile
    from algo_research.dataset import build_dataset
    from algo_research.features.cache import ParquetCache
    from algo_research.snapshot import export_snapshot, load_snapshot
    from tests.test_research_snapshot import CREATED, MultiFixtureSource, spec

    export_snapshot(MultiFixtureSource(), spec(), tmp_path / "snap", git_commit="c" * 40, created_at=CREATED)
    snapshot = load_snapshot(tmp_path / "snap" / "fixture-week")
    from algo_research.config import ResearchConfig
    cfg = ResearchConfig(profile="exness-standard", study="golden", instruments=("EURUSD", "XAUUSD"),
                         start=date(2026, 9, 29), snapshot="fixture-week",
                         slices={"explore": (date(2026, 9, 29), date(2026, 10, 1)),
                                 "confirm": (date(2026, 10, 1), date(2026, 10, 2))},
                         holdout_start=date(2026, 10, 2))
    specs = load_profile("exness-standard").specs()
    data = build_dataset(snapshot, cfg, specs, snapshot.strategy, ParquetCache(tmp_path / "cache"), workers=1)
    assert len(data.labels) == len(data.features) and list(data.labels.columns) == list(LABEL_COLUMNS)
    assert (data.labels.index == data.features.index).all()
    again = build_dataset(snapshot, cfg, specs, snapshot.strategy, ParquetCache(tmp_path / "cache"), workers=1)
    assert "labels:EURUSD" in again.summary["cache_hits"]
    pd.testing.assert_frame_equal(again.labels, data.labels)
    pd.testing.assert_frame_equal(again.features, data.features)
