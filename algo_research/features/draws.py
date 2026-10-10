"""The engine's draws as levels: when each was first traded beyond (update 2026-10e).

The daily anticipation (anticipation.py) names a draw above the D1 open and a
draw below it. These columns say when, within the candle, an M1 bar first
traded beyond each one, as the market features do for PDH and PDL: the close
of the first M1 bar with a high above the draw above (a low below the draw
below), known once that bar has closed, and null before it or while the draw
itself isn't known yet. They are computed once the anticipation is joined
(dataset.py), so ``anchor`` can skip a draw already taken and ``stratified``
can pool the untaken ones.

    taken = draw_taken_at(frame, features)       # same index as features

Validates: Requirement 18.1 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.features.market import Column, _first_by_key, _taken_at
from algo_research.frame import InstrumentFrame

__all__ = ["DRAW_COLUMNS", "draw_taken_at"]

DRAW_COLUMNS: dict[str, Column] = {
    "ant_draw_above_taken_at": Column("close of the candle's first M1 bar with high > ant_draw_above_price",
                                      "UTC time", "that bar's close"),
    "ant_draw_below_taken_at": Column("close of the candle's first M1 bar with low < ant_draw_below_price",
                                      "UTC time", "that bar's close"),
}

_SIDES = (("ant_draw_above_taken_at", "ant_draw_above_price", True),
          ("ant_draw_below_taken_at", "ant_draw_below_price", False))


def draw_taken_at(frame: InstrumentFrame, features: pd.DataFrame) -> pd.DataFrame:
    """``DRAW_COLUMNS`` for ``features``' rows of one instrument (the anticipation joined), same index."""
    out = pd.DataFrame(index=features.index)
    a = frame.arrays
    mt, high, low = a["time"], a["high"], a["low"]
    if len(mt) == 0 or features.empty:
        for name in DRAW_COLUMNS:
            out[name] = pd.Series(pd.NaT, index=features.index, dtype="datetime64[ns, UTC]")
        return out
    k = np.searchsorted(mt, pd.DatetimeIndex(features["t"]).as_unit("ns").asi8, "left")   # bars closed by t
    m1_dates = frame.m1["trading_date"].to_numpy(dtype="datetime64[ns]")
    row_dates = features["trading_date"].to_numpy(dtype="datetime64[ns]")
    for name, column, above in _SIDES:
        values = features[column].to_numpy(dtype=float)
        known = ~np.isnan(values)
        # The draw is one price per candle: spread it over the candle's bars.
        per_date = pd.Series(values[known], index=row_dates[known]).groupby(level=0).first()
        bar_level = per_date.reindex(m1_dates).to_numpy(dtype=float)
        with np.errstate(invalid="ignore"):
            beyond = high > bar_level if above else low < bar_level
        first = _first_by_key(beyond, m1_dates.astype(np.int64), row_dates.astype(np.int64))
        taken = pd.Series(_taken_at(mt, first, k), index=features.index)
        taken[~known] = pd.NaT
        out[name] = taken
    return out
