"""The M1 sweep model without a bias (2026-10-30): every M1 sweep of the day's M5 swings that changes the state of
delivery within 20 minutes, on both sides, at market for a fixed 2R. Noculus draws it as the "Sweep M1" layer.

- **Pools:** the trading day's M5 three-candle swing highs and lows (the day runs 17:00 to 17:00 New York). Each is live
  from the close of the candle after it until a sweep takes it.
- **Sweep:** an M1 bar trading through one or more live pools (a long's below a low). The extreme then follows price
  while it makes a new low within 20 minutes of the last, taking any further pools on the way.
- **CISD:** the first M1 close above the open of the run of down-closes into the extreme (the extreme's own open
  when there is no run), within 20 minutes of the extreme. Without one the sweep is dropped.
- **Entry:** at market at the next M1 bar's open; a buy pays the ask. None from 16:00 to 18:00 New York.
- **Stop:** the extreme, by H-N's rule: the short's triggers when the bid trades through the high and exits a spread
  above it. A risk under two spreads is skipped.
- **Exit:** 2R or the stop, whichever comes first (the stop wins a bar that does both); else the trading day's close.
- **Costs:** H-N's, the bar's spread or the market's median, whichever is larger.

No bias: the two sides are read apart, so a long and a short can be open together. Each trade carries its mirror (the
other side at the same moment with the same risk), the control a trade with no direction should only match.

This is the rule the trader's four gold trades of 13-14 Apr 2025 fell among (2026-10-22: ~45 signals a day per
market on the 2025 exploration slice; at 5R, -0.27R a trade against -0.30R for the mirror).

    python -m algo_research.sweep_m1 --window develop      # the rule's numbers on a window
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_crt import M1_SNAPSHOTS, NO_ENTRY, NY, _interval, _Path, race
from algo_research.search_d1 import MARKETS, SNAPSHOT

__all__ = ["TARGET", "session_trades", "signals", "trades"]

TARGET = 2.0
WINDOW = np.timedelta64(20, "m")
_M5 = np.timedelta64(5, "m").astype("timedelta64[ns]").astype("int64")
# The windows this may read: H-N's development window and the 2025 exploration slice; never the 2023-2024 test window.
WINDOWS = {"develop": ("2021-07-16", "2023-01-01"), "explore": ("2025-01-01", "2025-07-01")}
SNAPSHOTS = {**M1_SNAPSHOTS, "explore": SNAPSHOT.parent / "focus-2025-2026h1"}


def _pools(t: np.ndarray, low: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The M5 three-candle swing lows of one day's M1: price, the swing candle's open, and when it is known (the close
    of the candle after it). ``t`` in int64 nanoseconds."""
    starts, first = np.unique(t - t % _M5, return_index=True)
    lo = np.minimum.reduceat(low, first)
    k = np.arange(1, len(lo) - 1)
    k = k[(lo[k] < lo[k - 1]) & (lo[k] < lo[k + 1])]
    return lo[k], starts[k], starts[k + 1] + _M5


def _day(t: np.ndarray, o: np.ndarray, l: np.ndarray, c: np.ndarray) -> list[tuple[int, int, int, float, list[int]]]:
    """A long's signals in one day of oriented prices (a short's come in negated, its highs as lows): the sweep bar,
    the extreme's bar, the CISD bar, the CISD level and the pools taken. A signal, once fired, is kept whatever price
    does next; the search resumes after its CISD (or after the window, when none came)."""
    px, _, known = _pools(t, l)
    taken = np.zeros(len(px), bool)
    window = WINDOW.astype("timedelta64[ns]").astype("int64")
    n, i, out = len(l), 0, []
    while i < n:
        live = ~taken & (known <= t[i]) & (l[i] < px)
        if not live.any():
            i += 1
            continue
        took = list(np.flatnonzero(live))
        taken |= live
        ext_i, j, cisd, level = i, i, None, np.nan
        while j + 1 < n and t[j + 1] - t[ext_i] <= window:
            j += 1
            if l[j] < l[ext_i]:                                    # a new extreme: the window restarts from it
                ext_i = j
                more = ~taken & (known <= t[j]) & (l[j] < px)
                took += list(np.flatnonzero(more))
                taken |= more
                continue
            k = ext_i
            while k > 0 and c[k - 1] < o[k - 1]:                   # back over the run of down-closes into it
                k -= 1
            if c[j] > o[k]:
                cisd, level = j, o[k]
                break
        if cisd is None:
            i = j + 1
            continue
        out.append((i, ext_i, cisd, float(level), took))
        i = cisd + 1
    return out


def signals(m1: pd.DataFrame, p: _Path | None = None) -> list[dict]:
    """Every signal on a stretch of M1 (time, open, high, low, close), both sides: the side (+1 long), the bar
    indexes of the sweep, the extreme, the CISD and the entry (the next bar), the extreme, the CISD level and the
    pools taken (price and swing candle's open)."""
    p = p or _Path(m1.assign(spread=m1["spread"] if "spread" in m1 else 0.0))
    t = p.t.astype("int64")
    out = []
    for end in np.unique(p.day_end):
        a = int(np.searchsorted(p.day_end, end, side="left"))
        b = int(end) + 1
        for side in (1, -1):
            if side > 0:
                o, l, c = p.o[a:b], p.l[a:b], p.c[a:b]
            else:
                o, l, c = -p.o[a:b], -p.h[a:b], -p.c[a:b]
            px, at, _ = _pools(t[a:b], l)
            for i, x, j, level, took in _day(t[a:b], o, l, c):
                if a + j + 1 >= b:
                    continue                                       # the CISD closed the day
                out.append({"side": side, "sweep": a + i, "extreme_i": a + x, "cisd": a + j, "entry": a + j + 1,
                            "extreme": float(side * l[x]), "level": float(side * level),
                            "pools": [(float(side * px[q]), int(at[q])) for q in took]})
    out.sort(key=lambda s: (s["entry"], -s["side"]))
    return out


def _entries(m1: pd.DataFrame, p: _Path):
    """Each signal whose entry bar opens outside 16:00-18:00 New York."""
    clock = m1["time"].dt.tz_convert(NY).dt.strftime("%H:%M").to_numpy()
    for s in signals(m1, p):
        if not NO_ENTRY[0] <= clock[s["entry"]] < NO_ENTRY[1]:
            yield s, clock[s["entry"]]


def _mirror(p: _Path, s: dict, trade: dict) -> dict:
    """The other side at the same bar with the same risk (H-N's mirror)."""
    e, s0 = s["entry"], p.cost[s["entry"]]
    trigger = p.o[e] + trade["risk"] - s0 if s["side"] > 0 else p.o[e] + s0 - trade["risk"]
    return race(p, -s["side"], e, trigger, targets=(TARGET,)) or {}


def trades(m1: pd.DataFrame, market: str) -> pd.DataFrame:
    """The rule's trades in one market (M1 with its spread), each with its mirror."""
    p = _Path(m1)
    rows = []
    for s, clock in _entries(m1, p):
        e = s["entry"]
        trade = race(p, s["side"], e, s["extreme"], targets=(TARGET,))
        if trade is None:
            continue
        mirror = _mirror(p, s, trade)
        when = m1["time"].iloc[e]
        rows.append({"market": market, "entry": when, "clock": clock, "side": s["side"], "pools": len(s["pools"]),
                     "date": (when.tz_convert(NY) - pd.Timedelta(hours=17)).normalize().tz_localize(None),
                     "risk": trade["risk"], "risk_spreads": trade["risk_spreads"],
                     "net": trade[f"net_{TARGET:g}"], "gross": trade[f"gross_{TARGET:g}"],
                     "mirror": mirror.get(f"net_{TARGET:g}", np.nan)})
    return pd.DataFrame(rows)


def session_trades(m1: pd.DataFrame) -> list[dict]:
    """The rule's trades on a stretch of M1 (time, open, high, low, close, spread): what Noculus draws. Each has the
    pools swept, the extreme, the CISD, the fill, the stop and its exits at 2R, and its mirror's R (UTC times). An
    exit at the trading day's close is at the end of its bar; ``day_end`` is when that bar closes."""
    p = _Path(m1)
    minute = pd.Timedelta(minutes=1)
    times = pd.DatetimeIndex(m1["time"])
    out = []
    for s, _ in _entries(m1, p):
        e, long_ = s["entry"], s["side"] > 0
        trade = race(p, s["side"], e, s["extreme"], legs=True, targets=(TARGET,))
        if trade is None:
            continue
        fill = p.o[e] + p.cost[e] if long_ else p.o[e]
        legs = [{"share": share, "price": price, "kind": kind,
                 "at": times[i] + (minute if kind == "close" else pd.Timedelta(0))}
                for share, price, i, kind in trade[f"legs_{TARGET:g}"]]
        out.append({"side": int(s["side"]), "sweep": times[s["sweep"]], "extreme_at": times[s["extreme_i"]],
                    "cisd": times[s["cisd"]], "entry": times[e], "extreme": s["extreme"], "level": s["level"],
                    "pools": [{"price": px, "at": pd.Timestamp(at, tz="UTC")} for px, at in s["pools"]],
                    "fill": float(fill), "stop": float(fill - trade["risk"] if long_ else fill + trade["risk"]),
                    "risk": float(trade["risk"]), "net": trade[f"net_{TARGET:g}"], "legs": legs,
                    "mirror": _mirror(p, s, trade).get(f"net_{TARGET:g}"),
                    "day_end": times[int(p.day_end[e])] + minute})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    args = parser.parse_args()
    since, until = (pd.Timestamp(x, tz="UTC") for x in WINDOWS[args.window])
    parts = []
    for market in MARKETS:
        m1 = pd.read_parquet(SNAPSHOTS[args.window] / f"{market}_M1.parquet")
        m1 = m1[(m1["time"] >= since - pd.Timedelta(days=1)) & (m1["time"] < until + pd.Timedelta(days=1))]
        t = trades(m1.reset_index(drop=True), market)
        parts.append(t[(t["entry"] >= since) & (t["entry"] < until)])
        print(f"{market}: {len(parts[-1]):,} trades", flush=True)
    t = pd.concat(parts, ignore_index=True)
    lo, hi = _interval(t["date"].to_numpy(), t["net"].to_numpy(float), 0.95)
    days = t.groupby("market")["date"].nunique().sum()
    print(f"\n{args.window} {since:%Y-%m-%d} to {until:%Y-%m-%d}: {len(t):,} trades, {len(t) / days:.1f} a day per market, "
          f"median risk {t['risk_spreads'].median():.1f} spreads")
    print(f"2R reached before the stop {(t['net'] >= TARGET - 1e-9).mean():.1%} (a driftless walk: 33.3%)")
    print(f"R net {t['net'].mean():+.3f} [{lo:+.3f}, {hi:+.3f}], gross {t['gross'].mean():+.3f}, "
          f"mirror net {t['mirror'].mean():+.3f}, trade - mirror {(t['net'] - t['mirror']).mean():+.3f}")
    floor = t[t["risk_spreads"] >= 10]
    print(f"risk >= 10 spreads: {len(floor):,} trades, net {floor['net'].mean():+.3f}, gross {floor['gross'].mean():+.3f}")
    print("per market: " + ", ".join(f"{m} {g['net'].mean():+.3f} ({len(g):,})" for m, g in t.groupby("market")))


if __name__ == "__main__":
    main()
