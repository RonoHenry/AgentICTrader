"""Statistics: the day-cluster bootstrap, the pass rules and the verdict.

EURUSD and GBPUSD on one morning are close to one observation, so intervals
resample whole trading dates, never rows (Requirement 11):

- each event contributes, per series (the statistic, and each baseline), a
  sum and a count: a race's score and 1; a random-time baseline's K draws
  and K; a skipped event 0 and 0;
- per trading date, the sums and counts of all its instruments' events and
  their baseline draws are added together;
- a resample draws dates with replacement (as multinomial weights, B x
  dates); its statistic is the weighted sum of sums over the weighted sum of
  counts. A difference against a baseline uses the same weights for both,
  date by date (paired). Against the best naive rule, the best is chosen
  again within each resample;
- the interval is the 2.5th and 97.5th percentile of the B resamples.

Duplicating rows within a date doubles its sum and count, so no resample
changes (Property 7). A rule passes when its interval's lower bound is above
its ``min_effect``. The verdict is INSUFFICIENT below the minimum events or
dates, else PASS when every rule passes, else FAIL.

    t = series_table(dates, instruments, {"win_rate": (scores, ones), "coin_flip": (p, ones)})
    boot = Bootstrap(t, resamples=10_000, seed=seed_from(sha256, test_index))
    outcome = evaluate_rule(t, boot, Rule("win_rate", versus=("coin_flip",), label="coin_flip"))

Validates: Requirements 11.1-11.5 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd

__all__ = ["Bootstrap", "Outcome", "Rule", "breakdowns", "decide", "evaluate_rule", "point", "seed_from",
           "series_table"]

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def series_table(dates: Sequence, instruments: Sequence[str],
                 series: Mapping[str, tuple[np.ndarray, np.ndarray]]) -> pd.DataFrame:
    """One row per event: its trading date, instrument, and each series' sum and count."""
    table = pd.DataFrame({"trading_date": pd.to_datetime(pd.Series(list(dates))).dt.normalize(),
                          "instrument": list(instruments)})
    for key, (sums, counts) in series.items():
        sums, counts = np.asarray(sums, dtype=float), np.asarray(counts, dtype=float)
        table[f"sum:{key}"] = np.where(counts > 0, sums, 0.0)
        table[f"n:{key}"] = counts
    return table


def point(table: pd.DataFrame, key: str) -> float:
    total = table[f"n:{key}"].sum()
    return float(table[f"sum:{key}"].sum() / total) if total > 0 else float("nan")


def seed_from(sha256: str, index: int = 0) -> int:
    """The bootstrap and baseline seed: the hypothesis hash's first 8 bytes, plus the test's index."""
    return int(sha256[:16], 16) + index


class Bootstrap:
    """B resamples of the table's trading dates, as multinomial weights."""

    def __init__(self, table: pd.DataFrame, resamples: int, seed: int) -> None:
        self.dates = np.sort(table["trading_date"].unique())
        self.index = np.searchsorted(self.dates, table["trading_date"].to_numpy())
        rng = np.random.default_rng(seed)
        n = len(self.dates)
        self.weights = (rng.multinomial(n, np.full(n, 1.0 / n), size=resamples).astype(float)
                        if n else np.zeros((resamples, 0)))

    def per_date(self, table: pd.DataFrame, key: str) -> tuple[np.ndarray, np.ndarray]:
        n = len(self.dates)
        return (np.bincount(self.index, weights=table[f"sum:{key}"].to_numpy(), minlength=n),
                np.bincount(self.index, weights=table[f"n:{key}"].to_numpy(), minlength=n))

    def ratios(self, table: pd.DataFrame, key: str) -> np.ndarray:
        sums, counts = self.per_date(table, key)
        top, bottom = self.weights @ sums, self.weights @ counts
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(bottom > 0, top / bottom, np.nan)


@dataclass(frozen=True)
class Rule:
    stat: str                              # the statistic's series key
    versus: tuple[str, ...] = ()           # baseline series; several: the best of them (best_naive)
    label: Optional[str] = None            # how the report names the comparison
    min_effect: float = 0.0


@dataclass(frozen=True)
class Outcome:
    stat: str
    versus: Optional[str]
    min_effect: float
    value: float                           # the statistic
    baseline: Optional[float]              # the baseline (the best one, for best_naive)
    estimate: float                        # value - baseline, or value
    lo: float
    hi: float
    passed: bool


def evaluate_rule(table: pd.DataFrame, boot: Bootstrap, rule: Rule) -> Outcome:
    value = point(table, rule.stat)
    stat_r = boot.ratios(table, rule.stat)
    if rule.versus:
        baseline = max(point(table, key) for key in rule.versus)
        best = np.max(np.vstack([boot.ratios(table, key) for key in rule.versus]), axis=0)
        draws, estimate = stat_r - best, value - baseline
    else:
        baseline, draws, estimate = None, stat_r, value
    finite = draws[np.isfinite(draws)]
    lo, hi = (np.percentile(finite, [2.5, 97.5]) if len(finite) else (np.nan, np.nan))
    label = rule.label or (rule.versus[0] if len(rule.versus) == 1 else None)
    return Outcome(stat=rule.stat, versus=label, min_effect=rule.min_effect, value=value, baseline=baseline,
                   estimate=estimate, lo=float(lo), hi=float(hi), passed=bool(np.isfinite(lo) and lo > rule.min_effect))


def decide(n_events: int, n_dates: int, min_events: int, min_days: int, outcomes: Sequence[Outcome]) -> str:
    if n_events < min_events or n_dates < min_days:
        return "INSUFFICIENT"
    return "PASS" if outcomes and all(o.passed for o in outcomes) else "FAIL"


def breakdowns(table: pd.DataFrame, rule: Rule) -> dict:
    """The rule's effect per instrument, calendar quarter and weekday, with counts,
    and the share of quarters whose effect has the overall effect's sign. These
    inform; only the rules decide (Req 11.4)."""
    dates = pd.DatetimeIndex(table["trading_date"])
    groups = {
        "instrument": table["instrument"].to_numpy(),
        "quarter": np.array([f"{d.year}Q{d.quarter}" for d in dates], dtype=object),
        "weekday": np.array([_WEEKDAYS[d.weekday()] for d in dates], dtype=object),
    }
    out: dict = {}
    for name, keys in groups.items():
        rows = []
        for group in sorted(set(keys), key=lambda g: _WEEKDAYS.index(g) if name == "weekday" else g):
            part = table[keys == group]
            value = point(part, rule.stat)
            baseline = max(point(part, k) for k in rule.versus) if rule.versus else None
            rows.append({"group": group, "events": int((part[f"n:{rule.stat}"] > 0).sum()),
                         "dates": int(part["trading_date"].nunique()), "value": value, "baseline": baseline,
                         "effect": value - baseline if baseline is not None else value})
        out[name] = pd.DataFrame(rows, columns=["group", "events", "dates", "value", "baseline", "effect"])
    overall = point(table, rule.stat) - (max(point(table, k) for k in rule.versus) if rule.versus else 0.0)
    quarters = out["quarter"]["effect"].dropna()
    out["same_sign_quarters"] = (float((np.sign(quarters) == np.sign(overall)).mean())
                                 if len(quarters) and np.isfinite(overall) else float("nan"))
    return out
