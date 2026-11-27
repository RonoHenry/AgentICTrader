"""
Tests for Algo Mind on the context page: AlgoMindDIS beside the trader's calls (context-engine Requirement 35,
tasks 395 and 397; the brain was retired 2026-11-03).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agent.context_calls import Call
from algo_research.replay.context import ContextApp, coherence
from tests.test_context_calls import week_bars

UTC = timezone.utc


def app(tmp_path, clock, **kw):
    kw.setdefault("shadows", tmp_path / "dis")
    return ContextApp(tmp_path / "calls.json", tmp_path / "theses.json", clock=lambda: clock, **kw)


def _record(side: str, state: str) -> dict:
    return {"side": side, "state": state, "since": None, "draw": None, "protected": None, "evidence": [],
            "ignored": [], "invalidation": "", "ended": None}


#: AlgoMindDIS's read of a week (reader v0's records).
SHADOW = {"week": "2026-11-02", "source": "reader", "version": "v0-fe84645", "made_at": "2026-11-02T08:00:00+00:00",
          "rows": [{"market": "EURUSD", "open": _record("BEARISH", "ACTIVE"), "now": _record("BEARISH", "ACTIVE"),
                    "spans": [], "weeks": [], "reads": []},
                   {"market": "GBPUSD", "open": _record("NONE", "UNDETERMINED"),
                    "now": _record("NONE", "UNDETERMINED"), "spans": [], "weeks": [], "reads": []},
                   {"market": "DXY", "error": "the broker gives no H1 bars for it"}]}


def _shadow(tmp_path):
    (tmp_path / "dis").mkdir(exist_ok=True)
    (tmp_path / "dis" / "2026-11-02.json").write_text(json.dumps(SHADOW), encoding="utf-8")


def test_the_readers_record_sits_beside_the_call_and_its_button_reads_again(tmp_path):
    _shadow(tmp_path)
    made = []
    a = app(tmp_path, datetime(2026, 11, 2, 9, tzinfo=UTC), shadow_writer=made.append)
    v = a.view({"week": "2026-11-02"})
    rows = {r["instrument"]: r for r in v["rows"]}
    assert v["reader"] == {"source": "reader", "version": "v0-fe84645", "made_at": "2026-11-02T08:00:00+00:00"}
    assert rows["EURUSD"]["reader"]["open"]["side"] == "BEARISH" and rows["XAUUSD"]["reader"] is None
    assert "error" in rows["DXY"]["reader"]
    assert "brain" not in v and "brain" not in rows["EURUSD"]                # retired (task 397)
    assert a.run_reader({"week": "2026-11-02"})["reader"]["version"] == "v0-fe84645"
    assert [m.isoformat() for m in made] == ["2026-11-02"]
    assert a.view({"week": "2026-10-26"})["reader"] is None
    with pytest.raises(LookupError):                         # no terminal: nothing to read with
        app(tmp_path, datetime(2026, 11, 2, 9, tzinfo=UTC)).run_reader({"week": "2026-11-02"})


def test_a_saved_call_writes_only_the_traders_thesis_file(tmp_path):
    a = app(tmp_path, datetime(2026, 10, 31, 12, tzinfo=UTC))
    a.call({"week": "2026-11-02", "instrument": "EURUSD", "side": "BULLISH", "draw": 1.13, "protected": 1.10})
    assert list(json.loads((tmp_path / "theses.json").read_text(encoding="utf-8"))) == ["EURUSD"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["calls.json", "theses.json"]   # no agreement file
    assert coherence({"US100": "BULLISH", "US500": "BEARISH"}) == [
        "the US indices are called apart: US100 bullish, US500 bearish"]


def test_the_scorecard_scores_the_side_the_week_opened_with(tmp_path):
    _shadow(tmp_path)
    (tmp_path / "dis.json").write_text(json.dumps([
        {"instrument": "EURUSD", "placed_at": "2026-11-03T08:00:00+00:00", "filled_at": "2026-11-03T08:05:00+00:00",
         "net_r": -1.0}]), encoding="utf-8")
    a = app(tmp_path, datetime(2026, 11, 7, tzinfo=UTC), bars=lambda inst, s, e: week_bars(),
            paper={"context": tmp_path / "none.json", "dis": tmp_path / "dis.json"})
    a.book().put(Call("US500", "2026-11-02", "BULLISH", 105, 95, made_at="2026-10-31T12:00:00+00:00"))
    card = a.scorecard()
    rows = {r["market"]: r for r in card["weeks"][0]["rows"]}
    assert set(rows) == {"EURUSD", "US500"}                   # GBPUSD: no side from anyone
    assert rows["EURUSD"]["reader"] == {"call": "BEARISH", "state": "ACTIVE", "hit": False}   # the week went up
    assert rows["US500"]["reader"] is None and "brain" not in rows["US500"]
    t = card["totals"]
    assert t["reader"] == {"calls": 1, "final": 1, "hits": 0, "hit_rate": 0.0,
                           "agents": {"context": {"n": 0, "r": 0.0}, "dis": {"n": 1, "r": -1.0}}}
    assert t["agents"]["dis"] == {"n": 0, "r": 0.0}           # on the trader's markets: US500 only
    assert "brain" not in t and "agree" not in t


def test_the_dis_hands_differ_from_the_context_variant_only_in_their_thesis_file():
    from agent.context_calls import PAPER_FILES, REPO
    from algo_backtester.config import load_run_config
    from algo_mind.shadow import DIS_THESES

    focus = REPO / "config" / "backtests" / "focus.toml"
    context = load_run_config(focus, "fresh_near_gap_context")
    hands = load_run_config(focus, "fresh_near_gap_dis")
    assert (REPO / hands.strategy.thesis_file).resolve() == DIS_THESES.resolve()
    assert hands.strategy.model_dump(exclude={"thesis_file"}) == context.strategy.model_dump(exclude={"thesis_file"})
    assert hands.management == context.management
    assert set(PAPER_FILES) == {"context", "dis", "partial", "control"}
    for retired in ("fresh_near_gap_brain", "fresh_near_gap_agree"):
        with pytest.raises(ValueError, match="Unknown variant"):
            load_run_config(focus, retired)
