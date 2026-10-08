"""Phase B: the account, in time order across all instruments.

Phase A decided, per instrument, what the engine would do at every entry
close. Phase B replays those decisions through the live agent, in one time
line across instruments, so the rules that span the account see the true
state: one active trade per instrument, the concurrent-trade limit, and the
daily and weekly drawdown limits (Req 1.4, 1.5, 7.5).

Each order intent goes through the real AgentGraph, as the live runner sends
it: observe -> analyse -> decide (RiskEngine on the run's own fakeredis) ->
execute (SimBroker). The AI layers are off (no visual model or AlgoRAG
client), and so are learn_node and the audit trail: learn_node would queue an
MLflow retraining run every 50 decisions. The journal here records every
decision instead.

For each minute t, over the merged stream of M1 bars (closing at t) and
SignalRecords (at t), instruments in alphabetical order:
1. every bar closing at t steps the instrument's orders (fills, stops,
   targets, expiry) and closed trades are booked into the account; then the
   account is marked at t;
2. then each SignalRecord at t is journaled:
   - NoTrade / EngineError: as they are;
   - IN_TRADE: the instrument has a pending or open order. Live skips
     evaluation then too;
   - SETUP_ALREADY_ATTEMPTED: an order for this setup_id was placed before
     (D6), whatever became of it;
   - otherwise the account's exposure goes to RiskEngine's key, the clock is
     set to t, and the graph runs. Its final decision, reason and order id
     are journaled.

An order placed at t is eligible only for bars opening at or after t, so the
bar that just closed can't fill it.

    result = simulate(bars, signals, specs, cfg.strategy, cfg.account)
    result.journal      # one row per SignalRecord, with the trade it led to
    result.trades       # every order that closed, in closing order

Validates: Requirements 1.1, 1.4, 1.5, 6.3, 7.5 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import heapq
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from itertools import groupby
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional, Sequence

import fakeredis

from agent.brokers.fill_model import Bar
from agent.graph import AgentGraph
from agent.instruments import InstrumentSpecs
from agent.order_intent import OWN_DECISION_REASONS, NoTrade, OrderIntent
from agent.state import AgentMode
from agent.strategy_config import StrategyConfig
from algo_backtester.account import SimAccount
from algo_backtester.config import AccountSection
from algo_backtester.signals import EngineError, SignalRecord, TradeContext
from algo_backtester.sim_broker import ClosedTrade, Conversion, SimBroker, SimTrade
from services.risk_engine.main import RiskEngine

__all__ = ["JournalRow", "SimulationResult", "simulate"]

USER_ID = "default"
_EXPOSURE_KEY = f"risk:exposure:{USER_ID}"
_M1 = timedelta(minutes=1)
_BAR, _SIGNAL = 0, 1   # bars before signals at the same t: fills first, then decisions

Step = Callable[[datetime, SimBroker, SimAccount], None]


@dataclass(frozen=True)
class JournalRow:
    """One SignalRecord's outcome (Req 8.1). ``trade`` is the order it led to,
    once that order closed."""
    t: datetime
    instrument: str
    decision: str     # NO_TRADE / a rule's reason (OWN_DECISION_REASONS) / ENGINE_ERROR / IN_TRADE / SETUP_ALREADY_ATTEMPTED / EXECUTE / SKIP
    reason: str
    grade: Optional[str]
    intent: Optional[OrderIntent] = None
    context: Optional[TradeContext] = None
    order_id: Optional[str] = None
    trade: Optional[ClosedTrade] = None
    time_window: Optional[str] = None   # the intent's ICT time window (e.g. NY_AM_KILLZONE)

    @property
    def setup_id(self) -> Optional[str]:
        return None if self.intent is None else self.intent.setup_id


@dataclass
class SimulationResult:
    journal: list[JournalRow]      # in (t, instrument) order
    trades: list[ClosedTrade]      # every order that closed, in closing order
    open_orders: list[SimTrade]    # still pending or open at the end
    account: SimAccount


class _SimClock:
    def __init__(self) -> None:
        self.now: Optional[datetime] = None

    def __call__(self) -> datetime:
        return self.now


def simulate(
    bars: Mapping[str, Sequence[Bar]],
    signals: Mapping[str, Sequence[SignalRecord]],
    specs: InstrumentSpecs,
    strategy: StrategyConfig,
    account_cfg: AccountSection,
    conversion: Optional[Conversion] = None,
    cost_flag_fraction: float = 0.25,
    on_step: Optional[Step] = None,
) -> SimulationResult:
    """Run the account over ``bars`` (each instrument's M1 fill bars, oldest
    first) and ``signals`` (each instrument's Phase A records, oldest first).
    ``on_step(t, broker, account)`` is called after each minute."""
    clock = _SimClock()
    broker = SimBroker(specs, clock, strategy.pending_expiry, strategy.fallback_ttl, conversion,
                       cost_flag_fraction=cost_flag_fraction)
    account = SimAccount(account_cfg.initial_equity, account_cfg.risk_per_trade, account_cfg.compounding)
    redis = fakeredis.FakeRedis(decode_responses=True)
    graph = AgentGraph(
        redis_client=redis, risk_engine=RiskEngine(redis), fcm_sender=None, broker_client=broker,
        trade_journal_collection=None, user_id=USER_ID, agent_decisions_collection=None,
        visual_model_client=None, algorag_client=None, clock=clock,
    )
    journal: list[JournalRow] = []
    attempted: set[str] = set()

    for t, events in _events(bars, signals):
        clock.now = t
        records = []
        for _, kind, instrument, item in events:
            if kind == _BAR:
                for trade in broker.advance(instrument, item):
                    account.book(trade)
            else:
                records.append(item)
        account.mark(t, broker.open_pnl(), broker.active_count())
        for record in records:
            journal.append(_decide(record, t, broker, account, graph, redis, attempted))
        if records:
            account.mark(t, broker.open_pnl(), broker.active_count())   # orders placed just now
        if on_step is not None:
            on_step(t, broker, account)

    trades = broker.closed_trades()
    by_order = {trade.order_id: trade for trade in trades}
    journal = [replace(row, trade=by_order.get(row.order_id)) if row.order_id else row for row in journal]
    return SimulationResult(journal=journal, trades=trades, open_orders=broker.active_trades(), account=account)


def _decide(record: SignalRecord, t: datetime, broker: SimBroker, account: SimAccount, graph: AgentGraph,
            redis: Any, attempted: set[str]) -> JournalRow:
    result = record.result
    if isinstance(result, EngineError):
        return JournalRow(record.t, record.instrument, "ENGINE_ERROR", f"{result.exception}: {result.message}", None)
    if isinstance(result, NoTrade):
        decision = result.reason if result.reason in OWN_DECISION_REASONS else "NO_TRADE"
        return JournalRow(record.t, record.instrument, decision, result.detail, result.grade)

    row = dict(t=record.t, instrument=record.instrument, grade=result.grade.value, intent=result,
               context=record.context, time_window=result.time_features.time_window)
    active = broker.active_trade(record.instrument)
    if active is not None:
        return JournalRow(**row, decision="IN_TRADE", reason=f"{active.order_id} is {active.status.lower()}")
    if result.setup_id in attempted:
        return JournalRow(**row, decision="SETUP_ALREADY_ATTEMPTED", reason="one attempt per setup (D6)")

    # Orders placed earlier at this t count towards the concurrent-trade limit.
    account.mark(t, broker.open_pnl(), broker.active_count())
    redis.set(_EXPOSURE_KEY, json.dumps(account.exposure()))
    state = graph.run(result.to_message(AgentMode.AUTONOMOUS))
    if state.broker_order_id is not None:
        attempted.add(result.setup_id)
    decision = state.decision.value if state.decision is not None else "NONE"
    return JournalRow(**row, decision=decision, reason=state.decision_reason or state.error or "",
                      order_id=state.broker_order_id)


def _events(bars: Mapping[str, Sequence[Bar]], signals: Mapping[str, Sequence[SignalRecord]]) -> Iterator:
    """(t, events at t), oldest first; at each t bars before signals, and
    instruments alphabetically within each."""
    streams = [_stream(instrument, _BAR, series, lambda b: b.timestamp + _M1) for instrument, series in bars.items()]
    streams += [_stream(instrument, _SIGNAL, records, lambda r: r.t) for instrument, records in signals.items()]
    return groupby(heapq.merge(*streams, key=lambda event: event[:3]), key=lambda event: event[0])


def _stream(instrument: str, kind: int, items: Iterable, time_of: Callable[[Any], datetime]) -> Iterator[tuple]:
    return ((time_of(item), kind, instrument, item) for item in items)
