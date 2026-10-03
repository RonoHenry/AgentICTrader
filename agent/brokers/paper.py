"""PaperBrokerAdapter — simulated fills against live candles.

Lets the AUTONOMOUS execute → review → learn path run end to end, and be
scored, on a feed with no broker behind it (Binance crypto on weekends), or
on any feed without risking a demo account. Follows MT5BrokerAdapter's
conventions: an entry on the discount/premium side of the market rests as
a limit order (PENDING) instead of chasing price, and statuses are
PENDING / OPEN / CLOSED.

The runner feeds it candles via ``update(instrument, candles)`` (M1 is
best); fills and exits are decided from each bar's high/low:

- A bar only counts if it opened at or after the order was placed.
- Ambiguity resolves against the trade: if a bar touches both stop and
  target, it's a stop-out; a limit fill bar can stop out but not take
  profit (the target may have printed before the fill).
- Exits fill exactly at the stop/target level — no slippage or spread.
- Pending orders expire after ``pending_ttl``.

Each closed trade records gross R and fee-adjusted net R
(``fee_rate`` per side on entry and exit notional), since tight stops
can make fees dominate the outcome.

Trades persist to a JSON file so a forward test survives restarts.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from agent.brokers.base import BrokerClient

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
    ) -> None:
        self._path = Path(state_path) if state_path else None
        self._pending_ttl = pending_ttl
        self._fee_rate = fee_rate
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
        now = _now()
        trade_id = f"paper-{uuid.uuid4().hex[:10]}"
        trade = {
            "trade_id": trade_id,
            "setup_id": order.get("setup_id"),
            "instrument": instrument,
            "direction": direction,
            "entry": entry if is_pending else market,
            "requested_entry": entry,
            "stop_loss": stop,
            "take_profit": order.get("take_profit"),
            "size": order.get("size"),
            "risk_amount": order.get("risk_amount"),
            "status": "PENDING" if is_pending else "OPEN",
            "placed_at": now.isoformat(),
            "expires_at": (now + self._pending_ttl).isoformat() if is_pending else None,
            "filled_at": None if is_pending else now.isoformat(),
            "fill_price": None if is_pending else market,
            "closed_at": None,
            "exit_price": None,
            "exit_reason": None,
            "remaining_ratio": 1.0,
            "partials": [],
            "gross_r": None,
            "net_r": None,
        }
        if not is_pending and not _stop_on_correct_side(trade, market):
            raise PaperBrokerError(
                f"Stop {stop} is on the wrong side of market {market} for a {direction} — rejected"
            )
        self._trades[trade_id] = trade
        self._save()
        logger.info("paper: %s %s %s @ %s (stop %s, target %s)", trade["status"], direction, instrument,
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
            self._close(trade, None, "CANCELLED", _now())
        else:
            self._close(trade, self._last_price[trade["instrument"]], "MANUAL", _now())
        return True

    def partial_close(self, trade_id: str, ratio: float = 0.5) -> dict[str, Any]:
        trade = self._active(trade_id)
        if trade["status"] == "PENDING":
            raise PaperBrokerError(f"Cannot partial-close {trade_id}: order is still pending, not yet filled")
        price = self._last_price[trade["instrument"]]
        portion = trade["remaining_ratio"] * ratio
        trade["partials"].append({"ratio": portion, "price": price, "at": _now().isoformat()})
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
        """Advance this instrument's trades through ``candles`` (objects with
        timestamp/open/high/low/close, oldest first). Returns the trades that
        filled or closed, each with an ``event`` key."""
        candles = list(candles)
        if candles:
            self._last_price[instrument] = candles[-1].close

        events = []
        for trade in [t for t in self._trades.values() if t["instrument"] == instrument and t["status"] in ACTIVE]:
            placed_at = datetime.fromisoformat(trade["placed_at"])
            for bar in candles:
                if bar.timestamp < placed_at:
                    continue
                event = self._step(trade, bar)
                if event:
                    events.append({**trade, "event": event})
                if trade["status"] == "CLOSED":
                    break
        if events:
            self._save()
        return events

    def _step(self, trade: dict, bar: Any) -> Optional[str]:
        is_long = trade["direction"] == "LONG"
        stop, target = trade["stop_loss"], trade["take_profit"]
        stop_hit = bar.low <= stop if is_long else bar.high >= stop
        target_hit = target is not None and (bar.high >= target if is_long else bar.low <= target)

        if trade["status"] == "PENDING":
            if bar.timestamp >= datetime.fromisoformat(trade["expires_at"]):
                self._close(trade, None, "EXPIRED", bar.timestamp)
                return "EXPIRED"
            touched = bar.low <= trade["entry"] if is_long else bar.high >= trade["entry"]
            if not touched:
                return None
            trade.update(status="OPEN", fill_price=trade["entry"], filled_at=bar.timestamp.isoformat(),
                         fill_bar=bar.timestamp.isoformat())
            if stop_hit:
                self._close(trade, stop, "SL", bar.timestamp)
                return "FILLED+SL"
            return "FILLED"

        # update() re-scans recent bars each call: skip bars before the fill,
        # and on the fill bar itself only a stop-out can count.
        fill_bar = trade.get("fill_bar")
        if fill_bar is not None:
            fill_bar = datetime.fromisoformat(fill_bar)
            if bar.timestamp < fill_bar:
                return None
            if bar.timestamp == fill_bar:
                target_hit = False

        if stop_hit:
            self._close(trade, stop, "SL", bar.timestamp)
            return "SL"
        if target_hit:
            self._close(trade, target, "TP", bar.timestamp)
            return "TP"
        return None

    def _close(self, trade: dict, exit_price: Optional[float], reason: str, when: datetime) -> None:
        trade.update(status="CLOSED", exit_price=exit_price, exit_reason=reason, closed_at=when.isoformat())
        if trade["fill_price"] is not None and exit_price is not None:
            fill = trade["fill_price"]
            risk = abs(fill - trade["stop_loss"]) or float("nan")
            sign = 1 if trade["direction"] == "LONG" else -1
            legs = [(p["ratio"], p["price"]) for p in trade["partials"]] + [(trade["remaining_ratio"], exit_price)]
            gross = sum(ratio * sign * (price - fill) for ratio, price in legs) / risk
            fees = self._fee_rate * (fill + sum(ratio * price for ratio, price in legs)) / risk
            trade["gross_r"] = round(gross, 3)
            trade["net_r"] = round(gross - fees, 3)
        if self._on_close:
            self._on_close(trade)

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
            f"Total {gross:+.2f}R gross, {net:+.2f}R net of fees ({self._fee_rate:.2%}/side)."
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


def _stop_on_correct_side(trade: dict, price: float) -> bool:
    return trade["stop_loss"] < price if trade["direction"] == "LONG" else trade["stop_loss"] > price


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.6g}"
