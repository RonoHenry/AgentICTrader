"""
Tests for AlgoMindDIS's evidence, synthesis, timeframe hierarchy and narrative (algomind-dis Requirements 9-11;
task 403).
"""
from __future__ import annotations

import pytest

from algomind_dis.evidence import classify_lower, gather, htf_scores, scores
from algomind_dis.narrative import narrative, render
from algomind_dis.observe import observe
from algomind_dis.records import Evidence, make_id
from algomind_dis.settings import V1
from tests.test_algomind_dis_objectives import OHLC, ohlc


def item(category, direction, tf, source, sig=1.0, scope=""):
    return Evidence(make_id(category, direction, tf, source, sig), category, direction, tf, source, sig, 0, True, (),
                    f"{category} {direction} {tf}", scope)


def test_one_source_counts_once_and_each_timeframe_once_per_side():
    base = [item("STRUCTURE", "BULLISH", "W1", "e1"), item("STRUCTURE", "BULLISH", "D1", "e2", 0.5)]
    s0 = scores(base, ("MN1", "W1", "D1"))
    assert s0.by_category["STRUCTURE"][0] == pytest.approx((0.8 * 1 + 0.6 * 0.5) / 2.4)
    dup = base + [item("STRUCTURE", "BULLISH", "MN1", "e1", 0.9)]          # the same candles again, on MN1
    assert scores(dup, ("MN1", "W1", "D1")) == s0
    more = base + [item("STRUCTURE", "BULLISH", "D1", "e3", 0.4)]          # a weaker D1 item: D1 counts once
    assert scores(more, ("MN1", "W1", "D1")) == s0
    every = [item(c, "BULLISH", tf, f"{c}{tf}") for c in V1.category_weights for tf in ("MN1", "W1", "D1")]
    full = scores(every, ("MN1", "W1", "D1"))
    assert full.bullish == pytest.approx(1.0) and full.bearish == 0.0
    assert scores(every + [item("TEMPORAL", "NEUTRAL", "D1", "t")], ("MN1", "W1", "D1")) == full


def test_the_bullish_fvg_story_scores_on_its_categories():
    c = ohlc(OHLC)                         # D1 only: a BOS up, a sweep long consumed, discount, the FVG, delivery
    obs = observe("TEST", {"D1": c})
    items = gather(obs)
    s = scores(items, ("D1",))
    # candle 9 is one movement: its BOS (structure) and its CISD (delivery) count once, as structure (§9.3).
    # The bullish FVG's retest (candle 12) is a later event and counts 1.0 (displaced, after the sweep); the
    # bearish FVG 18.4-19.0 of candles 0-2 is valid, in premium and retested by candle 11: 0.5 against
    assert s.by_category == {"STRUCTURE": (1.0, 0.0), "LIQUIDITY": (0.0, 0.0), "PREMIUM_DISCOUNT": (0.5, 0.0),
                             "PD_ARRAY": (1.0, 0.5), "DELIVERY": (0.0, 0.0)}
    assert s.bullish == pytest.approx(0.25 + 0.20 * 0.5 + 0.15) and s.bearish == pytest.approx(0.15 * 0.5)
    assert htf_scores(items, ("D1",)) == pytest.approx((0.5, 0.0))        # structure, and no external sweep


def test_a_swept_external_pool_that_closed_back_is_liquidity_evidence():
    rows = OHLC[:9] + [(15.9, 16.1, 15.6, 15.95)]                          # the sweep (candle 8) is now recent
    obs = observe("TEST", {"D1": ohlc(rows)})
    liq = [e for e in gather(obs) if e.category == "LIQUIDITY"]
    assert liq and all(e.direction == "BULLISH" for e in liq)            # sell-side taken and closed back
    low = next(e for e in liq if "15" in e.text)                         # the swing low of candle 4, inside the
    assert low.significance == pytest.approx(0.6) and low.scope == ""    # range: internal, not external


def test_lower_timeframe_evidence_is_classified_never_counted():
    held = dict(side="BULLISH", protected=100.0, d1_range=(100.0, 120.0))
    assert classify_lower("BEARISH", price=110.0, d1_mss_against=False, d1_close=111.0, **held) == "RETRACEMENT"
    assert classify_lower("BEARISH", price=99.0, d1_mss_against=False, d1_close=101.0, **held) == "INTERNAL_DELIVERY"
    assert classify_lower("BEARISH", price=105.0, d1_mss_against=True, d1_close=104.0, **held) == "DEVELOPING_REVERSAL"
    assert classify_lower("BEARISH", price=99.0, d1_mss_against=False, d1_close=99.5, **held) == "DEVELOPING_REVERSAL"
    assert classify_lower("BULLISH", price=110.0, d1_mss_against=False, d1_close=111.0, **held) == "WITH_THE_SIDE"
    four = [item("STRUCTURE", "BEARISH", "H1", f"h{k}") for k in range(4)]
    assert scores(four, ("MN1", "W1", "D1")).bearish == 0.0                # lower frames aren't scored


def test_the_narrative_is_its_record_rendered():
    obs = observe("TEST", {"D1": ohlc(OHLC)})
    items = gather(obs)
    n = narrative(obs, items, scores(items, ("D1",)), "BULLISH", protected=14.6, status="ACTIVE")
    assert n.hypothesis == "BULLISH" and n.delivery_state == "BULLISH_DELIVERY"
    assert n.supporting and [e.category for e in n.conflicting] == ["PD_ARRAY"]
    assert n.invalidation == ("a D1 close under 14.6",)
    assert render(n) == n.text
    assert "BULLISH" in n.text and "FVG" in n.text and f"{n.confidence:.2f}" in n.text
    assert n.confidence == pytest.approx(0.5 - 0.075) and "RANGE_HIGH 20.5" in n.primary_objective
