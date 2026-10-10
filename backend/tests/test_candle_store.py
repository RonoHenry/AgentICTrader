"""Tests for services.market_data.candle_store — live candles → TimescaleDB."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from liquidity_engine.models import Candle, Timeframe
from services.market_data.candle_store import CandleStore

NOW = datetime(2026, 10, 3, 12, 7, tzinfo=timezone.utc)


def _candle(tf: Timeframe, ts: datetime, price: float = 775.0799999999999) -> Candle:
    return Candle(timestamp=ts, open=price, high=price + 1, low=price - 1, close=price,
                  volume=42, timeframe=tf, instrument="BNBUSDT")


class TestRows:
    store = CandleStore("postgresql+asyncpg://u:p@localhost/db", source="binance")

    def test_row_matches_candles_table_columns(self):
        [row] = self.store.rows([_candle(Timeframe.M5, datetime(2026, 10, 3, 11, 55, tzinfo=timezone.utc))], now=NOW)
        ts, instrument, tf, o, h, l, c, volume, complete, source = row
        assert (instrument, tf, volume, source) == ("BNBUSDT", "M5", 42, "binance")
        assert all(isinstance(x, Decimal) for x in (o, h, l, c))
        assert complete is True

    def test_forming_bar_is_incomplete(self):
        [row] = self.store.rows([_candle(Timeframe.M5, datetime(2026, 10, 3, 12, 5, tzinfo=timezone.utc))], now=NOW)
        assert row[8] is False

    def test_h3_and_w1_durations(self):
        rows = self.store.rows([
            _candle(Timeframe.H3, NOW - timedelta(hours=2)),
            _candle(Timeframe.W1, NOW - timedelta(days=8)),
        ], now=NOW)
        assert [r[8] for r in rows] == [False, True]

    def test_dsn_is_normalised_for_asyncpg(self):
        assert self.store._dsn.startswith("postgresql://")


def test_write_never_raises_when_database_is_unreachable():
    store = CandleStore("postgresql://u:p@127.0.0.1:1/db", source="binance")
    assert store.write([_candle(Timeframe.M1, NOW)]) == 0


def test_write_of_nothing_is_a_no_op():
    assert CandleStore("postgresql://u:p@127.0.0.1:1/db", source="binance").write([]) == 0
