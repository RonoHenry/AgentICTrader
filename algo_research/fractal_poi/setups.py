"""The indicator's setups as a table, for research (algo-backtester update 2026-10-20, Requirement 24).

    reader = FractalPOI(m1, "M15", FractalSettings(), "XAUUSD", archive=True)
    reader.at(end)                         # read the window
    table = setup_rows(reader)             # one row per setup that reached the indicator's history

A setup reaches the history in one of two ways:
- C4 opens after its CISD has triggered;
- C3 takes C2's extreme after the CISD (an xC2).

Each row carries the setup's levels, and the time each became known, in New York wall seconds:
- **C1 and C2:** ``c1_open`` and ``c2_open`` (the HTF candles), ``sweep_price`` (C1's extreme that C2 traded
  beyond), ``sweep_at`` (the first chart candle beyond it), and ``c2_extreme`` with its candle's time ``c2_extreme_at``.
- **CISD:** ``cisd_level`` (the open of the run into the extreme), ``cisd_from`` (that run's first candle), and
  ``cisd_at``, the close that broke it.
- **The zones:** ``c3_open`` (C2 has closed back inside C1, the C3 zone is set), ``c4_open`` and ``c4_close``;
  ``z3_low``/``z3_high`` and ``z4_low``/``z4_high``; ``invalid_at`` (an xC2: C3 took C2's extreme after the CISD)
  and ``c4_invalid_at`` (an xC4: C4 took C3's extreme).
- **Targets:** ``target_c1`` (C1's opposite extreme, the indicator's formation liquidity) and ``target_c0`` (the
  candle before's, when further); ``sd_1`` and ``sd_0``, the SD projection's anchors.
- **Other:** ``smt``, the partners that diverged at the sweep; ``ic_cisd``, how many IC-CISDs followed.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

__all__ = ["SETUP_COLUMNS", "setup_rows"]

SETUP_COLUMNS = ("uid", "direction", "htf", "c1_open", "c2_open", "sweep_price", "sweep_at", "c2_extreme",
                 "c2_extreme_at", "c2_mid", "cisd_level", "cisd_from", "cisd_at", "c3_open", "c4_open", "c4_close",
                 "z3_low", "z3_high", "z4_low", "z4_high", "c3_mid", "c3_extreme", "invalid_at", "c4_invalid_at",
                 "target_c1", "target_c0", "c1_taken_at", "sd_1", "sd_0", "smt", "ic_cisd")


def _nan(x) -> float:
    return np.nan if x is None else float(x)


def setup_rows(reader) -> pd.DataFrame:
    """Every setup in the reader's archive (``FractalPOI(..., archive=True)``), oldest first."""
    if reader.model.archive is None:
        raise ValueError("reader: build it with archive=True")
    ch = reader.chart
    opened = lambda idx: None if idx is None else int(ch.time[idx])             # noqa: E731
    closed = lambda idx: None if idx is None else int(ch.end[idx])              # noqa: E731
    rows = []
    for s in reader.model.archive:
        rows.append({
            "uid": s.uid, "direction": "LONG" if s.is_bullish else "SHORT", "htf": reader.model.htf,
            "c1_open": opened(s.swept_candle_idx), "c2_open": opened(s.htf_candle_idx),
            "sweep_price": s.sweep_price, "sweep_at": opened(s.sweep_bar_idx),
            "c2_extreme": s.c2_extreme, "c2_extreme_at": opened(s.extreme_bar_idx), "c2_mid": s.c2_mid,
            "cisd_level": s.cisd_level, "cisd_from": opened(s.cisd_start_idx), "cisd_at": closed(s.cisd_end_idx),
            "c3_open": s.ez_c3_left_time, "c4_open": s.ez_c4_left_time, "c4_close": s.ez_c4_right_time,
            "z3_low": s.ez_c3_bot if s.ez_c3_set else np.nan, "z3_high": s.ez_c3_top if s.ez_c3_set else np.nan,
            "z4_low": s.ez_c4_bot if s.ez_c4_set else np.nan, "z4_high": s.ez_c4_top if s.ez_c4_set else np.nan,
            "c3_mid": s.c3_mid, "c3_extreme": s.c3_extreme,
            "invalid_at": closed(s.invalid_idx), "c4_invalid_at": s.ez_c4_invalid_time,
            "target_c1": s.liq_c1_price, "target_c0": s.liq_c0_price, "c1_taken_at": opened(s.liq_c1_mitigated_idx),
            "sd_1": s.proj_anchor_1, "sd_0": s.proj_anchor_0,
            "smt": s.smt_symbol if s.has_smt else "", "ic_cisd": len(s.ic_list or ()),
        })
    table = pd.DataFrame(rows, columns=list(SETUP_COLUMNS))
    for name in ("c1_open", "c2_open", "sweep_at", "c2_extreme_at", "cisd_from", "cisd_at", "c3_open", "c4_open",
                 "c4_close", "invalid_at", "c4_invalid_at", "c1_taken_at"):
        table[name] = table[name].astype("Int64")
    return table.sort_values(["c2_open", "uid"]).reset_index(drop=True)


def known_at(row) -> Optional[int]:
    """When a setup can first be traded: C2 has closed back inside C1 (C3's open) and its CISD has broken."""
    if pd.isna(row["c3_open"]) or pd.isna(row["cisd_at"]):
        return None
    return int(max(row["c3_open"], row["cisd_at"]))
