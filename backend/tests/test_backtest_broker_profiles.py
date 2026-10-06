"""
Tests for agent/broker_profiles.py and the scripts that connect through it.

Task 215 (.kiro/specs/algo-backtester/tasks.md). No terminal, no network,
no real .env: credentials come from an injected getenv.
Validates: Requirements 10.1, 10.2, 10.3, 10.5, 10.6
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

import pytest

from agent.broker_profiles import BrokerProfile, connect_mt5, load_profile
from agent.instruments import CommissionSpec, InstrumentSpec, InstrumentSpecs, dumps_specs
from services.market_data.mt5_clock import MT5ClockMismatchError

ENV = {"MT5_LOGIN": "12345", "MT5_PASSWORD": "pw", "MT5_SERVER": "Broker-Demo"}


def _spec_file(tmp_path, venue="mt5"):
    spec = InstrumentSpec(
        symbol="EURUSD", venue=venue, point=0.00001, tick_size=0.00001, contract_size=100_000.0,
        volume_min=0.01, volume_step=0.01, volume_max=100.0, base_ccy="EUR", quote_ccy="USD",
        default_spread=0.00008, stop_slippage=0.00002,
        commission=CommissionSpec(kind="PER_LOT_PER_SIDE", value=0.0),
    )
    path = tmp_path / "specs.toml"
    path.write_text(dumps_specs(InstrumentSpecs(venue=venue, account_ccy="USD", specs={"EURUSD": spec})),
                    encoding="utf-8")
    return path


def _profile_file(tmp_path, body: Optional[str] = None, name="test-broker"):
    spec_path = _spec_file(tmp_path)
    if body is None:
        body = f'''
venue = "mt5"
spec_file = "{spec_path.as_posix()}"
server_clock = "+0"

[credentials]
login = "MT5_LOGIN"
password = "MT5_PASSWORD"
server = "MT5_SERVER"

[symbols]
EURUSD = "EURUSDm"
'''
    path = tmp_path / f"{name}.toml"
    path.write_text(body, encoding="utf-8")
    return path


# ── loading ────────────────────────────────────────────────────────────────

def test_load_profile_resolves_credentials_from_named_env_vars(tmp_path):
    profile = load_profile(_profile_file(tmp_path))
    assert profile.venue == "mt5"
    assert profile.credentials(getenv=ENV.get) == {"login": "12345", "password": "pw", "server": "Broker-Demo"}


def test_missing_credential_env_var_raises_naming_the_variable(tmp_path):
    profile = load_profile(_profile_file(tmp_path))
    with pytest.raises(ValueError, match="MT5_PASSWORD"):
        profile.credentials(getenv={"MT5_LOGIN": "1", "MT5_SERVER": "s"}.get)


def test_profile_file_never_contains_credential_values(tmp_path):
    # A login number (or any value) where an env-var name belongs must fail loudly:
    # profiles are committed, credentials must not be.
    body = _profile_file(tmp_path).read_text(encoding="utf-8").replace('login = "MT5_LOGIN"', 'login = "477461779"')
    with pytest.raises(ValueError, match="environment variable name"):
        load_profile(_profile_file(tmp_path, body))


@pytest.mark.parametrize("missing", ['server_clock = "+0"', 'password = "MT5_PASSWORD"'])
def test_mt5_profile_requires_clock_and_core_credentials(tmp_path, missing):
    body = _profile_file(tmp_path).read_text(encoding="utf-8").replace(missing, "")
    with pytest.raises(ValueError):
        load_profile(_profile_file(tmp_path, body))


def test_unknown_top_level_key_rejected(tmp_path):
    body = _profile_file(tmp_path).read_text(encoding="utf-8").replace('venue = "mt5"', 'venue = "mt5"\nsever_clock = "+2"')
    with pytest.raises(ValueError, match="sever_clock"):
        load_profile(_profile_file(tmp_path, body))


def test_symbol_map_resolves_and_defaults_to_instrument(tmp_path):
    profile = load_profile(_profile_file(tmp_path))
    assert profile.symbol("EURUSD") == "EURUSDm"
    assert profile.symbol("GBPUSD") == "GBPUSD"


def test_profile_loads_its_spec_file(tmp_path):
    profile = load_profile(_profile_file(tmp_path))
    specs = profile.specs()
    assert specs.venue == "mt5" and "EURUSD" in specs


def test_profile_clock_from_server_clock(tmp_path):
    profile = load_profile(_profile_file(tmp_path))
    assert profile.clock().spec == "+0"


def test_load_profile_by_name_from_config_brokers(tmp_path):
    brokers = tmp_path / "config" / "brokers"
    brokers.mkdir(parents=True)
    _profile_file(brokers, name="my-broker")
    profile = load_profile("my-broker", root=tmp_path)
    assert isinstance(profile, BrokerProfile) and profile.name == "my-broker"


@pytest.mark.parametrize("name, venue", [("exness-standard", "mt5"), ("binance", "binance")])
def test_committed_profiles_load(name, venue):
    profile = load_profile(name)
    assert profile.venue == venue
    assert profile.specs().venue == venue


def test_data_only_profile_has_no_spec_file(tmp_path):
    # A source of candles only (calendar test data), never priced or traded.
    body = "\n".join(
        line for line in _profile_file(tmp_path).read_text(encoding="utf-8").splitlines()
        if not line.startswith("spec_file")
    )
    profile = load_profile(_profile_file(tmp_path, body))
    assert profile.spec_file is None
    with pytest.raises(ValueError, match="data-only"):
        profile.specs()


def test_committed_metaquotes_profile_is_data_only_on_ny_close():
    # Task 186: the New York-close reference server for the aggregation-parity test.
    profile = load_profile("metaquotes-demo")
    assert (profile.venue, profile.server_clock, profile.spec_file) == ("mt5", "ny_close", None)
    # The connect-time clock check reads ticks from the listed symbols.
    assert {"EURUSD", "XAUUSD"} <= set(profile.symbols)


# ── connecting ─────────────────────────────────────────────────────────────

class FakeMT5:
    def __init__(self, tick_offset: timedelta, init_ok=True):
        self._tick_offset = tick_offset
        self._init_ok = init_ok
        self.init_kwargs = None
        self.shutdown_called = False

    def initialize(self, **kwargs):
        self.init_kwargs = kwargs
        return self._init_ok

    def last_error(self):
        return (-6, "Authorization failed")

    def symbol_select(self, symbol, enable):
        return True

    def symbol_info_tick(self, symbol):
        now = datetime.now(timezone.utc)
        return SimpleNamespace(time=int((now + self._tick_offset).timestamp()))

    def shutdown(self):
        self.shutdown_called = True


def test_mt5_connect_passes_credentials_and_verifies_clock(tmp_path):
    profile = load_profile(_profile_file(tmp_path))
    fake = FakeMT5(tick_offset=timedelta(0))  # server clock really is UTC+0
    assert connect_mt5(profile, mt5=fake, getenv=ENV.get) is fake
    assert fake.init_kwargs == {"login": 12345, "password": "pw", "server": "Broker-Demo"}
    assert not fake.shutdown_called


def test_mt5_connect_refuses_on_server_clock_mismatch(tmp_path):
    # Profile says UTC+0, but the terminal's ticks are stamped UTC+3.
    profile = load_profile(_profile_file(tmp_path))
    fake = FakeMT5(tick_offset=timedelta(hours=3))
    with pytest.raises(MT5ClockMismatchError):
        connect_mt5(profile, mt5=fake, getenv=ENV.get)
    assert fake.shutdown_called


def test_mt5_attach_uses_logged_in_terminal_and_still_verifies_clock(tmp_path):
    # attach=True: no login (no credentials needed), the terminal keeps the
    # account it is logged into, and the clock check still guards against
    # attaching to the wrong broker.
    profile = load_profile(_profile_file(tmp_path))
    fake = FakeMT5(tick_offset=timedelta(0))
    assert connect_mt5(profile, mt5=fake, getenv={}.get, attach=True) is fake
    assert fake.init_kwargs == {}

    wrong_broker = FakeMT5(tick_offset=timedelta(hours=3))
    with pytest.raises(MT5ClockMismatchError):
        connect_mt5(profile, mt5=wrong_broker, getenv={}.get, attach=True)
    assert wrong_broker.shutdown_called


def test_mt5_attach_passes_terminal_path_when_set(tmp_path):
    body = _profile_file(tmp_path).read_text(encoding="utf-8").replace(
        'server = "MT5_SERVER"', 'server = "MT5_SERVER"\npath = "MT5_PATH"')
    profile = load_profile(_profile_file(tmp_path, body))
    fake = FakeMT5(tick_offset=timedelta(0))
    connect_mt5(profile, mt5=fake, getenv={"MT5_PATH": "C:/MT5/terminal64.exe"}.get, attach=True)
    assert fake.init_kwargs == {"path": "C:/MT5/terminal64.exe"}


def test_mt5_connect_raises_on_failed_login(tmp_path):
    profile = load_profile(_profile_file(tmp_path))
    with pytest.raises(RuntimeError, match="Authorization failed"):
        connect_mt5(profile, mt5=FakeMT5(timedelta(0), init_ok=False), getenv=ENV.get)


# ── scripts accept --profile ───────────────────────────────────────────────

def test_export_script_accepts_profile(tmp_path, monkeypatch):
    from tests.test_backtest_export_specs import FakeMT5 as SpecsFakeMT5, _deal, _symbol_info
    from scripts import export_instrument_specs as export

    fake = SpecsFakeMT5(
        infos={"EURUSDm": _symbol_info()},
        deals=[_deal("EURUSDm", 1.0, -3.5), _deal("EURUSDm", 1.0, -3.5, type_=1)],
        spreads_points={"EURUSDm": [12]},
    )
    monkeypatch.setattr("agent.broker_profiles.connect_mt5", lambda profile: fake)
    out = tmp_path / "out.toml"

    assert export.main(["--profile", str(_profile_file(tmp_path)), "--instruments", "EURUSD", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert '["EURUSD"]' in text  # keyed by instrument, fetched as the broker's EURUSDm


def test_history_loader_accepts_profile(tmp_path, monkeypatch):
    import scripts.load_historical_data_mt5 as loader

    profile = load_profile(_profile_file(tmp_path))
    fetched = []

    def fake_fetch(symbol, instrument, timeframe, from_time, to_time, clock):
        fetched.append((symbol, instrument, clock.spec))
        return []

    monkeypatch.setattr("agent.broker_profiles.connect_mt5", lambda p: SimpleNamespace())
    monkeypatch.setattr(loader, "fetch_mt5_candles", fake_fetch)
    monkeypatch.setattr(loader, "mt5", SimpleNamespace(
        symbol_select=lambda symbol, enable: True,
        account_info=lambda: SimpleNamespace(server="Broker-Demo"),
        shutdown=lambda: None,
        last_error=lambda: (0, ""),
    ))

    asyncio.run(loader.load_all_data(["EURUSD"], ["M1"], 0.01, resume=False, dry_run=True, profile=profile))

    assert fetched == [("EURUSDm", "EURUSD", "+0")]
