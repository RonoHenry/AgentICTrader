"""The 2018-2024 search: H-N, the trader's M15 CRT entered at market on M1, managed with the partial
(docs/research/SEARCH_2018_2024.md).

- **The CRT:** C1 and C2 are consecutive M15 bars. A short: C2 trades above C1's high, not below its low, and closes
  below C1's high; a long, the mirror. A C2 that takes both sides is not traded.
- **Entry:** at market at C3's open, its first M1 bar: a buy pays the ask (the open plus the spread), a sell takes the
  bid. None when C3 opens from 16:00 to 18:00 New York.
- **Stop:** C2's extreme. The short's sits a spread above the high and triggers when the bid trades through the high
  (H-H's rule). A risk under two spreads is skipped.
- **Exits, each target its own trade:** 3R; 4R and 5R with a third off at 3R and the rest's stop to the fill from the
  next bar (the backtester's Requirement 28). The stop wins a bar that also reaches the partial or target; a bar
  opening beyond the stop exits at its open; the trading day's close (17:00 New York) exits what is open. Targets,
  the partial and break-even are read on the closing side (the bid for a long, the ask for a short).
- **Costs:** the bar's recorded spread or the market's median M1 spread in the window, whichever is larger.
- **Pass:** for a target, the mean R net is above zero, its trading-date interval at the Holm level for three
  targets (98.3%) is above zero, and it is positive in at least 6 of the 9 markets. H-N passes if one target does.

``session_trades`` gives Noculus the same trades on a session's own M1, each with its legs (context-engine
Requirement 31).

    python -m algo_research.search_crt --window develop
"""
from __future__ import annotations

import argparse
from typing import Optional

import numpy as np
import pandas as pd

from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT, RESAMPLES, SEED, SNAPSHOT

__all__ = ["TARGETS", "crt_signals", "judge", "m15_from_m1", "race", "session_trades", "trades"]

M1_SNAPSHOTS = {"develop": SNAPSHOT.parent / "mt5-m1-develop"}
WINDOWS = {"develop": ("2021-07-16", "2023-01-01"), "test": ("2023-01-01", "2025-01-01")}
TARGETS = (3.0, 4.0, 5.0)
PARTIAL_R, PARTIAL_SHARE = 3.0, 1 / 3
MIN_RISK_SPREADS, COST_FLOOR_SPREADS = 2.0, 10.0
LEVEL = 1 - 0.05 / len(TARGETS)
NY = "America/New_York"
NO_ENTRY = ("16:00", "18:00")
KILLZONES = (("02:00", "05:00"), ("07:00", "10:00"))
_M15 = pd.Timedelta(minutes=15)


def crt_signals(m15: pd.DataFrame) -> pd.DataFrame:
    """Every C2 that swept one side of C1 and closed back inside: C3's open, the side (+1 long), C2's extremes."""
    t, h, l, c = m15["time"], m15["high"], m15["low"], m15["close"]
    h1, l1 = h.shift(1), l.shift(1)
    consecutive = t.diff() == _M15
    short = consecutive & (h > h1) & (l >= l1) & (c < h1)
    long_ = consecutive & (l < l1) & (h <= h1) & (c > l1)
    picked = m15[short | long_]
    return pd.DataFrame({"c3": picked["time"] + _M15, "side": np.where(long_[short | long_], 1, -1),
                         "c2_high": picked["high"].to_numpy(float), "c2_low": picked["low"].to_numpy(float),
                         "c1_high": h1[short | long_].to_numpy(float), "c1_low": l1[short | long_].to_numpy(float),
                         "c2_close": picked["close"].to_numpy(float)})


def m15_from_m1(m1: pd.DataFrame) -> pd.DataFrame:
    """M15 bars from M1 (UTC quarter hours), only those whose fifteen minutes are all in the past of the last bar."""
    if m1.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    bars = m1.groupby(m1["time"].dt.floor("15min"), sort=True).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")).reset_index()
    return bars[bars["time"] + _M15 <= m1["time"].iloc[-1] + pd.Timedelta(minutes=1)].reset_index(drop=True)


class _Path:
    """One market's M1 arrays: bid prices, the spread paid, and each bar's trading-day end (17:00 New York)."""

    def __init__(self, m1: pd.DataFrame) -> None:
        self.t = m1["time"].to_numpy("datetime64[ns]")
        self.o, self.h, self.l, self.c = (m1[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.cost = np.maximum(m1["spread"].to_numpy(float), float(m1["spread"].median()))
        local = m1["time"].dt.tz_convert(NY).dt.tz_localize(None)
        day = (local - pd.Timedelta(hours=17)).dt.normalize().to_numpy("datetime64[ns]").astype("int64")
        self.day_end = np.searchsorted(day, day, side="right") - 1


def _first(mask: np.ndarray) -> Optional[int]:
    return int(np.argmax(mask)) if mask.any() else None


def race(p: _Path, side: int, e: int, trigger: float, legs: bool = False) -> Optional[dict]:
    """A market entry at bar ``e``'s open with its stop triggering at the bid level ``trigger``: R net and gross for
    each target, and whether 3R was reached. None when the risk is under two spreads. With ``legs``, each target's
    exits too: (share, price, bar index, kind), kind one of stop, partial, be, target, close."""
    end, s0 = int(p.day_end[e]), p.cost[e]
    o, h, l, c, cost = (a[e:end + 1] for a in (p.o, p.h, p.l, p.c, p.cost))
    if side > 0:
        fill, stop_exit = o[0] + s0, trigger
        risk = fill - trigger
        adverse, favourable, opening, close = l, h, o, c           # the bid closes a long
        stopped = l <= trigger
    else:
        fill, stop_exit = o[0], trigger + s0
        risk = stop_exit - fill
        adverse, favourable, opening, close = h + cost, l + cost, o + cost, c + cost
        stopped = h >= trigger
    if risk < MIN_RISK_SPREADS * s0:
        return None
    sign = side
    beyond = (lambda x, level: x <= level) if side > 0 else (lambda x, level: x >= level)   # the stop's side
    reach = (lambda x, level: x >= level) if side > 0 else (lambda x, level: x <= level)    # the target's side

    def stop_price(i: int, level: float) -> float:
        return opening[i] if i > 0 and beyond(opening[i], level) else level

    i_stop = _first(stopped)
    i_part = _first(reach(favourable, fill + sign * PARTIAL_R * risk))
    out = {"risk": risk, "risk_spreads": risk / s0 if s0 else np.inf, "reached_3r": i_part is not None and (i_stop is None or i_part < i_stop)}
    for k in TARGETS:
        target = fill + sign * k * risk
        i_tgt = _first(reach(favourable, target))
        if k <= PARTIAL_R:                                         # no partial at or beyond the target
            if i_stop is not None and (i_tgt is None or i_stop <= i_tgt):
                exits = [(1.0, stop_price(i_stop, stop_exit), i_stop, "stop")]
            elif i_tgt is not None:
                exits = [(1.0, target, i_tgt, "target")]
            else:
                exits = [(1.0, close[-1], len(close) - 1, "close")]
        elif i_stop is not None and (i_part is None or i_stop <= i_part):
            exits = [(1.0, stop_price(i_stop, stop_exit), i_stop, "stop")]
        elif i_part is None:
            exits = [(1.0, close[-1], len(close) - 1, "close")]
        else:
            part = (PARTIAL_SHARE, fill + sign * PARTIAL_R * risk, i_part, "partial")
            if i_tgt == i_part:
                rest = (1 - PARTIAL_SHARE, target, i_part, "target")
            else:
                j = i_part + 1
                i_be = _first(beyond(adverse[j:], fill))
                i_t2 = _first(reach(favourable[j:], target))
                if i_be is not None and (i_t2 is None or i_be <= i_t2):
                    rest = (1 - PARTIAL_SHARE, stop_price(j + i_be, fill), j + i_be, "be")
                elif i_t2 is not None:
                    rest = (1 - PARTIAL_SHARE, target, j + i_t2, "target")
                else:
                    rest = (1 - PARTIAL_SHARE, close[-1], len(close) - 1, "close")
            exits = [part, rest]
        net = sum(share * sign * (price - fill) for share, price, _, _ in exits) / risk
        # Gross: the same exits on bid prices, against the bid entry and the stop's bid level.
        ideal_risk = abs(o[0] - trigger)
        gross = (sum(share * sign * (price - (0.0 if side > 0 else cost[i]) - o[0]) for share, price, i, _ in exits)
                 / ideal_risk if ideal_risk else np.nan)
        out[f"net_{k:g}"], out[f"gross_{k:g}"] = float(net), float(gross)
        if legs:
            out[f"legs_{k:g}"] = [(share, float(price), e + i, kind) for share, price, i, kind in exits]
    return out


def _entries(m15: pd.DataFrame, p: _Path):
    """Each CRT that can be entered, with its New York clock and the index of C3's first M1 bar."""
    for s in crt_signals(m15).itertuples(index=False):
        clock = s.c3.tz_convert(NY).strftime("%H:%M")
        if NO_ENTRY[0] <= clock < NO_ENTRY[1]:
            continue
        e = int(np.searchsorted(p.t, s.c3.to_datetime64(), side="left"))
        if e >= len(p.t) or p.t[e] >= (s.c3 + _M15).to_datetime64():
            continue                                               # no M1 bar inside C3
        yield s, clock, e


def trades(m15: pd.DataFrame, m1: pd.DataFrame, market: str) -> pd.DataFrame:
    """H-N's trades in one market, each with its mirror: the same moment and risk, the other side."""
    p = _Path(m1)
    rows = []
    for s, clock, e in _entries(m15, p):
        trade = race(p, s.side, e, s.c2_low if s.side > 0 else s.c2_high)
        if trade is None:
            continue
        s0 = p.cost[e]
        # The other side's stop, at the same risk: a short's exits a spread above its trigger, a long's at it.
        mirror_trigger = p.o[e] + trade["risk"] - s0 if s.side > 0 else p.o[e] + s0 - trade["risk"]
        mirror = race(p, -s.side, e, mirror_trigger)
        local = s.c3.tz_convert(NY)
        rows.append({"market": market, "c3": s.c3, "date": (local - pd.Timedelta(hours=17)).normalize().tz_localize(None),
                     "clock": clock, "side": s.side, "killzone": any(a <= clock < b for a, b in KILLZONES), **trade,
                     **({f"mirror_{k}": v for k, v in mirror.items() if k.startswith("net_")} if mirror else {})})
    return pd.DataFrame(rows)


def session_trades(m1: pd.DataFrame) -> list[dict]:
    """H-N's trades on a stretch of M1 (time, open, high, low, close, spread), its M15 built from it: what Noculus
    draws. Each has C2's sweep, the fill, the stop, 1R, and per target its R net and exits (UTC times). An exit at
    the trading day's close is at the end of its bar; ``day_end`` is when that bar closes."""
    p = _Path(m1)
    minute = pd.Timedelta(minutes=1)
    times = pd.DatetimeIndex(m1["time"])
    out = []
    for s, _, e in _entries(m15_from_m1(m1), p):
        trade = race(p, s.side, e, s.c2_low if s.side > 0 else s.c2_high, legs=True)
        if trade is None:
            continue
        long_ = s.side > 0
        fill = p.o[e] + p.cost[e] if long_ else p.o[e]
        targets = {}
        for k in TARGETS:
            targets[f"{k:g}"] = {"net": trade[f"net_{k:g}"], "legs": [
                {"share": share, "price": price, "kind": kind,
                 "at": times[i] + (minute if kind == "close" else pd.Timedelta(0))}
                for share, price, i, kind in trade[f"legs_{k:g}"]]}
        out.append({"c2": s.c3 - _M15, "c3": s.c3, "side": int(s.side), "swept": s.c1_low if long_ else s.c1_high,
                    "c2_high": float(s.c2_high), "c2_low": float(s.c2_low), "c2_close": float(s.c2_close),
                    "extreme": s.c2_low if long_ else s.c2_high, "fill": float(fill),
                    "stop": float(fill - trade["risk"] if long_ else fill + trade["risk"]), "risk": float(trade["risk"]),
                    "reached_3r": bool(trade["reached_3r"]), "day_end": times[int(p.day_end[e])] + minute,
                    "targets": targets})
    return out


def _interval(keys: np.ndarray, values: np.ndarray, level: float) -> tuple[float, float]:
    """The ``level`` interval of the mean of ``values``, resampling the units in ``keys`` (search_d1's method)."""
    units, index = np.unique(keys, return_inverse=True)
    sums, counts = np.bincount(index, values, len(units)), np.bincount(index, minlength=len(units)).astype(float)
    weights = np.random.default_rng(SEED).multinomial(len(units), np.full(len(units), 1 / len(units)),
                                                      size=RESAMPLES).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = (weights @ sums) / (weights @ counts)
    tail = 100 * (1 - level) / 2
    lo, hi = np.percentile(draws[np.isfinite(draws)], [tail, 100 - tail])
    return float(lo), float(hi)


def judge(t: pd.DataFrame) -> dict:
    """Per target: the pass rule's numbers and the companions."""
    out = {}
    dates = t["date"].to_numpy()
    for k in TARGETS:
        net, gross = t[f"net_{k:g}"].to_numpy(float), t[f"gross_{k:g}"].to_numpy(float)
        lo, hi = _interval(dates, net, LEVEL)
        per = {m: (float(g[f"net_{k:g}"].mean()), len(g)) for m, g in t.groupby("market")}
        positive = sum(v > 0 for v, _ in per.values())
        paired = t.dropna(subset=[f"mirror_net_{k:g}"])
        floor = t[t["risk_spreads"] >= COST_FLOOR_SPREADS]
        out[k] = {"trades": len(t), "net": float(net.mean()), "lo": lo, "hi": hi, "gross": float(np.nanmean(gross)),
                  "win": float((net > 0).mean()), "per_market": per, "positive": positive,
                  "mirror": float(paired[f"mirror_net_{k:g}"].mean()),
                  "minus_mirror": float((paired[f"net_{k:g}"] - paired[f"mirror_net_{k:g}"]).mean()),
                  "floor": (float(floor[f"net_{k:g}"].mean()), float(floor[f"gross_{k:g}"].mean()), len(floor)),
                  "killzones": (float(t.loc[t["killzone"], f"net_{k:g}"].mean()), int(t["killzone"].sum())),
                  "passes": bool(net.mean() > 0 and lo > 0 and positive >= MIN_MARKETS)}
    return out


def render(window: str, t: pd.DataFrame, r: dict) -> str:
    since, until = WINDOWS[window]
    lines = [f"Window `{window}`: C3 opens {since} to {until}. {len(t):,} trades, {t['date'].nunique()} trading days; "
             f"3R reached before the stop on {t['reached_3r'].mean():.1%}; median risk {t['risk_spreads'].median():.1f} "
             f"spreads.", "",
             f"| Target | R net | {100 * LEVEL:.1f}% | R gross | Win | Mirror | Trade - mirror | Risk >= 10 spreads: net / gross (n) "
             f"| Killzones (n) | Markets > 0 | Passes |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, x in r.items():
        label = f"{k:g}R" + (" + partial" if k > PARTIAL_R else "")
        lines.append(f"| {label} | {x['net']:+.3f} | [{x['lo']:+.3f}, {x['hi']:+.3f}] | {x['gross']:+.3f} | {x['win']:.0%} | "
                     f"{x['mirror']:+.3f} | {x['minus_mirror']:+.3f} | {x['floor'][0]:+.3f} / {x['floor'][1]:+.3f} "
                     f"({x['floor'][2]:,}) | {x['killzones'][0]:+.3f} ({x['killzones'][1]:,}) | {x['positive']}/9 | "
                     f"{'yes' if x['passes'] else 'no'} |")
    lines += [""] + [f"R net per market, {k:g}R: " + ", ".join(f"{m} {v:+.3f} ({n:,})" for m, (v, n) in x["per_market"].items())
                     for k, x in r.items()]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(M1_SNAPSHOTS), required=True)
    args = parser.parse_args()
    since, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    parts = []
    for market in MARKETS:
        m15 = pd.read_parquet(SNAPSHOT / f"{market}_M15.parquet")
        m15 = m15[(m15["time"] >= since - _M15) & (m15["time"] < until)].reset_index(drop=True)
        m1 = pd.read_parquet(M1_SNAPSHOTS[args.window] / f"{market}_M1.parquet")
        m1 = m1[(m1["time"] >= since) & (m1["time"] < until + pd.Timedelta(days=1))].reset_index(drop=True)
        t = trades(m15, m1, market)
        parts.append(t[(t["c3"] >= since) & (t["c3"] < until)])
        print(f"{market}: {len(parts[-1]):,} trades", flush=True)
    t = pd.concat(parts, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_parquet(OUT / f"crt_{args.window}.parquet")
    print(render(args.window, t, judge(t)))


if __name__ == "__main__":
    main()
