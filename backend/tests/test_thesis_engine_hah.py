"""
Tests for H-AH's runner (thesis-engine Requirement 16; task 420): its verdict against V1's weekly break-even, and the
companion's R, a third off at +3R and the rest's stop moved to the fill.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from agent.brokers.fill_model import Bar, FillModel, SimOrder
from thesis_engine.hag import MARKETS
from thesis_engine.hah import judge
from thesis_engine.replay import _r

T0 = datetime(2022, 1, 5, 8, tzinfo=timezone.utc)


def _bar(i: int, o: float, h: float, low: float, c: float) -> Bar:
    return Bar(T0 + timedelta(minutes=i), o, h, low, c, 0.0001)


def test_the_companion_takes_a_third_at_3r_and_measures_from_the_planned_stop():
    order = SimOrder("o", "s", "EURUSD", "LONG", "LIMIT", 1.1000, 1.0990, 1.1100, T0, partial_r=3.0,
                     partial_fraction=1 / 3)
    fm = FillModel(stop_slippage=0.0)
    events = [ev.kind for b in (_bar(0, 1.1005, 1.1006, 1.0995, 1.1002), _bar(1, 1.1002, 1.1035, 1.1001, 1.1030),
                                _bar(2, 1.1030, 1.1031, 1.0995, 1.0996)) for ev in fm.step(order, b)]
    assert events == ["FILLED", "PARTIAL", "SL"] and order.stop == order.fill
    net, gross, risk = _r(order, 0.0001, 1.0990)
    assert risk == pytest.approx(0.0010)
    assert net == pytest.approx((1 / 3) * 3.0 + (2 / 3) * 0.0)
    assert gross == pytest.approx(((1 / 3) * (1.1030 - 1.0999) + (2 / 3) * (1.1000 - 1.0999)) / (1.0999 - 1.0990))


def test_without_a_partial_the_r_is_v1s():
    order = SimOrder("o", "s", "EURUSD", "SHORT", "MARKET", 1.1000, 1.1010, 1.0950, T0)
    fm = FillModel(stop_slippage=0.0)
    for b in (_bar(0, 1.1000, 1.1002, 1.0990, 1.0995), _bar(1, 1.0995, 1.0996, 1.0940, 1.0945)):
        fm.step(order, b)
    net, _, risk = _r(order, 0.0001, order.stop)
    assert order.exit_reason == "TP" and net == (order.fill - order.exit) / (order.stop - order.fill)


def _trades(oracle: float, mirror: float) -> pd.DataFrame:
    rows = [{"arm": arm, "market": m, "week": w, "net_r": r, "gross_r": r, "direction": "LONG", "risk_spreads": 20.0,
             "reason": "SL"} for arm, r in (("ORACLE", oracle), ("MIRROR", mirror)) for m in MARKETS for w in (1, 2)]
    return pd.DataFrame(rows)


def test_the_verdict_needs_a_weekly_break_even_below_v1s():
    weeks = {"ORACLE": 16, "MIRROR": 16}
    r = judge(_trades(1.0, -1.0), weeks, v1_week=0.583)
    assert r["break_even"]["per_week"] == pytest.approx(0.5) and r["passes"]
    worse = judge(_trades(1.0, -1.0), weeks, v1_week=0.45)
    assert not worse["passes"] and list(worse["checks"].values()) == [True, True, False]
    losing = judge(_trades(-0.1, -1.0), weeks, v1_week=0.583)
    assert not losing["passes"] and not list(losing["checks"].values())[0]
