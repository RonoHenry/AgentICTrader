"""Phase A: the engine's decision at every entry-timeframe close.

For each close t of an entry-timeframe bar in [start, end], the backtester
does what the live runner does when that bar closes: build the candle window
known at t (compose_as_of_view), run the real engine with t as its time, and
turn the graded setup into an order intent or a reason for no trade
(build_order_intent). Instruments are independent here, so they run in
parallel, one process each; Phase B then replays the records in time order
through the account.

    data = load_instrument(source, "EURUSD", start, end, cfg, clock, venue="mt5", max_gap_minutes=30)
    for record in generate_signals(data, cfg, start, end):
        record.t, record.result          # OrderIntent | NoTrade | EngineError

A failure inside the engine or the order logic is recorded as an EngineError
and counted, not raised: one bad bar mustn't end a year-long run.

Validates: Requirements 1.1, 2.1-2.6, 9.2 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterator, Mapping, Optional, Protocol, Sequence, Union

from agent.order_intent import NoTrade, OrderIntent, build_order_intent
from agent.strategy_config import StrategyConfig
from algo_backtester.data import InstrumentData
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Candle, Timeframe
from services.market_data.as_of_view import compose_as_of_view
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["EngineError", "SignalRecord", "entry_closes", "generate_all", "generate_signals", "signal_at"]

_CALENDAR = StrategyCalendar()
_M1 = timedelta(minutes=1)


class Engine(Protocol):
    def analyze(self, candles_by_tf: Mapping[Timeframe, Sequence[Candle]], instrument: str, timestamp: datetime) -> Any:
        ...


@dataclass(frozen=True)
class EngineError:
    exception: str   # the exception's type name
    message: str


@dataclass(frozen=True)
class SignalRecord:
    t: datetime
    instrument: str
    result: Union[OrderIntent, NoTrade, EngineError]


def entry_closes(data: InstrumentData, entry_tf: Timeframe, start: datetime, end: datetime) -> list[datetime]:
    """Closes of the entry-timeframe bars in [start, end] for which M1 exists."""
    last_close = data.m1[-1].timestamp + _M1 if data.m1 else start
    closes = (_CALENDAR.period_end(bar.timestamp, entry_tf) for bar in data.closed[entry_tf])
    return [t for t in closes if start <= t <= end and t <= last_close]


def signal_at(data: InstrumentData, cfg: StrategyConfig, t: datetime, engine: Optional[Engine] = None) -> SignalRecord:
    """The decision at t, from the data known at t only."""
    view = compose_as_of_view(data.closed, data.m1, t, cfg.entry_tf, cfg.candle_counts, _CALENDAR)
    try:
        liquidity_map = (engine or LiquidityMappingEngine()).analyze(view, data.instrument, t)
        result = build_order_intent(liquidity_map, view, data.instrument, t, cfg)
    except Exception as exc:
        result = EngineError(exception=type(exc).__name__, message=str(exc))
    return SignalRecord(t=t, instrument=data.instrument, result=result)


def generate_signals(data: InstrumentData, cfg: StrategyConfig, start: datetime, end: datetime,
                     engine: Optional[Engine] = None) -> Iterator[SignalRecord]:
    """One SignalRecord per entry-timeframe close in [start, end], oldest first."""
    engine = engine or LiquidityMappingEngine()  # stateless: one per instrument is enough
    for t in entry_closes(data, cfg.entry_tf, start, end):
        yield signal_at(data, cfg, t, engine)


def generate_all(datas: Sequence[InstrumentData], cfg: StrategyConfig, start: datetime, end: datetime,
                 workers: Optional[int] = None) -> dict[str, list[SignalRecord]]:
    """Phase A for every instrument, one process each (``workers=1``: in this
    process). Results are identical either way."""
    if workers == 1 or len(datas) <= 1:
        return {d.instrument: list(generate_signals(d, cfg, start, end)) for d in datas}
    with ProcessPoolExecutor(max_workers=min(workers or len(datas), len(datas))) as pool:
        futures = {d.instrument: pool.submit(_generate_list, d, cfg, start, end) for d in datas}
        return {instrument: future.result() for instrument, future in futures.items()}


def _generate_list(data: InstrumentData, cfg: StrategyConfig, start: datetime, end: datetime) -> list[SignalRecord]:
    return list(generate_signals(data, cfg, start, end))
