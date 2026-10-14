"""Scores for the blind replay (market-narrative Requirements 10.7 and 10.9).

A thesis is judged by delivery: did price reach the draw before the invalidation,
within the day? ``p_coin`` is what a driftless path would give from the same
distances, so a read only shows skill when its DRAW rate beats its mean p_coin.
A trade is filled where a bar's range holds the entry, then runs to its stop or
target (the stop winning any bar both touch), else it is marked to the close.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

__all__ = ["score_thesis", "score_trade", "summarize"]


def _first(mask: np.ndarray) -> Optional[int]:
    hits = np.flatnonzero(mask)
    return int(hits[0]) if hits.size else None


def score_thesis(read: dict, rows: pd.DataFrame, open_price: float, direction: Optional[str] = None) -> dict:
    """``rows``: the M1 bars from the read to the D1 close. ``direction``: the candle's (UP, DOWN, FLAT)."""
    bias = read["bias"]
    if bias == "NO_THESIS":
        return {"outcome": "NO_THESIS", "p_coin": None, "direction_right": None, "reached_at": None}
    bullish = bias == "BULLISH"
    draw, invalidation = float(read["draw"]), float(read["invalidation"])
    high, low = rows["high"].to_numpy(), rows["low"].to_numpy()
    a = _first(high >= draw if bullish else low <= draw)
    b = _first(low <= invalidation if bullish else high >= invalidation)
    if a is None and b is None:
        outcome, at = "NEITHER", None
    elif b is not None and (a is None or b <= a):
        outcome, at = "INVALIDATED", b
    else:
        outcome, at = "DRAW", a
    away, against = abs(draw - open_price), abs(open_price - invalidation)
    right = None if direction is None else direction == ("UP" if bullish else "DOWN")
    return {"outcome": outcome, "p_coin": against / (away + against), "direction_right": right,
            "reached_at": None if at is None else pd.Timestamp(rows["time"].iloc[at]).isoformat()}


def score_trade(trade: dict, rows: pd.DataFrame) -> dict:
    """``rows``: the M1 bars from the mark to the D1 close."""
    long = trade["direction"] == "LONG"
    entry, stop, target = float(trade["entry"]), float(trade["stop"]), float(trade["target"])
    risk = abs(entry - stop)
    high, low, close = rows["high"].to_numpy(), rows["low"].to_numpy(), rows["close"].to_numpy()
    fill = _first((low <= entry) & (entry <= high))
    if fill is None:
        return {"outcome": "NOT_FILLED", "r": None, "filled_at": None, "closed_at": None}
    for j in range(fill, len(rows)):
        if (low[j] <= stop) if long else (high[j] >= stop):
            outcome, r = "STOP", -1.0
        elif j > fill and ((high[j] >= target) if long else (low[j] <= target)):
            outcome, r = "TARGET", abs(target - entry) / risk
        else:
            continue
        return {"outcome": outcome, "r": r, "filled_at": pd.Timestamp(rows["time"].iloc[fill]).isoformat(),
                "closed_at": pd.Timestamp(rows["time"].iloc[j]).isoformat()}
    r = (close[-1] - entry) / risk * (1 if long else -1)
    return {"outcome": "OPEN", "r": float(r), "filled_at": pd.Timestamp(rows["time"].iloc[fill]).isoformat(),
            "closed_at": None}


def _interval(hits: Sequence[float], dates: Sequence[str], resamples: int = 4000, seed: int = 7) -> tuple:
    """95% bootstrap interval of the mean of ``hits``, resampling trading dates."""
    table = pd.DataFrame({"date": dates, "hit": hits}).groupby("date")["hit"].agg(["sum", "count"])
    if len(table) < 2:
        mean = float(np.mean(hits))
        return mean, mean
    idx = np.random.default_rng(seed).integers(0, len(table), size=(resamples, len(table)))
    means = table["sum"].to_numpy()[idx].sum(1) / table["count"].to_numpy()[idx].sum(1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize(records: Sequence[dict]) -> dict:
    """Requirement 10.9 over the revealed days."""
    days = [r for r in records if r.get("status") == "REVEALED"]
    thesis = [r for r in days if r["read"]["bias"] != "NO_THESIS"]
    hits = [1.0 if r["scores"]["thesis"]["outcome"] == "DRAW" else 0.0 for r in thesis]
    dates = [r["trading_date"] for r in thesis]
    known = [r["scores"]["thesis"]["direction_right"] for r in thesis
             if r["scores"]["thesis"]["direction_right"] is not None]
    trades = [t for r in days for t in r["scores"]["trades"] if t.get("r") is not None]
    rs = [float(t["r"]) for t in trades]
    return {
        "revealed": len(days),
        "thesis_days": len(thesis),
        "no_thesis_days": len(days) - len(thesis),
        "draw_rate": float(np.mean(hits)) if hits else None,
        "draw_interval": _interval(hits, dates) if hits else None,
        "mean_p_coin": float(np.mean([r["scores"]["thesis"]["p_coin"] for r in thesis])) if thesis else None,
        "direction_accuracy": float(np.mean(known)) if known else None,
        "trades": len(trades),
        "not_filled": sum(1 for r in days for t in r["scores"]["trades"] if t.get("outcome") == "NOT_FILLED"),
        "mean_r": float(np.mean(rs)) if rs else None,
        "total_r": float(np.sum(rs)) if rs else 0.0,
    }
