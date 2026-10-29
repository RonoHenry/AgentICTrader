"""
Tests for algo_research/search_cisd.py — H-S, the higher-timeframe CISD as the trend
(docs/research/SEARCH_2018_2024.md). Synthetic candles only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from algo_research.search_cisd import bias_calls, cisd_events, trend_of
from liquidity_engine.detectors.internal import PDArrayDetector
from liquidity_engine.models import BiasDirection, Candle, PDArrayType, Timeframe

T0 = datetime(2022, 3, 7, 22, tzinfo=timezone.utc)
HOUR = 3_600 * 10**9
SERIES = [(1.050, 1.060, 1.040, 1.045), (1.045, 1.046, 1.020, 1.025), (1.025, 1.040, 1.022, 1.038),
          (1.038, 1.042, 1.030, 1.032), (1.032, 1.034, 1.010, 1.015), (1.015, 1.030, 1.012, 1.028),
          (1.028, 1.060, 1.027, 1.055), (1.055, 1.070, 1.045, 1.065)]       # the engine's Requirement 31 series


def bars(rows, step=HOUR):
    t0 = pd.DatetimeIndex([T0]).as_unit("ns").asi8[0]
    return pd.DataFrame([{"open": o, "high": h, "low": l, "close": c, "t_open": t0 + k * step,
                          "t_close": t0 + (k + 1) * step, "date": pd.Timestamp("2022-03-08") + pd.Timedelta(days=k)}
                         for k, (o, h, l, c) in enumerate(rows)])


def test_the_cisd_is_the_engines_order_block_known_at_its_close_through():
    b = bars(SERIES)
    e = cisd_events(b, "H1")
    (bull,) = e[e["side"] > 0].itertuples()
    assert bull.known == b["t_close"].iat[6] and bull.swept and bull.imbalance
    assert bull.known_hp == b["t_close"].iat[7] and bull.extreme == 1.010 and bull.price == 1.055
    candles = [Candle(timestamp=T0 + timedelta(hours=k), open=o, high=h, low=l, close=c, timeframe=Timeframe.H1,
                      instrument="X") for k, (o, h, l, c) in enumerate(SERIES)]
    (ob,) = [a for a in PDArrayDetector("gap", "cisd").detect({Timeframe.H1: candles}, {})
             if a.array_type == PDArrayType.OB and a.direction == BiasDirection.BULLISH]
    assert ob.formed_at == T0 + timedelta(hours=6) and ob.high_probability is True     # the same block, from its open
    assert list(trend_of(e, "high_prob")["known"]) == [b["t_close"].iat[7]]


def test_a_bias_call_reads_the_d1_close_its_horizon_later_against_the_drift():
    d1 = bars([(10, 11, 9, 10), (10, 12, 9.5, 11), (11, 13, 10.5, 12), (12, 12.5, 10, 10.5), (10.5, 11, 10, 10.8)],
              step=24 * HOUR)
    m1 = pd.DataFrame({"time": pd.to_datetime(d1["t_open"], utc=True), "low": d1["low"], "high": d1["high"]})
    event = pd.DataFrame([{"known": d1["t_open"].iat[1] + HOUR, "side": 1, "price": 10.2, "extreme": 9.0}])
    calls = bias_calls(event, d1, m1, horizon=2, since=0, until=int(d1["t_close"].iat[-1]))
    (c,) = calls.itertuples()
    assert c.hit is True                                            # its day is day 1; day 3 closes at 10.5 > 10.2
    # moves over two days from each close: 12-10 up, 10.5-11 down, 10.8-12 down: a third go up
    assert np.isclose(c.base, 1 / 3) and c.held                    # the 9.0 low was never traded through
