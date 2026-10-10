"""
Tests for algo_research/features/partner.py — each row's correlated partner at
the same t, for SMT divergence (update 2026-10c).

Task 264 (.kiro/specs/algo-research/tasks.md). Hand-made M1 paths for two
instruments, through the real feature code.
Validates: Requirement 16.2 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from algo_research.events import FEATURE_NAMES
from algo_research.features.market import market_features
from algo_research.features.partner import PARTNER_COLUMNS, partner_features
from tests.research_fixtures import Path, crt_path, grid_for, ny

PAIR = (("EURUSD", "GBPUSD"),)


def asia(path: Path) -> Path:
    """The Asian range of Monday 2026-01-05: 1.0950-1.1060 (Sunday 20:00-23:00 New York)."""
    return path.bar(ny(2026, 1, 4, 21, 30), h=1.1060).bar(ny(2026, 1, 4, 22, 10), lo=1.0950)


def tables(paths: dict, pairs=PAIR) -> dict[str, pd.DataFrame]:
    markets = {}
    for name, path in paths.items():
        frame = path.frame(name)
        markets[name] = market_features(frame, grid_for(frame, date(2026, 1, 5), date(2026, 1, 6)))
    out = partner_features(markets, pairs)
    for name in paths:
        assert list(out[name].index) == list(markets[name].index)
        assert out[name].drop(columns=list(PARTNER_COLUMNS)).equals(markets[name])   # nothing else changes
    return {name: table.set_index("t") for name, table in out.items()}


def at(table: pd.DataFrame, t) -> pd.Series:
    return table.loc[pd.Timestamp(t)]


def test_columns_documented_and_readable_by_where():
    assert set(PARTNER_COLUMNS) <= FEATURE_NAMES
    for name, column in PARTNER_COLUMNS.items():
        assert column.definition and column.unit and column.known_at, name


def test_partner_asia_raids_at_the_same_t():
    eur = asia(Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17))).bar(ny(2026, 1, 5, 2, 0), lo=1.0940)   # EURUSD raids
    gbp = asia(Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17))).bar(ny(2026, 1, 5, 4, 0), h=1.1070)    # GBPUSD, later
    t = tables({"EURUSD": eur, "GBPUSD": gbp})
    e, g = t["EURUSD"], t["GBPUSD"]
    assert at(e, ny(2026, 1, 5, 2, 15))["partner"] == "GBPUSD" and at(g, ny(2026, 1, 5, 2, 15))["partner"] == "EURUSD"
    assert at(g, ny(2026, 1, 5, 2, 0))["partner_asia_low_raided"] == False    # noqa: E712 - the 02:00 bar hasn't closed
    assert at(g, ny(2026, 1, 5, 2, 15))["partner_asia_low_raided"] == True    # noqa: E712
    assert at(e, ny(2026, 1, 5, 2, 15))["partner_asia_low_raided"] == False   # noqa: E712 - GBPUSD held its low
    assert at(e, ny(2026, 1, 5, 4, 15))["partner_asia_high_raided"] == True   # noqa: E712
    assert pd.isna(at(e, ny(2026, 1, 4, 23, 45))["partner_asia_low_raided"])  # the range is known from midnight
    # Every row: the partner's own fact at the same t.
    for t_ in e.index:
        theirs = g.loc[t_]
        expected = pd.NA if pd.isna(theirs["asia_low"]) else pd.notna(theirs["asia_low_raided_at"])
        got = e.loc[t_, "partner_asia_low_raided"]
        assert (pd.isna(got) and pd.isna(expected)) or got == expected, t_


def test_partner_crt_sweeps_of_the_same_candle():
    t = tables({"EURUSD": crt_path(), "GBPUSD": Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17))})
    e, g = t["EURUSD"], t["GBPUSD"]
    nine = ny(2026, 1, 5, 9, 0)                                        # EURUSD's 05:00 H4 swept its C1's low
    assert at(g, nine)["partner_crt_h4_swept_low"] == True             # noqa: E712
    assert at(g, nine)["partner_crt_h4_swept_high"] == False           # noqa: E712
    assert at(e, nine)["partner_crt_h4_swept_low"] == False            # noqa: E712 - GBPUSD's didn't: SMT
    assert at(g, ny(2026, 1, 5, 3, 0))["partner_crt_h1_swept_high"] == True   # noqa: E712


def test_null_without_a_partner_row_or_with_a_different_candle():
    gbp = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17)).drop(ny(2026, 1, 5, 6, 0), ny(2026, 1, 5, 7, 0))
    e = tables({"EURUSD": crt_path(), "GBPUSD": gbp})["EURUSD"]
    assert e.loc[pd.Timestamp(ny(2026, 1, 5, 6, 30)), list(PARTNER_COLUMNS)[1:]].isna().all()   # no GBPUSD row
    row = at(e, ny(2026, 1, 5, 7, 15))           # GBPUSD's last H1 is 05:00's, EURUSD's 06:00's
    assert pd.isna(row["partner_crt_h1_swept_low"]) and pd.notna(row["partner_crt_h4_swept_low"])


def test_null_without_a_partner():
    t = tables({"EURUSD": crt_path(), "XAUUSD": crt_path()}, pairs=())
    for table in t.values():
        assert table[list(PARTNER_COLUMNS)].isna().all().all()
