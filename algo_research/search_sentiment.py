"""The 2018-2024 search: H-X, candle sentiment - the close in the range and the wicks (docs/research/SEARCH_2018_2024.md).

At each MN1, W1 and D1 close (the broker's D1 bars with Sunday merged into Monday, weeks and months built from them,
Amendment 1), the trader's read of the candle:
- **the close in the range:** (close - low) / (high - low); above one half is bullish, below bearish;
- **the wicks:** the longer lower wick is bullish, the longer upper bearish;
- **the call:** the side when the two agree, none otherwise. The colour plays no part.

The outcome is the next candle of the frame closing on the call's side, judged as the daily calls (H-D to H-G)
against the market's drift: the share of its candles of the frame in the window that went the call's way.

Pass: for a cell (a frame), the excess above zero, its interval over resampled call dates at 98.33% (Holm, three
cells) above zero, and positive in 6 of the 9 markets.

    python -m algo_research.search_sentiment --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_bias import _outcome, first_touch
from algo_research.search_crt import _interval
from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT, SNAPSHOT, WINDOWS, merge_sundays
from algo_research.search_side import monthly
from algo_research.search_soup import weekly

__all__ = ["FRAMES", "READS", "judge", "market_rows", "reads"]

FRAMES = ("MN1", "W1", "D1")
ABOVE = {"W1": "MN1", "D1": "W1"}
LEVEL = 1 - 0.05 / len(FRAMES)
STRONG_THIRD, STRONG_WICKS = 1 / 3, 2.0


def reads(bars: pd.DataFrame) -> pd.DataFrame:
    """Each candle's reads (+1 bullish, -1 bearish, 0 none): ``close`` (the close in the range), ``wicks``,
    ``call`` (the two agreeing), ``colour`` and ``strong`` (the call with a close in the outer third and the longer
    wick at least twice the other), with ``pos`` the close in the range."""
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    rng = h - l
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = np.where(rng > 0, (c - l) / rng, np.nan)
    upper, lower = h - np.maximum(o, c), np.minimum(o, c) - l
    close = np.where(np.isnan(pos), 0, np.sign(pos - 0.5)).astype(int)
    wicks = np.sign(lower - upper).astype(int)
    call = np.where(close == wicks, close, 0)
    big, small = np.maximum(upper, lower), np.minimum(upper, lower)
    outer = np.where(call > 0, pos >= 1 - STRONG_THIRD, pos <= STRONG_THIRD)
    strong = np.where((call != 0) & outer & (big >= STRONG_WICKS * small) & (big > 0), call, 0)
    return pd.DataFrame({"pos": pos, "close": close, "wicks": wicks, "call": call,
                         "colour": np.sign(c - o).astype(int), "strong": strong}, index=bars.index)


READS = ("call", "close", "wicks", "colour", "strong")


def market_rows(frames: dict[str, pd.DataFrame], hi: np.ndarray, lo: np.ndarray, market: str, since,
                until) -> pd.DataFrame:
    """Every candle of each frame closing in [since, until) with a next candle, its reads, the next candle's
    direction, the race from its close and the frame above's last closed call."""
    since, until = (pd.DatetimeIndex([pd.Timestamp(x)]).tz_localize(None if pd.Timestamp(x).tz else "UTC")
                    .as_unit("ns").asi8[0] for x in (since, until))
    parts = []
    for tf in FRAMES:
        bars = frames[tf].reset_index(drop=True)
        r = reads(bars)
        o, c = bars["open"].to_numpy(float), bars["close"].to_numpy(float)
        tc = bars["t_close"].to_numpy(np.int64)
        nxt = np.append(np.sign(c[1:] - o[1:]), np.nan)
        keep = (tc >= since) & (np.append(tc[1:], np.iinfo(np.int64).max) <= until) & ~np.isnan(nxt)
        k = np.nonzero(keep)[0]
        out = r.iloc[k].assign(market=market, frame=tf, date=pd.to_datetime(bars["date"].to_numpy()[k]),
                               next_dir=nxt[k])
        races, geos = [], []
        for j in k:
            s = int(r["call"].iat[j])
            if s == 0 or not np.isfinite(r["pos"].iat[j]):
                races.append(""), geos.append(np.nan)
                continue
            outcome, _ = _outcome(s, *first_touch(hi, lo, int(bars["i1"].iat[j]) + 1, bars["high"].iat[j],
                                                  bars["low"].iat[j]))
            races.append(outcome), geos.append(r["pos"].iat[j] if s > 0 else 1 - r["pos"].iat[j])
        out = out.assign(race=races, geo=geos)
        if tf in ABOVE:
            up = frames[ABOVE[tf]].reset_index(drop=True)
            up_call = reads(up)["call"].to_numpy()
            j = np.searchsorted(up["t_close"].to_numpy(np.int64), tc[k], side="right") - 1
            out["above"] = np.where(j >= 0, up_call[np.maximum(j, 0)], 0)
        else:
            out["above"] = 0
        parts.append(out)
    return pd.concat(parts, ignore_index=True)


def _base(t: pd.DataFrame) -> pd.Series:
    """Each row's market drift for its frame: the share of its next candles that closed up (dojis left out)."""
    moved = t[t["next_dir"] != 0]
    up = moved.groupby(["market", "frame"])["next_dir"].apply(lambda s: float((s > 0).mean()))
    return pd.Series([up.get((m, f), np.nan) for m, f in zip(t["market"], t["frame"])], index=t.index)


def _score(t: pd.DataFrame, col: str) -> pd.DataFrame:
    g = t[(t[col] != 0) & (t["next_dir"] != 0)]
    base = np.where(g[col] > 0, g["up_share"], 1 - g["up_share"])
    return g.assign(hit=(g["next_dir"] == g[col]).astype(float), base=base,
                    excess=(g["next_dir"] == g[col]).astype(float) - base)


def judge(t: pd.DataFrame, col: str = "call") -> dict:
    g = _score(t, col)
    if g.empty:
        return {"calls": 0}
    dates = g["date"].to_numpy()
    lo, hi = _interval(dates, g["excess"].to_numpy(), LEVEL) if g["date"].nunique() > 1 else (np.nan, np.nan)
    months = g["date"].dt.to_period("M").astype(str).to_numpy()
    mlo, mhi = _interval(months, g["excess"].to_numpy(), 0.95) if len(set(months)) > 1 else (np.nan, np.nan)
    per = {m: (float(x["excess"].mean()), len(x)) for m, x in g.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    excess = float(g["excess"].mean())
    return {"calls": len(g), "hit": float(g["hit"].mean()), "base": float(g["base"].mean()), "excess": excess,
            "lo": lo, "hi": hi, "month_lo": mlo, "month_hi": mhi, "per_market": per, "positive": positive,
            "passes": bool(excess > 0 and lo > 0 and positive >= MIN_MARKETS)}


def _excess(t: pd.DataFrame, col: str = "call") -> tuple[float, int]:
    g = _score(t, col)
    return (float(g["excess"].mean()) if len(g) else np.nan), len(g)


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def render(t: pd.DataFrame) -> str:
    lines = [f"| Cell | Calls | Hit | Base | Excess (pts) | {100 * LEVEL:.2f}% dates | 95% months | Markets > 0 | Passes |",
             "|---|---|---|---|---|---|---|---|---|"]
    results = {}
    for tf in FRAMES:
        r = results[tf] = judge(t[t["frame"] == tf])
        if not r["calls"]:
            lines.append(f"| {tf} | 0 | | | | | | | |")
            continue
        lines.append(f"| {tf} | {r['calls']:,} | {r['hit']:.1%} | {r['base']:.1%} | {_pts(r['excess'])} | "
                     f"[{_pts(r['lo'])}, {_pts(r['hi'])}] | [{_pts(r['month_lo'])}, {_pts(r['month_hi'])}] | "
                     f"{r['positive']}/9 | {'yes' if r['passes'] else 'no'} |")
    rows = [("the call (close and wicks agreeing)", lambda x: x, "call"),
            ("the close in the range alone", lambda x: x, "close"),
            ("the wicks alone", lambda x: x, "wicks"),
            ("the colour alone", lambda x: x, "colour"),
            ("the strong read", lambda x: x, "strong"),
            ("disagreeing: following the close", lambda x: x[(x["close"] != 0) & (x["wicks"] == -x["close"])], "close"),
            ("disagreeing: following the wicks", lambda x: x[(x["close"] != 0) & (x["wicks"] == -x["close"])], "wicks"),
            ("bullish calls", lambda x: x[x["call"] > 0], "call"),
            ("bearish calls", lambda x: x[x["call"] < 0], "call"),
            ("the frame above agreeing", lambda x: x[(x["above"] != 0) & (x["above"] == x["call"])], "call"),
            ("the frame above against", lambda x: x[(x["above"] != 0) & (x["above"] == -x["call"])], "call")]
    lines += ["", "Companions, hit rate minus drift in points (calls):", "",
              "| Read | " + " | ".join(FRAMES) + " |", "|---" * (len(FRAMES) + 1) + "|"]
    for name, pick, col in rows:
        cells = []
        for tf in FRAMES:
            x, n = _excess(pick(t[t["frame"] == tf]), col)
            cells.append(f"{_pts(x)} ({n:,})" if n else "–")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    race = ["| The race: the call's extreme first, against geometry | "]
    for tf in FRAMES:
        g = t[(t["frame"] == tf) & t["race"].isin(("held", "failed"))]
        race.append(f"{_pts(float(((g['race'] == 'held') - g['geo']).mean()))} ({len(g):,})" if len(g) else "–")
    lines.append(race[0] + " | ".join(race[1:]) + " |")
    lines += [""] + [f"Excess per market, {tf}: " + ", ".join(f"{m} {_pts(v)} ({n:,})"
                                                         for m, (v, n) in r["per_market"].items())
                     for tf, r in results.items() if r["calls"]]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=["develop"], required=True)
    args = parser.parse_args()
    since, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    parts = []
    for market in MARKETS:
        d1 = merge_sundays(pd.read_parquet(SNAPSHOT / f"{market}_D1.parquet"))
        d1 = d1[pd.to_datetime(d1["time"], utc=True) < until].reset_index(drop=True)
        weeks, days = weekly(d1)
        frames = {"D1": days, "W1": weeks, "MN1": monthly(days)}
        rows = market_rows(frames, days["high"].to_numpy(float), days["low"].to_numpy(float), market, since, until)
        parts.append(rows)
        print(f"{market}: " + ", ".join(f"{tf} {int(((rows['frame'] == tf) & (rows['call'] != 0)).sum()):,}"
                                        for tf in FRAMES), flush=True)
    t = pd.concat(parts, ignore_index=True)
    t["up_share"] = _base(t)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_parquet(OUT / f"sentiment_{args.window}.parquet")
    print(render(t))


if __name__ == "__main__":
    main()
