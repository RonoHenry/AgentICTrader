"""
Tests for the Thesis Engine's clock (thesis-engine Requirement 2, TE-D3, TE-D11, TE-D17; task 410).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from liquidity_engine.context.frame_state import Candles
from thesis_engine.clock import clean, frames, in_window, stale, trading_day

NY = "America/New_York"


def bars(start_ny: str, minutes: int, step: int = 1, price: float = 100.0) -> pd.DataFrame:
    t = pd.date_range(pd.Timestamp(start_ny, tz=NY), periods=minutes // step, freq=f"{step}min").tz_convert("UTC")
    p = price + np.arange(len(t)) * 0.001
    return pd.DataFrame({"time": t, "open": p, "high": p + 0.01, "low": p - 0.01, "close": p + 0.0005,
                         "spread": 0.0001})


def ny(ns: int) -> str:
    return pd.Timestamp(int(ns), tz="UTC").tz_convert(NY).strftime("%a %Y-%m-%d %H:%M")


def test_the_day_opens_at_17_for_fx_and_18_for_the_indices():
    week = bars("2022-03-13 17:00", 5 * 24 * 60)                   # Sunday 17:00 to Friday 17:00 New York
    fx = frames(week, "EURUSD")["D1"]
    assert [ny(t) for t in fx.t[:2]] == ["Sun 2022-03-13 17:00", "Mon 2022-03-14 17:00"]
    assert ny(fx.end[0]) == "Mon 2022-03-14 17:00"
    index = frames(week, "US500")["D1"]
    assert ny(index.t[1]) == "Mon 2022-03-14 18:00" and ny(index.end[1]) == "Tue 2022-03-15 18:00"


def test_h4_opens_every_four_hours_from_the_days_open():
    day = bars("2022-03-14 17:00", 24 * 60)
    h4 = frames(day, "XAUUSD")["H4"]
    assert [pd.Timestamp(int(t), tz="UTC").tz_convert(NY).hour for t in h4.t] == [17, 21, 1, 5, 9, 13]
    h4i = frames(bars("2022-03-14 18:00", 24 * 60), "US100")["H4"]
    assert [pd.Timestamp(int(t), tz="UTC").tz_convert(NY).hour for t in h4i.t] == [18, 22, 2, 6, 10, 14]


def test_the_week_runs_from_sundays_open_to_fridays_close_and_a_forming_candle_is_left_out():
    two = bars("2022-03-13 17:00", 5 * 24 * 60)
    more = pd.concat([two, bars("2022-03-20 17:00", 24 * 60)])     # the next week's first day only
    w1 = frames(more, "EURUSD")["W1"]
    assert len(w1) == 1
    assert ny(w1.t[0]) == "Sun 2022-03-13 17:00" and ny(w1.end[0]) == "Fri 2022-03-18 17:00"
    d1 = frames(more, "EURUSD")["D1"]
    assert ny(d1.end[-1]) == "Mon 2022-03-21 17:00"
    cut = frames(more.iloc[:-30], "EURUSD")["D1"]                  # the last day stops 30 minutes short
    assert ny(cut.end[-1]) == "Fri 2022-03-18 17:00"


def test_candles_are_ordered_and_closed():
    fr = frames(bars("2022-03-13 17:00", 2 * 24 * 60), "GBPUSD")
    for tf, c in fr.items():
        assert isinstance(c, Candles) and c.tf == tf
        assert (np.diff(c.t) > 0).all() and (c.end > c.t).all()
        assert (c.h >= np.maximum(c.o, c.c)).all() and (c.l <= np.minimum(c.o, c.c)).all()


def test_a_repeated_or_older_bar_is_dropped_and_so_is_a_leading_stand_in():
    b = bars("2022-03-14 09:00", 10)
    stand_in = b.iloc[:1].assign(time=b["time"].iloc[0] - pd.Timedelta(hours=9))
    messy = pd.concat([stand_in, b.iloc[:5], b.iloc[3:4], b.iloc[5:], b.iloc[2:3]]).reset_index(drop=True)
    out, dropped = clean(messy)
    assert dropped == {"repeated_or_older": 2, "leading_stand_ins": 1}
    assert out["time"].tolist() == b["time"].tolist()


def test_the_window_and_the_trading_day():
    t = pd.DatetimeIndex([pd.Timestamp(x, tz=NY) for x in
                          ("2022-03-14 00:00", "2022-03-14 11:55", "2022-03-14 12:00", "2022-03-13 23:00",
                           "2022-03-19 09:00")]).tz_convert("UTC").asi8
    assert in_window(t).tolist() == [True, True, False, False, False]
    days = trading_day(t, "EURUSD")
    assert pd.Timestamp(days[3]).strftime("%a %d") == "Mon 14"       # Sunday evening opens Monday's day


def test_the_first_candle_after_a_silence_inside_the_day_is_stale():
    b = bars("2022-03-14 09:00", 60)
    quiet = pd.concat([b.iloc[:20], b.iloc[45:]])                    # 25 minutes without a bar
    e = frames(quiet, "EURUSD")["M5"]
    flags = stale(e, "EURUSD")
    assert flags.sum() == 1 and ny(e.t[np.flatnonzero(flags)[0]]) == "Mon 2022-03-14 09:45"
