"""
Unit tests for services/nlp/calendar_monitor.py — Economic Calendar Blackout Monitor.

TDD Phase: RED → GREEN → REFACTOR
Run with: python -m pytest backend/tests/test_calendar_monitor.py -v --tb=short

All tests use mocks — no real DB or Redis connections required.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Import targets — will raise ImportError until implementation is written
# ---------------------------------------------------------------------------
from services.nlp.calendar_monitor import (
    CalendarMonitor,
    BlackoutState,
    blackout_key,
    INSTRUMENT_CURRENCIES,
    SUPPORTED_INSTRUMENTS,
    BLACKOUT_WINDOW_MINUTES,
    POLL_INTERVAL_SECONDS,
    TTL_BLACKOUT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_time: datetime,
    currency: str = "USD",
    event_name: str = "Non-Farm Payrolls",
    impact: str = "HIGH",
) -> dict:
    """Build a minimal event dict as returned by fetch_upcoming_high_impact_events."""
    return {
        "event_time": event_time,
        "currency": currency,
        "event_name": event_name,
        "impact": impact,
    }


def _make_monitor(**kwargs) -> CalendarMonitor:
    """Create a CalendarMonitor with default test params."""
    defaults = dict(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
        redis_host="localhost",
        redis_port=6379,
    )
    defaults.update(kwargs)
    return CalendarMonitor(**defaults)


# ===========================================================================
# 1. blackout_key format
# ===========================================================================

def test_blackout_key_format():
    """blackout_key('EURUSD') must return 'blackout:EURUSD'."""
    assert blackout_key("EURUSD") == "blackout:EURUSD"


# ===========================================================================
# 2–6. Instrument → currency mapping
# ===========================================================================

def test_instrument_currency_mapping_eurusd():
    """EURUSD maps to ['EUR', 'USD']."""
    assert INSTRUMENT_CURRENCIES["EURUSD"] == ["EUR", "USD"]


def test_instrument_currency_mapping_gbpusd():
    """GBPUSD maps to ['GBP', 'USD']."""
    assert INSTRUMENT_CURRENCIES["GBPUSD"] == ["GBP", "USD"]


def test_instrument_currency_mapping_us500():
    """US500 maps to ['USD']."""
    assert INSTRUMENT_CURRENCIES["US500"] == ["USD"]


def test_instrument_currency_mapping_xauusd():
    """XAUUSD maps to ['XAU', 'USD']."""
    assert INSTRUMENT_CURRENCIES["XAUUSD"] == ["XAU", "USD"]


def test_instrument_currency_mapping_btcusd():
    """BTCUSD maps to [] (no currency blackout)."""
    assert INSTRUMENT_CURRENCIES["BTCUSD"] == []


# ===========================================================================
# 7. Blackout active when event within 15 min BEFORE (event in future)
# ===========================================================================

def test_blackout_active_when_event_within_15min_before():
    """Event 10 min in the future → active=True."""
    monitor = _make_monitor()
    now = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)
    event_time = now + timedelta(minutes=10)
    events = [_make_event(event_time, currency="USD")]

    state = monitor.compute_blackout_state("EURUSD", events, now)

    assert state.active is True


# ===========================================================================
# 8. Blackout active when event within 15 min AFTER (event in past)
# ===========================================================================

def test_blackout_active_when_event_within_15min_after():
    """Event 10 min in the past → active=True."""
    monitor = _make_monitor()
    now = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)
    event_time = now - timedelta(minutes=10)
    events = [_make_event(event_time, currency="USD")]

    state = monitor.compute_blackout_state("EURUSD", events, now)

    assert state.active is True


# ===========================================================================
# 9. Blackout inactive when event outside window
# ===========================================================================

def test_blackout_inactive_when_event_outside_window():
    """Event 20 min away → active=False (outside ±15 min window)."""
    monitor = _make_monitor()
    now = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)
    event_time = now + timedelta(minutes=20)
    events = [_make_event(event_time, currency="USD")]

    state = monitor.compute_blackout_state("EURUSD", events, now)

    assert state.active is False


# ===========================================================================
# 10. Blackout inactive when no HIGH impact events
# ===========================================================================

def test_blackout_inactive_when_no_high_impact_events():
    """Empty events list → active=False."""
    monitor = _make_monitor()
    now = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)

    state = monitor.compute_blackout_state("EURUSD", [], now)

    assert state.active is False


# ===========================================================================
# 11. Blackout only triggers for HIGH impact
# ===========================================================================

def test_blackout_only_triggers_for_high_impact():
    """MEDIUM impact event within window → active=False (fetch_upcoming already filters HIGH).

    compute_blackout_state receives only HIGH events from the DB query.
    When events list is empty (no HIGH events), active must be False.
    """
    monitor = _make_monitor()
    now = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)

    # Simulate: no HIGH events were returned (MEDIUM was filtered by DB query)
    state = monitor.compute_blackout_state("EURUSD", [], now)

    assert state.active is False


# ===========================================================================
# 12. minutes_remaining positive for upcoming event
# ===========================================================================

def test_minutes_remaining_positive_for_upcoming_event():
    """Event 5 min in the future → minutes_remaining ≈ +5.0."""
    monitor = _make_monitor()
    now = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)
    event_time = now + timedelta(minutes=5)
    events = [_make_event(event_time)]

    state = monitor.compute_blackout_state("EURUSD", events, now)

    assert abs(state.minutes_remaining - 5.0) < 0.01


# ===========================================================================
# 13. minutes_remaining negative for past event
# ===========================================================================

def test_minutes_remaining_negative_for_past_event():
    """Event 5 min in the past → minutes_remaining ≈ -5.0."""
    monitor = _make_monitor()
    now = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)
    event_time = now - timedelta(minutes=5)
    events = [_make_event(event_time)]

    state = monitor.compute_blackout_state("EURUSD", events, now)

    assert abs(state.minutes_remaining - (-5.0)) < 0.01


# ===========================================================================
# 14. check_blackout queries correct time window
# ===========================================================================

@pytest.mark.asyncio
async def test_check_blackout_queries_correct_time_window():
    """fetch_upcoming_high_impact_events must query DB with ±15 min window."""
    monitor = _make_monitor()

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])

    async_ctx = AsyncMock()
    async_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    async_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=async_ctx)

    monitor._pool = mock_pool

    await monitor.fetch_upcoming_high_impact_events(["USD", "EUR"])

    mock_conn.fetch.assert_called_once()
    call_args = mock_conn.fetch.call_args
    sql = call_args[0][0]

    # SQL must reference the 15-minute window
    assert "15 minutes" in sql.lower() or "15" in sql
    assert "HIGH" in sql
    assert "impact" in sql.lower()


# ===========================================================================
# 15. publish_blackout_state sets Redis key
# ===========================================================================

@pytest.mark.asyncio
async def test_publish_blackout_state_sets_redis_key():
    """publish_blackout_state must call redis.set with key 'blackout:EURUSD'."""
    monitor = _make_monitor()
    mock_redis = AsyncMock()
    monitor._redis = mock_redis

    state = BlackoutState(
        instrument="EURUSD",
        active=True,
        event_name="Non-Farm Payrolls",
        minutes_remaining=5.0,
    )

    await monitor.publish_blackout_state(state)

    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    key = call_args[0][0]
    assert key == "blackout:EURUSD"


# ===========================================================================
# 16. publish_blackout_state sets TTL=120
# ===========================================================================

@pytest.mark.asyncio
async def test_publish_blackout_state_sets_ttl_120s():
    """publish_blackout_state must set TTL=120 on the Redis key."""
    monitor = _make_monitor()
    mock_redis = AsyncMock()
    monitor._redis = mock_redis

    state = BlackoutState(
        instrument="EURUSD",
        active=True,
        event_name="Non-Farm Payrolls",
        minutes_remaining=5.0,
    )

    await monitor.publish_blackout_state(state)

    call_kwargs = mock_redis.set.call_args[1]
    assert call_kwargs.get("ex") == 120


# ===========================================================================
# 17. publish inactive blackout when no events
# ===========================================================================

@pytest.mark.asyncio
async def test_publish_inactive_blackout_when_no_events():
    """When no HIGH events, check_instrument publishes active=False for the instrument."""
    monitor = _make_monitor()
    mock_redis = AsyncMock()
    monitor._redis = mock_redis

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])

    async_ctx = AsyncMock()
    async_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    async_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=async_ctx)
    monitor._pool = mock_pool

    now = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)
    state = await monitor.check_instrument("EURUSD", now)

    assert state.active is False
    mock_redis.set.assert_called_once()
    key = mock_redis.set.call_args[0][0]
    assert key == "blackout:EURUSD"
    value = json.loads(mock_redis.set.call_args[0][1])
    assert value["active"] is False


# ===========================================================================
# 18. run_once polls all instruments
# ===========================================================================

@pytest.mark.asyncio
async def test_run_once_polls_all_instruments():
    """run_once() must call check_instrument for every instrument in SUPPORTED_INSTRUMENTS."""
    monitor = _make_monitor()

    checked_instruments = []

    async def fake_check_instrument(instrument, now):
        checked_instruments.append(instrument)
        return BlackoutState(
            instrument=instrument,
            active=False,
            event_name="",
            minutes_remaining=0.0,
        )

    monitor.check_instrument = fake_check_instrument

    states = await monitor.run_once()

    assert set(checked_instruments) == set(SUPPORTED_INSTRUMENTS)
    assert len(states) == len(SUPPORTED_INSTRUMENTS)


# ===========================================================================
# 19. CalendarMonitor initialization
# ===========================================================================

def test_calendar_monitor_initialization():
    """Constructor must store db/redis config as instance attributes."""
    monitor = CalendarMonitor(
        db_host="db.example.com",
        db_port=5433,
        db_name="mydb",
        db_user="myuser",
        db_password="secret",
        redis_host="redis.example.com",
        redis_port=6380,
    )

    assert monitor._db_host == "db.example.com"
    assert monitor._db_port == 5433
    assert monitor._db_name == "mydb"
    assert monitor._db_user == "myuser"
    assert monitor._db_password == "secret"
    assert monitor._redis_host == "redis.example.com"
    assert monitor._redis_port == 6380


# ===========================================================================
# 20. connect() creates asyncpg pool
# ===========================================================================

@pytest.mark.asyncio
async def test_connect_creates_asyncpg_pool():
    """connect() must call asyncpg.create_pool with the configured DB params."""
    monitor = _make_monitor()

    with patch(
        "services.nlp.calendar_monitor.asyncpg.create_pool",
        new_callable=AsyncMock,
    ) as mock_create_pool, patch(
        "services.nlp.calendar_monitor.aioredis.Redis",
    ) as mock_redis_cls:
        mock_pool = AsyncMock()
        mock_create_pool.return_value = mock_pool
        mock_redis_cls.return_value = AsyncMock()

        await monitor.connect()

        mock_create_pool.assert_called_once()
        assert monitor._pool is mock_pool


# ===========================================================================
# 21. close() closes pool and redis
# ===========================================================================

@pytest.mark.asyncio
async def test_close_closes_pool_and_redis():
    """close() must call pool.close() and redis.aclose()."""
    monitor = _make_monitor()

    mock_pool = AsyncMock()
    mock_redis = AsyncMock()
    monitor._pool = mock_pool
    monitor._redis = mock_redis

    await monitor.close()

    mock_pool.close.assert_called_once()
    mock_redis.aclose.assert_called_once()


# ===========================================================================
# 22. Redis value contains event_name field
# ===========================================================================

@pytest.mark.asyncio
async def test_blackout_event_name_in_redis_value():
    """Redis value JSON must contain the event_name field."""
    monitor = _make_monitor()
    mock_redis = AsyncMock()
    monitor._redis = mock_redis

    state = BlackoutState(
        instrument="GBPUSD",
        active=True,
        event_name="UK GDP",
        minutes_remaining=3.5,
    )

    await monitor.publish_blackout_state(state)

    call_args = mock_redis.set.call_args
    value = json.loads(call_args[0][1])
    assert value["event_name"] == "UK GDP"
    assert value["active"] is True
    assert abs(value["minutes_remaining"] - 3.5) < 0.01


# ===========================================================================
# 23. Multiple events — uses nearest event
# ===========================================================================

def test_multiple_events_uses_nearest_event():
    """When 2 HIGH events are in window, use the one with smallest abs(minutes_remaining)."""
    monitor = _make_monitor()
    now = datetime(2026, 1, 15, 8, 30, 0, tzinfo=timezone.utc)

    # Event 1: 12 min in future
    event1 = _make_event(now + timedelta(minutes=12), event_name="NFP")
    # Event 2: 3 min in future (nearer)
    event2 = _make_event(now + timedelta(minutes=3), event_name="CPI")

    state = monitor.compute_blackout_state("EURUSD", [event1, event2], now)

    assert state.active is True
    assert state.event_name == "CPI"
    assert abs(state.minutes_remaining - 3.0) < 0.01
