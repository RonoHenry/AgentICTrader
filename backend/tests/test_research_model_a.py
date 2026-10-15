"""
Tests for algo_research/model_a.py — the Model A record (context-engine Requirement 16, update 2026-10-15).

Task 312 (.kiro/specs/context-engine/tasks.md). The funnel, rates with day-cluster intervals, the premise race
and its coin flip, breakdowns, and the baselines read on the hand-built day of test_context_model_a.
Validates: Requirements 16.1-16.3 (.kiro/specs/context-engine/requirements.md)
"""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algo_research.model_a import (ARMS, breakdown, funnel, mean, premise, premise_edge, rate, read_instances,
                                   record, summarise, trading_date)
from liquidity_engine.context.model_a import Variant

_spec = importlib.util.spec_from_file_location("ma_day", Path(__file__).with_name("test_context_model_a.py"))
DAYMOD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DAYMOD)


def the_day():
    return DAYMOD.m1(DAYMOD.day())


def fake(n=40, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n):
        states = {"FRAMED": k, "ARMED": k}
        end = "NO_MANIPULATION"
        if k % 2 == 0:
            states["MANIPULATED"] = k
            end = "NO_REJECTION"
            if k % 4 == 0:
                states["REJECTED"] = k
                end = "EXPIRED"
        rows.append({"states": states, "end": end, "trading_date": date(2025, 1, 2 + k % 10),
                     "premise": bool(rng.random() < 0.6) if "REJECTED" in states else None,
                     "premise_coin": 0.5 if "REJECTED" in states else np.nan, "c1_taken_in_c2": None,
                     "hits": {}, "r_tp1": None, "r_sd2": None, "time_sync": bool(k % 3 == 0), "inducement": None,
                     "poi_kind": "OB", "side": "SHORT"})
    return pd.DataFrame(rows)


def test_funnel_counts_states_and_invalidations():
    f = funnel(fake())
    assert f["FRAMED"] == 40 and f["MANIPULATED"] == 20 and f["REJECTED"] == 10
    assert f["end:NO_MANIPULATION"] == 20 and f["end:NO_REJECTION"] == 10 and f["end:EXPIRED"] == 10


def test_outcome_rates_with_day_cluster_intervals():
    df = fake()
    manip = df["states"].map(lambda s: "MANIPULATED" in s)
    rej = df["states"].map(lambda s: "REJECTED" in s)
    r = rate(df, manip, rej)
    assert r["n"] == 20 and r["k"] == 10 and r["rate"] == pytest.approx(0.5)
    assert 0 <= r["lo"] <= r["rate"] <= r["hi"] <= 1
    m = mean(df.assign(x=np.arange(40, dtype=float)), "x")
    assert m["n"] == 40 and m["lo"] <= m["mean"] <= m["hi"]
    edge = premise_edge(df)
    assert edge["n"] == 10 and edge["coin"] == pytest.approx(0.5) and edge["lo"] <= edge["edge"] <= edge["hi"]


def test_premise_race_and_its_coin():
    t, o, h, l, c = the_day()
    x = DAYMOD.the_one(DAYMOD.read(DAYMOD.day()))
    df = pd.DataFrame([{**x, "trading_date": trading_date(x["states"]["FRAMED"])}])
    got = premise(df, (t, o, h, l, c)).iloc[0]
    assert got["premise"] == True                                          # noqa: E712  C1's low (108.38) came first
    close = 107.6                                                          # C2's close
    d_t, d_s = close - 108.38, 110.22 - close
    assert got["premise_coin"] == pytest.approx(abs(d_s) / (abs(d_t) + abs(d_s)))
    assert got["c1_taken_in_c2"] == True                                   # noqa: E712  C2 itself traded under 108.38
    stopped = DAYMOD.the_one(DAYMOD.read(DAYMOD.day(c3=[(735, 110.5)], after=[(775, 110.6), (790, 110.0)],
                                                  c2=[(728, 110.2), (729, 109.4), (730, 108.6)])))
    if "REJECTED" in stopped["states"]:
        df2 = pd.DataFrame([{**stopped, "trading_date": trading_date(stopped["states"]["FRAMED"])}])
        t2 = DAYMOD.m1(DAYMOD.day(c3=[(735, 110.5)], after=[(775, 110.6), (790, 110.0)], c2=[(728, 110.2), (729, 109.4), (730, 108.6)]))
        assert premise(df2, t2).iloc[0]["premise"] == False                # noqa: E712  C2's high went first


def test_breakdowns_by_time_inducement_depth_and_variant():
    rows = breakdown(fake(), "time_sync")
    assert [v for v, _ in rows] == ["False", "True"] and sum(d["premise"]["n"] for _, d in rows) == 10


def test_baselines_share_the_c_and_e_rules():
    t, o, h, l, c = the_day()
    by = {arm.key: read_instances((t, o, h, l, c), DAYMOD.SMALL, arm.variant, int(t[0]), int(t[-1]) + 60, "XAUUSD")
          for arm in ARMS}
    model = by["model"][by["model"]["c1_open"] == DAYMOD.wall(720)].iloc[0]
    crt = by["crt"][by["crt"]["c1_open"] == DAYMOD.wall(720)].iloc[0]
    after = lambda states: {k: v for k, v in states.items() if k not in ("FRAMED", "ARMED", "MANIPULATED")}  # noqa: E731
    assert after(crt["states"]) == after(model["states"])                  # the same C and E rules after C2's run
    assert crt["states"]["MANIPULATED"] < model["states"]["MANIPULATED"]   # CRT's "POI" is C1's high itself
    assert crt["poi_kind"] == "C1_HIGH" and len(by["crt"]) > len(by["model"])  # no context: every C close starts one


def test_random_poi_is_seeded():
    t, o, h, l, c = DAYMOD.walk(5)
    run = lambda seed: read_instances((t, o, h, l, c), DAYMOD.SMALL, Variant(poi_mode="RANDOM_POI", seed=seed),  # noqa: E731
                                      int(t[0]), int(t[-1]), "X")
    a, b, other = run(1), run(1), run(2)
    assert a[["c1_open", "end", "poi_near"]].equals(b[["c1_open", "end", "poi_near"]])
    assert not a[["c1_open", "poi_near"]].equals(other[["c1_open", "poi_near"]])


def test_the_record_renders():
    t, o, h, l, c = the_day()
    text, instances = record({"XAUUSD": (t, o, h, l, c)}, [DAYMOD.SMALL], int(t[0]), int(t[-1]) + 60,
                             meta={"slice": "the hand-built day"}, progress=lambda s: None)
    assert "## XAUUSD" in text and "### small: F H1, C M5, E M1" in text and "**Premise**" in text
    arms = set(instances["arm"])                       # the time-gated arms find nothing at noon on this day
    assert {"model", "crt", "model_vol"} <= arms <= {a.key for a in ARMS} and "premise" in instances
    assert "+ time + volatility" in text and "C2's phase of the day" in text
    assert summarise(instances[instances["arm"] == "model"])["funnel"]["ENTERED"] >= 1


def test_the_record_renders_again_from_saved_instances(tmp_path):
    from algo_research.model_a import load_instances, render
    t, o, h, l, c = the_day()
    text, instances = record({"XAUUSD": (t, o, h, l, c)}, [DAYMOD.SMALL], int(t[0]), int(t[-1]) + 60, progress=lambda s: None)
    path = tmp_path / "instances.jsonl"
    instances.to_json(path, orient="records", lines=True, date_format="iso")
    again = render(load_instances(path), [DAYMOD.SMALL])
    assert again == text and "## Summary: the premise against its coin flip" in again


# ── the thesis (Requirement 19) ────────────────────────────────────────────

def walk_days(seed=4, days=45):
    return DAYMOD.walk(seed, minutes=days * 1440)


def test_oracle_and_prev_day_theses():
    from algo_research.model_a import daily_theses, day_directions
    m1 = walk_days()
    days = day_directions(m1)
    assert daily_theses(m1, "ORACLE") == days
    prev = daily_theses(m1, "PREV_DAY")
    keys = sorted(days)
    assert all(prev[d] == days[p] for p, d in zip(keys, keys[1:])) and keys[0] not in prev
    with pytest.raises(ValueError):
        daily_theses(m1, "TOMORROW")


def test_profile_thesis_reads_only_the_past():
    from algo_research.model_a import daily_theses
    t, o, h, l, c = walk_days(seed=9)
    full = daily_theses((t, o, h, l, c), "PROFILE")
    assert full and set(full.values()) <= {-1, 0, 1}
    day = sorted(full)[len(full) // 2]
    cut = int(np.searchsorted(t, day * 86400 + 61200 + 3600))           # an hour into that day
    part = daily_theses((t[:cut], o[:cut], h[:cut], l[:cut], c[:cut]), "PROFILE")
    assert {d: v for d, v in full.items() if d <= day} == {d: v for d, v in part.items() if d <= day}


def test_thesis_accuracy_against_the_day():
    from algo_research.model_a import day_directions, thesis_accuracy
    m1 = walk_days()
    days = day_directions(m1)
    right = thesis_accuracy(m1, days, int(m1[0][0]), int(m1[0][-1]))
    wrong = thesis_accuracy(m1, {d: -v for d, v in days.items()}, int(m1[0][0]), int(m1[0][-1]))
    assert right["right"] == 1.0 and wrong["right"] == 0.0 and right["named"] == wrong["named"] > 30


def test_the_record_scores_each_thesis():
    from algo_research.model_a import THESIS_ARMS
    m1 = walk_days(days=40)
    text, instances = record({"X": m1}, [DAYMOD.SMALL], int(m1[0][0]) + 30 * 86400, int(m1[0][-1]),
                             arms=[a for a in THESIS_ARMS if a.key in ("model_vt_oracle", "crt_vt_profile")],
                             progress=lambda s: None)
    assert "## The theses on their own" in text and "| X | ORACLE |" in text and "| X | PROFILE |" in text
    assert "100%" in text.split("| X | ORACLE |")[1].split("\n")[0]          # the oracle names every day right
