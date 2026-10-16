"""The economic calendar's history (algo-research update 2026-10i, Requirement 29).

The MetaTrader 5 terminal holds MetaQuotes' economic calendar, which the Python package can't read. The MQL5
script ``scripts/mql5/AgenticCalendarExport.mq5`` exports it once, to a CSV in the terminal's common folder.
This module imports that file, freezes it like a snapshot, and gives each instrument its releases.

    python -m algo_research calendar --import <export.csv> [--name mt5-calendar]

- **Times:** the calendar runs on the trade server's clock. Each row carries the server's offset from UTC at
  export, and the import subtracts it (Exness runs at +0).
- **Values:** blanks are nulls, the rest are numbers. A value exported twice is kept once.
- **The store:** ``data/research/calendar/<name>.parquet`` and ``<name>.json``, a manifest with the rows, a
  sha256, the period, the currencies and the source. Loading refuses data that no longer matches it.
- **Releases** (AR-D34 to AR-D36): only exact-time events are releases. Whole-day, timeless and tentative ones
  are kept for counting.

Validates: Requirement 29 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

__all__ = ["COLUMNS", "CalendarError", "import_calendar", "load_calendar", "releases", "write_calendar"]

COLUMNS = ["time", "currency", "country", "event", "importance", "time_mode", "actual", "forecast", "previous",
           "revised", "unit", "multiplier", "value_id", "event_id"]
_NUMBERS = ("actual", "forecast", "previous", "revised")
_TEXT = ("currency", "country", "event", "importance", "time_mode", "unit", "multiplier")


class CalendarError(RuntimeError):
    """A calendar store that is missing or no longer matches its manifest."""


def import_calendar(path: str | Path) -> pd.DataFrame:
    """The MQL5 export at ``path`` as a table in UTC, one row per calendar value, oldest first. The script writes
    with FILE_ANSI, the system code page (cp1252 here), so a file that isn't UTF-8 is read as cp1252."""
    try:
        raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    except UnicodeDecodeError:
        raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="cp1252")
    server = pd.to_datetime(raw["time_server"], format="%Y.%m.%d %H:%M:%S")
    offset = pd.to_timedelta(pd.to_numeric(raw["server_offset_s"]), unit="s")
    table = pd.DataFrame({"time": (server - offset).dt.tz_localize("UTC")})
    for column in _TEXT:
        table[column] = raw[column].str.strip()
    for column in _NUMBERS:
        table[column] = pd.to_numeric(raw[column].replace("", None), errors="coerce").astype(float)
    table["value_id"] = pd.to_numeric(raw["value_id"]).astype("int64")
    table["event_id"] = pd.to_numeric(raw["event_id"]).astype("int64")
    table = table.drop_duplicates("value_id", keep="last")
    return table.sort_values(["time", "value_id"], kind="stable").reset_index(drop=True)[COLUMNS]


def _sha256(table: pd.DataFrame) -> str:
    return hashlib.sha256(table[COLUMNS].to_csv(index=False).encode("utf-8")).hexdigest()


def write_calendar(table: pd.DataFrame, directory: str | Path, name: str, source: str) -> dict:
    """Write ``<directory>/<name>.parquet`` and its manifest; returns the manifest."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    table = table[COLUMNS].reset_index(drop=True)
    table.to_parquet(directory / f"{name}.parquet", index=False)
    manifest = {
        "name": name, "rows": len(table), "sha256": _sha256(table),
        "first": table["time"].min().isoformat() if len(table) else None,
        "last": table["time"].max().isoformat() if len(table) else None,
        "currencies": sorted(table["currency"].unique().tolist()), "source": source,
    }
    (directory / f"{name}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_calendar(directory: str | Path, name: str) -> pd.DataFrame:
    """The stored calendar, refused if it no longer matches its manifest."""
    directory = Path(directory)
    data, meta = directory / f"{name}.parquet", directory / f"{name}.json"
    if not data.is_file() or not meta.is_file():
        raise CalendarError(f"no calendar {name!r} in {directory}: import one with `python -m algo_research "
                            f"calendar --import <export.csv>`")
    table = pd.read_parquet(data)
    manifest = json.loads(meta.read_text(encoding="utf-8"))
    if (len(table), _sha256(table)) != (manifest["rows"], manifest["sha256"]):
        raise CalendarError(f"calendar {name!r} no longer matches its manifest; import it again")
    return table


def releases(table: pd.DataFrame, currencies: Iterable[str], importance: Iterable[str] = ("HIGH",),
             time_mode: Optional[str] = "DATETIME") -> pd.DatetimeIndex:
    """The sorted, distinct release times of exact-time events of ``currencies`` and ``importance``."""
    rows = table[table["currency"].isin(list(currencies)) & table["importance"].isin(list(importance))]
    if time_mode is not None:
        rows = rows[rows["time_mode"] == time_mode]
    return pd.DatetimeIndex(rows["time"].drop_duplicates().sort_values()).rename(None)
