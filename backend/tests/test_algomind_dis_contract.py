"""
Tests for AlgoMindDIS's contract, setup qualification and thesis entry (algomind-dis Requirement 13; task 405).
"""
from __future__ import annotations

import json

from algomind_dis import CONTRACT, VERSION
from algomind_dis.contract import Setup, output, qualify, thesis_entry
from algomind_dis.evidence import SCORED, gather, scores
from algomind_dis.observe import observe
from algomind_dis.records import DirectionalBiasOutput, from_json, to_json
from algomind_dis.state import Held
from tests.test_algomind_dis_objectives import OHLC, ohlc

HELD = Held("BULLISH", "BULLISH", 10, 20.5, 14.6, 3)


def bias(held=HELD):
    obs = observe("TEST", {"D1": ohlc(OHLC)})
    items = gather(obs)
    return output(obs, held, items, scores(items, SCORED))


def test_the_contract_is_versioned_and_round_trips():
    b = bias()
    assert (b.version, b.contract_version, b.primary_direction, b.state) == (VERSION, CONTRACT, "BULLISH", "ACTIVE")
    assert b.invalidation_conditions == ("a D1 close under 14.6",) and b.delivery_state == "BULLISH_DELIVERY"
    assert b.liquidity_objectives[0].source == "RANGE_HIGH" and b.premium_discount_context["D1"].zone == "DISCOUNT"
    assert from_json(DirectionalBiasOutput, json.loads(json.dumps(to_json(b)))) == b
    assert bias(Held(ended=("invalidated", 12))).state == "INVALIDATED"
    assert bias(Held(ended=("expired", 12))).state == "EXPIRED"
    t = bias(Held("TRANSITIONAL", "BULLISH", 10, 20.5, 14.6, 3, "BEARISH"))
    assert (t.primary_direction, t.state) == ("BULLISH", "TRANSITIONAL")
    n = bias(Held("NEUTRAL", ended=("delivered", 12)))
    assert (n.primary_direction, n.state, n.supporting_evidence) == ("NEUTRAL", "ACTIVE", ())


def test_qualify_gives_the_four_outcomes_with_reasons():
    b = bias()
    assert qualify(Setup("BULLISH", 20), b).outcome == "ALIGNED"
    q = qualify(Setup("BEARISH", 20, target=17.0, at_htf_array=True, after_sweep=True), b)
    assert q.outcome == "COUNTERTREND_JUSTIFIED" and "inside the D1 range" in q.reason
    q = qualify(Setup("BEARISH", 20, target=17.0), b)
    assert q.outcome == "INSUFFICIENT_CONTEXT" and "an opposing HTF array" in q.reason and "a sweep" in q.reason
    assert qualify(Setup("BEARISH", 20, target=10.0, at_htf_array=True, after_sweep=True), b).outcome == \
        "INSUFFICIENT_CONTEXT"                                             # its target is outside the D1 range
    assert qualify(Setup("BULLISH", 20), bias(Held())).outcome == "INSUFFICIENT_CONTEXT"
    assert qualify(Setup("BULLISH", 20), bias(Held(ended=("invalidated", 12)))).outcome == "INVALIDATED_CONTEXT"


def test_an_active_side_is_a_thesis_entry_the_engine_reads(tmp_path):
    from agent.order_intent import theses
    e = thesis_entry(HELD)
    assert e == {"side": "BULLISH", "draw": 20.5, "protected": 14.6, "since": "1970-01-01T00:00:00.000000010+00:00",
                 "source": f"algomind_dis {VERSION}"}
    assert thesis_entry(Held()) is None and thesis_entry(Held("TRANSITIONAL", "BULLISH", 1, 2.0, 1.0)) is None
    path = tmp_path / "dis_v1_theses.json"
    path.write_text(json.dumps({"GBPUSD": {"2026-11-04": e}}), encoding="utf-8")
    assert theses(str(path))["GBPUSD"]["2026-11-04"]["side"] == "BULLISH"
