"""The narrative's settings: frames, bias frame, direction rule, price basis.

Each is a proposed definition awaiting the trader (market-narrative ND-D6,
ND-D7, ND-D10), so each is a setting, read from
``config/research/narrative.toml`` (trading-method.md, section 9, rule 4).
Unknown keys and values are refused, naming the key.

Validates: Requirements 1.5, 2.1 (.kiro/specs/market-narrative/requirements.md)
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from liquidity_engine.models import Timeframe

__all__ = ["DEFAULT_PATH", "DIRECTION_RULES", "PRICE_RULES", "NarrativeConfig", "PriceBasis",
           "load_narrative_config"]

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "research" / "narrative.toml"
PRICE_RULES = ("NONE", "ROLLOVER_WINDOW")
DIRECTION_RULES = ("CLOSE_VS_OPEN",)          # ND-D6; DRAW_DELIVERED is stage 2
_KEYS = {"frames", "bias_frame", "direction_rule", "resamples", "price_basis"}
_BASIS_KEYS = {"rule", "minutes", "instruments"}


@dataclass(frozen=True)
class PriceBasis:
    """ND-D7: how the narrative's bars are priced (Requirement 2)."""
    rule: str = "ROLLOVER_WINDOW"
    minutes: int = 30                          # after 17:00 New York
    instruments: tuple[str, ...] = ("EURUSD", "GBPUSD", "USDJPY")

    def __post_init__(self) -> None:
        if self.rule not in PRICE_RULES:
            raise ValueError(f"price_basis.rule must be one of {PRICE_RULES}, not {self.rule!r}")
        if not 1 <= self.minutes <= 60:
            raise ValueError(f"price_basis.minutes must be 1-60, not {self.minutes}")


@dataclass(frozen=True)
class NarrativeConfig:
    frames: tuple[Timeframe, ...] = (Timeframe.W1, Timeframe.D1, Timeframe.H4)    # ND-D10
    bias_frame: Timeframe = Timeframe.D1
    direction_rule: str = "CLOSE_VS_OPEN"
    price_basis: PriceBasis = field(default_factory=PriceBasis)
    resamples: int = 2000                      # the autopsy split's bootstrap

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("frames must list at least one timeframe")
        if self.bias_frame not in self.frames:
            raise ValueError(f"bias_frame {self.bias_frame.value} must be one of the frames")
        if self.direction_rule not in DIRECTION_RULES:
            raise ValueError(f"direction_rule must be one of {DIRECTION_RULES}, not {self.direction_rule!r}")
        if self.resamples < 1:
            raise ValueError("resamples must be positive")


def _timeframe(key: str, value: Any) -> Timeframe:
    try:
        return Timeframe(value)
    except ValueError:
        raise ValueError(f"{key}: unknown timeframe {value!r}") from None


def _refuse_unknown(section: str, data: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"unknown key(s) in {section}: {', '.join(unknown)}")


def load_narrative_config(path: Optional[Path] = None) -> NarrativeConfig:
    """The settings from ``path``; with none, from config/research/narrative.toml
    when it exists, else the defaults."""
    if path is None:
        if not DEFAULT_PATH.is_file():
            return NarrativeConfig()
        path = DEFAULT_PATH
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    _refuse_unknown(str(path), data, _KEYS)
    basis = data.get("price_basis", {})
    _refuse_unknown("[price_basis]", basis, _BASIS_KEYS)
    defaults = NarrativeConfig()
    kwargs: dict[str, Any] = {}
    if "frames" in data:
        kwargs["frames"] = tuple(_timeframe("frames", v) for v in data["frames"])
    if "bias_frame" in data:
        kwargs["bias_frame"] = _timeframe("bias_frame", data["bias_frame"])
    for key in ("direction_rule", "resamples"):
        if key in data:
            kwargs[key] = data[key]
    kwargs["price_basis"] = PriceBasis(
        rule=basis.get("rule", defaults.price_basis.rule),
        minutes=basis.get("minutes", defaults.price_basis.minutes),
        instruments=tuple(basis.get("instruments", defaults.price_basis.instruments)),
    )
    return NarrativeConfig(**kwargs)
