"""
Tests for algo_research/replay/ — the blind replay (market-narrative Requirement 10).

Tasks 299, 300 and 302-303 (.kiro/specs/market-narrative/tasks.md). A synthetic gold-like
instrument: one M1 random walk, trading Sunday 18:00 to Friday 17:00 New York with
the daily 17:00-18:00 break, so trading days, the as-of chart, the reads and their
scores are checked without the snapshot.
Validates: Requirements 10.1-10.9, 11.1-11.6 (.kiro/specs/market-narrative/requirements.md)
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd
import pytest

from algo_research.replay.bars import ReplayBars
from algo_research.replay.journal import Journal, ReplayError, day_order
from algo_research.replay.scoring import score_thesis, score_trade, summarize
from algo_research.frame import aggregate_frame
from algo_research.replay.server import ReplayApp, make_server
from algo_research.replay.timeframes import bucket, wall_seconds
from liquidity_engine.models import Timeframe as TF

NY = "America/New_York"
FIRST, END = date(2025, 1, 7), date(2025, 1, 18)        # trading dates offered: Tue 7 to Fri 17 January


@lru_cache(maxsize=None)
def synthetic_m1(seed: int = 3) -> pd.DataFrame:
    wall = pd.date_range("2024-11-03 18:00", "2025-01-17 17:00", freq="1min", tz=NY, inclusive="left")
    closed = ((wall.weekday == 5) | ((wall.weekday == 4) & (wall.hour >= 17)) | ((wall.weekday == 6) & (wall.hour < 18))
              | (wall.hour == 17))
    times = wall[~closed].tz_convert("UTC")
    rng = np.random.default_rng(seed)
    close = 2650 + np.cumsum(rng.normal(0, 0.4, len(times)))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"time": times, "open": open_,
                         "high": np.maximum(open_, close) + rng.random(len(times)) * 0.3,
                         "low": np.minimum(open_, close) - rng.random(len(times)) * 0.3, "close": close})


@lru_cache(maxsize=None)
def bars() -> ReplayBars:
    return ReplayBars(synthetic_m1(), "XAUUSD")


def journal(tmp_path, days=None) -> Journal:
    return Journal(tmp_path, bars(), days if days is not None else bars().trading_dates(FIRST, END))


def bullish_read(j: Journal, **change) -> dict:
    price = j.current()["open_price"]
    return {"bias": "BULLISH", "draw": price + 5, "invalidation": price - 5, "confidence": 2, **change}


# ── as-of bars (10.2, 10.4) ─────────────────────────────────────────────────

def test_trading_dates_are_weekdays_with_m1():
    days = bars().trading_dates(FIRST, END)
    assert days[0] == date(2025, 1, 7) and days[-1] == date(2025, 1, 17)
    assert all(d.weekday() < 5 for d in days) and len(days) == 9


def wall(ny: str) -> int:
    return int(wall_seconds([pd.Timestamp(ny, tz=NY).tz_convert("UTC")])[0])


@pytest.mark.parametrize("until", ["2025-01-09 17:00", "2025-01-10 09:37", "2025-01-12 17:00", "2025-01-13 18:00"])
def test_as_of_never_shows_later_prices(until):
    """Every M1 bar that closes after `until` gets new prices: what the chart shows doesn't move."""
    t = pd.Timestamp(until, tz=NY).tz_convert("UTC")
    m1 = synthetic_m1()
    later = m1["time"] + pd.Timedelta(minutes=1) > t
    changed = m1.copy()
    changed.loc[later, ["open", "high", "low", "close"]] += 50.0
    other = ReplayBars(changed, "XAUUSD")
    for tf in ReplayBars.TIMEFRAMES:
        seen = bars().as_of(tf, t)
        assert not seen.empty, tf
        pd.testing.assert_frame_equal(seen, other.as_of(tf, t))
        assert (seen["time"] < wall(until)).all()


def test_forming_bar_is_built_from_closed_m1_and_becomes_the_closed_bar():
    t = pd.Timestamp("2025-01-10 09:37", tz=NY).tz_convert("UTC")
    forming = bars().as_of("H1", t).iloc[-1]
    assert forming["time"] == wall("2025-01-10 09:00")
    m1 = synthetic_m1()
    start = pd.Timestamp("2025-01-10 09:00", tz=NY)
    inside = m1[(m1["time"] >= start) & (m1["time"] + pd.Timedelta(minutes=1) <= t)]
    assert (forming["open"], forming["high"], forming["low"], forming["close"]) == (
        inside["open"].iloc[0], inside["high"].max(), inside["low"].min(), inside["close"].iloc[-1])
    full = bars().as_of("H1", pd.Timestamp("2025-01-10 10:00", tz=NY).tz_convert("UTC")).iloc[-1]
    assert full["time"] == forming["time"] and full["high"] >= forming["high"] and full["open"] == forming["open"]


@pytest.mark.parametrize("tf, at, start", [
    ("H4", "2025-01-09 18:30", "2025-01-09 17:00"), ("H4", "2025-01-10 02:15", "2025-01-10 01:00"),
    ("H4", "2025-01-10 09:59", "2025-01-10 09:00"), ("H4", "2025-01-10 13:00", "2025-01-10 13:00"),
    ("H7", "2025-01-09 23:59", "2025-01-09 17:00"), ("H7", "2025-01-10 00:30", "2025-01-10 00:00"),
    ("H7", "2025-01-10 16:59", "2025-01-10 14:00"), ("H12", "2025-01-10 04:59", "2025-01-09 17:00"),
    ("H12", "2025-01-10 05:00", "2025-01-10 05:00"), ("M45", "2025-01-09 17:44", "2025-01-09 17:00"),
    ("M45", "2025-01-09 18:31", "2025-01-09 18:30"), ("M20", "2025-01-10 09:59", "2025-01-10 09:40"),
    ("D1", "2025-01-10 16:59", "2025-01-09 17:00"), ("D1", "2025-01-10 17:00", "2025-01-10 17:00"),
    ("W1", "2025-01-08 10:00", "2025-01-05 17:00"), ("W1", "2025-01-12 18:00", "2025-01-12 17:00"),
    ("MN1", "2025-02-03 10:00", "2025-01-31 17:00"), ("MN1", "2025-01-30 10:00", "2024-12-31 17:00"),
])
def test_timeframes_are_anchored_at_the_new_york_open(tf, at, start):
    assert bucket(np.array([wall(at)]), tf)[0] == wall(start)


@pytest.mark.parametrize("tf", ["M5", "M15", "H1", "H4", "D1"])
def test_bars_match_the_strategy_calendar(tf):
    """Where the engine's calendar has the timeframe, the chart's bars are the same bars."""
    until = pd.Timestamp("2025-01-17 17:00", tz=NY).tz_convert("UTC")
    seen = bars().as_of(tf, until, limit=5000)
    research = aggregate_frame(bars().m1, TF(tf), as_of=until)
    research = research.assign(time=wall_seconds(research["time"]))[["time", "open", "high", "low", "close"]]
    both = seen.merge(research, on="time", suffixes=("", "_r"))
    assert len(both) >= min(len(seen), len(research)) - 1 and len(both) > 10
    for col in ("open", "high", "low", "close"):
        assert np.allclose(both[col], both[col + "_r"]), col


def test_since_returns_the_bar_holding_it_and_later():
    t = pd.Timestamp("2025-01-10 09:37", tz=NY).tz_convert("UTC")
    full = bars().as_of("M15", t)
    tail = bars().as_of("M15", t, since=wall("2025-01-10 09:05"))
    assert list(tail["time"]) == [wall("2025-01-10 09:00"), wall("2025-01-10 09:15"), wall("2025-01-10 09:30")]
    pd.testing.assert_frame_equal(tail, full.tail(3).reset_index(drop=True))


# ── the journal's rules (10.1, 10.3-10.6, 10.8) ─────────────────────────────

def test_days_are_shuffled_with_a_fixed_seed():
    days = bars().trading_dates(FIRST, END)
    assert day_order(days, "XAUUSD") == day_order(days, "XAUUSD")
    assert sorted(day_order(days, "XAUUSD")) == days and day_order(days, "XAUUSD") != days


def test_a_day_starts_reading_at_its_open_with_the_date_hidden(tmp_path):
    day = journal(tmp_path).current()
    assert day["status"] == "READING" and day["revealed_until"] == day["open_time"]
    open_ = pd.Timestamp(day["open_time"])
    assert open_.tz_convert(NY).hour == 17
    assert day["open_price"] == bars().price_at(open_)


@pytest.mark.parametrize("change, field", [
    ({"bias": "SIDEWAYS"}, "bias"),
    ({"draw": None}, "draw"),
    ({"invalidation": "x"}, "invalidation"),
    ({"draw": -1.0}, "draw"),                        # a bullish draw below the open
    ({"confidence": 4}, "confidence"),
    ({"array_low": 1.0, "array_high": 0.5}, "array"),
    ({"array_low": 1.0, "array_high": 2.0, "array_tf": "M7"}, "array_tf"),
])
def test_reads_that_break_the_rules_are_refused_naming_the_field(tmp_path, change, field):
    j = journal(tmp_path)
    read = bullish_read(j)
    if change.get("draw") == -1.0:
        change = {"draw": read["invalidation"] - 1}
    with pytest.raises(ReplayError, match=f"^{field}"):
        j.save_read({**read, **change})
    assert j.current()["status"] == "READING"


def test_a_no_thesis_read_needs_no_levels(tmp_path):
    j = journal(tmp_path)
    saved = j.save_read({"bias": "NO_THESIS", "draw": 1.0, "note": "inside day, nothing clean"})
    assert saved["status"] == "INTRADAY"
    assert saved["read"]["draw"] is None and saved["read"]["note"] == "inside day, nothing clean"


def test_the_read_is_locked_once_saved_and_nothing_is_accepted_after_the_reveal(tmp_path):
    j = journal(tmp_path)
    with pytest.raises(ReplayError, match="read"):
        j.reveal()                                   # a day needs a read, even NO_THESIS
    j.save_read(bullish_read(j))
    with pytest.raises(ReplayError):
        j.save_read(bullish_read(j))
    j.reveal()
    for write in (lambda: j.save_read(bullish_read(j)), lambda: j.advance(step="M5"),
                  lambda: j.mark_trade({"direction": "LONG", "entry": 1, "stop": 0, "target": 2}), j.reveal):
        with pytest.raises(ReplayError):
            write()


def test_time_only_moves_forward_and_stops_at_the_close(tmp_path):
    j = journal(tmp_path)
    j.save_read(bullish_read(j))
    open_ = pd.Timestamp(j.current()["open_time"])
    # gold pauses 17:00-18:00: a step into the pause lands that step past the reopen
    assert pd.Timestamp(j.advance(step="M15")["revealed_until"]) == open_ + pd.Timedelta(hours=1, minutes=15)
    assert pd.Timestamp(j.advance(step="M15")["revealed_until"]) == open_ + pd.Timedelta(hours=1, minutes=30)
    at = pd.Timestamp(j.advance(to="09:30")["revealed_until"]).tz_convert(NY)
    assert (at.hour, at.minute) == (9, 30) and at > open_
    with pytest.raises(ReplayError, match="past"):
        j.advance(to="03:00")
    close = pd.Timestamp(j.current()["close_time"])
    while pd.Timestamp(j.current()["revealed_until"]) < close:
        j.advance(step="H1")
    assert pd.Timestamp(j.current()["revealed_until"]) == close
    with pytest.raises(ReplayError, match="close"):
        j.advance(step="M1")
    with pytest.raises((ReplayError, ValueError)):
        j.advance(step="H7")


def test_trades_are_marked_at_the_revealed_time_and_checked(tmp_path):
    j = journal(tmp_path)
    j.save_read(bullish_read(j))
    j.advance(to="08:00")
    price = j.current()["price"]
    with pytest.raises(ReplayError, match="stop"):
        j.mark_trade({"direction": "LONG", "entry": price, "stop": price + 2, "target": price + 6})
    day = j.mark_trade({"direction": "LONG", "entry": price, "stop": price - 2, "target": price + 6})
    assert day["trades"][0]["marked_at"] == day["revealed_until"]
    for _ in range(2):
        j.mark_trade({"direction": "SHORT", "entry": price, "stop": price + 2, "target": price - 6})
    with pytest.raises(ReplayError, match="three"):
        j.mark_trade({"direction": "SHORT", "entry": price, "stop": price + 2, "target": price - 6})


def test_days_are_stored_resumed_and_skipped_once_revealed(tmp_path):
    j = journal(tmp_path)
    first = j.current()
    j.save_read(bullish_read(j))
    again = journal(tmp_path)                         # the server restarted mid-day
    assert again.current()["trading_date"] == first["trading_date"] and again.current()["status"] == "INTRADAY"
    again.reveal()
    stored = json.loads((tmp_path / "XAUUSD" / f"{first['trading_date']}.json").read_text(encoding="utf-8"))
    assert stored["status"] == "REVEALED" and stored["read"]["written_at"] and stored["revealed_at"]
    assert not list((tmp_path / "XAUUSD").glob("*.tmp"))
    third = journal(tmp_path)
    assert third.current()["trading_date"] != first["trading_date"]
    assert third.remaining() == len(bars().trading_dates(FIRST, END)) - 1



def box(id_="b1", **change) -> dict:
    return {"id": id_, "type": "rect", "points": [{"t": 1736460000, "p": 2650.5}, {"t": 1736463600, "p": 2648.0}],
            "kind": "FVG", "tf": "H1", "mid": True, **change}


def test_drawings_are_checked(tmp_path):
    j = journal(tmp_path)
    for bad, field in ((dict(type="circle"), "type"), (dict(points=[{"t": 1, "p": 2}]), "point"),
                       (dict(points=[{"t": "x", "p": 2}, {"t": 1, "p": 2}]), "point"), (dict(id=""), "id")):
        with pytest.raises(ReplayError, match=field):
            j.save_drawings([box(**bad)])
    with pytest.raises(ReplayError, match="twice"):
        j.save_drawings([box(), box()])
    saved = j.save_drawings([box(note="dropped", status="client only")])["drawings"][0]
    assert "note" not in saved and "status" not in saved and saved["kind"] == "FVG"



def test_drawings_take_a_style_coloured_levels_and_freehand_paths(tmp_path):
    """Update 2026-10-14c: every tool keeps its own look; fib levels carry colours; a brush is a path."""
    j = journal(tmp_path)
    fib = {"id": "f1", "type": "fib", "points": [{"t": 1, "p": 2660.0}, {"t": 2, "p": 2650.0}],
           "levels": [1, {"value": -2.5, "color": "#16a34a", "visible": False}],
           "style": {"color": "#2563eb", "width": 2, "dash": "dotted", "extendRight": True, "fontSize": None}}
    path = {"id": "p1", "type": "path", "points": [{"t": i, "p": 2650.0 + i} for i in range(50)], "locked": True}
    ext = {"id": "x1", "type": "fibext", "points": [{"t": 1, "p": 1.0}, {"t": 2, "p": 2.0}, {"t": 3, "p": 1.5}]}
    saved = {d["id"]: d for d in j.save_drawings([fib, path, ext])["drawings"]}
    assert saved["f1"]["levels"] == [1.0, {"value": -2.5, "color": "#16a34a", "visible": False}]
    assert saved["f1"]["style"] == fib["style"] and saved["p1"]["locked"] is True and len(saved["p1"]["points"]) == 50
    for bad, field in (({**fib, "style": {"nested": {"a": 1}}}, "style"), ({**fib, "levels": [{"color": "red"}]}, "level"),
                       ({**path, "points": path["points"][:1]}, "2 to 400"),
                       ({**fib, "style": {f"k{i}": 1 for i in range(40)}}, "style")):
        with pytest.raises(ReplayError, match=field):
            j.save_drawings([bad])

def test_drawings_keep_the_phase_and_time_they_were_made_in(tmp_path):
    j = journal(tmp_path)
    j.save_drawings([box("read-box")])
    j.save_read(bullish_read(j))
    day = j._current()
    assert [d["id"] for d in day["read"]["drawings"]] == ["read-box"]          # the read keeps the chart as it was
    j.advance(to="08:00")
    at_eight = j._current()["revealed_until"]
    j.save_drawings([box("read-box", p=1), box("later", kind="OB")])
    stored = {d["id"]: d for d in j._current()["drawings"]}
    assert stored["read-box"]["phase"] == "read" and "edited_at" not in stored["read-box"]
    assert stored["later"]["phase"] == "intraday" and stored["later"]["created_at"] == at_eight
    moved = box("read-box", points=[{"t": 1736460000, "p": 2651.0}, {"t": 1736463600, "p": 2648.0}])
    j.save_drawings([moved, box("later", kind="OB")])
    stored = {d["id"]: d for d in j._current()["drawings"]}
    assert stored["read-box"]["phase"] == "read" and stored["read-box"]["edited_phase"] == "intraday"
    assert [d["id"] for d in j._current()["read"]["drawings"]] == ["read-box"]
    assert j._current()["read"]["drawings"][0]["points"][0]["p"] == 2650.5       # the read's copy didn't move
    j.reveal()
    j.save_drawings([moved, box("later", kind="OB"), box("after")])
    stored = {d["id"]: d for d in j._current()["drawings"]}
    assert stored["after"]["phase"] == "narrative"
    assert {d["id"] for d in j._current()["drawings_at_reveal"]} == {"read-box", "later"}


def test_the_narrative_is_written_after_the_reveal(tmp_path):
    j = journal(tmp_path)
    with pytest.raises(ReplayError):
        j.save_narrative("too early")
    j.save_read(bullish_read(j))
    j.reveal()
    assert j.save_narrative("London took the Asian low, NY expanded to PDH")["narrative_note"].startswith("London")


def test_trades_are_followed_live(tmp_path):
    j = journal(tmp_path)
    j.save_read(bullish_read(j))
    j.advance(to="08:00")
    price = j.current()["price"]
    j.mark_trade({"direction": "LONG", "entry": price - 50, "stop": price - 60, "target": price - 40, "drawing": "pos1"})
    j.mark_trade({"direction": "LONG", "entry": price, "stop": price - 3, "target": price + 900})
    assert j._current()["trades"][0]["drawing"] == "pos1"
    j.advance(step="H1")
    live = j.live_trades()
    assert live[0]["outcome"] == "PENDING"                                       # 50 below: not reached in an hour
    assert live[1]["outcome"] in ("OPEN", "STOP")
    if live[1]["outcome"] == "OPEN":
        assert live[1]["r"] == pytest.approx((j.current()["price"] - price) / 3)

# ── scores (10.7, 10.9) ─────────────────────────────────────────────────────

def rows(*hl) -> pd.DataFrame:
    t = pd.date_range("2025-01-10 14:00", periods=len(hl), freq="1min", tz="UTC")
    high = [h for h, _ in hl]
    low = [lo for _, lo in hl]
    return pd.DataFrame({"time": t, "open": low, "high": high, "low": low, "close": [(h + lo) / 2 for h, lo in hl]})


def test_thesis_outcomes_and_p_coin():
    read = {"bias": "BULLISH", "draw": 110.0, "invalidation": 95.0}
    assert score_thesis(read, rows((105, 99), (110, 104)), 100.0)["outcome"] == "DRAW"
    assert score_thesis(read, rows((105, 95), (110, 104)), 100.0)["outcome"] == "INVALIDATED"
    assert score_thesis(read, rows((111, 94)), 100.0)["outcome"] == "INVALIDATED"       # one bar: the stop wins
    assert score_thesis(read, rows((105, 99)), 100.0)["outcome"] == "NEITHER"
    assert score_thesis(read, rows((105, 99)), 100.0)["p_coin"] == pytest.approx(5 / 15)
    bearish = {"bias": "BEARISH", "draw": 90.0, "invalidation": 104.0}
    assert score_thesis(bearish, rows((103, 95), (101, 90)), 100.0)["outcome"] == "DRAW"
    assert score_thesis({"bias": "NO_THESIS"}, rows((105, 99)), 100.0)["outcome"] == "NO_THESIS"


def test_trade_outcomes_in_r():
    long = {"direction": "LONG", "entry": 100.0, "stop": 98.0, "target": 106.0}
    assert score_trade(long, rows((103, 101), (102, 101)))["outcome"] == "NOT_FILLED"
    target = score_trade(long, rows((101, 99.5), (104, 100), (107, 103)))
    assert (target["outcome"], target["r"]) == ("TARGET", pytest.approx(3.0))
    assert score_trade(long, rows((101, 97)))["outcome"] == "STOP"                     # stop counts from the fill bar
    assert score_trade(long, rows((107, 99.5)))["outcome"] == "OPEN"                   # the target only from the next
    assert score_trade(long, rows((101, 99.5), (107, 97)))["outcome"] == "STOP"        # a tie goes to the stop
    open_ = score_trade(long, rows((101, 99.5), (103, 101)))
    assert open_["outcome"] == "OPEN" and open_["r"] == pytest.approx((102 - 100) / 2)
    short = {"direction": "SHORT", "entry": 100.0, "stop": 101.0, "target": 97.0}
    assert score_trade(short, rows((100.5, 99), (99, 96.5)))["r"] == pytest.approx(3.0)


def test_the_reveal_scores_the_day_and_gives_its_narrative(tmp_path):
    j = journal(tmp_path)
    j.save_read(bullish_read(j))
    j.advance(to="08:00")
    price = j.current()["price"]
    j.mark_trade({"direction": "LONG", "entry": price, "stop": price - 3, "target": price + 9})
    day = j.reveal()
    assert day["status"] == "REVEALED" and day["revealed_until"] == day["close_time"]
    assert day["scores"]["thesis"]["outcome"] in ("DRAW", "INVALIDATED", "NEITHER")
    assert day["scores"]["trades"][0]["outcome"] in ("TARGET", "STOP", "OPEN", "NOT_FILLED")
    assert day["narrative"]["direction"] in ("UP", "DOWN", "FLAT")
    assert day["scores"]["thesis"]["direction_right"] == (day["narrative"]["direction"] == "UP")


def test_summary_counts_and_rates():
    def day(d, bias, outcome, p, r=None):
        trades = [] if r is None else [{"outcome": "TARGET" if r > 0 else "STOP", "r": r}]
        return {"status": "REVEALED", "trading_date": d, "read": {"bias": bias},
                "scores": {"thesis": {"outcome": outcome, "p_coin": p, "direction_right": outcome == "DRAW"},
                           "trades": trades}}
    records = [day("2025-01-07", "BULLISH", "DRAW", 0.5, 3.0), day("2025-01-08", "BEARISH", "INVALIDATED", 0.4, -1.0),
               day("2025-01-09", "BULLISH", "DRAW", 0.3), day("2025-01-10", "NO_THESIS", "NO_THESIS", None),
               {"status": "INTRADAY", "trading_date": "2025-01-13", "read": {"bias": "BULLISH"}}]
    s = summarize(records)
    assert (s["revealed"], s["thesis_days"], s["no_thesis_days"]) == (4, 3, 1)
    assert s["draw_rate"] == pytest.approx(2 / 3) and s["mean_p_coin"] == pytest.approx(0.4)
    assert s["draw_interval"][0] <= s["draw_rate"] <= s["draw_interval"][1]
    assert (s["trades"], s["mean_r"], s["total_r"]) == (2, pytest.approx(1.0), pytest.approx(2.0))


# ── the server (10.1-10.6, 10.9) ────────────────────────────────────────────

def call(base: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_http_round_trip(tmp_path):
    server = make_server(ReplayApp(journal(tmp_path)), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, meta = call(base, "/api/meta")
        assert status == 200 and [t["tf"] for t in meta["timeframes"]][:3] == ["M1", "M2", "M3"]
        assert {"H7", "M45", "M20", "M4", "MN1"} <= {t["tf"] for t in meta["timeframes"]}
        status, state = call(base, "/api/state")
        assert status == 200 and state["status"] == "READING" and state["date"] is None and state["weekday"]
        open_epoch = state["revealed_until_epoch"]
        for tf in ("H7", "M45", "M2", "W1"):
            status, got = call(base, f"/api/bars?tf={tf}")
            assert status == 200 and got["bars"] and max(b["time"] for b in got["bars"]) < open_epoch, tf
        assert call(base, "/api/bars?tf=H5")[0] == 400
        status, saved = call(base, "/api/drawings", {"drawings": [box()]})
        assert status == 200 and saved["drawings"][0]["phase"] == "read" and "created_at" not in saved["drawings"][0]
        price = state["open_price"]
        assert call(base, "/api/read", {"bias": "BULLISH", "draw": price + 4, "invalidation": price - 4})[0] == 200
        status, again = call(base, "/api/read", {"bias": "BEARISH", "draw": price - 4, "invalidation": price + 4})
        assert status == 409 and again["error"]
        status, bars_m5 = call(base, "/api/bars?tf=M5")
        status, moved = call(base, "/api/advance", {"step": "M1", "tf": "M5", "since": bars_m5["bars"][-1]["time"]})
        assert status == 200 and len(moved["update"]["m1"]) == 1 and moved["update"]["bars"]
        assert moved["update"]["m1"][0]["time"] == open_epoch + 3600              # gold reopens at 18:00
        assert call(base, "/api/advance", {"to": "09:30"})[0] == 200
        status, now = call(base, "/api/state")
        assert call(base, "/api/trade", {"direction": "LONG", "entry": now["price"], "stop": now["price"] - 3,
                                         "target": now["price"] + 9})[0] == 200
        status, now = call(base, "/api/state")
        assert now["trades"][0]["live"]["outcome"] in ("PENDING", "OPEN", "STOP", "TARGET")
        status, revealed = call(base, "/api/reveal", {})
        assert status == 200 and revealed["date"] and revealed["scores"]["thesis"]["outcome"]
        assert call(base, "/api/narrative", {"text": "it delivered"})[1]["narrative_note"] == "it delivered"
        status, summary = call(base, "/api/summary")
        assert status == 200 and summary["revealed"] == 1
        status, nxt = call(base, "/api/next", {})
        assert status == 200 and nxt["status"] == "READING" and nxt["date"] is None and nxt["drawings"] == []
        page = urllib.request.urlopen(base + "/", timeout=10).read().decode()
        assert "lightweight-charts@4.2.0" in page and "/static/app.js" in page
        for name in ("app.js", "drawings.js", "settings.js", "app.css"):
            assert urllib.request.urlopen(f"{base}/static/{name}", timeout=10).status == 200
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(f"{base}/static/../journal.py", timeout=10)
    finally:
        server.shutdown()
        server.server_close()
