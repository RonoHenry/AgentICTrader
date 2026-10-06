"""Candle data for a backtest: sources, coverage check, fingerprint, warm-up, spreads.

M1 bars from the candle store are the backtest's single source of truth
(Req 3.1). For each instrument, ``load_instrument()``:

1. reads M1 back far enough to build every timeframe's warm-up window, plus
   the run itself;
2. builds each timeframe's strategy-calendar bars from that M1. Where M1
   history doesn't reach back far enough for a window, it fills the earlier
   part from the venue's native bars of that timeframe, or from native H1 if
   the venue's own bars follow a different clock (as the live runner does).
   The source used per timeframe is reported for the manifest;
3. checks coverage (Req 3.6): weekends and venue holidays may be missing,
   other gaps longer than ``max_gap_minutes`` may not, and history must span
   the whole run. The warm-up must also be complete;
4. fingerprints every row it used (Req 3.7), so a rerun on changed data is
   detectable.

    source = TimescaleSource(os.environ["TIMESCALE_URL"], source="mt5")
    data = load_instrument(source, "EURUSD", start, end, cfg.strategy, profile.clock(),
                           venue="mt5", max_gap_minutes=30)
    ensure_coverage([data.coverage], allow_gaps=False)      # refuses, listing problems
    bars, priced_at_typical = fill_bars(data.m1, spec.default_spread)   # for the fill model

Gap rules for MT5 venues, calibrated on real M1 (task 186 fixtures): FX
rollover leaves gaps of a few minutes around 17:00 New York; gold stops
around 17:00 for 62 minutes (Exness) to 120 (MetaQuotes); the FX weekend
runs from Friday 17:00 to Sunday 17:00. Binance trades 24/7: no exemptions.

Validates: Requirements 3.1, 3.2, 3.6, 3.7, 5.1 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional, Protocol, Sequence
from zoneinfo import ZoneInfo

from agent.brokers.fill_model import Bar
from agent.strategy_config import StrategyConfig
from liquidity_engine.models import Candle, Timeframe
from services.market_data.as_of_view import aggregate
from services.market_data.mt5_clock import MT5ServerClock
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = [
    "CandleSource",
    "Coverage",
    "CoverageError",
    "CsvSource",
    "DataFingerprint",
    "InstrumentData",
    "StoredBar",
    "TimescaleSource",
    "check_coverage",
    "ensure_coverage",
    "fill_bars",
    "fingerprint",
    "load_instrument",
]

UTC = timezone.utc
_NY = ZoneInfo("America/New_York")
_M1 = timedelta(minutes=1)
_CALENDAR = StrategyCalendar()
_NOMINAL_MINUTES = {
    Timeframe.M1: 1, Timeframe.M3: 3, Timeframe.M5: 5, Timeframe.M15: 15, Timeframe.M30: 30,
    Timeframe.H1: 60, Timeframe.H3: 180, Timeframe.H4: 240, Timeframe.H6: 360, Timeframe.H8: 480,
    Timeframe.H12: 720, Timeframe.D1: 1440, Timeframe.W1: 7 * 1440,
}
_DAILY_BREAK_MAX = timedelta(hours=3)   # longest stop around the 17:00 New York close
_HOLIDAYS = {(12, 25), (1, 1)}          # FX closed (New York dates)


@dataclass(frozen=True, slots=True)
class StoredBar:
    """One stored bar. Prices are bid; ``spread`` (price units) is None when the
    source records none. Lightweight on purpose: a year of M1 is ~370k rows,
    and aggregate()/compose_as_of_view() accept these as they accept Candles."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int]
    spread: Optional[float]
    timeframe: Timeframe
    instrument: str

    def candle(self) -> Candle:
        return Candle(timestamp=self.timestamp, open=self.open, high=self.high, low=self.low, close=self.close,
                      volume=self.volume, timeframe=self.timeframe, instrument=self.instrument)


class CandleSource(Protocol):
    def bars(self, instrument: str, tf: Timeframe, start: datetime, end: datetime) -> list[StoredBar]:
        """Stored ``tf`` bars opening in [start, end), oldest first; [] if none."""


class CsvSource:
    """``<root>/<INSTRUMENT>_<TF>.csv`` with columns time,open,high,low,close,volume,spread
    (ISO UTC times; spread may be empty). For fixtures and offline data."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def bars(self, instrument: str, tf: Timeframe, start: datetime, end: datetime) -> list[StoredBar]:
        path = self.root / f"{instrument}_{tf.value}.csv"
        if not path.exists():
            return []
        out = []
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                ts = datetime.fromisoformat(row["time"].replace("Z", "+00:00")).astimezone(UTC)
                if start <= ts < end:
                    out.append(StoredBar(
                        timestamp=ts, open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                        close=float(row["close"]), volume=int(float(row["volume"])) if row.get("volume") else None,
                        spread=float(row["spread"]) if row.get("spread") else None, timeframe=tf, instrument=instrument,
                    ))
        return sorted(out, key=lambda b: b.timestamp)


class TimescaleSource:
    """The project candle store (TimescaleDB ``candles``), rows from one ``source``
    (mt5, binance, ...), since the table's key holds one row per time and instrument."""

    def __init__(self, url: str, source: str) -> None:
        # .env holds the SQLAlchemy form; asyncpg accepts only postgresql://.
        self.url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self.source = source

    def bars(self, instrument: str, tf: Timeframe, start: datetime, end: datetime) -> list[StoredBar]:
        return asyncio.run(self._fetch(instrument, tf, start, end))

    async def _fetch(self, instrument: str, tf: Timeframe, start: datetime, end: datetime) -> list[StoredBar]:
        import asyncpg

        conn = await asyncpg.connect(self.url)
        try:
            rows = await conn.fetch(
                "SELECT time, open, high, low, close, volume, spread FROM candles "
                "WHERE instrument = $1 AND timeframe = $2 AND source = $3 AND time >= $4 AND time < $5 ORDER BY time",
                instrument, tf.value, self.source, start, end,
            )
        finally:
            await conn.close()
        return [
            StoredBar(timestamp=r["time"].astimezone(UTC), open=float(r["open"]), high=float(r["high"]),
                      low=float(r["low"]), close=float(r["close"]),
                      volume=int(r["volume"]) if r["volume"] is not None else None,
                      spread=float(r["spread"]) if r["spread"] is not None else None,
                      timeframe=tf, instrument=instrument)
            for r in rows
        ]


# ── coverage (Req 3.6) ─────────────────────────────────────────────────────

class CoverageError(RuntimeError):
    """Data coverage problems, and the run was not told to allow them."""


@dataclass(frozen=True)
class Coverage:
    instrument: str
    start: datetime
    end: datetime
    first: Optional[datetime]
    last: Optional[datetime]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def check_coverage(instrument: str, m1: Sequence[StoredBar], start: datetime, end: datetime, venue: str,
                   max_gap_minutes: int) -> Coverage:
    """Problems with the M1 history for [start, end): gaps the venue's schedule
    doesn't explain, and history starting late or ending early."""
    bars = [b for b in m1 if start <= b.timestamp < end]
    max_gap = timedelta(minutes=max_gap_minutes)
    problems = []
    if not bars:
        problems.append(f"{instrument}: no M1 history in {start:%Y-%m-%d %H:%M} .. {end:%Y-%m-%d %H:%M} UTC")
        return Coverage(instrument, start, end, None, None, tuple(problems))

    first, last_close = bars[0].timestamp, bars[-1].timestamp + _M1
    if not _allowed_gap(start, first, venue, max_gap):
        problems.append(f"{instrument}: M1 history starts {first:%Y-%m-%d %H:%M} UTC, after the run start {start:%Y-%m-%d %H:%M}")
    for previous, following in zip(bars, bars[1:]):
        gap_start = previous.timestamp + _M1
        if following.timestamp > gap_start and not _allowed_gap(gap_start, following.timestamp, venue, max_gap):
            minutes = int((following.timestamp - gap_start) / _M1)
            problems.append(f"{instrument}: {minutes} min gap {gap_start:%Y-%m-%d %H:%M} .. {following.timestamp:%Y-%m-%d %H:%M} UTC")
    if not _allowed_gap(last_close, end, venue, max_gap):
        problems.append(f"{instrument}: M1 history ends {last_close:%Y-%m-%d %H:%M} UTC, before the run end {end:%Y-%m-%d %H:%M}")
    return Coverage(instrument, start, end, first, bars[-1].timestamp, tuple(problems))


def ensure_coverage(coverages: Iterable[Coverage], allow_gaps: bool) -> dict[str, list[str]]:
    """Refuse the run on any coverage problem unless ``allow_gaps``; either way
    return the problems per instrument, for the manifest."""
    problems = {c.instrument: list(c.problems) for c in coverages if c.problems}
    if problems and not allow_gaps:
        listing = "\n".join(f"  - {p}" for ps in problems.values() for p in ps)
        raise CoverageError(f"Data coverage problems ({', '.join(problems)}):\n{listing}\n"
                            f"Fix the data, or allow them explicitly (data.allow_gaps / --allow-gaps).")
    return problems


def _allowed_gap(gap_start: datetime, gap_end: datetime, venue: str, max_gap: timedelta) -> bool:
    if gap_end - gap_start <= max_gap:
        return True
    if venue != "mt5":
        return False  # Binance trades 24/7
    start, end = gap_start.astimezone(_NY), gap_end.astimezone(_NY)
    # The daily close: rollover, and gold/index session breaks.
    close = datetime.combine(start.date(), time(17), tzinfo=_NY)
    if close < start:
        close += timedelta(days=1)
    if gap_end - gap_start <= _DAILY_BREAK_MAX and close <= end:
        return True
    # The FX weekend: Friday afternoon to Sunday evening.
    if start.weekday() in (4, 5, 6):
        friday = start.date() - timedelta(days=start.weekday() - 4)
        if (start >= datetime.combine(friday, time(15), tzinfo=_NY)
                and end <= datetime.combine(friday + timedelta(days=2), time(20), tzinfo=_NY)):
            return True
    # Christmas and New Year.
    if gap_end - gap_start <= timedelta(days=4):
        day = start.date()
        while day <= end.date():
            if (day.month, day.day) in _HOLIDAYS:
                return True
            day += timedelta(days=1)
    return False


# ── fingerprint (Req 3.7) and spreads (Req 5.1) ────────────────────────────

@dataclass(frozen=True)
class DataFingerprint:
    rows: int
    sha256: str


def fingerprint(bars: Iterable[StoredBar]) -> DataFingerprint:
    """Row count and sha256 over every value of every row, in order."""
    digest, rows = hashlib.sha256(), 0
    for b in bars:
        digest.update(f"{b.timeframe.value}|{b.timestamp.isoformat()}|{b.open!r}|{b.high!r}|{b.low!r}|"
                      f"{b.close!r}|{b.volume!r}|{b.spread!r}\n".encode())
        rows += 1
    return DataFingerprint(rows, digest.hexdigest())


def fill_bars(m1: Iterable[StoredBar], default_spread: float) -> tuple[list[Bar], int]:
    """M1 bars for the fill model, each priced at the larger of its recorded
    spread and the instrument's typical spread (D10), and how many were priced
    at the typical spread (none recorded, or a narrower one), for the report."""
    out, floored = [], 0
    for b in m1:
        if b.spread is None or b.spread < default_spread:
            floored += 1
        out.append(Bar(timestamp=b.timestamp, open=b.open, high=b.high, low=b.low, close=b.close,
                       spread=max(b.spread or 0.0, default_spread)))
    return out, floored


# ── one instrument's data ──────────────────────────────────────────────────

@dataclass
class InstrumentData:
    instrument: str
    m1: list[StoredBar]                          # from the warm-up through the run end
    closed: dict[Timeframe, list[Candle]]        # strategy-calendar bars per timeframe
    warmup_source: dict[str, str]                # timeframe -> "m1" | "native" | "native_h1"
    fingerprint: DataFingerprint                 # every row used, M1 and native
    coverage: Coverage                           # including an incomplete warm-up


def load_instrument(source: CandleSource, instrument: str, start: datetime, end: datetime, cfg: StrategyConfig,
                    clock: Optional[MT5ServerClock], venue: str, max_gap_minutes: int) -> InstrumentData:
    """Everything the backtest reads for ``instrument`` over [start, end).

    ``clock`` is the MT5 server clock (None for Binance): it decides which
    native bars follow the strategy calendar, for the warm-up fallback.
    """
    windows = cfg.candle_counts
    warmup_from = {tf: start - _warmup_span(tf, windows[tf]) for tf in cfg.timeframes}
    # A week more: the first period built from M1 may be partial and is dropped.
    m1 = source.bars(instrument, Timeframe.M1, min(warmup_from.values()) - timedelta(days=8), end)
    coverage = check_coverage(instrument, m1, start, end, venue, max_gap_minutes)

    closed: dict[Timeframe, list[Candle]] = {}
    sources: dict[str, str] = {}
    native_rows: list[StoredBar] = []
    problems = list(coverage.problems)
    for tf in cfg.timeframes:
        built = aggregate(m1, tf, _CALENDAR, as_of=end)[1:] if m1 else []
        if _closed_before(built, tf, start) >= windows[tf]:
            closed[tf], sources[tf.value] = built, "m1"
        else:
            cut = built[0].timestamp if built else end
            earlier, label, raw = _native_warmup(source, instrument, tf, warmup_from[tf], cut, clock)
            closed[tf], sources[tf.value] = earlier + built, label
            native_rows.extend(raw)
        have = _closed_before(closed[tf], tf, start)
        if have < windows[tf]:
            problems.append(f"{instrument} {tf.value}: warm-up has {have} closed bars before "
                            f"{start:%Y-%m-%d %H:%M} UTC; the window needs {windows[tf]}")

    return InstrumentData(
        instrument=instrument,
        m1=m1,
        closed=closed,
        warmup_source=sources,
        fingerprint=fingerprint([*native_rows, *m1]),
        coverage=Coverage(instrument, start, end, coverage.first, coverage.last, tuple(problems)),
    )


def _warmup_span(tf: Timeframe, bars: int) -> timedelta:
    # Room for `bars` periods when only weekdays trade (x1.5), plus holidays.
    factor = 1.0 if tf == Timeframe.W1 else 1.5
    return timedelta(minutes=_NOMINAL_MINUTES[tf] * bars * factor) + timedelta(days=7)


def _closed_before(bars: Sequence[Candle], tf: Timeframe, start: datetime) -> int:
    return sum(1 for b in bars if _CALENDAR.period_end(b.timestamp, tf) <= start)


def _native_warmup(source: CandleSource, instrument: str, tf: Timeframe, since: datetime, cut: datetime,
                   clock: Optional[MT5ServerClock]) -> tuple[list[Candle], str, list[StoredBar]]:
    """Calendar bars of ``tf`` for [since, cut), from native bars: the venue's
    own ``tf`` where it follows the strategy calendar, else built from native H1."""
    if _CALENDAR.matches_native(clock, tf):
        raw = source.bars(instrument, tf, since, cut)
        return [b.candle() for b in raw], "native", raw
    if not _CALENDAR.matches_native(clock, Timeframe.H1) or _NOMINAL_MINUTES[tf] <= 60:
        raise ValueError(f"{instrument}: no native series on the strategy calendar to warm up {tf.value} from")
    raw = source.bars(instrument, Timeframe.H1, since - timedelta(days=8), cut)
    # The first period may be partial; periods must end by the cut.
    return aggregate(raw, tf, _CALENDAR, as_of=cut)[1:] if raw else [], "native_h1", raw
