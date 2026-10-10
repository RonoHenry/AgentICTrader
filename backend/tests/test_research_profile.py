"""
Tests for algo_research/profile.py — where each instrument makes its range:
per H4 candle, per New York hour, per weekday. Descriptive, no verdict.

Task 273 (.kiro/specs/algo-research/tasks.md). A hand-made week, Monday
2026-01-05 to Friday 2026-01-09, whose highs and lows are placed by hand.
Validates: Requirement 21.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.research_fixtures import Path, ny

WEEK = [date(2026, 1, 5) + timedelta(days=i) for i in range(5)]


def eurusd():
    """Every day: the high (1.1050) at 03:10 New York, in the 01:00 H4; the low (1.0950) at 10:20, in the 09:00 H4."""
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 9, 17), base=1.1000)
    for d in WEEK:
        path.bar(ny(d.year, d.month, d.day, 3, 10), h=1.1050).bar(ny(d.year, d.month, d.day, 10, 20), lo=1.0950)
    return path.frame("EURUSD")


def xauusd():
    """Every day: the high at 20:30 New York the evening before (the 17:00 H4); the low at 14:00 (the 13:00 H4)."""
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 9, 17), base=2000.0, wick=0.1)
    for d in WEEK:
        evening = ny(d.year, d.month, d.day, 20, 30) - timedelta(days=1)
        path.bar(evening, h=2010.0).bar(ny(d.year, d.month, d.day, 14, 0), lo=1990.0)
    return path.frame("XAUUSD")


def test_h4_ranges_and_shares():
    from algo_research.profile import instrument_profile

    p = instrument_profile(eurusd(), date(2026, 1, 5), date(2026, 1, 10))
    assert p.days == 5
    assert p.h4.loc[2, "median_range"] == pytest.approx(1.1050 - 1.0999)       # the 01:00 H4: high to the wick
    assert p.h4.loc[4, "median_range"] == pytest.approx(1.1001 - 1.0950)
    assert p.h4.loc[0, "median_range"] == pytest.approx(0.0002)
    assert p.h4.loc[2, "median_share"] == pytest.approx(0.0051 / 0.0100)
    assert p.h4.loc[0, "median_share"] == pytest.approx(0.0002 / 0.0100)


def test_hours_of_the_high_and_the_low():
    from algo_research.profile import instrument_profile

    eur = instrument_profile(eurusd(), date(2026, 1, 5), date(2026, 1, 10))
    assert eur.hours.loc[3, "high_share"] == 1.0 and eur.hours.loc[10, "low_share"] == 1.0
    assert eur.hours["high_share"].sum() == pytest.approx(1.0) and eur.hours["low_share"].sum() == pytest.approx(1.0)
    gold = instrument_profile(xauusd(), date(2026, 1, 5), date(2026, 1, 10))
    assert gold.hours.loc[20, "high_share"] == 1.0 and gold.hours.loc[14, "low_share"] == 1.0


def test_weekday_split():
    from algo_research.profile import instrument_profile

    p = instrument_profile(eurusd(), date(2026, 1, 5), date(2026, 1, 10))
    assert list(p.weekdays.index) == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    assert (p.weekdays["days"] == 1).all()
    assert p.weekdays["median_range"].to_numpy() == pytest.approx([0.0100] * 5)
    assert (p.weekdays["high_h4"] == "01:00").all() and (p.weekdays["low_h4"] == "09:00").all()
    assert (p.weekdays["high_h4_share"] == 1.0).all()


def test_only_the_dates_asked_for():
    from algo_research.profile import instrument_profile

    p = instrument_profile(eurusd(), date(2026, 1, 6), date(2026, 1, 8))
    assert p.days == 2 and list(p.weekdays.index) == ["Tue", "Wed"]


def test_render_names_each_instrument_and_says_it_is_descriptive():
    from algo_research.profile import instrument_profile, render_profile

    profiles = [instrument_profile(f, date(2026, 1, 5), date(2026, 1, 10)) for f in (eurusd(), xauusd())]
    text = render_profile(profiles, {"snapshot": "hand-made", "slice": "explore 2026-01-05 to 2026-01-10",
                                     "code_commit": "0" * 40})
    assert text.startswith("# Volatility profile")
    for heading in ("## EURUSD", "## XAUUSD", "### By H4 candle", "### Hour of the day's high and low",
                    "### By weekday", "## Inputs"):
        assert heading in text, heading
    assert "no verdict" in text and "hand-made" in text


def test_lows_made_by_a_spread_blowout_are_flagged():
    # Prices are bid: at the 17:00 rollover the spread widens and the bid dips without anyone selling.
    # The profile reports the share of days whose low (high) formed on a spread of 5x typical or more.
    import numpy as np
    import pandas as pd

    from algo_research.frame import frame_from_arrays
    from algo_research.profile import instrument_profile, render_profile

    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 9, 17), base=1.1000)
    spread = np.full(len(path.times), 0.0001)
    for d in WEEK[:2]:                                    # Monday and Tuesday: the low is a rollover spike
        when = ny(d.year, d.month, d.day, 17, 2) - timedelta(days=1)
        path.bar(when, lo=1.0940)
        spread[path.index[when]] = 0.0015
    frame = frame_from_arrays("EURUSD", pd.DatetimeIndex(path.times), path.o, path.h, path.l, path.c, spread=spread,
                              typical_spread=0.0001, stop_slippage=0.0)
    p = instrument_profile(frame, date(2026, 1, 5), date(2026, 1, 10))
    assert p.spread_lows == pytest.approx(2 / 5) and p.spread_highs == 0.0
    text = render_profile([p], {"snapshot": "hand-made", "slice": "-", "code_commit": "0"})
    assert "40% of the days' lows" in text and "spread" in text
