"""
Tests for algo_mind/sources.py and algo_mind/memory.py — the live senses and memory (algo-mind Requirements 1, 3,
task 383).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from algo_mind.memory import analogs
from algo_mind.sources import live_days, state_at
from algo_research.search_state import FEATURES, state_table


def days(n=1400, seed=4, start="2015-01-05"):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n)
    o = 100 + rng.normal(0, 1, n).cumsum()
    c = o + rng.normal(0, 0.8, n)
    return pd.DataFrame({"date": dates, "open": o, "high": np.maximum(o, c) + rng.uniform(0.1, 1, n),
                         "low": np.minimum(o, c) - rng.uniform(0.1, 1, n), "close": c})


def test_a_live_state_matches_trainings_and_reads_nothing_from_its_week_on():
    d = days()
    table = state_table("X", d)
    for i in (5, 40, 77):                                   # weeks mid-month and at a month's turn
        row = table.iloc[-i]
        monday = row["week"]
        live, provisional = state_at("X", d, monday, price=row["open"])
        assert not provisional
        assert np.allclose([live[f] for f in FEATURES], row[list(FEATURES)].to_numpy(float))
        later = d.copy()
        later.loc[later["date"] >= monday, ["high", "low", "close"]] *= 1.5          # what follows can't matter
        again, _ = state_at("X", later, monday, price=row["open"])
        assert np.allclose([again[f] for f in FEATURES], [live[f] for f in FEATURES])
    monday = table["week"].iloc[-1]
    _, short = state_at("X", d[d["date"] < monday - pd.Timedelta(days=3)], monday)    # no Friday: provisional
    assert short


def chart(dates, opens, highs, lows, closes, last_price):
    t = [int(pd.Timestamp(x, tz="UTC").timestamp()) for x in dates]
    return {"chart": {"result": [{"meta": {"exchangeTimezoneName": "UTC", "regularMarketPrice": last_price},
                                  "timestamp": t, "indicators": {"quote": [
                                      {"open": opens, "high": highs, "low": lows, "close": closes}]}}]}}


def test_live_days_leave_out_today_and_close_an_fx_day_at_the_next_open():
    data = chart(["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"], [1.10, 1.11, 1.12, 1.13],
                 [1.12, 1.13, 1.14, 1.15], [1.09, 1.10, 1.11, 1.12], [1.10, 1.11, 1.12, 1.13], 1.125)
    fx = live_days(data, "EURUSD", date(2026, 10, 29))
    assert list(fx["date"].dt.day) == [26, 27, 28] and list(fx["close"]) == [1.11, 1.12, 1.13]
    weekend = live_days(data, "EURUSD", date(2026, 10, 31))
    assert weekend["close"].iat[-1] == 1.125                # the last day closes at the last price
    index = live_days(data, "US500", date(2026, 10, 29))
    assert list(index["close"]) == [1.10, 1.11, 1.12]


def test_memory_gives_the_nearest_training_weeks_and_their_up_share():
    rng = np.random.default_rng(0)
    train = pd.DataFrame(rng.normal(size=(300, len(FEATURES))), columns=list(FEATURES))
    train = train.assign(market="X", week=pd.date_range("2000-01-03", periods=300, freq="W-MON"),
                         up=np.where(rng.normal(size=300) > 0, 1.0, -1.0))
    state = train.iloc[17][list(FEATURES)].to_dict()
    a = analogs(train, state, k=20)
    assert a["k"] == 20 and a["weeks"][0]["week"] == train["week"].iat[17].date().isoformat()
    assert a["weeks"][0]["distance"] == 0.0
    z = (train[list(FEATURES)] - train[list(FEATURES)].mean()) / train[list(FEATURES)].std(ddof=0)
    d = np.sqrt(((z - z.iloc[17]) ** 2).sum(axis=1))
    expect = set(d.nsmallest(20).index)
    assert {w["week"] for w in a["weeks"]} == {train["week"].iat[i].date().isoformat() for i in expect}
    assert np.isclose(a["share_up"], (train.loc[list(expect), "up"] > 0).mean())
