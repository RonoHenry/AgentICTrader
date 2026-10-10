"""
Property 1: No Look-Ahead (Truncation Invariance).

For any entry-TF close t, the SignalRecord Phase A produces at t from the
full data equals the one produced from the data truncated to the M1 bars
closed at or before t. Real data (task 186 MetaQuotes fixtures) and the real
engine, so this tests the whole decision path: data loading, aggregation,
the as-of view, analyze() and build_order_intent().

Task 199 (.kiro/specs/algo-backtester/tasks.md).
Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from algo_backtester.data import load_instrument
from algo_backtester.signals import signal_at
from services.market_data.mt5_clock import MT5ServerClock
from tests.test_backtest_signals import CFG, END, START, FixtureSource, data_for, entry_closes

CLOSES = entry_closes(data_for("EURUSD"), START, END)


@settings(max_examples=25, deadline=None)
@given(st.sampled_from(CLOSES))
def test_property_1_signal_unchanged_when_data_after_t_removed(t):
    full = signal_at(data_for("EURUSD"), CFG, t)
    truncated_data = load_instrument(FixtureSource("EURUSD", m1_until=t), "EURUSD", START, END, CFG,
                                     MT5ServerClock("ny_close"), venue="mt5", max_gap_minutes=30)
    assert truncated_data.m1[-1].timestamp + timedelta(minutes=1) <= t  # nothing closes after t
    assert signal_at(truncated_data, CFG, t) == full
