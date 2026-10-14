"""
Tests for algo_research/replay/ — the blind replay (market-narrative Requirement 10).

Tasks 299 and 300 (.kiro/specs/market-narrative/tasks.md). A synthetic gold-like
instrument: one M1 random walk, trading Sunday 18:00 to Friday 17:00 New York with
the daily 17:00-18:00 break, so trading days, the as-of chart, the reads and their
scores are checked without the snapshot.
Validates: Requirements 10.1-10.9 (.kiro/specs/market-narrative/requirements.md)
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
from algo_research.replay.server import ReplayApp, make_server
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
        assert not seen.empty
        pd.testing.assert_frame_equal(seen, other.as_of(tf, t))
        assert (seen["time"] < t).all()


def test_forming_bar_is_built_from_closed_m1_and_becomes_the_closed_bar():
    t = pd.Timestamp("2025-01-10 09:37", tz=NY).tz_convert("UTC")
    h1 = bars().as_of(TF.H1, t)
    forming = h1.iloc[-1]
    assert forming["time"] == pd.Timestamp("2025-01-10 09:00", tz=NY) and forming["close_time"] > t
    m1 = synthetic_m1()
    inside = m1[(m1["time"] >= forming["time"]) & (m1["time"] + pd.Timedelta(minutes=1) <= t)]
    assert (forming["open"], forming["high"], forming["low"], forming["close"]) == (
        inside["open"].iloc[0], inside["high"].max(), inside["low"].min(), inside["close"].iloc[-1])
    full = bars().as_of(TF.H1, pd.Timestamp("2025-01-10 10:00", tz=NY).tz_convert("UTC")).iloc[-1]
    assert full["time"] == forming["time"] and full["close_time"] == pd.Timestamp("2025-01-10 10:00", tz=NY)
    assert full["high"] >= forming["high"] and full["open"] == forming["open"]


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
    assert pd.Timestamp(j.advance(step="M15")["revealed_until"]) == open_ + pd.Timedelta(minutes=15)
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
        status, state = call(base, "/api/state")
        assert status == 200 and state["status"] == "READING" and state["date"] is None and state["weekday"]
        open_epoch = state["revealed_until_epoch"]
        status, h1 = call(base, "/api/bars?tf=H1")
        assert status == 200 and h1["bars"] and max(b["time"] for b in h1["bars"]) < open_epoch
        assert call(base, "/api/bars?tf=H7")[0] == 400
        price = state["open_price"]
        assert call(base, "/api/read", {"bias": "BULLISH", "draw": price + 4, "invalidation": price - 4})[0] == 200
        status, again = call(base, "/api/read", {"bias": "BEARISH", "draw": price - 4, "invalidation": price + 4})
        assert status == 409 and again["error"]
        assert call(base, "/api/advance", {"to": "09:30"})[0] == 200
        status, now = call(base, "/api/state")
        assert call(base, "/api/trade", {"direction": "LONG", "entry": now["price"], "stop": now["price"] - 3,
                                         "target": now["price"] + 9})[0] == 200
        status, revealed = call(base, "/api/reveal", {})
        assert status == 200 and revealed["date"] and revealed["scores"]["thesis"]["outcome"]
        status, summary = call(base, "/api/summary")
        assert status == 200 and summary["revealed"] == 1
        status, nxt = call(base, "/api/next", {})
        assert status == 200 and nxt["status"] == "READING" and nxt["date"] is None
        status, page = 200, urllib.request.urlopen(base + "/", timeout=10).read().decode()
        assert "lightweight-charts@4.2.0" in page
    finally:
        server.shutdown()
        server.server_close()
