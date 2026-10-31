"""Algo Mind's bench and third look (algo-mind Requirements 6, 7.3).

**The bench.** The same fit and judgment as H-Y, on markets that have no edge by construction: driftless random walks
with each market's own dates, daily volatility and day ranges. It shows:
- how often the judged thirds beat drift by as much as H-Y's +2.9 points by chance (the false alarms);
- with an effect planted (the week leaning up when it opens in the bottom third of its 26-week range, down in the
  top third), how often H-Y's pass rule finds it (the power).

**The third look.** Brain v1's calls on the weeks of 2026 its live senses can read, against those weeks' drift.
Information only: 2025-2026 has been studied, so it changes nothing (Requirement 7.3).

    python -m algo_mind bench --runs 20 [--plant 0.05] [--workers 4]
    python -m algo_mind third-look
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from algo_research.search_d1 import MARKETS
from algo_research.search_state import FIT_UNTIL, JUDGE, fit_and_call, judge, load, state_table

__all__ = ["H_Y_EXCESS", "bench", "live_states", "random_walk_days", "third_look"]

H_Y_EXCESS = 0.029
RANGE_WEEKS = 26


def random_walk_days(real: pd.DataFrame, seed: int, plant: float = 0.0) -> pd.DataFrame:
    """A driftless random walk on ``real``'s dates with its daily volatility and mean day range. With ``plant``, each
    week's days drift so that the week leans up by about ``plant`` (in probability) when it opens in the bottom third
    of the 26 weeks before it, and down in the top third."""
    rng = np.random.default_rng(seed)
    dates = pd.DatetimeIndex(real["date"])
    r = np.diff(np.log(real["close"].to_numpy(float)))
    sigma = float(np.std(r[np.isfinite(r)])) or 0.01
    span = float(np.median((real["high"] - real["low"]) / real["close"]))
    week = (dates - pd.to_timedelta(dates.dayofweek, unit="D")).to_numpy()
    starts = np.flatnonzero(np.r_[True, week[1:] != week[:-1]])
    n = len(dates)
    o, c, h, lo = (np.empty(n) for _ in range(4))
    price, wk_high, wk_low = 100.0, [], []
    # a week leaning up by `plant` needs a weekly drift of about plant * sqrt(2 pi) weekly sigmas; spread over its days
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else n
        drift = 0.0
        if plant and len(wk_high) >= RANGE_WEEKS:
            top, bottom = max(wk_high[-RANGE_WEEKS:]), min(wk_low[-RANGE_WEEKS:])
            pd_ = (price - bottom) / (top - bottom) if top > bottom else 0.5
            lean = 1 if pd_ < 1 / 3 else -1 if pd_ > 2 / 3 else 0
            drift = lean * plant * np.sqrt(2 * np.pi) * sigma * np.sqrt(e - s) / (e - s)
        hi_w, lo_w = -np.inf, np.inf
        for k in range(s, e):
            o[k] = price
            price = price * np.exp(drift + sigma * rng.standard_normal())
            c[k] = price
            wick = span * price * rng.uniform(0.2, 0.8, 2)
            h[k], lo[k] = max(o[k], c[k]) + wick[0] * 0.5, min(o[k], c[k]) - wick[1] * 0.5
            hi_w, lo_w = max(hi_w, h[k]), min(lo_w, lo[k])
        wk_high.append(hi_w)
        wk_low.append(lo_w)
    return pd.DataFrame({"date": dates, "open": o, "high": h, "low": lo, "close": c})


def _one(args: tuple[int, float]) -> dict:
    seed, plant = args
    parts = []
    for j, market in enumerate(MARKETS):
        days = random_walk_days(load(market), seed * 100 + j, plant)
        parts.append(state_table(market, days))
    t = pd.concat(parts, ignore_index=True)
    fit = t[t["week"] < FIT_UNTIL]
    judged = t[(t["week"] >= JUDGE[0]) & (t["week"] < JUDGE[1])]
    _, called, _ = fit_and_call(fit, judged, "gbm")
    r = judge(called)
    return {"seed": seed, "plant": plant, "excess": r["excess"], "lo": r["lo"], "positive": r["positive"],
            "passes": r["passes"], "hit": r["hit"]}


def bench(runs: int = 20, plant: float = 0.0, workers: int = 4) -> pd.DataFrame:
    """``runs`` fits and judgments on random walks (with ``plant``), in ``workers`` processes."""
    jobs = [(seed, plant) for seed in range(1, runs + 1)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return pd.DataFrame(list(pool.map(_one, jobs)))


def live_states(now: Optional[datetime] = None) -> pd.DataFrame:
    """Every market's whole weeks read by the live senses, from Yahoo since 2025, with their outcomes."""
    from algo_mind.sources import fetch_live, live_days

    now = now or datetime.now(timezone.utc)
    parts = []
    for market in MARKETS:
        days = live_days(fetch_live(market, now), market, now.date())
        t = state_table(market, days)
        parts.append(t[t["week"] + pd.Timedelta(days=5) <= pd.Timestamp(now.date())])   # whole weeks only
    return pd.concat(parts, ignore_index=True)


def third_look(version: str = "v1", now: Optional[datetime] = None) -> dict:
    """Brain ``version``'s calls on every week its live senses read whole, from Yahoo since 2025, judged as H-Y's."""
    from algo_mind.brain import load_version

    brain = load_version(version)
    t = live_states(now)
    called = brain.call(t)
    called = called.assign(every=np.where(called["p"] >= 0.5, 1, -1))
    return {"weeks": len(t), "first": str(t["week"].min().date()) if len(t) else None,
            "last": str(t["week"].max().date()) if len(t) else None, "thirds": judge(called),
            "every": judge(called, "every")}
