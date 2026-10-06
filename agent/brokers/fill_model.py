"""The fill model the paper broker and AlgoBacktester share.

One pure state machine decides when an order fills, stops out, hits its
target or expires, bar by M1 bar (.kiro/specs/algo-backtester, task 194). The
paper forward test and the backtester both use it, so their results are
comparable (Req 4.1). It reads no clock: time is the bars' own timestamps.

    model = FillModel(stop_slippage=spec.stop_slippage)
    order = SimOrder(order_id=..., setup_id=..., instrument="EURUSD", direction="LONG",
                     kind="LIMIT", entry=1.0850, stop=1.0830, target=1.0910,
                     placed_at=t, expires_at=pending_expiry(t, cfg.pending_expiry, cfg.fallback_ttl))
    for bar in m1_bars:
        events = model.step(order, bar)   # FILLED / SL / TP / EXPIRED / REJECTED

Prices. Bars are bid prices (MT5 convention); ask = bid + spread. Fills and
exits happen on the executing side: buys at the ask, sells at the bid, stop
exits worsened by the slippage. Each order also records ``ideal_*`` prices:
the bid at the same moment, before slippage. A trade therefore pays the
spread once, on its buy (entry for LONG, exit for SHORT), and gross R is
measured on ideal prices, net R on actual ones.

Rules (Req 4):
- Bars before ``placed_at`` are ignored.
- MARKET fills at the first bar's open (ask for LONG, bid for SHORT). If that
  open is already beyond the stop or target, the order is REJECTED
  (INVALID_STOPS), as a broker rejects invalid stops.
- LIMIT fills at the entry when the ask low trades strictly below it (LONG)
  or the bid high strictly above it (SHORT); a touch is not a fill.
- A PENDING order expires on the first bar at or after ``expires_at``. No bars
  exist while the venue is closed, so nothing fills then, and an order whose
  expiry falls in a weekend expires on the first bar after the reopen.
- Stops trigger on the closing side (bid for LONG, ask for SHORT) and exit at
  the stop, or at the open when the bar opened beyond it (a gap), worsened by
  the slippage. Targets exit at the target, without slippage.
- When one bar reaches both, the stop wins. On the bar a LIMIT fills, a stop
  may trigger (at the stop: the position didn't exist at the open) but the
  target may not.
- MAE/MFE track the closing-side price from the fill. A limit's fill bar
  counts only its adverse extreme (the favourable one may predate the fill);
  an exit caps the excursion at the exit's market price.

Validates: Requirements 4.1-4.12 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Optional

from agent.strategy_config import PendingExpiry
from liquidity_engine.models import KillzoneWindow
from liquidity_engine.utils.time_utils import KILLZONE_WINDOWS, get_killzone, to_est, to_utc

__all__ = ["Bar", "FillEvent", "FillModel", "SimOrder", "pending_expiry"]

Direction = Literal["LONG", "SHORT"]
OrderKind = Literal["MARKET", "LIMIT"]
OrderStatus = Literal["PENDING", "OPEN", "CLOSED"]
EventKind = Literal["FILLED", "SL", "TP", "EXPIRED", "REJECTED"]


@dataclass(frozen=True)
class Bar:
    """One M1 bar. Prices are bid; ``spread`` (price units) is the larger of the
    recorded and the typical spread (Req 5.1), so ask = bid + spread."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    spread: float


@dataclass
class SimOrder:
    order_id: str
    setup_id: str
    instrument: str
    direction: Direction
    kind: OrderKind
    entry: float
    stop: float
    target: Optional[float]
    placed_at: datetime
    expires_at: Optional[datetime] = None
    status: OrderStatus = "PENDING"
    ideal_fill: Optional[float] = None   # bid at the fill, before spread
    fill: Optional[float] = None
    ideal_exit: Optional[float] = None   # bid at the exit, before slippage
    exit: Optional[float] = None
    exit_reason: Optional[str] = None    # SL / TP / EXPIRED / INVALID_STOPS
    filled_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    mae_price: Optional[float] = None    # closing-side price: bid for LONG, ask for SHORT
    mfe_price: Optional[float] = None


@dataclass(frozen=True)
class FillEvent:
    kind: EventKind
    order_id: str
    at: datetime
    price: Optional[float]  # the actual fill or exit price; None for EXPIRED / REJECTED


class FillModel:
    def __init__(self, stop_slippage: float) -> None:
        if stop_slippage < 0:
            raise ValueError(f"stop_slippage must be >= 0, got {stop_slippage}")
        self.stop_slippage = stop_slippage  # price units (InstrumentSpec.stop_slippage)

    def step(self, order: SimOrder, bar: Bar) -> list[FillEvent]:
        """Advance ``order`` through one M1 bar. Mutates the order and returns
        what happened on this bar, in order (e.g. FILLED then SL)."""
        if order.status == "CLOSED" or bar.timestamp < order.placed_at:
            return []
        events: list[FillEvent] = []
        fill_bar = False
        if order.status == "PENDING":
            if order.expires_at is not None and bar.timestamp >= order.expires_at:
                self._close(order, bar, "EXPIRED", None, None)
                return [FillEvent("EXPIRED", order.order_id, bar.timestamp, None)]
            if order.kind == "MARKET":
                return self._market_entry(order, bar)
            if not self._limit_fills(order, bar):
                return []
            self._fill(order, bar, ideal=order.entry - bar.spread if order.direction == "LONG" else order.entry,
                       price=order.entry)
            events.append(FillEvent("FILLED", order.order_id, bar.timestamp, order.fill))
            fill_bar = True
        events.extend(self._manage(order, bar, limit_fill_bar=fill_bar))
        return events

    # ── entries ────────────────────────────────────────────────────────────

    def _market_entry(self, order: SimOrder, bar: Bar) -> list[FillEvent]:
        long_ = order.direction == "LONG"
        price = bar.open + bar.spread if long_ else bar.open
        beyond_stop = price <= order.stop if long_ else price >= order.stop
        beyond_target = order.target is not None and (price >= order.target if long_ else price <= order.target)
        if beyond_stop or beyond_target:
            self._close(order, bar, "INVALID_STOPS", None, None)
            return [FillEvent("REJECTED", order.order_id, bar.timestamp, None)]
        self._fill(order, bar, ideal=bar.open, price=price)
        return [FillEvent("FILLED", order.order_id, bar.timestamp, order.fill),
                *self._manage(order, bar, limit_fill_bar=False)]

    @staticmethod
    def _limit_fills(order: SimOrder, bar: Bar) -> bool:
        if order.direction == "LONG":
            return bar.low + bar.spread < order.entry   # ask trades strictly below the limit
        return bar.high > order.entry                   # bid trades strictly above the limit

    @staticmethod
    def _fill(order: SimOrder, bar: Bar, ideal: float, price: float) -> None:
        order.status, order.filled_at = "OPEN", bar.timestamp
        order.ideal_fill, order.fill = ideal, price
        # Excursions start from the price the position would close at right now.
        order.mae_price = order.mfe_price = price - bar.spread if order.direction == "LONG" else price + bar.spread

    # ── an open position ───────────────────────────────────────────────────

    def _manage(self, order: SimOrder, bar: Bar, limit_fill_bar: bool) -> list[FillEvent]:
        long_ = order.direction == "LONG"
        # Closing side: LONG sells at the bid, SHORT buys at the ask.
        adverse = bar.low if long_ else bar.high + bar.spread
        favourable = bar.high if long_ else bar.low + bar.spread
        stop_hit = adverse <= order.stop if long_ else adverse >= order.stop
        target_hit = (not limit_fill_bar and order.target is not None
                      and (favourable >= order.target if long_ else favourable <= order.target))

        if stop_hit:
            closing_open = bar.open if long_ else bar.open + bar.spread
            gapped = not limit_fill_bar and (closing_open < order.stop if long_ else closing_open > order.stop)
            market = closing_open if gapped else order.stop       # closing-side price before slippage
            self._extend(order, adverse=market, favourable=None if limit_fill_bar else favourable)
            exit_price = market - self.stop_slippage if long_ else market + self.stop_slippage
            self._close(order, bar, "SL", market if long_ else market - bar.spread, exit_price)
            return [FillEvent("SL", order.order_id, bar.timestamp, exit_price)]
        if target_hit:
            self._extend(order, adverse=adverse, favourable=order.target)
            self._close(order, bar, "TP", order.target if long_ else order.target - bar.spread, order.target)
            return [FillEvent("TP", order.order_id, bar.timestamp, order.target)]
        self._extend(order, adverse=adverse, favourable=None if limit_fill_bar else favourable)
        return []

    @staticmethod
    def _extend(order: SimOrder, adverse: float, favourable: Optional[float]) -> None:
        if order.direction == "LONG":
            order.mae_price = min(order.mae_price, adverse)
            if favourable is not None:
                order.mfe_price = max(order.mfe_price, favourable)
        else:
            order.mae_price = max(order.mae_price, adverse)
            if favourable is not None:
                order.mfe_price = min(order.mfe_price, favourable)

    @staticmethod
    def _close(order: SimOrder, bar: Bar, reason: str, ideal_exit: Optional[float], exit_price: Optional[float]) -> None:
        order.status, order.closed_at, order.exit_reason = "CLOSED", bar.timestamp, reason
        order.ideal_exit, order.exit = ideal_exit, exit_price


def pending_expiry(placed_at: datetime, rule: PendingExpiry, fallback_ttl: timedelta) -> datetime:
    """When a pending order placed at ``placed_at`` expires (Req 4.10).

    KILLZONE_END: the end of the killzone containing ``placed_at`` (New York
    time, liquidity_engine.utils.time_utils.KILLZONE_WINDOWS), or
    ``placed_at + fallback_ttl`` outside every killzone. Killzones include
    their end, so an order placed at that instant expires at once.
    FIXED_TTL: always ``placed_at + fallback_ttl``.
    """
    if rule == PendingExpiry.KILLZONE_END:
        window = get_killzone(placed_at)
        if window != KillzoneWindow.NONE:
            ny = to_est(placed_at)
            end = KILLZONE_WINDOWS[window][1]
            return to_utc(ny.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0))
    return placed_at + fallback_ttl
