"""
Economic calendar blackout monitor for AgentICTrader.

Polls TimescaleDB economic_events every 60s.
Detects HIGH impact events within ±15 min window for each instrument's currency.
Publishes blackout state to Redis: key blackout:{instrument} → {active, event_name, minutes_remaining}

Redis keys:
  blackout:{instrument} — blackout state (TTL 120s)

Usage::

    monitor = CalendarMonitor()
    await monitor.connect()
    await monitor.run()          # continuous loop
    await monitor.close()
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLACKOUT_WINDOW_MINUTES: int = 15       # ±15 min around HIGH impact events
POLL_INTERVAL_SECONDS: int = 60         # poll TimescaleDB every 60s
TTL_BLACKOUT: int = 120                 # Redis TTL for blackout keys (2× poll interval)

# Instrument → list of currencies to monitor for blackout.
# Crypto instruments have no currency blackout.
INSTRUMENT_CURRENCIES: dict[str, list[str]] = {
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
    "US500":  ["USD"],
    "US30":   ["USD"],
    "XAUUSD": ["XAU", "USD"],
    "BTCUSD": [],   # crypto — no currency blackout
    "ETHUSD": [],   # crypto — no currency blackout
}

SUPPORTED_INSTRUMENTS: list[str] = list(INSTRUMENT_CURRENCIES.keys())


# ---------------------------------------------------------------------------
# Key builder
# ---------------------------------------------------------------------------

def blackout_key(instrument: str) -> str:
    """Return the Redis key for the blackout state of *instrument*.

    Args:
        instrument: e.g. ``"EURUSD"``

    Returns:
        ``"blackout:EURUSD"``
    """
    return f"blackout:{instrument}"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class BlackoutState:
    """Blackout state for a single instrument at a point in time.

    Attributes:
        instrument:        Instrument symbol, e.g. ``"EURUSD"``.
        active:            ``True`` when a HIGH impact event is within ±15 min.
        event_name:        Name of the triggering event; empty string when inactive.
        minutes_remaining: Signed minutes to/from the nearest event.
                           Positive = event in the future.
                           Negative = event already passed.
                           Zero when inactive.
    """
    instrument: str
    active: bool
    event_name: str
    minutes_remaining: float


# ---------------------------------------------------------------------------
# CalendarMonitor
# ---------------------------------------------------------------------------

class CalendarMonitor:
    """Polls TimescaleDB for HIGH impact economic events and publishes blackout
    state to Redis for every supported instrument.

    Lifecycle::

        monitor = CalendarMonitor()
        await monitor.connect()
        try:
            await monitor.run()          # blocks until cancelled
        finally:
            await monitor.close()
    """

    def __init__(
        self,
        db_host: str = "localhost",
        db_port: int = 5432,
        db_name: str = "agentictrader",
        db_user: str = "agentictrader",
        db_password: str = "changeme",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        poll_interval: int = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._db_host = db_host
        self._db_port = db_port
        self._db_name = db_name
        self._db_user = db_user
        self._db_password = db_password
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._poll_interval = poll_interval

        self._pool: Optional[asyncpg.Pool] = None
        self._redis: Optional[aioredis.Redis] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create asyncpg connection pool and Redis connection."""
        self._pool = await asyncpg.create_pool(
            host=self._db_host,
            port=self._db_port,
            database=self._db_name,
            user=self._db_user,
            password=self._db_password,
        )
        self._redis = aioredis.Redis(
            host=self._redis_host,
            port=self._redis_port,
            decode_responses=True,
        )
        logger.info(
            "CalendarMonitor connected (db=%s:%s/%s, redis=%s:%s)",
            self._db_host,
            self._db_port,
            self._db_name,
            self._redis_host,
            self._redis_port,
        )

    async def close(self) -> None:
        """Close asyncpg pool and Redis connection."""
        if self._pool is not None:
            try:
                await self._pool.close()
            except Exception:
                pass
            finally:
                self._pool = None

        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            finally:
                self._redis = None

        logger.info("CalendarMonitor closed")

    # ------------------------------------------------------------------
    # Database query
    # ------------------------------------------------------------------

    async def fetch_upcoming_high_impact_events(
        self, currencies: list[str]
    ) -> list[dict]:
        """Query TimescaleDB for HIGH impact events within ±15 min of now.

        Only events whose ``currency`` is in *currencies* are returned.
        Results are ordered by proximity to now (nearest first).

        Args:
            currencies: List of currency codes to filter on, e.g. ``["EUR", "USD"]``.

        Returns:
            List of dicts with keys ``event_time``, ``currency``, ``event_name``.
            Returns an empty list when *currencies* is empty.
        """
        if not currencies:
            return []

        sql = """
            SELECT event_time, currency, event_name
            FROM economic_events
            WHERE impact = 'HIGH'
              AND currency = ANY($1)
              AND event_time BETWEEN NOW() - INTERVAL '15 minutes'
                                 AND NOW() + INTERVAL '15 minutes'
            ORDER BY ABS(EXTRACT(EPOCH FROM (event_time - NOW())))
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, currencies)

        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Blackout computation
    # ------------------------------------------------------------------

    def compute_blackout_state(
        self,
        instrument: str,
        events: list[dict],
        now: datetime,
    ) -> BlackoutState:
        """Compute the BlackoutState for *instrument* given a list of HIGH impact events.

        The events list is assumed to already be filtered to the ±15 min window
        (as returned by :meth:`fetch_upcoming_high_impact_events`).

        Args:
            instrument: Instrument symbol, e.g. ``"EURUSD"``.
            events:     List of event dicts with at least ``event_time`` and
                        ``event_name`` keys.
            now:        Reference timestamp (timezone-aware UTC).

        Returns:
            :class:`BlackoutState` with:
            - ``active=False``, ``event_name=""``, ``minutes_remaining=0.0``
              when *events* is empty.
            - ``active=True`` and details of the nearest event otherwise.
        """
        if not events:
            return BlackoutState(
                instrument=instrument,
                active=False,
                event_name="",
                minutes_remaining=0.0,
            )

        # Find the nearest event (smallest absolute minutes_remaining)
        def _minutes(event: dict) -> float:
            event_time: datetime = event["event_time"]
            # Ensure both datetimes are timezone-aware for subtraction
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            return (event_time - now).total_seconds() / 60.0

        # Safety guard: only consider events within the ±BLACKOUT_WINDOW_MINUTES window
        window_events = [e for e in events if abs(_minutes(e)) <= BLACKOUT_WINDOW_MINUTES]

        if not window_events:
            return BlackoutState(
                instrument=instrument,
                active=False,
                event_name="",
                minutes_remaining=0.0,
            )

        nearest = min(window_events, key=lambda e: abs(_minutes(e)))
        mins = _minutes(nearest)

        return BlackoutState(
            instrument=instrument,
            active=True,
            event_name=nearest["event_name"],
            minutes_remaining=mins,
        )

    # ------------------------------------------------------------------
    # Redis publishing
    # ------------------------------------------------------------------

    async def publish_blackout_state(self, state: BlackoutState) -> None:
        """Write *state* to Redis.

        Key:   ``blackout:{instrument}``
        Value: JSON ``{"active": bool, "event_name": str, "minutes_remaining": float}``
        TTL:   :data:`TTL_BLACKOUT` seconds (120 s)

        Args:
            state: The :class:`BlackoutState` to publish.
        """
        key = blackout_key(state.instrument)
        value = json.dumps(
            {
                "active": state.active,
                "event_name": state.event_name,
                "minutes_remaining": state.minutes_remaining,
            }
        )
        await self._redis.set(key, value, ex=TTL_BLACKOUT)
        logger.debug(
            "Published blackout state for %s: active=%s (TTL=%ss)",
            state.instrument,
            state.active,
            TTL_BLACKOUT,
        )

    # ------------------------------------------------------------------
    # Per-instrument pipeline
    # ------------------------------------------------------------------

    async def check_instrument(
        self, instrument: str, now: datetime
    ) -> BlackoutState:
        """Run the full blackout pipeline for a single *instrument*.

        Steps:
        1. Look up the currencies for *instrument*.
        2. If no currencies → publish inactive state and return.
        3. Fetch HIGH impact events within ±15 min for those currencies.
        4. Compute the :class:`BlackoutState`.
        5. Publish the state to Redis.
        6. Return the state.

        Args:
            instrument: Instrument symbol, e.g. ``"EURUSD"``.
            now:        Reference timestamp (timezone-aware UTC).

        Returns:
            The computed :class:`BlackoutState`.
        """
        currencies = INSTRUMENT_CURRENCIES.get(instrument, [])

        if not currencies:
            # Crypto instruments — no currency blackout
            state = BlackoutState(
                instrument=instrument,
                active=False,
                event_name="",
                minutes_remaining=0.0,
            )
            await self.publish_blackout_state(state)
            return state

        events = await self.fetch_upcoming_high_impact_events(currencies)
        state = self.compute_blackout_state(instrument, events, now)
        await self.publish_blackout_state(state)
        return state

    # ------------------------------------------------------------------
    # Poll cycle
    # ------------------------------------------------------------------

    async def run_once(self) -> list[BlackoutState]:
        """Run one poll cycle: check all :data:`SUPPORTED_INSTRUMENTS`.

        Returns:
            List of :class:`BlackoutState` for every supported instrument.
        """
        now = datetime.now(tz=timezone.utc)
        states: list[BlackoutState] = []
        for instrument in SUPPORTED_INSTRUMENTS:
            state = await self.check_instrument(instrument, now)
            states.append(state)
        return states

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Continuous polling loop: call :meth:`run_once` every *poll_interval* seconds.

        Runs until cancelled.  :exc:`asyncio.CancelledError` is caught and the
        loop exits cleanly.
        """
        logger.info(
            "CalendarMonitor starting poll loop (interval=%ss)", self._poll_interval
        )
        try:
            while True:
                try:
                    await self.run_once()
                except Exception as exc:
                    logger.error("CalendarMonitor poll error: %s", exc, exc_info=True)
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            logger.info("CalendarMonitor poll loop cancelled — shutting down")
