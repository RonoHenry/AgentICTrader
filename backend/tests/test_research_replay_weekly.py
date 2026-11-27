"""
Tests for algo_research/replay/weekly.py — blind weekly calls (context-engine Requirement 36, task 396).

On hand-made daily bars: the charts' window and order, what a blind chart shows (nothing after its Friday, dates
56 years later on the same weekdays, the last close at 1000, no market), the call's checks, the score from the
real prices, the reveal only after the save, and the totals.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from algo_research.replay.weekly import EVIDENCE, WeeklyApp

FRIDAY = pd.Timestamp("2010-06-04")
ITEM = "AAA:2010-05-31"


def _days(seed: int, bend: bool = False) -> pd.DataFrame:
    dates = pd.bdate_range("1994-01-03", "2018-12-31")
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.3, len(dates)))
    close -= close[dates.get_loc(FRIDAY)] - 100                       # 100 at the test's Friday
    if bend:                                                          # the week after it rises to 104
        k = dates.get_loc(FRIDAY)
        close[k + 1:k + 6] = [100.5, 102.0, 104.0, 104.0, 104.0]
        close[k + 6:] += 104 - close[k + 6] + 0.0
    opens = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"date": dates, "open": opens, "close": close,
                         "high": np.maximum(opens, close) + 0.5, "low": np.minimum(opens, close) - 0.5})


@pytest.fixture()
def app(tmp_path):
    data = {"AAA": _days(1, bend=True), "BBB": _days(2)}
    return WeeklyApp(tmp_path, loader=lambda m: data[m], markets=("AAA", "BBB"), seed=7, reader=False)


def _n(app) -> int:
    return app.order().index(ITEM)


def test_the_charts_fall_in_the_window_in_a_fixed_order_once_each(app, tmp_path):
    order = app.order()
    assert len(order) == len(set(order))
    mondays = pd.to_datetime([i.split(":")[1] for i in order])
    assert mondays.min() >= pd.Timestamp("1996-01-01") and mondays.max() <= pd.Timestamp("2017-12-25")
    again = WeeklyApp(tmp_path / "x", loader=app.loader, markets=("AAA", "BBB"), seed=7, reader=False)
    assert again.order() == order


def test_a_blind_chart_ends_at_its_friday_moved_56_years_and_scaled_to_1000(app):
    c = app.chart({"id": _n(app)})
    assert "AAA" not in json.dumps(c) and "2010" not in json.dumps(c) and "market" not in c
    d1 = c["bars"]["D1"]
    last = pd.Timestamp(d1[-1]["time"])
    assert last == pd.Timestamp("2066-06-04") and last.dayofweek == FRIDAY.dayofweek
    assert d1[-1]["close"] == pytest.approx(1000.0)
    w1 = c["bars"]["W1"]
    assert pd.Timestamp(w1[-1]["time"]) == pd.Timestamp("2066-05-31")
    assert all(pd.Timestamp(b["time"]) <= last for tf in ("MN1", "W1", "D1") for b in c["bars"][tf])
    assert c["last"] == pytest.approx(1000.0)


def test_a_call_is_checked_against_the_last_close_and_keeps_the_real_prices(app):
    with pytest.raises(ValueError):
        app.call({"id": _n(app), "side": "BULLISH", "draw": 990, "protected": 980, "confidence": 2})
    with pytest.raises(ValueError):
        app.call({"id": _n(app), "side": "BULLISH", "draw": 1030, "protected": 980, "confidence": 2,
                  "evidence": ["not a tag"]})
    with pytest.raises(LookupError):
        app.reveal({"id": _n(app)})
    out = app.call({"id": _n(app), "side": "BULLISH", "draw": 1030, "protected": 980, "confidence": 3,
                    "evidence": [EVIDENCE[0]], "note": "test", "ms": 4200})
    rec = app.records()[ITEM]
    assert rec["draw_real"] == pytest.approx(103.0) and rec["protected_real"] == pytest.approx(98.0)
    assert out["market"] == "AAA" and out["friday"] == "2010-06-04"
    s = out["score"]
    assert s["week_hit"] == 1.0 and s["race"] == "held" and s["days"] == 5         # Wed 9 Jun's 104.5 high
    assert 0 <= s["drift"] <= 1 and 0 <= s["control"] <= 1 and 0 < s["geo"] < 1
    assert pd.Timestamp(out["bars_after"][0]["time"]) == pd.Timestamp("2066-06-07")
    assert len(out["bars_after"]) == 40
    with pytest.raises(ValueError):
        app.call({"id": _n(app), "side": "NONE"})                       # each chart once


def test_the_totals_leave_out_none_and_recognised_charts(app):
    order = [i for i, x in enumerate(app.order()) if x != ITEM]
    app.call({"id": _n(app), "side": "BULLISH", "draw": 1030, "protected": 980, "confidence": 2})
    app.call({"id": order[0], "side": "NONE"})
    c = app.chart({"id": order[1]})
    app.call({"id": order[1], "side": "BEARISH", "draw": c["last"] * 0.97, "protected": c["last"] * 1.02,
              "confidence": 1, "recognised": True})
    t = app.summary()
    assert (t["calls"], t["sided"], t["none"], t["recognised"]) == (3, 1, 1, 1)
    assert t["week"]["n"] == 1 and t["week"]["hit"] == 1.0
    assert t["race"]["n"] == 1
    assert app.chart()["id"] not in {_n(app), order[0], order[1]}
