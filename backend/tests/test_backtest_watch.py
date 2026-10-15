"""
Tests for algo_backtester/watch.py — watching the engine work (algo-backtester update 2026-10-14d).

Task 305 (.kiro/specs/algo-backtester/tasks.md). The task 186 MetaQuotes fixture week, written as a one-file
snapshot, a small strategy window and a scratch study: a session runs the backtest over one trading day and
serves the engine's state at each close, the journal and the bars as of any time.
Validates: Requirements 15.1-15.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from algo_backtester.watch import SnapshotSource, WatchApp, WatchSession, make_watch_server, ranked_candidates, wall
from liquidity_engine.grader.sequence import SetupSequenceDetector
from liquidity_engine.models import BiasDirection, PDArrayType
from liquidity_engine.models import Timeframe as TF
from tests.test_backtest_signals import FixtureSource

UTC = timezone.utc
DAY = date(2026, 9, 30)
CONFIG = """
[run]
profile = "exness-standard"
instruments = ["EURUSD"]
start = 2026-09-29
end = 2026-10-02
study = "watch-test"

[strategy]
entry_tf = "M15"
context_tfs = ["H4"]
candle_counts = { M15 = 60, H4 = 30, D1 = 20, W1 = 8 }
"""


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    root = tmp_path_factory.mktemp("watch")
    bars = FixtureSource("EURUSD").bars("EURUSD", TF.M1, datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 10, tzinfo=UTC))
    snap = root / "snapshot"
    snap.mkdir()
    pd.DataFrame({"time": [b.timestamp for b in bars], "open": [b.open for b in bars], "high": [b.high for b in bars],
                  "low": [b.low for b in bars], "close": [b.close for b in bars], "volume": [b.volume for b in bars],
                  "spread": [b.spread for b in bars]}).to_parquet(snap / "EURUSD_M1.parquet", index=False)
    (root / "base.toml").write_text(CONFIG, encoding="utf-8")
    study = root / "config" / "backtests" / "studies" / "watch-test.toml"
    study.parent.mkdir(parents=True)
    study.write_text("holdout_start = 2099-01-01\ncreated_from_data_end = 2099-01-01\n", encoding="utf-8")
    return root, snap


def test_snapshot_source_serves_m1_only(setup):
    _, snap = setup
    src = SnapshotSource(snap)
    m1 = src.bars("EURUSD", TF.M1, datetime(2026, 9, 30, tzinfo=UTC), datetime(2026, 9, 30, 1, tzinfo=UTC))
    assert m1 and all(b.timeframe == TF.M1 for b in m1) and src.bars("EURUSD", TF.H1, datetime(2026, 9, 1, tzinfo=UTC),
                                                                       datetime(2026, 10, 1, tzinfo=UTC)) == []
    assert src.last_time("EURUSD", TF.M1) is not None and src.last_time("GBPUSD", TF.M1) is None


@pytest.fixture(scope="module")
def session(setup):
    root, snap = setup
    s = WatchSession(root / "base.toml", None, "EURUSD", DAY, 1, snap, studies_root=root)
    s.prepare()
    assert s.state == "ready", s.message
    return s


def test_a_session_replays_the_engine_at_each_close(session):
    status = session.status()
    assert status["closes"] >= 80 and status["start"] == wall(pd.Timestamp("2026-09-29 17:00", tz="America/New_York"))
    assert {r["decision"] for r in session.journal} and all(r["t"] is not None for r in session.journal)
    noon = wall(pd.Timestamp("2026-09-30 12:07", tz="America/New_York"))
    state = session.state_at(noon)
    assert state["t"] <= noon and noon - state["t"] < 900
    assert {"arrays", "pools", "profile", "sequence", "grade", "bias", "decision"} <= set(state)
    assert state["decision"] is None or state["decision"]["t"] == state["t"]
    assert all(p["known"] <= state["t"] for p in state["pools"])
    assert all(a["formed"] <= state["t"] for a in state["arrays"])
    assert session.state_at(status["start"] - 2 * 86400) is None          # before the run window


def test_candidates_include_the_choice_and_leave_detect_unchanged():
    """Requirement 16.2 on the sequence detector's own fixture: every array it looked at, its choice first."""
    from tests.test_liquidity_sequence import BULLISH_FVG, BULLISH_ROWS, array, m15, series
    ob = array("ob", BiasDirection.BULLISH, 99.6, 100.4, 7, PDArrayType.OB, strength=0.7)
    old = array("old", BiasDirection.BULLISH, 100.3, 100.5, 3)               # formed before the raid: no sequence
    candles_by_tf = {TF.M15: series(BULLISH_ROWS)}
    arrays = [BULLISH_FVG, old, ob]
    seen = ranked_candidates(candles_by_tf, arrays, None)
    assert seen[0].sequence == SetupSequenceDetector().detect(candles_by_tf, arrays)
    assert [c.array.array_id for c in seen] == ["ob", "fvg", "old"]
    assert seen[0].key > seen[1].key and seen[2].sequence is None and seen[2].key is None
    assert seen[1].sequence.raid.raided_at == m15(7)
    assert ranked_candidates(candles_by_tf, [old], None)[0].sequence is None
    assert SetupSequenceDetector().detect(candles_by_tf, [old]) is None


def test_a_session_lists_the_candidates_at_each_close(session):
    """Requirement 16.2: every array the sequence detector ranked, the engine's choice marked first."""
    with_candidates = [s for s in session.states.values() if s.get("candidates", {}).get("ranked")]
    assert with_candidates, "no close had a candidate"
    for state in with_candidates:
        ranked = state["candidates"]["ranked"]
        assert [c["rank"] for c in ranked] == list(range(1, len(ranked) + 1))
        assert len({c["id"] for c in ranked}) == len(ranked)                   # each array once
        assert all(c["raid"]["at"] <= state["t"] and c["formed"] <= state["t"] for c in ranked)
        chosen = [c for c in ranked if c["chosen"]]
        if state["sequence"] is not None:
            assert len(chosen) == 1 and chosen[0]["rank"] == 1
            assert chosen[0]["raid"]["at"] == state["sequence"]["raided"]
    for state in session.states.values():                                # the engine's answer and the list agree
        if "candidates" in state and state["sequence"] is None:
            assert not state["candidates"]["ranked"]
    assert all(set(s["candidates"]) == {"ranked", "without"} for s in session.states.values() if "candidates" in s)


def test_a_session_keeps_each_trades_path(session):
    """Requirement 16.1: the backtest never moves a stop or takes a partial, so each filled trade shows its path:
    the best and worst point it reached before the exit, in R, at their times."""
    filled = [r for r in session.journal if r["filled_at"] is not None]
    for r in filled:
        path = r["path"]
        end = r["closed_at"] if r["closed_at"] is not None else wall(session.end)
        assert r["filled_at"] <= path["best_at"] <= end and r["filled_at"] <= path["worst_at"] <= end
        assert path["best_r"] >= path["worst_r"] and path["worst_r"] <= 0 <= path["best_r"]
    assert all(r.get("path") is None for r in session.journal if r["filled_at"] is None)


def test_picks_are_appended_with_the_engine_choice(session, tmp_path):
    """Requirement 16.3: the trader's pick at a close, beside the engine's, one line per pick, kept locally."""
    state = next(s for s in session.states.values() if s.get("candidates", {}).get("ranked"))
    first = state["candidates"]["ranked"][0]
    out = tmp_path / "picks.jsonl"
    session.save_pick({"t": state["t"], "pick": first["id"], "note": "the obvious one"}, out)
    session.save_pick({"t": state["t"], "pick": "none"}, out)
    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert [x["pick"] for x in lines] == [first["id"], "none"]
    assert lines[0]["engine"] == (next((c["id"] for c in state["candidates"]["ranked"] if c["chosen"]), None))
    assert lines[0]["instrument"] == "EURUSD" and lines[0]["note"] == "the obvious one" and lines[0]["t"] == state["t"]
    assert lines[0]["picked"]["tf"] == first["tf"]
    for bad in ({"t": state["t"], "pick": "no-such-array"}, {"t": state["t"] + 1, "pick": "none"}, {"pick": "none"}):
        with pytest.raises((ValueError, KeyError)):
            session.save_pick(bad, out)
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2


@pytest.fixture(scope="module")
def week(setup):
    """The fixture week's last three trading days: Model A needs a few days of context."""
    root, snap = setup
    s = WatchSession(root / "base.toml", None, "EURUSD", DAY, 3, snap, studies_root=root)
    s.prepare()
    assert s.state == "ready", s.message
    return s


def test_watch_session_keeps_model_a_instances(week):
    """Context-engine Requirement 17: Model A on the chart, nothing from after the clock."""
    session = week
    assert set(session.model_a) == {"model_d1", "model_h4"}
    every = [x for xs in session.model_a.values() for x in xs]
    assert every and all(x["states"]["FRAMED"] >= wall(session.start) for x in every)
    for name, xs in session.model_a.items():
        for x in xs:
            if "MANIPULATED" not in x["states"]:
                continue
            t = x["states"]["MANIPULATED"]
            shown = [y for y in session.model_a_at(name, t) if y["c1_open"] == x["c1_open"] and y["side"] == x["side"]]
            assert shown, (name, x["c1_open"])
            y = shown[0]
            assert all(e[1] <= t for e in y["events"]) and "c2_extreme" not in y and "entry" not in y
            if "ENTERED" in x["states"]:
                at = x["states"]["ENTERED"]
                y = [z for z in session.model_a_at(name, at) if z["c1_open"] == x["c1_open"] and z["side"] == x["side"]][0]
                assert y["entry"] == x["entry"] and y["fill"] == x["fill"] and y["order_at"] <= at
    with pytest.raises(ValueError):
        session.model_a_at("model_w1", wall(session.start))


def test_bars_never_pass_the_time_asked(session):
    t = wall(pd.Timestamp("2026-09-30 10:41", tz="America/New_York"))
    for tf in ("M1", "M15", "H1", "H4"):
        bars = session.bars_until(tf, t, None)
        assert bars and max(b["time"] for b in bars) < t


def test_the_watch_server_round_trip(setup):
    root, snap = setup
    app = WatchApp(root / "base.toml", snap, (date(2026, 9, 28), date(2026, 10, 3)), picks=root / "picks.jsonl")
    server = make_watch_server(app, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    get = lambda path: json.loads(urllib.request.urlopen(base + path, timeout=30).read())  # noqa: E731
    try:
        assert get("/api/watch/meta")["instruments"] == ["EURUSD"]
        assert get("/api/watch/status") == {"state": "none"}
        req = urllib.request.Request(base + "/api/watch/start", method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"instrument": "EURUSD", "first_day": "2025-01-02", "days": 1}).encode())
        with pytest.raises(urllib.error.HTTPError):              # outside the slice
            urllib.request.urlopen(req, timeout=30)
        app.session = WatchSession(root / "base.toml", None, "EURUSD", DAY, 1, snap, studies_root=root)
        app.session.prepare()
        status = get("/api/watch/status")
        assert status["state"] == "ready"
        assert get(f"/api/watch/state?t={status['start'] + 7200}")["state"]["arrays"] is not None
        assert get("/api/watch/journal")["rows"]
        assert get(f"/api/watch/bars?tf=M15&until={status['start'] + 7200}")["bars"]
        close = next(t for t, st in app.session.states.items() if st.get("candidates"))
        pick = urllib.request.Request(base + "/api/watch/pick", method="POST", headers={"Content-Type": "application/json"},
                                      data=json.dumps({"t": close, "pick": "none", "note": "no POI here"}).encode())
        assert json.loads(urllib.request.urlopen(pick, timeout=30).read())["pick"] == "none"
        assert [x["t"] for x in get("/api/watch/picks")["picks"]] == [close]
        assert b"engine.js" in urllib.request.urlopen(base + "/", timeout=30).read()
    finally:
        server.shutdown()
        server.server_close()
