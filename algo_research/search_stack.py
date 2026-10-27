"""The 2018-2024 search: ICT's confluences stacked call the next D1 candle, H-M (docs/research/SEARCH_2018_2024.md).

The trader (2026-10-24): test everything as a whole, stacking confluences to arrive at a conclusion. At each D1
close, on the broker's D1 bars with Sunday merged into Monday (Amendment 1), thirteen reads vote +1 (bullish),
-1 (bearish) or 0 (abstain), with equal weight (nothing is fitted, AR-D10):
- **Context, top-down** (``search_chain``): the MN1, W1 and D1 frames' own directions; the chain's call (H-K);
  the candle profile (``PROFILE``).
- **Value:** price in the W1 and in the D1 dealing range's discount (+1) or premium (-1).
- **Price action on D1** (the trader's five trend signals, ``algo_research.trend``): structure, closes, the failed
  sweep, arrays respected or traded through, PO3.
- **Intermarket:** SMT on the previous day's high and low (``search_smt``), for the paired markets; the others
  abstain.

The score is their sum. The call is its sign when it is at least 7 either way (a clear majority of all thirteen on
balance) and every frame has a dealing range. It is judged as the search's daily calls are, over the nine markets.
Companions: the hit rate at each level of agreement (does more confluence mean more accuracy?), and how alike the
votes are.

    python -m algo_research.search_stack --window develop
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from algo_research.atlas.arrays import build_arrays
from algo_research.search_calls import _window, daily_signals, judge_calls
from algo_research.search_chain import chain_rows
from algo_research.search_d1 import MARKETS, OUT, SNAPSHOT, WINDOWS, d1_frame, merge_sundays
from algo_research.search_smt import SMT_MARKETS, arm_calls, market_days, smt_legs
from algo_research.trend import SIGNALS, trend_signals
from liquidity_engine.models import Timeframe

__all__ = ["BUCKETS", "NET", "VOTES", "smt_sides", "stack_votes"]

VOTES = ("own-MN1", "own-W1", "own-D1", "H-K", "profile", "zone-W1", "zone-D1",
         "structure", "closes", "liquidity", "arrays", "po3", "smt")
#: The call: the score's sign at this many net votes or more, of thirteen.
NET = 7
#: Levels of agreement for the dose-response companion, (low, high) of |score|.
BUCKETS = ((1, 2), (3, 4), (5, 6), (7, 13))
_ZONE = {"DISCOUNT": 1, "PREMIUM": -1}


def _bars(market: str, until: str) -> pd.DataFrame:
    b = merge_sundays(pd.read_parquet(SNAPSHOT / f"{market}_D1.parquet"))
    return b[b["time"] < pd.Timestamp(until, tz="UTC")].reset_index(drop=True)


def smt_sides(bars: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
    """Each paired market's SMT side per date, ungated (H-L's companion `smt-all`): +1, -1, or absent."""
    days = {m: market_days(b) for m, b in bars.items() if m in SMT_MARKETS}
    legs = smt_legs(days)
    calls = arm_calls(legs, pd.Series(True, index=legs.index))
    return {m: calls[calls["market"] == m].set_index("date")["side"] for m in days}


def stack_votes(bars: pd.DataFrame, market: str = "X", smt: Optional[pd.Series] = None) -> pd.DataFrame:
    """The thirteen votes, the score and the call at every D1 close of ``bars``, from the bars to it only."""
    rows = chain_rows(bars)
    out = pd.DataFrame({"time": bars["time"].to_numpy()})
    for name in ("own-MN1", "own-W1", "own-D1", "H-K", "profile"):
        out[name] = rows[name].fillna(0).astype(int).to_numpy()
    zones = rows["zones"].fillna("None/None/None").str.split("/", expand=True)
    out["zone-W1"] = zones[1].map(_ZONE).fillna(0).astype(int).to_numpy()
    out["zone-D1"] = zones[2].map(_ZONE).fillna(0).astype(int).to_numpy()
    out["ranged"] = ~(zones == "None").any(axis=1).to_numpy()

    frame = d1_frame(market, bars)
    d1 = frame.bars[Timeframe.D1].reset_index(drop=True)
    if len(d1):
        assert np.allclose(d1["close"].to_numpy(float), bars["close"].to_numpy(float)[:len(d1)])
    signals = trend_signals(d1, build_arrays(frame, (Timeframe.D1,))) if len(d1) else pd.DataFrame(columns=SIGNALS)
    for name in SIGNALS:                                 # the frame's D1 candle k is bar k; the last isn't closed
        out[name] = np.r_[signals[name].to_numpy(int), np.zeros(len(bars) - len(signals), int)]

    dates = pd.Series(pd.DatetimeIndex(bars["time"]).normalize())
    side = dates.map(smt) if smt is not None else pd.Series(np.nan, index=dates.index)
    out["smt"] = side.fillna(0).astype(int).to_numpy()
    out["score"] = out[list(VOTES)].sum(axis=1)
    out["H-M"] = np.where(out["ranged"] & (out["score"].abs() >= NET), np.sign(out["score"]), 0)
    return out


def _market(args: Tuple[str, str, Optional[pd.Series]]) -> Tuple[str, pd.DataFrame]:
    market, window, smt = args
    since, until = WINDOWS[window]
    bars = _bars(market, until)
    votes = stack_votes(bars, market, smt)
    return market, _window(daily_signals(bars).join(votes.drop(columns="time")), since, until)


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def _row(label: str, r: dict, rule: bool = False) -> str:
    passes = ("yes" if r["passes"] else "no") if rule else "–"
    return (f"| {label} | {r['calls']} | {r['hit']:.1%} | {r['base']:.1%} | {_pts(r['excess'])} | "
            f"[{_pts(r['lo'])}, {_pts(r['hi'])}] | {r['positive']}/{len(r['per_market'])} (need {r['need']}) | "
            f"{r['body']:+.3f} | {passes} |")


def run(window: str, workers: int = 3) -> str:
    since, until = WINDOWS[window]
    smt = smt_sides({m: _bars(m, until) for m in SMT_MARKETS})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        frames = dict(pool.map(_market, [(m, window, smt.get(m)) for m in MARKETS]))
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat([f.assign(market=m) for m, f in frames.items()]).to_parquet(OUT / f"stack_calls_{window}.parquet")
    head = ["| | Calls | Hit | Base | Excess (pts) | 95% | Markets > 0 | Body (ranges) | Passes |",
            "|---|---|---|---|---|---|---|---|---|"]
    lines = [f"Window `{window}`: calls for D1 candles opening {since} to {until}.", "", *head,
             _row(f"**H-M: net {NET}+ of 13 votes**", judge_calls(frames, MARKETS, lambda d: d["H-M"].to_numpy()),
                  rule=True)]
    lines += ["", "By the level of agreement (|score|), ranged closes only:", "", *head]
    for lo, hi in BUCKETS:
        call = lambda d, a=lo, b=hi: np.where(d["ranged"] & d["score"].abs().between(a, b),  # noqa: E731
                                              np.sign(d["score"]), 0)
        lines.append(_row(f"{lo}-{hi}", judge_calls(frames, MARKETS, call)))
    allv = pd.concat(frames.values(), ignore_index=True)
    allv = allv[allv["ranged"]]
    corr = allv[list(VOTES)].astype(float).corr().to_numpy()
    off = corr[~np.eye(len(VOTES), dtype=bool)]
    share = allv["score"].abs().value_counts(normalize=True).sort_index()
    lines += ["", f"Ranged closes: {len(allv)}. Mean pairwise correlation of the votes: {np.nanmean(off):+.2f} "
              f"(the largest {np.nanmax(off):+.2f}).",
              "Share of ranged closes by |score|: " + ", ".join(f"{int(k)}: {v:.1%}" for k, v in share.items()) + "."]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    print(run(args.window, args.workers))


if __name__ == "__main__":
    main()
