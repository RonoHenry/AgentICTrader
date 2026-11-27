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

A risk-sized order (one carrying ``risk_amount``, as execute_node sends) is
sized by the backtest's rule, agent.brokers.sizing (live-execution
Requirement 1): rounded down, capped, and refused rather than sent at a size
nobody computed. The stop backstop (Requirement 2) refuses an order whose
spread and stop slippage are more than ``max_stop_overrun`` of the stop.
Refusals raise MT5BrokerError with a ``reason`` code, which execute_node turns
into a SKIP.

With ``expiry_rule`` set (the live runner passes its StrategyConfig's), a
pending order expires when the backtest's would (Requirement 3): the shared
``pending_expiry``, sent as ORDER_TIME_SPECIFIED in server time when the
symbol allows it and a ``server_clock`` is given, GTC otherwise. Either way
``sync()``, which the runner calls every minute, cancels own pending orders
past their expiry. The ledger (``MT5Ledger``, persisted to ``ledger_path``)
records each trade placed: its tickets, setup, prices and expiry. The
terminal stays the truth for each ticket's state; ``sync()`` reads it.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction;
live-execution Requirements 1, 2, 3, 5.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from agent.brokers.base import BrokerClient
from agent.brokers.fill_model import pending_expiry
from agent.brokers.sizing import SizingError, lots_for_risk, stop_overrun
from agent.clock import Clock, wall_clock
from agent.instruments import InstrumentSpecs
from agent.strategy_config import PendingExpiry
from services.market_data.mt5_clock import MT5ServerClock

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - exercised only when package is absent
    mt5 = None

__all__ = ["MT5BrokerAdapter", "MT5BrokerError", "MT5Ledger"]

ACTIVE = ("PENDING", "OPEN")
#: SYMBOL_EXPIRATION_MODE's bit for an order with its own expiry time.
_SYMBOL_EXPIRATION_SPECIFIED = 4

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


#: The stop backstop's default (live-execution LX-D1): spread plus slippage at
#: most half the stop, so a stop-out costs at most ~1.5 budgets.
DEFAULT_MAX_STOP_OVERRUN = 0.5


class MT5BrokerError(Exception):
    """Raised when the MT5 terminal connection or an order_send() call fails,
    or when an order is refused before it is sent. ``reason`` is the code the
    journal records (MIN_VOLUME_OVER_RISK, STOP_TOO_TIGHT, ...)."""

    def __init__(self, message: str, reason: str = "BROKER_ERROR") -> None:
        super().__init__(message)
        self.reason = reason


def _refused(reason: str, detail: str) -> MT5BrokerError:
    return MT5BrokerError(f"{reason}: {detail}", reason)


class MT5Ledger:
    """The trades this runner placed on MT5, persisted so a restart picks them up (live-execution Requirements 3, 5).

    One entry per trade, in placement order: ``trade_id``, ``setup_id``, ``instrument``, ``symbol``,
    ``direction``, ``kind`` (LIMIT / MARKET), ``entry``, ``stop_loss``, ``take_profit``, ``lots``, ``tickets``,
    ``placed_at``, ``expires_at``, ``status`` (PENDING / OPEN / CLOSED), ``filled_at``, ``fill_price``,
    ``closed_at`` and ``exit_reason``. Written with write-then-rename, as the paper broker's file is, so a crash
    mid-write can't leave a truncated file. Without a path it lives in memory.
    """

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self._path = Path(path) if path else None
        self._trades: dict[str, dict] = {}
        if self._path and self._path.exists():
            for trade in json.loads(self._path.read_text(encoding="utf-8")):
                self._trades[trade["trade_id"]] = trade

    def add(self, trade: dict) -> None:
        self._trades[trade["trade_id"]] = trade
        self.save()

    def get(self, trade_id: str) -> Optional[dict]:
        return self._trades.get(trade_id)

    def trades(self) -> list[dict]:
        return list(self._trades.values())

    def active(self) -> list[dict]:
        return [t for t in self._trades.values() if t["status"] in ACTIVE]

    def save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(self.trades(), indent=2, default=str), encoding="utf-8")
        os.replace(tmp, self._path)


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
        specs:         The broker profile's instrument specs: the stop
                       backstop counts each instrument's stop slippage.
                       Without them it counts the spread only.
        max_stop_overrun: The stop backstop (live-execution Req 2); None
                       switches it off.
        min_volume_tolerance: How far over its budget the minimum volume
                       may risk (the backtest's 10%).
        symbol_of:     The broker profile's symbol for an instrument
                       (``BrokerProfile.symbol``); the suffix applies to
                       instruments it doesn't name.
        expiry_rule, fallback_ttl: When a pending order expires, as in the
                       backtest (StrategyConfig.pending_expiry / fallback_ttl).
                       None: GTC, never cancelled (manual use).
        server_clock:  The broker's server clock, to send the expiry in
                       server time. Without it orders go GTC and only
                       ``sync()`` cancels them.
        clock:         Now, in UTC (the wall clock by default).
        ledger_path:   Where the ledger persists; None keeps it in memory.
    """

    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        path: str | None = None,
        symbol_suffix: str = "",
        magic: int = _DEFAULT_MAGIC,
        specs: Optional[InstrumentSpecs] = None,
        max_stop_overrun: Optional[float] = DEFAULT_MAX_STOP_OVERRUN,
        min_volume_tolerance: float = 0.10,
        symbol_of: Optional[Callable[[str], Optional[str]]] = None,
        expiry_rule: Optional[PendingExpiry] = None,
        fallback_ttl: timedelta = timedelta(hours=3),
        server_clock: Optional[MT5ServerClock] = None,
        clock: Optional[Clock] = None,
        ledger_path: Optional[str | Path] = None,
    ) -> None:
        self._login = login
        self._password = password
        self._server = server
        self._path = path
        self._symbol_suffix = symbol_suffix
        self._symbol_of = symbol_of
        self._magic = magic
        self._specs = specs
        self._max_stop_overrun = max_stop_overrun
        self._tolerance = min_volume_tolerance
        self._expiry_rule = expiry_rule
        self._fallback_ttl = fallback_ttl
        self._server_clock = server_clock
        self._clock = clock or wall_clock
        self.ledger = MT5Ledger(ledger_path)
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
        """The broker's symbol: the profile's (``symbol_of``, live-execution Req 6.1), else the instrument plus the
        suffix."""
        if self._symbol_of is not None:
            mapped = self._symbol_of(instrument)
            if mapped:
                return mapped
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

    def _lots_for_risk(self, instrument: str, symbol: str, reference: float, stop_loss: Any, risk_amount: float,
                       tick: Any) -> float:
        """The lots a risk-sized order trades, by the backtest's rule (live-execution Requirement 1).

        RiskEngine's position_size is OANDA units, so it is never the volume. The money a lot loses per price unit
        is the symbol's own trade_tick_value / trade_tick_size: MT5 computes it in the account currency, contract
        size and any cross conversion included, so JPY pairs, indices and crosses need no pip arithmetic here. The
        reference is the limit price, or the market for a market order without an entry, as in SimBroker.

        Raises MT5BrokerError: INVALID_ORDER without a stop, NO_TICK_VALUE without the symbol's tick data,
        STOP_TOO_TIGHT from the backstop, MIN_VOLUME_OVER_RISK from the sizing rule.
        """
        if stop_loss is None:
            raise _refused("INVALID_ORDER", f"{instrument}: a risk-sized order needs a stop_loss")
        info = mt5.symbol_info(symbol)
        tick_size = getattr(info, "trade_tick_size", None) if info is not None else None
        tick_value = getattr(info, "trade_tick_value", None) if info is not None else None
        if not tick_size or not tick_value or not getattr(info, "volume_step", None):
            raise _refused("NO_TICK_VALUE", f"{symbol}: no trade_tick_value/trade_tick_size/volume_step to size on")
        distance = abs(float(reference) - float(stop_loss))
        if self._max_stop_overrun is not None:
            spread = max(0.0, float(tick.ask) - float(tick.bid))
            slippage = (self._specs[instrument].stop_slippage
                        if self._specs is not None and instrument in self._specs else 0.0)
            if stop_overrun(distance, spread, slippage) > self._max_stop_overrun:
                raise _refused("STOP_TOO_TIGHT", f"{instrument}: spread {spread:.6g} + slippage {slippage:.6g} over "
                                                 f"{self._max_stop_overrun:.0%} of the {distance:.6g} stop")
        try:
            return lots_for_risk(risk_amount, distance / tick_size * tick_value, info.volume_min, info.volume_step,
                                 info.volume_max, self._tolerance)
        except SizingError as exc:
            raise _refused(exc.reason, f"{instrument}: {str(exc).split(': ', 1)[-1]}") from None

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

    def _lookup_trade(self, trade_id: str) -> tuple[str, Any]:
        """Look up *trade_id* across both mt5.positions_get() (filled) and
        mt5.orders_get() (still pending) — positions_get() alone can't tell
        "still pending" apart from "closed/never existed", which used to
        make get_position_status()/close_position()/partial_close() all
        misreport a live resting limit order as gone.

        Returns ("OPEN", position) | ("PENDING", order) | ("CLOSED", None).
        An id that isn't a ticket (the ledger's ``unsent-...``, LX-D7) was
        never at the terminal: CLOSED.
        """
        if not str(trade_id).isdigit():
            return "CLOSED", None
        ticket = int(trade_id)
        positions = mt5.positions_get(ticket=ticket)
        if positions:
            return "OPEN", positions[0]
        pending = mt5.orders_get(ticket=ticket)
        if pending:
            return "PENDING", pending[0]
        return "CLOSED", None

    def _cancel_pending_order(self, ticket: int) -> Any:
        request = {"action": mt5.TRADE_ACTION_REMOVE, "order": ticket}
        result = mt5.order_send(request)
        if _order_send_failed(result):
            raise MT5BrokerError(f"MT5 order_send failed: {_describe_order_send_failure(result)}")
        return result

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

        get_position_status()/close_position()/partial_close() all look the
        ticket up via _lookup_trade(), which checks mt5.orders_get() (still
        pending) as well as mt5.positions_get() (filled) — a resting limit
        order placed here reads as PENDING, not CLOSED, until it actually
        fills.
        """
        self._ensure_connected()

        instrument = order["instrument"]
        symbol = self._resolve_symbol(instrument)
        direction = order.get("direction", "LONG").upper()
        requested_entry = order.get("entry")

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5BrokerError(f"No tick data for symbol {symbol}", "NO_PRICE")

        is_long = direction == "LONG"
        market_price = tick.ask if is_long else tick.bid

        risk_amount = order.get("risk_amount")
        if risk_amount:
            reference = requested_entry if requested_entry is not None else market_price
            size = self._lots_for_risk(instrument, symbol, reference, order.get("stop_loss"), float(risk_amount),
                                       tick)
        else:
            # A manual order: its explicit size, on the symbol's step.
            size = self._normalize_volume(symbol, float(order.get("size", 0.01)))

        is_pending = requested_entry is not None and (
            requested_entry < market_price if is_long else requested_entry > market_price
        )

        now = self._clock()
        expires_at = (pending_expiry(now, self._expiry_rule, self._fallback_ttl)
                      if is_pending and self._expiry_rule is not None else None)
        trade = {
            "trade_id": None, "setup_id": order.get("setup_id"), "instrument": instrument, "symbol": symbol,
            "direction": direction, "kind": "LIMIT" if is_pending else "MARKET",
            "entry": requested_entry if requested_entry is not None else market_price,
            "stop_loss": order.get("stop_loss"), "take_profit": order.get("take_profit"), "lots": size,
            "tickets": [], "placed_at": now.isoformat(), "expires_at": expires_at.isoformat() if expires_at else None,
            "status": "PENDING", "filled_at": None, "fill_price": None, "closed_at": None, "exit_reason": None,
        }
        if expires_at is not None and expires_at <= now:
            # Placed at the end of its killzone: the backtest places it and it expires unfilled. Nothing is sent;
            # the ledger records it, so the setup counts as attempted (LX-D7).
            trade.update(trade_id=f"unsent-{now:%Y%m%dT%H%M%S}-{instrument}", status="CLOSED",
                         closed_at=now.isoformat(), exit_reason="EXPIRED")
            self.ledger.add(trade)
            return {"order_id": trade["trade_id"], "trade_id": trade["trade_id"], "pending": True}

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
        if expires_at is not None and self._server_clock is not None and self._allows_specified_expiry(symbol):
            request["type_time"] = mt5.ORDER_TIME_SPECIFIED
            request["expiration"] = int(self._server_clock.to_server(expires_at).timestamp())

        result = mt5.order_send(request)
        if _order_send_failed(result):
            raise MT5BrokerError(f"MT5 order_send failed: {_describe_order_send_failure(result)}")

        ticket = str(result.order)
        trade.update(trade_id=ticket, tickets=[int(result.order)])
        self.ledger.add(trade)
        return {"order_id": ticket, "trade_id": ticket, "pending": is_pending}

    def _allows_specified_expiry(self, symbol: str) -> bool:
        info = mt5.symbol_info(symbol)
        mode = getattr(info, "expiration_mode", 0) if info is not None else 0
        return isinstance(mode, int) and bool(mode & _SYMBOL_EXPIRATION_SPECIFIED)

    # ── the ledger, against the terminal (live-execution Requirements 3, 5) ──

    def sync(self) -> list[dict]:
        """Bring each active trade up to date with the terminal, now. Returns the trades that changed, each with an
        ``event``: FILLED (first seen as a position), EXPIRED (cancelled here past its expiry, or gone unfilled after
        it) or CLOSED (gone from the terminal).

        The runner calls it every minute (LX-D5). A pending order past its expiry is cancelled whether it was sent
        with one or GTC (LX-D6)."""
        self._ensure_connected()
        now = self._clock()
        events = []
        for trade in self.ledger.active():
            event = self._sync_trade(trade, now)
            if event:
                events.append({**trade, "event": event})
        if events:
            self.ledger.save()
        return events

    def _sync_trade(self, trade: dict, now: datetime) -> Optional[str]:
        states = {ticket: self._lookup_trade(str(ticket)) for ticket in trade["tickets"]}
        expired = trade["expires_at"] is not None and now >= datetime.fromisoformat(trade["expires_at"])
        pending = [ticket for ticket, (state, _) in states.items() if state == "PENDING"]
        opened = [obj for state, obj in states.values() if state == "OPEN"]
        if expired and pending:
            for ticket in pending:
                self._cancel_pending_order(ticket)
            pending = []
        if opened:
            if trade["status"] == "PENDING":
                trade.update(status="OPEN", filled_at=now.isoformat(), fill_price=float(opened[0].price_open))
                return "FILLED"
            return None
        if pending:
            return None
        # Nothing left at the terminal.
        never_filled = trade["status"] == "PENDING"
        reason = "EXPIRED" if never_filled and expired else "CLOSED"
        trade.update(status="CLOSED", closed_at=now.isoformat(), exit_reason=reason)
        return reason

    def active_trade(self, instrument: str) -> Optional[dict]:
        """The instrument's own pending or open trade, if any (one per instrument, Requirement 5.1)."""
        return next((t for t in self.ledger.active() if t["instrument"] == instrument), None)

    def active_count(self) -> int:
        """Own trades pending or open: a split trade counts once (Requirement 7.4)."""
        return len(self.ledger.active())

    def account_snapshot(self) -> tuple[float, float]:
        """The account's (balance, equity) from the terminal, for the risk engine's exposure (Requirement 4.1)."""
        self._ensure_connected()
        info = mt5.account_info()
        if info is None:
            code, desc = mt5.last_error()
            raise MT5BrokerError(f"MT5 account_info failed ({code}): {desc}", "NO_ACCOUNT")
        return float(info.balance), float(info.equity)

    def attempted_setups(self) -> set[str]:
        """Every setup ordered from this ledger, whatever became of it (algo-backtester D6)."""
        return {t["setup_id"] for t in self.ledger.trades() if t.get("setup_id")}

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
        """Close an open position, or cancel a still-pending resting order.

        "Close this trade" is the caller's intent either way — a pending
        limit order that never filled has nothing to close via a market
        deal, so it's cancelled instead of raising "no open position" for
        a trade that's actually still live and working.
        """
        self._ensure_connected()
        state, obj = self._lookup_trade(trade_id)
        if state == "OPEN":
            self._send_closing_deal(obj, obj.volume)
            return True
        if state == "PENDING":
            self._cancel_pending_order(int(trade_id))
            return True
        raise MT5BrokerError(f"No open position or pending order for ticket {trade_id}")

    def partial_close(self, trade_id: str, ratio: float = 0.5) -> dict[str, Any]:
        """Close ``ratio`` of an open position's current size at market.

        Only meaningful for an already-filled position — review_node only
        calls this once r_multiple is computable, which structurally
        implies a fill already happened — so a still-pending order here
        raises a clear, specific error rather than silently misreporting
        as "no open position" (the pre-fix behaviour) or inventing
        partial-cancel semantics that don't have a clean real-world
        meaning for a resting limit order.
        """
        self._ensure_connected()
        state, obj = self._lookup_trade(trade_id)
        if state == "PENDING":
            raise MT5BrokerError(
                f"Cannot partial-close ticket {trade_id}: order is still pending, not yet filled"
            )
        if state == "CLOSED":
            raise MT5BrokerError(f"No open position for ticket {trade_id}")
        ticket = int(trade_id)
        volume = round(obj.volume * ratio, 2)
        self._send_closing_deal(obj, volume)
        return {"trade_id": str(ticket), "closed_units": volume}

    def get_position_status(self, trade_id: str) -> dict[str, Any]:
        self._ensure_connected()
        state, obj = self._lookup_trade(trade_id)

        if state == "OPEN":
            tick = mt5.symbol_info_tick(obj.symbol)
            is_buy_position = obj.type == mt5.ORDER_TYPE_BUY
            current_price = tick.bid if is_buy_position else tick.ask
            return {"status": "OPEN", "unrealised_pnl": obj.profit, "current_price": current_price}

        if state == "PENDING":
            tick = mt5.symbol_info_tick(obj.symbol)
            is_buy_order = obj.type == mt5.ORDER_TYPE_BUY_LIMIT
            current_price = (tick.ask if is_buy_order else tick.bid) if tick is not None else None
            return {"status": "PENDING", "unrealised_pnl": 0.0, "current_price": current_price}

        return {"status": "CLOSED", "unrealised_pnl": 0.0, "current_price": None}
