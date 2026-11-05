"""
Tests for the Thesis Engine on Noculus and the trader's scenarios (thesis-engine Requirement 12; task 414): the
layer's route, the recent months' period, and the scenarios' record and run.
"""
from __future__ import annotations

import pandas as pd
import pytest

import algo_backtester.watch as watch
from tests.test_backtest_watch import session, setup  # noqa: F401  (fixtures)
from tests.thesis_engine_walks import walk_m1
from thesis_engine.replay import prepare
from thesis_engine.scenarios import Scenario, Trade, load, run_one, save


def test_the_layer_answers_for_every_source(session):  # noqa: F811
    end = session.status()["end"]
    for source in watch.THESIS_SOURCES:
        got = session.thesis({"t": end, "source": source})
        assert got["withheld"] is False and got["source"] == source and got["words"]
        assert set(got) >= {"moves", "now", "thesis", "level", "theses", "levels", "sweeps", "skips", "trades"}
        assert all(m["t"] <= end for m in got["moves"])
        assert got["hindsight"] == (source in ("ORACLE", "MIRROR"))
    with pytest.raises(ValueError):
        session.thesis({"t": end, "source": "GUESS"})


def test_a_trades_exit_shows_only_once_it_is_past(session):  # noqa: F811
    end = session.status()["end"]
    got = session.thesis({"t": end, "source": "ORACLE"})
    for tr in got["trades"]:
        if tr["closed"] is not None:
            early = session.thesis({"t": tr["closed"] - 60, "source": "ORACLE"})
            assert all(x["net_r"] is None for x in early["trades"] if x["placed"] == tr["placed"])


def test_a_blind_session_shows_nothing(session, monkeypatch):  # noqa: F811
    monkeypatch.setattr(type(session), "withheld", property(lambda self: True))
    assert session.thesis({"t": session.status()["end"], "source": "ORACLE"}) == {"withheld": True}


def test_scenarios_round_trip_and_their_r(tmp_path):
    sc = Scenario("UK100, 15 Oct", "UK100", "BULLISH", 10783.4, 10623.3, "2026-10-14 18:00", "2026-10-16 17:00",
                  Trade("LONG", 10708.6, 10702.5, 10775.9, "2026-10-15 01:51"), "from the notes")
    path = save([sc], tmp_path / "scenarios.json")
    assert load(path) == [sc]
    assert sc.trade.r == pytest.approx((10775.9 - 10708.6) / (10708.6 - 10702.5))
    th = sc.thesis()
    assert th.source == "SCENARIO" and th.since == pd.Timestamp("2026-10-14 18:00", tz="America/New_York").value
    short = Trade("SHORT", 100.0, 101.0, 95.0)
    assert short.r == pytest.approx(5.0)


def test_a_scenario_runs_beside_the_traders_trade():
    mk = prepare("EURUSD", walk_m1(8, seed=21))
    w1 = mk.book.frames["W1"].c
    ny = lambda ns: pd.Timestamp(int(ns), tz="UTC").tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M")  # noqa: E731
    k = 5
    up = w1.c[k] > w1.o[k]
    draw, protected = (w1.h[k], w1.l[k] - 0.001) if up else (w1.l[k], w1.h[k] + 0.001)
    sc = Scenario("walk", "EURUSD", "BULLISH" if up else "BEARISH", float(draw), float(protected), ny(w1.t[k]),
                  ny(w1.end[k]), Trade("LONG" if up else "SHORT", float(w1.o[k]), float(protected), float(draw),
                                       ny(w1.t[k] + 3600 * 10**9)), "a random walk")
    got = run_one(sc, mk)
    assert got["name"] == "walk" and got["moves"] and got["moves"][0][2] == "THESIS"
    assert got["ended"] is not None
    if got["trades"]:
        assert "nearest" in got
