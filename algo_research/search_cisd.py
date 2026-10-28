"""The 2018-2024 search: H-S, the higher-timeframe CISD as the trend (docs/research/SEARCH_2018_2024.md).

The CISD is liquidity-engine Requirement 31's, the engine's own helpers under ``ob_rule = "cisd"``. On H1, H4 and D1
in New York time (H-Q's frames, from M1), from closed candles: a bullish one is the latest run of down closes that
took the latest three-candle swing low before it, once a later candle closes above the run's first open, and is
known at that close. Bearish is the mirror. A frame's trend is the side of its latest CISD.

- **The bias:** each CISD calls its side for its frame's horizon (H1 3 trading days, H4 5, D1 15). It is right when
  the D1 close that many days after its trading day is beyond its own close, and is read against the drift: the
  share of moves over that horizon that went its way.
- **The setups:** H-N's development trades on the side of the frame's trend at C3's open, against their mirror.

Pass: a cell's excess (hit minus drift, or trade minus mirror) above zero with its trading-date interval at 99.17%
(Holm, six cells) above zero, and positive in 6 of the 9 markets.

    python -m algo_research.search_cisd --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_bias import drop_rollover, frames
from algo_research.search_crt import M1_SNAPSHOTS, WINDOWS, _interval
from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT
from algo_research.search_trend import trend_at
from liquidity_engine.detectors.internal import _closed_through_runs, _took_swing
from liquidity_engine.models import Candle, Timeframe

__all__ = ["FRAMES", "HORIZON", "VERSIONS", "bias_calls", "cisd_events", "trend_of"]

FRAMES = ("H1", "H4", "D1")
HORIZON = {"H1": 3, "H4": 5, "D1": 15}                    # trading days
CALLS_FROM = "2021-09-01"
LEVEL = 1 - 0.05 / 6


def _candles(bars: pd.DataFrame, tf: str) -> list[Candle]:
    return [Candle(timestamp=pd.Timestamp(int(t), unit="ns", tz="UTC").to_pydatetime(), open=o, high=h, low=l,
                   close=c, timeframe=Timeframe(tf), instrument="research")
            for t, o, h, l, c in zip(bars["t_open"], bars["open"], bars["high"], bars["low"], bars["close"])]


def cisd_events(bars: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Every CISD on ``bars``, oldest known first: when it is known (``known``, ns), its side (+1 bullish), whether its
    run took the swing before it (``swept``), whether the move away left a gap of its side and when that was known
    (``imbalance``, ``known_hp``), the run's extreme and the close it was known at (``price``)."""
    candles = _candles(bars, tf)
    h, l, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    closes = bars["t_close"].to_numpy(np.int64)
    rows = []
    for bullish in (True, False):
        for first, last, through in _closed_through_runs(candles, bullish):
            gap = next((k for k in range(max(2, last + 1), min(len(bars), through + 2))
                        if ((l[k] > h[k - 2]) if bullish else (h[k] < l[k - 2]))), None)
            rows.append({"known": int(closes[through]), "side": 1 if bullish else -1,
                         "swept": _took_swing(candles, first, last, bullish), "imbalance": gap is not None,
                         "known_hp": int(max(closes[through], closes[gap])) if gap is not None else None,
                         "extreme": float(l[first:last + 1].min() if bullish else h[first:last + 1].max()),
                         "price": float(c[through])})
    cols = ["known", "side", "swept", "imbalance", "known_hp", "extreme", "price"]
    return pd.DataFrame(rows, columns=cols).sort_values("known", kind="stable").reset_index(drop=True)


VERSIONS = ("swept", "every", "high_prob")


def trend_of(events: pd.DataFrame, version: str = "swept") -> pd.DataFrame:
    """The CISDs that set the trend under ``version``, oldest known first: ``swept`` (the rule), ``every`` CISD, or
    ``high_prob`` (swept, with an imbalance after it, known once the gap's third candle closes)."""
    if version == "every":
        e = events
    elif version == "swept":
        e = events[events["swept"]]
    else:
        e = events[events["swept"] & events["imbalance"]].assign(known=lambda x: x["known_hp"].astype("int64"))
    return e.sort_values("known", kind="stable").reset_index(drop=True)


def bias_calls(events: pd.DataFrame, d1: pd.DataFrame, m1: pd.DataFrame, horizon: int, since: int, until: int) -> pd.DataFrame:
    """Each CISD known in [since, until) whose horizon ends by ``until``: its trading date, side, whether the D1 close
    ``horizon`` trading days after its own day went its way (``hit``, None for no move), its market's drift that way
    (``base``) and whether its run's extreme held through the horizon (``held``)."""
    opens, closes_t = d1["t_open"].to_numpy(np.int64), d1["t_close"].to_numpy(np.int64)
    close = d1["close"].to_numpy(float)
    ok = (closes_t >= since) & (np.roll(closes_t, -horizon) <= until)
    ok[-horizon:] = False
    moves = (np.roll(close, -horizon) - close)[ok]
    moves = moves[moves != 0]
    up = float((moves > 0).mean()) if len(moves) else np.nan
    t, lo, hi = m1["time"].pipe(lambda s: pd.DatetimeIndex(s).as_unit("ns").asi8), m1["low"].to_numpy(float), m1["high"].to_numpy(float)
    rows = []
    for e in events.itertuples(index=False):
        if not since <= e.known < until:
            continue
        d = int(np.searchsorted(opens, e.known, side="right")) - 1
        if d < 0 or d + horizon >= len(d1) or closes_t[d + horizon] > until:
            continue
        move = close[d + horizon] - e.price
        a, b = np.searchsorted(t, [e.known, closes_t[d + horizon]])
        held = bool(lo[a:b].min() >= e.extreme) if e.side > 0 else bool(hi[a:b].max() <= e.extreme)
        rows.append({"date": d1["date"].iat[d], "side": int(e.side), "hit": None if move == 0 else bool(np.sign(move) == e.side),
                     "base": up if e.side > 0 else 1 - up, "held": held})
    return pd.DataFrame(rows, columns=["date", "side", "hit", "base", "held"])


def _judge(values: pd.Series, keys: np.ndarray, markets: pd.Series) -> dict:
    v = values.to_numpy(float)
    lo, hi = _interval(keys, v, LEVEL) if len(v) else (np.nan, np.nan)
    per = pd.Series(v).groupby(markets.to_numpy()).mean()
    edge = float(v.mean()) if len(v) else np.nan
    return {"n": len(v), "edge": edge, "lo": lo, "hi": hi, "positive": int((per > 0).sum()), "per": per.to_dict(),
            "passes": bool(edge > 0 and lo > 0 and (per > 0).sum() >= MIN_MARKETS)}


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(M1_SNAPSHOTS), required=True)
    args = parser.parse_args()
    start, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    since_ns, until_ns = (pd.DatetimeIndex([x]).as_unit("ns").asi8[0] for x in (pd.Timestamp(CALLS_FROM, tz="UTC"), until))
    trades = pd.read_parquet(OUT / f"crt_context_{args.window}.parquet")
    calls, tagged = [], []
    for market in MARKETS:
        m1 = pd.read_parquet(M1_SNAPSHOTS[args.window] / f"{market}_M1.parquet")
        m1 = drop_rollover(m1[(m1["time"] >= start) & (m1["time"] < until)].reset_index(drop=True))
        f = frames(m1)
        mine = trades[trades["market"] == market].reset_index(drop=True)
        c3 = pd.DatetimeIndex(mine["c3"]).as_unit("ns").asi8
        cols = {}
        counts = []
        for tf in FRAMES:
            events = cisd_events(f[tf], tf)
            for version in VERSIONS:
                use = trend_of(events, version)
                cols[f"{version}_{tf}"] = trend_at(use, c3)
                calls.append(bias_calls(use, f["D1"], m1, HORIZON[tf], since_ns, until_ns)
                             .assign(market=market, frame=tf, version=version))
            counts.append(f"{tf} {int(events['swept'].sum()):,} swept of {len(events):,}")
        tagged.append(mine.assign(**cols))
        print(f"{market}: CISDs " + ", ".join(counts), flush=True)
    b = pd.concat(calls, ignore_index=True)
    t = pd.concat(tagged, ignore_index=True)
    b.to_parquet(OUT / f"cisd_calls_{args.window}.parquet")
    t.to_parquet(OUT / f"cisd_trades_{args.window}.parquet")

    print(f"\n**The bias:** hit rate minus drift, in points [{100 * LEVEL:.2f}% trading dates]\n")
    print("| Frame (horizon) | CISD | Calls | Hit | Drift | Excess | Interval | 95% months | Markets > 0 | Extreme held | Passes |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for tf in FRAMES:
        for version in VERSIONS:
            x = b[(b["frame"] == tf) & (b["version"] == version)].dropna(subset=["hit"])
            if x.empty:
                print(f"| {tf} ({HORIZON[tf]}d) | {version} | 0 | | | | | | | | |")
                continue
            ex = x["hit"].astype(float) - x["base"]
            r = _judge(ex, pd.to_datetime(x["date"]).to_numpy(), x["market"])
            months = pd.to_datetime(x["date"]).dt.to_period("M").astype(str).to_numpy()
            mlo, mhi = _interval(months, ex.to_numpy(float), 0.95)
            name = f"**{tf} ({HORIZON[tf]}d)**" if version == "swept" else f"{tf} ({HORIZON[tf]}d)"
            print(f"| {name} | {version} | {len(x):,} | {x['hit'].mean():.1%} | {x['base'].mean():.1%} | {_pts(r['edge'])} | "
                  f"[{_pts(r['lo'])}, {_pts(r['hi'])}] | [{_pts(mlo)}, {_pts(mhi)}] | {r['positive']}/9 | {x['held'].mean():.0%} | "
                  f"{('yes' if r['passes'] else 'no') if version == 'swept' else '–'} |")

    print(f"\n**The setups in sync:** trade minus mirror, 5R with the partial [{100 * LEVEL:.2f}%]\n")
    print("| Setups | n | Trade - mirror | Interval | Markets > 0 | R net | R gross | Stopped before 3R | Passes |")
    print("|---|---|---|---|---|---|---|---|---|")
    paired = t.dropna(subset=["mirror_net_5"])

    def row(name, mask, judged=False):
        x = paired[mask.loc[paired.index]]
        if x.empty:
            return f"| {name} | 0 | | | | | | | |"
        r = _judge(x["net_5"] - x["mirror_net_5"], x["date"].to_numpy(), x["market"])
        return (f"| {name} | {len(x):,} | {r['edge']:+.3f} | [{r['lo']:+.3f}, {r['hi']:+.3f}] | {r['positive']}/9 | "
                f"{x['net_5'].mean():+.3f} | {x['gross_5'].mean():+.3f} | {(x['gross_3'] <= -0.999).mean():.0%} | "
                f"{('yes' if r['passes'] else 'no') if judged else '–'} |")

    for tf in FRAMES:
        print(row(f"**with the {tf} CISD trend**", t["side"] == t[f"swept_{tf}"], judged=True))
        print(row("against it", t["side"] == -t[f"swept_{tf}"]))
        print(row(f"with the {tf} trend, every CISD", t["side"] == t[f"every_{tf}"]))
        print(row(f"with the {tf} trend, high probability", t["side"] == t[f"high_prob_{tf}"]))
    print(row("with both H1 and H4", (t["side"] == t["swept_H1"]) & (t["side"] == t["swept_H4"])))
    print(row("all of H-N", t["side"] != 0))


if __name__ == "__main__":
    main()
