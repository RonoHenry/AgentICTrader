"""The 2018-2024 search: ICT's top-down chain calls the next D1 candle, H-K (docs/research/SEARCH_2018_2024.md;
context-engine Requirement 28).

Every layer of the bias hierarchy has been measured alone; this reads them together, top-down. At each D1 close, on
the broker's D1 bars with Sunday merged into Monday (Amendment 1):
- MN1 and W1 candles are built from the D1 candles. A week closes with its Friday candle and a month with its last
  weekday's; one whose last trading day falls earlier closes when the next opens (CE-D18). The forming week and
  month stretch their frame's dealing range.
- Each frame's state (``liquidity_engine.context.frame_state``) reads its own and its parents' closed candles, the
  D1 path to the close, and the IPDA 20/40/60-day ranges as objectives.
- The chain (``liquidity_engine.context.chain``, ``PD_POI``) runs MN1 -> W1 -> D1. The call is the D1 link's context
  direction, made only while the chain is armed and every frame has a dealing range.

It is judged as the search's daily calls are (``search_calls.judge_calls``): the hit rate against the market's
drift, with a trading-date interval, per market. Companions, not part of the rule: the draw reached before the
opposite objective against a driftless walk's chance, the chain's cases apart, and the ablations (``PROFILE``,
the monthly link dropped, no IPDA ranges, and each frame's own direction alone).

Each market's bars are cut at the window's end before anything is built.

    python -m algo_research.search_chain --window develop
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from algo_research.search_calls import _window, daily_signals, judge_calls
from algo_research.search_d1 import MARKETS, OUT, SNAPSHOT, WINDOWS, _interval, merge_sundays
from liquidity_engine.context.chain import ChainRule, chain
from liquidity_engine.context.frame_state import Candles, FrameState, frame_state
from liquidity_engine.context.ipda import ipda_ranges
from liquidity_engine.models import BiasDirection

__all__ = ["ARMS", "Ladder", "armed_call", "chain_rows", "draw_race", "frame_states", "judge_race", "month_interval",
           "periods"]

BULL, BEAR, NEUTRAL = BiasDirection.BULLISH, BiasDirection.BEARISH, BiasDirection.NEUTRAL
SIDE = {BULL: 1, BEAR: -1, NEUTRAL: 0}
DAY = 86_400

#: name: label. H-K is the hypothesis; the rest are companions.
ARMS: Dict[str, str] = {
    "H-K": "the chain MN1 -> W1 -> D1 (PD_POI, IPDA ranges)",
    "profile": "PROFILE on the same ladder",
    "no-mn1": "the monthly link dropped (W1 -> D1)",
    "no-ipda": "H-K without the IPDA ranges",
    "own-MN1": "the MN1 frame's own direction alone",
    "own-W1": "the W1 frame's own direction alone",
    "own-D1": "the D1 frame's own direction alone",
}


# ── weeks and months from D1 bars ──────────────────────────────────────────

def periods(times: pd.Series) -> Dict[str, np.ndarray]:
    """Per bar: its week's and month's index, and whether the calendar closes the week (a Friday) or the month (its
    last weekday) with this bar (CE-D18). Calendar only: no later bar is read."""
    day = pd.DatetimeIndex(times).tz_convert("UTC").normalize().tz_localize(None)
    week_start = day - pd.to_timedelta(day.dayofweek, unit="D")
    month_start = day.to_period("M").to_timestamp()
    next_weekday = day + pd.offsets.BDay(1)
    return {"week": pd.factorize(week_start)[0], "week_start": week_start.asi8 // 10**9,
            "month": pd.factorize(month_start)[0], "month_start": month_start.asi8 // 10**9,
            "week_closes": np.asarray(day.dayofweek >= 4), "month_closes": np.asarray(next_weekday.month != day.month)}


def _candles(tf: str, index: np.ndarray, start: np.ndarray, o, h, l, c, step) -> Candles:
    """The periods' candles from the D1 bars in them, each ending where the next period starts."""
    first = np.r_[0, np.flatnonzero(np.diff(index)) + 1]
    last = np.r_[first[1:] - 1, len(index) - 1]
    t = start[first]
    return Candles(tf, t, step(t), o[first], np.maximum.reduceat(h, first), np.minimum.reduceat(l, first), c[last])


def _next_month(t: np.ndarray) -> np.ndarray:
    return (pd.DatetimeIndex(pd.to_datetime(t, unit="s")).to_period("M") + 1).to_timestamp().asi8 // 10**9


def _head(c: Candles, n: int) -> Candles:
    return Candles(c.tf, c.t[:n], c.end[:n], c.o[:n], c.h[:n], c.l[:n], c.c[:n])


# ── the chain at every close ───────────────────────────────────────────────

class Ladder:
    """A market's D1 bars as the three frames: what each one has closed, and what its forming candle has made, at
    every D1 close."""

    def __init__(self, bars: pd.DataFrame):
        self.o, self.h, self.l, self.c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        t = pd.DatetimeIndex(bars["time"]).asi8 // 10**9
        self.p = periods(bars["time"])
        self.d1 = Candles("D1", t, t + DAY, self.o, self.h, self.l, self.c)
        self.w1 = _candles("W1", self.p["week"], self.p["week_start"], self.o, self.h, self.l, self.c,
                           lambda x: x + 7 * DAY)
        self.mn1 = _candles("MN1", self.p["month"], self.p["month_start"], self.o, self.h, self.l, self.c, _next_month)
        self.week_first = np.r_[0, np.flatnonzero(np.diff(self.p["week"])) + 1]
        self.month_first = np.r_[0, np.flatnonzero(np.diff(self.p["month"])) + 1]

    def at(self, i: int):
        """(days, weeks, months, the forming week's (high, low), the forming month's) at the close of bar i."""
        p, h, l = self.p, self.h, self.l
        wi, mi = p["week"][i], p["month"][i]
        weeks = _head(self.w1, wi + 1 if p["week_closes"][i] else wi)
        months = _head(self.mn1, mi + 1 if p["month_closes"][i] else mi)
        w0, m0 = self.week_first[wi], self.month_first[mi]
        w_forming = None if p["week_closes"][i] else (float(h[w0:i + 1].max()), float(l[w0:i + 1].min()))
        m_forming = None if p["month_closes"][i] else (float(h[m0:i + 1].max()), float(l[m0:i + 1].min()))
        return _head(self.d1, i + 1), weeks, months, w_forming, m_forming

    def __len__(self) -> int:
        return len(self.c)


def chain_rows(bars: pd.DataFrame) -> pd.DataFrame:
    """The chain read at every D1 close of ``bars`` (merged, cut at the window's end), from the bars to it only."""
    ladder = Ladder(bars)
    out = pd.DataFrame([_read(*ladder.at(i)) for i in range(len(ladder))])
    out.insert(0, "time", bars["time"].to_numpy())
    return out


def frame_states(days, weeks, months, w_forming, m_forming, levels) -> Tuple[FrameState, FrameState, FrameState]:
    """The MN1, W1 and D1 states at the last day's close (``Ladder.at``'s pieces), with ``levels`` as objectives."""
    price = float(days.c[-1])
    mn1 = frame_state(months, price, path=days, forming=m_forming, levels=levels)
    w1 = frame_state(weeks, price, parents=[months], path=days, forming=w_forming, levels=levels)
    d1 = frame_state(days, price, parents=[weeks, months], path=days, levels=levels)
    return mn1, w1, d1


def armed_call(link_chain, states) -> int:
    """The chain's call, +1 or -1, while it is armed and every frame in ``states`` has a range; else 0."""
    ranged = all(s.range is not None for s in states)
    return SIDE[link_chain.bias.context] if link_chain.armed and ranged else 0


def _read(days, weeks, months, w_forming, m_forming) -> dict:
    row: dict = {}
    if len(weeks) < 2 or len(months) < 2:
        return {name: 0 for name in ARMS}
    with_ipda = frame_states(days, weeks, months, w_forming, m_forming, ipda_ranges(days))
    plain = frame_states(days, weeks, months, w_forming, m_forming, ())
    mn1, w1, d1 = with_ipda
    main = chain(with_ipda)
    row["H-K"] = armed_call(main, with_ipda)
    row["profile"] = armed_call(chain(with_ipda, ChainRule.PROFILE), with_ipda)
    row["no-mn1"] = armed_call(chain((w1, d1)), with_ipda)
    row["no-ipda"] = armed_call(chain(plain), plain)
    ranged = all(s.range is not None for s in with_ipda)               # every arm waits for the same warm-up
    for s in with_ipda:
        row[f"own-{s.tf}"] = SIDE[s.own] if s.own_draw is not None and ranged else 0
    link = main.bias
    row["case"] = link.case
    row["draw"] = link.draw.price if link.draw is not None else np.nan
    opposite = d1.nearest(BEAR if link.context == BULL else BULL) if link.context != NEUTRAL else None
    row["opposite"] = opposite.price if opposite is not None else np.nan
    row["zones"] = "/".join(str(s.zone) for s in with_ipda)
    row["contexts"] = "/".join(x.context.value for x in main.links)
    row["reason"] = " | ".join(x.reason for x in main.links)
    return row


# ── the draw against geometry ──────────────────────────────────────────────

def draw_race(rows: pd.DataFrame, bars: pd.DataFrame, call: str = "H-K") -> pd.DataFrame:
    """For each call with a draw and an opposite objective: which one later D1 bars reach first (a bar reaching
    both fails the call), against a driftless walk's chance from the close. Unresolved by the bars' end: open."""
    h, l, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    out = []
    for i in np.flatnonzero((rows[call] != 0).to_numpy()):
        side, draw, opp = int(rows[call].iloc[i]), rows["draw"].iloc[i], rows["opposite"].iloc[i]
        if not (np.isfinite(draw) and np.isfinite(opp)):
            continue
        up, down = (draw, opp) if side > 0 else (opp, draw)
        hit_up = np.flatnonzero(h[i + 1:] >= up)
        hit_down = np.flatnonzero(l[i + 1:] <= down)
        first_up = hit_up[0] if len(hit_up) else np.inf
        first_down = hit_down[0] if len(hit_down) else np.inf
        if not np.isfinite(min(first_up, first_down)):
            outcome = "open"
        elif first_up == first_down:
            outcome = "both"
        else:
            outcome = "held" if (first_up < first_down) == (side > 0) else "failed"
        geo = (c[i] - opp) / (draw - opp)
        out.append({"time": rows["time"].iloc[i], "side": side, "outcome": outcome, "geo": float(geo)})
    return pd.DataFrame(out, columns=["time", "side", "outcome", "geo"])


def judge_race(races: Dict[str, pd.DataFrame]) -> dict:
    """The draw's excess over geometry across markets: resolved races only, a bar reaching both counted failed."""
    parts = [r.assign(market=m) for m, r in races.items() if len(r)]
    t = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["market", "outcome", "geo", "time"])
    g = t[t["outcome"] != "open"]
    gap = (g["outcome"] == "held").to_numpy(float) - g["geo"].to_numpy(float)
    dates = pd.to_datetime(g["time"]).dt.normalize().to_numpy()
    lo, hi = _interval(dates, gap) if len(g) else (np.nan, np.nan)
    per = {m: float(((x["outcome"] == "held").astype(float) - x["geo"]).mean()) for m, x in g.groupby("market")}
    return {"resolved": len(g), "open": int((t["outcome"] == "open").sum()),
            "both": int((g["outcome"] == "both").sum()),
            "held": float((g["outcome"] == "held").mean()) if len(g) else np.nan,
            "geo": float(g["geo"].mean()) if len(g) else np.nan, "excess": float(gap.mean()) if len(g) else np.nan,
            "lo": lo, "hi": hi, "positive": sum(v > 0 for v in per.values()), "markets": len(per)}


def month_interval(frames: Dict[str, pd.DataFrame], call) -> Tuple[float, float]:
    """The 95% interval of the hit rate's excess over each market's base rate, resampling calendar months (a
    companion: a slow chain's calls run in streaks, so neighbouring dates are not independent)."""
    parts = []
    for d in frames.values():
        side = call(d).astype(int)
        valid = d["next_dir"].ne(0).to_numpy() & np.isfinite(d["next_body"].to_numpy())
        up = float((d.loc[valid, "next_dir"] > 0).mean())
        picked = (side != 0) & valid
        s, nd = side[picked], d.loc[picked, "next_dir"].to_numpy()
        parts.append(pd.DataFrame({"month": d.loc[picked, "next_time"].dt.strftime("%Y-%m").to_numpy(),
                                   "x": (nd == s).astype(float) - np.where(s > 0, up, 1 - up)}))
    t = pd.concat(parts, ignore_index=True)
    return _interval(t["month"].to_numpy(), t["x"].to_numpy()) if len(t) else (np.nan, np.nan)


# ── the run ────────────────────────────────────────────────────────────────

def _market(args: Tuple[str, str]) -> Tuple[str, pd.DataFrame, pd.DataFrame]:
    market, window = args
    since, until = WINDOWS[window]
    bars = merge_sundays(pd.read_parquet(SNAPSHOT / f"{market}_D1.parquet"))
    bars = bars[bars["time"] < pd.Timestamp(until, tz="UTC")].reset_index(drop=True)
    rows = chain_rows(bars)
    signals = daily_signals(bars).join(rows.drop(columns="time"))
    called = _window(signals, since, until)
    race = draw_race(rows, bars)
    return market, called, race[race["time"].isin(called["time"])]


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def render(window: str, calls: Dict[str, dict], race: dict, cases: Dict[str, dict],
           months: Tuple[float, float]) -> str:
    since, until = WINDOWS[window]
    lines = [f"Window `{window}`: calls for D1 candles opening {since} to {until}.", "",
             "| | Calls | Hit | Base | Excess (pts) | 95% | Markets > 0 | Body (ranges) | Passes |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, r in calls.items():
        passes = ("yes" if r["passes"] else "no") if name == "H-K" else "–"
        lines.append(f"| {name}: {ARMS[name]} | {r['calls']} | {r['hit']:.1%} | {r['base']:.1%} | "
                     f"{_pts(r['excess'])} | [{_pts(r['lo'])}, {_pts(r['hi'])}] | "
                     f"{r['positive']}/{len(r['per_market'])} (need {r['need']}) | {r['body']:+.3f} | {passes} |")
    lines += ["", f"H-K's excess, 95% over resampled months: [{_pts(months[0])}, {_pts(months[1])}].",
              "", "H-K by the chain's case at the bias frame:", "",
              "| Case | Calls | Hit | Base | Excess (pts) | 95% |", "|---|---|---|---|---|---|"]
    for case, r in cases.items():
        lines.append(f"| {case} | {r['calls']} | {r['hit']:.1%} | {r['base']:.1%} | {_pts(r['excess'])} | "
                     f"[{_pts(r['lo'])}, {_pts(r['hi'])}] |")
    lines += ["", "H-K's draw reached before the D1 objective on the other side, against a driftless walk:", "",
              "| Resolved | Open | Both in a bar | Held | Geometry | Excess (pts) | 95% | Markets > 0 |",
              "|---|---|---|---|---|---|---|---|",
              f"| {race['resolved']} | {race['open']} | {race['both']} | {race['held']:.1%} | {race['geo']:.1%} | "
              f"{_pts(race['excess'])} | [{_pts(race['lo'])}, {_pts(race['hi'])}] | "
              f"{race['positive']}/{race['markets']} |"]
    markets = list(calls["H-K"]["per_market"])
    lines += ["", "H-K's excess per market, points (calls):", "", "| " + " | ".join(markets) + " |",
              "|" + "---|" * len(markets),
              "| " + " | ".join(f"{_pts(v)} ({n})" for v, n in calls["H-K"]["per_market"].values()) + " |"]
    return "\n".join(lines)


def run(window: str, workers: int = 3) -> str:
    with ProcessPoolExecutor(max_workers=workers) as pool:
        done = list(pool.map(_market, [(m, window) for m in MARKETS]))
    frames = {m: f for m, f, _ in done}
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat([f.assign(market=m) for m, f in frames.items()]).to_parquet(OUT / f"chain_calls_{window}.parquet")
    calls = {name: judge_calls(frames, MARKETS, lambda d, n=name: d[n].fillna(0).to_numpy()) for name in ARMS}
    cases = {}
    for case in ("WITH_PARENT", "TO_PARENT_POI"):
        r = judge_calls(frames, MARKETS, lambda d, k=case: np.where(d["case"].eq(k), d["H-K"].fillna(0), 0))
        cases[case] = r
    race = judge_race({m: r for m, _, r in done})
    months = month_interval(frames, lambda d: d["H-K"].fillna(0).to_numpy())
    return render(window, calls, race, cases, months)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    print(run(args.window, args.workers))


if __name__ == "__main__":
    main()
