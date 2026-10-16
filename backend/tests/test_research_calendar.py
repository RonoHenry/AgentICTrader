"""
Tests for algo_research/calendar.py — the economic calendar's history (algo-research update 2026-10i).

Task 327 (.kiro/specs/algo-research/tasks.md). A hand-written export in the MQL5 script's format.
Validates: Requirement 29 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from algo_research.calendar import CalendarError, import_calendar, load_calendar, releases, write_calendar

HEADER = ("value_id,event_id,time_server,server_offset_s,currency,country,event,importance,time_mode,actual,"
          "forecast,previous,revised,unit,multiplier")
ROWS = [
    "101,9001,2025.01.10 13:30:00,0,USD,US,Nonfarm Payrolls,HIGH,DATETIME,256,165,212,,people,THOUSANDS",
    "102,9002,2025.01.15 13:30:00,0,USD,US,CPI m/m,HIGH,DATETIME,0.4,0.3,0.3,0.3,%,NONE",
    "103,9003,2025.01.15 00:00:00,0,EUR,EU,Bank Holiday,NONE,DATE,,,,,,NONE",
    "104,9004,2025.01.16 12:00:00,10800,GBP,GB,GDP m/m,MODERATE,DATETIME,0.1,0.2,-0.1,,%,NONE",
    "101,9001,2025.01.10 13:30:00,0,USD,US,Nonfarm Payrolls,HIGH,DATETIME,256,165,212,,people,THOUSANDS",
    "105,9005,2025.01.14 13:30:00,0,USD,US,PPI m/m,HIGH,TENTATIVE,,0.3,0.4,,%,NONE",
]


def export(tmp_path, rows=ROWS):
    path = tmp_path / "agentic_calendar.csv"
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def test_the_import_gives_utc_times_numbers_and_one_row_per_value(tmp_path):
    table = import_calendar(export(tmp_path))
    assert list(table["value_id"]) == [101, 105, 103, 102, 104]               # sorted by time, the duplicate gone
    gdp = table.set_index("value_id").loc[104]
    assert gdp["time"] == pd.Timestamp("2025-01-16 09:00", tz="UTC")          # a server at UTC+3
    nfp = table.set_index("value_id").loc[101]
    assert nfp["time"] == pd.Timestamp("2025-01-10 13:30", tz="UTC")
    assert (nfp["actual"], nfp["forecast"], nfp["previous"]) == (256.0, 165.0, 212.0)
    assert np.isnan(nfp["revised"]) and np.isnan(table.set_index("value_id").loc[103, "actual"])
    assert (nfp["importance"], nfp["time_mode"], nfp["currency"]) == ("HIGH", "DATETIME", "USD")


def test_the_store_is_fingerprinted_and_refuses_changed_data(tmp_path):
    table = import_calendar(export(tmp_path))
    manifest = write_calendar(table, tmp_path / "calendar", "mt5", source="ExnessKE-MT5Trial9")
    assert manifest["rows"] == 5 and manifest["currencies"] == ["EUR", "GBP", "USD"]
    assert (manifest["first"], manifest["last"]) == ("2025-01-10T13:30:00+00:00", "2025-01-16T09:00:00+00:00")
    again = load_calendar(tmp_path / "calendar", "mt5")
    pd.testing.assert_frame_equal(again, table)
    other = write_calendar(table.iloc[:4], tmp_path / "other", "mt5", source="x")
    assert other["sha256"] != manifest["sha256"]
    meta = tmp_path / "calendar" / "mt5.json"
    tampered = json.loads(meta.read_text(encoding="utf-8")) | {"sha256": "0" * 64}
    meta.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(CalendarError, match="no longer matches"):
        load_calendar(tmp_path / "calendar", "mt5")


def test_releases_are_exact_time_rows_of_the_currencies_and_importance(tmp_path):
    table = import_calendar(export(tmp_path))
    usd = releases(table, ["USD"])
    assert list(usd) == [pd.Timestamp("2025-01-10 13:30", tz="UTC"), pd.Timestamp("2025-01-15 13:30", tz="UTC")]
    # The tentative PPI and the all-day holiday have no exact time; GDP is moderate.
    assert list(releases(table, ["USD", "EUR", "GBP"], importance=("HIGH", "MODERATE")))[-1] == pd.Timestamp(
        "2025-01-16 09:00", tz="UTC")
    assert releases(table, ["JPY"]).empty


def test_the_calendar_command_imports_an_export(tmp_path, capsys):
    from algo_research.cli import main
    from tests.test_research_snapshot import fixture_root

    root = fixture_root(tmp_path / "root")
    assert main(["calendar", "--import", str(export(tmp_path)), "--name", "mt5"], root=root) == 0
    assert (root / "data" / "research" / "calendar" / "mt5.parquet").is_file()
    out = capsys.readouterr().out
    assert "5 values" in out and "USD" in out
