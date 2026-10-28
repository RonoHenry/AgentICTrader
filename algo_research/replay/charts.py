"""One chart, two analysts (market-narrative Requirement 15, update 2026-10-15).

    python -m algo_research.replay [--instrument XAUUSD] [--port 8765] [--config config/backtests/base.toml]

One server for both modes of the chart: **You** at ``/`` (the blind replay, Requirements 10-12) and **Engine**
at ``/engine`` (the engine watch, algo-backtester Requirement 15). Each instrument of the research snapshot has
its own blind journal, opened when its tab is first chosen; the replay's API takes ``?inst=``. The watchlist
gives every instrument's last price and change as of a time the page names (the You mode: its day's revealed
time, read here, never later), so it can't show what the chart hasn't reached.

The two modes keep their own APIs: ``server.ReplayApp`` and ``algo_backtester.watch.WatchApp``. This module
routes to them and adds what they share: the instrument list and the watchlist.
"""
from __future__ import annotations

import threading
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Sequence
from urllib.parse import parse_qs, urlparse

import pandas as pd

from algo_backtester import watch as watch_mod
from algo_research.replay.bars import ReplayBars
from liquidity_engine.models import Timeframe
from algo_research.replay.journal import Journal, ReplayError
from algo_research.replay.server import (FILES, STATIC, ReplayApp, static_file,
                                         _Handler as _ReplayHandler)

__all__ = ["ChartsApp", "make_charts_server", "serve"]

#: Every page and script of both modes.
PAGES = {"/": "index.html", "/index.html": "index.html", "/you": "index.html", "/engine": "engine.html"}
ALL_FILES = {**FILES, **watch_mod.FILES, "shell.js": "text/javascript; charset=utf-8"}
_DAY, _DAY_OPEN = 86400, 61200


class ChartsApp:
    """The instruments, a blind journal per instrument (opened on first use), the engine watch and the watchlist."""

    def __init__(self, snapshot: Path, journal_root: Path, slice_: tuple[date, date], watch: watch_mod.WatchApp,
                 default: str = "XAUUSD", order: Sequence[str] = ()) -> None:
        self.snapshot, self.journal_root, self.slice, self.watch = Path(snapshot), Path(journal_root), slice_, watch
        held = sorted(p.name.split("_")[0] for p in self.snapshot.glob("*_M1.parquet"))
        # The tabs in the research order (algo-research Requirement 22.5), then anything else the snapshot holds.
        self.instruments = [i for i in dict.fromkeys(o.upper() for o in order) if i in held] + \
                           [i for i in held if i not in {o.upper() for o in order}]
        self.default = default.upper() if default.upper() in self.instruments else (self.instruments or [default])[0]
        self._bars: dict[str, ReplayBars] = {}
        self._replays: dict[str, ReplayApp] = {}
        self._lock = threading.Lock()

    def _check(self, instrument: Optional[str]) -> str:
        inst = (instrument or self.default).upper()
        if inst not in self.instruments:
            raise ValueError(f"inst: one of {', '.join(self.instruments)}")
        return inst

    def bars(self, instrument: str) -> ReplayBars:
        inst = self._check(instrument)
        with self._lock:
            if inst not in self._bars:
                frame = pd.read_parquet(self.snapshot / f"{inst}_M1.parquet", columns=["time", "open", "high", "low", "close"])
                self._bars[inst] = ReplayBars(frame, inst)
            return self._bars[inst]

    def replay(self, instrument: Optional[str]) -> ReplayApp:
        inst = self._check(instrument)
        if inst not in self._replays:
            bars = self.bars(inst)
            with self._lock:
                if inst not in self._replays:
                    first, end = self.slice
                    self._replays[inst] = ReplayApp(Journal(self.journal_root, bars, bars.trading_dates(first, end)))
        return self._replays[inst]

    def instrument_list(self) -> dict:
        return {"instruments": self.instruments, "default": self.default}

    def watchlist(self, until: pd.Timestamp, bars_of=None) -> dict:
        """Each instrument's last close by ``until`` and its change from the previous trading day's last close.
        ``bars_of`` gives an instrument's bars (default: the snapshot's); None, and the row stays empty."""
        rows = []
        for inst in self.instruments:
            bars = (bars_of or self.bars)(inst)
            row = {"instrument": inst, "digits": bars.digits if bars is not None else 5, "last": None, "change": None, "change_pct": None}
            try:
                if bars is None:
                    raise ValueError(inst)
                row["last"] = bars.price_at(until)
                wall = int(watch_mod.wall(until))
                day_open = (wall - _DAY_OPEN) // _DAY * _DAY + _DAY_OPEN       # the 17:00 New York open of the day
                prev = bars.price_at(watch_mod.from_wall(day_open))
                row["change"] = row["last"] - prev
                row["change_pct"] = 100 * row["change"] / prev if prev else None
            except ValueError:                                             # no bar yet: shown empty
                pass
            rows.append(row)
        return {"rows": rows}                                          # no time: it would name the blind day

    def blind(self, query: dict) -> dict:
        """How many of an engine session's trading days are still unread in that instrument's blind journal."""
        replay = self.replay(query.get("inst"))
        first = date.fromisoformat(str(query["first_day"]))
        span = [first + timedelta(days=i) for i in range(int(query.get("days", 1)))]
        days = [d for d in span if d in set(replay.journal.order)]
        return {"days": len(days), "unread": len(replay.journal.unrevealed(days))}

    def watchlist_for(self, query: dict) -> dict:
        """The You mode names its instrument (its day's revealed time is read here); the Engine mode names ``t``,
        a wall second, held to the session's end."""
        if "t" in query:
            t = int(query["t"])
            session = self.watch.session
            if session is not None and session.state == "ready":
                t = min(t, watch_mod.wall(session.end))
                if session.live:                       # the terminal's prices, not the snapshot's (Requirement 27.4)
                    return self.watchlist(watch_mod.from_wall(t), self._live_bars(session.source, watch_mod.from_wall(t)))
            return self.watchlist(watch_mod.from_wall(t))
        day = self.replay(query.get("inst")).journal.current()
        return self.watchlist(pd.Timestamp(day["revealed_until"]))


    @staticmethod
    def _live_bars(source, until: pd.Timestamp):
        """Each instrument's last four days of M1 from the live terminal, by ``until``: enough for its last close
        and the previous trading day's."""
        def bars_of(inst: str) -> Optional[ReplayBars]:
            try:
                frame = source.rates(inst, Timeframe.M1, (until - pd.Timedelta(days=4)).to_pydatetime(), until.to_pydatetime())
                return ReplayBars(frame, inst) if len(frame) else None
            except Exception:                           # a market the broker doesn't carry: shown empty
                return None
        return bars_of


class _Handler(BaseHTTPRequestHandler):
    """Routes each request to the mode's own handler code, with its app."""
    charts: ChartsApp

    _send = _ReplayHandler._send

    def _answer(self, call) -> None:
        try:
            self._send(200, call())
        except (ReplayError, LookupError) as exc:
            self._send(409, {"error": str(exc)})
        except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
            self._send(400, {"error": str(exc)})

    def _query(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        name = PAGES.get(path) or (path.removeprefix("/static/") if path.startswith("/static/") else None)
        served = static_file(name)
        if served is not None:
            self._send(200, *served)
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif path == "/api/instruments":
            self._answer(self.charts.instrument_list)
        elif path == "/api/blind":
            self._answer(lambda: self.charts.blind(self._query()))
        elif path == "/api/watchlist":
            self._answer(lambda: self.charts.watchlist_for(self._query()))
        elif path.startswith("/api/watch/"):
            self.app = self.charts.watch
            watch_mod._Handler.do_GET(self)
        elif path.startswith("/api/"):
            self._with_replay(_ReplayHandler.do_GET)
        else:
            self._send(404, {"error": f"no such path {path}"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/watch/"):
            self.app = self.charts.watch
            watch_mod._Handler.do_POST(self)
        else:
            self._with_replay(_ReplayHandler.do_POST)

    def _with_replay(self, method) -> None:
        try:
            self.app = self.charts.replay(self._query().get("inst"))
        except (ValueError, FileNotFoundError) as exc:
            self._send(400, {"error": str(exc)})
            return
        method(self)

    def log_message(self, format: str, *args) -> None:
        pass


def make_charts_server(charts: ChartsApp, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), type("ChartsHandler", (_Handler,), {"charts": charts}))


def serve(config: Path, port: int = 8765, browser: bool = True, instrument: str = "XAUUSD",
          journal_root: Optional[Path] = None, picks: Optional[Path] = None, page: str = "/") -> int:
    from algo_research.config import load_research_config
    from algo_research.replay.__main__ import JOURNAL_DIR
    from algo_research.snapshot import SNAPSHOTS_DIR

    research = load_research_config()
    snapshot = SNAPSHOTS_DIR / research.snapshot
    watch = watch_mod.WatchApp(Path(config), snapshot, research.slices.explore, picks=picks,
                               live=watch_mod.live_feed(Path(config)), periods=watch_mod.noculus_periods(research))
    charts = ChartsApp(snapshot, journal_root or JOURNAL_DIR, research.slices.explore, watch, default=instrument,
                       order=research.instruments)
    server = make_charts_server(charts, port=port)
    url = f"http://127.0.0.1:{server.server_address[1]}{page}"
    print(f"charts at {url}: You (the blind replay) at /, Engine (the watch) at /engine. "
          f"Instruments: {', '.join(charts.instruments)}. Ctrl+C stops.")
    if browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
