"""The blind replay's day records and their rules (market-narrative Requirement 10).

A day moves READING (the chart stops at the open) -> INTRADAY (the read is saved
and locked; time steps forward, trades may be marked) -> REVEALED (the rest of
the candle, its narrative and the scores). Every write in the wrong state is
refused, so a read can never be made or changed after seeing what followed.

One JSON file per instrument and trading date under the journal root
(data/journal/blind/ by default, git-ignored), written to a temporary file and
renamed into place.
"""
from __future__ import annotations

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
from algo_research.replay.scoring import score_thesis, score_trade
from liquidity_engine.models import Timeframe

__all__ = ["BIASES", "STEPS", "Journal", "ReplayError", "day_order"]

NY = "America/New_York"
BIASES = ("BULLISH", "BEARISH", "NO_THESIS")
ARRAY_KINDS = ("OB", "FVG", "BREAKER", "IFVG", "BPR", "LIQUIDITY", "OTHER")
STEPS = {"M1": 1, "M5": 5, "M15": 15, "H1": 60}
MAX_TRADES = 3


class ReplayError(ValueError):
    """A write the day's state or the rules don't allow; the message names the field first."""


def day_order(days: Sequence[date], instrument: str) -> list[date]:
    """The days in a fixed shuffled order: the same for an instrument every time."""
    order = list(days)
    random.Random(zlib.crc32(instrument.upper().encode())).shuffle(order)
    return order


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
                "started_at": _now(), "revealed_at": None, "scores": None, "narrative": None}

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
                if tf not in [t.value for t in ReplayBars.TIMEFRAMES] + ["MN1"]:
                    raise ReplayError(f"array_tf: one of {', '.join(t.value for t in ReplayBars.TIMEFRAMES)}, MN1")
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
        day["revealed_until"] = min(new, close).isoformat()
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
                              "note": str(trade.get("note") or "")[:1000]})
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
        day.update(status="REVEALED", revealed_until=close.isoformat(), revealed_at=_now(),
                   narrative=story, scores={"thesis": thesis, "trades": trades})
        self._save(day)
        return self.current()

    def next_day(self) -> dict:
        """Leave a revealed day for the next one."""
        self._require("REVEALED")
        self._day = None
        return self.current()
