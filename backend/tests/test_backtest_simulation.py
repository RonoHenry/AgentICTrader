"""
Tests for algo_backtester/simulation.py — Phase B, the event loop.

Task 203 (.kiro/specs/algo-backtester/tasks.md). Synthetic M1 bars and
scripted SignalRecords: every order goes through the real AgentGraph
(observe -> analyse -> decide -> execute) with RiskEngine on fakeredis, the
SimBroker and the SimAccount, in time order across instruments.
Validates: Requirements 1.1, 1.4, 1.5, 6.3, 7.5 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import algo_backtester.simulation as simulation
from agent.brokers.fill_model import Bar
from agent.instruments import CommissionSpec, InstrumentSpec, InstrumentSpecs
from agent.order_intent import NoTrade, OrderIntent
from agent.strategy_config import StrategyConfig
from algo_backtester.config import AccountSection
from algo_backtester.signals import EngineError, SignalRecord
from algo_backtester.simulation import simulate
from liquidity_engine.models import SetupGrade, Timeframe
from ml.features.session_features import TimeFeatures

UTC = timezone.utc
MIN = timedelta(minutes=1)
T0 = datetime(2026, 9, 30, 13, 0, tzinfo=UTC)          # 09:00 New York, in the NY AM killzone
START, END = datetime(2026, 9, 30, 12, 0, tzinfo=UTC), datetime(2026, 9, 30, 16, 0, tzinfo=UTC)
PRICES = {"EURUSD": 1.1000, "GBPUSD": 1.3000, "USDJPY": 150.00, "XAUUSD": 2650.0}
SPREADS = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "XAUUSD": 0.2}


def _spec(symbol: str) -> InstrumentSpec:
    base, quote = {"EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "USDJPY": ("USD", "JPY"),
                   "XAUUSD": ("XAU", "USD")}[symbol]
    return InstrumentSpec(symbol=symbol, venue="mt5", point=1e-5, tick_size=1e-5,
                          contract_size=100.0 if symbol == "XAUUSD" else 100_000.0, volume_min=0.01,
                          volume_step=0.01, volume_max=100.0, base_ccy=base, quote_ccy=quote,
                          default_spread=SPREADS[symbol], stop_slippage=0.0, commission=CommissionSpec("PER_LOT_PER_SIDE", 0.0))


SPECS = InstrumentSpecs("mt5", "USD", {s: _spec(s) for s in PRICES})
CFG = StrategyConfig()
ACCOUNT = AccountSection(initial_equity=10_000.0, risk_per_trade=0.01)


def flat(instrument: str, start: datetime = START, end: datetime = END) -> list[Bar]:
    price, spread, out, t = PRICES[instrument], SPREADS[instrument], [], start
    while t < end:
        out.append(Bar(t, price, price, price, price, spread))
        t += MIN
    return out


def dip(bars: list[Bar], opens_at: datetime, low: float) -> list[Bar]:
    """The bar opening at ``opens_at`` trades down to ``low`` and closes back."""
    return [replace(b, low=low) if b.timestamp == opens_at else b for b in bars]


def intent(instrument: str, t: datetime, setup_id: str, entry_offset: float = 0.0, stop_distance: float = 0.0010,
           direction: str = "LONG", confidence: float = 0.8) -> SignalRecord:
    """An intent at t. With entry_offset 0 a LONG enters at the ask (a market order)."""
    price, spread = PRICES[instrument], SPREADS[instrument]
    scale = price / PRICES["EURUSD"]
    sign = 1 if direction == "LONG" else -1
    entry = (price + spread if direction == "LONG" else price) + entry_offset * scale
    stop = entry - sign * stop_distance * scale
    target = entry + sign * 5 * stop_distance * scale
    features = TimeFeatures(time_window="NY_AM_KILLZONE", narrative_phase="EXPANSION", time_window_weight=1.0,
                            is_killzone=True, is_high_probability_window=True, price_vs_daily_open="BELOW",
                            price_vs_weekly_open="BELOW")
    return SignalRecord(t, instrument, OrderIntent(
        setup_id=setup_id, instrument=instrument, entry_tf=Timeframe.M15, as_of=t, grade=SetupGrade.A,
        direction=direction, entry=entry, stop_loss=stop, take_profit_1=target, take_profit_2=None, r_ratio=5.0,
        confidence=confidence, time_features=features, patterns=(), regime="TRENDING_BULLISH"))


def run(bars: dict, signals: dict, account: AccountSection = ACCOUNT, **kwargs):
    return simulate(bars, signals, SPECS, CFG, account, **kwargs)


def rows(result) -> list[tuple]:
    return [(r.t, r.instrument, r.decision) for r in result.journal]


# ── ordering ───────────────────────────────────────────────────────────────

def test_fills_processed_before_decisions_at_same_t():
    # A stops out on the bar closing at 13:30; B arrives at 13:30 and is not "in trade".
    bars = {"EURUSD": dip(flat("EURUSD"), T0 + 29 * MIN, low=1.0985)}
    signals = {"EURUSD": [intent("EURUSD", T0, "A"), intent("EURUSD", T0 + 30 * MIN, "B")]}
    result = run(bars, signals)
    assert rows(result) == [(T0, "EURUSD", "EXECUTE"), (T0 + 30 * MIN, "EURUSD", "EXECUTE")]
    a = result.journal[0].trade
    assert a.exit_reason == "SL" and a.closed_at == T0 + 29 * MIN


def test_in_trade_signal_journaled_not_evaluated():
    signals = {"EURUSD": [intent("EURUSD", T0, "A"), intent("EURUSD", T0 + 15 * MIN, "B")]}
    result = run({"EURUSD": flat("EURUSD")}, signals)
    assert rows(result) == [(T0, "EURUSD", "EXECUTE"), (T0 + 15 * MIN, "EURUSD", "IN_TRADE")]
    in_trade = result.journal[1]
    assert in_trade.order_id is None and "sim-000001" in in_trade.reason
    assert [o.order_id for o in result.open_orders] == ["sim-000001"]   # B never reached the broker


def test_setup_already_attempted_after_stop_out():
    bars = {"EURUSD": dip(flat("EURUSD"), T0 + 29 * MIN, low=1.0985)}
    signals = {"EURUSD": [intent("EURUSD", T0, "S1"), intent("EURUSD", T0 + 45 * MIN, "S1"),
                          intent("EURUSD", T0 + 60 * MIN, "S2")]}
    result = run(bars, signals)
    assert [r.decision for r in result.journal] == ["EXECUTE", "SETUP_ALREADY_ATTEMPTED", "EXECUTE"]   # D6


def test_concurrent_trade_limit_across_instruments():
    instruments = ["XAUUSD", "USDJPY", "GBPUSD", "EURUSD"]                 # any order in, alphabetical out
    result = run({i: flat(i) for i in instruments}, {i: [intent(i, T0, f"{i}-1")] for i in instruments})
    assert rows(result) == [(T0, "EURUSD", "EXECUTE"), (T0, "GBPUSD", "EXECUTE"),
                            (T0, "USDJPY", "EXECUTE"), (T0, "XAUUSD", "SKIP")]
    assert "concurrent trades 3 has reached the 3 trade limit" in result.journal[3].reason


def test_risk_rejection_journaled_with_reason():
    # Two 2% losses take the day past RiskEngine's 3% limit; the third setup is refused.
    bars = dip(dip(flat("EURUSD"), T0 + 14 * MIN, low=1.0985), T0 + 29 * MIN, low=1.0985)
    signals = {"EURUSD": [intent("EURUSD", T0, "S1"), intent("EURUSD", T0 + 15 * MIN, "S2"),
                          intent("EURUSD", T0 + 30 * MIN, "S3")]}
    result = run({"EURUSD": bars}, signals, account=AccountSection(initial_equity=10_000.0, risk_per_trade=0.02))
    assert [r.decision for r in result.journal] == ["EXECUTE", "EXECUTE", "SKIP"]
    assert result.journal[2].reason.startswith("daily drawdown 4.")
    assert result.account.equity == pytest.approx(10_000.0 - 2 * 200.0, abs=1.0)


@pytest.mark.parametrize("reason", ["NO_ANTICIPATION", "AGAINST_PROFILE", "NO_FALSE_MOVE", "OUTSIDE_WINDOW",
                                    "NO_POI", "STOP_TOO_TIGHT"])
def test_policy_reasons_journaled_as_their_own_decision(reason):
    # liquidity-engine Req 23.6: the breakdowns count each rule's refusals.
    record = SignalRecord(T0, "EURUSD", NoTrade("EURUSD", T0, "A", reason, "detail"))
    result = run({"EURUSD": flat("EURUSD")}, {"EURUSD": [record]})
    assert [(r.decision, r.reason, r.grade) for r in result.journal] == [(reason, "detail", "A")]


def test_no_trade_and_engine_error_records_journaled():
    no_trade = SignalRecord(T0, "EURUSD", NoTrade("EURUSD", T0, "A", "RR_BELOW_MIN", "R:R 2.10 is below the 3.0 floor", 2.1))
    graded_out = SignalRecord(T0 + 15 * MIN, "EURUSD", NoTrade("EURUSD", T0 + 15 * MIN, "NO_TRADE", "NO_TRADE", "5/8"))
    error = SignalRecord(T0 + 30 * MIN, "EURUSD", EngineError("ValueError", "boom"))
    bad_stop = SignalRecord(T0 + 45 * MIN, "EURUSD", NoTrade("EURUSD", T0 + 45 * MIN, "B", "INVALID_STOP", "WICK stop"))
    result = run({"EURUSD": flat("EURUSD")}, {"EURUSD": [no_trade, graded_out, error, bad_stop]})
    assert [(r.decision, r.reason) for r in result.journal] == [
        ("RR_BELOW_MIN", "R:R 2.10 is below the 3.0 floor"), ("NO_TRADE", "5/8"), ("ENGINE_ERROR", "ValueError: boom"),
        ("INVALID_STOP", "WICK stop")]
    assert result.journal[0].grade == "A" and result.trades == []


def test_agent_graph_runs_with_ai_clients_disabled_and_sim_clock(monkeypatch):
    built = {}

    class SpyGraph(simulation.AgentGraph):
        def __init__(self, **kwargs):
            built.update(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(simulation, "AgentGraph", SpyGraph)
    result = run({"EURUSD": flat("EURUSD")}, {"EURUSD": [intent("EURUSD", T0, "A")]})
    assert built["visual_model_client"] is None and built["algorag_client"] is None
    # no Mongo journal: learn_node would queue MLflow retraining every 50 decisions
    assert built["trade_journal_collection"] is None and built["agent_decisions_collection"] is None
    # a wall clock would make the 2026-09-30 setup stale (observe_node's 60 s check)
    assert result.journal[0].decision == "EXECUTE"
    assert result.open_orders[0].placed_at == T0 and result.open_orders[0].filled_at == T0


def test_order_not_eligible_on_bar_opening_before_t():
    # The bar that opened at 12:59 and closed at t trades through the limit; it predates the decision.
    bars = {"EURUSD": dip(flat("EURUSD"), T0 - MIN, low=1.0990)}
    result = run(bars, {"EURUSD": [intent("EURUSD", T0, "A", entry_offset=-0.0006)]})
    trade = result.journal[0].trade
    assert trade.kind == "LIMIT" and not trade.filled and trade.exit_reason == "EXPIRED"
    assert trade.closed_at == datetime(2026, 9, 30, 14, 0, tzinfo=UTC)   # 10:00 New York, the killzone end


def test_same_t_processed_in_alphabetical_instrument_order():
    signals = {"XAUUSD": [intent("XAUUSD", T0, "X")], "EURUSD": [intent("EURUSD", T0, "E")]}
    result = run({"XAUUSD": flat("XAUUSD"), "EURUSD": flat("EURUSD")}, signals)
    assert [(r.instrument, r.order_id) for r in result.journal] == [("EURUSD", "sim-000001"),
                                                                   ("XAUUSD", "sim-000002")]


def test_open_orders_at_end_reported_and_trades_attached_to_rows():
    bars = {"EURUSD": dip(flat("EURUSD"), T0 + 29 * MIN, low=1.0985), "XAUUSD": flat("XAUUSD")}
    signals = {"EURUSD": [intent("EURUSD", T0, "A")], "XAUUSD": [intent("XAUUSD", T0, "X")]}
    result = run(bars, signals)
    eur, xau = result.journal
    assert eur.trade is not None and eur.trade.order_id == eur.order_id and result.trades == [eur.trade]
    assert xau.trade is None and [o.order_id for o in result.open_orders] == [xau.order_id]
    assert eur.intent.setup_id == "A" and eur.setup_id == "A" and eur.time_window == "NY_AM_KILLZONE"


# ── Property 9 ─────────────────────────────────────────────────────────────

@st.composite
def scenarios(draw):
    instruments = ["EURUSD", "XAUUSD"]
    bars, signals = {}, {}
    for instrument in instruments:
        price, spread, scale = PRICES[instrument], SPREADS[instrument], PRICES[instrument] / PRICES["EURUSD"]
        out, t = [], START
        while t < START + timedelta(hours=3):
            step = draw(st.floats(-0.0006, 0.0006)) * scale
            o = price
            c = price + step
            out.append(Bar(t, o, max(o, c) + 0.0002 * scale, min(o, c) - 0.0002 * scale, c, spread))
            price, t = c, t + MIN
        bars[instrument] = out
        closes = draw(st.lists(st.integers(1, 11), unique=True, max_size=8))
        # Priced off a fixed level while the bars wander: a mix of limits, market orders and refusals.
        signals[instrument] = [
            intent(instrument, START + 15 * k * MIN, f"{instrument}-{draw(st.integers(0, 3))}",
                   entry_offset=draw(st.floats(-0.0010, 0.0003)), stop_distance=draw(st.floats(0.0003, 0.0020)),
                   direction=draw(st.sampled_from(["LONG", "SHORT"])))
            for k in sorted(closes)
        ]
    return bars, signals


@settings(max_examples=100, deadline=None)
@given(scenarios())
def test_property_9_account_state_matches_positions(case):
    bars, signals = case
    seen = []

    def check(t, broker, account):
        exposure = account.exposure()
        assert exposure["open_trades"] == broker.active_count()
        assert account.daily_dd_pct >= 0 and account.weekly_dd_pct >= 0
        active = [broker.active_trade(i) for i in bars]
        assert broker.active_count() == sum(a is not None for a in active)   # at most one per instrument
        seen.append(t)

    run(bars, signals, on_step=check)
    assert seen and seen == sorted(seen)
