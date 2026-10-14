"""The blind replay's day records and their rules (market-narrative Requirement 10).

A day moves READING (the chart stops at the open) -> INTRADAY (the read is saved
and locked; time steps forward, trades may be marked) -> REVEALED (the rest of
the candle, its narrative and the scores). Every write in the wrong state is
refused, so a read can never be made or changed after seeing what followed.

Drawings (update 2026-10-14b) may be made at any time, and each keeps the phase
and the revealed time it was made in: the read keeps a copy of the drawings made
before it was saved, the reveal a copy of those made before it, and drawings
made after the reveal are the trader's narrative, never part of a read.

One JSON file per instrument and trading date under the journal root
(data/journal/blind/ by default, git-ignored), written to a temporary file and
renamed into place.
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import zlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from algo_research.config import trading_date_open
from algo_research.narrative import narrate
from algo_research.replay.bars import ReplayBars
from algo_research.replay.timeframes import TIMEFRAMES
from algo_research.replay.scoring import score_thesis, score_trade
from liquidity_engine.models import Timeframe

__all__ = ["BIASES", "DRAWING_POINTS", "STEPS", "Journal", "ReplayError", "day_order"]

NY = "America/New_York"
BIASES = ("BULLISH", "BEARISH", "NO_THESIS")
ARRAY_KINDS = ("OB", "FVG", "BREAKER", "IFVG", "BPR", "LIQUIDITY", "OTHER")
STEPS = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}
#: Drawing types and their anchor points: lines, a box for a PD array, a fib/SD
#: projection, a long or short position (entry, stop, target), a text note.
DRAWING_POINTS = {"hline": 1, "hray": 1, "vline": 1, "text": 1, "trend": 2, "rect": 2, "fib": 2, "long": 3, "short": 3}
MAX_DRAWINGS = 400
_PHASE = {"READING": "read", "INTRADAY": "intraday", "REVEALED": "narrative"}
MAX_TRADES = 3


class ReplayError(ValueError):
    """A write the day's state or the rules don't allow; the message names the field first."""


def day_order(days: Sequence[date], instrument: str) -> list[date]:
    """The days in a fixed shuffled order: the same for an instrument every time."""
    order = list(days)
    random.Random(zlib.crc32(instrument.upper().encode())).shuffle(order)
    return order


def _content(drawing: dict) -> dict:
    return {k: v for k, v in drawing.items()
            if k not in ("phase", "created_at", "created_wall", "edited_phase", "edited_at")}


def _drawing(raw) -> dict:
    """One drawing, checked: its type, its anchor points (t: New York wall seconds, p: price) and its options."""
    if not isinstance(raw, dict):
        raise ReplayError("drawings: each drawing is an object")
    kind = raw.get("type")
    if kind not in DRAWING_POINTS:
        raise ReplayError(f"drawings: type one of {', '.join(DRAWING_POINTS)}")
    did = str(raw.get("id") or "")
    if not 1 <= len(did) <= 40:
        raise ReplayError("drawings: an id of 1 to 40 characters")
    points = raw.get("points")
    if not isinstance(points, list) or len(points) != DRAWING_POINTS[kind]:
        raise ReplayError(f"drawings: a {kind} has {DRAWING_POINTS[kind]} point(s)")
    try:
        clean_points = [{"t": int(p["t"]), "p": float(p["p"])} for p in points]
    except (KeyError, TypeError, ValueError):
        raise ReplayError("drawings: each point needs t (seconds) and p (a price)") from None
    if not all(math.isfinite(p["p"]) for p in clean_points):
        raise ReplayError("drawings: prices must be finite")
    clean = {"id": did, "type": kind, "points": clean_points}
    for key, limit in (("label", 200), ("text", 1000), ("tf", 5), ("kind", 12), ("color", 32), ("direction", 8)):
        if raw.get(key) not in (None, ""):
            clean[key] = str(raw[key])[:limit]
    for key in ("mid", "extend", "hidden"):
        if key in raw:
            clean[key] = bool(raw[key])
    if raw.get("levels") is not None:
        try:
            clean["levels"] = [float(x) for x in raw["levels"]][:24]
        except (TypeError, ValueError):
            raise ReplayError("drawings: levels are numbers") from None
    return clean


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _price(value, field: str) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError):
        raise ReplayError(f"{field}: a price is required") from None
    if not math.isfinite(price) or price <= 0:
        raise ReplayError(f"{field}: a positive price is required")
    return price


class Journal:
    """The days of one instrument, their records on disk, and the current day."""

    def __init__(self, root: Path, bars: ReplayBars, days: Sequence[date]) -> None:
        self.bars = bars
        self.instrument = bars.instrument
        self.dir = Path(root) / self.instrument
        self.order = day_order(days, self.instrument)
        self._day: Optional[dict] = None

    # ── records ──────────────────────────────────────────────────────────────

    def _path(self, day: str) -> Path:
        return self.dir / f"{day}.json"

    def _load(self, day: date) -> Optional[dict]:
        path = self._path(day.isoformat())
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _save(self, record: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f".{record['trading_date']}.{os.getpid()}.tmp"
        try:
            tmp.write_text(json.dumps(record, indent=1), encoding="utf-8")
            os.replace(tmp, self._path(record["trading_date"]))
        finally:
            tmp.unlink(missing_ok=True)

    def records(self) -> list[dict]:
        return [r for r in (self._load(d) for d in self.order) if r is not None]

    def remaining(self) -> int:
        """Days not yet revealed."""
        return sum(1 for d in self.order if (self._load(d) or {}).get("status") != "REVEALED")

    def _start(self, day: date) -> dict:
        open_ = pd.Timestamp(trading_date_open(day))
        close = pd.Timestamp(trading_date_open(date.fromordinal(day.toordinal() + 1)))
        return {"instrument": self.instrument, "trading_date": day.isoformat(), "status": "READING",
                "open_time": open_.isoformat(), "close_time": close.isoformat(), "revealed_until": open_.isoformat(),
                "open_price": self.bars.price_at(open_), "date_shown": False, "read": None, "trades": [],
                "started_at": _now(), "revealed_at": None, "scores": None, "narrative": None, "drawings": [],
                "narrative_note": None}

    # ── the current day ──────────────────────────────────────────────────────

    def _current(self) -> dict:
        if self._day is None:
            loaded = {d: self._load(d) for d in self.order}
            open_days = [d for d in self.order if loaded[d] and loaded[d]["status"] in ("READING", "INTRADAY")]
            fresh = [d for d in self.order if loaded[d] is None]
            if open_days:
                self._day = loaded[open_days[0]]
            elif fresh:
                self._day = self._start(fresh[0])
                self._save(self._day)
            else:
                raise ReplayError("day: every day has been read")
        return self._day

    def current(self) -> dict:
        """The current day, with the price at its revealed time and its weekday."""
        day = dict(self._current())
        until = pd.Timestamp(day["revealed_until"])
        day["price"] = self.bars.price_at(until)
        day["weekday"] = date.fromisoformat(day["trading_date"]).strftime("%a")
        return day

    def _require(self, *states: str) -> dict:
        day = self._current()
        if day["status"] not in states:
            raise ReplayError(f"status: the day is {day['status']}; this needs {' or '.join(states)}")
        return day

    def save_read(self, read: dict) -> dict:
        """Requirement 10.3: the read, checked, then locked."""
        day = self._require("READING")
        bias = read.get("bias")
        if bias not in BIASES:
            raise ReplayError(f"bias: one of {', '.join(BIASES)}")
        clean = {"bias": bias, "draw": None, "invalidation": None, "array_low": None, "array_high": None,
                 "array_tf": None, "array_kind": None}
        if bias != "NO_THESIS":
            draw, invalidation = _price(read.get("draw"), "draw"), _price(read.get("invalidation"), "invalidation")
            above, below = (draw, invalidation) if bias == "BULLISH" else (invalidation, draw)
            open_price = day["open_price"]
            if not above > open_price:
                field = "draw" if bias == "BULLISH" else "invalidation"
                raise ReplayError(f"{field}: must be above the open price {open_price} for a {bias.lower()} thesis")
            if not below < open_price:
                field = "invalidation" if bias == "BULLISH" else "draw"
                raise ReplayError(f"{field}: must be below the open price {open_price} for a {bias.lower()} thesis")
            clean.update(draw=draw, invalidation=invalidation)
            if read.get("array_low") not in (None, "") or read.get("array_high") not in (None, ""):
                low, high = _price(read.get("array_low"), "array_low"), _price(read.get("array_high"), "array_high")
                if not low < high:
                    raise ReplayError("array: its low must be below its high")
                tf = read.get("array_tf")
                if tf not in TIMEFRAMES:
                    raise ReplayError(f"array_tf: one of {', '.join(TIMEFRAMES)}")
                kind = read.get("array_kind") or "OTHER"
                if kind not in ARRAY_KINDS:
                    raise ReplayError(f"array_kind: one of {', '.join(ARRAY_KINDS)}")
                clean.update(array_low=low, array_high=high, array_tf=tf, array_kind=kind)
        confidence = read.get("confidence", 2)
        if confidence not in (1, 2, 3):
            raise ReplayError("confidence: 1, 2 or 3")
        note = str(read.get("note") or "")[:4000]
        clean.update(confidence=confidence, remembered=bool(read.get("remembered")), note=note,
                     written_at=_now(), as_of=day["revealed_until"])
        clean["drawings"] = copy.deepcopy(day.get("drawings", []))       # the chart as the read left it
        day.update(read=clean, status="INTRADAY")
        self._save(day)
        return self.current()

    def advance(self, step: Optional[str] = None, to: Optional[str] = None) -> dict:
        """Requirement 10.4: time moves forward by a bar or to a New York time, never past the close."""
        day = self._require("INTRADAY")
        until, close = pd.Timestamp(day["revealed_until"]), pd.Timestamp(day["close_time"])
        if until >= close:
            raise ReplayError("time: the day has reached its close; reveal it")
        if step is not None:
            if step not in STEPS:
                raise ReplayError(f"step: one of {', '.join(STEPS)}")
            new = until + pd.Timedelta(minutes=STEPS[step])
        elif to is not None:
            try:
                hour, minute = (int(x) for x in str(to).split(":"))
                open_ny = pd.Timestamp(day["open_time"]).tz_convert(NY)
                new = open_ny.normalize().tz_localize(None) + pd.Timedelta(hours=hour, minutes=minute)
                new = new.tz_localize(NY)
            except (ValueError, TypeError):
                raise ReplayError("to: a New York time HH:MM") from None
            if new < open_ny:
                new = (new.tz_localize(None) + pd.Timedelta(days=1)).tz_localize(NY)
            new = new.tz_convert("UTC")
            if new <= until:
                raise ReplayError(f"to: {to} New York is already past")
        else:
            raise ReplayError("step: give a step or a time")
        new = min(new, close)
        if step is not None and self.bars.m1_between(until, new).empty:
            nxt = self.bars.next_open(until)                # a step into a closed market lands past the gap
            if nxt is not None and nxt < close:
                new = min(nxt + pd.Timedelta(minutes=STEPS[step]), close)
        day["revealed_until"] = new.isoformat()
        self._save(day)
        return self.current()

    def mark_trade(self, trade: dict) -> dict:
        """Requirement 10.5: a trade at the revealed time."""
        day = self._require("INTRADAY")
        direction = trade.get("direction")
        if direction not in ("LONG", "SHORT"):
            raise ReplayError("direction: LONG or SHORT")
        entry = _price(trade.get("entry"), "entry")
        stop, target = _price(trade.get("stop"), "stop"), _price(trade.get("target"), "target")
        if (stop >= entry) if direction == "LONG" else (stop <= entry):
            raise ReplayError(f"stop: must be {'below' if direction == 'LONG' else 'above'} the entry")
        if (target <= entry) if direction == "LONG" else (target >= entry):
            raise ReplayError(f"target: must be {'above' if direction == 'LONG' else 'below'} the entry")
        if len(day["trades"]) >= MAX_TRADES:
            raise ReplayError(f"trades: at most three a day")
        day["trades"].append({"direction": direction, "entry": entry, "stop": stop, "target": target,
                              "marked_at": day["revealed_until"], "written_at": _now(),
                              "note": str(trade.get("note") or "")[:1000],
                              "drawing": str(trade["drawing"])[:40] if trade.get("drawing") else None})
        self._save(day)
        return self.current()

    def show_date(self) -> dict:
        """Requirement 10.1: the trader chose to see the date; the day records it."""
        day = self._require("READING", "INTRADAY", "REVEALED")
        day["date_shown"] = True
        self._save(day)
        return self.current()

    def reveal(self) -> dict:
        """Requirement 10.6-10.7: the rest of the candle, its narrative and the scores."""
        if self._current()["status"] == "READING":
            raise ReplayError("read: save a read first (NO_THESIS is a read)")
        day = self._require("INTRADAY")
        open_, close = pd.Timestamp(day["open_time"]), pd.Timestamp(day["close_time"])
        candle = self.bars.m1_between(open_, close)
        narrative = narrate(candle, Timeframe.M1, Timeframe.D1)
        row = narrative[narrative["start"] == open_]
        story = None
        if not row.empty:
            r = row.iloc[0]
            story = {"direction": r["direction"], "open": float(r["open"]), "high": float(r["high"]),
                     "low": float(r["low"]), "close": float(r["close"]), "t_high": pd.Timestamp(r["t_high"]).isoformat(),
                     "t_low": pd.Timestamp(r["t_low"]).isoformat(),
                     "false_move": None if pd.isna(r["false_move"]) else float(r["false_move"])}
        read_at = pd.Timestamp(day["read"]["as_of"])
        thesis = score_thesis(day["read"], self.bars.m1_between(read_at, close), day["open_price"],
                              None if story is None else story["direction"])
        trades = [score_trade(t, self.bars.m1_between(pd.Timestamp(t["marked_at"]), close)) for t in day["trades"]]
        day["drawings_at_reveal"] = copy.deepcopy(day.get("drawings", []))
        day.update(status="REVEALED", revealed_until=close.isoformat(), revealed_at=_now(),
                   narrative=story, scores={"thesis": thesis, "trades": trades})
        self._save(day)
        return self.current()

    def save_drawings(self, drawings: Sequence[dict]) -> dict:
        """The chart's drawings, replacing the working set. A new drawing is stamped with the
        phase and the revealed time it was made in; an existing one keeps them, and an edit
        is stamped too."""
        day = self._current()
        if not isinstance(drawings, (list, tuple)):
            raise ReplayError("drawings: a list")
        if len(drawings) > MAX_DRAWINGS:
            raise ReplayError(f"drawings: at most {MAX_DRAWINGS}")
        known = {d["id"]: d for d in day.get("drawings", [])}
        stamp = {"phase": _PHASE[day["status"]], "at": day["revealed_until"], "wall": _now()}
        out, seen = [], set()
        for raw in drawings:
            clean = _drawing(raw)
            if clean["id"] in seen:
                raise ReplayError(f"drawings: id {clean['id']} appears twice")
            seen.add(clean["id"])
            old = known.get(clean["id"])
            if old is None:
                clean.update(phase=stamp["phase"], created_at=stamp["at"], created_wall=stamp["wall"])
            else:
                clean.update({k: old[k] for k in ("phase", "created_at", "created_wall") if k in old})
                if _content(old) != _content(clean):
                    clean.update(edited_phase=stamp["phase"], edited_at=stamp["at"])
                else:
                    clean.update({k: old[k] for k in ("edited_phase", "edited_at") if k in old})
            out.append(clean)
        day["drawings"] = out
        self._save(day)
        return self.current()

    def save_narrative(self, text: str) -> dict:
        """After the reveal: the trader's own account of how the day formed."""
        day = self._require("REVEALED")
        day.update(narrative_note=str(text or "")[:8000], narrative_written_at=_now())
        self._save(day)
        return self.current()

    def live_trades(self) -> list[dict]:
        """Each marked trade as of the revealed time: PENDING until filled, then OPEN (with its
        unrealised R), STOP or TARGET. The reveal scores them to the close."""
        day = self._current()
        until = pd.Timestamp(day["revealed_until"])
        out = []
        for trade in day["trades"]:
            rows = self.bars.m1_between(pd.Timestamp(trade["marked_at"]), until)
            live = score_trade(trade, rows) if not rows.empty else {"outcome": "NOT_FILLED", "r": None}
            out.append({**live, "outcome": "PENDING" if live["outcome"] == "NOT_FILLED" else live["outcome"]})
        return out

    def next_day(self) -> dict:
        """Leave a revealed day for the next one."""
        self._require("REVEALED")
        self._day = None
        return self.current()
