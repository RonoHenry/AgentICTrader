"""Running one hypothesis test: event, filter, measure, baselines, statistics, verdict.

``run_test()`` is the core that ``explore`` and ``run`` share (cli.py). On
one slice of the research tables it:

1. runs the event, then the ``where`` filter over its features and its own
   columns (rows reading a null value are skipped and counted);
2. measures each event (Requirement 8, design "Measures"):
   - ``race``: a race per event (races.py): ``win_rate`` (the mean score),
     ``mean_net_r``, ``mean_gross_r``;
   - ``direction``: whether the move still to come has the event's sign
     (``accuracy``; zero moves skipped and counted) and the signed move in ATR;
   - ``rate``: the share of events where the label condition ``of`` holds,
     among those where ``given`` holds;
   - ``move``: a label column in ATR, signed by the event's direction;
3. computes each baseline the hypothesis uses (baselines.py), per event;
4. bootstraps trading dates (stats.py) for every pass rule, and decides.

Every random draw is seeded from the hypothesis hash and the test's index, so
a rerun reproduces its result exactly (Property 9).

Validates: Requirements 8.4, 10, 11 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from algo_research.baselines import (
    coin_flip,
    naive_direction,
    race_limits,
    random_time_draws,
    rescale_orders,
    shuffled_path,
    stratified,
)
from algo_research.dataset import ResearchData
from algo_research.events import EVENTS, run_event
from algo_research.filters import compile_filter
from algo_research.hypothesis import LEVEL_ALIASES, STATS, Hypothesis, Test, where_columns
from algo_research.labels import LABEL_COLUMNS
from algo_research.races import RaceCosts, run_races
from algo_research.stats import Bootstrap, Outcome, Rule, breakdowns, decide, evaluate_rule, point, series_table

__all__ = ["RunSettings", "TestResult", "run_test"]

_SIGN = {"LONG": 1.0, "SHORT": -1.0}


@dataclass(frozen=True)
class RunSettings:
    resamples: int = 10_000
    random_time_draws: int = 20
    shuffles: int = 200


@dataclass
class TestResult:
    label: str                                   # H002, or H001[at=05:00]
    test: Test
    slice: str
    seed: int
    events: pd.DataFrame                         # the events measured, with their direction and levels
    skipped: dict[str, int]
    table: pd.DataFrame                          # per event: each series' sum and count
    outcomes: list[Outcome]                      # one per pass rule
    stats: dict[str, Outcome]                    # each statistic of the measure, alone
    baselines: dict[str, float]                  # each baseline, for the main statistic
    breakdowns: dict
    verdict: str
    n_events: int
    n_dates: int
    races: Optional[pd.DataFrame] = None
    draws_available: Optional[np.ndarray] = None
    extra: dict = field(default_factory=dict)

    @property
    def main_stat(self) -> str:
        return self.test.hypothesis.pass_.require[0].stat


def run_test(test: Test, data: ResearchData, slice_name: str, costs: Mapping[str, RaceCosts], seed: int,
             settings: RunSettings = RunSettings()) -> TestResult:
    h = test.hypothesis
    features = data.features[data.features["slice"] == slice_name]
    labels = data.labels.loc[features.index]
    event = run_event(features, h.event.name, h.event.params)
    events, skipped = event.rows, dict(event.skipped)
    if h.event.where:
        mask, null = compile_filter(h.event.where, where_columns(EVENTS[h.event.name])).evaluate(
            _where_rows(features, events, EVENTS[h.event.name]))
        skipped["where_null"] = int(null.sum())
        skipped["where_false"] = int((~mask & ~null).sum())
        events = events[mask].reset_index(drop=True)

    kind = h.measure.kind
    measure = {"race": _race, "direction": _direction, "rate": _rate, "move": _move}[kind]
    series, extra = measure(h, events, features, labels, data, costs, seed, settings, skipped)
    table = series_table(events["trading_date"], events["instrument"], series)

    rules = [Rule(r.stat, _versus_keys(h, r.stat, r.versus), label=r.versus, min_effect=r.min_effect)
             for r in h.pass_.require]
    boot = Bootstrap(table, settings.resamples, seed)
    outcomes = [evaluate_rule(table, boot, rule) for rule in rules]
    stats = {s: evaluate_rule(table, boot, Rule(s)) for s in STATS[kind] if f"n:{s}" in table}
    main = h.pass_.require[0].stat
    measured = (table[f"n:{main}"] > 0).to_numpy() if len(table) else np.zeros(0, dtype=bool)
    n_events, n_dates = int(measured.sum()), int(table.loc[measured, "trading_date"].nunique()) if len(table) else 0
    baselines = {b: point(table, f"{b}:{main}") for b in _baseline_names(h) if f"n:{b}:{main}" in table}
    if h.naive_rules and f"n:naive:{h.naive_rules[0]}:{main}" in table:
        baselines["best_naive"] = max(point(table, f"naive:{r}:{main}") for r in h.naive_rules)
    primary = next((rule for rule in rules if rule.versus), rules[0])
    verdict = decide(n_events, n_dates, h.pass_.min_events, h.pass_.min_days, outcomes)
    starved = _starved(h, measured, extra.get("available"), settings.random_time_draws)
    if starved is not None:
        verdict = "INSUFFICIENT"
        extra["starved"] = starved
    return TestResult(
        label=test.label, test=test, slice=slice_name, seed=seed, events=events, skipped=skipped, table=table,
        outcomes=outcomes, stats=stats, baselines=baselines,
        breakdowns=breakdowns(table, primary) if len(table) else {},
        verdict=verdict,
        n_events=n_events, n_dates=n_dates, races=extra.get("races"), draws_available=extra.get("available"),
        extra=extra,
    )


def _starved(h: Hypothesis, measured: np.ndarray, available: Optional[np.ndarray], k: int) -> Optional[tuple]:
    """(mean draws per measured event, K) when a pass rule compares with random_time
    and its draws average under K/2: too few to judge by (Req 10.8). None otherwise."""
    if available is None or not any(r.versus == "random_time" for r in h.pass_.require):
        return None
    mean = float(available[measured].mean()) if measured.any() else 0.0
    return (mean, k) if mean < k / 2 else None


def _where_rows(features: pd.DataFrame, events: pd.DataFrame, event) -> pd.DataFrame:
    """Each event's feature row with the event's own columns laid over it (Req 9.5)."""
    rows = features.loc[events["row"]].reset_index(drop=True)
    for column in event.columns:
        rows[column] = events[column].to_numpy()
    return rows


def _baseline_names(h: Hypothesis) -> list[str]:
    return [b for b in h.baselines.use]


def _versus_keys(h: Hypothesis, stat: str, versus: Optional[str]) -> tuple[str, ...]:
    if versus is None:
        return ()
    if versus == "best_naive":
        return tuple(f"naive:{rule}:{stat}" for rule in h.naive_rules)
    return (f"{versus}:{stat}",)


def _signs(directions) -> np.ndarray:
    return np.array([_SIGN.get(d, np.nan) for d in directions], dtype=float)


# ── race ───────────────────────────────────────────────────────────────────

def _race(h, events, features, labels, data, costs, seed, settings, skipped):
    trade = h.trade
    rows = features.loc[events["row"]]
    direction = events["direction"].to_numpy() if trade.direction == "event" else np.full(len(events), trade.direction)
    sign = _signs(direction)
    close, atr = rows["close"].to_numpy(dtype=float), rows["atr_d1"].to_numpy(dtype=float)

    def level(ref, stop=None):
        if ref.kind == "level":
            return (events[ref.name] if ref.name in events.columns else rows[ref.name]).to_numpy(dtype=float)
        if ref.kind == "atr":
            return close + (-1 if stop is None else 1) * sign * ref.value * atr
        return close + sign * ref.value * np.abs(close - stop)               # r: a multiple of the stop distance

    stop = level(trade.stop)
    target = level(trade.target, stop=stop)
    valid = np.isfinite(stop) & np.isfinite(target) & np.isfinite(sign)
    skipped["null_level"] = int((~valid).sum())
    limits = (pd.DatetimeIndex(events["limit"]) if trade.time_limit == "event"
              else race_limits(rows, trade.time_limit))
    orders = pd.DataFrame({"t": pd.DatetimeIndex(events["t"]), "direction": direction, "stop": stop,
                           "target": target, "limit": limits}, index=events.index)
    races = _run(orders[valid], events["instrument"][valid], data, costs)
    races = races.reindex(events.index)
    races.loc[~valid, "outcome"] = "SKIPPED"
    ok = (races["outcome"].isin(["TARGET", "STOP", "TIMEOUT"])).to_numpy()
    skipped["rejected"] = int((races["outcome"] == "REJECTED").sum())
    ones = ok.astype(float)
    series = {"win_rate": (np.where(ok, races["score"], 0.0), ones),
              "mean_net_r": (np.where(ok, races["net_r"], 0.0), ones),
              "mean_gross_r": (np.where(ok, races["gross_r"], 0.0), ones)}
    if "coin_flip" in h.baselines.use:
        series["coin_flip:win_rate"] = (np.where(ok, races["p_coin"], 0.0), ones)
    extra = {"races": races}
    if "random_time" in h.baselines.use:
        live = events[valid]
        draws = random_time_draws(features, live, settings.random_time_draws, np.random.default_rng([seed, 1]))
        drawn = rescale_orders(features, live, orders.loc[valid, ["stop", "target", "limit"]].reset_index(drop=True),
                               draws.rows, trade.time_limit)
        priced = (np.isfinite(drawn["stop"]) & np.isfinite(drawn["target"])).to_numpy()   # rows without atr_d1
        skipped["draw_null_level"] = int((~priced).sum())
        instruments = features.loc[draws.rows["row"], "instrument"].reset_index(drop=True)
        drawn_races = _run(drawn[priced], instruments[priced], data, costs)
        done = drawn_races["outcome"].isin(["TARGET", "STOP", "TIMEOUT"]).reindex(drawn.index, fill_value=False)
        drawn_races = drawn_races.reindex(drawn.index)
        done = done.to_numpy(dtype=bool)
        event_of = live.index.to_numpy()[draws.rows["event"].to_numpy()]
        for stat, column in (("win_rate", "score"), ("mean_net_r", "net_r"), ("mean_gross_r", "gross_r")):
            values = drawn_races[column].to_numpy(dtype=float)
            series[f"random_time:{stat}"] = _per_event(event_of, np.where(done, values, 0.0),
                                                       done.astype(float), events.index)
        available = np.zeros(len(events), dtype=int)
        available[np.flatnonzero(valid)] = draws.available
        extra["available"] = available
        extra["draw_races"] = drawn_races
    return series, extra


def _run(orders: pd.DataFrame, instruments: pd.Series, data: ResearchData, costs) -> pd.DataFrame:
    parts = []
    for instrument in pd.unique(instruments):
        mine = orders[(instruments == instrument).to_numpy()]
        parts.append(run_races(data.frames[instrument], mine, costs.get(instrument)))
    if not parts:
        empty = pd.DataFrame(np.nan, columns=["score", "net_r", "gross_r", "p_coin"], index=orders.index)
        return empty.assign(outcome=pd.Series(None, index=orders.index, dtype=object))
    return pd.concat(parts).reindex(orders.index)


def _per_event(event_of: np.ndarray, sums: np.ndarray, counts: np.ndarray, index: pd.Index):
    position = pd.Index(index).get_indexer(event_of)
    n = len(index)
    return (np.bincount(position, weights=sums, minlength=n) if n else np.zeros(0),
            np.bincount(position, weights=counts, minlength=n) if n else np.zeros(0))


# ── direction and move ─────────────────────────────────────────────────────

def _moves(h: Hypothesis, rows: pd.DataFrame, at: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """The move still to come at each row (price, for its sign) and in ATR."""
    if h.measure.horizon == "rem":
        return at["rem_move"].to_numpy(dtype=float), at["rem_move_atr"].to_numpy(dtype=float)
    name = h.measure.horizon
    return (at[f"{name}_close"].to_numpy(dtype=float) - rows["close"].to_numpy(dtype=float),
            at[f"{name}_atr"].to_numpy(dtype=float))


def _direction(h, events, features, labels, data, costs, seed, settings, skipped):
    rows, at = features.loc[events["row"]], labels.loc[events["row"]]
    sign = _signs(events["direction"])
    move, move_atr = _moves(h, rows, at)
    valid = np.isfinite(move) & (move != 0)
    skipped["zero_move"] = int((move == 0).sum())
    skipped["null_label"] = int((~np.isfinite(move)).sum())
    ones, with_atr = valid.astype(float), (valid & np.isfinite(move_atr)).astype(float)
    series = {"accuracy": (np.where(valid, np.sign(move) == sign, 0.0).astype(float), ones),
              "mean_move_atr": (np.where(with_atr > 0, sign * move_atr, 0.0), with_atr)}
    for rule in h.naive_rules:
        call = _signs(naive_direction(rows, rule))
        abstain = np.isnan(call)
        series[f"naive:{rule}:accuracy"] = (np.where(valid, np.where(abstain, 0.5, np.sign(move) == call), 0.0)
                                            .astype(float), ones)
        series[f"naive:{rule}:mean_move_atr"] = (np.where(with_atr > 0, np.where(abstain, 0.0, call * move_atr),
                                                          0.0), with_atr)
    extra = {}
    if "random_time" in h.baselines.use:
        series.update(_random_time_moves(h, events, features, labels, seed, settings, valid, extra))
    return series, extra


def _random_time_moves(h, events, features, labels, seed, settings, valid, extra) -> dict:
    live = events[valid]
    draws = random_time_draws(features, live, settings.random_time_draws, np.random.default_rng([seed, 1]))
    drawn_rows = features.loc[draws.rows["row"]]
    move, move_atr = _moves(h, drawn_rows, labels.loc[draws.rows["row"]])
    sign = _signs(draws.rows["direction"])
    ok = np.isfinite(move) & (move != 0)
    ok_atr = ok & np.isfinite(move_atr)
    event_of = live.index.to_numpy()[draws.rows["event"].to_numpy()]
    available = np.zeros(len(events), dtype=int)
    available[np.flatnonzero(valid)] = draws.available
    extra["available"] = available
    out = {"random_time:accuracy": _per_event(event_of, np.where(ok, np.sign(move) == sign, 0.0).astype(float),
                                              ok.astype(float), events.index),
           "random_time:mean_move_atr": _per_event(event_of, np.where(ok_atr, sign * move_atr, 0.0),
                                                   ok_atr.astype(float), events.index)}
    if h.measure.kind == "move":
        column = labels.loc[draws.rows["row"], h.measure.column].to_numpy(dtype=float)
        good = np.isfinite(column)
        out = {"random_time:mean_move_atr": _per_event(event_of, np.where(good, sign * column, 0.0),
                                                       good.astype(float), events.index)}
    return out


def _move(h, events, features, labels, data, costs, seed, settings, skipped):
    column = labels.loc[events["row"], h.measure.column].to_numpy(dtype=float)
    sign = _signs(events["direction"])
    valid = np.isfinite(column) & np.isfinite(sign)
    skipped["null_label"] = int((~valid).sum())
    series = {"mean_move_atr": (np.where(valid, sign * column, 0.0), valid.astype(float))}
    extra = {}
    if "random_time" in h.baselines.use:
        series.update(_random_time_moves(h, events, features, labels, seed, settings, valid, extra))
    return series, extra


# ── rate ───────────────────────────────────────────────────────────────────

def _event_labels(events: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """The labels at each event's row, with the level_hit aliases resolved per row."""
    at = labels.loc[events["row"]].reset_index(drop=True)
    if "level_name" in events.columns:
        for alias in LEVEL_ALIASES:
            suffix = alias.removeprefix("level")
            values = [at.at[i, f"{name}{suffix}"] if isinstance(name, str) else None
                      for i, name in enumerate(events["level_name"])]
            at[alias] = pd.array(values, dtype="boolean") if suffix == "_hit_after" else pd.to_datetime(values, utc=True)
    at.index = events.index
    return at


def _rate(h, events, features, labels, data, costs, seed, settings, skipped):
    at = _event_labels(events, labels)
    names = set(LABEL_COLUMNS) | (set(LEVEL_ALIASES) if "level_name" in events.columns else set())
    of = compile_filter(h.measure.of, names)
    given = compile_filter(h.measure.given or "", names)
    of_mask, of_null = of.evaluate(at)
    given_mask, given_null = given.evaluate(at)
    null = of_null | given_null
    skipped["null_label"] = int(null.sum())
    counts = (given_mask & ~null).astype(float)
    series = {"rate": ((of_mask & given_mask & ~null).astype(float), counts)}
    if "stratified" in h.baselines.use:
        level = h.event.params.get("level")
        candidates = ("pdh", "pdl") if level == "trend" else (level,)
        sums, n = stratified(features, labels, events, candidates)
        series["stratified:rate"] = (sums, n * counts)                     # only where the event itself counts
    if "shuffled_path" in h.baselines.use:
        sums, n = shuffled_path(data.frames, events, of, given if h.measure.given else None, settings.shuffles,
                                np.random.default_rng([seed, 2]))
        keep = ~null
        series["shuffled_path:rate"] = (np.where(keep, sums, 0.0), np.where(keep, n, 0.0))
    return series, {}
