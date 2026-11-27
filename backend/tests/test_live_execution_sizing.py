"""The shared sizing rule (live-execution Requirements 1, 2; task 454).

SimBroker and the MT5 adapter size a risk-based order with the same functions,
so a live order's lots are the backtest's. SimBroker's own tests
(test_backtest_sim_broker.py) pin its behaviour through the refactor.

Validates: Requirements 1.1-1.3, 2.1-2.2 (.kiro/specs/live-execution/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.brokers.fill_model import Bar
from agent.brokers.sizing import SizingError, lots_for_risk, round_down, split_lots, stop_overrun
from agent.instruments import CommissionSpec, InstrumentSpec, InstrumentSpecs
from agent.strategy_config import PendingExpiry
from algo_backtester.sim_broker import SimBroker, SimBrokerError


class TestRoundDown:
    def test_rounds_down_to_the_step(self):
        assert round_down(0.039, 0.01) == 0.03

    def test_exact_multiples_survive_float_error(self):
        # 0.3 / 0.1 is 2.9999999999999996 in floating point.
        assert round_down(0.3, 0.1) == 0.3

    def test_whole_steps(self):
        assert round_down(7.9, 1.0) == 7.0


class TestLotsForRisk:
    def test_budget_over_risk_per_lot_rounded_down(self):
        # $100 budget, $199 per lot at the stop: 0.5025 lots -> 0.50.
        assert lots_for_risk(100.0, 199.0, volume_min=0.01, volume_step=0.01, volume_max=100.0) == 0.5

    def test_capped_at_volume_max(self):
        assert lots_for_risk(100.0, 0.5, volume_min=0.01, volume_step=0.01, volume_max=50.0) == 50.0

    def test_volume_min_within_tolerance(self):
        # 0.01 lots risk $10.5 against a $10 budget: within +10%.
        assert lots_for_risk(10.0, 1050.0, volume_min=0.01, volume_step=0.01, volume_max=100.0) == 0.01

    def test_volume_min_over_risk_refused(self):
        with pytest.raises(SizingError) as raised:
            lots_for_risk(10.0, 1200.0, volume_min=0.01, volume_step=0.01, volume_max=100.0)
        assert raised.value.reason == "MIN_VOLUME_OVER_RISK"

    def test_tolerance_is_a_parameter(self):
        with pytest.raises(SizingError):
            lots_for_risk(10.0, 1050.0, volume_min=0.01, volume_step=0.01, volume_max=100.0, tolerance=0.0)

    @settings(max_examples=200, deadline=None)
    @given(
        budget=st.floats(1.0, 10_000.0),
        risk_per_lot=st.floats(0.5, 100_000.0),
        step=st.sampled_from([0.01, 0.1, 1.0]),
    )
    def test_never_risks_more_than_the_budget_unless_at_the_minimum(self, budget, risk_per_lot, step):
        try:
            lots = lots_for_risk(budget, risk_per_lot, volume_min=step, volume_step=step, volume_max=1_000.0)
        except SizingError:
            assert step * risk_per_lot > budget * 1.10
            return
        assert lots >= step
        if lots > step:
            assert lots * risk_per_lot <= budget * (1 + 1e-9)
        else:
            assert lots * risk_per_lot <= budget * 1.10 * (1 + 1e-9)


class TestSplitLots:
    def test_a_third_rounded_down(self):
        assert split_lots(0.30, 1 / 3, volume_min=0.01, volume_step=0.01) == 0.1

    def test_part_under_the_minimum_runs_unmanaged(self):
        # 0.02 lots: a third is under the 0.01 minimum (D44).
        assert split_lots(0.02, 1 / 3, volume_min=0.01, volume_step=0.01) == 0.0

    def test_rest_under_the_minimum_runs_unmanaged(self):
        assert split_lots(0.10, 0.95, volume_min=0.01, volume_step=0.01) == 0.09
        assert split_lots(0.10, 0.95, volume_min=0.02, volume_step=0.01) == 0.0

    def test_no_fraction_no_split(self):
        assert split_lots(1.0, 0.0, volume_min=0.01, volume_step=0.01) == 0.0


class TestStopOverrun:
    def test_costs_as_a_share_of_the_stop(self):
        # 1 pip of spread plus 0.5 pip of slippage on a 10 pip stop.
        assert stop_overrun(0.0010, spread=0.0001, slippage=0.00005) == pytest.approx(0.15)

    def test_a_zero_stop_is_infinitely_over(self):
        assert stop_overrun(0.0, spread=0.0001, slippage=0.0) == float("inf")


# ── SimBroker: the backstop is a switch, off by default (LX-D1) ────────────

T0 = datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc)
SPECS = InstrumentSpecs("mt5", "USD", {"EURUSD": InstrumentSpec(
    symbol="EURUSD", venue="mt5", point=1e-5, tick_size=1e-5, contract_size=100_000.0, volume_min=0.01,
    volume_step=0.01, volume_max=100.0, base_ccy="EUR", quote_ccy="USD", default_spread=0.0001,
    stop_slippage=0.00002, commission=CommissionSpec("PER_LOT_PER_SIDE", 3.5))})


def _sim(**kwargs) -> SimBroker:
    b = SimBroker(SPECS, clock=lambda: T0, expiry_rule=PendingExpiry.KILLZONE_END,
                  fallback_ttl=timedelta(hours=3), **kwargs)
    b.advance("EURUSD", Bar(timestamp=T0 - timedelta(minutes=1), open=1.1010, high=1.1010, low=1.1010,
                            close=1.1010, spread=0.0001))
    return b


def _tight_long() -> dict:
    # A 2-pip stop: 1 pip of spread plus 0.2 of slippage is 60% of it.
    return {"instrument": "EURUSD", "direction": "LONG", "entry": 1.1000, "stop_loss": 1.0998,
            "take_profit": 1.1040, "risk_amount": 100.0, "setup_id": "s1"}


class TestSimBrokerBackstop:
    def test_off_by_default_so_recorded_results_stay(self):
        b = _sim()
        b.place_order(_tight_long())
        assert b.active_trade("EURUSD") is not None

    def test_on_it_refuses_with_the_code(self):
        b = _sim(max_stop_overrun=0.5)
        with pytest.raises(SimBrokerError) as raised:
            b.place_order(_tight_long())
        assert raised.value.reason == "STOP_TOO_TIGHT"
        assert b.active_trade("EURUSD") is None

    def test_on_it_lets_a_wide_stop_through(self):
        b = _sim(max_stop_overrun=0.5)
        b.place_order({**_tight_long(), "stop_loss": 1.0990})   # 10 pips: 12%
        assert b.active_trade("EURUSD") is not None
