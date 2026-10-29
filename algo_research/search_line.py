"""The 2018-2024 search: H-T, the line chart's trend (docs/research/SEARCH_2018_2024.md).

A line chart joins the closes, so the trend is read from closes only. On one frame (H1, H4 or D1 in New York time,
H-Q's frames):

- **A closing swing high:** a close above the close before and the close after, known at that next close; the
  low is the mirror.
- **A break:** a close beyond the latest known closing swing, known at that close; a swing counts once.
- **The trend:** the side of the latest break.

H-N's development trades on the trend's side at C3's open, against their mirror: H-R's pass rule (98.3%, three
frames, 6 of 9 markets).

    python -m algo_research.search_line --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_bias import drop_rollover, frames
from algo_research.search_crt import M1_SNAPSHOTS, WINDOWS
from algo_research.search_d1 import MARKETS, OUT
from algo_research.search_trend import FRAMES, LEVEL, _row, judge, trend_at, trend_breaks

__all__ = ["line_breaks", "line_structure"]


def line_breaks(bars: pd.DataFrame) -> pd.DataFrame:
    """The line chart's breaks on ``bars`` (closed candles, oldest first): when each is known (ns) and its side."""
    c = bars["close"].to_numpy(float)
    closes = bars["t_close"].to_numpy(np.int64)
    swing_high = swing_low = None
    rows = []
    for i in range(len(c)):
        if swing_high is not None and c[i] > swing_high:
            rows.append((closes[i], 1))
            swing_high = None
        if swing_low is not None and c[i] < swing_low:
            rows.append((closes[i], -1))
            swing_low = None
        if i >= 2:
            if c[i - 1] > c[i - 2] and c[i - 1] > c[i]:        # the closing swing at i - 1, known at this close
                swing_high = c[i - 1]
            if c[i - 1] < c[i - 2] and c[i - 1] < c[i]:
                swing_low = c[i - 1]
    return pd.DataFrame(rows, columns=["known", "side"])


def line_structure(bars: pd.DataFrame) -> pd.DataFrame:
    """The line chart's structure at each closing swing: up when its last two swing highs and last two swing lows
    both rise, down when both fall, none (0) otherwise; known when the swing is."""
    c = bars["close"].to_numpy(float)
    closes = bars["t_close"].to_numpy(np.int64)
    highs: list[float] = []
    lows: list[float] = []
    rows = []
    for i in range(2, len(c)):
        new = False
        if c[i - 1] > c[i - 2] and c[i - 1] > c[i]:
            highs.append(c[i - 1])
            new = True
        if c[i - 1] < c[i - 2] and c[i - 1] < c[i]:
            lows.append(c[i - 1])
            new = True
        if new and len(highs) >= 2 and len(lows) >= 2:
            up, down = highs[-1] > highs[-2] and lows[-1] > lows[-2], highs[-1] < highs[-2] and lows[-1] < lows[-2]
            rows.append((closes[i], 1 if up else -1 if down else 0))
    return pd.DataFrame(rows, columns=["known", "side"])


def tag(trades: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    """One market's H-N trades with the line chart's trend and structure, and H-R's wick-swing trend, per frame."""
    f = frames(m1)
    c3 = pd.DatetimeIndex(trades["c3"]).as_unit("ns").asi8
    out = {}
    for tf in FRAMES:
        out[f"line_{tf}"] = trend_at(line_breaks(f[tf]), c3)
        out[f"struct_{tf}"] = trend_at(line_structure(f[tf]), c3)
        out[f"wick_{tf}"] = trend_at(trend_breaks(f[tf], displacement=False), c3)
    return trades.assign(**out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(M1_SNAPSHOTS), required=True)
    args = parser.parse_args()
    start, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    trades = pd.read_parquet(OUT / f"crt_context_{args.window}.parquet")
    parts = []
    for market in MARKETS:
        m1 = pd.read_parquet(M1_SNAPSHOTS[args.window] / f"{market}_M1.parquet")
        m1 = drop_rollover(m1[(m1["time"] >= start) & (m1["time"] < until)].reset_index(drop=True))
        parts.append(tag(trades[trades["market"] == market].reset_index(drop=True), m1))
        print(f"{market}: {len(parts[-1]):,} trades", flush=True)
    t = pd.concat(parts, ignore_index=True)
    t.to_parquet(OUT / f"line_{args.window}.parquet")
    total = len(t)
    print(f"\n| Setups | n (share) | Trade - mirror, 5R + partial [{100 * LEVEL:.1f}%] | Markets > 0 | R net | R gross | "
          f"Stopped before 3R | Passes |")
    print("|---|---|---|---|---|---|---|---|")
    for tf in FRAMES:
        print(_row(f"**with the {tf} line-chart trend**", t[t["side"] == t[f"line_{tf}"]], total))
        print(_row("against it", t[t["side"] == -t[f"line_{tf}"]], total))
        print(_row(f"with the {tf} line-chart structure (HH-HL / LH-LL)", t[t["side"] == t[f"struct_{tf}"]], total))
        print(_row(f"with H-R's {tf} wick-swing trend", t[t["side"] == t[f"wick_{tf}"]], total))
    agree = np.logical_and.reduce([t["side"] == t[f"line_{tf}"] for tf in FRAMES])
    print(_row("with all three line charts", t[agree], total))
    print(_row("all of H-N", t, total))
    for tf in FRAMES:
        r = judge(t[t["side"] == t[f"line_{tf}"]])
        print(f"\nTrade - mirror per market, with the {tf} line chart: " +
              ", ".join(f"{m} {v:+.3f}" for m, v in r["per_market"].items()))


if __name__ == "__main__":
    main()
