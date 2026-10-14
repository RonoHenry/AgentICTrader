"""Watch the engine work (algo-backtester update 2026-10-14d).

    python -m algo_backtester watch [config/backtests/base.toml] [--port 8767] [--no-browser]

Pick an instrument and a few trading days of the research snapshot's exploration slice. The backtest runs over
them as ``run`` would (the configuration's strategy, Phase A and Phase B, the broker profile's costs), and a page
plays the days forward. At every entry-timeframe close it shows what the engine saw (its PD arrays, the liquidity
pools it can raid, the candle profile, the setup sequence, the grade) and what it did (the decision, the order, the
fill, the exit), so a flaw in its logic can be seen on the chart.

Nothing here decides anything: the engine and the simulation are the backtester's own; this module only runs
them over a short window and serialises what they produced. Times go to the page as New York wall-clock seconds.
"""
from __future__ import annotations

import io
import json
import threading
import traceback
import webbrowser
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from agent.broker_profiles import load_profile
from algo_backtester.config import REPO_ROOT, load_or_create_study, load_run_config
from algo_backtester.data import StoredBar, load_instrument
from algo_backtester.report import journal_csv
from algo_backtester.run import run_backtest
from algo_backtester.signals import entry_closes
from algo_research.config import load_research_config, trading_date_open
from algo_research.narrative import PriceBasis
from algo_research.replay.bars import ReplayBars
from algo_research.replay.timeframes import TIMEFRAMES, seconds_of, wall_seconds
from algo_research.snapshot import SNAPSHOTS_DIR
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.grader.sequence import SetupSequenceDetector
from liquidity_engine.models import Timeframe
from services.market_data.as_of_view import compose_as_of_view
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["SnapshotSource", "WatchSession", "make_watch_server", "serve"]

NY = "America/New_York"
STATIC = REPO_ROOT / "algo_research" / "replay" / "static"
FILES = {"engine.html": "text/html; charset=utf-8", "engine.js": "text/javascript; charset=utf-8",
         "drawings.js": "text/javascript; charset=utf-8", "settings.js": "text/javascript; charset=utf-8",
         "app.css": "text/css; charset=utf-8"}
MAX_DAYS = 5
_CALENDAR = StrategyCalendar()
_ARRAYS_SHOWN, _POOLS_SHOWN = 80, 50


def wall(t) -> int:
    return int(wall_seconds([pd.Timestamp(t)])[0])


def from_wall(w: int) -> pd.Timestamp:
    return pd.Timestamp(int(w), unit="s").tz_localize(NY).tz_convert("UTC")


class SnapshotSource:
    """A CandleSource over a research snapshot: M1 only (the backtester builds every other timeframe from it)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._m1: dict[str, pd.DataFrame] = {}

    def _frame(self, instrument: str) -> pd.DataFrame:
        if instrument not in self._m1:
            path = self.root / f"{instrument}_M1.parquet"
            frame = pd.read_parquet(path) if path.exists() else pd.DataFrame(
                columns=["time", "open", "high", "low", "close", "volume", "spread"])
            frame["time"] = pd.to_datetime(frame["time"], utc=True)
            self._m1[instrument] = frame.sort_values("time").reset_index(drop=True)
        return self._m1[instrument]

    def bars(self, instrument: str, tf: Timeframe, start: datetime, end: datetime) -> list[StoredBar]:
        if tf != Timeframe.M1:
            return []
        f = self._frame(instrument)
        f = f[(f["time"] >= pd.Timestamp(start)) & (f["time"] < pd.Timestamp(end))]
        spread = f["spread"] if "spread" in f else pd.Series([None] * len(f))
        volume = f["volume"] if "volume" in f else pd.Series([None] * len(f))
        return [StoredBar(t.to_pydatetime(), o, h, lo, c, None if pd.isna(v) else int(v), None if pd.isna(s) else float(s),
                          Timeframe.M1, instrument)
                for t, o, h, lo, c, v, s in zip(f["time"], f["open"], f["high"], f["low"], f["close"], volume, spread)]

    def last_time(self, instrument: str, tf: Timeframe) -> Optional[datetime]:
        f = self._frame(instrument)
        return None if f.empty or tf != Timeframe.M1 else f["time"].iloc[-1].to_pydatetime()


def _iso_wall(value) -> Optional[int]:
    if value is None or (isinstance(value, float) and np.isnan(value)) or value == "":
        return None
    return wall(pd.Timestamp(value).tz_convert("UTC") if pd.Timestamp(value).tzinfo else pd.Timestamp(value, tz="UTC"))


def _num(value) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else v


class WatchSession:
    """One instrument over a few trading days: the backtest's journal, the chart's bars and the engine's state."""

    def __init__(self, config: Path, variant: Optional[str], instrument: str, first_day: date, days: int,
                 snapshot: Path, studies_root: Path = REPO_ROOT) -> None:
        self.config, self.variant, self.instrument = Path(config), variant, instrument.upper()
        self.first_day, self.days = first_day, days
        self.snapshot, self.studies_root = Path(snapshot), studies_root
        self.state, self.progress, self.message = "preparing", 0.0, "loading candles"
        self.start = pd.Timestamp(trading_date_open(first_day))
        self.end = pd.Timestamp(trading_date_open(first_day + timedelta(days=days)))
        self.bars: Optional[ReplayBars] = None
        self.journal: list[dict] = []
        self.states: dict[int, dict] = {}
        self._keys: list[int] = []
        self.summary: dict = {}

    # ── preparing ───────────────────────────────────────────────────────────
    def prepare(self) -> None:
        try:
            self._prepare()
            self.state, self.progress, self.message = "ready", 1.0, ""
        except Exception as exc:  # shown on the page; the server keeps running
            self.state, self.message = "error", f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

    def _prepare(self) -> None:
        cfg = load_run_config(self.config, self.variant)
        run_start = (self.start - pd.Timedelta(hours=12)).date()
        run_end = (self.end + pd.Timedelta(hours=12)).date()
        cfg = cfg.model_copy(update={"run": cfg.run.model_copy(update={"instruments": (self.instrument,),
                                                                         "start": run_start, "end": run_end})})
        profile = load_profile(cfg.run.profile)
        study = load_or_create_study(cfg.run.study, date.today(), self.studies_root)
        start_dt = datetime(run_start.year, run_start.month, run_start.day, tzinfo=timezone.utc)
        end_dt = datetime(run_end.year, run_end.month, run_end.day, tzinfo=timezone.utc)
        source = SnapshotSource(self.snapshot)
        data = load_instrument(source, self.instrument, start_dt, end_dt, cfg.strategy,
                               profile.clock() if profile.venue == "mt5" else None, venue=profile.venue,
                               max_gap_minutes=cfg.data.max_gap_minutes)
        m1 = pd.DataFrame({"time": [b.timestamp for b in data.m1], "open": [b.open for b in data.m1],
                           "high": [b.high for b in data.m1], "low": [b.low for b in data.m1],
                           "close": [b.close for b in data.m1]})
        self.bars = ReplayBars(m1, self.instrument, PriceBasis(instruments=()))   # the engine's own prices, unflattened
        self.message, self.progress = "running the backtest (Phase A and B)", 0.1
        result = run_backtest(cfg, study, False, {self.instrument: data}, profile.specs(), cache=None, workers=1)
        frame = pd.read_csv(io.StringIO(journal_csv(result.journal, result.open_orders)))
        self.journal = [self._journal_row(r) for r in frame.to_dict("records")]
        filled = [r for r in self.journal if r["net_r"] is not None and r["filled_at"] is not None]
        self.summary = {"orders": sum(1 for r in self.journal if r["decision"] == "EXECUTE"), "trades": len(filled),
                        "total_r": round(sum(r["net_r"] for r in filled), 2)}
        self.message = "replaying the engine at each close"
        closes = entry_closes(data, cfg.strategy.entry_tf, start_dt, end_dt)
        engine = LiquidityMappingEngine()
        decisions = {r["t"]: r for r in self.journal}
        for n, t in enumerate(closes):
            view = compose_as_of_view(data.closed, data.m1, t, cfg.strategy.entry_tf, cfg.strategy.candle_counts, _CALENDAR)
            try:
                lm = engine.analyze(view, self.instrument, t)
                state = self._state(lm, view, t, cfg.strategy.entry_tf)
            except Exception as exc:
                state = {"error": f"{type(exc).__name__}: {exc}"}
            state["t"] = wall(t)
            state["decision"] = decisions.get(state["t"])
            self.states[state["t"]] = state
            self.progress = 0.1 + 0.9 * (n + 1) / max(1, len(closes))
        self._keys = sorted(self.states)

    @staticmethod
    def _journal_row(r: dict) -> dict:
        return {"t": _iso_wall(r.get("t")), "decision": r.get("decision"), "reason": r.get("reason"), "grade": r.get("grade"),
                "direction": r.get("direction") if isinstance(r.get("direction"), str) else None,
                "entry": _num(r.get("entry")), "stop": _num(r.get("stop")), "target": _num(r.get("target")),
                "r_ratio": _num(r.get("r_ratio")), "order_kind": r.get("order_kind") if isinstance(r.get("order_kind"), str) else None,
                "placed_at": _iso_wall(r.get("placed_at")), "expires_at": _iso_wall(r.get("expires_at")),
                "filled_at": _iso_wall(r.get("filled_at")), "fill": _num(r.get("fill")), "closed_at": _iso_wall(r.get("closed_at")),
                "exit": _num(r.get("exit")), "exit_reason": r.get("exit_reason") if isinstance(r.get("exit_reason"), str) else None,
                "net_r": _num(r.get("net_r")), "mfe_r": _num(r.get("mfe_r"))}

    def _state(self, lm, view, t: datetime, entry_tf: Timeframe) -> dict:
        price = view[entry_tf][-1].close if view.get(entry_tf) else None
        days = view.get(Timeframe.D1, [])[-6:]
        lo = min((c.low for c in days), default=price) if price else None
        hi = max((c.high for c in days), default=price) if price else None
        pad = (hi - lo) * 0.6 if lo is not None else 0
        near = (lambda p: lo - pad <= p <= hi + pad) if lo is not None else (lambda p: True)
        arrays = [a for a in lm.pd_arrays if not a.is_filled and (near(a.high) or near(a.low))]
        arrays.sort(key=lambda a: a.formed_at, reverse=True)
        seq = lm.setup_sequence
        keep = {seq.entry_array_id} if seq else set()
        shown = [a for a in arrays if a.array_id in keep] + [a for a in arrays if a.array_id not in keep][:_ARRAYS_SHOWN]
        out_arrays = [{"id": a.array_id, "type": a.array_type.value, "dir": a.direction.value, "tf": a.timeframe.value,
                       "high": a.high, "low": a.low, "formed": wall(a.formed_at),
                       "mt": None if a.ob_candle_open is None else (a.ob_candle_open + a.ob_candle_close) / 2,
                       "entry": bool(seq and a.array_id == seq.entry_array_id)} for a in shown]
        pools = []
        bars = view.get(entry_tf, [])
        opens = [c.timestamp for c in bars]
        for p in SetupSequenceDetector().pools(view, as_of=t):
            if p.known_at > t or not near(p.price):
                continue
            k = bisect_right(opens, p.known_at)
            later = bars[k:]
            above = p.side.value == "BSL"
            if any((c.high > p.price) if above else (c.low < p.price) for c in later):
                continue                                  # taken already
            pools.append({"side": p.side.value, "source": p.source.value, "tf": p.timeframe.value, "price": p.price,
                          "known": wall(p.known_at)})
        pools.sort(key=lambda p: p["known"], reverse=True)
        prof = lm.candle_profile
        profile = None
        if prof is not None:
            obj = lambda o: None if o is None else {"source": o.source, "tf": o.timeframe.value, "price": o.price,  # noqa: E731
                                                     "kind": o.kind}
            profile = {"open_time": wall(prof.open_time), "open": prof.frame_open, "midnight": prof.midnight_open,
                       "trend": prof.trend.value, "direction": prof.direction.value, "draw": obj(prof.draw),
                       "draw_above": obj(prof.draw_above), "draw_below": obj(prof.draw_below),
                       "false_move": prof.false_move_taken, "asia_raided": prof.asia_raided, "in_window": prof.in_window,
                       "raid_in_window": prof.raid_in_window}
        sequence = None
        if seq is not None:
            sequence = {"direction": seq.direction.value, "pool": {"side": seq.raid.pool.side.value, "source": seq.raid.pool.source.value,
                                                                   "tf": seq.raid.pool.timeframe.value, "price": seq.raid.pool.price},
                        "raided": wall(seq.raid.raided_at), "reclaimed": wall(seq.raid.reclaimed_at), "cisd": wall(seq.cisd_at),
                        "protected": {"wick": seq.protected_swing.wick, "body": seq.protected_swing.body,
                                      "at": wall(seq.protected_swing.candle_at)},
                        "leg_extreme": seq.leg_extreme}
        g = lm.setup_grade
        grade = None if g is None else {
            "grade": g.grade.value, "met": g.conditions_met, "reason": g.grade_reason, "entry": g.suggested_entry,
            "stop": g.suggested_stop, "counter_trend": g.counter_trend,
            "conditions": {"HTF bias (D1 and W1 not neutral)": g.htf_bias_confirmed, "Draw on liquidity": g.draw_on_liquidity_identified,
                           "Raid, reclaim and CISD (a setup sequence)": g.liquidity_sweep_confirmed,
                           "Displacement (an OB anywhere)": g.displacement_present, "CISD cascade": g.cisd_confirmed,
                           "Entry PD array (M1-M15)": g.entry_pd_array_present, "Stop beyond the entry array": g.stop_placement_valid,
                           "In a killzone": g.time_window_aligned}}
        bias = {tf: {"direction": b.direction.value, "open": b.reference_open} for tf, b in lm.htf_bias.items()
                if tf in ("W1", "D1", "H4", "H1")}
        return {"price": price, "arrays": out_arrays, "pools": pools[:_POOLS_SHOWN], "profile": profile, "sequence": sequence,
                "grade": grade, "bias": bias}

    # ── what the page asks ──────────────────────────────────────────────────
    def status(self) -> dict:
        return {"state": self.state, "progress": round(self.progress, 3), "message": self.message, "instrument": self.instrument,
                "variant": self.variant or "base", "first_day": self.first_day.isoformat(), "days": self.days,
                "start": wall(self.start), "end": wall(self.end), "digits": self.bars.digits if self.bars else 5,
                "summary": self.summary, "closes": len(self._keys)}

    def state_at(self, w: int) -> Optional[dict]:
        i = bisect_right(self._keys, int(w)) - 1
        return self.states[self._keys[i]] if i >= 0 else None

    def bars_until(self, tf: str, until: int, since: Optional[int]) -> list[dict]:
        seconds_of(tf)
        frame = self.bars.as_of(tf, from_wall(min(int(until), wall(self.end))), since=since)
        return [{"time": int(r.time), "open": float(r.open), "high": float(r.high), "low": float(r.low), "close": float(r.close)}
                for r in frame.itertuples()]


class WatchApp:
    def __init__(self, config: Path, snapshot: Path, slice_: tuple[date, date]) -> None:
        self.config, self.snapshot, self.slice = Path(config), Path(snapshot), slice_
        self.session: Optional[WatchSession] = None

    def meta(self) -> dict:
        import tomllib
        variants = sorted(tomllib.loads(self.config.read_text(encoding="utf-8")).get("variants", {}))
        instruments = sorted(p.name.split("_")[0] for p in self.snapshot.glob("*_M1.parquet"))
        return {"instruments": instruments, "variants": ["base", *variants], "first": self.slice[0].isoformat(),
                "last": (self.slice[1] - timedelta(days=1)).isoformat(), "max_days": MAX_DAYS, "timeframes": list(TIMEFRAMES),
                "config": str(self.config.relative_to(REPO_ROOT) if self.config.is_relative_to(REPO_ROOT) else self.config)}

    def start(self, body: dict) -> dict:
        day = date.fromisoformat(str(body.get("first_day")))
        days = int(body.get("days", 1))
        if not self.slice[0] <= day < self.slice[1]:
            raise ValueError(f"first_day: within the exploration slice, {self.slice[0]} to {self.slice[1] - timedelta(days=1)}")
        if not 1 <= days <= MAX_DAYS:
            raise ValueError(f"days: 1 to {MAX_DAYS}")
        variant = body.get("variant") or "base"
        session = WatchSession(self.config, None if variant == "base" else variant, str(body.get("instrument", "XAUUSD")),
                               day, days, self.snapshot)
        self.session = session
        threading.Thread(target=session.prepare, daemon=True).start()
        return session.status()

    def need(self) -> WatchSession:
        if self.session is None:
            raise LookupError("no session: start one")
        if self.session.state != "ready":
            raise LookupError(f"the session is {self.session.state}")
        return self.session


class _Handler(BaseHTTPRequestHandler):
    app: WatchApp

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
        except LookupError as exc:
            self._send(409, {"error": str(exc)})
        except (ValueError, KeyError, TypeError) as exc:
            self._send(400, {"error": str(exc)})

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        name = "engine.html" if url.path in ("/", "/index.html") else url.path.removeprefix("/static/")
        if name in FILES and (url.path in ("/", "/index.html") or url.path.startswith("/static/")):
            self._send(200, (STATIC / name).read_bytes(), FILES[name])
        elif url.path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif url.path == "/api/watch/meta":
            self._answer(self.app.meta)
        elif url.path == "/api/watch/status":
            self._answer(lambda: self.app.session.status() if self.app.session else {"state": "none"})
        elif url.path == "/api/watch/bars":
            self._answer(lambda: {"tf": q.get("tf", "M15"), "bars": self.app.need().bars_until(
                q.get("tf", "M15"), int(q["until"]), int(q["since"]) if q.get("since") else None)})
        elif url.path == "/api/watch/state":
            self._answer(lambda: {"state": self.app.need().state_at(int(q["t"]))})
        elif url.path == "/api/watch/journal":
            self._answer(lambda: {"rows": self.app.need().journal})
        else:
            self._send(404, {"error": f"no such path {url.path}"})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/watch/start":
            self._send(404, {"error": f"no such path {self.path}"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return
        self._answer(lambda: self.app.start(body))

    def log_message(self, format: str, *args) -> None:
        pass


def make_watch_server(app: WatchApp, host: str = "127.0.0.1", port: int = 8767) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), type("WatchHandler", (_Handler,), {"app": app}))


def serve(config: Path, port: int = 8767, browser: bool = True) -> int:
    research = load_research_config()
    app = WatchApp(Path(config), SNAPSHOTS_DIR / research.snapshot, research.slices.explore)
    server = make_watch_server(app, port=port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"engine watch at {url} (strategy from {config}; days from the exploration slice). Ctrl+C stops.")
    if browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
