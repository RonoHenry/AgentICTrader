"""Split a backtest's filled trades by where the entry sits in the sweep's leg (docs/backtests/CONFIRMATION_OTE.md).

The trader (2026-10-23, GBPUSD Wed 29 January 2025): after the sweep, a displacement, then the retracement into the
optimal trade entry, 0.62-0.79 of the leg (their Model A, 2026-10-15). For each filled trade of a run, oriented as a
short (longs mirrored), from M1 known at the decision time t:
- **the sweep extreme X**: the highest high since the raid window opened: the open of the strategy calendar's H4
  candle before the one holding t (H4 anchored at 17:00 New York; the variants' raid_window = H4, 2 candles);
- **the leg's low L**: the lowest low from X's minute to t;
- **pos**: the entry's place in the leg, (entry - L) / (X - L): 0 at L, 1 at X. In the OTE when 0.62 <= pos <= 0.79.

The OTE trades are then judged on the backtester's pass mark of 2026-10-07, with its own statistics
(algo_backtester.metrics): at least 100 trades; the expectancy's 95% interval above zero; profit factor >= 1.3;
drawdown <= 15R; costs <= 40% of gross R.

    python scripts/ote_split.py <run id or prefix> [--snapshot focus-2025-2026h1]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from algo_backtester.metrics import _max_drawdown, bootstrap_ci  # noqa: E402

NY = "America/New_York"
OTE = (0.62, 0.79)
RESAMPLES, SEED = 10_000, 20261007


def window_start(t: pd.Timestamp) -> pd.Timestamp:
    """The open of the strategy calendar's H4 candle before the one holding ``t`` (UTC)."""
    ny = t.tz_convert(NY)
    anchor = ny.normalize() + pd.Timedelta(hours=17)
    if anchor > ny:
        anchor -= pd.Timedelta(days=1)
    k = int((ny - anchor) / pd.Timedelta(hours=4))
    return (anchor + pd.Timedelta(hours=4 * (k - 1))).tz_convert("UTC")


def leg_position(trade: pd.Series, m1: pd.DataFrame) -> float:
    """``pos`` of one trade, NaN without a leg."""
    t = trade["t"]
    w = m1[(m1.index >= window_start(t)) & (m1.index < t)]
    if w.empty:
        return float("nan")
    short = trade["direction"] == "SHORT"
    hi, lo = (w["high"], w["low"]) if short else (-w["low"], -w["high"])
    x_time, x = hi.idxmax(), hi.max()
    low = lo[lo.index >= x_time].min()
    entry = trade["entry"] if short else -trade["entry"]
    return float((entry - low) / (x - low)) if x > low else float("nan")


def judge(trades: pd.DataFrame) -> dict:
    """The pass mark's five numbers, on trades in closing order."""
    done = trades.sort_values("closed_at")
    net = done["net_r"].to_list()
    won, lost = sum(r for r in net if r > 0), -sum(r for r in net if r < 0)
    gross = done["gross_r"].sum()
    cost = done[["cost_r_spread", "cost_r_slippage", "cost_r_commission", "cost_r_swap"]].fillna(0).to_numpy().sum()
    ci = bootstrap_ci(net, RESAMPLES, SEED) if net else (float("nan"), float("nan"))
    out = {"trades": len(net), "expectancy": float(np.mean(net)) if net else float("nan"), "ci": ci,
           "profit_factor": won / lost if lost > 0 else float("nan"), "drawdown": _max_drawdown(net, start=0.0),
           "cost_share": cost / gross if gross > 0 else float("nan"), "total": float(sum(net))}
    out["pass"] = {
        "trades >= 100": out["trades"] >= 100,
        "interval above 0": out["expectancy"] > 0 and ci[0] > 0,
        "profit factor >= 1.3": out["profit_factor"] >= 1.3,
        "drawdown <= 15R": out["drawdown"] <= 15,
        "costs <= 40%": out["cost_share"] <= 0.40,
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="run id or a unique prefix, under data/backtests")
    parser.add_argument("--snapshot", default="focus-2025-2026h1")
    args = parser.parse_args()
    run_dir = next((REPO / "data" / "backtests").glob(f"{args.run}*"))
    journal = pd.read_csv(run_dir / "journal.csv")
    trades = journal[(journal["decision"] == "EXECUTE") & journal["fill"].notna()].copy()
    trades["t"] = pd.to_datetime(trades["t"], utc=True, format="ISO8601")
    trades["closed_at"] = pd.to_datetime(trades["closed_at"], utc=True, format="ISO8601")
    snapshot = REPO / "data" / "research" / "snapshots" / args.snapshot
    parts = []
    for instrument, group in trades.groupby("instrument"):
        m1 = pd.read_parquet(snapshot / f"{instrument}_M1.parquet").set_index("time")
        parts.append(group.assign(pos=[leg_position(row, m1) for _, row in group.iterrows()]))
    trades = pd.concat(parts)
    trades["in_ote"] = trades["pos"].between(*OTE)
    print(f"{run_dir.name[:12]}: {len(trades)} filled trades, {int(trades['in_ote'].sum())} with the entry in "
          f"{OTE[0]}-{OTE[1]} of the sweep's leg")
    for name, part in (("in the OTE", trades[trades["in_ote"]]), ("the rest", trades[~trades["in_ote"]])):
        r = judge(part)
        verdict = "PASS" if all(r["pass"].values()) else "fail: " + ", ".join(k for k, ok in r["pass"].items() if not ok)
        print(f"  {name:10s} n {r['trades']:3d}  {r['expectancy']:+.2f}R [{r['ci'][0]:+.2f}, {r['ci'][1]:+.2f}]"
              f"  total {r['total']:+.1f}R  PF {r['profit_factor']:.2f}  DD {r['drawdown']:.1f}R"
              f"  costs {r['cost_share']:.0%}  -> {verdict}")
    for instrument, g in trades.groupby("instrument"):
        print(f"    {instrument:7s} in {g[g['in_ote']]['net_r'].mean():+.2f} ({int(g['in_ote'].sum())})"
              f"   rest {g[~g['in_ote']]['net_r'].mean():+.2f} ({int((~g['in_ote']).sum())})")


if __name__ == "__main__":
    main()
