"""
Tests for algo_research/search_state3.py, universe.py and fomc.py — H-AA, the brain on 41 markets with the flows
(docs/research/SEARCH_2018_2024.md). Hand-made bars and dates only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.fomc import STATEMENTS, statements
from algo_research.search_state3 import FEATURES, FLOWS, VOL, calendar_flows, money_flows
from algo_research.search_state2 import FEATURES as V2
from algo_research.universe import BROAD, EQUITY, first_clean, orientation


def test_the_fomc_list_has_eight_scheduled_statements_a_year():
    s = statements()
    assert s.is_monotonic_increasing and len(s) == len(STATEMENTS) == 29 * 8
    assert (s.to_series().dt.year.value_counts() == 8).all()
    assert pd.Timestamp("2020-03-18") in s and pd.Timestamp("2012-08-01") in s       # scheduled; the July 31-Aug 1


def test_calendar_flows_know_the_fomc_cycle_expiry_and_month_end():
    c = calendar_flows(pd.Series(pd.to_datetime(["2022-12-12", "2022-12-19", "2022-12-26", "2018-09-24",
                                                 "1990-01-08"]))).set_index("week")
    assert c.loc["2022-12-12", ["fomc_in_week", "fomc_cycle", "opex_week", "opex_quarter"]].tolist() == [1, 0, 1, 1]
    assert c.loc["2022-12-19", ["fomc_cycle", "fomc_even", "after_opex", "month_end_week"]].tolist() == [1, 0, 1, 0]
    assert c.loc["2022-12-26", ["fomc_cycle", "fomc_even", "month_end_week"]].tolist() == [2, 1, 1]
    assert c.loc["2018-09-24", ["fomc_in_week", "after_opex", "month_end_week"]].tolist() == [1, 1, 1]
    assert np.isnan(c.loc["1990-01-08", "fomc_cycle"])                               # before the list


def test_money_flows_read_last_weeks_closes_month_to_date(tmp_path):
    days = pd.bdate_range("2021-12-01", "2022-02-28")
    spx = pd.Series(np.linspace(100, 130, len(days)), index=days)
    tnx = pd.Series(np.linspace(1.5, 2.0, len(days)), index=days)
    for name, s in (("US500", spx), ("TNX", tnx), ("VIX", pd.Series(20.0, index=days))):
        pd.DataFrame({"date": days, "open": s.to_numpy(), "high": s.to_numpy() + 1, "low": s.to_numpy() - 1,
                      "close": s.to_numpy()}).to_parquet(tmp_path / f"{name}_D1.parquet")
    m = money_flows(tmp_path).set_index("week")
    friday = pd.Timestamp("2022-02-11")                                              # read at Monday 14 Feb
    jan_end = pd.Timestamp("2022-01-31")
    assert np.isclose(m.loc["2022-02-14", "eq_mtd"], spx[friday] / spx[jan_end] - 1)
    assert np.isclose(m.loc["2022-02-14", "bond_mtd"], -7.5 * (tnx[friday] - tnx[jan_end]) / 100)
    rv = float((100 * np.log(spx).diff()).pow(2).loc[:friday].tail(21).sum())
    assert np.isclose(m.loc["2022-02-14", "vrp"], 20.0 ** 2 / 12 - rv)


def test_the_clean_start_skips_years_whose_bars_carry_the_close_in_all_four():
    dates = pd.bdate_range("2000-01-03", periods=1200)
    rng = np.random.default_rng(0)
    c = 100 + rng.normal(0, 1, 1200).cumsum()
    o = c + rng.normal(0, 0.5, 1200)
    d = pd.DataFrame({"date": dates, "open": o, "high": np.maximum(o, c) + 0.3, "low": np.minimum(o, c) - 0.3,
                      "close": c})
    d.loc[:399, ["open", "high", "low"]] = np.c_[c[:400], c[:400], c[:400]]          # flat until row 400
    # the first window that passes holds 12 flat days (under 5% of 250); the high = low filter drops them later
    assert first_clean(d) == dates[400 - 12]


def test_the_universe_and_features():
    assert len(BROAD) == 35 and set(FEATURES) == set(V2) | set(FLOWS) | set(VOL)
    assert orientation("EURUSD") == (-1.0, 0.0) and orientation("USDJPY") == (1.0, 0.0)
    assert orientation("JP225") == (0.0, 1.0) and orientation("UST10") == (0.0, 0.0) and "US500" in EQUITY
