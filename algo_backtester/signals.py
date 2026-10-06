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

An order intent's record also carries a TradeContext: what the engine saw at
t (the entry array it chose, the draw on liquidity, the killzone), so the run
report can draw each setup from the run's own records without re-running the
engine (Req 11.5, 11.6). No-trade records carry none, which keeps the cache
small.

Records are cached between runs (algo_backtester/cache.py) as JSON lines:
``record.to_json()`` and ``SignalRecord.from_json()`` restore a record
exactly, types included.

Validates: Requirements 1.1, 2.1-2.6, 9.2, 11.5, 11.6 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Optional, Protocol, Sequence, Union

from agent.order_intent import NoTrade, OrderIntent, build_order_intent
from agent.strategy_config import StrategyConfig
from algo_backtester.data import InstrumentData
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Candle, KillzoneWindow, LiquidityMap, SetupGrade, Timeframe
from liquidity_engine.utils.time_utils import get_killzone
from ml.features.session_features import TimeFeatures
from services.market_data.as_of_view import compose_as_of_view
from services.market_data.strategy_calendar import StrategyCalendar

if TYPE_CHECKING:
    from algo_backtester.cache import SignalCache

__all__ = [
    "EngineError",
    "SignalRecord",
    "TradeContext",
    "entry_closes",
    "generate_all",
    "generate_signals",
    "signal_at",
    "trade_context",
]

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
class TradeContext:
    """A compact extract of the LiquidityMap at t, not the whole map. Values
    are JSON-ready (times as ISO strings), as the report draws them."""
    entry_array: Optional[dict]        # type, direction, timeframe, high, low, formed_at
    draw_on_liquidity: Optional[dict]  # type (BSL/SSL), source, price, formed_at
    swept_level: Optional[dict]        # the opposite-side raid; None until the grader records it
    killzone: Optional[str]            # LONDON, NY_AM, NY_PM; None outside every killzone


def trade_context(liquidity_map: LiquidityMap, t: datetime) -> TradeContext:
    grade = liquidity_map.setup_grade
    array = next((a for a in liquidity_map.pd_arrays if grade and a.array_id == grade.entry_array_id), None)
    draw = liquidity_map.draw_on_liquidity
    killzone = get_killzone(t)
    return TradeContext(
        entry_array=None if array is None else {
            "type": array.array_type.value, "direction": array.direction.value, "timeframe": array.timeframe.value,
            "high": array.high, "low": array.low, "formed_at": array.formed_at.isoformat(),
        },
        draw_on_liquidity=None if draw is None else {
            "type": draw.liquidity_type.value, "source": draw.source.value, "price": draw.price,
            "formed_at": draw.formed_at.isoformat(),
        },
        swept_level=None,
        killzone=None if killzone == KillzoneWindow.NONE else killzone.value,
    )


@dataclass(frozen=True)
class SignalRecord:
    t: datetime
    instrument: str
    result: Union[OrderIntent, NoTrade, EngineError]
    context: Optional[TradeContext] = None   # order intents only

    def to_json(self) -> dict:
        """Plain JSON values; from_json() gives back an equal record."""
        record = {"t": self.t.isoformat(), "instrument": self.instrument,
                  "result": {"kind": type(self.result).__name__, **_plain(self.result)}}
        if self.context is not None:
            record["context"] = _plain(self.context)
        return record

    @classmethod
    def from_json(cls, record: Mapping[str, Any]) -> SignalRecord:
        context = record.get("context")
        return cls(t=datetime.fromisoformat(record["t"]), instrument=record["instrument"],
                   result=_result_from_json(record["result"]),
                   context=None if context is None else TradeContext(**context))


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _result_from_json(result: Mapping[str, Any]) -> Union[OrderIntent, NoTrade, EngineError]:
    values = {k: v for k, v in result.items() if k != "kind"}
    kind = result["kind"]
    if kind == "OrderIntent":
        return OrderIntent(**{
            **values,
            "entry_tf": Timeframe(values["entry_tf"]),
            "as_of": datetime.fromisoformat(values["as_of"]),
            "grade": SetupGrade(values["grade"]),
            "time_features": TimeFeatures(**values["time_features"]),
            "patterns": tuple(values["patterns"]),
        })
    if kind == "NoTrade":
        return NoTrade(**{**values, "as_of": datetime.fromisoformat(values["as_of"])})
    if kind == "EngineError":
        return EngineError(**values)
    raise ValueError(f"unknown signal result kind {kind!r}")


def entry_closes(data: InstrumentData, entry_tf: Timeframe, start: datetime, end: datetime) -> list[datetime]:
    """Closes of the entry-timeframe bars in [start, end] for which M1 exists."""
    last_close = data.m1[-1].timestamp + _M1 if data.m1 else start
    closes = (_CALENDAR.period_end(bar.timestamp, entry_tf) for bar in data.closed[entry_tf])
    return [t for t in closes if start <= t <= end and t <= last_close]


def signal_at(data: InstrumentData, cfg: StrategyConfig, t: datetime, engine: Optional[Engine] = None) -> SignalRecord:
    """The decision at t, from the data known at t only."""
    view = compose_as_of_view(data.closed, data.m1, t, cfg.entry_tf, cfg.candle_counts, _CALENDAR)
    context = None
    try:
        liquidity_map = (engine or LiquidityMappingEngine()).analyze(view, data.instrument, t)
        result = build_order_intent(liquidity_map, view, data.instrument, t, cfg)
        if isinstance(result, OrderIntent):
            context = trade_context(liquidity_map, t)
    except Exception as exc:
        result = EngineError(exception=type(exc).__name__, message=str(exc))
    return SignalRecord(t=t, instrument=data.instrument, result=result, context=context)


def generate_signals(data: InstrumentData, cfg: StrategyConfig, start: datetime, end: datetime,
                     engine: Optional[Engine] = None) -> Iterator[SignalRecord]:
    """One SignalRecord per entry-timeframe close in [start, end], oldest first."""
    engine = engine or LiquidityMappingEngine()  # stateless: one per instrument is enough
    for t in entry_closes(data, cfg.entry_tf, start, end):
        yield signal_at(data, cfg, t, engine)


def generate_all(datas: Sequence[InstrumentData], cfg: StrategyConfig, start: datetime, end: datetime,
                 workers: Optional[int] = None, cache: Optional[SignalCache] = None) -> dict[str, list[SignalRecord]]:
    """Phase A for every instrument, one process each (``workers=1``: in this
    process). Results are identical either way.

    With a ``cache``, instruments it holds are served from it; the others are
    computed and stored by their worker."""
    hits = {d.instrument: cache.load(cache.key(d, cfg, start, end)) for d in datas} if cache else {}
    todo = [d for d in datas if hits.get(d.instrument) is None]
    if workers == 1 or len(todo) <= 1:
        computed = {d.instrument: _generate_list(d, cfg, start, end, cache) for d in todo}
    else:
        with ProcessPoolExecutor(max_workers=min(workers or len(todo), len(todo))) as pool:
            futures = {d.instrument: pool.submit(_generate_list, d, cfg, start, end, cache) for d in todo}
            computed = {instrument: future.result() for instrument, future in futures.items()}
    return {d.instrument: computed[d.instrument] if d.instrument in computed else hits[d.instrument] for d in datas}


def _generate_list(data: InstrumentData, cfg: StrategyConfig, start: datetime, end: datetime,
                   cache: Optional[SignalCache] = None) -> list[SignalRecord]:
    records = generate_signals(data, cfg, start, end)
    return cache.store(cache.key(data, cfg, start, end), records) if cache else list(records)
