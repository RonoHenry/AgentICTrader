"""SimBroker: the backtest's broker.

execute_node places orders through it exactly as it does through the MT5 or
paper broker (Req 1.2): it is a BrokerClient. Like MT5BrokerAdapter, it rests
an entry on the discount side of the market (below the ask for a LONG, above
the bid for a SHORT) as a limit order and sends anything else at market. It
sizes in lots from the order's money risk:

    lots = risk_amount / (|entry - stop| x money per price unit), rounded down to the volume step

Refused orders raise SimBrokerError, which execute_node turns into a skip with
the reason (Req 6.2):
- MIN_VOLUME_OVER_RISK: the minimum volume would risk more than 10% over the
  budget. The size is never rounded up past that.
- INVALID_STOPS: a stop or target on the wrong side, as MT5's order_send
  refuses it (a draw-on-liquidity fallback target can land behind the entry).
- INVALID_ORDER / NO_PRICE: a missing direction, stop or risk amount, or no
  bar seen yet for the instrument.

Phase B feeds it each instrument's M1 bars (agent.brokers.fill_model.Bar, with
spreads already floored, Req 5.1). Every active order steps through the
shared FillModel, and each order that closes comes back as a ClosedTrade:

    broker = SimBroker(specs, clock=lambda: t, expiry_rule=cfg.pending_expiry, fallback_ttl=cfg.fallback_ttl)
    broker.advance("EURUSD", bar)          # the bar closing at t: fills first, then the price for decisions at t
    execute_node(state, risk_engine, broker)
    for trade in broker.advance("EURUSD", next_bar):
        trade.net_r, trade.cost_r_spread

R accounting (Req 4.12, 5.3). 1R is the price distance the order was sized on,
|entry - stop|: the limit price, or the requested entry of a market order. R
is therefore money in units of the risk budget, the same for a LONG and its
mirror-image SHORT, and stays meaningful when the spread is as wide as the stop.
- gross R: on ideal prices, the bid at the fill and at the exit;
- net R: on executed prices, less commission;
- costs: the spread (paid once, on the buy), slippage (stop exits) and
  commission, each >= 0 and summing to gross R - net R;
- MAE / MFE: the closing-side excursions from the fill, in R.

Validates: Requirements 4.12, 5.1, 5.3, 5.5, 6.1, 6.2 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Optional

from agent.brokers.base import BrokerClient
from agent.brokers.fill_model import Bar, FillModel, SimOrder, pending_expiry
from agent.clock import Clock
from agent.instruments import InstrumentSpec, InstrumentSpecs, commission_per_side, money_per_price_unit
from agent.strategy_config import PendingExpiry

__all__ = ["ClosedTrade", "SimBroker", "SimBrokerError", "SimTrade"]

Conversion = Callable[[str, datetime], float]   # (instrument, t) -> its quote currency's rate in account currency


class SimBrokerError(Exception):
    """An order the broker refuses. ``reason`` is the code the journal records."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass
class SimTrade(SimOrder):
    """A placed order: the fill model's order, plus what it was sized on."""
    lots: float = 0.0
    risk_amount: float = 0.0                  # the money budget it was sized for
    planned_risk: float = 0.0                 # |entry - stop| it was sized on: 1R in price units
    money_per_price_unit: float = 0.0         # per lot, at placement
    conversion: Optional[float] = None        # quote -> account rate at placement (crosses only)
    entry_spread: Optional[float] = None      # the spread on the fill bar
    exit_spread: Optional[float] = None       # and on the exit bar


@dataclass(frozen=True)
class ClosedTrade:
    """An order that is done: exited, or closed without filling (EXPIRED,
    INVALID_STOPS, CANCELLED), in which case the R fields are None."""
    order_id: str
    setup_id: str
    instrument: str
    direction: str
    kind: str                         # MARKET / LIMIT
    entry: float                      # the limit price, or a market order's requested entry
    stop: float
    target: Optional[float]
    lots: float
    risk_amount: float
    placed_at: datetime
    expires_at: Optional[datetime]
    filled_at: Optional[datetime]
    closed_at: datetime
    exit_reason: str                  # TP / SL / MANUAL / EXPIRED / INVALID_STOPS / CANCELLED
    ideal_fill: Optional[float]
    fill: Optional[float]
    ideal_exit: Optional[float]
    exit: Optional[float]
    initial_risk: Optional[float]     # 1R in price units
    gross_r: Optional[float]
    net_r: Optional[float]
    cost_r_spread: Optional[float]
    cost_r_slippage: Optional[float]
    cost_r_commission: Optional[float]
    mae_r: Optional[float]
    mfe_r: Optional[float]
    pnl: float                        # account currency, net of costs
    cost_flag: bool                   # costs above the configured share of 1R (Req 5.5)

    @property
    def filled(self) -> bool:
        return self.fill is not None

    @property
    def cost_r(self) -> Optional[float]:
        if not self.filled:
            return None
        return self.cost_r_spread + self.cost_r_slippage + self.cost_r_commission

    @property
    def holding_time(self) -> Optional[timedelta]:
        return None if self.filled_at is None else self.closed_at - self.filled_at


class SimBroker(BrokerClient):
    def __init__(
        self,
        specs: InstrumentSpecs,
        clock: Clock,
        expiry_rule: PendingExpiry,
        fallback_ttl: timedelta,
        conversion: Optional[Conversion] = None,
        min_volume_tolerance: float = 0.10,
        cost_flag_fraction: float = 0.25,
    ) -> None:
        """``conversion`` gives a cross's quote -> account rate at a time (e.g.
        GBPUSD for EURGBP on a USD account); pairs quoted in or based on the
        account currency don't need it."""
        self._specs = specs
        self._clock = clock
        self._expiry_rule = expiry_rule
        self._fallback_ttl = fallback_ttl
        self._conversion = conversion
        self._tolerance = min_volume_tolerance
        self._cost_flag_fraction = cost_flag_fraction
        self._models: dict[str, FillModel] = {}
        self._last_bar: dict[str, Bar] = {}
        self._active: dict[str, SimTrade] = {}   # by order id, in placement order
        self._closed: list[ClosedTrade] = []
        self._next_id = 1

    # ── BrokerClient ───────────────────────────────────────────────────────

    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        instrument = order.get("instrument")
        direction = str(order.get("direction") or "").upper()
        stop, target = order.get("stop_loss"), order.get("take_profit")
        risk_amount = order.get("risk_amount")
        if direction not in ("LONG", "SHORT"):
            raise SimBrokerError("INVALID_ORDER", f"direction {order.get('direction')!r}")
        if stop is None:
            raise SimBrokerError("INVALID_ORDER", "no stop_loss")
        if not risk_amount or risk_amount <= 0:
            raise SimBrokerError("INVALID_ORDER", f"risk_amount {risk_amount!r}")
        last = self._last_bar.get(instrument)
        if last is None:
            raise SimBrokerError("NO_PRICE", f"no bar for {instrument} yet")

        long_ = direction == "LONG"
        market = last.close + last.spread if long_ else last.close   # where a market order would fill now
        entry = order.get("entry")
        pending = entry is not None and (entry < market if long_ else entry > market)
        reference = entry if entry is not None else market           # the price it is sized on
        _check_stops(long_, reference if pending else market, stop, target)

        now = self._clock()
        spec = self._specs[instrument]
        conversion = self._conversion_rate(spec, now)
        per_price_unit = money_per_price_unit(spec, reference, conversion, self._specs.account_ccy)
        lots = self._lots(spec, risk_amount, abs(reference - stop) * per_price_unit)

        order_id = f"sim-{self._next_id:06d}"
        self._next_id += 1
        self._active[order_id] = SimTrade(
            order_id=order_id, setup_id=order.get("setup_id") or "", instrument=instrument, direction=direction,
            kind="LIMIT" if pending else "MARKET", entry=reference, stop=stop, target=target, placed_at=now,
            expires_at=pending_expiry(now, self._expiry_rule, self._fallback_ttl) if pending else None,
            lots=lots, risk_amount=risk_amount, planned_risk=abs(reference - stop),
            money_per_price_unit=per_price_unit, conversion=conversion,
        )
        return {"order_id": order_id, "trade_id": order_id, "pending": pending}

    def set_sl_tp(self, trade_id: str, sl_price: float, tp_price: float) -> bool:
        trade = self._get_active(trade_id)
        trade.stop, trade.target = sl_price, tp_price
        return True

    def close_position(self, trade_id: str) -> bool:
        """Cancel a pending order, or close an open one at the last bar's close
        on its closing side (bid for LONG, ask for SHORT)."""
        trade = self._get_active(trade_id)
        trade.status, trade.closed_at = "CLOSED", self._clock()
        if trade.filled_at is None:
            trade.exit_reason = "CANCELLED"
        else:
            bar = self._last_bar[trade.instrument]
            long_ = trade.direction == "LONG"
            trade.exit_reason, trade.exit_spread = "MANUAL", bar.spread
            trade.ideal_exit, trade.exit = bar.close, bar.close if long_ else bar.close + bar.spread
            pick = (min, max) if long_ else (max, min)
            trade.mae_price, trade.mfe_price = pick[0](trade.mae_price, trade.exit), pick[1](trade.mfe_price, trade.exit)
        self._book(trade)
        return True

    def partial_close(self, trade_id: str, ratio: float = 0.5) -> dict[str, Any]:
        raise SimBrokerError("NOT_SIMULATED", "partial closes are not simulated (scale-out is deferred, D19)")

    def get_position_status(self, trade_id: str) -> dict[str, Any]:
        trade = self._active.get(trade_id)
        if trade is None:
            return {"status": "CLOSED", "unrealised_pnl": 0.0, "current_price": None}
        bar = self._last_bar[trade.instrument]
        if trade.status == "PENDING":
            return {"status": "PENDING", "unrealised_pnl": 0.0, "current_price": bar.close}
        long_ = trade.direction == "LONG"
        mark = bar.close if long_ else bar.close + bar.spread
        pnl = (1 if long_ else -1) * (mark - trade.fill) * trade.lots * trade.money_per_price_unit
        return {"status": "OPEN", "unrealised_pnl": pnl, "current_price": bar.close}

    # ── simulation ─────────────────────────────────────────────────────────

    def advance(self, instrument: str, bar: Bar) -> list[ClosedTrade]:
        """Step the instrument's active orders through ``bar``, the M1 bar
        closing now; it is also the market price for orders placed now.
        Returns the orders that closed on it."""
        self._last_bar[instrument] = bar
        model = self._model(instrument)
        closed = []
        for trade in [t for t in self._active.values() if t.instrument == instrument]:
            for event in model.step(trade, bar):
                if event.kind == "FILLED":
                    trade.entry_spread = bar.spread
                elif event.kind in ("SL", "TP"):
                    trade.exit_spread = bar.spread
            if trade.status == "CLOSED":
                closed.append(self._book(trade))
        return closed

    def active_trade(self, instrument: str) -> Optional[SimTrade]:
        """The instrument's pending or open order, if any (one per instrument, Req 1.5)."""
        return next((t for t in self._active.values() if t.instrument == instrument), None)

    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed)

    # ── helpers ────────────────────────────────────────────────────────────

    def _lots(self, spec: InstrumentSpec, risk_amount: float, risk_per_lot: float) -> float:
        lots = min(_round_down(risk_amount / risk_per_lot, spec.volume_step), spec.volume_max)
        if lots >= spec.volume_min:
            return lots
        if spec.volume_min * risk_per_lot > risk_amount * (1 + self._tolerance):
            raise SimBrokerError(
                "MIN_VOLUME_OVER_RISK",
                f"{spec.volume_min} lots risk {spec.volume_min * risk_per_lot:.2f}, "
                f"over the {risk_amount:.2f} budget + {self._tolerance:.0%}",
            )
        return spec.volume_min

    def _conversion_rate(self, spec: InstrumentSpec, t: datetime) -> Optional[float]:
        account = self._specs.account_ccy
        if account in (spec.quote_ccy, spec.base_ccy) or self._conversion is None:
            return None
        return self._conversion(spec.symbol, t)

    def _model(self, instrument: str) -> FillModel:
        if instrument not in self._models:
            self._models[instrument] = FillModel(self._specs[instrument].stop_slippage)
        return self._models[instrument]

    def _get_active(self, trade_id: str) -> SimTrade:
        trade = self._active.get(trade_id)
        if trade is None:
            raise SimBrokerError("UNKNOWN_TRADE", f"no pending or open order {trade_id}")
        return trade

    def _book(self, trade: SimTrade) -> ClosedTrade:
        del self._active[trade.order_id]
        closed = _closed_trade(trade, self._specs[trade.instrument], self._specs.account_ccy, self._cost_flag_fraction)
        self._closed.append(closed)
        return closed


def _check_stops(long_: bool, price: float, stop: float, target: Optional[float]) -> None:
    """Stop and target on the right sides of ``price`` (the limit, or the
    market fill), strictly, as MT5 requires."""
    valid = (stop < price and (target is None or target > price) if long_
             else stop > price and (target is None or target < price))
    if not valid:
        raise SimBrokerError("INVALID_STOPS", f"stop {stop} / target {target} against {price}")


def _round_down(value: float, step: float) -> float:
    steps = math.floor(value / step + 1e-9)   # 0.3 / 0.1 is 2.9999999999999996
    return round(steps * step, max(0, -Decimal(repr(step)).normalize().as_tuple().exponent))


def _closed_trade(trade: SimTrade, spec: InstrumentSpec, account_ccy: str, cost_flag_fraction: float) -> ClosedTrade:
    common = dict(
        order_id=trade.order_id, setup_id=trade.setup_id, instrument=trade.instrument, direction=trade.direction,
        kind=trade.kind, entry=trade.entry, stop=trade.stop, target=trade.target, lots=trade.lots,
        risk_amount=trade.risk_amount, placed_at=trade.placed_at, expires_at=trade.expires_at,
        filled_at=trade.filled_at, closed_at=trade.closed_at, exit_reason=trade.exit_reason,
        ideal_fill=trade.ideal_fill, fill=trade.fill, ideal_exit=trade.ideal_exit, exit=trade.exit,
    )
    if trade.fill is None:
        return ClosedTrade(**common, initial_risk=None, gross_r=None, net_r=None, cost_r_spread=None,
                           cost_r_slippage=None, cost_r_commission=None, mae_r=None, mfe_r=None, pnl=0.0,
                           cost_flag=False)

    sign = 1 if trade.direction == "LONG" else -1
    risk = trade.planned_risk
    risk_money = trade.lots * risk * trade.money_per_price_unit
    commission = sum(commission_per_side(spec, trade.lots, price, trade.conversion, account_ccy)
                     for price in (trade.fill, trade.exit))
    cost_r_spread = (trade.entry_spread if sign > 0 else trade.exit_spread) / risk
    cost_r_slippage = (spec.stop_slippage if trade.exit_reason == "SL" else 0.0) / risk
    cost_r_commission = commission / risk_money
    net_r = sign * (trade.exit - trade.fill) / risk - cost_r_commission
    return ClosedTrade(
        **common,
        initial_risk=risk,
        gross_r=sign * (trade.ideal_exit - trade.ideal_fill) / risk,
        net_r=net_r,
        cost_r_spread=cost_r_spread,
        cost_r_slippage=cost_r_slippage,
        cost_r_commission=cost_r_commission,
        mae_r=sign * (trade.mae_price - trade.fill) / risk,
        mfe_r=sign * (trade.mfe_price - trade.fill) / risk,
        pnl=net_r * risk_money,
        cost_flag=cost_r_spread + cost_r_slippage + cost_r_commission > cost_flag_fraction,
    )
