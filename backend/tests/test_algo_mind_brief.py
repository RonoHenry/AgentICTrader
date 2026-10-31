"""
Tests for algo_mind/brief.py — the week's brief and the thesis files (algo-mind Requirements 4.1, 5.1, task 384).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from agent.context_calls import Call, ContextBook
from algo_mind.brain import fit_version
from algo_mind.brief import write_agree_theses, write_brief
from algo_research.search_state import FEATURES


def chart(seed: int, end="2026-10-31"):
    """A Yahoo-shaped daily chart from 2025-01-01."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-01", end)
    n = len(dates)
    o = 100 + rng.normal(0, 1, n).cumsum()
    c = o + rng.normal(0, 0.8, n)
    q = {"open": list(o), "close": list(c), "high": list(np.maximum(o, c) + rng.uniform(0.1, 1, n)),
         "low": list(np.minimum(o, c) - rng.uniform(0.1, 1, n))}
    return {"chart": {"result": [{"meta": {"exchangeTimezoneName": "UTC", "regularMarketPrice": float(c[-1])},
                                  "timestamp": [int(pd.Timestamp(d, tz="UTC").timestamp()) for d in dates],
                                  "indicators": {"quote": [q]}}]}}


def brain(tmp_path):
    rng = np.random.default_rng(0)
    t = pd.DataFrame(rng.normal(size=(1200, len(FEATURES))), columns=list(FEATURES))
    t = t.assign(market=np.where(np.arange(1200) % 2, "US500", "UK100"),
                 week=pd.Timestamp("2005-01-03") + pd.to_timedelta((np.arange(1200) // 2) * 7, unit="D"),
                 up=np.where(rng.normal(size=1200) + 0.6 * t["W1_body"] > 0, 1.0, -1.0))
    return fit_version(t, end=pd.Timestamp("2020-01-01"), version="v1", root=tmp_path / "models")


def test_a_brief_reads_each_market_and_writes_the_brains_thesis_file(tmp_path):
    brain(tmp_path)
    charts = {"US500": chart(1), "UK100": chart(2)}
    macro = lambda symbol, a, b: chart(9)                                  # noqa: E731  (the yields and the VIX)
    path = write_brief(pd.Timestamp("2026-11-02"), "v1", now=datetime(2026, 10, 31, 12, tzinfo=timezone.utc),
                       markets=("US500", "UK100"), fetcher=lambda m, now: charts[m], root=tmp_path,
                       macro_fetcher=macro)
    brief = json.loads(path.read_text(encoding="utf-8"))
    assert brief["week"] == "2026-11-02" and brief["version"] == "v1"
    rows = {r["market"]: r for r in brief["rows"]}
    for r in rows.values():
        assert 0 <= r["p"] <= 1 and r["call"] in ("BULLISH", "BEARISH", "NONE") and r["provisional"] is False
        assert r["analogs"]["k"] == 20 and set(r["state"]) == set(FEATURES)
    theses = json.loads((tmp_path / "brain_theses.json").read_text(encoding="utf-8"))
    called = [m for m, r in rows.items() if r["call"] != "NONE"]
    assert sorted(theses) == sorted(called)
    for m in called:
        assert sorted(theses[m]) == ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
        assert theses[m]["2026-11-04"] == {"side": rows[m]["call"]}
    early = write_brief(pd.Timestamp("2026-11-02"), "v1", now=datetime(2026, 10, 29, 12, tzinfo=timezone.utc),
                        markets=("US500",), fetcher=lambda m, now: charts[m], root=tmp_path, name="early",
                        macro_fetcher=macro)
    assert json.loads(early.read_text(encoding="utf-8"))["rows"][0]["provisional"] is True     # no Thursday/Friday


def test_the_agreement_holds_only_the_markets_where_trader_and_brain_agree(tmp_path):
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / "2026-11-02.json").write_text(json.dumps({"week": "2026-11-02", "rows": [
        {"market": "US500", "call": "BULLISH"}, {"market": "UK100", "call": "BEARISH"},
        {"market": "EURUSD", "call": "NONE"}]}), encoding="utf-8")
    book = ContextBook(tmp_path / "calls.json", tmp_path / "theses.json")
    made = "2026-10-31T12:00:00+00:00"
    book.put(Call("US500", "2026-11-02", "BULLISH", 7900, 7600, made_at=made))
    book.put(Call("UK100", "2026-11-02", "BULLISH", 10900, 10500, made_at=made))
    book.put(Call("EURUSD", "2026-11-02", "BEARISH", 1.10, 1.13, made_at=made))
    out = write_agree_theses(book, briefs, tmp_path / "agree.json")
    agree = json.loads(out.read_text(encoding="utf-8"))
    assert list(agree) == ["US500"]
    assert agree["US500"]["2026-11-05"] == {"side": "BULLISH", "draw": 7900.0, "protected": 7600.0,
                                            "since": "2026-11-01T22:00:00+00:00"}


def test_a_candidate_version_calls_beside_the_one_in_use(tmp_path):
    from algo_research.search_state2 import FEATURES as WIDE

    brain(tmp_path)
    rng = np.random.default_rng(3)
    t = pd.DataFrame(rng.normal(size=(1200, len(WIDE))), columns=list(WIDE))
    t = t.assign(market=np.where(np.arange(1200) % 2, "US500", "UK100"),
                 week=pd.Timestamp("2005-01-03") + pd.to_timedelta((np.arange(1200) // 2) * 7, unit="D"),
                 up=np.where(rng.normal(size=1200) + 0.6 * t["curve"] > 0, 1.0, -1.0))
    fit_version(t, end=pd.Timestamp("2020-01-01"), version="v2", root=tmp_path / "models", features=WIDE)
    charts = {"US500": chart(1), "UK100": chart(2)}
    path = write_brief(pd.Timestamp("2026-11-02"), "v1", now=datetime(2026, 10, 31, 12, tzinfo=timezone.utc),
                       markets=("US500", "UK100"), fetcher=lambda m, now: charts[m], root=tmp_path,
                       candidates=("v2",), macro_fetcher=lambda s, a, b: chart(9))
    brief = json.loads(path.read_text(encoding="utf-8"))
    assert brief["version"] == "v1" and brief["candidates"] == ["v2"]
    for r in brief["rows"]:
        assert set(r["candidates"]) == {"v2"} and r["candidates"]["v2"]["call"] in ("BULLISH", "BEARISH", "NONE")
