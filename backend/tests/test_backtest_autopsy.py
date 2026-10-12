"""
Tests for algo_backtester/autopsy.py — the trade autopsy.

Tasks 291-292 (.kiro/specs/market-narrative/tasks.md). Every filled trade of a
run is labelled against the narratives of its candles, and the run's net R is
split by failure mode, so a backtest says which part of the engine loses.
The run directory is the only input. The labels are hindsight: they diagnose,
never decide.

The synthetic run is one EURUSD week on a 24/7 calendar (so its W1 candle is
complete), with one trade per failure mode on hand-built days:

    Mon  UP     low at bar 30, high at bar 70       T1 with/on time, T2 against/expansion,
                                                    T3 with/early, T4 with/late
    Tue  DOWN   inverted: low at 20, then high 60   T5 with/inverted, T6 against
    Wed  FLAT                                       T7 unknown
    Thu  DOWN   high at 20, low at 60               T8 against/early, T9 with/on time
                                                    T10 open at the end (left out)

Validates: Requirements 3.1-3.6, 4.1-4.5, 5.2 (.kiro/specs/market-narrative/requirements.md)
"""
from __future__ import annotations

import csv
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algo_backtester.autopsy import (
    AUTOPSY_COLUMNS,
    FAILURE_MODES,
    AutopsyError,
    autopsy_table,
    load_run,
    split,
)
from algo_research.narrative import NarrativeConfig, PriceBasis
from liquidity_engine.models import Timeframe

M15 = timedelta(minutes=15)
WEEK = pd.Timestamp("2026-01-10 22:00", tz="UTC")     # Saturday 17:00 New York: the W1 candle's start
NONE = NarrativeConfig(price_basis=PriceBasis(rule="NONE"))


def day_bars(start: pd.Timestamp, steps, wicks=(), n: int = 96) -> list[list]:
    """M15 bars whose closes follow ``steps`` [(from_bar, level)]; each bar opens at the
    previous close. ``wicks`` = (bar, high, low)."""
    def level(i):
        return [lv for k, lv in steps if k <= i][-1]
    rows = []
    for i in range(n):
        o, c = level(max(i - 1, 0)), level(i)
        rows.append([start + i * M15, o, max(o, c), min(o, c), c])
    for i, high, low in wicks:
        rows[i][2], rows[i][3] = max(rows[i][2], high), min(rows[i][3], low)
    return rows


def day(k: int) -> pd.Timestamp:
    return WEEK + timedelta(days=k)


def bar(k: int, i: int) -> pd.Timestamp:
    return day(k) + i * M15


def week_bars() -> list[list]:
    return (day_bars(day(0), [(0, 1.1000)])
            + day_bars(day(1), [(0, 1.1000), (35, 1.1020), (75, 1.1060)], wicks=((30, 1.1000, 1.0950), (70, 1.1080, 1.1060)))
            + day_bars(day(2), [(0, 1.1000), (25, 1.0980)], wicks=((20, 1.1000, 1.0950), (60, 1.1030, 1.0980)))
            + day_bars(day(3), [(0, 1.1000)], wicks=((40, 1.1020, 1.0990),))
            + day_bars(day(4), [(0, 1.1000), (25, 1.0990), (65, 1.0960)], wicks=((20, 1.1040, 1.1000), (60, 1.0990, 1.0940)))
            + day_bars(day(5), [(0, 1.0960)])
            + day_bars(day(6), [(0, 1.0960)]))


# (name, direction, day, bar, entry, stop, target, fill, exit, net_r, mfe_r, swept level or None)
TRADES = [
    ("T1", "LONG", 1, 50, 1.0990, 1.0970, 1.1050, 1.0990, "TP", 1.6, 1.6,
     {"side": "SSL", "source": "SWING_LOW", "timeframe": "M15", "price": 1.0960, "raided_at": bar(1, 30)}),
    ("T2", "SHORT", 1, 55, 1.1020, 1.1040, 1.0900, 1.1020, "SL", -1.0, 0.2,
     {"side": "BSL", "source": "PDH", "timeframe": "D1", "price": 1.1070, "raided_at": bar(0, 50)}),
    ("T3", "LONG", 1, 10, 1.1000, 1.0980, 1.1060, 1.1000, "SL", -1.0, 0.1, None),
    ("T4", "LONG", 1, 80, 1.1070, 1.1050, 1.1100, 1.1070, "SL", -1.0, 0.3,
     {"side": "SSL", "source": "SWING_LOW", "timeframe": "M15", "price": 1.1055, "raided_at": bar(1, 78)}),
    ("T5", "SHORT", 2, 70, 1.0990, 1.1040, 1.0900, 1.0990, "TP", 2.0, 2.0,
     {"side": "BSL", "source": "SWING_HIGH", "timeframe": "M15", "price": 1.1030, "raided_at": bar(2, 60)}),
    ("T6", "LONG", 2, 70, 1.0990, 1.0940, 1.1100, 1.0990, "SL", -1.0, 0.4,
     {"side": "SSL", "source": "SWING_LOW", "timeframe": "M15", "price": 1.0950, "raided_at": bar(2, 20)}),
    ("T7", "LONG", 3, 40, 1.1000, 1.0980, 1.1040, 1.1000, "SL", -1.0, 0.5,
     {"side": "SSL", "source": "SWING_LOW", "timeframe": "M15", "price": 1.0990, "raided_at": bar(3, 40)}),
    ("T8", "LONG", 4, 10, 1.1000, 1.0980, 1.1050, 1.1000, "SL", -1.0, 0.2,
     {"side": "SSL", "source": "SWING_LOW", "timeframe": "M15", "price": 1.0995, "raided_at": bar(4, 8)}),
    ("T9", "SHORT", 4, 30, 1.0995, 1.1045, 1.0945, 1.0995, "TP", 3.0, 3.0,
     {"side": "SSL", "source": "SWING_LOW", "timeframe": "M15", "price": 1.0990, "raided_at": bar(4, 22)}),
    ("T10", "SHORT", 4, 70, 1.0960, 1.0990, 1.0900, 1.0960, "OPEN_AT_END", 0.0, 0.0, None),
]


def iso(t: pd.Timestamp) -> str:
    return t.isoformat()


def write_run(root: Path, trades=TRADES, bars=None, timeframe: str = "M15", name: str = "a1b2c3") -> Path:
    run = root / name
    run.mkdir(parents=True)
    bars = week_bars() if bars is None else bars
    (run / "candles.json").write_text(json.dumps({
        "timeframe": timeframe, "bars_before": 60, "bars_after": 20,
        "instruments": {"EURUSD": [[iso(t), o, h, lo, c] for t, o, h, lo, c in bars]}}), encoding="utf-8")
    contexts, rows = [], []
    for name_, direction, k, i, entry, stop, target, fill, exit_reason, net_r, mfe_r, swept in TRADES if trades is TRADES else trades:
        filled = bar(k, i) + timedelta(minutes=5)
        rows.append({"t": iso(bar(k, i) - M15), "instrument": "EURUSD", "setup_id": name_, "grade": "A",
                     "decision": "EXECUTE", "reason": "", "direction": direction, "entry": entry, "stop": stop,
                     "target": target, "r_ratio": 3.0, "filled_at": iso(filled), "fill": fill, "ideal_fill": fill,
                     "closed_at": "" if exit_reason == "OPEN_AT_END" else iso(filled + timedelta(hours=1)),
                     "exit_reason": exit_reason, "gross_r": net_r, "net_r": net_r, "mae_r": -0.5, "mfe_r": mfe_r})
        if swept is not None:
            contexts.append({"t": iso(bar(k, i) - M15), "instrument": "EURUSD", "setup_id": name_,
                             "context": {"swept_level": {**swept, "raided_at": iso(swept["raided_at"]),
                                                         "formed_at": iso(swept["raided_at"] - timedelta(hours=2))},
                                         "killzone": "LONDON"}})
    rows.append({"t": iso(bar(2, 5)), "instrument": "EURUSD", "setup_id": "", "decision": "NO_TRADE",
                 "reason": "NO_SETUP"})
    columns = list(dict.fromkeys(k for r in rows for k in r))
    with (run / "journal.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    (run / "context.json").write_text(json.dumps(contexts), encoding="utf-8")
    return run


@pytest.fixture
def table(tmp_path) -> pd.DataFrame:
    return autopsy_table(load_run(write_run(tmp_path)), NONE).set_index("setup_id")


# ── Requirement 3.1: what each trade carries ───────────────────────────────

def test_load_run_keeps_closed_fills_and_counts_open_at_end(tmp_path):
    inputs = load_run(write_run(tmp_path))
    assert inputs.run_id == "a1b2c3" and inputs.bar_tf == Timeframe.M15 and inputs.open_at_end == 1
    assert sorted(inputs.journal.setup_id) == [f"T{i}" for i in range(1, 10)]
    assert set(inputs.contexts) == {"T1", "T2", "T4", "T5", "T6", "T7", "T8", "T9"}
    assert list(inputs.bars) == ["EURUSD"] and len(inputs.bars["EURUSD"]) == 7 * 96


def test_load_run_refuses_a_directory_without_run_files(tmp_path):
    run = write_run(tmp_path)
    (run / "context.json").unlink()
    with pytest.raises(AutopsyError, match="context.json"):
        load_run(run)


def test_columns_and_journal_fields(tmp_path, table):
    assert tuple(autopsy_table(load_run(write_run(tmp_path / "again")), NONE).columns) == AUTOPSY_COLUMNS
    t1 = table.loc["T1"]
    assert (t1.direction, t1.entry, t1.stop, t1.target, t1.exit_reason, t1.net_r) == ("LONG", 1.0990, 1.0970, 1.1050, "TP", 1.6)
    assert t1.trading_date == "2026-01-12" and t1.ny_hour == 5           # bar 50 of Monday: 05:30 New York
    assert t1.bias_start == day(1).isoformat()


def test_frame_directions_and_with(table):
    assert table.W1_dir.unique().tolist() == ["DOWN"]                     # the week closed below its open
    assert table.loc["T1", "W1_with"] is False and table.loc["T2", "W1_with"] is True
    assert table.loc[["T1", "T2", "T3", "T4"], "D1_dir"].tolist() == ["UP"] * 4
    assert table.loc["T1", "D1_with"] is True and table.loc["T2", "D1_with"] is False
    assert table.loc["T7", "D1_dir"] == "FLAT" and pd.isna(table.loc["T7", "D1_with"])
    assert table.loc["T9", "H4_dir"] == "DOWN" and table.loc["T9", "H4_with"] is True   # Thursday's 21:00 H4


# ── Requirements 3.2 and 3.4: phases and failure modes ─────────────────────

def test_failure_modes(table):
    assert table["phase"].to_dict() == {
        "T1": "IN_EXPANSION", "T2": "IN_EXPANSION", "T3": "BEFORE_FALSE_EXTREME", "T4": "AFTER_EXPANSION",
        "T5": "INVERTED", "T6": "INVERTED", "T7": "UNKNOWN", "T8": "BEFORE_FALSE_EXTREME", "T9": "IN_EXPANSION"}
    assert table["mode"].to_dict() == {
        "T1": "WITH_ON_TIME", "T2": "AGAINST_EXPANSION", "T3": "WITH_EARLY", "T4": "WITH_LATE",
        "T5": "WITH_INVERTED", "T6": "AGAINST_OTHER", "T7": "UNKNOWN", "T8": "AGAINST_OTHER", "T9": "WITH_ON_TIME"}
    assert set(table["mode"]) <= set(FAILURE_MODES)


# ── Requirement 3.3: the bias candle's columns ─────────────────────────────

def test_stopped_by_false_move_and_target_beyond_expansion(table):
    assert table.loc["T3", "stopped_by_false_move"] is True              # stop 1.0980 above the 1.0950 low
    assert table.loc["T4", "target_beyond_expansion"] is True            # 1.1100 beyond the 1.1080 high
    assert table.loc["T1", "target_beyond_expansion"] is False
    assert pd.isna(table.loc["T1", "stopped_by_false_move"])             # not an early fill
    assert pd.isna(table.loc["T2", "stopped_by_false_move"]) and pd.isna(table.loc["T2", "target_beyond_expansion"])


def test_raid_side_and_raid_in_candle(table):
    assert table.loc["T1", "raid_beyond_open"] is True and table.loc["T1", "raid_in_candle"] is True
    assert table.loc["T2", "raid_beyond_open"] is True and table.loc["T2", "raid_in_candle"] is False
    assert table.loc["T9", "raid_beyond_open"] is False and table.loc["T9", "raid_in_candle"] is True
    assert (table.loc["T2", "raid_tf"], table.loc["T2", "raid_source"]) == ("D1", "PDH")


def test_missing_raid_leaves_columns_empty(table):
    for column in ("raid_beyond_open", "raid_in_candle", "raid_tf", "raid_source"):
        assert pd.isna(table.loc["T3", column])


def test_fill_side(table):
    assert table["fill_side"].to_dict() == {
        "T1": "FAVOURABLE", "T2": "FAVOURABLE", "T3": "UNFAVOURABLE", "T4": "UNFAVOURABLE",
        "T5": "UNFAVOURABLE", "T6": "FAVOURABLE", "T7": "UNFAVOURABLE", "T8": "UNFAVOURABLE", "T9": "UNFAVOURABLE"}


def test_asof_shape_cases(table):
    assert table.loc["T1", "asof_shape"] == "WITH_SHAPE"     # low first, back above the open, long
    assert table.loc["T2", "asof_shape"] == "FADES_SHAPE"    # the same shape, short
    assert table.loc["T3", "asof_shape"] == "UNFORMED"       # nothing has moved yet
    assert table.loc["T9", "asof_shape"] == "WITH_SHAPE"     # high first, back below the open, short


def test_unknown_when_candle_incomplete_or_missing(tmp_path):
    bars = week_bars()[96 + 20:]                              # starts inside Monday's candle
    trades = [t for t in TRADES if t[0] in ("T1", "T9")]
    late = ("T11", "LONG", 8, 10, 1.1, 1.09, 1.12, 1.1, "SL", -1.0, 0.0, None)   # after the data ends
    table = autopsy_table(load_run(write_run(tmp_path, trades + [late], bars)), NONE).set_index("setup_id")
    assert table.loc["T1", "D1_dir"] == "UNKNOWN" and table.loc["T1", "mode"] == "UNKNOWN"
    assert table.loc["T1", "W1_dir"] == "UNKNOWN"
    assert table.loc["T9", "mode"] == "WITH_ON_TIME"
    assert table.loc["T11", "D1_dir"] == "UNKNOWN" and table.loc["T11", "mode"] == "UNKNOWN"
    assert table.loc["T11", "asof_shape"] == "UNFORMED"


def test_price_basis_moves_a_rollover_low(tmp_path):
    """A blown-out bid in Monday's first bar (17:00 New York) is not the day's low."""
    bars = week_bars()
    bars[96][3] = 1.0900                                       # Monday bar 0: a rollover dip
    run = write_run(tmp_path, [t for t in TRADES if t[0] == "T3"], bars)
    raw = autopsy_table(load_run(run), NONE).set_index("setup_id").loc["T3"]
    priced = autopsy_table(load_run(run), NarrativeConfig()).set_index("setup_id").loc["T3"]
    assert raw.phase == "IN_EXPANSION" and priced.phase == "BEFORE_FALSE_EXTREME"


# ── Requirement 3.5: the split ─────────────────────────────────────────────

def test_split_counts_shares_and_intervals(table):
    out = split(table.reset_index(), "mode", seed=7, resamples=500)
    assert out["mode"].tolist() == [m for m in FAILURE_MODES if m in set(table["mode"])]
    row = out.set_index("mode").loc["WITH_ON_TIME"]
    assert row.n == 2 and row.share == pytest.approx(2 / 9) and row.tp_rate == 1.0
    assert row.mean_r == pytest.approx(2.3) and row.sum_r == pytest.approx(4.6)
    assert all(out.lo <= out.mean_r + 1e-12) and all(out.mean_r <= out.hi + 1e-12)
    again = split(table.reset_index(), "mode", seed=7, resamples=500)
    pd.testing.assert_frame_equal(out, again)


def test_refuses_candles_not_finer_than_a_frame(tmp_path):
    run = write_run(tmp_path, timeframe="H4")
    with pytest.raises(AutopsyError, match="H4"):
        autopsy_table(load_run(run), NONE)


# ── Properties ─────────────────────────────────────────────────────────────

@settings(max_examples=100, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(FAILURE_MODES), st.floats(-2, 10, allow_nan=False),
                          st.integers(0, 20), st.sampled_from(["EURUSD", "XAUUSD"])), min_size=1, max_size=60))
def test_property_3_the_split_adds_up(rows):
    table = pd.DataFrame({"mode": [r[0] for r in rows], "net_r": [r[1] for r in rows],
                          "trading_date": [f"2026-01-{1 + r[2]:02d}" for r in rows],
                          "instrument": [r[3] for r in rows], "exit_reason": ["SL"] * len(rows)})
    out = split(table, "mode", seed=1, resamples=50)
    assert out.n.sum() == len(table)
    assert out.sum_r.sum() == pytest.approx(table.net_r.sum(), abs=1e-9)
    assert out.share.sum() == pytest.approx(1.0)


_RUN_CACHE: dict = {}


@settings(max_examples=100, deadline=None)
@given(st.sampled_from([t[0] for t in TRADES[:9]]), st.integers(0, 2**31 - 1))
def test_property_4_asof_shape_ignores_later_bars(tmp_path_factory, name, seed):
    if "base" not in _RUN_CACHE:
        root = tmp_path_factory.mktemp("base")
        _RUN_CACHE["base"] = autopsy_table(load_run(write_run(root)), NONE).set_index("setup_id")
    trade = next(t for t in TRADES if t[0] == name)
    filled = bar(trade[2], trade[3]) + timedelta(minutes=5)
    rng = np.random.default_rng(seed)
    bars = []
    for t, o, h, lo, c in week_bars():
        if t + M15 > filled:                                    # closes after the fill
            o, c = o + rng.normal(0, 0.003), c + rng.normal(0, 0.003)
            h, lo = max(o, c) + abs(rng.normal(0, 0.002)), min(o, c) - abs(rng.normal(0, 0.002))
        bars.append([t, o, h, lo, c])
    root = tmp_path_factory.mktemp("moved")
    moved = autopsy_table(load_run(write_run(root, [trade], bars)), NONE).set_index("setup_id")
    assert moved.loc[name, "asof_shape"] == _RUN_CACHE["base"].loc[name, "asof_shape"]

