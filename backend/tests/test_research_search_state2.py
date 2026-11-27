"""
Tests for algo_research/search_state2.py — H-Z, the weekly state widened (docs/research/SEARCH_2018_2024.md).
Hand-made bars only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_state2 import _Frame2, _smt, macro_table, state_table2, widen, FEATURES, PARTNER


def frame(ohlc):
    b = pd.DataFrame(ohlc, columns=["open", "high", "low", "close"], dtype=float)
    b["last"] = pd.bdate_range("2020-01-06", periods=len(b))
    return _Frame2(b, "D1")


# a swing high at 12 (bar 2), then a down run (bars 3-5, first open 11.6), closed through at bar 6 (a bullish CISD and
# order block of the run's bodies), then a close above 12 at bar 7 (a bullish break)
BARS = [(10, 10.5, 9.5, 10.2), (10.2, 11, 10, 10.8), (10.8, 12, 10.6, 11.6), (11.6, 11.8, 11, 11.5),
        (11.5, 11.6, 10.4, 10.6), (10.6, 10.8, 9.9, 10.0), (10.0, 11.9, 9.95, 11.8), (11.8, 12.6, 11.7, 12.4),
        (12.4, 12.7, 12.0, 12.5)] * 3


def test_breaks_cisds_and_the_cisd_rules_order_blocks():
    f = frame(BARS)
    assert f.bos_side[7] == 1 and f.bos_at[7] == 7                 # bar 7 closes above the swing high at 12
    assert f.cisd_side[6] == 1 and f.cisd_at[6] == 6               # bar 6 closes above the down run's first open 11.6
    k = np.nonzero(f.ob_k == 6)[0][0]
    assert (f.ob_lo[k], f.ob_hi[k], f.ob_side[k]) == (10.0, 11.6, 1)   # the run's bodies
    r = f.read(8, 12.5)
    assert np.isclose(r["ob_dn"], min(10.0, (12.5 - 10.8) / f.mean[8])) and r["bos"] == 1 and r["cisd"] in (1, -1)


def test_a_filled_gap_becomes_an_inversion_of_the_other_side():
    f = frame([(10, 10.5, 9.8, 10.4), (10.4, 11.5, 10.3, 11.4), (11.4, 12, 11.0, 11.9), (11.9, 12.0, 10.2, 10.3),
               (10.3, 10.6, 10.1, 10.5)] * 5)
    # bar 2's low 11.0 above bar 0's high 10.5: a bullish gap 10.5-11.0, closed through below 10.5 at bar 3
    k = np.nonzero((f.iv_lo == 10.5) & (f.iv_hi == 11.0))[0]
    assert len(k) and f.iv_side[k[0]] == -1 and f.iv_k[k[0]] == 3


def test_smt_is_a_low_or_high_the_partner_didnt_confirm():
    one, zero = np.array([1.0]), np.array([0.0])
    assert _smt(zero, one, zero, zero, False)[0] == 1                 # my low taken, the partner's not: bullish
    assert _smt(one, zero, zero, zero, False)[0] == -1                # my high taken alone: bearish
    assert _smt(one, zero, one, zero, False)[0] == 0                  # confirmed
    assert _smt(one, zero, zero, one, True)[0] == 0                   # apart: the partner's low confirms my high


def test_the_macro_state_is_last_weeks_closes_read_at_this_weeks_open(tmp_path):
    dates = pd.bdate_range("2019-01-07", periods=400)
    for name, base in (("TNX", 2.0), ("IRX", 1.0), ("VIX", 15.0)):
        pd.DataFrame({"date": dates, "close": base + np.arange(400) * 0.01}).to_parquet(tmp_path / f"{name}_D1.parquet")
    m = macro_table(tmp_path)
    row = m[m["week"] == pd.Timestamp("2019-03-04")].iloc[0]          # reads the week of 25 Feb, back to 28 Jan
    fri = list(dates).index(pd.Timestamp("2019-03-01"))
    assert np.isclose(row["curve"], 1.0) and np.isclose(row["y10_chg4w"], 20 * 0.01)
    assert fri == 39


def test_the_widened_table_joins_the_dollar_partner_and_macro():
    rng = np.random.default_rng(2)

    def days(seed):
        r = np.random.default_rng(seed)
        d = pd.bdate_range("2000-01-03", periods=1800)
        o = 100 + r.normal(0, 1, 1800).cumsum()
        c = o + r.normal(0, 0.8, 1800)
        return pd.DataFrame({"date": d, "open": o, "close": c, "high": np.maximum(o, c) + r.uniform(0.1, 1, 1800),
                             "low": np.minimum(o, c) - r.uniform(0.1, 1, 1800)})

    tables = {m: state_table2(m, days(i)) for i, m in enumerate(PARTNER)}
    macro = pd.DataFrame({"week": tables["DXY"]["week"], "y10_chg4w": 0.1, "curve": 1.5, "curve_chg4w": -0.2,
                          "vix_pct": 0.4, "vix_chg4w": 0.05})
    t = widen(tables, macro)
    assert set(FEATURES) <= set(t.columns) and t[list(FEATURES)].notna().all().all()
    eur = t[t["market"] == "EURUSD"].iloc[60]
    dxy = tables["DXY"].set_index("week").loc[eur["week"]]
    assert eur["dxy_w1_body"] == dxy["W1_body"] and eur["curve"] == 1.5
    assert rng is not None


def test_a_live_widened_state_matches_the_table_and_reads_nothing_from_its_week_on():
    from algo_research.search_state2 import own_state2_at

    r = np.random.default_rng(7)
    d = pd.bdate_range("2003-01-06", periods=1500)
    o = 100 + r.normal(0, 1, 1500).cumsum()
    c = o + r.normal(0, 0.8, 1500)
    days = pd.DataFrame({"date": d, "open": o, "close": c, "high": np.maximum(o, c) + r.uniform(0.1, 1, 1500),
                         "low": np.minimum(o, c) - r.uniform(0.1, 1, 1500)})
    table = state_table2("X", days)
    own = [f for f in FEATURES if f in table.columns] + ["took_hi", "took_lo", "mn_took_hi", "mn_took_lo", "w1_ret"]
    for i in (4, 33, 70):
        row = table.iloc[-i]
        live, provisional = own_state2_at("X", days, row["week"])
        assert not provisional
        assert np.allclose([live[f] for f in own], row[own].to_numpy(float))
