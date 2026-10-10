"""The research tables, built from a snapshot and cached.

``build_dataset()`` turns a loaded snapshot into what hypotheses read:

- ``frames``: each instrument's M1 and calendar bars (frame.py), for races
  and the shuffled-path baseline;
- ``features``: one row per instrument and M15 close of the slices, the
  market features (Req 3), the daily anticipation (Req 4) and the SMT
  partner's facts at the same t (Req 16, joined after the cache);
- ``labels``: the same rows, what happened after t (Req 6), in their own
  table: events and filters never see it.

Each table is cached per instrument (features/cache.py) under a key over the
instrument's data fingerprint, the code that computes it and its settings.
The rows of all instruments are stacked in the configuration's instrument
order; the feature and label tables share their index (the row id).

    data = build_dataset(snapshot, cfg, specs, ParquetCache.default())
    data.features, data.frames["EURUSD"], data.summary

Validates: Requirements 3.5, 18 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from agent.instruments import InstrumentSpecs
from agent.strategy_config import StrategyConfig
from algo_backtester.cache import engine_code_fingerprint
from algo_backtester.data import InstrumentData
from algo_research.config import ResearchConfig
from algo_research.features.anticipation import anticipation_key, daily_anticipation, join_anticipation
from algo_research.features.cache import LABEL_SOURCES, MARKET_SOURCES, ParquetCache, cache_key, code_fingerprint
from algo_research.features.draws import draw_taken_at
from algo_research.features.market import market_features
from algo_research.features.partner import partner_features
from algo_research.frame import InstrumentFrame, build_grid, frame_from_data, slices_of
from algo_research.labels import LABEL_COLUMNS, build_labels, draw_labels
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


def build_dataset(snapshot: Snapshot, cfg: ResearchConfig, specs: InstrumentSpecs, strategy: StrategyConfig,
                  cache: Optional[ParquetCache] = None, workers: Optional[int] = None) -> ResearchData:
    """Frames and the feature table for every instrument of ``snapshot``.
    ``strategy`` is the StrategyConfig the engine runs with (Phase A's);
    ``workers`` the processes for the anticipation (1: this process)."""
    _check_period(snapshot, cfg)
    summary: dict = {"timings": {}, "cache_hits": [], "rows": {}, "engine_errors": []}
    started = time.perf_counter()
    frames = build_frames(snapshot, specs)
    summary["timings"]["frames"] = time.perf_counter() - started

    slices = {name: [d.isoformat() for d in bounds] for name, bounds in slices_of(cfg).items()}
    codes = {"market": code_fingerprint(MARKET_SOURCES), "labels": code_fingerprint(LABEL_SOURCES)}

    def cached(kind: str, instrument: str, compute) -> pd.DataFrame:
        key = cache_key(kind, instrument, snapshot.manifest["data"][instrument]["sha256"], codes[kind], slices,
                        frames[instrument].typical_spread)
        table = cache.load(kind, key) if cache else None
        if table is not None:
            summary["cache_hits"].append(f"{kind}:{instrument}")
            return table
        table = compute()
        return cache.store(kind, key, table) if cache else table

    started = time.perf_counter()
    markets = {i: cached("market", i, lambda f=f: market_features(f, build_grid(f, slices_of(cfg))))
               for i, f in frames.items()}
    summary["rows"] = {i: len(t) for i, t in markets.items()}
    summary["timings"]["market"] = time.perf_counter() - started

    started = time.perf_counter()
    labels = [cached("labels", i, lambda i=i: build_labels(frames[i], markets[i])) for i in frames]
    summary["timings"]["labels"] = time.perf_counter() - started

    started = time.perf_counter()
    tables = _with_anticipation(snapshot, list(markets.values()), strategy, cache, workers, summary)
    summary["timings"]["anticipation"] = time.perf_counter() - started

    # The engine's draws as levels (Req 18): from the joined anticipation, so not cached with the market.
    started = time.perf_counter()
    for n, instrument in enumerate(markets):
        tables[n] = pd.concat([tables[n], draw_taken_at(frames[instrument], tables[n])], axis=1)
        drawn = draw_labels(frames[instrument], tables[n]).set_axis(labels[n].index)
        labels[n] = pd.concat([labels[n], drawn], axis=1)[list(LABEL_COLUMNS)]
    summary["timings"]["draws"] = time.perf_counter() - started
    tables = list(partner_features(dict(zip(markets, tables)), cfg.smt.pairs).values())   # after the cache
    features = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    label_table = pd.concat(labels, ignore_index=True) if labels else pd.DataFrame()
    return ResearchData(frames=frames, features=features, labels=label_table, summary=summary)


def _with_anticipation(snapshot: Snapshot, markets: list[pd.DataFrame], strategy: StrategyConfig,
                       cache: Optional[ParquetCache], workers: Optional[int], summary: dict) -> list[pd.DataFrame]:
    """Each instrument's market table with the engine's daily anticipation (Req 4),
    computed in one process per instrument unless cached."""
    engine_fp = engine_code_fingerprint()
    instruments = list(snapshot.data)
    keys, dailies = {}, {}
    for instrument, market in zip(instruments, markets):
        dates = sorted(pd.Timestamp(d).date().isoformat() for d in market["trading_date"].unique())
        keys[instrument] = anticipation_key(instrument, snapshot.manifest["data"][instrument]["sha256"], engine_fp,
                                            strategy, dates)
        daily = cache.load("anticipation", keys[instrument]) if cache else None
        if daily is not None:
            dailies[instrument] = daily
            summary["cache_hits"].append(f"anticipation:{instrument}")
    todo = [(i, m) for i, m in zip(instruments, markets) if i not in dailies]
    if workers == 1 or len(todo) <= 1:
        computed = {i: daily_anticipation(snapshot.data[i], m, strategy) for i, m in todo}
    else:
        with ProcessPoolExecutor(max_workers=min(workers or len(todo), len(todo))) as pool:
            futures = {i: pool.submit(_anticipation_worker, snapshot.data[i], m, strategy) for i, m in todo}
            computed = {i: future.result() for i, future in futures.items()}
    for instrument, (daily, _) in computed.items():
        dailies[instrument] = cache.store("anticipation", keys[instrument], daily) if cache else daily
    for instrument in instruments:
        summary["engine_errors"].extend(dailies[instrument]["error"].dropna())
    return [join_anticipation(m, dailies[i]) for i, m in zip(instruments, markets)]


def _anticipation_worker(data: InstrumentData, market: pd.DataFrame, strategy: StrategyConfig):
    return daily_anticipation(data, market, strategy)


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
