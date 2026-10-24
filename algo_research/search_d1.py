"""The 2018-2024 search: its D1 hypotheses, H-A to H-C (docs/research/SEARCH_2018_2024.md).

The broker's D1 bars are the price path (Amendment 1): the server day, with Sunday's short session merged into
Monday. Each market's frame is cut at the window's end before anything is built, so no later bar is read. The
atlas's own code then reads the frame:
- ``build_swings`` finds the swings and their W1 objectives;
- ``build_context`` finds the previous week's extreme (``liq_pw``).

The path has one bar per trading date. So a bar that trades beyond both the objective and the extreme is failed,
as the atlas rules a bar that does both, and the report counts them.

Pass on development: the excess over geometry (held - the driftless walk's chance from the confirming close) is
above zero, with its 95% interval over resampled trading dates above zero, and it is positive in at least 6 of the
9 markets. Reported beside it, not part of the rule: lows and highs apart (an excess from one side only is drift),
an interval over resampled calendar months, and the R a trade at the confirming close would have made, gross.

    python -m algo_research.search_d1 --window develop
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from algo_research.atlas.arrays import build_arrays
from algo_research.atlas.context import build_context
from algo_research.atlas.report import atlas_rows, truncate
from algo_research.atlas.swings import build_swings
from algo_research.frame import InstrumentFrame, frame_from_arrays
from liquidity_engine.models import Timeframe

__all__ = ["HYPOTHESES", "WINDOWS", "d1_frame", "judge", "merge_sundays", "swing_rows"]

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO / "data" / "research" / "snapshots" / "mt5-2018-2026"
OUT = REPO / "data" / "research" / "search"
MARKETS = ("DXY", "XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")
WINDOWS = {"develop": ("2018-07-01", "2023-01-01"), "test": ("2023-01-01", "2025-01-01")}
RESAMPLES, SEED = 10_000, 0
MIN_MARKETS = 6
_RESOLVED = ("held", "failed")

Mask = Callable[[pd.DataFrame], pd.Series]
HYPOTHESES: dict[str, tuple[str, Mask]] = {
    "H-A": ("D1 three-candle swing that took the previous week's extreme",
            lambda r: (r["type"] == "three") & r["liq_pw"].eq(True)),
    "H-B": ("D1 engulfing swing", lambda r: r["type"] == "engulf"),
    "H-C": ("D1 three-candle swing that is also engulfing (twin)",
            lambda r: (r["type"] == "three") & r["twin"].eq(True)),
}
BASE: tuple[str, Mask] = ("every D1 three-candle swing (the base, not a hypothesis)", lambda r: r["type"] == "three")


# ── the path ───────────────────────────────────────────────────────────────

def merge_sundays(d1: pd.DataFrame) -> pd.DataFrame:
    """Server D1 bars with each Sunday's short session merged into the next day's bar, stamped at that day."""
    day = d1["time"].dt.normalize()
    key = day + pd.to_timedelta((d1["time"].dt.dayofweek == 6).astype(int), unit="D")
    grouped = d1.groupby(key.to_numpy(), sort=True)
    return pd.DataFrame({"open": grouped["open"].first(), "high": grouped["high"].max(),
                         "low": grouped["low"].min(), "close": grouped["close"].last()}
                        ).rename_axis("time").reset_index()


def d1_frame(instrument: str, bars: pd.DataFrame) -> InstrumentFrame:
    """A research frame whose path bars are the D1 bars: each one opens at 00:00 UTC, inside the New York-close
    trading date of the same day, so the frame's D1 bars are the bars themselves and its W1 bars their weeks."""
    times = pd.DatetimeIndex(bars["time"])
    return frame_from_arrays(instrument, times, *(bars[k].to_numpy(float) for k in ("open", "high", "low", "close")),
                             spread=np.zeros(len(bars)), typical_spread=0.0, stop_slippage=0.0)


def _ambiguous(frame: InstrumentFrame, rows: pd.DataFrame) -> np.ndarray:
    """Failed swings whose failing bar also traded beyond the next-TF objective: the bar did both."""
    out = np.zeros(len(rows), bool)
    failed = (rows["out_next_tf"] == "failed").to_numpy()
    if not failed.any():
        return out
    t = frame.arrays["time"]
    stamp = pd.DatetimeIndex(rows.loc[failed, "resolved_next_tf"]) - pd.Timedelta(minutes=1)
    idx = np.searchsorted(t, stamp.tz_convert("UTC").tz_localize(None).asi8, "left")
    obj = rows.loc[failed, "obj_next_tf"].to_numpy(float)
    low_side = (rows.loc[failed, "side"] == "low").to_numpy()
    out[failed] = np.where(low_side, frame.arrays["high"][idx] > obj, frame.arrays["low"][idx] < obj)
    return out


def swing_rows(instrument: str, since, until) -> pd.DataFrame:
    """The market's D1 swings known in [since, until), scored and with their context, from its frame cut at
    ``until``."""
    since, until = pd.Timestamp(since, tz="UTC"), pd.Timestamp(until, tz="UTC")
    frame = truncate(d1_frame(instrument, merge_sundays(pd.read_parquet(SNAPSHOT / f"{instrument}_D1.parquet"))),
                     until)
    d1_all = build_swings(frame, Timeframe.D1, until=until)
    w1 = build_swings(frame, Timeframe.W1, until=until)
    d1 = d1_all[(d1_all["known_at"] >= since) & (d1_all["known_at"] < until)].reset_index(drop=True)
    table = build_context(frame, d1, build_arrays(frame, ()), all_swings=pd.concat([d1_all, w1], ignore_index=True))
    table["ambiguous"] = _ambiguous(frame, table)
    return atlas_rows({instrument: table})


# ── judging ────────────────────────────────────────────────────────────────

def _interval(keys: np.ndarray, values: np.ndarray, seed: int = SEED) -> tuple[float, float]:
    """95% interval of the mean of ``values``, resampling the units in ``keys`` (all rows of a unit together)."""
    units, index = np.unique(keys, return_inverse=True)
    sums, counts = np.bincount(index, values, len(units)), np.bincount(index, minlength=len(units)).astype(float)
    weights = np.random.default_rng(seed).multinomial(len(units), np.full(len(units), 1 / len(units)),
                                                      size=RESAMPLES).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = (weights @ sums) / (weights @ counts)
    lo, hi = np.percentile(draws[np.isfinite(draws)], [2.5, 97.5])
    return float(lo), float(hi)


def judge(rows: pd.DataFrame, mask: pd.Series) -> dict:
    """The pass rule's numbers and the companions for the swings in ``mask``."""
    picked = rows[mask.to_numpy(bool)]
    g = picked[picked["out_next_tf"].isin(_RESOLVED)]
    held = (g["out_next_tf"] == "held").to_numpy(float)
    geo = g["geo_next_tf"].to_numpy(float)
    gap = held - geo
    dates = pd.to_datetime(g["trading_date"]).to_numpy()
    months = pd.to_datetime(g["trading_date"]).dt.to_period("M").astype(str).to_numpy()
    lo, hi = _interval(dates, gap) if len(g) else (np.nan, np.nan)
    mlo, mhi = _interval(months, gap) if len(g) else (np.nan, np.nan)
    per = {inst: (float(x["held"].mean() - x["geo"].mean()), len(x))
           for inst, x in pd.DataFrame({"instrument": g["instrument"].to_numpy(), "held": held, "geo": geo})
           .groupby("instrument")}
    sides = {}
    for side in ("low", "high"):
        s = (g["side"] == side).to_numpy()
        sides[side] = (float(gap[s].mean()) if s.any() else np.nan, int(s.sum()))
    excess = float(gap.mean()) if len(g) else np.nan
    positive = sum(v > 0 for v, _ in per.values())
    with np.errstate(divide="ignore"):
        r_gross = held / geo - 1.0
    return {"swings": len(picked), "resolved": len(g), "open": int((picked["out_next_tf"] == "open").sum()),
            "no_objective": int(picked["obj_next_tf"].isna().sum()), "ambiguous": int(g["ambiguous"].sum()),
            "dates": int(len(np.unique(dates))), "held": float(held.mean()) if len(g) else np.nan,
            "geo": float(geo.mean()) if len(g) else np.nan, "excess": excess, "lo": lo, "hi": hi,
            "month_lo": mlo, "month_hi": mhi, "per_market": per, "positive": positive, "sides": sides,
            "r_gross": float(np.mean(r_gross)) if len(g) else np.nan,
            "median_geo": float(np.median(geo)) if len(g) else np.nan,
            "passes": bool(excess > 0 and lo > 0 and positive >= MIN_MARKETS)}


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def render(window: str, results: dict) -> str:
    since, until = WINDOWS[window]
    lines = [f"Window `{window}`: swings known {since} to {until}, outcomes read on D1 bars before {until}.", "",
             "| | Swings | Resolved | Held | Geometry | Excess (pts) | 95% dates | 95% months | Markets > 0 | "
             "Lows | Highs | R gross | Passes |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, (label, r) in results.items():
        lines.append(
            f"| {name}: {label} | {r['swings']} | {r['resolved']} | {r['held']:.0%} | {r['geo']:.0%} | "
            f"{_pts(r['excess'])} | [{_pts(r['lo'])}, {_pts(r['hi'])}] | [{_pts(r['month_lo'])}, {_pts(r['month_hi'])}] | "
            f"{r['positive']}/{len(r['per_market'])} | {_pts(r['sides']['low'][0])} ({r['sides']['low'][1]}) | "
            f"{_pts(r['sides']['high'][0])} ({r['sides']['high'][1]}) | {r['r_gross']:+.2f} | "
            f"{'yes' if r['passes'] else 'no' if name != 'base' else '–'} |")
    markets = sorted({m for _, r in results.values() for m in r["per_market"]})
    lines += ["", "Excess per market, points (resolved swings):", "",
              "| | " + " | ".join(markets) + " |", "|---|" + "---|" * len(markets)]
    for name, (_, r) in results.items():
        cells = [f"{_pts(r['per_market'][m][0])} ({r['per_market'][m][1]})" if m in r["per_market"] else "–"
                 for m in markets]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "Bookkeeping: " + "; ".join(
        f"{name} {r['open']} open, {r['no_objective']} without a W1 objective, {r['ambiguous']} failed on a bar that "
        f"did both, median geometry {r['median_geo']:.0%}" for name, (_, r) in results.items()) + "."]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    parser.add_argument("--hypotheses", default=",".join(HYPOTHESES),
                        help="the test window reads only the hypotheses that passed development")
    args = parser.parse_args()
    since, until = WINDOWS[args.window]
    rows = pd.concat([swing_rows(m, since, until) for m in MARKETS], ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(OUT / f"d1_swings_{args.window}.parquet")
    chosen = [h.strip() for h in args.hypotheses.split(",") if h.strip()]
    results = {"base": (BASE[0], judge(rows, BASE[1](rows)))} if args.window == "develop" else {}
    for name in chosen:
        label, mask = HYPOTHESES[name]
        results[name] = (label, judge(rows, mask(rows)))
    print(render(args.window, results))


if __name__ == "__main__":
    main()
