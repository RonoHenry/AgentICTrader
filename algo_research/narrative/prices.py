"""The narrative's price basis: market prices, not the bid dipping at the rollover.

At 17:00 New York the FX spread blows out for a few minutes and the bid
dips with it: 18-21% of FX day lows form there (task 273). ``ROLLOVER_WINDOW``
flattens the configured instruments' bars that open in the first ``minutes``
after 17:00 New York:

- after a pause (the last clean bar within ``closure_minutes``), to the last
  clean close, as if the market had paused (context-engine CE-D3);
- after a closure (the weekly reopen, a holiday) or at the start of a series,
  to the open of the first clean bar after the window. Friday's close is days
  old by Sunday's reopen; the gap between them is real (an NWOG), only the
  blown-out minutes after the reopen are not;
- with no clean bar after them, they are dropped.

A run's candles carry no spread, so the window is set by time; context-engine
task 276's spread-based quarantine will be a second rule here (ND-D7).

Only the narrative reads these prices. Fills and journals never do.

Validates: Requirements 2.1-2.4 (.kiro/specs/market-narrative/requirements.md)
"""
from __future__ import annotations

import pandas as pd

from algo_research.narrative.config import PriceBasis

__all__ = ["apply_price_basis"]

_OHLC = ["open", "high", "low", "close"]
_ROLLOVER_MINUTE = 17 * 60


def apply_price_basis(bars: pd.DataFrame, instrument: str, basis: PriceBasis) -> pd.DataFrame:
    """A copy of ``bars`` (time in UTC, open, high, low, close) priced by ``basis``."""
    out = bars.copy()
    if basis.rule == "NONE" or instrument not in basis.instruments or out.empty:
        return out.reset_index(drop=True)
    ny = pd.DatetimeIndex(out["time"]).tz_convert("America/New_York")
    minute = ny.hour * 60 + ny.minute
    window = pd.Series((minute >= _ROLLOVER_MINUTE) & (minute < _ROLLOVER_MINUTE + basis.minutes),
                       index=out.index)
    times = pd.Series(pd.DatetimeIndex(out["time"]), index=out.index)
    prev_close = out["close"].where(~window).ffill()
    prev_time = times.where(~window).ffill()
    next_open = out["open"].where(~window).bfill()
    paused = (times - prev_time) <= pd.Timedelta(minutes=basis.closure_minutes)
    level = prev_close.where(paused & prev_close.notna(), next_open)
    flat = window & level.notna()
    for name in _OHLC:
        out.loc[flat, name] = level[flat]
    return out[~(window & level.isna())].reset_index(drop=True)
