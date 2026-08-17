"""MT5BrokerAdapter — BrokerClient backed by a local MetaTrader5 terminal.

Unlike agent/brokers/oanda.py (stateless REST calls per request), the
`MetaTrader5` Python package is a process-wide singleton: `mt5.initialize()`
attaches to a terminal already installed and logged into this machine, and
every other call (order_send, positions_get, symbol_info_tick, ...) is a
plain module-level function operating on that one connection. This adapter
connects lazily on first use and reuses the connection afterwards.

Windows-only, and requires the MT5 terminal for this account to be
reachable on the same machine as this process — see agent/brokers/
pepperstone.py's module docstring for the cloud-bridge alternative
(MetaApi.cloud) when that constraint doesn't work.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction.
"""
from __future__ import annotations

from typing import Any

from agent.brokers.base import BrokerClient

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - exercised only when package is absent
    mt5 = None

__all__ = ["MT5BrokerAdapter", "MT5BrokerError"]

_DEFAULT_MAGIC = 990001
_DEVIATION_POINTS = 20

#: order_send()/order_check() retcodes that mean "the request went through".
#: TRADE_RETCODE_DONE (10009) is the documented success code, but some MT5
#: demo servers reply with 0 (undocumented, but real fills: deal/order
#: tickets populated, correct price, comment "Done") instead of following
#: the standard enum.
_SUCCESS_RETCODES = frozenset({0, 10009})


class MT5BrokerError(Exception):
    """Raised when the MT5 terminal connection or an order_send() call fails."""


def _order_send_failed(result: Any) -> bool:
    return result is None or result.retcode not in _SUCCESS_RETCODES


class MT5BrokerAdapter(BrokerClient):
    """BrokerClient implementation backed by a local MT5 terminal.

    Args:
        login:         MT5 account number.
        password:      MT5 account password.
        server:        MT5 server name (e.g. ``"ICMarketsSC-Demo"``).
        path:          Optional path to terminal64.exe. Omit to let the
                       package auto-detect an already-installed terminal.
        symbol_suffix: Appended to every instrument before sending to MT5
                       (some brokers list symbols as ``"EURUSD.a"`` etc.).
        magic:         Magic number tagging orders placed by this adapter.
    """

    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        path: str | None = None,
        symbol_suffix: str = "",
        magic: int = _DEFAULT_MAGIC,
    ) -> None:
        self._login = login
        self._password = password
        self._server = server
        self._path = path
        self._symbol_suffix = symbol_suffix
        self._magic = magic
        self._connected = False

    def _ensure_connected(self) -> None:
        if self._connected:
            return
        if mt5 is None:
            raise MT5BrokerError(
                "MetaTrader5 package is not installed — pip install MetaTrader5 "
                "(Windows-only; requires a local MT5 terminal)."
            )
        kwargs: dict[str, Any] = {
            "login": self._login,
            "password": self._password,
            "server": self._server,
        }
        if self._path:
            kwargs["path"] = self._path
        if not mt5.initialize(**kwargs):
            code, desc = mt5.last_error()
            raise MT5BrokerError(f"MT5 initialize failed ({code}): {desc}")
        self._connected = True

    def _resolve_symbol(self, instrument: str) -> str:
        return f"{instrument}{self._symbol_suffix}"

    def _resolve_filling_type(self, symbol: str) -> int:
        """Pick an order-filling mode this symbol actually accepts.

        Brokers vary in which of FOK/IOC they support per symbol (see
        SYMBOL_FILLING_MODE bitmask: bit 0 = FOK, bit 1 = IOC); sending an
        unsupported mode gets order_send() rejected with "Unsupported
        filling mode" even though everything else about the request is
        valid. IOC is tried first (matches prior hardcoded behaviour), FOK
        second, and ORDER_FILLING_RETURN as the last-resort default.
        """
        info = mt5.symbol_info(symbol)
        mode = info.filling_mode if info is not None else 0
        if mode & 2:
            return mt5.ORDER_FILLING_IOC
        if mode & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def _send_closing_deal(self, position: Any, volume: float) -> Any:
        symbol = position.symbol
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5BrokerError(f"No tick data for symbol {symbol}")

        is_buy_position = position.type == mt5.ORDER_TYPE_BUY
        close_type = mt5.ORDER_TYPE_SELL if is_buy_position else mt5.ORDER_TYPE_BUY
        price = tick.bid if is_buy_position else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "price": price,
            "position": position.ticket,
            "deviation": _DEVIATION_POINTS,
            "magic": self._magic,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._resolve_filling_type(symbol),
        }
        result = mt5.order_send(request)
        if _order_send_failed(result):
            comment = getattr(result, "comment", "no result from order_send")
            raise MT5BrokerError(f"MT5 order_send failed: {comment}")
        return result

    def _get_open_position(self, trade_id: str) -> Any:
        ticket = int(trade_id)
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise MT5BrokerError(f"No open position for ticket {ticket}")
        return positions[0]

    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        self._ensure_connected()

        symbol = self._resolve_symbol(order["instrument"])
        direction = order.get("direction", "LONG").upper()
        size = float(order.get("size", 0.01))

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5BrokerError(f"No tick data for symbol {symbol}")

        order_type = mt5.ORDER_TYPE_BUY if direction == "LONG" else mt5.ORDER_TYPE_SELL
        price = tick.ask if direction == "LONG" else tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": size,
            "type": order_type,
            "price": price,
            "sl": order.get("stop_loss") or 0.0,
            "tp": order.get("take_profit") or 0.0,
            "deviation": _DEVIATION_POINTS,
            "magic": self._magic,
            "comment": str(order.get("setup_id") or "agentictrader"),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._resolve_filling_type(symbol),
        }

        result = mt5.order_send(request)
        if _order_send_failed(result):
            comment = getattr(result, "comment", "no result from order_send")
            raise MT5BrokerError(f"MT5 order_send failed: {comment}")

        ticket = str(result.order)
        return {"order_id": ticket, "trade_id": ticket}

    def set_sl_tp(self, trade_id: str, sl_price: float, tp_price: float) -> bool:
        self._ensure_connected()
        ticket = int(trade_id)
        position = self._get_open_position(trade_id)

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": ticket,
            "sl": sl_price,
            "tp": tp_price,
        }
        result = mt5.order_send(request)
        if _order_send_failed(result):
            comment = getattr(result, "comment", "no result from order_send")
            raise MT5BrokerError(f"MT5 order_send failed: {comment}")
        return True

    def close_position(self, trade_id: str) -> bool:
        self._ensure_connected()
        position = self._get_open_position(trade_id)
        self._send_closing_deal(position, position.volume)
        return True

    def partial_close(self, trade_id: str, ratio: float = 0.5) -> dict[str, Any]:
        self._ensure_connected()
        ticket = int(trade_id)
        position = self._get_open_position(trade_id)
        volume = round(position.volume * ratio, 2)
        self._send_closing_deal(position, volume)
        return {"trade_id": str(ticket), "closed_units": volume}

    def get_position_status(self, trade_id: str) -> dict[str, Any]:
        self._ensure_connected()
        ticket = int(trade_id)
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"status": "CLOSED", "unrealised_pnl": 0.0, "current_price": None}

        position = positions[0]
        tick = mt5.symbol_info_tick(position.symbol)
        is_buy_position = position.type == mt5.ORDER_TYPE_BUY
        current_price = tick.bid if is_buy_position else tick.ask

        return {
            "status": "OPEN",
            "unrealised_pnl": position.profit,
            "current_price": current_price,
        }
