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
# MqlTradeRequest.comment is capped at 27 chars by MT5 itself — order_send()
# rejects anything longer client-side with "Invalid comment argument"
# (confirmed live by bisection: 27 succeeds, 31 fails — 31 is a commonly
# misquoted figure, not what this terminal build actually enforces).
# Truncated, not hashed: this is a human-readable trace back to the setup,
# not an identity requirement.
_MAX_COMMENT_LENGTH = 27

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


def _describe_order_send_failure(result: Any) -> str:
    """Best-effort failure reason for a failed order_send() call.

    A ``None`` result means the terminal rejected the request before it
    ever reached the trade server (invalid stops, market closed, ...) —
    order_send() itself carries no reason in that case, but
    mt5.last_error() does.
    """
    if result is not None:
        return getattr(result, "comment", f"retcode={result.retcode}")
    if mt5 is not None:
        code, desc = mt5.last_error()
        return f"order_send() returned None — last_error=({code}, {desc!r})"
    return "order_send() returned None"


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

    def _normalize_volume(self, symbol: str, size: float) -> float:
        """Round *size* to the symbol's volume_step and clamp to [min, max].

        A risk-engine-computed lot size (e.g. equity*1%/sl_pips) is very
        rarely already an exact multiple of the broker's step — MT5 rejects
        anything else outright with "Invalid volume" rather than rounding
        it for you (observed live: 0.032 lots rejected on a 0.01 step).
        """
        info = mt5.symbol_info(symbol)
        if info is None or not info.volume_step:
            return size
        step = info.volume_step
        normalized = round(size / step) * step
        normalized = max(info.volume_min, min(info.volume_max, normalized))
        decimals = len(str(step).split(".")[-1]) if "." in str(step) else 0
        return round(normalized, decimals)

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
            raise MT5BrokerError(f"MT5 order_send failed: {_describe_order_send_failure(result)}")
        return result

    def _get_open_position(self, trade_id: str) -> Any:
        ticket = int(trade_id)
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise MT5BrokerError(f"No open position for ticket {ticket}")
        return positions[0]

    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """Place a market or pending order depending on where ``entry`` sits.

        ICT-style setups (see liquidity_engine's SetupGrader) grade a zone
        as valid to trade *from*, not necessarily fillable this instant —
        ``suggested_entry`` is routinely well away from the live price
        (an OTE retracement, an unmitigated order block, ...). Firing a
        market order in that case attaches SL/TP computed relative to a
        price we never actually entered at, which order_send() correctly
        rejects (observed live: a LONG's take-profit landing behind the
        actual market entry once price had already run past the zone).

        So: when ``order["entry"]`` is on the discount/premium side of the
        current market (below ask for a LONG, above bid for a SHORT), this
        places a resting BUY_LIMIT/SELL_LIMIT at that price instead of
        chasing the market. When entry is missing or already reached, it
        places a market order exactly as before — existing callers that
        never set "entry" are unaffected.

        Known follow-on gap: get_position_status()/close_position()/
        partial_close() all look the order ticket up via
        mt5.positions_get(), which only returns *filled* positions. A
        pending order that hasn't triggered yet won't be found there — it
        reads as CLOSED/"no open position" rather than "still pending".
        Distinguishing those states needs its own tracking and isn't done
        here.
        """
        self._ensure_connected()

        symbol = self._resolve_symbol(order["instrument"])
        direction = order.get("direction", "LONG").upper()
        size = self._normalize_volume(symbol, float(order.get("size", 0.01)))
        requested_entry = order.get("entry")

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5BrokerError(f"No tick data for symbol {symbol}")

        is_long = direction == "LONG"
        market_price = tick.ask if is_long else tick.bid

        is_pending = requested_entry is not None and (
            requested_entry < market_price if is_long else requested_entry > market_price
        )

        if is_pending:
            order_type = mt5.ORDER_TYPE_BUY_LIMIT if is_long else mt5.ORDER_TYPE_SELL_LIMIT
            price = requested_entry
            action = mt5.TRADE_ACTION_PENDING
            # Pending orders don't fill immediately, so the IOC/FOK "fill
            # now or cancel" semantics _resolve_filling_type calibrates for
            # market deals don't apply — RETURN is what pending orders
            # expect across brokers.
            type_filling = mt5.ORDER_FILLING_RETURN
        else:
            order_type = mt5.ORDER_TYPE_BUY if is_long else mt5.ORDER_TYPE_SELL
            price = market_price
            action = mt5.TRADE_ACTION_DEAL
            type_filling = self._resolve_filling_type(symbol)

        request = {
            "action": action,
            "symbol": symbol,
            "volume": size,
            "type": order_type,
            "price": price,
            "sl": order.get("stop_loss") or 0.0,
            "tp": order.get("take_profit") or 0.0,
            "deviation": _DEVIATION_POINTS,
            "magic": self._magic,
            "comment": str(order.get("setup_id") or "agentictrader")[:_MAX_COMMENT_LENGTH],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": type_filling,
        }

        result = mt5.order_send(request)
        if _order_send_failed(result):
            raise MT5BrokerError(f"MT5 order_send failed: {_describe_order_send_failure(result)}")

        ticket = str(result.order)
        return {"order_id": ticket, "trade_id": ticket, "pending": is_pending}

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
            raise MT5BrokerError(f"MT5 order_send failed: {_describe_order_send_failure(result)}")
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
