"""
The thesis run and its score (market-narrative Requirement 16.5-16.6, task 350), with a fake model on the fixture
snapshot: nothing leaves the machine.
"""
from __future__ import annotations

import json
from datetime import date

import httpx

from algo_research.thesis.llm import LLMClient, LLMConfig
from algo_research.thesis.run import export, run, score, trading_days
from tests.test_backtest_watch import setup  # noqa: F401  (fixture: the EURUSD fixture month as a snapshot)


def test_trading_days_are_the_weekdays_in_a_fixed_shuffled_order():
    days = trading_days(date(2025, 1, 1), date(2025, 2, 1))
    assert len(days) == 23 and all(d.weekday() < 5 for d in days)
    assert days == trading_days(date(2025, 1, 1), date(2025, 2, 1)) and days != sorted(days)


def test_a_run_keeps_one_scored_thesis_per_day_and_resumes(setup, tmp_path):  # noqa: F811
    root, snap = setup
    answers = iter(['{"bias": "bullish", "draw": 1080, "invalidation": 960, "confidence": "medium", "reason": "r"}',
                    'thinking without an answer', '{"bias": "neutral", "draw": null, "invalidation": null}'])
    seen = []

    def model(request):
        seen.append(json.loads(request.content))
        text = next(answers)
        return httpx.Response(200, json={"model": "fake/m", "choices": [{"message": {"content": text}}],
                                         "usage": {"cost": 0.001}})

    client = LLMClient(LLMConfig(api_key="k", model="fake/m", cache_dir=tmp_path / "cache"),
                       transport=httpx.MockTransport(model), sleep=lambda s: None)
    out = tmp_path / "theses"
    kept = run(["EURUSD"], date(2026, 10, 1), date(2026, 10, 3), None, client, "low", root=out, snapshot=snap)
    assert [k["trading_date"] for k in kept] == ["2026-10-01", "2026-10-02"]
    first, second = kept
    assert first["thesis"]["bias"] == "BULLISH" and first["score"]["outcome"] in ("DRAW", "INVALIDATED", "NEITHER")
    assert first["thesis"]["draw"] > first["open"] > first["thesis"]["invalidation"]
    assert second["thesis"]["bias"] == "NO_THESIS" and second["error"] is None      # retried once, then neutral
    assert seen[2]["messages"][-1]["role"] == "user" and "fixed form" in seen[2]["messages"][-1]["content"]
    assert seen[0]["reasoning"] == {"effort": "low"} and "EURUSD" not in json.dumps(seen)
    assert (out / "fake__m" / "EURUSD" / "2026-10-01.json").is_file()
    again = run(["EURUSD"], date(2026, 10, 1), date(2026, 10, 3), None, client, "low", root=out, snapshot=snap)
    assert len(seen) == 3 and len(again) == 2                                        # kept days are not asked again
    text = score(out)
    assert "2 days, 1 with a thesis, 1 neutral" in text and "DRAW before invalidation" in text
    table = export("fake/m", tmp_path / "theses.json", root=out)
    assert table == {"EURUSD": {"2026-10-01": "BULLISH", "2026-10-02": "NO_THESIS"}}
    assert json.loads((tmp_path / "theses.json").read_text(encoding="utf-8")) == table
