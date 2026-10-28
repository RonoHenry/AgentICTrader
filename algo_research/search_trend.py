"""The 2018-2024 search: H-R, setups with the displacement trend (docs/research/SEARCH_2018_2024.md).

The trader's bullish trend: price breaks and displaces through swing highs, forming bullish FVGs as it goes. On one
frame (H1, H4 or D1 in New York time, H-Q's frames), from closed candles:

- **Swings:** three-candle swing highs and lows, each known at the close of the candle after it.
- **A bullish displacement break:** a candle closes above the latest known swing high, and it is the second or third
  candle of a bullish fair value gap; known at the gap's third close. Bearish is the mirror.
- **The trend:** the side of the latest displacement break. A close through a swing without a gap (a failure to
  displace) leaves it as it was; before any break there is none.

H-N's development trades are kept when their side is the trend's at C3's open. Pass: for a frame, the kept trades
beat their mirror (5R with the partial) with the trading-date interval at 98.3% (Holm, three frames) above zero, in
6 of the 9 markets.

    python -m algo_research.search_trend --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_bias import drop_rollover, frames
from algo_research.search_crt import M1_SNAPSHOTS, WINDOWS, _interval
from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT

__all__ = ["FRAMES", "trend_at", "trend_breaks"]

FRAMES = ("H1", "H4", "D1")
LEVEL = 1 - 0.05 / len(FRAMES)


def trend_breaks(bars: pd.DataFrame, displacement: bool = True) -> pd.DataFrame:
    """The breaks that set the trend on ``bars`` (closed candles, oldest first): when each is known (``known``, ns:
    the close that confirms it) and its side (+1 up). Without ``displacement`` every close through a swing counts."""
    h, l, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    closes = bars["t_close"].to_numpy(np.int64)
    swing_high = swing_low = None
    broke_up = broke_down = -10                                # the latest candle that closed through a swing
    rows = []
    for i in range(len(bars)):
        if swing_high is not None and c[i] > swing_high:
            broke_up, swing_high = i, None
            if not displacement:
                rows.append((closes[i], 1))
        if swing_low is not None and c[i] < swing_low:
            broke_down, swing_low = i, None
            if not displacement:
                rows.append((closes[i], -1))
        if i < 2:
            continue
        if displacement and l[i] > h[i - 2] and broke_up in (i - 1, i):       # the break is the gap's C2 or C3
            rows.append((closes[i], 1))
            broke_up = -10
        if displacement and h[i] < l[i - 2] and broke_down in (i - 1, i):
            rows.append((closes[i], -1))
            broke_down = -10
        if h[i - 1] > h[i - 2] and h[i - 1] > h[i]:            # the swing at i - 1, known at this close
            swing_high = h[i - 1]
        if l[i - 1] < l[i - 2] and l[i - 1] < l[i]:
            swing_low = l[i - 1]
    return pd.DataFrame(rows, columns=["known", "side"])


def trend_at(breaks: pd.DataFrame, times_ns: np.ndarray) -> np.ndarray:
    """The trend (+1, -1, 0 for none yet) at each of ``times_ns``, from the breaks known by then."""
    known = breaks["known"].to_numpy(np.int64)
    if not len(known):
        return np.zeros(len(times_ns), dtype=int)
    j = np.searchsorted(known, times_ns, side="right") - 1
    return np.where(j >= 0, breaks["side"].to_numpy()[np.maximum(j, 0)], 0)


def _ns(times) -> np.ndarray:
    return pd.DatetimeIndex(times).as_unit("ns").asi8


def tag(trades: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    """One market's H-N trades with the trend on each frame at C3's open, with and without the gap."""
    f = frames(m1)
    c3 = _ns(trades["c3"])
    out = {}
    for tf in FRAMES:
        out[f"trend_{tf}"] = trend_at(trend_breaks(f[tf]), c3)
        out[f"plain_{tf}"] = trend_at(trend_breaks(f[tf], displacement=False), c3)
    return trades.assign(**out)


def judge(t: pd.DataFrame) -> dict:
    """The pass rule's numbers for the trades ``t`` (all kept), and their own R."""
    paired = t.dropna(subset=["mirror_net_5"])
    diff = (paired["net_5"] - paired["mirror_net_5"]).to_numpy(float)
    lo, hi = _interval(paired["date"].to_numpy(), diff, LEVEL) if len(paired) else (np.nan, np.nan)
    per = {m: float((g["net_5"] - g["mirror_net_5"]).mean()) for m, g in paired.groupby("market")}
    positive = sum(v > 0 for v in per.values())
    edge = float(diff.mean()) if len(diff) else np.nan
    return {"trades": len(t), "edge": edge, "lo": lo, "hi": hi, "positive": positive, "per_market": per,
            "net": float(t["net_5"].mean()), "gross": float(t["gross_5"].mean()),
            "stopped": float((t["gross_3"] <= -0.999).mean()),
            "passes": bool(edge > 0 and lo > 0 and positive >= MIN_MARKETS)}


def _row(name: str, t: pd.DataFrame, total: int) -> str:
    if t.empty:
        return f"| {name} | 0 | | | | | | |"
    r = judge(t)
    return (f"| {name} | {r['trades']:,} ({r['trades'] / total:.0%}) | {r['edge']:+.3f} [{r['lo']:+.3f}, {r['hi']:+.3f}] | "
            f"{r['positive']}/9 | {r['net']:+.3f} | {r['gross']:+.3f} | {r['stopped']:.0%} | {'yes' if r['passes'] else 'no'} |")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(M1_SNAPSHOTS), required=True)
    args = parser.parse_args()
    start, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    trades = pd.read_parquet(OUT / f"crt_context_{args.window}.parquet")      # H-N's trades, with H-O's tags
    parts = []
    for market in MARKETS:
        m1 = pd.read_parquet(M1_SNAPSHOTS[args.window] / f"{market}_M1.parquet")
        m1 = drop_rollover(m1[(m1["time"] >= start) & (m1["time"] < until)].reset_index(drop=True))
        parts.append(tag(trades[trades["market"] == market].reset_index(drop=True), m1))
        print(f"{market}: {len(parts[-1]):,} trades", flush=True)
    t = pd.concat(parts, ignore_index=True)
    t.to_parquet(OUT / f"trend_{args.window}.parquet")
    total = len(t)
    print(f"\n| Setups | n (share) | Trade - mirror, 5R + partial [{100 * LEVEL:.1f}%] | Markets > 0 | R net | R gross | "
          f"Stopped before 3R | Passes |")
    print("|---|---|---|---|---|---|---|---|")
    for tf in FRAMES:
        print(_row(f"**with the {tf} displacement trend**", t[t["side"] == t[f"trend_{tf}"]], total))
        print(_row(f"against it", t[t["side"] == -t[f"trend_{tf}"]], total))
        print(_row(f"with the {tf} trend without the gap", t[t["side"] == t[f"plain_{tf}"]], total))
    agree = (t["side"] == t["trend_H1"]) & (t["side"] == t["trend_H4"]) & (t["side"] == t["trend_D1"])
    print(_row("with all three frames", t[agree], total))
    print(_row("with the H4 trend and at a gap (H-O's array)", t[(t["side"] == t["trend_H4"]) & t["array"]], total))
    print(_row("all of H-N", t, total))
    for tf in FRAMES:
        r = judge(t[t["side"] == t[f"trend_{tf}"]])
        print(f"\nTrade - mirror per market, with the {tf} trend: " +
              ", ".join(f"{m} {v:+.3f}" for m, v in r["per_market"].items()))


if __name__ == "__main__":
    main()
