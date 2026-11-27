"""
Tests for AlgoMindDIS's records, settings and frames (algomind-dis Requirement 2, 8.1; task 399).
"""
from __future__ import annotations

import dataclasses
import json

import numpy as np
import pandas as pd
import pytest

from algomind_dis import CONTRACT, VERSION
from algomind_dis.frames import Frames, from_daily
from algomind_dis.records import (ArrayContext, DealingRange, DeliveryState, DirectionalBiasOutput, Evidence,
                                  LiquidityObjective, MarketNarrative, PricePosition, StructureEvent,
                                  TimeframeContext, Transition, from_json, make_id, to_json)
from algomind_dis.settings import V1, Settings

T0 = int(pd.Timestamp("2026-10-05", tz="UTC").value)


def _records():
    rng = DealingRange(make_id("GBPUSD", "D1", "SWING", T0), "GBPUSD", "D1", "SWING", 1.35, 1.30, "swings at 3 and 9",
                       T0, True, None, "a D1 close outside 1.30-1.35")
    pos = PricePosition(rng.id, "D1", 0.2, "DEEP_DISCOUNT", rng.equilibrium, 1.31)
    obj = LiquidityObjective(make_id("GBPUSD", "W1", "SWING_HIGH", 1.36), "GBPUSD", "W1", 1.36, "EXTERNAL",
                             "SWING_HIGH", "BULLISH", rng.id, "IDENTIFIED", 0.8, T0, None, False)
    arr = ArrayContext(make_id("GBPUSD", "D1", "FVG", T0, 1.31), "GBPUSD", "D1", "FVG", "BULLISH", 1.305, 1.312, T0,
                       "INSIDE", rng.id, "DISCOUNT", True, False, True, True, True, None)
    ev = StructureEvent(make_id("GBPUSD", "D1", "MSS", T0), "D1", "MSS", "BULLISH", 1.325, T0, T0 - 86_400 * 10**9)
    dl = DeliveryState("D1", "BULLISH_DELIVERY", T0, ("SSL swept 1.300", "CISD above 1.318"))
    tfc = TimeframeContext("D1", "BULLISH", 1.31, (rng,), (pos,), (obj,), (arr,), dl, (ev,))
    e1 = Evidence(make_id("ev", 1), "STRUCTURE", "BULLISH", "D1", ev.id, 0.6, T0, True, (), "D1 MSS up")
    nar = MarketNarrative(make_id("nar", 1), "GBPUSD", T0, "D1", "BULLISH", "BULLISH_DELIVERY", obj.id, (e1,), (),
                          ("a D1 close under 1.30",), 0.42, "ACTIVE", "GBPUSD: bullish.")
    tr = Transition("GBPUSD", T0, "UNDETERMINED", "BULLISH", "established: 0.61 vs 0.19", "D1", nar.id)
    out = DirectionalBiasOutput("GBPUSD", make_id("bias", 1), VERSION, CONTRACT, "BULLISH", "ACTIVE", 0.42,
                                "2026-10-05T00:00:00+00:00", {"D1": tfc}, rng, {"D1": pos}, (obj,), (e1,), (),
                                "BULLISH_DELIVERY", ("a D1 close under 1.30",), None, nar.id, "OK")
    return [rng, pos, obj, arr, ev, dl, tfc, e1, nar, tr, out]


def test_every_record_round_trips_through_json():
    for r in _records():
        text = json.dumps(to_json(r))
        assert from_json(type(r), json.loads(text)) == r, type(r).__name__


def test_ids_follow_the_content():
    assert make_id("GBPUSD", "D1", 1.3) == make_id("GBPUSD", "D1", 1.3)
    assert make_id("GBPUSD", "D1", 1.3) != make_id("GBPUSD", "D1", 1.31)
    assert make_id("GBPUSD", "D1", 1.3) != make_id("EURUSD", "D1", 1.3)
    assert len(make_id("x")) == 16


def test_v1_settings_are_the_registered_ones_and_frozen():
    assert V1.version == VERSION == "v1" and CONTRACT == "1.0.0"
    assert V1.category_weights == {"STRUCTURE": 0.25, "LIQUIDITY": 0.25, "PREMIUM_DISCOUNT": 0.20, "PD_ARRAY": 0.15,
                                   "DELIVERY": 0.15}
    assert abs(sum(V1.category_weights.values()) - 1) < 1e-12
    assert V1.timeframe_weights["MN1"] == 1.0 and V1.timeframe_weights["W1"] == 0.8 and V1.timeframe_weights["D1"] == 0.6
    assert (V1.deep_discount, V1.discount, V1.premium, V1.deep_premium) == (0.25, 0.45, 0.55, 0.75)
    assert V1.type_weights == {"EXTERNAL": 1.0, "TEMPORAL": 0.8, "INTERNAL": 0.6} and V1.equal_bonus == 0.25
    assert (V1.establish_score, V1.establish_lead, V1.challenge_lead) == (0.5, 0.2, 0.3)
    assert (V1.resolve_closes, V1.validity_closes) == (3, 20)
    assert (V1.displacement_body, V1.body_window, V1.sweep_window, V1.adr_days) == (1.5, 20, 3, 20)
    with pytest.raises(dataclasses.FrozenInstanceError):
        V1.version = "v2"
    assert Settings() == V1


def _days(start: str, end: str) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    x = np.arange(len(dates), dtype=float)
    return pd.DataFrame({"date": dates, "open": 100 + x, "high": 101 + x, "low": 99 + x, "close": 100.5 + x})


def test_the_frames_hold_only_candles_closed_by_t():
    f = from_daily("TEST", _days("2026-08-31", "2026-10-21"))      # Mon 31 Aug to Wed 21 Oct, weekends included
    assert isinstance(f, Frames) and set(f.full) == {"MN1", "W1", "D1"}
    d1 = f.full["D1"]
    assert len(d1) == 38                                           # weekdays only: the weekend merged into Monday
    assert pd.Timestamp(int(f.full["W1"].t[-1]), tz="UTC").date().isoformat() == "2026-10-12"   # 19 Oct: forming
    assert [pd.Timestamp(int(t), tz="UTC").month for t in f.full["MN1"].t] == [8, 9]            # October: forming
    t = int(pd.Timestamp("2026-09-16 00:00", tz="UTC").value)      # Wednesday 16 Sep, 00:00: Tuesday has closed
    at = f.at(t)
    assert pd.Timestamp(int(at["D1"].t[-1]), tz="UTC").date().isoformat() == "2026-09-15"
    assert pd.Timestamp(int(at["W1"].t[-1]), tz="UTC").date().isoformat() == "2026-09-07"
    assert [pd.Timestamp(int(x), tz="UTC").month for x in at["MN1"].t] == [8]
    assert all((at[tf].end <= t).all() for tf in at)
    september = f.full["MN1"]
    assert september.h[-1] == d1.h[(d1.t >= pd.Timestamp("2026-09-01", tz="UTC").value)
                                    & (d1.t < pd.Timestamp("2026-10-01", tz="UTC").value)].max()
    assert f.closes("D1")[0] == d1.end[0]
