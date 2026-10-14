"""The blind replay's HTTP server (market-narrative Requirement 10; design: update 2026-10-14).

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

from algo_research.replay.bars import ReplayBars
from algo_research.replay.journal import Journal, ReplayError
from algo_research.replay.scoring import summarize
from liquidity_engine.models import Timeframe

__all__ = ["ReplayApp", "make_server"]

NY = "America/New_York"
PAGE = Path(__file__).parent / "static" / "index.html"
_EPOCH = pd.Timestamp("1970-01-01")


def ny_epoch(t) -> int:
    """New York wall-clock time as seconds since 1970, as the chart's UTC axis will draw it."""
    return int((pd.Timestamp(t).tz_convert(NY).tz_localize(None) - _EPOCH).total_seconds())


def ny_label(t) -> str:
    return pd.Timestamp(t).tz_convert(NY).strftime("%a %H:%M")


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
            read = {k: v for k, v in day["read"].items() if k != "as_of"}
        trades = [{k: v for k, v in t.items() if k != "marked_at"} | {"marked_epoch": ny_epoch(t["marked_at"]),
                                                                       "marked_ny": ny_label(t["marked_at"])}
                  for t in day["trades"]]
        return {
            "instrument": self.journal.instrument, "digits": self.journal.bars.digits, "weekday": day["weekday"],
            "status": day["status"], "date": day["trading_date"] if show else None, "date_shown": day["date_shown"],
            "open_price": day["open_price"], "price": day["price"],
            "open_epoch": ny_epoch(day["open_time"]), "close_epoch": ny_epoch(day["close_time"]),
            "revealed_until_epoch": ny_epoch(day["revealed_until"]), "revealed_until_ny": ny_label(day["revealed_until"]),
            "read": read, "trades": trades, "remaining": self.journal.remaining(),
            "narrative": day["narrative"] if revealed else None, "scores": day["scores"] if revealed else None,
        }

    def state(self) -> dict:
        with self._lock:
            return self._view(self.journal.current())

    def bars(self, tf: str) -> dict:
        try:
            timeframe = Timeframe(tf)
        except ValueError:
            raise ValueError(f"tf: one of {', '.join(t.value for t in ReplayBars.TIMEFRAMES)}") from None
        if timeframe not in ReplayBars.TIMEFRAMES:
            raise ValueError(f"tf: one of {', '.join(t.value for t in ReplayBars.TIMEFRAMES)}")
        with self._lock:
            until = pd.Timestamp(self.journal.current()["revealed_until"])
            frame = self.journal.bars.as_of(timeframe, until)
        return {"tf": timeframe.value, "bars": [
            {"time": ny_epoch(r.time), "open": float(r.open), "high": float(r.high), "low": float(r.low),
             "close": float(r.close)} for r in frame.itertuples()]}

    def _write(self, method, *args, **kwargs) -> dict:
        with self._lock:
            return self._view(method(*args, **kwargs))

    def read(self, body: dict) -> dict:
        return self._write(self.journal.save_read, body)

    def advance(self, body: dict) -> dict:
        return self._write(self.journal.advance, step=body.get("step"), to=body.get("to"))

    def trade(self, body: dict) -> dict:
        return self._write(self.journal.mark_trade, body)

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
          "/api/show-date": "show_date", "/api/next": "next"}


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
        if url.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/state":
            self._answer(self.app.state)
        elif url.path == "/api/bars":
            tf = parse_qs(url.query).get("tf", ["H1"])[0]
            self._answer(lambda: self.app.bars(tf))
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
