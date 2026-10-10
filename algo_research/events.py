"""Events: named, tested conditions that select decision times.

An event takes the feature table and its parameters and returns event rows:
the feature row it fired on, t, the instrument and trading date, a direction
(LONG, SHORT or none) and the levels a trade may use (Requirement 9). It
reads feature columns only, of rows at or before its own t (Property 1), and
fires at most once per instrument, trading date and direction (Req 9.4).

| Event | Fires | Direction | Levels |
|---|---|---|---|
| ``anchor`` | the M15 close at ``at`` (New York), or with ``at = "open"`` each candle's first close with its D1 open known | from ``direction_from``, a fixed ``direction``, or none | with ``level = "draw"``: the engine's draw on its side, ``level``, ``level_name`` (update 2026-10e) |
| ``asia_raid_reclaim`` | the first M15 close back inside the Asian range, within ``reclaim_within`` closes of a raid of one side in ``window``, the other side untaken | LONG after a low raid, SHORT after a high raid | ``raid_extreme``, ``asia_opposite`` |
| ``level_open`` | at ``at``, when ``level`` is untaken | toward the level | ``level``, ``level_name`` |
| ``daily`` | the candle's last M15 close | none | - |
| ``crt`` | the M15 close equal to C2's close on ``tf`` (H1, H4, D1), when C2 swept one side of C1 and closed back inside | LONG after C1's low was swept, SHORT after its high | ``c2_extreme``, ``c1_opposite``; its own ``limit``: C3's close |

``asia_raid_reclaim`` and ``crt`` carry ``smt`` (Req 16.3): true when the
correlated partner did not take its own matching level by t (its Asian low,
or its C1's low, for LONG; the highs for SHORT), false when it did, None when
unknown or unpaired.

Rows an event can't use (no direction, no trend, a level already taken) are
skipped and counted in ``EventResult.skipped``.

Beyond its levels, an event may carry attributes (``Event.attributes``). A
hypothesis's ``where`` may read the event's direction, levels and attributes
as well as the features (Req 9.5): all are computed from the event's row.
An event with ``Event.limit`` gives each row its own race time limit
(``trade.time_limit = "event"``).

    result = run_event(features, "asia_raid_reclaim", {"window": ["01:00", "09:00"], "reclaim_within": 4})
    result.rows, result.skipped

Validates: Requirements 9.1, 9.2, 9.4, 9.5, 15.2, 16.3, 18.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError, field_validator, model_validator

from algo_research.features.anticipation import ANTICIPATION_COLUMNS
from algo_research.features.draws import DRAW_COLUMNS
from algo_research.features.market import COLUMNS
from algo_research.features.partner import PARTNER_COLUMNS
from algo_research.frame import close_times
from liquidity_engine.models import Timeframe

__all__ = ["EVENTS", "EVENT_COLUMNS", "Event", "EventError", "EventResult", "direction_of", "run_event"]

EVENT_COLUMNS = ("row", "t", "instrument", "trading_date", "direction")
FEATURE_NAMES = (frozenset(COLUMNS) | frozenset(ANTICIPATION_COLUMNS) | frozenset(DRAW_COLUMNS)
                 | frozenset(PARTNER_COLUMNS))

_LONG = {"UP", "BULLISH", "LONG"}
_SHORT = {"DOWN", "BEARISH", "SHORT"}
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class EventError(ValueError):
    """An unknown event, or parameters it doesn't accept."""


@dataclass
class EventResult:
    rows: pd.DataFrame                                   # EVENT_COLUMNS, then the event's levels
    skipped: dict[str, int] = field(default_factory=dict)


def _minutes(value: str) -> int:
    match = _HHMM.match(value)
    if not match:
        raise ValueError(f"{value!r} is not a New York time HH:MM")
    return int(match[1]) * 60 + int(match[2])


def _m15(value: str) -> str:
    if _minutes(value) % 15:
        raise ValueError(f"{value!r} is not an M15 close (minutes 00, 15, 30 or 45)")
    return value


class _Params(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AnchorParams(_Params):
    at: str
    direction_from: Optional[str] = None                 # a feature column
    direction: Optional[Literal["LONG", "SHORT"]] = None # or a fixed direction (update 2026-10e)
    level: Optional[Literal["draw"]] = None              # the engine's draw on each row's side (Req 18.3)

    @field_validator("at")
    @classmethod
    def _at(cls, value: str) -> str:
        return value if value == "open" else _m15(value)

    @model_validator(mode="after")
    def _direction(self) -> "AnchorParams":
        if self.direction is not None and self.direction_from is not None:
            raise ValueError("give a fixed direction or direction_from, not both")
        if self.level is not None and self.direction is None and self.direction_from is None:
            raise ValueError("level = \"draw\" needs a direction (or direction_from): the draw is on its side")
        return self

    @field_validator("direction_from")
    @classmethod
    def _feature(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in FEATURE_NAMES:
            raise ValueError(f"{value!r} is not a feature column")
        return value


class AsiaRaidReclaimParams(_Params):
    window: tuple[str, str] = ("01:00", "09:00")         # the raid bar's New York time, [start, end)
    reclaim_within: PositiveInt = 4                      # M15 closes from the raid's first

    @field_validator("window")
    @classmethod
    def _window(cls, value: tuple[str, str]) -> tuple[str, str]:
        start, end = (_minutes(v) for v in value)
        if not start < end:
            raise ValueError(f"window {value} must run forward within the trading day's New York clock")
        return value


class LevelOpenParams(_Params):
    level: Literal["pdh", "pdl", "pwh", "pwl", "trend"]
    at: str

    @field_validator("at")
    @classmethod
    def _at(cls, value: str) -> str:
        return _m15(value)


class DailyParams(_Params):
    pass


class CrtParams(_Params):
    tf: Literal["H1", "H4", "D1"]


@dataclass(frozen=True)
class Event:
    name: str
    params: type[_Params]
    run: Callable[[pd.DataFrame, Any], EventResult]
    levels: tuple[str, ...] = ()
    directional: Callable[[Mapping[str, Any]], bool] = lambda params: True
    attributes: tuple[str, ...] = ()                     # further columns `where` may read (Req 9.5)
    limit: bool = False                                  # its rows carry a race time limit, ``limit``

    def parse(self, params: Mapping[str, Any]) -> _Params:
        return self.params(**params)

    @property
    def columns(self) -> tuple[str, ...]:
        """The event's own columns that `where` may read, besides the features."""
        return ("direction", *self.levels, *self.attributes)

    @property
    def output(self) -> tuple[str, ...]:
        """Every column of its rows."""
        return (*EVENT_COLUMNS, *self.levels, *self.attributes, *(("limit",) if self.limit else ()))


def direction_of(values: pd.Series) -> np.ndarray:
    """LONG / SHORT / None from a column: +1, UP, BULLISH or LONG is LONG; their opposites SHORT."""
    out = np.full(len(values), None, dtype=object)
    for i, value in enumerate(values.to_numpy()):
        if isinstance(value, str):
            out[i] = "LONG" if value in _LONG else "SHORT" if value in _SHORT else None
        elif value is not None and not pd.isna(value) and not isinstance(value, (bool, np.bool_)):
            out[i] = "LONG" if value > 0 else "SHORT" if value < 0 else None
    return out


def _not_taken(features: pd.DataFrame, column: str) -> np.ndarray:
    """SMT per row: True when the partner hasn't taken its own level (``column`` false), False
    when it has, None when that isn't known or there is no partner column (Req 16.3)."""
    out = np.full(len(features), None, dtype=object)
    if column in features.columns:
        values = features[column]
        known = values.notna().to_numpy()
        out[known] = [not bool(v) for v in values[known]]
    return out


def _rows(features: pd.DataFrame, picked: np.ndarray, direction, **levels) -> pd.DataFrame:
    chosen = features[picked]
    out = chosen[["t", "instrument", "trading_date"]].reset_index(drop=True)
    out.insert(0, "row", chosen.index.to_numpy())
    out["direction"] = pd.Series(direction[picked] if isinstance(direction, np.ndarray)
                                 else [direction] * len(out), dtype=object)
    for name, values in levels.items():
        out[name] = values[picked] if isinstance(values, np.ndarray) else values
    return out


def _anchor_times(features: pd.DataFrame, at: str) -> np.ndarray:
    """The rows at ``at`` (New York), or with ``at = "open"`` each candle's first M15 close with its
    D1 open known: 17:15 for FX, after the daily break for gold, when the anticipation is known."""
    if at != "open":
        return features["ny_minute"].to_numpy() == _minutes(at)
    t = features["t"].where(features["d1_open"].notna())
    first = t.groupby([features["instrument"], features["trading_date"]]).transform("min")
    return (features["t"] == first).to_numpy()


def _anchor(features: pd.DataFrame, p: AnchorParams) -> EventResult:
    at = _anchor_times(features, p.at)
    if p.direction_from is not None:
        direction = direction_of(features[p.direction_from])
    elif p.direction is not None:
        direction = np.full(len(features), p.direction, dtype=object)
    else:
        return EventResult(_rows(features, at, None))
    has = direction != None                               # noqa: E711 - an object array
    skipped = {"no_direction": int((at & ~has).sum())} if p.direction_from is not None else {}
    if p.level is None:
        return EventResult(_rows(features, at & has, direction), skipped)
    # The engine's draw on each row's side (Req 18.3): above for LONG, below for SHORT.
    long = direction == "LONG"
    name = np.where(long, "ant_draw_above", "ant_draw_below").astype(object)
    price = np.where(long, features["ant_draw_above_price"].to_numpy(dtype=float),
                     features["ant_draw_below_price"].to_numpy(dtype=float))
    taken = np.where(long, features["ant_draw_above_taken_at"].notna().to_numpy(),
                     features["ant_draw_below_taken_at"].notna().to_numpy())
    known = ~np.isnan(price)
    base = at & has
    skipped.update({k: v for k, v in (("no_level", int((base & ~known).sum())),
                                      ("taken", int((base & known & taken).sum()))) if v})
    return EventResult(_rows(features, base & known & ~taken, direction, level=price, level_name=name), skipped)


def _asia_raid_reclaim(features: pd.DataFrame, p: AsiaRaidReclaimParams) -> EventResult:
    start, end = (_minutes(v) for v in p.window)
    keys = [features["instrument"].to_numpy(), features["trading_date"].to_numpy()]
    close = features["close"].to_numpy(dtype=float)
    frames = []
    for side, raided, other, level, extreme, opposite, direction in (
            ("low", "asia_low_raided_at", "asia_high_raided_at", "asia_low", "post_midnight_low", "asia_high", "LONG"),
            ("high", "asia_high_raided_at", "asia_low_raided_at", "asia_high", "post_midnight_high", "asia_low",
             "SHORT")):
        known = features[raided].notna().to_numpy()
        # Closes since the raid's first, counted within each instrument-day (a raid stays known once known).
        since = pd.Series(known.astype(int)).groupby(keys).cumsum().to_numpy() - 1
        raid_open = pd.DatetimeIndex(features[raided]) - pd.Timedelta(minutes=1)
        local = raid_open.tz_convert("America/New_York")
        raid_minute = np.where(known, local.hour * 60 + local.minute, -1)
        level_price = features[level].to_numpy(dtype=float)
        with np.errstate(invalid="ignore"):
            back_inside = close > level_price if side == "low" else close < level_price
        candidate = (known & (since < p.reclaim_within) & (raid_minute >= start) & (raid_minute < end)
                     & back_inside & features[other].isna().to_numpy())
        first = pd.Series(candidate).groupby(keys).cumsum().to_numpy() == 1
        picked = candidate & first
        frames.append(_rows(features, picked, direction, raid_extreme=features[extreme].to_numpy(dtype=float),
                            asia_opposite=features[opposite].to_numpy(dtype=float),
                            smt=_not_taken(features, f"partner_asia_{side}_raided")))
    rows = pd.concat(frames, ignore_index=True).sort_values(["instrument", "t", "direction"], kind="stable")
    return EventResult(rows.reset_index(drop=True))


_TOWARD = {"pdh": "LONG", "pwh": "LONG", "pdl": "SHORT", "pwl": "SHORT"}


def _level_open(features: pd.DataFrame, p: LevelOpenParams) -> EventResult:
    at = features["ny_minute"].to_numpy() == _minutes(p.at)
    if p.level == "trend":
        trend = features["w1_trend"].to_numpy()
        name = np.where(trend == "UP", "pdh", np.where(trend == "DOWN", "pdl", None)).astype(object)
    else:
        name = np.full(len(features), p.level, dtype=object)
    has_name = name != None                                # noqa: E711
    price = np.full(len(features), np.nan)
    untaken = np.zeros(len(features), dtype=bool)
    for level in _TOWARD:
        mine = name == level
        if not mine.any():
            continue
        price[mine] = features[level].to_numpy(dtype=float)[mine]
        untaken[mine] = features[f"{level}_taken_at"].isna().to_numpy()[mine] & ~np.isnan(price[mine])
    direction = np.array([_TOWARD.get(n) for n in name], dtype=object)
    picked = at & has_name & untaken
    skipped = {"no_trend": int((at & ~has_name).sum()), "taken": int((at & has_name & ~untaken).sum())}
    return EventResult(_rows(features, picked, direction, level=price, level_name=name),
                       {k: v for k, v in skipped.items() if v or p.level == "trend"})


def _daily(features: pd.DataFrame, p: DailyParams) -> EventResult:
    last = features.groupby(["instrument", "trading_date"], sort=False)["t"].transform("max")
    return EventResult(_rows(features, (features["t"] == last).to_numpy(), None))


def _crt(features: pd.DataFrame, p: CrtParams) -> EventResult:
    name, tf = p.tf.lower(), Timeframe(p.tf)
    t = pd.DatetimeIndex(features["t"])
    side = features[f"crt_{name}_side"].to_numpy(dtype=float)
    fires = (pd.DatetimeIndex(features[f"crt_{name}_at"]) == t) & np.isin(side, (1.0, -1.0))
    long = side == 1.0
    column = lambda which: features[f"crt_{name}_{which}"].to_numpy(dtype=float)         # noqa: E731
    smt = np.where(long, _not_taken(features, f"partner_crt_{name}_swept_low"),
                   _not_taken(features, f"partner_crt_{name}_swept_high"))
    rows = _rows(features, fires, np.where(long, "LONG", "SHORT").astype(object),
                 c2_extreme=np.where(long, column("c2_low"), column("c2_high")),
                 c1_opposite=np.where(long, column("c1_high"), column("c1_low")), smt=smt)
    rows["limit"] = close_times(pd.DatetimeIndex(rows["t"]), tf)       # C3 opens at C2's close
    return EventResult(rows)


EVENTS: dict[str, Event] = {
    "anchor": Event("anchor", AnchorParams, _anchor,
                    directional=lambda params: params.get("direction_from") is not None
                    or params.get("direction") is not None),
    "asia_raid_reclaim": Event("asia_raid_reclaim", AsiaRaidReclaimParams, _asia_raid_reclaim,
                               levels=("raid_extreme", "asia_opposite"), attributes=("smt",)),
    "level_open": Event("level_open", LevelOpenParams, _level_open, levels=("level",)),
    "daily": Event("daily", DailyParams, _daily, directional=lambda params: False),
    "crt": Event("crt", CrtParams, _crt, levels=("c2_extreme", "c1_opposite"), attributes=("smt",), limit=True),
}


def run_event(features: pd.DataFrame, name: str, params: Mapping[str, Any]) -> EventResult:
    event = EVENTS.get(name)
    if event is None:
        raise EventError(f"unknown event {name!r}; known: {sorted(EVENTS)}")
    try:
        parsed = event.parse(params)
    except ValidationError as exc:
        fields = ", ".join(".".join(str(p) for p in e["loc"]) or name for e in exc.errors())
        raise EventError(f"event {name}: invalid parameter(s) {fields}: {exc.errors()[0]['msg']}") from None
    if features.empty:
        return EventResult(pd.DataFrame(columns=list(event.output)))
    return event.run(features, parsed)
