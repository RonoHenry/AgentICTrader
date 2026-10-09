"""ResearchConfig: what AlgoResearch studies, and the slices that keep it honest.

config/research/research.toml names the broker profile, the study, the
instruments and the research period, split in two (AR-D3):

- the exploration slice, for building and debugging questions (`explore`);
- the confirmation slice, which judges them (`run`).

The period ends where the study's hold-out begins. The hold-out start is
read from the study (config/backtests/studies/<study>.toml), never set here,
and a slice reaching past it is refused (Property 10): the hold-out belongs
to the backtester's final run.

Slices are made of whole trading dates. A trading date is the New York date
of the D1 candle, which opens at 17:00 New York the day before (Sunday 17:00
belongs to Monday), so a slice runs from 17:00 New York on the eve of its
first date to 17:00 on the eve of its end. The research period therefore
ends before the hold-out's first trading date even begins.

    cfg = load_research_config()                   # config/research/research.toml
    cfg.slice_of(t)                                # "explore", "confirm" or None
    cfg.strategy()                                 # the StrategyConfig Phase A uses
    cfg.smt.partners                               # {"EURUSD": "GBPUSD", ...}: SMT pairs (update 2026-10c)

Validates: Requirements 13.1, 13.2, 16.1 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import tomllib
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError, field_validator, model_validator

from agent.strategy_config import StrategyConfig
from algo_backtester.config import STUDIES_DIR, RunConfig, StudyConfig, load_run_config
from liquidity_engine.utils.time_utils import to_est, trading_day_open

__all__ = [
    "CONFIG_PATH",
    "REPO_ROOT",
    "SLICES",
    "HoldoutError",
    "ResearchConfig",
    "SmtSection",
    "load_research_config",
    "trading_date",
    "trading_date_open",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path("config") / "research" / "research.toml"
SLICES = ("explore", "confirm")

_NY = ZoneInfo("America/New_York")
_DAY_OPEN = time(17, 0)


class HoldoutError(ValueError):
    """A period that reaches the study's hold-out (Property 10)."""


def trading_date(t: datetime) -> date:
    """The New York date of the D1 candle containing ``t``: the candle opens at
    17:00 New York, so Sunday 17:00 belongs to Monday."""
    return to_est(trading_day_open(t)).date() + timedelta(days=1)


def trading_date_open(day: date) -> datetime:
    """The UTC instant trading date ``day`` opens: 17:00 New York the day before."""
    return datetime.combine(day - timedelta(days=1), _DAY_OPEN, tzinfo=_NY).astimezone(timezone.utc)


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Slices(_Section):
    explore: tuple[date, date]   # [first trading date, end), AR-D3
    confirm: tuple[date, date]


class BootstrapSection(_Section):
    resamples: int = Field(default=10_000, ge=100)   # AR-D5


class BaselinesSection(_Section):
    random_time_draws: PositiveInt = 20              # AR-D7
    shuffles: PositiveInt = 200                      # shuffled-path baseline


class SmtSection(_Section):
    pairs: tuple[tuple[str, str], ...] = ()          # correlated instruments, for SMT divergence (AR-D12)

    @field_validator("pairs")
    @classmethod
    def _uppercase(cls, pairs: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
        return tuple((a.upper(), b.upper()) for a, b in pairs)

    @property
    def partners(self) -> dict[str, str]:
        """Each paired instrument's partner, both ways."""
        return {**{a: b for a, b in self.pairs}, **{b: a for a, b in self.pairs}}


class ResearchConfig(_Section):
    profile: str                                     # broker profile: candle source and spec file (costs)
    study: str                                       # its holdout_start ends the research period
    instruments: tuple[str, ...] = Field(min_length=1)
    start: date                                      # the first trading date studied
    snapshot: str                                    # data/research/snapshots/<snapshot>/
    run_config: str = "config/backtests/base.toml"   # its [strategy] and [data] are Phase A's
    slices: Slices
    bootstrap: BootstrapSection = Field(default_factory=BootstrapSection)
    baselines: BaselinesSection = Field(default_factory=BaselinesSection)
    smt: SmtSection = Field(default_factory=SmtSection)
    holdout_start: date                              # from the study file, not research.toml

    @field_validator("instruments")
    @classmethod
    def _uppercase(cls, instruments: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(i.upper() for i in instruments)

    @model_validator(mode="after")
    def _pairs(self) -> ResearchConfig:
        seen: set[str] = set()
        for a, b in self.smt.pairs:
            if a == b:
                raise ValueError(f"smt.pairs: {a} can't be paired with itself")
            for instrument in (a, b):
                if instrument not in self.instruments:
                    raise ValueError(f"smt.pairs: {instrument} is not one of the instruments {list(self.instruments)}")
                if instrument in seen:
                    raise ValueError(f"smt.pairs: {instrument} is in two pairs")
                seen.add(instrument)
        return self

    @model_validator(mode="after")
    def _contiguous(self) -> ResearchConfig:
        explore, confirm = self.slices.explore, self.slices.confirm
        if confirm[1] > self.holdout_start:
            raise HoldoutError(f"slice confirm ends {confirm[1]}, inside study {self.study!r}'s hold-out "
                               f"(holdout_start {self.holdout_start}); research never reads the hold-out")
        if explore[0] != self.start:
            raise ValueError(f"slice explore starts {explore[0]}, not at start {self.start}")
        if not explore[0] < explore[1]:
            raise ValueError(f"slice explore {explore[0]} .. {explore[1]} is empty or backwards")
        if confirm[0] != explore[1]:
            raise ValueError(f"slice confirm starts {confirm[0]}, but explore ends {explore[1]}: "
                             f"slices must be contiguous, with no gap or overlap")
        if not confirm[0] < confirm[1]:
            raise ValueError(f"slice confirm {confirm[0]} .. {confirm[1]} is empty or backwards")
        if confirm[1] != self.holdout_start:
            raise ValueError(f"slice confirm ends {confirm[1]}; it must end at study {self.study!r}'s "
                             f"holdout_start {self.holdout_start}")
        return self

    # ── periods ────────────────────────────────────────────────────────────

    @property
    def period(self) -> tuple[datetime, datetime]:
        """The research period as UTC instants [start, end): from the open of the
        first trading date to the open of the hold-out's first trading date."""
        return trading_date_open(self.start), trading_date_open(self.holdout_start)

    def slice_period(self, name: str) -> tuple[datetime, datetime]:
        if name not in SLICES:
            raise ValueError(f"unknown slice {name!r}; expected one of {SLICES}")
        first, end = getattr(self.slices, name)
        return trading_date_open(first), trading_date_open(end)

    def slice_of(self, t: datetime) -> Optional[str]:
        """The slice of the trading date containing ``t``, or None outside the research period."""
        day = trading_date(t)
        for name in SLICES:
            first, end = getattr(self.slices, name)
            if first <= day < end:
                return name
        return None

    def check_end(self, end: date) -> None:
        """Refuse a period ending after the hold-out start, before any data is read."""
        if end > self.holdout_start:
            raise HoldoutError(f"a period ending {end} reaches study {self.study!r}'s hold-out, which starts "
                               f"{self.holdout_start}; research never reads the hold-out")

    # ── the backtester's settings ──────────────────────────────────────────

    def run(self, root: Path = REPO_ROOT) -> RunConfig:
        return load_run_config(root / self.run_config)

    def strategy(self, root: Path = REPO_ROOT) -> StrategyConfig:
        """The StrategyConfig Phase A uses: candle windows, entry timeframe."""
        return self.run(root).strategy


def load_research_config(path: Optional[Path] = None, root: Path = REPO_ROOT) -> ResearchConfig:
    """Load ``path`` (default config/research/research.toml under ``root``), with the
    hold-out start read from its study."""
    path = Path(path) if path is not None else root / CONFIG_PATH
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    study_path = root / STUDIES_DIR / f"{data.get('study')}.toml"
    if not study_path.is_file():
        raise FileNotFoundError(f"study {data.get('study')!r} has no {study_path}: create it with "
                                f"`python -m algo_backtester check-data` first, which sets its hold-out")
    study = StudyConfig(name=data["study"], **tomllib.loads(study_path.read_text(encoding="utf-8")))
    if "holdout_start" in data:
        raise ValueError(f"{path}: holdout_start comes from the study, not research.toml")
    try:
        return ResearchConfig(**data, holdout_start=study.holdout_start)
    except ValidationError as exc:
        # Surface a HoldoutError raised inside validation as itself.
        for error in exc.errors():
            if isinstance(error.get("ctx", {}).get("error"), HoldoutError):
                raise error["ctx"]["error"] from None
        raise
