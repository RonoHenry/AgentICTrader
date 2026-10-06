"""SimAccount: the backtest's account state.

It tracks what RiskEngine checks live (Req 1.4, 6.3):
- **equity:** closed trades only. ``equity_mark`` adds the open positions,
  marked at the last bar close on their closing side;
- **daily and weekly drawdown:** from anchors set at the start of each
  strategy-calendar D1 and W1 period (17:00 New York; the FX week opens inside
  W1's first day, so the weekly anchor is the Sunday open). An anchor is the
  last mark of the period before;
- **open trades:** pending or open orders.

    account = SimAccount(cfg.account.initial_equity, cfg.account.risk_per_trade)
    account.book(closed_trade)                                   # as orders close
    account.mark(t, broker.open_pnl(), broker.active_count())    # after each bar's fills
    redis.set("risk:exposure:default", json.dumps(account.exposure()))

The risk budget is fixed at ``initial_equity x risk_per_trade`` unless
compounding (Req 6.4), so results read in R. RiskEngine sizes every trade at
its own fixed 1% (RISK_PER_TRADE) of the equity in the exposure dict, so
exposure()["equity"] is the equity whose 1% is that budget: the starting
equity at the default 1% risk, without compounding.

Validates: Requirements 1.4, 6.3, 6.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from algo_backtester.sim_broker import ClosedTrade
from liquidity_engine.models import Timeframe
from services.market_data.strategy_calendar import StrategyCalendar
from services.risk_engine.main import RISK_PER_TRADE

__all__ = ["SimAccount"]

_CALENDAR = StrategyCalendar()
_EPSILON = timedelta(microseconds=1)


class SimAccount:
    def __init__(self, initial_equity: float, risk_per_trade: float, compounding: bool = False) -> None:
        self.initial_equity = initial_equity
        self.risk_per_trade = risk_per_trade
        self.compounding = compounding
        self.equity = initial_equity          # closed trades only
        self.equity_mark = initial_equity     # plus open positions at the last mark
        self.open_trades = 0
        self._day_anchor = self._week_anchor = initial_equity
        self._day: Optional[datetime] = None  # start of the current D1 / W1 period
        self._week: Optional[datetime] = None

    @property
    def risk_amount(self) -> float:
        """The money risked per trade."""
        return (self.equity if self.compounding else self.initial_equity) * self.risk_per_trade

    @property
    def daily_dd_pct(self) -> float:
        return max(0.0, (self._day_anchor - self.equity_mark) / self._day_anchor * 100)

    @property
    def weekly_dd_pct(self) -> float:
        return max(0.0, (self._week_anchor - self.equity_mark) / self._week_anchor * 100)

    def book(self, trade: ClosedTrade) -> None:
        """A closed order's result. The next mark() brings equity_mark up to date."""
        self.equity += trade.pnl

    def mark(self, t: datetime, open_pnl: float, open_trades: int) -> None:
        """The account at t, a bar close. A mark at exactly 17:00 New York
        closes the day; the first one after it opens the next, anchored on it."""
        # The period containing the instant before t: the bar closing at t belongs to it.
        day = _CALENDAR.period_start(t - _EPSILON, Timeframe.D1)
        week = _CALENDAR.period_start(t - _EPSILON, Timeframe.W1)
        if self._day is not None and day != self._day:
            self._day_anchor = self.equity_mark
        if self._week is not None and week != self._week:
            self._week_anchor = self.equity_mark
        self._day, self._week = day, week
        self.equity_mark = self.equity + open_pnl
        self.open_trades = open_trades

    def exposure(self) -> dict:
        """The dict RiskEngine reads from ``risk:exposure:{user_id}``."""
        return {
            "daily_dd_pct": self.daily_dd_pct,
            "weekly_dd_pct": self.weekly_dd_pct,
            "open_trades": self.open_trades,
            "equity": self.risk_amount / RISK_PER_TRADE,
        }
