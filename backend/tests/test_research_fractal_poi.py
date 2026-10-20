"""
Tests for algo_research/fractal_poi — the trader's Fractal + POI indicator, ported from Pine (algo-backtester
update 2026-10-19).

Tasks 333-336 (.kiro/specs/algo-backtester/tasks.md):
- the Fractal modes and candle boundaries;
- the model: one bearish setup built candle by candle, every value checked against the Pine rules;
- the HTF fair value gaps;
- the liquidity suite;
- Property 11: what is drawn at a clock is the same with or without the data after it.

Validates: Requirements 21.1-21.4, 22.1-22.2 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algo_research.fractal_poi import FractalPOI, FractalSettings, partners_for, warmup_days
from algo_research.fractal_poi.frames import (fractal_htf, fvg_auto, fvg_label, htf2_auto, htf_name, period_end,
                                               starts, valid_htf)
from algo_research.replay.timeframes import wall_seconds

NY = "America/New_York"


def w(text: str) -> int:
    """A New York wall-clock time as the charts' wall seconds."""
    return int(wall_seconds([pd.Timestamp(text, tz=NY)])[0])


def m1_from(candles: list[tuple], first: str, minutes: int = 15) -> pd.DataFrame:
    """M1 bars whose ``minutes``-minute candles are ``candles`` (open, high, low, close), from ``first`` (New York):
    each candle's first minute carries its range and the rest hold its close."""
    t0 = pd.Timestamp(first, tz=NY)
    rows = []
    for n, (o, h, l, c) in enumerate(candles):
        for m in range(minutes):
            t = t0 + pd.Timedelta(minutes=n * minutes + m)
            rows.append((t, o, h, l, c) if m == 0 else (t, c, c, c, c))
    frame = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close"])
    frame["time"] = frame["time"].dt.tz_convert("UTC")
    return frame


# ── frames ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_fractal_modes_pick_the_indicator_s_htf():
    auto = {"M1": "15", "M3": "30", "M5": "60", "M15": "240", "M30": "240", "H1": "1D", "H4": "1W", "D1": "1M",
            "W1": "3M", "MN1": "12M", "M2": "", "H3": ""}
    assert {tf: fractal_htf("Automatic", tf) for tf in auto} == auto
    assert fractal_htf("Intraday", "M1") == "15" and fractal_htf("Intraday", "M10") == "60"
    assert fractal_htf("Intraday", "H4") == "1D" and fractal_htf("Intraday", "D1") == "1W"
    assert fractal_htf("Scalp", "M1") == "5" and fractal_htf("Scalp", "M15") == "60" and fractal_htf("Scalp", "H1") == "240"
    assert fractal_htf("Swing", "M5") == "60" and fractal_htf("Swing", "H4") == "1W" and fractal_htf("Swing", "W1") == "1M"
    assert fractal_htf("Quarterly", "M1") == "SESSION_MICRO" and fractal_htf("Quarterly", "M5") == "SESSION_90"
    assert fractal_htf("Quarterly", "M30") == "SESSION_6H" and fractal_htf("Quarterly", "H1") == "1D"
    assert fractal_htf("Custom", "M5", "D") == "1D" and fractal_htf("15m-4H", "M1") == "240"
    assert htf2_auto("M15") == "1D" and htf2_auto("M5") == "240" and fvg_auto("M15") == "240" and fvg_auto("H1") == "1D"


def test_an_htf_must_be_a_whole_multiple_of_the_chart():
    assert valid_htf("240", "M15") and valid_htf("1D", "H4") and valid_htf("SESSION_MICRO", "M1")
    assert not valid_htf("", "M2") and not valid_htf("45", "M30") and not valid_htf("15", "H1")


def test_candles_start_where_a_tradingview_fx_chart_starts_them():
    def first(tf, *times):
        return [pd.Timestamp(int(x), unit="s").strftime("%a %H:%M") for x in starts(np.array([w(t) for t in times]), tf)]
    assert first("240", "2026-01-06 00:30", "2026-01-06 03:10", "2026-01-06 16:59") == ["Mon 21:00", "Tue 01:00", "Tue 13:00"]
    assert first("1D", "2026-01-06 16:59", "2026-01-06 17:00") == ["Mon 17:00", "Tue 17:00"]
    assert first("1W", "2026-01-08 10:00") == ["Sun 17:00"]
    assert first("1M", "2026-01-15 10:00") == ["Wed 17:00"]                      # the eve of Jan 1, 2026
    assert first("SESSION_6H", "2026-01-06 17:30", "2026-01-06 18:00", "2026-01-07 05:59") == ["Tue 12:00", "Tue 18:00", "Wed 00:00"]
    assert first("SESSION_90", "2026-01-06 19:31") == ["Tue 19:30"]
    # the micro cycle: 0, 22, 45, 67 minutes into each 90; nothing from 21:45, so the 21:22 candle runs to midnight
    assert first("SESSION_MICRO", "2026-01-06 18:21", "2026-01-06 18:22", "2026-01-06 19:07", "2026-01-06 21:30",
                 "2026-01-06 23:59", "2026-01-07 00:00") == ["Tue 18:00", "Tue 18:22", "Tue 19:07", "Tue 21:22",
                                                             "Tue 21:22", "Wed 00:00"]
    assert period_end(w("2026-01-06 13:00"), "240") == w("2026-01-06 17:00")
    assert period_end(w("2026-01-06 13:00"), "150") == w("2026-01-06 15:30")
    assert period_end(w("2026-01-06 16:00"), "150") == w("2026-01-06 17:00")       # cut at the day's open
    assert period_end(w("2025-12-31 17:00"), "1M") == w("2026-01-31 17:00")


def test_names_read_as_the_indicator_writes_them():
    assert [htf_name(x) for x in ("15", "240", "1D", "SESSION_90")] == ["15m", "4H", "1D", "Quarterly"]
    assert [fvg_label(x) for x in ("15", "240", "1D", "1W")] == ["15M", "4H", "1D", "1W"]


def test_settings_refuse_what_the_indicator_would_not_take():
    with pytest.raises(ValueError, match="unknown settings"):
        FractalSettings.from_dict({"fractl_mode": "Scalp"})
    with pytest.raises(ValueError, match="fractal_mode"):
        FractalSettings.from_dict({"fractal_mode": "Weekly"})
    with pytest.raises(ValueError, match="max_display"):
        FractalSettings.from_dict({"max_display": 2})
    s = FractalSettings.from_dict({"bias": "Bearish", "proj_show": "true", "sweep_history": "4"})
    assert s.bias == "Bearish" and s.proj_show is True and s.sweep_history == 4
    assert s.compute_key() == FractalSettings().compute_key()          # drawing inputs only
    assert FractalSettings(fractal_mode="Scalp").compute_key() != FractalSettings().compute_key()


# ── the model: a bearish C1/C2/C3/C4, candle by candle ──────────────────────────────────────────────────────
# M15 candles, read on an M15 chart with a custom H1 HTF, from Tuesday 01:00 New York.
Z = [(105, 115, 104, 106), (106, 107, 95, 100), (100, 104, 99, 103), (103, 106, 102, 105)]       # wide H1 before C1
A = [(100, 101, 99, 100.5), (100.5, 102, 100, 101.5), (101.5, 110, 101, 108), (108, 109, 105, 106)]   # C1: 110 / 99
B = [(106, 107, 105.5, 106.8), (106.8, 111, 106.5, 110.5), (110.5, 110.8, 107, 107.5), (107.5, 108, 105, 105.5)]
C = [(105.5, 106, 105.2, 105.4), (105.4, 107, 105.3, 106.9), (106.9, 106.95, 105.05, 105.2), (105.2, 105.5, 105.1, 105.3)]
D = [(105.3, 105.6, 105.1, 105.2), (105.2, 105.4, 105.1, 105.15)]
START = "2026-01-06 01:00"
H1 = FractalSettings(fractal_mode="Custom", custom_htf="60", proj_show=True, fvg_show=False, lq_show_sessions=False,
                     lq_show_pd=False, lq_show_pw=False, lq_show_htf1=False)


def _reader(candles, settings=H1):
    return FractalPOI(m1_from(candles, START), "M15", settings, "EURUSD")


def test_a_bearish_setup_is_the_pine_setup_value_for_value():
    reader = _reader(Z + A + B + C + D)
    clock = w("2026-01-06 05:30")                       # D's second candle has closed
    view = reader.at(clock)
    m = reader.model
    assert [k.o_time for k in m.candles] == [w("2026-01-06 05:00"), w("2026-01-06 04:00"), w("2026-01-06 03:00"),
                                             w("2026-01-06 02:00")]
    s = m.setups[0]
    assert not s.is_bullish and s.is_confirmed and s.is_post_c2 and not s.is_invalid
    a3, b1, b2, b4, c2, c3 = 6, 8, 9, 11, 13, 14
    assert (s.sweep_price, s.sweep_ltf_idx, s.swept_candle_idx, s.htf_candle_idx) == (110, a3, 4, b1)
    assert (s.tracked_extreme, s.extreme_bar_idx, s.c2_x, s.c2_y, s.c2_extreme) == (111, b2, b2, 111, 111)
    assert (s.cisd_level, s.cisd_start_idx, s.cisd_end_idx, s.cisd_triggered) == (106, b1, b4, True)   # b1's open
    assert (s.proj_anchor_1, s.proj_anchor_0) == (111, 105.5)                    # the swing, the CISD candle's low
    assert (s.liq_c1_price, s.liq_c1_start_idx, s.liq_c0_price) == (99, 4, 95)  # C1's low, then the candle before's
    # C3's zone: C2's mid 108 sits inside the CISD run's bodies (106-110.5), so it pairs with their mid 108.25
    assert (s.c2_mid, s.ez_c3_bot, s.ez_c3_top, s.ez_c3_left_time, s.ez_c3_right_time) == \
        (108, 108, 108.25, w("2026-01-06 04:00"), w("2026-01-06 05:00"))
    # C4's: C3's mid to C4's open, until C4 closes; invalid if C4 trades above C3's high
    assert (s.c3_mid, s.c3_extreme, s.ez_c4_bot, s.ez_c4_top) == (pytest.approx(106.025), 107, 105.3, pytest.approx(106.025))
    assert (s.ez_c4_left_time, s.ez_c4_right_time, s.ez_c4_invalid) == (w("2026-01-06 05:00"), w("2026-01-06 06:00"), False)
    # IC-CISDs: C3's up candle c2 (open 105.4) closed through by c3, the swing high at c2; then C3's last up
    # candle (open 105.2) closed through by C4's second, the swing high at C4's first
    assert [(ic.level, ic.start_idx, ic.end_idx, ic.extreme_price, ic.extreme_idx) for ic in s.ic_list] == \
        [(105.4, c2, c3, 107, c2), (105.2, 15, 17, 105.6, 16)]
    kinds = {(e["kind"], e["dir"]) for e in view["events"]}
    assert {("potential", "bear"), ("c2", "bear"), ("c2_cisd", "bear"), ("ic", "bear")} <= kinds
    drawn = [i for i in view["items"] if i.get("setup") == s.uid]
    texts = {i["t"] for i in drawn if i["k"] == "label"}
    assert {"C2", "C3", "C4", "●", "0", "1", "-1", "-2", "-2.5"} <= texts
    cisd = next(i for i in drawn if i["l"] == "cisd")
    assert (cisd["x1"], cisd["y1"], cisd["x2"]) == (w("2026-01-06 03:00"), 106, w("2026-01-06 04:00"))
    sd = sorted(i["y1"] for i in drawn if i["l"] == "proj" and i["k"] == "line")
    assert sd == pytest.approx([91.75, 94.5, 100, 105.5, 111])
    c4 = next(i for i in drawn if i["k"] == "box" and i["y1"] == pytest.approx(106.025))
    assert (c4["x1"], c4["x2"]) == (w("2026-01-06 05:00"), w("2026-01-06 05:30"))   # to the clock's candle's close


def test_c3_above_c2_s_high_after_cisd_invalidates_the_setup():
    breach = [(105.5, 106, 105.2, 105.4), (105.4, 111.5, 105.3, 110)]           # C3 trades through 111
    reader = _reader(Z + A + B + breach)
    view = reader.at(w("2026-01-06 04:30"))
    old = reader.model.setups[0]
    assert old.is_invalid and old.cisd_triggered
    new = reader.model.live[False]
    assert new is not None and new.sweep_price == 111 and new.swept_candle_idx == 8   # C2 is the new C1
    assert any(i["k"] == "label" and i["t"] == "xC2" for i in view["items"])


def test_a_c2_that_closes_beyond_c1_is_no_setup():
    beyond = B[:3] + [(107.5, 112, 107, 111.5)]                                 # C2 closes above 110
    reader = _reader(Z + A + beyond + C[:1])
    reader.at(w("2026-01-06 04:15"))
    assert reader.model.live[False] is None and not reader.model.setups


def test_the_bias_input_filters_what_is_drawn_not_what_is_read():
    reader = _reader(Z + A + B + C + D)
    clock = w("2026-01-06 05:30")
    bear = reader.at(clock)
    bull_only = reader.at(clock, FractalSettings(**{**H1.to_dict(), "bias": "Bullish"}))
    assert any(i.get("setup") for i in bear["items"]) and not any(i.get("setup") for i in bull_only["items"])
    assert not bull_only["events"] or all(e["dir"] == "bull" for e in bull_only["events"])
    with pytest.raises(ValueError, match="computing"):
        reader.at(clock, FractalSettings(**{**H1.to_dict(), "max_display": 6}))


def test_the_htf_candles_are_drawn_to_the_right_of_the_clock_s_candle():
    reader = _reader(Z + A + B + C + D)
    view = reader.at(w("2026-01-06 05:30"))
    bodies = sorted((i for i in view["items"] if i["l"] == "candles" and i["k"] == "box"), key=lambda i: i["x1"])
    now = w("2026-01-06 05:15")                       # the clock's candle, closed at 05:30, is Pine's last bar
    # offset 10, width 2: candles at +10, +13, +16, +19 chart candles, each two wide
    assert [(i["x1"] - now) // 900 for i in bodies] == [10, 13, 16, 19]
    assert [(i["x2"] - i["x1"]) // 900 for i in bodies] == [2, 2, 2, 2]
    assert next(i for i in view["items"] if i["l"] == "htf_label")["t"] == "1H\n\n(30:00)"


# ── fair value gaps ─────────────────────────────────────────────────────────────────────────────────────────
def _h1(*ranges) -> list[tuple]:
    """Four M15 candles per H1 (low, high): up through the range, closing near the high."""
    out = []
    for lo, hi in ranges:
        step = (hi - lo) / 4
        out += [(lo + k * step, lo + (k + 1) * step, lo + k * step, lo + (k + 1) * step - step / 4) for k in range(4)]
    return out


FVG = FractalSettings(fvg_auto_mode=False, fvg_manual_htf="60", lq_show_sessions=False, lq_show_pd=False,
                      lq_show_pw=False, lq_show_htf1=False, hide_candles=True, hide_setups=True, vt_show=False,
                      hl_show=False)


def test_a_gap_appears_at_the_next_htf_open_and_a_close_beyond_it_removes_it():
    candles = _h1((98, 100), (100, 104), (101, 105), (103, 106))               # C1 high 100, C3 low 101
    reader = FractalPOI(m1_from(candles, START), "M15", FVG, "EURUSD")
    assert not reader.at(w("2026-01-06 04:00"))["items"]                         # C3 closes at 04:00 ...
    view = reader.at(w("2026-01-06 04:15"))                                      # ... and is read at the next open
    gap = next(i for i in view["items"] if i["k"] == "box")
    assert (gap["y1"], gap["y2"], gap["x1"]) == (101, 100, w("2026-01-06 01:00"))  # top, bottom, from C1's open
    assert next(i for i in view["items"] if i["k"] == "label")["t"] == "FVG+1H"
    falls = candles + [(103, 103.5, 99, 99.5)] * 4 + [(99.5, 99.6, 99.4, 99.5)]  # an H1 closing below 100
    reader = FractalPOI(m1_from(falls, START), "M15", FVG, "EURUSD")
    assert any(i["k"] == "box" for i in reader.at(w("2026-01-06 05:00"))["items"])
    assert not any(i["k"] == "box" for i in reader.at(w("2026-01-06 06:15"))["items"])


def test_only_the_newest_gaps_are_kept():
    up = [(98 + 4 * k, 100 + 4 * k) for k in range(8)]                         # a gap every candle
    reader = FractalPOI(m1_from(_h1(*up), START), "M15", FVG, "EURUSD")
    boxes = [i for i in reader.at(w("2026-01-06 09:15"))["items"] if i["k"] == "box"]
    assert sorted(b["y2"] for b in boxes) == [108, 112, 116]                   # the newest three of five


# ── the liquidity suite ─────────────────────────────────────────────────────────────────────────────────────
LIQ = FractalSettings(fvg_show=False, lq_show_htf1=False, lq_show_pw=False, hide_candles=True, hide_setups=True,
                      vt_show=False, hl_show=False)


def _day(base: float, high_at: int, high: float, n: int = 96) -> list[tuple]:
    """A trading day of M15 candles around ``base``, with its high at candle ``high_at``."""
    out = [(base, base + 0.2, base - 0.2, base)] * n
    out[high_at] = (base, high, base - 0.2, base)
    return out


def test_the_previous_day_s_high_runs_from_its_candle_until_price_trades_through_it():
    day3 = [(100, 100.2, 99.8, 100), (100, 100.7, 99.9, 100.1), (100.1, 100.2, 99.9, 100)]
    days = _day(100, 40, 101) + _day(100, 10, 100.5) + day3                    # trading days from Mon 17:00
    reader = FractalPOI(m1_from(days, "2026-01-05 17:00"), "M15", LIQ, "EURUSD")
    pd_lines = lambda v: [i for i in v["items"] if i["l"] == "pd" and i["k"] == "line"]   # noqa: E731
    on_day2 = pd_lines(reader.at(w("2026-01-07 12:00")))
    high = next(i for i in on_day2 if i["y1"] == 101)                          # day 1's high, at Tue 03:00
    assert (high["x1"], high["x2"]) == (w("2026-01-06 03:00"), w("2026-01-07 11:45"))   # to the clock's candle
    assert not any(i["y1"] == 99.8 for i in on_day2)                          # day 2 trades at day 1's low at once:
    low = next(i for i in reader.at(w("2026-01-07 12:00"))["items"] if i["l"] == "purged" and i["k"] == "line")
    assert (low["y1"], low["x1"], low["x2"]) == (99.8, w("2026-01-06 16:45"), w("2026-01-06 17:15"))  # from the last
    on_day3 = pd_lines(reader.at(w("2026-01-07 17:15")))
    assert next(i for i in on_day3 if i["y1"] == 100.5)["x1"] == w("2026-01-06 19:30")   # day 2's high, from its candle
    view = reader.at(w("2026-01-07 17:45"))                                    # Wed 17:15 trades through 100.5
    assert not any(i["y1"] == 100.5 for i in pd_lines(view))
    grey = next(i for i in view["items"] if i["l"] == "purged" and i["k"] == "line" and i["y1"] == 100.5)
    assert (grey["y1"], grey["x1"], grey["x2"], grey["s"]) == (100.5, w("2026-01-06 19:30"), w("2026-01-07 17:15"), "dotted")
    assert any(i["k"] == "label" and i["t"] == "✕" and i["y"] == 100.5 for i in view["items"])


def test_a_session_s_high_and_low_run_until_touched_then_get_a_cross():
    asia = [(100, 100.1, 99.9, 100)] * 16                                       # 20:00-24:00
    asia[5] = (100, 100.6, 99.9, 100)                                           # A.H 100.6 at 21:15
    later = [(100, 100.2, 99.95, 100)] * 8 + [(100, 100.7, 100, 100.1)]         # 00:00 ... 02:00 takes it
    reader = FractalPOI(m1_from(asia + later, "2026-01-06 20:00"), "M15", LIQ, "EURUSD")
    view = reader.at(w("2026-01-07 01:00"))
    high = next(i for i in view["items"] if i["l"] == "sessions" and i["k"] == "line" and i["y1"] == 100.6)
    assert high["x1"] == w("2026-01-06 21:15") and high["x2"] == w("2026-01-07 00:45")   # runs to the clock's candle
    view = reader.at(w("2026-01-07 02:30"))
    high = next(i for i in view["items"] if i["l"] == "sessions" and i["k"] == "line" and i["y1"] == 100.6)
    assert high["x2"] == w("2026-01-07 02:00")                                 # stopped where it was touched
    assert any(i["l"] == "purged" and i["t"] == "✕" and i["y"] == 100.6 for i in view["items"] if i["k"] == "label")


def test_bsl_is_an_htf_swing_high_known_once_the_candle_after_it_closes():
    s = FractalSettings(fvg_show=False, lq_show_sessions=False, lq_show_pd=False, lq_show_pw=False, hide_candles=True,
                        hide_setups=True, vt_show=False, lq_htf1_mode="Manual", lq_htf1_manual="60")
    candles = _h1((99, 100), (100, 103), (99.5, 101), (99, 100.5), (99, 103.5))   # swing high 103 at H1 #2
    reader = FractalPOI(m1_from(candles, START), "M15", s, "EURUSD")
    assert not [i for i in reader.at(w("2026-01-06 04:00"))["items"] if i.get("t") == "BSL"]
    view = reader.at(w("2026-01-06 04:15"))
    bsl = next(i for i in view["items"] if i["l"] == "bsl1" and i["k"] == "line" and i["y1"] == 103)
    assert bsl["x1"] == w("2026-01-06 02:45")                                    # the swing's own high candle
    view = reader.at(w("2026-01-06 06:00"))                                       # H1 #5's last candle takes 103
    assert not any(i.get("t") == "BSL" and i["y"] == 103 for i in view["items"] if i["k"] == "label")
    assert any(i["l"] == "purged" and i["k"] == "line" and i["y1"] == 103 for i in view["items"])


# ── Property 11: nothing from after the clock ───────────────────────────────────────────────────────────────
def _walk(seed: int, days: int = 4, first: str = "2026-01-04 17:00") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = pd.date_range(pd.Timestamp(first, tz=NY), periods=days * 1440, freq="1min").tz_convert("UTC")
    close = 1.1 + np.cumsum(rng.normal(0, 0.00015, len(t)))
    open_ = np.r_[1.1, close[:-1]]
    spread = np.abs(rng.normal(0, 0.0001, len(t)))
    return pd.DataFrame({"time": t, "open": open_, "high": np.maximum(open_, close) + spread,
                         "low": np.minimum(open_, close) - spread, "close": close})


@pytest.mark.parametrize("tf", ["M15", "M5", "H1"])
def test_what_is_drawn_at_a_clock_is_the_same_without_the_data_after_it(tf):
    m1, partner = _walk(1), _walk(2)
    s = FractalSettings(proj_show=True, lq_show_pm=True, lq_show_htf2=True, lq_show_swings=True, htf2_show=True)
    full = FractalPOI(m1, tf, s, "EURUSD", {"GBPUSD": (partner, False)})
    wall = wall_seconds(m1["time"])
    rng = np.random.default_rng(7)
    for clock in sorted(rng.integers(int(wall[0]) + 86400, int(wall[-1]), 6)):
        clock = int(clock)
        cut = lambda f: f[wall_seconds(f["time"]) + 60 <= clock]                    # noqa: E731
        alone = FractalPOI(cut(m1), tf, s, "EURUSD", {"GBPUSD": (cut(partner), False)})
        assert full.at(clock) == alone.at(clock), f"{tf} at {pd.Timestamp(clock, unit='s')}"


def test_going_back_reads_as_a_fresh_reader_would():
    m1 = _walk(3)
    s = FractalSettings(proj_show=True)
    wall = wall_seconds(m1["time"])
    late, early = int(wall[-1]) - 3600, int(wall[0]) + 2 * 86400 + 1234
    reader = FractalPOI(m1, "M5", s, "EURUSD")
    reader.at(late)
    assert reader.at(early) == FractalPOI(m1, "M5", s, "EURUSD").at(early)


def test_partners_and_warmup():
    assert partners_for("EURUSD", FractalSettings(), ["GBPUSD", "DXY"]) == [("GBPUSD", False), ("DXY", True)]
    assert partners_for("BTCUSDT", FractalSettings(), ["GBPUSD"]) == []
    manual = FractalSettings(smt_mode="Manual", smt_sym1="us500", smt_sym2="us30", smt_sym2_inverse=True)
    assert partners_for("US100", manual, ["US500", "US30"]) == [("US500", False), ("US30", True)]
    assert warmup_days("M15", FractalSettings()) >= 15 and warmup_days("H1", FractalSettings()) <= 121


# ── task 338: the setups as a table, against the engine, as trades (Requirement 24) ─────────────────────────
def _path(m1: pd.DataFrame) -> dict:
    """The races' M1 path for built candles: no spread."""
    return {"time": np.asarray(wall_seconds(m1["time"]), dtype=np.int64),
            **{k: m1[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close")},
            "spread": np.zeros(len(m1))}


def test_a_setup_s_row_carries_its_levels_and_when_each_was_known():
    from algo_research.fractal_poi.setups import setup_rows
    reader = FractalPOI(m1_from(Z + A + B + C + D, START), "M15", H1, "EURUSD", archive=True)
    reader.at(w("2026-01-06 05:30"))
    row = setup_rows(reader).iloc[0]
    assert (row.direction, row.htf, row.sweep_price, row.c2_extreme, row.cisd_level) == ("SHORT", "60", 110, 111, 106)
    assert (row.c1_open, row.c2_open, row.sweep_at) == (w("2026-01-06 02:00"), w("2026-01-06 03:00"), w("2026-01-06 03:15"))
    assert (row.cisd_at, row.c3_open, row.c4_open, row.c4_close) == (w("2026-01-06 04:00"), w("2026-01-06 04:00"),
                                                                    w("2026-01-06 05:00"), w("2026-01-06 06:00"))
    assert (row.z3_low, row.z3_high, row.target_c1, row.target_c0) == (108, 108.25, 99, 95) and pd.isna(row.invalid_at)


def test_a_setup_that_fails_in_c3_is_still_traded_from_c3():
    """C3's close comes from the HTF clock, not from the setup's later record: only a survivor gets a C4, so
    reading it there would drop every setup that went on to fail (the 2026-10-20 look-ahead)."""
    from algo_research.fractal_poi.diff import trade_setups, windows
    from algo_research.fractal_poi.setups import setup_rows
    breach = [(105.5, 106, 105.2, 105.4), (105.4, 111.5, 105.3, 110)]           # C3 runs through C2's high, 111
    m1 = m1_from(Z + A + B + breach, START)
    reader = FractalPOI(m1, "M15", H1, "EURUSD", archive=True)
    reader.at(w("2026-01-06 04:30"))
    setups = windows(setup_rows(reader))
    failed = setups.iloc[0]
    assert pd.notna(failed.invalid_at) and pd.isna(failed.c4_open)              # an xC2: no C4 in its record
    assert (failed.c3_close, failed.w1) == (w("2026-01-06 05:00"), failed.invalid_at)
    trades = trade_setups(setups.iloc[:1], _path(m1)).set_index("variant")
    assert trades.loc["B", "state"] == "CLOSED" and trades.loc["B", "outcome"] == "STOP"   # filled at 108.25, stopped
    assert trades.loc["B", "fill"] == 108.25 and "C" not in trades.index                    # no C4 zone after an xC2


def test_engine_orders_are_with_against_or_outside_a_live_setup():
    from algo_research.fractal_poi.diff import classify_orders
    setups = pd.DataFrame({"direction": ["SHORT", "LONG"], "w0": [100, 500], "w1": [200, 600],
                           "sweep_price": [110.0, 90.0], "target_c1": [100.0, 100.0]})
    orders = pd.DataFrame({"tw": [150, 150, 550, 300], "direction": ["SHORT", "SHORT", "SHORT", "LONG"],
                           "raid": [{"price": 110.2}, {"price": 104.0}, {"price": 90.0}, None]})
    out = classify_orders(orders, setups)
    assert out.cls.tolist() == ["with", "with", "against", "outside"]
    assert out.raid_is_c1.tolist() == [True, False, None, None]                # within 5% of C1's range, or not
