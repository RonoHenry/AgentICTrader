"""MT5 broker server time <-> real UTC.

MT5 stamps every bar and tick with the broker *server's* wall-clock time,
encoded as if it were a Unix epoch — it is not UTC. Most forex brokers
(MetaQuotes-Demo, IC Markets, Pepperstone, ...) run the server clock at
New York time + 7h so the daily bar closes at 17:00 New York: UTC+2 in
winter, UTC+3 while US DST is in effect. Treating those values as UTC
shifts every candle 2-3 hours, which breaks killzones, sessions and the
daily/weekly opens.

``MT5_SERVER_TIMEZONE`` selects the rule:
  "ny_close" (default)   New York + 7h, following US DST
  "+2", "3", "0", ...    a fixed UTC offset in hours, no DST

Pure (no MetaTrader5 import) so both the live runner and the history
loader can use it, and it can be unit-tested without a terminal.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

__all__ = ["NY_CLOSE", "MT5ServerClock", "MT5ClockMismatchError", "measure_server_offset"]

NY_CLOSE = "ny_close"
_NEW_YORK = ZoneInfo("America/New_York")
_NY_CLOSE_SHIFT = timedelta(hours=7)
_EPOCH = datetime(1970, 1, 1)
# A tick this close to a whole half-hour offset from "now" is fresh enough
# to read the server offset off; anything else is a stale/empty tick.
_FRESH_TICK_TOLERANCE_S = 120


class MT5ClockMismatchError(RuntimeError):
    """The configured server timezone disagrees with the terminal's live clock."""


class MT5ServerClock:
    def __init__(self, spec: str = NY_CLOSE) -> None:
        self.spec = spec.strip().lower()
        if self.spec == NY_CLOSE:
            self._fixed: Optional[timedelta] = None
        else:
            try:
                self._fixed = timedelta(hours=float(self.spec))
            except ValueError:
                raise ValueError(
                    f"Invalid MT5_SERVER_TIMEZONE {spec!r}: use 'ny_close' or a UTC offset in hours like '+2'"
                ) from None

    def utc_offset_at(self, when_utc: datetime) -> timedelta:
        """Server clock minus UTC at the given instant."""
        if self._fixed is not None:
            return self._fixed
        return when_utc.astimezone(_NEW_YORK).utcoffset() + _NY_CLOSE_SHIFT

    def to_utc(self, server_ts: int) -> datetime:
        """Convert an MT5 bar/tick ``time`` value to a tz-aware UTC datetime."""
        wall = _EPOCH + timedelta(seconds=int(server_ts))
        if self._fixed is not None:
            return (wall - self._fixed).replace(tzinfo=timezone.utc)
        return (wall - _NY_CLOSE_SHIFT).replace(tzinfo=_NEW_YORK).astimezone(timezone.utc)

    def to_server(self, when_utc: datetime) -> datetime:
        """Convert a real UTC instant to the server-clock value MT5's
        copy_rates_range() compares against (returned as a UTC-tagged
        datetime, which is what the MetaTrader5 package expects)."""
        return (when_utc + self.utc_offset_at(when_utc)).astimezone(timezone.utc)

    def check(self, tick_times: Iterable[int], now_utc: datetime) -> Optional[timedelta]:
        """Verify this clock against live tick times from the terminal.

        Returns the measured offset, or None when no tick was fresh enough
        to measure (e.g. weekend). Raises MT5ClockMismatchError when a fresh
        tick shows a different offset than this clock predicts.
        """
        measured = measure_server_offset(tick_times, now_utc)
        expected = self.utc_offset_at(now_utc)
        if measured is not None and measured != expected:
            raise MT5ClockMismatchError(
                f"MT5 server clock is UTC{_fmt(measured)} but MT5_SERVER_TIMEZONE={self.spec!r} "
                f"predicts UTC{_fmt(expected)} right now — set MT5_SERVER_TIMEZONE in .env "
                f"(e.g. '{measured.total_seconds() / 3600:+g}')"
            )
        return measured


def measure_server_offset(tick_times: Iterable[int], now_utc: datetime) -> Optional[timedelta]:
    """Read the server's UTC offset off the freshest tick, rounded to 30 min."""
    now_ts = now_utc.timestamp()
    for tick_time in tick_times:
        diff = int(tick_time) - now_ts
        nearest = round(diff / 1800) * 1800
        if abs(diff - nearest) <= _FRESH_TICK_TOLERANCE_S:
            return timedelta(seconds=nearest)
    return None


def _fmt(offset: timedelta) -> str:
    return f"{offset.total_seconds() / 3600:+g}"
