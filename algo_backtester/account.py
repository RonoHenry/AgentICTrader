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

LiveAccount is the same account for the live runner (live-execution
Requirement 4): its balance and equity come from the broker's terminal at each
``sync``, and the anchors, the budget and the exposure dict are SimAccount's.
Without compounding the budget is fixed at the balance of the first sync
(LX-D3). Its state persists, so a restart keeps the first balance and the
day's and week's anchors.

    account = LiveAccount(cfg.account.risk_per_trade, cfg.account.compounding, state_path="data/live/mt5_account.json")
    account.sync(now, balance, equity, broker.active_count())
    redis.set("risk:exposure:<user>", json.dumps(account.exposure()))

Validates: Requirements 1.4, 6.3, 6.4 (.kiro/specs/algo-backtester/requirements.md);
live-execution Requirements 4.1-4.3
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from algo_backtester.sim_broker import ClosedTrade
from liquidity_engine.models import Timeframe
from services.market_data.strategy_calendar import StrategyCalendar
from services.risk_engine.main import RISK_PER_TRADE

__all__ = ["LiveAccount", "SimAccount"]

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


class LiveAccount(SimAccount):
    """SimAccount on the broker's numbers (live-execution Requirement 4). ``sync`` replaces ``book`` and ``mark``:
    the terminal's balance is the closed-trade equity, and its equity minus its balance is the open P&L."""

    def __init__(self, risk_per_trade: float, compounding: bool = False,
                 state_path: Optional[str | Path] = None) -> None:
        super().__init__(0.0, risk_per_trade, compounding)
        self._path = Path(state_path) if state_path else None
        self._started = False
        if self._path is not None and self._path.exists():
            self._load(json.loads(self._path.read_text(encoding="utf-8")))

    def sync(self, t: datetime, balance: float, equity: float, open_trades: int) -> None:
        """The account at ``t`` from the terminal. The first sync fixes the budget's balance and anchors the day
        and the week at the larger of the balance and the equity then: a loss already open counts as drawdown,
        a profit already open is no cushion."""
        if not self._started:
            self.initial_equity = balance
            self._day_anchor = self._week_anchor = max(balance, equity)
            self.equity_mark = equity
            self._started = True
        self.equity = balance
        self.mark(t, equity - balance, open_trades)
        self._save()

    def _state(self) -> dict:
        return {
            "initial_equity": self.initial_equity, "equity": self.equity, "equity_mark": self.equity_mark,
            "open_trades": self.open_trades, "day_anchor": self._day_anchor, "week_anchor": self._week_anchor,
            "day": self._day.isoformat() if self._day else None, "week": self._week.isoformat() if self._week else None,
        }

    def _load(self, state: dict) -> None:
        self.initial_equity, self.equity = state["initial_equity"], state["equity"]
        self.equity_mark, self.open_trades = state["equity_mark"], state["open_trades"]
        self._day_anchor, self._week_anchor = state["day_anchor"], state["week_anchor"]
        self._day = datetime.fromisoformat(state["day"]) if state["day"] else None
        self._week = datetime.fromisoformat(state["week"]) if state["week"] else None
        self._started = True

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(self._state(), indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
