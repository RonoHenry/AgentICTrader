"""
Tests for algo_research/baselines.py — what a statistic would be without the
information under test.

Task 253 (.kiro/specs/algo-research/tasks.md).
Validates: Requirements 10.1-10.6, 13.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algo_research.baselines import (
    coin_flip,
    naive_direction,
    race_limits,
    random_time_draws,
    rescale_orders,
    shuffled_path,
    stratified,
)
from algo_research.filters import compile_filter
from algo_research.frame import frame_from_arrays
from algo_research.labels import CANDLE_LABELS, candle_labels
from tests.research_fixtures import Path, ny


def grid(n_dates=40, instruments=("EURUSD", "XAUUSD"), minutes=(540, 555)) -> pd.DataFrame:
    rows = []
    for instrument in instruments:
        for d in range(n_dates):
            day = date(2025, 7, 1) + timedelta(days=d)
            for minute in minutes:
                rows.append({"t": pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=minute + 240),
                             "instrument": instrument, "trading_date": pd.Timestamp(day), "ny_minute": minute,
                             "slice": "explore" if d < 10 else "confirm", "close": 1.0 + d / 100,
                             "atr_d1": 0.01 * (1 + d % 3)})
    return pd.DataFrame(rows)


def events_at(features: pd.DataFrame, rows: list[int], direction="LONG") -> pd.DataFrame:
    chosen = features.loc[rows]
    return pd.DataFrame({"row": rows, "t": chosen["t"].to_numpy(), "instrument": chosen["instrument"].to_numpy(),
                         "trading_date": chosen["trading_date"].to_numpy(), "direction": direction})


# ── coin flip ───────────────────────────────────────────────────────────────

def test_coin_flip_skips_rejected_races():
    races = pd.DataFrame({"outcome": ["TARGET", "REJECTED", "STOP"], "p_coin": [0.25, np.nan, 0.5]})
    sums, counts = coin_flip(races)
    assert list(sums) == [0.25, 0.0, 0.5] and list(counts) == [1, 0, 1]


# ── random time ─────────────────────────────────────────────────────────────

def test_random_time_draws_same_instrument_slot_and_slice_never_event_dates():
    features = grid()
    events = events_at(features, [features.index[(features["instrument"] == "EURUSD") & (features["ny_minute"] == 540)
                                                 & (features["trading_date"] == pd.Timestamp(2025, 7, 20))][0],
                                  features.index[(features["instrument"] == "EURUSD") & (features["ny_minute"] == 555)
                                                 & (features["trading_date"] == pd.Timestamp(2025, 7, 25))][0]])
    draws = random_time_draws(features, events, k=20, rng=np.random.default_rng(1))
    assert list(draws.available) == [20, 20]
    drawn = features.loc[draws.rows["row"]]
    for event, part in drawn.groupby(draws.rows["event"].to_numpy()):
        source = features.loc[events["row"].iloc[event]]
        assert (part["instrument"] == source["instrument"]).all()
        assert (part["ny_minute"] == source["ny_minute"]).all()
        assert (part["slice"] == "confirm").all()
        assert len(part) == 20 and part.index.is_unique
    # Never on a date with an event for that instrument.
    assert not set(drawn["trading_date"]) & {pd.Timestamp(2025, 7, 20), pd.Timestamp(2025, 7, 25)}


def test_random_time_reproducible_and_reports_short_pools():
    features = grid(n_dates=14)                                  # confirm has 4 dates per slot
    row = features.index[(features["instrument"] == "XAUUSD") & (features["ny_minute"] == 540)
                         & (features["trading_date"] == pd.Timestamp(2025, 7, 12))][0]
    events = events_at(features, [row], direction="SHORT")
    a = random_time_draws(features, events, k=20, rng=np.random.default_rng(5))
    b = random_time_draws(features, events, k=20, rng=np.random.default_rng(5))
    pd.testing.assert_frame_equal(a.rows, b.rows)
    assert list(a.available) == [3]                              # the other 3 confirm dates
    assert (a.rows["direction"] == "SHORT").all()                # draws keep the event's direction


def test_rescale_orders_keeps_the_atr_distances():
    features = grid()
    events = events_at(features, [0])
    features.loc[0, ["close", "atr_d1"]] = [1.0, 0.01]
    trades = pd.DataFrame({"stop": [0.995], "target": [1.02]}, index=events.index)   # -0.5 ATR, +2 ATR
    draws = pd.DataFrame({"event": [0, 0], "row": [5, 6], "direction": ["LONG", "LONG"]})
    features.loc[5, ["close", "atr_d1"]] = [2.0, 0.04]
    features.loc[6, ["close", "atr_d1"]] = [1.5, 0.02]
    orders = rescale_orders(features, events, trades, draws, time_limit="day_close")
    assert list(orders["stop"]) == pytest.approx([2.0 - 0.02, 1.5 - 0.01])
    assert list(orders["target"]) == pytest.approx([2.0 + 0.08, 1.5 + 0.04])
    assert list(orders["t"]) == list(features.loc[[5, 6], "t"])
    first = features.loc[5, "trading_date"]
    assert orders["limit"].iloc[0] == pd.Timestamp(first.date(), tz="America/New_York") + pd.Timedelta(hours=17)
    orders = rescale_orders(features, events, trades, draws, time_limit={"minutes": 90})
    assert list(orders["limit"]) == [t + pd.Timedelta(minutes=90) for t in features.loc[[5, 6], "t"]]


def test_rescale_orders_keeps_the_events_own_duration():
    # time_limit = "event" (update 2026-10c): each draw keeps its event's limit - t from its own t.
    features = grid()
    events = events_at(features, [0, 1])
    t0, t1 = features.loc[0, "t"], features.loc[1, "t"]
    trades = pd.DataFrame({"stop": [0.99, 0.99], "target": [1.02, 1.02],
                           "limit": [t0 + pd.Timedelta(minutes=60), t1 + pd.Timedelta(minutes=240)]},
                          index=events.index)
    draws = pd.DataFrame({"event": [0, 1, 1], "row": [5, 6, 7], "direction": ["LONG"] * 3})
    orders = rescale_orders(features, events, trades, draws, time_limit="event")
    drawn = features.loc[[5, 6, 7], "t"].tolist()
    assert list(orders["limit"]) == [drawn[0] + pd.Timedelta(minutes=60), drawn[1] + pd.Timedelta(minutes=240),
                                     drawn[2] + pd.Timedelta(minutes=240)]
    with pytest.raises(ValueError, match="event"):
        race_limits(features.loc[[0]], "event")                       # the event's rows carry it, not the calendar


# ── naive rules ─────────────────────────────────────────────────────────────

def test_naive_rules_on_hand_made_rows():
    rows = pd.DataFrame({"prev_day_dir": [1.0, -1.0, 0.0], "w1_trend": ["UP", "NEUTRAL", "DOWN"],
                         "side_d1_open": [-1.0, 1.0, np.nan], "side_midnight_open": [0.0, -1.0, 1.0]})
    assert list(naive_direction(rows, "always_long")) == ["LONG"] * 3
    assert list(naive_direction(rows, "prev_day_dir")) == ["LONG", "SHORT", None]
    assert list(naive_direction(rows, "w1_trend")) == ["LONG", None, "SHORT"]
    assert list(naive_direction(rows, "side_d1_open")) == ["SHORT", "LONG", None]
    assert list(naive_direction(rows, "side_midnight_open")) == [None, "SHORT", "LONG"]
    with pytest.raises(ValueError, match="sometimes"):
        naive_direction(rows, "sometimes")


# ── stratified ──────────────────────────────────────────────────────────────

def test_stratified_buckets_by_distance_decile_and_hour():
    rng = np.random.default_rng(3)
    n = 4000
    distance = rng.uniform(0, 2, n)                               # in ATR
    hour = rng.choice([9, 10], n)
    features = pd.DataFrame({"close": 1.0, "atr_d1": 0.01, "pdh": 1.0 + distance * 0.01, "pdl": 0.5,
                             "pdh_taken_at": pd.NaT, "pdl_taken_at": pd.NaT, "ny_minute": hour * 60,
                             "w1_trend": "UP"})
    # Near levels trade far more often, and more so at 09:00.
    hit = rng.random(n) < np.where(hour == 9, 0.9, 0.6) * np.exp(-distance)
    labels = pd.DataFrame({"pdh_hit_after": pd.array(hit, dtype="boolean"),
                           "pdl_hit_after": pd.array(np.zeros(n, dtype=bool), dtype="boolean")})
    events = pd.DataFrame({"row": [10, 11], "level_name": ["pdh", "pdh"], "level": features.loc[[10, 11], "pdh"]})
    sums, counts = stratified(features, labels, events, candidates=("pdh",))
    for i, row in enumerate((10, 11)):
        same_hour = hour == hour[row]
        edges = np.quantile(distance, np.linspace(0, 1, 11))
        decile = np.clip(np.searchsorted(edges, distance, "right") - 1, 0, 9)
        cell = same_hour & (decile == decile[row])
        assert counts[i] == 1 and sums[i] == pytest.approx(hit[cell].mean())


def test_stratified_pool_excludes_taken_and_unknown_levels():
    features = pd.DataFrame({"close": [1.0] * 4, "atr_d1": [0.01, 0.01, np.nan, 0.01], "pdh": [1.01] * 4,
                             "pdh_taken_at": [pd.NaT, pd.Timestamp("2025-07-01", tz="UTC"), pd.NaT, pd.NaT],
                             "ny_minute": [540] * 4})
    labels = pd.DataFrame({"pdh_hit_after": pd.array([True, True, True, False], dtype="boolean")})
    events = pd.DataFrame({"row": [0], "level_name": ["pdh"], "level": [1.01]})
    sums, counts = stratified(features, labels, events, candidates=("pdh",))
    assert counts[0] == 1 and sums[0] == pytest.approx(0.5)      # rows 0 and 3 only


# ── shuffled path ───────────────────────────────────────────────────────────

def walk_frame(days: int = 120, seed: int = 4):
    path = Path(ny(2025, 9, 7, 17), ny(2025, 9, 7, 17) + timedelta(days=days * 7 // 5 + 2))
    rng = np.random.default_rng(seed)
    closes = 1.1 + np.cumsum(rng.normal(0, 0.0002, len(path.times)))
    opens = np.concatenate([[1.1], closes[:-1]])
    return frame_from_arrays("EURUSD", pd.DatetimeIndex(path.times), opens, np.maximum(opens, closes) + 0.00005,
                             np.minimum(opens, closes) - 0.00005, closes, spread=np.full(len(path.times), 0.0001),
                             typical_spread=0.0001, stop_slippage=0.0)


def test_shuffled_path_keeps_each_dates_open_and_close():
    frame = walk_frame(days=10)
    days = candle_labels(frame)
    events = pd.DataFrame({"instrument": "EURUSD", "trading_date": days["trading_date"]})
    given = compile_filter("day_dir == 1", CANDLE_LABELS)
    always = compile_filter("day_dir == day_dir", CANDLE_LABELS)
    sums, counts = shuffled_path({"EURUSD": frame}, events, of=always, given=given, shuffles=50,
                                 rng=np.random.default_rng(1))
    up = (days["day_dir"] == 1).to_numpy()
    assert list(counts) == pytest.approx(up.astype(float))          # the day's direction never changes
    assert list(sums) == pytest.approx(up.astype(float))


def test_unshuffled_path_gives_back_the_candle_labels():
    # Identity order: the path rebuilt from its M15 moves is the real day (update 2026-10c: quarters too).
    from algo_research.baselines import _m15_days, _path_labels

    frame = walk_frame(days=20)
    days = candle_labels(frame).set_index("trading_date")
    for day, bars in _m15_days(frame).items():
        if day not in days.index or day.weekday() >= 5:
            continue
        got = _path_labels(bars, np.arange(len(bars))[None, :]).iloc[0]
        want = days.loc[day]
        for name in ("day_dir", "day_high_h4", "day_low_h4", "day_high_q", "day_low_q"):
            assert got[name] == want[name], (day, name)
        assert got["day_high_final"] == pytest.approx(want["day_high_final"])
        assert got["day_low_final"] == pytest.approx(want["day_low_final"])


@pytest.mark.parametrize("of", ["day_low_h4 in [2, 3, 4]", "day_low_q == 1"])
def test_shuffled_path_matches_the_real_statistic_on_a_random_walk(of):
    frame = walk_frame(days=300)
    days = candle_labels(frame)
    days = days[days["trading_date"].dt.weekday < 5].iloc[1:-1]   # whole weekdays only
    events = pd.DataFrame({"instrument": "EURUSD", "trading_date": days["trading_date"].to_numpy()})
    of = compile_filter(of, CANDLE_LABELS)
    given = compile_filter("day_dir == 1", CANDLE_LABELS)
    sums, counts = shuffled_path({"EURUSD": frame}, events, of=of, given=given, shuffles=100,
                                 rng=np.random.default_rng(2))
    mask, _ = given.evaluate(days)
    hits, _ = of.evaluate(days)
    real = (hits & mask).sum() / mask.sum()
    shuffled = sums.sum() / counts.sum()
    se = np.sqrt(real * (1 - real) / mask.sum())
    assert abs(real - shuffled) < 3 * se, (real, shuffled, se)
