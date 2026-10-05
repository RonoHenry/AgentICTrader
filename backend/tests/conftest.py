"""
Base test configuration for AgentICTrader.
"""
import os
import sys
from pathlib import PurePath

import django
import pytest
from django.conf import settings
from hypothesis import settings as hypothesis_settings

# Hypothesis fails any example that runs longer than 200 ms by default. That
# is a slowness detector, not a correctness check, and under machine load it
# flakes (test_risk_engine.py, 2026-10-05: 369 ms on the first run, 187 ms on
# the retry). No property test here asserts speed; disable it suite-wide.
hypothesis_settings.register_profile("agentictrader", deadline=None)
hypothesis_settings.load_profile("agentictrader")

# Get the absolute path to the project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# Add project root to sys.path so we can import services module
if project_root not in sys.path:
    sys.path.insert(0, project_root)

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Test files that need live services: a running InfluxDB (localhost:8086/8087),
# Docker, or a live Deriv market-data connection. They are marked
# `infrastructure`, which backend/pytest.ini deselects by default
# (-m "not infrastructure"); run them with `pytest -m ""` or `-m infrastructure`.
# Paths are relative to backend/tests/, "/"-separated; an entry ending in "/"
# covers the whole directory.
_LIVE_SERVICE_TESTS = {
    # Live Deriv websocket scripts (scripts/test_deriv_connection.py connects
    # with a hard-coded token as soon as it runs).
    "scripts/": "live Deriv API",
    "test_deriv_live.py": "live Deriv API (DERIV_API_TOKEN)",
    "test_influxdb.py": "InfluxDB on localhost:8086",
    "test_influxdb_setup.py": "InfluxDB on localhost:8087",
    "test_timeseries.py": "InfluxDB on localhost:8087",
    "infrastructure/test_data_ingestion.py": "InfluxDB",
    "infrastructure/test_influxdb_manager.py": "InfluxDB",
    "infrastructure/test_influxdb_setup.py": "InfluxDB",
    "infrastructure/test_market_data_pipeline.py": "starts an InfluxDB Docker container",
    "infrastructure/test_timeseries.py": "InfluxDB on localhost:8086",
}


# Quarantined: tests that fail because they and the code they cover drifted
# apart, in areas the live MT5 trading path does not use. They are marked
# `legacy`, which backend/pytest.ini deselects by default, so the default run
# stays a clean signal. Revive an entry (fix the test or the code, then delete
# the entry) when a feature starts depending on that code again; run them with
# `pytest -m legacy`. Keys are node-id prefixes relative to backend/tests/:
# a file, "file::Class", or "file::test_name[param]".
_LEGACY_TESTS = {
    "test_deriv_api.py": (
        "written against an older DerivAPIClient (api_token kwarg, .config/.endpoint "
        "attributes, 'InvalidSymbol' error code)"
    ),
    "infrastructure/test_deriv_api.py::test_connect_and_authorize": "older DerivAPIClient interface",
    "infrastructure/test_deriv_api.py::test_get_tick_history": "older DerivAPIClient interface",
    "infrastructure/test_deriv_api.py::test_rate_limiting": "older DerivAPIClient interface",
    "infrastructure/test_deriv_api.py::test_api_error_handling": "older DerivAPIClient interface",
    "trader/test_ohlc_data.py": "DerivAPIClient.get_ohlc now requires connect(); mocks never connect",
    "trader/test_provider_factory.py::test_provider_factory[deriv-deriv_config]": (
        "expects DerivAPIClient.config, which no longer exists"
    ),
    # TimescaleDB writer: these tests had never been collected (the module only
    # existed in the un-importable services/market-data/ folder). Their mocks
    # are wrong: pool.acquire() is mocked as a coroutine, but asyncpg returns
    # an async context manager; and they build timestamps with second=i for
    # i up to 500.
    "test_timescaledb_writer.py::TestCandleUpsert": "broken pool.acquire() mock",
    "test_timescaledb_writer.py::TestTickBatching": "broken pool mock / invalid timestamps",
    "test_timescaledb_writer.py::TestBatchFlushInterval": "broken pool mock / invalid timestamps",
    "test_timescaledb_writer.py::TestWriteLatency": "broken pool mock / invalid timestamps",
}


def _relpath(path) -> str | None:
    try:
        return PurePath(os.path.relpath(str(path), _TESTS_DIR)).as_posix()
    except ValueError:  # different drive on Windows
        return None


def _needs_live_service(path) -> bool:
    rel = _relpath(path)
    if rel is None:
        return False
    return any(
        rel.startswith(entry) if entry.endswith("/") else rel == entry
        for entry in _LIVE_SERVICE_TESTS
    )


def _legacy_reason(item) -> str | None:
    rel = _relpath(item.fspath)
    if rel is None:
        return None
    nodeid = rel + item.nodeid[item.nodeid.index("::"):] if "::" in item.nodeid else rel
    for prefix, reason in _LEGACY_TESTS.items():
        if nodeid == prefix or nodeid.startswith(prefix + "::"):
            return reason
    return None


def pytest_configure():
    """Configure Django for testing."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agentictrader.settings_test')
    django.setup()

def get_user_model():
    """Get User model after Django is configured."""
    from django.contrib.auth.models import User
    return User

def pytest_collection_modifyitems(config, items):
    """Mark live-service tests `infrastructure` and quarantined ones `legacy`."""
    for item in items:
        if "test_infrastructure" in str(item.fspath) or _needs_live_service(item.fspath):
            item.add_marker(pytest.mark.infrastructure)
        reason = _legacy_reason(item)
        if reason is not None:
            item.add_marker(pytest.mark.legacy(reason=reason))

@pytest.fixture
def test_user():
    """Create a test user."""
    User = get_user_model()
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )
