"""
Tests for algo_research/stats.py — the day-cluster bootstrap, the pass rules,
the verdict and the stability breakdowns.

Task 252 (.kiro/specs/algo-research/tasks.md).
Validates: Requirements 11.1-11.5 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algo_research.stats import (
    Bootstrap,
    Rule,
    breakdowns,
    decide,
    evaluate_rule,
    point,
    seed_from,
    series_table,
)

DATES = [date(2025, 7, 1) + timedelta(days=i) for i in range(400)]


def table(values: dict[str, np.ndarray], dates=None, instruments=None, counts: dict[str, np.ndarray] = None):
    """One event per row: each key's value (its sum) and count (1 unless given)."""
    n = len(next(iter(values.values())))
    dates = dates if dates is not None else [DATES[i % len(DATES)] for i in range(n)]
    instruments = instruments if instruments is not None else ["EURUSD"] * n
    return series_table(dates, instruments, {k: (v, (counts or {}).get(k, np.ones(n))) for k, v in values.items()})


def test_constant_series_zero_width_interval():
    t = table({"stat": np.full(500, 0.42)})
    boot = Bootstrap(t, resamples=2000, seed=1)
    outcome = evaluate_rule(t, boot, Rule("stat"))
    assert outcome.estimate == pytest.approx(0.42)
    assert outcome.lo == pytest.approx(0.42) and outcome.hi == pytest.approx(0.42)


def test_independent_dates_match_the_binomial_interval():
    rng = np.random.default_rng(7)
    values = (rng.random(400) < 0.5).astype(float)           # one event per date
    t = table({"stat": values})
    outcome = evaluate_rule(t, Bootstrap(t, resamples=10_000, seed=3), Rule("stat"))
    p, n = values.mean(), len(values)
    half = 1.96 * np.sqrt(p * (1 - p) / n)
    assert outcome.lo == pytest.approx(p - half, abs=0.01)
    assert outcome.hi == pytest.approx(p + half, abs=0.01)


def test_correlated_rows_within_a_date_widen_the_interval():
    # Four instruments moving together on each date carry one date's evidence, not four.
    rng = np.random.default_rng(8)
    per_date = (rng.random(200) < 0.5).astype(float)
    together = table({"stat": np.repeat(per_date, 4)}, dates=np.repeat(DATES[:200], 4))
    alone = table({"stat": (rng.random(800) < 0.5).astype(float)}, dates=[DATES[i % 400] for i in range(800)])
    w_together = evaluate_rule(together, Bootstrap(together, 4000, 1), Rule("stat"))
    w_alone = evaluate_rule(alone, Bootstrap(alone, 4000, 1), Rule("stat"))
    assert (w_together.hi - w_together.lo) > 1.6 * (w_alone.hi - w_alone.lo)


def test_paired_difference_uses_the_same_dates():
    rng = np.random.default_rng(9)
    base = rng.normal(0, 1, 600)
    t = table({"stat": base + 0.25, "base": base})                 # every event 0.25 above its own baseline
    outcome = evaluate_rule(t, Bootstrap(t, 3000, 2), Rule("stat", versus=("base",)))
    assert outcome.estimate == pytest.approx(0.25)
    assert outcome.lo == pytest.approx(0.25) and outcome.hi == pytest.approx(0.25)   # unpaired would be wide
    assert outcome.value == pytest.approx(base.mean() + 0.25) and outcome.baseline == pytest.approx(base.mean())


def test_baseline_with_several_draws_per_event():
    # random_time: K draws per event, attributed to the event's date.
    t = table({"stat": np.ones(100), "random_time": np.full(100, 5.0)},
              counts={"random_time": np.full(100, 20.0)})
    outcome = evaluate_rule(t, Bootstrap(t, 500, 1), Rule("stat", versus=("random_time",)))
    assert outcome.baseline == pytest.approx(0.25) and outcome.estimate == pytest.approx(0.75)


def test_best_naive_rechosen_in_each_resample_never_looser():
    rng = np.random.default_rng(10)
    n = 400
    stat = (rng.random(n) < 0.56).astype(float)
    a = (rng.random(n) < 0.52).astype(float)
    b = (rng.random(n) < 0.52).astype(float)
    t = table({"stat": stat, "naive:a": a, "naive:b": b})
    boot = Bootstrap(t, 5000, 4)
    best = evaluate_rule(t, boot, Rule("stat", versus=("naive:a", "naive:b"), label="best_naive"))
    fixed_key = "naive:a" if point(t, "naive:a") >= point(t, "naive:b") else "naive:b"
    fixed = evaluate_rule(t, boot, Rule("stat", versus=(fixed_key,)))
    assert best.estimate == pytest.approx(fixed.estimate)
    assert best.lo <= fixed.lo + 1e-12
    assert best.versus == "best_naive"


def test_verdict():
    passing = [evaluate_rule(t, Bootstrap(t, 500, 1), Rule("stat", min_effect=0.1))
               for t in [table({"stat": np.full(150, 0.3)})]]
    failing = [evaluate_rule(t, Bootstrap(t, 500, 1), Rule("stat", min_effect=0.3))
               for t in [table({"stat": np.full(150, 0.3)})]]
    assert passing[0].passed and not failing[0].passed            # the bound must be above min_effect
    assert decide(150, 100, min_events=100, min_days=60, outcomes=passing) == "PASS"
    assert decide(150, 100, min_events=100, min_days=60, outcomes=passing + failing) == "FAIL"
    assert decide(99, 100, min_events=100, min_days=60, outcomes=passing) == "INSUFFICIENT"
    assert decide(150, 59, min_events=100, min_days=60, outcomes=passing) == "INSUFFICIENT"
    assert decide(0, 0, min_events=100, min_days=60, outcomes=[]) == "INSUFFICIENT"


def test_breakdowns_per_instrument_quarter_and_weekday():
    n = 300
    dates = [date(2025, 7, 1) + timedelta(days=i) for i in range(n)]
    instruments = ["EURUSD" if i % 3 else "XAUUSD" for i in range(n)]
    stat = np.where(np.array(instruments) == "EURUSD", 1.0, 0.0)
    t = table({"stat": stat, "base": np.full(n, 0.5)}, dates=dates, instruments=instruments)
    parts = breakdowns(t, Rule("stat", versus=("base",)))
    by_instrument = parts["instrument"].set_index("group")
    assert by_instrument.loc["EURUSD", "effect"] == pytest.approx(0.5)
    assert by_instrument.loc["XAUUSD", "effect"] == pytest.approx(-0.5)
    assert by_instrument.loc["EURUSD", "events"] == 200
    assert list(parts["quarter"]["group"]) == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert set(parts["weekday"]["group"]) == {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    assert parts["same_sign_quarters"] == pytest.approx(1.0)      # each quarter's effect is +1/6, like the whole


def test_same_seed_same_result_and_seed_from_hash():
    rng = np.random.default_rng(11)
    t = table({"stat": rng.normal(0, 1, 300)})
    a = evaluate_rule(t, Bootstrap(t, 1000, seed_from("ab" * 32, 0)), Rule("stat"))
    b = evaluate_rule(t, Bootstrap(t, 1000, seed_from("ab" * 32, 0)), Rule("stat"))
    c = evaluate_rule(t, Bootstrap(t, 1000, seed_from("ab" * 32, 1)), Rule("stat"))
    assert (a.lo, a.hi) == (b.lo, b.hi) and (a.lo, a.hi) != (c.lo, c.hi)
    assert seed_from("ab" * 32, 0) == int("ab" * 8, 16)


def test_skipped_events_count_nothing():
    # A row whose count is 0 (a REJECTED race, a zero move) adds nothing to its date.
    t = table({"stat": np.array([1.0, 0.0, 99.0])}, counts={"stat": np.array([1.0, 1.0, 0.0])})
    assert point(t, "stat") == pytest.approx(0.5)


# ── Property 7: duplicates don't shrink intervals ───────────────────────────

@settings(max_examples=100, deadline=None)
@given(st.lists(st.tuples(st.integers(0, 40), st.floats(-5, 5, allow_nan=False)), min_size=2, max_size=120),
       st.integers(0, 2**32 - 1))
def test_property_7_duplicates_dont_shrink_intervals(rows, seed):
    dates = [DATES[d] for d, _ in rows]
    values = np.array([v for _, v in rows])
    once = table({"stat": values}, dates=dates)
    twice = table({"stat": np.concatenate([values, values])}, dates=dates + dates)
    a = evaluate_rule(once, Bootstrap(once, 300, seed), Rule("stat"))
    b = evaluate_rule(twice, Bootstrap(twice, 300, seed), Rule("stat"))
    assert (a.estimate, a.lo, a.hi) == pytest.approx((b.estimate, b.lo, b.hi), rel=1e-12, abs=1e-12)
