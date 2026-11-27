"""
Tests for AlgoMindDIS on the Noculus engine chart (algomind-dis Requirement 16.3; task 407): the chart's trading days
from H1, and what the chart view serves.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from algomind_dis.frames import from_daily, ny_daily
from algomind_dis.view import ChartView, to_wall
from tests.test_algomind_dis_replay import walk


def test_h1_bars_become_the_charts_new_york_trading_days():
    t = pd.date_range("2026-10-30 19:00", "2026-11-03 01:00", freq="h", tz="UTC")     # across the clocks' change
    closed = (t >= pd.Timestamp("2026-10-30 21:00", tz="UTC")) & (t < pd.Timestamp("2026-11-01 22:00", tz="UTC"))
    t = t[~closed]                                  # Friday 17:00 New York (EDT) to Sunday 17:00 (EST): no bars
    x = np.arange(len(t), dtype=float)
    days = ny_daily(pd.DataFrame({"time": t, "open": x, "high": x + 1, "low": x - 1, "close": x + 0.5}))
    assert [d.date().isoformat() for d in days["date"]] == ["2026-10-30", "2026-11-02", "2026-11-03"]
    fri = days.iloc[0]
    assert fri["open"] == 0.0                                       # 19:00 UTC Friday is 15:00 New York (EDT)
    mon = days.iloc[1]                                              # Sunday 17:00 EST (22:00 UTC) to Monday 17:00
    first = int(np.flatnonzero(t == pd.Timestamp("2026-11-01 22:00", tz="UTC"))[0])
    last = int(np.flatnonzero(t == pd.Timestamp("2026-11-02 21:00", tz="UTC"))[0])
    assert (mon["open"], mon["close"]) == (float(first), last + 0.5)


def test_the_chart_view_serves_states_changes_and_a_close_on_wall_time():
    days = walk(3, "2016-01-04", 900)
    v = ChartView("WALK", from_daily("WALK", days))
    rows = v.timeline.rows
    first_wall = to_wall(int(rows["t"].iloc[0]))
    date0 = pd.Timestamp(days["date"].iloc[0])
    assert first_wall == int((date0 + pd.Timedelta(hours=17)).value // 10**9)    # the trading date's 17:00 close
    clock = to_wall(int(rows["t"].iloc[-1]))
    served = v.rows(clock - 60 * 86400, clock)
    assert served and all(r["close"] - r["open"] == 86400 for r in served)
    assert {r["state"] for r in served} <= {"UNDETERMINED", "BULLISH", "BEARISH", "NEUTRAL", "TRANSITIONAL"}
    k = v.index_at(clock)
    d = v.detail(k)
    json.dumps(d)                                                   # the page reads it as JSON
    assert d["close"] == clock and set(d["categories"]) == {"STRUCTURE", "LIQUIDITY", "PREMIUM_DISCOUNT", "PD_ARRAY",
                                                            "DELIVERY"}
    assert d["narrative"].startswith("WALK at ") and set(d["frames"]) == {"MN1", "W1", "D1"}
    assert v.index_at(first_wall - 1) is None
    sided = rows.index[rows["state"].isin(["BULLISH", "BEARISH"])]
    if len(sided):
        s = v.detail(int(sided[0]))
        assert s["since"] is not None and s["draw"] is not None and s["protected"] is not None and s["supporting"]
