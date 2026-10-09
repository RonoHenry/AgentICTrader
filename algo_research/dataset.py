"""The research tables, built from a snapshot and cached.

``build_dataset()`` turns a loaded snapshot into what hypotheses read:

- ``frames``: each instrument's M1 and calendar bars (frame.py), for races
  and the shuffled-path baseline;
- ``features``: one row per instrument and M15 close of the slices, the
  market features (Req 3) and the daily anticipation (Req 4);
- ``labels``: the same rows, what happened after t (Req 6).

Each table is cached per instrument (features/cache.py) under a key over the
instrument's data fingerprint, the code that computes it and its settings.
The rows of all instruments are stacked in the configuration's instrument
order; the feature and label tables share their index (the row id).

    data = build_dataset(snapshot, cfg, specs, ParquetCache.default())
    data.features, data.frames["EURUSD"], data.summary

Validates: Requirements 3.5 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from agent.instruments import InstrumentSpecs
from algo_research.config import ResearchConfig
from algo_research.features.cache import MARKET_SOURCES, ParquetCache, cache_key, code_fingerprint
from algo_research.features.market import market_features
from algo_research.frame import InstrumentFrame, build_grid, frame_from_data, slices_of
from algo_research.snapshot import Snapshot

__all__ = ["ResearchData", "build_dataset", "build_frames"]


@dataclass
class ResearchData:
    frames: dict[str, InstrumentFrame]
    features: pd.DataFrame
    labels: Optional[pd.DataFrame] = None
    summary: dict = field(default_factory=dict)   # timings, cache hits, row counts, engine errors


def build_frames(snapshot: Snapshot, specs: InstrumentSpecs) -> dict[str, InstrumentFrame]:
    return {i: frame_from_data(data, specs[i].default_spread, specs[i].stop_slippage)
            for i, data in snapshot.data.items()}


def build_dataset(snapshot: Snapshot, cfg: ResearchConfig, specs: InstrumentSpecs,
                  cache: Optional[ParquetCache] = None) -> ResearchData:
    """Frames and the feature table for every instrument of ``snapshot``."""
    _check_period(snapshot, cfg)
    summary: dict = {"timings": {}, "cache_hits": [], "rows": {}}
    started = time.perf_counter()
    frames = build_frames(snapshot, specs)
    summary["timings"]["frames"] = time.perf_counter() - started

    slices = slices_of(cfg)
    market_code = code_fingerprint(MARKET_SOURCES)
    tables = []
    started = time.perf_counter()
    for instrument, frame in frames.items():
        key = cache_key("market", instrument, snapshot.manifest["data"][instrument]["sha256"], market_code,
                        {name: [d.isoformat() for d in bounds] for name, bounds in slices.items()},
                        frame.typical_spread)
        table = cache.load("market", key) if cache else None
        if table is None:
            table = market_features(frame, build_grid(frame, slices))
            if cache:
                cache.store("market", key, table)
        else:
            summary["cache_hits"].append(f"market:{instrument}")
        summary["rows"][instrument] = len(table)
        tables.append(table)
    summary["timings"]["market"] = time.perf_counter() - started
    features = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    return ResearchData(frames=frames, features=features, summary=summary)


def _check_period(snapshot: Snapshot, cfg: ResearchConfig) -> None:
    """The snapshot must cover the slices and end by the hold-out start."""
    start, end = snapshot.period
    want_start, want_end = cfg.period
    if snapshot.manifest["study"] != cfg.study:
        raise ValueError(f"snapshot {snapshot.manifest['name']!r} is for study {snapshot.manifest['study']!r}, "
                         f"not {cfg.study!r}")
    if start > want_start or end < want_end:
        raise ValueError(f"snapshot {snapshot.manifest['name']!r} covers trading dates {snapshot.manifest['start']} "
                         f"to {snapshot.manifest['end']}, not the research period {cfg.start} to {cfg.holdout_start}")
