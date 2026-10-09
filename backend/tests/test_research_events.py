"""
Tests for algo_research/events.py — named conditions that select decision times.

Task 251 (.kiro/specs/algo-research/tasks.md). Hand-made M1 paths through the
real feature code, hand-made feature rows, and the backtester's fixture week
for Property 1 (extended to events).
Validates: Requirements 9.1-9.4 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algo_research.events import EVENTS, EventError, run_event
from algo_research.features.market import market_features
from algo_research.frame import InstrumentFrame, build_grid, frame_from_data
from tests.research_fixtures import Path, crt_path, grid_for, ny
from tests.test_backtest_signals import data_for


def features(path: Path, first=date(2026, 1, 5), end=date(2026, 1, 6)) -> pd.DataFrame:
    frame = path.frame()
    return market_features(frame, grid_for(frame, first, end))


def times(result) -> list:
    return [t.to_pydatetime() for t in result.rows["t"]]


def raid_path() -> Path:
    """Monday 2026-01-05: Asian range 1.0950-1.1060 (Sunday 20:00-23:00 New York)."""
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17))
    path.bar(ny(2026, 1, 4, 21, 30), h=1.1060).bar(ny(2026, 1, 4, 22, 10), lo=1.0950)
    return path


# ── anchor ──────────────────────────────────────────────────────────────────

def hand_rows(**columns) -> pd.DataFrame:
    n = len(next(iter(columns.values())))
    base = {"t": pd.date_range("2026-01-05 14:00", periods=n, freq="1D", tz="UTC"), "instrument": ["EURUSD"] * n,
            "trading_date": pd.date_range("2026-01-05", periods=n, freq="1D"), "ny_minute": [540] * n}
    return pd.DataFrame({**base, **columns})


def test_anchor_fires_at_the_time_and_skips_rows_without_direction():
    rows = hand_rows(side_midnight_open=[1.0, -1.0, 0.0, np.nan], ant_direction=["BULLISH", "BEARISH", "NEUTRAL", None])
    rows = pd.concat([rows, rows.assign(ny_minute=555)], ignore_index=True)       # 09:15: not the anchor
    plain = run_event(rows, "anchor", {"at": "09:00"})
    assert len(plain.rows) == 4 and plain.rows["direction"].isna().all()
    directed = run_event(rows, "anchor", {"at": "09:00", "direction_from": "side_midnight_open"})
    assert list(directed.rows["direction"]) == ["LONG", "SHORT"]
    assert directed.skipped == {"no_direction": 2}
    engine = run_event(rows, "anchor", {"at": "09:00", "direction_from": "ant_direction"})
    assert list(engine.rows["direction"]) == ["LONG", "SHORT"] and engine.skipped == {"no_direction": 2}
    assert list(engine.rows["row"]) == [0, 1]                                    # the feature rows they came from


def test_anchor_parameters_validated():
    rows = hand_rows(side_midnight_open=[1.0])
    with pytest.raises(EventError, match="at"):
        run_event(rows, "anchor", {"at": "09:07"})                                # not an M15 close
    with pytest.raises(EventError, match="direction_from"):
        run_event(rows, "anchor", {"at": "09:00", "direction_from": "nope"})
    with pytest.raises(EventError, match="unknown event"):
        run_event(rows, "anchors", {})


# ── asia_raid_reclaim ───────────────────────────────────────────────────────

def test_raid_and_reclaim_fires_toward_the_other_side():
    path = raid_path().bar(ny(2026, 1, 5, 2, 7), h=1.1070).bar(ny(2026, 1, 5, 2, 30), h=1.1080)
    result = run_event(features(path), "asia_raid_reclaim", {})
    [row] = result.rows.itertuples()
    assert row.t.to_pydatetime() == ny(2026, 1, 5, 2, 15)                        # the first close back inside
    assert row.direction == "SHORT"
    assert (row.raid_extreme, row.asia_opposite) == (1.1070, 1.0950)              # the furthest price so far


def test_no_event_once_the_other_side_is_taken():
    path = raid_path().bar(ny(2026, 1, 5, 2, 7), h=1.1070)                        # the high first...
    path.bar(ny(2026, 1, 5, 3, 20), lo=1.0940)                                    # ...then the low
    result = run_event(features(path), "asia_raid_reclaim", {})
    assert [r for r in result.rows["direction"]] == ["SHORT"]                     # no LONG: the high was taken


def test_both_sides_at_most_once_per_day():
    path = raid_path().bar(ny(2026, 1, 5, 2, 7), lo=1.0940)
    path.bar(ny(2026, 1, 5, 4, 7), lo=1.0930)                                     # a second low raid: same event
    result = run_event(features(path), "asia_raid_reclaim", {})
    assert list(result.rows["direction"]) == ["LONG"]
    assert result.rows["raid_extreme"].iloc[0] == 1.0940


@pytest.mark.parametrize("raid_at, fires", [((0, 30), False), ((1, 0), True), ((8, 59), True), ((9, 0), False)])
def test_window_edges(raid_at, fires):
    path = raid_path().bar(ny(2026, 1, 5, *raid_at), lo=1.0940)
    result = run_event(features(path), "asia_raid_reclaim", {"window": ["01:00", "09:00"]})
    assert (len(result.rows) == 1) == fires


@pytest.mark.parametrize("bars_below, within, fires", [(3, 4, True), (4, 4, False), (4, 5, True)])
def test_reclaim_within(bars_below, within, fires):
    path = raid_path()
    start = ny(2026, 1, 5, 3, 0)
    path.level(start, start + timedelta(minutes=15 * bars_below), 1.0945)        # closes below the Asian low
    result = run_event(features(path), "asia_raid_reclaim", {"reclaim_within": within})
    assert (len(result.rows) == 1) == fires
    if fires:
        assert result.rows["t"].iloc[0] == pd.Timestamp(start + timedelta(minutes=15 * (bars_below + 1)))


def test_no_asia_range_no_event():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17)).drop(ny(2026, 1, 4, 20), ny(2026, 1, 5, 0))
    path.bar(ny(2026, 1, 5, 3, 0), lo=1.0)
    assert run_event(features(path), "asia_raid_reclaim", {}).rows.empty


# ── level_open and daily ────────────────────────────────────────────────────

def test_level_open_maps_the_trend_and_needs_the_level_untaken():
    rows = hand_rows(w1_trend=["UP", "DOWN", "NEUTRAL", "UP"], pdh=[1.2, 1.2, 1.2, 1.2], pdl=[1.0, 1.0, 1.0, 1.0],
                     pdh_taken_at=[pd.NaT, pd.NaT, pd.NaT, pd.Timestamp("2026-01-08 10:00", tz="UTC")],
                     pdl_taken_at=[pd.NaT] * 4, close=[1.1] * 4)
    result = run_event(rows, "level_open", {"level": "trend", "at": "09:00"})
    assert list(result.rows["level_name"]) == ["pdh", "pdl"]
    assert list(result.rows["level"]) == [1.2, 1.0]
    assert list(result.rows["direction"]) == ["LONG", "SHORT"]
    assert result.skipped == {"no_trend": 1, "taken": 1}
    fixed = run_event(rows, "level_open", {"level": "pdl", "at": "09:00"})
    assert list(fixed.rows["direction"]) == ["SHORT"] * 4


def test_daily_fires_once_per_date_at_the_last_close():
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 7, 17))
    rows = features(path, date(2026, 1, 5), date(2026, 1, 8))
    result = run_event(rows, "daily", {})
    assert times(result) == [ny(2026, 1, 5, 16, 45), ny(2026, 1, 6, 16, 45), ny(2026, 1, 7, 16, 45)]
    assert result.rows["direction"].isna().all()


# ── crt (Requirement 15, update 2026-10c) ────────────────────────────────────

def test_crt_fires_at_c2s_close_with_its_levels_and_limit():
    rows = features(crt_path())
    h4 = run_event(rows, "crt", {"tf": "H4"}).rows
    assert times(run_event(rows, "crt", {"tf": "H4"})) == [ny(2026, 1, 5, 9, 0)]
    event = h4.iloc[0]
    assert event["direction"] == "LONG"
    assert (event["c2_extreme"], event["c1_opposite"]) == (1.0940, 1.1050)    # stop and target (AR-D13)
    assert event["limit"] == pd.Timestamp(ny(2026, 1, 5, 13, 0))              # C3's close

    h1 = run_event(rows, "crt", {"tf": "H1"}).rows
    assert list(zip([t.to_pydatetime() for t in h1["t"]], h1["direction"])) == [
        (ny(2026, 1, 5, 3, 0), "SHORT"), (ny(2026, 1, 5, 4, 0), "LONG"),
        (ny(2026, 1, 5, 6, 0), "SHORT"), (ny(2026, 1, 5, 7, 0), "LONG")]
    short = h1.iloc[2]
    assert short["c2_extreme"] == 1.1020 and short["c1_opposite"] == pytest.approx(1.0999)
    assert list(h1["limit"]) == [pd.Timestamp(ny(2026, 1, 5, h, 0)) for h in (4, 5, 7, 8)]


@pytest.mark.parametrize("sweep_at, fires_at", [(10, ny(2026, 1, 9, 13, 0)), (14, None)])
def test_crt_no_event_for_a_c2_closing_friday_at_17(sweep_at, fires_at):
    # Friday's 13:00 H4 closes at 17:00, which opens Saturday's candle: no row, no C3 before the weekend.
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 9, 17), base=1.1000)
    path.bar(ny(2026, 1, 9, sweep_at, 0), lo=1.0990)                  # C2 sweeps the candle before and closes back
    rows = features(path, date(2026, 1, 5), date(2026, 1, 10))
    assert times(run_event(rows, "crt", {"tf": "H4"})) == ([fires_at] if fires_at else [])


def test_crt_parameters_validated():
    with pytest.raises(EventError, match="tf"):
        run_event(features(crt_path()), "crt", {"tf": "M15"})


def test_registry_lists_levels_and_direction():
    assert EVENTS["crt"].levels == ("c2_extreme", "c1_opposite")
    assert EVENTS["crt"].limit and not EVENTS["asia_raid_reclaim"].limit
    assert EVENTS["asia_raid_reclaim"].levels == ("raid_extreme", "asia_opposite")
    assert EVENTS["level_open"].levels == ("level",)
    assert EVENTS["daily"].directional({}) is False
    assert EVENTS["anchor"].directional({"at": "09:00"}) is False
    assert EVENTS["anchor"].directional({"at": "09:00", "direction_from": "w1_trend"}) is True


# ── Property 1, extended: an event at t uses nothing after t ────────────────

SLICES = {"explore": (date(2026, 9, 29), date(2026, 10, 3))}


@lru_cache(maxsize=None)
def fixture():
    frame = frame_from_data(data_for("EURUSD"), typical_spread=0.00008, stop_slippage=0.00002)
    return frame, market_features(frame, build_grid(frame, SLICES))


def _truncated(frame: InstrumentFrame, t: pd.Timestamp) -> InstrumentFrame:
    m1 = frame.m1[frame.m1["time"] + pd.Timedelta(minutes=1) <= t].reset_index(drop=True)
    bars = {tf: b[b["close_time"] <= t].reset_index(drop=True) for tf, b in frame.bars.items()}
    return InstrumentFrame(frame.instrument, frame.typical_spread, frame.stop_slippage, m1, bars)


CASES = [("anchor", {"at": "09:00", "direction_from": "side_midnight_open"}),
         ("asia_raid_reclaim", {"window": ["00:00", "16:00"], "reclaim_within": 8}),
         ("level_open", {"level": "pdl", "at": "05:00"}),
         ("crt", {"tf": "H1"}), ("crt", {"tf": "H4"})]


def test_fixture_events_exist():
    _, rows = fixture()
    for name, params in CASES:
        assert len(run_event(rows, name, params).rows) > 0, name


@settings(max_examples=25, deadline=None)
@given(st.sampled_from(CASES), st.data())
def test_property_1_events_use_only_the_past(case, data):
    name, params = case
    frame, rows = fixture()
    full = run_event(rows, name, params).rows
    t = data.draw(st.sampled_from(list(full["t"])))
    short = _truncated(frame, t)
    again = run_event(market_features(short, build_grid(short, SLICES)), name, params).rows
    a = full[full["t"] == t].drop(columns="row").reset_index(drop=True)
    b = again[again["t"] == t].drop(columns="row").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)
