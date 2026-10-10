"""
Tests for algo_backtester/report.py — manifest, journal and summary writers.

Task 206 (.kiro/specs/algo-backtester/tasks.md). A run directory holds
manifest.json (what makes the run reproducible; its id is the hash of its
content), journal.csv (one row per SignalRecord, skipped intents included)
and summary.json / summary.md. Identical inputs give byte-identical files.
Validates: Requirements 8.1, 8.6, 9.5 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import pytest

from agent.instruments import load_specs
from algo_backtester.config import RunConfig
from algo_backtester.report import (
    JOURNAL_COLUMNS,
    GitState,
    build_manifest,
    git_state,
    journal_csv,
    run_id,
    spec_source,
    summary_md,
    write_run,
)
from algo_backtester.metrics import summarize
from algo_backtester.run import RunResult, WindowResult
from algo_backtester.signals import EngineError, SignalRecord
from agent.order_intent import NoTrade
from tests.test_backtest_signals import CFG, data_for
from tests.test_backtest_simulation import T0, dip, flat, intent, run

UTC = timezone.utc
MIN = timedelta(minutes=1)
SPEC_FILE = Path(__file__).resolve().parents[2] / "config" / "instruments" / "exness-standard.toml"
SPECS = load_specs(SPEC_FILE)
CREATED = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
GIT = GitState(commit="a" * 40, dirty=False)


def cfg() -> RunConfig:
    return RunConfig(run={"profile": "exness-standard", "instruments": ["EURUSD", "XAUUSD"],
                          "start": date(2026, 9, 30), "end": date(2026, 10, 1), "study": "test"},
                     strategy=CFG, variant=None)


@lru_cache(maxsize=None)
def scripted() -> RunResult:
    """Every kind of journal row: EXECUTE (stopped out, and still open at the end),
    IN_TRADE, SKIP, NO_TRADE, RR_BELOW_MIN, ENGINE_ERROR."""
    instruments = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
    bars = {i: flat(i) for i in instruments}
    bars["EURUSD"] = dip(bars["EURUSD"], T0 + 29 * MIN, low=1.0985)
    signals = {i: [intent(i, T0, f"{i}-1")] for i in instruments}       # XAUUSD: the 4th trade, refused
    signals["EURUSD"] += [
        intent("EURUSD", T0 + 15 * MIN, "EURUSD-2"),                    # in trade
        SignalRecord(T0 + 45 * MIN, "EURUSD", NoTrade("EURUSD", T0 + 45 * MIN, "NO_TRADE", "NO_TRADE", "5/8")),
        SignalRecord(T0 + 60 * MIN, "EURUSD", NoTrade("EURUSD", T0 + 60 * MIN, "A", "RR_BELOW_MIN",
                                                      "R:R 2.10 is below the 3.0 floor", 2.1)),
        SignalRecord(T0 + 75 * MIN, "EURUSD", EngineError("ValueError", "boom, with a comma")),
    ]
    sim = run(bars, signals)
    windows = [["2026-09-30T00:00:00+00:00", "2026-10-01T00:00:00+00:00"]]
    return RunResult(windows=[WindowResult(T0, T0 + timedelta(days=1), sim)], signals=signals,
                     floored_bars={"EURUSD": 12, "XAUUSD": 0},
                     manifest={"study": "test", "holdout_start": "2027-01-01", "final_validation": False,
                               "variant": None, "windows": windows})


def manifest(**changes) -> dict:
    datas = {"EURUSD": data_for("EURUSD"), "XAUUSD": data_for("XAUUSD")}
    args = dict(spec_source="Exness (KE) Limited / ExnessKE-MT5Trial9, exported 2026-10-05",
                engine_fingerprint="e" * 64, git=GIT, created_at=CREATED)
    return build_manifest(cfg(), scripted(), datas, SPECS, **{**args, **changes})


# ── manifest ───────────────────────────────────────────────────────────────

def test_run_id_is_manifest_hash_excluding_created_at():
    first = manifest()
    later = manifest(created_at=CREATED + timedelta(hours=5))
    assert first["run_id"] == later["run_id"] and len(first["run_id"]) == 64
    assert first["created_at"] != later["created_at"]
    assert manifest(git=GitState("a" * 40, dirty=True))["run_id"] != first["run_id"]
    assert manifest(engine_fingerprint="f" * 64)["run_id"] != first["run_id"]
    # the id is the content's hash, whatever the key order
    assert run_id(dict(reversed(list(first.items())))) == first["run_id"]
    assert first["bootstrap_seed"] == int(first["run_id"][:8], 16)


def test_manifest_records_git_engine_data_and_flags():
    m = manifest()
    assert (m["git_commit"], m["git_dirty"]) == ("a" * 40, False)
    assert m["engine_code_fingerprint"] == "e" * 64
    assert m["ai_modifiers"] == "disabled" and m["news_filter"] == "not_applied"
    assert (m["study"], m["final_validation"], m["variant"]) == ("test", False, None)
    assert m["broker_profile"] == "exness-standard"
    assert m["instrument_spec_source"].startswith("Exness (KE) Limited")
    assert m["instrument_specs"]["EURUSD"]["default_spread"] == 8e-05
    assert m["instrument_specs"]["EURUSD"]["commission"] == {"kind": "PER_LOT_PER_SIDE", "value": 0.0}
    assert m["strategy_config"] == CFG.model_dump(mode="json")
    assert m["run_config"]["run"]["instruments"] == ["EURUSD", "XAUUSD"]
    eur = m["data"]["EURUSD"]
    data = data_for("EURUSD")
    assert (eur["start"], eur["end"]) == ("2026-09-30T00:00:00+00:00", "2026-10-01T00:00:00+00:00")
    assert (eur["rows"], eur["sha256"], eur["m1_rows"]) == (data.fingerprint.rows, data.fingerprint.sha256,
                                                            len(data.m1))
    assert eur["warmup_source_by_tf"] == data.warmup_source and eur["default_spread_bars"] == 12
    assert eur["coverage_problems"] == []
    json.dumps(m)                                    # all of it is plain JSON


def test_spec_source_and_git_state_read_from_disk():
    assert spec_source(SPEC_FILE) == "Exness (KE) Limited / ExnessKE-MT5Trial9, exported 2026-10-05"
    state = git_state()
    assert len(state.commit) == 40 and isinstance(state.dirty, bool)


# ── journal ────────────────────────────────────────────────────────────────

def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def test_journal_includes_skipped_intents_with_reason():
    result = scripted()
    rows = _rows(journal_csv(result.journal, result.open_orders))
    assert len(rows) == len(result.journal) == 8
    by = {(r["instrument"], r["decision"]): r for r in rows}
    assert "concurrent trades 3" in by["XAUUSD", "SKIP"]["reason"]
    assert by["EURUSD", "IN_TRADE"]["reason"] == "sim-000001 is open"
    assert by["EURUSD", "NO_TRADE"]["reason"] == "5/8"
    assert by["EURUSD", "RR_BELOW_MIN"]["grade"] == "A"
    assert by["EURUSD", "ENGINE_ERROR"]["reason"] == "ValueError: boom, with a comma"   # quoted, not split
    stopped = next(r for r in rows if r["setup_id"] == "EURUSD-1")
    assert stopped["exit_reason"] == "SL" and stopped["net_r"]
    still_open = next(r for r in rows if r["setup_id"] == "GBPUSD-1")
    assert still_open["exit_reason"] == "OPEN_AT_END" and still_open["fill"] and not still_open["net_r"]


def test_journal_columns_order_and_fixed_precision():
    result = scripted()
    text = journal_csv(result.journal, result.open_orders)
    header = text.split("\n", 1)[0]
    assert header.split(",") == list(JOURNAL_COLUMNS)
    assert list(JOURNAL_COLUMNS[:8]) == ["t", "instrument", "setup_id", "grade", "decision", "reason", "killzone",
                                         "time_window"]
    stopped = next(r for r in _rows(text) if r["setup_id"] == "EURUSD-1")
    assert stopped["t"] == "2026-09-30T13:00:00+00:00" and stopped["direction"] == "LONG"
    assert stopped["entry"] == "1.100100" and stopped["stop"] == "1.099100"     # prices: 6 decimals
    assert stopped["net_r"] == "-1.0000" and stopped["gross_r"] == "-0.9000"    # R: 4 decimals
    assert stopped["lots"] == "1.00000" and stopped["confidence"] == "0.80"
    assert stopped["holding_minutes"] == "29" and stopped["cost_flag"] == "false"
    assert stopped["time_window"] == "NY_AM_KILLZONE"
    assert text.endswith("\n") and "\r" not in text
    ts = [(r["t"], r["instrument"]) for r in _rows(text)]
    assert ts == sorted(ts)


# ── summary ────────────────────────────────────────────────────────────────

def test_summary_md_marks_insufficient_buckets():
    result = scripted()
    summary = summarize(result.journal, 10_000.0, min_trades=30, resamples=200, seed=1)
    md = summary_md(summary, manifest(), min_trades=30)
    assert "Insufficient evidence" in md and "n < 30" in md
    eur_line = next(line for line in md.splitlines() if line.startswith("| EURUSD"))
    assert "insufficient" in eur_line
    assert manifest()["run_id"] in md and "ai_modifiers: disabled" in md and "news_filter: not_applied" in md
    roomy = summary_md(summarize(result.journal, 10_000.0, min_trades=1, resamples=200, seed=1), manifest(), 1)
    assert "insufficient" not in next(line for line in roomy.splitlines() if line.startswith("| EURUSD"))


def test_write_run_directory_and_byte_identical_rewrite(tmp_path):
    m = manifest()
    first = write_run(tmp_path, cfg(), m, scripted())
    assert first == tmp_path / m["run_id"]
    assert sorted(p.name for p in first.iterdir()) == ["journal.csv", "manifest.json", "summary.json", "summary.md"]
    saved = {p.name: p.read_bytes() for p in first.iterdir()}
    assert json.loads(saved["manifest.json"])["run_id"] == m["run_id"]
    summary = json.loads(saved["summary.json"])
    assert summary["overall"]["trades"] == 1 and summary["counts"]["open_at_end"] == 2   # GBPUSD, USDJPY
    assert set(summary["breakdowns"]) == {"instrument", "grade", "killzone", "time_window", "direction", "month"}

    second = write_run(tmp_path, cfg(), manifest(created_at=CREATED + timedelta(days=1)), scripted())
    assert second == first
    again = {p.name: p.read_bytes() for p in second.iterdir()}
    assert {k: v for k, v in again.items() if k != "manifest.json"} == {
        k: v for k, v in saved.items() if k != "manifest.json"}
