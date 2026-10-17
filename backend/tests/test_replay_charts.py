"""
Tests for algo_research/replay/charts.py — one chart, two analysts (market-narrative Requirement 15, update 2026-10-15).

Task 309 (.kiro/specs/market-narrative/tasks.md). Two synthetic instruments written as a snapshot: one server serves
the You mode (a blind journal per instrument) and the Engine mode (the watch), and a watchlist that never reads
past the clock it is given.
Validates: Requirements 15.1-15.2 (.kiro/specs/market-narrative/requirements.md)
"""
from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from datetime import date

import pandas as pd
import pytest

from algo_backtester.watch import WatchApp, from_wall, wall
from algo_research.replay.charts import ChartsApp, make_charts_server
from tests.test_replay import END, FIRST, NY, synthetic_m1


@pytest.fixture()
def charts(tmp_path):
    snap = tmp_path / "snapshot"
    snap.mkdir()
    synthetic_m1(3).to_parquet(snap / "XAUUSD_M1.parquet", index=False)
    euro = synthetic_m1(5).copy()
    for c in ("open", "high", "low", "close"):
        euro[c] = euro[c] / 2400                                             # a EURUSD-like price
    euro.to_parquet(snap / "EURUSD_M1.parquet", index=False)
    config = tmp_path / "base.toml"
    config.write_text("[run]\nprofile = \"exness-standard\"\n", encoding="utf-8")
    watch = WatchApp(config, snap, (FIRST, END), picks=tmp_path / "picks.jsonl")
    return ChartsApp(snap, tmp_path / "journal", (FIRST, END), watch, default="XAUUSD")


def test_the_watchlist_never_shows_a_price_after_the_clock(charts):
    until = pd.Timestamp("2025-01-09 10:30", tz=NY).tz_convert("UTC")
    rows = {r["instrument"]: r for r in charts.watchlist(until)["rows"]}
    assert set(rows) == {"EURUSD", "XAUUSD"}
    gold = synthetic_m1(3)
    closed = gold[gold["time"] <= until - pd.Timedelta(minutes=1)]
    assert rows["XAUUSD"]["last"] == pytest.approx(float(closed["close"].iloc[-1]))
    day_open = pd.Timestamp("2025-01-08 17:00", tz=NY).tz_convert("UTC")
    prev = float(gold[gold["time"] <= day_open - pd.Timedelta(minutes=1)]["close"].iloc[-1])
    assert rows["XAUUSD"]["change"] == pytest.approx(rows["XAUUSD"]["last"] - prev)
    assert rows["XAUUSD"]["change_pct"] == pytest.approx(100 * (rows["XAUUSD"]["last"] - prev) / prev)
    assert rows["XAUUSD"]["digits"] == 3 and rows["EURUSD"]["digits"] == 5
    early = {r["instrument"]: r for r in charts.watchlist(pd.Timestamp("2024-01-01", tz="UTC"))["rows"]}
    assert early["XAUUSD"]["last"] is None                                   # before the data: empty, not an error


def test_the_you_mode_watchlist_is_read_at_its_days_clock_and_names_no_time(charts):
    replay = charts.replay("XAUUSD")
    day = replay.journal.current()
    rows = {r["instrument"]: r for r in charts.watchlist_for({"inst": "XAUUSD"})["rows"]}
    assert rows["XAUUSD"]["last"] == pytest.approx(day["price"])
    assert set(charts.watchlist_for({"inst": "XAUUSD"})) == {"rows"}         # no time: it would name the blind day
    assert all(set(r) == {"instrument", "digits", "last", "change", "change_pct"} for r in rows.values())


def test_each_instrument_has_its_own_blind_journal(charts):
    gold, euro = charts.replay("XAUUSD"), charts.replay("eurusd")
    assert gold is charts.replay("XAUUSD") and gold is not euro
    assert gold.journal.instrument == "XAUUSD" and euro.journal.instrument == "EURUSD"
    with pytest.raises(ValueError):
        charts.replay("GBPUSD")


def test_the_charts_serve_both_modes(charts):
    server = make_charts_server(charts, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    get = lambda path: json.loads(urllib.request.urlopen(base + path, timeout=30).read())  # noqa: E731
    page = lambda path: urllib.request.urlopen(base + path, timeout=30).read()             # noqa: E731

    def post(path, body):
        req = urllib.request.Request(base + path, method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps(body).encode())
        return json.loads(urllib.request.urlopen(req, timeout=30).read())

    try:
        you, engine = page("/"), page("/engine")
        assert b"app.js" in you and b"shell.js" in you and b"engine.js" in engine and b"shell.js" in engine
        for name in ("shell.js", "motion.js", "drawings.js", "settings.js", "app.js", "engine.js", "app.css"):
            assert page("/static/" + name)
        assert get("/api/instruments") == {"instruments": ["EURUSD", "XAUUSD"], "default": "XAUUSD"}
        assert get("/api/state")["instrument"] == "XAUUSD"
        assert get("/api/state?inst=EURUSD")["instrument"] == "EURUSD"
        assert get("/api/meta?inst=EURUSD")["digits"] == 5
        saved = post("/api/drawings?inst=EURUSD", {"drawings": [{"id": "d1", "type": "hline", "points": [{"t": 1, "p": 1.1}]}]})
        assert [d["id"] for d in saved["drawings"]] == ["d1"]
        assert get("/api/state?inst=XAUUSD")["drawings"] == []               # the journals are apart
        assert {r["instrument"] for r in get("/api/watchlist?inst=EURUSD")["rows"]} == {"EURUSD", "XAUUSD"}
        t = wall(pd.Timestamp("2025-01-09 10:30", tz=NY).tz_convert("UTC"))
        rows = {r["instrument"]: r for r in get(f"/api/watchlist?t={t}")["rows"]}
        assert rows["XAUUSD"]["last"] == pytest.approx(charts.bars("XAUUSD").price_at(from_wall(t)))
        assert get("/api/watch/status") == {"state": "none"}
        with pytest.raises(urllib.error.HTTPError) as err:
            get("/api/state?inst=GBPUSD")
        assert err.value.code == 400
    finally:
        server.shutdown()
        server.server_close()


def test_the_engine_mode_is_warned_of_days_still_unread_in_the_blind_replay(charts):
    replay = charts.replay("XAUUSD")
    first = date.fromisoformat(replay.journal.current()["trading_date"])     # the day the blind replay serves first
    query = {"inst": "XAUUSD", "first_day": first.isoformat(), "days": 3}
    before = charts.blind(query)
    assert before["days"] >= 1 and before["unread"] == before["days"]
    replay.journal.save_read({"bias": "NO_THESIS", "confidence": 1})
    replay.journal.reveal()
    assert charts.blind(query) == {"days": before["days"], "unread": before["days"] - 1}


def test_a_watch_session_is_kept_for_its_tab(charts, monkeypatch):
    from algo_backtester import watch as watch_mod
    started = []
    monkeypatch.setattr(watch_mod.WatchSession, "prepare", lambda self: started.append(self.instrument))
    body = {"instrument": "XAUUSD", "first_day": "2025-01-08", "days": 1}
    charts.watch.start(body)
    first = charts.watch.session
    charts.watch.start({**body, "instrument": "EURUSD"})
    charts.watch.start(body)                                                 # back to the gold tab: the same session
    assert charts.watch.session is first and started == ["XAUUSD", "EURUSD"]


def test_static_serves_any_script_the_pages_ask_for(tmp_path):
    """A page is read from disk per request, so a long-running server must serve a script added since it
    started (2026-10-17: a stale server served the new engine page and 404ed noculus.js, killing the page)."""
    from algo_research.replay.server import STATIC, static_file

    for name in sorted(p.name for p in STATIC.glob("*.js")):
        served = static_file(name)
        assert served is not None, f"static/{name} is not served"
        assert served[1].startswith("text/javascript")
    assert static_file("app.css")[1].startswith("text/css")
    assert static_file("engine.html")[1].startswith("text/html")
    # Every script each page asks for is served.
    for page in ("index.html", "engine.html"):
        text = (STATIC / page).read_text(encoding="utf-8")
        for src in re.findall(r'<script src="/static/([^"]+)"', text):
            assert static_file(src) is not None, f"{page} asks for {src}, which is not served"


def test_static_refuses_anything_outside_the_folder():
    from algo_research.replay.server import static_file

    for name in ("../config/backtests/base.toml", "..\\..\\.env", "sub/app.js", "", None, ".env",
                 "../../algo_backtester/watch.py", "nothing_here.js", "app.js.bak"):
        assert static_file(name) is None, f"{name!r} must not be served"
