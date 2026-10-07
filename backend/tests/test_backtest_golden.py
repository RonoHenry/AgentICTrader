"""
The golden run: the whole backtester, end to end, on fixed real data.

Task 209 (.kiro/specs/algo-backtester/tasks.md). EURUSD on the task 186
MetaQuotes week (M1 from Sunday 2026-09-27, a year of native H1/H4/D1/W1 for
the warm-up), the live default strategy settings, and a frozen copy of the
exness-standard spec file (fixtures/backtester/golden/specs.toml). The run
covers 2026-09-30 to 2026-10-03, once the live M15 window has its warm-up.

Its journal is committed (golden/expected_journal.csv). Any change that alters
it on purpose (engine, order logic, fills, costs) regenerates it in the same
commit:

    UPDATE_GOLDEN=1 pytest tests/test_backtest_golden.py      (from backend/)

The user chose this week over a fresh two-week Exness export (2026-10-07).
Validates: Requirements 7.4, 9.4, 9.5 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.instruments import load_specs
from agent.strategy_config import StrategyConfig
from algo_backtester.cache import SignalCache
from algo_backtester.config import RunConfig, StudyConfig
from algo_backtester.data import load_instrument
from algo_backtester.report import GitState, build_manifest, journal_csv, write_run
from algo_backtester.report_html import write_html_report, write_report_inputs
from algo_backtester.run import run_backtest
from liquidity_engine import LiquidityMappingEngine
from services.market_data.mt5_clock import MT5ServerClock
from tests.test_backtest_signals import CFG, FixtureSource, data_for

UTC = timezone.utc
GOLDEN = Path(__file__).parent / "fixtures" / "backtester" / "golden"
SPECS = load_specs(GOLDEN / "specs.toml")
STUDY = StudyConfig(name="golden", holdout_start=date(2027, 1, 1), created_from_data_end=date(2027, 4, 1))
GIT = GitState(commit="0" * 40, dirty=False)            # fixed: the outputs mustn't depend on the checkout
CREATED = datetime(2026, 10, 7, tzinfo=UTC)


def golden_cfg() -> RunConfig:
    return RunConfig(run={"profile": "exness-standard", "instruments": ["EURUSD"], "start": date(2026, 9, 30),
                          "end": date(2026, 10, 3), "study": "golden"},
                     report={"bootstrap_resamples": 1_000})


@lru_cache(maxsize=None)
def golden_data():
    start, end = datetime(2026, 9, 30, tzinfo=UTC), datetime(2026, 10, 3, tzinfo=UTC)
    data = load_instrument(FixtureSource("EURUSD"), "EURUSD", start, end, StrategyConfig(),
                           MT5ServerClock("ny_close"), venue="mt5", max_gap_minutes=30)
    assert data.coverage.ok, data.coverage.problems
    return {"EURUSD": data}


def golden_run(root: Path, cache: SignalCache = None) -> Path:
    """The whole pipeline into root/<run_id>/, as `python -m algo_backtester run` writes it."""
    cfg, datas = golden_cfg(), golden_data()
    result = run_backtest(cfg, STUDY, final=False, datas=datas, specs=SPECS, cache=cache, workers=1)
    manifest = build_manifest(cfg, result, datas, SPECS, spec_source="golden fixture", engine_fingerprint="e" * 64,
                              git=GIT, created_at=CREATED)
    run_dir = write_run(root, cfg, manifest, result)
    write_report_inputs(run_dir, result.journal, {i: d.closed[cfg.strategy.entry_tf] for i, d in datas.items()},
                        cfg.strategy.entry_tf)
    write_html_report(run_dir)
    return run_dir


@lru_cache(maxsize=None)
def first_run() -> dict[str, bytes]:
    with tempfile.TemporaryDirectory() as root:
        run_dir = golden_run(Path(root))
        return {p.name: p.read_bytes() for p in run_dir.iterdir()}


def test_golden_journal_matches_expected():
    journal = first_run()["journal.csv"]
    expected = GOLDEN / "expected_journal.csv"
    if os.environ.get("UPDATE_GOLDEN"):
        expected.write_bytes(journal)
    assert journal == expected.read_bytes(), (
        "the golden journal changed: if the change is intended, rerun with UPDATE_GOLDEN=1 and commit the file")
    text = journal.decode()
    assert "EXECUTE" in text and "NO_TRADE" in text            # it exercises orders, not just no-trades


def test_second_run_byte_identical():
    with tempfile.TemporaryDirectory() as root:
        run_dir = golden_run(Path(root))
        again = {p.name: p.read_bytes() for p in run_dir.iterdir()}
    first = first_run()
    assert sorted(again) == sorted(first) == [
        "candles.json", "context.json", "journal.csv", "manifest.json", "report.html", "summary.json", "summary.md"]
    for name in first:
        assert again[name] == first[name], name


# ── Property 10: Determinism and Cache Transparency ────────────────────────
# Small engine windows keep each example quick; the cached run is forbidden
# from calling the engine, so it really is served from the cache.

def small_cfg(start: date, days: int) -> RunConfig:
    return RunConfig(run={"profile": "exness-standard", "instruments": ["EURUSD", "XAUUSD"], "start": start,
                          "end": start + timedelta(days=days), "study": "golden"},
                     strategy=CFG, report={"bootstrap_resamples": 200})


@settings(max_examples=6, deadline=None)
@given(st.sampled_from([date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)]), st.integers(1, 2),
       st.sampled_from([None, "1D"]))
def test_property_10_cache_hit_run_equals_empty_cache_run(start, days, walk_forward):
    cfg = small_cfg(start, days)
    datas = {"EURUSD": data_for("EURUSD"), "XAUUSD": data_for("XAUUSD")}

    def outputs(cache: SignalCache, root: Path) -> dict[str, bytes]:
        result = run_backtest(cfg, STUDY, final=False, datas=datas, specs=SPECS, cache=cache, workers=1,
                              walk_forward=walk_forward)
        manifest = build_manifest(cfg, result, datas, SPECS, spec_source="golden fixture",
                                  engine_fingerprint=cache.engine_fingerprint, git=GIT, created_at=CREATED)
        run_dir = write_run(root, cfg, manifest, result)
        return {name: (run_dir / name).read_bytes() for name in ("journal.csv", "summary.json", "summary.md")}

    with tempfile.TemporaryDirectory() as tmp:
        cache = SignalCache(Path(tmp) / "cache", "e" * 64)
        fresh = outputs(cache, Path(tmp) / "a")                                   # an empty cache: computed
        assert len(list((Path(tmp) / "cache").iterdir())) == 2                    # one entry per instrument

        engine = LiquidityMappingEngine.analyze
        LiquidityMappingEngine.analyze = _no_engine
        try:
            served = outputs(cache, Path(tmp) / "b")                              # every record from the cache
        finally:
            LiquidityMappingEngine.analyze = engine
    assert served == fresh


def _no_engine(*args, **kwargs):
    raise AssertionError("a cache hit must not run the engine")
