"""Tests for services.market_data.mt5_clock — MT5 server time <-> UTC."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.market_data.mt5_clock import (
    MT5ClockMismatchError,
    MT5ServerClock,
    measure_server_offset,
)


def _server_ts(*args: int) -> int:
    """MT5 encodes server wall-clock time as if it were a Unix epoch."""
    return int(datetime(*args, tzinfo=timezone.utc).timestamp())


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


class TestNYCloseClock:
    clock = MT5ServerClock("ny_close")

    def test_summer_is_utc_plus_3(self):
        assert self.clock.to_utc(_server_ts(2026, 7, 1, 16, 0)) == _utc(2026, 7, 1, 13, 0)

    def test_winter_is_utc_plus_2(self):
        assert self.clock.to_utc(_server_ts(2026, 1, 15, 16, 0)) == _utc(2026, 1, 15, 14, 0)

    def test_daily_bar_opens_at_new_york_close(self):
        # D1 bar stamped 00:00 server = 17:00 New York the previous day.
        assert self.clock.to_utc(_server_ts(2026, 7, 2, 0, 0)) == _utc(2026, 7, 1, 21, 0)
        assert self.clock.to_utc(_server_ts(2026, 1, 15, 0, 0)) == _utc(2026, 1, 14, 22, 0)

    def test_follows_us_not_eu_dst(self):
        # 2026-03-10: US DST already started (Mar 8), EU's hasn't (Mar 29).
        assert self.clock.utc_offset_at(_utc(2026, 3, 10, 12)) == timedelta(hours=3)

    def test_to_server_round_trips(self):
        for when in (_utc(2026, 7, 1, 13, 0), _utc(2026, 1, 15, 14, 0)):
            server = self.clock.to_server(when)
            assert self.clock.to_utc(int(server.timestamp())) == when


class TestFixedOffsetClock:
    def test_fixed_offset_ignores_dst(self):
        clock = MT5ServerClock("+2")
        assert clock.to_utc(_server_ts(2026, 7, 1, 16, 0)) == _utc(2026, 7, 1, 14, 0)
        assert clock.to_utc(_server_ts(2026, 1, 15, 16, 0)) == _utc(2026, 1, 15, 14, 0)

    def test_zero_offset_is_identity(self):
        assert MT5ServerClock("0").to_utc(_server_ts(2026, 7, 1, 16, 0)) == _utc(2026, 7, 1, 16, 0)

    def test_invalid_spec_rejected(self):
        with pytest.raises(ValueError, match="MT5_SERVER_TIMEZONE"):
            MT5ServerClock("EET")


class TestClockCheck:
    now = _utc(2026, 10, 2, 13, 19)

    def test_fresh_tick_matching_rule_passes(self):
        tick = int(self.now.timestamp()) + 3 * 3600 - 5
        assert MT5ServerClock("ny_close").check([tick], self.now) == timedelta(hours=3)

    def test_fresh_tick_contradicting_rule_raises(self):
        tick = int(self.now.timestamp()) + 3 * 3600
        with pytest.raises(MT5ClockMismatchError, match=r"UTC\+3"):
            MT5ServerClock("+2").check([tick], self.now)

    def test_stale_and_empty_ticks_are_skipped(self):
        stale = int(self.now.timestamp()) - 1052 * 3600 + 1234
        fresh = int(self.now.timestamp()) + 3 * 3600
        assert measure_server_offset([0, stale, fresh], self.now) == timedelta(hours=3)
        assert MT5ServerClock("+2").check([0, stale], self.now) is None
