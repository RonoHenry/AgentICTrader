"""The MT5 adapter's live-execution behaviour (tasks 455, 456, 459).

The profile's symbols, expiry, the ledger, the split and sync, on the patched
``mt5`` module (as test_mt5_broker_adapter.py patches it): nothing here
touches a terminal.

Validates: Requirements 3, 6.1, 7 (.kiro/specs/live-execution/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from agent.brokers.mt5 import MT5BrokerAdapter, MT5BrokerError
from agent.strategy_config import PendingExpiry
from services.market_data.mt5_clock import MT5ServerClock

CREDENTIALS = dict(login=1, password="x", server="Demo")


@pytest.fixture
def mock_mt5():
    with patch("agent.brokers.mt5.mt5") as mock:
        mock.initialize.return_value = True
        mock.TRADE_RETCODE_DONE = 10009
        mock.ORDER_TYPE_BUY, mock.ORDER_TYPE_SELL = 0, 1
        mock.ORDER_TYPE_BUY_LIMIT, mock.ORDER_TYPE_SELL_LIMIT = 2, 3
        mock.TRADE_ACTION_DEAL, mock.TRADE_ACTION_SLTP, mock.TRADE_ACTION_PENDING, mock.TRADE_ACTION_REMOVE = 1, 2, 5, 8
        mock.ORDER_TIME_GTC, mock.ORDER_TIME_SPECIFIED = 0, 2
        mock.ORDER_FILLING_IOC, mock.ORDER_FILLING_RETURN = 1, 2
        mock.symbol_info.return_value = MagicMock(
            filling_mode=2, volume_step=0.01, volume_min=0.01, volume_max=100.0,
            trade_tick_size=0.00001, trade_tick_value=1.0, expiration_mode=1 | 4,
        )
        mock.symbol_info_tick.return_value = MagicMock(ask=1.1001, bid=1.1000)
        mock.order_send.return_value = MagicMock(retcode=10009, order=555)
        mock.orders_get.return_value = ()
        mock.positions_get.return_value = ()
        yield mock


class TestTheProfilesSymbols:
    def test_a_symbol_map_names_the_broker_symbol(self, mock_mt5):
        adapter = MT5BrokerAdapter(**CREDENTIALS, symbol_of={"EURUSD": "EURUSDm"}.get)
        adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})
        assert mock_mt5.order_send.call_args[0][0]["symbol"] == "EURUSDm"
        mock_mt5.symbol_info_tick.assert_called_with("EURUSDm")


# ── expiry and the ledger (task 456) ───────────────────────────────────────

T0 = datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc)        # 09:00 New York: in the NY AM killzone
KILLZONE_END = datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc)   # 10:00 New York


class Clock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _limit(**overrides) -> dict:
    """A LONG resting below the ask (1.1001), sized $100 over a 20-pip stop."""
    return {"instrument": "EURUSD", "direction": "LONG", "entry": 1.0990, "stop_loss": 1.0970,
            "take_profit": 1.1100, "risk_amount": 100.0, "setup_id": "setup-1", **overrides}


def _adapter(clock: Clock, tmp_path=None, **kwargs) -> MT5BrokerAdapter:
    return MT5BrokerAdapter(**CREDENTIALS, clock=clock, expiry_rule=PendingExpiry.KILLZONE_END,
                            fallback_ttl=timedelta(hours=3),
                            ledger_path=(tmp_path / "ledger.json") if tmp_path is not None else None, **kwargs)


def _tickets(pending=(), open_=()):
    """orders_get / positions_get answering by ticket."""
    def orders_get(ticket=None, **_):
        return tuple(MagicMock(ticket=t, type=2, symbol="EURUSD") for t in pending if t == ticket)

    def positions_get(ticket=None, **_):
        return tuple(MagicMock(ticket=t, type=0, symbol="EURUSD", price_open=1.0990, volume=0.5, profit=0.0,
                               sl=1.0970, tp=1.1100) for t in open_ if t == ticket)
    return orders_get, positions_get


class TestExpiryIsSent:
    def test_specified_in_server_time_when_the_symbol_allows_it(self, mock_mt5):
        adapter = _adapter(Clock(), server_clock=MT5ServerClock("+2"))
        adapter.place_order(_limit())
        request = mock_mt5.order_send.call_args[0][0]
        assert request["type_time"] == mock_mt5.ORDER_TIME_SPECIFIED
        assert request["expiration"] == int(MT5ServerClock("+2").to_server(KILLZONE_END).timestamp())

    def test_gtc_when_the_symbol_allows_only_gtc(self, mock_mt5):
        mock_mt5.symbol_info.return_value.expiration_mode = 1
        adapter = _adapter(Clock(), server_clock=MT5ServerClock("+2"))
        adapter.place_order(_limit())
        request = mock_mt5.order_send.call_args[0][0]
        assert request["type_time"] == mock_mt5.ORDER_TIME_GTC and "expiration" not in request
        assert adapter.active_trade("EURUSD")["expires_at"] == KILLZONE_END.isoformat()

    def test_gtc_without_a_server_clock(self, mock_mt5):
        adapter = _adapter(Clock())
        adapter.place_order(_limit())
        assert mock_mt5.order_send.call_args[0][0]["type_time"] == mock_mt5.ORDER_TIME_GTC

    def test_a_market_order_has_no_expiry(self, mock_mt5):
        adapter = _adapter(Clock(), server_clock=MT5ServerClock("+2"))
        adapter.place_order(_limit(entry=1.1005, stop_loss=1.0985))   # above the ask: market
        request = mock_mt5.order_send.call_args[0][0]
        assert request["type_time"] == mock_mt5.ORDER_TIME_GTC
        assert adapter.active_trade("EURUSD")["expires_at"] is None

    def test_an_order_expiring_at_placement_is_recorded_not_sent(self, mock_mt5):
        adapter = _adapter(Clock(KILLZONE_END), server_clock=MT5ServerClock("+2"))
        result = adapter.place_order(_limit())
        mock_mt5.order_send.assert_not_called()
        assert result["pending"] is True and result["trade_id"]
        assert adapter.active_trade("EURUSD") is None
        assert adapter.attempted_setups() == {"setup-1"}
        assert adapter.get_position_status(result["trade_id"])["status"] == "CLOSED"


class TestSync:
    def test_a_pending_order_past_its_expiry_is_cancelled(self, mock_mt5):
        clock = Clock()
        adapter = _adapter(clock)
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets(pending=[555])
        adapter.place_order(_limit())
        mock_mt5.order_send.reset_mock()

        clock.now = KILLZONE_END - timedelta(minutes=1)
        assert adapter.sync() == []
        mock_mt5.order_send.assert_not_called()

        clock.now = KILLZONE_END
        events = adapter.sync()
        assert mock_mt5.order_send.call_args[0][0] == {"action": mock_mt5.TRADE_ACTION_REMOVE, "order": 555}
        assert [e["event"] for e in events] == ["EXPIRED"]
        assert adapter.active_trade("EURUSD") is None and adapter.active_count() == 0

    def test_a_fill_is_recorded_and_the_trade_stays_active(self, mock_mt5):
        clock = Clock()
        adapter = _adapter(clock)
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets(open_=[555])
        adapter.place_order(_limit())
        clock.now = KILLZONE_END + timedelta(minutes=5)   # past the expiry, but filled: nothing to cancel
        events = adapter.sync()
        assert [e["event"] for e in events] == ["FILLED"]
        trade = adapter.active_trade("EURUSD")
        assert trade["fill_price"] == 1.0990 and trade["filled_at"] == clock.now.isoformat()
        mock_mt5.order_send.assert_called_once()   # the placement only
        assert adapter.sync() == []                # recorded once

    def test_a_ticket_gone_from_the_terminal_closes_the_trade(self, mock_mt5):
        clock = Clock()
        adapter = _adapter(clock)
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets(open_=[555])
        adapter.place_order(_limit())
        adapter.sync()
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets()
        events = adapter.sync()
        assert [e["event"] for e in events] == ["CLOSED"]
        assert adapter.active_count() == 0

    def test_one_the_broker_expired_closes_as_expired(self, mock_mt5):
        clock = Clock()
        adapter = _adapter(clock)
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets()
        adapter.place_order(_limit())
        clock.now = KILLZONE_END
        assert [e["event"] for e in adapter.sync()] == ["EXPIRED"]


class TestTheLedger:
    def test_it_survives_a_restart(self, mock_mt5, tmp_path):
        _adapter(Clock(), tmp_path).place_order(_limit())
        reloaded = _adapter(Clock(), tmp_path)
        assert reloaded.active_trade("EURUSD")["tickets"] == [555]
        assert reloaded.attempted_setups() == {"setup-1"}
        assert not list(tmp_path.glob("*.tmp"))

    def test_a_refused_order_is_not_recorded(self, mock_mt5, tmp_path):
        adapter = _adapter(Clock(), tmp_path)
        with pytest.raises(MT5BrokerError):
            adapter.place_order(_limit(risk_amount=1.0))   # MIN_VOLUME_OVER_RISK
        assert adapter.attempted_setups() == set()

    def test_trades_are_found_by_instrument(self, mock_mt5):
        adapter = _adapter(Clock())
        adapter.place_order(_limit())
        assert adapter.active_trade("GBPUSD") is None
        assert adapter.active_trade("EURUSD")["setup_id"] == "setup-1"
        assert adapter.active_count() == 1


# ── the partial and break-even (task 459, LX-D2) ───────────────────────────

def _send_tickets(mock_mt5, *tickets):
    mock_mt5.order_send.side_effect = [MagicMock(retcode=10009, order=t) for t in tickets]


def _managed(clock=None, **kwargs) -> MT5BrokerAdapter:
    return _adapter(clock or Clock(), partial_r=3.0, partial_fraction=1 / 3, **kwargs)


def _positions(**by_ticket):
    """positions_get answering by ticket: ticket -> (price_open, price_current, sl, tp)."""
    def positions_get(ticket=None, **_):
        found = by_ticket.get(f"t{ticket}")
        if found is None:
            return ()
        price_open, price_current, sl, tp = found
        return (MagicMock(ticket=ticket, type=0, symbol="EURUSD", price_open=price_open, price_current=price_current,
                          sl=sl, tp=tp, volume=0.16, profit=0.0),)
    return positions_get


class TestTheSplit:
    def test_a_third_at_the_partial_level_the_rest_at_the_target(self, mock_mt5):
        _send_tickets(mock_mt5, 555, 556)
        adapter = _managed()
        result = adapter.place_order(_limit())   # 0.5 lots: 0.16 + 0.34; partial at 1.0990 + 3 x 20 pips
        part, rest = (c[0][0] for c in mock_mt5.order_send.call_args_list)
        assert (part["volume"], part["tp"]) == (0.16, pytest.approx(1.1050))
        assert (rest["volume"], rest["tp"]) == (0.34, 1.1100)
        assert part["sl"] == rest["sl"] == 1.0970 and part["price"] == rest["price"] == 1.0990
        trade = adapter.active_trade("EURUSD")
        assert trade["tickets"] == [555, 556] and trade["lots"] == 0.5 and result["trade_id"] == "555"
        assert adapter.active_count() == 1

    def test_too_small_to_split_runs_unmanaged(self, mock_mt5):
        adapter = _managed()
        adapter.place_order(_limit(risk_amount=2.0))   # 0.01 lots (D44)
        mock_mt5.order_send.assert_called_once()
        assert adapter.active_trade("EURUSD")["partial"] is None

    def test_a_partial_at_or_beyond_the_target_runs_unmanaged(self, mock_mt5):
        adapter = _managed()
        adapter.place_order(_limit(take_profit=1.1040))   # the partial (1.1050) is past it
        mock_mt5.order_send.assert_called_once()

    def test_without_the_partial_one_ticket(self, mock_mt5):
        adapter = _adapter(Clock())
        adapter.place_order(_limit())
        mock_mt5.order_send.assert_called_once()

    def test_the_rest_refused_cancels_the_part(self, mock_mt5):
        mock_mt5.order_send.side_effect = [MagicMock(retcode=10009, order=555), MagicMock(retcode=10013, order=0,
                                                                                         comment="Invalid request"),
                                           MagicMock(retcode=10009, order=555)]
        mock_mt5.orders_get.side_effect = lambda ticket=None, **_: (MagicMock(ticket=555),) if ticket == 555 else ()
        adapter = _managed()
        with pytest.raises(MT5BrokerError):
            adapter.place_order(_limit())
        assert mock_mt5.order_send.call_args[0][0] == {"action": mock_mt5.TRADE_ACTION_REMOVE, "order": 555}
        assert adapter.active_trade("EURUSD") is None and adapter.attempted_setups() == set()


class TestBreakEven:
    def _placed(self, mock_mt5, clock):
        _send_tickets(mock_mt5, 555, 556)
        adapter = _managed(clock)
        adapter.place_order(_limit())
        mock_mt5.order_send.reset_mock()
        mock_mt5.order_send.side_effect = None
        mock_mt5.order_send.return_value = MagicMock(retcode=10009, order=0)
        return adapter

    def test_the_part_closed_moves_the_rest_to_its_fill(self, mock_mt5):
        clock = Clock()
        adapter = self._placed(mock_mt5, clock)
        mock_mt5.positions_get.side_effect = _positions(t555=(1.0990, 1.1000, 1.0970, 1.1050),
                                                        t556=(1.0990, 1.1000, 1.0970, 1.1100))
        adapter.sync()                                         # both filled at the limit
        mock_mt5.order_send.reset_mock()
        mock_mt5.positions_get.side_effect = _positions(t556=(1.0990, 1.1052, 1.0970, 1.1100))   # the part took 3R
        events = adapter.sync()
        assert [e["event"] for e in events] == ["PARTIAL"]
        assert mock_mt5.order_send.call_args[0][0] == {"action": mock_mt5.TRADE_ACTION_SLTP, "symbol": "EURUSD",
                                                       "position": 556, "sl": 1.0990, "tp": 1.1100}
        assert adapter.active_trade("EURUSD")["partial"]["be_moved"] is True
        mock_mt5.order_send.reset_mock()
        assert adapter.sync() == [] and not mock_mt5.order_send.called   # moved once

    def test_the_part_stopped_out_moves_nothing(self, mock_mt5):
        clock = Clock()
        adapter = self._placed(mock_mt5, clock)
        mock_mt5.positions_get.side_effect = _positions(t555=(1.0990, 1.0980, 1.0970, 1.1050),
                                                        t556=(1.0990, 1.0980, 1.0970, 1.1100))
        adapter.sync()
        mock_mt5.order_send.reset_mock()
        mock_mt5.positions_get.side_effect = _positions(t556=(1.0990, 1.0969, 1.0970, 1.1100))   # at the stop
        assert adapter.sync() == []
        mock_mt5.order_send.assert_not_called()

    def test_a_fill_away_from_the_entry_resets_the_parts_target(self, mock_mt5):
        clock = Clock()
        adapter = self._placed(mock_mt5, clock)
        # Filled 1 pip better than the limit: the partial follows the fill, as the backtest's does.
        mock_mt5.positions_get.side_effect = _positions(t555=(1.0989, 1.0995, 1.0970, 1.1050),
                                                        t556=(1.0989, 1.0995, 1.0970, 1.1100))
        adapter.sync()
        request = mock_mt5.order_send.call_args[0][0]
        assert request["action"] == mock_mt5.TRADE_ACTION_SLTP and request["position"] == 555
        assert request["tp"] == pytest.approx(1.0989 + 3 * (1.0989 - 1.0970)) and request["sl"] == 1.0970


def test_a_ledger_from_before_the_partial_still_syncs(mock_mt5, tmp_path):
    import json

    (tmp_path / "ledger.json").write_text(json.dumps([{
        "trade_id": "555", "setup_id": "s0", "instrument": "EURUSD", "symbol": "EURUSD", "direction": "LONG",
        "kind": "LIMIT", "entry": 1.099, "stop_loss": 1.097, "take_profit": 1.11, "lots": 0.5, "tickets": [555],
        "placed_at": T0.isoformat(), "expires_at": None, "status": "OPEN", "filled_at": T0.isoformat(),
        "fill_price": 1.099, "closed_at": None, "exit_reason": None}]), encoding="utf-8")
    mock_mt5.positions_get.side_effect = _positions(t555=(1.099, 1.100, 1.097, 1.11))
    assert _adapter(Clock(), tmp_path).sync() == []
