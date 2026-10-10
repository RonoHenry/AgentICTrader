"""The engine's anticipation of each D1 candle, on every row of the candle.

The user's Power of 3 bias is tested as the engine implements it, not as a
copy (Requirement 4). For each instrument and trading date:

1. t_a is the candle's first M15 close at which one of its M1 bars has closed
   (17:15 New York for FX; later for gold, which stops 17:00-18:00), the
   first moment the engine has the candle's open;
2. the engine runs once, as Phase A runs it:
   ``compose_as_of_view(data.closed, data.m1, t_a, ...)`` then
   ``LiquidityMappingEngine().analyze(view, instrument, t_a).candle_profile``,
   with the backtester's base StrategyConfig;
3. the profile's anticipation (trend, direction, draw, draw above, draw
   below) is copied to every row of the candle from t_a on. Rows before t_a
   stay null: the anticipation reads the candle's open, not known before.

Liquidity-engine Property 35 makes the anticipation the same at every t in
the candle; a test checks it. An engine error, or no profile, leaves the
day null and is counted, not raised (Req 4.4).

Cost: one ``analyze()`` per instrument-day, about 400 days x 4 instruments x
~80 ms, about 2 minutes. Cached per instrument under a key over the data
fingerprint, ``engine_code_fingerprint()``, the StrategyConfig and the dates.

Validates: Requirements 4.1-4.4 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional, Protocol, Sequence

import pandas as pd

from agent.strategy_config import StrategyConfig
from algo_backtester.data import InstrumentData
from algo_research.features.cache import cache_key, code_fingerprint
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Candle, Objective, Timeframe
from services.market_data.as_of_view import compose_as_of_view
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["ANTICIPATION_COLUMNS", "ANTICIPATION_SOURCES", "anticipation_key", "daily_anticipation",
           "join_anticipation"]

ANTICIPATION_COLUMNS = (
    "ant_trend", "ant_direction",
    "ant_draw_price", "ant_draw_source", "ant_draw_tf",
    "ant_draw_above_price", "ant_draw_above_source", "ant_draw_above_tf",
    "ant_draw_below_price", "ant_draw_below_source", "ant_draw_below_tf",
)
ANTICIPATION_SOURCES = ("algo_research/features/anticipation.py",)

_CALENDAR = StrategyCalendar()


class Engine(Protocol):
    def analyze(self, candles_by_tf: Mapping[Timeframe, Sequence[Candle]], instrument: str,
                timestamp: datetime) -> Any:
        ...


def anticipation_key(instrument: str, data_sha256: str, engine_fingerprint: str, cfg: StrategyConfig,
                     dates: Sequence[str]) -> str:
    return cache_key("anticipation", instrument, data_sha256, engine_fingerprint, cfg.fingerprint(),
                     code_fingerprint(ANTICIPATION_SOURCES), list(dates))


def daily_anticipation(data: InstrumentData, market: pd.DataFrame, cfg: StrategyConfig,
                       engine: Optional[Engine] = None) -> tuple[pd.DataFrame, list[str]]:
    """One row per trading date of ``market`` (one instrument's market features):
    ``ant_at`` (t_a), the anticipation columns and ``error``, why a day has none.
    Also returns the errors, one message per day without an anticipation."""
    engine = engine or LiquidityMappingEngine()
    known = market[market["d1_open"].notna()]
    first = known.groupby("trading_date", sort=True)["t"].min()
    rows = []
    for trading_date in sorted(market["trading_date"].unique()):
        row = {"instrument": data.instrument, "trading_date": trading_date, "ant_at": first.get(trading_date, pd.NaT),
               **{name: None for name in ANTICIPATION_COLUMNS}, "error": None}
        rows.append(row)
        day = f"{data.instrument} {pd.Timestamp(trading_date).date()}"
        if pd.isna(row["ant_at"]):
            row["error"] = f"{day}: no M1 bar in the candle"
            continue
        t = row["ant_at"].to_pydatetime()
        try:
            view = compose_as_of_view(data.closed, data.m1, t, cfg.entry_tf, cfg.candle_counts, _CALENDAR)
            profile = engine.analyze(view, data.instrument, t).candle_profile
        except Exception as exc:
            row["error"] = f"{day}: {type(exc).__name__}: {exc}"
            continue
        if profile is None:
            row["error"] = f"{day}: the engine gave no candle profile"
        else:
            row.update(ant_trend=profile.trend.value, ant_direction=profile.direction.value,
                       **_objective("ant_draw", profile.draw), **_objective("ant_draw_above", profile.draw_above),
                       **_objective("ant_draw_below", profile.draw_below))
    daily = pd.DataFrame(rows, columns=["instrument", "trading_date", "ant_at", *ANTICIPATION_COLUMNS, "error"])
    for name in ANTICIPATION_COLUMNS:
        if name.endswith("_price"):
            daily[name] = daily[name].astype(float)
    return daily, daily["error"].dropna().tolist()


def _objective(prefix: str, objective: Optional[Objective]) -> dict:
    if objective is None:
        return {f"{prefix}_price": None, f"{prefix}_source": None, f"{prefix}_tf": None}
    return {f"{prefix}_price": objective.price, f"{prefix}_source": objective.source,
            f"{prefix}_tf": objective.timeframe.value}


def join_anticipation(market: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """``market`` with the anticipation columns: its candle's, from t_a on; null before."""
    joined = market.merge(daily[["instrument", "trading_date", "ant_at", *ANTICIPATION_COLUMNS]],
                          on=["instrument", "trading_date"], how="left", validate="many_to_one")
    early = ~(joined["t"] >= joined["ant_at"])            # before t_a, or no t_a at all
    for name in ANTICIPATION_COLUMNS:
        joined[name] = joined[name].astype(float if name.endswith("_price") else object)
        joined.loc[early, name] = None if not name.endswith("_price") else float("nan")
    joined.index = market.index
    return joined.drop(columns=["ant_at"])
