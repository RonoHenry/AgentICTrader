"""
Tests for algo_backtester/compare.py — runs side by side.

Task 207 (.kiro/specs/algo-backtester/tasks.md). Runs are compared from
their directories (manifest.json + summary.json). Runs on different data (a
different range, instrument set or data fingerprint) are refused: their
numbers don't measure the same thing. Different code, strategy settings or
costs are what a comparison is for.
Validates: Requirements 8.5 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from algo_backtester.compare import ComparisonError, compare
from algo_backtester.report import write_run
from tests.test_backtest_report import cfg, manifest, scripted


def _run(root: Path, **manifest_changes) -> Path:
    return write_run(root, cfg(), manifest(**manifest_changes), scripted())


def _edit_manifest(run_dir: Path, edit) -> Path:
    path = run_dir / "manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    edit(m)
    path.write_text(json.dumps(m, indent=2), encoding="utf-8")
    return run_dir


def test_side_by_side_summary(tmp_path):
    base = _run(tmp_path / "a")
    other = _edit_manifest(_run(tmp_path / "b", engine_fingerprint="f" * 64),
                           lambda m: m.update(variant="min_rr_5"))
    table = compare([base, other])
    lines = table.splitlines()
    header = next(line for line in lines if line.startswith("| metric"))
    assert "base" in header and "min_rr_5" in header
    trades = next(line for line in lines if line.startswith("| trades"))
    assert trades.count("| 1 ") == 2                                  # one column per run
    for metric in ("win rate", "avg net R", "expectancy R (95% CI)", "profit factor", "max DD R", "cost share",
                   "evidence", "code", "engine"):
        assert any(line.startswith(f"| {metric} ") for line in lines), metric
    assert "eeeeeeee" in table and "ffffffff" in table               # what differs between them


def test_side_by_side_breakdown(tmp_path):
    runs = [_run(tmp_path / "a"), _run(tmp_path / "b", engine_fingerprint="f" * 64)]
    table = compare(runs, by="instrument")
    eur = next(line for line in table.splitlines() if line.startswith("| EURUSD"))
    assert eur.count("-1.00") == 2 and "insufficient" in eur
    with pytest.raises(ComparisonError, match="breakdown"):
        compare(runs, by="weekday")


@pytest.mark.parametrize("field, value", [("sha256", "0" * 64), ("rows", 1), ("start", "2026-09-29T00:00:00+00:00"),
                                          ("end", "2026-10-02T00:00:00+00:00")])
def test_refuses_different_data_fingerprint_or_range(tmp_path, field, value):
    base = _run(tmp_path / "a")
    other = _edit_manifest(_run(tmp_path / "b", engine_fingerprint="f" * 64),
                           lambda m: m["data"]["EURUSD"].update({field: value}))
    with pytest.raises(ComparisonError, match=f"EURUSD.*{field}"):
        compare([base, other])


def test_not_a_run_directory_refused(tmp_path):
    with pytest.raises(ComparisonError, match="not a run directory"):
        compare([_run(tmp_path / "a"), tmp_path / "missing"])


def test_refuses_different_instruments_and_needs_two_runs(tmp_path):
    base = _run(tmp_path / "a")
    other = _edit_manifest(_run(tmp_path / "b", engine_fingerprint="f" * 64),
                           lambda m: m["data"].pop("XAUUSD"))
    with pytest.raises(ComparisonError, match="XAUUSD"):
        compare([base, other])
    with pytest.raises(ComparisonError, match="two"):
        compare([base])
