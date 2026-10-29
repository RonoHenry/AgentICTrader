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
t (the entry array it chose, the draw on liquidity, the raid and protected
swing of its setup sequence, the killzone, the candle profile), so the run
report can draw each setup from the run's own records without re-running the
engine (Req 11.5, 11.6). No-trade records carry none, which keeps the cache
small.

Records are cached between runs (algo_backtester/cache.py) as JSON lines:
``record.to_json()`` and ``SignalRecord.from_json()`` restore a record
exactly, types included.

Validates: Requirements 1.1, 2.1-2.6, 9.2, 11.5, 11.6 (.kiro/specs/algo-backtester/requirements.md);
Requirements 19.5, 24.1 (.kiro/specs/liquidity-engine/requirements.md)
"""
from __future__ import annotations

import pickle
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Optional, Protocol, Sequence, Union

from agent.order_intent import NoTrade, OrderIntent, build_order_intent
from agent.strategy_config import StrategyConfig
from algo_backtester.data import InstrumentData
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import (
    Candle, CandleProfile, KillzoneWindow, LiquidityMap, Objective, SetupGrade, Timeframe,
)
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
    "generate_many",
    "generate_signals",
    "same_view",
    "signal_at",
    "signals_at",
    "chunks",
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
    swept_level: Optional[dict]        # the raided pool: side (BSL/SSL), source, timeframe, price, formed_at, raided_at
    protected_swing: Optional[dict]    # the bar the stop hides behind: wick, body, candle_at
    killzone: Optional[str]            # LONDON, NY_AM, NY_PM; None outside every killzone
    # The D1 candle's anticipation and what it had done by t (liquidity-engine Req 24.1); None
    # in runs recorded before update 2026-10b.
    candle_profile: Optional[dict] = None


def trade_context(liquidity_map: LiquidityMap, t: datetime) -> TradeContext:
    grade = liquidity_map.setup_grade
    array = next((a for a in liquidity_map.pd_arrays if grade and a.array_id == grade.entry_array_id), None)
    draw = liquidity_map.draw_on_liquidity
    sequence = liquidity_map.setup_sequence
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
        swept_level=None if sequence is None else {
            "side": sequence.raid.pool.side.value, "source": sequence.raid.pool.source.value,
            "timeframe": sequence.raid.pool.timeframe.value, "price": sequence.raid.pool.price,
            "formed_at": sequence.raid.pool.formed_at.isoformat(), "raided_at": sequence.raid.raided_at.isoformat(),
        },
        protected_swing=None if sequence is None else {
            "wick": sequence.protected_swing.wick, "body": sequence.protected_swing.body,
            "candle_at": sequence.protected_swing.candle_at.isoformat(),
        },
        killzone=None if killzone == KillzoneWindow.NONE else killzone.value,
        candle_profile=None if liquidity_map.candle_profile is None else _profile_context(liquidity_map.candle_profile),
    )


def _profile_context(p: CandleProfile) -> dict:
    def objective(o: Optional[Objective]) -> Optional[dict]:
        return None if o is None else {"kind": o.kind, "source": o.source, "timeframe": o.timeframe.value,
                                       "price": o.price}

    return {
        "open_time": p.open_time.isoformat(), "frame_open": p.frame_open, "midnight_open": p.midnight_open,
        "trend": p.trend.value, "direction": p.direction.value, "draw": objective(p.draw),
        "draw_above": objective(p.draw_above), "draw_below": objective(p.draw_below),
        "false_move_taken": p.false_move_taken, "asia_raided": p.asia_raided,
        "raid_in_window": p.raid_in_window, "weekday": p.weekday,
    }


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


def signal_at(data: InstrumentData, cfg: StrategyConfig, t: datetime, engine: Optional[Engine] = None,
              typical_spread: Optional[float] = None) -> SignalRecord:
    """The decision at t, from the data known at t only. ``typical_spread`` is the
    instrument's spec spread, for cfg.min_stop_spreads."""
    return signals_at(data, (cfg,), t, engine, typical_spread)[0]


def signals_at(data: InstrumentData, cfgs: Sequence[StrategyConfig], t: datetime, engine: Optional[Engine] = None,
               typical_spread: Optional[float] = None) -> list[SignalRecord]:
    """signal_at for each of ``cfgs``, which share one engine view (same_view): the
    engine analyses t once and each configuration's order rules read its map."""
    view = compose_as_of_view(data.closed, data.m1, t, cfgs[0].entry_tf, cfgs[0].candle_counts, _CALENDAR)
    try:
        engine = engine or LiquidityMappingEngine(cfgs[0].fvg_zone, cfgs[0].cisd, cfgs[0].ob_rule)
        liquidity_map = engine.analyze(view, data.instrument, t)
    except Exception as exc:
        error = EngineError(exception=type(exc).__name__, message=str(exc))
        return [SignalRecord(t=t, instrument=data.instrument, result=error, context=None) for _ in cfgs]
    records = []
    for cfg in cfgs:
        context = None
        try:
            result = build_order_intent(liquidity_map, view, data.instrument, t, cfg, typical_spread)
            if isinstance(result, OrderIntent):
                context = trade_context(liquidity_map, t)
        except Exception as exc:
            result = EngineError(exception=type(exc).__name__, message=str(exc))
        records.append(SignalRecord(t=t, instrument=data.instrument, result=result, context=context))
    return records


def same_view(cfgs: Sequence[StrategyConfig]) -> bool:
    """Whether the engine reads the same map under every one of ``cfgs``: its analysis reads the view and
    its own ``fvg_zone``, ``cisd`` and ``ob_rule`` (liquidity-engine Req 26, 30, 31), so those must match for
    them to share it (generate_many)."""
    return len({(c.entry_tf, tuple(sorted(c.candle_counts.items())), c.fvg_zone, c.cisd, c.ob_rule)
                for c in cfgs}) <= 1


def generate_signals(data: InstrumentData, cfg: StrategyConfig, start: datetime, end: datetime,
                     engine: Optional[Engine] = None, typical_spread: Optional[float] = None) -> Iterator[SignalRecord]:
    """One SignalRecord per entry-timeframe close in [start, end], oldest first."""
    engine = engine or LiquidityMappingEngine(cfg.fvg_zone, cfg.cisd, cfg.ob_rule)  # stateless: one per instrument
    for t in entry_closes(data, cfg.entry_tf, start, end):
        yield signal_at(data, cfg, t, engine, typical_spread)


#: Phase A works in chunks of entry closes, one per UTC day (task 302). Each chunk is
#: cached as soon as it is done, so a run that dies (a restart, a broken worker)
#: resumes where it stopped instead of starting over.
CHUNK_SECONDS = 86_400


def chunks(closes: Sequence[datetime]) -> list[list[datetime]]:
    """``closes``, in order, cut where the bar ending at t starts a new CHUNK_SECONDS period."""
    out: list[list[datetime]] = []
    current = None
    for t in closes:
        key = int((t - _M1).timestamp()) // CHUNK_SECONDS
        if key != current:
            out.append([])
            current = key
        out[-1].append(t)
    return out


def generate_all(datas: Sequence[InstrumentData], cfg: StrategyConfig, start: datetime, end: datetime,
                 workers: Optional[int] = None, cache: Optional[SignalCache] = None,
                 spreads: Optional[Mapping[str, float]] = None) -> dict[str, list[SignalRecord]]:
    """Phase A for every instrument (``workers=1``: in this process). Results are
    identical either way. ``spreads`` holds each instrument's typical spread, for
    cfg.min_stop_spreads.

    Each instrument's closes are cut into daily chunks (``chunks``), computed by
    up to ``workers`` processes and joined in order: the engine is stateless per
    close, so the records don't change, only the wall time.

    With a ``cache``, instruments it holds are served from it; the others are
    stored whole, one entry per instrument. While a run is going, each finished
    chunk is cached too, so a run that dies resumes from its finished chunks;
    they are removed once the instrument's entry is stored."""
    return generate_many(datas, (cfg,), start, end, workers, cache, spreads)[0]


def generate_many(datas: Sequence[InstrumentData], cfgs: Sequence[StrategyConfig], start: datetime, end: datetime,
                  workers: Optional[int] = None, cache: Optional[SignalCache] = None,
                  spreads: Optional[Mapping[str, float]] = None) -> list[dict[str, list[SignalRecord]]]:
    """generate_all for several configurations at once, in their order (task 298).

    The engine's analysis reads only its view of the candles, so configurations
    with the same view (same_view; e.g. variants that change only order rules)
    share one analyze() per close: the batch costs about one run's Phase A
    instead of one per configuration. Each configuration's records are exactly
    what generate_all gives it alone, cached under its own key."""
    cfgs = list(cfgs)
    if not same_view(cfgs):
        raise ValueError("generate_many needs configurations with the same entry_tf, candle_counts, fvg_zone, cisd "
                         "and ob_rule")
    spreads = spreads or {}
    keys = ({(d.instrument, k): cache.key(d, cfg, start, end, spreads.get(d.instrument))
             for d in datas for k, cfg in enumerate(cfgs)} if cache else {})
    hits = {ik: cache.load(key) for ik, key in keys.items()} if cache else {}
    missing = {d.instrument: [k for k in range(len(cfgs)) if hits.get((d.instrument, k)) is None] for d in datas}
    todo = [d for d in datas if missing[d.instrument]]
    computed: dict[tuple[str, int], list[SignalRecord]] = {}

    def keep(d: InstrumentData, per_cfg: list[list[SignalRecord]]) -> None:
        for k, records in zip(missing[d.instrument], per_cfg):
            computed[d.instrument, k] = cache.store(keys[d.instrument, k], records) if cache else records

    plan = {d.instrument: chunks(entry_closes(d, cfgs[0].entry_tf, start, end)) for d in todo}

    def part(d: InstrumentData, k: int, i: int) -> str:
        piece = plan[d.instrument][i]
        return cache.part_key(keys[d.instrument, k], piece[0], piece[-1], len(piece))

    done: dict[tuple[str, int], list[list[SignalRecord]]] = {}
    pending = []
    for d in todo:
        for i in range(len(plan[d.instrument])):
            stored = [cache.load(part(d, k, i)) for k in missing[d.instrument]] if cache else [None]
            if all(records is not None for records in stored):
                done[d.instrument, i] = stored
            else:
                pending.append((d, i))

    def finish(d: InstrumentData, i: int, per_cfg: list[list[SignalRecord]]) -> None:
        done[d.instrument, i] = per_cfg
        if cache:
            for k, records in zip(missing[d.instrument], per_cfg):
                cache.store(part(d, k, i), records)

    if workers == 1 or (workers is None and len(todo) <= 1) or not pending:
        for d, i in pending:
            finish(d, i, _generate_closes(d, [cfgs[k] for k in missing[d.instrument]], plan[d.instrument][i],
                                          spreads.get(d.instrument)))
    else:
        # Each worker reads an instrument's data from a file once and keeps it for its next
        # chunks, so the chunks themselves travel light.
        with tempfile.TemporaryDirectory(prefix="phase-a-") as tmp:
            paths = {}
            for d, _ in pending:
                if d.instrument not in paths:
                    paths[d.instrument] = str(Path(tmp) / f"{d.instrument}.pickle")
                    with open(paths[d.instrument], "wb") as fh:
                        pickle.dump(d, fh, protocol=pickle.HIGHEST_PROTOCOL)
            with ProcessPoolExecutor(max_workers=min(workers or len(todo), len(pending))) as pool:
                futures = {pool.submit(_generate_chunk, paths[d.instrument], [cfgs[k] for k in missing[d.instrument]],
                                       plan[d.instrument][i], spreads.get(d.instrument)): (d, i) for d, i in pending}
                for future in as_completed(futures):
                    finish(*futures[future], future.result())

    for d in todo:
        n = len(plan[d.instrument])
        keep(d, [[r for i in range(n) for r in done[d.instrument, i][j]] for j in range(len(missing[d.instrument]))])
        if cache:
            for i in range(n):
                for k in missing[d.instrument]:
                    cache.path(part(d, k, i)).unlink(missing_ok=True)
    return [{d.instrument: computed[d.instrument, k] if (d.instrument, k) in computed else hits[d.instrument, k]
             for d in datas} for k in range(len(cfgs))]


_LOADED: dict[str, InstrumentData] = {}       # in a worker: the instrument it last read


def _generate_chunk(path: str, cfgs: Sequence[StrategyConfig], closes: Sequence[datetime],
                    typical_spread: Optional[float] = None) -> list[list[SignalRecord]]:
    """_generate_closes in a worker, the instrument's data read from ``path`` once."""
    if path not in _LOADED:
        _LOADED.clear()                          # one instrument at a time keeps a worker's memory flat
        with open(path, "rb") as fh:
            _LOADED[path] = pickle.load(fh)
    return _generate_closes(_LOADED[path], cfgs, closes, typical_spread)


def _generate_closes(data: InstrumentData, cfgs: Sequence[StrategyConfig], closes: Sequence[datetime],
                     typical_spread: Optional[float] = None) -> list[list[SignalRecord]]:
    """One chunk of Phase A: per configuration, the records at ``closes``, in order."""
    engine = LiquidityMappingEngine(cfgs[0].fvg_zone, cfgs[0].cisd, cfgs[0].ob_rule)   # same_view(): one map for all
    per_cfg: list[list[SignalRecord]] = [[] for _ in cfgs]
    for t in closes:
        for records, record in zip(per_cfg, signals_at(data, cfgs, t, engine, typical_spread)):
            records.append(record)
    return per_cfg
