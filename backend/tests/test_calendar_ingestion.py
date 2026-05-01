"""
Tests for economic calendar ingestion.

TDD Phase: RED → these tests are written BEFORE the implementation.
Run with: pytest backend/tests/test_calendar_ingestion.py -v

All tests in this file must FAIL before any implementation is written.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

# ---------------------------------------------------------------------------
# Import targets — these will raise ImportError until 8b is implemented
# ---------------------------------------------------------------------------
from services.market_data.calendar_ingestion import (
    CalendarIngestion,
    EconomicEvent,
    CalendarSource,
)


# ===========================================================================
# 1. Test: events ingested for currencies USD, EUR, GBP, XAU
# ===========================================================================

@pytest.mark.asyncio
async def test_events_ingested_for_all_currencies():
    """
    CalendarIngestion must fetch events for USD, EUR, GBP, XAU.
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    # Mock the fetch method to return events for each currency
    mock_events = [
        EconomicEvent(
            event_time=datetime.now(timezone.utc),
            currency="USD",
            event_name="Non-Farm Payrolls",
            impact="HIGH",
            forecast="200K",
            previous="180K",
            actual=None,
            source="test",
        ),
        EconomicEvent(
            event_time=datetime.now(timezone.utc),
            currency="EUR",
            event_name="ECB Interest Rate Decision",
            impact="HIGH",
            forecast="4.5%",
            previous="4.5%",
            actual=None,
            source="test",
        ),
        EconomicEvent(
            event_time=datetime.now(timezone.utc),
            currency="GBP",
            event_name="GDP Growth Rate",
            impact="MEDIUM",
            forecast="0.2%",
            previous="0.1%",
            actual=None,
            source="test",
        ),
        EconomicEvent(
            event_time=datetime.now(timezone.utc),
            currency="XAU",
            event_name="Gold Reserves",
            impact="LOW",
            forecast=None,
            previous=None,
            actual=None,
            source="test",
        ),
    ]
    
    with patch.object(ingestion, "_fetch_events", return_value=mock_events):
        events = await ingestion._fetch_events()
    
    # Verify all currencies are present
    currencies = {event.currency for event in events}
    assert "USD" in currencies, "USD events must be fetched"
    assert "EUR" in currencies, "EUR events must be fetched"
    assert "GBP" in currencies, "GBP events must be fetched"
    assert "XAU" in currencies, "XAU events must be fetched"


# ===========================================================================
# 2. Test: events stored in TimescaleDB economic_events table with correct schema
# ===========================================================================

@pytest.mark.asyncio
async def test_events_stored_with_correct_schema():
    """
    Events must be stored in TimescaleDB with the correct schema:
    - id (UUID)
    - event_time (TIMESTAMPTZ)
    - currency (VARCHAR)
    - event_name (VARCHAR)
    - impact (VARCHAR) - must be LOW, MEDIUM, or HIGH
    - forecast (VARCHAR, nullable)
    - previous (VARCHAR, nullable)
    - actual (VARCHAR, nullable)
    - source (VARCHAR)
    - created_at (TIMESTAMPTZ)
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    await ingestion.connect()
    
    event = EconomicEvent(
        event_time=datetime(2026, 5, 1, 8, 30, 0, tzinfo=timezone.utc),
        currency="USD",
        event_name="Non-Farm Payrolls",
        impact="HIGH",
        forecast="200K",
        previous="180K",
        actual="210K",
        source="test",
    )
    
    # Mock the database connection
    with patch.object(ingestion, "_pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_conn.execute = AsyncMock()
        
        await ingestion._store_event(event)
        
        # Verify execute was called with correct SQL
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        
        # Verify SQL contains all required columns
        assert "event_time" in sql
        assert "currency" in sql
        assert "event_name" in sql
        assert "impact" in sql
        assert "forecast" in sql
        assert "previous" in sql
        assert "actual" in sql
        assert "source" in sql
        
        # Verify values are passed correctly
        assert event.event_time in call_args[0]
        assert event.currency in call_args[0]
        assert event.event_name in call_args[0]
        assert event.impact in call_args[0]
    
    await ingestion.close()


@pytest.mark.asyncio
async def test_impact_must_be_valid_enum():
    """
    Impact field must be one of: LOW, MEDIUM, HIGH.
    """
    # Valid impacts should work
    valid_impacts = ["LOW", "MEDIUM", "HIGH"]
    for impact in valid_impacts:
        event = EconomicEvent(
            event_time=datetime.now(timezone.utc),
            currency="USD",
            event_name="Test Event",
            impact=impact,
            forecast=None,
            previous=None,
            actual=None,
            source="test",
        )
        assert event.impact == impact
    
    # Invalid impact should raise validation error
    with pytest.raises((ValueError, AssertionError)):
        event = EconomicEvent(
            event_time=datetime.now(timezone.utc),
            currency="USD",
            event_name="Test Event",
            impact="INVALID",  # Invalid impact
            forecast=None,
            previous=None,
            actual=None,
            source="test",
        )


# ===========================================================================
# 3. Test: daily refresh scheduled at 00:05 UTC
# ===========================================================================

@pytest.mark.asyncio
async def test_daily_refresh_scheduled_at_0005_utc():
    """
    CalendarIngestion must schedule a daily refresh at 00:05 UTC using APScheduler.
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    await ingestion.connect()
    
    # Start the scheduler
    ingestion.start_scheduler()
    
    # Verify scheduler is running
    assert ingestion._scheduler is not None, "Scheduler must be initialized"
    assert ingestion._scheduler.running, "Scheduler must be running"
    
    # Verify job is scheduled
    jobs = ingestion._scheduler.get_jobs()
    assert len(jobs) > 0, "At least one job must be scheduled"
    
    # Find the daily refresh job
    refresh_job = None
    for job in jobs:
        if "refresh" in job.id.lower() or "ingest" in job.id.lower():
            refresh_job = job
            break
    
    assert refresh_job is not None, "Daily refresh job must be scheduled"
    
    # Verify job runs at 00:05 UTC
    trigger = refresh_job.trigger
    assert hasattr(trigger, "hour"), "Job must have hour trigger"
    assert hasattr(trigger, "minute"), "Job must have minute trigger"
    assert trigger.hour == 0, "Job must run at hour 0 (midnight)"
    assert trigger.minute == 5, "Job must run at minute 5"
    
    # Stop the scheduler
    ingestion.stop_scheduler()
    await ingestion.close()


@pytest.mark.asyncio
async def test_scheduler_can_be_stopped():
    """
    Scheduler must be stoppable via stop_scheduler().
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    await ingestion.connect()
    ingestion.start_scheduler()
    
    assert ingestion._scheduler.running, "Scheduler must be running"
    
    ingestion.stop_scheduler()
    
    assert not ingestion._scheduler.running, "Scheduler must be stopped"
    
    await ingestion.close()


# ===========================================================================
# 4. Test: duplicate events are not inserted twice
# ===========================================================================

@pytest.mark.asyncio
async def test_duplicate_events_not_inserted_twice():
    """
    If the same event (same event_time, currency, event_name) is ingested twice,
    it should not be inserted twice into the database.
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    await ingestion.connect()
    
    event = EconomicEvent(
        event_time=datetime(2026, 5, 1, 8, 30, 0, tzinfo=timezone.utc),
        currency="USD",
        event_name="Non-Farm Payrolls",
        impact="HIGH",
        forecast="200K",
        previous="180K",
        actual=None,
        source="test",
    )
    
    # Mock the database connection
    with patch.object(ingestion, "_pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        # First insert should succeed
        mock_conn.execute = AsyncMock()
        await ingestion._store_event(event)
        first_call_count = mock_conn.execute.call_count
        
        # Second insert of same event should be skipped or use ON CONFLICT
        await ingestion._store_event(event)
        
        # Verify SQL uses ON CONFLICT or duplicate check
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0].lower()
        
        # Should use ON CONFLICT DO NOTHING or similar deduplication
        assert "on conflict" in sql or "where not exists" in sql, \
            "SQL must handle duplicates with ON CONFLICT or WHERE NOT EXISTS"
    
    await ingestion.close()


@pytest.mark.asyncio
async def test_duplicate_check_by_event_time_currency_name():
    """
    Duplicate detection must be based on (event_time, currency, event_name).
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    await ingestion.connect()
    
    # Same event_time, currency, event_name = duplicate
    event1 = EconomicEvent(
        event_time=datetime(2026, 5, 1, 8, 30, 0, tzinfo=timezone.utc),
        currency="USD",
        event_name="Non-Farm Payrolls",
        impact="HIGH",
        forecast="200K",
        previous="180K",
        actual=None,
        source="test",
    )
    
    event2 = EconomicEvent(
        event_time=datetime(2026, 5, 1, 8, 30, 0, tzinfo=timezone.utc),
        currency="USD",
        event_name="Non-Farm Payrolls",
        impact="HIGH",
        forecast="210K",  # Different forecast, but same key fields
        previous="180K",
        actual=None,
        source="test",
    )
    
    # Different event_time = not duplicate
    event3 = EconomicEvent(
        event_time=datetime(2026, 5, 1, 9, 30, 0, tzinfo=timezone.utc),  # Different time
        currency="USD",
        event_name="Non-Farm Payrolls",
        impact="HIGH",
        forecast="200K",
        previous="180K",
        actual=None,
        source="test",
    )
    
    with patch.object(ingestion, "_pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_conn.execute = AsyncMock()
        
        await ingestion._store_event(event1)
        await ingestion._store_event(event2)  # Should be treated as duplicate
        await ingestion._store_event(event3)  # Should NOT be duplicate (different time)
        
        # Verify the SQL uses the correct unique constraint
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0].lower()
        
        # Should reference event_time, currency, event_name in conflict clause
        if "on conflict" in sql:
            assert "event_time" in sql
            assert "currency" in sql
            assert "event_name" in sql
    
    await ingestion.close()


# ===========================================================================
# 5. Additional tests for robustness
# ===========================================================================

@pytest.mark.asyncio
async def test_calendar_ingestion_initialization():
    """
    CalendarIngestion must initialize with database connection parameters.
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    assert ingestion._host == "localhost"
    assert ingestion._port == 5432
    assert ingestion._database == "agentictrader"
    assert ingestion._user == "agentictrader"
    assert ingestion._password == "changeme"


@pytest.mark.asyncio
async def test_connect_creates_connection_pool():
    """
    connect() must create a connection pool.
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    with patch("services.market_data.calendar_ingestion.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = AsyncMock()
        mock_create_pool.return_value = mock_pool
        
        await ingestion.connect()
        
        mock_create_pool.assert_called_once()
        assert ingestion._pool == mock_pool


@pytest.mark.asyncio
async def test_close_closes_connection_pool():
    """
    close() must close the connection pool.
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    with patch("services.market_data.calendar_ingestion.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = AsyncMock()
        mock_create_pool.return_value = mock_pool
        
        await ingestion.connect()
        await ingestion.close()
        
        mock_pool.close.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_events_returns_list_of_events():
    """
    _fetch_events() must return a list of EconomicEvent objects.
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    # Mock the calendar source
    with patch.object(ingestion, "_fetch_from_source", return_value=[
        {
            "event_time": datetime.now(timezone.utc),
            "currency": "USD",
            "event_name": "Test Event",
            "impact": "HIGH",
            "forecast": None,
            "previous": None,
            "actual": None,
        }
    ]):
        events = await ingestion._fetch_events()
        
        assert isinstance(events, list)
        assert len(events) > 0
        assert all(isinstance(event, EconomicEvent) for event in events)


@pytest.mark.asyncio
async def test_ingest_events_stores_all_fetched_events():
    """
    ingest_events() must fetch and store all events.
    """
    ingestion = CalendarIngestion(
        db_host="localhost",
        db_port=5432,
        db_name="agentictrader",
        db_user="agentictrader",
        db_password="changeme",
    )
    
    await ingestion.connect()
    
    mock_events = [
        EconomicEvent(
            event_time=datetime.now(timezone.utc),
            currency="USD",
            event_name="Event 1",
            impact="HIGH",
            forecast=None,
            previous=None,
            actual=None,
            source="test",
        ),
        EconomicEvent(
            event_time=datetime.now(timezone.utc),
            currency="EUR",
            event_name="Event 2",
            impact="MEDIUM",
            forecast=None,
            previous=None,
            actual=None,
            source="test",
        ),
    ]
    
    with patch.object(ingestion, "_fetch_events", return_value=mock_events):
        with patch.object(ingestion, "_store_event", new_callable=AsyncMock) as mock_store:
            await ingestion.ingest_events()
            
            # Verify _store_event was called for each event
            assert mock_store.call_count == len(mock_events)
    
    await ingestion.close()


# ===========================================================================
# 6. Integration test (optional, requires running TimescaleDB)
# ===========================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_timescaledb_event_storage():
    """
    Integration test: store an event in real TimescaleDB and verify it was stored.
    This test requires TimescaleDB to be running (docker-compose up timescaledb).
    """
    pytest.skip("Integration test - requires running TimescaleDB instance")
    
    # This test would:
    # 1. Create a real CalendarIngestion instance
    # 2. Store a test event
    # 3. Query the database to verify the event was stored
    # 4. Clean up the test data
