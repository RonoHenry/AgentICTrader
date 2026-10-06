"""
Tests for algo_backtester/cache.py — the Phase A cache.

Task 200 (.kiro/specs/algo-backtester/tasks.md). Phase A costs about 14
minutes per instrument-year, so its records are cached, keyed by everything
they depend on. Real records come from the task 186 fixture week (see
test_backtest_signals.py): 12:00-14:00 UTC on 2026-09-30 holds both order
intents and no-trades.
Validates: Requirements 7.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import pytest

from agent.order_intent import NoTrade, OrderIntent
from agent.strategy_config import StrategyConfig
from algo_backtester.cache import ENGINE_SOURCES, SignalCache, cache_key, engine_code_fingerprint
from algo_backtester.data import DataFingerprint
from algo_backtester.signals import EngineError, SignalRecord, generate_all, generate_signals
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import SetupGrade, Timeframe
from ml.features.session_features import TimeFeatures
from tests.test_backtest_signals import CFG, data_for

UTC = timezone.utc
START, END = datetime(2026, 9, 30, 12, 0, tzinfo=UTC), datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
ENGINE_FP = "e" * 64


class CountingEngine:
    """The real engine, counting its analyze() calls."""

    def __init__(self):
        self.calls = 0
        self._engine = LiquidityMappingEngine()

    def analyze(self, view, instrument, t):
        self.calls += 1
        return self._engine.analyze(view, instrument, t)


@lru_cache(maxsize=None)
def real_records() -> tuple[SignalRecord, ...]:
    records = tuple(generate_signals(data_for(), CFG, START, END))
    assert {type(r.result) for r in records} == {OrderIntent, NoTrade}
    return records


def cfg_with(**changes) -> StrategyConfig:
    return StrategyConfig.model_validate({**CFG.model_dump(), **changes})


def key_with(**changes) -> str:
    args = dict(data_fp=DataFingerprint(1000, "a" * 64), engine_fp=ENGINE_FP, cfg=CFG, instrument="EURUSD",
                start=START, end=END)
    return cache_key(**{**args, **changes})


# ── key ────────────────────────────────────────────────────────────────────

def test_key_changes_with_each_input():
    base = key_with()
    variants = {
        "data rows": key_with(data_fp=DataFingerprint(1001, "a" * 64)),
        "data hash": key_with(data_fp=DataFingerprint(1000, "b" * 64)),
        "engine code": key_with(engine_fp="f" * 64),
        "min_rr": key_with(cfg=cfg_with(min_rr=5.0)),
        "tp_levels": key_with(cfg=cfg_with(tp_levels=(2.0, 4.0))),
        "candle_counts": key_with(cfg=cfg_with(candle_counts={**CFG.model_dump()["candle_counts"], "M15": 61})),
        "grade_confidence": key_with(cfg=cfg_with(grade_confidence={"A+": 0.9, "A": 0.8, "B": 0.6})),
        "instrument": key_with(instrument="GBPUSD"),
        "start": key_with(start=START - timedelta(minutes=15)),
        "end": key_with(end=END + timedelta(minutes=15)),
    }
    assert key_with() == base
    assert base not in variants.values()
    assert len(set(variants.values())) == len(variants)


def test_execution_only_settings_share_key():
    # Phase A never reads the expiry rule, so an expiry variant reuses the analysis (Req 7.4).
    assert key_with(cfg=cfg_with(pending_expiry="FIXED_TTL", fallback_ttl_minutes=60)) == key_with()


def test_same_instant_in_another_timezone_same_key():
    plus3 = timezone(timedelta(hours=3))
    assert key_with(start=START.astimezone(plus3), end=END.astimezone(plus3)) == key_with()


# ── hits ───────────────────────────────────────────────────────────────────

def test_hit_returns_identical_records(tmp_path):
    cache = SignalCache(tmp_path, ENGINE_FP)
    data = data_for()
    first, second = CountingEngine(), CountingEngine()

    fresh = cache.signals(data, CFG, START, END, engine=first)
    hit = cache.signals(data, CFG, START, END, engine=second)

    assert first.calls == len(fresh) > 0 and second.calls == 0
    assert hit == fresh == list(real_records())
    intent = next(r.result for r in hit if isinstance(r.result, OrderIntent))
    # == alone would accept "A" for SetupGrade.A: types must come back too
    assert type(intent.grade) is SetupGrade and type(intent.entry_tf) is Timeframe
    assert type(intent.time_features) is TimeFeatures and type(intent.patterns) is tuple
    assert intent.as_of.utcoffset() == timedelta(0)


def test_every_result_kind_round_trips(tmp_path):
    cache = SignalCache(tmp_path, ENGINE_FP)
    records = [*real_records(), SignalRecord(END, "EURUSD", EngineError("ValueError", "engine blew up"))]
    assert cache.store("k" * 64, records) == records
    assert cache.load("k" * 64) == records


def test_miss_returns_none(tmp_path):
    assert SignalCache(tmp_path, ENGINE_FP).load("k" * 64) is None


def test_generate_all_writes_and_reuses_cache(tmp_path):
    datas = [data_for("EURUSD"), data_for("XAUUSD")]
    start, end = datetime(2026, 9, 30, 13, 0, tzinfo=UTC), datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
    cache = SignalCache(tmp_path, ENGINE_FP)

    parallel = generate_all(datas, CFG, start, end, workers=2, cache=cache)

    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        cache.path(cache.key(d, CFG, start, end)).name for d in datas)
    assert generate_all(datas, CFG, start, end, workers=1, cache=cache) == parallel
    assert parallel == generate_all(datas, CFG, start, end, workers=1)


# ── corruption and atomic writes ───────────────────────────────────────────

CORRUPTIONS = {
    "cut mid-line": lambda text: text[: len(text) // 2],
    "first record lost": lambda text: "".join(text.splitlines(keepends=True)[1:]),
    "one value changed": lambda text: text.replace('"SHORT"', '"LONG"', 1),
    "empty": lambda text: "",
    "not json": lambda text: "\x00\x01garbage\n",
}


@pytest.mark.parametrize("corrupt", CORRUPTIONS.values(), ids=CORRUPTIONS.keys())
def test_corrupt_entry_recomputed(tmp_path, corrupt):
    cache = SignalCache(tmp_path, ENGINE_FP)
    data = data_for()
    fresh = cache.signals(data, CFG, START, END)
    path = cache.path(cache.key(data, CFG, START, END))
    path.write_text(corrupt(path.read_text(encoding="utf-8")), encoding="utf-8")

    assert cache.load(cache.key(data, CFG, START, END)) is None
    engine = CountingEngine()
    assert cache.signals(data, CFG, START, END, engine=engine) == fresh
    assert engine.calls == len(fresh)                               # recomputed, not served
    assert cache.load(cache.key(data, CFG, START, END)) == fresh   # and rewritten whole


class Crash(Exception):
    pass


def test_write_is_atomic(tmp_path):
    cache = SignalCache(tmp_path, ENGINE_FP)
    records = real_records()
    key = "k" * 64

    def crashing():
        for i, record in enumerate(records):
            assert not cache.path(key).exists()   # nothing appears under the key until the write completes
            if i == 3:
                raise Crash
            yield record

    with pytest.raises(Crash):
        cache.store(key, crashing())
    assert cache.load(key) is None
    assert list(tmp_path.iterdir()) == []         # no temporary file left behind

    cache.store(key, records)
    with pytest.raises(Crash):
        cache.store(key, (r if i < 3 else _raise(Crash) for i, r in enumerate(records)))
    assert cache.load(key) == list(records)       # a failed rewrite leaves the old entry intact
    assert list(tmp_path.iterdir()) == [cache.path(key)]


def _raise(exc):
    raise exc


# ── engine code fingerprint ────────────────────────────────────────────────

def _fake_repo(root: Path) -> None:
    files = ["liquidity_engine/__init__.py", "liquidity_engine/grader/setup_grader.py"]
    files += [s for s in ENGINE_SOURCES if "*" not in s]
    for rel in files:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(f"# {rel}\nx = 1\n".encode())   # LF, as git stores it
    (root / "agent" / "unrelated.py").write_bytes(b"y = 1\n")


def test_engine_source_edit_invalidates(tmp_path):
    _fake_repo(tmp_path)
    base = engine_code_fingerprint(tmp_path)
    grader = tmp_path / "liquidity_engine" / "grader" / "setup_grader.py"
    original = grader.read_bytes()

    assert engine_code_fingerprint(tmp_path) == base
    grader.write_bytes(original.replace(b"x = 1", b"x = 2"))
    edited = engine_code_fingerprint(tmp_path)
    assert edited != base

    grader.write_bytes(original)
    assert engine_code_fingerprint(tmp_path) == base
    (tmp_path / "liquidity_engine" / "new_detector.py").write_text("z = 1\n", encoding="utf-8")
    assert engine_code_fingerprint(tmp_path) not in (base, edited)

    data = data_for()
    assert SignalCache(tmp_path, base).key(data, CFG, START, END) != SignalCache(tmp_path, edited).key(
        data, CFG, START, END)


@pytest.mark.parametrize("rel", [s for s in ENGINE_SOURCES if "*" not in s])
def test_each_listed_source_counts(tmp_path, rel):
    _fake_repo(tmp_path)
    base = engine_code_fingerprint(tmp_path)
    (tmp_path / rel).write_text("changed = True\n", encoding="utf-8")
    assert engine_code_fingerprint(tmp_path) != base


def test_unrelated_file_and_line_endings_do_not_count(tmp_path):
    _fake_repo(tmp_path)
    base = engine_code_fingerprint(tmp_path)
    (tmp_path / "agent" / "unrelated.py").write_text("y = 2\n", encoding="utf-8")
    grader = tmp_path / "liquidity_engine" / "grader" / "setup_grader.py"
    grader.write_bytes(grader.read_bytes().replace(b"\n", b"\r\n"))  # a Windows checkout
    assert engine_code_fingerprint(tmp_path) == base


def test_missing_listed_source_raises(tmp_path):
    _fake_repo(tmp_path)
    (tmp_path / "agent" / "order_intent.py").unlink()
    with pytest.raises(FileNotFoundError, match="order_intent.py"):
        engine_code_fingerprint(tmp_path)


def test_repo_engine_fingerprint():
    fp = engine_code_fingerprint()
    assert len(fp) == 64 and fp == engine_code_fingerprint()
    assert SignalCache.default().engine_fingerprint == fp
