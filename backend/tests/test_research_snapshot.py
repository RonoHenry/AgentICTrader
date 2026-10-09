"""
Tests for algo_research/snapshot.py — the research data snapshot: export,
SnapshotSource, manifest and fingerprint check.

Task 245 (.kiro/specs/algo-research/tasks.md). Real data: the backtester's task
186 fixture week (MetaQuotes-Demo M1 from Sunday 2026-09-27, a year of native
H1/H4/D1/W1 for the warm-up), read through its FixtureSource, with the small
engine windows of the Phase A tests so the warm-up comes from native bars.
Validates: Requirements 1.1-1.5 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from algo_backtester.data import load_instrument
from algo_research.config import HoldoutError, trading_date_open
from algo_research.snapshot import (
    RecordingSource,
    SnapshotError,
    SnapshotSource,
    SnapshotSpec,
    export_snapshot,
    load_snapshot,
)
from liquidity_engine.models import Timeframe as TF
from services.market_data.mt5_clock import MT5ServerClock
from tests.test_backtest_signals import CFG, FixtureSource

UTC = timezone.utc
CREATED = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
CLOCK = MT5ServerClock("ny_close")


def spec(**changes) -> SnapshotSpec:
    base = SnapshotSpec(
        name="fixture-week", profile="metaquotes-demo", venue="mt5", source="mt5",
        instruments=("EURUSD", "XAUUSD"), start=date(2026, 9, 29), end=date(2026, 10, 2),
        study="golden", holdout_start=date(2026, 10, 2), strategy=CFG, clock=CLOCK, max_gap_minutes=30,
        spec_source="fixture specs",
    )
    return replace(base, **changes)


class MultiFixtureSource:
    """FixtureSource for several instruments, counting calls."""

    def __init__(self):
        self.calls = []

    def bars(self, instrument, tf, start, end):
        self.calls.append((instrument, tf, start, end))
        return FixtureSource(instrument).bars(instrument, tf, start, end)

    def last_time(self, instrument, tf):
        self.calls.append((instrument, tf))
        return None


def export(tmp_path: Path, **changes) -> Path:
    export_snapshot(MultiFixtureSource(), spec(**changes), tmp_path, git_commit="c" * 40, created_at=CREATED)
    return tmp_path / spec(**changes).name


def direct(instrument: str):
    s = spec()
    return load_instrument(FixtureSource(instrument), instrument, trading_date_open(s.start),
                           trading_date_open(s.end), CFG, CLOCK, venue="mt5", max_gap_minutes=30)


def test_recording_source_keeps_every_row_load_instrument_reads():
    inner = MultiFixtureSource()
    rec = RecordingSource(inner)
    s = spec()
    data = load_instrument(rec, "EURUSD", trading_date_open(s.start), trading_date_open(s.end), CFG, CLOCK,
                           venue="mt5", max_gap_minutes=30)
    assert rec.recorded("EURUSD", TF.M1) == data.m1
    # Every row any call returned is kept, once, in time order.
    returned = {}
    for instrument, tf, start, end in inner.calls:
        for bar in FixtureSource(instrument).bars(instrument, tf, start, end):
            returned.setdefault((tf, bar.timestamp), bar)
    kept = [(tf, b.timestamp) for tf in rec.timeframes("EURUSD") for b in rec.recorded("EURUSD", tf)]
    assert sorted(kept, key=lambda k: (k[0].value, k[1])) == sorted(returned, key=lambda k: (k[0].value, k[1]))
    assert len(set(kept)) == len(kept)
    assert set(rec.timeframes("EURUSD")) > {TF.M1}          # the native warm-up bars are in it too


def test_snapshot_round_trip_same_fingerprint(tmp_path):
    path = export(tmp_path)
    snapshot = load_snapshot(path)
    for instrument in ("EURUSD", "XAUUSD"):
        original = direct(instrument)
        loaded = snapshot.data[instrument]
        assert loaded.fingerprint == original.fingerprint          # Req 1.4
        assert loaded.m1 == original.m1
        assert loaded.closed == original.closed
        assert loaded.warmup_source == original.warmup_source
    assert snapshot.manifest["name"] == "fixture-week"
    assert snapshot.strategy == CFG


def test_snapshot_source_is_a_candle_source(tmp_path):
    source = SnapshotSource(export(tmp_path))
    s = spec()
    start, end = trading_date_open(s.start), trading_date_open(s.start).replace(hour=23)
    bars = source.bars("EURUSD", TF.M1, start, end)                # [start, end), oldest first
    assert bars and bars == FixtureSource("EURUSD").bars("EURUSD", TF.M1, start, end)
    assert source.bars("EURUSD", TF.M5, trading_date_open(s.start), trading_date_open(s.end)) == []
    assert source.bars("GBPUSD", TF.M1, trading_date_open(s.start), trading_date_open(s.end)) == []
    assert source.last_time("EURUSD", TF.M1) == direct("EURUSD").m1[-1].timestamp
    assert source.last_time("GBPUSD", TF.M1) is None


def test_export_refuses_end_after_holdout(tmp_path):
    inner = MultiFixtureSource()
    with pytest.raises(HoldoutError, match="2026-10-02"):
        export_snapshot(inner, spec(end=date(2026, 10, 3)), tmp_path, git_commit="c" * 40, created_at=CREATED)
    assert inner.calls == []                                       # refused before any read
    assert not (tmp_path / "fixture-week").exists()


def test_no_row_at_or_after_holdout(tmp_path):
    # Property 10: nothing in the snapshot opens at or after the hold-out start.
    path = export(tmp_path)
    holdout = datetime(2026, 10, 2, tzinfo=UTC)
    files = sorted(path.glob("*.parquet"))
    assert files
    for file in files:
        times = pq.read_table(file).column("time").to_pylist()
        assert times and max(times) < holdout, file.name


def test_manifest_records_inputs(tmp_path):
    path = export(tmp_path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "fixture-week"
    assert (manifest["profile"], manifest["venue"], manifest["source"]) == ("metaquotes-demo", "mt5", "mt5")
    assert manifest["instruments"] == ["EURUSD", "XAUUSD"]
    assert (manifest["start"], manifest["end"]) == ("2026-09-29", "2026-10-02")
    assert (manifest["study"], manifest["holdout_start"]) == ("golden", "2026-10-02")
    assert manifest["candle_counts"] == {"M15": 60, "H4": 30, "D1": 20, "W1": 8}
    assert manifest["strategy"] == json.loads(json.dumps(CFG.model_dump(mode="json")))
    assert manifest["server_clock"] == "ny_close" and manifest["max_gap_minutes"] == 30
    assert manifest["spec_source"] == "fixture specs"
    assert manifest["git_commit"] == "c" * 40
    assert manifest["created_at"] == CREATED.isoformat()
    for instrument in ("EURUSD", "XAUUSD"):
        entry = manifest["data"][instrument]
        fp = direct(instrument).fingerprint
        assert (entry["rows"], entry["sha256"]) == (fp.rows, fp.sha256)
        assert entry["coverage_problems"] == list(direct(instrument).coverage.problems)
        assert entry["warmup_source"] == direct(instrument).warmup_source
        assert sum(entry["files"].values()) >= fp.rows


def test_existing_snapshot_never_overwritten(tmp_path):
    export(tmp_path)
    with pytest.raises(SnapshotError, match="already exists"):
        export(tmp_path)


def test_changed_snapshot_refused(tmp_path):
    path = export(tmp_path)
    file = path / "XAUUSD_M1.parquet"
    table = pq.read_table(file)
    close = table.column("close").to_pylist()
    close[100] += 0.01                                             # one edited price
    pq.write_table(table.set_column(table.schema.get_field_index("close"), "close", pa.array(close)), file)
    with pytest.raises(SnapshotError, match="XAUUSD"):
        load_snapshot(path)
    load_snapshot(path, instruments=("EURUSD",))                   # the other instrument still loads


def test_missing_snapshot_names_the_export_command(tmp_path):
    with pytest.raises(SnapshotError, match="python -m algo_research snapshot"):
        load_snapshot(tmp_path / "nope")


# ── the snapshot command ─────────────────────────────────────────────────────

def fixture_root(tmp_path: Path, confirm_end: str = "2026-10-02") -> Path:
    """A repository root whose research.toml covers the fixture week."""
    (tmp_path / "config" / "research").mkdir(parents=True)
    (tmp_path / "config" / "research" / "research.toml").write_text(f"""
profile = "metaquotes-demo"
study = "golden"
instruments = ["EURUSD", "XAUUSD"]
start = 2026-09-29
snapshot = "fixture-week"

[slices]
explore = [2026-09-29, 2026-10-01]
confirm = [2026-10-01, {confirm_end}]
""", encoding="utf-8")
    (tmp_path / "config" / "backtests" / "studies").mkdir(parents=True)
    (tmp_path / "config" / "backtests" / "studies" / "golden.toml").write_text(
        "holdout_start = 2026-10-02\ncreated_from_data_end = 2027-01-01\n", encoding="utf-8")
    (tmp_path / "config" / "backtests" / "base.toml").write_text("""
[run]
profile = "metaquotes-demo"
instruments = ["EURUSD", "XAUUSD"]
start = 2026-09-29
end = 2026-10-02
study = "golden"

[strategy]
entry_tf = "M15"
context_tfs = ["H4"]
candle_counts = { M15 = 60, H4 = 30, D1 = 20, W1 = 8 }

[data]
max_gap_minutes = 30
""", encoding="utf-8")
    return tmp_path


def test_snapshot_command(tmp_path, capsys):
    from algo_research.cli import main

    root = fixture_root(tmp_path / "repo")
    code = main(["snapshot"], source_factory=lambda profile: MultiFixtureSource(), root=root,
                snapshots_dir=tmp_path / "snapshots")
    assert code == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert "EURUSD:" in out and "XAUUSD:" in out
    snapshot = load_snapshot(tmp_path / "snapshots" / "fixture-week")
    assert snapshot.manifest["profile"] == "metaquotes-demo"
    assert snapshot.data["EURUSD"].fingerprint == direct("EURUSD").fingerprint

    # A second export under the same name is refused; another name is fine.
    assert main(["snapshot"], source_factory=lambda profile: MultiFixtureSource(), root=root,
                snapshots_dir=tmp_path / "snapshots") == 2
    assert "already exists" in capsys.readouterr().out
