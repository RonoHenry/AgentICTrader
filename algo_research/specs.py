"""Each research instrument's costs, from its own broker profile (update 2026-10f).

An instrument may come from another profile than the configuration's
(``ResearchConfig.profiles``, e.g. BTCUSDT from Binance): its spec is read from
that profile's spec file, and its costs are counted in that profile's account
currency. Binance's commission is a rate on USDT notional.

    specs = research_specs(cfg)
    specs["BTCUSDT"]                     # InstrumentSpec, from config/instruments/binance.toml
    specs.account_ccy("BTCUSDT")         # "USDT"

Validates: Requirement 22.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Iterator

from agent.broker_profiles import load_profile
from agent.instruments import InstrumentSpec, InstrumentSpecs
from algo_research.config import REPO_ROOT, ResearchConfig

__all__ = ["ResearchSpecs", "research_specs"]


class ResearchSpecs(Mapping):
    """Instrument -> InstrumentSpec, in the configuration's order, each with its profile's account currency."""

    def __init__(self, specs: Mapping[str, InstrumentSpec], account_ccys: Mapping[str, str]) -> None:
        self._specs, self._account_ccys = dict(specs), dict(account_ccys)

    def __getitem__(self, instrument: str) -> InstrumentSpec:
        return self._specs[instrument]

    def __iter__(self) -> Iterator[str]:
        return iter(self._specs)

    def __len__(self) -> int:
        return len(self._specs)

    def account_ccy(self, instrument: str) -> str:
        """The account currency ``instrument``'s costs are counted in."""
        return self._account_ccys[instrument]


def research_specs(cfg: ResearchConfig, root: Path = REPO_ROOT) -> ResearchSpecs:
    """Every studied instrument's spec, read from its own profile's spec file. An
    instrument missing from that file raises, before anything runs."""
    by_profile: dict[str, InstrumentSpecs] = {}
    for instrument in cfg.instruments:
        name = cfg.profile_of(instrument)
        if name not in by_profile:
            by_profile[name] = load_profile(name, root).specs()
    return ResearchSpecs({i: by_profile[cfg.profile_of(i)][i] for i in cfg.instruments},
                         {i: by_profile[cfg.profile_of(i)].account_ccy for i in cfg.instruments})
