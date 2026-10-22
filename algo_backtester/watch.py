"""Watch the engine work (algo-backtester update 2026-10-14d).

    python -m algo_backtester watch [config/backtests/base.toml] [--port 8767] [--no-browser]

Pick an instrument and a few trading days of the research snapshot's exploration slice. The backtest runs over
them as ``run`` would (the configuration's strategy, Phase A and Phase B, the broker profile's costs), and a page
plays the days forward. At every entry-timeframe close it shows what the engine saw (its PD arrays, the liquidity
pools it can raid, the candle profile, the setup sequence, the grade) and what it did (the decision, the order, the
fill, the exit), so a flaw in its logic can be seen on the chart.

A session may be started **blind** (Noculus, Requirement 17): it then serves the bars and the clock alone, and
withholds everything the engine made until the trader reveals it. The trader's own marks and trades live in
``noculus.py``, one journal per blind session, so the comparison measures the trader, not the engine.
Every session also takes the trader's drawn positions (update 2026-10-21, Requirements 25-26), each set beside
the engine's idea at its clock; an open session keeps them in a journal of its own.

The trader's own indicator, Fractal + POI (Requirements 21-23), is served at the clock for any chart timeframe:
``algo_research.fractal_poi`` reads the snapshot's candles closed by then. It is the trader's tool, not the
engine's, so a blind session serves it too (D33).

A session may also be **live** (update 2026-10-22, Requirement 27): its candles come from the broker's MT5 terminal
(``live.py``), its window runs from the first day's open to the last closed minute, and while the page watches it
moves on with each new minute, reading the engine only at the new closes.

Nothing here decides anything: the engine and the simulation are the backtester's own; this module only runs
them over a short window and serialises what they produced. Times go to the page as New York wall-clock seconds.
"""
from __future__ import annotations

import io
import json
import tempfile
import threading
import time
from collections import OrderedDict
import traceback
import webbrowser
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from agent.broker_profiles import load_profile
from algo_backtester.cache import SignalCache, engine_code_fingerprint
from algo_backtester.config import REPO_ROOT, load_or_create_study, load_run_config
from algo_backtester.data import StoredBar, load_instrument
from algo_backtester.live import LiveSource, Terminal, stored_bars
from algo_backtester.noculus import (NOCULUS_DIR, NoculusJournal, average_ranges, build_mark, close as close_trade,
                                     compare, compare_positions, engine_ideas, place, position_ticket, settle)
from algo_backtester.report import journal_csv
from algo_backtester.run import run_backtest
from algo_backtester.signals import entry_closes, signals_at
from algo_research.config import load_research_config, trading_date_open
from algo_research.fractal_poi import FractalPOI, FractalSettings, partners_for, warmup_days
from algo_research.fractal_poi import defaults as fractal_defaults
from algo_research.frame import frame_from_data
from algo_research.narrative import PriceBasis
from algo_research.races import RaceCosts
from algo_research.replay.bars import ReplayBars
from algo_research.replay.server import static_file
from algo_research.replay.timeframes import TIMEFRAMES, seconds_of, wall_seconds
from algo_research.snapshot import SNAPSHOTS_DIR
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.grader.sequence import SetupSequenceDetector, _EntryWindow
from liquidity_engine.grader.setup_grader import _ENTRY_ELIGIBLE_TIMEFRAMES
from liquidity_engine.models import BiasDirection, PDArray, SetupSequence, Timeframe
from services.market_data.as_of_view import compose_as_of_view
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["SnapshotSource", "WatchSession", "live_feed", "live_first_day", "make_watch_server", "serve"]

NY = "America/New_York"
STATIC = REPO_ROOT / "algo_research" / "replay" / "static"
FILES = {"engine.html": "text/html; charset=utf-8", "engine.js": "text/javascript; charset=utf-8",
         "drawings.js": "text/javascript; charset=utf-8", "settings.js": "text/javascript; charset=utf-8",
         "motion.js": "text/javascript; charset=utf-8", "noculus.js": "text/javascript; charset=utf-8",
         "fractal.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8"}
MAX_DAYS = 5
KEPT_SESSIONS = 3
#: The trader's picks against the engine's choice (Requirement 16.3): local, git-ignored.
PICKS = REPO_ROOT / "data" / "journal" / "watch_picks.jsonl"
_CALENDAR = StrategyCalendar()
_ARRAYS_SHOWN, _POOLS_SHOWN, _CANDIDATES_SHOWN = 80, 50, 30
#: Model A on the chart (context-engine Requirement 17): the trader's frame sets, and how long an ended instance
#: that reached the manipulation stays drawn (one F candle).
MODEL_A_SETS = ("model_d1", "model_h4")
_MODEL_A_KEEP = {"model_d1": 86400, "model_h4": 4 * 3600}
_MODEL_A_HISTORY = pd.Timedelta(days=100)
#: The indicator readers a session keeps (chart timeframe x computing inputs), and the events it sends.
_FRACTAL_READERS, _FRACTAL_EVENTS = 4, 200
#: How often a live session watched by a page reads the terminal again (Requirement 27.2), in seconds.
LIVE_EVERY = 30


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
        return stored_bars(f[(f["time"] >= pd.Timestamp(start)) & (f["time"] < pd.Timestamp(end))], instrument, Timeframe.M1)

    def last_time(self, instrument: str, tf: Timeframe) -> Optional[datetime]:
        f = self._frame(instrument)
        return None if f.empty or tf != Timeframe.M1 else f["time"].iloc[-1].to_pydatetime()

    def held(self) -> list[str]:
        return [path.name.split("_")[0] for path in self.root.glob("*_M1.parquet")]


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


class Candidate(NamedTuple):
    """An entry-eligible array the sequence detector looks at (Requirement 16.2): the sequence that leads to it and
    the key it is ranked by, or None for both when no raid, CISD and intact swing lead to it."""
    array: PDArray
    sequence: Optional[SetupSequence]
    key: Optional[tuple]


def ranked_candidates(candles_by_tf, pd_arrays, as_of) -> list[Candidate]:
    """``SetupSequenceDetector.detect``'s own ranking, from its own parts, listing every array instead of keeping
    the best: those with a sequence first, best first (the engine's choice leads), then those without. The engine's
    code stays as it is (its fingerprint keys the signal cache); the tests hold the two to the same choice."""
    arrays_by_tf: dict = {}
    for array in pd_arrays:
        if (not array.is_filled and array.timeframe in _ENTRY_ELIGIBLE_TIMEFRAMES
                and array.direction != BiasDirection.NEUTRAL and candles_by_tf.get(array.timeframe)):
            arrays_by_tf.setdefault(array.timeframe, []).append(array)
    if not arrays_by_tf:
        return []
    pools = SetupSequenceDetector().pools(candles_by_tf, as_of)
    ranked, without = [], []
    for tf, arrays in arrays_by_tf.items():
        window = _EntryWindow(tf, candles_by_tf, pools)
        for array in arrays:
            found = window.sequence_for(array)
            if found is None:
                without.append(Candidate(array, None, None))
                continue
            sequence, weight = found
            ranked.append(Candidate(array, sequence,
                                    (sequence.raid.raided_at, weight, array.strength_score, array.formed_at, array.array_id)))
    return sorted(ranked, key=lambda c: c.key, reverse=True) + without


class WatchSession:
    """One instrument over a few trading days: the backtest's journal, the chart's bars and the engine's state."""

    def __init__(self, config: Path, variant: Optional[str], instrument: str, first_day: date, days: int,
                 snapshot: Path, studies_root: Path = REPO_ROOT, blind: bool = False,
                 live: Optional[LiveSource] = None) -> None:
        self.config, self.variant, self.instrument = Path(config), variant, instrument.upper()
        self.first_day, self.days = first_day, days
        # Noculus (Requirement 17.2): a blind session keeps the engine's work to itself until the trader reveals it.
        self.blind, self.revealed_at = bool(blind), None
        self.noculus: Optional[NoculusJournal] = None
        self.snapshot, self.studies_root = Path(snapshot), studies_root
        # Live (Requirement 27): the terminal's candles, a window that ends at its last closed minute, and the
        # engine's record at each close kept, so moving on reads only the new closes.
        self.live = live is not None
        self.source = live if live is not None else SnapshotSource(self.snapshot)
        self.version = 0
        self._records: dict = {}
        self._refreshing, self._refreshed_at = False, 0.0
        self._refresh_lock = threading.Lock()           # one refresh at a time
        self.state, self.progress, self.message = "preparing", 0.0, "loading candles"
        self.start = pd.Timestamp(trading_date_open(first_day))
        self.end = pd.Timestamp(trading_date_open(first_day + timedelta(days=days)))
        self.bars: Optional[ReplayBars] = None
        self.frame = None                      # the races' own view of the M1 (prices, spread, costs)
        self.path: dict = {}
        self.costs: Optional[RaceCosts] = None
        self.journal: list[dict] = []
        self.ideas: list[dict] = []            # the engine's orders and refused trades, priced (Requirement 26.1)
        self._ranges: dict[int, dict] = {}     # the average ranges at each position's clock, read once
        self.states: dict[int, dict] = {}
        self._keys: list[int] = []
        self.summary: dict = {}
        self.model_a: dict[str, list[dict]] = {}
        self._fractal: "OrderedDict[tuple, FractalPOI]" = OrderedDict()
        self._fractal_lock = threading.Lock()
        self._snapshot_m1: dict[str, pd.DataFrame] = {}

    # ── preparing ───────────────────────────────────────────────────────────
    def prepare(self) -> None:
        try:
            self._prepare()
            self._refreshed_at = time.monotonic()
            self.state, self.progress, self.message = "ready", 1.0, ""
        except Exception as exc:  # shown on the page; the server keeps running
            self.state, self.message = "error", f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

    def refresh(self) -> None:
        """A live session moves on to the terminal's last closed minute (Requirement 27.2): the new candles, the
        engine at each new close, then the account again. The page keeps reading the session meanwhile."""
        with self._refresh_lock:
            self._refreshed_at = time.monotonic()
            try:
                before = self.end
                self._prepare()
                if self.end != before:
                    self.version += 1
                self.message = ""
            except Exception as exc:  # the session stays as it was; the page shows why
                self.message = f"the live refresh failed: {type(exc).__name__}: {exc}"
                traceback.print_exc()
            finally:
                self._refreshing = False

    def _maybe_refresh(self) -> None:
        """While a page asks after a live session, read the terminal again every LIVE_EVERY seconds, in the background."""
        if not self.live or self.state != "ready" or self._refreshing or time.monotonic() - self._refreshed_at < LIVE_EVERY:
            return
        self._refreshing, self._refreshed_at = True, time.monotonic()
        threading.Thread(target=self.refresh, daemon=True).start()

    def _prepare(self) -> None:
        cfg = load_run_config(self.config, self.variant)
        end = self.end                 # a live session's new end is shown with the states that reach it, not before
        if self.live:
            self.source.refresh(self.instrument)
            last = self.source.last_time(self.instrument, Timeframe.M1)
            if last is None:
                raise LookupError(f"the terminal has no M1 for {self.instrument}")
            end = pd.Timestamp(last) + pd.Timedelta(minutes=1)
        run_start = (self.start - pd.Timedelta(hours=12)).date()
        # A live run reaches past the clock to the end of its UTC day; it holds no candle after the clock.
        run_end = end.date() + timedelta(days=1) if self.live else (end + pd.Timedelta(hours=12)).date()
        cfg = cfg.model_copy(update={"run": cfg.run.model_copy(update={"instruments": (self.instrument,),
                                                                         "start": run_start, "end": run_end})})
        profile = load_profile(cfg.run.profile)
        specs = profile.specs()
        study = load_or_create_study(cfg.run.study, date.today(), self.studies_root)
        start_dt = datetime(run_start.year, run_start.month, run_start.day, tzinfo=timezone.utc)
        end_dt = datetime(run_end.year, run_end.month, run_end.day, tzinfo=timezone.utc)
        data = load_instrument(self.source, self.instrument, start_dt, end_dt, cfg.strategy,
                               profile.clock() if profile.venue == "mt5" else None, venue=profile.venue,
                               max_gap_minutes=cfg.data.max_gap_minutes)
        m1 = pd.DataFrame({"time": [b.timestamp for b in data.m1], "open": [b.open for b in data.m1],
                           "high": [b.high for b in data.m1], "low": [b.low for b in data.m1],
                           "close": [b.close for b in data.m1]})
        self.bars = ReplayBars(m1, self.instrument, PriceBasis(instruments=()))   # the engine's own prices, unflattened
        # What a pseudo trade is priced on (Requirement 19.2): the same M1 and costs the races use, in wall seconds.
        spec = specs[self.instrument]
        self.frame = frame_from_data(data, spec.default_spread, spec.stop_slippage)
        self.costs = RaceCosts.from_spec(spec, specs.account_ccy)
        self.path = {"time": np.asarray(wall_seconds(self.frame.m1["time"]), dtype=np.int64),
                     **{k: self.frame.arrays[k] for k in ("open", "high", "low", "close", "spread")}}
        # Phase A, once a close: the backtest's own records, with the engine's view of each close kept for the page.
        # A live session's earlier closes read the same closed candles, so only the new ones are read.
        closes = entry_closes(data, cfg.strategy.entry_tf, start_dt, end_dt)
        spread = spec.default_spread
        engine = _Capturing(cfg.strategy.fvg_zone)
        states = dict(self.states)
        new = [t for t in closes if t not in self._records]
        for n, t in enumerate(new):
            if self.state == "preparing":
                self.message = f"the engine at close {n + 1} of {len(new)}"
            engine.last = None
            self._records[t] = signals_at(data, (cfg.strategy,), t, engine, spread)[0]
            try:
                state = (self._state(*engine.last, t, cfg.strategy.entry_tf) if engine.last
                         else {"error": "the engine raised: see the decision"})
            except Exception as exc:
                state = {"error": f"{type(exc).__name__}: {exc}"}
            state["t"] = wall(t)
            states[state["t"]] = state
            if self.state == "preparing":
                self.progress = 0.05 + 0.85 * (n + 1) / max(1, len(new))
        records = [self._records[t] for t in closes]
        # Phase B: the backtest itself, served those records from a temporary cache. A live session is forward data,
        # the days being traded now: the hold-out guard, which keeps a fixed past unread for the final run, is not
        # its question (D40).
        if self.state == "preparing":
            self.message = "simulating the account (orders, fills, exits)"
        with tempfile.TemporaryDirectory(prefix="watch-") as tmp:
            cache = SignalCache(Path(tmp), engine_code_fingerprint())
            cache.store(cache.key(data, cfg.strategy, start_dt, end_dt, spread), records)
            result = run_backtest(cfg, study, self.live, {self.instrument: data}, specs, cache=cache, workers=1)
        frame = pd.read_csv(io.StringIO(journal_csv(result.journal, result.open_orders)))
        journal = [self._journal_row(r) for r in frame.to_dict("records")]
        self._paths(data.m1, journal, end)
        self.ideas = engine_ideas(journal, self.path, wall(end), self.costs,
                                  step=seconds_of(cfg.strategy.entry_tf.value))
        self.journal = journal
        decisions = {r["t"]: r for r in journal}
        for w_, state in states.items():
            state["decision"] = decisions.get(w_)
        filled = [r for r in journal if r["net_r"] is not None and r["filled_at"] is not None]
        self.summary = {"orders": sum(1 for r in journal if r["decision"] == "EXECUTE"), "trades": len(filled),
                        "total_r": round(sum(r["net_r"] for r in filled), 2)}
        self.states, self._keys, self.end = states, sorted(states), end
        if self.state == "preparing":
            self.message = "reading Model A"
        if self.live:                                   # the indicator reads the new minutes too
            with self._fractal_lock:
                self._snapshot_m1.clear()
                self._fractal.clear()
        self.model_a = self._read_model_a()

    def _paths(self, m1, journal: list[dict], end: pd.Timestamp) -> None:
        """Each filled trade's best and worst point from the fill to the exit (or the session's end), in R and at
        their times (Requirement 16.1). The backtest never moves a stop or takes a partial, so this is all the
        managing there was to see. Within the fill's minute the extremes may precede the fill."""
        times = np.array(wall_seconds([b.timestamp for b in m1])) if m1 else np.array([], dtype=np.int64)
        highs = np.array([b.high for b in m1]); lows = np.array([b.low for b in m1])
        end_of_session = wall(end)
        for r in journal:
            r["path"] = None
            if r["filled_at"] is None or r["fill"] is None or r["stop"] is None or r["fill"] == r["stop"]:
                continue
            end = r["closed_at"] if r["closed_at"] is not None else end_of_session
            lo_i = max(0, int(np.searchsorted(times, r["filled_at"], side="right")) - 1)
            hi_i = int(np.searchsorted(times, end, side="right"))
            long_ = r["direction"] == "LONG"
            risk = abs(r["fill"] - r["stop"])
            best, best_at, worst, worst_at = r["fill"], r["filled_at"], r["fill"], r["filled_at"]
            if hi_i > lo_i:
                up, down = highs[lo_i:hi_i], lows[lo_i:hi_i]
                i_up, i_down = int(np.argmax(up)), int(np.argmin(down))
                fav, adv = (up, down) if long_ else (down, up)
                i_fav, i_adv = (i_up, i_down) if long_ else (i_down, i_up)
                if (fav[i_fav] > best) if long_ else (fav[i_fav] < best):
                    best, best_at = float(fav[i_fav]), max(int(times[lo_i + i_fav]), r["filled_at"])
                if (adv[i_adv] < worst) if long_ else (adv[i_adv] > worst):
                    worst, worst_at = float(adv[i_adv]), max(int(times[lo_i + i_adv]), r["filled_at"])
            sign = 1 if long_ else -1
            r["path"] = {"best": best, "best_at": min(best_at, end), "best_r": round(sign * (best - r["fill"]) / risk, 2),
                         "worst": worst, "worst_at": min(worst_at, end), "worst_r": round(sign * (worst - r["fill"]) / risk, 2)}

    # ── blind until revealed (Requirement 17.2, 17.3) ───────────────────────
    @property
    def withheld(self) -> bool:
        """Whether the engine's side of the session is still out of the trader's sight."""
        return self.blind and self.revealed_at is None

    def reveal(self, w: int) -> dict:
        """Show the engine's work up to the clock ``w``, and play on as an ordinary session. It can't be undone."""
        if not self.blind:
            raise LookupError("the session is not blind: there is nothing to reveal")
        if self.revealed_at is not None:
            raise LookupError(f"the session was already revealed at {self.revealed_at}")
        self.revealed_at = min(int(w), wall(self.end))
        if self.noculus is not None:
            self.noculus.data["reveal"] = {"t": self.revealed_at,
                                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self.comparison()                              # the diff, as it stood at the reveal (Requirement 20.2)
        return self.status()

    def comparison(self) -> dict:
        """The trader's reading of the session against the engine's, kept with the session (Requirement 20)."""
        journal = self.own_journal()
        if self.withheld:
            raise LookupError("the session is blind: reveal it before comparing, or the engine's arrays leak")
        clock = self.revealed_at if self.revealed_at is not None else wall(self.end)
        for trade in journal.data["trades"]:
            settle(trade, self.path, clock, self.costs)
        closes = self._keys[:bisect_right(self._keys, clock)]
        shown = [a for t in closes for a in self.states[t].get("arrays") or []]      # every close's, oldest first
        alive = (self.states[closes[-1]].get("arrays") or []) if closes else []
        journal.data["comparison"] = compare(journal.data["marks"], journal.data["trades"], shown, self.journal,
                                             clock, alive=alive, since=wall(self.start))
        journal.save()
        return journal.data["comparison"]

    def journal_rows(self) -> list[dict]:
        """The backtest's orders and trades, or nothing at all while the session is blind."""
        return [] if self.withheld else self.journal

    def engine_ideas(self) -> list[dict]:
        """The engine's orders and the trades its limits refused, or nothing while the session is blind."""
        return [] if self.withheld else self.ideas

    # ── the trader's own marks (Requirement 18) ─────────────────────────────
    def own_journal(self) -> NoculusJournal:
        if self.noculus is None:
            raise LookupError("the session keeps no Noculus journal: start it blind")
        return self.noculus

    def _still_marking(self) -> NoculusJournal:
        """The journal, while the trader may still add to their read: once the engine is seen it is closed, so
        nothing made after can pass for a blind read. An open trade can still be closed."""
        journal = self.own_journal()
        if not self.blind:
            raise LookupError("marks and the ticket are made blind: start the session blind (positions work in any)")
        if self.revealed_at is not None:
            raise LookupError(f"the session was revealed at {self.revealed_at}: the marking is done")
        return journal

    def _marking_bars(self, tf: str, clock: int) -> pd.DataFrame:
        """Every ``tf`` bar of the session up to the clock, so a click finds the candle it landed on."""
        return self.bars.as_of(tf, from_wall(clock), since=wall(self.bars.m1["time"].min()))

    def mark(self, body: dict) -> dict:
        """Mark an array by its candles, at the replay clock (Requirement 18.1)."""
        journal = self._still_marking()
        tf, clock = str(body.get("tf", "M15")), min(int(body["t"]), wall(self.end))
        record = build_mark(self._marking_bars(tf, clock), tool=str(body.get("tool", "FVG")), tf=tf, clock=clock,
                            candle=int(body["candle"]), direction=body.get("direction"), note=body.get("note") or "")
        return journal.add_mark(record)

    def unmark(self, body: dict) -> dict:
        """Delete one of the trader's marks, keeping it with the clock at which it went (Requirement 18.3)."""
        return self._still_marking().delete_mark(str(body["id"]), min(int(body["t"]), wall(self.end)))

    # ── the trader's own trades (Requirement 19) ────────────────────────────
    def place(self, body: dict) -> dict:
        """A pseudo trade at the replay clock. A limit with no expiry of its own runs to the session's end."""
        journal = self._still_marking()
        clock = min(int(body["t"]), wall(self.end))
        return journal.add_trade(place(body, self.path, clock, until=wall(self.end)))

    # ── the trader's positions beside the engine's ideas (Requirements 25-26) ──
    def place_position(self, body: dict) -> dict:
        """A drawn position placed at the clock, in any session that keeps a journal (Requirement 25.2-25.3).

        It becomes a market order or a limit by where its entry sits (D37). It records its drawing and whether the
        engine was in sight when it was placed, so a position made after seeing the engine never passes for a
        blind read (D39)."""
        journal = self.own_journal()
        clock = min(int(body["t"]), wall(self.end))
        trade = place(position_ticket(body, self.path, clock), self.path, clock, until=wall(self.end))
        trade.update(entry=float(body["entry"]), drawing=str(body.get("drawing") or "") or None,
                     engine_seen=not self.withheld)
        return journal.add_trade(trade)

    def positions(self, q: dict) -> dict:
        """Every trade of the trader's, settled to the clock, beside the engine's idea at its own clock (26.2-26.4).

        While blind the engine's side is withheld; once it is in sight the pairs are kept with the session."""
        journal = self.own_journal()
        clock = min(int(q.get("t") or wall(self.end)), wall(self.end))
        self.trades({"t": clock})

        def ranges_at(at: int) -> dict:
            if at not in self._ranges:
                self._ranges[at] = average_ranges(self._m1(self.instrument, 30), at)
            return self._ranges[at]

        out = compare_positions(journal.data["trades"], self.ideas, ranges_at, clock, hidden=self.withheld)
        if not self.withheld:
            kept = journal.data.get("positions") or {}
            changed = json.dumps([kept.get("pairs"), kept.get("summary")], sort_keys=True, default=str) !=                 json.dumps([out["pairs"], out["summary"]], sort_keys=True, default=str)
            journal.data["positions"] = out
            if changed:
                journal.save()                              # the page asks on every tick; write only on a change
        return out

    def trades(self, body: dict) -> list[dict]:
        """Every pseudo trade, each advanced to the clock. The journal keeps what they have become."""
        journal = self.own_journal()
        clock = min(int(body.get("t") or wall(self.end)), wall(self.end))
        rows = journal.data["trades"]
        before = json.dumps(rows, sort_keys=True)
        for trade in rows:
            settle(trade, self.path, clock, self.costs)
        if json.dumps(rows, sort_keys=True) != before:
            journal.save()                                  # the page asks on every tick; write only on a change
        return rows

    def close_trade(self, body: dict) -> dict:
        """The trader's own exit at the clock (Requirement 19.3)."""
        journal = self.own_journal()
        clock = min(int(body["t"]), wall(self.end))
        trade = close_trade(journal.trade(str(body["id"])), self.path, clock, self.costs)
        journal.save()
        return trade

    def save_pick(self, body: dict, path: Optional[Path] = None) -> dict:
        """The trader's pick at a close: one of the ranked candidates, "none" or "other" (Requirement 16.3)."""
        if self.withheld:
            raise LookupError("the session is blind: reveal it before picking among the engine's candidates")
        t = int(body["t"])
        if t not in self.states:
            raise KeyError(f"t: {t} is not one of the session's closes")
        state = self.states[t]
        ranked = (state.get("candidates") or {}).get("ranked", [])
        pick = str(body.get("pick") or "")
        by_id = {c["id"]: c for c in ranked}
        if pick not in by_id and pick not in ("none", "other"):
            raise ValueError("pick: one of the close's candidates, none or other")
        chosen = next((c for c in ranked if c["chosen"]), None)
        brief = lambda c: None if c is None else {k: c[k] for k in ("id", "rank", "tf", "type", "dir", "low", "high", "raid")}  # noqa: E731
        line = {"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "instrument": self.instrument,
                "variant": self.variant or "base", "first_day": self.first_day.isoformat(), "t": t,
                "t_ny": from_wall(t).tz_convert(NY).isoformat(), "pick": pick, "picked": brief(by_id.get(pick)),
                "engine": chosen["id"] if chosen else None, "engine_choice": brief(chosen),
                "decision": (state.get("decision") or {}).get("decision"), "note": str(body.get("note") or "")[:1000]}
        path = Path(path or PICKS)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        return line

    def picks(self, path: Optional[Path] = None) -> list[dict]:
        """This session's picks, latest per close."""
        path = Path(path or PICKS)
        if not path.exists():
            return []
        latest: dict[int, dict] = {}
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            if line.get("instrument") == self.instrument and int(line.get("t", -1)) in self.states:
                latest[int(line["t"])] = line
        return [latest[k] for k in sorted(latest)]

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

    def _state(self, lm, view, seen, t: datetime, entry_tf: Timeframe) -> dict:
        price = view[entry_tf][-1].close if view.get(entry_tf) else None
        days = view.get(Timeframe.D1, [])[-6:]
        lo = min((c.low for c in days), default=price) if price else None
        hi = max((c.high for c in days), default=price) if price else None
        pad = (hi - lo) * 0.6 if lo is not None else 0
        near = (lambda p: lo - pad <= p <= hi + pad) if lo is not None else (lambda p: True)
        unique = {a.array_id: a for a in reversed(lm.pd_arrays)}           # one of each: the list can repeat an array
        arrays = [a for a in unique.values() if not a.is_filled and (near(a.high) or near(a.low))]
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
                "grade": grade, "bias": bias, "candidates": self._candidates(seen, seq, t)}

    @staticmethod
    def _candidates(seen, chosen_sequence, t: datetime) -> dict:
        """The arrays the sequence detector ranked at this close, best first, and how many had no sequence."""
        ranked, without, ids = [], {}, set()
        for c in seen or ():
            a = c.array
            if a.array_id in ids:                   # the engine's list can hold one array more than once
                continue
            ids.add(a.array_id)
            if c.sequence is None:
                without[a.timeframe.value] = without.get(a.timeframe.value, 0) + 1
                continue
            if len(ranked) >= _CANDIDATES_SHOWN:
                continue
            s = c.sequence
            ranked.append({
                "id": a.array_id, "rank": len(ranked) + 1, "tf": a.timeframe.value, "type": a.array_type.value, "dir": a.direction.value,
                "low": a.low, "high": a.high, "formed": wall(a.formed_at), "strength": round(a.strength_score, 3),
                "mt": None if a.ob_candle_open is None else (a.ob_candle_open + a.ob_candle_close) / 2,
                "raid": {"side": s.raid.pool.side.value, "source": s.raid.pool.source.value, "tf": s.raid.pool.timeframe.value,
                         "price": s.raid.pool.price, "at": wall(s.raid.raided_at),
                         "age_h": round((pd.Timestamp(t) - pd.Timestamp(s.raid.raided_at)).total_seconds() / 3600, 1)},
                "cisd": wall(s.cisd_at), "protected": s.protected_swing.wick, "weight": c.key[1],
                "chosen": bool(chosen_sequence is not None and a.array_id == chosen_sequence.entry_array_id and not ranked),
            })
        return {"ranked": ranked, "without": without}

    # ── what the page asks ──────────────────────────────────────────────────
    def status(self) -> dict:
        self._maybe_refresh()
        return {"state": self.state, "progress": round(self.progress, 3), "message": self.message, "instrument": self.instrument,
                "variant": self.variant or "base", "first_day": self.first_day.isoformat(), "days": self.days,
                "start": wall(self.start), "end": wall(self.end), "digits": self.bars.digits if self.bars else 5,
                "summary": {} if self.withheld else self.summary, "closes": len(self._keys),
                "blind": self.blind, "revealed_at": self.revealed_at, "live": self.live, "version": self.version}

    def _read_model_a(self) -> dict[str, list[dict]]:
        """Model A's instances over the session, both of the trader's frame sets, both sides (Requirement 17), with
        volatility and time (``MODEL_A_VT``, Requirement 18), on the session's prices with 100 days of history."""
        from liquidity_engine.context.model_a import MODEL_A_VT, MODEL_SETS, ModelAReader
        frame = self.source._frame(self.instrument)
        frame = frame[(frame["time"] >= self.start - _MODEL_A_HISTORY) & (frame["time"] < self.end)]
        if frame.empty:
            return {}
        walls = wall_seconds(frame["time"])
        o, h, l, c = (frame[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        out = {}
        for name in MODEL_A_SETS:
            rows = []
            for side in ("SHORT", "LONG"):
                rows += ModelAReader(MODEL_SETS[name], walls, o, h, l, c, side=side,
                                     variant=MODEL_A_VT).run(wall(self.start), wall(self.end))
            out[name] = sorted(rows, key=lambda x: x["states"]["FRAMED"])
        return out

    def model_a_at(self, name: str, w: int) -> list[dict]:
        """The instances of a frame set as the chart may show them at ``w``: the live one, and those that reached
        the manipulation and ended within one F candle. Every level appears only once its state is reached (C2's
        extreme once C2 has closed; the order once C2 has rejected and price displaced), so nothing comes from
        after the clock."""
        if name not in self.model_a:
            raise ValueError(f"set: one of {', '.join(self.model_a) or MODEL_A_SETS}")
        if self.withheld:
            return []                                           # the engine's reading of the frames: out of sight
        keep, out = _MODEL_A_KEEP.get(name, 86400), []
        base = ("side", "set", "f", "c", "e", "poi_kind", "poi_label", "poi_near", "poi_far", "f_range", "c1_open",
                "c1_extreme", "c1_opposite", "phase")
        for x in self.model_a[name]:
            if x["states"]["FRAMED"] > w:
                break
            ended = x["end_at"] is not None and x["end_at"] <= w
            if ended and ("MANIPULATED" not in x["states"] or x["end_at"] < w - keep):
                continue
            events = [list(e) for e in x["events"] if e[1] <= w]
            reached = {e[0] for e in events}
            y = {k: x[k] for k in base}
            y.update(events=events, state=events[-1][0], reason=events[-1][2], ended=x["end"] if ended else None,
                     end_at=x["end_at"] if ended else None)
            if "MANIPULATED" in reached:
                y.update(time_sync=x["time_sync"], inducement=x["inducement"])
            if "REJECTED" in reached or (ended and x["end"] in ("RANGE_SPENT", "TOO_LARGE", "NO_ROOM")):
                y.update({k: x[k] for k in ("c2_extreme", "adr_used", "size_adr", "target_reach")})   # C2 has closed
            if "REJECTED" in reached and "DISPLACED" in reached and x["entry"] is not None:
                y.update({k: x[k] for k in ("range_end", "entry", "stop", "ote_near", "ote_far", "tp1", "sd1", "sd2", "sd25")})
                y["order_at"] = max(x["states"]["REJECTED"], x["states"]["DISPLACED"])
            if "ENTERED" in reached:
                y["fill"] = x["fill"]
            out.append(y)
        return out

    # ── the trader's indicator (Requirements 21-23) ─────────────────────────
    def _m1(self, instrument: str, days: int) -> pd.DataFrame:
        """The session's M1 (the snapshot's or the terminal's) for ``instrument`` from ``days`` before the session to
        its end."""
        if instrument not in self._snapshot_m1:
            frame = self.source._frame(instrument)
            self._snapshot_m1[instrument] = frame[["time", "open", "high", "low", "close"]]
        frame = self._snapshot_m1[instrument]
        return frame[(frame["time"] >= self.start - pd.Timedelta(days=days)) & (frame["time"] < self.end)]

    def fractal(self, q: dict) -> dict:
        """The Fractal + POI indicator at the clock ``t`` on a chart of ``tf``, with the settings ``s`` (JSON).

        A reader is kept per chart timeframe and computing inputs, so playing forward reads only the new
        candles, and changing a drawing input only redraws. The events are the session's own, the latest few."""
        tf, t = str(q.get("tf") or "M15"), int(q["t"])
        settings = FractalSettings.from_dict(json.loads(q.get("s") or "{}"))
        key = (tf, settings.compute_key())
        with self._fractal_lock:
            reader = self._fractal.pop(key, None)
            if reader is None:
                days = warmup_days(tf, settings)
                held = self.source.held()
                partners = {name: (self._m1(name, days), inverse)
                            for name, inverse in partners_for(self.instrument, settings, held)}
                reader = FractalPOI(self._m1(self.instrument, days), tf, settings, self.instrument, partners)
            self._fractal[key] = reader
            while len(self._fractal) > _FRACTAL_READERS:
                self._fractal.popitem(last=False)
            view = reader.at(min(t, wall(self.end)), settings)
        since = wall(self.start)
        view["events"] = [e for e in view["events"] if e["t"] >= since][-_FRACTAL_EVENTS:]
        return view

    def state_at(self, w: int) -> Optional[dict]:
        i = bisect_right(self._keys, int(w)) - 1
        if i < 0:
            return None
        return {"t": self._keys[i], "withheld": True} if self.withheld else self.states[self._keys[i]]

    def bars_until(self, tf: str, until: int, since: Optional[int]) -> list[dict]:
        seconds_of(tf)
        frame = self.bars.as_of(tf, from_wall(min(int(until), wall(self.end))), since=since)
        return [{"time": int(r.time), "open": float(r.open), "high": float(r.high), "low": float(r.low), "close": float(r.close)}
                for r in frame.itertuples()]


class _Capturing:
    """The engine, keeping the last view and map it produced, for the page."""

    def __init__(self, fvg_zone: str = "candles") -> None:
        self.engine = LiquidityMappingEngine(fvg_zone)
        self.last = None

    def analyze(self, view, instrument, t):
        lm = self.engine.analyze(view, instrument, t)
        self.last = (lm, view, ranked_candidates(view, lm.pd_arrays, t))   # what the detector ranked, for the page
        return lm


def live_first_day(now: datetime, days: int) -> date:
    """The first trading date of a live window of ``days`` that ends now: today's trading date (from 17:00 New
    York; a weekend's is Friday's) and the weekdays before it."""
    day = (pd.Timestamp(now).tz_convert(NY) + pd.Timedelta(hours=7)).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    for _ in range(days - 1):
        day -= timedelta(days=3 if day.weekday() == 0 else 1)
    return day


def live_feed(config: Path) -> Optional[Callable[[], LiveSource]]:
    """The broker's terminal for live sessions (Requirement 27), from the configuration's profile; None when the
    profile isn't an MT5 one. The terminal connects on the first live session, not before."""
    profile = load_profile(load_run_config(Path(config), None).run.profile)
    if profile.venue != "mt5":
        return None
    research = load_research_config()
    return lambda: LiveSource(Terminal(profile), research.instruments)


class WatchApp:
    def __init__(self, config: Path, snapshot: Path, slice_: tuple[date, date], picks: Optional[Path] = None,
                 noculus_root: Optional[Path] = None, studies_root: Path = REPO_ROOT,
                 live: Optional[Callable[[], LiveSource]] = None) -> None:
        self.config, self.snapshot, self.slice = Path(config), Path(snapshot), slice_
        self.picks_path = Path(picks) if picks else PICKS
        self.noculus_root = Path(noculus_root) if noculus_root else NOCULUS_DIR
        self.studies_root = Path(studies_root)
        self.session: Optional[WatchSession] = None
        self._kept: dict[tuple, WatchSession] = {}          # the last few sessions, so a tab can come back to one
        self._live_feed, self._live = live, None             # the terminal, made on the first live session

    def live_source(self) -> LiveSource:
        if self._live_feed is None:
            raise ValueError("live: this server has no live feed (its profile is not an MT5 broker's)")
        if self._live is None:
            self._live = self._live_feed()
        return self._live

    def meta(self) -> dict:
        import tomllib
        variants = sorted(tomllib.loads(self.config.read_text(encoding="utf-8")).get("variants", {}))
        instruments = sorted(p.name.split("_")[0] for p in self.snapshot.glob("*_M1.parquet"))
        return {"instruments": instruments, "variants": ["base", *variants], "live": self._live_feed is not None,
                "first": self.slice[0].isoformat(),
                "last": (self.slice[1] - timedelta(days=1)).isoformat(), "max_days": MAX_DAYS, "timeframes": list(TIMEFRAMES),
                "config": str(self.config.relative_to(REPO_ROOT) if self.config.is_relative_to(REPO_ROOT) else self.config)}

    def start(self, body: dict) -> dict:
        days = int(body.get("days", 1))
        if not 1 <= days <= MAX_DAYS:
            raise ValueError(f"days: 1 to {MAX_DAYS}")
        live = self.live_source() if body.get("live") else None
        if live is not None:                                 # the last ``days`` trading days, up to now (Requirement 27.1)
            day = live_first_day(live.now(), days)
        else:
            day = date.fromisoformat(str(body.get("first_day")))
            if not self.slice[0] <= day < self.slice[1]:
                raise ValueError(f"first_day: within the exploration slice, {self.slice[0]} to {self.slice[1] - timedelta(days=1)}")
        variant = body.get("variant") or "base"
        instrument = str(body.get("instrument", "XAUUSD")).upper()
        blind = bool(body.get("blind"))
        key = (instrument, day, days, variant, blind, live is not None)   # blind, open and live sessions are apart
        kept = self._kept.get(key)
        if kept is not None and kept.state != "error":
            self.session = kept
            return kept.status()
        session = WatchSession(self.config, None if variant == "base" else variant, instrument, day, days, self.snapshot,
                               studies_root=self.studies_root, blind=blind, live=live)
        session.noculus = self._journal(session)            # an open session's positions are kept too (D39)
        if blind:
            reveal = session.noculus.data.get("reveal")
            if reveal:                                       # the engine was seen once: it can't be un-seen
                session.revealed_at = int(reveal["t"])
        self.session = self._kept[key] = session
        while len(self._kept) > KEPT_SESSIONS:
            self._kept.pop(next(iter(self._kept)))
        threading.Thread(target=session.prepare, daemon=True).start()
        return session.status()

    def _journal(self, session: WatchSession) -> NoculusJournal:
        """A session's own journal, one file per instrument and window (Requirement 17.4); an open session's
        is apart from the blind one's over the same days (D39)."""
        name = f"{'live-' if session.live else ''}{session.first_day.isoformat()}-{session.days}d-{session.variant or 'base'}"
        name += ".json" if session.blind else "-open.json"
        return NoculusJournal(self.noculus_root / session.instrument / name,
                              {"instrument": session.instrument, "first_day": session.first_day.isoformat(),
                               "days": session.days, "variant": session.variant or "base", "live": session.live,
                               "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})

    def need(self) -> WatchSession:
        if self.session is None:
            raise LookupError("no session: start one")
        if self.session.state != "ready":
            raise LookupError(f"the session is {self.session.state}")
        return self.session

    def need_journal(self) -> NoculusJournal:
        session = self.need()
        if session.noculus is None:
            raise LookupError("the session keeps no Noculus journal")
        return session.noculus


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
        served = static_file(name) if (url.path in ("/", "/index.html") or url.path.startswith("/static/")) else None
        if served is not None:
            self._send(200, *served)
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
            self._answer(lambda: {"rows": self.app.need().journal_rows(), "ideas": self.app.need().engine_ideas()})
        elif url.path == "/api/watch/noculus":
            self._answer(lambda: self.app.need_journal().data)
        elif url.path == "/api/watch/noculus/trades":
            self._answer(lambda: {"trades": self.app.need().trades(q)})
        elif url.path == "/api/watch/noculus/positions":
            self._answer(lambda: self.app.need().positions(q))
        elif url.path == "/api/watch/noculus/comparison":
            self._answer(self.app.need().comparison)
        elif url.path == "/api/watch/fractal-defaults":
            self._answer(fractal_defaults)
        elif url.path == "/api/watch/fractal":
            self._answer(lambda: self.app.need().fractal(q))
        elif url.path == "/api/watch/model-a":
            self._answer(lambda: {"set": q.get("set", "model_d1"),
                                  "instances": self.app.need().model_a_at(q.get("set", "model_d1"), int(q["t"]))})
        elif url.path == "/api/watch/picks":
            self._answer(lambda: {"picks": self.app.need().picks(self.app.picks_path)})
        else:
            self._send(404, {"error": f"no such path {url.path}"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in ("/api/watch/start", "/api/watch/pick", "/api/watch/reveal", "/api/watch/noculus/mark",
                        "/api/watch/noculus/unmark", "/api/watch/noculus/place", "/api/watch/noculus/close",
                        "/api/watch/noculus/position"):
            self._send(404, {"error": f"no such path {self.path}"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return
        if path == "/api/watch/pick":
            self._answer(lambda: self.app.need().save_pick(body, self.app.picks_path))
        elif path == "/api/watch/reveal":
            self._answer(lambda: self.app.need().reveal(int(body["t"])))
        elif path == "/api/watch/noculus/mark":
            self._answer(lambda: self.app.need().mark(body))
        elif path == "/api/watch/noculus/unmark":
            self._answer(lambda: self.app.need().unmark(body))
        elif path == "/api/watch/noculus/place":
            self._answer(lambda: self.app.need().place(body))
        elif path == "/api/watch/noculus/close":
            self._answer(lambda: self.app.need().close_trade(body))
        elif path == "/api/watch/noculus/position":
            self._answer(lambda: self.app.need().place_position(body))
        else:
            self._answer(lambda: self.app.start(body))

    def log_message(self, format: str, *args) -> None:
        pass


def make_watch_server(app: WatchApp, host: str = "127.0.0.1", port: int = 8767) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), type("WatchHandler", (_Handler,), {"app": app}))


def serve(config: Path, port: int = 8767, browser: bool = True, picks: Optional[Path] = None) -> int:
    research = load_research_config()
    app = WatchApp(Path(config), SNAPSHOTS_DIR / research.snapshot, research.slices.explore, picks=picks,
                   live=live_feed(config))
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
