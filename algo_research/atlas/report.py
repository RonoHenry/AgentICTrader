"""The atlas report (algo-research update 2026-10g, Requirement 26).

    python -m algo_research atlas            # docs/research/TURN_ATLAS.md, data/research/atlas/<snapshot>/

- **The slice:** the atlas reads the exploration slice only. Each frame is cut at the slice's end before
  anything is built, so no later bar is ever in memory.
- **Base rates:** every swing, per timeframe, swing type and objective: the held rate among the resolved
  swings, the mean geometry and the excess (held rate - geometry). Open swings are counted apart.
- **Context values** (AR-D32, AR-D33), per timeframe and objective (``same_tf`` and ``next_tf``), on the
  three-candle swings (``twin`` marks the ones that were also engulfing, the user's variation):
  - every value of every context column (numbers in buckets);
  - its excess over geometry, and that excess against the excess of the swings without it (``vs_rest``);
  - 95% intervals from resampling trading dates across instruments (``stats.Bootstrap``);
  - a value qualifies with at least 100 swings on 40 dates. The table ranks by the lower bound of
    ``vs_rest``, never by the raw rate, which mostly measures how near the confirming close sits to the
    objective.
- **Output:** descriptive, like the volatility profile: no verdict and no ledger row. A value that stands out
  is a lead to pre-register, not a finding.

Validates: Requirement 26 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from typing import Mapping, Optional

import numpy as np
import pandas as pd

from algo_research.atlas.arrays import build_arrays
from algo_research.atlas.context import CONTEXT_COLUMNS, LIQUIDITY, build_context
from algo_research.atlas.swings import OBJECTIVES, SWING_TIMEFRAMES, build_swings
from algo_research.frame import InstrumentFrame, calendar_columns
from algo_research.stats import Bootstrap

__all__ = ["CELL_OBJECTIVES", "MIN_DATES", "MIN_SWINGS", "REPORT_TIMEFRAMES", "atlas_rows", "base_rates",
           "build_atlas", "per_instrument", "render_atlas", "truncate", "value_table"]

REPORT_TIMEFRAMES = ("M15", "H1", "H4", "D1")
CELL_OBJECTIVES = ("same_tf", "next_tf")
MIN_SWINGS, MIN_DATES = 100, 40
BUCKETS = {"displacement": (1.0, 1.5), "wick_share": (0.5,)}
_CATEGORICAL = ("pd_zone", "session", "killzone", "h4_index", "weekday", "ny_hour")
_BOOLEAN = (("twin", "engulf_full", "arr_any", "arr_htf_any") + tuple(f"liq_{n}" for n in LIQUIDITY)
            + ("pd_aligned", "turtle_soup", "closes_beyond", "own_fvg"))
_ARRAYS = tuple(c for c in CONTEXT_COLUMNS if c.startswith("arr_") and c not in ("arr_any", "arr_htf_any"))
_RESOLVED = ("held", "failed")


# ── building ───────────────────────────────────────────────────────────────

def truncate(frame: InstrumentFrame, until) -> InstrumentFrame:
    """The frame with only the M1 bars opening before ``until`` and the bars closed by it."""
    until = pd.Timestamp(until)
    m1 = frame.m1[frame.m1["time"] < until].reset_index(drop=True)
    bars = {tf: b[b["close_time"] <= until].reset_index(drop=True) for tf, b in frame.bars.items()}
    return InstrumentFrame(frame.instrument, frame.typical_spread, frame.stop_slippage, m1, bars, frame.all_week)


def build_atlas(frame: InstrumentFrame, since, until) -> pd.DataFrame:
    """Every swing of every timeframe known in [since, until], scored and with its context, from the frame cut
    at ``until``."""
    frame = truncate(frame, until)
    swings = pd.concat([build_swings(frame, tf, since=since, until=until) for tf in SWING_TIMEFRAMES],
                       ignore_index=True)
    return build_context(frame, swings, build_arrays(frame))


def atlas_rows(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Every instrument's swings, with its instrument and trading date (of the extreme)."""
    parts = []
    for instrument, table in tables.items():
        kept = table.drop(columns="instrument", errors="ignore")
        kept.insert(0, "instrument", instrument)
        kept["trading_date"] = calendar_columns(pd.DatetimeIndex(kept["extreme_time"]))["trading_date"].to_numpy()
        parts.append(kept)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ── base rates and values ──────────────────────────────────────────────────

def base_rates(rows: pd.DataFrame) -> pd.DataFrame:
    """Per timeframe, swing type and objective: swings, open, resolved, held, the held rate, the mean geometry
    and the excess, over the resolved swings."""
    out = []
    for (tf, kind), group in rows.groupby(["tf", "type"], sort=False):
        for objective in OBJECTIVES:
            column = f"out_{objective}"
            if column not in group:
                continue
            outcome = group[column]
            is_resolved = outcome.isin(_RESOLVED)
            resolved = int(is_resolved.sum())
            held = int((outcome == "held").sum())
            rate = held / resolved if resolved else np.nan
            geo = float(group.loc[is_resolved, f"geo_{objective}"].mean()) if resolved else np.nan
            out.append({"tf": tf, "type": kind, "objective": objective, "swings": len(group),
                        "open": int((outcome == "open").sum()), "resolved": resolved, "held": held,
                        "rate": rate, "geo": geo, "excess": rate - geo})
    order = {tf: n for n, tf in enumerate(t.value for t in SWING_TIMEFRAMES)}
    table = pd.DataFrame(out)
    return table.sort_values(["tf", "type"], key=lambda s: s.map(order) if s.name == "tf" else s,
                             kind="stable").reset_index(drop=True) if len(table) else table


def _cells(group: pd.DataFrame):
    """(column, value, mask) for every value of every context column present."""
    for column in _CATEGORICAL + _ARRAYS:
        if column in group:
            values = group[column].dropna()
            for value in sorted(values.unique(), key=str):
                yield column, str(value), (group[column] == value).to_numpy()
    for column in _BOOLEAN:
        if column in group:
            yield column, "True", group[column].eq(True).to_numpy()      # None (no value) counts as not
    for column, thresholds in BUCKETS.items():
        if column in group:
            for threshold in thresholds:
                yield column, f">= {threshold:g}", (group[column] >= threshold).fillna(False).to_numpy()


def _interval(draws: np.ndarray) -> tuple[float, float]:
    finite = draws[np.isfinite(draws)]
    return tuple(np.percentile(finite, [2.5, 97.5])) if len(finite) else (np.nan, np.nan)


def value_table(rows: pd.DataFrame, tf: str, objective: str, resamples: int = 10_000, seed: int = 0,
                min_swings: int = MIN_SWINGS, min_dates: int = MIN_DATES) -> pd.DataFrame:
    """Every context value of ``tf``'s three-candle swings for ``objective``: its held rate, geometry and excess,
    and its excess against the rest's, with 95% intervals from resampled trading dates. Ranked: qualifying
    values first, by the lower bound against the rest."""
    column = f"out_{objective}"
    group = rows[(rows["tf"] == tf) & (rows["type"] == "three") & rows[column].isin(_RESOLVED)].reset_index(drop=True)
    columns = ["column", "value", "swings", "dates", "rate", "geo", "excess", "excess_lo", "excess_hi", "vs_rest",
               "vs_rest_lo", "vs_rest_hi", "qualifies"]
    if group.empty:
        return pd.DataFrame(columns=columns)
    held = (group[column] == "held").to_numpy(float)
    geo = group[f"geo_{objective}"].to_numpy(float)
    boot = Bootstrap(group[["trading_date"]].assign(trading_date=pd.to_datetime(group["trading_date"])),
                     resamples, seed)
    days, index, weights = len(boot.dates), boot.index, boot.weights
    all_h, all_g = np.bincount(index, held, days), np.bincount(index, geo, days)
    all_n = np.bincount(index, minlength=days).astype(float)
    out = []
    for name, value, mask in _cells(group):
        n = int(mask.sum())
        if n == 0:
            continue
        c_h, c_g = np.bincount(index[mask], held[mask], days), np.bincount(index[mask], geo[mask], days)
        c_n = np.bincount(index[mask], minlength=days).astype(float)
        r_h, r_g, r_n = all_h - c_h, all_g - c_g, all_n - c_n
        excess = (c_h.sum() - c_g.sum()) / n
        rest = (r_h.sum() - r_g.sum()) / r_n.sum() if r_n.sum() else np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            excess_b = (weights @ (c_h - c_g)) / (weights @ c_n)
            rest_b = (weights @ (r_h - r_g)) / (weights @ r_n)
        e_lo, e_hi = _interval(excess_b)
        r_lo, r_hi = _interval(excess_b - rest_b)
        dates = int((c_n > 0).sum())
        out.append({"column": name, "value": value, "swings": n, "dates": dates, "rate": c_h.sum() / n,
                    "geo": c_g.sum() / n, "excess": excess, "excess_lo": e_lo, "excess_hi": e_hi,
                    "vs_rest": excess - rest, "vs_rest_lo": r_lo, "vs_rest_hi": r_hi,
                    "qualifies": n >= min_swings and dates >= min_dates})
    table = pd.DataFrame(out, columns=columns)
    return table.sort_values(["qualifies", "vs_rest_lo"], ascending=[False, False], kind="stable",
                             na_position="last").reset_index(drop=True)


def per_instrument(rows: pd.DataFrame, tf: str, objective: str, column: str, value: str) -> dict:
    """{instrument: (excess over geometry, swings)} of one value of the three-candle swings, for stability."""
    out_col = f"out_{objective}"
    group = rows[(rows["tf"] == tf) & (rows["type"] == "three") & rows[out_col].isin(_RESOLVED)]
    mask = next((m for c, v, m in _cells(group) if c == column and v == value), None)
    if mask is None:
        return {}
    picked = group[mask]
    return {inst: (float((g[out_col] == "held").mean() - g[f"geo_{objective}"].mean()), len(g))
            for inst, g in picked.groupby("instrument")}


# ── rendering ──────────────────────────────────────────────────────────────

def _pct(x) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:.0f}%"


def _signed(x) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:+.1f}"


def _pts(x, lo, hi) -> str:
    if not np.isfinite(x):
        return "–"
    return f"{100 * x:+.1f} [{100 * lo:+.1f}, {100 * hi:+.1f}]"


def render_atlas(base: pd.DataFrame, tables: Mapping[tuple, pd.DataFrame], inputs: Mapping[str, str],
                 stability: Optional[Mapping[tuple, Mapping]] = None, top: int = 15, bottom: int = 10) -> str:
    lines = ["# Turn atlas", "",
             "Every swing point of the exploration slice (three-candle and engulfing), scored by what it delivered "
             "and read against the context it formed in. Descriptive: no verdict, no ledger row. A value that "
             "stands out is a lead to pre-register, not a finding (algo-research update 2026-10g).", "",
             "- **held**: price traded beyond the objective before trading beyond the swing's extreme; a touch is "
             "neither. `crt` is the candle range's other side, `same_tf` the origin of the leg into the swing, "
             "`next_tf` the next timeframe's untaken swing.",
             "- **geometry**: the chance that a driftless random walk from the confirming close reaches the "
             "objective first, (close - extreme) / (objective - extreme). **Excess** = held rate - geometry: what the "
             "swing delivered beyond where its confirming candle had already put price (AR-D33).",
             "- **vs the rest**: a value's excess minus the excess of the three-candle swings without it.",
             f"- **qualifies**: at least {MIN_SWINGS} swings on {MIN_DATES} trading dates. Differences are in "
             "percentage points with 95% intervals from resampled trading dates.", "",
             "## Base rates", "",
             "| Timeframe | Type | Objective | Swings | Resolved | Held | Rate | Geometry | Excess | Open |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in base.itertuples():
        lines.append(f"| {r.tf} | {r.type} | {r.objective} | {r.swings} | {r.resolved} | {r.held} | {_pct(r.rate)} "
                     f"| {_pct(r.geo)} | {_signed(r.excess)} | {r.open} |")
    for (tf, objective), table in tables.items():
        lines += ["", f"## {tf}: {objective}", ""]
        good = table[table["qualifies"]]
        if good.empty:
            lines.append("No value qualifies.")
            continue
        head = ["| Context | Value | Swings | Dates | Held | Geometry | Excess | vs the rest |",
                "|---|---|---|---|---|---|---|---|"]

        def rows_of(part):
            return [f"| {r.column} | {r.value} | {r.swings} | {r.dates} | {_pct(r.rate)} | {_pct(r.geo)} | "
                    f"{_pts(r.excess, r.excess_lo, r.excess_hi)} | {_pts(r.vs_rest, r.vs_rest_lo, r.vs_rest_hi)} |"
                    for r in part.itertuples()]
        lines += ["Strongest, by the lower bound against the rest:", ""] + head + rows_of(good.head(top))
        weakest = good.sort_values("vs_rest_hi", kind="stable").head(bottom)
        lines += ["", "Weakest, by the upper bound against the rest:", ""] + head + rows_of(weakest)
        per = (stability or {}).get((tf, objective))
        if per:
            instruments = sorted({i for v in per.values() for i in v})
            lines += ["", "Per instrument, for the strongest (excess in points, swings):", "",
                      "| Value | " + " | ".join(instruments) + " |", "|---|" + "---|" * len(instruments)]
            for label, by_inst in per.items():
                cells = [f"{_signed(by_inst[i][0])} ({by_inst[i][1]})" if i in by_inst else "–" for i in instruments]
                lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "## Inputs", ""] + [f"- {k}: {v}" for k, v in inputs.items()]
    return "\n".join(lines) + "\n"
