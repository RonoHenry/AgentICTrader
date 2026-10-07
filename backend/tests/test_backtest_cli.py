"""
Tests for algo_backtester/cli.py — python -m algo_backtester run | compare | check-data.

Task 208 (.kiro/specs/algo-backtester/tasks.md). The CLI is driven with the
task 186 MetaQuotes fixture week as its candle source (the store is injected)
and the real engine; studies and run outputs go to a temporary directory.
Validates: Requirements 7.1 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from algo_backtester.cli import main, parse_args
from tests.test_backtest_signals import FixtureSource

UTC = timezone.utc

CONFIG = """
[run]
profile = "exness-standard"
instruments = ["EURUSD"]
start = 2026-09-30
end = 2026-10-01
study = "cli-test"

[strategy]
entry_tf = "M15"
context_tfs = ["H4"]
candle_counts = { M15 = 60, H4 = 30, D1 = 20, W1 = 8 }

[report]
bootstrap_resamples = 200

[variants.min_rr_5]
strategy.min_rr = 5.0
"""


class Source(FixtureSource):
    """The fixture week, plus the latest stored bar (what sets a new study's hold-out)."""

    def last_time(self, instrument, tf):
        bars = self.bars(instrument, tf, datetime(2000, 1, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC))
        return bars[-1].timestamp if bars else None


@pytest.fixture
def setup(tmp_path):
    config = tmp_path / "base.toml"
    config.write_text(CONFIG, encoding="utf-8")
    return config, tmp_path


def study(root: Path, holdout_start: str) -> None:
    path = root / "config" / "backtests" / "studies" / "cli-test.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"holdout_start = {holdout_start}\ncreated_from_data_end = 2026-10-02\n", encoding="utf-8")


def cli(args, root, source=None) -> int:
    return main(args, source_factory=lambda profile: source or Source("EURUSD"), studies_root=root)


# ── check-data ─────────────────────────────────────────────────────────────

def test_check_data_nonzero_exit_on_coverage_failure(setup, capsys):
    config, root = setup
    cut = Source("EURUSD", m1_until=datetime(2026, 9, 30, 12, 0, tzinfo=UTC))   # M1 history stops mid-run
    assert cli(["check-data", str(config)], root, cut) == 1
    out = capsys.readouterr().out
    assert "EURUSD" in out and "ends" in out
    # the study is created on first use, its hold-out set from the latest stored data (D7)
    created = (root / "config" / "backtests" / "studies" / "cli-test.toml").read_text(encoding="utf-8")
    assert "holdout_start = 2026-06-30" in created and "hold-out" in out


def test_check_data_zero_exit_when_covered(setup, capsys):
    config, root = setup
    study(root, "2026-10-01")
    assert cli(["check-data", str(config)], root) == 0
    out = capsys.readouterr().out
    assert "EURUSD: ok" in out and "2026-10-01" in out


# ── run ────────────────────────────────────────────────────────────────────

def test_run_writes_outputs_to_run_dir(setup, capsys):
    config, root = setup
    study(root, "2026-10-01")
    runs = root / "runs"
    assert cli(["run", str(config), "--runs-dir", str(runs), "--no-cache", "--workers", "1"], root) == 0
    [run_dir] = list(runs.iterdir())
    assert sorted(p.name for p in run_dir.iterdir()) == ["journal.csv", "manifest.json", "summary.json", "summary.md"]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == run_dir.name and manifest["final_validation"] is False
    assert manifest["instrument_spec_source"].startswith("Exness")
    assert len((run_dir / "journal.csv").read_text(encoding="utf-8").splitlines()) > 50   # a day of M15 closes
    assert str(run_dir) in capsys.readouterr().out


def test_run_refuses_holdout_and_coverage_problems(setup, capsys):
    config, root = setup
    study(root, "2026-09-30")                                    # the run is inside the hold-out
    assert cli(["run", str(config), "--runs-dir", str(root / "runs"), "--no-cache"], root) == 2
    assert "--final" in capsys.readouterr().out
    study(root, "2026-10-01")
    cut = Source("EURUSD", m1_until=datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
    assert cli(["run", str(config), "--runs-dir", str(root / "runs"), "--no-cache"], root, cut) == 1
    assert "coverage" in capsys.readouterr().out.lower()
    assert not (root / "runs").exists()


def test_variant_and_final_flags_parsed(setup, capsys):
    args = parse_args(["run", "base.toml", "--variant", "min_rr_5", "--final", "--walk-forward", "3M", "--workers", "2"])
    assert (args.command, args.config, args.variant, args.final, args.walk_forward, args.workers) == (
        "run", "base.toml", "min_rr_5", True, "3M", 2)
    assert parse_args(["run", "base.toml"]).final is False

    config, root = setup
    study(root, "2026-09-30")
    runs = root / "runs"
    assert cli(["run", str(config), "--variant", "min_rr_5", "--final", "--runs-dir", str(runs), "--no-cache",
                "--workers", "1"], root) == 0
    [run_dir] = list(runs.iterdir())
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["final_validation"] is True and manifest["variant"] == "min_rr_5"
    assert manifest["strategy_config"]["min_rr"] == 5.0


# ── compare ────────────────────────────────────────────────────────────────

def test_compare_prints_side_by_side_and_refuses_with_exit_2(setup, capsys):
    config, root = setup
    study(root, "2026-10-01")
    runs = root / "runs"
    assert cli(["run", str(config), "--runs-dir", str(runs), "--no-cache", "--workers", "1"], root) == 0
    assert cli(["run", str(config), "--variant", "min_rr_5", "--runs-dir", str(runs), "--no-cache", "--workers", "1"],
               root) == 0
    capsys.readouterr()
    run_dirs = sorted(str(p) for p in runs.iterdir())
    assert cli(["compare", *run_dirs], root) == 0
    assert "| trades |" in capsys.readouterr().out
    assert cli(["compare", run_dirs[0]], root) == 2
