"""
Tests for algo_backtester/run.py — the hold-out and walk-forward run modes.

Task 204 (.kiro/specs/algo-backtester/tasks.md). A run refuses to reach into
its study's hold-out unless it is the final validation run, and records that
flag. Walk-forward runs Phase A once over the whole range, then a fresh
Phase B (new account, new broker) per window; the combined result is the
windows' results concatenated. Real data: the task 186 MetaQuotes week with
the real engine, priced with the exness-standard spec file.
Validates: Requirements 7.2, 7.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

import pytest

from agent.instruments import InstrumentSpecs, load_specs
from algo_backtester.config import HoldoutOverlapError, RunConfig, StudyConfig
from algo_backtester.run import run_backtest, walk_forward_windows
from tests.test_backtest_signals import CFG, data_for

UTC = timezone.utc
SPECS = load_specs(Path(__file__).resolve().parents[2] / "config" / "instruments" / "exness-standard.toml")


def utc(y, m, d) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


def cfg(start=date(2026, 9, 29), end=date(2026, 10, 2)) -> RunConfig:
    return RunConfig(run={"profile": "exness-standard", "instruments": ["EURUSD"], "start": start, "end": end,
                          "study": "test"}, strategy=CFG)


STUDY = StudyConfig(name="test", holdout_start=date(2026, 10, 1), created_from_data_end=date(2026, 10, 2))
OPEN_STUDY = StudyConfig(name="test", holdout_start=date(2027, 1, 1), created_from_data_end=date(2027, 4, 1))


@lru_cache(maxsize=None)
def runs():
    datas = {"EURUSD": data_for("EURUSD")}
    whole = run_backtest(cfg(), OPEN_STUDY, final=False, datas=datas, specs=SPECS, workers=1)
    windowed = run_backtest(cfg(), OPEN_STUDY, final=False, datas=datas, specs=SPECS, workers=1, walk_forward="1D")
    return whole, windowed


# ── hold-out ───────────────────────────────────────────────────────────────

def test_holdout_overlap_refused_without_final():
    with pytest.raises(HoldoutOverlapError, match="--final"):
        run_backtest(cfg(), STUDY, final=False, datas={}, specs=SPECS)   # refused before any work


def test_final_flag_recorded_in_manifest():
    final = run_backtest(cfg(end=date(2026, 9, 30)), STUDY, final=True,
                         datas={"EURUSD": data_for("EURUSD")}, specs=SPECS, workers=1)
    assert final.manifest["final_validation"] is True
    assert final.manifest["study"] == "test" and final.manifest["holdout_start"] == "2026-10-01"
    whole, _ = runs()
    assert whole.manifest["final_validation"] is False
    assert whole.manifest["windows"] == [["2026-09-29T00:00:00+00:00", "2026-10-02T00:00:00+00:00"]]


# ── walk-forward ───────────────────────────────────────────────────────────

def test_walk_forward_window_boundaries():
    assert walk_forward_windows(utc(2025, 1, 1), utc(2026, 7, 1), "3M") == [
        (utc(2025, 1, 1), utc(2025, 4, 1)), (utc(2025, 4, 1), utc(2025, 7, 1)), (utc(2025, 7, 1), utc(2025, 10, 1)),
        (utc(2025, 10, 1), utc(2026, 1, 1)), (utc(2026, 1, 1), utc(2026, 4, 1)), (utc(2026, 4, 1), utc(2026, 7, 1))]
    assert walk_forward_windows(utc(2025, 1, 31), utc(2025, 5, 15), "1M")[:2] == [
        (utc(2025, 1, 31), utc(2025, 2, 28)), (utc(2025, 2, 28), utc(2025, 3, 31))]   # month ends clamp
    assert walk_forward_windows(utc(2026, 9, 29), utc(2026, 10, 2), "2D") == [
        (utc(2026, 9, 29), utc(2026, 10, 1)), (utc(2026, 10, 1), utc(2026, 10, 2))]   # the last window is cut
    with pytest.raises(ValueError):
        walk_forward_windows(utc(2025, 1, 1), utc(2026, 1, 1), "3Q")


def test_walk_forward_windows_and_warmup_before_window():
    _, windowed = runs()
    assert [(w.start, w.end) for w in windowed.windows] == [
        (utc(2026, 9, 29), utc(2026, 9, 30)), (utc(2026, 9, 30), utc(2026, 10, 1)), (utc(2026, 10, 1), utc(2026, 10, 2))]
    for window in windowed.windows:
        assert window.result.journal and all(window.start <= r.t < window.end for r in window.result.journal)
        # warm-up comes from before the window: the first decision is priced and analysed like any other
        assert not any("NO_PRICE" in r.reason for r in window.result.journal)
        assert window.result.journal[0].t == window.start                  # decides from its first minute
        # each window is a full Phase B run: a fresh account, nothing carried over
        assert window.result.account.initial_equity == 10_000.0
        assert all(window.start <= tr.placed_at < window.end for tr in window.result.trades)


def test_walk_forward_combined_equals_concatenation():
    whole, windowed = runs()
    assert windowed.journal == [row for w in windowed.windows for row in w.result.journal]
    assert windowed.trades == [trade for w in windowed.windows for trade in w.result.trades]
    assert windowed.open_orders == [o for w in windowed.windows for o in w.result.open_orders]
    # the same decisions reach Phase B either way; only account state differs
    assert [(r.t, r.instrument, r.intent) for r in windowed.journal] == [
        (r.t, r.instrument, r.intent) for r in whole.journal]
    assert len(whole.windows) == 1 and whole.journal == whole.windows[0].result.journal


def test_cross_without_conversion_refused():
    # A cross needs its quote currency's USD rate over time; refuse it rather than skip every trade.
    eurgbp = replace(SPECS["EURUSD"], symbol="EURGBP", quote_ccy="GBP")
    specs = InstrumentSpecs("mt5", "USD", {**{s: SPECS[s] for s in SPECS}, "EURGBP": eurgbp})
    run_cfg = cfg().model_copy(update={"run": cfg().run.model_copy(update={"instruments": ("EURUSD", "EURGBP")})})
    with pytest.raises(ValueError, match="EURGBP"):
        run_backtest(run_cfg, OPEN_STUDY, final=False, datas={}, specs=specs)
