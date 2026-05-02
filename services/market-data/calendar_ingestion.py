"""
Economic calendar ingestion for AgentICTrader.

This module provides async ingestion of economic calendar events from external sources
(ForexFactory RSS or Investing.com API) and stores them in TimescaleDB.

Features:
- Fetches events for USD, EUR, GBP, XAU currencies
- Validates impact levels (LOW, MEDIUM, HIGH)
- Prevents duplicate event insertion using ON CONFLICT
- Schedules daily refresh at 00:05 UTC via APScheduler
- Connection pooling for performance
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


class CalendarSource(Enum):
    """Supported calendar data sources."""
    FOREXFACTORY = "forexfactory"
    INVESTING_COM = "investing_com"


@dataclass
class EconomicEvent:
    """
    Represents a single economic calendar event.
    
    Attributes:
        event_time: When the event occurs (TIMESTAMPTZ)
        currency: Currency code (USD, EUR, GBP, XAU)
        event_name: Name of the economic event
        impact: Impact level - must be LOW, MEDIUM, or HIGH
        forecast: Forecasted value (optional)
        previous: Previous value (optional)
        actual: Actual value (optional, filled after event)
        source: Data source identifier
    """
    event_time: datetime
    currency: str
    event_name: str
    impact: str
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    source: str = "forexfactory"
    
    def __post_init__(self):
        """Validate impact level after initialization."""
        valid_impacts = {"LOW", "MEDIUM", "HIGH"}
        if self.impact not in valid_impacts:
            raise ValueError(
                f"Invalid impact level: {self.impact}. "
                f"Must be one of {valid_impacts}"
            )


class CalendarIngestion:
    """
    Async ingestion of economic calendar events into TimescaleDB.
    
    Features:
    - Fetches events for USD, EUR, GBP, XAU
    - Stores events with ON CONFLICT handling for duplicates
    - Schedules daily refresh at 00:05 UTC
    - Connection pooling for performance
    """
    
    # Supported currencies
    SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "XAU"]
    
    def __init__(
        self,
        db_host: str,
        db_port: int,
        db_name: str,
        db_user: str,
        db_password: str,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
        source: CalendarSource = CalendarSource.FOREXFACTORY,
    ):
        """
        Initialize the calendar ingestion service.
        
        Args:
            db_host: Database host
            db_port: Database port
            db_name: Database name
            db_user: Database user
            db_password: Database password
            min_pool_size: Minimum connection pool size
            max_pool_size: Maximum connection pool size
            source: Calendar data source
        """
        self._host = db_host
        self._port = db_port
        self._database = db_name
        self._user = db_user
        self._password = db_password
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size
        self._source = source
        
        self._pool: Optional[asyncpg.Pool] = None
        self._scheduler: Optional[AsyncIOScheduler] = None
    
    async def connect(self) -> None:
        """Create the connection pool."""
        self._pool = await asyncpg.create_pool(
            host=self._host,
            port=self._port,
            database=self._database,
            user=self._user,
            password=self._password,
            min_size=self._min_pool_size,
            max_size=self._max_pool_size,
        )
    
    async def close(self) -> None:
        """Close the connection pool and stop scheduler if running."""
        if self._scheduler and self._scheduler.running:
            self.stop_scheduler()
        
        if self._pool:
            await self._pool.close()
    
    async def _fetch_events(self) -> List[EconomicEvent]:
        """
        Fetch economic events from the configured source.
        
        Returns:
            List of EconomicEvent objects for supported currencies
        """
        # For testing, check if _fetch_from_source returns data
        test_data = await self._fetch_from_source()
        if test_data:
            # Convert test data to EconomicEvent objects
            events = []
            for data in test_data:
                event = EconomicEvent(
                    event_time=data["event_time"],
                    currency=data["currency"],
                    event_name=data["event_name"],
                    impact=data["impact"],
                    forecast=data.get("forecast"),
                    previous=data.get("previous"),
                    actual=data.get("actual"),
                    source="test",
                )
                events.append(event)
            return events
        
        # Production path: fetch from configured source
        if self._source == CalendarSource.FOREXFACTORY:
            return await self._fetch_from_forexfactory()
        elif self._source == CalendarSource.INVESTING_COM:
            return await self._fetch_from_investing_com()
        else:
            return []
    
    async def _fetch_from_forexfactory(self) -> List[EconomicEvent]:
        """
        Fetch events from ForexFactory RSS feed.
        
        This is a placeholder implementation. In production, this would:
        1. Fetch the ForexFactory RSS feed
        2. Parse XML to extract events
        3. Filter for supported currencies (USD, EUR, GBP, XAU)
        4. Map impact levels to LOW/MEDIUM/HIGH
        5. Return list of EconomicEvent objects
        """
        # Placeholder - would use aiohttp to fetch RSS feed
        return []
    
    async def _fetch_from_investing_com(self) -> List[EconomicEvent]:
        """
        Fetch events from Investing.com API.
        
        Fetches economic calendar events for the next 7 days for supported currencies.
        Uses the Investing.com economic calendar API endpoint.
        
        Returns:
            List of EconomicEvent objects
        """
        import aiohttp
        from datetime import timedelta
        
        events = []
        
        # Investing.com API endpoint (this is a simplified example)
        # In production, you would need proper API credentials and endpoint
        base_url = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
        
        # Calculate date range (next 7 days)
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=7)
        
        # Map our currencies to Investing.com country codes
        currency_to_country = {
            "USD": "5",    # United States
            "EUR": "72",   # Euro Zone
            "GBP": "4",    # United Kingdom
            "XAU": "5",    # Gold (use US as proxy for gold-related events)
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                for currency in self.SUPPORTED_CURRENCIES:
                    country_id = currency_to_country.get(currency)
                    if not country_id:
                        continue
                    
                    # Prepare request payload
                    payload = {
                        "country[]": country_id,
                        "dateFrom": start_date.strftime("%Y-%m-%d"),
                        "dateTo": end_date.strftime("%Y-%m-%d"),
                        "timeZone": "55",  # UTC
                        "timeFilter": "timeRemain",
                        "currentTab": "custom",
                        "limit_from": "0",
                    }
                    
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "X-Requested-With": "XMLHttpRequest",
                    }
                    
                    try:
                        async with session.post(
                            base_url,
                            data=payload,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                # Parse the response and extract events
                                if "data" in data:
                                    for row in data["data"]:
                                        try:
                                            # Parse event data
                                            event_time_str = row.get("date")
                                            event_name = row.get("event", "").strip()
                                            impact_raw = row.get("importance", "1")
                                            
                                            # Skip if missing critical data
                                            if not event_time_str or not event_name:
                                                continue
                                            
                                            # Parse event time
                                            event_time = datetime.fromtimestamp(
                                                int(event_time_str),
                                                tz=timezone.utc
                                            )
                                            
                                            # Map impact level (1=LOW, 2=MEDIUM, 3=HIGH)
                                            impact_map = {"1": "LOW", "2": "MEDIUM", "3": "HIGH"}
                                            impact = impact_map.get(str(impact_raw), "LOW")
                                            
                                            # Extract forecast, previous, actual
                                            forecast = row.get("forecast", "").strip() or None
                                            previous = row.get("previous", "").strip() or None
                                            actual = row.get("actual", "").strip() or None
                                            
                                            # Create event
                                            event = EconomicEvent(
                                                event_time=event_time,
                                                currency=currency,
                                                event_name=event_name,
                                                impact=impact,
                                                forecast=forecast,
                                                previous=previous,
                                                actual=actual,
                                                source="investing_com",
                                            )
                                            events.append(event)
                                            
                                        except (KeyError, ValueError, TypeError) as e:
                                            # Skip malformed events
                                            continue
                    
                    except aiohttp.ClientError as e:
                        # Log error but continue with other currencies
                        print(f"Error fetching events for {currency}: {e}")
                        continue
        
        except Exception as e:
            print(f"Error in _fetch_from_investing_com: {e}")
        
        return events
    
    async def _fetch_from_source(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Generic fetch method for testing purposes.
        
        This method is used by tests to mock the fetch behavior.
        """
        return []
    
    async def _store_event(self, event: EconomicEvent) -> None:
        """
        Store an economic event in TimescaleDB.
        
        Uses ON CONFLICT (event_time, currency, event_name) DO NOTHING
        to prevent duplicate insertion.
        
        Args:
            event: EconomicEvent to store
        """
        if not self._pool:
            raise RuntimeError("Not connected. Call connect() first.")
        
        sql = """
            INSERT INTO economic_events (
                event_time, currency, event_name, impact,
                forecast, previous, actual, source, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (event_time, currency, event_name)
            DO NOTHING
        """
        
        async with self._pool.acquire() as conn:
            await conn.execute(
                sql,
                event.event_time,
                event.currency,
                event.event_name,
                event.impact,
                event.forecast,
                event.previous,
                event.actual,
                event.source,
            )
    
    async def ingest_events(self) -> None:
        """
        Fetch and store all economic events.
        
        This is the main ingestion method that:
        1. Fetches events from the configured source
        2. Stores each event in TimescaleDB
        3. Handles duplicates automatically via ON CONFLICT
        """
        events = await self._fetch_events()
        
        for event in events:
            await self._store_event(event)
    
    def start_scheduler(self) -> None:
        """
        Start the APScheduler to run daily ingestion at 00:05 UTC.
        
        The scheduler will:
        - Run ingest_events() every day at 00:05 UTC
        - Use AsyncIOScheduler for async compatibility
        - Use CronTrigger for precise scheduling
        """
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler()
        
        # Schedule daily refresh at 00:05 UTC
        self._scheduler.add_job(
            self.ingest_events,
            trigger=CronTrigger(hour=0, minute=5, timezone="UTC"),
            id="daily_calendar_refresh",
            name="Daily Economic Calendar Refresh",
            replace_existing=True,
        )
        
        self._scheduler.start()
    
    def stop_scheduler(self) -> None:
        """Stop the scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
