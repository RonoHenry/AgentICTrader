"""PaperBrokerAdapter — simulated fills against live candles.

Lets the AUTONOMOUS execute → review → learn path run end to end, and be
scored, on a feed with no broker behind it (Binance crypto on weekends), or
on any feed without risking a demo account. Follows MT5BrokerAdapter's
conventions: an entry on the discount/premium side of the market rests as
a limit order (PENDING) instead of chasing price, and statuses are
PENDING / OPEN / CLOSED.

Fills, stops, targets and expiry come from the fill model AlgoBacktester
uses (agent/brokers/fill_model.py, task 195), so forward-test and backtest
results are comparable: limits fill only when price trades through, market
orders fill at the next bar's open on the ask (LONG) or bid (SHORT), stops
pay the instrument's slippage, and a stop wins a bar that also reaches the
target. Spreads and slippage come from the instrument specs
(config/instruments/<venue>.toml); without specs both are zero.

The runner feeds it closed M1 bars via ``update(instrument, candles)``.
Each bar is processed once, so overlapping windows are safe; a bar that is
still forming must not be passed, since its later extremes would be missed.

Each closed trade records gross R (chart prices) and net R (executed prices,
less ``fee_rate`` per side on entry and exit notional), since tight stops
can make costs dominate the outcome. Trades persist to a JSON file so a
forward test survives restarts; files written before task 195 still load.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from agent.brokers.base import BrokerClient
from agent.brokers.fill_model import Bar, FillModel, SimOrder, pending_expiry
from agent.clock import Clock, wall_clock
from agent.instruments import CommissionSpec, InstrumentSpecs
from agent.strategy_config import PendingExpiry

__all__ = ["PaperBrokerAdapter", "PaperBrokerError"]

logger = logging.getLogger(__name__)

ACTIVE = ("PENDING", "OPEN")


class PaperBrokerError(Exception):
    pass


class PaperBrokerAdapter(BrokerClient):
    def __init__(
        self,
        state_path: Optional[str | Path] = None,
        pending_ttl: timedelta = timedelta(hours=3),
        fee_rate: float = 0.0,
        on_close: Optional[Callable[[dict], None]] = None,
        specs: Optional[InstrumentSpecs] = None,
        clock: Optional[Clock] = None,
        expiry_rule: PendingExpiry = PendingExpiry.FIXED_TTL,
    ) -> None:
        """``pending_ttl`` is the fallback TTL of ``expiry_rule`` (the whole TTL
        under FIXED_TTL); the live runner passes its StrategyConfig's rule."""
        self._path = Path(state_path) if state_path else None
        self._pending_ttl = pending_ttl
        self._expiry_rule = expiry_rule
        self.commission = CommissionSpec("RATE_PER_SIDE", fee_rate)
        self._specs = specs
        self._clock = clock or _now
        self._on_close = on_close
        self._last_price: dict[str, float] = {}
        self._trades: dict[str, dict] = {}
        if self._path and self._path.exists():
            for trade in json.loads(self._path.read_text(encoding="utf-8")):
                self._trades[trade["trade_id"]] = trade

    # ── BrokerClient ───────────────────────────────────────────────────────

    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        instrument = order["instrument"]
        market = self._last_price.get(instrument)
        if market is None:
            raise PaperBrokerError(f"No price for {instrument} yet — call update() before placing orders")

        direction = order.get("direction", "LONG").upper()
        is_long = direction == "LONG"
        entry = order.get("entry")
        stop = order.get("stop_loss")
        if stop is None:
            raise PaperBrokerError("Paper orders need a stop_loss to measure R")

        is_pending = entry is not None and (entry < market if is_long else entry > market)
        if not is_pending and not (stop < market if is_long else stop > market):
            raise PaperBrokerError(
                f"Stop {stop} is on the wrong side of market {market} for a {direction} — rejected"
            )
        now = self._clock()
        trade_id = f"paper-{uuid.uuid4().hex[:10]}"
        trade = {
            "trade_id": trade_id,
            "setup_id": order.get("setup_id"),
            "instrument": instrument,
            "direction": direction,
            # A limit rests at its entry; a market order fills at the next bar's open.
            "kind": "LIMIT" if is_pending else "MARKET",
            "entry": entry if is_pending else market,
            "requested_entry": entry,
            "stop_loss": stop,
            "take_profit": order.get("take_profit"),
            "size": order.get("size"),
            "risk_amount": order.get("risk_amount"),
            "status": "PENDING",
            "placed_at": now.isoformat(),
            "expires_at": (pending_expiry(now, self._expiry_rule, self._pending_ttl).isoformat()
                           if is_pending else None),
            "filled_at": None,
            "fill_price": None,
            "ideal_fill": None,
            "closed_at": None,
            "exit_price": None,
            "ideal_exit": None,
            "exit_reason": None,
            "mae_price": None,
            "mfe_price": None,
            "processed_through": None,
            "remaining_ratio": 1.0,
            "partials": [],
            "gross_r": None,
            "net_r": None,
        }
        self._trades[trade_id] = trade
        self._save()
        logger.info("paper: %s %s %s @ %s (stop %s, target %s)", trade["kind"], direction, instrument,
                    trade["entry"], stop, trade["take_profit"])
        return {"order_id": trade_id, "trade_id": trade_id, "pending": is_pending}

    def set_sl_tp(self, trade_id: str, sl_price: float, tp_price: float) -> bool:
        trade = self._active(trade_id)
        trade["stop_loss"], trade["take_profit"] = sl_price, tp_price
        self._save()
        return True

    def close_position(self, trade_id: str) -> bool:
        trade = self._active(trade_id)
        if trade["status"] == "PENDING":
            self._finish(trade, "CANCELLED", None, None, self._clock())
        else:
            price = self._last_price[trade["instrument"]]
            self._finish(trade, "MANUAL", price, price, self._clock())
        self._save()
        return True

    def partial_close(self, trade_id: str, ratio: float = 0.5) -> dict[str, Any]:
        trade = self._active(trade_id)
        if trade["status"] == "PENDING":
            raise PaperBrokerError(f"Cannot partial-close {trade_id}: order is still pending, not yet filled")
        price = self._last_price[trade["instrument"]]
        portion = trade["remaining_ratio"] * ratio
        trade["partials"].append({"ratio": portion, "price": price, "at": self._clock().isoformat()})
        trade["remaining_ratio"] -= portion
        self._save()
        return {"trade_id": trade_id, "closed_units": portion * (trade["size"] or 0)}

    def get_position_status(self, trade_id: str) -> dict[str, Any]:
        trade = self._trades.get(trade_id)
        if trade is None or trade["status"] == "CLOSED":
            return {"status": "CLOSED", "unrealised_pnl": 0.0, "current_price": None}
        price = self._last_price.get(trade["instrument"])
        if trade["status"] == "PENDING":
            return {"status": "PENDING", "unrealised_pnl": 0.0, "current_price": price}
        sign = 1 if trade["direction"] == "LONG" else -1
        pnl = sign * (price - trade["fill_price"]) * (trade["size"] or 0) * trade["remaining_ratio"]
        return {"status": "OPEN", "unrealised_pnl": pnl, "current_price": price}

    # ── simulation ─────────────────────────────────────────────────────────

    def update(self, instrument: str, candles: Iterable[Any]) -> list[dict]:
        """Advance this instrument's trades through closed ``candles`` (objects
        with timestamp/open/high/low/close and optionally spread, oldest first).
        Returns the trades that filled or closed, each with an ``event`` key
        (FILLED, SL, TP, EXPIRED, REJECTED, or e.g. FILLED+SL on one bar)."""
        candles = list(candles)
        if candles:
            self._last_price[instrument] = candles[-1].close

        events = []
        for trade in [t for t in self._trades.values() if t["instrument"] == instrument and t["status"] in ACTIVE]:
            model = FillModel(self._spec_value(instrument, "stop_slippage"))
            order = _to_order(trade)
            done = _processed_through(trade)
            for candle in candles:
                if done is not None and candle.timestamp <= done:
                    continue  # already processed in an earlier, overlapping window
                fired = model.step(order, self._bar(instrument, candle))
                done = candle.timestamp
                if fired:
                    _from_order(trade, order)
                    if order.status == "CLOSED":
                        self._finish(trade, order.exit_reason, order.ideal_exit, order.exit, order.closed_at)
                    events.append({**trade, "event": "+".join(e.kind for e in fired)})
                if order.status == "CLOSED":
                    break
            _from_order(trade, order)
            trade["processed_through"] = done.isoformat() if done is not None else None
        if events or candles:
            self._save()
        return events

    def _bar(self, instrument: str, candle: Any) -> Bar:
        # The larger of the bar's recorded spread and the instrument's typical
        # spread (Req 5.1): many feeds record 0 or the bar's minimum, and
        # Binance klines record none.
        recorded = getattr(candle, "spread", None) or 0.0
        return Bar(timestamp=candle.timestamp, open=candle.open, high=candle.high, low=candle.low,
                   close=candle.close, spread=max(float(recorded), self._spec_value(instrument, "default_spread")))

    def _spec_value(self, instrument: str, field: str) -> float:
        return 0.0 if self._specs is None else getattr(self._specs[instrument], field)

    def _finish(self, trade: dict, reason: str, ideal_exit: Optional[float], exit_price: Optional[float],
                when: datetime) -> None:
        trade.update(status="CLOSED", exit_reason=reason, ideal_exit=ideal_exit, exit_price=exit_price,
                     closed_at=when.isoformat())
        if trade["fill_price"] is not None and exit_price is not None:
            trade["gross_r"], trade["net_r"] = self._r_multiples(trade)
        if self._on_close:
            self._on_close(trade)

    def _r_multiples(self, trade: dict) -> tuple[float, float]:
        """Gross R on chart (bid) prices, net R on executed prices less fees.
        1R is the planned risk on the chart: ideal fill to stop."""
        fill, ideal_fill = trade["fill_price"], trade.get("ideal_fill") or trade["fill_price"]
        risk = abs(ideal_fill - trade["stop_loss"]) or float("nan")
        sign = 1 if trade["direction"] == "LONG" else -1
        # Manual partial closes book at the last price on both measures.
        legs = [(p["ratio"], p["price"], p["price"]) for p in trade["partials"]]
        legs.append((trade["remaining_ratio"], trade.get("ideal_exit") or trade["exit_price"], trade["exit_price"]))
        gross = sum(ratio * sign * (ideal - ideal_fill) for ratio, ideal, _ in legs) / risk
        executed = sum(ratio * sign * (price - fill) for ratio, _, price in legs) / risk
        fees = self.commission.value * (fill + sum(ratio * price for ratio, _, price in legs)) / risk
        return round(gross, 3), round(executed - fees, 3)

    # ── reporting / helpers ────────────────────────────────────────────────

    def active_trade(self, instrument: str) -> Optional[dict]:
        return next((t for t in self._trades.values() if t["instrument"] == instrument and t["status"] in ACTIVE), None)

    def trades(self) -> list[dict]:
        return sorted(self._trades.values(), key=lambda t: t["placed_at"])

    def report(self) -> str:
        trades = self.trades()
        closed = [t for t in trades if t["status"] == "CLOSED"]
        filled = [t for t in closed if t["gross_r"] is not None]
        wins = [t for t in filled if t["gross_r"] > 0]
        lines = [
            f"{'placed (UTC)':<17} {'instrument':<9} {'dir':<5} {'entry':>12} {'stop':>12} {'target':>12} "
            f"{'status':<8} {'exit':<9} {'gross R':>8} {'net R':>8}",
        ]
        for t in trades:
            lines.append(
                f"{t['placed_at'][:16]:<17} {t['instrument']:<9} {t['direction']:<5} {_fmt(t['entry']):>12} "
                f"{_fmt(t['stop_loss']):>12} {_fmt(t['take_profit']):>12} {t['status']:<8} "
                f"{t['exit_reason'] or '':<9} {_fmt(t['gross_r']):>8} {_fmt(t['net_r']):>8}"
            )
        gross = sum(t["gross_r"] for t in filled)
        net = sum(t["net_r"] for t in filled)
        lines.append(
            f"\n{len(trades)} orders: {len(filled)} filled & closed ({len(wins)} won), "
            f"{sum(t['exit_reason'] == 'EXPIRED' for t in closed)} expired unfilled, "
            f"{sum(t['status'] in ACTIVE for t in trades)} still active. "
            f"Total {gross:+.2f}R gross, {net:+.2f}R net of costs ({self.commission.value:.2%}/side fees)."
        )
        return "\n".join(lines)

    def _active(self, trade_id: str) -> dict:
        trade = self._trades.get(trade_id)
        if trade is None or trade["status"] not in ACTIVE:
            raise PaperBrokerError(f"No open position or pending order for {trade_id}")
        return trade

    def _save(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-rename so a crash mid-write can't leave a truncated
            # file that breaks the next start.
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(json.dumps(self.trades(), indent=2, default=str), encoding="utf-8")
            os.replace(tmp, self._path)


def _to_order(trade: dict) -> SimOrder:
    """The trade dict as a fill-model order. Trades saved before task 195 lack
    kind / ideal prices / excursions: an OPEN one continues from its fill."""
    fill = trade["fill_price"]
    return SimOrder(
        order_id=trade["trade_id"],
        setup_id=trade.get("setup_id") or "",
        instrument=trade["instrument"],
        direction=trade["direction"],
        kind=trade.get("kind") or ("LIMIT" if trade["status"] == "PENDING" else "MARKET"),
        entry=trade["entry"],
        stop=trade["stop_loss"],
        target=trade["take_profit"],
        placed_at=datetime.fromisoformat(trade["placed_at"]),
        expires_at=datetime.fromisoformat(trade["expires_at"]) if trade.get("expires_at") else None,
        status=trade["status"],
        ideal_fill=trade.get("ideal_fill", fill) if fill is not None else None,
        fill=fill,
        filled_at=datetime.fromisoformat(trade["filled_at"]) if trade.get("filled_at") else None,
        mae_price=trade.get("mae_price") if trade.get("mae_price") is not None else fill,
        mfe_price=trade.get("mfe_price") if trade.get("mfe_price") is not None else fill,
    )


def _from_order(trade: dict, order: SimOrder) -> None:
    trade.update(
        status=order.status,
        fill_price=order.fill,
        ideal_fill=order.ideal_fill,
        filled_at=order.filled_at.isoformat() if order.filled_at else None,
        mae_price=order.mae_price,
        mfe_price=order.mfe_price,
    )


def _processed_through(trade: dict) -> Optional[datetime]:
    """The last bar this trade was stepped through. Trades saved before task 195
    only record their fill bar: bars up to it were already processed."""
    marker = trade.get("processed_through") or trade.get("fill_bar")
    return datetime.fromisoformat(marker) if marker else None


def _now() -> datetime:
    return wall_clock()


def _fmt(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.6g}"
