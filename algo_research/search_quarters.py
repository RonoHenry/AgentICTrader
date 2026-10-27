"""The 2018-2024 search: H-P, the quarterly theory's false move traded into Q3 (docs/research/SEARCH_2018_2024.md).

Daye's quarters in New York time: the day's (Q1 18:00-00:00, Q2 00:00-06:00, Q3 06:00-12:00, Q4 12:00-18:00), and
each six hours' four quarters of 90 minutes. In a set (a day, or one six-hour session) Q1 is C1, Q2 C2 and Q3 C3:

- **The false move:** Q2 trades beyond one side of Q1's range, not the other, and closes back inside it.
- **The trade:** at market at Q3's first M1 bar, against the false move; the stop beyond Q2's extreme; 5R with a
  third off at 3R and the rest's stop to the fill; out by 17:00 New York. H-N's race and costs.
- **At a gap:** Q2's wick reached into an unfilled H1 or H4 gap of the trade's side formed before Q2 opened, and Q2
  closed short of its far edge (H-O's ``Context``).
- **Pass:** a cell's mean R net above zero with its trading-date interval at 98.75% (Holm, four cells), and positive
  in 6 of the 9 markets.

Beside it: the mirror, the risk in spreads, and each quarter's share of its set's range.

    python -m algo_research.search_quarters --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_crt import M1_SNAPSHOTS, NY, WINDOWS, _interval, _Path, race
from algo_research.search_crt_context import WARMUP, Context
from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT, SNAPSHOT

__all__ = ["LEVELS", "quarter_sets", "false_moves", "trades"]

LEVELS = ("day", "session")
LEVEL = 1 - 0.05 / 4
TARGET = "5"
_DAY_OPENS = pd.Timedelta(hours=18)


def quarter_sets(m1: pd.DataFrame, level: str) -> pd.DataFrame:
    """Each set's quarters (0-3): its start (New York, naive), high, low, close, first M1 row and first time."""
    local = m1["time"].dt.tz_convert(NY).dt.tz_localize(None)
    day = (local - _DAY_OPENS).dt.normalize() + _DAY_OPENS                 # the 18:00 that opens the day
    minutes = ((local - day).dt.total_seconds() // 60).astype(int)
    dq = minutes // 360
    if level == "day":
        start, quarter = day, dq
    else:
        start, quarter = day + pd.to_timedelta(dq * 6, unit="h"), (minutes % 360) // 90
    frame = pd.DataFrame({"set": start, "quarter": quarter, "high": m1["high"].to_numpy(float),
                          "low": m1["low"].to_numpy(float), "close": m1["close"].to_numpy(float),
                          "i": np.arange(len(m1)), "time": m1["time"]})
    return frame.groupby(["set", "quarter"], sort=True).agg(high=("high", "max"), low=("low", "min"),
                                                           close=("close", "last"), i=("i", "first"),
                                                           time=("time", "first")).reset_index()


def false_moves(sets: pd.DataFrame) -> pd.DataFrame:
    """The sets whose Q2 took one side of Q1 and closed back inside: the side to trade (+1 long), Q2's extremes and
    close, Q2's open and Q3's first M1 row."""
    wide = sets.pivot(index="set", columns="quarter")
    need = all((f, q) in wide.columns for f in ("high", "low", "close", "i", "time") for q in (0, 1, 2))
    if not need:
        return pd.DataFrame(columns=["set", "side", "q2_high", "q2_low", "q2_close", "q2_open", "e"])
    w = wide.dropna(subset=[("high", 0), ("high", 1), ("i", 2)])
    h1, l1 = w[("high", 0)], w[("low", 0)]
    h2, l2, c2 = w[("high", 1)], w[("low", 1)], w[("close", 1)]
    short = (h2 > h1) & (l2 >= l1) & (c2 < h1)
    long_ = (l2 < l1) & (h2 <= h1) & (c2 > l1)
    picked = w[short | long_]
    return pd.DataFrame({"set": picked.index, "side": np.where(long_[short | long_], 1, -1),
                         "q2_high": picked[("high", 1)].to_numpy(float), "q2_low": picked[("low", 1)].to_numpy(float),
                         "q2_close": picked[("close", 1)].to_numpy(float), "q2_open": picked[("time", 1)].to_numpy(),
                         "e": picked[("i", 2)].to_numpy(int)})


def shares(sets: pd.DataFrame) -> pd.DataFrame:
    """Each complete set's four quarters' ranges as shares of their sum."""
    r = (sets["high"] - sets["low"]).to_numpy(float)
    wide = pd.DataFrame({"set": sets["set"], "quarter": sets["quarter"], "range": r}).pivot(
        index="set", columns="quarter", values="range").dropna()
    total = wide.sum(axis=1)
    return wide[total > 0].div(total[total > 0], axis=0)


def trades(m1: pd.DataFrame, ctx: Context, market: str, level: str) -> pd.DataFrame:
    """H-P's trades in one market at one level, each with its mirror, its gaps and its trading date."""
    p = _Path(m1)
    rows = []
    for s in false_moves(quarter_sets(m1, level)).itertuples(index=False):
        e = int(s.e)
        trade = race(p, int(s.side), e, s.q2_low if s.side > 0 else s.q2_high)
        if trade is None:
            continue
        s0 = p.cost[e]
        mirror_trigger = p.o[e] + trade["risk"] - s0 if s.side > 0 else p.o[e] + s0 - trade["risk"]
        mirror = race(p, -int(s.side), e, mirror_trigger)
        c3 = pd.Timestamp(p.t[e], tz="UTC")
        arrays = ctx.arrays_at(int(pd.Timestamp(s.q2_open).value), int(s.side), s.q2_high, s.q2_low, s.q2_close)
        rows.append({"market": market, "level": level, "c3": c3,
                     "date": (c3.tz_convert(NY) - pd.Timedelta(hours=17)).normalize().tz_localize(None),
                     "side": int(s.side), "gap": bool(arrays), "arrays": ", ".join(arrays),
                     "risk_spreads": trade["risk_spreads"], "net": trade[f"net_{TARGET}"],
                     "gross": trade[f"gross_{TARGET}"], "mirror": mirror[f"net_{TARGET}"] if mirror else np.nan})
    return pd.DataFrame(rows)


def judge(t: pd.DataFrame) -> dict:
    dates = t["date"].to_numpy()
    lo, hi = _interval(dates, t["net"].to_numpy(float), LEVEL)
    paired = t.dropna(subset=["mirror"])
    diff = (paired["net"] - paired["mirror"]).to_numpy(float)
    mlo, mhi = _interval(paired["date"].to_numpy(), diff, 0.95)
    per = {m: float(g["net"].mean()) for m, g in t.groupby("market")}
    positive = sum(v > 0 for v in per.values())
    return {"n": len(t), "net": float(t["net"].mean()), "lo": lo, "hi": hi, "gross": float(t["gross"].mean()),
            "minus_mirror": float(diff.mean()), "mlo": mlo, "mhi": mhi, "risk": float(t["risk_spreads"].median()),
            "win": float((t["net"] > 0).mean()), "per": per, "positive": positive,
            "passes": bool(t["net"].mean() > 0 and lo > 0 and positive >= MIN_MARKETS)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(M1_SNAPSHOTS), required=True)
    args = parser.parse_args()
    since, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    parts, vol = [], {level: [] for level in LEVELS}
    for market in MARKETS:
        m15 = pd.read_parquet(SNAPSHOT / f"{market}_M15.parquet")
        m15 = m15[(m15["time"] >= since - WARMUP) & (m15["time"] < until)].reset_index(drop=True)
        ctx = Context(m15)
        m1 = pd.read_parquet(M1_SNAPSHOTS[args.window] / f"{market}_M1.parquet")
        m1 = m1[(m1["time"] >= since) & (m1["time"] < until + pd.Timedelta(days=1))].reset_index(drop=True)
        for level in LEVELS:
            t = trades(m1, ctx, market, level)
            parts.append(t[(t["c3"] >= since) & (t["c3"] < until)])
            vol[level].append(shares(quarter_sets(m1, level)).assign(market=market))
        print(f"{market}: " + ", ".join(f"{lv} {int((parts[-2 + k]['level'] == lv).sum()):,}" for k, lv in enumerate(LEVELS)),
              flush=True)
    t = pd.concat(parts, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_parquet(OUT / f"quarters_{args.window}.parquet")
    print(f"\nWindow `{args.window}`: Q3 opens {WINDOWS[args.window][0]} to {WINDOWS[args.window][1]}; 5R, a third off at 3R.\n")
    print(f"| Cell | Trades | R net | {100 * LEVEL:.2f}% | R gross | Win | Trade - mirror [95%] | Median risk (spreads) "
          f"| Markets > 0 | Passes |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    results = {}
    for level in LEVELS:
        for gap in (False, True):
            cell = t[(t["level"] == level) & (t["gap"] if gap else True)]
            if cell.empty:
                continue
            r = results[(level, gap)] = judge(cell)
            print(f"| {level} quarters{' at a gap' if gap else ''} | {r['n']:,} | {r['net']:+.3f} | [{r['lo']:+.3f}, "
                  f"{r['hi']:+.3f}] | {r['gross']:+.3f} | {r['win']:.0%} | {r['minus_mirror']:+.3f} [{r['mlo']:+.3f}, "
                  f"{r['mhi']:+.3f}] | {r['risk']:.1f} | {r['positive']}/9 | {'yes' if r['passes'] else 'no'} |")
    for (level, gap), r in results.items():
        print(f"\nR net per market, {level}{' at a gap' if gap else ''}: " +
              ", ".join(f"{m} {v:+.3f}" for m, v in r["per"].items()))
    for level in LEVELS:
        v = pd.concat(vol[level])
        mean = v[[0, 1, 2, 3]].mean()
        print(f"\nShare of the {level}'s range by quarter (mean over {len(v):,} sets): " +
              ", ".join(f"Q{q + 1} {mean[q]:.1%}" for q in range(4)) +
              "  |  Q2+Q3 by market: " + ", ".join(f"{m} {g[1].mean() + g[2].mean():.0%}" for m, g in v.groupby("market")))


if __name__ == "__main__":
    main()
