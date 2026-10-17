"""The blind replay's HTTP server (market-narrative Requirement 10; design: updates 2026-10-14 and 2026-10-14b).

``ReplayApp`` is the API as plain methods over a Journal; ``make_server`` wraps it
in the standard library's threading HTTP server on 127.0.0.1, so the trader's
reads never leave the machine. Times go to the page as New York wall-clock
seconds (the chart draws them as given). Until the reveal, nothing the page
receives names the date except the bar times themselves, which the page labels
by weekday and time only.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import pandas as pd

from algo_research.replay.journal import STEPS, Journal, ReplayError
from algo_research.replay.scoring import summarize
from algo_research.replay.timeframes import TIMEFRAMES, seconds_of, wall_seconds

__all__ = ["ReplayApp", "make_server"]

NY = "America/New_York"
STATIC = Path(__file__).parent / "static"
#: The page's files: name -> content type. Nothing else under static/ is served.
FILES = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
         "drawings.js": "text/javascript; charset=utf-8", "settings.js": "text/javascript; charset=utf-8",
         "motion.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8"}
#: What ``/static/`` serves beyond the names above: any file of these types sitting directly in ``static/``.
#: A page is read from disk on every request, so a server left running would otherwise serve a page that asks
#: for a script added since it started and then 404 that script — which kills the page with no clue why.
STATIC_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
                ".ico": "image/x-icon", ".woff2": "font/woff2", ".map": "application/json"}


def static_file(name: Optional[str]) -> Optional[tuple[bytes, str]]:
    """The bytes and content type of ``static/<name>``, or None.

    The name must be a plain file name of a known type that is really in ``static/``: no directory parts, so
    no traversal, and nothing hidden. ``FILES`` keeps the content types of the pages themselves.
    """
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    kind = FILES.get(name) or STATIC_TYPES.get(Path(name).suffix)
    path = STATIC / name
    if kind is None or not path.is_file():
        return None
    return path.read_bytes(), kind
_EPOCH = pd.Timestamp("1970-01-01")


def ny_epoch(t) -> int:
    """New York wall-clock time as seconds since 1970, as the chart's UTC axis will draw it."""
    return int((pd.Timestamp(t).tz_convert(NY).tz_localize(None) - _EPOCH).total_seconds())


def ny_label(t) -> str:
    return pd.Timestamp(t).tz_convert(NY).strftime("%a %H:%M")


def _rows(frame: pd.DataFrame) -> list[dict]:
    return [{"time": int(r.time), "open": float(r.open), "high": float(r.high), "low": float(r.low),
             "close": float(r.close)} for r in frame.itertuples()]


_STAMPS = ("created_at", "edited_at")         # market times: they would name the date


class ReplayApp:
    """The replay's API over one journal. Calls are serialised: one trader, one day at a time."""

    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self._lock = threading.Lock()

    def _view(self, day: dict) -> dict:
        revealed = day["status"] == "REVEALED"
        show = revealed or day["date_shown"]
        read = None
        if day["read"] is not None:
            read = {k: v for k, v in day["read"].items() if k not in ("as_of", "drawings")}
        live = self.journal.live_trades() if day["status"] == "INTRADAY" else [None] * len(day["trades"])
        trades = [{k: v for k, v in t.items() if k != "marked_at"}
                  | {"marked_epoch": ny_epoch(t["marked_at"]), "marked_ny": ny_label(t["marked_at"]), "live": status}
                  for t, status in zip(day["trades"], live)]
        drawings = [{k: v for k, v in d.items() if k not in _STAMPS} for d in day.get("drawings", [])]
        return {
            "instrument": self.journal.instrument, "digits": self.journal.bars.digits, "weekday": day["weekday"],
            "status": day["status"], "date": day["trading_date"] if show else None, "date_shown": day["date_shown"],
            "open_price": day["open_price"], "price": day["price"],
            "open_epoch": ny_epoch(day["open_time"]), "close_epoch": ny_epoch(day["close_time"]),
            "revealed_until_epoch": ny_epoch(day["revealed_until"]), "revealed_until_ny": ny_label(day["revealed_until"]),
            "read": read, "trades": trades, "drawings": drawings, "remaining": self.journal.remaining(),
            "narrative": day["narrative"] if revealed else None, "scores": day["scores"] if revealed else None,
            "narrative_note": day.get("narrative_note"),
        }

    def meta(self) -> dict:
        return {"instrument": self.journal.instrument, "digits": self.journal.bars.digits,
                "timeframes": [{"tf": tf, "seconds": seconds_of(tf)} for tf in TIMEFRAMES], "steps": list(STEPS)}

    def state(self) -> dict:
        with self._lock:
            return self._view(self.journal.current())

    def _bars(self, tf: str, since: Optional[int] = None) -> list[dict]:
        seconds_of(tf)                                                  # refuses an unknown timeframe
        until = pd.Timestamp(self.journal.current()["revealed_until"])
        return _rows(self.journal.bars.as_of(tf, until, since=since))

    def bars(self, tf: str, since: Optional[int] = None) -> dict:
        with self._lock:
            return {"tf": tf, "bars": self._bars(tf, since)}

    def _write(self, method, *args, **kwargs) -> dict:
        with self._lock:
            return self._view(method(*args, **kwargs))

    def read(self, body: dict) -> dict:
        return self._write(self.journal.save_read, body)

    def advance(self, body: dict) -> dict:
        """Time forward. With ``tf`` (and ``since``, the start of the chart's last bar), the answer also
        carries the chart's bars from ``since`` and the M1 bars this step revealed, for a live update."""
        tf, since = body.get("tf"), body.get("since")
        with self._lock:
            before = pd.Timestamp(self.journal.current()["revealed_until"])
            view = self._view(self.journal.advance(step=body.get("step"), to=body.get("to")))
            if tf:
                after = pd.Timestamp(self.journal.current()["revealed_until"])
                m1 = self.journal.bars.m1_between(before, after)
                view["update"] = {"tf": tf, "bars": self._bars(tf, None if since is None else int(since)),
                                  "m1": [dict(r, time=int(w)) for r, w in
                                         zip(_rows(m1.assign(time=0)), wall_seconds(m1["time"]))]}
            return view

    def trade(self, body: dict) -> dict:
        return self._write(self.journal.mark_trade, body)

    def drawings(self, body: dict) -> dict:
        return self._write(self.journal.save_drawings, body.get("drawings"))

    def narrative(self, body: dict) -> dict:
        return self._write(self.journal.save_narrative, body.get("text"))

    def reveal(self, body: Optional[dict] = None) -> dict:
        return self._write(self.journal.reveal)

    def show_date(self, body: Optional[dict] = None) -> dict:
        return self._write(self.journal.show_date)

    def next(self, body: Optional[dict] = None) -> dict:
        return self._write(self.journal.next_day)

    def summary(self) -> dict:
        with self._lock:
            return summarize(self.journal.records())


_POSTS = {"/api/read": "read", "/api/advance": "advance", "/api/trade": "trade", "/api/reveal": "reveal",
          "/api/show-date": "show_date", "/api/next": "next", "/api/drawings": "drawings",
          "/api/narrative": "narrative"}


class _Handler(BaseHTTPRequestHandler):
    app: ReplayApp

    def _send(self, status: int, payload: Any, content_type: str = "application/json") -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _answer(self, call) -> None:
        try:
            self._send(200, call())
        except ReplayError as exc:
            self._send(409, {"error": str(exc)})
        except (ValueError, KeyError, TypeError) as exc:
            self._send(400, {"error": str(exc)})

    def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
        url = urlparse(self.path)
        name = "index.html" if url.path in ("/", "/index.html") else url.path.removeprefix("/static/")
        served = static_file(name) if (url.path in ("/", "/index.html") or url.path.startswith("/static/")) else None
        if served is not None:
            self._send(200, *served)
        elif url.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif url.path == "/api/state":
            self._answer(self.app.state)
        elif url.path == "/api/meta":
            self._answer(self.app.meta)
        elif url.path == "/api/bars":
            query = parse_qs(url.query)
            since = query.get("since", [None])[0]
            self._answer(lambda: self.app.bars(query.get("tf", ["H1"])[0], None if since is None else int(since)))
        elif url.path == "/api/summary":
            self._answer(self.app.summary)
        else:
            self._send(404, {"error": f"no such path {url.path}"})

    def do_POST(self) -> None:  # noqa: N802
        name = _POSTS.get(urlparse(self.path).path)
        if name is None:
            self._send(404, {"error": f"no such path {self.path}"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body: a JSON object")
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return
        self._answer(lambda: getattr(self.app, name)(body))

    def log_message(self, format: str, *args) -> None:  # quiet: the terminal is for the trader
        pass


def make_server(app: ReplayApp, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = type("ReplayHandler", (_Handler,), {"app": app})
    return ThreadingHTTPServer((host, port), handler)
