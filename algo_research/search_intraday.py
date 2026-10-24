"""The 2018-2024 search: its intraday effects, H-H and H-I (docs/research/SEARCH_2018_2024.md).

On the broker's M15 bars (bid prices), which start on 2021-07-16 (Amendment 1). Each index is read in its own cash
session, in its local time. A buy pays the bar's spread, or the market's median spread if that is larger.

- **H-H, the opening-range breakout:** the session's first M15 bar is the range. One closing above its open is
  bought at the next bar's open, with the stop at the range's low; one closing below its open is sold, with the stop
  at its high. Both stops trigger when the bid trades through the range's extreme: the long sells there, and the
  short buys there at the ask. The exit is the stop, or the cash close at the session's last bar's close. A bar
  opening beyond the stop exits at its open, and a trade whose risk is under two spreads is skipped. Pass: the mean
  R net of the spread is above zero with its 95% trading-date interval, positive in at least 4 of the 5 indices.
- **H-I, intraday momentum:** the move from the previous cash close (16:00 New York) to 10:00 calls the last
  half-hour (15:30-16:00) its way. Judged like the daily calls: the hit rate minus the share of that index's last
  half-hours that went the call's way. Pass: above zero with its interval, in at least 2 of the 3 indices.
- **H-J, the breakout with a cost floor:** H-H, traded only when the risk is at least 10 spreads (the spread costs at
  most a tenth of R). Derived from H-H's development run; its pass rule is H-H's.

    python -m algo_research.search_intraday --window develop
"""
from __future__ import annotations

import argparse
from typing import Optional

import numpy as np
import pandas as pd

from algo_research.search_d1 import OUT, SNAPSHOT, _interval

__all__ = ["COST_FLOOR_SPREADS", "SESSIONS", "WINDOWS", "momentum_calls", "orb_trades", "session_bars"]

#: index: (time zone, cash open, cash close), local time
SESSIONS = {"US100": ("America/New_York", "09:30", "16:00"), "US500": ("America/New_York", "09:30", "16:00"),
            "US30": ("America/New_York", "09:30", "16:00"), "GER40": ("Europe/Berlin", "09:00", "17:30"),
            "UK100": ("Europe/London", "08:00", "16:30")}
US = ("US100", "US500", "US30")
WINDOWS = {"develop": ("2021-07-16", "2023-01-01"), "test": ("2023-01-01", "2025-01-01")}
MIN_RISK_SPREADS = 2.0
COST_FLOOR_SPREADS = 10.0          # H-J


def session_bars(m15: pd.DataFrame, instrument: str) -> pd.DataFrame:
    """The index's M15 bars with their local date and clock (HH:MM of the open), and the spread a trade pays."""
    tz = SESSIONS[instrument][0]
    local = m15["time"].dt.tz_convert(tz)
    out = m15.copy()
    out["date"] = local.dt.tz_localize(None).dt.normalize()
    out["clock"] = local.dt.strftime("%H:%M")
    out["cost"] = np.maximum(m15["spread"].to_numpy(float), float(m15["spread"].median()))
    return out


def _orb_day(day: pd.DataFrame, opening: str, closing: str, min_risk: float) -> Optional[dict]:
    session = day[(day["clock"] >= opening) & (day["clock"] < closing)]
    if len(session) < 3 or session["clock"].iloc[0] != opening:
        return None
    rng, rest = session.iloc[0], session.iloc[1:]
    side = int(np.sign(rng["close"] - rng["open"]))
    if side == 0:
        return None
    spread = float(rest["cost"].iloc[0])
    o, h, l, c = (rest[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    if side > 0:
        entry, stop = o[0] + spread, float(rng["low"])
        risk = entry - stop
        hit = np.flatnonzero(l <= stop)
        exit_bid = (min(o[hit[0]], stop) if hit[0] > 0 else stop) if len(hit) else c[-1]
        net, gross = (exit_bid - entry) / risk, (exit_bid - o[0]) / (o[0] - stop) if o[0] > stop else np.nan
    else:
        entry, stop = o[0], float(rng["high"]) + spread
        risk = stop - entry
        hit = np.flatnonzero(h + spread >= stop)
        exit_ask = (max(o[hit[0]] + spread, stop) if hit[0] > 0 else stop) if len(hit) else c[-1] + spread
        net = (entry - exit_ask) / risk
        gross = (entry - (exit_ask - spread)) / (stop - spread - entry) if stop - spread > entry else np.nan
    if risk < min_risk * spread:
        return None
    return {"side": side, "net": float(net), "gross": float(gross), "stopped": bool(len(hit)),
            "risk_spreads": risk / spread}


def orb_trades(bars: pd.DataFrame, instrument: str, min_risk: float = MIN_RISK_SPREADS) -> pd.DataFrame:
    """The breakout's trades, one per session at most, skipping risks under ``min_risk`` spreads: date, side, R net
    and gross, stopped."""
    _, opening, closing = SESSIONS[instrument]
    rows = []
    for date, day in bars.groupby("date", sort=True):
        trade = _orb_day(day, opening, closing, min_risk)
        if trade is not None:
            rows.append({"market": instrument, "date": date, **trade})
    return pd.DataFrame(rows)


def momentum_calls(bars: pd.DataFrame, instrument: str) -> pd.DataFrame:
    """H-I's calls: the previous cash close to 10:00 calls 15:30-16:00 (New York)."""
    by_clock = bars.set_index(["date", "clock"])
    dates = bars["date"].drop_duplicates().sort_values().to_numpy()
    rows, prev_close = [], None
    for date in dates:
        def bar(clock):
            try:
                return by_clock.loc[(date, clock)]
            except KeyError:
                return None
        first, last_open, last_close = bar("09:45"), bar("15:30"), bar("15:45")
        if prev_close is not None and first is not None and last_open is not None and last_close is not None:
            call = int(np.sign(first["close"] - prev_close))
            move = last_close["close"] - last_open["open"]
            if call != 0 and move != 0:
                rows.append({"market": instrument, "date": date, "side": call, "move": int(np.sign(move)),
                             "bps": 1e4 * move / last_open["open"]})
        if last_close is not None:                          # a weekend or holiday keeps the last cash close
            prev_close = last_close["close"]
    return pd.DataFrame(rows)


def _window(t: pd.DataFrame, since, until) -> pd.DataFrame:
    return t[(t["date"] >= pd.Timestamp(since)) & (t["date"] < pd.Timestamp(until))].reset_index(drop=True)


def judge_orb(t: pd.DataFrame) -> dict:
    dates = t["date"].to_numpy()
    lo, hi = _interval(dates, t["net"].to_numpy())
    gross = t["gross"].dropna()
    glo, ghi = _interval(t.loc[gross.index, "date"].to_numpy(), gross.to_numpy())
    per = {m: (float(g["net"].mean()), len(g)) for m, g in t.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    sides = {("long" if s > 0 else "short"): (float(g["net"].mean()), len(g)) for s, g in t.groupby("side")}
    wins, losses = t.loc[t["net"] > 0, "net"].sum(), -t.loc[t["net"] < 0, "net"].sum()
    return {"trades": len(t), "net": float(t["net"].mean()), "lo": lo, "hi": hi, "gross": float(gross.mean()),
            "gross_lo": glo, "gross_hi": ghi, "win": float((t["net"] > 0).mean()),
            "pf": float(wins / losses) if losses else np.nan, "stopped": float(t["stopped"].mean()),
            "per_market": per, "positive": positive, "sides": sides,
            "passes": bool(t["net"].mean() > 0 and lo > 0 and positive >= 4)}


def judge_momentum(t: pd.DataFrame) -> dict:
    parts = []
    for market, g in t.groupby("market"):
        up = float((g["move"] > 0).mean())
        mean_bps = float(g["bps"].mean())
        parts.append(g.assign(hit=(g["move"] == g["side"]).astype(float),
                              base=np.where(g["side"] > 0, up, 1 - up),
                              edge_bps=g["side"] * g["bps"] - g["side"] * mean_bps))
    t = pd.concat(parts, ignore_index=True)
    excess = (t["hit"] - t["base"]).to_numpy()
    lo, hi = _interval(t["date"].to_numpy(), excess)
    blo, bhi = _interval(t["date"].to_numpy(), t["edge_bps"].to_numpy())
    per = {m: (float((g["hit"] - g["base"]).mean()), len(g)) for m, g in t.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    return {"calls": len(t), "hit": float(t["hit"].mean()), "base": float(t["base"].mean()),
            "excess": float(excess.mean()), "lo": lo, "hi": hi, "bps": float(t["edge_bps"].mean()),
            "bps_lo": blo, "bps_hi": bhi, "per_market": per, "positive": positive,
            "passes": bool(excess.mean() > 0 and lo > 0 and positive >= 2)}


def _orb_lines(title: str, r: dict) -> list[str]:
    return [f"**{title}:**", "",
            "| Trades | R net | 95% | R gross | 95% | Win | PF | Stopped | Long | Short | Indices > 0 | Passes |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
            f"| {r['trades']} | {r['net']:+.3f} | [{r['lo']:+.3f}, {r['hi']:+.3f}] | {r['gross']:+.3f} | "
            f"[{r['gross_lo']:+.3f}, {r['gross_hi']:+.3f}] | {r['win']:.0%} | {r['pf']:.2f} | {r['stopped']:.0%} | "
            f"{r['sides']['long'][0]:+.3f} ({r['sides']['long'][1]}) | {r['sides']['short'][0]:+.3f} "
            f"({r['sides']['short'][1]}) | {r['positive']}/5 | {'yes' if r['passes'] else 'no'} |", "",
            "R net per index: " + ", ".join(f"{m} {v:+.3f} ({n})" for m, (v, n) in r["per_market"].items()), ""]


def render(window: str, orbs: dict, mom: Optional[dict]) -> str:
    since, until = WINDOWS[window]
    lines = [f"Window `{window}`: sessions {since} to {until}.", ""]
    for title, r in orbs.items():
        lines += _orb_lines(title, r)
    if mom is not None:
        lines += ["**H-I, intraday momentum:**", "",
                  "| Calls | Hit | Base | Excess (pts) | 95% | Edge (bps) | 95% | Indices > 0 | Passes |",
                  "|---|---|---|---|---|---|---|---|---|",
                  f"| {mom['calls']} | {mom['hit']:.1%} | {mom['base']:.1%} | {100 * mom['excess']:+.1f} | "
                  f"[{100 * mom['lo']:+.1f}, {100 * mom['hi']:+.1f}] | {mom['bps']:+.2f} | [{mom['bps_lo']:+.2f}, "
                  f"{mom['bps_hi']:+.2f}] | {mom['positive']}/3 | {'yes' if mom['passes'] else 'no'} |", "",
                  "Excess per index: " + ", ".join(f"{m} {100 * v:+.1f} ({n})" for m, (v, n) in mom["per_market"].items())]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    parser.add_argument("--hypotheses", default="H-H,H-I,H-J",
                        help="the test window reads only the hypotheses that passed development")
    args = parser.parse_args()
    since, until = WINDOWS[args.window]
    chosen = {h.strip() for h in args.hypotheses.split(",")}
    floors = {name: floor for name, floor in (("H-H", MIN_RISK_SPREADS), ("H-J", COST_FLOOR_SPREADS)) if name in chosen}
    trades, calls = {name: [] for name in floors}, []
    for instrument in SESSIONS:
        m15 = pd.read_parquet(SNAPSHOT / f"{instrument}_M15.parquet")
        start, end = pd.Timestamp(since, tz="UTC") - pd.Timedelta(days=7), pd.Timestamp(until, tz="UTC") + pd.Timedelta(days=1)
        m15 = m15[(m15["time"] >= start) & (m15["time"] < end)].reset_index(drop=True)   # a week before: the first close
        bars = session_bars(m15, instrument)
        for name, floor in floors.items():
            trades[name].append(_window(orb_trades(bars, instrument, floor), since, until))
        if "H-I" in chosen and instrument in US:
            calls.append(_window(momentum_calls(bars, instrument), since, until))
    OUT.mkdir(parents=True, exist_ok=True)
    titles = {"H-H": "H-H, the opening-range breakout", "H-J": "H-J, the breakout with a cost floor (risk >= 10 spreads)"}
    orbs = {}
    for name, parts in trades.items():
        t = pd.concat(parts, ignore_index=True)
        t.to_parquet(OUT / f"orb_{name[-1].lower()}_{args.window}.parquet")
        orbs[titles[name]] = judge_orb(t)
    mom = None
    if calls:
        c = pd.concat(calls, ignore_index=True)
        c.to_parquet(OUT / f"momentum_{args.window}.parquet")
        mom = judge_momentum(c)
    print(render(args.window, orbs, mom))


if __name__ == "__main__":
    main()
