"""
The live runner builds its candle window with compose_as_of_view(), like
the backtester, from whatever a venue serves natively.

Task 192 (.kiro/specs/algo-backtester/tasks.md). A fake venue serves one
synthetic M1 stream as a New York-close MT5 server, a UTC MT5 server or
Binance would: native bars on that venue's own clock, the last one still
forming. No MT5 or Binance.
Validates: Requirements 2.7 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from types import SimpleNamespace

import pytest

import scripts.run_live_agent as runner
from agent.strategy_config import StrategyConfig
from liquidity_engine.models import Candle, Timeframe as TF
from services.market_data.as_of_view import aggregate
from services.market_data.mt5_clock import MT5ServerClock
from services.market_data.strategy_calendar import StrategyCalendar

CAL = StrategyCalendar()
UTC = timezone.utc
MINUTE = timedelta(minutes=1)
NOW = datetime(2026, 1, 14, 15, 7, 20, tzinfo=UTC)  # Wednesday; the M15 bar from 15:00 is forming
CFG = StrategyConfig(candle_counts={
    TF.M1: 300, TF.M3: 300, TF.M5: 300, TF.M15: 12,
    TF.H3: 6, TF.H4: 6, TF.H6: 5, TF.H8: 5, TF.H12: 4, TF.D1: 5, TF.W1: 3,
})
VENUES = {"ny_close": MT5ServerClock("ny_close"), "utc_mt5": MT5ServerClock("+0"), "binance": None}


@lru_cache(maxsize=1)
def m1_stream() -> tuple[Candle, ...]:
    """Six weeks of 24/7 M1 up to NOW, the last bar still forming."""
    start = NOW.replace(second=0) - timedelta(weeks=6)
    bars, price, ts, i = [], 10_000, start, 0
    while ts <= NOW:
        step = (i * 7919) % 11 - 5  # deterministic wiggle
        price = max(100, price + step)
        o, c = price / 10_000, (price + step) / 10_000
        bars.append(Candle(timestamp=ts, open=o, high=max(o, c) + 0.0002, low=min(o, c) - 0.0002, close=c,
                           volume=1, timeframe=TF.M1, instrument="EURUSD"))
        ts, i = ts + MINUTE, i + 1
    return tuple(bars)


def _utc_floor(ts: datetime, tf: TF) -> datetime:
    """Boundaries of a UTC venue: intraday from 00:00 UTC, D1 at midnight, W1 on Monday (Binance)."""
    day = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if tf == TF.W1:
        return day - timedelta(days=day.weekday())
    if tf == TF.D1:
        return day
    minutes = {TF.M1: 1, TF.M5: 5, TF.M15: 15, TF.H1: 60, TF.H3: 180, TF.H4: 240, TF.H6: 360, TF.H8: 480, TF.H12: 720}[tf]
    elapsed = (ts - day) // MINUTE
    return day + (elapsed - elapsed % minutes) * MINUTE


class FakeVenue:
    def __init__(self, kind: str, lag_bars: int = 0):
        self.kind, self.lag_bars = kind, lag_bars
        self.native_calls: list[tuple[TF, int]] = []
        self.m1_calls: list[tuple[datetime, datetime]] = []

    @lru_cache(maxsize=None)
    def native(self, tf: TF) -> list[Candle]:
        m1 = list(m1_stream())
        if self.kind == "ny_close":  # its bars are the strategy calendar's; the last one forming
            return aggregate(m1, tf, CAL, as_of=datetime(2100, 1, 1, tzinfo=UTC))
        groups: dict[datetime, list[Candle]] = {}
        for b in m1:
            groups.setdefault(_utc_floor(b.timestamp, tf), []).append(b)
        return [Candle(timestamp=ts, open=g[0].open, high=max(b.high for b in g), low=min(b.low for b in g),
                       close=g[-1].close, volume=len(g), timeframe=tf, instrument="EURUSD")
                for ts, g in groups.items()]

    def fetch(self, tf: TF, count: int) -> list[Candle]:
        self.native_calls.append((tf, count))
        bars = self.native(tf)
        if tf == CFG.entry_tf and self.lag_bars:
            bars = bars[: -self.lag_bars]  # the venue hasn't delivered its newest bars yet
        return bars[-count:]

    def fetch_m1(self, start: datetime, end: datetime) -> list[Candle]:
        self.m1_calls.append((start, end))
        return [b for b in m1_stream() if start <= b.timestamp < end]


def window(kind: str, **venue_kwargs):
    venue = FakeVenue(kind, **venue_kwargs)
    view, t = runner._as_of_window(venue.fetch, venue.fetch_m1, VENUES[kind], CFG, NOW)
    return venue, view, t


@pytest.mark.parametrize("kind", list(VENUES))
def test_forming_entry_bar_dropped(kind):
    venue, view, _ = window(kind)
    assert venue.native(TF.M15)[-1].timestamp == datetime(2026, 1, 14, 15, 0, tzinfo=UTC)  # forming at NOW
    assert view[TF.M15][-1].timestamp == datetime(2026, 1, 14, 14, 45, tzinfo=UTC)
    assert len(view[TF.M15]) == CFG.candle_counts[TF.M15]


def test_evaluation_timestamp_is_last_entry_bar_close():
    _, _, t = window("ny_close")
    assert t == datetime(2026, 1, 14, 15, 0, tzinfo=UTC)  # not NOW: the close of the 14:45 bar

    # A venue that hasn't delivered the 14:45 bar yet: evaluate as of the newest bar it has.
    _, view, lagging_t = window("ny_close", lag_bars=2)
    assert lagging_t == datetime(2026, 1, 14, 14, 45, tzinfo=UTC)
    assert view[TF.M15][-1].timestamp == datetime(2026, 1, 14, 14, 30, tzinfo=UTC)


@pytest.mark.parametrize("kind", list(VENUES))
def test_m1_fetched_to_cover_current_w1_period(kind):
    venue, _, t = window(kind)
    assert venue.m1_calls == [(CAL.period_start(t, TF.W1), t)]


def test_htf_in_progress_bar_composed_from_m1():
    _, view, t = window("utc_mt5")
    known = [b for b in m1_stream() if b.timestamp + MINUTE <= t]
    for tf in (TF.H4, TF.D1, TF.W1):
        forming = view[tf][-1]
        start = CAL.period_start(t, tf)
        expected = aggregate([b for b in known if b.timestamp >= start], tf, CAL, as_of=CAL.period_end(t, tf))
        assert forming == expected[-1] and forming.timestamp == start, tf
        assert len(view[tf]) == CFG.candle_counts[tf]


def test_native_htf_bars_used_only_where_calendar_matches():
    ny, ny_view, _ = window("ny_close")
    assert {tf for tf, _ in ny.native_calls} == set(CFG.timeframes)  # every timeframe native, no H1 detour

    for kind in ("utc_mt5", "binance"):
        venue, view, _ = window(kind)
        fetched = [tf for tf, _ in venue.native_calls]
        # Only what lines up natively; everything above H1 comes from native H1.
        assert set(fetched) == {CFG.entry_tf, TF.H1}, kind
        h1_count = dict(venue.native_calls)[TF.H1]
        assert h1_count >= (CFG.candle_counts[TF.W1] + 1) * 7 * 24
        # The point of D9: the same prices give the engine the same candles at any venue.
        assert view == ny_view, kind


def test_short_history_refused_not_evaluated():
    # A venue that returns less history than the windows need (e.g. while the
    # terminal is still downloading it) would give the engine shorter windows
    # than the backtest ever uses. Refuse; the next pass retries.
    class ShortVenue(FakeVenue):
        def fetch(self, tf, count):
            bars = super().fetch(tf, count)
            return bars[-(7 * 24):] if tf == TF.H1 else bars  # one week of H1: too few for W1 x 3

    venue = ShortVenue("utc_mt5")
    with pytest.raises(RuntimeError, match="W1"):
        runner._as_of_window(venue.fetch, venue.fetch_m1, VENUES["utc_mt5"], CFG, NOW)


def test_handoff_passes_observe_node_staleness_check():
    # The setup's data is as of t, the last bar close, but it is detected when
    # the runner evaluates it, possibly minutes later. observe_node rejects
    # setups detected over 60 s before it sees them, so the message must carry
    # the hand-off time, not t. A real window graded A (EURUSD M5) at a t
    # long past: stamped with t, observe_node would reject it as stale.
    from agent.nodes.observe_node import observe_node
    from tests.test_liquidity_engine_perf import FIXTURES, _load

    _, candles_by_tf, t = _load(FIXTURES / "EURUSD_M5.json.gz")
    messages = []
    graph = SimpleNamespace(run=lambda message: messages.append(message) or SimpleNamespace(
        decision=None, decision_reason="", error=None, trade_id=None))

    runner._process_instrument("EURUSD", candles_by_tf, t, graph, StrategyConfig(entry_tf=TF.M5), "AUTONOMOUS",
                               verbose=False)

    [message] = messages
    state = observe_node(message)
    assert state.error is None and state.decision is None


def test_same_entry_bar_not_evaluated_twice():
    # t no longer moves with the wall clock: over an FX weekend every pass
    # would re-send Friday's last bar. Each (instrument, t) is evaluated once.
    _, view, t = window("ny_close")
    runs = []
    graph = SimpleNamespace(run=lambda message: runs.append(message) or SimpleNamespace(
        decision=None, decision_reason="", error=None, trade_id=None))
    evaluated: dict[str, datetime] = {}

    first = runner._process_instrument("EURUSD", view, t, graph, CFG, "AUTONOMOUS", verbose=False, evaluated=evaluated)
    again = runner._process_instrument("EURUSD", view, t, graph, CFG, "AUTONOMOUS", verbose=False, evaluated=evaluated)

    assert first["decision"] != "NO NEW BAR"
    assert again == {"instrument": "EURUSD", "grade": "-", "decision": "NO NEW BAR", "trade_id": None}
    assert evaluated == {"EURUSD": t}
