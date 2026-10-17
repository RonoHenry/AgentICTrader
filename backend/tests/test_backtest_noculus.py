"""
Tests for Noculus (algo-backtester update 2026-10-16): the trader's marks and trades against the engine's.

Task 329 (.kiro/specs/algo-backtester/tasks.md): blind sessions and the session journal. The watch tests' fixture
week and prepared session are reused; a blind session is the same prepared session, started blind.
Validates: Requirements 17.1-17.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import copy
import json
from datetime import timedelta

import pytest

from algo_backtester.noculus import NoculusJournal
from algo_backtester.watch import STATIC, WatchApp, wall
from tests.test_backtest_watch import DAY, session, setup  # noqa: F401  (fixtures)


@pytest.fixture()
def blind(session):  # noqa: F811
    s = copy.copy(session)
    s.blind, s.revealed_at = True, None
    return s


def _engine_keys(state: dict) -> set:
    return set(state) - {"t", "withheld"}


def test_a_blind_session_withholds_the_engine_until_reveal(blind, session):  # noqa: F811
    mid = blind._keys[len(blind._keys) // 2]
    state = blind.state_at(mid)
    assert state == {"t": mid, "withheld": True}                         # the clock only
    assert blind.journal_rows() == [] and blind.model_a_at("model_d1", mid) == []
    assert blind.status()["summary"] == {} and blind.status()["blind"] is True
    with pytest.raises(LookupError, match="reveal"):
        blind.save_pick({"t": mid, "pick": "none"})
    # The open session shows everything, as before.
    assert _engine_keys(session.state_at(mid)) and session.journal_rows() == session.journal


def test_reveal_shows_everything_up_to_the_clock_and_cannot_be_undone(blind, session):  # noqa: F811
    mid = blind._keys[len(blind._keys) // 2]
    blind.reveal(mid)
    assert blind.revealed_at == mid and blind.status()["revealed_at"] == mid
    assert blind.state_at(mid) == session.state_at(mid)
    assert blind.journal_rows() == session.journal and blind.status()["summary"] == session.summary
    with pytest.raises(LookupError, match="already revealed"):
        blind.reveal(mid)
    with pytest.raises(LookupError, match="not blind"):
        copy.copy(session).reveal(mid)


def test_the_journal_round_trips_and_is_written_whole(tmp_path):
    path = tmp_path / "EURUSD" / "s1.json"
    journal = NoculusJournal(path, {"instrument": "EURUSD", "first_day": "2026-09-30", "days": 1})
    journal.data["marks"].append({"id": "m1", "tool": "FVG"})
    journal.save()
    again = NoculusJournal(path)
    assert again.data["marks"] == [{"id": "m1", "tool": "FVG"}] and again.data["session"]["instrument"] == "EURUSD"
    assert set(again.data) == {"session", "marks", "trades", "reveal", "comparison"}
    assert not list(path.parent.glob("*.tmp"))                           # written through a temporary file
    assert json.loads(path.read_text(encoding="utf-8"))["session"]["days"] == 1


def test_a_blind_start_gets_its_own_journal(setup, tmp_path):  # noqa: F811
    root, snap = setup
    app = WatchApp(root / "base.toml", snap, (DAY, DAY + timedelta(days=1)), noculus_root=tmp_path,
                   studies_root=root)
    status = app.start({"instrument": "EURUSD", "first_day": DAY.isoformat(), "days": 1, "blind": True})
    assert status["blind"] is True
    session = app.session
    assert session.noculus is not None and session.noculus.path.parent == tmp_path / "EURUSD"
    assert session.noculus.data["session"]["first_day"] == DAY.isoformat()
    other = app.start({"instrument": "EURUSD", "first_day": DAY.isoformat(), "days": 1})
    assert other["blind"] is False                                       # the open session is a different one


def test_the_pages_are_called_noculus():
    for page in ("engine.html", "index.html"):
        text = (STATIC / page).read_text(encoding="utf-8")
        assert "<title>Noculus" in text and "Noculus" in text.split("<h1>")[1].split("</h1>")[0]


def test_the_reveal_endpoint_and_the_journal_endpoint(setup, tmp_path):  # noqa: F811
    import threading
    import time
    import urllib.request

    from algo_backtester.watch import make_watch_server

    root, snap = setup
    app = WatchApp(root / "base.toml", snap, (DAY, DAY + timedelta(days=1)), noculus_root=tmp_path,
                   studies_root=root)
    server = make_watch_server(app, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    try:
        call("/api/watch/start", {"instrument": "EURUSD", "first_day": DAY.isoformat(), "days": 1, "blind": True})
        for _ in range(600):
            if call("/api/watch/status")["state"] == "ready":
                break
            time.sleep(0.2)
        t = app.session._keys[10]
        assert call(f"/api/watch/state?t={t}")["state"]["withheld"] is True
        assert call("/api/watch/reveal", {"t": t})["revealed_at"] == t
        assert "withheld" not in call(f"/api/watch/state?t={t}")["state"]
        journal = call("/api/watch/noculus")
        assert journal["reveal"]["t"] == t and journal["marks"] == []
    finally:
        server.shutdown()
