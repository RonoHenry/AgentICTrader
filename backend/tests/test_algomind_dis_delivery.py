"""
Tests for AlgoMindDIS's delivery, time and volatility (algomind-dis Requirements 7, 8; task 402).
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from algo_research.phases import label_phases
from algomind_dis.analyzers.context import ny_hours, time_context, volatility_context
from algomind_dis.analyzers.delivery import delivery, sequences
from liquidity_engine.context.frame_state import Candles
from tests.test_algomind_dis_objectives import OHLC, ohlc
from tests.test_algomind_dis_structure import DAY, cut


def test_a_sweep_a_displacement_and_a_cisd_deliver_until_a_close_beyond_the_sweep():
    c = ohlc(OHLC)                         # candle 8 sweeps the low of candle 4; candle 9 displaces and closes
    d = delivery(c)                        # above 16.5, the open of the down run (6-7) that delivered the sweep
    assert (d.state, d.since) == ("BULLISH_DELIVERY", c.end[9])
    assert any("14.6" in e for e in d.evidence) and any("16.5" in e for e in d.evidence)
    broken = ohlc(OHLC + [(17.2, 17.4, 14.0, 14.2)])           # a close under the sweep's low ends it
    assert delivery(broken).state != "BULLISH_DELIVERY"


def test_a_sweep_and_displacement_without_a_cisd_is_transitional():
    rows = OHLC[:9] + [(15.0, 16.4, 14.9, 16.3)]               # a big up body that stays under 16.5
    assert delivery(ohlc(rows)).state == "TRANSITIONAL"
    assert delivery(ohlc(OHLC[:9])).state in ("UNCONFIRMED", "CONSOLIDATION")   # the sweep alone: not yet


def test_a_tight_box_is_consolidation():
    rng = np.random.default_rng(3)
    wide = 100 + np.cumsum(rng.normal(0, 1, 30))
    rows = [(x, x + 1.5, x - 1.5, x + 0.2) for x in wide]
    last = float(wide[-1]) + 0.2
    rows += [(last, last + 0.05, last - 0.05, last + 0.01 * (k % 2)) for k in range(10)]
    c = ohlc(rows)
    assert label_phases(c.o, c.h, c.l, c.c)[-1] == "consolidation"
    assert delivery(c).state == "CONSOLIDATION"


def test_delivery_at_a_cut_is_the_full_frames_read_up_to_it():
    c = ohlc(OHLC + [(17.2, 17.4, 14.0, 14.2), (14.2, 14.5, 13.0, 13.3), (13.3, 15.5, 13.2, 15.4)])
    seqs, labels = sequences(c), label_phases(c.o, c.h, c.l, c.c)
    for n in range(3, len(c) + 1):
        k = cut(c, n)
        assert delivery(k) == delivery(k, seqs=seqs, labels=labels), n


def test_mirrored_bars_deliver_the_other_way():
    c = ohlc(OHLC)
    m = Candles("D1", c.t, c.end, -c.o, -c.l, -c.h, -c.c)
    assert (delivery(m).state, delivery(m).since) == ("BEARISH_DELIVERY", c.end[9])


def test_time_is_read_in_new_york_across_the_clocks_change_and_news_has_no_side():
    days = pd.date_range("2026-10-26", "2026-11-13", freq="B")
    n = len(days)
    t = days.tz_localize("UTC").as_unit("ns").asi8
    x = np.linspace(100, 110, n)
    d1 = Candles("D1", t, t + DAY, x, x + 1, x - 1, x + 0.5)
    k = int(np.searchsorted(t, pd.Timestamp("2026-11-03", tz="UTC").value))    # Tuesday 3 Nov has closed
    sub = Candles("D1", d1.t[:k + 1], d1.end[:k + 1], d1.o[:k + 1], d1.h[:k + 1], d1.l[:k + 1], d1.c[:k + 1])
    tc = time_context(sub, calendar=lambda when: ["USD CPI 08:30 New York"])
    assert tc.weekday == "Tuesday" and tc.week_of_month == 1 and tc.first_two_weeks
    assert tc.week_open == d1.o[k - 1] and tc.month_open == d1.o[k - 1]        # Monday 2 Nov opens both
    assert tc.scheduled == ("USD CPI 08:30 New York",)
    assert "direction" not in {f.name for f in dataclasses.fields(tc)}
    assert ny_hours(pd.Timestamp("2026-10-30 13:30", tz="UTC")) == 9.5         # EDT, before the change
    assert ny_hours(pd.Timestamp("2026-11-03 14:30", tz="UTC")) == 9.5         # EST, after it
    v = volatility_context(sub)
    assert v.adr == 2.0 and v.last_ratio == 1.0 and not v.expanding
