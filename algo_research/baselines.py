"""Baselines: what a statistic would be without the information under test.

Every number is shown next to what chance and simple rules give, so that
information can be told apart from trend, time-of-day volatility and the
arcsine law (Requirement 10). Each baseline yields, per event, a sum and a
count, which the day bootstrap (stats.py) pairs with the event's own value.

| Baseline | Measures | Per event |
|---|---|---|
| ``coin_flip`` | race | ``p_coin``: a driftless path's chance of the target first, from the closing-side price at entry. Analytic. |
| ``random_time`` | race, direction, move | K draws: same instrument and New York 15-minute slot, other trading dates of the same slice with no event for that instrument. Draws keep the event's direction, and its stop and target distances in ``atr_d1`` units, rescaled by the drawn row's ``atr_d1``. |
| ``naive:<rule>`` | direction | ``always_long``, ``prev_day_dir``, ``w1_trend``, ``side_d1_open`` or ``side_midnight_open`` on the event's row. An abstaining rule scores 0.5. |
| ``stratified`` | rate | The rate among the slice's rows in the same decile of distance to the level (in ``atr_d1``, deciles over those rows) and the same New York hour, for the event's cell. |
| ``shuffled_path`` | rate (timing) | Each date's M15 bars in shuffled order, the open and close kept, the statistic recomputed; averaged over the shuffles. |

The shuffle moves whole M15 bars: each keeps its move from the previous close
and its high and low relative to it, and takes the time slot (and so the H4
candle) it lands in. Unshuffled, it gives back the candle labels exactly.

Draws are reproducible: their generator is seeded from the hypothesis hash
(stats.seed_from) by the caller (Req 10.6).

Validates: Requirements 10.1-10.6, 13.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd

from algo_research.events import direction_of
from algo_research.filters import Filter
from algo_research.frame import InstrumentFrame, calendar_columns, ny_instant
from liquidity_engine.models import Timeframe

__all__ = ["NAIVE", "RandomTimeDraws", "coin_flip", "naive_direction", "random_time_draws", "rescale_orders",
           "shuffled_path", "stratified"]

NAIVE = ("always_long", "prev_day_dir", "w1_trend", "side_d1_open", "side_midnight_open")


def coin_flip(races: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per race: its ``p_coin``; REJECTED races count nothing."""
    ok = (races["outcome"] != "REJECTED").to_numpy()
    return np.where(ok, races["p_coin"].to_numpy(dtype=float), 0.0), ok.astype(float)


# ── random time ────────────────────────────────────────────────────────────

@dataclass
class RandomTimeDraws:
    rows: pd.DataFrame          # event (its position in the events table), row (the drawn feature row), direction
    available: np.ndarray       # per event: how many were drawn (K, or fewer when the pool is smaller)


def random_time_draws(features: pd.DataFrame, events: pd.DataFrame, k: int,
                      rng: np.random.Generator) -> RandomTimeDraws:
    """K feature rows per event from the same instrument, New York 15-minute slot
    and slice, on trading dates without an event for that instrument."""
    slot = features[["instrument", "ny_minute", "slice"]].reset_index(drop=True)
    pools = slot.groupby(["instrument", "ny_minute", "slice"]).indices         # positions per slot
    labels = features.index.to_numpy()
    dates = features["trading_date"].to_numpy(dtype="datetime64[ns]")
    event_dates: dict[str, np.ndarray] = {
        instrument: np.unique(part.to_numpy(dtype="datetime64[ns]"))
        for instrument, part in events.groupby("instrument")["trading_date"]}
    rows, available = [], np.zeros(len(events), dtype=int)
    for i, (row, direction) in enumerate(zip(events["row"].to_numpy(), events["direction"].to_numpy())):
        source = features.loc[row]
        pool = pools.get((source["instrument"], source["ny_minute"], source["slice"]), np.array([], dtype=int))
        pool = pool[~np.isin(dates[pool], event_dates.get(source["instrument"], []))]
        chosen = np.sort(rng.choice(pool, size=min(k, len(pool)), replace=False)) if len(pool) else pool
        available[i] = len(chosen)
        rows.extend((i, int(labels[position]), direction) for position in chosen)
    return RandomTimeDraws(pd.DataFrame(rows, columns=["event", "row", "direction"]), available)


def rescale_orders(features: pd.DataFrame, events: pd.DataFrame, trades: pd.DataFrame, draws: pd.DataFrame,
                   time_limit: Union[str, Mapping[str, int]]) -> pd.DataFrame:
    """Race orders for the draws: each event's stop and target distances from its
    row's close, in its row's atr_d1, laid off the drawn row's close in the drawn
    row's atr_d1."""
    event_rows = features.loc[events["row"].to_numpy()]
    close_e = event_rows["close"].to_numpy(dtype=float)
    atr_e = event_rows["atr_d1"].to_numpy(dtype=float)
    stop_atr = (trades["stop"].to_numpy(dtype=float) - close_e) / atr_e
    target_atr = (trades["target"].to_numpy(dtype=float) - close_e) / atr_e
    drawn = features.loc[draws["row"].to_numpy()]
    which = draws["event"].to_numpy()
    close_d, atr_d = drawn["close"].to_numpy(dtype=float), drawn["atr_d1"].to_numpy(dtype=float)
    t = pd.DatetimeIndex(drawn["t"])
    return pd.DataFrame({
        "t": t, "direction": draws["direction"].to_numpy(),
        "stop": close_d + stop_atr[which] * atr_d, "target": close_d + target_atr[which] * atr_d,
        "limit": race_limits(drawn, time_limit),
    }, index=draws.index)


def race_limits(rows: pd.DataFrame, time_limit: Union[str, Mapping[str, int]]) -> pd.DatetimeIndex:
    """A race's time limit at each row: its D1 close (17:00 New York), or t + minutes."""
    if time_limit == "day_close":
        return ny_instant(pd.DatetimeIndex(rows["trading_date"]) + pd.Timedelta(days=1), 17 * 60)
    minutes = time_limit["minutes"] if isinstance(time_limit, Mapping) else time_limit.minutes
    return pd.DatetimeIndex(rows["t"]) + pd.Timedelta(minutes=minutes)


# ── naive rules ────────────────────────────────────────────────────────────

def naive_direction(rows: pd.DataFrame, rule: str) -> np.ndarray:
    """LONG / SHORT / None: the rule's call on each row."""
    if rule == "always_long":
        return np.full(len(rows), "LONG", dtype=object)
    if rule not in NAIVE:
        raise ValueError(f"unknown naive rule {rule!r}; known: {NAIVE}")
    return direction_of(rows[rule])


# ── stratified ─────────────────────────────────────────────────────────────

def stratified(features: pd.DataFrame, labels: pd.DataFrame, events: pd.DataFrame,
               candidates: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    """Per event: the hit rate of ``<level>_hit_after`` among ``features``' rows with
    an untaken, known level of the ``candidates`` (all of them pooled), in the
    event's cell of distance decile (in atr_d1) and New York hour."""
    pool = []
    for level in candidates:
        price = features[level].to_numpy(dtype=float)
        atr = features["atr_d1"].to_numpy(dtype=float)
        hit = labels[f"{level}_hit_after"]
        ok = (~np.isnan(price) & ~np.isnan(atr) & features[f"{level}_taken_at"].isna().to_numpy()
              & hit.notna().to_numpy())
        pool.append(pd.DataFrame({
            "distance": np.abs(price - features["close"].to_numpy(dtype=float))[ok] / atr[ok],
            "hour": (features["ny_minute"].to_numpy()[ok] // 60),
            "hit": hit[ok].astype(float).to_numpy(),
        }))
    pool = pd.concat(pool, ignore_index=True)
    sums, counts = np.zeros(len(events)), np.zeros(len(events))
    if pool.empty:
        return sums, counts
    edges = np.quantile(pool["distance"].to_numpy(), np.linspace(0, 1, 11))
    pool["decile"] = _decile(pool["distance"].to_numpy(), edges)
    rates = pool.groupby(["decile", "hour"])["hit"].mean()
    rows = features.loc[events["row"].to_numpy()]
    distance = np.abs(events["level"].to_numpy(dtype=float) - rows["close"].to_numpy(dtype=float)) \
        / rows["atr_d1"].to_numpy(dtype=float)
    deciles, hours = _decile(distance, edges), rows["ny_minute"].to_numpy() // 60
    for i, (decile, hour) in enumerate(zip(deciles, hours)):
        rate = rates.get((decile, hour)) if np.isfinite(distance[i]) else None
        if rate is not None and np.isfinite(rate):
            sums[i], counts[i] = rate, 1.0
    return sums, counts


def _decile(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.clip(np.searchsorted(edges, values, "right") - 1, 0, 9)


# ── shuffled path ──────────────────────────────────────────────────────────

def shuffled_path(frames: Mapping[str, InstrumentFrame], events: pd.DataFrame, of: Filter, given: Optional[Filter],
                  shuffles: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Per event (an instrument and trading date): over ``shuffles`` shuffles of the
    date's M15 bars, the share where ``given`` and ``of`` hold (sum) and where
    ``given`` holds (count), both averaged over the shuffles."""
    by_day = {i: _m15_days(frame) for i, frame in frames.items()}
    sums, counts = np.zeros(len(events)), np.zeros(len(events))
    for i, (instrument, day) in enumerate(zip(events["instrument"], events["trading_date"])):
        bars = by_day[instrument].get(pd.Timestamp(day))
        if bars is None:
            continue
        labels = _shuffled_labels(bars, shuffles, rng)
        held = given.evaluate(labels)[0] if given is not None and given.tree is not None else np.ones(shuffles, bool)
        hits = of.evaluate(labels)[0]
        sums[i], counts[i] = (hits & held).mean(), held.mean()
    return sums, counts


def _m15_days(frame: InstrumentFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    bars = frame.bars[Timeframe.M15]
    cal = calendar_columns(pd.DatetimeIndex(bars["time"]))
    bars = bars.assign(trading_date=cal["trading_date"].to_numpy(), h4_index=cal["h4_index"].to_numpy())
    return {pd.Timestamp(day): part.reset_index(drop=True) for day, part in bars.groupby("trading_date")}


def _shuffled_labels(bars: pd.DataFrame, shuffles: int, rng: np.random.Generator) -> pd.DataFrame:
    o = bars["open"].to_numpy()
    h, l, c = (bars[name].to_numpy() for name in ("high", "low", "close"))
    previous = np.concatenate([[o[0]], c[:-1]])
    move, up, down = c - previous, h - previous, l - previous
    n = len(c)
    order = rng.permuted(np.tile(np.arange(n), (shuffles, 1)), axis=1)
    level_after = o[0] + np.cumsum(move[order], axis=1)
    level_before = np.concatenate([np.full((shuffles, 1), o[0]), level_after[:, :-1]], axis=1)
    highs, lows = level_before + up[order], level_before + down[order]
    h4 = bars["h4_index"].to_numpy()                       # a slot keeps its time, and so its H4 candle
    final = level_after[:, -1]
    return pd.DataFrame({
        "day_dir": np.sign(final - o[0]),
        "day_high_final": highs.max(axis=1), "day_low_final": lows.min(axis=1),
        "day_high_h4": h4[highs.argmax(axis=1)], "day_low_h4": h4[lows.argmin(axis=1)],
    })
