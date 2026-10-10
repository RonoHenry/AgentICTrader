"""Tests for services.market_data.binance — Binance spot kline fetching."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import requests

from services.market_data import binance
from services.market_data.binance import BinanceError, BinanceKlineClient, BinanceUnavailable, Kline, resample

H1_MS = 3_600_000


def _row(open_ms: int, o: float, h: float, l: float, c: float, trades: int = 10) -> list:
    """A Binance /api/v3/klines row (prices come back as strings)."""
    return [open_ms, str(o), str(h), str(l), str(c), "1.0", open_ms + H1_MS - 1, "0", trades, "0", "0", "0"]


def _ms(*args: int) -> int:
    return int(datetime(*args, tzinfo=timezone.utc).timestamp() * 1000)


class _Resp:
    def __init__(self, status: int, payload=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeSession:
    """Serves H1 rows from a fixed list, honouring startTime/endTime/limit."""

    def __init__(self, rows: list, failures: list | None = None):
        self.rows = rows
        self.failures = list(failures or [])
        self.calls: list[dict] = []

    def get(self, url, params, timeout):
        self.calls.append(dict(params))
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure
        start = params.get("startTime", 0)
        end = params.get("endTime", 2**62)
        matching = [r for r in self.rows if start <= r[0] <= end]
        if "startTime" not in params:
            matching = matching[-params["limit"]:]
        return _Resp(200, matching[: params["limit"]])


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(binance.time, "sleep", lambda _s: None)


class TestParse:
    def test_rows_become_utc_klines_with_trade_count_volume(self):
        session = _FakeSession([_row(_ms(2024, 1, 1, 5), 100, 110, 90, 105, trades=42)])
        [k] = BinanceKlineClient(session=session).latest("BTCUSDT", "H1", 1)
        assert k.open_time == datetime(2024, 1, 1, 5, tzinfo=timezone.utc)
        assert (k.open, k.high, k.low, k.close) == ("100", "110", "90", "105")
        assert k.trades == 42
        assert k.complete

    def test_current_bar_is_flagged_incomplete(self):
        now_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        session = _FakeSession([_row(int(now_hour.timestamp() * 1000), 1, 1, 1, 1)])
        [k] = BinanceKlineClient(session=session).latest("BTCUSDT", "H1", 1)
        assert not k.complete


class TestIterRange:
    def test_paginates_until_end_without_duplicates(self, monkeypatch):
        monkeypatch.setattr(binance, "MAX_LIMIT", 10)
        rows = [_row(_ms(2024, 1, 1) + i * H1_MS, 1, 2, 0.5, 1.5) for i in range(25)]
        session = _FakeSession(rows)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        pages = list(BinanceKlineClient(session=session).iter_range("BTCUSDT", "H1", start, start + timedelta(hours=25)))
        times = [k.open_time for page in pages for k in page]
        assert len(times) == 25 == len(set(times))
        assert [len(p) for p in pages] == [10, 10, 5]

    def test_end_is_exclusive(self):
        rows = [_row(_ms(2024, 1, 1) + i * H1_MS, 1, 2, 0.5, 1.5) for i in range(5)]
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        pages = list(BinanceKlineClient(session=_FakeSession(rows)).iter_range("BTCUSDT", "H1", start, start + timedelta(hours=3)))
        assert [k.open_time.hour for page in pages for k in page] == [0, 1, 2]


class TestResample:
    def _h1(self, hour: int, o, h, l, c, trades=1) -> Kline:
        return Kline(datetime(2024, 1, 1, hour, tzinfo=timezone.utc), str(o), str(h), str(l), str(c), trades, True)

    def test_h3_buckets_are_utc_aligned_ohlc_aggregates(self):
        bars = [
            self._h1(3, 10, 12, 9, 11, 1),
            self._h1(4, 11, 15, 10, 14, 2),
            self._h1(5, 14, 14, 8, 9, 3),
            self._h1(6, 9, 10, 7, 8, 4),
        ]
        out = resample(bars, "H3")
        assert [k.open_time.hour for k in out] == [3, 6]
        first = out[0]
        assert (first.open, first.high, first.low, first.close, first.trades) == ("10", "15", "8", "9", 6)

    def test_partial_leading_bucket_is_dropped(self):
        bars = [self._h1(4, 1, 1, 1, 1), self._h1(5, 1, 1, 1, 1), self._h1(6, 2, 2, 2, 2)]
        assert [k.open_time.hour for k in resample(bars, "H3")] == [6]

    def test_latest_h3_returns_requested_count(self):
        rows = [_row(_ms(2024, 1, 1) + i * H1_MS, 1, 2, 0.5, 1.5) for i in range(48)]
        out = BinanceKlineClient(session=_FakeSession(rows)).latest("BTCUSDT", "H3", 5)
        assert len(out) == 5
        assert all(k.open_time.hour % 3 == 0 for k in out)
        assert out[-1].open_time == datetime(2024, 1, 2, 21, tzinfo=timezone.utc)


class TestRetries:
    def test_network_resets_and_rate_limits_are_retried(self):
        rows = [_row(_ms(2024, 1, 1), 1, 1, 1, 1)]
        session = _FakeSession(
            rows,
            failures=[requests.ConnectionError("reset"), _Resp(429, headers={"Retry-After": "1"}), _Resp(502)],
        )
        assert len(BinanceKlineClient(session=session).latest("BTCUSDT", "H1", 1)) == 1
        assert len(session.calls) == 4

    def test_exhausted_retries_raise_feed_unavailable(self):
        session = _FakeSession([], failures=[requests.ConnectionError("reset")] * binance._MAX_RETRIES)
        with pytest.raises(BinanceUnavailable):
            BinanceKlineClient(session=session).latest("BTCUSDT", "H1", 1)
        assert len(session.calls) == binance._MAX_RETRIES

    def test_client_errors_are_not_retried(self):
        session = _FakeSession([], failures=[_Resp(400, {"code": -1121, "msg": "Invalid symbol."})])
        with pytest.raises(BinanceError, match="400"):
            BinanceKlineClient(session=session).latest("NOPEUSDT", "H1", 1)
        assert len(session.calls) == 1
