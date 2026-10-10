"""The research data snapshot: a frozen, fingerprinted copy of the study's candles.

Research runs on a snapshot, not on the live candle store, so every result is
reproducible and nothing needs Docker after the export (Requirement 1).

Export (`python -m algo_research snapshot`, once per study, needs the store):
``load_instrument()`` runs for each instrument over the research period on a
``RecordingSource`` wrapped round the store. The recorder keeps every row the
loader reads (the M1 bars and the native bars of the warm-up), and they are
written per instrument and timeframe to Parquet under
``data/research/snapshots/<name>/``, with a manifest. The snapshot therefore
holds exactly what the loader reads, and ``SnapshotSource`` (a CandleSource
over those files) gives ``load_instrument()`` the same rows back: the same
``InstrumentData.fingerprint`` as on the store (Req 1.4).

    export_snapshot(TimescaleSource(url, "mt5"), spec, root, git_commit=..., created_at=...)
    snapshot = load_snapshot(root / "exness-2025-2026h1")   # refuses changed data
    snapshot.data["EURUSD"]                                  # InstrumentData, as Phase A loads it

Guards:
- an export whose end is after the study's hold-out start is refused before
  any read, and no row opening at or after the hold-out is ever written
  (Property 10);
- a snapshot is never overwritten: changed data is a new snapshot, under a
  new name;
- loading recomputes each instrument's fingerprint and refuses a snapshot
  whose data no longer matches its manifest (Req 1.5).

Validates: Requirements 1.1-1.5 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import json
import os
import shutil
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from agent.strategy_config import StrategyConfig
from algo_backtester.data import CandleSource, InstrumentData, StoredBar, load_instrument
from algo_research.config import REPO_ROOT, HoldoutError, trading_date_open
from liquidity_engine.models import Timeframe
from services.market_data.mt5_clock import MT5ServerClock

__all__ = [
    "SNAPSHOTS_DIR",
    "RecordingSource",
    "Snapshot",
    "SnapshotError",
    "SnapshotSource",
    "SnapshotSpec",
    "export_snapshot",
    "load_snapshot",
]

SNAPSHOTS_DIR = REPO_ROOT / "data" / "research" / "snapshots"
MANIFEST = "manifest.json"

UTC = timezone.utc
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SCHEMA = pa.schema([
    ("time", pa.timestamp("us", tz="UTC")),
    ("open", pa.float64()), ("high", pa.float64()), ("low", pa.float64()), ("close", pa.float64()),
    ("volume", pa.int64()), ("spread", pa.float64()),
])


class SnapshotError(RuntimeError):
    """A snapshot that is missing, already exists, or no longer matches its manifest."""


# ── recording ──────────────────────────────────────────────────────────────

class RecordingSource:
    """A CandleSource that passes every call to ``inner`` and keeps each row it
    returns, once per instrument, timeframe and open time."""

    def __init__(self, inner: CandleSource) -> None:
        self.inner = inner
        self._rows: dict[tuple[str, Timeframe], dict[datetime, StoredBar]] = {}

    def bars(self, instrument: str, tf: Timeframe, start: datetime, end: datetime) -> list[StoredBar]:
        rows = self.inner.bars(instrument, tf, start, end)
        kept = self._rows.setdefault((instrument, tf), {})
        for bar in rows:
            previous = kept.setdefault(bar.timestamp, bar)
            if previous != bar:
                raise SnapshotError(f"{instrument} {tf.value} {bar.timestamp}: two reads returned different rows")
        return rows

    def last_time(self, instrument: str, tf: Timeframe) -> Optional[datetime]:
        return self.inner.last_time(instrument, tf)

    def timeframes(self, instrument: str) -> list[Timeframe]:
        return [tf for (i, tf) in self._rows if i == instrument]

    def recorded(self, instrument: str, tf: Timeframe) -> list[StoredBar]:
        """The rows kept for ``instrument`` and ``tf``, oldest first."""
        kept = self._rows.get((instrument, tf), {})
        return [kept[t] for t in sorted(kept)]


# ── export ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SnapshotSpec:
    """What a snapshot holds: the loader's inputs for each instrument."""
    name: str
    profile: str                         # broker profile
    venue: str                           # mt5 / binance: the coverage rules
    source: str                          # the store's source column
    instruments: tuple[str, ...]
    start: date                          # first trading date
    end: date                            # end trading date, exclusive; at most the hold-out start
    study: str
    holdout_start: date
    strategy: StrategyConfig             # its candle windows set the warm-up
    clock: Optional[MT5ServerClock]      # which native bars follow the strategy calendar
    max_gap_minutes: int
    spec_source: Optional[str]           # the spec file's source line: where the costs come from


def export_snapshot(source: CandleSource, spec: SnapshotSpec, root: Path = SNAPSHOTS_DIR, *, git_commit: str,
                    created_at: datetime) -> dict:
    """Write ``root/<spec.name>/``: Parquet per instrument and timeframe, and the
    manifest. Returns the manifest."""
    if spec.end > spec.holdout_start:
        raise HoldoutError(f"snapshot {spec.name!r} would end {spec.end}, inside study {spec.study!r}'s hold-out "
                           f"(holdout_start {spec.holdout_start}); research never reads the hold-out")
    target = Path(root) / spec.name
    if target.exists():
        raise SnapshotError(f"snapshot {target} already exists; snapshots are never overwritten. "
                            f"Export changed data under a new name.")
    start, end = trading_date_open(spec.start), trading_date_open(spec.end)
    holdout = datetime.combine(spec.holdout_start, datetime.min.time(), tzinfo=UTC)

    tmp = Path(root) / f".{spec.name}.{os.getpid()}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        data = {}
        for instrument in spec.instruments:
            recorder = RecordingSource(source)
            loaded = load_instrument(recorder, instrument, start, end, spec.strategy, spec.clock, venue=spec.venue,
                                     max_gap_minutes=spec.max_gap_minutes)
            files = {}
            for tf in sorted(recorder.timeframes(instrument), key=lambda t: t.value):
                rows = recorder.recorded(instrument, tf)
                late = [b for b in rows if b.timestamp >= min(end, holdout)]
                if late:   # load_instrument reads [warm-up, end); this guards Property 10 regardless
                    raise HoldoutError(f"{instrument} {tf.value}: a row at {late[0].timestamp} is past the period end")
                _write(tmp / f"{instrument}_{tf.value}.parquet", rows)
                files[tf.value] = len(rows)
            data[instrument] = {
                "rows": loaded.fingerprint.rows,
                "sha256": loaded.fingerprint.sha256,
                "coverage_problems": list(loaded.coverage.problems),
                "warmup_source": loaded.warmup_source,
                "files": files,
            }
        manifest = {
            "name": spec.name,
            "profile": spec.profile,
            "venue": spec.venue,
            "source": spec.source,
            "instruments": list(spec.instruments),
            "start": spec.start.isoformat(),
            "end": spec.end.isoformat(),
            "study": spec.study,
            "holdout_start": spec.holdout_start.isoformat(),
            "candle_counts": {tf.value: n for tf, n in spec.strategy.candle_counts.items()
                              if tf in spec.strategy.timeframes},
            "strategy": spec.strategy.model_dump(mode="json"),
            "server_clock": spec.clock.spec if spec.clock is not None else None,
            "max_gap_minutes": spec.max_gap_minutes,
            "spec_source": spec.spec_source,
            "data": data,
            "git_commit": git_commit,
            "created_at": created_at.isoformat(),
        }
        (tmp / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, target)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return manifest


def _write(path: Path, rows: Sequence[StoredBar]) -> None:
    table = pa.table({
        "time": pa.array([b.timestamp for b in rows], type=_SCHEMA.field("time").type),
        "open": [b.open for b in rows], "high": [b.high for b in rows], "low": [b.low for b in rows],
        "close": [b.close for b in rows],
        "volume": pa.array([b.volume for b in rows], type=pa.int64()),
        "spread": pa.array([b.spread for b in rows], type=pa.float64()),
    }, schema=_SCHEMA)
    pq.write_table(table, path)


# ── loading ────────────────────────────────────────────────────────────────

class SnapshotSource:
    """A CandleSource over a snapshot's Parquet files, read lazily per file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not (self.path / MANIFEST).is_file():
            raise SnapshotError(f"no snapshot at {self.path}: export it first with `python -m algo_research "
                                f"snapshot` (it reads the candle store, so Docker must be running)")
        self._bars: dict[tuple[str, Timeframe], tuple[list[datetime], list[StoredBar]]] = {}

    def bars(self, instrument: str, tf: Timeframe, start: datetime, end: datetime) -> list[StoredBar]:
        times, rows = self._load(instrument, tf)
        return rows[bisect_left(times, start): bisect_left(times, end)]

    def last_time(self, instrument: str, tf: Timeframe) -> Optional[datetime]:
        times, _ = self._load(instrument, tf)
        return times[-1] if times else None

    def _load(self, instrument: str, tf: Timeframe) -> tuple[list[datetime], list[StoredBar]]:
        key = (instrument, tf)
        if key not in self._bars:
            file = self.path / f"{instrument}_{tf.value}.parquet"
            self._bars[key] = _read(file, instrument, tf) if file.is_file() else ([], [])
        return self._bars[key]


def _read(path: Path, instrument: str, tf: Timeframe) -> tuple[list[datetime], list[StoredBar]]:
    table = pq.read_table(path)
    micros = table.column("time").cast(pa.int64()).to_pylist()
    times = [_EPOCH + timedelta(microseconds=us) for us in micros]
    columns = [table.column(name).to_pylist() for name in ("open", "high", "low", "close", "volume", "spread")]
    rows = [StoredBar(t, o, h, lo, c, v, s, tf, instrument) for t, o, h, lo, c, v, s in zip(times, *columns)]
    return times, rows


@dataclass
class Snapshot:
    path: Path
    manifest: dict
    strategy: StrategyConfig
    data: dict[str, InstrumentData] = field(default_factory=dict)

    @property
    def period(self) -> tuple[datetime, datetime]:
        return (trading_date_open(date.fromisoformat(self.manifest["start"])),
                trading_date_open(date.fromisoformat(self.manifest["end"])))

    @property
    def fingerprint(self) -> str:
        """One string over every instrument's data fingerprint, for cache keys and reports."""
        parts = [f"{i}:{d['rows']}:{d['sha256']}" for i, d in sorted(self.manifest["data"].items())]
        return "|".join(parts)


def load_snapshot(path: str | Path, instruments: Optional[Iterable[str]] = None) -> Snapshot:
    """Load ``instruments`` (default: all) as InstrumentData, refusing any whose
    data no longer matches the manifest's fingerprint."""
    source = SnapshotSource(path)
    manifest = json.loads((source.path / MANIFEST).read_text(encoding="utf-8"))
    strategy = StrategyConfig.model_validate(manifest["strategy"])
    snapshot = Snapshot(source.path, manifest, strategy)
    start, end = snapshot.period
    clock = MT5ServerClock(manifest["server_clock"]) if manifest["server_clock"] is not None else None
    wanted = list(instruments) if instruments is not None else manifest["instruments"]
    for instrument in wanted:
        expected = manifest["data"].get(instrument)
        if expected is None:
            raise SnapshotError(f"snapshot {manifest['name']!r} has no {instrument}; it holds {manifest['instruments']}")
        data = load_instrument(source, instrument, start, end, strategy, clock, venue=manifest["venue"],
                               max_gap_minutes=manifest["max_gap_minutes"])
        if (data.fingerprint.rows, data.fingerprint.sha256) != (expected["rows"], expected["sha256"]):
            raise SnapshotError(
                f"{instrument}: snapshot {manifest['name']!r} no longer matches its manifest "
                f"({data.fingerprint.rows} rows, sha256 {data.fingerprint.sha256[:12]}… vs {expected['rows']} rows, "
                f"{expected['sha256'][:12]}…). The data changed since export: re-export under a new name.")
        snapshot.data[instrument] = data
    return snapshot

