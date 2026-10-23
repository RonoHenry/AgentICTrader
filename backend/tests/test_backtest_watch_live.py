"""
Tests for a live Noculus session (algo-backtester update 2026-10-22): the broker's terminal instead of the snapshot.

Task 352 (.kiro/specs/algo-backtester/tasks.md). The task 186 fixture month stands in for the terminal: a fake
``Rates`` serves it, and a clock the test moves decides which minutes have closed. Nothing here touches MT5.
Validates: Requirements 27.1-27.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

import algo_backtester.watch as watch
from algo_backtester.live import COLUMNS, LiveSource
from algo_backtester.watch import SnapshotSource, WatchApp, WatchSession, live_first_day, wall
from algo_research.replay.charts import ChartsApp
from liquidity_engine.models import Timeframe as TF
from tests.test_backtest_watch import CONFIG, setup  # noqa: F401  (fixture: the EURUSD fixture month as a snapshot)

UTC = timezone.utc


class FakeTerminal:
    """``Rates`` over the fixture snapshot: every bar opening in [start, end), forming ones too, as a terminal
    returns them. It keeps each request."""

    def __init__(self, snap):
        self.frame = SnapshotSource(snap)._frame("EURUSD")
        self.calls = []

    def quote(self, instrument):
        """The last tick: the last bar opened by the clock's close as the bid, a 2-point spread."""
        bar = self.frame[self.frame["time"] <= pd.Timestamp(self.clock[0])].iloc[-1]
        return self.clock[0], float(bar["close"]), float(bar["close"]) + 0.0002

    def __call__(self, instrument, tf, start, end):
        self.calls.append((instrument, tf, start, end))
        if instrument != "EURUSD" or tf != TF.M1:
            return pd.DataFrame(columns=COLUMNS)
        f = self.frame
        return f[(f["time"] >= pd.Timestamp(start)) & (f["time"] < pd.Timestamp(end))][COLUMNS].reset_index(drop=True)


@pytest.fixture
def live(setup):  # noqa: F811
    root, snap = setup
    # A study whose hold-out has already begun: a replay of these days is refused, a live session is not (D40).
    (root / "live.toml").write_text(CONFIG.replace('study = "watch-test"', 'study = "live-test"'), encoding="utf-8")
    (root / "config" / "backtests" / "studies" / "live-test.toml").write_text(
        "holdout_start = 2026-09-01\ncreated_from_data_end = 2026-09-30\n", encoding="utf-8")
    clock = [datetime(2026, 9, 30, 10, 0, 30, tzinfo=UTC)]
    terminal = FakeTerminal(snap)
    terminal.clock = clock
    source = LiveSource(terminal, ["EURUSD"], history=timedelta(days=40), now=lambda: clock[0])
    return root, snap, clock, terminal, source


def test_a_live_source_serves_closed_minutes_and_tops_up(live):
    _, snap, clock, terminal, source = live
    frame = source._frame("EURUSD")
    assert frame["time"].iloc[-1] == pd.Timestamp("2026-09-30 09:59", tz="UTC")     # 10:00 closes at 10:01
    assert frame["time"].iloc[0] >= pd.Timestamp(clock[0]) - pd.Timedelta(days=40)
    asked = (datetime(2026, 9, 30, 8, tzinfo=UTC), datetime(2026, 9, 30, 9, tzinfo=UTC))
    assert source.bars("EURUSD", TF.M1, *asked) == SnapshotSource(snap).bars("EURUSD", TF.M1, *asked) != []
    assert source.held() == ["EURUSD"] and source.last_time("EURUSD", TF.M1) == datetime(2026, 9, 30, 9, 59, tzinfo=UTC)

    clock[0] = datetime(2026, 9, 30, 10, 15, tzinfo=UTC)
    assert source.refresh("EURUSD") == 15                                            # 10:00 to 10:14
    assert terminal.calls[-1][2] == datetime(2026, 9, 30, 10, 0, tzinfo=UTC)         # only from the last one held
    assert source.refresh("EURUSD") == 0 and source._frame("EURUSD")["time"].is_unique

    empty = LiveSource(lambda *a: pd.DataFrame(columns=COLUMNS), ["XAUUSD"], now=lambda: clock[0])
    assert empty._frame("XAUUSD").empty and empty.last_time("XAUUSD", TF.M1) is None


@pytest.mark.parametrize("now, days, first", [
    ("2026-10-22 12:00", 1, date(2026, 10, 22)),        # Thursday
    ("2026-10-22 12:00", 3, date(2026, 10, 20)),
    ("2026-10-22 21:30", 1, date(2026, 10, 23)),        # 17:30 New York: Friday's trading date has begun
    ("2026-10-24 12:00", 1, date(2026, 10, 23)),        # Saturday: Friday's
    ("2026-10-26 10:00", 2, date(2026, 10, 23)),        # Monday and the Friday before
])
def test_a_live_window_ends_at_todays_trading_date(now, days, first):
    assert live_first_day(pd.Timestamp(now, tz="UTC").to_pydatetime(), days) == first


def _ready(app_or_session, timeout=120):
    stop = time.time() + timeout
    session = getattr(app_or_session, "session", app_or_session)
    while session.state == "preparing" and time.time() < stop:
        time.sleep(0.2)
    assert session.state == "ready", session.message
    return session


def test_a_live_session_follows_the_clock_and_reads_only_the_new_closes(live, monkeypatch):
    root, snap, clock, _, source = live
    read = []
    signals_at = watch.signals_at
    monkeypatch.setattr(watch, "signals_at", lambda data, cfgs, t, *a: read.append(t) or signals_at(data, cfgs, t, *a))
    app = WatchApp(root / "live.toml", snap, (date(2026, 9, 28), date(2026, 10, 3)), noculus_root=root / "noculus",
                   studies_root=root, live=lambda: source)
    assert app.meta()["live"] is True
    status = app.start({"instrument": "EURUSD", "days": 1, "variant": "base", "live": True})
    assert status["live"] is True and status["first_day"] == "2026-09-30"          # today's trading date
    session = _ready(app)
    ten = wall(pd.Timestamp("2026-09-30 10:00", tz="UTC"))
    assert session.status()["end"] == ten and max(session.states) == ten            # nothing after the clock
    assert session.bars_until("M1", ten + 86400, None)[-1]["time"] == ten - 60
    assert session.noculus.path.name == "live-2026-09-30-1d-base-open.json"
    assert session.model_a and session.journal
    first, version = len(read), session.version

    clock[0] = datetime(2026, 9, 30, 11, 0, 30, tzinfo=UTC)
    session.refresh()
    eleven = wall(pd.Timestamp("2026-09-30 11:00", tz="UTC"))
    assert read[first:] == [pd.Timestamp(f"2026-09-30 {t}", tz="UTC").to_pydatetime()
                            for t in ("10:15", "10:30", "10:45", "11:00")]           # only the new closes
    assert session.version == version + 1 and session.status()["end"] == eleven and max(session.states) == eleven
    assert session.state == "ready" and session.message == ""

    session.refresh()                                                                # nothing new: nothing read
    assert len(read) == first + 4 and session.version == version + 1

    # A page asking after it starts the refresh in the background, at most every LIVE_EVERY seconds.
    clock[0] = datetime(2026, 9, 30, 11, 20, 30, tzinfo=UTC)
    session._refreshed_at = 0.0
    session.status()
    stop = time.time() + 60
    while session._refreshing and time.time() < stop:
        time.sleep(0.1)
    assert session.status()["end"] == wall(pd.Timestamp("2026-09-30 11:20", tz="UTC"))

    # The same days replayed from the snapshot reach the study's hold-out, and are refused there (D40).
    replay = WatchSession(root / "live.toml", None, "EURUSD", date(2026, 9, 30), 1, snap, studies_root=root)
    replay.prepare()
    assert replay.state == "error" and "hold-out" in replay.message


def test_without_a_live_feed_a_live_start_is_refused(setup):  # noqa: F811
    root, snap = setup
    app = WatchApp(root / "base.toml", snap, (date(2026, 9, 28), date(2026, 10, 3)), noculus_root=root / "noculus")
    assert app.meta()["live"] is False
    with pytest.raises(ValueError, match="live"):
        app.start({"instrument": "EURUSD", "days": 1, "live": True})


def test_the_watchlist_reads_the_terminal_in_a_live_session(live):
    root, snap, clock, terminal, source = live
    charts = ChartsApp(snap, root / "journal", (date(2026, 9, 28), date(2026, 10, 3)),
                       WatchApp(root / "live.toml", snap, (date(2026, 9, 28), date(2026, 10, 3))), default="EURUSD")
    until = pd.Timestamp("2026-09-30 10:00", tz="UTC")
    rows = charts.watchlist(until, ChartsApp._live_bars(source, until))["rows"]
    snapshot = charts.watchlist(until)["rows"]
    assert rows == snapshot and rows[0]["last"] is not None                         # the same prices, from the terminal
    assert terminal.calls[-1][1] == TF.M1 and terminal.calls[-1][3] == until.to_pydatetime()
    nothing = ChartsApp._live_bars(LiveSource(lambda *a: pd.DataFrame(columns=COLUMNS), ["EURUSD"]), until)
    assert charts.watchlist(until, nothing)["rows"][0]["last"] is None


def test_the_market_now_moves_between_the_engines_closes(live):
    root, snap, clock, _, source = live
    app = WatchApp(root / "live.toml", snap, (date(2026, 9, 28), date(2026, 10, 3)), noculus_root=root / "noculus",
                   studies_root=root, live=lambda: source)
    app.start({"instrument": "EURUSD", "days": 1, "variant": "base", "live": True})
    session = _ready(app)
    ten = wall(pd.Timestamp("2026-09-30 10:00", tz="UTC"))
    m1 = SnapshotSource(snap)._frame("EURUSD").set_index("time")
    now = session.live_now("M1")
    assert [b["time"] for b in now["bars"]] == [ten - 60, ten]                    # the last closed minute, the forming one
    assert now["bars"][-1]["close"] == pytest.approx(m1.loc[pd.Timestamp("2026-09-30 10:00", tz="UTC"), "close"])
    assert now["bid"] == now["bars"][-1]["close"] and now["ask"] > now["bid"] and now["end"] == ten
    m15 = session.live_now("M15")["bars"]
    assert [b["time"] for b in m15] == [ten - 900, ten]                           # 09:45 closed, 10:00 forming
    # The forming minute is the chart's only: the engine and the account still end at the last closed minute.
    assert max(session.states) == ten and source.last_time("EURUSD", TF.M1) == datetime(2026, 9, 30, 9, 59, tzinfo=UTC)
    with pytest.raises(ValueError):
        session.live_now("M7")


def test_two_live_sessions_on_one_market_both_move_on(live):
    root, snap, clock, _, source = live
    app = WatchApp(root / "live.toml", snap, (date(2026, 9, 28), date(2026, 10, 3)), noculus_root=root / "noculus",
                   studies_root=root, live=lambda: source)
    app.start({"instrument": "EURUSD", "days": 1, "variant": "base", "live": True})
    open_ = _ready(app)
    app.start({"instrument": "EURUSD", "days": 1, "variant": "base", "live": True, "blind": True})
    blind = _ready(app)
    assert open_ is not blind and open_.source is blind.source
    clock[0] = datetime(2026, 9, 30, 10, 30, 30, tzinfo=UTC)
    open_.refresh()                                          # tops up the shared minutes
    blind.refresh()                                          # which must not look like "nothing new" to the other
    half = wall(pd.Timestamp("2026-09-30 10:30", tz="UTC"))
    assert open_.status()["end"] == blind.status()["end"] == half
    with pytest.raises(LookupError, match="not live"):
        WatchSession(root / "base.toml", None, "EURUSD", date(2026, 9, 30), 1, snap).live_now("M1")


def test_a_cross_is_watched_in_its_own_currency(setup, monkeypatch):  # noqa: F811
    # GER40 (EUR) and UK100 (GBP) on a USD account: the backtester refuses to convert them, so the watch follows a
    # cross in an account of its own quote currency; it shows R, which no currency changes (D42).
    root, snap = setup
    real = watch.load_profile

    class Elsewhere:                                         # the same broker, its account in yen
        def __init__(self, name):
            self._p = real(name)

        def __getattr__(self, name):
            return getattr(self._p, name)

        def specs(self):
            specs = self._p.specs()
            return watch.InstrumentSpecs(specs.venue, "JPY", {k: specs[k] for k in specs})

    monkeypatch.setattr(watch, "load_profile", Elsewhere)
    session = WatchSession(root / "base.toml", None, "EURUSD", date(2026, 9, 30), 1, snap, studies_root=root)
    session.prepare()
    assert session.state == "ready", session.message
    assert session.journal and session.costs is not None
