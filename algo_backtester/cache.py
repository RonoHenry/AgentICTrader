"""Phase A cache: signal records reused while nothing they depend on changes.

Phase A costs about 14 minutes per instrument-year (task 199), and variants
that change only execution or risk settings don't change it. Records are
stored per instrument under a key over everything that shapes them (Req 7.4):

- the instrument's data fingerprint (every M1 and native row used);
- the engine code fingerprint: the source of the engine, the order logic and
  the code that builds what the engine sees (ENGINE_SOURCES). Any edit there
  changes the key, so a stale entry is never hit;
- the StrategyConfig, minus the settings only the fill model reads;
- the instrument and the run's [start, end].

    cache = SignalCache.default()                      # data/backtests/cache/
    records = cache.signals(data, cfg, start, end)     # served, or computed and stored
    generate_all(datas, cfg, start, end, cache=cache)  # the same, per instrument

An entry is one JSON line per record, then a trailer with the key, the record
count and a sha256 of the record lines. It is written to a temporary file and
renamed into place, so a crash never leaves a half-written entry. An entry
that fails its trailer check is deleted and recomputed.

Validates: Requirements 7.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from agent.strategy_config import StrategyConfig
from algo_backtester.config import REPO_ROOT
from algo_backtester.data import DataFingerprint, InstrumentData
from algo_backtester.signals import Engine, SignalRecord, generate_signals

__all__ = ["CACHE_DIR", "ENGINE_SOURCES", "SignalCache", "cache_key", "engine_code_fingerprint"]

logger = logging.getLogger(__name__)

CACHE_DIR = REPO_ROOT / "data" / "backtests" / "cache"

# The code a SignalRecord depends on, relative to the repository root.
ENGINE_SOURCES = (
    "liquidity_engine/**/*.py",                    # the analysis and the grader
    "agent/order_intent.py",                       # graded setup -> order intent
    "agent/strategy_config.py",
    "ml/features/session_features.py",            # an intent's time features
    "algo_backtester/data.py",                     # warm-up: which bars the engine sees
    "algo_backtester/signals.py",                  # Phase A itself and the record format
    "services/market_data/as_of_view.py",          # aggregation and the as-of window
    "services/market_data/strategy_calendar.py",
    "services/market_data/mt5_clock.py",
)

# Read by the fill model only, never by Phase A: variants on them share entries.
_EXECUTION_ONLY = frozenset({"pending_expiry", "fallback_ttl_minutes"})


def engine_code_fingerprint(root: Path = REPO_ROOT) -> str:
    """sha256 over the paths and contents of ENGINE_SOURCES under ``root``.
    Line endings are normalised, so Windows and Linux checkouts of one commit
    agree. A listed file that is missing raises: ENGINE_SOURCES needs updating."""
    files = set()
    for pattern in ENGINE_SOURCES:
        if "*" in pattern:
            files.update(p for p in root.glob(pattern) if p.is_file())
        elif (root / pattern).is_file():
            files.add(root / pattern)
        else:
            raise FileNotFoundError(f"engine source {pattern} is missing under {root}; update ENGINE_SOURCES")
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(f"{path.relative_to(root).as_posix()}\n{len(content)}\n".encode())
        digest.update(content)
    return digest.hexdigest()


def cache_key(data_fp: DataFingerprint, engine_fp: str, cfg: StrategyConfig, instrument: str,
              start: datetime, end: datetime) -> str:
    strategy = {k: v for k, v in cfg.model_dump(mode="json").items() if k not in _EXECUTION_ONLY}
    parts = [data_fp.rows, data_fp.sha256, engine_fp, strategy, instrument,
             start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()]
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class SignalCache:
    root: Path
    engine_fingerprint: str   # computed once per run, so every worker keys alike

    @classmethod
    def default(cls) -> SignalCache:
        return cls(CACHE_DIR, engine_code_fingerprint())

    def key(self, data: InstrumentData, cfg: StrategyConfig, start: datetime, end: datetime) -> str:
        return cache_key(data.fingerprint, self.engine_fingerprint, cfg, data.instrument, start, end)

    def path(self, key: str) -> Path:
        return Path(self.root) / f"{key}.jsonl"

    def signals(self, data: InstrumentData, cfg: StrategyConfig, start: datetime, end: datetime,
                engine: Optional[Engine] = None) -> list[SignalRecord]:
        """generate_signals(), served from the cache when it holds the entry."""
        key = self.key(data, cfg, start, end)
        records = self.load(key)
        if records is None:
            records = self.store(key, generate_signals(data, cfg, start, end, engine))
        return records

    def load(self, key: str) -> Optional[list[SignalRecord]]:
        """The entry's records; None when there is none, or it was corrupt (and is now deleted)."""
        path = self.path(key)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            *lines, trailer = text.splitlines()
            body = "".join(f"{line}\n" for line in lines)
            if json.loads(trailer) != _trailer(key, len(lines), hashlib.sha256(body.encode())):
                raise ValueError("the trailer doesn't match the records")
            return [SignalRecord.from_json(json.loads(line)) for line in lines]
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Phase A cache entry %s is corrupt (%s); recomputing", path.name, exc)
            path.unlink(missing_ok=True)
            return None

    def store(self, key: str, records: Iterable[SignalRecord]) -> list[SignalRecord]:
        """Write the entry, all or nothing, and return the records written."""
        Path(self.root).mkdir(parents=True, exist_ok=True)
        tmp = Path(self.root) / f".{key}.{os.getpid()}.tmp"
        written, digest = [], hashlib.sha256()
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as fh:
                for record in records:
                    line = json.dumps(record.to_json(), separators=(",", ":")) + "\n"
                    fh.write(line)
                    digest.update(line.encode())
                    written.append(record)
                fh.write(json.dumps(_trailer(key, len(written), digest)) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path(key))
        finally:
            tmp.unlink(missing_ok=True)
        return written


def _trailer(key: str, records: int, digest) -> dict:
    return {"key": key, "records": records, "sha256": digest.hexdigest()}
