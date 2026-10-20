"""
Tests for Noculus (algo-backtester update 2026-10-16): the trader's marks and trades against the engine's.

Tasks 329-330 (.kiro/specs/algo-backtester/tasks.md): blind sessions and the session journal; arrays marked by
their candles. The watch tests' fixture week and prepared session are reused; a blind session is the same
prepared session, started blind. A mark's geometry is checked against ``algo_research.atlas.arrays``, which is
the same definition read the other way round (from the bars, not from a click).
Validates: Requirements 17.1-17.4, 18.1-18.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import copy
import json
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from algo_backtester.noculus import (NoculusJournal, build_mark, close, compare, place, settle,
                                     write_report)
from algo_backtester.watch import STATIC, WatchApp, from_wall, wall
from algo_research.atlas.arrays import fvgs, order_blocks
from algo_research.replay.timeframes import seconds_of, wall_seconds
from liquidity_engine.models import Timeframe
from tests.test_backtest_watch import DAY, session, setup  # noqa: F401  (fixtures)


@pytest.fixture()
def blind(session):  # noqa: F811
    s = copy.copy(session)
    s.blind, s.revealed_at = True, None
    return s


def _engine_keys(state: dict) -> set:
    return set(state) - {"t", "withheld"}


# ── the bars a mark is read from, and the same bars read by the atlas ──────────
def _bars(session, tf: str):  # noqa: F811
    """The session's ``tf`` bars up to its end, as the chart draws them."""
    first = wall(session.bars.m1["time"].min())
    return session.bars.as_of(tf, from_wall(wall(session.end)), since=first)


def _atlas(bars: pd.DataFrame, tf: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    size = seconds_of(tf)
    frame = pd.DataFrame({"time": [from_wall(t) for t in bars["time"]],
                          "close_time": [from_wall(int(t) + size) for t in bars["time"]],
                          "open": bars["open"], "high": bars["high"], "low": bars["low"], "close": bars["close"]})
    return fvgs(frame, Timeframe(tf)), order_blocks(frame, Timeframe(tf))


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
    import urllib.error
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
        # The trader marks an array by its candle, then takes it back, while the engine is still hidden.
        bars = _bars(app.session, "H1")
        table, _ = _atlas(bars, "H1")
        third = next(wall(r.formed_at) for r in table.itertuples() if wall(r.formed_at) <= t) - seconds_of("H1")
        mark = call("/api/watch/noculus/mark", {"tool": "FVG", "tf": "H1", "t": t, "candle": third, "note": "C3"})
        assert mark["id"] == "m1" and mark["tool"] == "FVG" and mark["clock"] == t
        with pytest.raises(urllib.error.HTTPError) as bad:                   # a refusal comes back as the reason
            call("/api/watch/noculus/mark", {"tool": "FVG", "tf": "H1", "t": t, "candle": third + 7})
        assert "no H1 candle" in json.loads(bad.value.read())["error"]
        assert call("/api/watch/noculus/unmark", {"id": "m1", "t": t})["deleted_at"] == t
        assert call("/api/watch/reveal", {"t": t})["revealed_at"] == t
        assert "withheld" not in call(f"/api/watch/state?t={t}")["state"]
        journal = call("/api/watch/noculus")
        assert journal["reveal"]["t"] == t and [m["id"] for m in journal["marks"]] == ["m1"]
        assert journal["marks"][0]["deleted_at"] == t                        # deleted, and still in the journal
    finally:
        server.shutdown()


# ── task 330: arrays marked by their candles (Requirements 18.1-18.3) ─────────
def test_an_fvg_mark_is_the_atlas_read_from_its_third_candle(session):  # noqa: F811
    bars = _bars(session, "H1")
    table, _ = _atlas(bars, "H1")
    clock = int(bars["time"].iloc[-1])                              # the last bar is still forming
    seen = set()
    for row in table.itertuples():
        third = wall(row.formed_at) - seconds_of("H1")              # the candle that closed the gap
        if wall(row.formed_at) > clock:
            continue
        mark = build_mark(bars, tool="FVG", tf="H1", clock=clock, candle=third)
        assert (mark["direction"], mark["low"], mark["high"], mark["mid"]) == (
            row.direction, row.low, row.high, row.mid), f"the mark at {row.formed_at} is not the atlas's"
        assert from_wall(mark["formed_at"]) == row.formed_at and mark["candles"] == [third - 2 * 3600, third - 3600, third]
        seen.add(row.direction)
    assert seen == {1, -1}, "the fixture week should offer a gap each way"


def test_three_candles_without_a_gap_are_refused(session):  # noqa: F811
    bars = _bars(session, "H1")
    clock, h, l = int(bars["time"].iloc[-1]), bars["high"].to_numpy(float), bars["low"].to_numpy(float)
    flat = next(i for i in range(2, len(bars) - 1) if not (l[i] > h[i - 2]) and not (h[i] < l[i - 2]))
    with pytest.raises(ValueError, match="gap"):
        build_mark(bars, tool="FVG", tf="H1", clock=clock, candle=int(bars["time"].iloc[flat]))
    with pytest.raises(ValueError, match="two candles"):                     # nothing before C1
        build_mark(bars, tool="FVG", tf="H1", clock=clock, candle=int(bars["time"].iloc[0]))


def test_an_ifvg_needs_a_later_close_beyond_it_by_the_clock(session):  # noqa: F811
    bars = _bars(session, "H1")
    table, _ = _atlas(bars, "H1")
    flipped = table[table["flipped_at"].notna()].iloc[0]
    third = wall(flipped["formed_at"]) - seconds_of("H1")
    flip = wall(flipped["flipped_at"])
    with pytest.raises(ValueError, match="no H1 close beyond it"):            # before the flip it is still an FVG
        build_mark(bars, tool="IFVG", tf="H1", clock=flip - seconds_of("H1"), candle=third)
    mark = build_mark(bars, tool="IFVG", tf="H1", clock=flip, candle=third)
    assert mark["direction"] == -flipped["direction"]                         # facing the other way
    assert (mark["low"], mark["high"], mark["mid"]) == (flipped["low"], flipped["high"], flipped["mid"])
    assert mark["formed_at"] == flip and mark["candles"][-1] == flip - seconds_of("H1")


def test_an_order_block_mark_takes_the_body_midpoint_and_the_trader_s_direction(session):  # noqa: F811
    bars = _bars(session, "H1")
    clock = int(bars["time"].iloc[-1])
    up = next(i for i in range(len(bars) - 1) if bars["close"].iloc[i] > bars["open"].iloc[i])
    bar, t = bars.iloc[up], int(bars["time"].iloc[up])
    mark = build_mark(bars, tool="OB", tf="H1", clock=clock, candle=t)
    assert mark["direction"] == -1                                           # an up candle is a bearish block
    assert (mark["low"], mark["high"]) == (bar["low"], bar["high"])
    assert mark["mid"] == pytest.approx((bar["open"] + bar["close"]) / 2)     # the MT, the body's midpoint
    assert mark["formed_at"] == t + seconds_of("H1") and mark["candles"] == [t]
    assert build_mark(bars, tool="OB", tf="H1", clock=clock, candle=t, direction=1)["direction"] == 1


def test_an_order_block_mark_matches_the_engine_s_own_block(session):  # noqa: F811
    _, table = _atlas(bars := _bars(session, "H1"), "H1")
    clock, found = int(bars["time"].iloc[-1]), 0
    for row in table.itertuples():
        same = bars[(bars["low"] == row.low) & (bars["high"] == row.high)]    # the block's own candle
        if len(same) != 1 or int(same["time"].iloc[0]) + seconds_of("H1") > clock:
            continue
        mark = build_mark(bars, tool="OB", tf="H1", clock=clock, candle=int(same["time"].iloc[0]), direction=row.direction)
        assert (mark["low"], mark["high"], mark["mid"]) == (row.low, row.high, row.mid)
        found += 1
    assert found, "the fixture week should offer an order block to mark"


def test_a_breaker_needs_a_close_beyond_the_block(session):  # noqa: F811
    bars = _bars(session, "H1")
    clock = int(bars["time"].iloc[-1])
    up = next(i for i in range(len(bars) - 1) if bars["close"].iloc[i] > bars["open"].iloc[i])
    t, high = int(bars["time"].iloc[up]), float(bars["high"].iloc[up])
    beyond = bars[(bars["time"] > t) & (bars["close"] > high)]                # a bearish block breaks upward
    assert not beyond.empty, "the fixture week should break the first bullish candle's block"
    flip = int(beyond["time"].iloc[0]) + seconds_of("H1")
    with pytest.raises(ValueError, match="no H1 close beyond it"):
        build_mark(bars, tool="BRK", tf="H1", clock=flip - seconds_of("H1"), candle=t)
    mark = build_mark(bars, tool="BRK", tf="H1", clock=flip, candle=t)
    assert mark["direction"] == 1 and mark["formed_at"] == flip               # the block now faces the other way


def test_a_candle_that_has_not_closed_by_the_clock_is_refused(session):  # noqa: F811
    bars = _bars(session, "H1")
    table, _ = _atlas(bars, "H1")
    row = table.iloc[-1]
    third = wall(row["formed_at"]) - seconds_of("H1")
    with pytest.raises(ValueError, match="has not closed"):
        build_mark(bars, tool="FVG", tf="H1", clock=third, candle=third)      # C3 is still forming
    with pytest.raises(ValueError, match="no H1 candle"):
        build_mark(bars, tool="FVG", tf="H1", clock=third, candle=third + 17)  # not a bar's start at all


def test_the_journal_keeps_a_mark_and_keeps_it_when_deleted(tmp_path):
    journal = NoculusJournal(tmp_path / "EURUSD" / "s1.json", {"instrument": "EURUSD"})
    one = journal.add_mark({"tool": "FVG", "tf": "H1", "direction": 1, "low": 1.0, "high": 1.1, "mid": 1.05,
                            "formed_at": 100, "candles": [0, 50, 100], "clock": 200, "note": "the gap I like"})
    two = journal.add_mark({"tool": "OB", "tf": "H4", "direction": -1, "low": 1.0, "high": 1.2, "mid": 1.1,
                            "formed_at": 300, "candles": [200], "clock": 400, "note": ""})
    assert [one["id"], two["id"]] == ["m1", "m2"] and one["deleted_at"] is None
    journal.delete_mark("m1", 500)
    again = NoculusJournal(journal.path)
    kept = {m["id"]: m for m in again.data["marks"]}
    assert len(kept) == 2 and kept["m1"]["deleted_at"] == 500 and kept["m2"]["deleted_at"] is None
    with pytest.raises(KeyError, match="m9"):
        again.delete_mark("m9", 600)


def test_a_session_marks_only_while_it_keeps_a_journal(blind, session, tmp_path):  # noqa: F811
    bars = _bars(session, "H1")
    table, _ = _atlas(bars, "H1")
    third = wall(table.iloc[0]["formed_at"]) - seconds_of("H1")
    clock = wall(session.end)
    with pytest.raises(LookupError, match="journal"):                         # the open session keeps none
        session.mark({"tool": "FVG", "tf": "H1", "t": clock, "candle": third})
    blind.noculus = NoculusJournal(tmp_path / "EURUSD" / "s1.json", {"instrument": "EURUSD"})
    mark = blind.mark({"tool": "FVG", "tf": "H1", "t": clock, "candle": third, "note": "C3 here"})
    assert mark["id"] == "m1" and mark["note"] == "C3 here" and mark["clock"] == clock
    assert NoculusJournal(blind.noculus.path).data["marks"] == [mark]          # saved as it was made
    assert blind.unmark({"id": "m1", "t": clock})["deleted_at"] == clock


def test_the_page_carries_the_marking_tools():
    from algo_backtester.watch import FILES
    page, js = (STATIC / "engine.html").read_text(encoding="utf-8"), (STATIC / "noculus.js").read_text(encoding="utf-8")
    assert "noculus.js" in FILES and '<script src="/static/noculus.js">' in page
    assert 'id="noculus"' in page and 'id="sBlind"' in page                   # the panel, and starting blind
    assert all(f'"{tool}"' in js for tool in ("FVG", "IFVG", "OB", "BRK"))
    for path in ("/api/watch/noculus/mark", "/api/watch/noculus/unmark", "/api/watch/reveal"):
        assert path in js


# ── task 331: pseudo trades (Requirements 19.1-19.3) ─────────────────────────
def _orders(clock: int, direction: str, stop: float, target: float, until: int) -> pd.DataFrame:
    return pd.DataFrame({"t": [from_wall(clock)], "direction": [direction], "stop": [stop], "target": [target],
                         "limit": [from_wall(until)]})


def _price(session, clock: int) -> float:  # noqa: F811
    return float(session.bars.price_at(from_wall(clock)))


def test_a_market_trade_settles_as_a_race_does(session):  # noqa: F811
    from algo_research.races import run_races

    clock, end = wall(session.start) + 7200, wall(session.end)
    bid = _price(session, clock)
    for direction, sign in (("LONG", 1), ("SHORT", -1)):
        stop, target = bid - sign * 0.0010, bid + sign * 0.0010
        race = run_races(session.frame, _orders(clock, direction, stop, target, end)).iloc[0]
        assert race["outcome"] in ("TARGET", "STOP"), "the test wants a race that resolves"
        trade = place({"direction": direction, "kind": "MARKET", "stop": stop, "target": target}, session.path, clock)
        settle(trade, session.path, end, session.costs)
        assert trade["state"] == "CLOSED" and trade["outcome"] == race["outcome"]
        assert trade["fill"] == pytest.approx(race["entry"]) and trade["filled_at"] == wall(race["entry_time"])
        assert trade["exit"] == pytest.approx(race["exit"]) and trade["exit_at"] == wall(race["exit_time"])
        assert trade["net_r"] == pytest.approx(race["net_r"]) and trade["gross_r"] == pytest.approx(race["gross_r"])
        assert trade["mfe_r"] == pytest.approx(race["mfe_r"]) and trade["mae_r"] == pytest.approx(race["mae_r"])


def test_a_limit_fills_at_the_first_bar_through_it_or_expires(session):  # noqa: F811
    clock, end = wall(session.start) + 7200, wall(session.end)
    path, bid = session.path, _price(session, wall(session.start) + 7200)
    price = bid - 0.0005                                                      # a long limit, below the ask
    t, low, sp = path["time"], path["low"], path["spread"]
    through = int(t[np.flatnonzero((t >= clock) & (low + sp <= price))[0]])
    trade = place({"direction": "LONG", "kind": "LIMIT", "price": price, "stop": price - 0.0010,
                   "target": price + 0.0010, "expiry": end}, path, clock)
    assert trade["state"] == "PENDING" and trade["fill"] is None
    settle(trade, path, through + 60, session.costs)
    assert trade["filled_at"] == through and trade["fill"] == pytest.approx(price)
    early = place({"direction": "LONG", "kind": "LIMIT", "price": price, "stop": price - 0.0010,
                   "target": price + 0.0010, "expiry": through}, path, clock)
    settle(early, path, end, session.costs)
    assert early["state"] == "EXPIRED" and early["fill"] is None and early["net_r"] is None


def test_a_trade_closed_by_hand_exits_at_the_closing_side_of_the_last_close(session):  # noqa: F811
    clock = wall(session.start) + 7200
    path, bid = session.path, _price(session, wall(session.start) + 7200)
    trade = place({"direction": "SHORT", "kind": "MARKET", "stop": bid + 0.0050, "target": bid - 0.0050}, path, clock)
    settle(trade, path, clock + 1800, session.costs)
    assert trade["state"] == "OPEN" and trade["live_r"] is not None
    at = clock + 1800
    n = int(np.count_nonzero(path["time"] + 60 <= at))
    close(trade, path, at, session.costs)
    assert trade["state"] == "CLOSED" and trade["outcome"] == "MANUAL"
    assert trade["exit"] == pytest.approx(path["close"][n - 1] + path["spread"][n - 1])   # a short closes at the ask
    assert trade["exit_at"] == int(path["time"][n - 1]) + 60


def test_nothing_settles_from_bars_after_the_clock(session):  # noqa: F811
    clock, end = wall(session.start) + 7200, wall(session.end)
    path, bid = session.path, _price(session, wall(session.start) + 7200)
    far = place({"direction": "LONG", "kind": "MARKET", "stop": bid - 0.0010, "target": bid + 0.0010}, path, clock)
    settle(far, path, clock, session.costs)                                   # the entry bar has not closed
    assert far["state"] == "PENDING" and far["fill"] is None
    settle(far, path, clock + 120, session.costs)
    assert far["fill"] is not None and far["settled_to"] == clock + 120
    resolved = place({"direction": "LONG", "kind": "MARKET", "stop": bid - 0.0010, "target": bid + 0.0010}, path, clock)
    settle(resolved, path, end, session.costs)
    assert resolved["state"] == "CLOSED"
    assert far["state"] == "OPEN" or far["exit_at"] > clock + 120             # nothing read from later bars


def test_a_trade_is_refused_when_it_makes_no_sense(session):  # noqa: F811
    clock, path, bid = wall(session.start) + 7200, session.path, _price(session, wall(session.start) + 7200)
    for body, reason in (
        ({"direction": "LONG", "kind": "MARKET", "stop": bid + 0.0010, "target": bid + 0.0020}, "stop"),
        ({"direction": "LONG", "kind": "MARKET", "stop": bid - 0.0010, "target": bid - 0.0020}, "target"),
        ({"direction": "LONG", "kind": "LIMIT", "price": bid + 0.0050, "stop": bid, "target": bid + 0.01}, "below"),
        ({"direction": "SHORT", "kind": "LIMIT", "price": bid - 0.0050, "stop": bid, "target": bid - 0.01}, "above"),
        ({"direction": "SIDEWAYS", "kind": "MARKET", "stop": bid, "target": bid}, "direction"),
    ):
        with pytest.raises(ValueError, match=reason):
            place(body, path, clock)


def test_the_session_places_settles_and_closes_its_own_trades(blind, session, tmp_path):  # noqa: F811
    clock = wall(session.start) + 7200
    bid = _price(session, clock)
    with pytest.raises(LookupError, match="journal"):
        session.place({"direction": "LONG", "kind": "MARKET", "stop": bid - 0.001, "target": bid + 0.001, "t": clock})
    blind.noculus = NoculusJournal(tmp_path / "EURUSD" / "s1.json", {"instrument": "EURUSD"})
    trade = blind.place({"direction": "LONG", "kind": "MARKET", "stop": bid - 0.0050, "target": bid + 0.0050,
                         "t": clock, "note": "my long"})
    assert trade["id"] == "t1" and trade["state"] == "PENDING" and trade["placed_at"] == clock
    rows = blind.trades({"t": clock + 1800})                                  # settled to the clock on each read
    assert rows[0]["state"] in ("OPEN", "CLOSED") and rows[0]["id"] == "t1"
    assert NoculusJournal(blind.noculus.path).data["trades"][0]["state"] == rows[0]["state"]
    done = blind.close_trade({"id": "t1", "t": clock + 1800})
    assert done["outcome"] == "MANUAL" and done["net_r"] is not None


def test_the_trade_endpoints_and_the_ticket_on_the_page(setup, tmp_path):  # noqa: F811
    import threading
    import time
    import urllib.request

    from algo_backtester.watch import make_watch_server

    root, snap = setup
    app = WatchApp(root / "base.toml", snap, (DAY, DAY + timedelta(days=1)), noculus_root=tmp_path, studies_root=root)
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
        session = app.session
        t = wall(session.start) + 7200
        bid = float(session.bars.price_at(from_wall(t)))
        placed = call("/api/watch/noculus/place", {"direction": "LONG", "kind": "MARKET", "t": t,
                                                   "stop": bid - 0.0050, "target": bid + 0.0050, "note": "mine"})
        assert placed["id"] == "t1" and placed["state"] == "PENDING"
        rows = call(f"/api/watch/noculus/trades?t={t + 3600}")["trades"]
        assert rows[0]["fill"] is not None and rows[0]["state"] in ("OPEN", "CLOSED")
        if rows[0]["state"] == "OPEN":
            assert call("/api/watch/noculus/close", {"id": "t1", "t": t + 3600})["outcome"] == "MANUAL"
        assert json.loads((session.noculus.path).read_text(encoding="utf-8"))["trades"][0]["id"] == "t1"
    finally:
        server.shutdown()


def test_the_page_carries_the_trade_ticket():
    js = (STATIC / "noculus.js").read_text(encoding="utf-8")
    for path in ("/api/watch/noculus/place", "/api/watch/noculus/close", "/api/watch/noculus/trades"):
        assert path in js
    for field in ("nKind", "nPrice", "nStop", "nTarget", "nPlace", "nMark"):
        assert field in js


# ── task 332: reveal and compare (Requirements 20.1-20.3) ────────────────────
def _mark(**kw) -> dict:
    row = {"id": "m1", "tool": "FVG", "tf": "H1", "direction": 1, "low": 1.1, "high": 1.11, "mid": 1.105,
           "formed_at": 1790553600, "candles": [1790546400, 1790550000, 1790553600], "clock": 1790553600,
           "note": "", "deleted_at": None}
    row.update(kw)
    return row


def _array(**kw) -> dict:
    row = {"id": "a1", "type": "FVG", "dir": "BULLISH", "tf": "H1", "high": 1.11, "low": 1.1,
           "formed": 1790553600, "mt": None, "entry": False}
    row.update(kw)
    return row


def _trade(**kw) -> dict:
    row = {"id": "t1", "direction": "LONG", "kind": "MARKET", "price": None, "stop": 1.09, "target": 1.12,
           "expiry": None, "mark": None, "placed_at": 1790553600, "note": "", "state": "CLOSED", "fill": 1.1,
           "fill_bid": 1.1, "filled_at": 1790553660, "exit": 1.12, "exit_bid": 1.12, "exit_at": 1790560000,
           "outcome": "TARGET", "risk": 0.01, "gross_r": 2.0, "net_r": 2.0, "commission_r": 0.0, "mfe_r": 2.0,
           "mae_r": -0.1, "live_r": None, "ambiguous": False, "settled_to": 1790560000}
    row.update(kw)
    return row


def _row(**kw) -> dict:
    row = {"t": 1790553600, "decision": "EXECUTE", "reason": "", "grade": "B", "direction": "LONG", "entry": 1.1,
           "stop": 1.09, "target": 1.12, "r_ratio": 2.0, "order_kind": "MARKET", "placed_at": 1790553600,
           "expires_at": None, "filled_at": 1790553660, "fill": 1.1, "closed_at": 1790560000, "exit": 1.12,
           "exit_reason": "TARGET", "net_r": 2.0, "mfe_r": 2.0}
    row.update(kw)
    return row


def test_arrays_match_by_their_formation_candle_within_one_candle():
    clock = 1790600000
    mine = [_mark(), _mark(id="m2", tool="OB", direction=-1, formed_at=1790557200),
            _mark(id="m3", tf="H4", formed_at=1790553600)]
    engine = [_array(formed=1790550000),                                 # one H1 candle early: still a match
              _array(id="a2", type="BREAKER", dir="BEARISH", formed=1790557200),
              _array(id="a3", type="OB", dir="BULLISH", tf="H1", formed=1790560800),
              _array(id="a4", type="FVG", dir="BULLISH", tf="D1", formed=1790553600)]
    out = compare(mine, [], engine, [], clock)["arrays"]
    assert [p["mine"]["id"] for p in out["matched"]] == ["m1", "m2"]      # the breaker counts as the OB family
    assert out["matched"][0]["apart"] == 3600 and out["matched"][1]["apart"] == 0
    assert [m["id"] for m in out["mine_only"]] == ["m3"]                  # no H4 array from the engine
    assert [a["id"] for a in out["engine_only"]] == ["a3"]                # a4's D1 was never marked
    assert out["counts"] == {"mine": 3, "matched": 2, "mine_only": 1, "engine_only": 1}
    assert out["by_kind"]["FVG"] == {"mine": 2, "matched": 1} and out["by_kind"]["OB"] == {"mine": 1, "matched": 1}
    assert out["by_tf"]["H1"]["matched"] == 2 and out["by_tf"]["H4"]["matched"] == 0


def test_a_mark_matches_an_array_the_engine_had_earlier_even_if_it_is_gone_by_the_reveal():
    """Under the three-candle FVG a wick fills it, so the engine can drop an array before the reveal. The
    trader saw it as the engine did: the match is against everything the engine showed up to the clock."""
    clock = 1790600000
    shown = [_array(id="early", formed=1790553600)]                       # shown at an earlier close, then filled
    alive = [_array(id="late", type="OB", formed=1790560800)]             # what is still live at the reveal
    out = compare([_mark()], [], shown + alive, [], clock, alive=alive)["arrays"]
    assert [p["engine"]["id"] for p in out["matched"]] == ["early"]
    assert [a["id"] for a in out["engine_only"]] == ["late"]              # unmarked and still live
    assert out["counts"] == {"mine": 1, "matched": 1, "mine_only": 0, "engine_only": 1}


def test_one_window_reported_twice_with_growing_bounds_counts_once():
    """While its third candle forms the engine re-reports a gap with new bounds, so a new id; it is one array."""
    clock = 1790600000
    v1 = _array(id="v1", formed=1790553600, high=1.1080)
    v2 = _array(id="v2", formed=1790553600, high=1.1100)                  # the same window, a later close
    out = compare([], [], [v1, v2], [], clock, alive=[v2])["arrays"]
    assert out["counts"]["engine_only"] == 0                              # no marks: nothing counted on H1
    out = compare([_mark(tf="H1")], [], [v1, v2], [], clock, alive=[v2])["arrays"]
    assert [p["engine"]["id"] for p in out["matched"]] == ["v2"]          # the latest version is the one shown
    assert out["counts"]["engine_only"] == 0                              # and it is not also counted unmarked
    other = _array(id="o", formed=1790560800)
    out = compare([_mark(tf="H1")], [], [v1, v2, other], [], clock, alive=[v2, other])["arrays"]
    assert [a["id"] for a in out["engine_only"]] == ["o"]

def test_a_mark_matches_nothing_of_another_kind_direction_or_timeframe():
    clock = 1790600000
    mine = [_mark()]
    for engine in ([_array(type="OB")], [_array(dir="BEARISH")], [_array(tf="H4")],
                   [_array(formed=1790553600 + 2 * 3600)]):               # two candles away
        out = compare(mine, [], engine, [], clock)["arrays"]
        assert out["counts"]["matched"] == 0 and [m["id"] for m in out["mine_only"]] == ["m1"]


def test_marks_made_after_the_clock_or_deleted_are_left_out():
    clock = 1790553600
    mine = [_mark(), _mark(id="m2", clock=clock + 3600), _mark(id="m3", deleted_at=clock)]
    out = compare(mine, [], [_array()], [], clock)["arrays"]
    assert out["counts"]["mine"] == 1 and out["counts"]["matched"] == 1


def test_trades_are_paired_by_day_and_direction():
    clock = 1790700000
    mine = [_trade(), _trade(id="t2", direction="SHORT", placed_at=1790560000, filled_at=1790560060,
                             fill=1.12, stop=1.13, target=1.09, net_r=-1.0, outcome="STOP")]
    engine = [_row(), _row(t=1790564000, direction="SHORT", placed_at=1790564000, filled_at=1790564060,
                           fill=1.121, net_r=1.5, exit_reason="TARGET")]
    out = compare([], mine, [], engine, clock)["trades"]
    day = out["days"][0]
    assert len(out["days"]) == 1
    assert [(p["mine"]["id"], p["same_side"]) for p in day["pairs"]] == [("t1", True), ("t2", True)]
    assert day["pairs"][1]["apart_minutes"] == pytest.approx(66.7, abs=0.05)   # to a tenth of a minute
    assert day["mine_r"] == pytest.approx(1.0) and day["engine_r"] == pytest.approx(3.5)
    assert out["totals"]["mine_r"] == pytest.approx(1.0) and out["totals"]["engine_r"] == pytest.approx(3.5)
    assert out["totals"]["days_apart"] == 0                               # they agreed on the side both times


def test_opposite_sides_on_the_same_day_are_paired_and_flagged():
    clock = 1790700000
    mine = [_trade(direction="SHORT", stop=1.12, target=1.08, net_r=-1.0, outcome="STOP")]
    out = compare([], mine, [], [_row()], clock)["trades"]
    day = out["days"][0]
    assert day["pairs"][0]["same_side"] is False and day["pairs"][0]["engine"]["direction"] == "LONG"
    assert out["totals"]["days_apart"] == 1


def test_a_day_only_one_of_them_traded_is_still_reported():
    clock = 1790900000
    mine = [_trade()]
    engine = [_row(t=1790640000, placed_at=1790640000, filled_at=1790640060)]     # the next trading day
    out = compare([], mine, [], engine, clock)["trades"]
    assert len(out["days"]) == 2 and out["days"][0]["day"] < out["days"][1]["day"]
    assert out["days"][0]["pairs"] == [] and [x["id"] for x in out["days"][0]["mine_only"]] == ["t1"]
    assert len(out["days"][1]["engine_only"]) == 1 and out["days"][1]["mine_only"] == []


def test_engine_trades_before_the_traders_window_are_left_out():
    """The engine's run starts early to warm up; an order placed before the session opens was never the
    trader's to see, so it makes no day of disagreement."""
    clock = 1790900000
    engine = [_row(t=1790500000, placed_at=1790500000, filled_at=1790500060), _row()]
    out = compare([], [_trade()], [], engine, clock, since=1790550000)["trades"]
    assert len(out["days"]) == 1 and out["totals"]["engine"] == 1
    assert out["days"][0]["pairs"][0]["same_side"] is True and out["totals"]["days_apart"] == 0

def test_the_session_saves_its_comparison_on_reveal(blind, session, tmp_path):  # noqa: F811
    blind.noculus = NoculusJournal(tmp_path / "EURUSD" / "s1.json", {"instrument": "EURUSD"})
    mid = blind._keys[len(blind._keys) // 2]
    bars = _bars(session, "H1")
    table, _ = _atlas(bars, "H1")
    third = next(wall(r.formed_at) for r in table.itertuples() if wall(r.formed_at) <= mid) - seconds_of("H1")
    blind.mark({"tool": "FVG", "tf": "H1", "t": mid, "candle": third})
    blind.reveal(mid)
    saved = NoculusJournal(blind.noculus.path).data["comparison"]
    assert saved["clock"] == mid and saved["arrays"]["counts"]["mine"] == 1
    assert "days" in saved["trades"] and saved["arrays"]["engine_only"] is not None
    assert blind.comparison()["clock"] == mid                             # and it can be asked for again


def test_the_report_summarises_every_saved_session(tmp_path):
    for day, net in (("2026-09-29", 2.0), ("2026-09-30", -1.0)):
        j = NoculusJournal(tmp_path / "EURUSD" / f"{day}.json", {"instrument": "EURUSD", "first_day": day})
        j.data["reveal"] = {"t": 1790600000, "at": "2026-10-17T06:00:00+00:00"}
        j.data["comparison"] = {"clock": 1790600000,
                                "arrays": {"counts": {"mine": 2, "matched": 1, "mine_only": 1, "engine_only": 3},
                                           "by_kind": {"FVG": {"mine": 2, "matched": 1}},
                                           "by_tf": {"H1": {"mine": 2, "matched": 1}},
                                           "matched": [], "mine_only": [], "engine_only": []},
                                "trades": {"days": [{"day": day, "pairs": [], "mine_only": [], "engine_only": [],
                                                     "mine_r": net, "engine_r": 0.5}],
                                           "totals": {"mine_r": net, "engine_r": 0.5, "days_apart": 1,
                                                      "mine": 1, "engine": 1}}}
        j.save()
    text = write_report(tmp_path)
    assert (tmp_path / "REPORT.md").read_text(encoding="utf-8") == text
    assert "EURUSD" in text and "2026-09-29" in text and "2026-09-30" in text
    assert "2 sessions" in text and "50%" in text                         # the match rate over both sessions
    assert "+1.00R" in text and "+1.00R" in text                          # the trader's net R, and the engine's


def test_the_comparison_is_refused_while_the_session_is_blind(blind, tmp_path):  # noqa: F811
    blind.noculus = NoculusJournal(tmp_path / "EURUSD" / "s1.json", {"instrument": "EURUSD"})
    with pytest.raises(LookupError, match="leak"):                        # it would show the engine's arrays
        blind.comparison()
    blind.reveal(blind._keys[2])
    assert blind.comparison()["clock"] == blind._keys[2]


def test_the_page_carries_the_comparison_and_the_cli_writes_the_report():
    js = (STATIC / "noculus.js").read_text(encoding="utf-8")
    assert "/api/watch/noculus/comparison" in js and "You against the engine" in js and "nDiff" in js
    from algo_backtester.cli import parse_args
    args = parse_args(["noculus"])
    assert args.command == "noculus" and args.root is None


def test_a_blind_session_started_again_resumes_its_marks(setup, tmp_path):  # noqa: F811
    """A restart, or the session dropped from memory: starting it again picks up its journal."""
    root, snap = setup
    app = WatchApp(root / "base.toml", snap, (DAY, DAY + timedelta(days=1)), noculus_root=tmp_path, studies_root=root)
    app.start({"instrument": "EURUSD", "first_day": DAY.isoformat(), "days": 1, "blind": True})
    path = app.session.noculus.path
    app.session.noculus.data["marks"].append({"id": "m1", "tool": "FVG", "clock": 1, "deleted_at": None})
    app.session.noculus.save()
    again = WatchApp(root / "base.toml", snap, (DAY, DAY + timedelta(days=1)), noculus_root=tmp_path, studies_root=root)
    again.start({"instrument": "EURUSD", "first_day": DAY.isoformat(), "days": 1, "blind": True})
    assert again.session.noculus.path == path and [m["id"] for m in again.session.noculus.data["marks"]] == ["m1"]
    assert again.session.withheld                                        # never revealed: still blind


def test_a_session_revealed_once_stays_revealed_when_started_again(setup, tmp_path):  # noqa: F811
    """The engine can't be un-seen: a journal that holds a reveal opens revealed, and the marking stays shut."""
    root, snap = setup
    app = WatchApp(root / "base.toml", snap, (DAY, DAY + timedelta(days=1)), noculus_root=tmp_path, studies_root=root)
    app.start({"instrument": "EURUSD", "first_day": DAY.isoformat(), "days": 1, "blind": True})
    t = wall(app.session.start) + 3600
    app.session.noculus.data["reveal"] = {"t": t, "at": "2026-10-17T09:00:00+00:00"}
    app.session.noculus.save()
    again = WatchApp(root / "base.toml", snap, (DAY, DAY + timedelta(days=1)), noculus_root=tmp_path, studies_root=root)
    status = again.start({"instrument": "EURUSD", "first_day": DAY.isoformat(), "days": 1, "blind": True})
    assert status["revealed_at"] == t and not again.session.withheld
    with pytest.raises(LookupError, match="already revealed"):
        again.session.reveal(t + 60)


def test_no_new_marks_or_trades_after_the_reveal(blind, session, tmp_path):  # noqa: F811
    blind.noculus = NoculusJournal(tmp_path / "EURUSD" / "s1.json", {"instrument": "EURUSD"})
    mid = blind._keys[len(blind._keys) // 2]
    bid = float(session.bars.price_at(from_wall(mid)))
    placed = blind.place({"direction": "LONG", "kind": "MARKET", "stop": bid - 0.005, "target": bid + 0.005, "t": mid})
    blind.reveal(mid)
    bars = _bars(session, "H1")
    table, _ = _atlas(bars, "H1")
    third = next(wall(r.formed_at) for r in table.itertuples() if wall(r.formed_at) <= mid) - seconds_of("H1")
    with pytest.raises(LookupError, match="revealed"):
        blind.mark({"tool": "FVG", "tf": "H1", "t": mid, "candle": third})
    with pytest.raises(LookupError, match="revealed"):
        blind.place({"direction": "LONG", "kind": "MARKET", "stop": bid - 0.005, "target": bid + 0.005, "t": mid})
    with pytest.raises(LookupError, match="revealed"):
        blind.unmark({"id": "m1", "t": mid})
    later = mid + 3600
    rows = blind.trades({"t": later})                                     # a trade from before still plays out
    if rows[0]["state"] == "OPEN":
        assert blind.close_trade({"id": placed["id"], "t": later})["outcome"] == "MANUAL"   # and can be closed


# ── task 337: the trader's Fractal + POI indicator on Noculus (Requirements 21-23) ──
def test_the_session_serves_the_trader_s_indicator_at_the_clock(session):  # noqa: F811
    from algo_research.fractal_poi import FractalPOI, FractalSettings

    clock = wall(session.start) + 9 * 3600 + 5 * 60
    view = session.fractal({"tf": "M15", "t": clock, "s": "{}"})
    assert view["items"] and view["dashboard"]["htf1"] == "4H" and view["dashboard"]["asset"] == "EURUSD"
    assert all(wall(session.start) <= e["t"] <= clock for e in view["events"])          # the session's own, so far
    # the same chart candles as the page's, and nothing read from a candle that closes after the clock
    reader = next(r for k, r in session._fractal.items() if k[0] == "M15")
    shown = session.bars_until("M15", clock, None)
    closed = {b["time"]: b for b in shown if b["time"] + 900 <= clock}
    assert closed and all(reader.chart.time[i] not in closed or
                          (reader.chart.o[i], reader.chart.h[i], reader.chart.l[i], reader.chart.c[i]) ==
                          tuple(closed[reader.chart.time[i]][k] for k in ("open", "high", "low", "close"))
                          for i in range(reader.chart.n))
    m1 = session._m1("EURUSD", 120)
    cut = m1[wall_seconds(m1["time"]) + 60 <= clock]
    alone = FractalPOI(cut[cut["time"] >= reader_start(reader, m1)], "M15", FractalSettings(), "EURUSD").at(clock)
    assert alone["items"] == view["items"] and alone["dashboard"] == view["dashboard"]
    later = session.fractal({"tf": "M15", "t": clock + 900, "s": json.dumps({"bias": "Bearish"})})
    assert later["clock"] == clock + 900 and len(session._fractal) == 1     # a drawing input: the same reader


def reader_start(reader, m1):
    """The first M1 the session's reader holds (its warm-up start)."""
    return m1["time"].iloc[int(np.searchsorted(wall_seconds(m1["time"]), int(reader.chart.m1_wall[0])))]


def test_a_blind_session_serves_the_indicator_too(blind):
    view = blind.fractal({"tf": "H1", "t": wall(blind.start) + 6 * 3600})
    assert view["items"] and blind.withheld                                  # the trader's tool, not the engine's


def test_the_indicator_endpoints(setup, tmp_path):  # noqa: F811
    import threading
    import time
    import urllib.error
    import urllib.parse
    import urllib.request

    from algo_backtester.watch import make_watch_server

    root, snap = setup
    app = WatchApp(root / "base.toml", snap, (DAY, DAY + timedelta(days=1)), noculus_root=tmp_path, studies_root=root)
    server = make_watch_server(app, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    try:
        defaults = call("/api/watch/fractal-defaults")
        assert defaults["settings"]["fractal_mode"] == "Automatic" and "bias" in defaults["draw_only"]
        call("/api/watch/start", {"instrument": "EURUSD", "first_day": DAY.isoformat(), "days": 1, "blind": True})
        for _ in range(600):
            if call("/api/watch/status")["state"] == "ready":
                break
            time.sleep(0.2)
        t = wall(app.session.start) + 4 * 3600
        q = urllib.parse.quote(json.dumps({"fractal_mode": "Scalp"}))
        view = call(f"/api/watch/fractal?tf=M5&t={t}&s={q}")
        assert view["dashboard"]["htf1"] == "15m" and view["clock"] == t
        with pytest.raises(urllib.error.HTTPError) as bad:
            call(f"/api/watch/fractal?tf=M5&t={t}&s={urllib.parse.quote(json.dumps({'max_display': 1}))}")
        assert bad.value.code == 400 and "max_display" in json.loads(bad.value.read())["error"]
    finally:
        server.shutdown()


def test_the_page_carries_the_indicator_layer():
    page = (STATIC / "engine.html").read_text(encoding="utf-8")
    script = (STATIC / "engine.js").read_text(encoding="utf-8")
    assert '<script src="/static/fractal.js"></script>' in page and 'id="fractal"' in page
    assert '["fractal", "Fractal + POI"]' in script and "fractal.tick()" in script
