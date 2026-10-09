"""Hypotheses: a question written down, with its pass mark, before it runs.

A hypothesis is a TOML file ``config/research/hypotheses/H<nnn>-<slug>.toml``
(Requirement 8). It holds the question in words, the event and its filter,
the measure (and the trade, for races), the baselines, and the pass rules
with their minimum samples. It is validated in full before any data is read,
and every error names its field.

    h = load_hypothesis("config/research/hypotheses/H002-asia-raid-reclaim.toml")
    h.sha256                    # of the file's bytes, line endings normalised
    for test in h.tests():      # one per value of [vary], or one
        test.name, test.hypothesis

Measures and their statistics:

| ``measure.kind`` | statistics | reads |
|---|---|---|
| ``race`` | win_rate, mean_net_r, mean_gross_r | races |
| ``direction`` | accuracy, mean_move_atr | ``rem_move`` (or ``fwd_1h`` / ``fwd_4h``) |
| ``rate`` | rate (of a label condition ``of``, optionally ``given`` another) | labels |
| ``move`` | mean_move_atr of a label ``column``, signed by the event's direction | labels |

What the checks enforce:
- ``where`` reads feature columns, and the event's own direction, levels and
  attributes (Req 9.5); ``of`` / ``given`` read label columns only (Req 6.1,
  9.3);
- ``trade.time_limit = "event"`` only with an event that gives each row a
  limit (Req 15.3);
- candle labels (``day_dir``, ``day_*_final``, ``day_*_h4``) only with the
  ``daily`` event: asked at 09:00, the whole candle partly restates the past
  (Req 6.2);
- a race needs ``[trade]``, and nothing else may have one; a direction
  measure needs a directional event;
- each baseline fits the measure, and each rule's ``versus`` is a baseline in
  use, or ``best_naive`` when naive rules are;
- ``[vary]`` lists a few values for one parameter, each one test (Req 8.5).

Validates: Requirements 6.2, 8.1, 8.5, 9.5, 15.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import copy
import hashlib
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, PrivateAttr, ValidationError, model_validator

from algo_research.config import REPO_ROOT
from algo_research.events import EVENTS, FEATURE_NAMES, Event
from algo_research.features.market import COLUMNS
from algo_research.filters import FilterError, compile_filter
from algo_research.labels import CANDLE_LABELS, FORWARD_LABELS, LABEL_COLUMNS

__all__ = [
    "BASELINES",
    "HYPOTHESES_DIR",
    "NAIVE_RULES",
    "STATS",
    "Hypothesis",
    "HypothesisError",
    "Test",
    "file_sha256",
    "find_hypothesis",
    "load_hypothesis",
    "parse_hypothesis",
    "where_columns",
]

HYPOTHESES_DIR = REPO_ROOT / "config" / "research" / "hypotheses"

STATS = {
    "race": ("win_rate", "mean_net_r", "mean_gross_r"),
    "direction": ("accuracy", "mean_move_atr"),
    "rate": ("rate",),
    "move": ("mean_move_atr",),
}
NAIVE_RULES = ("always_long", "prev_day_dir", "w1_trend", "side_d1_open", "side_midnight_open")
BASELINES = {
    "race": ("coin_flip", "random_time"),
    "direction": ("random_time", *(f"naive:{r}" for r in NAIVE_RULES)),
    "move": ("random_time",),
    "rate": ("stratified", "shuffled_path"),
}
#: Baselines that judge only some statistics; the others judge every statistic of their measures.
BASELINE_STATS = {"coin_flip": ("win_rate",), "stratified": ("rate",), "shuffled_path": ("rate",)}
#: Candle labels the shuffled-path baseline recomputes from each shuffled day.
SHUFFLE_LABELS = frozenset(CANDLE_LABELS)
LEVEL_ALIASES = ("level_hit_after", "level_hit_at")
_PRICE_FEATURES = frozenset(name for name, column in COLUMNS.items() if column.unit == "price")
_ID = re.compile(r"^H\d{3}$")


class HypothesisError(ValueError):
    """An invalid hypothesis: the message names the field."""


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EventSection(_Section):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)
    where: str = ""                                      # a filter over feature columns


class LevelRef(_Section):
    kind: Literal["level", "atr", "r"]                   # a price column; value x atr_d1; value x the stop distance
    name: Optional[str] = None
    value: Optional[PositiveFloat] = None


class TimeLimit(_Section):
    minutes: PositiveInt


class TradeSection(_Section):
    direction: Literal["event", "LONG", "SHORT"] = "event"
    stop: LevelRef
    target: LevelRef
    time_limit: Union[Literal["day_close", "event"], TimeLimit] = "day_close"   # event: the event's own limit


class MeasureSection(_Section):
    kind: Literal["race", "direction", "rate", "move"]
    horizon: Literal["rem", "fwd_1h", "fwd_4h"] = "rem"  # direction: the move it is judged on
    of: Optional[str] = None                             # rate: a label condition
    given: Optional[str] = None                          # rate: the condition it is a rate among
    column: Optional[str] = None                         # move: a label column in ATR


class BaselinesSection(_Section):
    use: tuple[str, ...] = ()


class Rule(_Section):
    stat: str
    versus: Optional[str] = None                         # a baseline in use, best_naive, or none
    min_effect: float = 0.0


class PassSection(_Section):
    min_events: PositiveInt = 100                        # AR-D4
    min_days: PositiveInt = 60
    require: tuple[Rule, ...] = Field(min_length=1)


class Vary(_Section):
    key: str                                             # a dotted path, e.g. event.params.at
    values: tuple[Any, ...] = Field(min_length=2, max_length=6)
    names: Optional[tuple[str, ...]] = None              # required when the values are tables


class Hypothesis(_Section):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: str
    title: str
    statement: str
    family: str
    created: date
    slice: Literal["confirm"] = "confirm"                # official runs judge on the confirmation slice
    supersedes: Optional[str] = None
    event: EventSection
    measure: MeasureSection
    trade: Optional[TradeSection] = None
    baselines: BaselinesSection = Field(default_factory=BaselinesSection)
    pass_: PassSection = Field(alias="pass")
    vary: Optional[Vary] = None

    _path: Optional[Path] = PrivateAttr(default=None)
    _sha256: Optional[str] = PrivateAttr(default=None)

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @property
    def sha256(self) -> Optional[str]:
        return self._sha256

    @property
    def naive_rules(self) -> tuple[str, ...]:
        return tuple(b.split(":", 1)[1] for b in self.baselines.use if b.startswith("naive:"))

    @model_validator(mode="after")
    def _semantics(self) -> Hypothesis:
        problems = _problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def tests(self) -> list[Test]:
        """One test per value of ``vary`` (Req 8.5), or the hypothesis itself."""
        if self.vary is None:
            return [Test("", self, 0)]
        return [Test(name, _with_value(self, value), i) for i, (name, value) in enumerate(_vary_values(self.vary))]


@dataclass(frozen=True)
class Test:
    name: str                       # "" without [vary], else e.g. "at=05:00"
    hypothesis: Hypothesis
    index: int

    @property
    def label(self) -> str:
        return f"{self.hypothesis.id}[{self.name}]" if self.name else self.hypothesis.id


# ── checks ─────────────────────────────────────────────────────────────────

def _problems(h: Hypothesis) -> list[str]:
    problems: list[str] = []
    if not _ID.match(h.id):
        problems.append(f"id: {h.id!r} must be H followed by three digits, e.g. H007")
    if h.supersedes is not None and not _ID.match(h.supersedes):
        problems.append(f"supersedes: {h.supersedes!r} must be a hypothesis id like H007")

    event = EVENTS.get(h.event.name)
    if event is None:
        return [*problems, f"event.name: unknown event {h.event.name!r}; known: {sorted(EVENTS)}"]
    try:
        event.parse(h.event.params)
    except ValidationError as exc:
        for e in exc.errors():
            where = ".".join(str(p) for p in e["loc"])
            problems.append(f"event.params.{where}: {e['msg']}")
    directional = event.directional(h.event.params)
    labels = {name: "a label column" for name in LABEL_COLUMNS}
    try:
        compile_filter(h.event.where, where_columns(event), forbidden=labels)
    except FilterError as exc:
        problems.append(f"event.where: {exc}")

    kind = h.measure.kind
    if kind == "race":
        if h.trade is None:
            problems.append("trade: a race measure needs a [trade] table: direction, stop, target, time_limit")
        else:
            problems.extend(_trade_problems(h.trade, event, directional))
    elif h.trade is not None:
        problems.append(f"trade: only race measures have a [trade]; this measure is {kind}")
    if kind in ("direction", "move") and not directional:
        problems.append(f"measure.kind: a {kind} measure needs an event with a direction; "
                        f"{h.event.name} with these parameters has none")
    if kind == "rate":
        if not h.measure.of:
            problems.append("measure.of: a rate measure needs a label condition, e.g. of = \"pdh_hit_after\"")
        problems.extend(_label_problems(h, ("of", "given")))
    elif h.measure.of or h.measure.given:
        problems.append(f"measure.of: only rate measures have of / given; this measure is {kind}")
    if kind == "move":
        if h.measure.column not in FORWARD_LABELS and not (h.event.name == "daily" and h.measure.column in CANDLE_LABELS):
            problems.append(f"measure.column: {h.measure.column!r} must be a label column, e.g. rem_move_atr")

    allowed = BASELINES[kind]
    for baseline in h.baselines.use:
        if baseline not in allowed:
            problems.append(f"baselines.use: {baseline!r} doesn't fit a {kind} measure; use {list(allowed)}")
    if "stratified" in h.baselines.use:
        if h.event.name != "level_open":
            problems.append("baselines.use: stratified buckets by the distance to the event's level: use level_open")
        if h.measure.of not in ("level_hit_after", *(f"{lv}_hit_after" for lv in ("pdh", "pdl", "pwh", "pwl")))                or h.measure.given:
            problems.append("baselines.use: stratified compares the rate the event's level trades: "
                            "of = \"level_hit_after\", with no given")
    if "shuffled_path" in h.baselines.use:
        if h.event.name != "daily":
            problems.append("baselines.use: shuffled_path recomputes whole days: use the daily event")
        read = _label_columns(h)
        if not read <= SHUFFLE_LABELS:
            problems.append(f"baselines.use: shuffled_path recomputes only {sorted(SHUFFLE_LABELS)}, "
                            f"not {sorted(read - SHUFFLE_LABELS)}")

    for i, rule in enumerate(h.pass_.require):
        if rule.stat not in STATS[kind]:
            problems.append(f"pass.require[{i}].stat: {rule.stat!r} isn't a {kind} statistic; use {list(STATS[kind])}")
        if rule.versus == "best_naive":
            if not h.naive_rules:
                problems.append(f"pass.require[{i}].versus: best_naive needs naive:<rule> baselines in use")
        elif rule.versus is not None and rule.versus not in h.baselines.use:
            problems.append(f"pass.require[{i}].versus: {rule.versus!r} isn't a baseline in use {list(h.baselines.use)}")
        elif rule.versus in BASELINE_STATS and rule.stat not in BASELINE_STATS[rule.versus]:
            problems.append(f"pass.require[{i}].versus: {rule.versus} judges only {list(BASELINE_STATS[rule.versus])}, "
                            f"not {rule.stat}")

    if h.vary is not None and not problems:
        problems.extend(_vary_problems(h))
    return problems


def where_columns(event: Event) -> frozenset[str]:
    """What an event's ``where`` may read: the features and the event's own columns (Req 9.5)."""
    return FEATURE_NAMES | frozenset(event.columns)


def _trade_problems(trade: TradeSection, event: Event, directional: bool) -> list[str]:
    problems = []
    if trade.direction == "event" and not directional:
        problems.append("trade.direction: the event has no direction; set LONG or SHORT")
    if trade.time_limit == "event" and not event.limit:
        problems.append(f"trade.time_limit: the event {event.name} has no time limit of its own; "
                        f"use day_close or {{ minutes = ... }}")
    names = set(event.levels) | _PRICE_FEATURES
    for side in ("stop", "target"):
        ref: LevelRef = getattr(trade, side)
        if ref.kind == "level":
            if ref.name not in names:
                problems.append(f"trade.{side}.name: {ref.name!r} is not one of the event's levels {list(event.levels)} "
                                f"or a price feature")
            if ref.value is not None:
                problems.append(f"trade.{side}.value: a level stop or target takes a name, not a value")
        else:
            if ref.value is None:
                problems.append(f"trade.{side}.value: required for kind {ref.kind}")
            if ref.name is not None:
                problems.append(f"trade.{side}.name: kind {ref.kind} takes a value, not a name")
    if trade.stop.kind == "r":
        problems.append("trade.stop.kind: r is a multiple of the stop distance, so it can only set the target")
    return problems


def _label_names(h: Hypothesis) -> set[str]:
    names = set(LABEL_COLUMNS)
    if h.event.name == "level_open":
        names |= set(LEVEL_ALIASES)
    return names


def _label_problems(h: Hypothesis, fields: tuple[str, ...]) -> list[str]:
    problems = []
    features = {name: "a feature column: filter with event.where instead" for name in FEATURE_NAMES}
    for name in fields:
        expression = getattr(h.measure, name)
        if not expression:
            continue
        try:
            read = compile_filter(expression, _label_names(h), forbidden=features).columns
        except FilterError as exc:
            problems.append(f"measure.{name}: {exc}")
            continue
        leaks = sorted(read & set(CANDLE_LABELS))
        if leaks and h.event.name != "daily":
            problems.append(f"measure.{name}: {', '.join(leaks)} describe(s) the whole candle, bars before t "
                            f"included; candle labels need the daily event (Req 6.2)")
    return problems


def _label_columns(h: Hypothesis) -> set[str]:
    read = set()
    for expression in (h.measure.of, h.measure.given):
        if expression:
            try:
                read |= compile_filter(expression, _label_names(h)).columns
            except FilterError:
                pass
    return read


def _vary_values(vary: Vary) -> list[tuple[str, Any]]:
    leaf = vary.key.rsplit(".", 1)[-1]
    if vary.names is not None:
        return list(zip(vary.names, vary.values))
    return [(f"{leaf}={value}", value) for value in vary.values]


def _vary_problems(h: Hypothesis) -> list[str]:
    vary = h.vary
    data = h.model_dump(by_alias=True)
    node = data
    *parents, leaf = vary.key.split(".")
    for part in parents:
        node = node.get(part) if isinstance(node, dict) else None
    if not isinstance(node, dict) or leaf not in node:
        return [f"vary.key: {vary.key!r} isn't a value of this hypothesis"]
    if vary.names is not None and len(vary.names) != len(vary.values):
        return ["vary.names: one name per value"]
    if any(isinstance(v, dict) for v in vary.values) and vary.names is None:
        return ["vary.names: table values need names"]
    problems = []
    for name, value in _vary_values(vary):
        try:
            _with_value(h, value)
        except (ValidationError, ValueError) as exc:
            problems.append(f"vary.values: {name}: {_message(exc)}")
    return problems


def _with_value(h: Hypothesis, value: Any) -> Hypothesis:
    data = copy.deepcopy(h.model_dump(by_alias=True, exclude={"vary"}))
    *parents, leaf = h.vary.key.split(".")
    node = data
    for part in parents:
        node = node[part]
    node[leaf] = {**node[leaf], **value} if isinstance(value, dict) and isinstance(node[leaf], dict) else value
    test = Hypothesis.model_validate(data)
    test._path, test._sha256 = h._path, h._sha256
    return test


# ── loading ────────────────────────────────────────────────────────────────

def file_sha256(path: str | Path) -> str:
    """sha256 of the file's bytes with line endings normalised: Windows and Linux checkouts agree."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def parse_hypothesis(text: str) -> Hypothesis:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise HypothesisError(f"not valid TOML: {exc}") from None
    try:
        return Hypothesis.model_validate(data)
    except ValidationError as exc:
        raise HypothesisError(_message(exc)) from None


def load_hypothesis(path: str | Path) -> Hypothesis:
    path = Path(path)
    h = parse_hypothesis(path.read_text(encoding="utf-8"))
    if not (path.stem == h.id or path.stem.startswith(f"{h.id}-")):
        raise HypothesisError(f"file {path.name} holds id {h.id}: name it {h.id}-<slug>.toml")
    h._path, h._sha256 = path, file_sha256(path)
    return h


def find_hypothesis(hypothesis_id: str, root: Path = HYPOTHESES_DIR) -> Path:
    """The file of ``hypothesis_id`` (H<nnn>) under ``root``."""
    matches = sorted(Path(root).glob(f"{hypothesis_id}-*.toml")) + sorted(Path(root).glob(f"{hypothesis_id}.toml"))
    if not matches:
        raise HypothesisError(f"no hypothesis file {hypothesis_id}-<slug>.toml in {root}")
    if len(matches) > 1:
        raise HypothesisError(f"several files for {hypothesis_id}: {[m.name for m in matches]}")
    return matches[0]


def _message(exc: Exception) -> str:
    if not isinstance(exc, ValidationError):
        return str(exc)
    parts = []
    for error in exc.errors():
        where = ".".join(str(p) for p in error["loc"] if not str(p).startswith(("literal[", "function-")))
        message = error["msg"].removeprefix("Value error, ")
        parts.append(f"{where}: {message}" if where else message)
    return "; ".join(parts)

