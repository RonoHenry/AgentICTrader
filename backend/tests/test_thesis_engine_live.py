"""
Tests for the Thesis Engine on live bars, on paper (thesis-engine Requirement 14; task 416), with a fake terminal.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

import pandas as pd
import pytest

from agent.context_calls import Call
from tests.thesis_engine_walks import walk_m1
from thesis_engine.live import MARKETS, Runner


@pytest.fixture(scope="module")
def walk():
    return walk_m1(8, seed=21)


def fake(walk, asked):
    def bars(market, start, end):
        asked.append((market, start, end))
        t = walk["time"]
        return walk[(t >= pd.Timestamp(start)) & (t < pd.Timestamp(end))].reset_index(drop=True)
    return bars


def test_without_a_call_every_market_is_flat_and_nothing_is_read(walk, tmp_path):
    asked = []
    rows = Runner(fake(walk, asked), calls=tmp_path / "none.json", out=tmp_path / "out").cycle(
        datetime(2022, 2, 9, 12, tzinfo=timezone.utc))
    assert [r["market"] for r in rows] == list(MARKETS)
    assert all(r["state"] == "FLAT" for r in rows) and asked == []
    assert json.loads((tmp_path / "out" / "status.json").read_text(encoding="utf-8"))["markets"]


def test_a_live_call_runs_the_machine_and_each_cycle_extends_the_last(walk, tmp_path):
    week = walk[(walk["time"] >= pd.Timestamp("2022-02-06 22:00", tz="UTC"))]
    open_ = float(week["open"].iloc[0])
    call = Call("EURUSD", "2022-02-07", "BULLISH", open_ + 0.02, open_ - 0.02, made_at="2022-02-05T10:00:00+00:00")
    calls = tmp_path / "calls.json"
    calls.write_text(json.dumps([asdict(call)]), encoding="utf-8")
    asked = []
    runner = Runner(fake(walk, asked), calls=calls, out=tmp_path / "out")
    now = datetime(2022, 2, 8, 15, 30, 30, tzinfo=timezone.utc)
    first = {r["market"]: r for r in runner.cycle(now)}
    assert {m for m, _, _ in asked} == {"EURUSD"}                      # only the market with a live call is read
    eur = first["EURUSD"]
    assert eur["state"] != "FLAT" and eur["new"] and eur["new"][0][2] == "THESIS"
    m1 = runner._m1["EURUSD"]
    assert (m1["time"] + pd.Timedelta(minutes=1) <= pd.Timestamp(now)).all()   # never the forming minute
    later = {r["market"]: r for r in runner.cycle(datetime(2022, 2, 10, 15, tzinfo=timezone.utc))}
    seen = len(eur["new"])
    again = (tmp_path / "out" / "EURUSD.jsonl").read_text(encoding="utf-8").splitlines()
    moves = [json.loads(x) for x in again if json.loads(x)["record"] == "transition"]
    assert [(m["t"], m["frm"], m["to"]) for m in moves[seen:]] == [(t, a, b) for t, a, b, _ in later["EURUSD"]["new"]]
    assert asked[-1][1] > asked[0][1]                                  # the second cycle reads only new minutes
