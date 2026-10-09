"""Parquet cache for built tables, keyed by everything they depend on.

Building the features, the anticipation and the labels reads the whole
snapshot; reruns reuse them while nothing they depend on changes
(Requirements 3.5, 4.3). A key is a sha256 over:

- the kind of table and the instrument;
- the instrument's data fingerprint (from the snapshot manifest);
- the code fingerprint of the sources that compute it: any edit there
  changes the key, so a stale entry is never hit;
- the settings that shape it (slices, typical spread, StrategyConfig).

    cache = ParquetCache.default()                     # data/research/cache/
    key = cache_key("market", "EURUSD", fingerprint, code_fingerprint(MARKET_SOURCES), slices)
    table = cache.load("market", key)                  # None when missing
    cache.store("market", key, table)                  # written whole, then renamed into place

Validates: Requirements 3.5, 4.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

from algo_research.config import REPO_ROOT

__all__ = ["CACHE_DIR", "MARKET_SOURCES", "ParquetCache", "cache_key", "code_fingerprint"]

logger = logging.getLogger(__name__)

CACHE_DIR = REPO_ROOT / "data" / "research" / "cache"

# The code the market features depend on, relative to the repository root.
MARKET_SOURCES = (
    "algo_research/frame.py",
    "algo_research/features/market.py",
    "algo_backtester/data.py",                       # which bars the loader reads
    "liquidity_engine/utils/*.py",                   # killzones, calendar opens, ATR
    "liquidity_engine/grader/sequence.py",           # the Asian session
    "services/market_data/as_of_view.py",
    "services/market_data/strategy_calendar.py",
    "services/market_data/mt5_clock.py",
)


def code_fingerprint(patterns: Iterable[str], root: Path = REPO_ROOT) -> str:
    """sha256 over the paths and contents of the files matching ``patterns``
    under ``root``, line endings normalised. A plain path that is missing raises."""
    files = set()
    for pattern in patterns:
        if "*" in pattern:
            files.update(p for p in root.glob(pattern) if p.is_file())
        elif (root / pattern).is_file():
            files.add(root / pattern)
        else:
            raise FileNotFoundError(f"source {pattern} is missing under {root}")
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(f"{path.relative_to(root).as_posix()}\n{len(content)}\n".encode())
        digest.update(content)
    return digest.hexdigest()


def cache_key(kind: str, *parts: Any) -> str:
    return hashlib.sha256(json.dumps([kind, *parts], sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


@dataclass(frozen=True)
class ParquetCache:
    root: Path

    @classmethod
    def default(cls) -> ParquetCache:
        return cls(CACHE_DIR)

    def path(self, kind: str, key: str) -> Path:
        return Path(self.root) / kind / f"{key}.parquet"

    def load(self, kind: str, key: str) -> Optional[pd.DataFrame]:
        path = self.path(kind, key)
        if not path.is_file():
            return None
        try:
            return pd.read_parquet(path)
        except Exception as exc:   # a corrupt entry is recomputed, never trusted
            logger.warning("research cache entry %s is unreadable (%s); recomputing", path, exc)
            path.unlink(missing_ok=True)
            return None

    def store(self, kind: str, key: str, table: pd.DataFrame) -> pd.DataFrame:
        path = self.path(kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{key}.{os.getpid()}.tmp")
        try:
            table.to_parquet(tmp, index=False)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        return table
