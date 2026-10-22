"""
The thesis developer's blind facts and the answer's fixed form (market-narrative Requirement 16.1-16.3, task 349).

The facts are built with the backtester's own pieces on its fixture week: the as-of view, the engine under the gap,
its pools, and the trader's Fractal + POI indicator. They must name no date or market, rescale every price, and read
nothing after the open.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from agent.strategy_config import StrategyConfig
from algo_backtester.data import load_instrument
from algo_backtester.watch import SnapshotSource
from algo_research.fractal_poi import FractalPOI, FractalSettings
from algo_research.thesis.facts import Rescale, facts_at
from algo_research.thesis.prompt import messages_for, parse_answer
from tests.test_backtest_watch import setup  # noqa: F401  (fixture: the EURUSD fixture month as a snapshot)

UTC = timezone.utc
OPEN = datetime(2026, 9, 30, 21, 0, tzinfo=UTC)           # 17:00 New York (EDT): Thursday 1 October's trading day


def test_rescale_maps_the_open_to_1000_and_one_range_to_100_and_back():
    rs = Rescale(open=1.1050, atr=0.0080)
    assert rs.to(1.1050) == 1000.0 and rs.to(1.1130) == 1100.0 and rs.to(1.0970) == 900.0
    assert abs(rs.back(1100.0) - 1.1130) < 1e-12 and abs(rs.back(rs.to(1.10734)) - 1.10734) < 1e-5


def _facts(snap, alter_after=None):
    if alter_after is not None:                                 # every bar after the open moved far away
        frame = pd.read_parquet(snap / "EURUSD_M1.parquet")
        later = pd.to_datetime(frame["time"], utc=True) >= alter_after
        for k in ("open", "high", "low", "close"):
            frame.loc[later, k] = frame.loc[later, k] + 0.05
        out = snap.parent / "altered"
        out.mkdir(exist_ok=True)
        frame.to_parquet(out / "EURUSD_M1.parquet", index=False)
        snap = out
    cfg = StrategyConfig(fvg_zone="gap")
    source = SnapshotSource(snap)
    data = load_instrument(source, "EURUSD", datetime(2026, 9, 25, tzinfo=UTC), datetime(2026, 10, 3, tzinfo=UTC), cfg,
                           None, venue="binance", max_gap_minutes=60)
    m1 = source._frame("EURUSD")[["time", "open", "high", "low", "close"]]
    readers = {"H1": FractalPOI(m1, "H1", FractalSettings(), "EURUSD"),
               "H4": FractalPOI(m1, "H4", FractalSettings(), "EURUSD")}
    return facts_at(data, cfg, OPEN, readers)


def test_the_facts_are_blind_and_rescaled(setup):  # noqa: F811
    root, snap = setup
    facts = _facts(snap)
    text = facts.text
    assert "EURUSD" not in text and "EUR" not in text
    assert not re.search(r"20\d\d|\d{4}-\d{2}-\d{2}", text)
    assert not re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|"
                         r"December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", text)
    assert not re.search(r"\b1\.\d{3,}", text)                 # no real EURUSD price
    assert "Thursday's trading day" in text and "1000.0" in text
    for section in ("CANDLES", "PHASE OF DELIVERY", "THE ENGINE'S READ", "THE FRACTAL + POI INDICATOR"):
        assert section in text
    assert messages_for(facts)[1]["content"] == text and "JSON" in messages_for(facts)[0]["content"]


def test_nothing_after_the_open_changes_the_facts(setup):  # noqa: F811
    root, snap = setup
    assert _facts(snap).text == _facts(snap, alter_after=pd.Timestamp(OPEN)).text


RS = Rescale(open=100.0, atr=2.0)


def test_the_answer_is_read_in_its_fixed_form_and_mapped_back():
    text = 'Thinking first... {"bias": "x"} then\n```json\n{"bias": "bullish", "draw": 1150, "invalidation": 940, ' \
           '"confidence": "medium", "reason": "the draw is the old high"}\n```'
    t = parse_answer(text, RS)
    assert (t.bias, t.draw, t.invalidation, t.confidence) == ("BULLISH", 103.0, 98.8, "medium")
    assert t.as_read() == {"bias": "BULLISH", "draw": 103.0, "invalidation": 98.8}
    neutral = parse_answer('{"bias": "neutral", "draw": null, "invalidation": null, "confidence": "low", '
                           '"reason": "conflict"}', RS)
    assert neutral.bias == "NO_THESIS" and neutral.draw is None


@pytest.mark.parametrize("text, why", [
    ("no json here", "no JSON"),
    ('{"bias": "up", "draw": 1100, "invalidation": 900}', "bias"),
    ('{"bias": "bullish", "draw": 950, "invalidation": 900}', "above 1000"),
    ('{"bias": "bearish", "draw": 900, "invalidation": 990}', "below 1000"),
    ('{"bias": "bullish", "draw": "high", "invalidation": 900}', "numeric"),
    ('{"bias": "bullish", "draw": 1100, "invalidation": 900, "confidence": "sure"}', "confidence"),
])
def test_an_answer_outside_the_fixed_form_is_refused_with_the_reason(text, why):
    with pytest.raises(ValueError, match=why):
        parse_answer(text, RS)
