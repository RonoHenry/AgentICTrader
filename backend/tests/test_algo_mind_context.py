"""
Tests for the brain on the context page (algo-mind Requirements 4.2-4.3, 5.1, task 385).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from agent.context_calls import Call
from algo_research.replay.context import ContextApp, coherence
from tests.test_context_calls import week_bars

UTC = timezone.utc
BRIEF = {"week": "2026-11-02", "version": "v1", "made_at": "2026-11-01T12:00:00+00:00", "thresholds": [0.48, 0.52],
         "rows": [{"market": "DXY", "call": "BULLISH", "p": 0.53, "provisional": False, "analogs": {"share_up": 0.6}},
                  {"market": "EURUSD", "call": "BULLISH", "p": 0.54, "provisional": False,
                   "analogs": {"share_up": 0.45}},
                  {"market": "US500", "call": "BEARISH", "p": 0.46, "provisional": False,
                   "analogs": {"share_up": 0.4}},
                  {"market": "UK100", "call": "NONE", "p": 0.50, "provisional": False, "analogs": {"share_up": 0.5}}]}


def app(tmp_path, clock, **kw):
    briefs = tmp_path / "briefs"
    briefs.mkdir(exist_ok=True)
    (briefs / "2026-11-02.json").write_text(json.dumps(BRIEF), encoding="utf-8")
    return ContextApp(tmp_path / "calls.json", tmp_path / "theses.json", clock=lambda: clock, briefs=briefs,
                      agree=tmp_path / "agree.json", **kw)


def test_the_brain_sits_beside_the_traders_call_and_the_agreement_is_written(tmp_path):
    a = app(tmp_path, datetime(2026, 10, 31, 12, tzinfo=UTC))
    a.call({"week": "2026-11-02", "instrument": "EURUSD", "side": "BULLISH", "draw": 1.13, "protected": 1.10})
    a.call({"week": "2026-11-02", "instrument": "US500", "side": "BULLISH", "draw": 7900, "protected": 7600})
    v = a.view({"week": "2026-11-02"})
    rows = {r["instrument"]: r for r in v["rows"]}
    assert rows["EURUSD"]["brain"] == {"call": "BULLISH", "p": 0.54, "provisional": False, "share_up": 0.45}
    assert rows["GBPUSD"]["brain"] is None and rows["EURUSD"]["call"]["side"] == "BULLISH"
    assert "DXY and EURUSD both bullish: they usually move apart" in v["brain"]["notes"]
    agree = json.loads((tmp_path / "agree.json").read_text(encoding="utf-8"))
    assert list(agree) == ["EURUSD"]                         # US500: the trader bullish, the brain bearish
    assert coherence({"US100": "BULLISH", "US500": "BEARISH"}) == [
        "the US indices are called apart: US100 bullish, US500 bearish"]


def test_the_brain_button_makes_the_brief_again(tmp_path):
    made = []
    a = app(tmp_path, datetime(2026, 10, 31, 12, tzinfo=UTC), brief_writer=lambda monday, book: made.append(monday))
    v = a.run_brain({"week": "2026-11-02"})
    assert [m.isoformat() for m in made] == ["2026-11-02"] and v["brain"]["version"] == "v1"


def test_the_scorecard_scores_the_brain_and_the_agreement(tmp_path):
    a = app(tmp_path, datetime(2026, 11, 7, tzinfo=UTC), bars=lambda inst, s, e: week_bars(),
            paper={"context": tmp_path / "none.json"})
    book = a.book()
    made = "2026-10-31T12:00:00+00:00"
    book.put(Call("EURUSD", "2026-11-02", "BULLISH", 105, 95, made_at=made))       # the week: 100 -> 103.5, up
    book.put(Call("US500", "2026-11-02", "BULLISH", 105, 95, made_at=made))
    card = a.scorecard()
    rows = {r["market"]: r for r in card["weeks"][0]["rows"]}
    assert set(rows) == {"DXY", "EURUSD", "US500"}            # UK100: no call from either
    assert rows["DXY"]["call"] is None and rows["DXY"]["brain"]["hit"] is True
    assert rows["US500"]["brain"]["hit"] is False and rows["US500"]["hit"] is True
    t = card["totals"]
    assert (t["calls"], t["hits"]) == (2, 2)
    assert t["brain"] == {"calls": 3, "final": 3, "hits": 2, "hit_rate": 2 / 3}
    assert t["agree"] == {"calls": 1, "final": 1, "hits": 1, "hit_rate": 1.0}
