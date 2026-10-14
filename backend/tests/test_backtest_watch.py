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

from algo_backtester.watch import SnapshotSource, WatchApp, WatchSession, make_watch_server, wall
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


def test_bars_never_pass_the_time_asked(session):
    t = wall(pd.Timestamp("2026-09-30 10:41", tz="America/New_York"))
    for tf in ("M1", "M15", "H1", "H4"):
        bars = session.bars_until(tf, t, None)
        assert bars and max(b["time"] for b in bars) < t


def test_the_watch_server_round_trip(setup):
    root, snap = setup
    app = WatchApp(root / "base.toml", snap, (date(2026, 9, 28), date(2026, 10, 3)))
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
        assert b"engine.js" in urllib.request.urlopen(base + "/", timeout=30).read()
    finally:
        server.shutdown()
        server.server_close()
