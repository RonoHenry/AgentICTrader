"""
Tests for algo_research/search_chain.py — ICT's chain calling the next D1 candle, H-K (context-engine Requirement 28;
docs/research/SEARCH_2018_2024.md).

Task 366 (.kiro/specs/context-engine/tasks.md). Synthetic bars only: nothing here reads the snapshot. A calendar
around Easter 2020 checks how weeks and months close (CE-D18); a slow wave with noise gives the monthly frame its
swings, so the chain calls, and cutting the bars after any day leaves every earlier call unchanged (Property 2).
Validates: Requirements 28.1-28.2 (.kiro/specs/context-engine/requirements.md); Property 2
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algo_research.search_calls import daily_signals
from algo_research.search_chain import ARMS, Ladder, chain_rows, draw_race, judge_race, month_interval, periods


def bars_on(days, seed=0, wave=True):
    days = pd.DatetimeIndex(days)
    rng = np.random.default_rng(seed)
    i = np.arange(len(days))
    c = 100 + (8 * np.sin(2 * np.pi * i / 110) if wave else 0) + np.cumsum(rng.normal(0, 0.6, len(days)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"time": days, "open": o, "high": np.maximum(o, c) + rng.random(len(days)) * 0.5,
                         "low": np.minimum(o, c) - rng.random(len(days)) * 0.5, "close": c})


EASTER = pd.bdate_range("2020-03-25", "2020-04-14", tz="UTC").drop(pd.Timestamp("2020-04-10", tz="UTC"))


def at(times, day):
    return int(np.flatnonzero(pd.DatetimeIndex(times) == pd.Timestamp(day, tz="UTC"))[0])


def test_weeks_and_months_close_on_the_calendar():
    p = periods(pd.Series(EASTER))
    closes = {d.strftime("%m-%d") for d, w in zip(EASTER, p["week_closes"]) if w}
    assert closes == {"03-27", "04-03"}                              # Fridays; Good Friday is missing
    assert {d.strftime("%m-%d") for d, m in zip(EASTER, p["month_closes"]) if m} == {"03-31"}

    ladder = Ladder(bars_on(EASTER))
    thursday = ladder.at(at(EASTER, "2020-04-09"))
    monday = ladder.at(at(EASTER, "2020-04-13"))
    assert len(monday[1]) == len(thursday[1]) + 1                    # the short week closes when the next opens
    week = bars_on(EASTER).iloc[at(EASTER, "2020-04-06"):at(EASTER, "2020-04-09") + 1]
    assert (monday[1].h[-1], monday[1].l[-1]) == (week["high"].max(), week["low"].min())


def test_forming_week_and_month_stretch_their_ranges():
    b = bars_on(EASTER)
    ladder = Ladder(b)
    days, weeks, months, w_forming, m_forming = ladder.at(at(EASTER, "2020-04-01"))   # a Wednesday, a new month
    so_far = b.iloc[at(EASTER, "2020-03-30"):at(EASTER, "2020-04-01") + 1]
    assert w_forming == (so_far["high"].max(), so_far["low"].min())
    month = b.iloc[at(EASTER, "2020-04-01"):at(EASTER, "2020-04-01") + 1]
    assert m_forming == (month["high"].max(), month["low"].min())
    assert len(days) == at(EASTER, "2020-04-01") + 1 and weeks.end[-1] <= days.t[-1]
    friday = ladder.at(at(EASTER, "2020-04-03"))
    assert friday[3] is None and len(friday[1]) == len(weeks) + 1   # Friday closes the week
    assert ladder.at(at(EASTER, "2020-03-31"))[4] is None           # the month's last weekday closes it


@pytest.fixture(scope="module")
def wave():
    b = bars_on(pd.bdate_range("2019-01-01", periods=420, tz="UTC"), seed=4)
    return b, chain_rows(b)


def test_no_call_until_every_frame_has_a_range(wave):
    short = chain_rows(bars_on(pd.bdate_range("2019-01-01", periods=60, tz="UTC")))
    assert all((short[name] == 0).all() for name in ARMS)
    _, rows = wave
    called = rows[rows["H-K"] != 0]
    assert len(called) > 50                                          # the wave ranges the monthly frame
    assert not called["zones"].str.contains("None").any()


def test_each_call_is_the_bias_frames_context_with_its_draw_ahead(wave):
    b, rows = wave
    called = rows[rows["H-K"] != 0]
    last = called["contexts"].str.split("/").str[-1].map({"BULLISH": 1, "BEARISH": -1})
    assert last.eq(called["H-K"]).all()
    assert set(called["case"]) <= {"WITH_PARENT", "TO_PARENT_POI"}
    close = b.loc[called.index, "close"]
    assert ((called["draw"] > close) == (called["H-K"] > 0)).all()
    has = called["opposite"].notna()
    assert ((called.loc[has, "opposite"] < close[has]) == (called.loc[has, "H-K"] > 0)).all()


def test_call_reads_only_the_past(wave):
    """Property 2: the bars after a close change nothing read at it."""
    b, rows = wave
    for cut in (300, 377):
        part = chain_rows(b.iloc[:cut].reset_index(drop=True))
        pd.testing.assert_frame_equal(part, rows.iloc[:cut].reset_index(drop=True), check_dtype=False)


def test_draw_race_against_geometry():
    days = pd.bdate_range("2021-01-04", periods=8, tz="UTC")
    b = pd.DataFrame({"time": days, "open": 100.0, "close": 100.0,
                      "high": [100.5, 101.0, 106.0, 101.0, 101.0, 110.0, 101.0, 101.0],
                      "low": [99.5, 99.0, 99.0, 99.0, 99.0, 90.0, 99.0, 99.0]})
    rows = pd.DataFrame({"time": days, "H-K": [1, -1, 0, 1, 0, 0, 0, 1],
                         "draw": [105.0, 95.0, np.nan, 109.0, np.nan, np.nan, np.nan, 120.0],
                         "opposite": [97.5, 105.0, np.nan, 95.0, np.nan, np.nan, np.nan, 80.0]})
    race = draw_race(rows, b)
    assert list(race["outcome"]) == ["held", "failed", "both", "open"]
    assert race["geo"].tolist() == pytest.approx([2.5 / 7.5, 0.5, 5 / 14, 0.5])
    r = judge_race({"X": race})
    assert (r["resolved"], r["open"], r["both"]) == (3, 1, 1)
    assert r["held"] == pytest.approx(1 / 3) and r["excess"] == pytest.approx(np.mean([1 - 1 / 3, -0.5, -5 / 14]))


def test_month_interval_brackets_the_excess(wave):
    b, rows = wave
    frame = daily_signals(b).join(rows.drop(columns="time"))
    lo, hi = month_interval({"X": frame, "Y": frame}, lambda d: d["H-K"].fillna(0).to_numpy())
    called = frame[(frame["H-K"] != 0) & frame["next_dir"].ne(0) & frame["next_body"].notna()]
    up = float((frame.loc[frame["next_dir"].ne(0) & frame["next_body"].notna(), "next_dir"] > 0).mean())
    excess = ((called["next_dir"] == called["H-K"]).astype(float)
              - np.where(called["H-K"] > 0, up, 1 - up)).mean()
    assert lo <= excess <= hi and hi - lo > 0
