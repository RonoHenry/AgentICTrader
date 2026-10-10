"""CandleStore — write live candles into TimescaleDB as they're fetched.

The live runner fetches a rolling window of candles per timeframe every
pass; upserting that window keeps the candles table current (and fills
short gaps after downtime) without a separate ingestion service. Longer
gaps are filled by running a historical loader with --resume.

Synchronous from the caller's side: each write opens one asyncpg
connection, upserts the batch, and closes — cheap at one write per pass,
and it avoids holding a pool bound to an event loop across asyncio.run()
calls.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Optional

__all__ = ["CandleStore", "TIMEFRAME_SECONDS"]

logger = logging.getLogger(__name__)

TIMEFRAME_SECONDS = {
    "M1": 60, "M3": 180, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H3": 10800, "H4": 14400, "H6": 21600, "H8": 28800, "H12": 43200,
    "D1": 86400, "W1": 604800,
}

_UPSERT = """
    INSERT INTO candles (time, instrument, timeframe, open, high, low, close, volume, complete, source, created_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
    ON CONFLICT (time, instrument, timeframe)
    DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        complete = EXCLUDED.complete,
        source = EXCLUDED.source
"""


class CandleStore:
    def __init__(self, connection_string: str, source: str) -> None:
        # .env holds the SQLAlchemy form; asyncpg only accepts postgresql://.
        self._dsn = connection_string.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._source = source

    def rows(self, candles: Iterable[Any], now: Optional[datetime] = None) -> list[tuple]:
        """liquidity_engine Candles → upsert rows; the still-forming bar is
        stored with complete=False and overwritten by later passes."""
        now = now or datetime.now(timezone.utc)
        out = []
        for c in candles:
            tf = c.timeframe.value if hasattr(c.timeframe, "value") else str(c.timeframe)
            seconds = TIMEFRAME_SECONDS.get(tf)
            if seconds is None:
                continue
            out.append((
                c.timestamp, c.instrument, tf,
                Decimal(str(c.open)), Decimal(str(c.high)), Decimal(str(c.low)), Decimal(str(c.close)),
                int(c.volume or 0),
                c.timestamp + timedelta(seconds=seconds) <= now,
                self._source,
            ))
        return out

    def write(self, candles: Iterable[Any]) -> int:
        """Upsert candles; returns rows written. Never raises — a database
        hiccup must not stop the trading loop."""
        rows = self.rows(candles)
        if not rows:
            return 0
        try:
            asyncio.run(self._write(rows))
            return len(rows)
        except Exception as exc:
            logger.warning("CandleStore: write of %d rows failed: %s", len(rows), exc)
            return 0

    async def _write(self, rows: list[tuple]) -> None:
        import asyncpg

        conn = await asyncpg.connect(self._dsn, timeout=10)
        try:
            await conn.executemany(_UPSERT, rows)
        finally:
            await conn.close()
