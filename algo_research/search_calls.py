"""The 2018-2024 search: its daily direction calls, H-D to H-G (docs/research/SEARCH_2018_2024.md).

Each call is made at a D1 close for the next D1 candle (up: it closes above its open), on the broker's D1 bars with
Sunday merged into Monday (Amendment 1). It is judged against the market's drift. The base rate is the share of the
market's D1 candles in the window that went the call's way; a candle that closes at its open counts for neither.

Pass on development: the hit rate minus the base rate is above zero, with its 95% interval over resampled called
dates above zero, in at least two-thirds of the markets the call covers. Companions, not part of the rule:
- the absolute hit rate;
- the next candle's body in 20-day average ranges, signed by the call, minus the market's mean body signed the
  same way.

    python -m algo_research.search_calls --window develop
"""
from __future__ import annotations

import argparse
from typing import Callable

import numpy as np
import pandas as pd

from algo_research.search_d1 import MARKETS, OUT, SNAPSHOT, WINDOWS, _interval, merge_sundays

__all__ = ["CALLS", "EQUITY", "daily_signals", "judge_calls"]

EQUITY = ("US100", "US500", "US30", "GER40", "UK100")
TREND_BARS, LOOKBACK, RANGE_BARS = 200, 5, 20

#: name: (label, the markets it covers, the call at each close: +1 up, -1 down, 0 none)
Call = Callable[[pd.DataFrame], np.ndarray]
CALLS: dict[str, tuple[str, tuple[str, ...], Call]] = {
    "H-D": ("a 5-day closing low above the 200-day average calls the next day up", EQUITY,
            lambda d: np.where(d["low5"] & (d["close"] > d["sma200"]), 1, 0)),
    "H-E": ("short-term reversal: a 5-day closing low calls up, a 5-day closing high down", MARKETS,
            lambda d: np.where(d["low5"], 1, np.where(d["high5"], -1, 0))),
    "H-F": ("the 200-day trend: above it calls up, below it down", MARKETS,
            lambda d: np.where(d["sma200"].isna(), 0, np.sign(d["close"] - d["sma200"]))),
    "H-G": ("turn of the month: the last trading day and the first three called up", EQUITY,
            lambda d: np.where(d["next_tom"], 1, 0)),
}


def daily_signals(bars: pd.DataFrame) -> pd.DataFrame:
    """Merged D1 bars with what each close knows (the 200-day average, 5-day closing extremes, the 20-day average
    range, whether the next trading day is a turn-of-month day) and the next candle it calls."""
    d = bars.copy()
    close = d["close"]
    d["sma200"] = close.rolling(TREND_BARS).mean()
    d["low5"] = close < close.shift(1).rolling(LOOKBACK - 1).min()
    d["high5"] = close > close.shift(1).rolling(LOOKBACK - 1).max()
    d["avg_range"] = (d["high"] - d["low"]).rolling(RANGE_BARS).mean()
    month = d["time"].dt.strftime("%Y-%m")
    turn = (d.groupby(month).cumcount() < 3) | (d.groupby(month).cumcount(ascending=False) == 0)
    d["next_tom"] = turn.shift(-1, fill_value=False).astype(bool)
    d["next_time"] = d["time"].shift(-1)
    d["next_dir"] = np.sign(d["close"].shift(-1) - d["open"].shift(-1))
    d["next_body"] = (d["close"].shift(-1) - d["open"].shift(-1)) / d["avg_range"]
    return d


def _window(d: pd.DataFrame, since, until) -> pd.DataFrame:
    """The closes whose next candle opens in [since, until)."""
    since, until = pd.Timestamp(since, tz="UTC"), pd.Timestamp(until, tz="UTC")
    return d[(d["next_time"] >= since) & (d["next_time"] < until)]


def judge_calls(frames: dict[str, pd.DataFrame], markets: tuple[str, ...], call: Call) -> dict:
    """The pass rule's numbers and the companions for one call across ``markets``."""
    parts = []
    for market in markets:
        d = frames[market]
        side = call(d).astype(int)
        valid = d["next_dir"].ne(0).to_numpy() & np.isfinite(d["next_body"].to_numpy())
        up_share = float((d.loc[valid, "next_dir"] > 0).mean())
        mean_body = float(d.loc[valid, "next_body"].mean())
        picked = (side != 0) & valid
        s = side[picked]
        nd = d.loc[picked, "next_dir"].to_numpy()
        base = np.where(s > 0, up_share, 1 - up_share)
        parts.append(pd.DataFrame({
            "market": market, "date": d.loc[picked, "next_time"].dt.normalize().to_numpy(), "side": s,
            "hit": (nd == s).astype(float), "base": base,
            "body": s * d.loc[picked, "next_body"].to_numpy() - s * mean_body}))
    t = pd.concat(parts, ignore_index=True)
    excess = t["hit"] - t["base"]
    lo, hi = _interval(t["date"].to_numpy(), excess.to_numpy())
    blo, bhi = _interval(t["date"].to_numpy(), t["body"].to_numpy())
    per = {m: (float((g["hit"] - g["base"]).mean()), len(g)) for m, g in t.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    need = int(np.ceil(2 * len(markets) / 3))
    sides = {name: (float((g["hit"] - g["base"]).mean()), len(g)) for name, g in
             t.groupby(np.where(t["side"] > 0, "up", "down"))}
    return {"calls": len(t), "hit": float(t["hit"].mean()), "base": float(t["base"].mean()),
            "excess": float(excess.mean()), "lo": lo, "hi": hi, "body": float(t["body"].mean()), "body_lo": blo,
            "body_hi": bhi, "per_market": per, "positive": positive, "need": need, "sides": sides,
            "passes": bool(excess.mean() > 0 and lo > 0 and positive >= need)}


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def render(window: str, results: dict) -> str:
    since, until = WINDOWS[window]
    lines = [f"Window `{window}`: calls for D1 candles opening {since} to {until}.", "",
             "| | Calls | Hit | Base | Excess (pts) | 95% | Markets > 0 | Up calls | Down calls | Body (ranges) | 95% | "
             "Passes |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, (label, r) in results.items():
        up, down = r["sides"].get("up", (np.nan, 0)), r["sides"].get("down", (np.nan, 0))
        lines.append(f"| {name}: {label} | {r['calls']} | {r['hit']:.1%} | {r['base']:.1%} | {_pts(r['excess'])} | "
                     f"[{_pts(r['lo'])}, {_pts(r['hi'])}] | {r['positive']}/{len(r['per_market'])} (need {r['need']}) | "
                     f"{_pts(up[0])} ({up[1]}) | {_pts(down[0])} ({down[1]}) | {r['body']:+.3f} | "
                     f"[{r['body_lo']:+.3f}, {r['body_hi']:+.3f}] | {'yes' if r['passes'] else 'no'} |")
    markets = [m for m in MARKETS if any(m in r["per_market"] for _, r in results.values())]
    lines += ["", "Excess per market, points (calls):", "", "| | " + " | ".join(markets) + " |",
              "|---|" + "---|" * len(markets)]
    for name, (_, r) in results.items():
        cells = [f"{_pts(r['per_market'][m][0])} ({r['per_market'][m][1]})" if m in r["per_market"] else "–"
                 for m in markets]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    parser.add_argument("--calls", default=",".join(CALLS),
                        help="the test window reads only the calls that passed development")
    args = parser.parse_args()
    since, until = WINDOWS[args.window]
    frames = {m: _window(daily_signals(merge_sundays(pd.read_parquet(SNAPSHOT / f"{m}_D1.parquet"))), since, until)
              for m in MARKETS}
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat([f.assign(market=m) for m, f in frames.items()]).to_parquet(OUT / f"d1_calls_{args.window}.parquet")
    results = {}
    for name in (c.strip() for c in args.calls.split(",") if c.strip()):
        label, markets, call = CALLS[name]
        results[name] = (label, judge_calls(frames, markets, call))
    print(render(args.window, results))


if __name__ == "__main__":
    main()
