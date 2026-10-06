"""Broker profiles: one broker account's venue, credentials, clock, symbols and costs.

The same strategy can be priced and traded at any broker without code
changes (.kiro/specs/algo-backtester, Requirement 10, task 215). A profile
lives in config/brokers/<name>.toml:

    venue = "mt5"
    spec_file = "config/instruments/exness-standard.toml"
    server_clock = "+0"          # "ny_close" or a fixed UTC offset in hours

    [credentials]                # names of environment variables, never values
    login = "MT5_LOGIN"
    password = "MT5_PASSWORD"
    server = "MT5_SERVER"
    path = "MT5_PATH"            # optional: terminal64.exe for this broker

    [symbols]                    # instrument -> broker symbol; unlisted map to themselves
    EURUSD = "EURUSDm"

Profiles are committed; the credential values stay in the git-ignored .env.
Loading rejects anything in [credentials] that isn't an environment variable
name, so a pasted login or password fails loudly instead of being committed.

A profile without spec_file is data-only: a source of candles (e.g. the
New York-close reference server for the aggregation-parity test) that is
never priced or traded.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from agent.instruments import VENUES, InstrumentSpecs, load_specs
from services.market_data.mt5_clock import MT5ClockMismatchError, MT5ServerClock

__all__ = ["BrokerProfile", "connect_mt5", "load_profile"]

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = Path("config") / "brokers"

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
_TOP_LEVEL = {"venue", "spec_file", "server_clock", "credentials", "symbols"}
_MT5_REQUIRED_CREDENTIALS = ("login", "password", "server")
_MT5_OPTIONAL_CREDENTIALS = ("path",)

GetEnv = Callable[[str], Optional[str]]


@dataclass(frozen=True)
class BrokerProfile:
    name: str
    venue: str
    spec_file: Optional[Path]  # None: data-only profile
    server_clock: Optional[str]
    credential_vars: Mapping[str, str]
    symbols: Mapping[str, str]

    def symbol(self, instrument: str) -> str:
        """The broker's symbol for ``instrument`` (e.g. EURUSD -> EURUSDm)."""
        return self.symbols.get(instrument, instrument)

    def clock(self) -> MT5ServerClock:
        if self.server_clock is None:
            raise ValueError(f"Profile {self.name!r} ({self.venue}) has no server clock")
        return MT5ServerClock(self.server_clock)

    def specs(self) -> InstrumentSpecs:
        if self.spec_file is None:
            raise ValueError(f"Profile {self.name!r} is data-only (no spec_file): it can't be priced or traded")
        specs = load_specs(self.spec_file)
        if specs.venue != self.venue:
            raise ValueError(
                f"Profile {self.name!r} is venue {self.venue!r} but {self.spec_file} is venue {specs.venue!r}"
            )
        return specs

    def credentials(self, getenv: Optional[GetEnv] = None) -> dict[str, str]:
        """Read the credential values from the environment (or .env) at call time."""
        getenv = getenv or _default_getenv()
        values, missing = {}, []
        for key, var in self.credential_vars.items():
            value = getenv(var)
            if value:
                values[key] = value
            elif key not in _MT5_OPTIONAL_CREDENTIALS:
                missing.append(var)
        if missing:
            raise ValueError(f"Profile {self.name!r}: environment variable(s) {missing} not set (add them to .env)")
        return values


def load_profile(name_or_path: str | Path, root: Path = REPO_ROOT) -> BrokerProfile:
    """Load ``config/brokers/<name>.toml`` under ``root``, or a profile file path."""
    path = Path(name_or_path)
    if path.suffix != ".toml":
        path = root / PROFILES_DIR / f"{name_or_path}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    name = path.stem

    unknown = sorted(set(data) - _TOP_LEVEL)
    if unknown:
        raise ValueError(f"{path}: unknown key(s) {unknown}")
    venue = data.get("venue")
    if venue not in VENUES:
        raise ValueError(f"{path}: venue must be one of {VENUES}, got {venue!r}")
    credential_vars = dict(data.get("credentials", {}))
    for key, var in credential_vars.items():
        if not isinstance(var, str) or not _ENV_NAME.match(var):
            raise ValueError(
                f"{path}: credentials.{key} must be an environment variable name like MT5_LOGIN, "
                f"not a value. Put the value in .env and name the variable here."
            )

    server_clock = data.get("server_clock")
    if venue == "mt5":
        if server_clock is None:
            raise ValueError(f"{path}: server_clock is required for MT5 profiles ('ny_close' or e.g. '+0')")
        MT5ServerClock(server_clock)  # validates the spec
        missing = [key for key in _MT5_REQUIRED_CREDENTIALS if key not in credential_vars]
        if missing:
            raise ValueError(f"{path}: MT5 profiles need credentials {missing}")
        unexpected = sorted(set(credential_vars) - {*_MT5_REQUIRED_CREDENTIALS, *_MT5_OPTIONAL_CREDENTIALS})
        if unexpected:
            raise ValueError(f"{path}: unknown credential key(s) {unexpected}")

    symbols = dict(data.get("symbols", {}))
    for instrument, symbol in symbols.items():
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(f"{path}: symbols.{instrument} must be a non-empty string")

    spec_file = Path(data["spec_file"]) if "spec_file" in data else None
    if spec_file is not None and not spec_file.is_absolute():
        spec_file = root / spec_file
    return BrokerProfile(
        name=name,
        venue=venue,
        spec_file=spec_file,
        server_clock=server_clock,
        credential_vars=credential_vars,
        symbols=symbols,
    )


def connect_mt5(
    profile: BrokerProfile,
    mt5: Any = None,
    getenv: Optional[GetEnv] = None,
    now: Optional[datetime] = None,
    attach: bool = False,
) -> Any:
    """Log in to the profile's MT5 account and verify its server clock (Req 10.6).

    With ``attach``, no login happens: the terminal keeps the account it is
    already logged into (no credentials needed, e.g. a demo opened in the
    terminal), and the clock check is what confirms it is this broker.

    Returns the connected MetaTrader5 module. Raises RuntimeError on a failed
    login and MT5ClockMismatchError (after shutting the connection down) when
    live ticks show a different server clock than the profile declares, since
    every bar time read afterwards would be shifted by the difference.
    """
    if profile.venue != "mt5":
        raise ValueError(f"Profile {profile.name!r} is venue {profile.venue!r}, not mt5")
    if mt5 is None:
        import MetaTrader5 as mt5  # Windows-only; imported lazily

    if attach:
        getenv = getenv or _default_getenv()
        path_var = profile.credential_vars.get("path")
        terminal = getenv(path_var) if path_var else None
        kwargs: dict[str, Any] = {"path": terminal} if terminal else {}
        target = "the logged-in terminal"
    else:
        credentials = profile.credentials(getenv)
        kwargs = {
            "login": int(credentials["login"]),
            "password": credentials["password"],
            "server": credentials["server"],
        }
        if credentials.get("path"):
            kwargs["path"] = credentials["path"]
        target = credentials["server"]
    if not mt5.initialize(**kwargs):
        code, desc = mt5.last_error()
        raise RuntimeError(f"MT5 login to {target} failed ({code}): {desc}")

    tick_times = []
    for symbol in profile.symbols.values():
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if tick is not None and tick.time:
            tick_times.append(tick.time)
    try:
        profile.clock().check(tick_times, now or datetime.now(timezone.utc))
    except MT5ClockMismatchError:
        mt5.shutdown()
        raise
    return mt5


def _default_getenv() -> GetEnv:
    """Process environment first, then the repo's .env (same precedence as python-decouple)."""
    env_file = REPO_ROOT / ".env"
    repository = None
    if env_file.exists():
        from decouple import Config, RepositoryEnv

        repository = Config(RepositoryEnv(str(env_file)))

    def getenv(name: str) -> Optional[str]:
        if name in os.environ:
            return os.environ[name]
        return repository(name, default=None) if repository else None

    return getenv
