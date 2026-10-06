"""Run configuration, named variants, and the study hold-out.

A run is configured by a TOML file (config/backtests/base.toml); a variant is
a named set of dotted-key overrides on top of it (Req 7.1):

    [strategy]
    min_rr = 3.0

    [variants.min_rr_5]
    strategy.min_rr = 5.0

    cfg = load_run_config("config/backtests/base.toml", variant="min_rr_5")
    cfg.strategy        # the agent's StrategyConfig, validated the same way live is

Unknown keys are rejected everywhere, so a typo fails instead of silently
running the default.

A study groups the runs that compare variants. Its hold-out is set once, when
the study is first used, to the most recent 3 months of data (D7), and is
written to config/backtests/studies/<study>.toml so it never moves. A run
that reaches into the hold-out is refused unless it is the final validation
run (Req 7.2).

Validates: Requirements 7.1, 7.2 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import calendar
import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, field_validator, model_validator

from agent.strategy_config import StrategyConfig

__all__ = [
    "HOLDOUT_MONTHS",
    "HoldoutOverlapError",
    "RunConfig",
    "StudyConfig",
    "check_holdout",
    "load_or_create_study",
    "load_run_config",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
STUDIES_DIR = Path("config") / "backtests" / "studies"
HOLDOUT_MONTHS = 3  # D7
_STUDY_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class HoldoutOverlapError(ValueError):
    """A run reaches into its study's hold-out without being the final validation run."""


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RunSection(_Section):
    profile: str                         # broker profile: venue, specs, costs, symbols (D11)
    instruments: tuple[str, ...] = Field(min_length=1)
    start: date                          # [start, end), UTC days
    end: date
    study: str

    @field_validator("instruments")
    @classmethod
    def _uppercase(cls, instruments: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(i.upper() for i in instruments)

    @model_validator(mode="after")
    def _ordered(self) -> RunSection:
        if self.start >= self.end:
            raise ValueError(f"run.start {self.start} must be before run.end {self.end}")
        return self


class AccountSection(_Section):
    initial_equity: PositiveFloat = 10_000.0
    risk_per_trade: float = Field(default=0.01, gt=0, le=0.1)
    compounding: bool = False


class DataSection(_Section):
    max_gap_minutes: PositiveInt = 30    # outside weekends/holidays (Req 3.6)
    allow_gaps: bool = False


class ReportSection(_Section):
    min_trades: PositiveInt = 30         # D8
    cost_flag_fraction: float = Field(default=0.25, gt=0)   # Req 5.5
    bootstrap_resamples: int = Field(default=10_000, ge=100)


class RunConfig(_Section):
    run: RunSection
    account: AccountSection = AccountSection()
    strategy: StrategyConfig = StrategyConfig()
    data: DataSection = DataSection()
    report: ReportSection = ReportSection()
    variant: Optional[str] = None        # the variant applied, if any


class StudyConfig(_Section):
    name: str
    holdout_start: date                  # the hold-out is [holdout_start, end of data)
    created_from_data_end: date          # the data end the hold-out was derived from


def load_run_config(path: str | Path, variant: Optional[str] = None) -> RunConfig:
    """Load a run configuration, applying ``variant``'s overrides if given."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    variants = data.pop("variants", {})
    if variant is not None:
        if variant not in variants:
            raise ValueError(f"Unknown variant {variant!r} in {path}; available: {sorted(variants)}")
        data = _deep_merge(data, variants[variant])
    return RunConfig(**data, variant=variant)


def load_or_create_study(name: str, data_end: date, root: Path = REPO_ROOT) -> StudyConfig:
    """The study's settings; created on first use with the hold-out set to the
    last HOLDOUT_MONTHS months before ``data_end``, then never changed."""
    if not _STUDY_NAME.match(name):
        raise ValueError(f"Study name {name!r}: use lowercase letters, digits, '.', '_' or '-'")
    path = root / STUDIES_DIR / f"{name}.toml"
    if path.exists():
        return StudyConfig(name=name, **tomllib.loads(path.read_text(encoding="utf-8")))

    study = StudyConfig(name=name, holdout_start=_months_before(data_end, HOLDOUT_MONTHS),
                        created_from_data_end=data_end)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Study {name!r}. The hold-out is set once, when the study is first used (Req 7.2, D7):\n"
        f"# runs reaching into it are refused unless they are the final validation run.\n"
        f"holdout_start = {study.holdout_start.isoformat()}\n"
        f"created_from_data_end = {study.created_from_data_end.isoformat()}\n",
        encoding="utf-8",
    )
    return study


def check_holdout(cfg: RunConfig, study: StudyConfig, final: bool) -> None:
    """Refuse a run whose [start, end) reaches the hold-out, unless ``final``."""
    if cfg.run.study != study.name:
        raise ValueError(f"Run is configured for study {cfg.run.study!r}, not {study.name!r}")
    if cfg.run.end > study.holdout_start and not final:
        raise HoldoutOverlapError(
            f"Run {cfg.run.start} .. {cfg.run.end} reaches study {study.name!r}'s hold-out, "
            f"which starts {study.holdout_start}. End the run by then, or pass --final for the final validation run."
        )


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _months_before(day: date, months: int) -> date:
    years, month0 = divmod(day.month - 1 - months, 12)
    year, month = day.year + years, month0 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))
