"""Binance spot klines — a 24/7 crypto feed for weekend development.

The MT5 demo server (MetaQuotes-Demo) lists no crypto CFDs, so when FX is
closed this is where live-moving candles come from. Uses Binance's public
market-data endpoint: no account or API key, history back to 2017.

Every timeframe liquidity_engine uses is native on Binance except H3, which
is built here from H1. All bars are UTC-aligned: D1 opens 00:00 UTC and W1
opens Monday 00:00 UTC (unlike MT5's New York-close alignment).

Volume is the bar's trade count — the closest analogue to MT5's tick_volume
and, unlike Binance's fractional base-asset volume, an integer like the
candles.volume column.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator, List, Optional

import requests

__all__ = ["Kline", "TIMEFRAMES", "BinanceKlineClient", "BinanceError", "BinanceUnavailable"]

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://data-api.binance.vision"
MAX_LIMIT = 1000

# Platform timeframe → Binance interval, and duration in seconds.
_NATIVE = {
    "M1": ("1m", 60),
    "M3": ("3m", 180),
    "M5": ("5m", 300),
    "M15": ("15m", 900),
    "H1": ("1h", 3600),
    "H4": ("4h", 14400),
    "H6": ("6h", 21600),
    "H8": ("8h", 28800),
    "H12": ("12h", 43200),
    "D1": ("1d", 86400),
    "W1": ("1w", 604800),
}
# Platform timeframe → (source timeframe, bars per bucket).
_RESAMPLED = {"H3": ("H1", 3)}
TIMEFRAMES = [*_NATIVE, *_RESAMPLED]

_MAX_RETRIES = 6


class BinanceError(RuntimeError):
    pass


class BinanceUnavailable(BinanceError):
    """Retries exhausted on network errors / 5xx — the feed itself is down,
    as opposed to a bad request for one symbol."""


@dataclass(frozen=True)
class Kline:
    open_time: datetime
    open: str  # prices kept as Binance's exact decimal strings
    high: str
    low: str
    close: str
    trades: int
    complete: bool


def _duration(timeframe: str) -> timedelta:
    if timeframe in _RESAMPLED:
        source, factor = _RESAMPLED[timeframe]
        return timedelta(seconds=_NATIVE[source][1] * factor)
    return timedelta(seconds=_NATIVE[timeframe][1])


def _ms(when: datetime) -> int:
    return int(when.timestamp() * 1000)


class BinanceKlineClient:
    def __init__(self, base_url: Optional[str] = None, session: Optional[requests.Session] = None) -> None:
        self.base_url = (base_url or os.getenv("BINANCE_API_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._session = session or requests.Session()

    # ── public API ─────────────────────────────────────────────────────────

    def latest(self, symbol: str, timeframe: str, count: int) -> List[Kline]:
        """The most recent ``count`` bars, the last one usually still forming."""
        if timeframe in _RESAMPLED:
            source, factor = _RESAMPLED[timeframe]
            # One extra bucket so a partial leading bucket can be dropped.
            raw = self.latest(symbol, source, min(MAX_LIMIT, (count + 1) * factor))
            return resample(raw, timeframe)[-count:]
        if count > MAX_LIMIT:
            raise ValueError(f"count {count} exceeds Binance's {MAX_LIMIT}-bar limit")
        return self._parse(self._get_klines(symbol, _NATIVE[timeframe][0], limit=count), timeframe)

    def iter_range(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Iterator[List[Kline]]:
        """Yield pages of bars opening in [start, end), oldest first.

        Resampled timeframes are fetched whole and yielded as one page
        (H3 over years of H1 is only tens of thousands of bars)."""
        if timeframe in _RESAMPLED:
            source, _ = _RESAMPLED[timeframe]
            raw = [k for page in self.iter_range(symbol, source, start, end) for k in page]
            yield resample(raw, timeframe)
            return

        interval, seconds = _NATIVE[timeframe]
        cursor = start
        while cursor < end:
            rows = self._get_klines(symbol, interval, start_ms=_ms(cursor), end_ms=_ms(end) - 1, limit=MAX_LIMIT)
            page = self._parse(rows, timeframe)
            if not page:
                return
            yield page
            cursor = page[-1].open_time + timedelta(seconds=seconds)

    # ── internals ──────────────────────────────────────────────────────────

    def _parse(self, rows: list, timeframe: str) -> List[Kline]:
        duration = _duration(timeframe)
        now = datetime.now(timezone.utc)
        klines = []
        for r in rows:
            open_time = datetime.fromtimestamp(r[0] / 1000, tz=timezone.utc)
            klines.append(
                Kline(
                    open_time=open_time,
                    open=r[1],
                    high=r[2],
                    low=r[3],
                    close=r[4],
                    trades=int(r[8]),
                    complete=open_time + duration <= now,
                )
            )
        return klines

    def _get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ) -> list:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms

        url = f"{self.base_url}/api/v3/klines"
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = self._session.get(url, params=params, timeout=20)
            except requests.RequestException as e:
                # This network resets TLS connections intermittently — retry.
                wait = min(30, 2 ** attempt)
                logger.warning(f"Binance request failed ({e.__class__.__name__}), retry {attempt}/{_MAX_RETRIES} in {wait}s")
                time.sleep(wait)
                continue

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (418, 429):
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning(f"Binance rate limit ({resp.status_code}), waiting {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                time.sleep(min(30, 2 ** attempt))
                continue
            raise BinanceError(f"Binance {resp.status_code} for {symbol} {interval}: {resp.text[:200]}")

        raise BinanceUnavailable(f"Binance klines for {symbol} {interval} failed after {_MAX_RETRIES} attempts")


def resample(klines: List[Kline], timeframe: str) -> List[Kline]:
    """Aggregate source bars into UTC-aligned buckets of ``timeframe``.

    Leading buckets missing their first source bar are dropped (their open
    would be wrong); interior gaps (exchange maintenance) are tolerated.
    """
    source, factor = _RESAMPLED[timeframe]
    source_s = _NATIVE[source][1]
    bucket_s = source_s * factor
    now = datetime.now(timezone.utc)

    buckets: dict[int, List[Kline]] = {}
    for k in klines:
        ts = int(k.open_time.timestamp())
        buckets.setdefault(ts - ts % bucket_s, []).append(k)

    out = []
    for start_ts in sorted(buckets):
        group = buckets[start_ts]
        if not out and int(group[0].open_time.timestamp()) != start_ts:
            continue
        open_time = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        out.append(
            Kline(
                open_time=open_time,
                open=group[0].open,
                high=max(group, key=lambda k: float(k.high)).high,
                low=min(group, key=lambda k: float(k.low)).low,
                close=group[-1].close,
                trades=sum(k.trades for k in group),
                complete=open_time + timedelta(seconds=bucket_s) <= now,
            )
        )
    return out
