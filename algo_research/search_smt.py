"""The 2018-2024 search: SMT divergence at a major array calls the next D1 candle, H-L (docs/research/
SEARCH_2018_2024.md; context-engine Requirement 29).

The trader's rule (2026-10-24): SMT is confluence, read only where price meets a major institutional array. On the
broker's D1 bars with Sunday merged into Monday (Amendment 1), for the pairs EURUSD-GBPUSD, US100-US500-US30 (each
pair) and the dollar index inverse to EURUSD, GBPUSD and gold:
- **Bullish SMT** on a day: one leg trades below its previous day's low while its partner holds above its own (the
  dollar index, inverse, holds below its previous day's high). Bearish is the mirror.
- **A leg is called** for the next D1 candle, its side of the divergence, only when its own day is at a major array,
  any one of:
  a. it traded into an unfilled D1 order block or breaker of that side;
  b. it took a major pool on the other side: the previous week's extreme, an untaken D1 swing (two candles each
     side), or the 20-day extreme (which the 40 and 60-day extremes lie beyond);
  c. it closed in the outer 25% of its W1 dealing range (the bottom for bullish).
  A market called both ways on one day is not called. (No H4 arrays: the broker has no H4 before July 2021.)

Judged as the search's daily calls (``search_calls.judge_calls``), over the seven paired markets. Companions: SMT
with no gate, each gate alone, the leg that swept against the one that held, and the calls H-K agreed with.

    python -m algo_research.search_smt --window develop
"""
from __future__ import annotations

import argparse
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from algo_research.search_calls import _window, daily_signals, judge_calls
from algo_research.search_chain import Ladder, periods
from algo_research.search_d1 import OUT, SNAPSHOT, WINDOWS, merge_sundays
from liquidity_engine.context.frame_state import dealing_range
from liquidity_engine.context.measures import bearish_breakers, bearish_order_blocks, mirror, swing_highs, swing_lows

__all__ = ["ARMS", "PAIRS", "SMT_MARKETS", "arm_calls", "market_days", "smt_legs"]

SMT_MARKETS = ("DXY", "EURUSD", "GBPUSD", "XAUUSD", "US100", "US500", "US30")
#: (a, b, +1 moving together / -1 inversely)
PAIRS: Tuple[Tuple[str, str, int], ...] = (
    ("EURUSD", "GBPUSD", 1), ("US100", "US500", 1), ("US100", "US30", 1), ("US500", "US30", 1),
    ("DXY", "EURUSD", -1), ("DXY", "GBPUSD", -1), ("DXY", "XAUUSD", -1))
EXTREME = 0.25
RANGE_DAYS = 20

ARMS: Dict[str, str] = {
    "H-L": "SMT at a major array (any gate)",
    "smt-all": "SMT with no gate",
    "gate-a": "SMT at an unfilled D1 order block or breaker",
    "gate-b": "SMT that took a major pool",
    "gate-c": "SMT in the outer 25% of the W1 range",
    "swept": "H-L, the leg that took its level",
    "held": "H-L, the leg that held",
    "with-H-K": "H-L where H-K called the same side",
}


# ── each market's days ─────────────────────────────────────────────────────

def _first_touches(n: int, zones, touched) -> np.ndarray:
    """Days on which an array is first traded into after it formed: (low, high, formed index) zones, and
    ``touched(day, low, high)``."""
    out = np.zeros(n, bool)
    for low, high, formed in zones:
        for d in range(formed + 1, n):
            if touched(d, low, high):
                out[d] = True
                break
    return out


def _swing_taken(extreme: np.ndarray, side: int) -> np.ndarray:
    """Days that trade beyond an untaken swing (two candles each side) confirmed by the day before: below a swing
    low for side +1 (bullish SMT), above a swing high for -1."""
    n = len(extreme)
    swings = set(swing_lows(extreme) if side > 0 else swing_highs(extreme))
    live: List[float] = []
    out = np.zeros(n, bool)
    for d in range(n):
        s = d - 3                                        # confirmed at s + 2 = d - 1
        if s in swings:
            live.append(float(extreme[s]))
        if live:
            beyond = [p for p in live if (extreme[d] < p if side > 0 else extreme[d] > p)]
            out[d] = bool(beyond)
            live = [p for p in live if p not in beyond]
    return out


def market_days(bars: pd.DataFrame) -> pd.DataFrame:
    """Per D1 bar: whether it took the previous day's low and high, and each gate for each side, read from the
    bars to it only."""
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(bars)
    out = pd.DataFrame({"date": pd.DatetimeIndex(bars["time"]).normalize()})
    out["took_low"] = np.r_[False, l[1:] < l[:-1]]
    out["took_high"] = np.r_[False, h[1:] > h[:-1]]

    bull_zones = [(-hi, -lo, i) for _j, i, lo, hi in bearish_order_blocks(*mirror(o, h, l, c))]
    bull_zones += [(-hi, -lo, k) for k, lo, hi in bearish_breakers(*mirror(o, h, l, c))]
    bear_zones = [(lo, hi, i) for _j, i, lo, hi in bearish_order_blocks(o, h, l, c)]
    bear_zones += [(lo, hi, k) for k, lo, hi in bearish_breakers(o, h, l, c)]
    out["a_bull"] = _first_touches(n, bull_zones, lambda d, lo, hi: l[d] <= hi)
    out["a_bear"] = _first_touches(n, bear_zones, lambda d, lo, hi: h[d] >= lo)

    p = periods(bars["time"])
    week = p["week"]
    first = np.r_[0, np.flatnonzero(np.diff(week)) + 1]
    week_low = np.minimum.reduceat(l, first)
    week_high = np.maximum.reduceat(h, first)
    prev = week - 1
    pwl = np.where(prev >= 0, week_low[np.maximum(prev, 0)], np.nan)
    pwh = np.where(prev >= 0, week_high[np.maximum(prev, 0)], np.nan)
    low20 = pd.Series(l).shift(1).rolling(RANGE_DAYS).min().to_numpy()
    high20 = pd.Series(h).shift(1).rolling(RANGE_DAYS).max().to_numpy()
    with np.errstate(invalid="ignore"):
        out["b_bull"] = (l < pwl) | (l < low20) | _swing_taken(l, 1)
        out["b_bear"] = (h > pwh) | (h > high20) | _swing_taken(h, -1)

    ladder = Ladder(bars)
    position = np.full(n, np.nan)
    for d in range(n):
        _days, weeks, _months, forming, _m = ladder.at(d)
        rng = dealing_range(weeks.h, weeks.l, len(weeks), *(forming or (None, None)))
        if rng is not None and rng.high > rng.low:
            position[d] = rng.position(c[d])
    out["c_bull"] = position <= EXTREME
    out["c_bear"] = position >= 1 - EXTREME
    return out


# ── the divergences and the calls ──────────────────────────────────────────

def smt_legs(days: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Every leg of every divergence: (market, date, side, swept, gate_a, gate_b, gate_c)."""
    rows = []
    for a, b, sign in PAIRS:
        if a not in days or b not in days:
            continue
        both = days[a].merge(days[b], on="date", suffixes=("_a", "_b"))
        for side in (1, -1):
            a_took = both["took_low_a" if side > 0 else "took_high_a"]
            b_key = ("took_low_b" if side > 0 else "took_high_b") if sign > 0 else \
                ("took_high_b" if side > 0 else "took_low_b")
            b_took = both[b_key]
            hit = (a_took ^ b_took).to_numpy()
            for market, suffix, leg_side, took in ((a, "_a", side, a_took), (b, "_b", side * sign, b_took)):
                g = "bull" if leg_side > 0 else "bear"
                picked = both[hit]
                rows.append(pd.DataFrame({
                    "market": market, "date": picked["date"].to_numpy(), "side": leg_side,
                    "swept": took[hit].to_numpy(), "gate_a": picked[f"a_{g}{suffix}"].to_numpy(),
                    "gate_b": picked[f"b_{g}{suffix}"].to_numpy(), "gate_c": picked[f"c_{g}{suffix}"].to_numpy()}))
    rows = [r for r in rows if len(r)]
    cols = ["market", "date", "side", "swept", "gate_a", "gate_b", "gate_c"]
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=cols)


def arm_calls(legs: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    """The legs in ``mask`` as calls, one per market and day; a market called both ways that day is dropped."""
    picked = legs[mask.to_numpy(bool)]
    sides = picked.groupby(["market", "date"])["side"].agg(["min", "max"]).reset_index()
    agreed = sides[sides["min"] == sides["max"]]
    return agreed.rename(columns={"min": "side"})[["market", "date", "side"]]


def _arm_masks(legs: pd.DataFrame) -> Dict[str, pd.Series]:
    gated = legs["gate_a"] | legs["gate_b"] | legs["gate_c"]
    return {"H-L": gated, "smt-all": pd.Series(True, index=legs.index), "gate-a": legs["gate_a"],
            "gate-b": legs["gate_b"], "gate-c": legs["gate_c"], "swept": gated & legs["swept"],
            "held": gated & ~legs["swept"]}


# ── the run ────────────────────────────────────────────────────────────────

def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def run(window: str) -> str:
    since, until = WINDOWS[window]
    bars = {}
    for m in SMT_MARKETS:
        b = merge_sundays(pd.read_parquet(SNAPSHOT / f"{m}_D1.parquet"))
        bars[m] = b[b["time"] < pd.Timestamp(until, tz="UTC")].reset_index(drop=True)
    days = {m: market_days(b) for m, b in bars.items()}
    legs = smt_legs(days)
    frames = {m: daily_signals(b).assign(date=lambda d: pd.DatetimeIndex(d["time"]).normalize())
              for m, b in bars.items()}
    for arm, mask in _arm_masks(legs).items():
        calls = arm_calls(legs, mask)
        for m in frames:
            side = calls[calls["market"] == m].set_index("date")["side"]
            frames[m][arm] = frames[m]["date"].map(side).fillna(0).astype(int).to_numpy()
    chain = pd.read_parquet(OUT / f"chain_calls_{window}.parquet", columns=["market", "time", "H-K"])
    for m in frames:
        hk = chain[chain["market"] == m].set_index("time")["H-K"]
        agree = frames[m]["time"].map(hk).fillna(0).to_numpy() == frames[m]["H-L"].to_numpy()
        frames[m]["with-H-K"] = np.where(agree, frames[m]["H-L"], 0)
    windowed = {m: _window(f, since, until) for m, f in frames.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat([f.assign(market=m) for m, f in windowed.items()]).to_parquet(OUT / f"smt_calls_{window}.parquet")
    lines = [f"Window `{window}`: calls for D1 candles opening {since} to {until}.", "",
             "| | Calls | Hit | Base | Excess (pts) | 95% | Markets > 0 | Body (ranges) | Passes |",
             "|---|---|---|---|---|---|---|---|---|"]
    results = {}
    for arm, label in ARMS.items():
        r = judge_calls(windowed, SMT_MARKETS, lambda d, a=arm: d[a].to_numpy())
        results[arm] = r
        passes = ("yes" if r["passes"] else "no") if arm == "H-L" else "–"
        lines.append(f"| {arm}: {label} | {r['calls']} | {r['hit']:.1%} | {r['base']:.1%} | {_pts(r['excess'])} | "
                     f"[{_pts(r['lo'])}, {_pts(r['hi'])}] | {r['positive']}/{len(r['per_market'])} "
                     f"(need {r['need']}) | {r['body']:+.3f} | {passes} |")
    per = results["H-L"]["per_market"]
    lines += ["", "H-L's excess per market, points (calls):", "", "| " + " | ".join(per) + " |",
              "|" + "---|" * len(per), "| " + " | ".join(f"{_pts(v)} ({k})" for v, k in per.values()) + " |"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    print(run(parser.parse_args().window))


if __name__ == "__main__":
    main()
